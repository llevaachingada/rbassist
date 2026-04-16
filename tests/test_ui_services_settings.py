from __future__ import annotations

import subprocess
import sys
import types
import unittest

from rbassist.ui_services.settings import (
    build_settings_pipeline_request,
    build_settings_pipeline_view,
    parse_folder_inputs,
)


class SettingsServiceTests(unittest.TestCase):
    def test_parse_folder_inputs_handles_quotes_and_separators(self) -> None:
        raw = "\n".join(
            [
                '  "C:/Music/Alpha" ; "C:/Music/Beta"  ',
                "'C:/Music/Gamma'",
                "C:/Music/Delta",
                r"\\Server\Share\Epsilon",
            ]
        )

        self.assertEqual(
            parse_folder_inputs(raw),
            [
                "C:/Music/Alpha",
                "C:/Music/Beta",
                "C:/Music/Gamma",
                "C:/Music/Delta",
                r"\\Server\Share\Epsilon",
            ],
        )

    def test_settings_pipeline_request_builds_text_and_payload(self) -> None:
        request = build_settings_pipeline_request(
            scope_label="configured folders",
            files_total=12,
            embed_total=7,
            analysis_total=5,
            beatgrid_total=3,
            overwrite=True,
            skip_analyzed=False,
            use_timbre=True,
            resume_embed=True,
            duration_s=120,
            workers=4,
            batch_size=8,
            device="cuda",
            add_cues=True,
            beatgrid_enabled=True,
            beatgrid_overwrite=False,
            checkpoint_file="data/checkpoint.json",
            checkpoint_every=50,
        )

        self.assertEqual(
            request.result_payload(),
            {
                "scope": "configured folders",
                "files_total": 12,
                "embed_total": 7,
                "analysis_total": 5,
                "beatgrid_total": 3,
            },
        )
        self.assertIn("12 files found", request.preflight_text())
        self.assertIn("overwrite=ON", request.preflight_text())
        self.assertIn("resume=ON", request.preflight_text())
        self.assertIn("configured folders", request.running_text())
        self.assertEqual(request.completed_text(), "Embed + Analyze + Index complete")
        self.assertEqual(request.failed_text(), "Pipeline failed")

    def test_settings_pipeline_view_uses_job_and_history_data(self) -> None:
        snapshot = types.SimpleNamespace(
            job_id="job-1",
            status="running",
            phase="embed",
            message="Embedding 1/2",
            progress=0.5,
            error=None,
        )
        recent_jobs = [
            types.SimpleNamespace(status="running", phase="embed"),
            types.SimpleNamespace(status="queued", phase="preflight"),
        ]

        view = build_settings_pipeline_view(snapshot, recent_jobs)

        self.assertTrue(view.progress_visible)
        self.assertEqual(view.progress_value, 0.5)
        self.assertEqual(view.status_text, "Embedding 1/2")
        self.assertEqual(view.phase_text, "Phase: embed | Status: running")
        self.assertEqual(view.error_text, "")
        self.assertIn("Recent settings jobs: running:embed", view.history_text)
        self.assertIn("queued:preflight", view.history_text)

    def test_settings_service_import_is_headless(self) -> None:
        script = (
            "import importlib, sys; "
            "importlib.import_module('rbassist.ui_services.settings'); "
            "raise SystemExit(1 if 'nicegui' in sys.modules or 'PySide6' in sys.modules else 0)"
        )
        result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
