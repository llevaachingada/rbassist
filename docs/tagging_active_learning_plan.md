# Tagging + Active Learning Integration Plan (Ready-to-Implement)

This document captures the full code plan and install steps for the improved MyTags system with AI suggestions, active learning, and user-style modeling. No code is executed or installed yet; use this as a checklist to roll out quickly.

## Overview

- Keep MERT embeddings + centroid tag profiles (prototypical networks).
- Add namespaces: user tags vs. AI suggestions (accept/reject moves suggestions into user tags).
- Add active learning (margin/entropy/least-confidence) to pick “teach me” tracks.
- Optional: user style model to bias suggestions based on past corrections.

## Ready-to-drop code (from prior draft)

Below are the concrete code blocks to add when you roll this out. They are **not** installed or referenced yet; copy them into new modules when ready.

### `rbassist/safe_tagstore.py`
```python
"""
Safe tag storage with namespace separation: user tags vs AI suggestions.
"""

from __future__ import annotations
import pathlib, json, yaml
from enum import Enum
from datetime import datetime
from typing import Dict, List, Set
from .utils import load_meta, save_meta, console

_CONFIG_DIR = pathlib.Path(__file__).resolve().parents[1] / "config"
_USER_TAGS = _CONFIG_DIR / "my_tags.yml"
_AI_SUGGESTIONS = _CONFIG_DIR / "ai_suggestions.json"
_CORRECTION_LOG = _CONFIG_DIR / "tag_corrections.json"

class TagNamespace(Enum):
    USER = "user"
    AI = "ai"

class TagSource(Enum):
    REKORDBOX_IMPORT = "rekordbox"
    USER_MANUAL = "manual"
    AI_SUGGESTED = "ai_suggestion"
    AI_ACCEPTED = "ai_accepted"

class TagPermissionError(Exception):
    pass

# ----- User tags (protected) -----
def load_user_tags() -> Dict[str, List[str]]:
    if not _USER_TAGS.exists():
        return {}
    try:
        data = yaml.safe_load(_USER_TAGS.read_text("utf-8")) or {}
        return data.get("tracks", {})
    except Exception as e:
        console.print(f"[red]Error loading user tags: {e}")
        return {}

def save_user_tags(tags: Dict[str, List[str]]) -> None:
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"version": "1.0", "last_modified": datetime.utcnow().isoformat(), "tracks": tags}
    _USER_TAGS.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

def add_user_tag(track: str, tag: str, source: TagSource = TagSource.USER_MANUAL) -> None:
    if source == TagSource.AI_SUGGESTED:
        raise TagPermissionError("AI cannot write user tags directly.")
    tags = load_user_tags()
    current = set(tags.get(track, []))
    current.add(tag)
    tags[track] = sorted(current)
    save_user_tags(tags)
    meta = load_meta()
    info = meta["tracks"].setdefault(track, {})
    info["mytags"] = tags[track]
    save_meta(meta)

def remove_user_tag(track: str, tag: str) -> None:
    tags = load_user_tags()
    if track in tags and tag in tags[track]:
        tags[track] = [t for t in tags[track] if t != tag]
        if not tags[track]:
            del tags[track]
        save_user_tags(tags)
        meta = load_meta()
        if track in meta["tracks"]:
            meta["tracks"][track]["mytags"] = tags.get(track, [])
            save_meta(meta)

def get_user_tags(track: str) -> List[str]:
    return load_user_tags().get(track, [])

# ----- AI suggestions (separate) -----
def load_ai_suggestions() -> Dict[str, Dict[str, float]]:
    if not _AI_SUGGESTIONS.exists():
        return {}
    try:
        return json.loads(_AI_SUGGESTIONS.read_text("utf-8"))
    except Exception:
        return {}

def save_ai_suggestions(suggestions: Dict[str, Dict[str, float]]) -> None:
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"version": "1.0", "generated": datetime.utcnow().isoformat(), "suggestions": suggestions}
    _AI_SUGGESTIONS.write_text(json.dumps(payload, indent=2), encoding="utf-8")

def add_ai_suggestion(track: str, tag: str, confidence: float) -> None:
    suggestions = load_ai_suggestions()
    suggestions.setdefault(track, {})[tag] = float(confidence)
    save_ai_suggestions(suggestions)

def get_ai_suggestions(track: str, min_confidence: float = 0.0) -> Dict[str, float]:
    sugg = load_ai_suggestions().get(track, {})
    return {k: v for k, v in sugg.items() if v >= min_confidence}

def clear_ai_suggestions(track: str) -> None:
    suggestions = load_ai_suggestions()
    if track in suggestions:
        del suggestions[track]
        save_ai_suggestions(suggestions)

# ----- Accept / reject flow -----
def load_correction_history() -> List[Dict]:
    if not _CORRECTION_LOG.exists():
        return []
    try:
        return json.loads(_CORRECTION_LOG.read_text("utf-8"))
    except Exception:
        return []

def save_correction_history(history: List[Dict]) -> None:
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _CORRECTION_LOG.write_text(json.dumps(history, indent=2), encoding="utf-8")

def accept_ai_suggestion(track: str, tag: str) -> None:
    suggestions = load_ai_suggestions()
    if track not in suggestions or tag not in suggestions[track]:
        raise ValueError(f"No AI suggestion for {tag} on {track}")
    confidence = suggestions[track][tag]
    history = load_correction_history()
    history.append({"timestamp": datetime.utcnow().isoformat(), "track": track, "action": "accepted", "tag": tag, "confidence": confidence})
    save_correction_history(history)
    add_user_tag(track, tag, source=TagSource.AI_ACCEPTED)
    del suggestions[track][tag]
    if not suggestions[track]:
        del suggestions[track]
    save_ai_suggestions(suggestions)

def reject_ai_suggestion(track: str, tag: str, reason: str | None = None) -> None:
    suggestions = load_ai_suggestions()
    if track not in suggestions or tag not in suggestions[track]:
        return
    confidence = suggestions[track][tag]
    history = load_correction_history()
    history.append({"timestamp": datetime.utcnow().isoformat(), "track": track, "action": "rejected", "tag": tag, "confidence": confidence, "reason": reason})
    save_correction_history(history)
    del suggestions[track][tag]
    if not suggestions[track]:
        del suggestions[track]
    save_ai_suggestions(suggestions)

# ----- Combined views / migration / validation -----
def get_all_tags(track: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for tag in get_user_tags(track):
        out[tag] = "user"
    for tag in get_ai_suggestions(track):
        out[tag] = "ai"
    return out

def get_all_user_tags() -> Set[str]:
    tags = load_user_tags()
    return set(tag for tlist in tags.values() for tag in tlist)

def get_correction_stats() -> Dict[str, int]:
    history = load_correction_history()
    return {
        "total": len(history),
        "accepted": sum(1 for h in history if h["action"] == "accepted"),
        "rejected": sum(1 for h in history if h["action"] == "rejected"),
    }

def migrate_from_old_tagstore() -> None:
    from . import tagstore as old_store
    console.print("[yellow]Migrating tags from old system...")
    try:
        old_cfg = old_store._read_config()
        old_lib = old_cfg.get("library", {})
    except Exception as e:
        console.print(f"[red]Migration failed: {e}")
        return
    new_tags = {p: sorted(set(tags)) for p, tags in old_lib.items() if tags}
    save_user_tags(new_tags)
    meta = load_meta()
    for p, tags in new_tags.items():
        meta["tracks"].setdefault(p, {})["mytags"] = tags
    save_meta(meta)
    console.print(f"[green]✓ Migrated {len(new_tags)} tracks into user tags")

def validate_tag_safety() -> List[str]:
    issues: List[str] = []
    user_tags = load_user_tags()
    ai_sugg = load_ai_suggestions()
    for track in ai_sugg:
        if track in user_tags:
            overlap = set(user_tags[track]) & set(ai_sugg[track].keys())
            if overlap:
                issues.append(f"{track}: AI suggestions overlap user tags: {overlap}")
    for file, name in [(_USER_TAGS, "User tags"), (_AI_SUGGESTIONS, "AI suggestions")]:
        if file.exists():
            try:
                file.read_text("utf-8")
            except Exception as e:
                issues.append(f"{name} file corrupted: {e}")
    return issues
```

