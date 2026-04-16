from __future__ import annotations

import copy
import json
import pathlib
import re
import unicodedata
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from datetime import datetime, timezone
from typing import Iterable

from rbassist.utils import (
    DATA,
    ROOT,
    is_junk_path,
    load_meta,
    normalize_path_string,
    read_paths_file,
    resolve_track_path,
    save_meta,
    walk_audio,
)

try:
    from mutagen import File as MFile  # type: ignore
except Exception:
    MFile = None

MERGE_SET_FIELDS = {"mytags", "tags"}
MERGE_PREFER_LONGER_LIST_FIELDS = {"cues", "tempos"}


def _is_bare_path(path: str | pathlib.Path) -> bool:
    candidate = pathlib.Path(str(path))
    return not candidate.drive and not candidate.is_absolute()


def _is_empty(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    return False


def _embedding_exists(embedding_path: str | pathlib.Path | None, *, repo: pathlib.Path) -> bool:
    if not embedding_path:
        return False
    path = pathlib.Path(str(embedding_path))
    if not path.is_absolute():
        path = (repo / path).resolve()
    return path.exists()


def _music_root_prefix(path: str | pathlib.Path) -> str | None:
    normalized = normalize_path_string(path)
    match = re.match(r"^([A-Z]:/Users/[^/]+/Music)(?:/.*)?$", normalized, re.IGNORECASE)
    if not match:
        return None
    return normalize_path_string(match.group(1))


def default_music_roots() -> list[str]:
    home_music = pathlib.Path.home() / "Music"
    if home_music.exists():
        return [str(home_music)]
    return []


def _classify_collision_group(source_paths: list[str]) -> str:
    normalized = {normalize_path_string(path) for path in source_paths}
    if len(normalized) == 1:
        return "slash_or_case_variants"
    has_legacy = any("TTSAdmin" in path for path in source_paths)
    has_current = any("Users/hunte" in path or "Users\\hunte" in path for path in source_paths)
    if has_legacy and has_current:
        return "legacy_root_plus_current"
    if has_legacy:
        return "legacy_root_variants"
    return "absolute_path_variants"


def _merge_unique_list(current, incoming) -> list:
    merged: list = []
    seen: set[str] = set()
    for value in list(current or []) + list(incoming or []):
        key = json.dumps(value, sort_keys=True, ensure_ascii=False) if isinstance(value, (dict, list)) else repr(value)
        if key in seen:
            continue
        seen.add(key)
        merged.append(copy.deepcopy(value))
    return merged


def _merge_dict_missing(current: dict, incoming: dict) -> tuple[dict, list[str]]:
    merged = copy.deepcopy(current)
    conflicts: list[str] = []
    for key, value in incoming.items():
        if key not in merged or _is_empty(merged.get(key)):
            merged[key] = copy.deepcopy(value)
            continue
        if isinstance(merged.get(key), dict) and isinstance(value, dict):
            nested, nested_conflicts = _merge_dict_missing(merged[key], value)
            merged[key] = nested
            conflicts.extend([f"{key}.{item}" for item in nested_conflicts])
            continue
        if merged.get(key) != value:
            conflicts.append(str(key))
    return merged, conflicts


def _score_track_entry(path: str, info: dict, *, canonical_path: str, repo: pathlib.Path) -> float:
    score = 0.0
    if path == canonical_path:
        score += 200.0
    try:
        if resolve_track_path(path, base_dir=repo).exists():
            score += 120.0
    except Exception:
        pass
    if not _is_bare_path(path):
        score += 20.0
    if _embedding_exists(info.get("embedding"), repo=repo):
        score += 50.0
    if info.get("bpm"):
        score += 10.0
    if info.get("key"):
        score += 10.0
    if info.get("artist"):
        score += 5.0
    if info.get("title"):
        score += 5.0
    if info.get("cues"):
        score += 10.0 + len(info.get("cues", []))
    if info.get("tempos"):
        score += 10.0 + len(info.get("tempos", []))
    if info.get("mytags"):
        score += min(float(len(info.get("mytags", [])) * 2), 12.0)
    if info.get("tags"):
        score += min(float(len(info.get("tags", [])) * 2), 12.0)
    if info.get("features"):
        score += 10.0
    return score


def _merge_track_group(canonical_path: str, entries: list[dict], *, repo: pathlib.Path) -> tuple[dict, dict]:
    ranked = sorted(
        entries,
        key=lambda entry: _score_track_entry(entry["source_path"], entry["info"], canonical_path=canonical_path, repo=repo),
        reverse=True,
    )
    primary = ranked[0]
    merged = copy.deepcopy(primary["info"])
    conflict_fields: set[str] = set()

    for entry in ranked[1:]:
        info = entry["info"]
        for key, value in info.items():
            if _is_empty(value):
                continue
            current = merged.get(key)
            if key in MERGE_SET_FIELDS:
                merged[key] = _merge_unique_list(current, value)
                continue
            if key in MERGE_PREFER_LONGER_LIST_FIELDS:
                if _is_empty(current):
                    merged[key] = copy.deepcopy(value)
                elif list(current) != list(value):
                    if len(value) > len(current):
                        merged[key] = copy.deepcopy(value)
                    conflict_fields.add(key)
                continue
            if isinstance(current, dict) and isinstance(value, dict):
                merged[key], nested_conflicts = _merge_dict_missing(current, value)
                conflict_fields.update(nested_conflicts)
                continue
            if _is_empty(current):
                merged[key] = copy.deepcopy(value)
                continue
            if current != value:
                conflict_fields.add(key)

    group_report = {
        "canonical_path": canonical_path,
        "kept_path": primary["source_path"],
        "source_paths": [entry["source_path"] for entry in entries],
        "group_kind": _classify_collision_group([entry["source_path"] for entry in entries]),
        "conflict_fields": sorted(conflict_fields),
        "merged_entry_count": len(entries),
    }
    return merged, group_report


def suggest_rewrite_pairs(health_report: dict, music_roots: Iterable[str]) -> list[tuple[str, str]]:
    current_prefixes = sorted({_music_root_prefix(root) for root in music_roots if _music_root_prefix(root)})
    if not current_prefixes:
        return []
    current_prefix = current_prefixes[0]
    stale_paths = health_report.get("samples", {}).get("stale_paths", []) if isinstance(health_report, dict) else []
    legacy_prefixes = sorted(
        {
            prefix
            for prefix in (_music_root_prefix(path) for path in stale_paths)
            if prefix and prefix != current_prefix
        }
    )
    return [(prefix, current_prefix) for prefix in legacy_prefixes]




def _normalize_music_roots(roots: Iterable[str] | None) -> list[str]:
    normalized: list[str] = []
    for root in roots or []:
        raw = str(root or '').strip()
        if not raw:
            continue
        normalized.append(normalize_path_string(pathlib.Path(raw).expanduser()))
    return sorted(dict.fromkeys(normalized))


def _path_within_roots(path: str | pathlib.Path, normalized_roots: Iterable[str]) -> bool:
    candidate = normalize_path_string(path)
    for root in normalized_roots:
        base = root.rstrip('/')
        if candidate == base or candidate.startswith(base + '/'):
            return True
    return False


def _load_rekordbox_source_index(rekordbox_report: dict | None) -> dict[str, list[str]]:
    index: dict[str, list[str]] = defaultdict(list)
    if not isinstance(rekordbox_report, dict):
        return index

    for item in rekordbox_report.get('relink_suggestion_report', {}).get('suggestions', []) or []:
        source_path = str(item.get('source_path', '')).strip()
        row_id = str(item.get('id', '')).strip()
        if source_path and row_id:
            normalized = normalize_path_string(source_path)
            if row_id not in index[normalized]:
                index[normalized].append(row_id)

    for item in rekordbox_report.get('consolidation_plan_report', {}).get('plan', []) or []:
        source_path = str(item.get('source_path', '')).strip()
        row_id = str(item.get('id', '')).strip()
        if source_path and row_id:
            normalized = normalize_path_string(source_path)
            if row_id not in index[normalized]:
                index[normalized].append(row_id)

    return index


def _write_repo_meta_backup(*, repo: pathlib.Path, meta: dict, prefix: str) -> pathlib.Path:
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    backup_dir = repo / 'data' / 'backups'
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f'{prefix}_{stamp}.json'
    source_meta = repo / 'data' / 'meta.json'
    if source_meta.exists():
        backup_path.write_text(source_meta.read_text(encoding='utf-8'), encoding='utf-8')
    else:
        backup_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding='utf-8')
    return backup_path

