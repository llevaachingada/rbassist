from __future__ import annotations

import copy
import json
import pathlib
import re
from collections import Counter, defaultdict
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


def audit_meta_health(*, repo: pathlib.Path | None = None, meta: dict | None = None) -> dict:
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
    return {
        "repo": str(repo),
        "counts": dict(counts),
        "samples": {
            "stale_paths": stale_paths[:25],
            "bare_paths": bare_paths[:25],
            "junk_paths": junk_paths[:25],
            "broken_embedding_paths": broken_embedding_paths[:25],
        },
    }


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


def default_gap_output_prefix() -> pathlib.Path:
    return DATA / "pending_embedding_paths.health"


def resolve_bare_meta_paths(
    *,
    repo: pathlib.Path | None = None,
    roots: list[str] | None = None,
    apply_changes: bool = False,
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
    for path in scanned_files:
        by_name[pathlib.Path(path).name.lower()].append(path)

    counts = Counter()
    bare_samples_unique: list[dict] = []
    bare_samples_ambiguous: list[dict] = []
    bare_samples_missing: list[dict] = []
    grouped_tracks: dict[str, list[dict]] = defaultdict(list)

    for path, info in tracks.items():
        if not _is_bare_path(path):
            grouped_tracks[str(path)].append({"source_path": str(path), "info": copy.deepcopy(info)})

    for path, info in tracks.items():
        if not _is_bare_path(path):
            continue
        counts["bare_total"] += 1
        filename = pathlib.Path(str(path)).name.lower()
        matches = sorted(dict.fromkeys(by_name.get(filename, [])))
        if len(matches) == 1:
            target = matches[0]
            counts["unique_matches_total"] += 1
            if target in tracks:
                counts["matched_existing_absolute_total"] += 1
            else:
                counts["matched_new_absolute_total"] += 1
            grouped_tracks[target].append({"source_path": str(path), "info": copy.deepcopy(info)})
            if len(bare_samples_unique) < 100:
                bare_samples_unique.append({"from": str(path), "to": target})
        elif len(matches) > 1:
            counts["ambiguous_matches_total"] += 1
            if len(bare_samples_ambiguous) < 100:
                bare_samples_ambiguous.append({"from": str(path), "candidates": matches[:10]})
            grouped_tracks[str(path)].append({"source_path": str(path), "info": copy.deepcopy(info)})
        else:
            counts["missing_matches_total"] += 1
            if len(bare_samples_missing) < 100:
                bare_samples_missing.append({"from": str(path)})
            grouped_tracks[str(path)].append({"source_path": str(path), "info": copy.deepcopy(info)})

    merged_tracks: dict[str, dict] = {}
    merged_groups: list[dict] = []
    conflicting_groups: list[dict] = []
    group_kinds = Counter()
    for canonical_path, entries in grouped_tracks.items():
        if len(entries) == 1:
            merged_tracks[canonical_path] = copy.deepcopy(entries[0]["info"])
            continue
        merged_info, group_report = _merge_track_group(canonical_path, entries, repo=repo)
        merged_tracks[canonical_path] = merged_info
        counts["resolved_groups_total"] += 1
        counts["merged_entries_total"] += len(entries) - 1
        group_kinds[group_report["group_kind"]] += 1
        if group_report["conflict_fields"]:
            counts["conflicting_groups_total"] += 1
            counts["conflicting_fields_total"] += len(group_report["conflict_fields"])
            if len(conflicting_groups) < 100:
                conflicting_groups.append(group_report)
        if len(merged_groups) < 100:
            merged_groups.append(group_report)

    counts["unresolved_bare_total"] = counts["ambiguous_matches_total"] + counts["missing_matches_total"]
    report = {
        "repo": str(repo),
        "music_roots": roots,
        "counts": dict(counts),
        "samples": {
            "unique_matches": bare_samples_unique,
            "ambiguous_matches": bare_samples_ambiguous,
            "missing_matches": bare_samples_missing,
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
