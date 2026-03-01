import pathlib
import tempfile
import unittest

from rbassist import health


class AuditMetaHealthTests(unittest.TestCase):
    def test_audit_counts_missing_and_stale(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            good_track = base / "good.mp3"
            good_track.write_text("x", encoding="utf-8")
            emb = base / "emb.npy"
            emb.write_text("x", encoding="utf-8")
            meta = {
                "tracks": {
                    str(good_track): {"embedding": str(emb), "bpm": 128, "key": "8A", "cues": [{"name": "A"}], "mytags": ["x"]},
                    str(base / "missing.mp3"): {},
                    "bare-name.mp3": {},
                    str(base / "__MACOSX" / "._junk.mp3"): {},
                }
            }
            report = health.audit_meta_health(repo=base, meta=meta)
            self.assertEqual(report["counts"]["tracks_total"], 4)
            self.assertEqual(report["counts"]["embedding_ok"], 1)
            self.assertGreaterEqual(report["counts"]["missing_embedding_ref"], 3)
            self.assertGreaterEqual(report["counts"]["stale_track_path_total"], 3)


if __name__ == "__main__":
    unittest.main()
