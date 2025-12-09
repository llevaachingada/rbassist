from __future__ import annotations

import asyncio
from pathlib import Path
from nicegui import ui

from ..state import get_state
from ..components.track_table import TrackTable
from rbassist.utils import walk_audio
from rbassist.embed import build_embeddings
from rbassist.analyze import analyze_bpm_key
from rbassist.recommend import build_index

def render() -> None:
    """Render the library page."""
    state = get_state()
    state.refresh_meta()

    with ui.column().classes("w-full gap-4"):
        # Header with stats
        with ui.row().classes("w-full items-center justify-between"):
            ui.label("Library").classes("text-2xl font-bold text-white")
            with ui.row().classes("gap-4"):
                ui.badge(f"{state.get_track_count()} tracks", color="gray")
                ui.badge(f"{state.get_embedded_count()} embedded", color="indigo")
                ui.badge(f"{state.get_analyzed_count()} analyzed", color="purple")

        # Folder selection
        folder_list = ui.label(f"Folders: {', '.join(state.music_folders) or 'No folders selected'}").classes("text-lg")

        with ui.row().classes("w-full gap-4"):
            ui.button(
                "Analyze Library",
                icon="music_note",
                on_click=lambda: ui.notify(
                    "Use Settings → Embed + Analyze + Index to run the full pipeline.",
                    type="info",
                ),
            ).classes("w-1/2 bg-blue-600 text-white")

        # Rest of the original track table rendering remains the same
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
