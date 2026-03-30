import types
import unittest

from rbassist.ui.components.filters import format_tempo_pct
from rbassist.ui.components.progress import describe_job_snapshot
from rbassist.ui.components.track_table import _selected_row


class UiComponentHelperTests(unittest.TestCase):
    def test_format_tempo_pct_uses_ascii_label(self) -> None:
        self.assertEqual(format_tempo_pct(6), "+/-6.0%")
        self.assertEqual(format_tempo_pct(3.5), "+/-3.5%")

    def test_selected_row_returns_first_selection(self) -> None:
        event = types.SimpleNamespace(selection=[{"path": "first"}, {"path": "second"}])
        self.assertEqual(_selected_row(event), {"path": "first"})

    def test_selected_row_returns_none_when_empty(self) -> None:
        event = types.SimpleNamespace(selection=[])
        self.assertIsNone(_selected_row(event))

    def test_describe_job_snapshot_reports_running_and_completed_states(self) -> None:
        running = types.SimpleNamespace(status="running", phase="embed", message="Embedding 1/4")
        completed = types.SimpleNamespace(status="completed", phase="completed", message="Done")
        self.assertEqual(describe_job_snapshot(running), ("Embedding 1/4", True))
        self.assertEqual(describe_job_snapshot(completed), ("Done", False))


if __name__ == "__main__":
    unittest.main()