def audit_meta_health(
    *,
    repo: pathlib.Path | None = None,
    meta: dict | None = None,
    roots: list[str] | None = None,
    rekordbox_report: dict | None = None,
) -> dict:
    repo = (repo or ROOT).resolve()
    meta = meta if meta is not None else load_meta()
    tracks = meta.get("tracks", {})
    counts = Counter()
    stale_paths: list[str] = []
    bare_paths: list[str] = []
    junk_paths: list[str] = []
    broken_embedding_paths: list[str] = []
    duplicate_norm_keys = Counter()

    for path, info in tracks.items():
        info = info or {}
        counts["tracks_total"] += 1
        normalized = normalize_path_string(path)
        duplicate_norm_keys[normalized] += 1
        if _is_bare_path(path):
            counts["bare_path_total"] += 1
            bare_paths.append(str(path))
        try:
            resolved = resolve_track_path(path, base_dir=repo)
            if not resolved.exists():
                counts["stale_track_path_total"] += 1
                stale_paths.append(str(path))
        except Exception:
            counts["stale_track_path_total"] += 1
            stale_paths.append(str(path))
        if is_junk_path(path):
            counts["junk_path_total"] += 1
            junk_paths.append(str(path))

        embedding_path = info.get("embedding")
        if embedding_path:
            counts["embedding_field_total"] += 1
            if _embedding_exists(embedding_path, repo=repo):
                counts["embedding_ok"] += 1
            else:
                counts["embedding_file_missing"] += 1
                broken_embedding_paths.append(str(path))
        else:
            counts["missing_embedding_ref"] += 1

        if not info.get("bpm"):
            counts["missing_bpm_total"] += 1
        if not info.get("key"):
            counts["missing_key_total"] += 1
        if not info.get("cues"):
            counts["missing_cues_total"] += 1
        if not info.get("mytags"):
            counts["missing_mytags_total"] += 1

    counts["duplicate_normalized_path_keys"] = sum(1 for _, count in duplicate_norm_keys.items() if count > 1)
    counts["embedding_gap_total"] = counts["missing_embedding_ref"] + counts["embedding_file_missing"]
    counts["missing_analysis_total"] = sum(1 for info in tracks.values() if not (info.get("bpm") and info.get("key")))

    report = {
        "repo": str(repo),
        "counts": dict(counts),
        "samples": {
            "stale_paths": stale_paths[:25],
            "bare_paths": bare_paths[:25],
            "junk_paths": junk_paths[:25],
            "broken_embedding_paths": broken_embedding_paths[:25],
        },
    }

    triage_roots = roots if roots is not None else default_music_roots()
    if triage_roots:
        triage = triage_stale_meta_paths(repo=repo, roots=triage_roots, meta=meta, rekordbox_report=rekordbox_report)
        triage_counts = triage.get("counts", {})
        for key in (
            "stale_inside_root_total",
            "stale_outside_root_total",
            "stale_archive_remove_total",
            "stale_keep_review_total",
        ):
            report["counts"][key] = triage_counts.get(key, 0)
        report["stale_triage"] = {
            "counts": {
                key: triage_counts.get(key, 0)
                for key in (
                    "stale_total",
                    "stale_inside_root_total",
                    "stale_outside_root_total",
                    "stale_archive_remove_total",
                    "stale_keep_review_total",
                    "inside_root_relink_candidate_total",
                    "outside_root_rekordbox_candidate_total",
                    "duplicate_stale_candidate_total",
                )
            },
            "samples": triage.get("samples", {}),
        }
    return report


