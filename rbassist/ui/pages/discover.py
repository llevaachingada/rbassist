"""Discover page - recommendations hero section."""

from __future__ import annotations

import numpy as np
from nicegui import ui

from ..state import get_state
from ..components.seed_card import SeedCard
from ..components.filters import FilterPanel
from ..components.track_table import TrackTable


class DiscoverPage:
    """Main recommendations page."""

    def __init__(self):
        self.state = get_state()
        self.recommendations: list[dict] = []
        self.rec_table: TrackTable | None = None

    def render(self) -> None:
        """Render the discover page."""
        with ui.row().classes("w-full gap-6 items-start"):
            # Left sidebar - seed + filters (30%)
            with ui.column().classes("w-80 gap-4 flex-shrink-0"):
                self.seed_card = SeedCard(on_change=self._on_seed_change)
                self.filter_panel = FilterPanel(on_change=self._on_filter_change)

                # Load track options
                indexed = self.state.get_indexed_paths()
                if indexed:
                    self.seed_card.set_track_options(indexed)

            # Right main area - recommendations (70%)
            with ui.column().classes("flex-1 gap-4"):
                # Header row
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label("Recommendations").classes("text-2xl font-bold text-white")
                    with ui.row().classes("gap-2"):
                        self.refresh_btn = ui.button(
                            "Refresh", icon="refresh", on_click=self._refresh_recommendations
                        ).props("flat dense").classes("bg-indigo-600 hover:bg-indigo-500")
                        self.count_label = ui.label("0 results").classes("text-gray-400")

                # Recommendations table
                with ui.card().classes("w-full bg-[#1a1a1a] border border-[#333] p-0"):
                    self.rec_table = TrackTable(
                        on_select=self._on_rec_select,
                        extra_columns=[
                            {"name": "dist", "label": "Distance", "field": "dist", "sortable": True, "align": "right"},
                            {"name": "key_rule", "label": "Key Rule", "field": "key_rule", "sortable": False, "align": "left"},
                        ],
                    )
                    self.rec_table.build()

                # Action buttons
                with ui.row().classes("w-full gap-2"):
                    ui.button("Select All", icon="select_all").props("flat dense").classes(
                        "bg-[#252525] hover:bg-[#333] text-gray-300"
                    )
                    ui.button("Add to Playlist", icon="playlist_add").props("flat dense").classes(
                        "bg-[#252525] hover:bg-[#333] text-gray-300"
                    )
                    ui.button("Export Selection", icon="download").props("flat dense").classes(
                        "bg-[#252525] hover:bg-[#333] text-gray-300"
                    )

    def _on_seed_change(self) -> None:
        """Handle seed track change."""
        self._refresh_recommendations()

    def _on_filter_change(self) -> None:
        """Handle filter change."""
        self._refresh_recommendations()

    def _on_rec_select(self, track: dict | None) -> None:
        """Handle recommendation selection."""
        if track:
            ui.notify(f"Selected: {track.get('artist', '')} - {track.get('title', '')}")

    def _refresh_recommendations(self) -> None:
        """Fetch and display recommendations."""
        seed = self.state.seed_track
        if not seed:
            ui.notify("Select a seed track first", type="warning")
            return

        if not self.state.has_index():
            ui.notify("No index found. Run 'rbassist index' first.", type="warning")
            return

        try:
            recs = self._get_recommendations(seed)
            self.recommendations = recs
            if self.rec_table:
                self.rec_table.update(recs)
            self.count_label.text = f"{len(recs)} results"
        except Exception as e:
            ui.notify(f"Error: {e}", type="negative")

    def _get_recommendations(self, seed_path: str, top: int = 50) -> list[dict]:
        """Get recommendations for seed track."""
        from rbassist.recommend import load_embedding_safe, IDX
        from rbassist.utils import camelot_relation, tempo_match
        import hnswlib
        import json

        meta = self.state.meta
        tracks = meta.get("tracks", {})
        seed_info = tracks.get(seed_path, {})

        # Load seed embedding
        emb_path = seed_info.get("embedding")
        if not emb_path:
            raise ValueError("Seed track has no embedding")

        seed_vec = load_embedding_safe(emb_path)
        if seed_vec is None:
            raise ValueError("Could not load seed embedding")

        # Load index
        paths_file = IDX / "paths.json"
        paths_map = json.loads(paths_file.read_text(encoding="utf-8"))

        index = hnswlib.Index(space="cosine", dim=seed_vec.shape[0])
        index.load_index(str(IDX / "hnsw.idx"))
        index.set_ef(64)

        # Query
        labels, dists = index.knn_query(seed_vec, k=min(top * 2, len(paths_map)))
        labels, dists = labels[0].tolist(), dists[0].tolist()

        # Filter and format results
        filters = self.state.filters
        seed_bpm = seed_info.get("bpm")
        seed_key = seed_info.get("key")

        results = []
        for label, dist in zip(labels, dists):
            path = paths_map[label]
            if path == seed_path:
                continue

            info = tracks.get(path, {})
            cand_bpm = info.get("bpm")
            cand_key = info.get("key")

            # Apply Camelot filter
            if filters.get("camelot"):
                ok, rule = camelot_relation(seed_key, cand_key)
                if not ok:
                    continue
            else:
                rule = "-"

            # Apply tempo filter
            if not tempo_match(
                seed_bpm, cand_bpm,
                pct=filters.get("tempo_pct", 6.0),
                allow_doubletime=filters.get("doubletime", True)
            ):
                continue

            results.append({
                "path": path,
                "artist": info.get("artist", ""),
                "title": info.get("title", path.split("\\")[-1].split("/")[-1]),
                "bpm": f"{cand_bpm:.0f}" if cand_bpm else "-",
                "key": cand_key or "-",
                "dist": f"{dist:.3f}",
                "key_rule": rule,
            })

            if len(results) >= top:
                break

        return results


# Page instance
_page: DiscoverPage | None = None


def render() -> None:
    """Render the discover page."""
    global _page
    _page = DiscoverPage()
    _page.render()
