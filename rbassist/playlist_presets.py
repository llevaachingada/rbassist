from __future__ import annotations

import pathlib
from typing import Dict, List

import yaml

_CONFIG_DIR = pathlib.Path(__file__).resolve().parents[1] / "config"
_PRESET_FILE = _CONFIG_DIR / "playlist_presets.yml"


def _read() -> List[Dict[str, object]]:
    if _PRESET_FILE.exists():
        try:
            data = yaml.safe_load(_PRESET_FILE.read_text("utf-8")) or []
        except Exception:
            data = []
    else:
        data = []
    presets: List[Dict[str, object]] = []
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            presets.append(
                {
                    "name": item.get("name", "Preset"),
                    "output": item.get("output", "rb_intelligent.xml"),
                    "mytag": item.get("mytag", ""),
                    "rating_min": int(item.get("rating_min", 0) or 0),
                    "since": item.get("since", "") or "",
                    "until": item.get("until", "") or "",
                }
            )
    return presets


def _write(presets: List[Dict[str, object]]) -> None:
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    payload = []
    for preset in presets:
        payload.append(
            {
                "name": preset.get("name", "Preset"),
                "output": preset.get("output", "rb_intelligent.xml"),
                "mytag": preset.get("mytag", ""),
                "rating_min": int(preset.get("rating_min", 0) or 0),
                "since": preset.get("since", "") or "",
                "until": preset.get("until", "") or "",
            }
        )
    _PRESET_FILE.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def load_presets() -> List[Dict[str, object]]:
    return _read()


def upsert_preset(preset: Dict[str, object]) -> None:
    presets = _read()
    name = str(preset.get("name", "Preset"))
    filtered = [p for p in presets if p.get("name") != name]
    filtered.append(
        {
            "name": name,
            "output": preset.get("output", "rb_intelligent.xml"),
            "mytag": preset.get("mytag", ""),
            "rating_min": int(preset.get("rating_min", 0) or 0),
            "since": preset.get("since", "") or "",
            "until": preset.get("until", "") or "",
        }
    )
    filtered.sort(key=lambda p: p["name"])
    _write(filtered)


def delete_preset(name: str) -> None:
    presets = [p for p in _read() if p.get("name") != name]
    _write(presets)