def list_embedding_gaps(
    *,
    repo: pathlib.Path | None = None,
    roots: list[str],
    exclude_file: str = "",
    out_prefix: str | pathlib.Path | None = None,
    chunk_size: int = 2000,
    meta: dict | None = None,
) -> dict:
    repo = (repo or ROOT).resolve()
    meta = meta if meta is not None else load_meta()
    tracks = meta.get("tracks", {})
    excludes: set[str] = set()
    if exclude_file:
        for path in read_paths_file(exclude_file):
            excludes.add(normalize_path_string(path))
    counts = Counter()
    counts["exclude_entries_total"] = len(excludes)

    meta_lookup: dict[str, dict] = {}
    for path, info in tracks.items():
        meta_lookup[normalize_path_string(path)] = info or {}

    scanned = walk_audio(roots)
    pending: list[str] = []
    missing_meta: list[str] = []
    missing_embedding_ref: list[str] = []
    stale_meta_paths: list[str] = []

    for audio in scanned:
        normalized = normalize_path_string(audio)
        if normalized in excludes:
            counts["excluded_audio_files_total"] += 1
            continue
        if is_junk_path(audio):
            continue
        counts["audio_files_scanned"] += 1
        info = meta_lookup.get(normalized)
        if info is None:
            counts["missing_meta_total"] += 1
            missing_meta.append(audio)
            pending.append(audio)
            continue
        if _embedding_exists(info.get("embedding"), repo=repo):
            continue
        counts["missing_embedding_ref_total"] += 1
        missing_embedding_ref.append(audio)
        pending.append(audio)

    scanned_norm = {normalize_path_string(path) for path in scanned}
    for path in tracks.keys():
        if normalize_path_string(path) not in scanned_norm:
            counts["stale_meta_paths_total"] += 1
            stale_meta_paths.append(str(path))

    pending = sorted(dict.fromkeys(pending))
    counts["pending_embedding_total"] = len(pending)

    output_paths_file = ""
    output_json_file = ""
    chunk_files: list[str] = []
    if out_prefix:
        output_prefix = pathlib.Path(out_prefix)
        if not output_prefix.is_absolute():
            output_prefix = (repo / output_prefix).resolve()
        output_prefix.parent.mkdir(parents=True, exist_ok=True)

        txt_path = output_prefix.with_suffix(".txt")
        txt_path.write_text("\n".join(pending) + ("\n" if pending else ""), encoding="utf-8")
        output_paths_file = str(txt_path)

        if chunk_size > 0 and pending:
            for idx, start in enumerate(range(0, len(pending), chunk_size), start=1):
                part_path = output_prefix.with_name(f"{output_prefix.name}.part{idx:03d}.txt")
                chunk = pending[start:start + chunk_size]
                part_path.write_text("\n".join(chunk) + "\n", encoding="utf-8")
                chunk_files.append(str(part_path))

    report = {
        "repo": str(repo),
        "music_roots": roots,
        "counts": dict(counts),
        "output_paths_file": output_paths_file,
        "output_json_file": output_json_file,
        "chunk_files": chunk_files,
        "samples": {
            "missing_meta": missing_meta[:25],
            "missing_embedding_ref": missing_embedding_ref[:25],
            "stale_meta_paths": stale_meta_paths[:25],
            "pending_embedding": pending[:25],
        },
    }

    if out_prefix:
        json_path = pathlib.Path(output_paths_file).with_suffix(".json")
        json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        report["output_json_file"] = str(json_path)
    return report