### `rbassist/active_learning.py`
```python
"""
Active learning for tagging: margin / entropy / least-confidence.
"""

from __future__ import annotations
import numpy as np
from typing import Dict, List, Tuple
from dataclasses import dataclass
from .tag_model import TagProfile

@dataclass
class UncertainTrack:
    path: str
    uncertainty_score: float
    top_tags: List[Tuple[str, float]]
    reason: str

def _margin(scores: List[float]) -> float:
    if len(scores) < 2:
        return 1.0
    s = sorted(scores, reverse=True)
    return s[0] - s[1]

def _entropy(scores: List[float]) -> float:
    if not scores:
        return 0.0
    arr = np.array(scores, dtype=float)
    if arr.sum() == 0:
        return 0.0
    probs = arr / arr.sum()
    return float(-np.sum(probs * np.log(probs + 1e-10)))

def _least_conf(scores: List[float]) -> float:
    if not scores:
        return 1.0
    return 1.0 - max(scores)

def _score_all(vec: np.ndarray, profiles: Dict[str, TagProfile]) -> Dict[str, float]:
    out = {}
    for tag, profile in profiles.items():
        out[tag] = profile.score(vec)
    return out

def suggest_tracks_to_tag(
    untagged_tracks: List[str],
    profiles: Dict[str, TagProfile],
    embeddings: Dict[str, np.ndarray],
    strategy: str = "margin",
    top_k: int = 10,
) -> List[UncertainTrack]:
    if not profiles:
        return []
    uncertain: List[UncertainTrack] = []
    for track in untagged_tracks:
        if track not in embeddings:
            continue
        scores = _score_all(embeddings[track], profiles)
        if not scores:
            continue
        vals = list(scores.values())
        if strategy == "margin":
            unc = 1.0 - _margin(vals)
            reason = "Close call between top tags"
        elif strategy == "entropy":
            unc = _entropy(vals)
            reason = "Uncertain across many tags"
        elif strategy == "least_confidence":
            unc = _least_conf(vals)
            reason = "Low confidence in all tags"
        else:
            raise ValueError(f"Unknown strategy: {strategy}")
        top_tags = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]
        uncertain.append(UncertainTrack(track, unc, top_tags, reason))
    uncertain.sort(key=lambda x: x.uncertainty_score, reverse=True)
    return uncertain[:top_k]

def explain_uncertainty(track: UncertainTrack) -> str:
    if not track.top_tags:
        return "No scores"
    top_tag, top_score = track.top_tags[0]
    if track.reason == "Close call between top tags" and len(track.top_tags) > 1:
        second_tag, second_score = track.top_tags[1]
        return f"{top_tag} ({top_score:.0%}) vs {second_tag} ({second_score:.0%}) — which is it?"
    if track.reason == "Uncertain across many tags":
        tags_str = ", ".join(f"{t} ({s:.0%})" for t, s in track.top_tags)
        return f"Could be any of: {tags_str}"
    return f"Best guess {top_tag} ({top_score:.0%}) but low confidence"
```

