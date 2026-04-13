from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
import re
from types import SimpleNamespace
from typing import Any, Iterable, Sequence
from urllib.parse import unquote

import numpy as np

from .bpm_sources import normalize_rekordbox_bpm, track_bpm_sources
from .export_xml import write_rekordbox_xml
from .recommend import IDX, load_embedding_safe
from .utils import camelot_relation, load_meta, make_path_aliases, normalize_path_string, tempo_match

try:
    from pyrekordbox import Rekordbox6Database  # type: ignore
except Exception:  # pragma: no cover - optional dependency handling
    Rekordbox6Database = None  # type: ignore

try:
    from pyrekordbox.rbxml import RekordboxXml  # type: ignore
except Exception:  # pragma: no cover - optional dependency handling
    RekordboxXml = None  # type: ignore

try:
    import hnswlib  # type: ignore
except Exception:  # pragma: no cover - optional dependency handling
    hnswlib = None  # type: ignore


@dataclass(slots=True)
class SeedTrack:
    rekordbox_path: str
    meta_path: str | None
    title: str = ""
    artist: str = ""
    bpm: float | None = None
    rekordbox_bpm: float | None = None
    rbassist_bpm: float | None = None
    bpm_delta: float | None = None
    bpm_mismatch: bool = False
    bpm_source: str = "unknown"
    key: str | None = None
    mytags: list[str] = field(default_factory=list)
    embedding_path: str | None = None
    matched_by: str = "path"

    @property
    def export_path(self) -> str | None:
        return self.meta_path

    @property
    def matched_path(self) -> str | None:
        return self.meta_path

    @property
    def status(self) -> str:
        if not self.meta_path:
            return "unmapped"
        if not self.embedding_path:
            return "missing_embedding"
        return "matched"

    def to_dict(self) -> dict[str, Any]:
        return {
            "rekordbox_path": self.rekordbox_path,
            "matched_path": self.meta_path,
            "title": self.title,
            "artist": self.artist,
            "bpm": self.bpm,
            "rekordbox_bpm": self.rekordbox_bpm,
            "rbassist_bpm": self.rbassist_bpm,
            "bpm_delta": self.bpm_delta,
            "bpm_mismatch": self.bpm_mismatch,
            "bpm_source": self.bpm_source,
            "key": self.key,
            "mytags": list(self.mytags),
            "embedding_path": self.embedding_path,
            "matched_by": self.matched_by,
            "status": self.status,
        }


@dataclass(slots=True)
class SeedPlaylist:
    source: str
    seed_ref: str
    playlist_name: str | None
    tracks: list[SeedTrack] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def resolved_tracks(self) -> list[SeedTrack]:
        return [track for track in self.tracks if track.status == "matched"]

    @property
    def seed_tracks(self) -> list[SeedTrack]:
        return self.tracks

    @property
    def name(self) -> str:
        return self.playlist_name or self.seed_ref

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "seed_ref": self.seed_ref,
            "playlist_name": self.playlist_name,
            "seed_tracks": [track.to_dict() for track in self.tracks],
            "diagnostics": dict(self.diagnostics),
        }


@dataclass(slots=True)
class ExpandedTrack:
    path: str
    score: float
    base_score: float = 0.0
    final_score: float = 0.0
    ann_distance: float | None = None
    support_count: int = 1
    title: str = ""
    artist: str = ""
    bpm: float | None = None
    rekordbox_bpm: float | None = None
    rbassist_bpm: float | None = None
    bpm_delta: float | None = None
    bpm_mismatch: bool = False
    bpm_source: str = "unknown"
    key: str | None = None
    mytags: list[str] = field(default_factory=list)
    component_scores: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "score": round(float(self.score), 6),
            "base_score": round(float(self.base_score), 6),
            "final_score": round(float(self.final_score), 6),
            "ann_distance": self.ann_distance,
            "support_count": self.support_count,
            "title": self.title,
            "artist": self.artist,
            "bpm": self.bpm,
            "rekordbox_bpm": self.rekordbox_bpm,
            "rbassist_bpm": self.rbassist_bpm,
            "bpm_delta": self.bpm_delta,
            "bpm_mismatch": self.bpm_mismatch,
            "bpm_source": self.bpm_source,
            "key": self.key,
            "mytags": list(self.mytags),
            "component_scores": {key: round(float(value), 6) for key, value in self.component_scores.items()},
            "reasons": list(self.reasons),
        }


@dataclass(slots=True)
class ExpansionResult:
    seed_tracks: list[SeedTrack]
    added_tracks: list[ExpandedTrack]
    combined_tracks: list[str]
    diagnostics: dict[str, Any]
    target_total: int
    add_count: int
    strategy: str
    mode: str = "balanced"

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed_tracks": [track.to_dict() for track in self.seed_tracks],
            "added_tracks": [track.to_dict() for track in self.added_tracks],
            "combined_tracks": list(self.combined_tracks),
            "diagnostics": dict(self.diagnostics),
            "target_total": self.target_total,
            "add_count": self.add_count,
            "strategy": self.strategy,
            "mode": self.mode,
        }


@dataclass(slots=True)
class CandidateHit:
    path: str
    distance: float | None = None
    support_count: int = 1
    support_distance: float | None = None
    support_seeds: int = 1


@dataclass(slots=True)
class PlaylistExpansionWeights:
    ann_centroid: float = 0.30
    ann_seed_coverage: float = 0.20
    group_match: float = 0.16
    bpm_match: float = 0.12
    key_match: float = 0.08
    tag_match: float = 0.14
    transition_outro_to_intro: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            "ann_centroid": float(self.ann_centroid),
            "ann_seed_coverage": float(self.ann_seed_coverage),
            "group_match": float(self.group_match),
            "bpm_match": float(self.bpm_match),
            "key_match": float(self.key_match),
            "tag_match": float(self.tag_match),
            "transition_outro_to_intro": float(self.transition_outro_to_intro),
        }

    @classmethod
    def from_mapping(cls, mapping: dict[str, Any] | None = None) -> "PlaylistExpansionWeights":
        mapping = dict(mapping or {})
        return cls(
            ann_centroid=float(mapping.get("ann_centroid", mapping.get("ann", cls().ann_centroid))),
            ann_seed_coverage=float(mapping.get("ann_seed_coverage", cls().ann_seed_coverage)),
            group_match=float(mapping.get("group_match", cls().group_match)),
            bpm_match=float(mapping.get("bpm_match", mapping.get("bpm", cls().bpm_match))),
            key_match=float(mapping.get("key_match", mapping.get("key", cls().key_match))),
            tag_match=float(mapping.get("tag_match", mapping.get("tags", cls().tag_match))),
            transition_outro_to_intro=float(
                mapping.get(
                    "transition_outro_to_intro",
                    mapping.get("transition", cls().transition_outro_to_intro),
                )
            ),
        )

    def normalized(self) -> "PlaylistExpansionWeights":
        values = self.to_dict()
        total = sum(max(float(value), 0.0) for value in values.values())
        if total <= 0:
            raise ValueError("At least one playlist expansion weight must be positive.")
        return PlaylistExpansionWeights(**{key: max(float(value), 0.0) / total for key, value in values.items()})


@dataclass(slots=True)
class PlaylistExpansionFilters:
    tempo_pct: float = 6.0
    allow_doubletime: bool = True
    key_mode: str = "soft"
    require_tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tempo_pct": float(self.tempo_pct),
            "allow_doubletime": bool(self.allow_doubletime),
            "key_mode": str(self.key_mode),
            "require_tags": list(self.require_tags),
        }

    @classmethod
    def from_mapping(cls, mapping: dict[str, Any] | None = None) -> "PlaylistExpansionFilters":
        mapping = dict(mapping or {})
        key_mode = str(mapping.get("key_mode", cls().key_mode) or cls().key_mode).lower().strip()
        if key_mode not in {"off", "soft", "filter"}:
            key_mode = cls().key_mode
        require_tags = mapping.get("require_tags", [])
        if isinstance(require_tags, str):
            require_tags = [require_tags]
        return cls(
            tempo_pct=float(mapping.get("tempo_pct", cls().tempo_pct)),
            allow_doubletime=bool(mapping.get("allow_doubletime", mapping.get("doubletime", cls().allow_doubletime))),
            key_mode=key_mode,
            require_tags=[str(tag) for tag in (require_tags or []) if str(tag).strip()],
        )

    def merged(self, overrides: dict[str, Any] | None = None) -> "PlaylistExpansionFilters":
        base = self.to_dict()
        overrides = dict(overrides or {})
        if "camelot_filter" in overrides and overrides.get("camelot_filter"):
            overrides["key_mode"] = "filter"
        if "camelot_filter" in overrides and not overrides.get("camelot_filter") and "key_mode" not in overrides:
            overrides.pop("camelot_filter", None)
        base.update(overrides)
        return PlaylistExpansionFilters.from_mapping(base)


@dataclass(slots=True)
class PlaylistExpansionControls:
    mode: str = "balanced"
    strategy: str = "blend"
    weights: PlaylistExpansionWeights = field(default_factory=PlaylistExpansionWeights)
    diversity: float = 0.28
    filters: PlaylistExpansionFilters = field(default_factory=PlaylistExpansionFilters)
    candidate_pool: int = 250
    use_section_scores: bool = False

    def normalized(self) -> "PlaylistExpansionControls":
        return PlaylistExpansionControls(
            mode=self.mode,
            strategy=self.strategy,
            weights=self.weights.normalized(),
            diversity=max(0.0, min(1.0, float(self.diversity))),
            filters=self.filters,
            candidate_pool=max(1, int(self.candidate_pool)),
            use_section_scores=bool(self.use_section_scores),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "strategy": self.strategy,
            "weights": self.weights.to_dict(),
            "diversity": float(self.diversity),
            "filters": self.filters.to_dict(),
            "candidate_pool": int(self.candidate_pool),
            "use_section_scores": bool(self.use_section_scores),
        }


