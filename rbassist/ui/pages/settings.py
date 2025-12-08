"""Settings page - configuration and preferences."""

from __future__ import annotations

from pathlib import Path
import asyncio
from nicegui import ui

from ..state import get_state


def render() -> None:
    """Render the settings page."""
    state = get_state()

    with ui.column().classes("w-full gap-4 max-w-3xl"):
        ui.label("Settings").classes("text-2xl font-bold text-white")

        # Workspace
        with ui.card().classes("w-full bg-[#1a1a1a] border border-[#333] p-4"):
            ui.label("Workspace").classes("text-lg font-semibold text-gray-200 mb-3")

            with ui.column().classes("gap-4"):
                with ui.row().classes("w-full items-center gap-4"):
                    ui.label("Music Folder:").classes("text-gray-400 w-32")
                    folder_input = ui.input(
                        value=state.music_folder or "",
                        placeholder="Select your music library folder..."
                    ).props("dark dense").classes("flex-1")

                    def pick_folder():
                        try:
                            import tkinter as tk
                            from tkinter import filedialog
                            root = tk.Tk()
                            root.withdraw()
                            folder = filedialog.askdirectory(title="Select Music Folder")
                            root.destroy()
                            if folder:
                                folder_input.value = folder
                                state.music_folder = folder
                                ui.notify(f"Selected: {folder}", type="positive")
                        except Exception as e:
                            ui.notify(f"Folder picker error: {e}", type="negative")

                    ui.button(icon="folder", on_click=pick_folder).props("flat dense")

                with ui.row().classes("w-full items-center gap-4"):
                    ui.label("Device:").classes("text-gray-400 w-32")
                    device_select = ui.select(
                        ["auto", "cuda", "cpu", "mps"],
                        value=state.device or "auto",
                    ).props("dark dense").classes("w-48")

                    # Show detected device
                    try:
                        import torch
                        if torch.cuda.is_available():
                            device_name = torch.cuda.get_device_name(0)
                            ui.label(f"Detected: {device_name}").classes("text-green-500 text-sm")
                        else:
                            ui.label("GPU not available").classes("text-amber-500 text-sm")
                    except Exception:
                        ui.label("PyTorch not configured").classes("text-gray-500 text-sm")

        # Embedding Settings
        with ui.card().classes("w-full bg-[#1a1a1a] border border-[#333] p-4"):
            ui.label("Embedding").classes("text-lg font-semibold text-gray-200 mb-3")

            with ui.column().classes("gap-4"):
                with ui.row().classes("w-full items-center gap-4"):
                    ui.label("Duration cap (s):").classes("text-gray-400 w-32")
                    duration_input = ui.number(value=state.duration_s, min=30, max=300, step=10).props("dark dense").classes("w-32")
                    ui.label("Cap per track; embed still uses intro/core/late windows").classes("text-gray-500 text-sm")

                with ui.row().classes("w-full items-center gap-4"):
                    ui.label("Workers:").classes("text-gray-400 w-32")
                    workers_input = ui.number(value=state.workers, min=0, max=16, step=1).props("dark dense").classes("w-32")
                    ui.label("Parallel audio loaders (0 = serial)").classes("text-gray-500 text-sm")

                with ui.row().classes("w-full items-center gap-4"):
                    ui.label("Batch Size:").classes("text-gray-400 w-32")
                    batch_input = ui.number(value=state.batch_size, min=1, max=16, step=1).props("dark dense").classes("w-32")
                    ui.label("Model inference batch size").classes("text-gray-500 text-sm")

                # Show active flags (read-only)
                with ui.row().classes("w-full items-center gap-2"):
                    ui.badge(f"Timbre: {'On' if state.use_timbre else 'Off'}", color="indigo" if state.use_timbre else "gray")
                    ui.badge(f"Overwrite: {'On' if state.embed_overwrite else 'Off'}", color="red" if state.embed_overwrite else "gray")

                # Pipeline progress UI
                pipe_progress = ui.linear_progress(value=0).props("rounded color=indigo").classes("w-full")
                pipe_label = ui.label("Idle").classes("text-gray-400 text-sm")

                async def run_pipeline():
                    from rbassist.utils import walk_audio
                    from rbassist.embed import build_embeddings
                    from rbassist.analyze import analyze_bpm_key
                    from rbassist.recommend import build_index

                    music_root = state.music_folder
                    if not music_root:
                        ui.notify("Set Music Folder first", type="warning")
                        return
                    files = walk_audio([music_root])
                    if not files:
                        ui.notify("No audio files found under Music Folder", type="warning")
                        return

                    total_steps = len(files) * 2 + 1  # embed + analyze + index
                    completed = 0
                    use_timbre = state.use_timbre
                    overwrite = state.embed_overwrite

                    def _update(label: str):
                        pipe_label.text = label
                        pipe_progress.value = min(max(completed / max(total_steps, 1), 0.0), 1.0)
                        pipe_progress.update()
                        pipe_label.update()

                    ui.notify(f"Running pipeline for {len(files)} track(s)...", type="info")
                    _update("Starting pipeline...")

                    async def _work():
                        nonlocal completed
                        # Embed
                        def _embed_cb(done: int, count: int, path: str):
                            nonlocal completed
                            completed = done
                            _update(f"Embedding {done}/{count}: {path}")

                        build_embeddings(
                            files,
                            duration_s=int(duration_input.value or state.duration_s),
                            device=(state.device if state.device != "auto" else None),
                            num_workers=int(workers_input.value or state.workers),
                            batch_size=int(batch_input.value or state.batch_size),
                            overwrite=overwrite,
                            timbre=use_timbre,
                            progress_callback=_embed_cb,
                        )
                        completed = len(files)
                        _update("Embedding complete")

                        # Analyze
                        def _analyze_cb(done: int, count: int, path: str):
                            nonlocal completed
                            completed = len(files) + done
                            _update(f"Analyzing {done}/{count}: {path}")

                        analyze_bpm_key(
                            files,
                            duration_s=90,
                            only_new=not overwrite,
                            force=overwrite,
                            add_cues=state.auto_cues,
                            workers=(int(workers_input.value) if int(workers_input.value) > 0 else None),
                            progress_callback=_analyze_cb,
                        )
                        completed = len(files) * 2
                        _update("Analyzing complete")

                        # Index
                        _update("Building index...")
                        build_index()
                        completed = total_steps
                        _update("Index built")

                    try:
                        await asyncio.to_thread(_work)
                        ui.notify("Embed + Analyze + Index complete", type="positive")
                    except Exception as e:
                        ui.notify(f"Pipeline failed: {e}", type="negative")

                ui.button("Embed + Analyze + Index", icon="play_arrow", on_click=run_pipeline).props("flat").classes(
                    "bg-indigo-600 hover:bg-indigo-500 w-64"
                )

        # Analysis Settings
        with ui.card().classes("w-full bg-[#1a1a1a] border border-[#333] p-4"):
            ui.label("Analysis").classes("text-lg font-semibold text-gray-200 mb-3")

            with ui.column().classes("gap-3"):
                cues_check = ui.checkbox("Auto-generate cue points", value=state.auto_cues).props("dark")
                skip_check = ui.checkbox("Skip already analyzed files", value=state.skip_analyzed).props("dark")
                ui.checkbox("Compute bass contour features", value=True).props("dark")

        # Data Paths
        with ui.card().classes("w-full bg-[#1a1a1a] border border-[#333] p-4"):
            ui.label("Data Locations").classes("text-lg font-semibold text-gray-200 mb-3")

            from rbassist.utils import DATA, EMB, IDX, META

            with ui.column().classes("gap-2"):
                for label, path in [
                    ("Data folder", DATA),
                    ("Embeddings", EMB),
                    ("Index", IDX),
                    ("Metadata", META),
                ]:
                    with ui.row().classes("w-full items-center gap-4"):
                        ui.label(f"{label}:").classes("text-gray-400 w-32")
                        ui.label(str(path)).classes("text-gray-300 font-mono text-sm")
                        exists = path.exists() if hasattr(path, "exists") else Path(path).exists()
                        if exists:
                            ui.icon("check_circle", size="sm").classes("text-green-500")
                        else:
                            ui.icon("warning", size="sm").classes("text-amber-500")

        # Save button
        def save_all_settings():
            try:
                # Update state from inputs
                state.music_folder = folder_input.value or ""
                state.device = device_select.value or "auto"
                state.duration_s = int(duration_input.value or 120)
                state.workers = int(workers_input.value or 4)
                state.batch_size = int(batch_input.value or 4)
                state.auto_cues = cues_check.value
                state.skip_analyzed = skip_check.value

                # Save to file
                state.save_settings()
                ui.notify("Settings saved successfully!", type="positive")
            except Exception as e:
                ui.notify(f"Error saving settings: {e}", type="negative")

        ui.button("Save Settings", icon="save", on_click=save_all_settings).props(
            "flat"
        ).classes("bg-indigo-600 hover:bg-indigo-500")
