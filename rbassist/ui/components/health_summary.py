from __future__ import annotations

from pathlib import Path

from nicegui import ui


def _root_scope_label(roots: list[str]) -> str:
    names = []
    for root in roots:
        path = Path(root)
        names.append(path.name or str(path))
    if len(names) <= 3:
        return ', '.join(names)
    return ', '.join(names[:3]) + f' +{len(names) - 3} more'


def render_health_summary(health: dict) -> None:
    counts = health.get('counts', {}) if isinstance(health, dict) else {}
    suggestions = health.get('suggested_rewrite_pairs', []) if isinstance(health, dict) else []
    roots = [str(root) for root in (health.get('music_roots') or [])] if isinstance(health, dict) else []

    with ui.card().classes('w-full bg-[#1a1a1a] border border-[#333] p-4'):
        ui.label('Library Health').classes('text-lg font-semibold text-gray-200 mb-1')
        if roots:
            ui.label(f"Scope: {_root_scope_label(roots)}").classes('text-gray-400 text-sm mb-3')

        with ui.row().classes('w-full gap-3 flex-wrap'):
            for label, key, color in [
                ('Tracks', 'tracks_total', 'gray'),
                ('Emb OK', 'embedding_ok', 'indigo'),
                ('Emb Gap', 'embedding_gap_total', 'amber'),
                ('Stale In Scope', 'stale_inside_root_total', 'red'),
                ('Stale Paths', 'stale_track_path_total', 'red'),
                ('Bare Paths', 'bare_path_total', 'orange'),
                ('Review Needed', 'stale_keep_review_total', 'orange'),
                ('Missing BPM', 'missing_bpm_total', 'purple'),
                ('Missing Key', 'missing_key_total', 'blue'),
                ('Missing Cues', 'missing_cues_total', 'blue'),
            ]:
                ui.badge(f"{label}: {counts.get(key, 0)}", color=color)

        warning_bits: list[str] = []
        if counts.get('stale_track_path_total', 0):
            warning_bits.append(f"{counts.get('stale_track_path_total', 0)} stale metadata paths")
        if counts.get('stale_inside_root_total', 0):
            warning_bits.append(f"{counts.get('stale_inside_root_total', 0)} stale entries still point into the active root")
        if counts.get('bare_path_total', 0):
            warning_bits.append(f"{counts.get('bare_path_total', 0)} bare filename entries")
        if counts.get('junk_path_total', 0):
            warning_bits.append(f"{counts.get('junk_path_total', 0)} junk AppleDouble/__MACOSX entries")
        if counts.get('embedding_file_missing', 0):
            warning_bits.append(f"{counts.get('embedding_file_missing', 0)} broken embedding files")
        if warning_bits:
            ui.label('Warnings: ' + ' | '.join(warning_bits)).classes('text-amber-400 text-sm mt-3')

        if suggestions:
            text = ', '.join(f"{item.get('from')} -> {item.get('to')}" for item in suggestions)
            ui.label(f"Suggested rewrite: {text}").classes('text-indigo-300 text-sm mt-2')
