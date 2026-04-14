from __future__ import annotations

from dataclasses import dataclass
import json
import pathlib
import random
from typing import Any, Iterable

from .playlist_expand import SeedPlaylist, SeedTrack, list_rekordbox_playlists, load_rekordbox_playlist
from .utils import camelot_relation, load_meta, tempo_match


@dataclass(frozen=True)
class PairDatasetResult:
    rows: list[dict[str, Any]]
    diagnostics: dict[str, Any]


def _track_path(track: SeedTrack) -> str | None:
    value = track.meta_path or track.rekordbox_path
    return str(value) if value else None


def _eligible_tracks(playlist: SeedPlaylist, meta_tracks: dict[str, dict[str, Any]]) -> list[tuple[int, SeedTrack]]:
    eligible: list[tuple[int, SeedTrack]] = []
    for pos, track in enumerate(playlist.tracks):
        path = _track_path(track)
        if not path:
            continue
        info = meta_tracks.get(path, {})
        if not info.get("embedding"):
            continue
        eligible.append((pos, track))
    return eligible


def _row(
    *,
    left: SeedTrack,
    right: SeedTrack,
    label: float,
    pair_type: str,
    playlist: SeedPlaylist | None,
    left_position: int | None = None,
    right_position: int | None = None,
    reason: str = "",
    meta_tracks: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    left_path = _track_path(left) or ""
    right_path = _track_path(right) or ""
    left_info = meta_tracks.get(left_path, {})
    right_info = meta_tracks.get(right_path, {})
    left_bpm = left_info.get("bpm", left.bpm)
    right_bpm = right_info.get("bpm", right.bpm)
    left_key = left_info.get("key", left.key)
    right_key = right_info.get("key", right.key)
    bpm_delta_pct = None
    if isinstance(left_bpm, (int, float)) and isinstance(right_bpm, (int, float)) and left_bpm:
        bpm_delta_pct = abs(float(left_bpm) - float(right_bpm)) / float(left_bpm) * 100.0
    camelot_ok, camelot_rule = camelot_relation(left_key, right_key)
    left_tags = set(str(tag) for tag in (left_info.get("mytags") or left.mytags or []) if str(tag).strip())
    right_tags = set(str(tag) for tag in (right_info.get("mytags") or right.mytags or []) if str(tag).strip())
    playlist_diagnostics = playlist.diagnostics if playlist is not None else {}
    return {
        "left_path": left_path,
        "right_path": right_path,
        "label": float(label),
        "pair_type": pair_type,
        "reason": reason,
        "playlist_source": playlist.source if playlist is not None else None,
        "playlist_name": playlist.name if playlist is not None else None,
        "playlist_path": playlist_diagnostics.get("playlist_path") if isinstance(playlist_diagnostics, dict) else None,
        "left_position": left_position,
        "right_position": right_position,
        "bpm_delta_pct": round(float(bpm_delta_pct), 4) if bpm_delta_pct is not None else None,
        "camelot_compatible": bool(camelot_ok),
        "camelot_rule": camelot_rule,
        "shared_tags": sorted(left_tags & right_tags),
        "left_bpm": left_bpm,
        "right_bpm": right_bpm,
        "left_key": left_key,
        "right_key": right_key,
        "left_embedding": left_info.get("embedding", left.embedding_path),
        "right_embedding": right_info.get("embedding", right.embedding_path),
        "diagnostics": {
            "reason": reason,
            "left_status": left.status,
            "right_status": right.status,
            "left_matched_by": left.matched_by,
            "right_matched_by": right.matched_by,
        },
    }


def _pair_key(left: SeedTrack, right: SeedTrack, pair_type: str) -> tuple[str, str, str]:
    paths = sorted([_track_path(left) or "", _track_path(right) or ""])
    return pair_type, paths[0], paths[1]


def _candidate_negative_label(
    left: SeedTrack,
    right: SeedTrack,
    meta_tracks: dict[str, dict[str, Any]],
    *,
    tempo_pct: float,
    allow_doubletime: bool,
) -> tuple[float, str]:
    left_info = meta_tracks.get(_track_path(left) or "", {})
    right_info = meta_tracks.get(_track_path(right) or "", {})
    left_bpm = left_info.get("bpm", left.bpm)
    right_bpm = right_info.get("bpm", right.bpm)
    left_key = left_info.get("key", left.key)
    right_key = right_info.get("key", right.key)
    tempo_ok = tempo_match(left_bpm, right_bpm, pct=tempo_pct, allow_doubletime=allow_doubletime)
    key_ok, _ = camelot_relation(left_key, right_key)
    if tempo_ok and key_ok:
        return 0.3, "different_playlist_similar_bpm_key"
    if tempo_ok:
        return 0.2, "different_playlist_similar_bpm_incompatible_key"
    return 0.0, "different_playlist_dissimilar_bpm_or_key"


def build_playlist_pair_dataset(
    playlists: Iterable[SeedPlaylist],
    *,
    meta_tracks: dict[str, dict[str, Any]] | None = None,
    include_weak_positives: bool = True,
    negatives_per_positive: float = 1.0,
    max_pairs_per_playlist: int = 500,
    tempo_pct: float = 6.0,
    allow_doubletime: bool = True,
    random_seed: int = 13,
) -> PairDatasetResult:
    """Build read-only playlist pair rows for future learned similarity training."""
    if meta_tracks is None:
        meta_tracks = load_meta().get("tracks", {})
    playlist_list = list(playlists)
    rng = random.Random(random_seed)
    rows: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str, str]] = set()
    eligible_by_playlist: list[tuple[SeedPlaylist, list[tuple[int, SeedTrack]]]] = []
    skipped_playlists = 0

    for playlist in playlist_list:
        eligible = _eligible_tracks(playlist, meta_tracks)
        if len(eligible) < 2:
            skipped_playlists += 1
            continue
        eligible_by_playlist.append((playlist, eligible))
        playlist_rows: list[dict[str, Any]] = []
        for (left_pos, left), (right_pos, right) in zip(eligible, eligible[1:]):
            key = _pair_key(left, right, "adjacent_positive")
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            playlist_rows.append(
                _row(
                    left=left,
                    right=right,
                    label=1.0,
                    pair_type="adjacent_positive",
                    playlist=playlist,
                    left_position=left_pos,
                    right_position=right_pos,
                    reason="adjacent_tracks_in_playlist",
                    meta_tracks=meta_tracks,
                )
            )
        if include_weak_positives:
            weak_pairs: list[tuple[int, SeedTrack, int, SeedTrack]] = []
            for idx, (left_pos, left) in enumerate(eligible):
                for right_pos, right in eligible[idx + 2 :]:
                    weak_pairs.append((left_pos, left, right_pos, right))
            rng.shuffle(weak_pairs)
            remaining = max(0, max_pairs_per_playlist - len(playlist_rows))
            for left_pos, left, right_pos, right in weak_pairs[:remaining]:
                key = _pair_key(left, right, "same_playlist_weak_positive")
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)
                playlist_rows.append(
                    _row(
                        left=left,
                        right=right,
                        label=0.7,
                        pair_type="same_playlist_weak_positive",
                        playlist=playlist,
                        left_position=left_pos,
                        right_position=right_pos,
                        reason="same_playlist_non_adjacent",
                        meta_tracks=meta_tracks,
                    )
                )
                if len(playlist_rows) >= max_pairs_per_playlist:
                    break
        rows.extend(playlist_rows[:max_pairs_per_playlist])

    positive_count = len(rows)
    negative_target = max(0, int(round(positive_count * max(0.0, float(negatives_per_positive)))))
    if negative_target and len(eligible_by_playlist) >= 2:
        pool: list[tuple[int, SeedTrack]] = []
        memberships: dict[str, set[str]] = {}
        for playlist_index, (playlist, eligible) in enumerate(eligible_by_playlist):
            playlist_id = playlist.name or playlist.seed_ref or str(playlist_index)
            for _, track in eligible:
                path = _track_path(track)
                if not path:
                    continue
                pool.append((playlist_index, track))
                memberships.setdefault(path, set()).add(playlist_id)
        candidates: list[tuple[SeedTrack, SeedTrack]] = []
        for idx, (left_playlist, left) in enumerate(pool):
            left_path = _track_path(left) or ""
            for right_playlist, right in pool[idx + 1 :]:
                right_path = _track_path(right) or ""
                if left_playlist == right_playlist or left_path == right_path:
                    continue
                if memberships.get(left_path, set()) & memberships.get(right_path, set()):
                    continue
                candidates.append((left, right))
        rng.shuffle(candidates)
        for left, right in candidates:
            key = _pair_key(left, right, "different_playlist_negative")
            if key in seen_pairs:
                continue
            label, reason = _candidate_negative_label(
                left,
                right,
                meta_tracks,
                tempo_pct=tempo_pct,
                allow_doubletime=allow_doubletime,
            )
            seen_pairs.add(key)
            rows.append(
                _row(
                    left=left,
                    right=right,
                    label=label,
                    pair_type="different_playlist_negative",
                    playlist=None,
                    reason=reason,
                    meta_tracks=meta_tracks,
                )
            )
            if len(rows) - positive_count >= negative_target:
                break

    diagnostics = {
        "playlists_total": len(playlist_list),
        "playlists_used": len(eligible_by_playlist),
        "playlists_skipped": skipped_playlists,
        "positive_pairs": positive_count,
        "negative_pairs": max(0, len(rows) - positive_count),
        "rows_total": len(rows),
        "max_pairs_per_playlist": int(max_pairs_per_playlist),
        "negatives_per_positive": float(negatives_per_positive),
        "random_seed": int(random_seed),
    }
    return PairDatasetResult(rows=rows, diagnostics=diagnostics)


