"""Filter and weight controls for recommendations."""

from __future__ import annotations

from typing import Callable

from nicegui import ui

from ..state import get_state


# Weight presets
PRESETS = {
    "Balanced": {"ann": 0.6, "samples": 0.1, "bass": 0.1, "rhythm": 0.1, "bpm": 0.05, "key": 0.05, "harmony": 0.0, "learned_sim": 0.0, "tags": 0.0},
    "Energy": {"ann": 0.45, "samples": 0.35, "bass": 0.1, "rhythm": 0.05, "bpm": 0.05, "key": 0.0, "harmony": 0.0, "learned_sim": 0.0, "tags": 0.0},
    "Groove": {"ann": 0.4, "samples": 0.1, "bass": 0.2, "rhythm": 0.2, "bpm": 0.05, "key": 0.05, "harmony": 0.0, "learned_sim": 0.0, "tags": 0.0},
    "Harmonic": {"ann": 0.35, "samples": 0.05, "bass": 0.1, "rhythm": 0.05, "bpm": 0.15, "key": 0.15, "harmony": 0.15, "learned_sim": 0.0, "tags": 0.0},
    "Learned": {"ann": 0.35, "samples": 0.05, "bass": 0.1, "rhythm": 0.05, "bpm": 0.1, "key": 0.05, "harmony": 0.05, "learned_sim": 0.25, "tags": 0.0},
    "Pure ANN": {"ann": 1.0, "samples": 0.0, "bass": 0.0, "rhythm": 0.0, "bpm": 0.0, "key": 0.0, "harmony": 0.0, "learned_sim": 0.0, "tags": 0.0},
}


def format_tempo_pct(value: float) -> str:
    """Format tempo tolerance using plain ASCII text."""
    return f"+/-{float(value):.1f}%"