@dataclass(slots=True)
class PreparedCandidate:
    path: str
    source_flags: set[str] = field(default_factory=set)
    ann_distance: float | None = None
    coverage_distance: float | None = None
    support_count: int = 1
    support_distance: float | None = None
    support_seeds: int = 1
    vector: np.ndarray | None = None
    title: str = ""
    artist: str = ""
    bpm: float | None = None
    rekordbox_bpm: float | None = None
    rbassist_bpm: float | None = None
    bpm_delta: float | None = None
    bpm_mismatch: bool = False
    bpm_source: str = "unknown"
    key: str | None = None
    mytags: list[str] = field(default_factory=list)
    component_scores: dict[str, float] = field(default_factory=dict)
    section_intro: np.ndarray | None = None

    def source_rank(self) -> tuple[int, float, float, str]:
        source_score = 0
        if "centroid" in self.source_flags:
            source_score += 2
        if "coverage" in self.source_flags:
            source_score += 1
        return (
            -source_score,
            self.ann_distance if self.ann_distance is not None else 999.0,
            -(float(self.support_count) if self.support_count is not None else 0.0),
            self.path.lower(),
        )


@dataclass(slots=True)
class ExpansionWorkspace:
    seed_tracks: list[SeedTrack]
    controls: PlaylistExpansionControls
    meta_tracks: dict[str, dict[str, Any]]
    seed_vectors: list[np.ndarray]
    meta_stats: dict[str, Any]
    candidates: list[PreparedCandidate]
    diagnostics: dict[str, Any]


def _normalize_rb_location(raw_path: str | None) -> str:
    if not raw_path:
        return ""
    text = str(raw_path).strip()
    if text.startswith("file://"):
        text = text[len("file://") :]
        if text.startswith("localhost/"):
            text = text[len("localhost/") :]
        text = unquote(text)
        if len(text) > 2 and text[0] == "/" and text[2:3] == ":":
            text = text[1:]
    return normalize_path_string(text)


def _iter_path_aliases(path: str) -> list[str]:
    aliases: list[str] = []
    for alias in [path, _normalize_rb_location(path), *sorted(make_path_aliases(path))]:
        clean = str(alias).strip()
        if clean and clean not in aliases:
            aliases.append(clean)
    return aliases


def _build_alias_index(tracks: dict[str, dict[str, Any]]) -> dict[str, str]:
    alias_to_path: dict[str, str] = {}
    for path in tracks.keys():
        for alias in _iter_path_aliases(path):
            key = alias.lower()
            alias_to_path.setdefault(key, path)
    return alias_to_path


def _match_meta_path(raw_path: str, alias_index: dict[str, str]) -> tuple[str | None, str]:
    for alias in _iter_path_aliases(raw_path):
        match = alias_index.get(alias.lower())
        if match:
            return match, alias
    return None, ""


def _seed_track_from_meta(
    raw_path: str,
    meta_path: str | None,
    meta_tracks: dict[str, dict[str, Any]],
    matched_by: str,
    *,
    fallback_title: str = "",
    fallback_artist: str = "",
    fallback_bpm: float | None = None,
    fallback_key: str | None = None,
) -> SeedTrack:
    info = meta_tracks.get(meta_path or raw_path, {}) if meta_path else {}
    bpm_info = track_bpm_sources(meta_path or raw_path, info, rekordbox_bpm=fallback_bpm)
    return SeedTrack(
        rekordbox_path=raw_path,
        meta_path=meta_path,
        title=str(info.get("title", "") or fallback_title or ""),
        artist=str(info.get("artist", "") or fallback_artist or ""),
        bpm=bpm_info.preferred_bpm,
        rekordbox_bpm=bpm_info.rekordbox_bpm,
        rbassist_bpm=bpm_info.rbassist_bpm,
        bpm_delta=bpm_info.delta,
        bpm_mismatch=bpm_info.large_mismatch,
        bpm_source=bpm_info.preferred_source,
        key=str(info.get("key", "") or fallback_key or "") or None,
        mytags=[str(tag) for tag in (info.get("mytags", []) or []) if str(tag).strip()],
        embedding_path=str(info.get("embedding", "") or "") or None,
        matched_by=matched_by or "path",
    )


def _playlist_path_segments(playlist_path: str | None) -> list[str]:
    if not playlist_path:
        return []
    text = str(playlist_path).strip().strip("\\/")
    if not text:
        return []
    for sep in ("\\", "/"):
        text = text.replace(sep, "/")
    return [segment for segment in text.split("/") if segment]


def _query_rows(value: Any) -> list[Any]:
    if value is None:
        return []
    if hasattr(value, "all"):
        return list(value.all())
    if hasattr(value, "ID") or hasattr(value, "Songs"):
        return [value]
    return list(value)


def _resolve_single_playlist(value: Any, description: str) -> Any | None:
    matches = _query_rows(value)
    if not matches:
        return None
    if len(matches) > 1:
        raise ValueError(f"Multiple Rekordbox playlists matched {description}. Use a more specific reference.")
    return matches[0]


def _db_playlist_id_from_ref(seed_ref: Any) -> int | None:
    if isinstance(seed_ref, int):
        return seed_ref
    if isinstance(seed_ref, str):
        text = seed_ref.strip()
        if text.lower().startswith("db:"):
            raw_id = text.split(":", 1)[1].strip()
            if not raw_id.isdigit():
                raise ValueError(f"Invalid Rekordbox DB playlist ID reference: {seed_ref}")
            return int(raw_id)
    return None


def _resolve_db_playlist(db: Any, seed_ref: Any, playlist_path: str | None = None) -> Any:
    if hasattr(seed_ref, "is_playlist") or hasattr(seed_ref, "Songs"):
        return seed_ref
    playlist_id = _db_playlist_id_from_ref(seed_ref)
    if playlist_id is not None:
        return _resolve_single_playlist(db.get_playlist(ID=playlist_id), f"ID {playlist_id}")

    segments = _playlist_path_segments(playlist_path)
    if not segments:
        if isinstance(seed_ref, str):
            segments = _playlist_path_segments(seed_ref)
        elif isinstance(seed_ref, Sequence) and not isinstance(seed_ref, (str, bytes, bytearray)):
            segments = [str(part).strip() for part in seed_ref if str(part).strip()]

    if segments:
        current = None
        for segment in segments:
            query = db.get_playlist(Name=segment) if current is None else db.get_playlist(Name=segment, ParentID=current.ID)
            matches = _query_rows(query)
            if not matches:
                return None
            if len(matches) > 1:
                raise ValueError(
                    f"Playlist reference is ambiguous at segment '{segment}'. Use a more specific Rekordbox playlist path."
                )
            matches.sort(key=lambda pl: (bool(getattr(pl, "is_folder", False)), bool(getattr(pl, "is_smart_playlist", False))))
            current = matches[0]
        return current

    if not isinstance(seed_ref, str):
        return None

    query = db.get_playlist(Name=seed_ref)
    matches = _query_rows(query)
    if not matches:
        return None
    if len(matches) > 1:
        raise ValueError(
            f"Multiple Rekordbox playlists matched '{seed_ref}'. Use a full playlist path."
        )
    matches.sort(key=lambda pl: (bool(getattr(pl, "is_folder", False)), bool(getattr(pl, "is_smart_playlist", False))))
    return matches[0]


def _playlist_name_from_obj(playlist: Any) -> str | None:
    return str(getattr(playlist, "Name", "") or "").strip() or None


def _walk_xml_playlists(node: Any, segments: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], Any]]:
    items: list[tuple[tuple[str, ...], Any]] = []
    for child in node.get_playlists():
        name = str(getattr(child, "name", "") or getattr(child, "Name", "") or "").strip()
        child_segments = segments + ((name,) if name else tuple())
        items.append((child_segments, child))
        if bool(getattr(child, "is_folder", False)):
            items.extend(_walk_xml_playlists(child, child_segments))
    return items


def _playlist_tracks_from_db(seed_ref: Any, playlist_path: str | None = None) -> tuple[str | None, list[tuple[str, Any]]]:
    if Rekordbox6Database is None:
        raise RuntimeError("pyrekordbox is required for Rekordbox DB playlist loading.")
    db = Rekordbox6Database()
    try:
        playlist = _resolve_db_playlist(db, seed_ref, playlist_path=playlist_path)
        if playlist is None:
            return None, []
        query = db.get_playlist_contents(playlist)
        rows = list(query.all()) if hasattr(query, "all") else list(query)
        items: list[tuple[str, Any]] = []
        for row in rows:
            title = str(getattr(row, "Title", "") or "")
            artist = str(getattr(row, "ArtistName", "") or "")
            bpm = getattr(row, "BPM", None)
            key = str(getattr(row, "KeyName", "") or getattr(row, "Tonality", "") or "")
            raw_path = _normalize_rb_location(
                getattr(row, "FolderPath", None)
                or getattr(row, "Location", None)
                or getattr(row, "OrgFolderPath", None)
                or ""
            )
            if raw_path:
                items.append(
                    (
                        raw_path,
                        SimpleNamespace(
                            Title=title,
                            ArtistName=artist,
                            BPM=bpm,
                            KeyName=key,
                        ),
                    )
                )
        return _playlist_name_from_obj(playlist), items
    finally:
        try:
            db.close()
        except Exception:
            pass


