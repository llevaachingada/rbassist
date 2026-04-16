import pathlib
import tempfile
import unittest

from rbassist import health


class TriageStaleMetaPathsTests(unittest.TestCase):
    def test_classifies_archive_remove_and_rekordbox_and_inside_root(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            music_root = base / "Music"
            music_root.mkdir()
            inside_stale = music_root / "missing_inside.mp3"
            outside_stale = base / "Elsewhere" / "missing_outside.mp3"
            outside_stale.parent.mkdir(parents=True)
            outside_in_rekordbox = base / "Legacy" / "tracked_elsewhere.mp3"
            outside_in_rekordbox.parent.mkdir(parents=True)

            live_dup = music_root / "crate" / "same_name.mp3"
            live_dup.parent.mkdir(parents=True)
            live_dup.write_text("x", encoding="utf-8")
            stale_dup = base / "OldCopies" / "same_name.mp3"
            stale_dup.parent.mkdir(parents=True)

            meta = {
                "tracks": {
                    str(inside_stale): {"title": "Inside"},
                    str(outside_stale): {},
                    str(outside_in_rekordbox): {"mytags": ["legacy"]},
                    str(stale_dup): {"artist": "Artist"},
                    str(live_dup): {"embedding": "emb.npy", "bpm": 128},
                }
            }
            rekordbox_report = {
                "relink_suggestion_report": {
                    "suggestions": [
                        {"id": "42", "source_path": str(outside_in_rekordbox)},
                    ]
                }
            }
            report = health.triage_stale_meta_paths(
                repo=base,
                roots=[str(music_root)],
                meta=meta,
                rekordbox_report=rekordbox_report,
            )
            entries = {item["path"]: item for item in report["entries"]}
            self.assertEqual(entries[str(inside_stale)]["suggested_action"], "inside_root_relink_candidate")
            self.assertEqual(entries[str(outside_stale)]["suggested_action"], "archive_remove")
            self.assertEqual(entries[str(outside_in_rekordbox)]["suggested_action"], "outside_root_rekordbox_candidate")
            self.assertEqual(entries[str(stale_dup)]["suggested_action"], "duplicate_stale_candidate")
            self.assertEqual(report["counts"]["stale_archive_remove_total"], 1)
            self.assertEqual(report["counts"]["stale_inside_root_total"], 1)


if __name__ == "__main__":
    unittest.main()
