from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

__all__ = [
    "DesktopOverview",
    "DesktopShellModel",
    "DiscoverReadiness",
    "JobStatusSummary",
    "LibraryHealthSummary",
    "build_desktop_overview",
    "build_discover_readiness",
    "build_desktop_shell_model",
    "build_job_status_summary",
    "build_library_health_summary",
    "main",
    "run",
]


@dataclass(frozen=True, slots=True)
class DesktopOverview:
    tracks_total: int
    embedded_total: int
    analyzed_total: int
    preview_rows: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class JobStatusSummary:
    active_total: int
    rows: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class DiscoverReadiness:
    ready: bool
    message: str
    details: list[str]


@dataclass(frozen=True, slots=True)
class LibraryHealthSummary:
    issue_rows_total: int
    issue_counts: dict[str, int]
    top_issues: list[str]


@dataclass(frozen=True, slots=True)
class DesktopShellModel:
    overview: DesktopOverview
    library_preview_rows: list[dict[str, Any]]
    library_health: LibraryHealthSummary
    job_summary: JobStatusSummary
    discover_readiness: DiscoverReadiness
    discover_placeholder: str


def build_desktop_overview(meta: Mapping[str, Any] | None = None, *, preview_limit: int = 100) -> DesktopOverview:
    """Build a read-only desktop proof-of-life model without importing PySide."""
    from rbassist.ui_services.library import build_library_snapshot

    if meta is None:
        from rbassist.utils import load_meta

        meta = load_meta()

    snapshot = build_library_snapshot(meta, preview_limit=preview_limit)
    return DesktopOverview(
        tracks_total=snapshot.tracks_total,
        embedded_total=snapshot.embedded_total,
        analyzed_total=snapshot.analyzed_total,
        preview_rows=snapshot.preview_rows,
    )


def build_job_status_summary(*, limit: int = 5) -> JobStatusSummary:
    """Build a read-only summary of recent long-running jobs."""
    from rbassist.runtime.jobs import list_recent_jobs
    from rbassist.ui_services.jobs import describe_job

    rows: list[dict[str, Any]] = []
    active_total = 0

    for snapshot in list_recent_jobs(limit=limit):
        display = describe_job(snapshot)
        if display.busy:
            active_total += 1
        rows.append(
            {
                "kind": str(getattr(snapshot, "kind", "") or ""),
                "status": display.status or str(getattr(snapshot, "status", "") or ""),
                "phase": display.phase or str(getattr(snapshot, "phase", "") or ""),
                "text": display.text,
                "progress": "-" if display.progress is None else f"{float(display.progress) * 100:.0f}%",
                "started_at": str(getattr(snapshot, "started_at", "") or ""),
                "finished_at": str(getattr(snapshot, "finished_at", "") or ""),
            }
        )

    return JobStatusSummary(active_total=active_total, rows=rows)


def build_discover_readiness(overview: DesktopOverview) -> DiscoverReadiness:
    """Build a safe Discover readiness model without touching ranking or writes."""
    details = [
        f"{overview.tracks_total:,} tracks",
        f"{overview.embedded_total:,} embedded",
        f"{overview.analyzed_total:,} analyzed",
    ]

    if overview.tracks_total <= 0:
        return DiscoverReadiness(
            ready=False,
            message="Discover is waiting for library content before it can preview recommendations.",
            details=details,
        )

    if overview.embedded_total <= 0:
        return DiscoverReadiness(
            ready=False,
            message="Discover preview is read-only for now; embeddings are still needed for ranked results.",
            details=details,
        )

    if overview.analyzed_total <= 0:
        return DiscoverReadiness(
            ready=False,
            message="Discover preview is ready for the shell, but analysis data is still sparse.",
            details=details,
        )

    return DiscoverReadiness(
        ready=True,
        message="Discover looks preview-ready for the next bridge slice.",
        details=details,
    )


