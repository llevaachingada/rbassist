from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence, Tuple, Optional

import numpy as np

from .utils import load_meta


@dataclass
class TagProfile:
    tag: str
    centroid: np.ndarray
    threshold: float
    mean_sim: float
    std_sim: float
    samples: int

    def score(self, vec: np.ndarray) -> float:
        return float(vec @ self.centroid)

    def accepts(self, vec: np.ndarray, margin: float = 0.0) -> bool:
        score = self.score(vec)
        return score >= (self.threshold - margin)


def _normalise(vec: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vec))
    if norm == 0.0 or math.isnan(norm):
        return vec
    return vec / norm


def _load_embedding(path: str | None) -> np.ndarray | None:
    if not path:
        return None
    try:
        arr = np.load(path)
        if arr.ndim != 1:
            arr = arr.reshape(-1)
        return _normalise(arr.astype(np.float32))
    except Exception:
        return None


def learn_tag_profiles(min_samples: int = 3, meta: Optional[dict] = None) -> Dict[str, TagProfile]:
    """Build centroid profiles per tag from existing tagged tracks."""
    meta = meta or load_meta()
    tag_vectors: Dict[str, List[np.ndarray]] = {}
    for path, info in meta.get("tracks", {}).items():
        tags = info.get("mytags")
        if not tags:
            continue
        vec = _load_embedding(info.get("embedding"))
        if vec is None or not np.any(vec):
            continue
        for tag in tags:
            tag_vectors.setdefault(tag, []).append(vec)

    profiles: Dict[str, TagProfile] = {}
    for tag, vectors in tag_vectors.items():
        if len(vectors) < max(1, min_samples):
            continue
        mat = np.stack(vectors, axis=0)
        centroid = _normalise(mat.mean(axis=0))
        sims = mat @ centroid
        mean = float(np.mean(sims))
        std = float(np.std(sims))
        threshold = mean - std
        profiles[tag] = TagProfile(
            tag=tag,
            centroid=centroid,
            threshold=threshold,
            mean_sim=mean,
            std_sim=std,
            samples=len(vectors),
        )
    return profiles


def suggest_tags_for_tracks(
    tracks: Sequence[str],
    profiles: Dict[str, TagProfile],
    margin: float = 0.0,
    top_k: int = 3,
    meta: Optional[dict] = None,
) -> Dict[str, List[Tuple[str, float, float]]]:
    """
    Score candidate tracks against learned tag profiles.

    Returns mapping path -> list of (tag, score, threshold).
    """
    out: Dict[str, List[Tuple[str, float, float]]] = {}
    if not profiles:
        return out
    meta = meta or load_meta()
    track_meta = meta.get("tracks", {})
    for path in tracks:
        info = track_meta.get(path)
        if info is None:
            continue
        vec = _load_embedding(info.get("embedding"))
        if vec is None or not np.any(vec):
            continue
        scored: List[Tuple[str, float, float]] = []
        for tag, profile in profiles.items():
            score = profile.score(vec)
            if profile.accepts(vec, margin=margin):
                scored.append((tag, score, profile.threshold))
        if scored:
            scored.sort(key=lambda item: item[1], reverse=True)
            if top_k > 0:
                scored = scored[:top_k]
            out[path] = scored
    return out


def evaluate_existing_tags(
    tracks: Sequence[str],
    profiles: Dict[str, TagProfile],
    meta: Optional[dict] = None,
) -> Dict[str, List[Tuple[str, float, float]]]:
    """Return similarity scores for tags already assigned to each track."""
    out: Dict[str, List[Tuple[str, float, float]]] = {}
    if not profiles:
        return out
    meta = meta or load_meta()
    track_meta = meta.get("tracks", {})
    for path in tracks:
        info = track_meta.get(path)
        if info is None:
            continue
        vec = _load_embedding(info.get("embedding"))
        if vec is None or not np.any(vec):
            continue
        rows: List[Tuple[str, float, float]] = []
        for tag in info.get("mytags", []) or []:
            profile = profiles.get(tag)
            if not profile:
                continue
            score = profile.score(vec)
            rows.append((tag, score, profile.threshold))
        if rows:
            out[path] = rows
    return out
