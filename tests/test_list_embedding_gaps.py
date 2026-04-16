import pathlib
import tempfile
import unittest

from rbassist import health


class ListEmbeddingGapsTests(unittest.TestCase):
    def test_gap_scan_outputs_pending(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            repo = base / "repo"
            repo.mkdir()
            (repo / "data").mkdir()
            music = base / "music"
            music.mkdir()
            track_a = music / "a.mp3"
            track_b = music / "b.mp3"
            track_a.write_text("a", encoding="utf-8")
            track_b.write_text("b", encoding="utf-8")
            emb = repo / "data" / "embeddings" / "a.npy"
            emb.parent.mkdir(parents=True)
            emb.write_text("e", encoding="utf-8")
            meta = {"tracks": {str(track_a): {"embedding": str(emb)}}}
            report = health.list_embedding_gaps(
                repo=repo,
                roots=[str(music)],
                out_prefix="data/pending_embedding_paths.test",
                chunk_size=2,
                meta=meta,
            )
            self.assertEqual(report["counts"]["audio_files_scanned"], 2)
            self.assertEqual(report["counts"]["pending_embedding_total"], 1)
            txt = pathlib.Path(report["output_paths_file"]).read_text(encoding="utf-8")
            self.assertIn(str(track_b), txt)

    def test_gap_scan_respects_exclude_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            repo = base / "repo"
            repo.mkdir()
            (repo / "data").mkdir()
            music = base / "music"
            music.mkdir()
            keep = music / "keep.mp3"
            skip = music / "skip.mp3"
            keep.write_text("keep", encoding="utf-8")
            skip.write_text("skip", encoding="utf-8")
            exclude_file = base / "exclude.txt"
            exclude_file.write_text(str(skip) + "\n", encoding="utf-8")

            report = health.list_embedding_gaps(
                repo=repo,
                roots=[str(music)],
                exclude_file=str(exclude_file),
                out_prefix="data/pending_embedding_paths.exclude_test",
                chunk_size=10,
                meta={"tracks": {}},
            )

            self.assertEqual(report["counts"]["exclude_entries_total"], 1)
            self.assertEqual(report["counts"]["excluded_audio_files_total"], 1)
            self.assertEqual(report["counts"]["audio_files_scanned"], 1)
            self.assertEqual(report["counts"]["pending_embedding_total"], 1)
            txt = pathlib.Path(report["output_paths_file"]).read_text(encoding="utf-8")
            self.assertIn(str(keep), txt)
            self.assertNotIn(str(skip), txt)


if __name__ == "__main__":
    unittest.main()