def build_library_health_summary(meta: Mapping[str, Any]) -> LibraryHealthSummary:
    """Build read-only Library health counts for the desktop shell."""
    from rbassist.ui_services.library import build_library_page_model

    page_model = build_library_page_model(meta)
    issue_rows_total = sum(1 for row in page_model.rows if row.get("issues") != "-")
    labels = {
        "missing_embedding": "missing embedding",
        "missing_analysis": "missing analysis",
        "missing_cues": "missing cues",
        "stale_path": "stale path",
        "bare_path": "bare path",
        "junk_path": "junk path",
    }
    top_issues = [
        f"{labels.get(key, key.replace('_', ' '))}: {count}"
        for key, count in sorted(
            page_model.issue_counts.items(),
            key=lambda item: (-int(item[1]), item[0]),
        )
        if count
    ][:4]
    if not top_issues:
        top_issues = ["No current health issues in the preview model."]
    return LibraryHealthSummary(
        issue_rows_total=issue_rows_total,
        issue_counts=dict(page_model.issue_counts),
        top_issues=top_issues,
    )


def build_desktop_shell_model(
    meta: Mapping[str, Any] | None = None,
    *,
    preview_limit: int = 100,
    job_limit: int = 5,
) -> DesktopShellModel:
    """Build the pure-data model used by the read-only desktop shell."""
    if meta is None:
        from rbassist.utils import load_meta

        meta = load_meta()
    overview = build_desktop_overview(meta=meta, preview_limit=preview_limit)
    library_health = build_library_health_summary(meta)
    job_summary = build_job_status_summary(limit=job_limit)
    discover_readiness = build_discover_readiness(overview)
    return DesktopShellModel(
        overview=overview,
        library_preview_rows=overview.preview_rows,
        library_health=library_health,
        job_summary=job_summary,
        discover_readiness=discover_readiness,
        discover_placeholder=discover_readiness.message,
    )


def _make_read_only_table(
    QtWidgets: Any,
    QtCore: Any,
    *,
    headers: list[str],
    rows: list[dict[str, Any]],
    columns: list[str],
) -> Any:
    table = QtWidgets.QTableWidget(len(rows), len(headers))
    table.setHorizontalHeaderLabels(headers)
    for row_index, row in enumerate(rows):
        values = [row.get(column, "") for column in columns]
        for column_index, value in enumerate(values):
            item = QtWidgets.QTableWidgetItem(str(value))
            item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
            table.setItem(row_index, column_index, item)
    table.resizeColumnsToContents()
    return table


