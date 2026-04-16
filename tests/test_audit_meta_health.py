import pathlib
import tempfile
import unittest

from rbassist import health


class AuditMetaHealthTests(unittest.TestCase):
    def test_audit_counts_missing_and_stale(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            music_root = base / "Music"
            music_root.mkdir()
            good_track = music_root / "good.mp3"
            good_track.write_text("x", encoding="utf-8")
            emb = base / "emb.npy"
            emb.write_text("x", encoding="utf-8")
            outside_stale = base / "Elsewhere" / "missing.mp3"
            outside_stale.parent.mkdir(parents=True)
            inside_stale = music_root / "missing_inside.mp3"
            meta = {
                "tracks": {
                    str(good_track): {"embedding": str(emb), "bpm": 128, "key": "8A", "cues": [{"name": "A"}], "mytags": ["x"]},
                    str(outside_stale): {},
                    str(inside_stale): {"title": "Inside"},
                    "bare-name.mp3": {},
                    str(base / "__MACOSX" / "._junk.mp3"): {},
                }
            }
            report = health.audit_meta_health(repo=base, meta=meta, roots=[str(music_root)])
            self.assertEqual(report["counts"]["tracks_total"], 5)
            self.assertEqual(report["counts"]["embedding_ok"], 1)
            self.assertGreaterEqual(report["counts"]["missing_embedding_ref"], 4)
            self.assertGreaterEqual(report["counts"]["stale_track_path_total"], 4)
            self.assertEqual(report["counts"]["stale_inside_root_total"], 1)
            self.assertEqual(report["counts"]["stale_archive_remove_total"], 2)
            self.assertEqual(report["counts"]["stale_keep_review_total"], 0)


if __name__ == "__main__":
    unittest.main()