def _build_normalized_track_plan(
    *,
    repo: pathlib.Path,
    tracks: dict[str, dict],
    rewrite_from: list[str],
    rewrite_to: list[str],
    drop_junk: bool,
) -> dict:
    rewrites = list(zip(rewrite_from, rewrite_to))
    counts = Counter()
    changes: list[dict] = []
    review_only: list[str] = []
    collision_samples: list[dict] = []
    passthrough_tracks: dict[str, dict] = {}
    grouped_tracks: dict[str, list[dict]] = defaultdict(list)

    for path, info in tracks.items():
        original = str(path)
        candidate = original

        if drop_junk and is_junk_path(candidate):
            counts["dropped_junk"] += 1
            changes.append({"action": "drop_junk", "from": original, "to": None})
            continue

        if _is_bare_path(candidate):
            counts["review_only"] += 1
            review_only.append(original)
            passthrough_tracks[original] = copy.deepcopy(info)
            continue

        rewrite_applied = False
        normalized_candidate = normalize_path_string(candidate)
        for src, dst in rewrites:
            normalized_src = normalize_path_string(src)
            if normalized_candidate.startswith(normalized_src):
                suffix = normalized_candidate[len(normalized_src):].lstrip("/")
                candidate = str(pathlib.Path(dst) / pathlib.Path(suffix))
                rewrite_applied = True
                counts["rewritten_prefix"] += 1
                break

        try:
            resolved = str(resolve_track_path(candidate, base_dir=repo))
        except Exception:
            resolved = candidate

        if resolved != original:
            action = "rewrite" if rewrite_applied else "canonicalize"
            changes.append({"action": action, "from": original, "to": resolved})
            counts["changed_paths"] += 1

        grouped_tracks[resolved].append(
            {
                "source_path": original,
                "candidate_path": candidate,
                "info": copy.deepcopy(info),
            }
        )

    for canonical_path, entries in grouped_tracks.items():
        if len(entries) <= 1:
            continue
        counts["collision_groups_total"] += 1
        counts["collisions_total"] += len(entries) - 1
        if len(collision_samples) < 250:
            collision_samples.append(
                {
                    "canonical_path": canonical_path,
                    "group_kind": _classify_collision_group([entry["source_path"] for entry in entries]),
                    "source_paths": [entry["source_path"] for entry in entries],
                }
            )

    return {
        "counts": counts,
        "changes": changes,
        "review_only": review_only,
        "passthrough_tracks": passthrough_tracks,
        "grouped_tracks": grouped_tracks,
        "collisions": collision_samples,
    }


def remediate_meta_collisions(
    *,
    repo: pathlib.Path | None = None,
    grouped_tracks: dict[str, list[dict]],
) -> dict:
    repo = (repo or ROOT).resolve()
    counts = Counter()
    group_kinds = Counter()
    merged_tracks: dict[str, dict] = {}
    merged_groups: list[dict] = []
    conflicting_groups: list[dict] = []

    for canonical_path, entries in grouped_tracks.items():
        if len(entries) == 1:
            merged_tracks[canonical_path] = copy.deepcopy(entries[0]["info"])
            continue

        counts["collision_groups_total"] += 1
        counts["collisions_total"] += len(entries) - 1
        merged_info, group_report = _merge_track_group(canonical_path, entries, repo=repo)
        merged_tracks[canonical_path] = merged_info
        counts["resolved_collision_groups_total"] += 1
        counts["merged_collision_entries_total"] += len(entries) - 1
        if group_report["conflict_fields"]:
            counts["conflicting_groups_total"] += 1
            counts["conflicting_fields_total"] += len(group_report["conflict_fields"])
            if len(conflicting_groups) < 100:
                conflicting_groups.append(group_report)
        group_kinds[group_report["group_kind"]] += 1
        if len(merged_groups) < 100:
            merged_groups.append(group_report)

    return {
        "counts": dict(counts),
        "group_kinds": dict(group_kinds),
        "samples": {
            "merged_groups": merged_groups,
            "conflicting_groups": conflicting_groups,
        },
        "merged_tracks": merged_tracks,
    }


