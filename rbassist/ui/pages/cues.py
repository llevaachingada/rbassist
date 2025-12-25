"""Cues page - auto-generate hot cues / memory cues with simple logic."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Callable

import librosa
from nicegui import ui

from rbassist.cues import propose_cues
from rbassist.analyze import _estimate_tempo  # reuse tempo estimator
from rbassist.utils import load_meta, save_meta, console, walk_audio
from ..state import get_state


def _generate_cues_for_file(path: str, duration_s: int, overwrite: bool) -> tuple[bool, str]:
    """Generate cues for a single file; returns (ok, message)."""
    try:
        meta = load_meta()
        info = meta["tracks"].setdefault(path, {})
        if info.get("cues") and not overwrite:
            return True, "Skipped (existing cues)"

        y, sr = librosa.load(path, sr=None, mono=True, duration=duration_s if duration_s > 0 else None)
        if y.size == 0 or sr is None or sr <= 0:
            return False, "Empty audio"
        bpm = _estimate_tempo(y, sr)
        cues = propose_cues(y, sr, bpm=float(bpm))
        info["bpm"] = float(bpm)
        info["cues"] = cues
        save_meta(meta)
        return True, f"Cues updated (BPM {bpm:.2f})"
    except Exception as e:
        try:
            console.print(f"[red]Cue gen failed for {path}: {e}")
        except Exception:
            pass
        return False, str(e)


def render() -> None:
    """Render the Cues page."""
    state = get_state()

    with ui.column().classes("w-full gap-4"):
        # Header
        ui.label("Auto Cues").classes("text-2xl font-bold text-white")
        ui.label("Generate hot cues / memory cues using intro/core/drop logic.").classes("text-gray-400 mb-2")

        # Main card
        with ui.card().classes("w-full bg-[#1a1a1a] border border-[#333] p-4"):
            ui.label("Cue Generation Settings").classes("text-lg font-semibold text-gray-200 mb-3")

            with ui.column().classes("gap-3"):
                # Settings
                with ui.row().classes("gap-4 items-center"):
                    ui.label("Duration cap (s)").classes("text-gray-400")
                    duration_input = ui.number(value=120, min=0, max=600, step=10).props("dark dense").classes("w-32")
                    ui.label("(0 = full track)").classes("text-gray-500 text-sm")

                overwrite_check = ui.checkbox("Overwrite existing cues", value=False).props("dark")

                ui.label("Cues will be generated at intro, drop, core, and mix-out points based on energy analysis.").classes("text-gray-500 text-sm")

            # Progress and status
            progress_bar = ui.linear_progress(value=0).props("rounded").style("max-width: 400px; display: none;")
            status_label = ui.label("").classes("text-gray-400 text-sm")

            # Batch processing function
            async def _process_cues_batch(paths: list[str]) -> None:
                if not paths:
                    ui.notify("No audio files found.", type="warning")
                    return

                total = len(paths)
                progress_bar.style("max-width: 400px; display: block;")
                progress_bar.value = 0
                progress_bar.update()
                status_label.text = "Starting cue generation..."
                status_label.update()
                ui.notify(f"Generating cues for {total} track(s)...", type="info")

                def _work():
                    meta = load_meta()
                    targets = paths

                    # Filter out tracks that already have cues if overwrite is false
                    if not overwrite_check.value:
                        targets = [p for p in paths if not meta.get("tracks", {}).get(p, {}).get("cues")]

                    success_count = 0
                    error_count = 0

                    for idx, path in enumerate(targets):
                        # Update progress
                        done = idx + 1
                        progress_bar.value = max(0.0, min(1.0, done / max(len(targets), 1)))
                        progress_bar.update()
                        status_label.text = f"Processing {done}/{len(targets)}: {Path(path).name}"
                        status_label.update()

                        # Generate cues
                        ok, msg = _generate_cues_for_file(path, int(duration_input.value or 120), overwrite_check.value)
                        if ok:
                            success_count += 1
                        else:
                            error_count += 1

                    return success_count, error_count, len(targets)

                success, errors, processed = await asyncio.to_thread(_work)

                # Update final status
                progress_bar.value = 1.0
                progress_bar.update()

                skipped = total - processed
                status_label.text = f"Complete: {success} success, {errors} errors, {skipped} skipped"
                status_label.update()

                if errors > 0:
                    ui.notify(f"Cue generation complete: {success} success, {errors} errors", type="warning")
                else:
                    ui.notify(f"Cue generation complete: {success} track(s) processed", type="positive")

                state.refresh_meta()

            # Music folders batch processing
            async def _run_music_folders():
                if not state.music_folders:
                    ui.notify("Set Music Folders in Settings first.", type="warning")
                    return
                files = walk_audio(state.music_folders)
                await _process_cues_batch(files)

            # Single file processing
            file_input = ui.input(
                placeholder="Type/paste file path or use Browse button..."
            ).props("dark dense clearable").classes("w-96")

            async def _browse_file():
                """Browse for a single file to process."""
                def _pick():
                    try:
                        import tkinter as tk
                        from tkinter import filedialog
                        root = tk.Tk()
                        root.withdraw()
                        root.attributes('-topmost', True)
                        path = filedialog.askopenfilename(
                            title="Select audio file for cue generation",
                            filetypes=[
                                ("Audio files", "*.wav *.flac *.mp3 *.m4a *.aiff *.aif"),
                                ("All files", "*.*")
                            ]
                        )
                        root.destroy()
                        return path
                    except Exception as e:
                        return None

                path = await asyncio.to_thread(_pick)
                if path:
                    file_input.value = path
                    file_input.update()
                    ui.notify(f"Selected: {Path(path).name}", type="positive")
                else:
                    ui.notify("No file selected. You can also type/paste the file path.", type="info")

            async def _run_single_file():
                path = (file_input.value or "").strip()
                if not path:
                    ui.notify("Please select a file using Browse or type the path.", type="warning")
                    return

                # Check if file exists
                if not Path(path).exists():
                    ui.notify(f"File not found: {path}", type="negative")
                    ui.notify("Please check the path and try again.", type="info")
                    return

                await _process_cues_batch([path])

            # Action buttons
            with ui.row().classes("gap-3 items-center mt-4"):
                ui.button("Process music folders", icon="folder_open", on_click=_run_music_folders).props("flat").classes(
                    "bg-indigo-600 hover:bg-indigo-500 text-white"
                )
                ui.button("Process single file", icon="audiotrack", on_click=_run_single_file).props("flat").classes(
                    "bg-purple-600 hover:bg-purple-500 text-white"
                )
                ui.button("Browse", icon="folder", on_click=_browse_file).props("flat").classes(
                    "bg-[#252525] hover:bg-[#333] text-gray-200"
                )
                file_input

            progress_bar
            status_label
