from __future__ import annotations

import importlib
import sys
import types
import unittest
from types import SimpleNamespace
from unittest import mock


def _fresh_desktop_app():
    sys.modules.pop("rbassist.desktop.app", None)
    return importlib.import_module("rbassist.desktop.app")


def _build_fake_pyside_modules(state: dict[str, object]) -> dict[str, types.ModuleType]:
    modules: dict[str, types.ModuleType] = {}

    pyside = types.ModuleType("PySide6")
    qtcore = types.ModuleType("PySide6.QtCore")
    qtwidgets = types.ModuleType("PySide6.QtWidgets")

    class FakeQt:
        ItemIsEditable = 1

    class QApplication:
        _instance = None

        def __init__(self, args=None):
            self.args = args
            self.exec_called = False
            QApplication._instance = self

        @classmethod
        def instance(cls):
            return cls._instance

        def exec(self):
            self.exec_called = True
            return 0

    class QWidget:
        def __init__(self):
            self.layout = None

        def setLayout(self, layout):
            self.layout = layout

    class QVBoxLayout:
        def __init__(self, parent=None):
            self.parent = parent
            self.widgets = []
            self.stretches = []
            if parent is not None:
                parent.setLayout(self)

        def addWidget(self, widget):
            self.widgets.append(widget)

        def addStretch(self, value):
            self.stretches.append(value)

    class QLabel:
        def __init__(self, text=""):
            self.text = text
            self.word_wrap = False

        def setWordWrap(self, enabled):
            self.word_wrap = bool(enabled)

    class QMainWindow:
        def __init__(self):
            self.title = ""
            self.central_widget = None
            self.size = None
            self.shown = False

        def setWindowTitle(self, title):
            self.title = title

        def setCentralWidget(self, widget):
            self.central_widget = widget
            state["window"] = self

        def resize(self, width, height):
            self.size = (width, height)

        def show(self):
            self.shown = True

    class QTabWidget:
        def __init__(self):
            self.tabs = []
            state["tabs_widget"] = self

        def addTab(self, widget, title):
            self.tabs.append((title, widget))

    class QTableWidgetItem:
        def __init__(self, text):
            self.text = text
            self._flags = 3

        def flags(self):
            return self._flags

        def setFlags(self, flags):
            self._flags = flags

    class QTableWidget:
        def __init__(self, rows, columns):
            self.rows = rows
            self.columns = columns
            self.headers = []
            self.items = {}
            self.resized = False
            state.setdefault("tables", []).append(self)

        def setHorizontalHeaderLabels(self, labels):
            self.headers = list(labels)

        def setItem(self, row, column, item):
            self.items[(row, column)] = item

        def resizeColumnsToContents(self):
            self.resized = True

    qtcore.Qt = FakeQt
    qtwidgets.QApplication = QApplication
    qtwidgets.QLabel = QLabel
    qtwidgets.QMainWindow = QMainWindow
    qtwidgets.QTabWidget = QTabWidget
    qtwidgets.QTableWidget = QTableWidget
    qtwidgets.QTableWidgetItem = QTableWidgetItem
    qtwidgets.QVBoxLayout = QVBoxLayout
    qtwidgets.QWidget = QWidget

    modules["PySide6"] = pyside
    modules["PySide6.QtCore"] = qtcore
    modules["PySide6.QtWidgets"] = qtwidgets
    return modules


