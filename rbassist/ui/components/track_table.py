"""Reusable track table component."""

from __future__ import annotations

from typing import Callable

from nicegui import ui
from nicegui.events import TableSelectionEventArguments


DEFAULT_ROWS_PER_PAGE_OPTIONS = [25, 50, 100, 250, 500]


def _selected_row(event: TableSelectionEventArguments) -> dict | None:
    """Return the first selected row from NiceGUI's table selection payload."""
    return event.selection[0] if event.selection else None


def track_table(
    tracks: list[dict],
    on_select: Callable[[dict], None] | None = None,
    on_row_click: Callable[[dict], None] | None = None,
    selectable: bool = True,
    columns: list[dict] | None = None,
    rows_per_page: int = 50,
    rows_per_page_options: list[int] | None = None,
) -> ui.table:
    """Create a styled track table."""
    default_columns = [
        {'name': 'artist', 'label': 'Artist', 'field': 'artist', 'sortable': True, 'align': 'left'},
        {'name': 'title', 'label': 'Title', 'field': 'title', 'sortable': True, 'align': 'left'},
        {'name': 'bpm', 'label': 'BPM', 'field': 'bpm', 'sortable': True, 'align': 'right'},
        {'name': 'key', 'label': 'Key', 'field': 'key', 'sortable': True, 'align': 'center'},
    ]

    cols = columns or default_columns
    options = rows_per_page_options or DEFAULT_ROWS_PER_PAGE_OPTIONS

    table = ui.table(
        columns=cols,
        rows=tracks,
        row_key='path',
        pagination={
            'rowsPerPage': rows_per_page,
            'rowsPerPageOptions': options,
            'sortBy': 'artist',
            'descending': False,
            'page': 1,
        },
    )

    props = 'dark dense flat bordered'
    if selectable:
        props += ' selection=single'
    table.props(props)
    table.classes('w-full')

    if on_select and selectable:
        table.on_select(lambda e: on_select(_selected_row(e)))

    if on_row_click:
        table.on('row-click', lambda e: on_row_click(e.args[1] if len(e.args) > 1 else None))

    return table


class TrackTable:
    """Managed track table with state."""

    def __init__(
        self,
        on_select: Callable[[dict], None] | None = None,
        on_row_click: Callable[[dict], None] | None = None,
        selectable: bool = True,
        extra_columns: list[dict] | None = None,
        rows_per_page: int = 50,
        rows_per_page_options: list[int] | None = None,
    ):
        self.on_select = on_select
        self.on_row_click = on_row_click
        self.selectable = selectable
        self.rows_per_page = rows_per_page
        self.rows_per_page_options = rows_per_page_options or list(DEFAULT_ROWS_PER_PAGE_OPTIONS)
        self._tracks: list[dict] = []

        self.columns = [
            {'name': 'artist', 'label': 'Artist', 'field': 'artist', 'sortable': True, 'align': 'left'},
            {'name': 'title', 'label': 'Title', 'field': 'title', 'sortable': True, 'align': 'left'},
            {'name': 'bpm', 'label': 'BPM', 'field': 'bpm', 'sortable': True, 'align': 'right'},
            {'name': 'key', 'label': 'Key', 'field': 'key', 'sortable': True, 'align': 'center'},
        ]
        if extra_columns:
            self.columns.extend(extra_columns)

        self.table: ui.table | None = None

    def build(self) -> ui.table:
        """Build and return the table widget."""
        self.table = ui.table(
            columns=self.columns,
            rows=self._tracks,
            row_key='path',
            pagination={
                'rowsPerPage': self.rows_per_page,
                'rowsPerPageOptions': self.rows_per_page_options,
                'sortBy': 'artist',
                'descending': False,
                'page': 1,
            },
        )

        props = 'dark dense flat bordered'
        if self.selectable:
            props += ' selection=single'
        self.table.props(props)
        self.table.classes('w-full')

        if self.on_select and self.selectable:
            self.table.on_select(lambda e: self.on_select(_selected_row(e)))

        if self.on_row_click:
            self.table.on('row-click', lambda e: self.on_row_click(e.args[1] if len(e.args) > 1 else None))

        return self.table

    def update(self, tracks: list[dict]) -> None:
        self._tracks = tracks
        if self.table:
            self.table.rows = tracks
            self.table.update()

    def clear_selection(self) -> None:
        if self.table:
            self.table.selected = []
            self.table.update()

    def set_sort(self, sort_by: str, descending: bool = False) -> None:
        if not self.table:
            return
        pagination = self.table.pagination or {}
        if not isinstance(pagination, dict):
            pagination = {}
        pagination = dict(pagination)
        pagination['sortBy'] = sort_by
        pagination['descending'] = descending
        pagination.setdefault('page', 1)
        self.table.pagination = pagination
        self.table.update()

    def set_rows_per_page(self, rows_per_page: int) -> None:
        self.rows_per_page = int(rows_per_page)
        if not self.table:
            return
        pagination = self.table.pagination or {}
        if not isinstance(pagination, dict):
            pagination = {}
        pagination = dict(pagination)
        pagination['rowsPerPage'] = self.rows_per_page
        pagination.setdefault('page', 1)
        self.table.pagination = pagination
        self.table.update()
