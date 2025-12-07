"""Reusable track table component."""

from __future__ import annotations

from typing import Callable
from nicegui import ui


def track_table(
    tracks: list[dict],
    on_select: Callable[[dict], None] | None = None,
    on_row_click: Callable[[dict], None] | None = None,
    selectable: bool = True,
    columns: list[dict] | None = None,
) -> ui.table:
    """Create a styled track table.

    Args:
        tracks: List of track dictionaries
        on_select: Callback when selection changes
        on_row_click: Callback when row is clicked
        selectable: Enable row selection
        columns: Custom column definitions (optional)
    """
    default_columns = [
        {"name": "artist", "label": "Artist", "field": "artist", "sortable": True, "align": "left"},
        {"name": "title", "label": "Title", "field": "title", "sortable": True, "align": "left"},
        {"name": "bpm", "label": "BPM", "field": "bpm", "sortable": True, "align": "right"},
        {"name": "key", "label": "Key", "field": "key", "sortable": True, "align": "center"},
    ]

    cols = columns or default_columns

    table = ui.table(
        columns=cols,
        rows=tracks,
        row_key="path",
        pagination={"rowsPerPage": 25},
    )

    # Apply dark styling
    props = "dark dense flat bordered"
    if selectable:
        props += " selection=single"
    table.props(props)

    # Style the table
    table.classes("w-full")

    if on_select and selectable:
        table.on("selection", lambda e: on_select(e.args[1] if e.args else None))

    if on_row_click:
        table.on("row-click", lambda e: on_row_click(e.args[1] if len(e.args) > 1 else None))

    return table


class TrackTable:
    """Managed track table with state."""

    def __init__(
        self,
        on_select: Callable[[dict], None] | None = None,
        selectable: bool = True,
        extra_columns: list[dict] | None = None,
    ):
        self.on_select = on_select
        self.selectable = selectable
        self._tracks: list[dict] = []

        # Build columns
        self.columns = [
            {"name": "artist", "label": "Artist", "field": "artist", "sortable": True, "align": "left"},
            {"name": "title", "label": "Title", "field": "title", "sortable": True, "align": "left"},
            {"name": "bpm", "label": "BPM", "field": "bpm", "sortable": True, "align": "right"},
            {"name": "key", "label": "Key", "field": "key", "sortable": True, "align": "center"},
        ]
        if extra_columns:
            self.columns.extend(extra_columns)

        self.table: ui.table | None = None

    def build(self) -> ui.table:
        """Build and return the table widget."""
        self.table = ui.table(
            columns=self.columns,
            rows=self._tracks,
            row_key="path",
            pagination={"rowsPerPage": 25},
        )

        props = "dark dense flat bordered"
        if self.selectable:
            props += " selection=single"
        self.table.props(props)
        self.table.classes("w-full")

        if self.on_select and self.selectable:
            self.table.on("selection", lambda e: self.on_select(e.args[1] if e.args else None))

        return self.table

    def update(self, tracks: list[dict]) -> None:
        """Update table data."""
        self._tracks = tracks
        if self.table:
            self.table.rows = tracks
            self.table.update()

    def clear_selection(self) -> None:
        """Clear current selection."""
        if self.table:
            self.table.selected = []
            self.table.update()
