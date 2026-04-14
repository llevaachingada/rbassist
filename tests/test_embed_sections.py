import pathlib
import json
import tempfile
import unittest
from unittest import mock

import numpy as np

from rbassist import embed as embed_mod


class _SectionFakeEmbedder:
    def __init__(self, model_name: str = "", device: str | None = None):
        self.device = "cpu"

    def encode_array(self, y: np.ndarray, sr: int) -> np.ndarray:
        return np.full(8, float(np.mean(y)), dtype=np.float32)

    def encode_batch(self, items):
        return [self.encode_array(y, sr) for y, sr in items]

    def encode_section_vectors(self, segments):
        return self.encode_batch(segments)


class _CountingSectionEmbedder(_SectionFakeEmbedder):
    def __init__(self, model_name: str = "", device: str | None = None):
        super().__init__(model_name=model_name, device=device)
        self.batch_calls = 0

    def encode_batch(self, items):
        self.batch_calls += 1
        return super().encode_batch(items)


class EmbedSectionTests(unittest.TestCase):
    def test_section_vectors_have_correct_shape(self) -> None:
        y = np.ones(160 * 10, dtype=np.float32)
        windows = [(0.0, 10.0), (50.0, 110.0), (145.0, 155.0)]
        result = embed_mod.embed_with_section_vectors(y, 10, _SectionFakeEmbedder(), windows=windows)

        self.assertEqual(set(result), {"intro", "core", "late", "combined"})
        for vec in result.values():
            self.assertEqual(vec.shape, (8,))
            self.assertEqual(vec.dtype, np.float32)

    def test_section_combined_matches_existing(self) -> None:
        y = np.linspace(0.0, 1.0, 160 * 10, dtype=np.float32)
        windows = [(0.0, 10.0), (50.0, 110.0), (145.0, 155.0)]
        embedder = _SectionFakeEmbedder()

        sections = embed_mod.embed_with_section_vectors(y, 10, embedder, windows=windows)
        baseline = embed_mod.embed_with_default_windows(y, 10, embedder, windows=windows)

        np.testing.assert_allclose(sections["combined"], baseline, rtol=0.0, atol=1e-6)

    def test_short_track_all_sections_equal(self) -> None:
        y = np.ones(20 * 10, dtype=np.float32)
        result = embed_mod.embed_with_section_vectors(y, 10, _SectionFakeEmbedder(), windows=[(0.0, 20.0)])

        np.testing.assert_array_equal(result["intro"], result["core"])
        np.testing.assert_array_equal(result["core"], result["late"])
        np.testing.assert_array_equal(result["late"], result["combined"])

    def test_build_embeddings_writes_additive_section_meta_and_float16_files(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            emb_dir = base / "embeddings"
            checkpoint = base / "checkpoint.json"
            track = str(base / "Artist - Title.wav")
            meta_store: dict = {"tracks": {track: {"embedding": "preexisting.npy"}}}

            def fake_load_meta() -> dict:
                return meta_store

            def fake_save_meta(meta: dict) -> None:
                saved = json.loads(json.dumps(meta))
                meta_store.clear()
                meta_store.update(saved)

            with (
                mock.patch.object(embed_mod, "MertEmbedder", _SectionFakeEmbedder),
                mock.patch.object(embed_mod, "load_meta", side_effect=fake_load_meta),
                mock.patch.object(embed_mod, "save_meta", side_effect=fake_save_meta),
                mock.patch.object(embed_mod, "mode_for_path", return_value="baseline"),
                mock.patch.object(embed_mod, "EMB", emb_dir),
                mock.patch.object(embed_mod.librosa, "load", return_value=(np.ones(160 * 10, dtype=np.float32), 10)),
            ):
                embed_mod.build_embeddings(
                    [track],
                    duration_s=0,
                    num_workers=0,
                    checkpoint_file=str(checkpoint),
                    section_embed=True,
                )

            info = meta_store["tracks"][track]
            self.assertIn("embedding_intro", info)
            self.assertIn("embedding_core", info)
            self.assertIn("embedding_late", info)
            self.assertEqual(info["embedding_version"], "v2_section")
            self.assertTrue(info["embedding_intro"].endswith("_intro.npy"))
            self.assertTrue(info["embedding_core"].endswith("_core.npy"))
            self.assertTrue(info["embedding_late"].endswith("_late.npy"))
            for key in ("embedding_intro", "embedding_core", "embedding_late"):
                arr = np.load(info[key])
                self.assertEqual(arr.dtype, np.float16)

    def test_build_embeddings_backfills_missing_sidecar_without_overwriting_existing_sidecars(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            emb_dir = base / "embeddings"
            checkpoint = base / "checkpoint.json"
            emb_dir.mkdir(parents=True, exist_ok=True)
            track = str(base / "Artist - Title.wav")

            primary = emb_dir / "Artist - Title.npy"
            intro = emb_dir / "Artist - Title_intro.npy"
            core = emb_dir / "Artist - Title_core.npy"
            np.save(primary, np.full(8, 7.0, dtype=np.float16))
            np.save(intro, np.full(8, 9.0, dtype=np.float16))
            np.save(core, np.full(8, 11.0, dtype=np.float16))

            meta_store: dict = {
                "tracks": {
                    track: {
                        "embedding": str(primary),
                        "embedding_intro": str(intro),
                        "embedding_core": str(core),
                    }
                }
            }

            def fake_load_meta() -> dict:
                return meta_store

            def fake_save_meta(meta: dict) -> None:
                saved = json.loads(json.dumps(meta))
                meta_store.clear()
                meta_store.update(saved)

            with (
                mock.patch.object(embed_mod, "MertEmbedder", _SectionFakeEmbedder),
                mock.patch.object(embed_mod, "load_meta", side_effect=fake_load_meta),
                mock.patch.object(embed_mod, "save_meta", side_effect=fake_save_meta),
                mock.patch.object(embed_mod, "mode_for_path", return_value="baseline"),
                mock.patch.object(embed_mod, "EMB", emb_dir),
                mock.patch.object(embed_mod.librosa, "load", return_value=(np.ones(160 * 10, dtype=np.float32), 10)),
            ):
                embed_mod.build_embeddings(
                    [track],
                    duration_s=0,
                    num_workers=0,
                    checkpoint_file=str(checkpoint),
                    section_embed=True,
                    resume=True,
                )

            info = meta_store["tracks"][track]
            self.assertIn("embedding_late", info)
            self.assertTrue(info["embedding_intro"].endswith("_intro.npy"))
            self.assertTrue(info["embedding_core"].endswith("_core.npy"))
            self.assertTrue(info["embedding_late"].endswith("_late.npy"))
            np.testing.assert_array_equal(np.load(info["embedding_intro"]), np.full(8, 9.0, dtype=np.float16))
            np.testing.assert_array_equal(np.load(info["embedding_core"]), np.full(8, 11.0, dtype=np.float16))
            late = np.load(info["embedding_late"])
            self.assertEqual(late.dtype, np.float16)
            np.testing.assert_array_equal(late, np.ones(8, dtype=np.float16))

    def test_section_embed_common_path_uses_single_batch_pass(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            emb_dir = base / "embeddings"
            checkpoint = base / "checkpoint.json"
            track = str(base / "Artist - Title.wav")
            meta_store: dict = {"tracks": {}}
            holder: dict[str, _CountingSectionEmbedder] = {}

            def embedder_factory(model_name: str = "", device: str | None = None):
                emb = _CountingSectionEmbedder(model_name=model_name, device=device)
                holder["embedder"] = emb
                return emb

            def fake_load_meta() -> dict:
                return meta_store

            def fake_save_meta(meta: dict) -> None:
                saved = json.loads(json.dumps(meta))
                meta_store.clear()
                meta_store.update(saved)

            with (
                mock.patch.object(embed_mod, "MertEmbedder", side_effect=embedder_factory),
                mock.patch.object(embed_mod, "load_meta", side_effect=fake_load_meta),
                mock.patch.object(embed_mod, "save_meta", side_effect=fake_save_meta),
                mock.patch.object(embed_mod, "mode_for_path", return_value="baseline"),
                mock.patch.object(embed_mod, "EMB", emb_dir),
                mock.patch.object(embed_mod.librosa, "load", return_value=(np.ones(160 * 10, dtype=np.float32), 10)),
            ):
                embed_mod.build_embeddings(
                    [track],
                    duration_s=0,
                    num_workers=0,
                    checkpoint_file=str(checkpoint),
                    section_embed=True,
                )

            self.assertEqual(holder["embedder"].batch_calls, 1)

    def test_build_embeddings_writes_opt_in_profile_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            emb_dir = base / "embeddings"
            checkpoint = base / "checkpoint.json"
            profile = base / "embed_profile.jsonl"
            track = str(base / "Artist - Title.wav")
            meta_store: dict = {"tracks": {}}

            def fake_load_meta() -> dict:
                return meta_store

            def fake_save_meta(meta: dict) -> None:
                saved = json.loads(json.dumps(meta))
                meta_store.clear()
                meta_store.update(saved)

            with (
                mock.patch.object(embed_mod, "MertEmbedder", _SectionFakeEmbedder),
                mock.patch.object(embed_mod, "load_meta", side_effect=fake_load_meta),
                mock.patch.object(embed_mod, "save_meta", side_effect=fake_save_meta),
                mock.patch.object(embed_mod, "mode_for_path", return_value="baseline"),
                mock.patch.object(embed_mod, "EMB", emb_dir),
                mock.patch.object(embed_mod.librosa, "load", return_value=(np.ones(20, dtype=np.float32), 10)),
            ):
                embed_mod.build_embeddings(
                    [track],
                    duration_s=1,
                    num_workers=0,
                    checkpoint_file=str(checkpoint),
                    checkpoint_every=1,
                    section_embed=True,
                    profile_embed_out=str(profile),
                )

            rows = [json.loads(line) for line in profile.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(row["event"], "track")
            self.assertEqual(row["path"], track)
            self.assertEqual(row["source_sample_rate"], 10)
            self.assertEqual(row["decoded_samples"], 20)
            self.assertEqual(row["trimmed_samples"], 10)
            self.assertEqual(row["duration_cap_s"], 1)
            self.assertEqual(row["mert_flattened_item_count"], 1)
            self.assertEqual(row["actual_mert_batch_size"], 1)
            self.assertTrue(row["section_embed"])
            self.assertFalse(row["layer_mix"])
            self.assertFalse(row["timbre"])
            for key in ("load_audio_s", "mert_encode_s", "save_s", "checkpoint_write_s", "meta_write_s"):
                self.assertIn(key, row)
                self.assertGreaterEqual(row[key], 0.0)


if __name__ == "__main__":
    unittest.main()
