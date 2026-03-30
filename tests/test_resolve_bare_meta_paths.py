import pathlib
import tempfile
import unittest
from unittest import mock

from rbassist import health


class ResolveBareMetaPathsTests(unittest.TestCase):
    def test_resolves_high_confidence_and_preserves_ambiguous(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            music = base / "Music"
            music.mkdir()
            unique_target = music / "Artist - Unique.mp3"
            unique_target.write_text("u", encoding="utf-8")
            dup_a = music / "crate_a" / "Artist - Duplicate.mp3"
            dup_b = music / "crate_b" / "Artist - Duplicate.mp3"
            dup_a.parent.mkdir(parents=True)
            dup_b.parent.mkdir(parents=True)
            dup_a.write_text("a", encoding="utf-8")
            dup_b.write_text("b", encoding="utf-8")
            meta = {
                "tracks": {
                    "Artist - Unique.mp3": {"mytags": ["alpha"], "title": "Unique"},
                    "Artist - Duplicate.mp3": {"mytags": ["beta"]},
                    str(unique_target): {"embedding": "emb.npy", "bpm": 128.0},
                }
            }
            report = health.resolve_bare_meta_paths(repo=base, roots=[str(music)], apply_changes=False, meta=meta)
            entries = {item["source_bare_path"]: item for item in report["entries"]}
            self.assertEqual(report["counts"]["high_confidence_unique_total"], 1)
            self.assertEqual(report["counts"]["ambiguous_matches_total"], 1)
            self.assertEqual(report["counts"]["matched_existing_absolute_total"], 1)
            self.assertEqual(entries["Artist - Unique.mp3"]["classification"], "high_confidence_unique")
            self.assertEqual(entries["Artist - Duplicate.mp3"]["classification"], "ambiguous")
            self.assertTrue(entries["Artist - Unique.mp3"]["merged_into_existing"])

    def test_medium_confidence_unique_stays_review_only(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            music = base / "Music"
            music.mkdir()
            target = music / "Artist - Song.mp3"
            target.write_text("x", encoding="utf-8")
            meta = {
                "tracks": {
                    "Artist Song Edit.mp3": {"title": "Song Edit"},
                }
            }
            report = health.resolve_bare_meta_paths(repo=base, roots=[str(music)], apply_changes=False, meta=meta)
            entry = report["entries"][0]
            self.assertEqual(entry["classification"], "medium_confidence_unique")
            self.assertEqual(entry["action_taken"], "review_only")
            self.assertEqual(report["counts"]["medium_confidence_unique_total"], 1)

    def test_apply_merges_only_high_confidence_entries(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            music = base / "Music"
            music.mkdir()
            target = music / "Artist - Song.mp3"
            target.write_text("x", encoding="utf-8")
            review_only_target = music / "Artist - Other.mp3"
            review_only_target.write_text("y", encoding="utf-8")
            meta = {
                "tracks": {
                    "Artist - Song.mp3": {"mytags": ["alpha"], "title": "Song"},
                    "Artist Other Edit.mp3": {"mytags": ["beta"], "title": "Other Edit"},
                    str(target): {"embedding": "emb.npy", "bpm": 126.0},
                }
            }
            saved = {}
            with mock.patch.object(health, "save_meta", side_effect=lambda payload: saved.update(payload)):
                report = health.resolve_bare_meta_paths(
                    repo=base,
                    roots=[str(music)],
                    apply_changes=True,
                    meta=meta,
                )
            self.assertTrue(report["applied"])
            self.assertIn(str(target), saved["tracks"])
            self.assertIn("Artist Other Edit.mp3", saved["tracks"])
            merged = saved["tracks"][str(target)]
            self.assertEqual(merged["bpm"], 126.0)
            self.assertEqual(sorted(merged["mytags"]), ["alpha"])
            self.assertNotIn(str(review_only_target), saved["tracks"])


if __name__ == "__main__":
    unittest.main()
