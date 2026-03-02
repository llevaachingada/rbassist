import json
import pathlib
import tempfile
import unittest
from unittest import mock

from rbassist import health


class ApplyStaleMetaCleanupTests(unittest.TestCase):
    def test_apply_archives_only_archive_remove_rows(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            (base / "data").mkdir()
            music_root = base / "Music"
            music_root.mkdir()

            inside_stale = music_root / "missing_inside.mp3"
            outside_stale = base / "Elsewhere" / "missing_outside.mp3"
            outside_stale.parent.mkdir(parents=True)
            inside_live = music_root / "keep_live.mp3"
            inside_live.write_text("x", encoding="utf-8")

            meta = {
                "tracks": {
                    str(inside_stale): {"title": "Inside"},
                    str(outside_stale): {},
                    str(inside_live): {"bpm": 126.0},
                }
            }
            (base / "data" / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
            saved = {}
            with mock.patch.object(health, "save_meta", side_effect=lambda payload: saved.update(payload)):
                report = health.apply_stale_meta_cleanup(
                    repo=base,
                    roots=[str(music_root)],
                    apply_changes=True,
                    meta=meta,
                )
            self.assertTrue(report["applied"])
            self.assertTrue(pathlib.Path(report["backup_path"]).exists())
            self.assertTrue(pathlib.Path(report["archive_path"]).exists())
            self.assertEqual(report["removed_paths"], [str(outside_stale)])
            self.assertIn(str(inside_stale), saved["tracks"])
            self.assertIn(str(inside_live), saved["tracks"])
            self.assertNotIn(str(outside_stale), saved["tracks"])
            archive_lines = pathlib.Path(report["archive_path"]).read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(archive_lines), 1)
            archived = json.loads(archive_lines[0])
            self.assertEqual(archived["path"], str(outside_stale))
            self.assertEqual(archived["suggested_action"], "archive_remove")


if __name__ == "__main__":
    unittest.main()
