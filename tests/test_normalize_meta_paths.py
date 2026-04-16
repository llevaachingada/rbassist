import pathlib
import tempfile
import unittest
from unittest import mock

from rbassist import health


class NormalizeMetaPathsTests(unittest.TestCase):
    def test_rewrite_prefix_and_preserve_bare_review(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            meta = {"tracks": {"C:/Users/TTSAdmin/Music/test.mp3": {"embedding": "x.npy"}, "bare.mp3": {}}}
            saved = {}
            with mock.patch.object(health, "save_meta", side_effect=lambda payload: saved.update(payload)):
                report = health.normalize_meta_paths(
                    repo=base,
                    rewrite_from=["C:/Users/TTSAdmin/Music"],
                    rewrite_to=["C:/Users/hunte/Music"],
                    drop_junk=False,
                    apply_changes=True,
                    meta=meta,
                )
            self.assertTrue(report["applied"])
            self.assertTrue(any("Users" in key for key in saved["tracks"].keys()))
            self.assertIn("bare.mp3", saved["tracks"])

    def test_apply_is_blocked_when_collisions_exist(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            meta = {
                "tracks": {
                    "C:/Users/hunte/Music/test.mp3": {},
                    "C:\\Users\\hunte\\Music\\test.mp3": {},
                }
            }
            with mock.patch.object(health, "save_meta") as save_meta:
                report = health.normalize_meta_paths(
                    repo=base,
                    rewrite_from=[],
                    rewrite_to=[],
                    drop_junk=False,
                    apply_changes=True,
                    meta=meta,
                )
            self.assertFalse(report["applied"])
            self.assertEqual(report["blocked_reason"], "collisions_detected")
            save_meta.assert_not_called()

    def test_resolve_collisions_merges_duplicate_variants(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            actual_track = base / "crate" / "song.mp3"
            actual_track.parent.mkdir(parents=True)
            actual_track.write_text("x", encoding="utf-8")
            posix_variant = str(actual_track).replace("\\", "/")
            meta = {
                "tracks": {
                    str(actual_track): {
                        "embedding": "emb.npy",
                        "bpm": 128.0,
                        "key": "8A",
                        "cues": [{"name": "A"}],
                        "mytags": ["alpha"],
                        "artist": "Artist",
                    },
                    posix_variant: {
                        "title": "Song",
                        "mytags": ["beta"],
                    },
                }
            }
            saved = {}
            with mock.patch.object(health, "save_meta", side_effect=lambda payload: saved.update(payload)):
                report = health.normalize_meta_paths(
                    repo=base,
                    rewrite_from=[],
                    rewrite_to=[],
                    drop_junk=False,
                    resolve_collisions=True,
                    apply_changes=True,
                    meta=meta,
                )
            self.assertTrue(report["applied"])
            self.assertEqual(report["counts"]["resolved_collision_groups_total"], 1)
            self.assertEqual(len(saved["tracks"]), 1)
            merged = next(iter(saved["tracks"].values()))
            self.assertEqual(sorted(merged["mytags"]), ["alpha", "beta"])
            self.assertEqual(merged["bpm"], 128.0)
            self.assertEqual(merged["title"], "Song")


if __name__ == "__main__":
    unittest.main()