def _playlist_tracks_from_xml(
    seed_ref: Any,
    playlist_path: str | None = None,
    *,
    xml_path: str | Path | None = None,
) -> tuple[str | None, list[tuple[str, Any]]]:
    if RekordboxXml is None:
        raise RuntimeError("pyrekordbox XML support is required for XML playlist loading.")

    xml_file: Path | None = None
    playlist_override: str | None = playlist_path
    if xml_path is not None:
        xml_file = Path(str(xml_path))
        if playlist_override is None and isinstance(seed_ref, str):
            playlist_override = seed_ref
    elif isinstance(seed_ref, (list, tuple)) and seed_ref:
        xml_file = Path(str(seed_ref[0]))
        if len(seed_ref) > 1 and not playlist_override:
            playlist_override = str(seed_ref[1])
    else:
        xml_file = Path(str(seed_ref))

    xml = RekordboxXml(xml_file)
    segments = tuple(_playlist_path_segments(playlist_override))
    if segments:
        if len(segments) == 1:
            matches = [
                node
                for path_segments, node in _walk_xml_playlists(xml.get_playlist())
                if path_segments and path_segments[-1].lower() == segments[0].lower()
            ]
            if len(matches) > 1:
                raise ValueError(
                    f"Multiple XML playlists matched '{segments[0]}'. Use the full playlist path."
                )
            if not matches:
                raise ValueError(f"XML playlist not found: {segments[0]}")
            playlist = matches[0]
        else:
            playlist = xml.get_playlist(*segments)
    else:
        playlist = xml.get_playlist()
    keys = list(playlist.get_tracks())
    items: list[tuple[str, Any]] = []
    for key in keys:
        track = xml.get_track(TrackID=key) if isinstance(key, int) else xml.get_track(Location=key)
        location = track.get("Location") or track.get("LOCATION") or track.get("FolderPath") or ""
        raw_path = _normalize_rb_location(location)
        if raw_path:
            items.append((raw_path, track))
    return _playlist_name_from_obj(playlist), items


def _playlist_tracks_from_manual(seed_ref: Any) -> tuple[str | None, list[tuple[str, Any]]]:
    if isinstance(seed_ref, SeedPlaylist):
        return seed_ref.playlist_name, [(track.rekordbox_path, track) for track in seed_ref.tracks]

    if isinstance(seed_ref, (str, Path)):
        items = [str(seed_ref)]
    else:
        items = [str(path) for path in seed_ref or []]
    return None, [(path, path) for path in items if str(path).strip()]


def list_rekordbox_playlists(
    *,
    source: str = "db",
    xml_path: str | Path | None = None,
    include_folders: bool = False,
) -> list[dict[str, Any]]:
    source = str(source or "db").lower().strip()

    if source == "db":
        if Rekordbox6Database is None:
            raise RuntimeError("pyrekordbox is required for Rekordbox DB playlist loading.")
        db = Rekordbox6Database()
        try:
            query = db.get_playlist()
            rows = list(query.all()) if hasattr(query, "all") else list(query)
            by_id = {getattr(row, "ID", None): row for row in rows}

            def full_path(playlist: Any, seen: set[int] | None = None) -> str:
                playlist_id = getattr(playlist, "ID", None)
                if playlist_id is None:
                    return str(getattr(playlist, "Name", "") or "").strip()
                seen = set(seen or set())
                if playlist_id in seen:
                    return str(getattr(playlist, "Name", "") or "").strip()
                seen.add(int(playlist_id))
                name = str(getattr(playlist, "Name", "") or "").strip()
                parent_id = getattr(playlist, "ParentID", None)
                parent = by_id.get(parent_id)
                if parent is None or not parent_id:
                    return name
                parent_path = full_path(parent, seen)
                return "/".join([segment for segment in [parent_path, name] if segment])

            items: list[dict[str, Any]] = []
            for playlist in rows:
                is_folder = bool(getattr(playlist, "is_folder", False))
                if is_folder and not include_folders:
                    continue
                items.append(
                    {
                        "source": "db",
                        "name": str(getattr(playlist, "Name", "") or "").strip(),
                        "path": full_path(playlist),
                        "id": getattr(playlist, "ID", None),
                        "parent_id": getattr(playlist, "ParentID", None),
                        "is_folder": is_folder,
                        "is_smart_playlist": bool(getattr(playlist, "is_smart_playlist", False)),
                    }
                )
            items.sort(key=lambda item: (str(item.get("path", "")).lower(), str(item.get("name", "")).lower()))
            return items
        finally:
            try:
                db.close()
            except Exception:
                pass

    if source == "xml":
        if RekordboxXml is None:
            raise RuntimeError("pyrekordbox XML support is required for XML playlist loading.")
        if xml_path is None:
            raise ValueError("xml_path is required when listing XML playlists.")
        xml = RekordboxXml(Path(str(xml_path)))
        items: list[dict[str, Any]] = []
        for segments, node in _walk_xml_playlists(xml.get_playlist()):
            is_folder = bool(getattr(node, "is_folder", False))
            if is_folder and not include_folders:
                continue
            path_text = "/".join(segments)
            items.append(
                {
                    "source": "xml",
                    "name": str(getattr(node, "name", "") or getattr(node, "Name", "") or "").strip(),
                    "path": path_text,
                    "id": None,
                    "parent_id": None,
                    "is_folder": is_folder,
                    "is_smart_playlist": False,
                }
            )
        items.sort(key=lambda item: (str(item.get("path", "")).lower(), str(item.get("name", "")).lower()))
        return items

    raise ValueError(f"Unsupported playlist source: {source}")


def load_rekordbox_playlist(
    seed_ref: Any,
    source: str = "db",
    *,
    playlist_path: str | None = None,
    xml_path: str | Path | None = None,
) -> SeedPlaylist:
    source = str(source or "db").lower().strip()
    meta_tracks = load_meta().get("tracks", {})
    alias_index = _build_alias_index(meta_tracks)

    if source == "db":
        playlist_name, playlist_rows = _playlist_tracks_from_db(seed_ref, playlist_path=playlist_path)
    elif source == "xml":
        playlist_name, playlist_rows = _playlist_tracks_from_xml(seed_ref, playlist_path=playlist_path, xml_path=xml_path)
    elif source == "manual":
        playlist_name, playlist_rows = _playlist_tracks_from_manual(seed_ref)
    else:
        raise ValueError(f"Unsupported playlist source: {source}")
    if playlist_name is None and not playlist_rows:
        raise ValueError(f"Playlist not found for source '{source}': {seed_ref}")

    tracks: list[SeedTrack] = []
    counts: Counter[str] = Counter()
    for raw_path, row in playlist_rows:
        meta_path, matched_by = _match_meta_path(raw_path, alias_index)
        title = str(getattr(row, "Title", "") or getattr(row, "Name", "") or "")
        artist = str(getattr(row, "ArtistName", "") or getattr(row, "Artist", "") or "")
        bpm = normalize_rekordbox_bpm(getattr(row, "BPM", None))
        key = str(getattr(row, "KeyName", "") or getattr(row, "Tonality", "") or "") or None
        track = _seed_track_from_meta(
            raw_path,
            meta_path,
            meta_tracks,
            matched_by=matched_by or ("manual" if source == "manual" else "alias"),
            fallback_title=title,
            fallback_artist=artist,
            fallback_bpm=bpm,
            fallback_key=key,
        )
        counts[track.status] += 1
        tracks.append(track)

    diagnostics = {
        "source": source,
        "seed_ref": str(seed_ref),
        "playlist_name": playlist_name,
        "playlist_path": playlist_path,
        "seed_tracks_total": len(tracks),
        "matched_total": counts["matched"],
        "missing_embedding_total": counts["missing_embedding"],
        "unmapped_total": counts["unmapped"],
    }
    return SeedPlaylist(
        source=source,
        seed_ref=str(seed_ref),
        playlist_name=playlist_name,
        tracks=tracks,
        diagnostics=diagnostics,
    )


def _coerce_seed_tracks(seed_paths: Any, meta_tracks: dict[str, dict[str, Any]]) -> tuple[list[SeedTrack], dict[str, Any]]:
    alias_index = _build_alias_index(meta_tracks)
    if isinstance(seed_paths, SeedPlaylist):
        return list(seed_paths.resolved_tracks), dict(seed_paths.diagnostics)

    if isinstance(seed_paths, SeedTrack):
        seed_list = [seed_paths]
    elif isinstance(seed_paths, (str, Path)):
        seed_list = [str(seed_paths)]
    else:
        seed_list = list(seed_paths or [])

    resolved_tracks: list[SeedTrack] = []
    unresolved: list[str] = []
    missing_embedding: list[str] = []
    for raw in seed_list:
        if isinstance(raw, SeedTrack):
            if raw.status == "matched":
                resolved_tracks.append(raw)
            elif raw.meta_path:
                missing_embedding.append(raw.rekordbox_path)
            else:
                unresolved.append(raw.rekordbox_path)
            continue
        raw_path = str(raw).strip()
        if not raw_path:
            continue
        meta_path, matched_by = _match_meta_path(raw_path, alias_index)
        if meta_path:
            track = _seed_track_from_meta(raw_path, meta_path, meta_tracks, matched_by=matched_by)
            if track.status == "matched":
                resolved_tracks.append(track)
            else:
                missing_embedding.append(raw_path)
        else:
            unresolved.append(raw_path)

    diagnostics = {
        "seed_input_total": len(seed_list),
        "seed_resolved_total": len(resolved_tracks),
        "seed_unresolved_total": len(unresolved),
        "seed_missing_embedding_total": len(missing_embedding),
        "unresolved_seed_paths": unresolved,
        "missing_embedding_seed_paths": missing_embedding,
    }
    return resolved_tracks, diagnostics


def _seed_embedding_vector(track: SeedTrack, meta_tracks: dict[str, dict[str, Any]]) -> np.ndarray | None:
    info = meta_tracks.get(track.meta_path or "", {})
    emb_path = info.get("embedding") or track.embedding_path
    if not emb_path:
        return None
    return load_embedding_safe(str(emb_path))


def _load_track_embedding(info: dict[str, Any], key: str) -> np.ndarray | None:
    emb_path = info.get(key)
    if not emb_path:
        return None
    return load_embedding_safe(str(emb_path))