def normalize_meta_paths(
    *,
    repo: pathlib.Path | None = None,
    rewrite_from: list[str] | None = None,
    rewrite_to: list[str] | None = None,
    drop_junk: bool = False,
    apply_changes: bool = False,
    resolve_collisions: bool = False,
    meta: dict | None = None,
) -> dict:
    repo = (repo or ROOT).resolve()
    meta = meta if meta is not None else load_meta()
    tracks = meta.get("tracks", {})
    rewrite_from = rewrite_from or []
    rewrite_to = rewrite_to or []
    if len(rewrite_from) != len(rewrite_to):
        raise ValueError("rewrite_from and rewrite_to must have the same length")

    plan = _build_normalized_track_plan(
        repo=repo,
        tracks=tracks,
        rewrite_from=rewrite_from,
        rewrite_to=rewrite_to,
        drop_junk=drop_junk,
    )

    report = {
        "repo": str(repo),
        "counts": dict(plan["counts"]),
        "changes": plan["changes"][:250],
        "review_only": plan["review_only"][:250],
        "collisions": plan["collisions"][:250],
        "applied": False,
    }

    new_tracks = dict(plan["passthrough_tracks"])
    if resolve_collisions:
        resolution = remediate_meta_collisions(repo=repo, grouped_tracks=plan["grouped_tracks"])
        report["collision_resolution"] = {
            "counts": resolution["counts"],
            "group_kinds": resolution["group_kinds"],
            "samples": resolution["samples"],
        }
        report["counts"]["resolved_collision_groups_total"] = resolution["counts"].get("resolved_collision_groups_total", 0)
        report["counts"]["merged_collision_entries_total"] = resolution["counts"].get("merged_collision_entries_total", 0)
        report["counts"]["conflicting_groups_total"] = resolution["counts"].get("conflicting_groups_total", 0)
        report["counts"]["conflicting_fields_total"] = resolution["counts"].get("conflicting_fields_total", 0)
        new_tracks.update(resolution["merged_tracks"])
    else:
        for canonical_path, entries in plan["grouped_tracks"].items():
            if len(entries) == 1:
                new_tracks[canonical_path] = copy.deepcopy(entries[0]["info"])

    if apply_changes:
        if plan["counts"].get("collisions_total", 0) and not resolve_collisions:
            report["blocked_reason"] = "collisions_detected"
            return report
        if resolve_collisions and not report["counts"].get("resolved_collision_groups_total", 0) and plan["counts"].get("collisions_total", 0):
            report["blocked_reason"] = "collision_resolution_failed"
            return report
        meta["tracks"] = new_tracks
        save_meta(meta)
        report["applied"] = True
    return report



