from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from rbassist.utils import ROOT, is_junk_path, resolve_track_path

from rbassist.bpm_sources import track_bpm_sources


@dataclass(frozen=True, slots=True)
class LibrarySnapshot:
    tracks_total: int
    embedded_total: int
    analyzed_total: int
    preview_rows: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class LibraryPageModel:
    """GUI-neutral data for the Library page health table."""

    rows: list[dict[str, Any]]
    issue_counts: dict[str, int]
    tracks_total: int
    embedded_total: int
    analyzed_total: int


def format_bpm_cell(value: float | None) -> str:
    return f"{float(value):.0f}" if isinstance(value, (int, float)) and value else "-"


def format_bpm_metric(value: float | None) -> str:
    return f"{float(value):.2f} BPM" if isinstance(value, (int, float)) and value else "-- BPM"


def bpm_alert_text(large_mismatch: bool) -> str:
    return "Large mismatch" if large_mismatch else "-"


def track_display_name(path: str, info: Mapping[str, Any]) -> str:
    title = str(info.get("title") or "").strip()
    if title:
        return title
    return str(path).split("\\")[-1].split("/")[-1]


def build_library_rows(meta: Mapping[str, Any], *, limit: int | None = None) -> list[dict[str, Any]]:
    """Build read-only rows for library-style frontends."""
    tracks = meta.get("tracks", {}) if isinstance(meta, Mapping) else {}
    rows: list[dict[str, Any]] = []
    for path, info in tracks.items():
        if not isinstance(info, Mapping):
            info = {}
        bpm_info = track_bpm_sources(str(path), info)
        rows.append(
            {
                "path": str(path),
                "artist": info.get("artist", ""),
                "title": track_display_name(str(path), info),
                "bpm": format_bpm_cell(bpm_info.preferred_bpm),
                "rekordbox_bpm": format_bpm_cell(bpm_info.rekordbox_bpm),
                "rbassist_bpm": format_bpm_cell(bpm_info.rbassist_bpm),
                "bpm_alert": bpm_alert_text(bpm_info.large_mismatch),
                "key": info.get("key") or "-",
            }
        )

    rows.sort(key=lambda row: (str(row["artist"]).lower(), str(row["title"]).lower()))
    if limit is not None:
        return rows[: max(0, int(limit))]
    return rows


def build_library_snapshot(meta: Mapping[str, Any], *, preview_limit: int = 100) -> LibrarySnapshot:
    """Build a small read-only summary for desktop proof-of-life views."""
    tracks = meta.get("tracks", {}) if isinstance(meta, Mapping) else {}
    embedded = 0
    analyzed = 0
    for info in tracks.values():
        if not isinstance(info, Mapping):
            continue
        if info.get("embedding"):
            embedded += 1
        if info.get("bpm") and info.get("key"):
            analyzed += 1
    return LibrarySnapshot(
        tracks_total=len(tracks),
        embedded_total=embedded,
        analyzed_total=analyzed,
        preview_rows=build_library_rows(meta, limit=preview_limit),
    )


def build_library_page_model(
    meta: Mapping[str, Any],
    *,
    base_dir: Path = ROOT,
) -> LibraryPageModel:
    """Build the Library page table data without any GUI dependencies."""
    tracks = meta.get("tracks", {}) if isinstance(meta, Mapping) else {}
    rows: list[dict[str, Any]] = []
    embedded_total = 0
    analyzed_total = 0

    for path, info in tracks.items():
        if not isinstance(info, Mapping):
            info = {}

        tags = info.get("mytags") or info.get("tags") or []
        if isinstance(tags, (list, tuple)):
            tags_str = ", ".join(str(tag) for tag in tags)
        else:
            tags_str = str(tags)

        try:
            stale_path = not resolve_track_path(path, base_dir=base_dir).exists()
        except Exception:
            stale_path = True

        bare_path = not Path(str(path)).drive and not Path(str(path)).is_absolute()
        junk_path = is_junk_path(path)

        embedding_path = info.get("embedding")
        embedding_ok = False
        if embedding_path:
            emb_candidate = Path(str(embedding_path))
            if not emb_candidate.is_absolute():
                emb_candidate = (base_dir / emb_candidate).resolve()
            embedding_ok = emb_candidate.exists()

        missing_embedding = not embedding_ok
        missing_analysis = not (info.get("bpm") and info.get("key"))
        missing_cues = not info.get("cues")

        if embedding_ok:
            embedded_total += 1
        if not missing_analysis:
            analyzed_total += 1

        issues: list[str] = []
        if stale_path:
            issues.append("stale path")
        if bare_path:
            issues.append("bare path")
        if junk_path:
            issues.append("junk path")
        if missing_embedding:
            issues.append("missing embedding")
        if missing_analysis:
            issues.append("missing analysis")
        if missing_cues:
            issues.append("missing cues")

        rows.append(
            {
                "path": str(path),
                "artist": info.get("artist", ""),
                "title": info.get("title", Path(str(path)).name),
                "bpm": f"{info.get('bpm', 0):.0f}" if info.get("bpm") else "-",
                "key": info.get("key", "-"),
                "embedded": "Yes" if embedding_ok else "No",
                "analyzed": "Yes" if not missing_analysis else "No",
                "beatgrid": "Yes" if info.get("tempos") else "No",
                "mytags": tags_str,
                "issues": ", ".join(issues) if issues else "-",
                "_health": {
                    "missing_embedding": missing_embedding,
                    "missing_analysis": missing_analysis,
                    "missing_cues": missing_cues,
                    "stale_path": stale_path,
                    "bare_path": bare_path,
                    "junk_path": junk_path,
                },
            }
        )

    issue_modes = [
        "missing_embedding",
        "missing_analysis",
        "missing_cues",
        "stale_path",
        "bare_path",
        "junk_path",
    ]
    issue_counts = {
        mode: sum(1 for row in rows if row.get("_health", {}).get(mode))
        for mode in issue_modes
    }

    return LibraryPageModel(
        rows=rows,
        issue_counts=issue_counts,
        tracks_total=len(tracks),
        embedded_total=embedded_total,
        analyzed_total=analyzed_total,
    )
