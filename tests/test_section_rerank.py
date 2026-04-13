import json
import pathlib
import tempfile
import unittest
from unittest import mock

import numpy as np

from rbassist import playlist_expand as pe
from rbassist import recommend


class _FakeRecommendIndex:
    def __init__(self, space=None, dim=None):
        self.space = space
        self.dim = dim

    def load_index(self, path):
        self.path = path

    def set_ef(self, value):
        self.ef = value

    def knn_query(self, vec, k):
        return np.array([[0, 1, 2]], dtype=np.int64), np.array([[0.0, 0.2, 0.1]], dtype=np.float32)


class SectionRerankTests(unittest.TestCase):
    def test_load_section_embeddings_missing_is_graceful(self) -> None:
        loaded = recommend.load_section_embeddings({})
        self.assertEqual(loaded, {"intro": None, "core": None, "late": None})

    def test_recommend_without_flag_unchanged_order(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            idx = base / "index"
            idx.mkdir()
            (idx / "hnsw.idx").write_text("fake", encoding="utf-8")
            paths = ["seed", "candidate_a", "candidate_b"]
            (idx / "paths.json").write_text(json.dumps(paths), encoding="utf-8")
            emb = base / "emb"
            emb.mkdir()
            for name in paths:
                np.save(emb / f"{name}.npy", np.ones(recommend.DIM, dtype=np.float32))
            meta = {
                "tracks": {
                    "seed": {"embedding": str(emb / "seed.npy")},
                    "candidate_a": {"embedding": str(emb / "candidate_a.npy")},
                    "candidate_b": {"embedding": str(emb / "candidate_b.npy")},
                }
            }

            with (
                mock.patch.object(recommend, "IDX", idx),
                mock.patch.object(recommend, "load_meta", return_value=meta),
                mock.patch.object(recommend.hnswlib, "Index", side_effect=lambda *args, **kwargs: _FakeRecommendIndex(*args, **kwargs)),
            ):
                recommend.recommend("seed", top=2, camelot_neighbors=False, weights={"transition": 1.0}, use_section_scores=False)

    def test_playlist_transition_score_range(self) -> None:
        seed_late = np.array([1.0, 0.0], dtype=np.float32)
        cand_intro = np.array([1.0, 1.0], dtype=np.float32)
        candidate = pe.PreparedCandidate(
            path="candidate",
            vector=np.array([1.0, 0.0], dtype=np.float32),
            section_intro=cand_intro,
        )
        controls = pe.PlaylistExpansionControls(
            weights=pe.PlaylistExpansionWeights(transition_outro_to_intro=1.0),
            use_section_scores=True,
        ).normalized()

        scores = pe._compute_component_scores(
            candidate,
            {
                "seed_vectors": [np.array([1.0, 0.0], dtype=np.float32)],
                "seed_centroid": np.array([1.0, 0.0], dtype=np.float32),
                "seed_late_centroid": seed_late,
                "seed_core_tags": set(),
                "seed_keys": [],
                "seed_bpm_median": None,
            },
            controls,
        )

        self.assertGreaterEqual(scores["transition_score"], 0.0)
        self.assertLessEqual(scores["transition_score"], 1.0)
        self.assertEqual(scores["transition_outro_to_intro"], scores["transition_score"])

    def test_playlist_transition_missing_section_is_zero(self) -> None:
        candidate = pe.PreparedCandidate(path="candidate", vector=np.array([1.0, 0.0], dtype=np.float32))
        scores = pe._compute_component_scores(
            candidate,
            {
                "seed_vectors": [np.array([1.0, 0.0], dtype=np.float32)],
                "seed_centroid": np.array([1.0, 0.0], dtype=np.float32),
                "seed_late_centroid": np.array([1.0, 0.0], dtype=np.float32),
                "seed_core_tags": set(),
                "seed_keys": [],
                "seed_bpm_median": None,
            },
            pe.PlaylistExpansionControls(use_section_scores=True).normalized(),
        )
        self.assertEqual(scores["transition_outro_to_intro"], 0.0)
        self.assertNotIn("transition_score", scores)


if __name__ == "__main__":
    unittest.main()
