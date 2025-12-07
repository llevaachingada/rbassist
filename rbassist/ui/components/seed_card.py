"""Seed track display card."""

from __future__ import annotations

from typing import Callable
from nicegui import ui

from ..state import get_state


class SeedCard:
    """Card displaying the current seed track."""

    def __init__(self, on_change: Callable[[], None] | None = None):
        self.on_change = on_change
        self.state = get_state()
        self._track_options: list[str] = []

        with ui.card().classes("bg-[#1a1a1a] border border-[#333] p-4 w-full"):
            ui.label("Seed Track").classes("text-lg font-semibold text-gray-200 mb-3")

            # Track info display
            with ui.column().classes("w-full gap-1 mb-3") as self.info_container:
                self.artist_label = ui.label("No track selected").classes("text-xl text-white font-medium")
                self.title_label = ui.label("").classes("text-lg text-gray-300")
                with ui.row().classes("gap-4 mt-2"):
                    self.bpm_badge = ui.badge("--", color="gray").classes("text-sm")
                    self.key_badge = ui.badge("--", color="gray").classes("text-sm")

            ui.separator().classes("my-3")

            # Search/select
            ui.label("Search or select:").classes("text-gray-400 text-sm mb-1")
            self.search_input = ui.input(
                placeholder="Type to search tracks..."
            ).props("dark dense clearable").classes("w-full mb-2")

            self.track_select = ui.select(
                options=[],
                with_input=True,
                on_change=self._on_select,
            ).props("dark dense clearable use-input").classes("w-full")

            self.search_input.on("update:model-value", self._on_search)

    def _on_search(self, e) -> None:
        """Filter track options based on search."""
        query = (e.args or "").lower()
        tracks = self.state.meta.get("tracks", {})

        if not query:
            # Show first 100 tracks
            options = []
            for p in self._track_options[:500]:
                info = tracks.get(p, {})
                artist = info.get("artist", "")
                title = info.get("title", p.split("\\")[-1].split("/")[-1])
                if artist:
                    label = f"{artist} - {title}"
                else:
                    label = title
                options.append(label)
            self.track_select.options = options[:100]
        else:
            # Filter by query
            filtered = []
            for p in self._track_options:
                info = tracks.get(p, {})
                artist = info.get("artist", "")
                title = info.get("title", p.split("\\")[-1].split("/")[-1])
                if artist:
                    label = f"{artist} - {title}"
                else:
                    label = title

                if query in label.lower() or query in p.lower():
                    filtered.append(label)
                    if len(filtered) >= 100:
                        break

            self.track_select.options = filtered
        self.track_select.update()

    def _on_select(self, e) -> None:
        """Handle track selection."""
        selected = e.value if e else None
        if not selected:
            return

        # Find the actual path from the label
        tracks = self.state.meta.get("tracks", {})
        path = None
        for p in self._track_options:
            info = tracks.get(p, {})
            artist = info.get("artist", "")
            title = info.get("title", p.split("\\")[-1].split("/")[-1])
            if artist:
                label = f"{artist} - {title}"
            else:
                label = title

            if label == selected:
                path = p
                break

        if not path:
            return

        self.state.seed_track = path
        self._update_display(path)

        if self.on_change:
            self.on_change()

    def _update_display(self, path: str) -> None:
        """Update card display with track info."""
        tracks = self.state.meta.get("tracks", {})
        info = tracks.get(path, {})

        artist = info.get("artist", "Unknown Artist")
        title = info.get("title", path.split("\\")[-1].split("/")[-1])
        bpm = info.get("bpm")
        key = info.get("key")

        self.artist_label.text = artist
        self.title_label.text = title
        self.bpm_badge.text = f"{bpm:.0f} BPM" if bpm else "--"
        self.key_badge.text = key or "--"

        # Color badges
        if bpm:
            self.bpm_badge.props("color=indigo")
        if key:
            self.key_badge.props("color=purple")

    def set_track_options(self, paths: list[str]) -> None:
        """Set available track options."""
        self._track_options = paths

        # Format options with artist - title
        tracks = self.state.meta.get("tracks", {})
        options = []
        for p in paths[:500]:  # Limit for performance
            info = tracks.get(p, {})
            artist = info.get("artist", "")
            title = info.get("title", p.split("\\")[-1].split("/")[-1])
            if artist:
                label = f"{artist} - {title}"
            else:
                label = title
            options.append(label)

        self.track_select.options = options[:100]
        self.track_select.update()

    def set_seed(self, path: str) -> None:
        """Programmatically set seed track."""
        self.state.seed_track = path
        self.track_select.value = path
        self._update_display(path)