def _cosine_similarity(left: np.ndarray, right: np.ndarray) -> float:
    if left.size == 0 or right.size == 0:
        return 0.0
    denom = float(np.linalg.norm(left) * np.linalg.norm(right))
    if denom <= 0:
        return 0.0
    return float(np.dot(left, right) / denom)


def _collect_meta_features(
    meta_tracks: dict[str, dict[str, Any]],
    seed_tracks: list[SeedTrack],
) -> dict[str, Any]:
    bpm_values = [float(track.bpm) for track in seed_tracks if isinstance(track.bpm, (int, float))]
    seed_keys = [str(track.key) for track in seed_tracks if str(track.key or "").strip()]
    tag_counts: Counter[str] = Counter()
    for track in seed_tracks:
        tag_counts.update(track.mytags)
    core_tags = {tag for tag, count in tag_counts.items() if count >= 2}
    if not core_tags:
        core_tags = set(tag_counts)
    seed_vectors = []
    seed_late_vectors = []
    for track in seed_tracks:
        info = meta_tracks.get(track.meta_path or "", {})
        vec = _seed_embedding_vector(track, meta_tracks)
        if vec is not None:
            seed_vectors.append(vec)
        late_vec = _load_track_embedding(info, "embedding_late")
        if late_vec is not None:
            seed_late_vectors.append(late_vec)
    centroid = np.mean(np.stack(seed_vectors, axis=0), axis=0).astype(np.float32) if seed_vectors else None
    late_centroid = (
        np.mean(np.stack(seed_late_vectors, axis=0), axis=0).astype(np.float32)
        if seed_late_vectors
        else None
    )
    return {
        "seed_bpm_median": float(np.median(bpm_values)) if bpm_values else None,
        "seed_keys": seed_keys,
        "seed_tag_counts": tag_counts,
        "seed_core_tags": core_tags,
        "seed_vectors": seed_vectors,
        "seed_centroid": centroid,
        "seed_late_vectors": seed_late_vectors,
        "seed_late_centroid": late_centroid,
    }


_REPEAT_VERSION_MARKERS = (
    "acoustic",
    "album",
    "bootleg",
    "club",
    "dub",
    "edit",
    "extended",
    "instrumental",
    "live",
    "mix",
    "original",
    "radio",
    "rework",
    "reprise",
    "remaster",
    "remix",
    "version",
    "vip",
)


def _normalize_repeat_text(value: str | None) -> str:
    text = str(value or "").casefold().strip()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _has_repeat_version_marker(text: str) -> bool:
    lowered = text.casefold()
    return any(marker in lowered for marker in _REPEAT_VERSION_MARKERS)


def _track_repeat_signature(title: str | None, artist: str | None, path: str | None = None) -> dict[str, str]:
    raw_title = str(title or "").strip() or (Path(str(path)).stem if path else "")
    raw_artist = str(artist or "").strip()

    title_work = raw_title
    version_tokens: list[str] = []

    def _collect_version_tokens(text: str) -> None:
        lowered = text.casefold()
        for marker in _REPEAT_VERSION_MARKERS:
            if marker in lowered and marker not in version_tokens:
                version_tokens.append(marker)

    def _strip_version_chunk(match: re.Match[str]) -> str:
        content = str(match.group(1) or "")
        if _has_repeat_version_marker(content):
            _collect_version_tokens(content)
            return " "
        return match.group(0)

    title_work = re.sub(r"\(([^()]*)\)", _strip_version_chunk, title_work)
    title_work = re.sub(r"\[([^\[\]]*)\]", _strip_version_chunk, title_work)
    title_work = re.sub(r"\{([^{}]*)\}", _strip_version_chunk, title_work)

    suffix_match = re.search(r"\s*[-–—]\s*(.+)$", title_work)
    if suffix_match and _has_repeat_version_marker(suffix_match.group(1)):
        _collect_version_tokens(suffix_match.group(1))
        title_work = title_work[: suffix_match.start()]

    _collect_version_tokens(raw_title)
    title_stem = _normalize_repeat_text(title_work)
    artist_key = _normalize_repeat_text(raw_artist)
    version_key = " ".join(sorted(version_tokens))

    return {
        "artist": artist_key,
        "title_stem": title_stem,
        "version": version_key,
    }


def _repeat_penalty(
    candidate: PreparedCandidate,
    seen_signatures: Counter[tuple[str, str, str]],
) -> tuple[float, list[str], dict[str, str]]:
    signature = _track_repeat_signature(candidate.title, candidate.artist, candidate.path)
    penalty = 0.0
    reasons: list[str] = []

    artist_key = signature["artist"]
    title_stem = signature["title_stem"]
    version_key = signature["version"]

    if artist_key:
        artist_count = seen_signatures[("artist", artist_key, "")]
        if artist_count:
            penalty += min(0.18, 0.07 + 0.03 * max(artist_count - 1, 0))
            reasons.append("artist_repeat")

    if title_stem:
        stem_count = seen_signatures[("stem", artist_key, title_stem)]
        if stem_count:
            penalty += min(0.32, 0.18 + 0.06 * max(stem_count - 1, 0))
            reasons.append("title_repeat")

    if title_stem and version_key:
        version_count = seen_signatures[("version", title_stem, version_key)]
        if version_count:
            penalty += min(0.24, 0.12 + 0.04 * max(version_count - 1, 0))
            reasons.append("version_repeat")

    return min(penalty, 0.75), reasons, signature


def _register_repeat_signature(seen_signatures: Counter[tuple[str, str, str]], signature: dict[str, str]) -> None:
    if signature.get("artist"):
        seen_signatures[("artist", signature["artist"], "")] += 1
    if signature.get("title_stem"):
        seen_signatures[("stem", signature["artist"], signature["title_stem"])] += 1
    if signature.get("title_stem") and signature.get("version"):
        seen_signatures[("version", signature["title_stem"], signature["version"])] += 1


def _query_candidate_hits(
    meta_tracks: dict[str, dict[str, Any]],
    seed_tracks: list[SeedTrack],
    candidate_pool: int,
    strategy: str,
) -> list[CandidateHit]:
    strategy = strategy.lower().strip()
    exclude = {track.meta_path for track in seed_tracks if track.meta_path}
    seed_vectors = []
    for track in seed_tracks:
        vec = _seed_embedding_vector(track, meta_tracks)
        if vec is not None:
            seed_vectors.append((track.meta_path or track.rekordbox_path, vec))

    if not seed_vectors:
        return []

    if strategy == "coverage":
        support: dict[str, CandidateHit] = {}
        for _, vec in seed_vectors:
            query_hits = _query_index_or_bruteforce(meta_tracks, vec, max(candidate_pool, 50), exclude)
            for hit in query_hits:
                current = support.get(hit.path)
                if current is None:
                    support[hit.path] = CandidateHit(
                        path=hit.path,
                        distance=hit.distance,
                        support_count=1,
                        support_distance=hit.distance,
                        support_seeds=1,
                    )
                    continue
                current.support_count += 1
                current.support_seeds += 1
                if hit.distance is not None and (current.support_distance is None or hit.distance < current.support_distance):
                    current.support_distance = hit.distance
                if hit.distance is not None and (current.distance is None or hit.distance < current.distance):
                    current.distance = hit.distance
        ranked = sorted(
            support.values(),
            key=lambda item: (
                -item.support_count,
                item.distance if item.distance is not None else 999.0,
                item.path.lower(),
            ),
        )
        return ranked[:candidate_pool]

    centroid = _collect_meta_features(meta_tracks, seed_tracks)["seed_centroid"]
    if centroid is None:
        return []
    hits = _query_index_or_bruteforce(meta_tracks, centroid, candidate_pool, exclude)
    return hits


def _query_index_or_bruteforce(
    meta_tracks: dict[str, dict[str, Any]],
    query_vec: np.ndarray,
    candidate_pool: int,
    exclude_paths: set[str | None],
) -> list[CandidateHit]:
    paths_file = IDX / "paths.json"
    index_file = IDX / "hnsw.idx"
    if hnswlib is not None and paths_file.exists() and index_file.exists():
        try:
            paths_map = []
            with paths_file.open("r", encoding="utf-8") as fh:
                paths_map = list(__import__("json").load(fh))
            if not paths_map:
                return []
            index = hnswlib.Index(space="cosine", dim=int(query_vec.shape[0]))
            index.load_index(str(index_file))
            index.set_ef(64)
            k = min(max(candidate_pool * 4, candidate_pool), len(paths_map))
            labels, dists = index.knn_query(query_vec, k=k)
            hits: list[CandidateHit] = []
            for label, dist in zip(labels[0].tolist(), dists[0].tolist()):
                path = paths_map[label]
                if path in exclude_paths:
                    continue
                if path not in meta_tracks:
                    continue
                hits.append(CandidateHit(path=path, distance=float(dist), support_count=1, support_distance=float(dist), support_seeds=1))
                if len(hits) >= candidate_pool:
                    break
            return hits
        except Exception:
            pass

    hits: list[CandidateHit] = []
    for path, info in meta_tracks.items():
        if path in exclude_paths:
            continue
        emb_path = info.get("embedding")
        if not emb_path:
            continue
        vec = load_embedding_safe(str(emb_path))
        if vec is None or vec.size == 0:
            continue
        sim = _cosine_similarity(query_vec, vec.astype(np.float32, copy=False))
        distance = 1.0 - sim
        hits.append(CandidateHit(path=path, distance=distance, support_count=1, support_distance=distance, support_seeds=1))
    hits.sort(key=lambda item: (item.distance if item.distance is not None else 999.0, item.path.lower()))
    return hits[:candidate_pool]


