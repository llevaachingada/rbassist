"""Crate/Playlist Expander - Get recommendations from multiple seed tracks."""

from __future__ import annotations

import numpy as np
from nicegui import ui

from ..state import get_state
from ..components.track_table import TrackTable


class CrateExpander:
    """Expand a crate/playlist with similar recommendations."""

    def __init__(self):
        self.state = get_state()
        self.selected_seeds: list[str] = []
        self.recommendations: list[dict] = []

    def render(self) -> None:
        """Render the crate expander interface."""
        with ui.column().classes("w-full gap-4"):
            ui.label("Crate Expander").classes("text-2xl font-bold text-white")
            ui.label(
                "Select multiple tracks from your library to get recommendations that match the vibe of the group."
            ).classes("text-gray-400 text-sm mb-4")

            with ui.row().classes("w-full gap-6 items-start"):
                # Left: Seed selection
                with ui.card().classes("w-96 bg-[#1a1a1a] border border-[#333] p-4"):
                    ui.label("Seed Tracks").classes("text-lg font-semibold text-gray-200 mb-3")

                    # Search and add tracks
                    search_input = ui.input(
                        placeholder="Search to add tracks..."
                    ).props("dark dense").classes("w-full mb-2")

                    search_results = ui.column().classes(
                        "w-full max-h-48 overflow-y-auto bg-[#252525] rounded border border-[#333] mb-3"
                    )
                    search_results.visible = False

                    def search_tracks(e) -> None:
                        query = (e.args or "").lower().strip()
                        search_results.clear()

                        if not query:
                            search_results.visible = False
                            return

                        tracks = self.state.meta.get("tracks", {})
                        matches = []

                        for p, info in tracks.items():
                            if p in self.selected_seeds:
                                continue

                            artist = (info.get("artist", "") or "").lower()
                            title = (info.get("title", "") or "").lower()

                            if query in artist or query in title or query in p.lower():
                                matches.append((p, info))
                                if len(matches) >= 50:
                                    break

                        with search_results:
                            for p, info in matches:
                                artist = info.get("artist", "")
                                title = info.get("title", p.split("\\")[-1].split("/")[-1])

                                with ui.row().classes(
                                    "w-full p-2 hover:bg-[#333] cursor-pointer"
                                ).on("click", lambda path=p: add_seed(path)):
                                    ui.label(f"{artist} - {title}" if artist else title).classes(
                                        "text-gray-200 text-sm"
                                    )

                        search_results.visible = len(matches) > 0

                    def add_seed(path: str) -> None:
                        if path not in self.selected_seeds:
                            self.selected_seeds.append(path)
                            render_seeds()
                        search_input.value = ""
                        search_results.visible = False

                    search_input.on("update:model-value", search_tracks)

                    ui.separator().classes("my-3")

                    # Selected seeds list
                    seeds_container = ui.column().classes("w-full gap-2")

                    def render_seeds() -> None:
                        seeds_container.clear()
                        tracks = self.state.meta.get("tracks", {})

                        with seeds_container:
                            if not self.selected_seeds:
                                ui.label("No tracks selected").classes("text-gray-500 italic")
                            else:
                                for p in self.selected_seeds:
                                    info = tracks.get(p, {})
                                    artist = info.get("artist", "")
                                    title = info.get("title", p.split("\\")[-1].split("/")[-1])

                                    with ui.row().classes("w-full items-center gap-2"):
                                        ui.label(f"{artist} - {title}" if artist else title).classes(
                                            "text-gray-300 text-sm flex-1"
                                        )
                                        ui.button(
                                            icon="close",
                                            on_click=lambda path=p: remove_seed(path),
                                        ).props("flat round dense").classes("text-gray-400")

                    def remove_seed(path: str) -> None:
                        if path in self.selected_seeds:
                            self.selected_seeds.remove(path)
                            render_seeds()

                    render_seeds()

                    ui.separator().classes("my-3")

                    # Controls
                    count_input = ui.number(
                        value=25, min=5, max=100, step=5
                    ).props("dark dense label='Tracks to suggest'").classes("w-full mb-2")

                    diversity_slider = ui.slider(
                        min=0, max=1, step=0.1, value=0.3
                    ).props("dark label-always").classes("w-full")
                    ui.label("Diversity: Lower = More similar to seeds, Higher = More varied").classes(
                        "text-gray-500 text-xs mb-3"
                    )

                    def generate_recs() -> None:
                        if len(self.selected_seeds) < 1:
                            ui.notify("Add at least one seed track", type="warning")
                            return

                        try:
                            recs = self._get_multi_seed_recommendations(
                                self.selected_seeds,
                                top=int(count_input.value or 25),
                                diversity=float(diversity_slider.value or 0.3),
                            )
                            self.recommendations = recs
                            rec_table.update(recs)
                            result_count.text = f"{len(recs)} results"
                            result_count.update()
                            ui.notify(f"Found {len(recs)} recommendations", type="positive")
                        except Exception as e:
                            ui.notify(f"Error: {e}", type="negative")

                    ui.button(
                        "Generate Recommendations",
                        icon="auto_awesome",
                        on_click=generate_recs,
                    ).props("flat").classes("bg-indigo-600 hover:bg-indigo-500 w-full")

                    def clear_seeds() -> None:
                        self.selected_seeds.clear()
                        render_seeds()
                        rec_table.update([])
                        result_count.text = "0 results"
                        result_count.update()

                    ui.button("Clear All", icon="clear", on_click=clear_seeds).props("flat").classes(
                        "bg-[#252525] hover:bg-[#333] text-gray-300 w-full mt-2"
                    )

                # Right: Results
                with ui.column().classes("flex-1 gap-4"):
                    with ui.row().classes("w-full items-center justify-between"):
                        ui.label("Recommendations").classes("text-xl font-bold text-white")
                        result_count = ui.label("0 results").classes("text-gray-400")

                    with ui.card().classes("w-full bg-[#1a1a1a] border border-[#333] p-0"):
                        rec_table = TrackTable(
                            extra_columns=[
                                {"name": "score", "label": "Match", "field": "score", "sortable": True, "align": "right"},
                                {"name": "key_rule", "label": "Key", "field": "key_rule", "sortable": False, "align": "left"},
                            ]
                        )
                        rec_table.build()

    def _get_multi_seed_recommendations(
        self, seed_paths: list[str], top: int = 25, diversity: float = 0.3
    ) -> list[dict]:
        """Get recommendations from multiple seed tracks using averaged embeddings."""
        from rbassist.recommend import load_embedding_safe, IDX
        from rbassist.utils import camelot_relation, tempo_match
        import hnswlib
        import json

        meta = self.state.meta
        tracks = meta.get("tracks", {})

        seed_vecs = []
        seed_bpms = []
        seed_keys = []

        for path in seed_paths:
            info = tracks.get(path, {})
            emb_path = info.get("embedding")
            if not emb_path:
                continue

            vec = load_embedding_safe(emb_path)
            if vec is None:
                continue

            seed_vecs.append(vec)
            if info.get("bpm"):
                seed_bpms.append(float(info["bpm"]))
            if info.get("key"):
                seed_keys.append(str(info["key"]))

        if not seed_vecs:
            raise ValueError("No valid seed embeddings found")

        combined_vec = np.mean(np.stack(seed_vecs, axis=0), axis=0).astype(np.float32)
        avg_bpm = np.mean(seed_bpms) if seed_bpms else None

        paths_file = IDX / "paths.json"
        paths_map = json.loads(paths_file.read_text(encoding="utf-8"))

        index = hnswlib.Index(space="cosine", dim=combined_vec.shape[0])
        index.load_index(str(IDX / "hnsw.idx"))
        index.set_ef(64)

        query_k = min(top * 10, len(paths_map))
        labels, dists = index.knn_query(combined_vec, k=query_k)
        labels, dists = labels[0].tolist(), dists[0].tolist()

        filters = self.state.filters

        candidates = []
        for label, dist in zip(labels, dists):
            path = paths_map[label]
            if path in seed_paths:
                continue

            info = tracks.get(path, {})
            cand_bpm = float(info.get("bpm") or 0.0)
            cand_key = str(info.get("key") or "")

            if avg_bpm and cand_bpm:
                if not tempo_match(
                    avg_bpm, cand_bpm,
                    pct=filters.get("tempo_pct", 6.0),
                    allow_doubletime=filters.get("doubletime", True),
                ):
                    continue

            if filters.get("camelot") and seed_keys and cand_key:
                compatible = any(camelot_relation(sk, cand_key)[0] for sk in seed_keys)
                if not compatible:
                    continue

            base_score = 1.0 - float(dist)

            diversity_penalty = 0.0
            if diversity > 0 and candidates:
                for prev_path, _ in candidates[-5:]:
                    prev_info = tracks.get(prev_path, {})
                    prev_emb = load_embedding_safe(prev_info.get("embedding"))
                    if prev_emb is not None:
                        cand_emb = load_embedding_safe(info.get("embedding"))
                        if cand_emb is not None:
                            similarity = np.dot(prev_emb, cand_emb)
                            diversity_penalty += similarity * diversity

            final_score = base_score - (diversity_penalty / max(len(candidates[-5:]), 1))
            candidates.append((path, final_score))

        candidates.sort(key=lambda x: x[1], reverse=True)

        results = []
        for path, score in candidates[:top]:
            info = tracks.get(path, {})
            cand_bpm = info.get("bpm")
            cand_key = info.get("key")

            key_rule = "-"
            if cand_key and seed_keys:
                for sk in seed_keys:
                    ok, rule = camelot_relation(sk, cand_key)
                    if ok and rule != "-":
                        key_rule = rule
                        break

            results.append({
                "path": path,
                "artist": info.get("artist", ""),
                "title": info.get("title", path.split("\\")[-1].split("/")[-1]),
                "bpm": f"{cand_bpm:.0f}" if cand_bpm else "-",
                "key": cand_key or "-",
                "score": f"{score:.3f}",
                "key_rule": key_rule,
            })

        return results


def render() -> None:
    """Render the crate expander page."""
    expander = CrateExpander()
    expander.render()
