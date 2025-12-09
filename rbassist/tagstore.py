from __future__ import annotations

import pathlib
from typing import Dict, List, Iterable
from urllib.parse import unquote
import xml.etree.ElementTree as ET

import yaml

from .utils import load_meta, save_meta

_CONFIG_DIR = pathlib.Path(__file__).resolve().parents[1] / "config"
_TAG_FILE = _CONFIG_DIR / "tags.yml"

_DEFAULT_CONFIG: Dict[str, object] = {
    "available": [
        "Warm-up",
        "Peak Hour",
        "Vocals",
        "Energy Boost",
        "Closer",
    ],
    "library": {},
}


def _read_config() -> Dict[str, object]:
    if _TAG_FILE.exists():
        try:
            data = yaml.safe_load(_TAG_FILE.read_text("utf-8")) or {}
        except Exception:
            data = {}
    else:
        data = {}
    cfg: Dict[str, object] = {
        "available": list(dict.fromkeys(data.get("available", []) or _DEFAULT_CONFIG["available"])),
        "library": data.get("library", {}) or {},
    }
    return cfg


def _write_config(data: Dict[str, object]) -> None:
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "available": sorted(set(data.get("available", []))),
        "library": data.get("library", {}),
    }
    _TAG_FILE.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def available_tags() -> List[str]:
    return list(_read_config()["available"])


def set_available_tags(tags: List[str]) -> None:
    cfg = _read_config()
    merged = list(dict.fromkeys(tags + cfg["available"]))  # type: ignore[arg-type]
    cfg["available"] = merged
    _write_config(cfg)


def track_tags(path: str) -> List[str]:
    cfg = _read_config()
    lib = cfg.get("library", {})
    try:
        tags = lib.get(path, [])  # type: ignore[assignment]
    except AttributeError:
        tags = []
    return list(tags or [])


def bulk_set_track_tags(mapping: Dict[str, Iterable[str]], only_existing: bool = False) -> int:
    """Assign or clear MyTags for multiple tracks in one shot."""
    if not mapping:
        return 0

    cfg = _read_config()
    lib = cfg.get("library", {})
    if not isinstance(lib, dict):
        lib = {}
    available: List[str] = list(cfg.get("available", []))  # type: ignore[list-item]

    meta = load_meta()
    tracks_meta = meta.setdefault("tracks", {})

    applied = 0
    cleaned: Dict[str, List[str]] = {}
    for raw_path, tags in mapping.items():
        if only_existing and raw_path not in tracks_meta:
            continue
        clean = [t.strip() for t in (tags or []) if t and t.strip()]
        cleaned[raw_path] = clean
        if clean:
            for tag in clean:
                if tag not in available:
                    available.append(tag)
        applied += 1

    if not cleaned:
        return 0

    for path, clean in cleaned.items():
        if clean:
            lib[path] = clean
        else:
            lib.pop(path, None)
        info = tracks_meta.setdefault(path, {})
        if clean:
            info["mytags"] = clean
        else:
            info.pop("mytags", None)

    cfg["library"] = lib
    cfg["available"] = available
    _write_config(cfg)
    save_meta(meta)
    return applied


def set_track_tags(path: str, tags: List[str]) -> None:
    bulk_set_track_tags({path: tags})


def sync_meta_from_config() -> None:
    cfg = _read_config()
    lib = cfg.get("library", {})
    if not isinstance(lib, dict):
        return
    meta = load_meta()
    for path, tags in lib.items():
        info = meta["tracks"].setdefault(path, {})
        info["mytags"] = list(tags)
    save_meta(meta)


def _location_to_path(loc: str) -> str | None:
    if not loc:
        return None
    prefix = "file://"
    if loc.startswith(prefix):
        loc = loc[len(prefix):]
        if loc.startswith("localhost/"):
            loc = loc[len("localhost/"):]
    loc = unquote(loc)
    # On Windows the path will already look like C:/Foo; Path will normalise separators.
    return str(pathlib.Path(loc))


def import_rekordbox_tags(xml_path: str, only_existing: bool = True) -> int:
    """Import My Tags from a Rekordbox XML export."""
    tree = ET.parse(xml_path)
    root = tree.getroot()
    mapping: Dict[str, List[str]] = {}
    for track in root.findall("./COLLECTION/TRACK"):
        loc = track.get("Location")
        tag_parent = track.find("MY_TAG")
        if not loc or tag_parent is None:
            continue
        tags = [tag.get("Name") or "" for tag in tag_parent.findall("TAG")]
        tags = [t for t in tags if t.strip()]
        if not tags:
            continue
        path = _location_to_path(loc)
        if not path:
            continue
        mapping[path] = tags
    if not mapping:
        return 0
    # Allow tags to create meta entries even if the track has not been seen
    # by rbassist yet; this makes Rekordbox XML imports more forgiving.
    return bulk_set_track_tags(mapping, only_existing=False)
