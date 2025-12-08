"""Filter and weight controls for recommendations."""

from __future__ import annotations

from typing import Callable
from nicegui import ui

from ..state import get_state


# Weight presets
PRESETS = {
    "Balanced": {"ann": 0.6, "samples": 0.1, "bass": 0.1, "rhythm": 0.1, "bpm": 0.05, "key": 0.05, "tags": 0.0},
    "Energy": {"ann": 0.45, "samples": 0.35, "bass": 0.1, "rhythm": 0.05, "bpm": 0.05, "key": 0.0, "tags": 0.0},
    "Groove": {"ann": 0.4, "samples": 0.1, "bass": 0.2, "rhythm": 0.2, "bpm": 0.05, "key": 0.05, "tags": 0.0},
    "Harmonic": {"ann": 0.4, "samples": 0.05, "bass": 0.15, "rhythm": 0.05, "bpm": 0.15, "key": 0.2, "tags": 0.0},
    "Pure ANN": {"ann": 1.0, "samples": 0.0, "bass": 0.0, "rhythm": 0.0, "bpm": 0.0, "key": 0.0, "tags": 0.0},
}


class FilterPanel:
    """Filter controls for recommendations."""

    def __init__(self, on_change: Callable[[], None] | None = None):
        self.on_change = on_change
        self.state = get_state()

        with ui.card().classes("bg-[#1a1a1a] border border-[#333] p-4 w-full"):
            ui.label("Filters").classes("text-lg font-semibold text-gray-200 mb-3")

            # Tempo tolerance
            with ui.row().classes("w-full items-center gap-2 mb-3"):
                ui.label("Tempo:").classes("text-gray-400 w-20")
                self.tempo_slider = ui.slider(
                    min=1, max=15, step=0.5, value=self.state.filters["tempo_pct"]
                ).props("dark color=indigo label-always").classes("flex-1")
                self.tempo_label = ui.label(f"±{self.state.filters['tempo_pct']:.1f}%").classes("text-gray-300 w-16")

            self.tempo_slider.on("update:model-value", self._on_tempo_change)

            # Key filtering
            with ui.row().classes("w-full items-center gap-4 mb-3"):
                self.camelot_check = ui.checkbox(
                    "Camelot Key", value=self.state.filters["camelot"]
                ).props("dark color=indigo")
                self.doubletime_check = ui.checkbox(
                    "Allow 2x/0.5x", value=self.state.filters["doubletime"]
                ).props("dark color=indigo")

            self.camelot_check.on("update:model-value", self._on_filter_change)
            self.doubletime_check.on("update:model-value", self._on_filter_change)

            ui.separator().classes("my-3")

            # Weight sliders
            ui.label("Audio Features").classes("text-md font-medium text-gray-300 mb-2")

            with ui.column().classes("w-full gap-2"):
                # ANN weight
                with ui.row().classes("w-full items-center gap-2"):
                    ui.label("ANN:").classes("text-gray-400 w-20")
                    self.ann_slider = ui.slider(
                        min=0, max=1, step=0.05, value=self.state.weights.get("ann", 0.6)
                    ).props("dark color=indigo").classes("flex-1")
                    self.ann_label = ui.label(f"{self.state.weights.get('ann', 0.6):.2f}").classes("text-gray-300 w-12")

                # Samples weight
                with ui.row().classes("w-full items-center gap-2"):
                    ui.label("Samples:").classes("text-gray-400 w-20")
                    self.samples_slider = ui.slider(
                        min=0, max=1, step=0.05, value=self.state.weights.get("samples", 0.1)
                    ).props("dark color=indigo").classes("flex-1")
                    self.samples_label = ui.label(f"{self.state.weights.get('samples', 0.1):.2f}").classes("text-gray-300 w-12")

                # Bass weight
                with ui.row().classes("w-full items-center gap-2"):
                    ui.label("Bass:").classes("text-gray-400 w-20")
                    self.bass_slider = ui.slider(
                        min=0, max=1, step=0.05, value=self.state.weights.get("bass", 0.1)
                    ).props("dark color=indigo").classes("flex-1")
                    self.bass_label = ui.label(f"{self.state.weights.get('bass', 0.1):.2f}").classes("text-gray-300 w-12")

                # Rhythm weight
                with ui.row().classes("w-full items-center gap-2"):
                    ui.label("Rhythm:").classes("text-gray-400 w-20")
                    self.rhythm_slider = ui.slider(
                        min=0, max=1, step=0.05, value=self.state.weights.get("rhythm", 0.1)
                    ).props("dark color=indigo").classes("flex-1")
                    self.rhythm_label = ui.label(f"{self.state.weights.get('rhythm', 0.1):.2f}").classes("text-gray-300 w-12")

            ui.separator().classes("my-2")
            ui.label("Metadata Features").classes("text-md font-medium text-gray-300 mb-2")

            with ui.column().classes("w-full gap-2"):
                # BPM weight
                with ui.row().classes("w-full items-center gap-2"):
                    ui.label("BPM:").classes("text-gray-400 w-20")
                    self.bpm_slider = ui.slider(
                        min=0, max=1, step=0.05, value=self.state.weights.get("bpm", 0.05)
                    ).props("dark color=indigo").classes("flex-1")
                    self.bpm_label = ui.label(f"{self.state.weights.get('bpm', 0.05):.2f}").classes("text-gray-300 w-12")

                # Key weight
                with ui.row().classes("w-full items-center gap-2"):
                    ui.label("Key:").classes("text-gray-400 w-20")
                    self.key_slider = ui.slider(
                        min=0, max=1, step=0.05, value=self.state.weights.get("key", 0.05)
                    ).props("dark color=indigo").classes("flex-1")
                    self.key_label = ui.label(f"{self.state.weights.get('key', 0.05):.2f}").classes("text-gray-300 w-12")

                # Tags weight
                with ui.row().classes("w-full items-center gap-2"):
                    ui.label("Tags:").classes("text-gray-400 w-20")
                    self.tags_slider = ui.slider(
                        min=0, max=1, step=0.05, value=self.state.weights.get("tags", 0.0)
                    ).props("dark color=indigo").classes("flex-1")
                    self.tags_label = ui.label(f"{self.state.weights.get('tags', 0.0):.2f}").classes("text-gray-300 w-12")

            self.ann_slider.on("update:model-value", self._on_weight_change)
            self.samples_slider.on("update:model-value", self._on_weight_change)
            self.bass_slider.on("update:model-value", self._on_weight_change)
            self.rhythm_slider.on("update:model-value", self._on_weight_change)
            self.bpm_slider.on("update:model-value", self._on_weight_change)
            self.key_slider.on("update:model-value", self._on_weight_change)
            self.tags_slider.on("update:model-value", self._on_weight_change)

            ui.separator().classes("my-3")

            # Presets
            ui.label("Presets").classes("text-md font-medium text-gray-300 mb-2")
            with ui.row().classes("w-full gap-2 flex-wrap"):
                for name in PRESETS:
                    ui.button(name, on_click=lambda n=name: self._apply_preset(n)).props(
                        "flat dense"
                    ).classes("bg-[#252525] hover:bg-[#333] text-gray-300")

    def _on_tempo_change(self, e) -> None:
        self.state.filters["tempo_pct"] = e.args
        self.tempo_label.text = f"±{e.args:.1f}%"
        if self.on_change:
            self.on_change()

    def _on_filter_change(self, e=None) -> None:
        self.state.filters["camelot"] = self.camelot_check.value
        self.state.filters["doubletime"] = self.doubletime_check.value
        if self.on_change:
            self.on_change()

    def _on_weight_change(self, e=None) -> None:
        self.state.weights["ann"] = self.ann_slider.value
        self.state.weights["samples"] = self.samples_slider.value
        self.state.weights["bass"] = self.bass_slider.value
        self.state.weights["rhythm"] = self.rhythm_slider.value
        self.state.weights["bpm"] = self.bpm_slider.value
        self.state.weights["key"] = self.key_slider.value
        self.state.weights["tags"] = self.tags_slider.value
        self.ann_label.text = f"{self.ann_slider.value:.2f}"
        self.samples_label.text = f"{self.samples_slider.value:.2f}"
        self.bass_label.text = f"{self.bass_slider.value:.2f}"
        self.rhythm_label.text = f"{self.rhythm_slider.value:.2f}"
        self.bpm_label.text = f"{self.bpm_slider.value:.2f}"
        self.key_label.text = f"{self.key_slider.value:.2f}"
        self.tags_label.text = f"{self.tags_slider.value:.2f}"
        if self.on_change:
            self.on_change()

    def _apply_preset(self, name: str) -> None:
        preset = PRESETS.get(name)
        if not preset:
            return
        self.state.weights.update(preset)
        self.ann_slider.value = preset.get("ann", 0.6)
        self.samples_slider.value = preset.get("samples", 0.1)
        self.bass_slider.value = preset.get("bass", 0.1)
        self.rhythm_slider.value = preset.get("rhythm", 0.1)
        self.bpm_slider.value = preset.get("bpm", 0.05)
        self.key_slider.value = preset.get("key", 0.05)
        self.tags_slider.value = preset.get("tags", 0.0)
        self.ann_label.text = f"{preset.get('ann', 0.6):.2f}"
        self.samples_label.text = f"{preset.get('samples', 0.1):.2f}"
        self.bass_label.text = f"{preset.get('bass', 0.1):.2f}"
        self.rhythm_label.text = f"{preset.get('rhythm', 0.1):.2f}"
        self.bpm_label.text = f"{preset.get('bpm', 0.05):.2f}"
        self.key_label.text = f"{preset.get('key', 0.05):.2f}"
        self.tags_label.text = f"{preset.get('tags', 0.0):.2f}"
        if self.on_change:
            self.on_change()
