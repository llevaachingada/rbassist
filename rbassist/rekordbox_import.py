from __future__ import annotations

from typing import Any, Dict, List
from pathlib import Path

from pyrekordbox import Rekordbox6Database
from pyrekordbox.db6.tables import DjmdContent

from .utils import console
from .tagstore import bulk_set_track_tags


def _normalize_rb_path(folder_path: str | None) -> str | None:
    """Normalize Rekordbox DjmdContent.FolderPath into a canonical path string.

    Rekordbox stores paths with forward slashes; rbassist typically uses OS-native
    paths. Routing through Path(...) ensures we match the style used in meta/config.
    """
    if not folder_path:
        return None
    try:
        return str(Path(str(folder_path).strip()))
    except Exception:
        return str(folder_path).strip()


def import_rekordbox_mytags_from_db() -> int:
    """
    Import Rekordbox 6/7 MyTags directly from the encrypted master.db into
    rbassist's meta.json.

    This is read-only with respect to Rekordbox: we only traverse ORM objects and
    persist tags into rbassist's own metadata store.

    Returns the number of (track, tag) associations that were added.
    """
    db = Rekordbox6Database()
    try:
        mapping: Dict[str, List[str]] = {}
        # get_content() with no filters returns a Query[DjmdContent]
        query = db.get_content()
        if isinstance(query, list):
            contents: List[DjmdContent] = query
        else:
            contents = list(query.all())

        added = 0
        for cont in contents:
            # FolderPath is the canonical full path field used elsewhere in pyrekordbox.
            key = _normalize_rb_path(getattr(cont, "FolderPath", None))
            if not key:
                continue

            # MyTags relationship is DjmdSongMyTag rows; MyTagName proxy gives the label.
            tag_names = []
            for item in getattr(cont, "MyTags", []):
                name = getattr(item, "MyTagName", None)
                if name:
                    tag_names.append(str(name).strip())

            clean = [t for t in tag_names if t]
            if not clean:
                continue

            mapping[key] = clean

        if mapping:
            # Let tagstore handle keeping config/tags.yml and meta.json in sync.
            added = bulk_set_track_tags(mapping, only_existing=False)
        else:
            added = 0

        console.print(
            f"[green]Imported/merged {added} Rekordbox MyTag assignments from master.db.[/green]"
        )
        return added
    finally:
        try:
            db.close()
        except Exception:
            pass
