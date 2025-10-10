from __future__ import annotations
import datetime as dt
from .utils import load_meta
from .export_xml import write_rekordbox_xml


def _date_ok(info: dict, since: str | None, until: str | None) -> bool:
    try:
        added = info.get("added")
        if not added:
            return True
        d = dt.date.fromisoformat(str(added)[:10])
        if since and d < dt.date.fromisoformat(since):
            return False
        if until and d > dt.date.fromisoformat(until):
            return False
        return True
    except Exception:
        return True


def filter_tracks(my_tag: str | None = None, rating_min: int | None = None,
                  since: str | None = None, until: str | None = None) -> list[str]:
    tracks = load_meta().get("tracks", {})
    out: list[str] = []
    for path, info in tracks.items():
        if my_tag:
            tags = info.get("mytags", [])
            if my_tag not in tags:
                continue
        if rating_min is not None:
            try:
                if int(info.get("rating", 0)) < int(rating_min):
                    continue
            except Exception:
                continue
        if not _date_ok(info, since, until):
            continue
        out.append(path)
    return out


def make_intelligent_playlist(xml_out: str, name: str,
                              my_tag: str | None = None, rating_min: int | None = None,
                              since: str | None = None, until: str | None = None) -> None:
    selected = set(filter_tracks(my_tag, rating_min, since, until))
    meta_all = load_meta()
    sub = {"tracks": {p: meta_all["tracks"][p] for p in meta_all["tracks"] if p in selected}}
    write_rekordbox_xml(sub, out_path=xml_out, playlist_name=name)