### `rbassist/user_model.py` (optional skeleton)
```python
"""
User tagging style model: track corrections and simple preferences.
"""

from __future__ import annotations
import json, pathlib
from collections import Counter
from datetime import datetime
from typing import Dict, List, Tuple

_CFG = pathlib.Path(__file__).resolve().parents[1] / "config" / "user_style.json"

class UserTaggingStyle:
    def __init__(self) -> None:
        self.history: List[Dict] = []
        self.tag_choices: Counter[str] = Counter()
        self._load()

    def _load(self) -> None:
        if _CFG.exists():
            try:
                data = json.loads(_CFG.read_text("utf-8"))
                self.history = data.get("history", [])
                self.tag_choices = Counter(data.get("tag_choices", {}))
            except Exception:
                self.history = []
                self.tag_choices = Counter()

    def _save(self) -> None:
        payload = {
            "history": self.history,
            "tag_choices": dict(self.tag_choices),
            "updated": datetime.utcnow().isoformat(),
        }
        _CFG.parent.mkdir(parents=True, exist_ok=True)
        _CFG.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def record_correction(self, track: str, ai_tag: str, user_tag: str) -> None:
        self.history.append({
            "track": track,
            "ai_tag": ai_tag,
            "user_tag": user_tag,
            "ts": datetime.utcnow().isoformat(),
        })
        self.tag_choices[user_tag] += 1
        self._save()

    def preferred_between(self, tag_a: str, tag_b: str) -> str | None:
        ca, cb = self.tag_choices[tag_a], self.tag_choices[tag_b]
        if ca == cb:
            return None
        return tag_a if ca > cb else tag_b
```

