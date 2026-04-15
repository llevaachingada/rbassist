from __future__ import annotations

import argparse
import json
import pathlib
import tempfile
import unittest
from unittest import mock

import numpy as np
import torch

from rbassist import recommend
from rbassist.similarity_head import SimilarityHead, pick_similarity_device, similarity_score
from scripts import train_similarity_head


class _FakeIndex:
    def load_index(self, path):
        self.path = path

    def set_ef(self, value):
        self.ef = value

    def knn_query(self, query, k):
        return np.array([[0, 1, 2]], dtype=np.int64), np.array([[0.0, 0.2, 0.1]], dtype=np.float32)


class _FakeLoadedHead:
    device = "cuda"
    path = pathlib.Path("data/models/similarity_head.pt")

    def __init__(self, tracks):
        self.tracks = tracks

    def score(self, left, right):
        for path, info in self.tracks.items():
            emb = np.load(info["embedding"])
            if np.allclose(right, emb):
                return 0.95 if path == "learned-high" else 0.05
        return 0.0


class SimilarityHeadTests(unittest.TestCase):
    def test_forward_pass_shape_and_range(self) -> None:
        model = SimilarityHead(embed_dim=4, hidden=8, bottleneck=4)
        model.eval()
        left = torch.ones((3, 4), dtype=torch.float32)
        right = torch.zeros((3, 4), dtype=torch.float32)

        out = model(left, right)

        self.assertEqual(tuple(out.shape), (3,))
        self.assertTrue(torch.all(out >= 0.0))
        self.assertTrue(torch.all(out <= 1.0))

    def test_similarity_score_handles_bad_shapes(self) -> None:
        model = SimilarityHead(embed_dim=4, hidden=8, bottleneck=4)
        model.eval()

        self.assertEqual(similarity_score(np.ones(4), np.ones(3), model, device="cpu"), 0.0)

    def test_cuda_is_default_when_available_else_cpu(self) -> None:
        with mock.patch.object(torch.cuda, "is_available", return_value=True):
            self.assertEqual(pick_similarity_device(None), "cuda")
        with mock.patch.object(torch.cuda, "is_available", return_value=False):
            self.assertEqual(pick_similarity_device(None), "cpu")

    def test_recommend_learned_similarity_can_rerank_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            idx_dir = base / "index"
            idx_dir.mkdir(parents=True)
            (idx_dir / "hnsw.idx").write_text("idx", encoding="utf-8")
            paths = ["seed-track", "learned-low", "learned-high"]
            (idx_dir / "paths.json").write_text(json.dumps(paths), encoding="utf-8")

            embed_dir = base / "embeddings"
            embed_dir.mkdir()
            tracks = {}
            for i, path in enumerate(paths):
                emb_path = embed_dir / f"{i}.npy"
                vec = np.zeros(4, dtype=np.float32)
                vec[i % 4] = 1.0
                np.save(emb_path, vec)
                tracks[path] = {"embedding": str(emb_path), "bpm": 128.0, "key": "8A", "features": {}}

            printed = []
            fake_head = _FakeLoadedHead(tracks)
            with mock.patch.object(recommend, "IDX", idx_dir), \
                    mock.patch.object(recommend, "load_meta", return_value={"tracks": tracks}), \
                    mock.patch.object(recommend, "load_embedding_safe", side_effect=lambda path, expected_dim=None: np.load(path)), \
                    mock.patch.object(recommend.hnswlib, "Index", side_effect=lambda *args, **kwargs: _FakeIndex()), \
                    mock.patch.object(recommend, "load_similarity_head", return_value=fake_head), \
                    mock.patch.object(recommend.console, "print", side_effect=printed.append):
                recommend.recommend(
                    "seed-track",
                    top=2,
                    camelot_neighbors=False,
                    weights={"learned_sim": 1.0},
                    learned_similarity=True,
                )

            table = printed[1]
            self.assertEqual(list(table.columns[1]._cells)[:2], ["learned-high", "learned-low"])

    def test_train_script_writes_checkpoint_with_cpu_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            embeds = base / "embeds"
            embeds.mkdir()
            rows = []
            for idx in range(6):
                left = embeds / f"left-{idx}.npy"
                right = embeds / f"right-{idx}.npy"
                np.save(left, np.ones(4, dtype=np.float32) * idx)
                np.save(right, np.ones(4, dtype=np.float32) * (idx + 1))
                rows.append({"left_embedding": str(left), "right_embedding": str(right), "label": idx % 2})
            pairs = base / "pairs.jsonl"
            pairs.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
            out = base / "similarity_head.pt"
            args = argparse.Namespace(
                pairs=str(pairs),
                out=str(out),
                device="cpu",
                embed_dim=4,
                hidden=8,
                bottleneck=4,
                batch_size=3,
                epochs=1,
                patience=1,
                lr=1e-3,
                weight_decay=1e-4,
                valid_fraction=0.33,
                seed=123,
                max_rows=None,
            )

            result = train_similarity_head.train(args)

            self.assertTrue(out.exists())
            self.assertEqual(result["device"], "cpu")


if __name__ == "__main__":
    unittest.main()
