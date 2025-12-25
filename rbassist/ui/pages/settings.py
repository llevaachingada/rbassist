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
    sync_guard: dict[str, bool] = {"busy": False}

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
                    last_add_result: dict[str, list[str]] = {"paths": []}

                    def _render_folder_list() -> None:
                        folder_list.clear()
                        with folder_list:
                            if not state.music_folders:
                                ui.label("No folders selected. Add one below.").classes("text-gray-500 text-sm")
                            for path in state.music_folders:
                                with ui.row().classes("w-full items-center gap-2"):
                                    ui.label(path).classes("text-gray-200 text-sm truncate")

                                    async def _import_one(p: str = path) -> None:
                                        await run_pipeline(roots=[p])

                                    def _remove(p: str = path) -> None:
                                        state.music_folders = [f for f in state.music_folders if f != p]
                                        _render_folder_list()

                                    ui.button(icon="play_arrow", on_click=_import_one).props("flat round dense").classes("text-indigo-400")
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
                        added_paths: list[str] = []
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
                            added_paths.append(resolved)

                        last_add_result["paths"] = added_paths
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

                    async def add_and_import() -> None:
                        raw = (folder_input.value or "").strip()
                        if not raw:
                            ui.notify("Paste a folder path first (or use the folder picker).", type="warning")
                            return
                        _add_folder(raw)
                        added_paths = last_add_result.get("paths", [])
                        if len(added_paths) == 1:
                            await run_pipeline(roots=[added_paths[0]])
                            return
                        if len(added_paths) > 1:
                            ui.notify("Added multiple folders; use the Import button next to the folder you want to process.", type="info")
                            return
                        # Duplicate or invalid; try importing the resolved path if it already exists in the list.
                        try:
                            resolved = str(Path(raw).expanduser().resolve())
                        except Exception:
                            resolved = ""
                        if resolved and resolved in state.music_folders:
                            await run_pipeline(roots=[resolved])
                        else:
                            ui.notify("No folder to import (nothing new added).", type="info")

                    with ui.column().classes("flex-1 gap-2"):
                        _render_folder_list()
                        with ui.row().classes("w-full items-center gap-2"):
                            ui.button(icon="folder", on_click=pick_folder).props("flat dense")
                            ui.button("Add path", on_click=lambda: _add_folder(folder_input.value)).props("flat dense").classes("bg-[#252525] text-gray-200")
                            ui.button("Add + Import", icon="play_arrow", on_click=add_and_import).props("flat dense").classes("bg-indigo-600 hover:bg-indigo-500 text-white")
                        ui.label("Tip: use Import next to a folder to process one folder at a time.").classes("text-gray-500 text-xs")

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

                # Pipeline options
                timbre_check = ui.checkbox("Use timbre embedding (OpenL3)", value=state.use_timbre).props("dark")

                def _on_overwrite_changed() -> None:
                    """Keep 'Overwrite' and 'Skip analyzed' in sync (inverse)."""
                    if sync_guard["busy"]:
                        return
                    sync_guard["busy"] = True
                    try:
                        skip_check.value = not bool(overwrite_check.value)
                        skip_check.update()
                    except Exception:
                        pass
                    finally:
                        sync_guard["busy"] = False

                overwrite_check = ui.checkbox(
                    "Overwrite existing tracks (re-embed + re-analyze)",
                    value=state.embed_overwrite,
                    on_change=_on_overwrite_changed,
                ).props("dark")
                ui.label("Tip: turn overwrite OFF to import a new folder without reprocessing your whole library.").classes("text-gray-500 text-xs")

                # Pipeline progress UI
                pipe_progress = ui.linear_progress(value=0).props("rounded color=indigo").classes("w-full")
                pipe_label = ui.label("Idle").classes("text-gray-400 text-sm")

                async def run_pipeline(roots: list[str] | None = None) -> None:
                    from rbassist.utils import walk_audio, load_meta
                    from rbassist.embed import build_embeddings
                    from rbassist.analyze import analyze_bpm_key
                    from rbassist.recommend import build_index

                    # If user pasted paths but didn't click "Add path", ingest them now (default scope only)
                    default_scope = roots is None
                    if roots is None:
                        if folder_input.value:
                            _add_folder(folder_input.value)
                        roots = list(state.music_folders)

                    roots = [str(p) for p in (roots or []) if str(p).strip()]

                    # Filter out missing paths but warn the user
                    music_roots = [p for p in roots if Path(p).exists()]
                    missing = [p for p in roots if p not in music_roots]
                    if missing:
                        ui.notify(f"Skipping missing folder(s): {', '.join(missing)}", type="warning")
                    if not music_roots:
                        ui.notify("Set at least one Music Folder first", type="warning")
                        return
                    files = walk_audio(music_roots)
                    if not files:
                        ui.notify("No audio files found under the selected folder(s)", type="warning")
                        return

                    completed = 0
                    overwrite = bool(overwrite_check.value)
                    skip_analyzed = bool(skip_check.value)
                    use_timbre = bool(timbre_check.value)

                    meta = load_meta()

                    embed_files = files
                    if not overwrite:
                        embed_files = []
                        for f in files:
                            info = meta.get("tracks", {}).get(f, {})
                            epath = info.get("embedding")
                            if not epath or not Path(epath).exists():
                                embed_files.append(f)

                    analysis_files = files
                    if skip_analyzed and not overwrite:
                        analysis_files = [
                            f for f in files
                            if not (
                                meta.get("tracks", {}).get(f, {}).get("bpm")
                                and meta.get("tracks", {}).get(f, {}).get("key")
                            )
                        ]

                    bg_files: list[str] = []
                    if beatgrid_check.value:
                        if beatgrid_overwrite_check.value:
                            bg_files = files
                        else:
                            bg_files = [
                                f for f in files
                                if not meta.get("tracks", {}).get(f, {}).get("tempos")
                            ]

                    total_steps = max(1, len(embed_files) + len(analysis_files) + len(bg_files) + 1)

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
                        scope_label = "all folders" if default_scope else f"{len(music_roots)} folder(s)"
                        if not default_scope and len(music_roots) == 1:
                            scope_label = Path(music_roots[0]).name
                        ui.notify(
                            f"Running pipeline on {scope_label}: {len(files)} track(s) "
                            f"({len(embed_files)} embed, {len(analysis_files)} analyze)...",
                            type="info",
                        )
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

                        if embed_files:
                            build_embeddings(
                                embed_files,
                                duration_s=120,
                                device=(device_select.value if device_select.value != "auto" else None),
                                num_workers=int(workers_input.value or 0),
                                batch_size=int(batch_input.value or 4),
                                overwrite=True,
                                timbre=use_timbre,
                                progress_callback=_embed_cb,
                            )
                            completed = len(embed_files)
                            _update("Embedding complete")
                        else:
                            completed = 0
                            _update("Embedding skipped (no targets)")

                        # Analyze
                        def _analyze_cb(done: int, count: int, path: str):
                            nonlocal completed
                            completed = len(embed_files) + done
                            _update(f"Analyzing {done}/{count}: {path}")

                        if analysis_files:
                            analyze_bpm_key(
                                analysis_files,
                                duration_s=90,
                                only_new=not overwrite,
                                force=overwrite,
                                add_cues=bool(cues_check.value),
                                workers=(int(workers_input.value) if int(workers_input.value) > 0 else None),
                                progress_callback=_analyze_cb,
                            )
                            completed = len(embed_files) + len(analysis_files)
                            _update("Analyzing complete")
                        else:
                            completed = len(embed_files)
                            _update("Analyzing skipped (no targets)")

                        # Beatgrid (optional)
                        if beatgrid_check.value:
                            if bg_files:
                                def _bg_cb(done: int, count: int, path: str):
                                    nonlocal completed
                                    completed = len(embed_files) + len(analysis_files) + done
                                    _update(f"Beatgrid {done}/{count}: {path}")

                                _update(f"Beatgridding {len(bg_files)} track(s)...")
                                analyze_beatgrid_paths(
                                    bg_files,
                                    cfg=BeatgridConfig(mode="fixed", backend="beatnet"),
                                    overwrite=beatgrid_overwrite_check.value,
                                    progress_callback=_bg_cb,
                                )
                                completed = len(embed_files) + len(analysis_files) + len(bg_files)
                            else:
                                completed = len(embed_files) + len(analysis_files)
                                _update("Beatgrid skipped (no targets)")

                        # Index
                        _update("Building index...")
                        build_index(incremental=not overwrite)
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

                ui.button("Process all folders (Embed + Analyze + Index)", icon="play_arrow", on_click=run_pipeline).props("flat").classes(
                    "bg-indigo-600 hover:bg-indigo-500 w-64"
                )

        # Analysis Settings
        with ui.card().classes("w-full bg-[#1a1a1a] border border-[#333] p-4"):
            ui.label("Analysis").classes("text-lg font-semibold text-gray-200 mb-3")

            with ui.column().classes("gap-3"):
                cues_check = ui.checkbox("Auto-generate cue points", value=state.auto_cues).props("dark")

                def _on_skip_changed() -> None:
                    """Keep 'Skip analyzed' and 'Overwrite' in sync (inverse)."""
                    if sync_guard["busy"]:
                        return
                    sync_guard["busy"] = True
                    try:
                        overwrite_check.value = not bool(skip_check.value)
                        overwrite_check.update()
                    finally:
                        sync_guard["busy"] = False

                skip_check = ui.checkbox(
                    "Skip already analyzed tracks",
                    value=state.skip_analyzed,
                    on_change=_on_skip_changed,
                ).props("dark")
                beatgrid_check = ui.checkbox("Analyze beatgrid", value=state.beatgrid_enable).props("dark")
                beatgrid_overwrite_check = ui.checkbox("Overwrite existing beatgrid", value=state.beatgrid_overwrite).props("dark")
                ui.label("Bass/rhythm contour features are computed automatically (when available).").classes("text-gray-500 text-xs")

                mismatch = bool(overwrite_check.value) == bool(skip_check.value)
                sync_guard["busy"] = True
                try:
                    overwrite_check.value = not bool(skip_check.value)
                    overwrite_check.update()
                finally:
                    sync_guard["busy"] = False
                if mismatch:
                    ui.label("Note: Overwrite + Skip were out of sync; they are now linked.").classes("text-amber-500 text-xs")

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

        # How-To
        with ui.card().classes("w-full bg-[#1a1a1a] border border-[#333] p-4"):
            ui.label("How-To").classes("text-lg font-semibold text-gray-200 mb-3")

            with ui.tabs().classes("text-gray-400") as howto_tabs:
                ui.tab("howto", label="How to use", icon="help")
                ui.tab("faq", label="FAQ", icon="quiz")

            with ui.tab_panels(howto_tabs, value="howto").classes("w-full"):
                with ui.tab_panel("howto"):
                    ui.markdown(
                        """
                        **Import one folder at a time**
                        1. Add Music Folders (folder icon or paste a path).
                        2. Click the **play** icon next to the folder you want to import (or use **Add + Import**).
                        3. Keep **Overwrite** OFF to only process new tracks (recommended).
                        4. Click **Save Settings** if you want these choices to persist.

                        **Full rebuild**
                        - Turn **Overwrite** ON, then click **Process all folders**.
                        """
                    ).classes("text-gray-300")

                with ui.tab_panel("faq"):
                    ui.markdown(
                        """
                        - **Overwrite vs Skip analyzed:** these are linked; turning Overwrite ON turns Skip analyzed OFF (and vice-versa).
                        - **Why is Discover empty?** Discover needs an index; run the pipeline (folder Import or Process all folders).
                        - **What does Timbre do?** Adds extra texture features; it is slower and requires `openl3` installed.
                        """
                    ).classes("text-gray-300")

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
                state.use_timbre = bool(timbre_check.value)
                state.embed_overwrite = bool(overwrite_check.value)
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