def triage_stale_meta_paths(
    *,
    repo: pathlib.Path | None = None,
    roots: list[str],
    meta: dict | None = None,
    rekordbox_report: dict | None = None,
) -> dict:
    repo = (repo or ROOT).resolve()
    meta = meta if meta is not None else load_meta()
    tracks = meta.get("tracks", {})
    normalized_roots = _normalize_music_roots(roots)
    if not normalized_roots:
        raise ValueError("Provide at least one active music root for stale-path triage")

    rekordbox_index = _load_rekordbox_source_index(rekordbox_report)
    existing_by_basename: dict[str, list[dict[str, str]]] = defaultdict(list)
    for track_path in tracks.keys():
        if _is_bare_path(track_path):
            continue
        try:
            resolved = resolve_track_path(track_path, base_dir=repo)
        except Exception:
            continue
        if not resolved.exists():
            continue
        existing_by_basename[pathlib.Path(str(track_path)).name.lower()].append(
            {
                "path": str(track_path),
                "normalized_path": normalize_path_string(track_path),
            }
        )

    counts = Counter()
    samples: dict[str, list[dict]] = defaultdict(list)
    entries: list[dict] = []

    for path, info in tracks.items():
        if _is_bare_path(path):
            continue
        info = info or {}
        try:
            resolved = resolve_track_path(path, base_dir=repo)
            exists_on_disk = resolved.exists()
        except Exception:
            exists_on_disk = False
        if exists_on_disk:
            continue

        normalized_path = normalize_path_string(path)
        inside_active_root = _path_within_roots(path, normalized_roots)
        basename = pathlib.Path(str(path)).name.lower()
        duplicate_candidates = [
            item["path"]
            for item in existing_by_basename.get(basename, [])
            if item["normalized_path"] != normalized_path
        ]
        rekordbox_row_ids = sorted(set(rekordbox_index.get(normalized_path, [])))
        has_embedding = _embedding_exists(info.get("embedding"), repo=repo)
        has_bpm = bool(info.get("bpm"))
        has_key = bool(info.get("key"))
        has_cues = bool(info.get("cues"))
        has_mytags = bool(info.get("mytags"))

        if duplicate_candidates:
            suggested_action = "duplicate_stale_candidate"
            reason = "existing_active_entry_with_same_basename"
        elif inside_active_root:
            suggested_action = "inside_root_relink_candidate"
            reason = "stale_path_inside_active_root"
        elif rekordbox_row_ids:
            suggested_action = "outside_root_rekordbox_candidate"
            reason = "stale_path_referenced_by_rekordbox"
        elif not any([has_embedding, has_bpm, has_key, has_cues, has_mytags]):
            suggested_action = "archive_remove"
            reason = "outside_root_stale_without_metadata_or_rekordbox_reference"
        else:
            suggested_action = "keep_review"
            reason = "outside_root_stale_with_metadata_or_unclear_origin"

        entry = {
            "path": str(path),
            "normalized_path": normalized_path,
            "inside_active_root": inside_active_root,
            "exists_on_disk": exists_on_disk,
            "has_embedding": has_embedding,
            "has_bpm": has_bpm,
            "has_key": has_key,
            "has_cues": has_cues,
            "has_mytags": has_mytags,
            "in_rekordbox": bool(rekordbox_row_ids),
            "rekordbox_row_ids": rekordbox_row_ids,
            "suggested_action": suggested_action,
            "reason": reason,
            "duplicate_candidate_paths": duplicate_candidates[:10],
        }
        entries.append(entry)
        counts["stale_total"] += 1
        if inside_active_root:
            counts["stale_inside_root_total"] += 1
        else:
            counts["stale_outside_root_total"] += 1
        counts[f"{suggested_action}_total"] += 1
        if len(samples[suggested_action]) < 50:
            samples[suggested_action].append(entry)

    counts["stale_archive_remove_total"] = counts.get("archive_remove_total", 0)
    counts["stale_keep_review_total"] = counts.get("keep_review_total", 0)
    return {
        "repo": str(repo),
        "music_roots": [str(pathlib.Path(root)) for root in roots],
        "counts": dict(counts),
        "samples": dict(samples),
        "entries": entries,
        "applied": False,
    }


