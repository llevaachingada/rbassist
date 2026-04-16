import pathlib
import tempfile
import unittest
from unittest import mock

import numpy as np

from rbassist import analyze
from rbassist import playlist_expand as pe
from rbassist.features import harmonic_compatibility, harmonic_compatibility_from_features


def _profiles(pc: int = 0) -> dict:
    chroma = np.zeros(12, dtype=np.float32)
    chroma[pc % 12] = 1.0
    tonnetz = np.array([1.0, 0.5, 0.25, 0.0, 0.0, 0.0], dtype=np.float32)
    return {"features": {"chroma_profile": chroma.tolist(), "tonnetz_profile": tonnetz.tolist()}}


class HarmonicCompatibilityTests(unittest.TestCase):
    def test_identical_profiles_score_high(self) -> None:
        info = _profiles(0)
        score = harmonic_compatibility_from_features(info, info)
        self.assertGreater(score, 0.99)

    def test_missing_or_malformed_profiles_score_zero(self) -> None:
        self.assertEqual(harmonic_compatibility_from_features({}, _profiles(0)), 0.0)
        self.assertEqual(
            harmonic_compatibility(
                np.ones(11, dtype=np.float32),
                np.ones(6, dtype=np.float32),
                np.ones(12, dtype=np.float32),
                np.ones(6, dtype=np.float32),
            ),
            0.0,
        )

    def test_playlist_expansion_can_use_harmonic_profiles_for_soft_key_match(self) -> None:
        seed_info = _profiles(0)
        cand_info = _profiles(0)
        candidate = pe.PreparedCandidate(
            path="candidate",
            vector=np.array([1.0, 0.0], dtype=np.float32),
            key="1A",
            info=cand_info,
        )
        meta_stats = {
            "seed_vectors": [np.array([1.0, 0.0], dtype=np.float32)],
            "seed_centroid": np.array([1.0, 0.0], dtype=np.float32),
            "seed_infos": [seed_info],
            "seed_keys": ["8A"],
            "seed_core_tags": set(),
            "seed_bpm_median": None,
        }

        fallback_scores = pe._compute_component_scores(
            candidate,
            meta_stats,
            pe.PlaylistExpansionControls().normalized(),
        )
        harmonic_scores = pe._compute_component_scores(
            candidate,
            meta_stats,
            pe.PlaylistExpansionControls(use_harmonic_key_scores=True).normalized(),
        )

        self.assertEqual(fallback_scores["key_match"], 0.0)
        self.assertGreater(harmonic_scores["key_match"], 0.99)
        self.assertEqual(harmonic_scores["harmonic_key_score"], harmonic_scores["key_match"])

    def test_analyze_adds_harmonic_profiles_without_overwriting_existing_features(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            track = pathlib.Path(td) / "Artist - Title.wav"
            track.write_bytes(b"fake audio")
            meta_store = {"tracks": {str(track): {"bpm": 128.0, "key": "8A", "sig_bpmkey": "sig"}}}

            class FakeMetaManager:
                def __init__(self):
                    self.meta = meta_store
                    self.dirty = False

                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return None

                def mark_dirty(self):
                    self.dirty = True

            with (
                mock.patch.object(analyze, "MetaManager", FakeMetaManager),
                mock.patch.object(analyze, "current_file_sig", return_value="sig"),
                mock.patch.object(analyze.librosa, "load", return_value=(np.ones(100, dtype=np.float32), 100)),
                mock.patch.object(analyze, "_estimate_tempo", return_value=132.0),
                mock.patch.object(analyze, "_estimate_key", return_value=("9A", "E minor")),
                mock.patch.object(
                    analyze,
                    "chroma_tonnetz_profiles",
                    return_value={"chroma_profile": [1.0] + [0.0] * 11, "tonnetz_profile": [1.0] + [0.0] * 5},
                ),
            ):
                analyze.analyze_bpm_key(
                    [str(track)],
                    duration_s=1,
                    only_new=True,
                    harmonic_profiles=True,
                    workers=0,
                )

        feats = meta_store["tracks"][str(track)]["features"]
        self.assertEqual(meta_store["tracks"][str(track)]["bpm"], 128.0)
        self.assertEqual(meta_store["tracks"][str(track)]["key"], "8A")
        self.assertEqual(len(feats["chroma_profile"]), 12)
        self.assertEqual(len(feats["tonnetz_profile"]), 6)


if __name__ == "__main__":
    unittest.main()
