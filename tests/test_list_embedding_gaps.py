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


if __name__ == "__main__":
    unittest.main()