def apply_stale_meta_cleanup(
    *,
    repo: pathlib.Path | None = None,
    roots: list[str],
    archive_path: str | pathlib.Path | None = None,
    apply_changes: bool = False,
    meta: dict | None = None,
    rekordbox_report: dict | None = None,
) -> dict:
    repo = (repo or ROOT).resolve()
    meta = meta if meta is not None else load_meta()
    report = triage_stale_meta_paths(repo=repo, roots=roots, meta=meta, rekordbox_report=rekordbox_report)
    removable = [entry for entry in report.get("entries", []) if entry.get("suggested_action") == "archive_remove"]
    report["removed_paths"] = [entry["path"] for entry in removable]
    report["archive_path"] = ""
    report["backup_path"] = ""

    if not apply_changes:
        return report

    tracks = meta.get("tracks", {})
    backup_path_ref = _write_repo_meta_backup(repo=repo, meta=meta, prefix='meta_before_stale_cleanup')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    archive_target = pathlib.Path(archive_path) if archive_path else (repo / 'data' / 'archives' / f'meta_stale_archive_{stamp}.jsonl')
    if not archive_target.is_absolute():
        archive_target = (repo / archive_target).resolve()
    archive_target.parent.mkdir(parents=True, exist_ok=True)

    removed_lookup = {entry['path']: entry for entry in removable}
    archive_lines: list[str] = []
    for path, entry in removed_lookup.items():
        archive_record = {
            'path': path,
            'info': copy.deepcopy(tracks.get(path, {})),
            'normalized_path': entry['normalized_path'],
            'suggested_action': entry['suggested_action'],
            'reason': entry['reason'],
            'archived_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        }
        archive_lines.append(json.dumps(archive_record, ensure_ascii=False))

    archive_target.write_text('\n'.join(archive_lines) + ('\n' if archive_lines else ''), encoding='utf-8')
    meta['tracks'] = {path: copy.deepcopy(info) for path, info in tracks.items() if path not in removed_lookup}
    save_meta(meta)
    report['applied'] = True
    report['backup_path'] = str(backup_path_ref)
    report['archive_path'] = str(archive_target)
    return report


def default_gap_output_prefix() -> pathlib.Path:
    return DATA / "pending_embedding_paths.health"




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


def _name_similarity(left: str | None, right: str | None) -> float:
    left_key = _name_key(left)
    right_key = _name_key(right)
    if not left_key or not right_key:
        return 0.0
    return SequenceMatcher(None, left_key, right_key).ratio()


def _duration_of_audio(path: str | pathlib.Path) -> float | None:
    if MFile is None:
        return None
    try:
        media = MFile(str(path))
        length = float(getattr(getattr(media, "info", None), "length", 0.0) or 0.0)
        return round(length, 3) if length > 0 else None
    except Exception:
        return None


def _duration_from_track_info(info: dict | None) -> float | None:
    if not isinstance(info, dict):
        return None
    raw = info.get("duration")
    try:
        value = float(raw)
    except Exception:
        return None
    return value if value > 0 else None


def _score_bare_candidate(
    *,
    source_path: str,
    source_info: dict,
    candidate_path: str,
    candidate_info: dict | None,
) -> dict:
    source_name = pathlib.Path(source_path).name
    source_stem = pathlib.Path(source_path).stem
    candidate_name = pathlib.Path(candidate_path).name
    candidate_stem = pathlib.Path(candidate_path).stem
    source_ext = pathlib.Path(source_path).suffix.lower()
    candidate_ext = pathlib.Path(candidate_path).suffix.lower()

    confidence = 0.0
    reasons: list[str] = []
    if source_name.lower() == candidate_name.lower():
        confidence = max(confidence, 0.98)
        reasons.append("exact_basename")

    name_similarity = _name_similarity(source_stem, candidate_stem)
    if name_similarity >= 0.98:
        confidence = max(confidence, 0.97)
        reasons.append("normalized_name_similarity_ge_0_98")
    elif name_similarity >= 0.92:
        confidence = max(confidence, 0.9)
        reasons.append("normalized_name_similarity_ge_0_92")
    elif name_similarity >= 0.85:
        confidence = max(confidence, 0.84)
        reasons.append("normalized_name_similarity_ge_0_85")
    elif name_similarity >= 0.75:
        confidence = max(confidence, 0.82)
        reasons.append("normalized_name_similarity_ge_0_75")

    if source_ext and source_ext == candidate_ext:
        confidence = min(1.0, max(confidence, 0.0) + 0.01)
        reasons.append("same_extension")

    source_duration = _duration_from_track_info(source_info)
    candidate_duration = _duration_from_track_info(candidate_info) or _duration_of_audio(candidate_path)
    duration_delta = None
    if source_duration is not None and candidate_duration is not None:
        duration_delta = round(abs(source_duration - candidate_duration), 3)
        if duration_delta <= 2.0:
            confidence = min(1.0, confidence + 0.03)
            reasons.append("duration_within_2s")
        elif duration_delta > 5.0:
            confidence = min(confidence, 0.79)
            reasons.append("duration_mismatch_gt_5s")

    return {
        "path": candidate_path,
        "candidate_path": candidate_path,
        "confidence": round(confidence, 3),
        "match_reasons": reasons,
        "duration_delta": duration_delta,
        "name_similarity": round(name_similarity, 3),
        "existing_absolute_entry": candidate_info is not None,
    }

def resolve_bare_meta_paths(
    *,
    repo: pathlib.Path | None = None,
    roots: list[str] | None = None,
    apply_changes: bool = False,
    min_confidence: float = 0.92,
    meta: dict | None = None,
) -> dict:
    repo = (repo or ROOT).resolve()
    meta = meta if meta is not None else load_meta()
    tracks = meta.get("tracks", {})
    roots = [str(pathlib.Path(root).expanduser()) for root in (roots or default_music_roots())]
    if not roots:
        raise ValueError("Provide at least one music root for bare-path resolution")

    scanned_files = walk_audio(roots)
    by_name: dict[str, list[str]] = defaultdict(list)
    by_stem: dict[str, list[str]] = defaultdict(list)
    by_first_token: dict[str, list[str]] = defaultdict(list)
    absolute_info_lookup: dict[str, dict] = {}

    for path, info in tracks.items():
        if _is_bare_path(path):
            continue
        absolute_info_lookup[normalize_path_string(path)] = info or {}

    for path in scanned_files:
        name = pathlib.Path(path).name.lower()
        stem_key = _name_key(pathlib.Path(path).stem)
        by_name[name].append(path)
        if stem_key:
            by_stem[stem_key].append(path)
            first_token = stem_key.split()[0]
            if first_token:
                by_first_token[first_token].append(path)

    counts = Counter()
    grouped_tracks: dict[str, list[dict]] = defaultdict(list)
    samples: dict[str, list[dict]] = defaultdict(list)
    entries: list[dict] = []

    for path, info in tracks.items():
        if not _is_bare_path(path):
            grouped_tracks[str(path)].append({"source_path": str(path), "info": copy.deepcopy(info)})

    for path, info in tracks.items():
        if not _is_bare_path(path):
            continue
        counts["bare_total"] += 1
        source_path = str(path)
        source_info = info or {}
        source_name = pathlib.Path(source_path).name.lower()
        source_stem_key = _name_key(pathlib.Path(source_path).stem)
        first_token = source_stem_key.split()[0] if source_stem_key else ""

        candidate_pool: dict[str, str] = {}
        for candidate in by_name.get(source_name, []):
            candidate_pool[normalize_path_string(candidate)] = candidate
        for candidate in by_stem.get(source_stem_key, []):
            candidate_pool[normalize_path_string(candidate)] = candidate
        if first_token:
            for candidate in by_first_token.get(first_token, []):
                similarity = _name_similarity(pathlib.Path(source_path).stem, pathlib.Path(candidate).stem)
                if similarity >= 0.75:
                    candidate_pool[normalize_path_string(candidate)] = candidate

        scored_candidates = []
        for normalized_candidate, candidate in candidate_pool.items():
            candidate_info = absolute_info_lookup.get(normalized_candidate)
            scored = _score_bare_candidate(
                source_path=source_path,
                source_info=source_info,
                candidate_path=candidate,
                candidate_info=candidate_info,
            )
            if scored["confidence"] >= 0.8 or "exact_basename" in scored["match_reasons"]:
                scored_candidates.append(scored)
        scored_candidates = sorted(scored_candidates, key=lambda item: (item["confidence"], item["name_similarity"]), reverse=True)

        classification = "not_found"
        best_candidate = None
        if not scored_candidates:
            counts["missing_matches_total"] += 1
        elif len(scored_candidates) == 1:
            best_candidate = scored_candidates[0]
            counts["unique_matches_total"] += 1
            if best_candidate["confidence"] >= min_confidence:
                classification = "high_confidence_unique"
                counts["high_confidence_unique_total"] += 1
            else:
                classification = "medium_confidence_unique"
                counts["medium_confidence_unique_total"] += 1
            if best_candidate["existing_absolute_entry"]:
                counts["matched_existing_absolute_total"] += 1
            else:
                counts["matched_new_absolute_total"] += 1
        else:
            classification = "ambiguous"
            counts["ambiguous_matches_total"] += 1
            best_candidate = scored_candidates[0]

        merged_into_existing = bool(best_candidate and best_candidate["existing_absolute_entry"])
        created_new_absolute_entry = bool(best_candidate and not best_candidate["existing_absolute_entry"] and classification == "high_confidence_unique")
        if classification == "high_confidence_unique" and best_candidate is not None:
            grouped_tracks[best_candidate["candidate_path"]].append({"source_path": source_path, "info": copy.deepcopy(source_info)})
            action_taken = "merge_high_confidence"
        else:
            grouped_tracks[source_path].append({"source_path": source_path, "info": copy.deepcopy(source_info)})
            action_taken = "review_only"

        entry = {
            "source_bare_path": source_path,
            "candidate_path": (best_candidate or {}).get("candidate_path", ""),
            "confidence": (best_candidate or {}).get("confidence", 0.0),
            "classification": classification,
            "match_reasons": (best_candidate or {}).get("match_reasons", []),
            "merged_into_existing": merged_into_existing,
            "created_new_absolute_entry": created_new_absolute_entry,
            "candidate_count": len(scored_candidates),
            "candidates": scored_candidates[:10],
            "action_taken": action_taken,
        }
        entries.append(entry)
        if len(samples[classification]) < 100:
            samples[classification].append(entry)

    merged_tracks: dict[str, dict] = {}
    merged_groups: list[dict] = []
    conflicting_groups: list[dict] = []
    group_kinds = Counter()
    for canonical_path, grouped_entries in grouped_tracks.items():
        if len(grouped_entries) == 1:
            merged_tracks[canonical_path] = copy.deepcopy(grouped_entries[0]["info"])
            continue
        merged_info, group_report = _merge_track_group(canonical_path, grouped_entries, repo=repo)
        merged_tracks[canonical_path] = merged_info
        counts["resolved_groups_total"] += 1
        counts["merged_entries_total"] += len(grouped_entries) - 1
        group_kinds[group_report["group_kind"]] += 1
        if group_report["conflict_fields"]:
            counts["conflicting_groups_total"] += 1
            counts["conflicting_fields_total"] += len(group_report["conflict_fields"])
            if len(conflicting_groups) < 100:
                conflicting_groups.append(group_report)
        if len(merged_groups) < 100:
            merged_groups.append(group_report)

    counts["unresolved_bare_total"] = counts.get("ambiguous_matches_total", 0) + counts.get("missing_matches_total", 0) + counts.get("medium_confidence_unique_total", 0)
    report = {
        "repo": str(repo),
        "music_roots": roots,
        "min_confidence": min_confidence,
        "counts": dict(counts),
        "entries": entries,
        "samples": {
            "high_confidence_unique": samples.get("high_confidence_unique", []),
            "medium_confidence_unique": samples.get("medium_confidence_unique", []),
            "ambiguous": samples.get("ambiguous", []),
            "not_found": samples.get("not_found", []),
            "merged_groups": merged_groups,
            "conflicting_groups": conflicting_groups,
        },
        "group_kinds": dict(group_kinds),
        "applied": False,
    }
    if apply_changes:
        meta["tracks"] = merged_tracks
        save_meta(meta)
        report["applied"] = True
    return report

