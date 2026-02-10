"""Discover page - recommendations hero section."""

from __future__ import annotations

import numpy as np
from nicegui import ui

from ..state import get_state
from ..components.seed_card import SeedCard
from ..components.filters import FilterPanel
from ..components.track_table import TrackTable


def tempo_score(seed_bpm: float, cand_bpm: float, max_diff: float = 6.0) -> float:
    """Calculate BPM similarity score in [0, 1]."""
    if seed_bpm <= 0 or cand_bpm <= 0:
        return 0.0
    diff = abs(seed_bpm - cand_bpm)
    if max_diff > 0 and diff > max_diff:
        return 0.0
    if max_diff <= 0:
        max_diff = 6.0
    return max(0.0, 1.0 - diff / max_diff)


def camelot_relation_score(seed: str, cand: str) -> float:
    """Calculate key relation score in [0, 1] based on Camelot wheel."""
    if not seed or not cand:
        return 0.0
    if seed == cand:
        return 1.0

    try:
        n1, m1 = int(seed[:-1]), seed[-1].upper()
        n2, m2 = int(cand[:-1]), cand[-1].upper()
    except Exception:
        return 0.0

    if n1 == n2 and m1 != m2:
        return 0.8

    if (n1 - n2) % 12 in (1, 11):
        return 0.7

    return 0.0


def tag_similarity_score(seed_tags: set, cand_tags: set, prefer_tags: set = None) -> float:
    """Calculate tag similarity using Jaccard similarity."""
    if not seed_tags and not cand_tags:
        return 0.0

    if prefer_tags:
        all_tags = seed_tags | prefer_tags
    else:
        all_tags = seed_tags

    if not all_tags:
        return 0.0

    inter = len(cand_tags & all_tags)
    union = len(cand_tags | all_tags)

    if union == 0:
        return 0.0

    return inter / union