def _build_tab_widget(QtWidgets: Any, QtCore: Any, model: DesktopShellModel) -> Any:
    tabs = QtWidgets.QTabWidget()

    overview_tab = QtWidgets.QWidget()
    overview_layout = QtWidgets.QVBoxLayout(overview_tab)
    overview_title = QtWidgets.QLabel("Overview")
    overview_title.setWordWrap(True)
    overview_layout.addWidget(overview_title)

    overview_summary = QtWidgets.QLabel(
        f"{model.overview.tracks_total:,} tracks | {model.overview.embedded_total:,} embedded | "
        f"{model.overview.analyzed_total:,} analyzed"
    )
    overview_summary.setWordWrap(True)
    overview_layout.addWidget(overview_summary)

    overview_note = QtWidgets.QLabel(
        "This shell is read-only, import-safe, and intentionally narrow while the desktop bridge grows."
    )
    overview_note.setWordWrap(True)
    overview_layout.addWidget(overview_note)

    jobs_title = QtWidgets.QLabel("Recent jobs")
    jobs_title.setWordWrap(True)
    overview_layout.addWidget(jobs_title)

    jobs_summary = QtWidgets.QLabel(
        f"{model.job_summary.active_total} active job(s) | {len(model.job_summary.rows)} recent snapshot(s)"
    )
    jobs_summary.setWordWrap(True)
    overview_layout.addWidget(jobs_summary)

    if model.job_summary.rows:
        jobs_table = _make_read_only_table(
            QtWidgets,
            QtCore,
            headers=["Kind", "Status", "Phase", "Text", "Progress"],
            rows=model.job_summary.rows,
            columns=["kind", "status", "phase", "text", "progress"],
        )
        overview_layout.addWidget(jobs_table)
    else:
        jobs_empty = QtWidgets.QLabel("No recent jobs in the shared registry.")
        jobs_empty.setWordWrap(True)
        overview_layout.addWidget(jobs_empty)

    overview_layout.addStretch(1)
    tabs.addTab(overview_tab, "Overview")

    library_tab = QtWidgets.QWidget()
    library_layout = QtWidgets.QVBoxLayout(library_tab)
    library_title = QtWidgets.QLabel("Library preview")
    library_title.setWordWrap(True)
    library_layout.addWidget(library_title)

    library_health_summary = QtWidgets.QLabel(
        f"{model.library_health.issue_rows_total} row(s) currently have Library health notes."
    )
    library_health_summary.setWordWrap(True)
    library_layout.addWidget(library_health_summary)

    for issue in model.library_health.top_issues:
        issue_label = QtWidgets.QLabel(issue)
        issue_label.setWordWrap(True)
        library_layout.addWidget(issue_label)

    library_rows = list(model.library_preview_rows)
    library_table = _make_read_only_table(
        QtWidgets,
        QtCore,
        headers=["Artist", "Title", "BPM", "Key", "Path"],
        rows=library_rows,
        columns=["artist", "title", "bpm", "key", "path"],
    )
    library_layout.addWidget(library_table)
    tabs.addTab(library_tab, "Library preview")

    discover_tab = QtWidgets.QWidget()
    discover_layout = QtWidgets.QVBoxLayout(discover_tab)
    discover_title = QtWidgets.QLabel("Discover preview")
    discover_title.setWordWrap(True)
    discover_layout.addWidget(discover_title)

    discover_label = QtWidgets.QLabel(model.discover_placeholder)
    discover_label.setWordWrap(True)
    discover_layout.addWidget(discover_label)

    discover_status = QtWidgets.QLabel(
        "Ready" if model.discover_readiness.ready else "Waiting on read-only signals"
    )
    discover_status.setWordWrap(True)
    discover_layout.addWidget(discover_status)

    for detail in model.discover_readiness.details:
        detail_label = QtWidgets.QLabel(detail)
        detail_label.setWordWrap(True)
        discover_layout.addWidget(detail_label)

    discover_next = QtWidgets.QLabel(
        "Next slice: wire this tab to the shared recommendation service once the UI seam is ready."
    )
    discover_next.setWordWrap(True)
    discover_layout.addWidget(discover_next)
    discover_layout.addStretch(1)
    tabs.addTab(discover_tab, "Discover preview")

    return tabs


def run() -> int:
    """Run a tiny read-only PySide proof-of-life window."""
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import (
            QApplication,
            QLabel,
            QMainWindow,
            QTabWidget,
            QTableWidget,
            QTableWidgetItem,
            QVBoxLayout,
            QWidget,
        )
    except Exception as exc:
        print("PySide6 is not installed. Install the desktop extra with: pip install -e .[desktop]")
        print(f"Import error: {exc}")
        return 2

    model = build_desktop_shell_model(preview_limit=100)
    app = QApplication.instance() or QApplication([])
    window = QMainWindow()
    window.setWindowTitle("rbassist Desktop Preview")

    root = QWidget()
    layout = QVBoxLayout(root)

    headline = QLabel("rbassist Desktop Preview (read-only proof of life)")
    headline.setWordWrap(True)
    layout.addWidget(headline)

    counts = QLabel(
        f"{model.overview.tracks_total:,} tracks | {model.overview.embedded_total:,} embedded | "
        f"{model.overview.analyzed_total:,} analyzed"
    )
    counts.setWordWrap(True)
    layout.addWidget(counts)

    tabs = _build_tab_widget(
        type(
            "_QtWidgets",
            (),
            {
                "QWidget": QWidget,
                "QLabel": QLabel,
                "QVBoxLayout": QVBoxLayout,
                "QTabWidget": QTabWidget,
                "QTableWidget": QTableWidget,
                "QTableWidgetItem": QTableWidgetItem,
            },
        ),
        type("_QtCore", (), {"Qt": Qt}),
        model,
    )
    layout.addWidget(tabs)

    window.setCentralWidget(root)
    window.resize(1100, 700)
    window.show()
    return int(app.exec())


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
