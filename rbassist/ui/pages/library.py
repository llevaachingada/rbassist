from __future__ import annotations

import asyncio
import base64
import io
from pathlib import Path
from typing import Optional

import librosa
import numpy as np
from nicegui import ui

from rbassist.beatgrid import BeatgridConfig, analyze_file, analyze_paths as analyze_beatgrid_paths
from rbassist.utils import walk_audio

from ..jobs import complete_job, fail_job, latest_job, list_recent_jobs, resolve_active_job, start_job, update_job
from ..components.health_summary import render_health_summary
from ..components.track_table import TrackTable
from ..state import get_state
from rbassist.ui_services.library import build_library_page_model


ROWS_PER_PAGE_OPTIONS = [25, 50, 100, 250, 500]


def render() -> None:
    """Render the library page."""
    state = get_state()
    state.refresh_meta()
    state.refresh_health()
    active_roots = state.current_music_roots()
    beatgrid_job_id: dict[str, str | None] = {'value': None}

    with ui.column().classes('w-full gap-4'):
        with ui.row().classes('w-full items-center justify-between'):
            with ui.column().classes('gap-1'):
                ui.label('Library').classes('text-2xl font-bold text-white')
                ui.label(f"Scope: {', '.join(active_roots) or 'No active folders configured'}").classes('text-gray-400 text-sm')
            with ui.row().classes('gap-4'):
                ui.badge(f"{state.get_track_count()} tracks", color='gray')
                ui.badge(f"{state.get_embedded_count()} embedded", color='indigo')
                ui.badge(f"{state.get_analyzed_count()} analyzed", color='purple')
                ui.badge(f"{len(active_roots)} active roots", color='teal')

        render_health_summary(state.health)

        ui.label(f"Folders: {', '.join(active_roots) or 'No folders selected'}").classes('text-lg')

        with ui.row().classes('w-full gap-4 items-center'):
            ui.button(
                'Ingest Workflow',
                icon='info',
                on_click=lambda: ui.notify(
                    'Open Settings and use Process configured folders or Process paths file for ingest and repair.',
                    type='info',
                ),
            ).classes('bg-blue-600 text-white')
            if any(state.health.get('counts', {}).get(key, 0) for key in ('stale_track_path_total', 'bare_path_total', 'junk_path_total')):
                ui.label(
                    'Tip: use Settings -> Library Health -> Dry run path repair to clean up stale, duplicate, and orphan path variants.'
                ).classes('text-amber-400 text-sm self-center')

        with ui.card().classes('w-full bg-[#1a1a1a] border border-[#333] p-4'):
            ui.label('Beatgrid').classes('text-lg font-semibold text-gray-200 mb-2')

            with ui.column().classes('gap-2'):
                ui.label('Choose backend and thresholds').classes('text-gray-400 text-sm')
                mode_toggle = ui.toggle(['fixed', 'dynamic'], value='fixed').props('dense').classes('text-gray-200')
                backend_select = ui.select(
                    ['beatnet', 'auto', 'librosa'],
                    value='beatnet',
                ).props('dark dense').classes('w-40')
                with ui.row().classes('gap-3 items-center'):
                    ui.label('Drift %').classes('text-gray-400')
                    drift_input = ui.number(value=1.5, min=0.1, max=5.0, step=0.1).props('dark dense').classes('w-28')
                    ui.label('Bars window').classes('text-gray-400')
                    bars_input = ui.number(value=16, min=4, max=64, step=4).props('dark dense').classes('w-28')
                    ui.label('Duration cap (s)').classes('text-gray-400')
                    duration_input = ui.number(value=0, min=0, max=600, step=10).props('dark dense').classes('w-28')
                overwrite_check = ui.checkbox('Overwrite existing beatgrids', value=False).props('dark')
                ui.label(
                    'Fixed uses one BPM across the track. Dynamic starts a new segment when tempo drift crosses the threshold over the selected bar window.'
                ).classes('text-gray-500 text-sm')

            preview_state: dict[str, Optional[object]] = {'path': None, 'result': None}
            preview_img = ui.image().style('max-width: 100%; display: none;')
            preview_label = ui.label('Select a file to preview beatgrid analysis').classes('text-gray-400 text-sm')
            beat_progress = ui.linear_progress(value=0).props('rounded').style('max-width: 240px; display: none;')
            beat_status = ui.label('').classes('text-gray-400 text-sm')
            preview_file_input = ui.input(
                placeholder='Or type/paste file path here...'
            ).props('dark dense clearable').classes('w-96')

            def _preview_path() -> str:
                return str(preview_state.get('path') or (preview_file_input.value or '').strip())

            async def _pick_preview_file() -> None:
                def _pick() -> str | None:
                    try:
                        import tkinter as tk
                        from tkinter import filedialog

                        root = tk.Tk()
                        root.withdraw()
                        root.attributes('-topmost', True)
                        path = filedialog.askopenfilename(
                            title='Select audio file for beatgrid preview',
                            filetypes=[
                                ('Audio files', '*.wav *.flac *.mp3 *.m4a *.aiff *.aif'),
                                ('All files', '*.*'),
                            ],
                        )
                        root.destroy()
                        return path
                    except Exception:
                        return None

                path = await asyncio.to_thread(_pick)
                if path:
                    preview_state['path'] = path
                    preview_file_input.value = path
                    preview_file_input.update()
                    preview_label.text = f"Selected: {Path(path).name}"
                    preview_label.update()
                    ui.notify(f"Selected: {Path(path).name}", type='positive')
                else:
                    ui.notify('No file selected. You can also type or paste the file path.', type='info')

            async def _render_preview() -> None:
                path = _preview_path()
                if not path:
                    ui.notify('Please select a file first using Browse or type the path.', type='warning')
                    return

                if path != preview_state.get('path'):
                    preview_state['path'] = path
                    preview_label.text = f"Selected: {Path(path).name}"
                    preview_label.update()

                if not Path(path).exists():
                    ui.notify(f"File not found: {path}", type='negative')
                    return

                cfg = BeatgridConfig(
                    mode=str(mode_toggle.value).strip().lower(),
                    backend=str(backend_select.value or 'beatnet').strip().lower(),
                    drift_pct=float(drift_input.value or 1.5),
                    bars_window=int(bars_input.value or 16),
                    duration_s=int(duration_input.value or 0),
                )

                preview_label.text = f"Analyzing: {Path(path).name}..."
                preview_label.update()
                beat_status.text = 'Preview in progress...'
                beat_status.update()

                def _work() -> tuple[str | None, str | None, list[str], dict | None]:
                    _, result, err, warns = analyze_file(path, cfg)
                    if err or result is None or not result.get('beats'):
                        return None, err or 'no beats detected', warns, None
                    try:
                        import matplotlib.pyplot as plt
                    except ModuleNotFoundError:
                        return (
                            None,
                            'Waveform preview requires matplotlib; install matplotlib or skip preview.',
                            warns,
                            result,
                        )
                    beats = np.array(result['beats'], dtype=float)
                    downbeats = np.array(result.get('downbeats', []), dtype=float)
                    max_beats = 64
                    cutoff_idx = min(len(beats) - 1, max_beats - 1)
                    window_end = beats[cutoff_idx] + 1.0

                    y, sr = librosa.load(path, sr=None, mono=True, duration=window_end)
                    t = np.linspace(0, len(y) / sr, num=len(y))

                    fig, ax = plt.subplots(figsize=(10, 3))
                    ax.plot(t, y, color='#4ade80', linewidth=0.8, alpha=0.7)

                    for beat in beats:
                        if beat <= window_end:
                            ax.axvline(
                                beat,
                                color='#f472b6',
                                linestyle='--',
                                linewidth=0.6,
                                alpha=0.7,
                                label='Beat' if beat == beats[0] else '',
                            )

                    if downbeats.size > 0:
                        for downbeat in downbeats:
                            if downbeat <= window_end:
                                ax.axvline(
                                    downbeat,
                                    color='#fbbf24',
                                    linestyle='-',
                                    linewidth=1.2,
                                    alpha=0.9,
                                    label='Downbeat' if downbeat == downbeats[0] else '',
                                )

                    ax.set_xlim(0, window_end)
                    ax.set_xlabel('Time (seconds)', fontsize=10)
                    ax.set_ylabel('Amplitude', fontsize=10)
                    bpm_str = f"{result.get('bpm_est', 0):.1f} BPM"
                    conf_str = f"Confidence: {result.get('confidence', 0):.2f}"
                    seg_count = len(result.get('tempos', []))
                    ax.set_title(f"Beatgrid Preview - {bpm_str} - {conf_str} - {seg_count} segment(s)", fontsize=11, pad=10)
                    if downbeats.size > 0:
                        ax.legend(loc='upper right', fontsize=9)

                    fig.tight_layout()
                    buf = io.BytesIO()
                    fig.savefig(buf, format='png', dpi=120, facecolor='#1a1a1a')
                    plt.close(fig)
                    buf.seek(0)
                    return base64.b64encode(buf.read()).decode('ascii'), None, warns, result

                b64, err, warns, result = await asyncio.to_thread(_work)
                for warning in warns or []:
                    ui.notify(warning, type='warning')

                if err or not b64:
                    ui.notify(f"Preview failed: {err}", type='negative')
                    preview_label.text = f"Preview failed for {Path(path).name}"
                    preview_label.update()
                    beat_status.text = 'Preview failed.'
                    beat_status.update()
                    return

                preview_state['result'] = result
                preview_img.source = f"data:image/png;base64,{b64}"
                preview_img.style('max-width: 100%; display: block;')
                preview_img.update()

                if result:
                    bpm = result.get('bpm_est', 0)
                    conf = result.get('confidence', 0)
                    beats_count = len(result.get('beats', []))
                    downbeats_count = len(result.get('downbeats', []))
                    preview_label.text = (
                        f"OK: {Path(path).name} | {bpm:.1f} BPM | {beats_count} beats | {downbeats_count} downbeats | confidence {conf:.2f}"
                    )
                    preview_label.update()
                    if conf < 0.35:
                        beat_status.text = 'Low-confidence preview. Apply fixed fallback if this track needs a safer single-BPM grid.'
                    else:
                        beat_status.text = 'Preview looks healthy. Apply fixed fallback only if you want a simpler single-BPM grid.'
                    beat_status.update()
                    ui.notify('Preview generated successfully.', type='positive')

            async def _apply_fixed_fallback() -> None:
                path = _preview_path()
                if not path:
                    ui.notify('Select a preview file first.', type='warning')
                    return
                if not Path(path).exists():
                    ui.notify(f"File not found: {path}", type='negative')
                    return

                cfg = BeatgridConfig(
                    mode='fixed',
                    backend='auto',
                    drift_pct=float(drift_input.value or 1.5),
                    bars_window=int(bars_input.value or 16),
                    duration_s=int(duration_input.value or 0),
                )
                beat_progress.style('max-width: 240px; display: block;')
                beat_progress.value = 0.2
                beat_progress.update()
                beat_status.text = f"Applying fixed fallback to {Path(path).name}..."
                beat_status.update()

                def _work() -> None:
                    analyze_beatgrid_paths([path], cfg=cfg, overwrite=True)

                try:
                    await asyncio.to_thread(_work)
                except Exception as exc:
                    beat_progress.value = 0
                    beat_progress.update()
                    beat_status.text = 'Fixed fallback failed.'
                    beat_status.update()
                    ui.notify(f"Fixed fallback failed: {exc}", type='negative')
                    return

                state.refresh_meta()
                state.refresh_health()
                beat_progress.value = 1
                beat_progress.update()
                beat_status.text = f"Applied fixed fallback beatgrid to {Path(path).name}."
                beat_status.update()
                ui.notify('Fixed fallback applied to preview track.', type='positive')

            with ui.row().classes('gap-3 items-center mt-2 flex-wrap'):
                ui.button('Browse', icon='folder_open', on_click=_pick_preview_file).props('flat').classes(
                    'bg-indigo-600 hover:bg-indigo-500 text-white'
                )
                preview_file_input
                ui.button('Generate Preview', icon='visibility', on_click=_render_preview).props('flat').classes(
                    'bg-purple-600 hover:bg-purple-500 text-white'
                )
                ui.button('Apply Fixed Fallback', icon='restart_alt', on_click=_apply_fixed_fallback).props('flat').classes(
                    'bg-amber-600 hover:bg-amber-500 text-white'
                )
            preview_label
            preview_img
            beat_progress
            beat_status

            batch_progress = ui.linear_progress(value=0).props('rounded color=indigo').style('max-width: 240px; display: none;')
            batch_status = ui.label('No shared beatgrid job started yet.').classes('text-gray-400 text-sm')
            batch_phase = ui.label('').classes('text-gray-500 text-xs')
            batch_history = ui.label('Recent beatgrid jobs: none yet.').classes('text-gray-500 text-xs')

            def _refresh_batch_job_view() -> None:
                snapshot = resolve_active_job(beatgrid_job_id['value'], kind='library_beatgrid')
                if snapshot is not None:
                    beatgrid_job_id['value'] = snapshot.job_id
                if snapshot is None:
                    batch_progress.style('max-width: 240px; display: none;')
                    batch_progress.value = 0
                    batch_status.text = 'No active beatgrid batch.'
                    batch_phase.text = ''
                else:
                    batch_progress.style('max-width: 240px; display: block;')
                    batch_progress.value = snapshot.progress or 0.0
                    batch_status.text = snapshot.message or 'Idle'
                    batch_phase.text = f"Phase: {snapshot.phase or '-'} | Status: {snapshot.status}"

                recent = list_recent_jobs(kind='library_beatgrid', limit=3)
                if recent:
                    batch_history.text = 'Recent beatgrid jobs: ' + ' | '.join(
                        f"{job.status}:{job.phase or '-'}"
                        for job in recent
                    )
                else:
                    batch_history.text = 'Recent beatgrid jobs: none yet.'

                batch_progress.update()
                batch_status.update()
                batch_phase.update()
                batch_history.update()

            ui.timer(0.5, _refresh_batch_job_view)

            async def _beatgrid_paths(paths: list[str]) -> None:
                if not paths:
                    ui.notify('No audio files found.', type='warning')
                    return
                active_job = latest_job(kind='library_beatgrid')
                if active_job and active_job.status == 'running':
                    ui.notify('A beatgrid batch is already running. Wait for it to finish before starting another.', type='warning')
                    return
                cfg = BeatgridConfig(
                    mode=str(mode_toggle.value).strip().lower(),
                    backend=str(backend_select.value or 'auto').strip().lower(),
                    drift_pct=float(drift_input.value or 1.5),
                    bars_window=int(bars_input.value or 16),
                    duration_s=int(duration_input.value or 0),
                )
                overwrite_existing = bool(overwrite_check.value)
                state.refresh_meta()
                targets = paths
                if not overwrite_existing:
                    meta = state.meta
                    targets = [p for p in paths if not meta.get('tracks', {}).get(p, {}).get('tempos')]

                total = len(paths)
                job = start_job(
                    'library_beatgrid',
                    phase='preflight',
                    message=f'Preparing beatgrid batch ({len(targets)} target(s))...',
                    progress=0.0,
                    result={
                        'paths_total': total,
                        'targets_total': len(targets),
                        'overwrite': overwrite_existing,
                    },
                )
                beatgrid_job_id['value'] = job.job_id
                _refresh_batch_job_view()
                ui.notify(f"Beatgridding {len(targets)} track(s)...", type='info')

                def _work() -> None:
                    def _cb(done: int, count: int, path: str) -> None:
                        update_job(
                            job.job_id,
                            phase='beatgrid',
                            message=f"Beatgrid {done}/{count}: {Path(path).name}",
                            progress=done / max(count, 1),
                        )

                    if not targets:
                        update_job(
                            job.job_id,
                            phase='beatgrid',
                            message='Beatgrid skipped (no targets)',
                            progress=1.0,
                        )
                        return

                    update_job(job.job_id, phase='beatgrid', message=f'Beatgridding {len(targets)} track(s)...', progress=0.0)
                    analyze_beatgrid_paths(targets, cfg=cfg, overwrite=overwrite_existing, progress_callback=_cb)

                try:
                    await asyncio.to_thread(_work)
                except Exception as exc:
                    fail_job(
                        job.job_id,
                        phase='failed',
                        message='Beatgrid failed',
                        error=str(exc),
                        result={
                            'paths_total': total,
                            'targets_total': len(targets),
                        },
                    )
                    _refresh_batch_job_view()
                    ui.notify(f'Beatgrid failed: {exc}', type='negative')
                    return

                state.refresh_meta()
                state.refresh_health()
                complete_job(
                    job.job_id,
                    phase='completed',
                    message=f'Beatgrid complete ({len(targets)} target(s))',
                    result={
                        'paths_total': total,
                        'targets_total': len(targets),
                    },
                )
                _refresh_batch_job_view()
                ui.notify('Beatgrid complete', type='positive')

            async def _run_music_folders() -> None:
                roots = state.current_music_roots()
                if not roots:
                    ui.notify('Set Music Folders in Settings first.', type='warning')
                    return
                files = walk_audio(roots)
                await _beatgrid_paths(files)

            single_path = {'path': ''}
            file_input = ui.input(
                placeholder='Type/paste file path or use Browse button...'
            ).props('dark dense clearable').classes('w-96')

            async def _browse_file() -> None:
                def _pick() -> str | None:
                    try:
                        import tkinter as tk
                        from tkinter import filedialog

                        root = tk.Tk()
                        root.withdraw()
                        root.attributes('-topmost', True)
                        path = filedialog.askopenfilename(
                            title='Select audio file for beatgrid analysis',
                            filetypes=[
                                ('Audio files', '*.wav *.flac *.mp3 *.m4a *.aiff *.aif'),
                                ('All files', '*.*'),
                            ],
                        )
                        root.destroy()
                        return path
                    except Exception:
                        return None

                path = await asyncio.to_thread(_pick)
                if path:
                    single_path['path'] = path
                    file_input.value = path
                    file_input.update()
                    ui.notify(f"Selected: {Path(path).name}", type='positive')
                else:
                    ui.notify('No file selected. You can also type or paste the file path.', type='info')

            async def _run_single_file() -> None:
                path = (file_input.value or '').strip()
                if not path:
                    ui.notify('Please select a file using Browse or type the path.', type='warning')
                    return
                if not Path(path).exists():
                    ui.notify(f"File not found: {path}", type='negative')
                    return
                single_path['path'] = path
                await _beatgrid_paths([path])

            with ui.row().classes('gap-3 items-center flex-wrap'):
                ui.button('Beatgrid music folders', icon='timeline', on_click=_run_music_folders).props('flat').classes(
                    'bg-indigo-600 hover:bg-indigo-500 text-white'
                )
                ui.button('Beatgrid single file', icon='audiotrack', on_click=_run_single_file).props('flat').classes(
                    'bg-purple-600 hover:bg-purple-500 text-white'
                )
                ui.button('Browse', icon='folder', on_click=_browse_file).props('flat').classes(
                    'bg-[#252525] hover:bg-[#333] text-gray-200'
                )
                file_input
                ui.label('Mode').classes('text-gray-400')
                mode_toggle
                ui.label('Drift %').classes('text-gray-400')
                drift_input
                ui.label('Bars').classes('text-gray-400')
                bars_input
                ui.label('Duration cap (s)').classes('text-gray-400')
                duration_input
                overwrite_check

            async def _export_rekordbox() -> None:
                try:
                    from rbassist.export_xml import write_rekordbox_xml
                    from rbassist.utils import load_meta

                    meta = load_meta()
                    out = 'rbassist_beatgrid.xml'
                    await asyncio.to_thread(write_rekordbox_xml, meta, out, playlist_name='rbassist export')
                    ui.notify(f"Exported -> {out}", type='positive')
                except Exception as exc:
                    ui.notify(f"Export failed: {exc}", type='negative')

            ui.button('Export Rekordbox XML', icon='download', on_click=_export_rekordbox).props('flat').classes(
                'bg-teal-600 hover:bg-teal-500 text-white mt-2'
            )

        page_model = build_library_page_model(state.meta)
        all_rows = page_model.rows
        issue_counts = page_model.issue_counts

        with ui.row().classes('w-full items-center gap-3 flex-wrap'):
            search_box = ui.input(placeholder='Search artist / title / MyTags / issues').props('dark dense clearable').classes('w-96')
            filter_select = ui.select(
                {
                    'all': 'All tracks',
                    'missing_embedding': 'Missing embedding',
                    'missing_analysis': 'Missing analysis',
                    'missing_cues': 'Missing cues',
                    'stale_path': 'Stale path',
                    'bare_path': 'Bare path',
                    'junk_path': 'Junk path',
                },
                value='all',
                label='Health filter',
            ).props('dark dense').classes('w-56')
            rows_per_page = ui.select(ROWS_PER_PAGE_OPTIONS, value=50, label='Rows per page').props('dark dense').classes('w-40')
            ui.label('Filter the table by current metadata issues without changing your library data.').classes('text-gray-500 text-sm')

        filtered_rows = list(all_rows)

        def _matches_health_filter(row: dict) -> bool:
            mode = filter_select.value or 'all'
            if mode == 'all':
                return True
            return bool(row.get('_health', {}).get(mode))

        def apply_filter() -> None:
            term = (search_box.value or '').strip().lower()
            nonlocal filtered_rows
            filtered_rows = []
            for row in all_rows:
                if not _matches_health_filter(row):
                    continue
                if term and not (
                    term in row['artist'].lower()
                    or term in row['title'].lower()
                    or term in row['mytags'].lower()
                    or term in row['issues'].lower()
                ):
                    continue
                filtered_rows.append(row)
            table.update(filtered_rows)
            count_label.text = (
                f"Showing {len(filtered_rows)} of {len(all_rows)} tracks | "
                f"rows/page {rows_per_page.value or 50} | "
                f"issue rows {sum(1 for row in filtered_rows if row['issues'] != '-')}"
            )
            count_label.update()

        def _set_filter(mode: str) -> None:
            filter_select.value = mode
            filter_select.update()
            apply_filter()

        with ui.row().classes('w-full gap-2 flex-wrap'):
            quick_filters = [
                ('All', 'all', 'bg-[#252525] hover:bg-[#333] text-gray-200', len(all_rows)),
                ('Emb Gap', 'missing_embedding', 'bg-amber-700 hover:bg-amber-600 text-white', issue_counts['missing_embedding']),
                ('Analysis Gap', 'missing_analysis', 'bg-purple-700 hover:bg-purple-600 text-white', issue_counts['missing_analysis']),
                ('Cues Gap', 'missing_cues', 'bg-blue-700 hover:bg-blue-600 text-white', issue_counts['missing_cues']),
                ('Stale', 'stale_path', 'bg-red-700 hover:bg-red-600 text-white', issue_counts['stale_path']),
                ('Bare', 'bare_path', 'bg-orange-700 hover:bg-orange-600 text-white', issue_counts['bare_path']),
            ]
            for label, mode, button_classes, count in quick_filters:
                ui.button(
                    f"{label} ({count})",
                    on_click=lambda _=None, selected_mode=mode: _set_filter(selected_mode),
                ).props('outline dense').classes(button_classes)

        with ui.card().classes('w-full bg-[#1a1a1a] border border-[#333] p-0'):
            table = TrackTable(
                extra_columns=[
                    {'name': 'embedded', 'label': 'Embedded', 'field': 'embedded', 'sortable': True, 'align': 'center'},
                    {'name': 'analyzed', 'label': 'Analyzed', 'field': 'analyzed', 'sortable': True, 'align': 'center'},
                    {'name': 'beatgrid', 'label': 'Beatgrid', 'field': 'beatgrid', 'sortable': True, 'align': 'center'},
                    {'name': 'mytags', 'label': 'MyTags', 'field': 'mytags', 'sortable': False, 'align': 'left'},
                    {'name': 'issues', 'label': 'Issues', 'field': 'issues', 'sortable': False, 'align': 'left'},
                ],
                rows_per_page=50,
                rows_per_page_options=ROWS_PER_PAGE_OPTIONS,
            )
            table.build()
            table.set_sort('artist', descending=False)
            table.update(filtered_rows)

        count_label = ui.label('').classes('text-gray-500 text-sm')

        search_box.on_value_change(lambda e: apply_filter())
        filter_select.on_value_change(lambda e: apply_filter())
        rows_per_page.on_value_change(lambda e: (table.set_rows_per_page(int(rows_per_page.value or 50)), apply_filter()))

        apply_filter()