class DiscoverPage:
    """Main recommendations page with library browser."""

    def __init__(self):
        self.state = get_state()
        self.recommendations: list[dict] = []
        self.rec_table: TrackTable | None = None
        self.browse_mode = False

    def render(self) -> None:
        """Render the discover page."""
        if not self.state.has_index():
            with ui.card().classes("bg-[#1a1a1a] border border-[#333] p-4 w-full"):
                ui.label("No index found").classes("text-lg font-semibold text-red-400")
                ui.label("Run Embed + Analyze + Index from Settings or Library to enable recommendations.").classes(
                    "text-gray-300 text-sm"
                )
            return

        with ui.row().classes("w-full gap-6 items-start"):
            # Left sidebar - seed + filters (30%)
            with ui.column().classes("w-80 gap-4 flex-shrink-0"):
                with ui.row().classes("w-full gap-2"):
                    self.mode_btn = ui.button(
                        "Browse Library",
                        icon="library_music",
                        on_click=self._toggle_browse,
                    ).props("flat dense").classes("flex-1 bg-purple-600 hover:bg-purple-500 text-sm")

                self.seed_card = SeedCard(on_change=self._on_seed_change)
                self.filter_panel = FilterPanel(on_change=self._on_filter_change)

                indexed = self.state.get_indexed_paths()
                if indexed:
                    self.seed_card.set_track_options(indexed)

            # Right main area - recommendations (70%)
            with ui.column().classes("flex-1 gap-4"):
                with ui.row().classes("w-full items-center justify-between"):
                    self.page_title = ui.label("Recommendations").classes("text-2xl font-bold text-white")
                    with ui.row().classes("gap-2"):
                        self.refresh_btn = ui.button(
                            "Refresh", icon="refresh", on_click=self._refresh_recommendations
                        ).props("flat dense").classes("bg-indigo-600 hover:bg-indigo-500")
                        self.reset_sort_btn = ui.button(
                            "Reset Sort", icon="sort", on_click=self._reset_sort
                        ).props("flat dense").classes("bg-[#252525] hover:bg-[#333] text-gray-300")
                        self.count_label = ui.label("0 results").classes("text-gray-400")

                with ui.card().classes("w-full bg-[#1a1a1a] border border-[#333] p-0"):
                    self.rec_table = TrackTable(
                        on_select=self._on_rec_select,
                        on_row_click=self._on_rec_click,
                        extra_columns=[
                            {"name": "score", "label": "Match", "field": "score", "sortable": True, "align": "right"},
                            {"name": "dist", "label": "Distance", "field": "dist", "sortable": True, "align": "right"},
                            {"name": "key_rule", "label": "Key Rule", "field": "key_rule", "sortable": False, "align": "left"},
                        ],
                    )
                    self.rec_table.build()

                with ui.row().classes("w-full gap-2"):
                    ui.button(
                        "Use as Seed",
                        icon="psychology",
                        on_click=self._use_selected_as_seed,
                    ).props("flat dense").classes("bg-green-600 hover:bg-green-500 text-gray-200")
                    ui.button(
                        "Add to Playlist",
                        icon="playlist_add",
                        on_click=lambda: ui.notify("Playlist export coming soon", type="info"),
                    ).props("flat dense").classes("bg-[#252525] hover:bg-[#333] text-gray-300")
                    ui.button(
                        "Export Selection",
                        icon="download",
                        on_click=lambda: ui.notify("Selection export coming soon", type="info"),
                    ).props("flat dense").classes("bg-[#252525] hover:bg-[#333] text-gray-300")

    def _toggle_browse(self) -> None:
        """Toggle between recommendations and library browse mode."""
        self.browse_mode = not self.browse_mode

        if self.browse_mode:
            self.page_title.text = "Library Browser"
            self.mode_btn.text = "Back to Recommendations"
            self.mode_btn.props("icon=recommend color=indigo")
            self.refresh_btn.text = "Load All"
            self._show_library()
        else:
            self.page_title.text = "Recommendations"
            self.mode_btn.text = "Browse Library"
            self.mode_btn.props("icon=library_music color=purple")
            self.refresh_btn.text = "Refresh"
            if self.state.seed_track:
                self._refresh_recommendations()

        self.mode_btn.update()
        self.refresh_btn.update()

    def _show_library(self) -> None:
        """Show full library in browse mode."""
        tracks = self.state.meta.get("tracks", {})

        rows = []
        for path, info in tracks.items():
            bpm = info.get("bpm")
            key = info.get("key")

            rows.append({
                "path": path,
                "artist": info.get("artist", ""),
                "title": info.get("title", path.split("\\")[-1].split("/")[-1]),
                "bpm": f"{bpm:.0f}" if bpm else "-",
                "key": key or "-",
                "dist": "-",
                "key_rule": "-",
            })

        rows.sort(key=lambda r: (r["artist"].lower(), r["title"].lower()))

        if self.rec_table:
            self.rec_table.update(rows[:500])
        self.count_label.text = f"{len(rows)} tracks (showing {min(len(rows), 500)})"
        self.count_label.update()

    def _on_seed_change(self) -> None:
        """Handle seed track change."""
        if not self.browse_mode:
            self._refresh_recommendations()

    def _on_filter_change(self) -> None:
        """Handle filter change."""
        if self.browse_mode:
            self._show_library()
        else:
            self._refresh_recommendations()

    def _on_rec_select(self, track: dict | None) -> None:
        """Handle recommendation selection."""
        if track:
            ui.notify(f"Selected: {track.get('artist', '')} - {track.get('title', '')}")

    def _on_rec_click(self, track: dict | None) -> None:
        """Handle recommendation row click - quick preview."""
        if not track:
            return
        path = track.get("path")
        if not path:
            return
        info = self.state.meta.get("tracks", {}).get(path, {})
        bpm = info.get("bpm")
        key = info.get("key")
        tags = ", ".join(info.get("mytags", []) or []) or "No tags"
        bpm_text = f"{bpm:.0f} BPM" if isinstance(bpm, (int, float)) and bpm else "-- BPM"
        key_text = key or "-"

        ui.notify(
            f"{track.get('artist', '')} - {track.get('title', '')}\n{bpm_text} | {key_text} | {tags}",
            type="info",
            position="top-right",
        )

    def _use_selected_as_seed(self) -> None:
        """Use selected track as new seed."""
        if not self.rec_table or not self.rec_table.table:
            return
        selected = self.rec_table.table.selected
        if selected and len(selected) > 0:
            track = selected[0]
            if isinstance(track, dict):
                path = track.get("path")
            else:
                path = track
            if path:
                self.seed_card.set_seed(path)
                self._refresh_recommendations()
                ui.notify("Updated seed track", type="positive")
        else:
            ui.notify("Select a track first", type="warning")

    def _reset_sort(self) -> None:
        """Reset table sorting to default match score."""
        if self.rec_table:
            self.rec_table.set_sort("score", True)

    def _refresh_recommendations(self) -> None:
        """Fetch and display recommendations."""
        if self.browse_mode:
            self._show_library()
            return

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
            self.count_label.update()
        except Exception as e:
            ui.notify(f"Error: {e}", type="negative")

    def _get_recommendations(self, seed_path: str, top: int = 50) -> list[dict]:
        """Get recommendations for seed track with weighted scoring."""
        from rbassist.recommend import load_embedding_safe, IDX
        from rbassist.utils import camelot_relation, tempo_match
        import hnswlib
        import json

        try:
            from rbassist.features import bass_similarity, rhythm_similarity
        except Exception:
            bass_similarity = None
            rhythm_similarity = None

        meta = self.state.meta
        tracks = meta.get("tracks", {})
        seed_info = tracks.get(seed_path, {})

        emb_path = seed_info.get("embedding")
        if not emb_path:
            raise ValueError("Seed track has no embedding")

        seed_vec = load_embedding_safe(emb_path)
        if seed_vec is None:
            raise ValueError("Could not load seed embedding")

        paths_file = IDX / "paths.json"
        paths_map = json.loads(paths_file.read_text(encoding="utf-8"))

        index = hnswlib.Index(space="cosine", dim=seed_vec.shape[0])
        index.load_index(str(IDX / "hnsw.idx"))
        index.set_ef(64)

        labels, dists = index.knn_query(seed_vec, k=min(top * 4, len(paths_map)))
        labels, dists = labels[0].tolist(), dists[0].tolist()

        filters = self.state.filters
        weights = self.state.weights

        seed_bpm = float(seed_info.get("bpm") or 0.0)
        seed_key = str(seed_info.get("key") or "")
        seed_camelot = str(seed_info.get("camelot") or "")
        seed_features = seed_info.get("features", {})
        seed_tags = set(seed_info.get("tags", []) + seed_info.get("mytags", []))

        seed_bass_contour = np.array(
            seed_features.get("bass_contour", {}).get("contour", []),
            dtype=float,
        )
        seed_rhythm_contour = np.array(
            seed_features.get("rhythm_contour", {}).get("contour", []),
            dtype=float,
        )

        bpm_max_diff = float(filters.get("bpm_max_diff", 0.0))
        allowed_key_rel = set(filters.get("allowed_key_relations", []))
        require_tags = set(filters.get("require_tags", []))
        prefer_tags = set(filters.get("prefer_tags", []))

        weight_sum = sum(weights.values())
        if weight_sum <= 0:
            weight_sum = 1.0

        results = []
        for label, dist in zip(labels, dists):
            path = paths_map[label]
            if path == seed_path:
                continue

            info = tracks.get(path, {})
            cand_bpm = float(info.get("bpm") or 0.0)
            cand_key = str(info.get("key") or "")
            cand_camelot = str(info.get("camelot") or "")
            cand_features = info.get("features", {})
            cand_tags = set(info.get("tags", []) + info.get("mytags", []))

            if bpm_max_diff > 0 and seed_bpm > 0 and cand_bpm > 0:
                if abs(seed_bpm - cand_bpm) > bpm_max_diff:
                    continue

            if not tempo_match(
                seed_bpm, cand_bpm,
                pct=filters.get("tempo_pct", 6.0),
                allow_doubletime=filters.get("doubletime", True)
            ):
                continue

            if require_tags and not require_tags.issubset(cand_tags):
                continue

            key_score = camelot_relation_score(seed_camelot or seed_key, cand_camelot or cand_key)

            if allowed_key_rel:
                if key_score >= 0.99:
                    rel = "same"
                elif key_score >= 0.79:
                    rel = "relative"
                elif key_score >= 0.69:
                    rel = "neighbor"
                else:
                    rel = "other"

                if rel not in allowed_key_rel:
                    continue
            else:
                if key_score >= 0.99:
                    rel = "same"
                elif key_score >= 0.79:
                    rel = "relative"
                elif key_score >= 0.69:
                    rel = "neighbor"
                else:
                    ok, rel = camelot_relation(seed_key, cand_key)
                    if filters.get("camelot") and not ok:
                        continue
                    if not ok:
                        rel = "-"

            score = 0.0

            if weights.get("ann", 0.0):
                ann_score = 1.0 - float(dist)
                score += weights["ann"] * ann_score

            if weights.get("samples", 0.0):
                samples_val = float(cand_features.get("samples", 0.0))
                score += weights["samples"] * samples_val

            if weights.get("bass", 0.0) and bass_similarity is not None:
                cand_bass_contour = np.array(
                    cand_features.get("bass_contour", {}).get("contour", []),
                    dtype=float,
                )
                if seed_bass_contour.size and cand_bass_contour.size:
                    bass_score = float(bass_similarity(seed_bass_contour, cand_bass_contour))
                    score += weights["bass"] * bass_score

            if weights.get("rhythm", 0.0) and rhythm_similarity is not None:
                cand_rhythm_contour = np.array(
                    cand_features.get("rhythm_contour", {}).get("contour", []),
                    dtype=float,
                )
                if seed_rhythm_contour.size and cand_rhythm_contour.size:
                    rhythm_score = float(rhythm_similarity(seed_rhythm_contour, cand_rhythm_contour))
                    score += weights["rhythm"] * rhythm_score

            if weights.get("bpm", 0.0) and seed_bpm > 0 and cand_bpm > 0:
                bpm_score = tempo_score(seed_bpm, cand_bpm, bpm_max_diff or filters.get("tempo_pct", 6.0))
                score += weights["bpm"] * bpm_score

            if weights.get("key", 0.0):
                score += weights["key"] * key_score

            if weights.get("tags", 0.0):
                tag_score = tag_similarity_score(seed_tags, cand_tags, prefer_tags)
                score += weights["tags"] * tag_score

            score /= weight_sum

            results.append({
                "path": path,
                "artist": info.get("artist", ""),
                "title": info.get("title", path.split("\\")[-1].split("/")[-1]),
                "bpm": f"{cand_bpm:.0f}" if cand_bpm else "-",
                "key": cand_key or "-",
                "dist": round(float(dist), 3),
                "key_rule": rel,
                "score": round(float(score), 3),
            })

        results.sort(key=lambda r: r["score"], reverse=True)

        return results[:top]


_page: DiscoverPage | None = None


def render() -> None:
    """Render the discover page."""
    global _page
    _page = DiscoverPage()
    _page.render()
