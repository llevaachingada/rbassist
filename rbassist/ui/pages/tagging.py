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

                    from rbassist.tag_model import learn_tag_profiles, suggest_tags_for_tracks, evaluate_existing_tags
                    from rbassist.utils import load_meta

                    profiles_info = ui.label("Profiles not learned yet").classes("text-gray-500 text-sm")

                    min_samples_input = ui.number(value=3, min=1, max=20).props("dark dense").classes("w-20")
                    margin_input = ui.number(value=0.0, min=0, max=0.5, step=0.01).props("dark dense").classes("w-20")

                    def _learn_profiles() -> dict:
                        meta = load_meta()
                        profiles = learn_tag_profiles(min_samples=int(min_samples_input.value or 3), meta=meta)
                        if not profiles:
                            ui.notify("No tagged tracks available to learn from.", type="warning")
                            profiles_info.text = "No profiles learned"
                        else:
                            ui.notify(f"Learned {len(profiles)} tag profile(s).", type="positive")
                            profiles_info.text = f"Profiles: {len(profiles)} tag(s)"
                        profiles_info.update()
                        return profiles

                    def _generate_suggestions(apply_changes: bool = False) -> None:
                        meta = load_meta()
                        profiles = learn_tag_profiles(min_samples=int(min_samples_input.value or 3), meta=meta)
                        if not profiles:
                            ui.notify("No profiles available. Learn profiles first.", type="warning")
                            return
                        tracks = [
                            p for p, info in meta.get("tracks", {}).items()
                            if info.get("embedding") and info.get("mytags")
                        ]
                        if not tracks:
                            ui.notify("No tracks with embeddings/My Tags to score.", type="warning")
                            return
                        suggestions = suggest_tags_for_tracks(
                            tracks,
                            profiles,
                            margin=float(margin_input.value or 0.0),
                            top_k=3,
                            meta=meta,
                        )
                        existing = evaluate_existing_tags(tracks, profiles, meta=meta)
                        if not suggestions and not existing and not apply_changes:
                            ui.notify("No tag suggestions met the confidence thresholds.", type="warning")
                            return
                        out = "data/tag_suggestions.csv"
                        rows: list[list[object]] = []
                        for path, tags in suggestions.items():
                            for tag, score, thr in tags:
                                rows.append(["suggest", path, tag, score, thr, score - thr])
                        for path, tags in existing.items():
                            for tag, score, thr in tags:
                                rows.append(["existing", path, tag, score, thr, score - thr])
                        try:
                            import csv, os
                            os.makedirs("data", exist_ok=True)
                            with open(out, "w", newline="", encoding="utf-8") as fh:
                                writer = csv.writer(fh)
                                writer.writerow(["type", "path", "tag", "score", "threshold", "delta"])
                                writer.writerows(rows)
                            if not apply_changes:
                                ui.notify(f"Wrote tag suggestions -> {out}", type="positive")
                        except Exception as e:
                            ui.notify(f"Failed to write CSV: {e}", type="negative")
                            return

                        if apply_changes:
                            # Mirror a simplified tags-auto --apply: add suggested tags to mytags.
                            from rbassist.tagstore import bulk_set_track_tags

                            meta_live = load_meta()
                            updates: dict[str, list[str]] = {}
                            for path, tags in suggestions.items():
                                info = meta_live.get("tracks", {}).get(path, {})
                                current = set(info.get("mytags", []))
                                for tag, _score, _thr in tags:
                                    current.add(tag)
                                if current:
                                    updates[path] = sorted(current)
                            if updates:
                                bulk_set_track_tags(updates, only_existing=False)
                                ui.notify(f"Applied suggestions to {len(updates)} track(s).", type="positive")
                            else:
                                ui.notify("No suggestions to apply.", type="warning")

                    with ui.row().classes("gap-4 mb-2"):
                        ui.button("Learn Profiles", icon="school", on_click=_learn_profiles).props("flat").classes(
                            "bg-indigo-600 hover:bg-indigo-500"
                        )
                        ui.button("Preview Suggestions (CSV)", icon="auto_fix_high", on_click=lambda: _generate_suggestions(False)).props("flat").classes(
                            "bg-purple-600 hover:bg-purple-500"
                        )

                    apply_confirm = ui.checkbox("Apply suggestions to My Tags", value=False).props("dark")

                    def _apply_clicked() -> None:
                        if not apply_confirm.value:
                            ui.notify("Tick the checkbox to confirm applying tag suggestions.", type="warning")
                            return
                        _generate_suggestions(True)

                    ui.button("Apply Suggestions", icon="check", on_click=_apply_clicked).props("flat").classes(
                        "bg-green-600 hover:bg-green-500 mt-1"
                    )

                    # Settings
                    with ui.row().classes("gap-4 items-center"):
                        ui.label("Min samples:").classes("text-gray-400")
                        min_samples_input
                        ui.label("Margin:").classes("text-gray-400")
                        margin_input

                    ui.separator().classes("my-4")

                    ui.label("Preview writes data/tag_suggestions.csv; Apply merges suggestions into My Tags.").classes("text-gray-500 text-sm")

                # Import/Export
                with ui.card().classes("w-full bg-[#1a1a1a] border border-[#333] p-4"):
                    ui.label("Import / Export").classes("text-lg font-semibold text-gray-200 mb-3")

                    with ui.row().classes("gap-2"):
                        def _import_rekordbox():
                            from nicegui import events
                            from rbassist.tagstore import import_rekordbox_tags

                            async def _pick_and_import(e: events.ClickEventArguments) -> None:
                                try:
                                    result = await ui.run_javascript('''
                                        return await new Promise(resolve => {
                                            const input = document.createElement('input');
                                            input.type = 'file';
                                            input.accept = '.xml';
                                            input.onchange = () => {
                                                const file = input.files[0];
                                                resolve(file ? file.path || file.name : null);
                                            };
                                            input.click();
                                        });
                                    ''')
                                except Exception:
                                    ui.notify("File selection is not supported in this browser session.", type="warning")
                                    return
                                if not result:
                                    ui.notify("No XML selected.", type="info")
                                    return
                                try:
                                    count = import_rekordbox_tags(str(result), only_existing=True)
                                except FileNotFoundError:
                                    ui.notify(f"XML not found: {result}", type="negative")
                                    return
                                except Exception as ex:
                                    ui.notify(f"Import failed: {ex}", type="negative")
                                    return
                                if count:
                                    ui.notify(f"Imported My Tags for {count} track(s).", type="positive")
                                else:
                                    ui.notify("No matching My Tags found in XML.", type="warning")

                            ui.on('click', _pick_and_import)

                        ui.button("Import Rekordbox XML", icon="upload", on_click=_import_rekordbox).props("flat").classes(
                            "bg-[#252525] hover:bg-[#333] text-gray-300"
                        )
                        ui.button("Export to Rekordbox", icon="download").props("flat").classes(
                            "bg-[#252525] hover:bg-[#333] text-gray-300"
                        )
