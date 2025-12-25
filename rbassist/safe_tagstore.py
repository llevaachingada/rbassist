"""
Safe tag storage with namespace separation.
Research-backed implementation preventing AI/user tag collision.

This module provides a safety layer that separates:
- USER TAGS: Manually assigned tags (sacred, never modified by AI)
- AI SUGGESTIONS: AI-generated suggestions (can be accepted/rejected)
"""

from __future__ import annotations

import json
import pathlib
from datetime import datetime
from enum import Enum
from typing import Dict, List, Set

import yaml

from .utils import console, load_meta, save_meta

_CONFIG_DIR = pathlib.Path(__file__).resolve().parents[1] / "config"
_USER_TAGS = _CONFIG_DIR / "my_tags.yml"
_AI_SUGGESTIONS = _CONFIG_DIR / "ai_suggestions.json"
_CORRECTION_LOG = _CONFIG_DIR / "tag_corrections.json"


class TagNamespace(Enum):
    """Namespace for tag ownership"""

    USER = "user"
    AI = "ai"


class TagSource(Enum):
    """Where did this tag come from?"""

    REKORDBOX_IMPORT = "rekordbox"
    USER_MANUAL = "manual"
    AI_SUGGESTED = "ai_suggestion"
    AI_ACCEPTED = "ai_accepted"


class TagPermissionError(Exception):
    """Raised when attempting unsafe tag operations"""

    pass


# ============================================================================
# USER TAGS (Sacred - Never Modified by AI)
# ============================================================================


def load_user_tags() -> Dict[str, List[str]]:
    """Load user-owned tags from my_tags.yml"""
    if not _USER_TAGS.exists():
        return {}
    try:
        data = yaml.safe_load(_USER_TAGS.read_text("utf-8")) or {}
        return data.get("tracks", {})
    except Exception as e:
        console.print(f"[red]Error loading user tags: {e}")
        return {}


def save_user_tags(tags: Dict[str, List[str]]) -> None:
    """Save user tags (PROTECTED)"""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "version": "1.0",
        "last_modified": datetime.utcnow().isoformat(),
        "tracks": tags,
    }
    _USER_TAGS.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def add_user_tag(
    track: str, tag: str, source: TagSource = TagSource.USER_MANUAL
) -> None:
    """Add a tag to user namespace (SAFE)"""
    if source == TagSource.AI_SUGGESTED:
        raise TagPermissionError(
            "AI cannot directly write to user tags. Use accept_ai_suggestion()."
        )

    tags = load_user_tags()
    track_tags = set(tags.get(track, []))
    track_tags.add(tag)
    tags[track] = sorted(track_tags)
    save_user_tags(tags)

    # Also update meta.json
    meta = load_meta()
    info = meta["tracks"].setdefault(track, {})
    info["mytags"] = sorted(track_tags)
    save_meta(meta)


def remove_user_tag(track: str, tag: str) -> None:
    """Remove tag from user namespace"""
    tags = load_user_tags()
    if track in tags and tag in tags[track]:
        tags[track] = [t for t in tags[track] if t != tag]
        if not tags[track]:
            del tags[track]
        save_user_tags(tags)

        # Sync meta.json
        meta = load_meta()
        if track in meta["tracks"]:
            meta["tracks"][track]["mytags"] = tags.get(track, [])
            save_meta(meta)


def get_user_tags(track: str) -> List[str]:
    """Get user tags for a track"""
    return load_user_tags().get(track, [])


# ============================================================================
# AI SUGGESTIONS (Separate - Can Be Accepted/Rejected)
# ============================================================================


def load_ai_suggestions() -> Dict[str, Dict[str, float]]:
    """
    Load AI suggestions.
    Format: {track_path: {tag: confidence_score}}
    """
    if not _AI_SUGGESTIONS.exists():
        return {}
    try:
        data = json.loads(_AI_SUGGESTIONS.read_text("utf-8"))
        return data.get("suggestions", {})
    except Exception:
        return {}


def save_ai_suggestions(suggestions: Dict[str, Dict[str, float]]) -> None:
    """Save AI suggestions"""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "version": "1.0",
        "generated": datetime.utcnow().isoformat(),
        "suggestions": suggestions,
    }
    _AI_SUGGESTIONS.write_text(json.dumps(data, indent=2), encoding="utf-8")