class FilterPanel:
    """Filter controls for recommendations."""

    def __init__(self, on_change: Callable[[], None] | None = None):
        self.on_change = on_change
        self.state = get_state()

        with ui.card().classes("bg-[#1a1a1a] border border-[#333] p-4 w-full"):
            ui.label("Filters").classes("text-lg font-semibold text-gray-200 mb-3")
            ui.label(
                "How recommendations work: we start with similar-sounding tracks, then rerank them using the sliders below."
            ).classes("text-gray-500 text-xs mb-2")
            ui.label(
                "Higher weights make that signal matter more in the final ranking. Leave them alone unless you want to steer the results."
            ).classes("text-gray-500 text-xs mb-3")

            # Tempo tolerance
            with ui.row().classes("w-full items-center gap-2 mb-3"):
                ui.label("Tempo window:").classes("text-gray-400 w-28")
                self.tempo_slider = ui.slider(
                    min=1, max=15, step=0.5, value=self.state.filters["tempo_pct"]
                ).props("dark color=indigo label-always").classes("flex-1")
                self.tempo_label = ui.label(
                    format_tempo_pct(self.state.filters["tempo_pct"])
                ).classes("text-gray-300 w-16")
            ui.label(
                "This controls how far from the seed track's BPM we are willing to go."
            ).classes("text-gray-500 text-xs mb-3")

            self.tempo_slider.on("update:model-value", self._on_tempo_change)

            # Key filtering
            with ui.row().classes("w-full items-center gap-4 mb-3"):
                self.camelot_check = ui.checkbox(
                    "Require harmonic key compatibility", value=self.state.filters["camelot"]
                ).props("dark color=indigo")
                self.doubletime_check = ui.checkbox(
                    "Treat halftime/doubletime as compatible", value=self.state.filters["doubletime"]
                ).props("dark color=indigo")
                self.learned_similarity_check = ui.checkbox(
                    "Use learned playlist-pair model", value=bool(self.state.filters.get("learned_similarity", False))
                ).props("dark color=indigo")
            ui.label(
                "The learned model is opt-in and uses CUDA by default when your trained model is available."
            ).classes("text-gray-500 text-xs mb-1")

            self.camelot_check.on("update:model-value", self._on_filter_change)
            self.doubletime_check.on("update:model-value", self._on_filter_change)
            self.learned_similarity_check.on("update:model-value", self._on_filter_change)

            ui.separator().classes("my-3")

            # Weight sliders
            ui.label("Sound Features").classes("text-md font-medium text-gray-300 mb-2")

            with ui.column().classes("w-full gap-2"):
                # ANN weight
                with ui.row().classes("w-full items-center gap-2"):
                    ui.label("Overall sound:").classes("text-gray-400 w-28")
                    self.ann_slider = ui.slider(
                        min=0, max=1, step=0.05, value=self.state.weights.get("ann", 0.6)
                    ).props("dark color=indigo").classes("flex-1")
                    self.ann_label = ui.label(f"{self.state.weights.get('ann', 0.6):.2f}").classes("text-gray-300 w-12")
                ui.label(
                    "Technical name: ANN. This is the main similar-sounding audio match."
                ).classes("text-gray-500 text-xs")

                # Samples weight
                with ui.row().classes("w-full items-center gap-2"):
                    ui.label("Texture / intensity:").classes("text-gray-400 w-28")
                    self.samples_slider = ui.slider(
                        min=0, max=1, step=0.05, value=self.state.weights.get("samples", 0.1)
                    ).props("dark color=indigo").classes("flex-1")
                    self.samples_label = ui.label(f"{self.state.weights.get('samples', 0.1):.2f}").classes("text-gray-300 w-12")
                ui.label(
                    "Technical name: Samples. Use this when you want to care more about density, texture, or intensity."
                ).classes("text-gray-500 text-xs")

                # Bass weight
                with ui.row().classes("w-full items-center gap-2"):
                    ui.label("Low-end feel:").classes("text-gray-400 w-28")
                    self.bass_slider = ui.slider(
                        min=0, max=1, step=0.05, value=self.state.weights.get("bass", 0.1)
                    ).props("dark color=indigo").classes("flex-1")
                    self.bass_label = ui.label(f"{self.state.weights.get('bass', 0.1):.2f}").classes("text-gray-300 w-12")
                ui.label(
                    "Push this up if the bass character matters more than the exact overall sound."
                ).classes("text-gray-500 text-xs")

                # Rhythm weight
                with ui.row().classes("w-full items-center gap-2"):
                    ui.label("Groove pattern:").classes("text-gray-400 w-28")
                    self.rhythm_slider = ui.slider(
                        min=0, max=1, step=0.05, value=self.state.weights.get("rhythm", 0.1)
                    ).props("dark color=indigo").classes("flex-1")
                    self.rhythm_label = ui.label(f"{self.state.weights.get('rhythm', 0.1):.2f}").classes("text-gray-300 w-12")
                ui.label(
                    "Use this when you want similar swing, pulse, or rhythmic feel."
                ).classes("text-gray-500 text-xs")

            ui.separator().classes("my-2")
            ui.label("Tempo, Harmonic, And Tag Features").classes("text-md font-medium text-gray-300 mb-2")

            with ui.column().classes("w-full gap-2"):
                # BPM weight
                with ui.row().classes("w-full items-center gap-2"):
                    ui.label("Tempo fit:").classes("text-gray-400 w-28")
                    self.bpm_slider = ui.slider(
                        min=0, max=1, step=0.05, value=self.state.weights.get("bpm", 0.05)
                    ).props("dark color=indigo").classes("flex-1")
                    self.bpm_label = ui.label(f"{self.state.weights.get('bpm', 0.05):.2f}").classes("text-gray-300 w-12")
                ui.label(
                    "Higher values keep the recommendations closer to the seed track's BPM."
                ).classes("text-gray-500 text-xs")

                # Key weight
                with ui.row().classes("w-full items-center gap-2"):
                    ui.label("Harmonic fit:").classes("text-gray-400 w-28")
                    self.key_slider = ui.slider(
                        min=0, max=1, step=0.05, value=self.state.weights.get("key", 0.05)
                    ).props("dark color=indigo").classes("flex-1")
                    self.key_label = ui.label(f"{self.state.weights.get('key', 0.05):.2f}").classes("text-gray-300 w-12")
                ui.label(
                    "Raise this when harmonic compatibility matters more for blending."
                ).classes("text-gray-500 text-xs")

                # Cached harmonic profile weight
                with ui.row().classes("w-full items-center gap-2"):
                    ui.label("Profile harmony:").classes("text-gray-400 w-28")
                    self.harmony_slider = ui.slider(
                        min=0, max=1, step=0.05, value=self.state.weights.get("harmony", 0.0)
                    ).props("dark color=indigo").classes("flex-1")
                    self.harmony_label = ui.label(f"{self.state.weights.get('harmony', 0.0):.2f}").classes("text-gray-300 w-12")
                ui.label(
                    "Uses cached chroma/tonnetz profiles when present. Missing profiles quietly score as zero."
                ).classes("text-gray-500 text-xs")

                # Learned similarity weight
                with ui.row().classes("w-full items-center gap-2"):
                    ui.label("Learned fit:").classes("text-gray-400 w-28")
                    self.learned_slider = ui.slider(
                        min=0, max=1, step=0.05, value=self.state.weights.get("learned_sim", 0.0)
                    ).props("dark color=indigo").classes("flex-1")
                    self.learned_label = ui.label(f"{self.state.weights.get('learned_sim', 0.0):.2f}").classes("text-gray-300 w-12")
                ui.label(
                    "Uses the trained playlist-pair model only when the checkbox above is enabled."
                ).classes("text-gray-500 text-xs")

                # Tags weight
                with ui.row().classes("w-full items-center gap-2"):
                    ui.label("Tag overlap:").classes("text-gray-400 w-28")
                    self.tags_slider = ui.slider(
                        min=0, max=1, step=0.05, value=self.state.weights.get("tags", 0.0)
                    ).props("dark color=indigo").classes("flex-1")
                    self.tags_label = ui.label(f"{self.state.weights.get('tags', 0.0):.2f}").classes("text-gray-300 w-12")
                ui.label(
                    "Use tags when your My Tags are good enough to steer the recommendations."
                ).classes("text-gray-500 text-xs")

            self.ann_slider.on("update:model-value", self._on_weight_change)
            self.samples_slider.on("update:model-value", self._on_weight_change)
            self.bass_slider.on("update:model-value", self._on_weight_change)
            self.rhythm_slider.on("update:model-value", self._on_weight_change)
            self.bpm_slider.on("update:model-value", self._on_weight_change)
            self.key_slider.on("update:model-value", self._on_weight_change)
            self.harmony_slider.on("update:model-value", self._on_weight_change)
            self.learned_slider.on("update:model-value", self._on_weight_change)
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
        self.tempo_label.text = format_tempo_pct(e.args)
        self.tempo_label.update()
        if self.on_change:
            self.on_change()

    def _on_filter_change(self, e=None) -> None:
        self.state.filters["camelot"] = self.camelot_check.value
        self.state.filters["doubletime"] = self.doubletime_check.value
        self.state.filters["learned_similarity"] = self.learned_similarity_check.value
        self.state.filters["similarity_device"] = "cuda"
        if self.on_change:
            self.on_change()

    def _on_weight_change(self, e=None) -> None:
        self.state.weights["ann"] = self.ann_slider.value
        self.state.weights["samples"] = self.samples_slider.value
        self.state.weights["bass"] = self.bass_slider.value
        self.state.weights["rhythm"] = self.rhythm_slider.value
        self.state.weights["bpm"] = self.bpm_slider.value
        self.state.weights["key"] = self.key_slider.value
        self.state.weights["harmony"] = self.harmony_slider.value
        self.state.weights["learned_sim"] = self.learned_slider.value
        self.state.weights["tags"] = self.tags_slider.value
        self.ann_label.text = f"{self.ann_slider.value:.2f}"
        self.samples_label.text = f"{self.samples_slider.value:.2f}"
        self.bass_label.text = f"{self.bass_slider.value:.2f}"
        self.rhythm_label.text = f"{self.rhythm_slider.value:.2f}"
        self.bpm_label.text = f"{self.bpm_slider.value:.2f}"
        self.key_label.text = f"{self.key_slider.value:.2f}"
        self.harmony_label.text = f"{self.harmony_slider.value:.2f}"
        self.learned_label.text = f"{self.learned_slider.value:.2f}"
        self.tags_label.text = f"{self.tags_slider.value:.2f}"
        self.ann_label.update()
        self.samples_label.update()
        self.bass_label.update()
        self.rhythm_label.update()
        self.bpm_label.update()
        self.key_label.update()
        self.harmony_label.update()
        self.learned_label.update()
        self.tags_label.update()
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
        self.harmony_slider.value = preset.get("harmony", 0.0)
        self.learned_slider.value = preset.get("learned_sim", 0.0)
        self.tags_slider.value = preset.get("tags", 0.0)
        self.learned_similarity_check.value = bool(preset.get("learned_sim", 0.0) > 0.0)
        self.state.filters["learned_similarity"] = self.learned_similarity_check.value
        self.state.filters["similarity_device"] = "cuda"
        self.ann_slider.update()
        self.samples_slider.update()
        self.bass_slider.update()
        self.rhythm_slider.update()
        self.bpm_slider.update()
        self.key_slider.update()
        self.harmony_slider.update()
        self.learned_slider.update()
        self.tags_slider.update()
        self.learned_similarity_check.update()
        self.ann_label.text = f"{preset.get('ann', 0.6):.2f}"
        self.samples_label.text = f"{preset.get('samples', 0.1):.2f}"
        self.bass_label.text = f"{preset.get('bass', 0.1):.2f}"
        self.rhythm_label.text = f"{preset.get('rhythm', 0.1):.2f}"
        self.bpm_label.text = f"{preset.get('bpm', 0.05):.2f}"
        self.key_label.text = f"{preset.get('key', 0.05):.2f}"
        self.harmony_label.text = f"{preset.get('harmony', 0.0):.2f}"
        self.learned_label.text = f"{preset.get('learned_sim', 0.0):.2f}"
        self.tags_label.text = f"{preset.get('tags', 0.0):.2f}"
        self.ann_label.update()
        self.samples_label.update()
        self.bass_label.update()
        self.rhythm_label.update()
        self.bpm_label.update()
        self.key_label.update()
        self.harmony_label.update()
        self.learned_label.update()
        self.tags_label.update()
        if self.on_change:
            self.on_change()
