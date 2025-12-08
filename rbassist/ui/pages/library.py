"""Library page - track browser and operations."""

from __future__ import annotations

import asyncio
from nicegui import ui

from ..state import get_state
from ..components.track_table import TrackTable
from ..components.progress import ProgressPanel
from rbassist.utils import walk_audio
from rbassist.embed import build_embeddings
from rbassist.analyze import analyze_bpm_key
from rbassist.recommend import build_index


def render() -> None:
    """Render the library page."""
    state = get_state()
    state.refresh_meta()

    with ui.column().classes("w-full gap-4"):
        # Header with stats
        with ui.row().classes("w-full items-center justify-between"):
            ui.label("Library").classes("text-2xl font-bold text-white")
            with ui.row().classes("gap-4"):
                ui.badge(f"{state.get_track_count()} tracks", color="gray")
                ui.badge(f"{state.get_embedded_count()} embedded", color="indigo")
                ui.badge(f"{state.get_analyzed_count()} analyzed", color="purple")

        # Status bar
        with ui.row().classes("w-full items-center gap-4 text-sm text-gray-300"):
            ui.label(f"Folder: {state.music_folder or '(not set)'}")
            ui.label(f"Index: {'yes' if state.has_index() else 'missing'}")
            ui.label(f"Timbre: {'On' if state.use_timbre else 'Off'}")
            ui.label(f"Overwrite: {'On' if state.embed_overwrite else 'Off'}")

        # Pipeline helpers
        progress_dialog = ui.dialog()
        with progress_dialog:
            with ui.card().classes("w-96 bg-[#1a1a1a] border border-[#333] p-4"):
                prog_label = ui.label("Preparing...").classes("text-gray-300 text-sm")
                prog_bar = ui.linear_progress(value=0).props("rounded color=indigo").classes("w-full mt-2")

        async def run_pipeline(mode: str):
            """Run pipeline with simple progress.
            mode: 'full' (embed+analyze+index), 'analyze' (analyze+index), 'index' (index only).
            """
            music_root = state.music_folder
            if not music_root:
                ui.notify("Set Music Folder in Settings first", type="warning")
                return
            files = walk_audio([music_root])
            if not files:
                ui.notify("No audio files found under Music Folder", type="warning")
                return

            progress_dialog.open()
            prog_bar.value = 0
            prog_label.text = f"Starting {mode}..."
            prog_bar.update()
            prog_label.update()

            overwrite = state.embed_overwrite
            use_timbre = state.use_timbre
            if mode == "full":
                total_steps = len(files) * 2 + 1
            elif mode == "analyze":
                total_steps = len(files) + 1
            else:
                total_steps = 1
            done = 0

            def _update(lbl: str):
                prog_label.text = lbl
                if total_steps > 0:
                    prog_bar.value = min(max(done / total_steps, 0.0), 1.0)
                prog_bar.update()
                prog_label.update()

            async def _work():
                nonlocal done
                try:
                    if mode == "full":
                        def _embed_cb(d: int, c: int, path: str):
                            nonlocal done
                            done = d
                            _update(f"Embedding {d}/{c}: {path}")

                        build_embeddings(
                            files,
                            duration_s=state.duration_s,
                            device=(state.device if state.device != "auto" else None),
                            num_workers=state.workers,
                            batch_size=state.batch_size,
                            overwrite=overwrite,
                            timbre=use_timbre,
                            progress_callback=_embed_cb,
                        )
                        done = len(files)
                        _update("Embedding complete")
                        # Analyze
                        def _an_cb(d: int, c: int, path: str):
                            nonlocal done
                            done = len(files) + d
                            _update(f"Analyzing {d}/{c}: {path}")

                        analyze_bpm_key(
                            files,
                            duration_s=90,
                            only_new=not overwrite,
                            force=overwrite,
                            add_cues=state.auto_cues,
                            workers=(state.workers if state.workers and state.workers > 0 else None),
                            progress_callback=_an_cb,
                        )
                        done = len(files) * 2
                        _update("Analysis complete")
                        _update("Building index...")
                        build_index()
                        done = total_steps
                        _update("Index rebuilt")

                    elif mode == "analyze":
                        def _an_cb(d: int, c: int, path: str):
                            nonlocal done
                            done = d
                            _update(f"Analyzing {d}/{c}: {path}")

                        analyze_bpm_key(
                            files,
                            duration_s=90,
                            only_new=not overwrite,
                            force=overwrite,
                            add_cues=state.auto_cues,
                            workers=(state.workers if state.workers and state.workers > 0 else None),
                            progress_callback=_an_cb,
                        )
                        done = total_steps
                        _update("Analysis complete")
                        build_index()
                        _update("Index rebuilt")

                    elif mode == "index":
                        _update("Building index...")
                        build_index()
                        done = total_steps
                        _update("Index rebuilt")
                finally:
                    state.refresh_meta()

            try:
                await asyncio.to_thread(_work)
                ui.notify(f"{mode.title()} pipeline complete", type="positive")
            except Exception as e:
                ui.notify(f"{mode.title()} failed: {e}", type="negative")
            finally:
                progress_dialog.close()

        # Action buttons
        with ui.row().classes("w-full gap-2"):
            ui.button("Embed + Analyze + Index", icon="play_arrow", on_click=lambda: run_pipeline("full")).props(
                "flat"
            ).classes("bg-indigo-600 hover:bg-indigo-500")
            ui.button("Analyze + Index", icon="music_note", on_click=lambda: run_pipeline("analyze")).props(
                "flat"
            ).classes("bg-purple-600 hover:bg-purple-500")
            ui.button("Rebuild Index", icon="refresh", on_click=lambda: run_pipeline("index")).props(
                "flat"
            ).classes("bg-[#252525] hover:bg-[#333] text-gray-300")
            ui.button("Export XML", icon="download", on_click=lambda: ui.notify("Export coming soon")).props(
                "flat"
            ).classes("bg-[#252525] hover:bg-[#333] text-gray-300")

        # Progress panel (hidden by default)
        progress = ProgressPanel("Processing")

        # Search/filter bar
        with ui.row().classes("w-full gap-4 items-center"):
            search = ui.input(placeholder="Search tracks...").props("dark dense clearable").classes("flex-1")
            ui.select(
                ["All", "Has Embedding", "Needs Embedding", "Analyzed", "Not Analyzed"],
                value="All",
            ).props("dark dense").classes("w-48")

        # Track table
        tracks = state.meta.get("tracks", {})
        rows = []
        for path, info in list(tracks.items())[:500]:  # Limit for performance
            rows.append({
                "path": path,
                "artist": info.get("artist", ""),
                "title": info.get("title", path.split("\\")[-1].split("/")[-1]),
                "bpm": f"{info.get('bpm', 0):.0f}" if info.get("bpm") else "-",
                "key": info.get("key", "-"),
                "embedded": "Yes" if info.get("embedding") else "No",
                "analyzed": "Yes" if info.get("bpm") and info.get("key") else "No",
            })

        with ui.card().classes("w-full bg-[#1a1a1a] border border-[#333] p-0"):
            table = TrackTable(
                extra_columns=[
                    {"name": "embedded", "label": "Embedded", "field": "embedded", "sortable": True, "align": "center"},
                    {"name": "analyzed", "label": "Analyzed", "field": "analyzed", "sortable": True, "align": "center"},
                ],
            )
            table.build()
            table.update(rows)

        ui.label(f"Showing {len(rows)} of {len(tracks)} tracks").classes("text-gray-500 text-sm")
