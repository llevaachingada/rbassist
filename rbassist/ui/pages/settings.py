"""Settings page - configuration and preferences."""

from __future__ import annotations

from pathlib import Path
import asyncio
import shlex
import re
from nicegui import ui

from ..state import get_state
from rbassist.beatgrid import analyze_paths as analyze_beatgrid_paths, BeatgridConfig


def render() -> None:
    """Render the settings page."""
    state = get_state()

    with ui.column().classes("w-full gap-4 max-w-3xl"):
        ui.label("Settings").classes("text-2xl font-bold text-white")

        # Workspace
        with ui.card().classes("w-full bg-[#1a1a1a] border border-[#333] p-4"):
            ui.label("Workspace").classes("text-lg font-semibold text-gray-200 mb-3")

            with ui.column().classes("gap-4"):
                with ui.row().classes("w-full items-start gap-4"):
                    ui.label("Music Folders:").classes("text-gray-400 w-32 pt-1")

                    folder_list = ui.column().classes("flex-1 gap-2")
                    folder_input = ui.input(
                        value="",
                        placeholder="Paste a folder path to add..."
                    ).props("dark dense").classes("w-full")

                    def _render_folder_list() -> None:
                        folder_list.clear()
                        with folder_list:
                            if not state.music_folders:
                                ui.label("No folders selected. Add one below.").classes("text-gray-500 text-sm")
                            for path in state.music_folders:
                                with ui.row().classes("w-full items-center gap-2"):
                                    ui.label(path).classes("text-gray-200 text-sm truncate")

                                    def _remove(p: str = path) -> None:
                                        state.music_folders = [f for f in state.music_folders if f != p]
                                        _render_folder_list()

                                    ui.button(icon="close", on_click=_remove).props("flat round dense").classes("text-gray-400")

                    def _add_folder(val: str) -> None:
                        def _parse_folder_inputs(raw: str) -> list[str]:
                            if not raw:
                                return []
                            tokens: list[str] = []

                            def _strip_quotes(s: str) -> str:
                                s = s.strip()
                                if len(s) >= 2 and s[0] == s[-1] and s[0] in {"'", '"', "“", "”", "‘", "’"}:
                                    return s[1:-1]
                                # handle mismatched leading/trailing smart quotes
                                if s[:1] in {"'", '"', "“", "”", "‘", "’"}:
                                    s = s[1:]
                                if s[-1:] in {"'", '"', "“", "”", "‘", "’"}:
                                    s = s[:-1]
                                return s.strip()

                            def _extract_quoted(line: str) -> list[str]:
                                # Look for "quoted", 'quoted', or “smart quoted” segments
                                matches = re.findall(r'"([^"]+)"|“([^”]+)”|\'([^\']+)\'|‘([^’]+)’', line)
                                out: list[str] = []
                                for a, b, c, d in matches:
                                    candidate = a or b or c or d
                                    if candidate:
                                        out.append(candidate)
                                return out

                            for line in raw.replace("\r", "\n").split("\n"):
                                line = line.strip()
                                if not line:
                                    continue
                                try:
                                    parts = shlex.split(line, posix=False)
                                except ValueError:
                                    parts = [line]
                                # Fallback: if shlex returned one long string but we had multiple quoted segments
                                if len(parts) == 1:
                                    quoted = _extract_quoted(line)
                                    if len(quoted) > 1:
                                        parts = quoted
                                for part in parts:
                                    for piece in part.split(";"):
                                        piece = _strip_quotes(piece)
                                        if piece:
                                            tokens.append(piece)
                            return tokens

                        paths = _parse_folder_inputs(val)
                        if not paths:
                            ui.notify("Folder path is empty", type="warning")
                            return
                        added = 0
                        skipped_dupe = 0
                        missing: list[str] = []

                        for raw_path in paths:
                            p = Path(raw_path).expanduser()
                            if not p.exists():
                                missing.append(str(raw_path))
                                continue
                            resolved = str(p.resolve())
                            if resolved in state.music_folders:
                                skipped_dupe += 1
                                continue
                            state.music_folders.append(resolved)
                            added += 1

                        folder_input.value = ""
                        _render_folder_list()
                        if added:
                            ui.notify(f"Added {added} folder(s)", type="positive")
                        if skipped_dupe:
                            ui.notify(f"{skipped_dupe} duplicate folder(s) skipped", type="info")
                        if missing:
                            ui.notify(f"Folder does not exist: {', '.join(missing)}", type="warning")

                    def pick_folder():
                        try:
                            import tkinter as tk
                            from tkinter import filedialog
                            root = tk.Tk()
                            root.withdraw()
                            folder = filedialog.askdirectory(title="Select Music Folder")
                            root.destroy()
                            if folder:
                                _add_folder(folder)
                            else:
                                ui.notify("No folder selected. Paste a path instead.", type="info")
                        except Exception as e:
                            ui.notify(f"Folder picker error: {e}. Paste a path instead.", type="warning")

                    with ui.column().classes("flex-1 gap-2"):
                        _render_folder_list()
                        with ui.row().classes("w-full items-center gap-2"):
                            ui.button(icon="folder", on_click=pick_folder).props("flat dense")
                            ui.button("Add path", on_click=lambda: _add_folder(folder_input.value)).props("flat dense").classes("bg-[#252525] text-gray-200")
                        ui.label("You can add multiple folders; all will be scanned.").classes("text-gray-500 text-xs")

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
                    # Hard-wired to canonical default; UI is informational only.
                    duration_input = ui.number(value=120, min=120, max=120, step=0).props("dark dense readonly").classes("w-32")
                    ui.label("Fixed: canonical intro/core/late windowing (120s cap)").classes("text-gray-500 text-sm")

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

                    # If user pasted paths but didn't click "Add path", ingest them now
                    if folder_input.value:
                        _add_folder(folder_input.value)
                    # Filter out missing paths but warn the user
                    music_roots = [p for p in state.music_folders if Path(p).exists()]
                    missing = [p for p in state.music_folders if p not in music_roots]
                    if missing:
                        ui.notify(f"Skipping missing folder(s): {', '.join(missing)}", type="warning")
                    if not music_roots:
                        ui.notify("Set at least one Music Folder first", type="warning")
                        return
                    files = walk_audio(music_roots)
                    if not files:
                        ui.notify("No audio files found under Music Folders", type="warning")
                        return

                    total_steps = len(files) * 2 + 1  # embed + analyze + index
                    if beatgrid_check.value:
                        total_steps += 1
                    completed = 0
                    use_timbre = True
                    overwrite = state.embed_overwrite

                    def _update(label: str):
                        """Safely update progress UI; ignore if client/slot is gone."""
                        try:
                            pipe_label.text = label
                            pipe_progress.value = min(max(completed / max(total_steps, 1), 0.0), 1.0)
                            pipe_progress.update()
                            pipe_label.update()
                        except RuntimeError:
                            # Client or parent element has been deleted (tab closed/reloaded);
                            # allow background pipeline to continue silently.
                            pass

                    try:
                        ui.notify(f"Running pipeline for {len(files)} track(s)...", type="info")
                    except RuntimeError:
                        # Same rationale as _update: UI may no longer be attached.
                        pass
                    _update("Starting pipeline...")

                    def _work():
                        nonlocal completed
                        # Embed
                        def _embed_cb(done: int, count: int, path: str):
                            nonlocal completed
                            completed = done
                            _update(f"Embedding {done}/{count}: {path}")

                        build_embeddings(
                            files,
                            duration_s=120,
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

                        # Beatgrid (optional)
                        if beatgrid_check.value:
                            bg_files = files
                            if not beatgrid_overwrite_check.value:
                                from rbassist.utils import load_meta
                                meta = load_meta()
                                bg_files = [
                                    f for f in files
                                    if not meta.get("tracks", {}).get(f, {}).get("tempos")
                                ]
                            if bg_files:
                                _update(f"Beatgridding {len(bg_files)} track(s)...")
                                analyze_beatgrid_paths(
                                    bg_files,
                                    cfg=BeatgridConfig(mode="fixed", backend="auto"),
                                    overwrite=beatgrid_overwrite_check.value,
                                )
                            else:
                                _update("Beatgrid skipped (no targets)")

                        # Index
                        _update("Building index...")
                        build_index()
                        completed = total_steps
                        _update("Index built")

                    try:
                        await asyncio.to_thread(_work)
                        try:
                            ui.notify("Embed + Analyze + Index complete", type="positive")
                        except RuntimeError:
                            # Client may have gone away; pipeline still finished.
                            pass
                    except Exception as e:
                        try:
                            ui.notify(f"Pipeline failed: {e}", type="negative")
                        except RuntimeError:
                            # If the client is gone we can't surface the error in UI;
                            # let it be visible in the terminal logs only.
                            pass

                ui.button("Embed + Analyze + Index", icon="play_arrow", on_click=run_pipeline).props("flat").classes(
                    "bg-indigo-600 hover:bg-indigo-500 w-64"
                )

        # Analysis Settings
        with ui.card().classes("w-full bg-[#1a1a1a] border border-[#333] p-4"):
            ui.label("Analysis").classes("text-lg font-semibold text-gray-200 mb-3")

            with ui.column().classes("gap-3"):
                cues_check = ui.checkbox("Auto-generate cue points", value=state.auto_cues).props("dark")
                skip_check = ui.checkbox("Skip already analyzed files", value=state.skip_analyzed).props("dark")
                beatgrid_check = ui.checkbox("Analyze beatgrid", value=state.beatgrid_enable).props("dark")
                beatgrid_overwrite_check = ui.checkbox("Overwrite existing beatgrid", value=state.beatgrid_overwrite).props("dark")
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
                if folder_input.value:
                    _add_folder(folder_input.value)
                # Update state from inputs
                state.music_folders = [str(Path(f).resolve()) for f in state.music_folders if Path(f).exists()]
                state.device = device_select.value or "auto"
                state.duration_s = int(duration_input.value or 120)
                state.workers = int(workers_input.value or 4)
                state.batch_size = int(batch_input.value or 4)
                state.auto_cues = cues_check.value
                state.skip_analyzed = skip_check.value
                state.beatgrid_enable = beatgrid_check.value
                state.beatgrid_overwrite = beatgrid_overwrite_check.value

                # Save to file
                state.save_settings()
                ui.notify("Settings saved successfully!", type="positive")
            except Exception as e:
                ui.notify(f"Error saving settings: {e}", type="negative")

        ui.button("Save Settings", icon="save", on_click=save_all_settings).props(
            "flat"
        ).classes("bg-indigo-600 hover:bg-indigo-500")
