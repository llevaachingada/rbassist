import importlib.util
import pathlib
import sys
import tempfile
import unittest
from unittest import mock


def _load_script_module(name: str, relative_path: str):
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    module_path = repo_root / relative_path
    spec = importlib.util.spec_from_file_location(name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


maintenance = _load_script_module(
    "test_run_music_root_background_maintenance_module",
    "scripts/run_music_root_background_maintenance.py",
)


class MaintenanceQuarantineTests(unittest.TestCase):
    def test_discover_failed_logs_dedupes_recursive_and_extra_paths(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            run_dir = base / "run"
            nested = run_dir / "nested"
            nested.mkdir(parents=True)
            a = run_dir / "embed_checkpoint_failed.jsonl"
            b = nested / "embed_checkpoint_part001_failed.jsonl"
            a.write_text("", encoding="utf-8")
            b.write_text("", encoding="utf-8")

            discovered = maintenance._discover_failed_logs(run_dir, extra_logs=[a, b])

            self.assertEqual(discovered, [a.resolve(), b.resolve()])

    def test_update_quarantine_from_failed_logs_summarizes_updates(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            run_dir = base / "run"
            run_dir.mkdir()
            a = run_dir / "embed_checkpoint_failed.jsonl"
            b = run_dir / "embed_checkpoint_part001_failed.jsonl"
            a.write_text("", encoding="utf-8")
            b.write_text("", encoding="utf-8")

            def fake_run_update(*, repo, failed_log, quarantine_file):
                if failed_log == a.resolve():
                    return {
                        "status": "ok",
                        "failed_log": str(failed_log),
                        "new_records": 3,
                        "merged_records": 5,
                    }
                return {
                    "status": "failed",
                    "failed_log": str(failed_log),
                    "stderr": "boom",
                }

            with mock.patch.object(maintenance, "_run_quarantine_update", side_effect=fake_run_update):
                report = maintenance._update_quarantine_from_failed_logs(
                    repo=base,
                    run_dir=run_dir,
                    quarantine_file="data/quarantine_embed.jsonl",
                )

            self.assertEqual(report["failed_logs_found"], 2)
            self.assertEqual(report["failed_logs_processed"], 1)
            self.assertEqual(report["failed_logs_failed"], 1)
            self.assertEqual(report["new_records_added"], 3)
            self.assertEqual(report["merged_records_total"], 5)
            self.assertEqual(len(report["updates"]), 2)


if __name__ == "__main__":
    unittest.main()
