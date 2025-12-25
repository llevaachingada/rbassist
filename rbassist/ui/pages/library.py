from __future__ import annotations

import asyncio
import base64
import io
from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import numpy as np
import librosa
from nicegui import ui

from ..state import get_state
from ..components.track_table import TrackTable
from rbassist.utils import walk_audio
from rbassist.embed import build_embeddings
from rbassist.analyze import analyze_bpm_key
from rbassist.recommend import build_index
from rbassist.beatgrid import analyze_paths as analyze_beatgrid_paths, BeatgridConfig, analyze_file


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

            with ui.column().classes("gap-2"):
                ui.label("Choose backend and thresholds").classes("text-gray-400 text-sm")
                mode_toggle = ui.toggle(["fixed", "dynamic"], value="fixed").props("dense").classes("text-gray-200")
                backend_select = ui.select(
                    ["beatnet", "auto", "librosa"],
                    value="beatnet",
                ).props("dark dense").classes("w-40")
                with ui.row().classes("gap-3 items-center"):
                    ui.label("Drift %").classes("text-gray-400")
                    drift_input = ui.number(value=1.5, min=0.1, max=5.0, step=0.1).props("dark dense").classes("w-28")
                    ui.label("Bars window").classes("text-gray-400")
                    bars_input = ui.number(value=16, min=4, max=64, step=4).props("dark dense").classes("w-28")
                    ui.label("Duration cap (s)").classes("text-gray-400")
                    duration_input = ui.number(value=0, min=0, max=600, step=10).props("dark dense").classes("w-28")
                overwrite_check = ui.checkbox("Overwrite existing beatgrids", value=False).props("dark")
                ui.label("Fixed: single BPM. Dynamic: new segment when tempo drifts beyond the threshold over the window. Backend: BeatNet (GPU if available), auto (try BeatNet then fallback), or librosa (CPU).").classes("text-gray-500 text-sm")

            # Beatgrid preview (first ~16 bars)
            preview_path: dict[str, Optional[str]] = {"path": None}
            preview_img = ui.image().style("max-width: 100%; display: none;")
            preview_label = ui.label("").classes("text-gray-400 text-sm")

            async def _pick_preview_file():
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
                if result:
                    preview_path["path"] = str(result)
                    preview_label.text = f"Preview: {preview_path['path']}"
                    preview_label.update()
                else:
                    ui.notify("No file selected.", type="info")

            async def _render_preview():
                if not preview_path.get("path"):
                    ui.notify("Pick a file to preview.", type="warning")
                    return
                cfg = BeatgridConfig(
                    mode=str(mode_toggle.value).strip().lower(),
                    backend=str(backend_select.value or "beatnet").strip().lower(),
                    drift_pct=float(drift_input.value or 1.5),
                    bars_window=int(bars_input.value or 16),
                    duration_s=int(duration_input.value or 0),
                )

                def _work():
                    # Run beatgrid to get beats
                    _path, result, err, warns = analyze_file(preview_path["path"], cfg)
                    if err or result is None or not result.get("beats"):
                        return None, err or "no beats detected", warns
                    beats = np.array(result["beats"], dtype=float)
                    # Limit to first ~16 bars (~64 beats)
                    max_beats = 64
                    if beats.size == 0:
                        return None, "no beats detected", warns
                    cutoff_idx = min(len(beats) - 1, max_beats - 1)
                    window_end = beats[cutoff_idx] + 1.0
                    y, sr = librosa.load(preview_path["path"], sr=None, mono=True, duration=window_end)
                    t = np.linspace(0, len(y) / sr, num=len(y))
                    fig, ax = plt.subplots(figsize=(8, 2))
                    ax.plot(t, y, color="#4ade80", linewidth=0.8)
                    for b in beats:
                        if b <= window_end:
                            ax.axvline(b, color="#f472b6", linestyle="--", linewidth=0.6, alpha=0.8)
                    ax.set_xlim(0, window_end)
                    ax.set_xlabel("Seconds")
                    ax.set_ylabel("Amplitude")
                    ax.set_title("Beatgrid preview (first ~16 bars)")
                    fig.tight_layout()
                    buf = io.BytesIO()
                    fig.savefig(buf, format="png", dpi=120)
                    plt.close(fig)
                    buf.seek(0)
                    b64 = base64.b64encode(buf.read()).decode("ascii")
                    return b64, None, warns

                b64, err, warns = await asyncio.to_thread(_work)
                for w in (warns or []):
                    ui.notify(w, type="warning")
                if err or not b64:
                    ui.notify(f"Preview failed: {err}", type="negative")
                    return
                preview_img.source = f"data:image/png;base64,{b64}"
                preview_img.style("max-width: 100%; display: block;")
                preview_img.update()

            with ui.row().classes("gap-3 items-center mt-2"):
                ui.button("Pick preview file", icon="folder_open", on_click=_pick_preview_file).props("flat").classes(
                    "bg-[#252525] hover:bg-[#333] text-gray-200"
                )
                ui.button("Preview beatgrid (16 bars)", icon="visibility", on_click=_render_preview).props("flat").classes(
                    "bg-[#252525] hover:bg-[#333] text-gray-200"
                )
                preview_label
            preview_img

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

        # Table data with search + pagination (client-side)
        tracks = state.meta.get("tracks", {})
        all_rows = []
        for path, info in tracks.items():
            tags = info.get("mytags") or info.get("tags") or []
            if isinstance(tags, (list, tuple)):
                tags_str = ", ".join(str(t) for t in tags)
            else:
                tags_str = str(tags)

            all_rows.append({
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

        search_box = ui.input(placeholder="Search artist / title / MyTags").props("dark dense clearable").classes("w-96")

        filtered_rows = all_rows

        def apply_filter() -> None:
            term = (search_box.value or "").strip().lower()
            nonlocal filtered_rows
            if not term:
                filtered_rows = all_rows
            else:
                filtered_rows = [
                    r for r in all_rows
                    if term in r["artist"].lower()
                    or term in r["title"].lower()
                    or term in r["mytags"].lower()
                ]
            table.update(filtered_rows)

        search_box.on_value_change(lambda e: apply_filter())

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
            table.update(filtered_rows)

        ui.label(lambda: f"Showing {len(filtered_rows)} of {len(all_rows)} tracks").classes("text-gray-500 text-sm")
