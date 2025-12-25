"""
Active learning for music tagging.
Research-backed uncertainty sampling strategies.

Based on:
- "Active Learning" (Settles, 2012)
- "Uncertainty Sampling for Music Tagging" (ACM RecSys 2024)
- "Prototypical Networks for Few-shot Learning" (Snell et al., 2017)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np

from .tag_model import TagProfile
from .utils import console


@dataclass
class UncertainTrack:
    """A track that would teach the AI a lot if tagged"""

    path: str
    uncertainty_score: float
    top_tags: List[Tuple[str, float]]  # (tag, confidence)
    reason: str


def calculate_margin(scores: List[float]) -> float:
    """
    Margin sampling: difference between top 2 scores.
    Low margin = uncertain between two options.
    """
    if len(scores) < 2:
        return 1.0
    sorted_scores = sorted(scores, reverse=True)
    return sorted_scores[0] - sorted_scores[1]


def calculate_entropy(scores: List[float]) -> float:
    """
    Entropy-based: uncertainty across ALL options.
    High entropy = many similar scores.
    """
    if not scores:
        return 0.0

    # Normalize to probabilities
    scores_arr = np.array(scores)
    if scores_arr.sum() == 0:
        return 0.0
    probs = scores_arr / scores_arr.sum()

    # Shannon entropy
    return float(-np.sum(probs * np.log(probs + 1e-10)))


def calculate_least_confidence(scores: List[float]) -> float:
    """
    Least confidence: 1 - max(scores).
    High value = not confident in any option.
    """
    if not scores:
        return 1.0
    return 1.0 - max(scores)


def score_all_tags(
    track_embedding: np.ndarray, profiles: Dict[str, TagProfile]
) -> Dict[str, float]:
    """Score a track against all tag profiles"""
    scores = {}
    for tag, profile in profiles.items():
        score = profile.score(track_embedding)
        scores[tag] = score
    return scores


def suggest_tracks_to_tag(
    untagged_embeddings: Dict[str, np.ndarray],
    profiles: Dict[str, TagProfile],
    strategy: str = "margin",
    top_k: int = 10,
) -> List[UncertainTrack]:
    """
    Suggest which tracks to tag next for maximum learning.

    Args:
        untagged_embeddings: {track_path: embedding_vector}
        profiles: Learned tag profiles
        strategy: "margin" | "entropy" | "least_confidence"
        top_k: Number of tracks to suggest

    Returns:
        List of UncertainTrack objects, sorted by uncertainty
    """
    if not profiles:
        console.print("[yellow]No tag profiles yet. Tag some tracks first!")
        return []

    uncertain_tracks = []

    for track, embedding in untagged_embeddings.items():
        tag_scores = score_all_tags(embedding, profiles)

        if not tag_scores:
            continue

        # Calculate uncertainty based on strategy
        scores_list = list(tag_scores.values())

        if strategy == "margin":
            uncertainty = 1.0 - calculate_margin(scores_list)
            reason = "Close call between top tags"
        elif strategy == "entropy":
            uncertainty = calculate_entropy(scores_list)
            reason = "Uncertain across many tags"
        elif strategy == "least_confidence":
            uncertainty = calculate_least_confidence(scores_list)
            reason = "Low confidence in all tags"
        else:
            raise ValueError(f"Unknown strategy: {strategy}")

        # Get top tags
        top_tags = sorted(tag_scores.items(), key=lambda x: x[1], reverse=True)[:3]

        uncertain_tracks.append(
            UncertainTrack(
                path=track,
                uncertainty_score=uncertainty,
                top_tags=top_tags,
                reason=reason,
            )
        )

    # Sort by uncertainty (highest first)
    uncertain_tracks.sort(key=lambda x: x.uncertainty_score, reverse=True)

    return uncertain_tracks[:top_k]


def explain_uncertainty(track: UncertainTrack) -> str:
    """Human-readable explanation of why this track is uncertain"""
    if not track.top_tags:
        return "No confident predictions"

    top_tag, top_score = track.top_tags[0]

    if track.reason == "Close call between top tags" and len(track.top_tags) >= 2:
        second_tag, second_score = track.top_tags[1]
        return (
            f"I'm {top_score:.0%} sure it's '{top_tag}' but {second_score:.0%} "
            f"sure it's '{second_tag}'. Which is it?"
        )
    elif track.reason == "Uncertain across many tags":
        tags_str = ", ".join(f"'{t}' ({s:.0%})" for t, s in track.top_tags)
        return f"Could be any of: {tags_str}"
    else:  # least_confidence
        return f"Best guess is '{top_tag}' but only {top_score:.0%} confident"


def diversity_sample(
    uncertain_tracks: List[UncertainTrack],
    embeddings: Dict[str, np.ndarray],
    n: int = 5,
) -> List[UncertainTrack]:
    """
    Select diverse uncertain tracks (avoid similar tracks).
    Uses greedy farthest-first sampling.
    """
    if len(uncertain_tracks) <= n:
        return uncertain_tracks

    # Start with most uncertain
    selected = [uncertain_tracks[0]]
    remaining = uncertain_tracks[1:]

    while len(selected) < n and remaining:
        # Find track farthest from all selected
        max_min_dist = -1.0
        best_idx = 0

        for i, track in enumerate(remaining):
            if track.path not in embeddings:
                continue

            # Minimum distance to any selected track
            min_dist = min(
                float(np.linalg.norm(embeddings[track.path] - embeddings[s.path]))
                for s in selected
                if s.path in embeddings
            )

            if min_dist > max_min_dist:
                max_min_dist = min_dist
                best_idx = i

        selected.append(remaining.pop(best_idx))

    return selected


def get_tracks_near_threshold(
    embeddings: Dict[str, np.ndarray],
    profiles: Dict[str, TagProfile],
    margin: float = 0.05,
) -> Dict[str, List[Tuple[str, float, float]]]:
    """
    Find tracks that are near the decision boundary for any tag.

    Returns:
        {track_path: [(tag, score, threshold)]}
    """
    near_threshold = {}

    for track, embedding in embeddings.items():
        close_calls = []

        for tag, profile in profiles.items():
            score = profile.score(embedding)
            threshold = profile.threshold

            # Check if score is close to threshold
            if abs(score - threshold) <= margin:
                close_calls.append((tag, score, threshold))

        if close_calls:
            # Sort by how close to threshold (closest first)
            close_calls.sort(key=lambda x: abs(x[1] - x[2]))
            near_threshold[track] = close_calls

    return near_threshold


def suggest_by_tag_confidence(
    embeddings: Dict[str, np.ndarray],
    profiles: Dict[str, TagProfile],
    target_tag: str,
    top_k: int = 10,
) -> List[Tuple[str, float]]:
    """
    Find tracks most likely to have a specific tag.
    Useful for bootstrapping new tags.

    Returns:
        [(track_path, confidence)]
    """
    if target_tag not in profiles:
        return []

    profile = profiles[target_tag]
    scored_tracks = []

    for track, embedding in embeddings.items():
        score = profile.score(embedding)
        scored_tracks.append((track, score))

    # Sort by score (highest first)
    scored_tracks.sort(key=lambda x: x[1], reverse=True)

    return scored_tracks[:top_k]


def analyze_tag_confusion(
    correction_history: List[Dict],
) -> Dict[Tuple[str, str], int]:
    """
    Analyze which tags are commonly confused.

    Returns:
        {(ai_suggested_tag, user_chose_tag): count}
    """
    confusion_matrix = {}

    for entry in correction_history:
        if entry.get("action") == "rejected" and "user_chose" in entry:
            ai_tag = entry["tag"]
            user_tag = entry["user_chose"]
            key = (ai_tag, user_tag)
            confusion_matrix[key] = confusion_matrix.get(key, 0) + 1

    return confusion_matrix


def get_learning_recommendations(
    profiles: Dict[str, TagProfile],
    min_samples_per_tag: int = 5,
) -> List[str]:
    """
    Recommend which tags need more training examples.

    Returns:
        List of tag names that need more examples
    """
    needs_more = []

    for tag, profile in profiles.items():
        if profile.samples < min_samples_per_tag:
            needs_more.append(tag)

    # Sort by how many more samples needed
    needs_more.sort(
        key=lambda tag: min_samples_per_tag - profiles[tag].samples, reverse=True
    )

    return needs_more
