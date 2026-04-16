from __future__ import annotations

import json
import math
import pathlib
import re
import unicodedata
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from .utils import load_meta, make_path_aliases, normalize_path_string, walk_audio

try:
    from mutagen import File as MFile  # type: ignore
except Exception:
    MFile = None


def _fold_text(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text


def _tokenize_name(value: str | None) -> list[str]:
    text = _fold_text(value).lower()
    text = re.sub(r"\.[a-z0-9]{2,5}$", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return [part for part in text.split() if part]


def _name_key(value: str | None) -> str:
    return " ".join(_tokenize_name(value))


def _path_key(path: str | pathlib.Path) -> str:
    return normalize_path_string(path).lower()


def _duration_of(path: str) -> float | None:
    if MFile is None:
        return None
    try:
        media = MFile(path)
        length = float(getattr(getattr(media, "info", None), "length", 0.0) or 0.0)
        return round(length, 3) if length > 0 else None
    except Exception:
        return None


def _size_of(path: str) -> int | None:
    try:
        return pathlib.Path(path).stat().st_size
    except Exception:
        return None


def _duration_bucket(duration: float | None, *, precision: float = 0.5) -> int | None:
    if duration is None or precision <= 0:
        return None
    return int(round(duration / precision))


def _within_root(path: str | pathlib.Path, music_root: pathlib.Path) -> bool:
    try:
        normalized_path = _path_key(path)
        normalized_root = _path_key(music_root)
        return normalized_path.startswith(normalized_root.rstrip("/") + "/") or normalized_path == normalized_root
    except Exception:
        return False


def _outside_root_anchor(path: pathlib.Path) -> str:
    parts = list(path.parts)
    if len(parts) >= 4 and parts[1].lower() == "users":
        return parts[3]
    if path.parent.name:
        return path.parent.name
    return "outside_root"


def _safe_consolidation_target(source_path: str, consolidate_root: pathlib.Path) -> str:
    source = pathlib.Path(source_path)
    anchor = _outside_root_anchor(source)
    return str((consolidate_root / anchor / source.name).resolve())


def _token_overlap(left: str | None, right: str | None) -> float:
    left_tokens = set(_tokenize_name(left))
    right_tokens = set(_tokenize_name(right))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / max(len(left_tokens | right_tokens), 1)


@dataclass
class CatalogRecord:
    path: str
    path_key: str
    basename: str
    stem_key: str
    extension: str
    size: int | None
    duration: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "basename": self.basename,
            "stem_key": self.stem_key,
            "extension": self.extension,
            "size": self.size,
            "duration": self.duration,
        }


def _catalog_one(path: str) -> CatalogRecord:
    candidate = pathlib.Path(path)
    return CatalogRecord(
        path=str(candidate),
        path_key=_path_key(candidate),
        basename=candidate.name.lower(),
        stem_key=_name_key(candidate.stem),
        extension=candidate.suffix.lower(),
        size=_size_of(str(candidate)),
        duration=_duration_of(str(candidate)),
    )


def build_music_catalog(music_root: str | pathlib.Path, *, workers: int = 8) -> dict[str, Any]:
    root = pathlib.Path(music_root).resolve()
    files = walk_audio([str(root)])
    if workers and workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            records = list(executor.map(_catalog_one, files))
    else:
        records = [_catalog_one(path) for path in files]

    by_path = {record.path_key: record for record in records}
    by_basename: dict[str, list[CatalogRecord]] = defaultdict(list)
    by_stem: dict[str, list[CatalogRecord]] = defaultdict(list)
    for record in records:
        by_basename[record.basename].append(record)
        by_stem[record.stem_key].append(record)

    return {
        "music_root": str(root),
        "records": records,
        "by_path": by_path,
        "by_basename": by_basename,
        "by_stem": by_stem,
    }


def _load_rekordbox_rows() -> list[dict[str, Any]]:
    try:
        from pyrekordbox import Rekordbox6Database
    except Exception as exc:
        raise RuntimeError(
            "Rekordbox audit requires pyrekordbox in the active interpreter."
        ) from exc

    db = Rekordbox6Database()
    try:
        query = db.get_content()
        if isinstance(query, list):
            contents = query
        else:
            contents = list(query.all())
        rows: list[dict[str, Any]] = []
        for item in contents:
            folder_path = str(getattr(item, "FolderPath", "") or "").strip()
            rows.append(
                {
                    "id": str(getattr(item, "ID", "") or ""),
                    "title": str(getattr(item, "Title", "") or "").strip(),
                    "artist": str(getattr(item, "ArtistName", "") or "").strip(),
                    "folder_path": folder_path,
                    "file_name": str(getattr(item, "FileNameL", "") or "").strip(),
                    "length": float(getattr(item, "Length", 0.0) or 0.0),
                    "bpm": float(getattr(item, "BPM", 0.0) or 0.0),
                    "stock_date": str(getattr(item, "StockDate", "") or "").strip(),
                }
            )
        return rows
    finally:
        try:
            db.close()
        except Exception:
            pass


def _score_candidate(
    row: dict[str, Any],
    candidate: CatalogRecord,
    *,
    duration_tolerance_s: float,
) -> tuple[float, list[str]]:
    reasons: list[str] = []
    score = 0.0
    row_path = pathlib.Path(row.get("folder_path", ""))
    row_basename = row_path.name.lower()
    row_stem_key = _name_key(row_path.stem or row.get("file_name", ""))
    row_title_key = _name_key(row.get("title", ""))
    row_artist_key = _name_key(row.get("artist", ""))

    if row_basename and row_basename == candidate.basename:
        score += 75.0
        reasons.append("exact_basename")
    if row_stem_key and row_stem_key == candidate.stem_key:
        score += 55.0
        reasons.append("exact_stem")

    stem_similarity = SequenceMatcher(None, row_stem_key, candidate.stem_key).ratio() if row_stem_key and candidate.stem_key else 0.0
    if stem_similarity >= 0.96:
        score += 18.0
        reasons.append("very_high_name_similarity")
    elif stem_similarity >= 0.88:
        score += 10.0
        reasons.append("high_name_similarity")

    token_overlap = max(
        _token_overlap(row.get("title", ""), candidate.stem_key),
        _token_overlap(row.get("file_name", ""), candidate.basename),
    )
    if token_overlap >= 0.8:
        score += 12.0
        reasons.append("strong_token_overlap")
    elif token_overlap >= 0.6:
        score += 6.0
        reasons.append("moderate_token_overlap")

    if row_title_key and row_title_key in candidate.stem_key:
        score += 8.0
        reasons.append("title_in_filename")
    if row_artist_key and row_artist_key in candidate.stem_key:
        score += 6.0
        reasons.append("artist_in_filename")

    row_length = float(row.get("length", 0.0) or 0.0)
    if row_length > 0 and candidate.duration is not None:
        delta = abs(row_length - candidate.duration)
        if delta <= 0.5:
            score += 70.0
            reasons.append("duration_within_0_5s")
        elif delta <= 1.0:
            score += 55.0
            reasons.append("duration_within_1s")
        elif delta <= duration_tolerance_s:
            score += 35.0
            reasons.append("duration_within_tolerance")
        elif delta <= 5.0:
            score += 8.0
            reasons.append("duration_near")
        else:
            score -= 45.0
            reasons.append("duration_mismatch")

    if row_path.suffix.lower() and row_path.suffix.lower() == candidate.extension:
        score += 4.0
        reasons.append("same_extension")

    return score, reasons


def _classify_relink_group(matches: list[dict[str, Any]]) -> tuple[str, dict[str, Any] | None]:
    if not matches:
        return "not_found", None
    ranked = sorted(matches, key=lambda item: item["score"], reverse=True)
    best = ranked[0]
    next_best = ranked[1] if len(ranked) > 1 else None
    margin = best["score"] - (next_best["score"] if next_best else 0.0)
    if best["score"] >= 120.0 and (next_best is None or margin >= 25.0):
        return "high_confidence_unique", best
    if best["score"] >= 95.0 and (next_best is None or margin >= 15.0):
        return "likely_unique", best
    if len(ranked) == 1 and best["score"] >= 85.0:
        return "likely_unique", best
    return "ambiguous", best


def suggest_relinks_for_rows(
    rows: list[dict[str, Any]],
    catalog: dict[str, Any],
    *,
    music_root: str | pathlib.Path,
    consolidate_root: str | pathlib.Path | None = None,
    duration_tolerance_s: float = 2.0,
    top_candidates: int = 5,
) -> dict[str, Any]:
    root = pathlib.Path(music_root).resolve()
    consolidation_root = pathlib.Path(consolidate_root).resolve() if consolidate_root else (root / "_Consolidate" / "rekordbox_outside_root")
    counts = Counter()
    audit_samples: dict[str, list[dict[str, Any]]] = {
        "broken_links": [],
        "outside_root_existing": [],
        "outside_root_missing": [],
        "high_confidence_relinks": [],
        "ambiguous_relinks": [],
        "not_found_relinks": [],
        "consolidation_actions": [],
    }
    relink_suggestions: list[dict[str, Any]] = []
    consolidation_plan: list[dict[str, Any]] = []

    meta = load_meta()
    meta_aliases: set[str] = set()
    for path in meta.get("tracks", {}).keys():
        meta_aliases.update({_path_key(alias) for alias in make_path_aliases(path)})

    for row in rows:
        folder_path = row.get("folder_path", "")
        if not folder_path:
            counts["missing_folder_path_total"] += 1
            continue

        record_path = pathlib.Path(folder_path)
        path_key = _path_key(record_path)
        exists = record_path.exists()
        inside_root = _within_root(record_path, root)

        if inside_root and exists:
            counts["inside_root_existing_total"] += 1
        elif inside_root and not exists:
            counts["inside_root_missing_total"] += 1
        elif not inside_root and exists:
            counts["outside_root_existing_total"] += 1
            if len(audit_samples["outside_root_existing"]) < 50:
                audit_samples["outside_root_existing"].append(
                    {
                        "id": row.get("id", ""),
                        "path": folder_path,
                        "title": row.get("title", ""),
                        "artist": row.get("artist", ""),
                    }
                )
        else:
            counts["outside_root_missing_total"] += 1
            if len(audit_samples["outside_root_missing"]) < 50:
                audit_samples["outside_root_missing"].append(
                    {
                        "id": row.get("id", ""),
                        "path": folder_path,
                        "title": row.get("title", ""),
                        "artist": row.get("artist", ""),
                    }
                )

        if not exists and len(audit_samples["broken_links"]) < 50:
            audit_samples["broken_links"].append(
                {
                    "id": row.get("id", ""),
                    "path": folder_path,
                    "title": row.get("title", ""),
                    "artist": row.get("artist", ""),
                }
            )

        if path_key in meta_aliases:
            counts["rbassist_meta_match_total"] += 1

        if inside_root and exists:
            continue

        candidates = []
        basename_matches = list(catalog["by_basename"].get(record_path.name.lower(), []))
        stem_matches = list(catalog["by_stem"].get(_name_key(record_path.stem or row.get("file_name", "")), []))
        candidate_map: dict[str, CatalogRecord] = {}
        for item in basename_matches + stem_matches:
            candidate_map[item.path_key] = item
        for candidate in candidate_map.values():
            score, reasons = _score_candidate(row, candidate, duration_tolerance_s=duration_tolerance_s)
            candidates.append(
                {
                    "path": candidate.path,
                    "score": round(score, 2),
                    "duration": candidate.duration,
                    "size": candidate.size,
                    "extension": candidate.extension,
                    "reasons": reasons,
                }
            )
        candidates = sorted(candidates, key=lambda item: item["score"], reverse=True)
        classification, best = _classify_relink_group(candidates)
        counts[f"{classification}_relink_total"] += 1
        suggestion = {
            "id": row.get("id", ""),
            "source_path": folder_path,
            "title": row.get("title", ""),
            "artist": row.get("artist", ""),
            "row_length": row.get("length", 0.0),
            "inside_root": inside_root,
            "exists": exists,
            "classification": classification,
            "best_candidate": best,
            "candidates": candidates[:top_candidates],
        }
        relink_suggestions.append(suggestion)

        if classification == "high_confidence_unique" and len(audit_samples["high_confidence_relinks"]) < 50:
            audit_samples["high_confidence_relinks"].append(suggestion)
        elif classification in {"likely_unique", "ambiguous"} and len(audit_samples["ambiguous_relinks"]) < 50:
            audit_samples["ambiguous_relinks"].append(suggestion)
        elif classification == "not_found" and len(audit_samples["not_found_relinks"]) < 50:
            audit_samples["not_found_relinks"].append(suggestion)

        if classification in {"high_confidence_unique", "likely_unique"} and best is not None:
            action = "relink_to_existing_inside_root"
            suggested_target = best["path"]
        elif not inside_root and exists:
            action = "move_into_music_root_then_relink"
            suggested_target = _safe_consolidation_target(folder_path, consolidation_root)
        else:
            action = "manual_review"
            suggested_target = ""

        plan_item = {
            "id": row.get("id", ""),
            "source_path": folder_path,
            "title": row.get("title", ""),
            "artist": row.get("artist", ""),
            "exists": exists,
            "inside_root": inside_root,
            "classification": classification,
            "action": action,
            "suggested_target": suggested_target,
            "best_candidate": best,
        }
        consolidation_plan.append(plan_item)
        counts[f"{action}_total"] += 1
        if action != "manual_review" and len(audit_samples["consolidation_actions"]) < 50:
            audit_samples["consolidation_actions"].append(plan_item)

    return {
        "music_root": str(root),
        "consolidate_root": str(consolidation_root),
        "counts": dict(counts),
        "samples": audit_samples,
        "relink_suggestions": relink_suggestions,
        "consolidation_plan": consolidation_plan,
    }


def find_name_duration_duplicates(
    catalog: dict[str, Any],
    *,
    duration_tolerance_s: float = 2.0,
    top_groups: int = 250,
) -> dict[str, Any]:
    counts = Counter()
    groups: list[dict[str, Any]] = []
    stem_buckets: dict[str, list[CatalogRecord]] = defaultdict(list)
    for record in catalog["records"]:
        stem_buckets[record.stem_key].append(record)

    for stem_key, records in stem_buckets.items():
        if len(records) < 2 or not stem_key:
            continue
        sorted_records = sorted(
            records,
            key=lambda item: (
                _duration_bucket(item.duration, precision=0.5) if item.duration is not None else math.inf,
                item.path,
            ),
        )
        current: list[CatalogRecord] = []
        for record in sorted_records:
            if not current:
                current = [record]
                continue
            prev = current[-1]
            comparable = (
                prev.duration is not None
                and record.duration is not None
                and abs(prev.duration - record.duration) <= duration_tolerance_s
            )
            same_size = prev.size is not None and record.size is not None and prev.size == record.size
            if comparable or same_size:
                current.append(record)
            else:
                if len(current) > 1:
                    _append_duplicate_group(groups, counts, stem_key, current, top_groups)
                current = [record]
        if len(current) > 1:
            _append_duplicate_group(groups, counts, stem_key, current, top_groups)

    return {
        "counts": dict(counts),
        "groups": groups,
    }


def _append_duplicate_group(
    groups: list[dict[str, Any]],
    counts: Counter,
    stem_key: str,
    records: list[CatalogRecord],
    top_groups: int,
) -> None:
    counts["duplicate_groups_total"] += 1
    counts["duplicate_files_total"] += len(records)
    ext_set = sorted({record.extension for record in records})
    is_cross_type = len(ext_set) > 1
    if is_cross_type:
        counts["same_name_different_type_groups_total"] += 1
    keep = sorted(
        records,
        key=lambda item: (
            item.extension in {".flac", ".wav", ".aiff", ".aif"},
            item.size or 0,
            -(item.duration or 0.0),
        ),
        reverse=True,
    )[0]
    if is_cross_type or len(groups) < top_groups:
        groups.append(
            {
                "stem_key": stem_key,
                "keep": keep.to_dict(),
                "candidates": [record.to_dict() for record in records],
                "extensions": ext_set,
                "duration_span": [
                    min(record.duration for record in records if record.duration is not None)
                    if any(record.duration is not None for record in records)
                    else None,
                    max(record.duration for record in records if record.duration is not None)
                    if any(record.duration is not None for record in records)
                    else None,
                ],
            }
        )


def audit_rekordbox_library(
    *,
    music_root: str | pathlib.Path,
    consolidate_root: str | pathlib.Path | None = None,
    duration_tolerance_s: float = 2.0,
    top_candidates: int = 5,
    catalog_workers: int = 8,
) -> dict[str, Any]:
    rows = _load_rekordbox_rows()
    catalog = build_music_catalog(music_root, workers=catalog_workers)
    relinks = suggest_relinks_for_rows(
        rows,
        catalog,
        music_root=music_root,
        consolidate_root=consolidate_root,
        duration_tolerance_s=duration_tolerance_s,
        top_candidates=top_candidates,
    )
    duplicates = find_name_duration_duplicates(catalog, duration_tolerance_s=duration_tolerance_s)
    return {
        "music_root": str(pathlib.Path(music_root).resolve()),
        "rekordbox_tracks_total": len(rows),
        "catalog_file_total": len(catalog["records"]),
        "rekordbox_audit": {
            "counts": relinks["counts"],
            "samples": relinks["samples"],
        },
        "relink_suggestion_report": {
            "counts": {
                key: value
                for key, value in relinks["counts"].items()
                if key.endswith("_relink_total") or key in {"inside_root_existing_total", "inside_root_missing_total", "outside_root_existing_total", "outside_root_missing_total"}
            },
            "suggestions": relinks["relink_suggestions"],
        },
        "consolidation_plan_report": {
            "counts": {
                key: value
                for key, value in relinks["counts"].items()
                if key.endswith("_total")
                and key.startswith(("move_into_music_root_then_relink", "relink_to_existing_inside_root", "manual_review"))
            },
            "plan": relinks["consolidation_plan"],
            "consolidate_root": relinks["consolidate_root"],
        },
        "duplicate_dry_run_report": duplicates,
    }


def dump_report(report: dict[str, Any], out_path: str | pathlib.Path) -> pathlib.Path:
    target = pathlib.Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return target
