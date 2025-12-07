"""Tagging page - tag management and auto-suggestions."""

from __future__ import annotations

from nicegui import ui

from ..state import get_state


def render() -> None:
    """Render the tagging page."""
    state = get_state()

    with ui.column().classes("w-full gap-4"):
        ui.label("Tag Management").classes("text-2xl font-bold text-white")

        with ui.row().classes("w-full gap-6 items-start"):
            # Left: Tag library
            with ui.card().classes("w-64 bg-[#1a1a1a] border border-[#333] p-4"):
                ui.label("Available Tags").classes("text-lg font-semibold text-gray-200 mb-3")

                # Get tags from config
                try:
                    from rbassist.tagstore import available_tags
                    tags = available_tags()
                except Exception:
                    tags = []

                if tags:
                    for tag in tags:
                        with ui.row().classes("w-full items-center justify-between py-1"):
                            ui.label(tag).classes("text-gray-300")
                            ui.badge("0", color="gray").classes("text-xs")
                else:
                    ui.label("No tags defined").classes("text-gray-500 italic")

                ui.separator().classes("my-3")

                with ui.row().classes("gap-2"):
                    new_tag = ui.input(placeholder="New tag...").props("dark dense").classes("flex-1")
                    ui.button(icon="add", on_click=lambda: ui.notify("Add tag coming soon")).props("flat dense")

            # Right: Auto-tag suggestions
            with ui.column().classes("flex-1 gap-4"):
                with ui.card().classes("w-full bg-[#1a1a1a] border border-[#333] p-4"):
                    ui.label("Auto-Tag Suggestions").classes("text-lg font-semibold text-gray-200 mb-3")

                    with ui.row().classes("gap-4 mb-4"):
                        ui.button("Learn Profiles", icon="school").props("flat").classes(
                            "bg-indigo-600 hover:bg-indigo-500"
                        )
                        ui.button("Generate Suggestions", icon="auto_fix_high").props("flat").classes(
                            "bg-purple-600 hover:bg-purple-500"
                        )

                    # Settings
                    with ui.row().classes("gap-4 items-center"):
                        ui.label("Min samples:").classes("text-gray-400")
                        ui.number(value=3, min=1, max=20).props("dark dense").classes("w-20")
                        ui.label("Margin:").classes("text-gray-400")
                        ui.number(value=0.0, min=0, max=0.5, step=0.01).props("dark dense").classes("w-20")

                    ui.separator().classes("my-4")

                    ui.label("Suggestions will appear here after running.").classes("text-gray-500 italic")

                # Import/Export
                with ui.card().classes("w-full bg-[#1a1a1a] border border-[#333] p-4"):
                    ui.label("Import / Export").classes("text-lg font-semibold text-gray-200 mb-3")

                    with ui.row().classes("gap-2"):
                        ui.button("Import Rekordbox XML", icon="upload").props("flat").classes(
                            "bg-[#252525] hover:bg-[#333] text-gray-300"
                        )
                        ui.button("Export to Rekordbox", icon="download").props("flat").classes(
                            "bg-[#252525] hover:bg-[#333] text-gray-300"
                        )