def load_playlists_for_dataset(
    *,
    source: str = "db",
    playlist_refs: Iterable[str] | None = None,
    xml_path: str | pathlib.Path | None = None,
    max_playlists: int | None = None,
) -> list[SeedPlaylist]:
    source = str(source or "db").lower().strip()
    refs = [str(ref) for ref in (playlist_refs or []) if str(ref).strip()]
    if not refs:
        refs = []
        for item in list_rekordbox_playlists(source=source, xml_path=xml_path):
            if source == "db" and item.get("id") is not None:
                refs.append(f"db:{item['id']}|{item.get('path') or item.get('name') or ''}")
            else:
                refs.append(str(item.get("path") or item.get("name") or ""))
            if max_playlists and len(refs) >= max_playlists:
                break

    playlists: list[SeedPlaylist] = []
    for ref in refs:
        seed_ref: Any = ref
        playlist_path = ref
        if source == "db" and ref.startswith("db:"):
            payload = ref[3:]
            playlist_id, _, path_hint = payload.partition("|")
            seed_ref = int(playlist_id)
            playlist_path = path_hint or None
        playlists.append(load_rekordbox_playlist(seed_ref, source=source, playlist_path=playlist_path, xml_path=xml_path))
    return playlists


def write_pair_dataset_jsonl(rows: Iterable[dict[str, Any]], out_path: str | pathlib.Path) -> pathlib.Path:
    path = pathlib.Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    tmp.replace(path)
    return path