def add_ai_suggestion(track: str, tag: str, confidence: float) -> None:
    """AI adds a suggestion (SAFE - separate namespace)"""
    suggestions = load_ai_suggestions()
    if track not in suggestions:
        suggestions[track] = {}
    suggestions[track][tag] = confidence
    save_ai_suggestions(suggestions)


def bulk_add_ai_suggestions(
    suggestions_dict: Dict[str, Dict[str, float]]
) -> int:
    """Bulk add AI suggestions. Returns count of tracks updated."""
    if not suggestions_dict:
        return 0

    existing = load_ai_suggestions()
    count = 0
    for track, tag_scores in suggestions_dict.items():
        if track not in existing:
            existing[track] = {}
        existing[track].update(tag_scores)
        count += 1

    save_ai_suggestions(existing)
    return count


def get_ai_suggestions(track: str, min_confidence: float = 0.0) -> Dict[str, float]:
    """Get AI suggestions for a track"""
    all_sugg = load_ai_suggestions()
    track_sugg = all_sugg.get(track, {})
    return {tag: conf for tag, conf in track_sugg.items() if conf >= min_confidence}


def get_all_ai_suggestions(min_confidence: float = 0.0) -> Dict[str, Dict[str, float]]:
    """Get all AI suggestions across library"""
    all_sugg = load_ai_suggestions()
    if min_confidence <= 0.0:
        return all_sugg

    filtered = {}
    for track, tag_scores in all_sugg.items():
        filtered_scores = {
            tag: score for tag, score in tag_scores.items() if score >= min_confidence
        }
        if filtered_scores:
            filtered[track] = filtered_scores
    return filtered


def clear_ai_suggestions(track: str) -> None:
    """Clear all AI suggestions for a track"""
    suggestions = load_ai_suggestions()
    if track in suggestions:
        del suggestions[track]
        save_ai_suggestions(suggestions)


def clear_all_ai_suggestions() -> int:
    """Clear all AI suggestions. Returns count of tracks cleared."""
    suggestions = load_ai_suggestions()
    count = len(suggestions)
    save_ai_suggestions({})
    return count


# ============================================================================
# USER FEEDBACK (Learn from Decisions)
# ============================================================================


def load_correction_history() -> List[Dict]:
    """Load history of user corrections"""
    if not _CORRECTION_LOG.exists():
        return []
    try:
        return json.loads(_CORRECTION_LOG.read_text("utf-8"))
    except Exception:
        return []


def save_correction_history(history: List[Dict]) -> None:
    """Save correction history"""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _CORRECTION_LOG.write_text(json.dumps(history, indent=2), encoding="utf-8")


def accept_ai_suggestion(track: str, tag: str) -> None:
    """
    User accepts an AI suggestion.
    This is the ONLY way AI suggestions become user tags.
    """
    # Get the suggestion
    suggestions = load_ai_suggestions()
    if track not in suggestions or tag not in suggestions[track]:
        raise ValueError(f"No AI suggestion for tag '{tag}' on track '{track}'")

    confidence = suggestions[track][tag]

    # Log the acceptance
    history = load_correction_history()
    history.append(
        {
            "timestamp": datetime.utcnow().isoformat(),
            "track": track,
            "action": "accepted",
            "tag": tag,
            "confidence": confidence,
        }
    )
    save_correction_history(history)

    # Move to user tags
    add_user_tag(track, tag, source=TagSource.AI_ACCEPTED)

    # Remove from suggestions
    del suggestions[track][tag]
    if not suggestions[track]:
        del suggestions[track]
    save_ai_suggestions(suggestions)


def reject_ai_suggestion(track: str, tag: str, reason: str | None = None) -> None:
    """User rejects an AI suggestion (learn from this)"""
    suggestions = load_ai_suggestions()
    if track not in suggestions or tag not in suggestions[track]:
        return  # Already removed or never existed

    confidence = suggestions[track][tag]

    # Log the rejection
    history = load_correction_history()
    history.append(
        {
            "timestamp": datetime.utcnow().isoformat(),
            "track": track,
            "action": "rejected",
            "tag": tag,
            "confidence": confidence,
            "reason": reason,
        }
    )
    save_correction_history(history)

    # Remove from suggestions
    del suggestions[track][tag]
    if not suggestions[track]:
        del suggestions[track]
    save_ai_suggestions(suggestions)


