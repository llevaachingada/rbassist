"""Crate/Playlist expander - playlist expansion with shared backend controls."""

from __future__ import annotations

import asyncio
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from nicegui import background_tasks, ui

from ..components.track_table import TrackTable
from ..state import get_state
from rbassist.playlist_expand import (
    PLAYLIST_EXPANSION_PRESETS,
    ExpansionResult,
    ExpansionWorkspace,
    PlaylistExpansionControls,
    PlaylistExpansionFilters,
    PlaylistExpansionWeights,
    list_rekordbox_playlists,
    load_rekordbox_playlist,
    prepare_playlist_expansion,
    rerank_playlist_expansion,
    write_expansion_xml,
)
from rbassist.utils import ROOT


def _track_name(path: str) -> str:
    try:
        return Path(path).stem or path
    except Exception:
        return path


def _format_bpm_cell(value: float | None) -> str:
    return f"{float(value):.0f}" if isinstance(value, (int, float)) and value else "-"


def _format_bpm_metric(value: float | None) -> str:
    return f"{float(value):.2f} BPM" if isinstance(value, (int, float)) and value else "-- BPM"


def _format_count_label(mode: str, value: int, seed_count: int) -> str:
    if mode == "add_count":
        return f"Add count: {max(0, int(value))}"
    return f"Target total: {max(int(value), seed_count)}"


def _plain_component_name(name: str) -> str:
    mapping = {
        "ann_centroid": "playlist vibe",
        "ann_seed_coverage": "shared seed support",
        "group_match": "group fit",
        "bpm_match": "tempo fit",
        "key_match": "harmonic fit",
        "tag_match": "tag overlap",
        "anti_repetition": "repeat protection",
    }
    return mapping.get(str(name), str(name).replace("_", " "))


REQUIRED_TAG_PRESETS: list[tuple[str, str]] = [
    ("Warm-up", "Warm-up"),
    ("Opener", "Opener"),
    ("Tool", "Tool"),
    ("Peak-time", "Peak-time"),
    ("Closer", "Closer"),
]

CRATE_EXPANDER_EXPORT_DIR = ROOT / "exports" / "crate_expander"


def _safe_export_stem(value: str) -> str:
    text = re.sub(r'[<>:"/\\|?*]+', "_", str(value or "").strip())
    text = re.sub(r"\s+", " ", text).strip().rstrip(".")
    return text or "crate_expander_export"


def _open_folder(path: Path) -> None:
    if hasattr(os, "startfile"):
        os.startfile(str(path))


def _playlist_item_label(item: dict[str, Any]) -> str:
    return str(item.get("path") or item.get("name") or item.get("id") or "").strip()


def _playlist_item_value(item: dict[str, Any]) -> str:
    source = str(item.get("source") or "").lower().strip()
    playlist_id = item.get("id")
    if source == "db" and playlist_id not in (None, ""):
        return f"db:{playlist_id}"
    return _playlist_item_label(item)


