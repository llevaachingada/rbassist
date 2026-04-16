from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Mapping

from .utils import make_path_aliases, normalize_path_string

try:
    from pyrekordbox import Rekordbox6Database  # type: ignore
except Exception:  # pragma: no cover - optional dependency handling
    Rekordbox6Database = None  # type: ignore


LARGE_BPM_MISMATCH_THRESHOLD = 5.0


@dataclass(frozen=True, slots=True)
class TrackBpmSources:
    preferred_bpm: float | None
    preferred_source: str
    rekordbox_bpm: float | None
    rbassist_bpm: float | None
    delta: float | None
    large_mismatch: bool


def normalize_rekordbox_bpm(value: Any) -> float | None:
    try:
        bpm = float(value)
    except Exception:
        return None
    if bpm <= 0:
        return None
    if bpm > 1000:
        bpm = bpm / 100.0
    return round(float(bpm), 2)


@lru_cache(maxsize=1)
def load_rekordbox_bpm_map() -> dict[str, float]:
    if Rekordbox6Database is None:
        return {}
    db = Rekordbox6Database()
    try:
        query = db.get_content()
        rows = list(query.all()) if hasattr(query, "all") else list(query)
        mapping: dict[str, float] = {}
        for row in rows:
            raw_path = (
                getattr(row, "FolderPath", None)
                or getattr(row, "Location", None)
                or getattr(row, "OrgFolderPath", None)
                or ""
            )
            bpm = normalize_rekordbox_bpm(getattr(row, "BPM", None))
            if not raw_path or bpm is None:
                continue
            mapping[normalize_path_string(str(raw_path))] = bpm
        return mapping
    finally:
        try:
            db.close()
        except Exception:
            pass


def clear_rekordbox_bpm_cache() -> None:
    load_rekordbox_bpm_map.cache_clear()


def lookup_rekordbox_bpm(
    path: str | None,
    *,
    rekordbox_bpm_by_path: Mapping[str, float] | None = None,
) -> float | None:
    if not path:
        return None
    bpm_map = rekordbox_bpm_by_path if rekordbox_bpm_by_path is not None else load_rekordbox_bpm_map()
    for alias in sorted(make_path_aliases(path)):
        match = bpm_map.get(normalize_path_string(alias))
        if match is not None:
            return float(match)
    return None


def track_bpm_sources(
    path: str | None,
    info: Mapping[str, Any] | None = None,
    *,
    rekordbox_bpm: float | None = None,
    rekordbox_bpm_by_path: Mapping[str, float] | None = None,
    mismatch_threshold: float = LARGE_BPM_MISMATCH_THRESHOLD,
) -> TrackBpmSources:
    info = info or {}
    rbassist_bpm = normalize_rekordbox_bpm(info.get("bpm"))
    rekordbox_bpm_value = normalize_rekordbox_bpm(rekordbox_bpm)
    if rekordbox_bpm_value is None:
        rekordbox_bpm_value = lookup_rekordbox_bpm(path, rekordbox_bpm_by_path=rekordbox_bpm_by_path)
    preferred_bpm = rekordbox_bpm_value if rekordbox_bpm_value is not None else rbassist_bpm
    preferred_source = "rekordbox" if rekordbox_bpm_value is not None else ("rbassist" if rbassist_bpm is not None else "unknown")
    delta = None
    if rekordbox_bpm_value is not None and rbassist_bpm is not None:
        delta = round(rbassist_bpm - rekordbox_bpm_value, 2)
    return TrackBpmSources(
        preferred_bpm=preferred_bpm,
        preferred_source=preferred_source,
        rekordbox_bpm=rekordbox_bpm_value,
        rbassist_bpm=rbassist_bpm,
        delta=delta,
        large_mismatch=bool(delta is not None and abs(delta) >= float(mismatch_threshold)),
    )
