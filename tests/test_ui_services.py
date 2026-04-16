from __future__ import annotations

import json
import subprocess
import sys
import types
import unittest
from unittest import mock
from tempfile import TemporaryDirectory
from pathlib import Path

from rbassist.desktop.app import build_desktop_overview
from rbassist.ui_services.cues import build_cue_page_view, plan_cue_targets
from rbassist.ui_services.discover import (
    audio_distance_note,
    build_recommendation_rows,
    build_track_detail,
    should_apply_refresh_result,
    should_continue_refresh_drain,
    should_start_refresh_task,
)
from rbassist.ui_services.jobs import describe_job, job_to_dict
from rbassist.ui_services.library import build_library_page_model, build_library_rows, build_library_snapshot


class UiServicesTests(unittest.TestCase):
    def _write_vec(self, path: Path, first: float) -> str:
        import numpy as np

        vec = np.zeros(1024, dtype=np.float32)
        vec[0] = first
        np.save(path, vec)
        return str(path)

    def test_library_snapshot_counts_and_preview_rows(self) -> None:
        meta = {
            "tracks": {
                "C:/Music/B.mp3": {"artist": "B", "title": "Beta", "bpm": 124, "key": "8A", "embedding": "b.npy"},
                "C:/Music/A.mp3": {"artist": "A", "title": "Alpha", "bpm": 122},
            }
        }
        snapshot = build_library_snapshot(meta, preview_limit=1)
        self.assertEqual(snapshot.tracks_total, 2)
        self.assertEqual(snapshot.embedded_total, 1)
        self.assertEqual(snapshot.analyzed_total, 1)
        self.assertEqual(snapshot.preview_rows[0]["artist"], "A")

    def test_build_library_rows_formats_missing_values(self) -> None:
        rows = build_library_rows({"tracks": {"C:/Music/Test.mp3": {}}})
        self.assertEqual(rows[0]["title"], "Test.mp3")
        self.assertEqual(rows[0]["bpm"], "-")
        self.assertEqual(rows[0]["key"], "-")

    def test_build_library_page_model_extracts_health_rows(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            track_path = tmp_path / "Alpha.mp3"
            track_path.write_text("", encoding="utf-8")
            embedding_path = tmp_path / "Alpha.npy"
            embedding_path.write_text("", encoding="utf-8")

            model = build_library_page_model(
                {
                    "tracks": {
                        str(track_path): {
                            "artist": "A",
                            "title": "Alpha",
                            "bpm": 124,
                            "key": "8A",
                            "embedding": str(embedding_path),
                            "cues": [1, 2],
                        },
                        "Bare.mp3": {
                            "artist": "B",
                            "title": "Beta",
                        },
                    }
                },
                base_dir=tmp_path,
            )

        self.assertEqual(model.tracks_total, 2)
        self.assertEqual(model.embedded_total, 1)
        self.assertEqual(model.analyzed_total, 1)
        self.assertEqual(model.issue_counts["stale_path"], 1)
        self.assertEqual(model.issue_counts["bare_path"], 1)
        self.assertEqual(model.issue_counts["missing_embedding"], 1)
        self.assertEqual(model.issue_counts["missing_analysis"], 1)
        self.assertEqual(model.issue_counts["missing_cues"], 1)
        self.assertEqual(model.rows[0]["issues"], "-")
        self.assertIn("bare path", model.rows[1]["issues"])
        self.assertEqual(model.rows[0]["embedded"], "Yes")

    def test_discover_refresh_helpers(self) -> None:
        self.assertTrue(should_apply_refresh_result(request_id=3, latest_request_id=3, browse_mode=False))
        self.assertFalse(should_apply_refresh_result(request_id=2, latest_request_id=3, browse_mode=False))
        self.assertFalse(should_start_refresh_task(running=True))
        self.assertTrue(
            should_continue_refresh_drain(completed_request_id=2, latest_request_id=3, browse_mode=False)
        )

    def test_discover_detail_text_is_plain_data(self) -> None:
        detail = build_track_detail(
            path="C:/Music/Track.mp3",
            track={"artist": "Artist", "title": "Title", "score": 0.9, "dist": 0.123, "key_rule": "same"},
            info={"bpm": 124, "key": "8A", "mytags": ["Peak"]},
            browse_mode=False,
        )
        self.assertEqual(detail["title"], "Artist - Title")
        self.assertIn("0.123", detail["summary"])
        self.assertIn("Peak", detail["metrics"])
        self.assertEqual(audio_distance_note("-"), "Not shown in library browse mode")

    def test_discover_detail_includes_advanced_scores_when_present(self) -> None:
        detail = build_track_detail(
            path="C:/Music/Track.mp3",
            track={
                "artist": "Artist",
                "title": "Title",
                "score": 0.9,
                "dist": 0.123,
                "key_rule": "same",
                "harmonic_score": 0.8,
                "learned_score": 0.7,
            },
            info={"bpm": 124, "key": "8A"},
            browse_mode=False,
        )

        self.assertIn("Profile harmony 0.8", detail["summary"])
        self.assertIn("Learned fit 0.7", detail["summary"])

    def test_discover_recommendations_can_use_learned_similarity(self) -> None:
        class FakeIndex:
            def __init__(self, *args, **kwargs) -> None:
                pass

            def load_index(self, _path: str) -> None:
                return None

            def set_ef(self, _value: int) -> None:
                return None

            def knn_query(self, _vec, k: int):
                import numpy as np

                return np.array([[0, 1, 2]], dtype=np.int64), np.array([[0.0, 0.2, 0.1]], dtype=np.float32)

        class FakeHead:
            def score(self, _seed_vec, cand_vec) -> float:
                return float(cand_vec[0])

        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            idx_dir = tmp_path / "idx"
            idx_dir.mkdir()
            (idx_dir / "paths.json").write_text(json.dumps(["seed", "low", "high"]), encoding="utf-8")
            (idx_dir / "hnsw.idx").write_text("", encoding="utf-8")
            meta = {
                "tracks": {
                    "seed": {
                        "artist": "Seed",
                        "title": "Seed",
                        "bpm": 124,
                        "key": "8A",
                        "embedding": self._write_vec(tmp_path / "seed.npy", 1.0),
                    },
                    "low": {
                        "artist": "Low",
                        "title": "Low",
                        "bpm": 124,
                        "key": "8A",
                        "embedding": self._write_vec(tmp_path / "low.npy", 0.1),
                    },
                    "high": {
                        "artist": "High",
                        "title": "High",
                        "bpm": 124,
                        "key": "8A",
                        "embedding": self._write_vec(tmp_path / "high.npy", 0.9),
                    },
                }
            }

            with (
                mock.patch("rbassist.recommend.IDX", idx_dir),
                mock.patch("hnswlib.Index", FakeIndex),
                mock.patch("rbassist.similarity_head.load_similarity_head", return_value=FakeHead()),
            ):
                rows = build_recommendation_rows(
                    seed_path="seed",
                    meta=meta,
                    filters={"tempo_pct": 6.0, "doubletime": True, "learned_similarity": True},
                    weights={"learned_sim": 1.0},
                    top=2,
                )

        self.assertEqual([row["path"] for row in rows], ["high", "low"])
        self.assertEqual(rows[0]["learned_score"], 0.9)

    def test_job_display_is_gui_neutral(self) -> None:
        snapshot = types.SimpleNamespace(status="running", phase="embed", message="", progress=0.5)
        display = describe_job(snapshot)
        self.assertTrue(display.busy)
        self.assertEqual(display.text, "Running embed")
        self.assertEqual(job_to_dict(snapshot)["progress"], 0.5)

    def test_cues_service_plans_targets_and_view_model(self) -> None:
        meta = {
            "tracks": {
                "C:/Music/Keep.mp3": {"cues": [{"pos": 1}]},
                "C:/Music/Need.mp3": {},
            }
        }
        plan = plan_cue_targets(meta, ["C:/Music/Keep.mp3", "C:/Music/Need.mp3"], overwrite_existing=False)
        self.assertEqual(plan.total_paths, 2)
        self.assertEqual(plan.target_paths, ["C:/Music/Need.mp3"])
        self.assertFalse(plan.overwrite_existing)

        snapshot = types.SimpleNamespace(
            job_id="job-1",
            status="running",
            phase="cues",
            message="Processing 1/1",
            progress=1.0,
        )
        view = build_cue_page_view(snapshot, [types.SimpleNamespace(status="running", phase="cues")])
        self.assertTrue(view.progress_visible)
        self.assertEqual(view.status_text, "Processing 1/1")
        self.assertIn("Phase: cues", view.phase_text)
        self.assertIn("Recent cue jobs: running:cues", view.history_text)

    def test_desktop_overview_builds_without_pyside(self) -> None:
        overview = build_desktop_overview(
            {"tracks": {"C:/Music/A.mp3": {"artist": "A", "title": "Alpha", "embedding": "a.npy"}}},
            preview_limit=10,
        )
        self.assertEqual(overview.tracks_total, 1)
        self.assertEqual(overview.embedded_total, 1)
        self.assertEqual(overview.preview_rows[0]["title"], "Alpha")

    def test_desktop_module_import_does_not_load_backend_utils(self) -> None:
        script = (
            "import importlib, sys; "
            "importlib.import_module('rbassist.desktop.app'); "
            "raise SystemExit(1 if 'rbassist.utils' in sys.modules else 0)"
        )
        result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
