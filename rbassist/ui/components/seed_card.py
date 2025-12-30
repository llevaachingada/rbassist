"""Enhanced seed track display card with better search and library integration."""

from __future__ import annotations

from typing import Callable
from nicegui import ui

from ..state import get_state


class SeedCard:
    """Card displaying the current seed track with improved search."""

    def __init__(self, on_change: Callable[[], None] | None = None):
        self.on_change = on_change
        self.state = get_state()
        self._track_options: list[str] = []
        self._filtered_options: list[str] = []

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

            # Enhanced search
            ui.label("Search tracks:").classes("text-gray-400 text-sm mb-1")

            with ui.row().classes("w-full gap-2 items-center mb-2"):
                self.search_input = ui.input(
                    placeholder="Type artist, title, or path..."
                ).props("dark dense clearable").classes("flex-1")

                self.result_count = ui.label("0 results").classes("text-gray-500 text-xs")

            # Results dropdown
            self.results_container = ui.column().classes(
                "w-full max-h-96 overflow-y-auto bg-[#252525] rounded border border-[#333]"
            )
            self.results_container.visible = False

            self.search_input.on("update:model-value", self._on_search)
            self.search_input.on("focus", lambda: self._show_results())

            # Quick filters
            with ui.row().classes("gap-2 flex-wrap mt-2"):
                ui.button("Show All", on_click=lambda: self._apply_filter("")).props("flat dense").classes(
                    "bg-[#252525] hover:bg-[#333] text-gray-300 text-xs"
                )
                ui.button("Embedded", on_click=lambda: self._apply_filter("embedded")).props("flat dense").classes(
                    "bg-[#252525] hover:bg-[#333] text-gray-300 text-xs"
                )
                ui.button("Analyzed", on_click=lambda: self._apply_filter("analyzed")).props("flat dense").classes(
                    "bg-[#252525] hover:bg-[#333] text-gray-300 text-xs"
                )

    def _show_results(self) -> None:
        """Show results dropdown when search is focused."""
        if self._filtered_options:
            self.results_container.visible = True
            self._render_results()

    def _hide_results(self) -> None:
        """Hide results dropdown."""
        self.results_container.visible = False

    def _apply_filter(self, filter_type: str) -> None:
        """Apply quick filter to track list."""
        tracks = self.state.meta.get("tracks", {})

        if filter_type == "embedded":
            filtered = [p for p in self._track_options if tracks.get(p, {}).get("embedding")]
        elif filter_type == "analyzed":
            filtered = [p for p in self._track_options if tracks.get(p, {}).get("bpm") and tracks.get(p, {}).get("key")]
        else:
            filtered = self._track_options

        self._filtered_options = filtered[:1000]
        self.result_count.text = f"{len(self._filtered_options)} results"
        self.result_count.update()
        self._render_results()
        self.results_container.visible = True

    def _on_search(self, e) -> None:
        """Filter track options based on search with improved matching."""
        query = (e.args or "").lower().strip()
        tracks = self.state.meta.get("tracks", {})

        if not query:
            self._filtered_options = self._track_options[:1000]
        else:
            # Multi-term search (all terms must match)
            terms = query.split()
            filtered = []

            for p in self._track_options:
                info = tracks.get(p, {})
                artist = (info.get("artist", "") or "").lower()
                title = (info.get("title", "") or p.split("\\")[-1].split("/")[-1]).lower()
                path_lower = p.lower()

                if all(
                    term in artist or term in title or term in path_lower
                    for term in terms
                ):
                    filtered.append(p)
                    if len(filtered) >= 1000:
                        break

            self._filtered_options = filtered

        self.result_count.text = f"{len(self._filtered_options)} results"
        self.result_count.update()
        self._render_results()
        self.results_container.visible = True

    def _render_results(self) -> None:
        """Render search results as clickable items."""
        self.results_container.clear()
        tracks = self.state.meta.get("tracks", {})

        with self.results_container:
            if not self._filtered_options:
                ui.label("No tracks found").classes("text-gray-500 italic p-2")
                return

            for p in self._filtered_options[:100]:
                info = tracks.get(p, {})
                artist = info.get("artist", "")
                title = info.get("title", p.split("\\")[-1].split("/")[-1])
                bpm = info.get("bpm")
                key = info.get("key")

                with ui.row().classes(
                    "w-full p-2 hover:bg-[#333] cursor-pointer items-center gap-2"
                ).on("click", lambda path=p: self._select_track(path)):
                    with ui.column().classes("flex-1 gap-0"):
                        if artist:
                            ui.label(f"{artist} - {title}").classes("text-gray-200 text-sm")
                        else:
                            ui.label(title).classes("text-gray-200 text-sm")

                        with ui.row().classes("gap-1"):
                            if bpm:
                                ui.badge(f"{bpm:.0f}", color="indigo").classes("text-xs")
                            if key:
                                ui.badge(key, color="purple").classes("text-xs")

    def _select_track(self, path: str) -> None:
        """Handle track selection from results."""
        self.state.seed_track = path
        self._update_display(path)
        self._hide_results()

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

        if bpm:
            self.bpm_badge.props("color=indigo")
        if key:
            self.key_badge.props("color=purple")

    def set_track_options(self, paths: list[str]) -> None:
        """Set available track options."""
        self._track_options = paths
        self._filtered_options = paths[:1000]
        self.result_count.text = f"{len(self._track_options)} total tracks"
        self.result_count.update()

    def set_seed(self, path: str) -> None:
        """Programmatically set seed track."""
        self.state.seed_track = path
        self._update_display(path)
