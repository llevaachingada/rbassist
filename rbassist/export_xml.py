from __future__ import annotations
import pathlib, urllib.parse
from typing import Optional
from xml.etree.ElementTree import Element, SubElement, ElementTree
from .versions import __version__

def _as_location_uri(path: str) -> str:
    p = pathlib.Path(path).resolve()
    return "file://localhost/" + urllib.parse.quote(p.as_posix())

def write_rekordbox_xml(meta: dict, out_path: str, playlist_name: Optional[str] = None) -> None:
    root = Element("DJ_PLAYLISTS", Version="1.0.0")
    SubElement(root, "PRODUCT", Name="rbassist", Version=__version__, Company="You")

    tracks = meta.get("tracks", {})
    coll = SubElement(root, "COLLECTION", Entries=str(len(tracks)))

    # Build global MyTag registry once so we can emit consistent IDs
    all_tags = sorted(
        {
            tag
            for info in tracks.values()
            for tag in (info.get("mytags") or [])
            if isinstance(tag, str) and tag.strip()
        }
    )
    tag_ids = {tag: str(idx) for idx, tag in enumerate(all_tags, start=1)}
    if tag_ids:
        tag_root = SubElement(root, "MY_TAGS")
        for tag, tag_id in tag_ids.items():
            SubElement(tag_root, "TAG", ID=tag_id, Name=tag)

    for i, (path, info) in enumerate(tracks.items(), start=1):
        t = SubElement(coll, "TRACK", TrackID=str(i))
        t.set("Name", info.get("title",""))
        t.set("Artist", info.get("artist",""))
        if info.get("genre"): t.set("Genre", info.get("genre"))
        if info.get("grouping"): t.set("Grouping", info.get("grouping"))
        if info.get("comments"): t.set("Comments", info.get("comments"))
        if info.get("key"): t.set("Tonality", info.get("key"))
        if info.get("bpm"): t.set("AverageBpm", f"{float(info['bpm']):.2f}")
        t.set("Location", _as_location_uri(path))

        # Beatgrid segments
        tempos = info.get("tempos")
        if not tempos and info.get("bpm"):
            tempos = [{"inizio_sec": 0.0, "bpm": float(info["bpm"]), "metro": "4/4", "battito": 1}]
        for seg in tempos or []:
            SubElement(t, "TEMPO",
                Inizio=f"{float(seg.get('inizio_sec',0.0)):.3f}",
                Bpm=f"{float(seg.get('bpm',0.0)):.2f}",
                Metro=seg.get("metro","4/4"),
                Battito=str(int(seg.get("battito",1)))
            )

        # Cues/loops
        for c in info.get("cues", []):
            SubElement(t, "POSITION_MARK",
                Name=c.get("name",""),
                Type=str(int(c.get("type",0))),
                Start=f"{float(c.get('start',0.0)):.3f}",
                End=f"{float(c.get('end',0.0)):.3f}",
                Num=str(int(c.get("num",-1)))
            )

        mytags = [m for m in info.get("mytags", []) if m in tag_ids]
        if mytags:
            mytag_node = SubElement(t, "MY_TAG")
            for tag in mytags:
                SubElement(mytag_node, "TAG", ID=tag_ids[tag], Name=tag)

    # Optional playlist keyed by Location
    pls = SubElement(root, "PLAYLISTS")
    rootnode = SubElement(pls, "NODE", Type="0", Name="ROOT", Count="0")
    if playlist_name:
        pnode = SubElement(rootnode, "NODE", Type="1", Name=playlist_name, Entries=str(len(tracks)), KeyType="1")
        for path in tracks.keys():
            SubElement(pnode, "TRACK", Key=_as_location_uri(path))
        rootnode.set("Count", "1")

    ElementTree(root).write(out_path, encoding="UTF-8", xml_declaration=True)
