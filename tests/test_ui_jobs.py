import unittest

from rbassist.ui.jobs import JobRegistry, resolve_active_job


class JobRegistryTests(unittest.TestCase):
    def test_job_lifecycle_tracks_progress_and_completion(self) -> None:
        registry = JobRegistry()
        snapshot = registry.start("settings_pipeline", phase="preflight", message="Preparing", progress=0.1)

        registry.update(snapshot.job_id, phase="embed", message="Embedding", progress=0.4)
        updated = registry.get(snapshot.job_id)
        self.assertIsNotNone(updated)
        self.assertEqual(updated.phase, "embed")
        self.assertEqual(updated.message, "Embedding")
        self.assertEqual(updated.progress, 0.4)

        registry.complete(snapshot.job_id, message="Done", result={"files_total": 3})
        completed = registry.get(snapshot.job_id)
        self.assertIsNotNone(completed)
        self.assertEqual(completed.status, "completed")
        self.assertEqual(completed.message, "Done")
        self.assertEqual(completed.progress, 1.0)
        self.assertEqual(completed.result, {"files_total": 3})
        self.assertIsNotNone(completed.finished_at)

    def test_list_recent_filters_by_kind(self) -> None:
        registry = JobRegistry()
        first = registry.start("settings_pipeline", message="one")
        second = registry.start("discover_refresh", message="two")
        third = registry.start("settings_pipeline", message="three")

        recent = registry.list_recent(kind="settings_pipeline", limit=5)
        self.assertEqual([job.job_id for job in recent], [third.job_id, first.job_id])
        self.assertEqual(registry.latest(kind="discover_refresh").job_id, second.job_id)

    def test_progress_is_clamped(self) -> None:
        registry = JobRegistry()
        snapshot = registry.start("settings_pipeline", progress=5)
        self.assertEqual(snapshot.progress, 1.0)
        registry.update(snapshot.job_id, progress=-1)
        self.assertEqual(registry.get(snapshot.job_id).progress, 0.0)

    def test_resolve_active_job_prefers_local_job_id(self) -> None:
        registry = JobRegistry()
        snapshot = registry.start("settings_pipeline", message="active")
        from rbassist.ui import jobs as ui_jobs

        old_registry = ui_jobs._REGISTRY
        ui_jobs._REGISTRY = registry
        try:
            self.assertEqual(resolve_active_job(snapshot.job_id, kind="settings_pipeline"), snapshot)
        finally:
            ui_jobs._REGISTRY = old_registry

    def test_resolve_active_job_falls_back_to_latest_running_job_by_kind(self) -> None:
        registry = JobRegistry()
        snapshot = registry.start("settings_pipeline", message="active")
        from rbassist.ui import jobs as ui_jobs

        old_registry = ui_jobs._REGISTRY
        ui_jobs._REGISTRY = registry
        try:
            self.assertEqual(resolve_active_job(None, kind="settings_pipeline"), snapshot)
        finally:
            ui_jobs._REGISTRY = old_registry

    def test_resolve_active_job_ignores_completed_fallback_job(self) -> None:
        registry = JobRegistry()
        snapshot = registry.start("settings_pipeline", message="active")
        registry.complete(snapshot.job_id, message="done")
        from rbassist.ui import jobs as ui_jobs

        old_registry = ui_jobs._REGISTRY
        ui_jobs._REGISTRY = registry
        try:
            self.assertIsNone(resolve_active_job(None, kind="settings_pipeline"))
        finally:
            ui_jobs._REGISTRY = old_registry


if __name__ == "__main__":
    unittest.main()