def _candidate_score(
    path: str,
    info: dict[str, Any],
    hit: CandidateHit,
    meta_stats: dict[str, Any],
    filters: dict[str, Any],
) -> tuple[float, list[str]]:
    reasons: list[str] = []
    score = 0.0
    if hit.distance is not None:
        relevance = 1.0 - float(hit.distance)
        score += max(relevance, -1.0)
        reasons.append("ann")

    bpm_info = track_bpm_sources(path, info)
    cand_bpm = bpm_info.preferred_bpm
    seed_bpm = meta_stats.get("seed_bpm_median")
    tempo_pct = float(filters.get("tempo_pct", 6.0) or 6.0)
    allow_doubletime = bool(filters.get("doubletime", True))
    if seed_bpm and cand_bpm:
        if tempo_match(seed_bpm, cand_bpm, pct=tempo_pct, allow_doubletime=allow_doubletime):
            score += 0.35
            reasons.append("tempo_match")
        else:
            score -= 0.25
            reasons.append("tempo_miss")

    cand_key = str(info.get("key") or "") or None
    seed_keys = [str(key) for key in meta_stats.get("seed_keys", []) if str(key).strip()]
    if seed_keys and cand_key:
        relations = [camelot_relation(seed_key, cand_key) for seed_key in seed_keys]
        match_relations = [relation for ok, relation in relations if ok]
        if match_relations:
            score += 0.25
            reasons.append(match_relations[0])
        else:
            score -= 0.15
            reasons.append("key_miss")

    seed_core_tags = set(meta_stats.get("seed_core_tags", set()))
    cand_tags = {str(tag) for tag in (info.get("mytags", []) or []) if str(tag).strip()}
    if seed_core_tags and cand_tags:
        tag_overlap = len(seed_core_tags & cand_tags) / max(len(seed_core_tags), 1)
        if tag_overlap > 0:
            score += min(0.35, tag_overlap * 0.35)
            reasons.append("tags")

    samples = info.get("features", {}).get("samples", 0.0)
    try:
        score += 0.05 * float(samples or 0.0)
    except Exception:
        pass

    return score, reasons


def _rank_candidates(
    meta_tracks: dict[str, dict[str, Any]],
    hits: list[CandidateHit],
    meta_stats: dict[str, Any],
    filters: dict[str, Any],
    exclude_paths: set[str],
) -> list[ExpandedTrack]:
    ranked: list[ExpandedTrack] = []
    for hit in hits:
        if hit.path in exclude_paths:
            continue
        info = meta_tracks.get(hit.path, {})
        bpm_info = track_bpm_sources(hit.path, info)
        if filters.get("camelot_filter"):
            seed_keys = [str(key) for key in meta_stats.get("seed_keys", []) if str(key).strip()]
            cand_key = str(info.get("key") or "") or None
            if seed_keys and cand_key and not any(camelot_relation(seed_key, cand_key)[0] for seed_key in seed_keys):
                continue
        score, reasons = _candidate_score(hit.path, info, hit, meta_stats, filters)
        ranked.append(
            ExpandedTrack(
                path=hit.path,
                score=score,
                ann_distance=hit.distance,
                support_count=hit.support_count,
                title=str(info.get("title", "") or ""),
                artist=str(info.get("artist", "") or ""),
                bpm=bpm_info.preferred_bpm,
                rekordbox_bpm=bpm_info.rekordbox_bpm,
                rbassist_bpm=bpm_info.rbassist_bpm,
                bpm_delta=bpm_info.delta,
                bpm_mismatch=bpm_info.large_mismatch,
                bpm_source=bpm_info.preferred_source,
                key=str(info.get("key", "") or "") or None,
                mytags=[str(tag) for tag in (info.get("mytags", []) or []) if str(tag).strip()],
                reasons=reasons,
            )
        )
    ranked.sort(key=lambda item: (-item.score, item.path.lower()))
    return ranked


def _apply_diversity_rerank(
    ranked: list[ExpandedTrack],
    meta_tracks: dict[str, dict[str, Any]],
    seed_tracks: list[SeedTrack],
    add_count: int,
    diversity: float,
) -> list[ExpandedTrack]:
    if add_count <= 0:
        return []
    if not ranked:
        return []
    diversity = max(0.0, min(1.0, float(diversity)))
    if diversity <= 0.0 or len(ranked) == 1:
        return ranked[:add_count]

    selected: list[ExpandedTrack] = []
    selected_vecs: list[np.ndarray] = []
    seed_vecs = []
    seen_signatures: Counter[tuple[str, str, str]] = Counter()
    for track in seed_tracks:
        vec = _seed_embedding_vector(track, meta_tracks)
        if vec is not None:
            seed_vecs.append(vec)
        info = meta_tracks.get(track.meta_path or track.rekordbox_path, {})
        seed_signature = _track_repeat_signature(
            track.title or str(info.get("title", "") or ""),
            track.artist or str(info.get("artist", "") or ""),
            track.meta_path or track.rekordbox_path,
        )
        _register_repeat_signature(seen_signatures, seed_signature)

    remaining = list(ranked)
    total_repeat_penalty = 0.0
    repeat_reason_counts: Counter[str] = Counter()
    while remaining and len(selected) < add_count:
        best_idx = 0
        best_candidate = None
        best_score = float("-inf")
        best_vec = np.asarray([], dtype=np.float32)
        best_repeat_penalty = 0.0
        best_repeat_reasons: list[str] = []
        best_repeat_signature = {"artist": "", "title_stem": "", "version": ""}
        for idx, candidate in enumerate(remaining):
            cand_info = meta_tracks.get(candidate.path, {})
            cand_vec = load_embedding_safe(str(cand_info.get("embedding", "") or ""))
            if cand_vec is None:
                cand_vec = np.asarray([], dtype=np.float32)
            max_similarity = 0.0
            if cand_vec.size:
                reference_vecs = selected_vecs or seed_vecs
                for vec in reference_vecs:
                    max_similarity = max(max_similarity, _cosine_similarity(cand_vec, vec))
            repeat_penalty, repeat_reasons, repeat_signature = _repeat_penalty(candidate, seen_signatures)
            mmr_score = candidate.score - (diversity * max_similarity) - repeat_penalty
            if mmr_score > best_score or (mmr_score == best_score and candidate.path.lower() < (best_candidate.path.lower() if best_candidate else "")):
                best_idx = idx
                component_scores = dict(candidate.component_scores)
                if repeat_penalty > 0:
                    component_scores["anti_repetition"] = repeat_penalty
                best_candidate = ExpandedTrack(
                    path=candidate.path,
                    score=mmr_score,
                    ann_distance=candidate.ann_distance,
                    support_count=candidate.support_count,
                    title=candidate.title,
                    artist=candidate.artist,
                    bpm=candidate.bpm,
                    rekordbox_bpm=candidate.rekordbox_bpm,
                    rbassist_bpm=candidate.rbassist_bpm,
                    bpm_delta=candidate.bpm_delta,
                    bpm_mismatch=candidate.bpm_mismatch,
                    bpm_source=candidate.bpm_source,
                    key=candidate.key,
                    mytags=list(candidate.mytags),
                    component_scores=component_scores,
                    reasons=list(candidate.reasons) + (repeat_reasons + (["diversity"] if diversity > 0 else [])),
                )
                best_score = mmr_score
                best_vec = cand_vec
                best_repeat_penalty = repeat_penalty
                best_repeat_reasons = list(repeat_reasons)
                best_repeat_signature = repeat_signature

        if best_candidate is None:
            break
        selected.append(best_candidate)
        if best_vec.size:
            selected_vecs.append(best_vec)
        if best_repeat_penalty > 0:
            total_repeat_penalty += float(best_repeat_penalty)
            repeat_reason_counts.update(best_repeat_reasons)
        _register_repeat_signature(seen_signatures, best_repeat_signature)
        remaining.pop(best_idx)

    selected.sort(key=lambda item: (-item.score, item.path.lower()))
    return selected[:add_count]


PLAYLIST_EXPANSION_PRESETS: dict[str, dict[str, Any]] = {
    "tight": {
        "weights": PlaylistExpansionWeights(
            ann_centroid=0.26,
            ann_seed_coverage=0.20,
            group_match=0.18,
            bpm_match=0.18,
            key_match=0.12,
            tag_match=0.06,
            transition_outro_to_intro=0.0,
        ),
        "diversity": 0.15,
        "filters": PlaylistExpansionFilters(tempo_pct=4.0, allow_doubletime=True, key_mode="filter"),
    },
    "balanced": {
        "weights": PlaylistExpansionWeights(
            ann_centroid=0.30,
            ann_seed_coverage=0.20,
            group_match=0.16,
            bpm_match=0.12,
            key_match=0.08,
            tag_match=0.14,
            transition_outro_to_intro=0.0,
        ),
        "diversity": 0.28,
        "filters": PlaylistExpansionFilters(tempo_pct=6.0, allow_doubletime=True, key_mode="soft"),
    },
    "adventurous": {
        "weights": PlaylistExpansionWeights(
            ann_centroid=0.36,
            ann_seed_coverage=0.20,
            group_match=0.12,
            bpm_match=0.08,
            key_match=0.04,
            tag_match=0.20,
            transition_outro_to_intro=0.0,
        ),
        "diversity": 0.55,
        "filters": PlaylistExpansionFilters(tempo_pct=10.0, allow_doubletime=True, key_mode="off"),
    },
}


def _normalize_playlist_expansion_mode(mode: str) -> str:
    clean = str(mode or "balanced").lower().strip()
    if clean not in PLAYLIST_EXPANSION_PRESETS:
        raise ValueError(f"Unsupported playlist expansion mode: {mode}")
    return clean


def _normalize_playlist_expansion_strategy(strategy: str) -> str:
    clean = str(strategy or "blend").lower().strip()
    if clean not in {"blend", "centroid", "coverage"}:
        raise ValueError(f"Unsupported playlist expansion strategy: {strategy}")
    return clean


