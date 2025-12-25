"""Tagging page - tag management and auto-suggestions."""

from __future__ import annotations

from nicegui import ui

from ..state import get_state
from rbassist.beatgrid import analyze_paths as analyze_beatgrid_paths, BeatgridConfig


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
                    from rbassist.tagstore import available_tags, set_available_tags
                    tags = available_tags()
                except Exception:
                    tags = []

                tag_list = ui.column().classes("w-full")

                def _render_tags(current: list[str]) -> None:
                    tag_list.clear()
                    with tag_list:
                        if current:
                            for tag in current:
                                with ui.row().classes("w-full items-center justify-between py-1"):
                                    ui.label(tag).classes("text-gray-300")
                                    ui.badge("✓", color="gray").classes("text-xs")
                        else:
                            ui.label("No tags defined").classes("text-gray-500 italic")

                _render_tags(tags)

                ui.separator().classes("my-3")

                new_tag = ui.input(placeholder="New tag...").props("dark dense").classes("flex-1")

                def _add_tag() -> None:
                    val = (new_tag.value or "").strip()
                    if not val:
                        ui.notify("Enter a tag name first", type="warning")
                        return
                    try:
                        set_available_tags([val])
                        new_tag.value = ""
                        try:
                            from rbassist.tagstore import available_tags
                            _render_tags(available_tags())
                        except Exception:
                            pass
                        ui.notify(f"Added tag '{val}'", type="positive")
                    except Exception as e:
                        ui.notify(f"Failed to add tag: {e}", type="negative")

                with ui.row().classes("gap-2"):
                    new_tag
                    ui.button(icon="add", on_click=_add_tag).props("flat dense")

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
                            if info.get("embedding") and not info.get("mytags")
                        ]
                        if not tracks:
                            ui.notify("No untagged tracks with embeddings to score.", type="warning")
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
                        async def _export_rekordbox():
                            from rbassist.export_xml import write_rekordbox_xml
                            meta = load_meta()
                            out = "rbassist_mytags.xml"
                            try:
                                await ui.run_worker(lambda: write_rekordbox_xml(meta, out_path=out, playlist_name="rbassist export"))
                                ui.notify(f"Exported -> {out}", type="positive")
                            except Exception as ex:
                                ui.notify(f"Export failed: {ex}", type="negative")

                        ui.button("Export to Rekordbox", icon="download", on_click=_export_rekordbox).props("flat").classes(
                            "bg-[#252525] hover:bg-[#333] text-gray-300"
                        )
                        async def _beatgrid_folder():
                            try:
                                from rbassist.utils import walk_audio
                                folders = state.music_folders
                                if not folders:
                                    ui.notify("Set Music Folders in Settings first.", type="warning")
                                    return
                                files = walk_audio(folders)
                                if not files:
                                    ui.notify("No audio files found under Music Folders.", type="warning")
                                    return
                                cfg = BeatgridConfig(mode="fixed", backend="auto")
                                await ui.run_worker(lambda: analyze_beatgrid_paths(files, cfg=cfg, overwrite=True))
                                ui.notify(f"Beatgrid complete for {len(files)} track(s).", type="positive")
                            except Exception as ex:
                                ui.notify(f"Beatgrid failed: {ex}", type="negative")

                        ui.button("Beatgrid music folders", icon="timeline", on_click=_beatgrid_folder).props("flat").classes(
                            "bg-[#252525] hover:bg-[#333] text-gray-300"
                        )
