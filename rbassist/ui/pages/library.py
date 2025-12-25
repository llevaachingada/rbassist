from __future__ import annotations

import asyncio
from pathlib import Path
from nicegui import ui

from ..state import get_state
from ..components.track_table import TrackTable
from rbassist.utils import walk_audio
from rbassist.embed import build_embeddings
from rbassist.analyze import analyze_bpm_key
from rbassist.recommend import build_index
from rbassist.beatgrid import analyze_paths as analyze_beatgrid_paths, BeatgridConfig


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

        # Folder selection
        folder_list = ui.label(f"Folders: {', '.join(state.music_folders) or 'No folders selected'}").classes("text-lg")

        with ui.row().classes("w-full gap-4"):
            ui.button(
                "Analyze Library",
                icon="music_note",
                on_click=lambda: ui.notify(
                    "Use Settings ƒ+' Embed + Analyze + Index to run the full pipeline.",
                    type="info",
                ),
            ).classes("w-1/2 bg-blue-600 text-white")

        # Beatgrid controls (fixed vs dynamic)
        with ui.card().classes("w-full bg-[#1a1a1a] border border-[#333] p-4"):
            ui.label("Beatgrid").classes("text-lg font-semibold text-gray-200 mb-2")
            mode_toggle = ui.toggle(["fixed", "dynamic"], value="fixed").props("dense").classes("text-gray-200")
            backend_select = ui.select(
                ["auto", "beatnet", "librosa"],
                value="auto",
            ).props("dark dense").classes("w-36")
            drift_input = ui.number(value=1.5, min=0.1, max=5.0, step=0.1).props("dark dense").classes("w-28")
            bars_input = ui.number(value=16, min=4, max=64, step=4).props("dark dense").classes("w-28")
            duration_input = ui.number(value=0, min=0, max=600, step=10).props("dark dense").classes("w-28")
            overwrite_check = ui.checkbox("Overwrite existing", value=False).props("dark")
            ui.label("Dynamic splits when tempo drifts beyond the threshold over the given bars; fixed keeps one BPM.").classes("text-gray-500 text-sm mb-2")

            async def _beatgrid_paths(paths: list[str]) -> None:
                if not paths:
                    ui.notify("No audio files found.", type="warning")
                    return
                cfg = BeatgridConfig(
                    mode=str(mode_toggle.value).strip().lower(),
                    backend=str(backend_select.value or "auto").strip().lower(),
                    drift_pct=float(drift_input.value or 1.5),
                    bars_window=int(bars_input.value or 16),
                    duration_s=int(duration_input.value or 0),
                )
                ui.notify(f"Beatgridding {len(paths)} track(s)...", type="info")

                def _work():
                    targets = paths
                    if not overwrite_check.value:
                        meta = state.meta
                        targets = [p for p in paths if not meta.get("tracks", {}).get(p, {}).get("tempos")]
                    analyze_beatgrid_paths(targets, cfg=cfg, overwrite=overwrite_check.value)

                await asyncio.to_thread(_work)
                state.refresh_meta()
                ui.notify("Beatgrid complete", type="positive")

            async def _run_music_folders():
                if not state.music_folders:
                    ui.notify("Set Music Folders in Settings first.", type="warning")
                    return
                files = walk_audio(state.music_folders)
                await _beatgrid_paths(files)

            async def _run_single_file():
                try:
                    result = await ui.run_javascript('''
                        return await new Promise(resolve => {
                            const input = document.createElement('input');
                            input.type = 'file';
                            input.accept = '.wav,.flac,.mp3,.m4a,.aiff,.aif';
                            input.onchange = () => {
                                const file = input.files[0];
                                resolve(file ? file.path || file.name : null);
                            };
                            input.click();
                        });
                    ''')
                except Exception:
                    ui.notify("File picker not supported in this session.", type="warning")
                    return
                if not result:
                    ui.notify("No file selected.", type="info")
                    return
                await _beatgrid_paths([str(result)])

            with ui.row().classes("gap-3 items-center"):
                ui.button("Beatgrid music folders", icon="timeline", on_click=_run_music_folders).props("flat").classes(
                    "bg-indigo-600 hover:bg-indigo-500 text-white"
                )
                ui.button("Beatgrid single file", icon="audiotrack", on_click=_run_single_file).props("flat").classes(
                    "bg-purple-600 hover:bg-purple-500 text-white"
                )
                ui.label("Mode").classes("text-gray-400")
                mode_toggle
                ui.label("Drift %").classes("text-gray-400")
                drift_input
                ui.label("Bars").classes("text-gray-400")
                bars_input
                ui.label("Duration cap (s)").classes("text-gray-400")
                duration_input
                overwrite_check

            async def _export_rekordbox():
                try:
                    from rbassist.export_xml import write_rekordbox_xml
                    from rbassist.utils import load_meta
                    meta = load_meta()
                    out = "rbassist_beatgrid.xml"
                    await asyncio.to_thread(write_rekordbox_xml, meta, out, playlist_name="rbassist export")
                    ui.notify(f"Exported -> {out}", type="positive")
                except Exception as e:
                    ui.notify(f"Export failed: {e}", type="negative")

            ui.button("Export Rekordbox XML", icon="download", on_click=_export_rekordbox).props("flat").classes(
                "bg-teal-600 hover:bg-teal-500 text-white mt-2"
            )

        # Rest of the original track table rendering remains the same
        tracks = state.meta.get("tracks", {})
        rows = []
        for path, info in list(tracks.items())[:500]:  # Limit for performance
            tags = info.get("mytags") or info.get("tags") or []
            if isinstance(tags, (list, tuple)):
                tags_str = ", ".join(str(t) for t in tags)
            else:
                tags_str = str(tags)

            rows.append({
                "path": path,
                "artist": info.get("artist", ""),
                "title": info.get("title", path.split("\\")[-1].split("/")[-1]),
                "bpm": f"{info.get('bpm', 0):.0f}" if info.get("bpm") else "-",
                "key": info.get("key", "-"),
                "embedded": "Yes" if info.get("embedding") else "No",
                "analyzed": "Yes" if info.get("bpm") and info.get("key") else "No",
                "beatgrid": "Yes" if info.get("tempos") else "No",
                "mytags": tags_str,
            })

        with ui.card().classes("w-full bg-[#1a1a1a] border border-[#333] p-0"):
            table = TrackTable(
                extra_columns=[
                    {"name": "embedded", "label": "Embedded", "field": "embedded", "sortable": True, "align": "center"},
                    {"name": "analyzed", "label": "Analyzed", "field": "analyzed", "sortable": True, "align": "center"},
                    {"name": "beatgrid", "label": "Beatgrid", "field": "beatgrid", "sortable": True, "align": "center"},
                    {"name": "mytags", "label": "MyTags", "field": "mytags", "sortable": False, "align": "left"},
                ],
            )
            table.build()
            table.update(rows)

        ui.label(f"Showing {len(rows)} of {len(tracks)} tracks").classes("text-gray-500 text-sm")
