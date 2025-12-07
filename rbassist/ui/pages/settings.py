"""Settings page - configuration and preferences."""

from __future__ import annotations

from pathlib import Path
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

                    async def pick_folder():
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
                            ui.notify(f"Error: {e}", type="negative")

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
                    ui.label("Duration (s):").classes("text-gray-400 w-32")
                    duration_input = ui.number(value=state.duration_s, min=30, max=300, step=10).props("dark dense").classes("w-32")
                    ui.label("Seconds of audio to analyze per track").classes("text-gray-500 text-sm")

                with ui.row().classes("w-full items-center gap-4"):
                    ui.label("Workers:").classes("text-gray-400 w-32")
                    workers_input = ui.number(value=state.workers, min=0, max=16, step=1).props("dark dense").classes("w-32")
                    ui.label("Parallel audio loaders (0 = serial)").classes("text-gray-500 text-sm")

                with ui.row().classes("w-full items-center gap-4"):
                    ui.label("Batch Size:").classes("text-gray-400 w-32")
                    batch_input = ui.number(value=state.batch_size, min=1, max=16, step=1).props("dark dense").classes("w-32")
                    ui.label("Model inference batch size").classes("text-gray-500 text-sm")

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
