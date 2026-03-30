"""Tagging page - tag management and auto-suggestions."""

from __future__ import annotations

import asyncio
from pathlib import Path

from nicegui import ui

from ..state import get_state
from rbassist.beatgrid import analyze_paths as analyze_beatgrid_paths, BeatgridConfig


def render() -> None:
    """Render the tagging page."""
    state = get_state()

    with ui.column().classes('w-full gap-4'):
        ui.label('Tag Management').classes('text-2xl font-bold text-white')

        with ui.row().classes('w-full gap-6 items-start'):
            with ui.card().classes('w-64 bg-[#1a1a1a] border border-[#333] p-4'):
                ui.label('Available Tags').classes('text-lg font-semibold text-gray-200 mb-3')

                try:
                    from rbassist.tagstore import available_tags, set_available_tags
                    tags = available_tags()
                except Exception:
                    tags = []

                tag_list = ui.column().classes('w-full')

                def _render_tags(current: list[str]) -> None:
                    tag_list.clear()
                    with tag_list:
                        if current:
                            for tag in current:
                                with ui.row().classes('w-full items-center justify-between py-1'):
                                    ui.label(tag).classes('text-gray-300')
                                    ui.badge('ready', color='gray').classes('text-xs')
                        else:
                            ui.label('No tags defined').classes('text-gray-500 italic')

                _render_tags(tags)

                ui.separator().classes('my-3')
                new_tag = ui.input(placeholder='New tag...').props('dark dense').classes('flex-1')

                def _add_tag() -> None:
                    val = (new_tag.value or '').strip()
                    if not val:
                        ui.notify('Enter a tag name first', type='warning')
                        return
                    try:
                        set_available_tags([val])
                        new_tag.value = ''
                        try:
                            from rbassist.tagstore import available_tags
                            _render_tags(available_tags())
                        except Exception:
                            pass
                        ui.notify(f"Added tag '{val}'", type='positive')
                    except Exception as exc:
                        ui.notify(f"Failed to add tag: {exc}", type='negative')

                with ui.row().classes('gap-2'):
                    new_tag
                    ui.button(icon='add', on_click=_add_tag).props('flat dense')

            with ui.column().classes('flex-1 gap-4'):
                with ui.card().classes('w-full bg-[#1a1a1a] border border-[#333] p-4'):
                    ui.label('Auto-Tag Suggestions').classes('text-lg font-semibold text-gray-200 mb-3')

                    from rbassist.tag_model import learn_tag_profiles, suggest_tags_for_tracks, evaluate_existing_tags
                    from rbassist.utils import load_meta

                    profiles_info = ui.label('Profiles not learned yet').classes('text-gray-500 text-sm')
                    summary_info = ui.label('Run a preview to see suggestions in the app before applying them.').classes('text-gray-500 text-sm')
                    preview_container = ui.column().classes('w-full gap-3 max-h-[340px] overflow-y-auto')

                    min_samples_input = ui.number(value=3, min=1, max=20).props('dark dense').classes('w-20')
                    margin_input = ui.number(value=0.0, min=0, max=0.5, step=0.01).props('dark dense').classes('w-20')
                    top_k_input = ui.number(value=3, min=1, max=10, step=1).props('dark dense').classes('w-20')

                    def _render_preview(suggestions: dict, existing: dict) -> None:
                        preview_container.clear()
                        suggestion_rows = sum(len(tags) for tags in suggestions.values())
                        existing_rows = sum(len(tags) for tags in existing.values())
                        summary_info.text = (
                            f"Preview: {len(suggestions)} tracks with new suggestions, {suggestion_rows} suggestion rows, "
                            f"and {existing_rows} existing-tag evaluations."
                        )
                        summary_info.update()

                        with preview_container:
                            if not suggestions and not existing:
                                ui.label('No suggestions met the current thresholds.').classes('text-gray-500 italic')
                                return

                            for path, tags in list(suggestions.items())[:15]:
                                with ui.card().classes('w-full bg-[#252525] p-3'):
                                    ui.label(Path(path).name).classes('text-white font-medium')
                                    ui.label(path).classes('text-gray-500 text-xs')
                                    with ui.row().classes('gap-2 flex-wrap mt-2'):
                                        for tag, score, threshold in tags:
                                            ui.badge(f"{tag} {score:.2f} (thr {threshold:.2f})").classes('bg-purple-600 text-white')

                            if existing:
                                ui.separator().classes('my-2')
                                ui.label('Existing-tag confidence checks').classes('text-gray-300 text-sm')
                                for path, tags in list(existing.items())[:10]:
                                    with ui.card().classes('w-full bg-[#202020] p-3'):
                                        ui.label(Path(path).name).classes('text-gray-200 font-medium')
                                        with ui.row().classes('gap-2 flex-wrap mt-2'):
                                            for tag, score, threshold in tags:
                                                ui.badge(f"{tag} {score:.2f} (thr {threshold:.2f})").classes('bg-slate-600 text-white')

                    def _learn_profiles() -> dict:
                        meta = load_meta()
                        profiles = learn_tag_profiles(min_samples=int(min_samples_input.value or 3), meta=meta)
                        if not profiles:
                            ui.notify('No tagged tracks available to learn from.', type='warning')
                            profiles_info.text = 'No profiles learned'
                        else:
                            ui.notify(f"Learned {len(profiles)} tag profile(s).", type='positive')
                            profiles_info.text = f"Profiles ready: {len(profiles)} tags with at least {int(min_samples_input.value or 3)} example(s)."
                        profiles_info.update()
                        return profiles

                    def _generate_suggestions(apply_changes: bool = False) -> None:
                        meta = load_meta()
                        profiles = learn_tag_profiles(min_samples=int(min_samples_input.value or 3), meta=meta)
                        if not profiles:
                            ui.notify('No profiles available. Learn profiles first.', type='warning')
                            return
                        tracks = [
                            path for path, info in meta.get('tracks', {}).items()
                            if info.get('embedding') and not info.get('mytags')
                        ]
                        if not tracks:
                            ui.notify('No untagged tracks with embeddings to score.', type='warning')
                            return
                        suggestions = suggest_tags_for_tracks(
                            tracks,
                            profiles,
                            margin=float(margin_input.value or 0.0),
                            top_k=int(top_k_input.value or 3),
                            meta=meta,
                        )
                        existing = evaluate_existing_tags(tracks, profiles, meta=meta)
                        _render_preview(suggestions, existing)
                        if not suggestions and not existing and not apply_changes:
                            ui.notify('No tag suggestions met the confidence thresholds.', type='warning')
                            return

                        out = 'data/tag_suggestions.csv'
                        rows: list[list[object]] = []
                        for path, tags in suggestions.items():
                            for tag, score, threshold in tags:
                                rows.append(['suggest', path, tag, score, threshold, score - threshold])
                        for path, tags in existing.items():
                            for tag, score, threshold in tags:
                                rows.append(['existing', path, tag, score, threshold, score - threshold])
                        try:
                            import csv
                            import os

                            os.makedirs('data', exist_ok=True)
                            with open(out, 'w', newline='', encoding='utf-8') as handle:
                                writer = csv.writer(handle)
                                writer.writerow(['type', 'path', 'tag', 'score', 'threshold', 'delta'])
                                writer.writerows(rows)
                            if not apply_changes:
                                ui.notify(f"Wrote tag suggestions -> {out}", type='positive')
                        except Exception as exc:
                            ui.notify(f"Failed to write CSV: {exc}", type='negative')
                            return

                        if apply_changes:
                            from rbassist.tagstore import bulk_set_track_tags

                            meta_live = load_meta()
                            updates: dict[str, list[str]] = {}
                            for path, tags in suggestions.items():
                                info = meta_live.get('tracks', {}).get(path, {})
                                current = set(info.get('mytags', []))
                                for tag, _score, _threshold in tags:
                                    current.add(tag)
                                if current:
                                    updates[path] = sorted(current)
                            if updates:
                                bulk_set_track_tags(updates, only_existing=False)
                                state.refresh_meta()
                                ui.notify(f"Applied suggestions to {len(updates)} track(s).", type='positive')
                            else:
                                ui.notify('No suggestions to apply.', type='warning')

                    with ui.row().classes('gap-4 mb-2'):
                        ui.button('Learn Profiles', icon='school', on_click=_learn_profiles).props('flat').classes(
                            'bg-indigo-600 hover:bg-indigo-500'
                        )
                        ui.button('Preview Suggestions', icon='auto_fix_high', on_click=lambda: _generate_suggestions(False)).props('flat').classes(
                            'bg-purple-600 hover:bg-purple-500'
                        )

                    apply_confirm = ui.checkbox('Apply suggestions to My Tags', value=False).props('dark')

                    def _apply_clicked() -> None:
                        if not apply_confirm.value:
                            ui.notify('Tick the checkbox to confirm applying tag suggestions.', type='warning')
                            return
                        _generate_suggestions(True)

                    ui.button('Apply Suggestions', icon='check', on_click=_apply_clicked).props('flat').classes(
                        'bg-green-600 hover:bg-green-500 mt-1'
                    )

                    with ui.row().classes('gap-4 items-center flex-wrap'):
                        ui.label('Min samples:').classes('text-gray-400')
                        min_samples_input
                        ui.label('Margin:').classes('text-gray-400')
                        margin_input
                        ui.label('Top K:').classes('text-gray-400')
                        top_k_input

                    ui.separator().classes('my-4')
                    ui.label('Preview writes data/tag_suggestions.csv and also renders the strongest candidates below.').classes('text-gray-500 text-sm')
                    preview_container

                with ui.card().classes('w-full bg-[#1a1a1a] border border-[#333] p-4'):
                    ui.label('Import / Export').classes('text-lg font-semibold text-gray-200 mb-3')
                    ui.label(
                        'Import reads My Tags from a Rekordbox XML export and only merges tracks already known to rbassist.'
                    ).classes('text-gray-500 text-sm mb-3')
                    xml_path_input = ui.input(
                        placeholder='Paste a Rekordbox XML export path or use Browse...'
                    ).props('dark dense clearable').classes('w-full')
                    xml_status = ui.label('Ready for import or export.').classes('text-gray-500 text-sm')

                    with ui.row().classes('gap-2 flex-wrap'):
                        async def _browse_rekordbox_xml() -> None:
                            def _pick() -> str | None:
                                try:
                                    import tkinter as tk
                                    from tkinter import filedialog

                                    root = tk.Tk()
                                    root.withdraw()
                                    root.attributes('-topmost', True)
                                    path = filedialog.askopenfilename(
                                        title='Select Rekordbox XML export',
                                        filetypes=[
                                            ('XML files', '*.xml'),
                                            ('All files', '*.*'),
                                        ],
                                    )
                                    root.destroy()
                                    return path or None
                                except Exception:
                                    return None

                            path = await asyncio.to_thread(_pick)
                            if not path:
                                ui.notify('No XML selected. You can also paste the export path.', type='info')
                                return
                            xml_path_input.value = path
                            xml_path_input.update()
                            xml_status.text = f"Selected XML: {Path(path).name}"
                            xml_status.update()
                            ui.notify(f"Selected: {Path(path).name}", type='positive')

                        async def _import_rekordbox() -> None:
                            from rbassist.tagstore import import_rekordbox_tags

                            xml_path = (xml_path_input.value or '').strip()
                            if not xml_path:
                                ui.notify('Choose or paste a Rekordbox XML path first.', type='warning')
                                return
                            candidate = Path(xml_path).expanduser()
                            if not candidate.exists():
                                ui.notify(f"XML not found: {candidate}", type='negative')
                                return
                            try:
                                count = await ui.run_worker(
                                    lambda: import_rekordbox_tags(str(candidate), only_existing=True)
                                )
                            except Exception as exc:
                                ui.notify(f"Import failed: {exc}", type='negative')
                                xml_status.text = f"Import failed for {candidate.name}"
                                xml_status.update()
                                return
                            state.refresh_meta()
                            if count:
                                xml_status.text = f"Imported My Tags for {count} track(s) from {candidate.name}."
                                ui.notify(f"Imported My Tags for {count} track(s).", type='positive')
                            else:
                                xml_status.text = f"No matching My Tags found in {candidate.name}."
                                ui.notify('No matching My Tags found in XML.', type='warning')
                            xml_status.update()

                        ui.button('Browse XML', icon='folder_open', on_click=_browse_rekordbox_xml).props('flat').classes(
                            'bg-[#252525] hover:bg-[#333] text-gray-300'
                        )
                        ui.button('Import Rekordbox XML', icon='upload', on_click=_import_rekordbox).props('flat').classes(
                            'bg-indigo-600 hover:bg-indigo-500 text-white'
                        )

                        async def _export_rekordbox() -> None:
                            from rbassist.export_xml import write_rekordbox_xml
                            meta = load_meta()
                            out = Path('rbassist_mytags.xml').resolve()
                            try:
                                await ui.run_worker(
                                    lambda: write_rekordbox_xml(meta, out_path=str(out), playlist_name='rbassist export')
                                )
                                xml_status.text = f"Exported Rekordbox XML to {out}"
                                xml_status.update()
                                ui.notify(f"Exported -> {out.name}", type='positive')
                            except Exception as exc:
                                ui.notify(f"Export failed: {exc}", type='negative')
                                xml_status.text = 'Export failed.'
                                xml_status.update()

                        ui.button('Export to Rekordbox', icon='download', on_click=_export_rekordbox).props('flat').classes(
                            'bg-[#252525] hover:bg-[#333] text-gray-300'
                        )

                        async def _beatgrid_folder() -> None:
                            try:
                                from rbassist.utils import walk_audio
                                folders = state.current_music_roots()
                                if not folders:
                                    ui.notify('Set Music Folders in Settings first.', type='warning')
                                    return
                                files = walk_audio(folders)
                                if not files:
                                    ui.notify('No audio files found under Music Folders.', type='warning')
                                    return
                                cfg = BeatgridConfig(mode='fixed', backend='auto')
                                await ui.run_worker(lambda: analyze_beatgrid_paths(files, cfg=cfg, overwrite=True))
                                ui.notify(f"Beatgrid complete for {len(files)} track(s).", type='positive')
                            except Exception as exc:
                                ui.notify(f"Beatgrid failed: {exc}", type='negative')

                        ui.button('Beatgrid music folders', icon='timeline', on_click=_beatgrid_folder).props('flat').classes(
                            'bg-[#252525] hover:bg-[#333] text-gray-300'
                        )
                    xml_status
