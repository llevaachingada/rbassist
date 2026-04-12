"""Discover page - recommendations hero section."""

from __future__ import annotations

import asyncio
from nicegui import ui

from rbassist.ui_services.discover import (
    audio_distance_note as _audio_distance_note,
    bpm_summary_text as _bpm_summary_text,
    build_recommendation_rows,
    build_track_detail,
    camelot_relation_score,
    plain_key_fit as _plain_key_fit,
    should_apply_refresh_result as _should_apply_refresh_result,
    should_continue_refresh_drain as _should_continue_refresh_drain,
    should_start_refresh_task as _should_start_refresh_task,
    tag_similarity_score,
    tempo_score,
)
from rbassist.ui_services.library import (
    bpm_alert_text as _bpm_alert_text,
    build_library_rows,
    format_bpm_cell as _format_bpm_cell,
    format_bpm_metric as _format_bpm_metric,
)
from ..jobs import complete_job, fail_job, start_job, update_job
from ..state import get_state
from ..components.seed_card import SeedCard
from ..components.filters import FilterPanel
from ..components.track_table import TrackTable


class DiscoverPage:
    """Main recommendations page with library browser."""

    def __init__(self):
        self.state = get_state()
        self.recommendations: list[dict] = []
        self.rec_table: TrackTable | None = None
        self.browse_mode = False
        self.refresh_job_id: str | None = None
        self._refresh_request_id = 0
        self._latest_refresh_request_id = 0
        self._refresh_task: asyncio.Task | None = None
        self.detail_card = None
        self.detail_title = None
        self.detail_summary = None
        self.detail_metrics = None
        self.detail_note = None
        self.refresh_status = None
        self.refresh_hint = None

    def _set_recommendation_table_mode(self) -> None:
        if not self.rec_table or not self.rec_table.table:
            return
        self.rec_table.table.columns = list(self.rec_table.columns)
        self.rec_table.table.update()

    def _set_library_table_mode(self) -> None:
        if not self.rec_table or not self.rec_table.table:
            return
        self.rec_table.table.columns = list(self.rec_table.columns[:4])
        self.rec_table.table.update()

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
                self.refresh_status = ui.label("Recommendation refresh is idle.").classes("text-gray-500 text-sm")
                self.refresh_hint = ui.label(
                    "New seed or filter changes replace older refreshes before stale results can land."
                ).classes("text-gray-500 text-xs")

                with ui.card().classes("w-full bg-[#1a1a1a] border border-[#333] p-4"):
                    ui.label("How recommendations work").classes("text-sm font-medium text-gray-200")
                    ui.label(
                        "We start with tracks that sound close to your seed, then rerank them using the tempo, harmonic, groove, bass, and tag settings in the left panel."
                    ).classes("text-gray-400 text-sm")
                    ui.label(
                        "Overall fit is the final score. Audio distance is the raw sound-distance from the seed, so lower is closer."
                    ).classes("text-gray-500 text-xs mt-1")

                with ui.card().classes("w-full bg-[#1a1a1a] border border-[#333] p-0"):
                    self.rec_table = TrackTable(
                        on_select=self._on_rec_select,
                        on_row_click=self._on_rec_click,
                        extra_columns=[
                            {"name": "rekordbox_bpm", "label": "RB BPM", "field": "rekordbox_bpm", "sortable": True, "align": "right"},
                            {"name": "rbassist_bpm", "label": "Assist BPM", "field": "rbassist_bpm", "sortable": True, "align": "right"},
                            {"name": "bpm_alert", "label": "Tempo Note", "field": "bpm_alert", "sortable": True, "align": "left"},
                            {"name": "score", "label": "Overall fit", "field": "score", "sortable": True, "align": "right"},
                            {"name": "dist", "label": "Audio distance", "field": "dist", "sortable": True, "align": "right"},
                            {"name": "key_rule", "label": "Harmonic fit", "field": "key_rule", "sortable": False, "align": "left"},
                        ],
                    )
                    self.rec_table.build()
                    self._set_recommendation_table_mode()

                with ui.card().classes("w-full bg-[#151515] border border-[#2a2a2a] p-4"):
                    ui.label("Why this track showed up").classes("text-sm font-medium text-gray-200")
                    self.detail_title = ui.label("Click any row to see a plain-English explanation.").classes(
                        "text-gray-300 text-sm"
                    )
                    self.detail_summary = ui.label(
                        "You will see the overall fit, raw audio distance, harmonic relationship, and the track's core metadata."
                    ).classes("text-gray-400 text-sm")
                    self.detail_metrics = ui.label("").classes("text-gray-500 text-xs")
                    self.detail_note = ui.label(
                        "This panel explains the result; it does not change the score."
                    ).classes("text-gray-500 text-xs mt-1")

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
            self._latest_refresh_request_id += 1

        if self.browse_mode:
            self.page_title.text = "Library Browser"
            self.mode_btn.text = "Back to Recommendations"
            self.mode_btn.props("icon=recommend color=indigo")
            self.refresh_btn.text = "Load All"
            self._set_library_table_mode()
            self._set_refresh_state(running=False, status="Library browse mode is active.")
            self._show_library()
        else:
            self.page_title.text = "Recommendations"
            self.mode_btn.text = "Browse Library"
            self.mode_btn.props("icon=library_music color=purple")
            self.refresh_btn.text = "Refresh"
            self._set_recommendation_table_mode()
            if self.state.seed_track:
                self._refresh_recommendations()
            else:
                if self.rec_table:
                    self.rec_table.update([])
                self.count_label.text = "0 results"
                self.count_label.update()
                self._set_detail_card(
                    title="Recommendations",
                    summary="Select a seed track to see ranked matches.",
                    metrics="Overall fit, audio distance, and harmonic fit appear after a recommendation run.",
                    note="Browse mode can show your library without a seed, but recommendation mode needs one.",
                )
                self._set_refresh_state(running=False, status="Select a seed track to refresh recommendations.")

        self.mode_btn.update()
        self.refresh_btn.update()

    def _show_library(self) -> None:
        """Show full library in browse mode."""
        rows = build_library_rows(self.state.meta)

        if self.rec_table:
            self.rec_table.update(rows[:500])
            self.rec_table.set_sort("artist", False)
        self.count_label.text = f"{len(rows)} tracks (showing {min(len(rows), 500)})"
        self.count_label.update()
        self._set_detail_card(
            title="Library browse mode",
            summary="This table is just a library view. Switch back to Recommendations to see ranked matches and score explanations.",
            metrics="Audio distance and harmonic fit are only meaningful in recommendation mode.",
            note="Click a row here for track metadata only.",
        )
        self._set_refresh_state(running=False, status=f"Library browse ready ({len(rows)} tracks, showing {min(len(rows), 500)}).")

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
        """Handle recommendation row click."""
        if not track:
            return
        path = track.get("path")
        if not path:
            return
        info = self.state.meta.get("tracks", {}).get(path, {})
        detail = build_track_detail(path=path, track=track, info=info, browse_mode=self.browse_mode)
        self._set_detail_card(
            title=detail["title"],
            summary=detail["summary"],
            metrics=detail["metrics"],
            note=detail["note"],
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
            if self.browse_mode:
                self.rec_table.set_sort("artist", False)
            else:
                self.rec_table.set_sort("score", True)

    def _refresh_recommendations(self) -> None:
        """Fetch and display recommendations."""
        if self.browse_mode:
            self._show_library()
            return
        self._refresh_request_id += 1
        request_id = self._refresh_request_id
        self._latest_refresh_request_id = request_id
        if _should_start_refresh_task(
            running=self._refresh_task is not None and not self._refresh_task.done()
        ):
            self._refresh_task = asyncio.create_task(self._drain_refresh_requests())
        else:
            self._set_refresh_state(running=True, status="Queued a newer recommendation request...")

    async def _drain_refresh_requests(self) -> None:
        """Run at most one active refresh task while coalescing newer requests."""
        try:
            while True:
                request_id = self._latest_refresh_request_id
                await self._refresh_recommendations_async(request_id)
                if not _should_continue_refresh_drain(
                    completed_request_id=request_id,
                    latest_request_id=self._latest_refresh_request_id,
                    browse_mode=self.browse_mode,
                ):
                    break
        finally:
            self._refresh_task = None

    async def _refresh_recommendations_async(self, request_id: int) -> None:
        """Refresh recommendations without blocking the UI thread."""
        if self.browse_mode or request_id != self._latest_refresh_request_id:
            return

        seed = self.state.seed_track
        if not seed:
            ui.notify("Select a seed track first", type="warning")
            self._set_refresh_state(running=False, status="Select a seed track to refresh recommendations.")
            return

        if not self.state.has_index():
            ui.notify("No index found. Run 'rbassist index' first.", type="warning")
            self._set_refresh_state(running=False, status="No index found yet.")
            return

        seed_name = str(seed).split("\\")[-1].split("/")[-1]
        filters = dict(self.state.filters)
        weights = dict(self.state.weights)
        meta = self.state.meta
        job = start_job(
            "discover_refresh",
            phase="ranking",
            message=f"Refreshing recommendations for {seed_name}...",
            progress=0.1,
            result={"seed": seed, "request_id": request_id},
        )
        self.refresh_job_id = job.job_id
        self._set_refresh_state(running=True, status=f"Refreshing recommendations for {seed_name}...")
        try:
            recs = await asyncio.to_thread(
                self._get_recommendations,
                seed,
                50,
                meta,
                filters,
                weights,
            )
            if not _should_apply_refresh_result(
                request_id=request_id,
                latest_request_id=self._latest_refresh_request_id,
                browse_mode=self.browse_mode,
            ):
                update_job(
                    job.job_id,
                    status="cancelled",
                    phase="superseded",
                    message="Superseded by a newer recommendation request",
                    progress=1.0,
                    finished=True,
                )
                return
            self.recommendations = recs
            if self.rec_table:
                self.rec_table.update(recs)
                self.rec_table.set_sort("score", True)
            self.count_label.text = f"{len(recs)} results"
            self.count_label.update()
            self._set_recommendation_table_mode()
            self._set_detail_card(
                title="Why this track showed up",
                summary="Click any result row to see a plain-English explanation of the score and metadata.",
                metrics="Overall fit is the final ranking. Audio distance is the raw audio match, where lower means closer.",
                note="Use the left-side filters when you want to steer the ranking.",
            )
            complete_job(
                job.job_id,
                phase="completed",
                message=f"Recommendations ready ({len(recs)} result(s))",
                result={"seed": seed, "request_id": request_id, "results_total": len(recs)},
            )
            self._set_refresh_state(running=False, status=f"{len(recs)} recommendation(s) ready.")
        except Exception as e:
            fail_job(
                job.job_id,
                phase="failed",
                message="Recommendation refresh failed",
                error=str(e),
                result={"seed": seed, "request_id": request_id},
            )
            if request_id == self._latest_refresh_request_id and not self.browse_mode:
                self._set_refresh_state(running=False, status="Recommendation refresh failed.")
                ui.notify(f"Error: {e}", type="negative")

    def _set_detail_card(self, *, title: str, summary: str, metrics: str, note: str) -> None:
        if self.detail_title is not None:
            self.detail_title.text = title
            self.detail_title.update()
        if self.detail_summary is not None:
            self.detail_summary.text = summary
            self.detail_summary.update()
        if self.detail_metrics is not None:
            self.detail_metrics.text = metrics
            self.detail_metrics.update()
        if self.detail_note is not None:
            self.detail_note.text = note
            self.detail_note.update()

    def _set_refresh_state(self, *, running: bool, status: str) -> None:
        if self.refresh_btn is not None:
            if running:
                self.refresh_btn.disable()
            else:
                self.refresh_btn.enable()
            self.refresh_btn.update()
        if self.refresh_status is not None:
            self.refresh_status.text = status
            self.refresh_status.update()

    def _get_recommendations(
        self,
        seed_path: str,
        top: int = 50,
        meta: dict | None = None,
        filters: dict | None = None,
        weights: dict | None = None,
    ) -> list[dict]:
        """Get recommendations for seed track with weighted scoring."""
        return build_recommendation_rows(
            seed_path=seed_path,
            top=top,
            meta=meta or self.state.meta,
            filters=filters or self.state.filters,
            weights=weights or self.state.weights,
        )


_page: DiscoverPage | None = None


def render() -> None:
    """Render the discover page."""
    global _page
    _page = DiscoverPage()
    _page.render()