class CrateExpander:
    """Expand a crate/playlist using the shared playlist expansion backend."""

    def __init__(self) -> None:
        self.state = get_state()
        self.selected_seeds: list[str] = []
        self.workspace: ExpansionWorkspace | None = None
        self.workspace_signature: tuple[Any, ...] | None = None
        self.current_result: ExpansionResult | None = None
        self.recommendations: list[dict[str, Any]] = []
        self.rekordbox_source = "db"
        self.rekordbox_xml_path = ""
        self.rekordbox_playlist_items: list[dict[str, Any]] = []
        self.rekordbox_playlist_query = ""
        self.loaded_playlist_name: str | None = None
        self.require_tags_text = ""
        self.detail_title = None
        self.detail_summary = None
        self.detail_metrics = None
        self.detail_note = None
        self.export_status_label = None
        self.last_export_path: Path | None = None

        preset = PLAYLIST_EXPANSION_PRESETS["balanced"]
        weights = preset["weights"].to_dict()
        filters = preset["filters"].to_dict()

        self.preset_name = "balanced"
        self.strategy_name = "blend"
        self.count_mode = "target_total"
        self.count_value = 30
        self.candidate_pool = 250
        self.diversity = float(preset["diversity"])
        self.tempo_pct = float(filters["tempo_pct"])
        self.allow_doubletime = bool(filters["allow_doubletime"])
        self.key_mode = str(filters["key_mode"])
        self.weight_values = {
            "ann_centroid": float(weights["ann_centroid"]),
            "ann_seed_coverage": float(weights["ann_seed_coverage"]),
            "group_match": float(weights["group_match"]),
            "bpm_match": float(weights["bpm_match"]),
            "key_match": float(weights["key_match"]),
            "tag_match": float(weights["tag_match"]),
        }

    def _effective_seed_count(self) -> int:
        if self.workspace is not None:
            return int(self.workspace.diagnostics.get("clean_seed_tracks_total", len(self.selected_seeds)))
        return len(self.selected_seeds)

    def render(self) -> None:
        """Render the crate expander interface."""
        with ui.column().classes("w-full gap-4"):
            ui.label("Crate Expander").classes("text-2xl font-bold text-white")
            ui.label(
                "Expand a Rekordbox playlist into a larger crate using the shared backend. "
                "Seed order stays first, additions are appended after reranking."
            ).classes("text-gray-400 text-sm mb-4")
            with ui.card().classes("w-full bg-[#1a1a1a] border border-[#333] p-4"):
                ui.label("How playlist expansion works").classes("text-sm font-medium text-gray-200")
                ui.label(
                    "We keep your seed playlist, build a candidate pool around the whole group's vibe, then append the strongest additions after tempo, key, tag, and variety checks."
                ).classes("text-gray-400 text-sm")
                ui.label(
                    "Overall fit is the final score after reranking. Raw fit is the score before variety and repeat-protection nudges."
                ).classes("text-gray-500 text-xs mt-1")

            with ui.row().classes("w-full gap-6 items-start"):
                with ui.card().classes("w-[34rem] bg-[#1a1a1a] border border-[#333] p-4"):
                    ui.label("Seeds").classes("text-lg font-semibold text-gray-200 mb-3")

                    ui.label("Load Rekordbox Playlist").classes("text-md font-medium text-gray-300 mb-2")
                    with ui.row().classes("w-full items-center gap-2"):
                        self.rekordbox_source_toggle = ui.toggle(
                            {"db": "Rekordbox DB", "xml": "Rekordbox XML"},
                            value=self.rekordbox_source,
                        ).props("dark").classes("flex-1")
                        ui.button("Refresh", icon="refresh", on_click=self._refresh_rekordbox_playlists).props(
                            "flat dense"
                        ).classes("bg-[#252525] hover:bg-[#333] text-gray-300")

                    self.rekordbox_xml_input = ui.input(
                        label="XML path (only needed for XML source)",
                        placeholder=r"C:\Exports\rekordbox.xml",
                        value=self.rekordbox_xml_path,
                    ).props("dark dense").classes("w-full mt-2")
                    self.rekordbox_xml_input.visible = False

                    self.rekordbox_filter_input = ui.input(
                        label="Filter playlists",
                        placeholder="Search playlists by name or path...",
                    ).props("dark dense").classes("w-full mt-2")

                    self.rekordbox_playlist_select = ui.select(
                        {},
                        value=None,
                        label="Rekordbox playlist",
                    ).props("dark dense").classes("w-full mt-2")

                    with ui.row().classes("w-full gap-2 mt-2"):
                        ui.button(
                            "Load Playlist As Seeds",
                            icon="playlist_play",
                            on_click=self._load_selected_rekordbox_playlist,
                        ).props(
                            "flat"
                        ).classes("bg-indigo-600 hover:bg-indigo-500 flex-1")
                        ui.button("Use Manual Seeds", icon="queue_music", on_click=lambda: ui.notify("Manual seed search stays available below.", type="info")).props("flat").classes(
                            "bg-[#252525] text-gray-300"
                        )

                    self.rekordbox_status_label = ui.label("Refresh to view Rekordbox playlists.").classes(
                        "text-gray-500 text-xs mb-3"
                    )

                    ui.separator().classes("my-3")

                    search_input = ui.input(placeholder="Search to add tracks...").props("dark dense").classes(
                        "w-full mb-2"
                    )
                    search_results = ui.column().classes(
                        "w-full max-h-48 overflow-y-auto bg-[#252525] rounded border border-[#333] mb-3"
                    )
                    search_results.visible = False

                    def search_tracks(e) -> None:
                        query = str(e.args or "").lower().strip()
                        search_results.clear()

                        if not query:
                            search_results.visible = False
                            return

                        tracks = self.state.meta.get("tracks", {})
                        matches: list[tuple[str, dict[str, Any]]] = []
                        for path, info in tracks.items():
                            if path in self.selected_seeds:
                                continue
                            artist = str(info.get("artist", "") or "").lower()
                            title = str(info.get("title", "") or "").lower()
                            if query in artist or query in title or query in path.lower():
                                matches.append((path, info))
                                if len(matches) >= 50:
                                    break

                        with search_results:
                            for path, info in matches:
                                artist = str(info.get("artist", "") or "")
                                title = str(info.get("title", "") or _track_name(path))
                                display = f"{artist} - {title}" if artist else title
                                with ui.row().classes("w-full p-2 hover:bg-[#333] cursor-pointer").on(
                                    "click", lambda seed_path=path: add_seed(seed_path)
                                ):
                                    ui.label(display).classes("text-gray-200 text-sm")

                        search_results.visible = bool(matches)

                    def add_seed(path: str) -> None:
                        if path not in self.selected_seeds:
                            self.selected_seeds.append(path)
                            self.workspace = None
                            self.workspace_signature = None
                            self.current_result = None
                            self.recommendations = []
                            render_seeds()
                            update_seed_summary()
                        search_input.value = ""
                        search_results.visible = False

                    search_input.on("update:model-value", search_tracks)

                    ui.separator().classes("my-3")

                    seeds_container = ui.column().classes("w-full gap-2")

                    self.seed_count_label = ui.label("0 selected").classes("text-gray-400 text-sm")
                    self.loaded_playlist_label = ui.label("No Rekordbox playlist loaded").classes("text-gray-500 text-xs")

                    def update_seed_summary() -> None:
                        self.seed_count_label.text = f"{len(self.selected_seeds)} selected"
                        if self.loaded_playlist_name:
                            self.loaded_playlist_label.text = f"Loaded playlist: {self.loaded_playlist_name}"
                        else:
                            self.loaded_playlist_label.text = "No Rekordbox playlist loaded"
                        if self.workspace is not None:
                            seed_info = self.workspace.diagnostics
                            self.status_label.text = (
                                f"Ready: {seed_info.get('clean_seed_tracks_total', 0)} mapped seeds, "
                                f"{seed_info.get('candidate_pool_total', 0)} prepared candidates"
                            )
                        else:
                            self.status_label.text = "Ready: add at least 3 mapped seeds, then generate"
                        self.seed_count_label.update()
                        self.loaded_playlist_label.update()
                        self.status_label.update()

                    def render_seeds() -> None:
                        seeds_container.clear()
                        tracks = self.state.meta.get("tracks", {})
                        with seeds_container:
                            if not self.selected_seeds:
                                ui.label("No tracks selected").classes("text-gray-500 italic")
                            else:
                                for path in self.selected_seeds:
                                    info = tracks.get(path, {})
                                    artist = str(info.get("artist", "") or "")
                                    title = str(info.get("title", "") or _track_name(path))
                                    display = f"{artist} - {title}" if artist else title
                                    with ui.row().classes("w-full items-center gap-2"):
                                        ui.label(display).classes("text-gray-300 text-sm flex-1")
                                        ui.button(
                                            icon="close",
                                            on_click=lambda seed_path=path: remove_seed(seed_path),
                                        ).props("flat round dense").classes("text-gray-400")

                    def remove_seed(path: str) -> None:
                        if path in self.selected_seeds:
                            self.selected_seeds.remove(path)
                            self.workspace = None
                            self.workspace_signature = None
                            self.current_result = None
                            self.recommendations = []
                            render_seeds()
                            update_seed_summary()
                            self._clear_results_table()

                    render_seeds()

                    ui.separator().classes("my-3")

                    with ui.row().classes("w-full items-center justify-between"):
                        ui.label("Result Size").classes("text-md font-medium text-gray-300")
                        # seed_count_label is created above so the summary callback can update it.

                    with ui.row().classes("w-full items-end gap-2"):
                        self.count_mode_toggle = ui.toggle(
                            {"target_total": "Target total", "add_count": "Add count"},
                            value=self.count_mode,
                        ).props("dark").classes("w-44")
                        self.count_value_input = ui.number(
                            value=self.count_value,
                            min=0,
                            step=1,
                        ).props("dark dense").classes("flex-1")

                    self.count_hint_label = ui.label("").classes("text-gray-500 text-xs mb-2")
                    ui.label(
                        "Target total keeps the mapped seed tracks and grows the crate to this final size. "
                        "Add count appends exactly this many new tracks."
                    ).classes("text-gray-500 text-xs mb-2")

                    def update_count_hint() -> None:
                        self.count_hint_label.text = _format_count_label(
                            str(self.count_mode_toggle.value or self.count_mode),
                            int(float(self.count_value_input.value or 0)),
                            self._effective_seed_count(),
                        )
                        self.count_hint_label.update()

                    update_count_hint()

                    ui.separator().classes("my-3")

                    ui.label("Presets").classes("text-md font-medium text-gray-300 mb-2")
                    self.preset_toggle = ui.toggle(
                        {"tight": "Tight", "balanced": "Balanced", "adventurous": "Adventurous"},
                        value=self.preset_name,
                    ).props("dark").classes("w-full")
                    ui.label(
                        "Tight stays closer to the original playlist, Balanced mixes similarity with variety, "
                        "and Adventurous explores farther while still respecting the playlist vibe."
                    ).classes("text-gray-500 text-xs mb-2")

                    ui.separator().classes("my-3")

                    ui.label("Advanced Controls").classes("text-md font-medium text-gray-300 mb-2")
                    ui.label(
                        "Use these when you want to shape how expansion behaves. Strategy changes the candidate pool; "
                        "the rest mainly rerank that pool."
                    ).classes("text-gray-500 text-xs mb-2")
                    with ui.column().classes("w-full gap-2"):
                        with ui.row().classes("w-full items-center gap-2"):
                            ui.label("Matching view").classes("text-gray-400 w-24")
                            self.strategy_toggle = ui.toggle(
                                {"blend": "Blend", "centroid": "Centroid", "coverage": "Coverage"},
                                value=self.strategy_name,
                            ).props("dark").classes("flex-1")
                        ui.label(
                            "Blend combines the playlist-average view with per-seed support. Centroid follows the overall average vibe. "
                            "Coverage favors tracks supported by more individual seed neighborhoods."
                        ).classes("text-gray-500 text-xs")

                        with ui.row().classes("w-full items-center gap-2"):
                            ui.label("Search depth").classes("text-gray-400 w-24")
                            self.candidate_pool_input = ui.number(value=self.candidate_pool, min=25, step=25).props(
                                "dark dense"
                            ).classes("flex-1")
                        ui.label(
                            "Candidate pool is how many possible tracks we fetch before scoring and diversity reranking. "
                            "Higher values can give better variety, but cost more work."
                        ).classes("text-gray-500 text-xs")

                        with ui.row().classes("w-full items-center gap-2"):
                            ui.label("Tempo window").classes("text-gray-400 w-24")
                            self.tempo_slider = ui.slider(
                                min=1,
                                max=15,
                                step=0.5,
                                value=self.tempo_pct,
                            ).props("dark color=indigo label-always").classes("flex-1")
                        ui.label(
                            "Tempo sets the BPM envelope around the playlist median BPM. Smaller values stay tighter; "
                            "larger values allow broader tempo drift."
                        ).classes("text-gray-500 text-xs")

                        with ui.row().classes("w-full items-center gap-2"):
                            ui.label("Key mode").classes("text-gray-400 w-24")
                            self.key_mode_toggle = ui.toggle(
                                {"off": "Off", "soft": "Soft", "filter": "Filter"},
                                value=self.key_mode,
                            ).props("dark").classes("flex-1")
                        ui.label(
                            "Off ignores key, Soft rewards compatible Camelot keys, and Filter removes tracks that are not key-compatible."
                        ).classes("text-gray-500 text-xs")

                        with ui.row().classes("w-full items-center gap-2"):
                            ui.label("Variety").classes("text-gray-400 w-24")
                            self.diversity_slider = ui.slider(
                                min=0,
                                max=1,
                                step=0.05,
                                value=self.diversity,
                            ).props("dark color=indigo label-always").classes("flex-1")
                        ui.label(
                            "Diversity reduces near-duplicate additions. Lower values stay closer to the top matches; "
                            "higher values spread the picks out more."
                        ).classes("text-gray-500 text-xs")

                        with ui.row().classes("w-full items-center gap-2"):
                            ui.label("Half/doubletime").classes("text-gray-400 w-24")
                            self.doubletime_switch = ui.switch(value=self.allow_doubletime).props("dark")
                        ui.label(
                            "Allow 2x/0.5x lets the BPM envelope treat doubletime and halftime as compatible when tempo matching."
                        ).classes("text-gray-500 text-xs")

                        self.require_tags_input = ui.input(
                            label="Required tags",
                            placeholder="Comma-separated My Tags, e.g. Warm-up, Opener",
                            value=self.require_tags_text,
                        ).props("dark dense").classes("w-full")
                        ui.label(
                            "Required tags are hard filters. Use them for purpose-built crates like warm-up, opener, tool, peak-time, or closer pools."
                        ).classes("text-gray-500 text-xs")
                        with ui.row().classes("w-full gap-2 flex-wrap"):
                            for label, tag_value in REQUIRED_TAG_PRESETS:
                                ui.button(
                                    label,
                                    on_click=lambda value=tag_value: self._set_required_tags(value),
                                ).props("flat dense").classes("bg-[#252525] text-gray-300")
                            ui.button("Clear", on_click=lambda: self._set_required_tags("")).props(
                                "flat dense"
                            ).classes("bg-[#252525] text-gray-400")
                        ui.label(
                            "Tap a lane to prefill the filter, or type your own comma-separated tags."
                        ).classes("text-gray-500 text-xs")

                        ui.separator().classes("my-2")
                        ui.label(
                            "Weights decide what matters most in the final score. They are normalized automatically, so raising one "
                            "signal makes it matter more relative to the others."
                        ).classes("text-gray-500 text-xs")

                        self.ann_centroid_slider = self._weight_slider_row("Playlist vibe", self.weight_values["ann_centroid"])
                        ui.label(
                            "Technical name: ANN centroid. This is similarity to the playlist's average embedding, which captures the overall vibe."
                        ).classes("text-gray-500 text-xs")
                        self.ann_seed_coverage_slider = self._weight_slider_row(
                            "Across seeds", self.weight_values["ann_seed_coverage"]
                        )
                        ui.label(
                            "Technical name: ANN coverage. This rewards tracks that show up across more individual seed neighborhoods."
                        ).classes("text-gray-500 text-xs")
                        self.group_match_slider = self._weight_slider_row("Group fit", self.weight_values["group_match"])
                        ui.label(
                            "Technical name: Group match. This is direct similarity to the seed set as a group, not just the overall centroid."
                        ).classes("text-gray-500 text-xs")
                        self.bpm_match_slider = self._weight_slider_row("Tempo fit", self.weight_values["bpm_match"])
                        ui.label(
                            "Tempo fit rewards tracks closer to the playlist tempo envelope."
                        ).classes("text-gray-500 text-xs")
                        self.key_match_slider = self._weight_slider_row("Key fit", self.weight_values["key_match"])
                        ui.label(
                            "Key fit rewards Camelot-compatible harmonic matches."
                        ).classes("text-gray-500 text-xs")
                        self.tag_match_slider = self._weight_slider_row("Tag fit", self.weight_values["tag_match"])
                        ui.label(
                            "Tag fit rewards overlap with the playlist's core My Tags when tags are available."
                        ).classes("text-gray-500 text-xs")

                    ui.separator().classes("my-3")

                    with ui.row().classes("w-full gap-2"):
                        ui.button("Generate / Rerank", icon="auto_awesome", on_click=self._generate).props("flat").classes(
                            "bg-indigo-600 hover:bg-indigo-500 w-full"
                        )
                    ui.button("Clear All", icon="clear", on_click=self._clear_all).props("flat").classes(
                        "bg-[#252525] hover:bg-[#333] text-gray-300 w-full mt-2"
                    )
                    ui.button(
                        "Save Rekordbox Playlist XML",
                        icon="download",
                        on_click=self._save_rekordbox_xml,
                    ).props("flat").classes("bg-teal-600 hover:bg-teal-500 text-white w-full mt-2")
                    ui.label(
                        "Saves a Rekordbox playlist XML file only. It does not save, change, or overwrite your Rekordbox library. "
                        "After saving, the export folder opens so you can drag the XML into Rekordbox to import it as a new playlist."
                    ).classes("text-gray-500 text-xs mt-2")
                    self.export_status_label = ui.label(
                        f"Default save folder: {CRATE_EXPANDER_EXPORT_DIR}"
                    ).classes("text-gray-500 text-xs")

                with ui.column().classes("flex-1 gap-4"):
                    with ui.row().classes("w-full items-center justify-between"):
                        ui.label("Expanded Playlist").classes("text-xl font-bold text-white")
                        self.result_count_label = ui.label("0 tracks").classes("text-gray-400")

                    self.status_label = ui.label("Ready: add at least 3 mapped seeds, then generate").classes(
                        "text-gray-500 text-sm"
                    )

                    with ui.card().classes("w-full bg-[#1a1a1a] border border-[#333] p-0"):
                        self.rec_table = TrackTable(
                            on_row_click=self._show_track_detail,
                            extra_columns=[
                                {"name": "rekordbox_bpm", "label": "RB BPM", "field": "rekordbox_bpm", "sortable": True, "align": "right"},
                                {"name": "rbassist_bpm", "label": "Assist BPM", "field": "rbassist_bpm", "sortable": True, "align": "right"},
                                {"name": "bpm_alert", "label": "Tempo Note", "field": "bpm_alert", "sortable": True, "align": "left"},
                                {"name": "score", "label": "Overall fit", "field": "score", "sortable": True, "align": "right"},
                                {
                                    "name": "base_score",
                                    "label": "Raw fit",
                                    "field": "base_score",
                                    "sortable": True,
                                    "align": "right",
                                },
                                {
                                    "name": "support_count",
                                    "label": "Seed support",
                                    "field": "support_count",
                                    "sortable": True,
                                    "align": "right",
                                },
                                {
                                    "name": "components",
                                    "label": "Why it matched",
                                    "field": "components",
                                    "sortable": False,
                                    "align": "left",
                                },
                            ],
                        )
                        self.rec_table.build()

                    ui.label(
                        "Click a row for a compact breakdown of the backend scores and controls used."
                    ).classes("text-gray-500 text-xs")
                    with ui.card().classes("w-full bg-[#151515] border border-[#2a2a2a] p-4"):
                        ui.label("Why this track matched").classes("text-sm font-medium text-gray-200")
                        self.detail_title = ui.label("Click any added track for a plain-English explanation.").classes(
                            "text-gray-300 text-sm"
                        )
                        self.detail_summary = ui.label(
                            "You will see the overall fit, raw fit, seed support, and the strongest match reasons."
                        ).classes("text-gray-400 text-sm")
                        self.detail_metrics = ui.label("").classes("text-gray-500 text-xs")
                        self.detail_note = ui.label(
                            "This panel explains the ranking; it does not change the result."
                        ).classes("text-gray-500 text-xs mt-1")

        self._wire_control_events()
        update_seed_summary()
        update_count_hint()
        self._render_seeds_callback = render_seeds
        background_tasks.create(self._refresh_rekordbox_playlists(notify=False), name="crate-expander-refresh")

    def _weight_slider_row(self, label: str, value: float):
        with ui.row().classes("w-full items-center gap-2"):
            ui.label(f"{label}:").classes("text-gray-400 w-24")
            slider = ui.slider(min=0, max=1, step=0.05, value=value).props("dark color=indigo").classes("flex-1")
            value_label = ui.label(f"{value:.2f}").classes("text-gray-300 w-12")
        slider.on("update:model-value", lambda e, label_ref=value_label: self._update_weight_label(label_ref, e.args))
        return slider

    def _update_weight_label(self, label, value: Any) -> None:
        try:
            label.text = f"{float(value):.2f}"
        except Exception:
            label.text = "0.00"
        label.update()

    def _wire_control_events(self) -> None:
        self.rekordbox_source_toggle.on("update:model-value", self._on_rekordbox_source_change)
        self.rekordbox_xml_input.on("update:model-value", lambda e: self._on_rekordbox_xml_change())
        self.rekordbox_filter_input.on("update:model-value", lambda e: self._filter_rekordbox_playlists())
        self.count_mode_toggle.on("update:model-value", lambda e: self._on_count_control_change())
        self.count_value_input.on("update:model-value", lambda e: self._on_count_control_change())

        self.preset_toggle.on("update:model-value", lambda e: self._apply_preset(str(self.preset_toggle.value or "balanced")))
        self.strategy_toggle.on("update:model-value", lambda e: self._on_rebuild_control_change())
        self.candidate_pool_input.on("update:model-value", lambda e: self._on_rebuild_control_change())

        self.tempo_slider.on("update:model-value", lambda e: self._on_rerank_control_change())
        self.key_mode_toggle.on("update:model-value", lambda e: self._on_rerank_control_change())
        self.diversity_slider.on("update:model-value", lambda e: self._on_rerank_control_change())
        self.doubletime_switch.on("update:model-value", lambda e: self._on_rerank_control_change())
        self.require_tags_input.on("update:model-value", lambda e: self._on_rerank_control_change())

        self.ann_centroid_slider.on("update:model-value", lambda e: self._on_rerank_control_change())
        self.ann_seed_coverage_slider.on("update:model-value", lambda e: self._on_rerank_control_change())
        self.group_match_slider.on("update:model-value", lambda e: self._on_rerank_control_change())
        self.bpm_match_slider.on("update:model-value", lambda e: self._on_rerank_control_change())
        self.key_match_slider.on("update:model-value", lambda e: self._on_rerank_control_change())
        self.tag_match_slider.on("update:model-value", lambda e: self._on_rerank_control_change())

    async def _on_rekordbox_source_change(self, _event: Any = None) -> None:
        self.rekordbox_source = str(self.rekordbox_source_toggle.value or "db")
        self.rekordbox_xml_input.visible = self.rekordbox_source == "xml"
        self.rekordbox_xml_input.update()
        await self._refresh_rekordbox_playlists()

    def _on_rekordbox_xml_change(self) -> None:
        self.rekordbox_xml_path = str(self.rekordbox_xml_input.value or "").strip()

    def _filter_rekordbox_playlists(self) -> None:
        self.rekordbox_playlist_query = str(self.rekordbox_filter_input.value or "").strip().lower()
        options: dict[str, str] = {}
        for item in self.rekordbox_playlist_items:
            path = _playlist_item_label(item)
            name = str(item.get("name", "") or "")
            haystack = f"{path} {name}".lower()
            if self.rekordbox_playlist_query and self.rekordbox_playlist_query not in haystack:
                continue
            value = _playlist_item_value(item)
            if value:
                options[value] = path or value
        current_value = self.rekordbox_playlist_select.value
        self.rekordbox_playlist_select.options = options
        if current_value not in options:
            self.rekordbox_playlist_select.value = next(iter(options.keys()), None)
        self.rekordbox_playlist_select.update()
        self.rekordbox_status_label.text = f"{len(options)} playlists available"
        self.rekordbox_status_label.update()

    async def _refresh_rekordbox_playlists(self, *, notify: bool = True) -> None:
        try:
            source = str(self.rekordbox_source_toggle.value or self.rekordbox_source or "db")
            self.rekordbox_source = source
            xml_path = str(self.rekordbox_xml_input.value or "").strip()
            self.rekordbox_xml_path = xml_path
            if source == "xml" and not xml_path:
                self.rekordbox_playlist_items = []
                self.rekordbox_playlist_select.options = {}
                self.rekordbox_playlist_select.value = None
                self.rekordbox_playlist_select.update()
                self.rekordbox_status_label.text = "Enter a Rekordbox XML path to load playlists."
                self.rekordbox_status_label.update()
                return
            self.rekordbox_status_label.text = "Loading Rekordbox playlists..."
            self.rekordbox_status_label.update()
            self.rekordbox_playlist_items = await asyncio.to_thread(
                list_rekordbox_playlists,
                source=source,
                xml_path=xml_path or None,
            )
            self._filter_rekordbox_playlists()
            if notify:
                ui.notify(f"Loaded {len(self.rekordbox_playlist_items)} Rekordbox playlists", type="positive")
        except Exception as exc:
            self.rekordbox_playlist_items = []
            self.rekordbox_playlist_select.options = {}
            self.rekordbox_playlist_select.value = None
            self.rekordbox_playlist_select.update()
            self.rekordbox_status_label.text = f"Playlist load failed: {exc}"
            self.rekordbox_status_label.update()
            if notify:
                ui.notify(f"Rekordbox playlist load failed: {exc}", type="negative")

    def _selected_rekordbox_playlist_ref(self) -> tuple[Any, str]:
        playlist_value = self.rekordbox_playlist_select.value
        playlist_label = str(playlist_value or "")
        for item in self.rekordbox_playlist_items:
            if _playlist_item_value(item) != playlist_value:
                continue
            playlist_label = _playlist_item_label(item) or playlist_label
            source = str(item.get("source") or self.rekordbox_source_toggle.value or "db").lower().strip()
            playlist_id = item.get("id")
            if source == "db" and playlist_id not in (None, ""):
                try:
                    return int(playlist_id), playlist_label
                except (TypeError, ValueError):
                    return f"db:{playlist_id}", playlist_label
            return playlist_label, playlist_label

        value_text = str(playlist_value or "").strip()
        if value_text.lower().startswith("db:"):
            raw_id = value_text.split(":", 1)[1].strip()
            if raw_id.isdigit():
                return int(raw_id), value_text
        return playlist_value, playlist_label

    async def _load_selected_rekordbox_playlist(self) -> None:
        playlist_ref = self.rekordbox_playlist_select.value
        if not playlist_ref:
            ui.notify("Choose a Rekordbox playlist first", type="warning")
            return
        playlist_ref, playlist_label = self._selected_rekordbox_playlist_ref()
        source = str(self.rekordbox_source_toggle.value or "db").lower().strip()
        xml_path = str(self.rekordbox_xml_input.value or "").strip() or None
        try:
            if hasattr(self, "status_label"):
                self.status_label.text = f"Loading playlist '{playlist_label}'..."
                self.status_label.update()
            seed_playlist = await asyncio.to_thread(
                load_rekordbox_playlist,
                playlist_ref,
                source=source,
                playlist_path=playlist_label if source == "db" else None,
                xml_path=xml_path,
            )
            self.selected_seeds = [track.meta_path or track.rekordbox_path for track in seed_playlist.tracks]
            self.loaded_playlist_name = seed_playlist.name
            self.workspace = None
            self.workspace_signature = None
            self.current_result = None
            self.recommendations = []
            if hasattr(self, "_render_seeds_callback"):
                self._render_seeds_callback()
            if hasattr(self, "seed_count_label"):
                self.seed_count_label.text = f"{len(self.selected_seeds)} selected"
                self.seed_count_label.update()
            self._clear_results_table()
            self._update_count_hint()
            if hasattr(self, "status_label"):
                loader = seed_playlist.diagnostics
                self.status_label.text = (
                    f"Loaded {seed_playlist.name}: "
                    f"{loader.get('matched_total', 0)} matched, "
                    f"{loader.get('missing_embedding_total', 0)} missing embedding, "
                    f"{loader.get('unmapped_total', 0)} unmapped"
                )
                self.status_label.update()
            if hasattr(self, "loaded_playlist_label"):
                self.loaded_playlist_label.text = f"Loaded playlist: {seed_playlist.name}"
                self.loaded_playlist_label.update()
            ui.notify(f"Loaded Rekordbox playlist '{seed_playlist.name}' into seeds", type="positive")
        except Exception as exc:
            ui.notify(f"Failed to load Rekordbox playlist: {exc}", type="negative")

    def _update_count_hint(self) -> None:
        self.count_mode = str(self.count_mode_toggle.value or "target_total")
        try:
            self.count_value = int(float(self.count_value_input.value or 0))
        except Exception:
            self.count_value = 0
        effective_seed_count = self._effective_seed_count()
        update_text = _format_count_label(self.count_mode, self.count_value, effective_seed_count)
        if hasattr(self, "count_mode_toggle"):
            self.count_mode_toggle.update()
        if hasattr(self, "count_value_input"):
            self.count_value_input.update()
        if hasattr(self, "count_hint_label"):
            self.count_hint_label.text = update_text
            self.count_hint_label.update()

    def _apply_preset(self, mode: str) -> None:
        mode = str(mode or "balanced").lower().strip()
        if mode not in PLAYLIST_EXPANSION_PRESETS:
            mode = "balanced"
        self.preset_name = mode
        preset = PLAYLIST_EXPANSION_PRESETS[mode]
        weights = preset["weights"].to_dict()
        filters = preset["filters"].to_dict()

        self.tempo_pct = float(filters["tempo_pct"])
        self.allow_doubletime = bool(filters["allow_doubletime"])
        self.key_mode = str(filters["key_mode"])
        self.diversity = float(preset["diversity"])
        self.weight_values = {
            "ann_centroid": float(weights["ann_centroid"]),
            "ann_seed_coverage": float(weights["ann_seed_coverage"]),
            "group_match": float(weights["group_match"]),
            "bpm_match": float(weights["bpm_match"]),
            "key_match": float(weights["key_match"]),
            "tag_match": float(weights["tag_match"]),
        }

        self.preset_toggle.value = mode
        self.tempo_slider.value = self.tempo_pct
        self.doubletime_switch.value = self.allow_doubletime
        self.key_mode_toggle.value = self.key_mode
        self.diversity_slider.value = self.diversity
        self.ann_centroid_slider.value = self.weight_values["ann_centroid"]
        self.ann_seed_coverage_slider.value = self.weight_values["ann_seed_coverage"]
        self.group_match_slider.value = self.weight_values["group_match"]
        self.bpm_match_slider.value = self.weight_values["bpm_match"]
        self.key_match_slider.value = self.weight_values["key_match"]
        self.tag_match_slider.value = self.weight_values["tag_match"]

        self._rerank_if_ready(rebuild=False)

    def _weight_values_from_widgets(self) -> PlaylistExpansionWeights:
        return PlaylistExpansionWeights(
            ann_centroid=float(self.ann_centroid_slider.value or 0.0),
            ann_seed_coverage=float(self.ann_seed_coverage_slider.value or 0.0),
            group_match=float(self.group_match_slider.value or 0.0),
            bpm_match=float(self.bpm_match_slider.value or 0.0),
            key_match=float(self.key_match_slider.value or 0.0),
            tag_match=float(self.tag_match_slider.value or 0.0),
        )

    def _filters_from_widgets(self) -> PlaylistExpansionFilters:
        require_tags = [
            tag.strip()
            for tag in str(self.require_tags_input.value or "").replace(";", ",").split(",")
            if str(tag).strip()
        ]
        return PlaylistExpansionFilters(
            tempo_pct=float(self.tempo_slider.value or 0.0),
            allow_doubletime=bool(self.doubletime_switch.value),
            key_mode=str(self.key_mode_toggle.value or "soft"),
            require_tags=require_tags,
        )

    def _set_required_tags(self, value: str) -> None:
        self.require_tags_input.value = value
        self.require_tags_input.update()
        self._on_rerank_control_change()

    def _build_controls(self) -> PlaylistExpansionControls:
        return PlaylistExpansionControls(
            mode=str(self.preset_toggle.value or "balanced"),
            strategy=str(self.strategy_toggle.value or "blend"),
            weights=self._weight_values_from_widgets(),
            diversity=float(self.diversity_slider.value or 0.0),
            filters=self._filters_from_widgets(),
            candidate_pool=max(25, int(float(self.candidate_pool_input.value or 250))),
        )

    def _workspace_signature(self) -> tuple[Any, ...]:
        controls = self._build_controls()
        return (
            tuple(self.selected_seeds),
            controls.strategy,
            controls.candidate_pool,
        )

    def _on_rebuild_control_change(self) -> None:
        self._rerank_if_ready(rebuild=True)

    def _on_rerank_control_change(self) -> None:
        self._rerank_if_ready(rebuild=False)

    def _on_count_control_change(self) -> None:
        self._update_count_hint()
        self._rerank_if_ready(rebuild=False)

    def _requested_counts(self) -> tuple[int | None, int | None]:
        count_mode = str(self.count_mode_toggle.value or "target_total")
        try:
            count_value = int(float(self.count_value_input.value or 0))
        except Exception:
            count_value = 0

        if count_mode == "add_count":
            return None, max(0, count_value)
        return max(self._effective_seed_count(), count_value), None

    def _rerank_if_ready(self, *, rebuild: bool) -> None:
        if not self.selected_seeds:
            self._clear_results_table()
            self.workspace = None
            self.workspace_signature = None
            self.current_result = None
            if hasattr(self, "status_label"):
                self.status_label.text = "Ready: add at least 3 mapped seeds, then generate"
                self.status_label.update()
            return

        try:
            controls = self._build_controls()
            signature = self._workspace_signature()
            if rebuild or self.workspace is None or self.workspace_signature != signature:
                self.workspace = prepare_playlist_expansion(self.selected_seeds, controls=controls)
                self.workspace_signature = signature

            target_total, add_count = self._requested_counts()
            result = rerank_playlist_expansion(
                self.workspace,
                controls=controls,
                target_total=target_total,
                add_count=add_count,
            )
            self.current_result = result
            self._render_result(result)
        except Exception as exc:
            ui.notify(f"Error: {exc}", type="negative")
            self._clear_results_table()
            self.current_result = None

    def _generate(self) -> None:
        self._rerank_if_ready(rebuild=True)

    def _default_export_playlist_name(self) -> str:
        if self.loaded_playlist_name:
            return f"{self.loaded_playlist_name} Expanded"
        return "Crate Expander Export"

    async def _save_rekordbox_xml(self) -> None:
        if self.current_result is None:
            ui.notify("Generate a crate first, then save the Rekordbox playlist XML.", type="warning")
            return

        playlist_name = self._default_export_playlist_name()
        export_dir = CRATE_EXPANDER_EXPORT_DIR.resolve()
        export_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = export_dir / f"{_safe_export_stem(playlist_name)}_{timestamp}.xml"

        try:
            await ui.run_worker(
                lambda: write_expansion_xml(
                    self.current_result,
                    out_path=str(out_path),
                    playlist_name=playlist_name,
                )
            )
            self.last_export_path = out_path
            if self.export_status_label is not None:
                self.export_status_label.text = (
                    f"Saved playlist XML only -> {out_path}. Rekordbox library unchanged. "
                    "Drag this XML into Rekordbox to import the playlist."
                )
                self.export_status_label.update()
            ui.notify(
                f"Saved playlist XML -> {out_path.name}. Rekordbox library unchanged.",
                type="positive",
            )
            try:
                await ui.run_worker(lambda: _open_folder(export_dir))
            except Exception:
                pass
        except Exception as exc:
            if self.export_status_label is not None:
                self.export_status_label.text = "Crate export failed."
                self.export_status_label.update()
            ui.notify(f"Crate export failed: {exc}", type="negative")

    def _clear_all(self) -> None:
        self.selected_seeds.clear()
        self.loaded_playlist_name = None
        self.workspace = None
        self.workspace_signature = None
        self.current_result = None
        self.recommendations = []
        self._clear_results_table()
        self.count_value_input.value = 30
        self.count_mode_toggle.value = "target_total"
        if hasattr(self, "require_tags_input"):
            self.require_tags_input.value = ""
            self.require_tags_input.update()
        self._update_count_hint()
        if hasattr(self, "_render_seeds_callback"):
            self._render_seeds_callback()
        if hasattr(self, "seed_count_label"):
            self.seed_count_label.text = "0 selected"
            self.seed_count_label.update()
        if hasattr(self, "loaded_playlist_label"):
            self.loaded_playlist_label.text = "No Rekordbox playlist loaded"
            self.loaded_playlist_label.update()
        if self.export_status_label is not None:
            self.export_status_label.text = f"Default save folder: {CRATE_EXPANDER_EXPORT_DIR}"
            self.export_status_label.update()
        if hasattr(self, "status_label"):
            self.status_label.text = "Ready: add at least 3 mapped seeds, then generate"
            self.status_label.update()

    def _clear_results_table(self) -> None:
        if hasattr(self, "rec_table"):
            self.rec_table.update([])
        if hasattr(self, "result_count_label"):
            self.result_count_label.text = "0 tracks"
            self.result_count_label.update()
        self._set_detail_card(
            title="Why this track matched",
            summary="Click any added track for a plain-English explanation.",
            metrics="You will see the overall fit, raw fit, seed support, and the strongest match reasons.",
            note="This panel explains the ranking; it does not change the result.",
        )

    def _compact_components(self, component_scores: dict[str, float]) -> str:
        ordered = sorted(component_scores.items(), key=lambda item: (-float(item[1]), item[0]))
        return ", ".join(f"{_plain_component_name(key)} {float(value):.2f}" for key, value in ordered[:4])

    def _render_result(self, result: ExpansionResult) -> None:
        rows: list[dict[str, Any]] = []
        for track in result.added_tracks:
            rows.append(
                {
                    "path": track.path,
                    "artist": track.artist or "",
                    "title": track.title or _track_name(track.path),
                    "bpm": _format_bpm_cell(track.bpm),
                    "bpm_value": track.bpm,
                    "rekordbox_bpm": _format_bpm_cell(track.rekordbox_bpm),
                    "rekordbox_bpm_value": track.rekordbox_bpm,
                    "rbassist_bpm": _format_bpm_cell(track.rbassist_bpm),
                    "rbassist_bpm_value": track.rbassist_bpm,
                    "bpm_alert": "Large mismatch" if track.bpm_mismatch else "-",
                    "bpm_source": track.bpm_source,
                    "key": track.key or "-",
                    "score": round(float(track.final_score or track.score), 6),
                    "base_score": round(float(track.base_score), 6),
                    "support_count": int(track.support_count),
                    "ann_distance": round(float(track.ann_distance), 6) if track.ann_distance is not None else "-",
                    "components": self._compact_components(track.component_scores),
                    "detail_components": ", ".join(
                        f"{_plain_component_name(name)} {float(value):.2f}"
                        for name, value in sorted(track.component_scores.items(), key=lambda item: (-float(item[1]), item[0]))
                    ),
                }
            )

        self.recommendations = rows
        if hasattr(self, "rec_table"):
            self.rec_table.update(rows)
            self.rec_table.set_sort("score", True)
        if hasattr(self, "result_count_label"):
            self.result_count_label.text = f"{len(rows)} tracks"
            self.result_count_label.update()

        diag = result.diagnostics
        if hasattr(self, "status_label"):
            self.status_label.text = (
                f"{diag.get('mode', result.mode)} / {diag.get('strategy', result.strategy)} | "
                f"{diag.get('selected_count', len(rows))} additions from "
                f"{diag.get('candidate_pool_total', diag.get('candidate_pool', 0))} prepared candidates"
            )
            self.status_label.update()

        self._update_count_hint()

    def _show_track_detail(self, track: dict | None) -> None:
        if not track:
            return
        artist = str(track.get("artist", "") or "")
        title = str(track.get("title", "") or "")
        heading = f"{artist} - {title}".strip(" -") or "Track detail"
        self._set_detail_card(
            title=heading,
            summary=(
                f"Overall fit {float(track.get('score', 0) or 0):.3f}, raw fit {float(track.get('base_score', 0) or 0):.3f}, "
                f"seed support {int(track.get('support_count', 0) or 0)}."
            ),
            metrics=(
                f"Tempo: Using {_format_bpm_metric(track.get('bpm_value'))}"
                f" | Rekordbox: {_format_bpm_metric(track.get('rekordbox_bpm_value'))}"
                f" | RB Assist: {_format_bpm_metric(track.get('rbassist_bpm_value'))}"
                f" | Key: {track.get('key', '-')} | "
                f"Why it matched: {track.get('detail_components', track.get('components', ''))}"
            ),
            note=(
                "Overall fit is the final reranked score. Raw fit is before variety and repeat-protection nudges. "
                "Tempo matching prefers Rekordbox BPM when it is available."
            ),
        )

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


def render() -> None:
    """Render the crate expander page."""
    expander = CrateExpander()
    expander.render()