def bulk_accept_suggestions(track_tags: Dict[str, List[str]]) -> int:
    """Accept multiple suggestions at once. Returns count accepted."""
    count = 0
    for track, tags in track_tags.items():
        for tag in tags:
            try:
                accept_ai_suggestion(track, tag)
                count += 1
            except ValueError:
                pass  # Suggestion doesn't exist, skip
    return count


# ============================================================================
# COMBINED VIEWS (Read-Only)
# ============================================================================


def get_all_tags(track: str) -> Dict[str, str]:
    """
    Get all tags for a track with their source.
    Returns: {tag: "user" | "ai"}
    """
    result = {}

    # User tags
    for tag in get_user_tags(track):
        result[tag] = "user"

    # AI suggestions
    for tag in get_ai_suggestions(track):
        result[tag] = "ai"

    return result


def get_all_user_tags() -> Set[str]:
    """Get set of all unique user tags across library"""
    tags = load_user_tags()
    return set(tag for track_tags in tags.values() for tag in track_tags)


def get_correction_stats() -> Dict[str, int]:
    """Get statistics on user corrections"""
    history = load_correction_history()
    return {
        "total": len(history),
        "accepted": sum(1 for h in history if h["action"] == "accepted"),
        "rejected": sum(1 for h in history if h["action"] == "rejected"),
    }


def get_suggestion_stats() -> Dict[str, int]:
    """Get statistics on pending AI suggestions"""
    suggestions = load_ai_suggestions()
    total_suggestions = sum(len(tags) for tags in suggestions.values())
    return {
        "tracks_with_suggestions": len(suggestions),
        "total_suggestions": total_suggestions,
    }


# ============================================================================
# IMPORT FROM OLD SYSTEM (Migration)
# ============================================================================


def migrate_from_old_tagstore() -> Dict[str, int]:
    """
    One-time migration from old tagstore.py system.
    All existing tags become USER tags.

    Returns: {"tracks_migrated": count, "tags_migrated": count}
    """
    from . import tagstore as old_store

    console.print("[yellow]Migrating tags from old system...")

    # Load old config
    try:
        old_config = old_store._read_config()
        old_library = old_config.get("library", {})
    except Exception as e:
        console.print(f"[red]Migration failed: {e}")
        return {"tracks_migrated": 0, "tags_migrated": 0}

    if not old_library:
        console.print("[yellow]No tags to migrate")
        return {"tracks_migrated": 0, "tags_migrated": 0}

    # Convert to new format
    new_tags = {}
    total_tags = 0
    for track, tags in old_library.items():
        if tags:
            new_tags[track] = sorted(set(tags))
            total_tags += len(new_tags[track])

    # Save as user tags
    save_user_tags(new_tags)

    # Update meta.json
    meta = load_meta()
    for track, tags in new_tags.items():
        info = meta["tracks"].setdefault(track, {})
        info["mytags"] = tags
    save_meta(meta)

    track_count = len(new_tags)
    console.print(f"[green]✓ Migrated {track_count} tracks with {total_tags} tags")
    console.print(f"[green]✓ All existing tags are now USER tags (protected)")
    console.print(
        f"[yellow]⚠ Old tags.yml is still in config/ - you can delete it after verifying"
    )

    return {"tracks_migrated": track_count, "tags_migrated": total_tags}


# ============================================================================
# VALIDATION
# ============================================================================


def validate_tag_safety() -> List[str]:
    """
    Run safety checks. Returns list of issues found.
    """
    issues = []

    # Check 1: AI suggestions should not overlap with user tags
    user_tags = load_user_tags()
    ai_sugg = load_ai_suggestions()

    for track in ai_sugg:
        if track in user_tags:
            user_set = set(user_tags[track])
            ai_set = set(ai_sugg[track].keys())
            overlap = user_set & ai_set
            if overlap:
                issues.append(
                    f"Track {track}: AI suggestions overlap with user tags: {overlap}"
                )

    # Check 2: Files should exist and be readable
    for file, name in [
        (_USER_TAGS, "User tags"),
        (_AI_SUGGESTIONS, "AI suggestions"),
    ]:
        if file.exists():
            try:
                file.read_text("utf-8")
            except Exception as e:
                issues.append(f"{name} file corrupted: {e}")

    return issues