class DesktopAppTests(unittest.TestCase):
    def test_import_does_not_load_pyside_or_utils(self) -> None:
        for name in [
            "rbassist.desktop.app",
            "rbassist.utils",
            "PySide6",
            "PySide6.QtCore",
            "PySide6.QtWidgets",
        ]:
            sys.modules.pop(name, None)

        module = importlib.import_module("rbassist.desktop.app")

        self.assertIsNotNone(module)
        self.assertNotIn("PySide6", sys.modules)
        self.assertNotIn("rbassist.utils", sys.modules)

    def test_shell_model_includes_job_summary_and_discover_readiness(self) -> None:
        desktop_app = _fresh_desktop_app()

        fake_jobs = [
            SimpleNamespace(
                kind="discover",
                status="running",
                phase="refresh",
                message="Refreshing discover results",
                progress=0.5,
                started_at="2026-04-12T10:00:00+00:00",
                finished_at=None,
            ),
            SimpleNamespace(
                kind="library",
                status="completed",
                phase="scan",
                message="Library scan complete",
                progress=1.0,
                started_at="2026-04-12T09:55:00+00:00",
                finished_at="2026-04-12T10:05:00+00:00",
            ),
        ]

        with mock.patch("rbassist.runtime.jobs.list_recent_jobs", return_value=fake_jobs):
            model = desktop_app.build_desktop_shell_model(
                {
                    "tracks": {
                        "C:/Music/A.mp3": {
                            "artist": "A",
                            "title": "Alpha",
                            "embedding": "a.npy",
                            "bpm": 123,
                            "key": "8A",
                        }
                    }
                },
                preview_limit=10,
                job_limit=5,
            )

        self.assertEqual(model.job_summary.active_total, 1)
        self.assertEqual(len(model.job_summary.rows), 2)
        self.assertEqual(model.job_summary.rows[0]["kind"], "discover")
        self.assertEqual(model.job_summary.rows[0]["progress"], "50%")
        self.assertEqual(model.library_health.issue_rows_total, 1)
        self.assertIn("missing cues: 1", model.library_health.top_issues)
        self.assertTrue(model.discover_readiness.ready)
        self.assertIn("preview-ready", model.discover_placeholder)

    def test_library_health_summary_reports_clean_and_issue_rows(self) -> None:
        desktop_app = _fresh_desktop_app()

        clean = desktop_app.build_library_health_summary(
            {
                "tracks": {
                    "C:/Music/Ready.mp3": {
                        "artist": "A",
                        "title": "Ready",
                        "embedding": "ready.npy",
                        "bpm": 123,
                        "key": "8A",
                        "cues": [{"pos": 1}],
                    }
                }
            }
        )
        self.assertIn("missing_embedding", clean.issue_counts)

        issue = desktop_app.build_library_health_summary(
            {
                "tracks": {
                    "Bare.mp3": {
                        "artist": "B",
                        "title": "Needs Work",
                    }
                }
            }
        )
        self.assertEqual(issue.issue_rows_total, 1)
        self.assertTrue(any("missing embedding" in text for text in issue.top_issues))

    def test_run_builds_three_tab_shell_with_stubbed_pyside(self) -> None:
        desktop_app = _fresh_desktop_app()

        state: dict[str, object] = {}
        fake_modules = _build_fake_pyside_modules(state)
        model = desktop_app.DesktopShellModel(
            overview=desktop_app.DesktopOverview(tracks_total=2, embedded_total=1, analyzed_total=1, preview_rows=[]),
            library_preview_rows=[
                {"artist": "A", "title": "Alpha", "bpm": "122", "key": "8A", "path": "C:/Music/A.mp3"},
                {"artist": "B", "title": "Beta", "bpm": "124", "key": "9A", "path": "C:/Music/B.mp3"},
            ],
            library_health=desktop_app.LibraryHealthSummary(
                issue_rows_total=2,
                issue_counts={"missing_embedding": 2},
                top_issues=["missing embedding: 2"],
            ),
            job_summary=desktop_app.JobStatusSummary(
                active_total=1,
                rows=[
                    {
                        "kind": "discover",
                        "status": "running",
                        "phase": "refresh",
                        "text": "Refreshing discover results",
                        "progress": "50%",
                    }
                ],
            ),
            discover_readiness=desktop_app.DiscoverReadiness(
                ready=True,
                message="Discover looks preview-ready for the next bridge slice.",
                details=["2 tracks", "1 embedded", "1 analyzed"],
            ),
            discover_placeholder="Discover looks preview-ready for the next bridge slice.",
        )

        with mock.patch.dict(sys.modules, fake_modules, clear=False):
            with mock.patch.object(desktop_app, "build_desktop_shell_model", return_value=model):
                exit_code = desktop_app.run()

        self.assertEqual(exit_code, 0)
        self.assertIn("tabs_widget", state)
        tabs_widget = state["tabs_widget"]
        self.assertEqual([title for title, _ in tabs_widget.tabs], ["Overview", "Library preview", "Discover preview"])
        self.assertTrue(state["window"].shown)

        overview_tab = tabs_widget.tabs[0][1]
        overview_labels = [widget.text for widget in overview_tab.layout.widgets if hasattr(widget, "text")]
        self.assertTrue(any("Recent jobs" in text for text in overview_labels))
        self.assertTrue(any("1 active job" in text for text in overview_labels))

        discover_tab = tabs_widget.tabs[2][1]
        discover_labels = [widget.text for widget in discover_tab.layout.widgets if hasattr(widget, "text")]
        self.assertTrue(any("preview-ready" in text for text in discover_labels))
        self.assertTrue(any("2 tracks" in text for text in discover_labels))

        library_tab = tabs_widget.tabs[1][1]
        library_labels = [widget.text for widget in library_tab.layout.widgets if hasattr(widget, "text")]
        self.assertTrue(any("2 row(s)" in text for text in library_labels))
        self.assertTrue(any("missing embedding: 2" in text for text in library_labels))

        tables = state["tables"]
        self.assertEqual(len(tables), 2)
        self.assertEqual(tables[0].headers, ["Kind", "Status", "Phase", "Text", "Progress"])
        self.assertEqual(tables[1].headers, ["Artist", "Title", "BPM", "Key", "Path"])
        self.assertTrue(all(table.resized for table in tables))
        self.assertEqual(tables[1].items[(0, 0)].text, "A")
        self.assertNotEqual(tables[1].items[(0, 0)].flags() & 1, 1)


if __name__ == "__main__":
    unittest.main()
