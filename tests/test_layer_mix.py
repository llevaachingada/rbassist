from types import SimpleNamespace
import unittest

import numpy as np
import torch

from rbassist import embed as embed_mod
from rbassist.layer_mix import extract_layer_pools, fixed_weight_mix


class _FakeProcessor:
    def __call__(self, y, sampling_rate=None, return_tensors=None, padding=False):
        return {"input_values": torch.ones(1, 4)}


class _FakeModel:
    def __init__(self):
        self.calls = 0

    def __call__(self, **kwargs):
        self.calls += 1
        hidden_states = tuple(
            torch.ones(1, 3, 1024, dtype=torch.float32) * float(idx + 1)
            for idx in range(25)
        )
        return SimpleNamespace(hidden_states=hidden_states)


class LayerMixTests(unittest.TestCase):
    def test_extract_layer_pools_shape(self) -> None:
        hidden_states = tuple(np.ones((1, 3, 1024), dtype=np.float32) for _ in range(25))
        pools = extract_layer_pools(hidden_states)
        self.assertEqual(pools.shape, (6, 1024))

    def test_fixed_weight_mix_normalized(self) -> None:
        pools = np.ones((6, 1024), dtype=np.float32)
        mixed = fixed_weight_mix(pools)
        self.assertEqual(mixed.shape, (1024,))
        self.assertAlmostEqual(float(np.linalg.norm(mixed)), 1.0, places=6)

    def test_encode_array_full_single_forward_pass(self) -> None:
        embedder = embed_mod.MertEmbedder.__new__(embed_mod.MertEmbedder)
        embedder.device = "cpu"
        embedder.processor = _FakeProcessor()
        embedder.model = _FakeModel()
        embedder.layer_mix = False
        embedder.layer_mix_weights = None

        out = embedder.encode_array_full(np.ones(10, dtype=np.float32), embed_mod.SAMPLE_RATE)

        self.assertEqual(set(out), {"standard", "layer_mix"})
        self.assertEqual(out["standard"].shape, (1024,))
        self.assertEqual(out["layer_mix"].shape, (1024,))
        self.assertEqual(embedder.model.calls, 1)

    def test_layer_mix_false_identical_to_original_path(self) -> None:
        embedder = embed_mod.MertEmbedder.__new__(embed_mod.MertEmbedder)
        embedder.device = "cpu"
        embedder.processor = _FakeProcessor()
        embedder.model = _FakeModel()
        embedder.layer_mix = False
        embedder.layer_mix_weights = None

        out = embedder.encode_array(np.ones(10, dtype=np.float32), embed_mod.SAMPLE_RATE)

        self.assertTrue(np.allclose(out, np.full(1024, 25.0, dtype=np.float32)))
        self.assertEqual(embedder.model.calls, 1)


if __name__ == "__main__":
    unittest.main()