def _coerce_playlist_expansion_weights(
    weights: PlaylistExpansionWeights | dict[str, Any] | None,
) -> PlaylistExpansionWeights | None:
    if weights is None:
        return None
    if isinstance(weights, PlaylistExpansionWeights):
        return weights
    return PlaylistExpansionWeights.from_mapping(weights)


def _coerce_playlist_expansion_filters(
    filters: PlaylistExpansionFilters | dict[str, Any] | None,
) -> PlaylistExpansionFilters | None:
    if filters is None:
        return None
    if isinstance(filters, PlaylistExpansionFilters):
        return filters
    return PlaylistExpansionFilters.from_mapping(filters)


def _overlay_playlist_expansion_weights(
    base: PlaylistExpansionWeights,
    overrides: PlaylistExpansionWeights | dict[str, Any] | None,
) -> PlaylistExpansionWeights:
    override_weights = _coerce_playlist_expansion_weights(overrides)
    if override_weights is None:
        return base
    merged = base.to_dict()
    merged.update(override_weights.to_dict())
    return PlaylistExpansionWeights.from_mapping(merged)


def _weights_specify_transition(weights: PlaylistExpansionWeights | dict[str, Any] | None) -> bool:
    if weights is None:
        return False
    if isinstance(weights, PlaylistExpansionWeights):
        return float(weights.transition_outro_to_intro) != 0.0
    keys = {"transition_outro_to_intro", "transition"}
    return any(key in weights for key in keys)


def _overlay_playlist_expansion_filters(
    base: PlaylistExpansionFilters,
    overrides: PlaylistExpansionFilters | dict[str, Any] | None,
) -> PlaylistExpansionFilters:
    override_filters = _coerce_playlist_expansion_filters(overrides)
    if override_filters is None:
        return base
    merged = base.to_dict()
    merged.update(override_filters.to_dict())
    return PlaylistExpansionFilters.from_mapping(merged)


def _resolve_playlist_expansion_controls(
    *,
    mode: str = "balanced",
    strategy: str = "blend",
    candidate_pool: int = 250,
    diversity: float | None = None,
    filters: PlaylistExpansionFilters | dict[str, Any] | None = None,
    weights: PlaylistExpansionWeights | dict[str, Any] | None = None,
    controls: PlaylistExpansionControls | dict[str, Any] | None = None,
) -> PlaylistExpansionControls:
    if isinstance(controls, PlaylistExpansionControls):
        resolved = controls
    elif isinstance(controls, dict):
        resolved = PlaylistExpansionControls(
            mode=str(controls.get("mode", mode) or mode),
            strategy=str(controls.get("strategy", strategy) or strategy),
            weights=_coerce_playlist_expansion_weights(controls.get("weights"))
            or PlaylistExpansionWeights.from_mapping(controls),
            diversity=float(controls.get("diversity", diversity if diversity is not None else 0.28)),
            filters=_coerce_playlist_expansion_filters(controls.get("filters"))
            or PlaylistExpansionFilters.from_mapping(controls),
            candidate_pool=int(controls.get("candidate_pool", candidate_pool)),
            use_section_scores=bool(controls.get("use_section_scores", controls.get("section_scores", False))),
        )
    else:
        resolved_mode = _normalize_playlist_expansion_mode(mode)
        preset = PLAYLIST_EXPANSION_PRESETS[resolved_mode]
        resolved = PlaylistExpansionControls(
            mode=resolved_mode,
            strategy=_normalize_playlist_expansion_strategy(strategy),
            weights=preset["weights"],
            diversity=float(preset["diversity"]),
            filters=preset["filters"],
            candidate_pool=int(candidate_pool),
            use_section_scores=False,
        )

    use_section_scores = bool(resolved.use_section_scores)
    resolved = PlaylistExpansionControls(
        mode=_normalize_playlist_expansion_mode(resolved.mode if resolved.mode else mode),
        strategy=_normalize_playlist_expansion_strategy(resolved.strategy if resolved.strategy else strategy),
        weights=_overlay_playlist_expansion_weights(
            PLAYLIST_EXPANSION_PRESETS[_normalize_playlist_expansion_mode(resolved.mode if resolved.mode else mode)]["weights"],
            weights if weights is not None else resolved.weights,
        ),
        diversity=float(diversity if diversity is not None else resolved.diversity),
        filters=_overlay_playlist_expansion_filters(
            PLAYLIST_EXPANSION_PRESETS[_normalize_playlist_expansion_mode(resolved.mode if resolved.mode else mode)]["filters"],
            filters if filters is not None else resolved.filters,
        ),
        candidate_pool=max(1, int(candidate_pool if candidate_pool is not None else resolved.candidate_pool)),
        use_section_scores=use_section_scores,
    )
    if (
        resolved.use_section_scores
        and resolved.mode == "tight"
        and float(resolved.weights.transition_outro_to_intro) == 0.0
        and not _weights_specify_transition(weights)
    ):
        preset_weights = resolved.weights.to_dict()
        preset_weights["transition_outro_to_intro"] = 0.18
        resolved = PlaylistExpansionControls(
            mode=resolved.mode,
            strategy=resolved.strategy,
            weights=PlaylistExpansionWeights.from_mapping(preset_weights),
            diversity=resolved.diversity,
            filters=resolved.filters,
            candidate_pool=resolved.candidate_pool,
            use_section_scores=resolved.use_section_scores,
        )
    return resolved.normalized()


def _camelot_relation_score(seed_key: str | None, cand_key: str | None) -> float:
    if not seed_key or not cand_key:
        return 0.0
    ok, relation = camelot_relation(seed_key, cand_key)
    if not ok:
        return 0.0
    if relation == "Same Key":
        return 1.0
    if relation == "Relative Maj/Min":
        return 0.8
    if relation != "-":
        return 0.7
    return 0.0


def _tempo_similarity(seed_bpm: float | None, cand_bpm: float | None, tempo_pct: float, allow_doubletime: bool) -> float:
    if not seed_bpm or not cand_bpm:
        return 0.0
    seed_bpm = float(seed_bpm)
    cand_bpm = float(cand_bpm)
    threshold = max(seed_bpm * (max(float(tempo_pct), 0.0) / 100.0), 1e-6)
    comparisons = [cand_bpm]
    if allow_doubletime:
        comparisons.extend([cand_bpm * 2.0, cand_bpm / 2.0])
    best_diff = min(abs(seed_bpm - value) for value in comparisons)
    if best_diff > threshold:
        return 0.0
    return max(0.0, 1.0 - (best_diff / threshold))


def _tag_overlap_score(seed_tags: set[str], candidate_tags: set[str]) -> float:
    if not seed_tags and not candidate_tags:
        return 0.0
    union = seed_tags | candidate_tags
    if not union:
        return 0.0
    return len(seed_tags & candidate_tags) / len(union)


