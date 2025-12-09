"""Tools page - duplicates, playlists, utilities."""

from __future__ import annotations

from nicegui import ui

from ..state import get_state


def render() -> None:
    """Render the tools page."""
    state = get_state()

    with ui.column().classes("w-full gap-4"):
        ui.label("Tools").classes("text-2xl font-bold text-white")

        with ui.row().classes("w-full gap-6 items-start flex-wrap"):
            # Duplicate Finder
            with ui.card().classes("w-96 bg-[#1a1a1a] border border-[#333] p-4"):
                ui.label("Duplicate Finder").classes("text-lg font-semibold text-gray-200 mb-3")
                ui.label(
                    "Find and review duplicate tracks in your library (no files are deleted or moved)."
                ).classes("text-gray-400 text-sm mb-4")

                exact_checkbox = ui.checkbox("Exact match (content hash)", value=False).props("dark")

                dup_table = ui.table(
                    columns=[
                        {"name": "keep", "label": "Keep", "field": "keep"},
                        {"name": "lose", "label": "Remove", "field": "lose"},
                        {"name": "warnings", "label": "Warnings", "field": "warnings"},
                    ],
                    rows=[],
                ).props("dense flat").classes("text-xs max-h-64 overflow-y-auto mt-3")

                def _scan_duplicates() -> None:
                    from rbassist.utils import load_meta
                    from rbassist.duplicates import find_duplicates, cdj_warnings

                    meta = load_meta()
                    pairs = find_duplicates(meta, exact=bool(exact_checkbox.value))
                    if not pairs:
                        ui.notify("No duplicates detected.", type="positive")
                        dup_table.rows = []
                        dup_table.update()
                        return
                    rows = []
                    for keep, lose in pairs:
                        warns = "; ".join(cdj_warnings(keep))
                        rows.append({"keep": keep, "lose": lose, "warnings": warns})
                    dup_table.rows = rows
                    dup_table.update()
                    ui.notify(f"Found {len(rows)} duplicate pair(s). Review before deleting in your file manager.", type="info")

                ui.button("Scan for Duplicates", icon="search", on_click=_scan_duplicates).props("flat").classes(
                    "bg-indigo-600 hover:bg-indigo-500 w-full"
                )

            # Playlist Builder
            with ui.card().classes("w-96 bg-[#1a1a1a] border border-[#333] p-4"):
                ui.label("Intelligent Playlists").classes("text-lg font-semibold text-gray-200 mb-3")
                ui.label(
                    "Create smart playlists based on tags, ratings, and dates."
                ).classes("text-gray-400 text-sm mb-4")

                with ui.column().classes("gap-3"):
                    ui.select(
                        ["All Tags", "Tech House", "Deep House", "Minimal"],
                        label="Filter by Tag",
                        value="All Tags",
                    ).props("dark dense").classes("w-full")

                    with ui.row().classes("gap-2 items-center"):
                        ui.label("Min Rating:").classes("text-gray-400")
                        ui.slider(min=0, max=5, step=1, value=0).props("dark label-always").classes("flex-1")

                ui.button("Generate Playlist", icon="playlist_add", on_click=lambda: ui.notify("Coming soon")).props(
                    "flat"
                ).classes("bg-purple-600 hover:bg-purple-500 w-full mt-4")

            # Export Tools
            with ui.card().classes("w-96 bg-[#1a1a1a] border border-[#333] p-4"):
                ui.label("Export").classes("text-lg font-semibold text-gray-200 mb-3")
                ui.label(
                    "Export your library to Rekordbox or other formats."
                ).classes("text-gray-400 text-sm mb-4")

                with ui.column().classes("gap-2"):
                    def _export_rekordbox_xml() -> None:
                        from rbassist.export_xml import write_rekordbox_xml
                        from rbassist.utils import load_meta
                        try:
                            out = "rbassist.xml"
                            meta = load_meta()
                            write_rekordbox_xml(meta, out_path=out, playlist_name="rbassist export")
                            ui.notify(f"Wrote {out}", type="positive")
                        except Exception as e:
                            ui.notify(f"Export failed: {e}", type="negative")

                    ui.button(
                        "Export Rekordbox XML",
                        icon="download",
                        on_click=_export_rekordbox_xml,
                    ).props("flat").classes(
                        "bg-[#252525] hover:bg-[#333] text-gray-300 w-full"
                    )

                    ui.button(
                        "Export Suggestions CSV",
                        icon="table_chart",
                        on_click=lambda: ui.notify("Suggestions CSV export coming soon", type="info"),
                    ).props("flat").classes(
                        "bg-[#252525] hover:bg-[#333] text-gray-300 w-full"
                    )

            # Demucs Cache (if available)
            with ui.card().classes("w-96 bg-[#1a1a1a] border border-[#333] p-4"):
                ui.label("Stem Cache").classes("text-lg font-semibold text-gray-200 mb-3")
                ui.label(
                    "Manage cached stem separations from Demucs."
                ).classes("text-gray-400 text-sm mb-4")

                try:
                    from rbassist.stems import have_demucs, list_cache
                    has_demucs = have_demucs()
                except Exception:
                    has_demucs = False

                if has_demucs:
                    ui.label("Demucs available").classes("text-green-500 mb-2")
                    ui.button("Clear Cache", icon="delete", on_click=lambda: ui.notify("Coming soon")).props(
                        "flat"
                    ).classes("bg-[#252525] hover:bg-[#333] text-gray-300 w-full")
                else:
                    ui.label("Demucs not installed").classes("text-gray-500 italic")
                    ui.label("pip install demucs").classes("text-xs text-gray-600 font-mono")
