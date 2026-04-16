from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from rbassist.bpm_sources import track_bpm_sources
from rbassist.ui_services.library import (
    bpm_alert_text,
    build_library_rows,
    format_bpm_cell,
    format_bpm_metric,
)


def tempo_score(seed_bpm: float, cand_bpm: float, max_diff: float = 6.0) -> float:
    if seed_bpm <= 0 or cand_bpm <= 0:
        return 0.0
    diff = abs(seed_bpm - cand_bpm)
    if max_diff > 0 and diff > max_diff:
        return 0.0
    if max_diff <= 0:
        max_diff = 6.0
    return max(0.0, 1.0 - diff / max_diff)


def camelot_relation_score(seed: str, cand: str) -> float:
    if not seed or not cand:
        return 0.0
    if seed == cand:
        return 1.0
    try:
        n1, m1 = int(seed[:-1]), seed[-1].upper()
        n2, m2 = int(cand[:-1]), cand[-1].upper()
    except Exception:
        return 0.0
    if n1 == n2 and m1 != m2:
        return 0.8
    if (n1 - n2) % 12 in (1, 11):
        return 0.7
    return 0.0


def tag_similarity_score(seed_tags: set, cand_tags: set, prefer_tags: set | None = None) -> float:
    if not seed_tags and not cand_tags:
        return 0.0
    all_tags = seed_tags | prefer_tags if prefer_tags else seed_tags
    if not all_tags:
        return 0.0
    inter = len(cand_tags & all_tags)
    union = len(cand_tags | all_tags)
    if union == 0:
        return 0.0
    return inter / union


def plain_key_fit(label: str) -> str:
    clean = str(label or "-").strip().lower()
    if clean in {"same", "relative", "neighbor"}:
        return clean.title()
    if clean == "-":
        return "Not scored"
    return clean.replace("_", " ").title()


def audio_distance_note(value: object) -> str:
    if isinstance(value, (int, float)):
        return f"{float(value):.3f} (lower means the raw audio match is closer)"
    return "Not shown in library browse mode"


def bpm_summary_text(path: str, info: Mapping[str, Any]) -> str:
    bpm_info = track_bpm_sources(path, info)
    preferred_label = "Rekordbox" if bpm_info.preferred_source == "rekordbox" else "RB Assist"
    summary = (
        f"Using {preferred_label}: {format_bpm_metric(bpm_info.preferred_bpm)}"
        f" | Rekordbox: {format_bpm_metric(bpm_info.rekordbox_bpm)}"
        f" | RB Assist: {format_bpm_metric(bpm_info.rbassist_bpm)}"
    )
    if bpm_info.large_mismatch and bpm_info.delta is not None:
        summary += f" | Delta: {bpm_info.delta:+.2f}"
    return summary


def should_apply_refresh_result(*, request_id: int, latest_request_id: int, browse_mode: bool) -> bool:
    return not browse_mode and request_id == latest_request_id


def should_start_refresh_task(*, running: bool) -> bool:
    return not running


def should_continue_refresh_drain(*, completed_request_id: int, latest_request_id: int, browse_mode: bool) -> bool:
    return not browse_mode and completed_request_id != latest_request_id


def build_track_detail(
    *,
    path: str,
    track: Mapping[str, Any],
    info: Mapping[str, Any],
    browse_mode: bool,
) -> dict[str, str]:
    tags = ", ".join(
        dict.fromkeys(
            str(tag).strip()
            for tag in list(info.get("tags", []) or []) + list(info.get("mytags", []) or [])
            if str(tag).strip()
        )
    ) or "No tags"
    key_text = str(info.get("key") or "-")
    title = f"{track.get('artist', '')} - {track.get('title', '')}".strip(" -")
    summary = (
        f"Overall fit {track.get('score', '-')}, audio distance {audio_distance_note(track.get('dist'))}, "
        f"harmonic fit {plain_key_fit(str(track.get('key_rule', '-')))}."
    )
    if track.get("harmonic_score") not in (None, "", "-"):
        summary += f" Profile harmony {track.get('harmonic_score')}."
    if track.get("learned_score") not in (None, "", "-"):
        summary += f" Learned fit {track.get('learned_score')}."
    if browse_mode:
        summary = "Library browse mode shows track metadata only. Switch back to Recommendations for ranked matches."
    return {
        "title": title or str(track.get("title", "") or "Track detail"),
        "summary": summary,
        "metrics": f"Tempo: {bpm_summary_text(path, info)} | Key: {key_text} | Tags: {tags}",
        "note": (
            "Tempo scoring prefers Rekordbox BPM when it is available. RB Assist BPM stays visible as the local analysis value."
            if not browse_mode
            else "This row is not being reranked in browse mode."
        ),
    }