def _compute_component_scores(
    candidate: PreparedCandidate,
    meta_stats: dict[str, Any],
    controls: PlaylistExpansionControls,
) -> dict[str, float]:
    seed_vectors = [vec for vec in meta_stats.get("seed_vectors", []) if isinstance(vec, np.ndarray) and vec.size]
    seed_centroid = meta_stats.get("seed_centroid")
    seed_count = max(len(seed_vectors), 1)
    scores = {
        "ann_centroid": 0.0,
        "ann_seed_coverage": 0.0,
        "group_match": 0.0,
        "bpm_match": 0.0,
        "key_match": 0.0,
        "tag_match": 0.0,
        "transition_outro_to_intro": 0.0,
    }
    if candidate.vector is not None and candidate.vector.size and seed_centroid is not None:
        centroid_sim = _cosine_similarity(candidate.vector.astype(np.float32, copy=False), seed_centroid.astype(np.float32, copy=False))
        scores["ann_centroid"] = max(0.0, min(1.0, centroid_sim))
        group_sims = [
            max(0.0, min(1.0, _cosine_similarity(candidate.vector.astype(np.float32, copy=False), seed_vec.astype(np.float32, copy=False))))
            for seed_vec in seed_vectors
        ]
        if group_sims:
            top_k = max(2, (len(group_sims) + 2) // 3)
            group_sims.sort(reverse=True)
            scores["group_match"] = float(np.mean(group_sims[:top_k]))
    scores["ann_seed_coverage"] = max(0.0, min(1.0, float(candidate.support_count) / float(seed_count)))
    scores["bpm_match"] = _tempo_similarity(
        meta_stats.get("seed_bpm_median"),
        candidate.bpm,
        controls.filters.tempo_pct,
        controls.filters.allow_doubletime,
    )
    if controls.filters.key_mode != "off":
        seed_keys = [str(key) for key in meta_stats.get("seed_keys", []) if str(key).strip()]
        cand_key = str(candidate.key or "").strip() or None
        if seed_keys and cand_key:
            key_scores = [_camelot_relation_score(seed_key, cand_key) for seed_key in seed_keys]
            scores["key_match"] = max(key_scores) if key_scores else 0.0
        else:
            scores["key_match"] = 0.0
    seed_tags = set(str(tag) for tag in meta_stats.get("seed_core_tags", []) if str(tag).strip())
    candidate_tags = set(str(tag) for tag in candidate.mytags if str(tag).strip())
    scores["tag_match"] = _tag_overlap_score(seed_tags, candidate_tags)
    if controls.use_section_scores:
        seed_late = meta_stats.get("seed_late_centroid")
        if seed_late is not None and candidate.section_intro is not None:
            transition_score = max(
                0.0,
                min(
                    1.0,
                    _cosine_similarity(
                        seed_late.astype(np.float32, copy=False),
                        candidate.section_intro.astype(np.float32, copy=False),
                    ),
                ),
            )
            scores["transition_outro_to_intro"] = transition_score
            scores["transition_score"] = transition_score
    return scores


def _candidate_matches_strategy(candidate: PreparedCandidate, strategy: str) -> bool:
    strategy = _normalize_playlist_expansion_strategy(strategy)
    if strategy == "blend":
        return bool(candidate.source_flags)
    if strategy == "centroid":
        return "centroid" in candidate.source_flags
    if strategy == "coverage":
        return "coverage" in candidate.source_flags
    return False


def _candidate_passes_filters(candidate: PreparedCandidate, meta_stats: dict[str, Any], controls: PlaylistExpansionControls) -> bool:
    if controls.filters.key_mode == "filter":
        seed_keys = [str(key) for key in meta_stats.get("seed_keys", []) if str(key).strip()]
        cand_key = str(candidate.key or "").strip() or None
        if seed_keys:
            if not cand_key:
                return False
            if not any(camelot_relation(seed_key, cand_key)[0] for seed_key in seed_keys):
                return False
    if controls.filters.require_tags:
        candidate_tags = {str(tag) for tag in candidate.mytags if str(tag).strip()}
        required_tags = {str(tag) for tag in controls.filters.require_tags if str(tag).strip()}
        if not required_tags.issubset(candidate_tags):
            return False
    return True


def _select_candidate_vector(
    meta_tracks: dict[str, dict[str, Any]],
    path: str,
    info: dict[str, Any],
) -> np.ndarray | None:
    emb_path = info.get("embedding")
    if not emb_path:
        return None
    vec = load_embedding_safe(str(emb_path))
    if vec is None or vec.size == 0:
        return None
    return vec.astype(np.float32, copy=False)


def _build_prepared_candidate(
    meta_tracks: dict[str, dict[str, Any]],
    path: str,
    meta_stats: dict[str, Any],
    controls: PlaylistExpansionControls,
    support_count: int,
    support_distance: float | None,
    source_flags: set[str],
) -> PreparedCandidate | None:
    info = meta_tracks.get(path, {})
    vector = _select_candidate_vector(meta_tracks, path, info)
    if vector is None:
        return None
    bpm_info = track_bpm_sources(path, info)
    candidate = PreparedCandidate(
        path=path,
        source_flags=set(source_flags),
        support_count=max(int(support_count), 1),
        support_distance=support_distance,
        support_seeds=max(int(support_count), 1),
        vector=vector,
        title=str(info.get("title", "") or ""),
        artist=str(info.get("artist", "") or ""),
        bpm=bpm_info.preferred_bpm,
        rekordbox_bpm=bpm_info.rekordbox_bpm,
        rbassist_bpm=bpm_info.rbassist_bpm,
        bpm_delta=bpm_info.delta,
        bpm_mismatch=bpm_info.large_mismatch,
        bpm_source=bpm_info.preferred_source,
        key=str(info.get("key", "") or "") or None,
        mytags=[str(tag) for tag in (info.get("mytags", []) or []) if str(tag).strip()],
        section_intro=_load_track_embedding(info, "embedding_intro") if controls.use_section_scores else None,
    )
    if meta_stats.get("seed_centroid") is not None:
        candidate.ann_distance = 1.0 - _cosine_similarity(vector, meta_stats["seed_centroid"].astype(np.float32, copy=False))
    candidate.component_scores = _compute_component_scores(candidate, meta_stats, controls)
    return candidate


def _merge_candidate_maps(
    centroid_hits: list[CandidateHit],
    coverage_hits: list[CandidateHit],
    meta_tracks: dict[str, dict[str, Any]],
    meta_stats: dict[str, Any],
    controls: PlaylistExpansionControls,
) -> list[PreparedCandidate]:
    prepared: dict[str, PreparedCandidate] = {}
    for hit in centroid_hits:
        candidate = _build_prepared_candidate(
            meta_tracks,
            hit.path,
            meta_stats,
            controls,
            support_count=hit.support_count,
            support_distance=hit.support_distance,
            source_flags={"centroid"},
        )
        if candidate is None:
            continue
        prepared[hit.path] = candidate
    for hit in coverage_hits:
        existing = prepared.get(hit.path)
        if existing is None:
            candidate = _build_prepared_candidate(
                meta_tracks,
                hit.path,
                meta_stats,
                controls,
                support_count=hit.support_count,
                support_distance=hit.support_distance,
                source_flags={"coverage"},
            )
            if candidate is None:
                continue
            prepared[hit.path] = candidate
            continue
        existing.source_flags.add("coverage")
        existing.support_count = max(existing.support_count, int(hit.support_count))
        if hit.support_distance is not None:
            existing.support_distance = hit.support_distance if existing.support_distance is None else min(existing.support_distance, hit.support_distance)
        existing.support_seeds = max(existing.support_seeds, int(hit.support_seeds))
        if existing.vector is not None and meta_stats.get("seed_centroid") is not None:
            existing.ann_distance = 1.0 - _cosine_similarity(existing.vector, meta_stats["seed_centroid"].astype(np.float32, copy=False))
        existing.component_scores = _compute_component_scores(existing, meta_stats, controls)
    ordered = list(prepared.values())
    ordered.sort(key=lambda item: item.source_rank())
    return ordered


def prepare_playlist_expansion(
    seed_paths: Any,
    *,
    mode: str = "balanced",
    strategy: str = "blend",
    candidate_pool: int = 250,
    diversity: float | None = None,
    filters: PlaylistExpansionFilters | dict[str, Any] | None = None,
    weights: PlaylistExpansionWeights | dict[str, Any] | None = None,
    controls: PlaylistExpansionControls | dict[str, Any] | None = None,
) -> ExpansionWorkspace:
    meta = load_meta()
    meta_tracks = meta.get("tracks", {})
    resolved_controls = _resolve_playlist_expansion_controls(
        mode=mode,
        strategy=strategy,
        candidate_pool=candidate_pool,
        diversity=diversity,
        filters=filters,
        weights=weights,
        controls=controls,
    )
    seed_tracks, seed_diagnostics = _coerce_seed_tracks(seed_paths, meta_tracks)
    if not seed_tracks:
        raise ValueError("No seed tracks could be resolved into rbassist metadata.")

    resolved_seed_paths = [track.meta_path for track in seed_tracks if track.meta_path]
    if not resolved_seed_paths:
        raise ValueError("No seed tracks with embeddings or metadata were available for expansion.")
    if len(resolved_seed_paths) < 3:
        raise ValueError("At least 3 mapped seed tracks are required for playlist expansion.")

    meta_stats = _collect_meta_features(meta_tracks, seed_tracks)
    if not meta_stats["seed_vectors"]:
        raise ValueError("No seed embeddings were available for playlist expansion.")

    candidate_limit = max(1, int(resolved_controls.candidate_pool))
    exclude_paths = set(resolved_seed_paths)
    centroid_hits: list[CandidateHit] = []
    coverage_hits: list[CandidateHit] = []

    centroid_vec = meta_stats.get("seed_centroid")
    if centroid_vec is not None:
        centroid_hits = _query_index_or_bruteforce(meta_tracks, centroid_vec, candidate_limit, exclude_paths)

    coverage_support: dict[str, CandidateHit] = {}
    seed_query_limit = max(candidate_limit, 50)
    for track in seed_tracks:
        seed_vec = _seed_embedding_vector(track, meta_tracks)
        if seed_vec is None:
            continue
        query_hits = _query_index_or_bruteforce(meta_tracks, seed_vec, seed_query_limit, exclude_paths)
        for hit in query_hits:
            current = coverage_support.get(hit.path)
            if current is None:
                coverage_support[hit.path] = CandidateHit(
                    path=hit.path,
                    distance=hit.distance,
                    support_count=1,
                    support_distance=hit.distance,
                    support_seeds=1,
                )
                continue
            current.support_count += 1
            current.support_seeds += 1
            if hit.distance is not None and (current.support_distance is None or hit.distance < current.support_distance):
                current.support_distance = hit.distance
            if hit.distance is not None and (current.distance is None or hit.distance < current.distance):
                current.distance = hit.distance
    coverage_hits = sorted(
        coverage_support.values(),
        key=lambda item: (
            -item.support_count,
            item.distance if item.distance is not None else 999.0,
            item.path.lower(),
        ),
    )[:candidate_limit]

    candidates = _merge_candidate_maps(centroid_hits, coverage_hits, meta_tracks, meta_stats, resolved_controls)
    transition_candidate_scores = [
        float(candidate.component_scores["transition_score"])
        for candidate in candidates
        if "transition_score" in candidate.component_scores
    ]
    diagnostics = {
        **seed_diagnostics,
        "seed_loader_diagnostics": dict(getattr(seed_paths, "diagnostics", {})) if isinstance(seed_paths, SeedPlaylist) else {},
        "mode": resolved_controls.mode,
        "strategy": resolved_controls.strategy,
        "controls_applied": resolved_controls.to_dict(),
        "normalized_weights": resolved_controls.weights.to_dict(),
        "candidate_pool": int(resolved_controls.candidate_pool),
        "candidate_pool_total": len(candidates),
        "candidate_pool_centroid_total": len(centroid_hits),
        "candidate_pool_coverage_total": len(coverage_hits),
        "diversity": float(resolved_controls.diversity),
        "resolved_seed_paths": resolved_seed_paths,
        "clean_seed_tracks_total": len(resolved_seed_paths),
        "seed_embedding_count": len(meta_stats["seed_vectors"]),
        "core_seed_tag_count": len(meta_stats["seed_core_tags"]),
        "section_scores_requested": bool(resolved_controls.use_section_scores),
        "seed_section_late_count": len(meta_stats.get("seed_late_vectors", [])),
        "candidate_section_intro_count": sum(1 for candidate in candidates if candidate.section_intro is not None),
        "transition_candidate_score_count": len(transition_candidate_scores),
        "transition_candidate_score_mean": (
            round(float(np.mean(transition_candidate_scores)), 6) if transition_candidate_scores else None
        ),
    }
    return ExpansionWorkspace(
        seed_tracks=list(seed_tracks),
        controls=resolved_controls,
        meta_tracks=meta_tracks,
        seed_vectors=list(meta_stats["seed_vectors"]),
        meta_stats=meta_stats,
        candidates=candidates,
        diagnostics=diagnostics,
    )


def rerank_playlist_expansion(
    workspace: ExpansionWorkspace,
    *,
    controls: PlaylistExpansionControls | dict[str, Any] | None = None,
    add_count: int | None = None,
    target_total: int | None = None,
) -> ExpansionResult:
    resolved_controls = _resolve_playlist_expansion_controls(
        mode=workspace.controls.mode,
        strategy=workspace.controls.strategy,
        candidate_pool=workspace.controls.candidate_pool,
        diversity=workspace.controls.diversity,
        filters=workspace.controls.filters,
        weights=workspace.controls.weights,
        controls=controls,
    )

    resolved_seed_paths = [track.meta_path for track in workspace.seed_tracks if track.meta_path]
    if target_total is None and add_count is None:
        add_count = 25
    elif target_total is None:
        add_count = max(int(add_count or 0), 0)
        target_total = len(resolved_seed_paths) + add_count
    elif add_count is None:
        target_total = max(int(target_total), 0)
        add_count = max(target_total - len(resolved_seed_paths), 0)
    else:
        target_total = max(int(target_total), 0)
        add_count = max(int(add_count), 0)
        if target_total != len(resolved_seed_paths) + add_count:
            raise ValueError("target_total and add_count are inconsistent with the resolved seed count.")

    if add_count <= 0:
        combined_tracks = [track.meta_path for track in workspace.seed_tracks if track.meta_path]
        diagnostics = {
            **workspace.diagnostics,
            "requested_target_total": int(target_total),
            "requested_add_count": int(add_count),
            "target_total": int(target_total),
            "add_count": int(add_count),
            "added_tracks_total": 0,
            "selected_count": 0,
            "combined_tracks_total": len(combined_tracks),
        }
        return ExpansionResult(
            seed_tracks=list(workspace.seed_tracks),
            added_tracks=[],
            combined_tracks=combined_tracks,
            diagnostics=diagnostics,
            target_total=int(target_total),
            add_count=int(add_count),
            strategy=resolved_controls.strategy,
            mode=resolved_controls.mode,
        )

    candidate_pool = min(max(1, int(resolved_controls.candidate_pool)), len(workspace.candidates))
    candidates = [candidate for candidate in workspace.candidates if _candidate_matches_strategy(candidate, resolved_controls.strategy)]
    candidates.sort(key=lambda item: item.source_rank())
    candidates = candidates[:candidate_pool]

    scored_candidates: list[tuple[PreparedCandidate, float, float, dict[str, float], list[str]]] = []
    normalized_weights = resolved_controls.weights.normalized().to_dict()
    for candidate in candidates:
        if not _candidate_passes_filters(candidate, workspace.meta_stats, resolved_controls):
            continue
        base_score = sum(float(normalized_weights.get(name, 0.0)) * float(candidate.component_scores.get(name, 0.0)) for name in normalized_weights)
        reasons = [name for name, value in candidate.component_scores.items() if value > 0.0]
        scored_candidates.append((candidate, base_score, base_score, dict(candidate.component_scores), reasons))

    selected: list[ExpandedTrack] = []
    selected_vecs: list[np.ndarray] = []
    remaining = sorted(scored_candidates, key=lambda item: (-item[1], item[0].path.lower()))
    diversity = max(0.0, min(1.0, float(resolved_controls.diversity)))
    seen_signatures: Counter[tuple[str, str, str]] = Counter()
    for track in workspace.seed_tracks:
        info = workspace.meta_tracks.get(track.meta_path or track.rekordbox_path, {})
        seed_signature = _track_repeat_signature(
            track.title or str(info.get("title", "") or ""),
            track.artist or str(info.get("artist", "") or ""),
            track.meta_path or track.rekordbox_path,
        )
        _register_repeat_signature(seen_signatures, seed_signature)

    repeat_penalty_total = 0.0
    repeat_reason_counts: Counter[str] = Counter()
    while remaining and len(selected) < add_count:
        best_idx = 0
        best_candidate: ExpandedTrack | None = None
        best_score = float("-inf")
        best_vec = np.asarray([], dtype=np.float32)
        best_repeat_penalty = 0.0
        best_repeat_reasons: list[str] = []
        best_repeat_signature = {"artist": "", "title_stem": "", "version": ""}
        for idx, (candidate, base_score, _base_copy, component_scores, reasons) in enumerate(remaining):
            max_similarity = 0.0
            if candidate.vector is not None and candidate.vector.size:
                reference_vecs = selected_vecs or workspace.seed_vectors
                for vec in reference_vecs:
                    max_similarity = max(max_similarity, _cosine_similarity(candidate.vector, vec))
            repeat_penalty, repeat_reasons, repeat_signature = _repeat_penalty(
                SimpleNamespace(path=candidate.path, title=candidate.title, artist=candidate.artist),
                seen_signatures,
            )
            final_score = base_score - (diversity * max_similarity) - repeat_penalty
            if final_score > best_score or (final_score == best_score and candidate.path.lower() < (best_candidate.path.lower() if best_candidate else "")):
                best_idx = idx
                best_score = final_score
                best_vec = candidate.vector if candidate.vector is not None else np.asarray([], dtype=np.float32)
                repeat_component_scores = dict(component_scores)
                if repeat_penalty > 0:
                    repeat_component_scores["anti_repetition"] = repeat_penalty
                best_candidate = ExpandedTrack(
                    path=candidate.path,
                    score=final_score,
                    base_score=base_score,
                    final_score=final_score,
                    ann_distance=candidate.ann_distance,
                    support_count=candidate.support_count,
                    title=candidate.title,
                    artist=candidate.artist,
                    bpm=candidate.bpm,
                    rekordbox_bpm=candidate.rekordbox_bpm,
                    rbassist_bpm=candidate.rbassist_bpm,
                    bpm_delta=candidate.bpm_delta,
                    bpm_mismatch=candidate.bpm_mismatch,
                    bpm_source=candidate.bpm_source,
                    key=candidate.key,
                    mytags=list(candidate.mytags),
                    component_scores=repeat_component_scores,
                    reasons=reasons + repeat_reasons + (["diversity"] if diversity > 0 else []),
                )
                best_repeat_penalty = repeat_penalty
                best_repeat_reasons = list(repeat_reasons)
                best_repeat_signature = repeat_signature
        if best_candidate is None:
            break
        selected.append(best_candidate)
        if best_vec.size:
            selected_vecs.append(best_vec)
        if best_repeat_penalty > 0:
            repeat_penalty_total += float(best_repeat_penalty)
            repeat_reason_counts.update(best_repeat_reasons)
        _register_repeat_signature(seen_signatures, best_repeat_signature)
        remaining.pop(best_idx)

    selected.sort(key=lambda item: (-item.final_score, item.path.lower()))
    combined_tracks = [track.meta_path for track in workspace.seed_tracks if track.meta_path] + [track.path for track in selected]
    selected_transition_scores = [
        float(track.component_scores["transition_score"])
        for track in selected
        if "transition_score" in track.component_scores
    ]
    diagnostics = {
        **workspace.diagnostics,
        "controls_applied": resolved_controls.to_dict(),
        "normalized_weights": normalized_weights,
        "requested_target_total": int(target_total),
        "requested_add_count": int(add_count),
        "target_total": int(target_total),
        "add_count": int(add_count),
        "candidate_pool_total": len(workspace.candidates),
        "selected_candidate_pool_total": len(candidates),
        "selected_count": len(selected),
        "added_tracks_total": len(selected),
        "combined_tracks_total": len(combined_tracks),
        "anti_repetition_penalty_total": round(float(repeat_penalty_total), 6),
        "anti_repetition_reason_counts": dict(repeat_reason_counts),
        "selected_transition_score_count": len(selected_transition_scores),
        "selected_transition_score_mean": (
            round(float(np.mean(selected_transition_scores)), 6) if selected_transition_scores else None
        ),
    }
    return ExpansionResult(
        seed_tracks=list(workspace.seed_tracks),
        added_tracks=selected,
        combined_tracks=combined_tracks,
        diagnostics=diagnostics,
        target_total=int(target_total),
        add_count=int(add_count),
        strategy=resolved_controls.strategy,
        mode=resolved_controls.mode,
    )


def expand_playlist(
    seed_paths: Any,
    *,
    add_count: int | None = None,
    target_total: int | None = None,
    mode: str = "balanced",
    strategy: str = "blend",
    candidate_pool: int = 250,
    diversity: float = 0.28,
    filters: PlaylistExpansionFilters | dict[str, Any] | None = None,
    weights: PlaylistExpansionWeights | dict[str, Any] | None = None,
    controls: PlaylistExpansionControls | dict[str, Any] | None = None,
) -> ExpansionResult:
    workspace = prepare_playlist_expansion(
        seed_paths,
        mode=mode,
        strategy=strategy,
        candidate_pool=candidate_pool,
        diversity=diversity,
        filters=filters,
        weights=weights,
        controls=controls,
    )
    return rerank_playlist_expansion(
        workspace,
        add_count=add_count,
        target_total=target_total,
        controls=controls,
    )


def build_export_meta(result: ExpansionResult, *, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    meta_all = meta or load_meta()
    tracks_meta = meta_all.get("tracks", {})
    ordered_tracks: dict[str, dict[str, Any]] = {}
    for path in result.combined_tracks:
        if path in tracks_meta and path not in ordered_tracks:
            ordered_tracks[path] = tracks_meta[path]
    return {"tracks": ordered_tracks}


def write_expansion_xml(
    result: ExpansionResult,
    *,
    out_path: str,
    playlist_name: str,
    meta: dict[str, Any] | None = None,
) -> None:
    export_meta = build_export_meta(result, meta=meta)
    write_rekordbox_xml(export_meta, out_path=out_path, playlist_name=playlist_name)
