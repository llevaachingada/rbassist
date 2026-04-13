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


class _RecoveringCudaEmbedder:
    instance_count = 0

    def __init__(self, model_name: str = "", device: str | None = None):
        type(self).instance_count += 1
        self.instance_id = type(self).instance_count
        self.device = "cuda"

    def encode_array(self, y: np.ndarray, sr: int) -> np.ndarray:
        return np.ones(8, dtype=np.float32)

    def encode_batch(self, items):
        if self.instance_id == 1:
            raise embed_mod.torch.AcceleratorError("CUDA error: invalid program counter")
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

    def test_build_embeddings_recovers_from_cuda_accelerator_error(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            emb_dir = base / "embeddings"
            checkpoint = base / "embed_checkpoint.json"
            good = str(base / "good.wav")
            meta_store: dict = {"tracks": {}}

            def fake_load_meta() -> dict:
                return meta_store

            def fake_save_meta(meta: dict) -> None:
                meta_store.clear()
                meta_store.update(meta)

            def fake_librosa_load(path: str, sr=None, mono=True):
                return np.ones(24000, dtype=np.float32), 24000

            _RecoveringCudaEmbedder.instance_count = 0
            with mock.patch.object(embed_mod, "MertEmbedder", _RecoveringCudaEmbedder), \
                mock.patch.object(embed_mod, "load_meta", side_effect=fake_load_meta), \
                mock.patch.object(embed_mod, "save_meta", side_effect=fake_save_meta), \
                mock.patch.object(embed_mod, "mode_for_path", return_value="baseline"), \
                mock.patch.object(embed_mod, "EMB", emb_dir), \
                mock.patch.object(embed_mod.librosa, "load", side_effect=fake_librosa_load), \
                mock.patch.object(embed_mod.torch.cuda, "is_available", return_value=False):
                embed_mod.build_embeddings(
                    [good],
                    num_workers=0,
                    checkpoint_file=str(checkpoint),
                    checkpoint_every=1,
                )

            checkpoint_data = json.loads(checkpoint.read_text(encoding="utf-8"))
            self.assertIn(good, checkpoint_data.get("completed_paths", []))
            self.assertEqual(checkpoint_data.get("failed_paths", []), [])
            self.assertEqual(checkpoint_data.get("recovery", {}).get("cuda_retries"), 1)
            self.assertEqual(checkpoint_data.get("recovery", {}).get("cuda_retry_successes"), 1)

    def test_resume_backfills_sections_for_completed_track_with_existing_primary(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            emb_dir = base / "embeddings"
            checkpoint = base / "embed_checkpoint.json"
            emb_dir.mkdir(parents=True, exist_ok=True)
            track = str(base / "Artist - Title.wav")
            primary = emb_dir / "Artist - Title.npy"
            np.save(primary, np.full(8, 5.0, dtype=np.float16))
            checkpoint.write_text(
                json.dumps(
                    {
                        "completed_paths": [track],
                        "failed_paths": [],
                    }
                ),
                encoding="utf-8",
            )
            meta_store: dict = {"tracks": {track: {"embedding": str(primary)}}}
            load_calls: list[str] = []

            def fake_load_meta() -> dict:
                return meta_store

            def fake_save_meta(meta: dict) -> None:
                saved = json.loads(json.dumps(meta))
                meta_store.clear()
                meta_store.update(saved)

            def fake_librosa_load(path: str, sr=None, mono=True):
                load_calls.append(path)
                return np.ones(24000, dtype=np.float32), 24000

            with mock.patch.object(embed_mod, "MertEmbedder", _FakeEmbedder), \
                mock.patch.object(embed_mod, "load_meta", side_effect=fake_load_meta), \
                mock.patch.object(embed_mod, "save_meta", side_effect=fake_save_meta), \
                mock.patch.object(embed_mod, "mode_for_path", return_value="baseline"), \
                mock.patch.object(embed_mod, "EMB", emb_dir), \
                mock.patch.object(embed_mod.librosa, "load", side_effect=fake_librosa_load):
                embed_mod.build_embeddings(
                    [track],
                    num_workers=0,
                    checkpoint_file=str(checkpoint),
                    checkpoint_every=1,
                    resume=True,
                    section_embed=True,
                )

            info = meta_store["tracks"][track]
            self.assertEqual(load_calls, [track])
            self.assertEqual(info["embedding"], str(primary))
            self.assertIn("embedding_intro", info)
            self.assertIn("embedding_core", info)
            self.assertIn("embedding_late", info)
            self.assertTrue(info["embedding_intro"].endswith("_intro.npy"))
            self.assertTrue(info["embedding_core"].endswith("_core.npy"))
            self.assertTrue(info["embedding_late"].endswith("_late.npy"))


if __name__ == "__main__":
    unittest.main()
