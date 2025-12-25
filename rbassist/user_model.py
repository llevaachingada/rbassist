"""
User tagging style model.
Learn individual preferences and improve over time.

Research basis:
- "Personalized Music Organization" (CHI 2024)
- "Learning User Preferences" (UMAP 2023)
- "Collaborative Filtering for Music Recommendation" (2019)
"""

from __future__ import annotations

import json
import pathlib
from collections import Counter, defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

_CONFIG_DIR = pathlib.Path(__file__).resolve().parents[1] / "config"
_USER_PROFILE = _CONFIG_DIR / "user_profile.json"


class UserTaggingStyle:
    """Learn individual user's tagging patterns"""

    def __init__(self):
        self.tag_preferences: Dict[str, int] = {}  # tag -> usage count
        self.tag_pairs: Dict[Tuple[str, str], int] = {}  # (tag1, tag2) -> co-occurrence
        self.correction_history: List[Dict] = []
        self.tag_substitutions: Dict[str, str] = {}  # ai_tag -> preferred_user_tag

    @classmethod
    def load(cls) -> UserTaggingStyle:
        """Load user style profile from disk"""
        model = cls()

        if not _USER_PROFILE.exists():
            return model

        try:
            data = json.loads(_USER_PROFILE.read_text("utf-8"))
            model.tag_preferences = data.get("tag_preferences", {})
            # Convert tuple keys from JSON
            model.tag_pairs = {
                tuple(json.loads(k)): v for k, v in data.get("tag_pairs", {}).items()
            }
            model.correction_history = data.get("correction_history", [])
            model.tag_substitutions = data.get("tag_substitutions", {})
        except Exception:
            pass  # Return empty model on error

        return model

    def save(self) -> None:
        """Save user style profile to disk"""
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        # Convert tuple keys to JSON strings
        tag_pairs_serializable = {
            json.dumps(k): v for k, v in self.tag_pairs.items()
        }

        data = {
            "version": "1.0",
            "last_updated": datetime.utcnow().isoformat(),
            "tag_preferences": self.tag_preferences,
            "tag_pairs": tag_pairs_serializable,
            "correction_history": self.correction_history,
            "tag_substitutions": self.tag_substitutions,
        }

        _USER_PROFILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def update_from_user_tags(
        self, track: str, tags: List[str], timestamp: Optional[str] = None
    ) -> None:
        """Learn from user manually adding tags"""
        if timestamp is None:
            timestamp = datetime.utcnow().isoformat()

        # Update individual tag frequencies
        for tag in tags:
            self.tag_preferences[tag] = self.tag_preferences.get(tag, 0) + 1

        # Update tag co-occurrence (which tags appear together)
        for i, tag1 in enumerate(tags):
            for tag2 in tags[i + 1 :]:
                pair = tuple(sorted([tag1, tag2]))
                self.tag_pairs[pair] = self.tag_pairs.get(pair, 0) + 1

    def update_from_correction(
        self, track: str, ai_tag: str, user_tag: str, timestamp: Optional[str] = None
    ) -> None:
        """Learn from when user corrects AI"""
        if timestamp is None:
            timestamp = datetime.utcnow().isoformat()

        self.correction_history.append(
            {
                "track": track,
                "ai_suggested": ai_tag,
                "user_chose": user_tag,
                "timestamp": timestamp,
            }
        )

        # Learn substitution pattern
        if ai_tag != user_tag:
            # Track how often user prefers user_tag when AI suggests ai_tag
            self.tag_substitutions[ai_tag] = user_tag

    def predict_preference(self, tag_a: str, tag_b: str) -> Optional[str]:
        """
        Between two similar tags, which would user choose?
        Returns preferred tag or None if no preference.
        """
        freq_a = self.tag_preferences.get(tag_a, 0)
        freq_b = self.tag_preferences.get(tag_b, 0)

        if freq_a == freq_b:
            return None

        return tag_a if freq_a > freq_b else tag_b

    def get_complementary_tags(self, existing_tags: List[str]) -> List[str]:
        """
        Given some tags on a track, suggest other tags that often appear with them.
        """
        if not existing_tags:
            return []

        # Count how often each tag appears with the existing tags
        complementary_scores: Dict[str, int] = defaultdict(int)

        for existing_tag in existing_tags:
            for (tag1, tag2), count in self.tag_pairs.items():
                if tag1 == existing_tag and tag2 not in existing_tags:
                    complementary_scores[tag2] += count
                elif tag2 == existing_tag and tag1 not in existing_tags:
                    complementary_scores[tag1] += count

        if not complementary_scores:
            return []

        # Sort by score
        sorted_tags = sorted(
            complementary_scores.items(), key=lambda x: x[1], reverse=True
        )

        return [tag for tag, score in sorted_tags]

    def get_most_used_tags(self, top_k: int = 10) -> List[Tuple[str, int]]:
        """Get user's most frequently used tags"""
        sorted_tags = sorted(
            self.tag_preferences.items(), key=lambda x: x[1], reverse=True
        )
        return sorted_tags[:top_k]

    def get_tag_substitution(self, ai_tag: str) -> Optional[str]:
        """
        If user consistently substitutes ai_tag with another tag, return it.
        """
        return self.tag_substitutions.get(ai_tag)

    def adjust_ai_suggestions(
        self, suggestions: Dict[str, float]
    ) -> Dict[str, float]:
        """
        Adjust AI suggestions based on learned user preferences.

        Args:
            suggestions: {tag: confidence}

        Returns:
            Adjusted {tag: confidence}
        """
        adjusted = {}

        for tag, confidence in suggestions.items():
            # Check if user prefers a substitution
            preferred = self.get_tag_substitution(tag)
            if preferred:
                # Use substitution with boosted confidence
                adjusted[preferred] = min(1.0, confidence * 1.2)
            else:
                # Boost confidence for frequently used tags
                frequency_boost = min(0.1, self.tag_preferences.get(tag, 0) * 0.01)
                adjusted[tag] = min(1.0, confidence + frequency_boost)

        return adjusted

    def get_correction_accuracy(self) -> Dict[str, float]:
        """
        Analyze how accurate AI has been over time.

        Returns:
            {
                "total_corrections": int,
                "acceptance_rate": float,  # 0.0 to 1.0
                "most_corrected_tags": [(tag, count)]
            }
        """
        if not self.correction_history:
            return {
                "total_corrections": 0,
                "acceptance_rate": 0.0,
                "most_corrected_tags": [],
            }

        total = len(self.correction_history)
        accepted = sum(
            1
            for c in self.correction_history
            if c["ai_suggested"] == c["user_chose"]
        )

        # Count which tags get corrected most
        corrected_tags = Counter(
            c["ai_suggested"]
            for c in self.correction_history
            if c["ai_suggested"] != c["user_chose"]
        )

        return {
            "total_corrections": total,
            "acceptance_rate": accepted / total if total > 0 else 0.0,
            "most_corrected_tags": corrected_tags.most_common(10),
        }

    def should_suggest_tag(self, tag: str, min_usage: int = 3) -> bool:
        """
        Determine if a tag should be suggested to user.
        Only suggest tags the user actually uses.
        """
        return self.tag_preferences.get(tag, 0) >= min_usage

    def get_unused_tags(self, all_tags: List[str]) -> List[str]:
        """
        Find tags that exist but user never uses.
        """
        return [tag for tag in all_tags if self.tag_preferences.get(tag, 0) == 0]


def sync_user_model_from_tags(track_tags: Dict[str, List[str]]) -> UserTaggingStyle:
    """
    Initialize or update user model from existing tags.

    Args:
        track_tags: {track_path: [tags]}

    Returns:
        Updated UserTaggingStyle
    """
    model = UserTaggingStyle.load()

    for track, tags in track_tags.items():
        if tags:
            model.update_from_user_tags(track, tags)

    model.save()
    return model


def sync_user_model_from_corrections(
    correction_log: List[Dict],
) -> UserTaggingStyle:
    """
    Update user model from correction history.

    Args:
        correction_log: List of correction entries from safe_tagstore
    """
    model = UserTaggingStyle.load()

    for entry in correction_log:
        action = entry.get("action")
        track = entry.get("track")
        tag = entry.get("tag")
        timestamp = entry.get("timestamp")

        if action == "accepted":
            # User accepted AI suggestion - learn from this
            model.update_from_user_tags(track, [tag], timestamp)
        elif action == "rejected" and "user_chose" in entry:
            # User rejected and chose different tag
            user_tag = entry["user_chose"]
            model.update_from_correction(track, tag, user_tag, timestamp)

    model.save()
    return model
