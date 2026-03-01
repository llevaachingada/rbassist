from __future__ import annotations

from rbassist.rekordbox_audit import CatalogRecord, find_name_duration_duplicates, suggest_relinks_for_rows


def _catalog(records: list[CatalogRecord]) -> dict:
    by_path = {record.path_key: record for record in records}
    by_basename = {}
    by_stem = {}
    for record in records:
        by_basename.setdefault(record.basename, []).append(record)
        by_stem.setdefault(record.stem_key, []).append(record)
    return {
        "records": records,
        "by_path": by_path,
        "by_basename": by_basename,
        "by_stem": by_stem,
    }


def test_duplicate_dry_run_groups_same_stem_and_duration() -> None:
    catalog = _catalog(
        [
            CatalogRecord(
                path=r"C:\Users\hunte\Music\A\Artist - Track.flac",
                path_key=r"c:/users/hunte/music/a/artist - track.flac",
                basename="artist - track.flac",
                stem_key="artist track",
                extension=".flac",
                size=1000,
                duration=245.1,
            ),
            CatalogRecord(
                path=r"C:\Users\hunte\Music\B\Artist - Track.mp3",
                path_key=r"c:/users/hunte/music/b/artist - track.mp3",
                basename="artist - track.mp3",
                stem_key="artist track",
                extension=".mp3",
                size=800,
                duration=244.6,
            ),
            CatalogRecord(
                path=r"C:\Users\hunte\Music\B\Artist - Something Else.mp3",
                path_key=r"c:/users/hunte/music/b/artist - something else.mp3",
                basename="artist - something else.mp3",
                stem_key="artist something else",
                extension=".mp3",
                size=700,
                duration=210.0,
            ),
        ]
    )
    report = find_name_duration_duplicates(catalog, duration_tolerance_s=2.0)
    assert report["counts"]["duplicate_groups_total"] == 1
    assert report["counts"]["same_name_different_type_groups_total"] == 1
    assert report["groups"][0]["keep"]["extension"] == ".flac"


def test_relink_suggestions_prefer_unique_inside_root_match() -> None:
    catalog = _catalog(
        [
            CatalogRecord(
                path=r"C:\Users\hunte\Music\BREAKS\Artist - Track.flac",
                path_key=r"c:/users/hunte/music/breaks/artist - track.flac",
                basename="artist - track.flac",
                stem_key="artist track",
                extension=".flac",
                size=1000,
                duration=245.1,
            ),
            CatalogRecord(
                path=r"C:\Users\hunte\Music\BREAKS\Artist - Track (Edit).mp3",
                path_key=r"c:/users/hunte/music/breaks/artist - track (edit).mp3",
                basename="artist - track (edit).mp3",
                stem_key="artist track edit",
                extension=".mp3",
                size=800,
                duration=230.0,
            ),
        ]
    )
    rows = [
        {
            "id": "1",
            "title": "Track",
            "artist": "Artist",
            "folder_path": r"C:\Users\hunte\Deezloader Music\Artist - Track.flac",
            "file_name": "Artist - Track.flac",
            "length": 245.0,
        }
    ]
    report = suggest_relinks_for_rows(
        rows,
        catalog,
        music_root=r"C:\Users\hunte\Music",
        duration_tolerance_s=2.0,
        top_candidates=3,
    )
    suggestion = report["relink_suggestions"][0]
    assert suggestion["classification"] == "high_confidence_unique"
    assert suggestion["best_candidate"]["path"] == r"C:\Users\hunte\Music\BREAKS\Artist - Track.flac"
