import json
import pathlib
import tempfile
import unittest
from unittest import mock

import numpy as np

from rbassist import cli
from rbassist import embed as embed_mod


class _FakeEmbedder:
    def __init__(self, model_name: str = "", device: str | None = None):
        self.device = "cpu"

    def encode_array(self, y: np.ndarray, sr: int) -> np.ndarray:
        return np.ones(8, dtype=np.float32)

    def encode_batch(self, items):
        return [np.ones(8, dtype=np.float32) for _ in items]


class EmbedResumeTests(unittest.TestCase):
    def test_read_paths_file_supports_comments_quotes_and_relative(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            rel_dir = base / "crate"
            rel_dir.mkdir(parents=True, exist_ok=True)
            abs_path = str(base / "absolute.mp3")
            paths_file = base / "paths.txt"
            paths_file.write_text(
                "\n".join(
                    [
                        "# comment",
                        " ",
                        "crate",
                        "\"crate\"",
                        abs_path,
                    ]
                ),
                encoding="utf-8",
            )

            out = cli._read_paths_file(paths_file)
            self.assertEqual(out[0], str((base / "crate").resolve()))
            self.assertEqual(out[1], str((base / "crate").resolve()))
            self.assertEqual(out[2], abs_path)

    def test_build_embeddings_writes_checkpoint_and_resumes(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            emb_dir = base / "embeddings"
            checkpoint = base / "embed_checkpoint.json"
            good = str(base / "good.wav")
            bad = str(base / "bad.wav")
            meta_store: dict = {"tracks": {}}
            load_calls: list[str] = []

            def fake_load_meta() -> dict:
                return meta_store

            def fake_save_meta(meta: dict) -> None:
                meta_store.clear()
                meta_store.update(meta)

            def fake_librosa_load(path: str, sr=None, mono=True):
                load_calls.append(path)
                if path == bad:
                    raise RuntimeError("decode failed")
                return np.ones(24000, dtype=np.float32), 24000

            with mock.patch.object(embed_mod, "MertEmbedder", _FakeEmbedder), \
                mock.patch.object(embed_mod, "load_meta", side_effect=fake_load_meta), \
                mock.patch.object(embed_mod, "save_meta", side_effect=fake_save_meta), \
                mock.patch.object(embed_mod, "mode_for_path", return_value="baseline"), \
                mock.patch.object(embed_mod, "EMB", emb_dir), \
                mock.patch.object(embed_mod.librosa, "load", side_effect=fake_librosa_load):
                embed_mod.build_embeddings(
                    [good, bad],
                    num_workers=0,
                    checkpoint_file=str(checkpoint),
                    checkpoint_every=1,
                )

                self.assertTrue(checkpoint.exists())
                checkpoint_data = json.loads(checkpoint.read_text(encoding="utf-8"))
                self.assertIn(good, checkpoint_data.get("completed_paths", []))
                self.assertIn(bad, checkpoint_data.get("failed_paths", []))

                failed_log = pathlib.Path(checkpoint_data["failed_log"])
                self.assertTrue(failed_log.exists())
                lines = [line for line in failed_log.read_text(encoding="utf-8").splitlines() if line.strip()]
                self.assertTrue(lines)
                parsed = [json.loads(line) for line in lines]
                self.assertTrue(any(item.get("path") == bad for item in parsed))

                load_calls.clear()
                embed_mod.build_embeddings(
                    [good, bad],
                    num_workers=0,
                    checkpoint_file=str(checkpoint),
                    checkpoint_every=1,
                    resume=True,
                )
                self.assertEqual(load_calls, [bad])


if __name__ == "__main__":
    unittest.main()
