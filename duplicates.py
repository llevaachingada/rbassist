from __future__ import annotations
import pathlib
from collections import defaultdict
from typing import Tuple

try:
    from mutagen import File as MFile  # type: ignore
except Exception as e:
    MFile = None  # lazy handling in functions


def _media_key(info: dict) -> Tuple[str, str, int]:
    a = (info.get("artist", "") or "").strip().lower()
    t = (info.get("title", "") or "").strip().lower()
    dur = int(info.get("duration", 0))
    return (a, t, dur)


def _bitrate_of(path: str) -> int:
    try:
        if MFile is None:
            return 0
        mf = MFile(path)
        return int(getattr(getattr(mf, "info", None), "bitrate", 0) or 0)
    except Exception:
        return 0


def _sample_rate_of(path: str) -> int:
    try:
        if MFile is None:
            return 0
        mf = MFile(path)
        return int(getattr(getattr(mf, "info", None), "sample_rate", 0) or 0)
    except Exception:
        return 0


def _is_lossless(path: str) -> int:
    return 1 if pathlib.Path(path).suffix.lower() in {".flac", ".wav", ".aiff", ".aif"} else 0


def find_duplicates(meta: dict) -> list[tuple[str, str]]:
    tracks = meta.get("tracks", {})
    buckets: dict[Tuple[str, str, int], list[str]] = defaultdict(list)
    for p, info in tracks.items():
        buckets[_media_key(info)].append(p)

    to_remove: list[tuple[str, str]] = []
    for _, paths in buckets.items():
        if len(paths) < 2:
            continue
        ranked = sorted(paths, key=lambda x: (_is_lossless(x), _bitrate_of(x)), reverse=True)
        keep = ranked[0]
        for lose in ranked[1:]:
            to_remove.append((keep, lose))
    return to_remove


def cdj_warnings(path: str) -> list[str]:
    warns: list[str] = []
    sr = _sample_rate_of(path)
    if sr and sr > 96000:
        warns.append(f"Sample rate {sr}Hz may be unsupported")
    return warns

