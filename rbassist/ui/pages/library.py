"""Library page - track browser and operations."""

from __future__ import annotations

from nicegui import ui

from ..state import get_state
from ..components.track_table import TrackTable
from ..components.progress import ProgressPanel


def render() -> None:
    """Render the library page."""
    state = get_state()

    with ui.column().classes("w-full gap-4"):
        # Header with stats
        with ui.row().classes("w-full items-center justify-between"):
            ui.label("Library").classes("text-2xl font-bold text-white")
            with ui.row().classes("gap-4"):
                ui.badge(f"{state.get_track_count()} tracks", color="gray")
                ui.badge(f"{state.get_embedded_count()} embedded", color="indigo")
                ui.badge(f"{state.get_analyzed_count()} analyzed", color="purple")

        # Action buttons
        with ui.row().classes("w-full gap-2"):
            ui.button("Embed New", icon="memory", on_click=lambda: ui.notify("Embed coming soon")).props(
                "flat"
            ).classes("bg-indigo-600 hover:bg-indigo-500")
            ui.button("Analyze BPM/Key", icon="music_note", on_click=lambda: ui.notify("Analyze coming soon")).props(
                "flat"
            ).classes("bg-purple-600 hover:bg-purple-500")
            ui.button("Rebuild Index", icon="refresh", on_click=lambda: ui.notify("Index coming soon")).props(
                "flat"
            ).classes("bg-[#252525] hover:bg-[#333] text-gray-300")
            ui.button("Export XML", icon="download", on_click=lambda: ui.notify("Export coming soon")).props(
                "flat"
            ).classes("bg-[#252525] hover:bg-[#333] text-gray-300")

        # Progress panel (hidden by default)
        progress = ProgressPanel("Processing")

        # Search/filter bar
        with ui.row().classes("w-full gap-4 items-center"):
            search = ui.input(placeholder="Search tracks...").props("dark dense clearable").classes("flex-1")
            ui.select(
                ["All", "Has Embedding", "Needs Embedding", "Analyzed", "Not Analyzed"],
                value="All",
            ).props("dark dense").classes("w-48")

        # Track table
        tracks = state.meta.get("tracks", {})
        rows = []
        for path, info in list(tracks.items())[:500]:  # Limit for performance
            rows.append({
                "path": path,
                "artist": info.get("artist", ""),
                "title": info.get("title", path.split("\\")[-1].split("/")[-1]),
                "bpm": f"{info.get('bpm', 0):.0f}" if info.get("bpm") else "-",
                "key": info.get("key", "-"),
                "embedded": "Yes" if info.get("embedding") else "No",
                "analyzed": "Yes" if info.get("bpm") and info.get("key") else "No",
            })

        with ui.card().classes("w-full bg-[#1a1a1a] border border-[#333] p-0"):
            table = TrackTable(
                extra_columns=[
                    {"name": "embedded", "label": "Embedded", "field": "embedded", "sortable": True, "align": "center"},
                    {"name": "analyzed", "label": "Analyzed", "field": "analyzed", "sortable": True, "align": "center"},
                ],
            )
            table.build()
            table.update(rows)

        ui.label(f"Showing {len(rows)} of {len(tracks)} tracks").classes("text-gray-500 text-sm")
