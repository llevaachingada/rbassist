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

    def _add_section_sidecars(self, meta: dict, base: pathlib.Path, names: list[str]) -> None:
        emb = base / "emb"
        for name in names:
            for suffix in ("intro", "core", "late"):
                path = emb / f"{name}_{suffix}.npy"
                np.save(path, np.ones(bench.DIM, dtype=np.float32))
                meta["tracks"][name][f"embedding_{suffix}"] = str(path)

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
        self.assertIn("C", result["listening_review"])
        self.assertEqual(result["listening_review"]["C"][0]["tracks"][0]["rank"], 1)

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

    def test_listening_overlap_reports_changes_vs_baseline_row_c(self) -> None:
        review = {
            "C": [{"seed_path": "seed", "tracks": [{"path": "a"}, {"path": "b"}]}],
            "G": [{"seed_path": "seed", "tracks": [{"path": "b"}, {"path": "c"}]}],
        }

        overlap = bench.compute_listening_overlap(review)

        self.assertTrue(overlap["_baseline"]["available"])
        self.assertEqual(overlap["G"][0]["overlap_with_C_count"], 1)
        self.assertTrue(overlap["G"][0]["baseline_available"])
        self.assertEqual(overlap["G"][0]["new_vs_C"], ["c"])
        self.assertEqual(overlap["G"][0]["dropped_from_C"], ["a"])

    def test_listening_overlap_marks_missing_baseline(self) -> None:
        review = {
            "G": [{"seed_path": "seed", "tracks": [{"path": "b"}, {"path": "c"}]}],
        }

        overlap = bench.compute_listening_overlap(review)

        self.assertFalse(overlap["_baseline"]["available"])
        self.assertEqual(overlap["_baseline"]["reason"], "row C baseline unavailable")
        self.assertNotIn("G", overlap)

    def test_main_writes_listening_review_json(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            meta = self._fixture_meta(base)
            meta_path = base / "meta.json"
            out_path = base / "benchmark.json"
            review_path = base / "review.json"
            meta_path.write_text(json.dumps(meta), encoding="utf-8")

            exit_code = bench.main(
                [
                    "--meta",
                    str(meta_path),
                    "--seeds",
                    "seed",
                    "--rows",
                    "C",
                    "--top",
                    "1",
                    "--candidate-pool",
                    "2",
                    "--out",
                    str(out_path),
                    "--listening-review-out",
                    str(review_path),
                ]
            )

            self.assertEqual(exit_code, 0)
            self.assertTrue(out_path.exists())
            self.assertTrue(review_path.exists())
            review = json.loads(review_path.read_text(encoding="utf-8"))
            self.assertIn("C", review["rows"])
            self.assertTrue(review["overlap_vs_C"]["_baseline"]["available"])

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

    def test_benchmark_skips_section_rows_when_section_sidecars_unusable(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            meta = self._fixture_meta(pathlib.Path(td))
            result = bench.run_benchmark(
                meta,
                ["seed"],
                rows=["D"],
                top=2,
                candidate_pool=2,
                allow_section_rows=True,
                allow_layer_mix_rows=False,
            )

        self.assertTrue(result["rows"]["D"]["skipped"])
        self.assertEqual(
            result["rows"]["D"]["reason"],
            "section rows require usable seed late + candidate intro sidecars",
        )
        self.assertEqual(result["rows"]["D"]["transition_pairs_scored"], 0)
        self.assertEqual(result["rows"]["D"]["section_scores_enabled"], False)

    def test_benchmark_section_row_reports_diagnostics_when_applied(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            meta = self._fixture_meta(base)
            self._add_section_sidecars(meta, base, ["seed", "a", "b"])
            result = bench.run_benchmark(
                meta,
                ["seed"],
                rows=["D"],
                top=2,
                candidate_pool=2,
                allow_section_rows=True,
                allow_layer_mix_rows=False,
            )

        row = result["rows"]["D"]
        self.assertFalse(row.get("skipped", False))
        self.assertEqual(row["section_scores_requested"], True)
        self.assertEqual(row["section_scores_enabled"], True)
        self.assertEqual(row["seed_section_late_count"], 1)
        self.assertEqual(row["selected_candidate_intro_count"], 2)
        self.assertEqual(row["transition_pairs_scored"], 2)
        self.assertIsNotNone(row["transition_score_mean"])

    def test_benchmark_harmonic_and_learned_rows_are_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            meta = self._fixture_meta(pathlib.Path(td))

            result = bench.run_benchmark(
                meta,
                ["seed"],
                rows=["G", "H"],
                top=2,
                candidate_pool=2,
                allow_section_rows=False,
                allow_layer_mix_rows=False,
                learned_similarity_model=str(pathlib.Path(td) / "missing.pt"),
            )

        self.assertFalse(result["rows"]["G"].get("skipped", False))
        self.assertTrue(result["rows"]["H"]["skipped"])

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
