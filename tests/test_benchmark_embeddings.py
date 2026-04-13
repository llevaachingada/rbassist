import argparse
import json
import os
import pathlib
import tempfile
import unittest

import numpy as np

from scripts import benchmark_embeddings as bench


class BenchmarkEmbeddingTests(unittest.TestCase):
    def _fixture_meta(self, base: pathlib.Path) -> dict:
        emb = base / "emb"
        emb.mkdir()
        tracks = {}
        vectors = {
            "seed": np.array([1.0, 0.0] + [0.0] * (bench.DIM - 2), dtype=np.float32),
            "a": np.array([0.9, 0.1] + [0.0] * (bench.DIM - 2), dtype=np.float32),
            "b": np.array([0.0, 1.0] + [0.0] * (bench.DIM - 2), dtype=np.float32),
        }
        for name, vec in vectors.items():
            path = emb / f"{name}.npy"
            np.save(path, vec)
            tracks[name] = {
                "artist": name,
                "title": name,
                "bpm": 128.0,
                "key": "8A",
                "mytags": ["Warm-up"],
                "embedding": str(path),
            }
        return {"tracks": tracks}

    def test_benchmark_runs_row_abc(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            meta = self._fixture_meta(pathlib.Path(td))
            result = bench.run_benchmark(
                meta,
                ["seed"],
                rows=["A", "B", "C"],
                top=2,
                candidate_pool=2,
                allow_section_rows=False,
                allow_layer_mix_rows=False,
            )

        self.assertEqual(set(result["rows"]), {"A", "B", "C"})
        self.assertIn("camelot_compat_rate", result["rows"]["A"])
        self.assertEqual(result["coverage"]["primary_embedding_count"], 3)
        self.assertEqual(result["coverage"]["section_embedding_complete_count"], 0)
        self.assertEqual(result["coverage"]["layer_mix_embedding_count"], 0)

    def test_benchmark_output_json_valid_and_compare_deltas(self) -> None:
        current = {
            "rows": {
                "A": {"camelot_compat_rate": 0.75, "bpm_compat_rate": 1.0},
            }
        }
        prior = {
            "rows": {
                "A": {"camelot_compat_rate": 0.50, "bpm_compat_rate": 1.0},
            }
        }
        deltas = bench.compute_deltas(current, prior)
        self.assertAlmostEqual(deltas["A"]["camelot_compat_rate"], 0.25)
        json.dumps({"rows": current["rows"], "deltas_vs_prior": deltas})

    def test_benchmark_skips_section_rows_without_flag(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            meta = self._fixture_meta(pathlib.Path(td))
            result = bench.run_benchmark(
                meta,
                ["seed"],
                rows=["D"],
                top=2,
                candidate_pool=2,
                allow_section_rows=False,
                allow_layer_mix_rows=False,
            )

        self.assertTrue(result["rows"]["D"]["skipped"])

    def test_embedding_coverage_counts_section_and_case_collisions(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            emb = base / "emb"
            emb.mkdir()
            paths = {}
            for stem in ("track", "track_intro", "track_core", "track_late", "track_layer"):
                path = emb / f"{stem}.npy"
                np.save(path, np.ones(bench.DIM, dtype=np.float32))
                paths[stem] = path
            meta = {
                "tracks": {
                    "C:/Music/Track.flac": {
                        "embedding": str(paths["track"]),
                        "embedding_intro": str(paths["track_intro"]),
                        "embedding_core": str(paths["track_core"]),
                        "embedding_late": str(paths["track_late"]),
                        "embedding_layer_mix": str(paths["track_layer"]),
                    },
                    "c:/music/track.flac": {"embedding": str(paths["track"])},
                }
            }

            coverage = bench.embedding_coverage(meta)

        self.assertEqual(coverage["tracks_total"], 2)
        self.assertEqual(coverage["primary_embedding_count"], 2)
        self.assertEqual(coverage["section_embedding_complete_count"], 1)
        self.assertEqual(coverage["section_embedding_missing_count"], 1)
        self.assertEqual(coverage["layer_mix_embedding_count"], 1)
        self.assertEqual(coverage["case_collision_key_count"], 1)
        self.assertEqual(coverage["case_collision_extra_row_count"], 1)

    def test_explicit_seeds_do_not_create_default_config(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cwd = pathlib.Path.cwd()
            os.chdir(td)
            try:
                seeds = bench._load_seed_list(argparse.Namespace(seeds=["seed"], seeds_file=None))
                self.assertEqual(seeds, ["seed"])
                self.assertFalse(pathlib.Path("config/benchmark_seeds.txt").exists())
            finally:
                os.chdir(cwd)


if __name__ == "__main__":
    unittest.main()