def build_recommendation_rows(
    *,
    seed_path: str,
    meta: Mapping[str, Any],
    filters: Mapping[str, Any],
    weights: Mapping[str, float],
    top: int = 50,
) -> list[dict[str, Any]]:
    """Build Discover recommendation rows without depending on a GUI toolkit."""
    import hnswlib
    from rbassist.recommend import IDX, load_embedding_safe
    from rbassist.utils import camelot_relation, tempo_match

    try:
        from rbassist.features import bass_similarity, harmonic_compatibility_from_features, rhythm_similarity
    except Exception:
        bass_similarity = None
        harmonic_compatibility_from_features = None
        rhythm_similarity = None

    try:
        from rbassist.similarity_head import DEFAULT_SIMILARITY_MODEL, load_similarity_head
    except Exception:
        DEFAULT_SIMILARITY_MODEL = Path("data/models/similarity_head.pt")  # type: ignore
        load_similarity_head = None  # type: ignore

    tracks = meta.get("tracks", {}) if isinstance(meta, Mapping) else {}
    seed_info = tracks.get(seed_path, {})
    if not isinstance(seed_info, Mapping):
        seed_info = {}

    emb_path = seed_info.get("embedding")
    if not emb_path:
        raise ValueError("Seed track has no embedding")

    seed_vec = load_embedding_safe(str(emb_path))
    if seed_vec is None:
        raise ValueError("Could not load seed embedding")

    paths_map = json.loads((IDX / "paths.json").read_text(encoding="utf-8"))
    index = hnswlib.Index(space="cosine", dim=seed_vec.shape[0])
    index.load_index(str(IDX / "hnsw.idx"))
    index.set_ef(64)
    labels, dists = index.knn_query(seed_vec, k=min(top * 4, len(paths_map)))
    labels, dists = labels[0].tolist(), dists[0].tolist()

    filters = dict(filters)
    weights = dict(weights)
    seed_bpm_info = track_bpm_sources(seed_path, seed_info)
    seed_bpm = float(seed_bpm_info.preferred_bpm or 0.0)
    seed_key = str(seed_info.get("key") or "")
    seed_camelot = str(seed_info.get("camelot") or "")
    seed_features = seed_info.get("features", {})
    seed_tags = set(seed_info.get("tags", []) + seed_info.get("mytags", []))
    seed_bass_contour = np.array(seed_features.get("bass_contour", {}).get("contour", []), dtype=float)
    seed_rhythm_contour = np.array(seed_features.get("rhythm_contour", {}).get("contour", []), dtype=float)

    bpm_max_diff = float(filters.get("bpm_max_diff", 0.0))
    allowed_key_rel = set(filters.get("allowed_key_relations", []))
    require_tags = set(filters.get("require_tags", []))
    prefer_tags = set(filters.get("prefer_tags", []))
    weight_sum = sum(weights.values()) or 1.0
    learned_head = None
    if bool(filters.get("learned_similarity", False)) and float(weights.get("learned_sim", 0.0)):
        if load_similarity_head is not None:
            learned_head = load_similarity_head(
                filters.get("similarity_head_path") or DEFAULT_SIMILARITY_MODEL,
                device=str(filters.get("similarity_device") or "cuda"),
            )

    results: list[dict[str, Any]] = []
    for label, dist in zip(labels, dists):
        path = paths_map[label]
        if path == seed_path:
            continue

        info = tracks.get(path, {})
        if not isinstance(info, Mapping):
            info = {}
        cand_bpm_info = track_bpm_sources(path, info)
        cand_bpm = float(cand_bpm_info.preferred_bpm or 0.0)
        cand_key = str(info.get("key") or "")
        cand_camelot = str(info.get("camelot") or "")
        cand_features = info.get("features", {})
        cand_tags = set(info.get("tags", []) + info.get("mytags", []))
        cand_vec: np.ndarray | None = None

        if bpm_max_diff > 0 and seed_bpm > 0 and cand_bpm > 0 and abs(seed_bpm - cand_bpm) > bpm_max_diff:
            continue
        if not tempo_match(seed_bpm, cand_bpm, pct=filters.get("tempo_pct", 6.0), allow_doubletime=filters.get("doubletime", True)):
            continue
        if require_tags and not require_tags.issubset(cand_tags):
            continue

        key_score = camelot_relation_score(seed_camelot or seed_key, cand_camelot or cand_key)
        if allowed_key_rel:
            if key_score >= 0.99:
                rel = "same"
            elif key_score >= 0.79:
                rel = "relative"
            elif key_score >= 0.69:
                rel = "neighbor"
            else:
                rel = "other"
            if rel not in allowed_key_rel:
                continue
        else:
            if key_score >= 0.99:
                rel = "same"
            elif key_score >= 0.79:
                rel = "relative"
            elif key_score >= 0.69:
                rel = "neighbor"
            else:
                ok, rel = camelot_relation(seed_key, cand_key)
                if filters.get("camelot") and not ok:
                    continue
                if not ok:
                    rel = "-"

        score = 0.0
        if weights.get("ann", 0.0):
            score += weights["ann"] * (1.0 - float(dist))
        if weights.get("samples", 0.0):
            score += weights["samples"] * float(cand_features.get("samples", 0.0))
        if weights.get("bass", 0.0) and bass_similarity is not None:
            cand_bass_contour = np.array(cand_features.get("bass_contour", {}).get("contour", []), dtype=float)
            if seed_bass_contour.size and cand_bass_contour.size:
                score += weights["bass"] * float(bass_similarity(seed_bass_contour, cand_bass_contour))
        if weights.get("rhythm", 0.0) and rhythm_similarity is not None:
            cand_rhythm_contour = np.array(cand_features.get("rhythm_contour", {}).get("contour", []), dtype=float)
            if seed_rhythm_contour.size and cand_rhythm_contour.size:
                score += weights["rhythm"] * float(rhythm_similarity(seed_rhythm_contour, cand_rhythm_contour))
        if weights.get("bpm", 0.0) and seed_bpm > 0 and cand_bpm > 0:
            score += weights["bpm"] * tempo_score(seed_bpm, cand_bpm, bpm_max_diff or filters.get("tempo_pct", 6.0))
        if weights.get("key", 0.0):
            score += weights["key"] * key_score
        harmonic_score = 0.0
        if weights.get("harmony", 0.0) and harmonic_compatibility_from_features is not None:
            harmonic_score = float(harmonic_compatibility_from_features(seed_info, info))
            score += weights["harmony"] * harmonic_score
        learned_score = 0.0
        if learned_head is not None and weights.get("learned_sim", 0.0):
            cand_vec = load_embedding_safe(str(info.get("embedding") or ""), seed_vec.shape[0])
            if cand_vec is not None:
                learned_score = float(learned_head.score(seed_vec, cand_vec))
                score += weights["learned_sim"] * learned_score
        if weights.get("tags", 0.0):
            score += weights["tags"] * tag_similarity_score(seed_tags, cand_tags, prefer_tags)

        score /= weight_sum
        results.append(
            {
                "path": path,
                "artist": info.get("artist", ""),
                "title": info.get("title", str(path).split("\\")[-1].split("/")[-1]),
                "bpm": format_bpm_cell(cand_bpm_info.preferred_bpm),
                "rekordbox_bpm": format_bpm_cell(cand_bpm_info.rekordbox_bpm),
                "rbassist_bpm": format_bpm_cell(cand_bpm_info.rbassist_bpm),
                "bpm_alert": bpm_alert_text(cand_bpm_info.large_mismatch),
                "key": cand_key or "-",
                "dist": round(float(dist), 3),
                "key_rule": rel,
                "harmonic_score": round(float(harmonic_score), 3),
                "learned_score": round(float(learned_score), 3) if learned_head is not None else "-",
                "score": round(float(score), 3),
            }
        )

    results.sort(key=lambda row: row["score"], reverse=True)
    return results[:top]