## Files to add

### 1) `rbassist/safe_tagstore.py`
- Purpose: separate user tags and AI suggestions; log accepts/rejects; migrate old tags.
- Key pieces:
  - Paths: `config/my_tags.yml`, `config/ai_suggestions.json`, `config/tag_corrections.json`.
  - User tags API: `load_user_tags()`, `save_user_tags()`, `add_user_tag()`, `remove_user_tag()`, `get_user_tags()`.
  - AI suggestions API: `load_ai_suggestions()`, `save_ai_suggestions()`, `add_ai_suggestion()`, `get_ai_suggestions()`, `clear_ai_suggestions()`.
  - Accept/reject: `accept_ai_suggestion(track, tag)`, `reject_ai_suggestion(track, tag, reason=None)` (logs to corrections, moves accepted tags into user namespace).
  - Migration: `migrate_from_old_tagstore()` to pull tags from current `tagstore` config into user tags.
  - Validation: `validate_tag_safety()` to detect overlaps/corruption.
  - Guardrails: TagPermissionError if AI tries to write directly into user tags.

### 2) `rbassist/active_learning.py`
- Purpose: uncertainty sampling to pick the most informative untagged tracks.
- Key pieces:
  - Strategies: margin (top-2 gap), entropy (distribution spread), least-confidence (1 - max score).
  - Data class: `UncertainTrack(path, uncertainty_score, top_tags, reason)`.
  - Functions: `suggest_tracks_to_tag(untagged_tracks, profiles, embeddings, strategy="margin", top_k=10)`, `explain_uncertainty(track)`, `diversity_sample(...)`.
  - Uses existing `TagProfile.score` and embeddings loaded from meta.

### 3) (Optional) `rbassist/user_model.py`
- Purpose: track user correction history and simple preferences between tags.
- Key pieces:
  - Store a small JSON under `config` for correction history and preferences.
  - Methods to update preferences when user accepts/rejects suggestions.
  - Optional helper: bias suggestion ordering using past choices (simple counters).

## Existing files to touch

### `rbassist/tag_model.py`
- Add optional confidence/uncertainty outputs (e.g., normalized scores) to surface in UI.
- Optionally expose a helper to get embeddings for tracks (`_load_embedding`) for active learning.

### `rbassist/tagstore.py`
- Keep as-is for legacy, but add a note to migrate to `safe_tagstore` once rolled out.

### `rbassist/ui/pages/tagging.py` (UI integration)
- Add a “Teach me” panel:
  - Button: “Find uncertain tracks” (strategy selector: margin/entropy/least-confidence).
  - List top-N uncertain untagged tracks with reasons and top tag scores.
  - “Score & suggest” button to regenerate AI suggestions for those tracks.
- AI Suggestions panel:
  - Show suggestions per track (tag + confidence).
  - Accept -> calls `accept_ai_suggestion`; Reject -> `reject_ai_suggestion`.
  - Reflect changes immediately in user tags and suggestions list.
- Ensure user tags and AI suggestions are displayed separately; user tags remain read-only to AI.

### `rbassist/ui/pages/tools.py` or `settings.py`
- Add a one-time “Migrate legacy tags” button to call `migrate_from_old_tagstore()`.
- Add a “Validate tag safety” button to run `validate_tag_safety()` and show issues.

## Installation (when ready)

- Core dependencies already present. Optional:
  - Add to `pyproject.toml` deps: `scikit-learn>=1.3.0` (only if you want helper metrics; margin/entropy can be pure numpy).
  - No other heavy deps required.

## Rollout steps (when implementing)

1) Add new files: `safe_tagstore.py`, `active_learning.py` (and optional `user_model.py`).
2) Wire Tagging UI to show uncertain tracks and accept/reject flow.
3) Add migration + validation buttons.
4) (Optional) Add a small CLI entry for migration/validation (`rbassist tags-migrate`, `rbassist tags-validate`).
5) Test: migrate tags, generate suggestions, accept/reject, ensure user tags untouched by AI unless accepted.

## Why this path

- Matches research-backed few-shot tagging (prototypical networks) you already use.
- Active learning + user/AI namespaces give you immediate quality and safety benefits without heavy training.
- Low complexity, minimal dependencies, fast to ship.
