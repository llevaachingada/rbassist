from __future__ import annotations
import csv, pathlib
from typing import Dict, Any
import yaml

# Simple CSV reader + mapping into our meta store

def load_mapping(config_path: str | pathlib.Path) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def import_bandcamp(csv_path: str, config_path: str, meta: dict) -> dict:
    cfg = load_mapping(config_path)
    cols = cfg.get("columns", {})
    with open(csv_path, newline='', encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            artist = row.get(cols.get("artist", "artist"), "").strip()
            title  = row.get(cols.get("title", "title"), "").strip()
            # We try to find a matching path in meta by Artist - Title
            for path, info in meta.get("tracks", {}).items():
                if (info.get("artist", "").strip().lower(), info.get("title", "").strip().lower()) == (artist.lower(), title.lower()):
                    # store tags into info["tags"] (list)
                    tags_raw = row.get(cols.get("tags", "tags"), "")
                    tags = [t.strip() for t in tags_raw.replace(";", ",").split(",") if t.strip()]
                    info.setdefault("tags", sorted(set(info.get("tags", []) + tags)))
                    info["genre"] = row.get(cols.get("genre", "genre")) or info.get("genre")
                    info["subgenre"] = row.get(cols.get("subgenre", "subgenre")) or info.get("subgenre")
    return meta



