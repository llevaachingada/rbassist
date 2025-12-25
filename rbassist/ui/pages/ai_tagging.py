"""AI-powered tagging page with safe suggestion review."""

from __future__ import annotations

import pathlib
from typing import Dict, List, Optional

from nicegui import ui

from rbassist import safe_tagstore, active_learning, user_model
from rbassist.tag_model import TagProfile, learn_tag_profiles, suggest_tags_for_tracks
from rbassist.utils import load_meta, console
from ..state import get_state


def render() -> None:
    """Render the AI tagging page with safe suggestion workflow."""
    state = get_state()

    with ui.column().classes("w-full gap-4 p-4"):
        ui.label("AI Tag Learning").classes("text-3xl font-bold text-white mb-2")
        ui.label(
            "AI learns from YOUR tagging style and suggests tags. You stay in control."
        ).classes("text-gray-400 mb-4")

        # Instructions/About panel
        _render_instructions_panel()

        # Stats row
        with ui.row().classes("w-full gap-4 mb-4"):
            _render_stats_cards()

        # Main content
        with ui.row().classes("w-full gap-6 items-start"):
            # Left: Learning controls
            with ui.column().classes("flex-1 gap-4"):
                _render_learning_panel()
                _render_active_learning_panel()

            # Right: Suggestion review
            with ui.column().classes("flex-1 gap-4"):
                _render_suggestion_review()

        # Bottom: Migration and utilities
        with ui.expansion("Advanced Tools", icon="settings").classes(
            "w-full bg-[#1a1a1a] border border-[#333]"
        ).props("dark"):
            _render_advanced_tools()


def _render_instructions_panel() -> None:
    """Render the instructions and about panel with scrollable content"""
    with ui.expansion("ℹ️ How It Works", icon="info").classes(
        "w-full bg-[#1a1a1a] border border-[#333]"
    ).props("dark"):
        with ui.column().classes("w-full gap-3 p-4"):
            # Create scrollable area for instructions
            with ui.scroll_area().classes("w-full h-64 bg-[#0f0f0f] rounded border border-[#444]"):
                with ui.column().classes("w-full gap-3 p-4"):
                    # Step-by-step guide
                    ui.label("🚀 Quick Start").classes("text-lg font-bold text-blue-400 mb-2")

                    with ui.column().classes("gap-2 text-sm text-gray-300"):
                        ui.label("1️⃣ Tag Tracks").classes("font-semibold text-gray-200")
                        ui.label("   Go to the 'Tags' tab and manually tag 5-10 tracks per tag.").classes("text-xs text-gray-400 ml-2")

                        ui.label("2️⃣ Train AI").classes("font-semibold text-gray-200 mt-2")
                        ui.label("   Click 'Learn & Generate Suggestions' to learn your tagging style.").classes("text-xs text-gray-400 ml-2")

                        ui.label("3️⃣ Review").classes("font-semibold text-gray-200 mt-2")
                        ui.label("   Check suggestions below and click ✓ to accept or ✗ to reject.").classes("text-xs text-gray-400 ml-2")

                        ui.label("4️⃣ Improve").classes("font-semibold text-gray-200 mt-2")
                        ui.label("   AI learns from your decisions and gets better over time!").classes("text-xs text-gray-400 ml-2")

                    ui.separator().classes("my-3")

                    # What each panel does
                    ui.label("📊 What's What").classes("text-lg font-bold text-green-400 mb-2")

                    with ui.column().classes("gap-2 text-sm text-gray-300"):
                        ui.label("Stats Dashboard").classes("font-semibold text-gray-200")
                        ui.label("   Shows tagged tracks, pending suggestions, and acceptance rate.").classes("text-xs text-gray-400 ml-2")

                        ui.label("Train AI Panel").classes("font-semibold text-gray-200 mt-2")
                        ui.label("   Learn profiles from your tags and generate AI suggestions.").classes("text-xs text-gray-400 ml-2")

                        ui.label("Smart Suggestions").classes("font-semibold text-gray-200 mt-2")
                        ui.label("   AI finds uncertain tracks where your input teaches it the most.").classes("text-xs text-gray-400 ml-2")

                        ui.label("Review Panel").classes("font-semibold text-gray-200 mt-2")
                        ui.label("   Accept (✓) good suggestions or reject (✗) bad ones.").classes("text-xs text-gray-400 ml-2")

                    ui.separator().classes("my-3")

                    # Key tips
                    ui.label("💡 Pro Tips").classes("text-lg font-bold text-yellow-400 mb-2")

                    with ui.column().classes("gap-2 text-sm text-gray-300"):
                        ui.label("• Use 'Smart Suggestions' to find uncertain tracks - tag those!").classes("text-xs text-gray-400")
                        ui.label("• Be consistent with tag names (use 'Techno' not 'Tech')").classes("text-xs text-gray-400")
                        ui.label("• Reject bad suggestions - AI learns from mistakes!").classes("text-xs text-gray-400")
                        ui.label("• Start with 3-5 tags you use most, expand gradually").classes("text-xs text-gray-400")
                        ui.label("• Check stats to monitor AI accuracy").classes("text-xs text-gray-400")

                    ui.separator().classes("my-3")

                    # Safety guarantee
                    ui.label("🔒 Your Tags Are Safe").classes("text-lg font-bold text-green-500 mb-2")

                    with ui.column().classes("gap-2 text-sm text-gray-300"):
                        ui.label("✓ User tags in protected 'USER' namespace").classes("text-xs text-green-400")
                        ui.label("✓ AI suggestions in separate 'AI' namespace").classes("text-xs text-green-400")
                        ui.label("✓ Nothing changes without your explicit approval").classes("text-xs text-green-400")
                        ui.label("✓ Full history of all decisions kept for learning").classes("text-xs text-green-400")

                    ui.separator().classes("my-3")

                    # FAQ
                    ui.label("❓ FAQ").classes("text-lg font-bold text-orange-400 mb-2")

                    with ui.column().classes("gap-2 text-sm text-gray-300"):
                        ui.label("Q: How many examples do I need per tag?").classes("font-semibold text-gray-200")
                        ui.label("A: Minimum 3-5 tracks. More examples = better accuracy.").classes("text-xs text-gray-400 ml-2")

                        ui.label("Q: Can AI modify my tags?").classes("font-semibold text-gray-200 mt-2")
                        ui.label("A: No! You must explicitly accept each suggestion.").classes("text-xs text-gray-400 ml-2")

                        ui.label("Q: What if AI suggests wrong tags?").classes("font-semibold text-gray-200 mt-2")
                        ui.label("A: Click ✗ to reject. AI learns from your feedback!").classes("text-xs text-gray-400 ml-2")

            ui.separator().classes("mt-3")
            ui.label("Scroll above to see full instructions and tips →").classes("text-xs text-gray-500 italic")


def _render_stats_cards() -> None:
    """Render statistics cards"""

    def _get_stats():
        user_tags = safe_tagstore.load_user_tags()
        correction_stats = safe_tagstore.get_correction_stats()
        suggestion_stats = safe_tagstore.get_suggestion_stats()

        return {
            "user_tracks": len(user_tags),
            "total_suggestions": suggestion_stats["total_suggestions"],
            "accepted": correction_stats["accepted"],
            "rejected": correction_stats["rejected"],
        }

    stats = _get_stats()

    cards_data = [
        ("library", "User Tagged Tracks", stats["user_tracks"], "blue"),
        ("psychology", "Pending Suggestions", stats["total_suggestions"], "purple"),
        ("thumb_up", "Accepted", stats["accepted"], "green"),
        ("thumb_down", "Rejected", stats["rejected"], "orange"),
    ]

    for icon, label, value, color in cards_data:
        with ui.card().classes(
            f"bg-[#1a1a1a] border border-[#333] p-4 flex-1"
        ):
            ui.icon(icon).classes(f"text-{color}-500 text-3xl mb-2")
            ui.label(str(value)).classes("text-2xl font-bold text-white")
            ui.label(label).classes("text-sm text-gray-400")


def _render_learning_panel() -> None:
    """Render the AI learning control panel"""
    with ui.card().classes("w-full bg-[#1a1a1a] border border-[#333] p-4"):
        ui.label("Train AI on Your Tags").classes(
            "text-xl font-semibold text-gray-200 mb-3"
        )

        min_samples = ui.number(
            label="Min samples per tag", value=3, min=1, max=20
        ).props("dark dense").classes("w-32 mb-2")

        margin = ui.number(
            label="Confidence margin", value=0.0, min=0, max=0.5, step=0.01
        ).props("dark dense").classes("w-32 mb-4")

        profiles_info = ui.label("No profiles learned yet").classes(
            "text-gray-500 text-sm mb-4"
        )

        def _learn_and_generate():
            """Learn profiles and generate suggestions"""
            try:
                meta = load_meta()

                # Learn profiles
                profiles = learn_tag_profiles(
                    min_samples=int(min_samples.value or 3), meta=meta
                )

                if not profiles:
                    ui.notify(
                        "No tagged tracks to learn from. Tag some tracks first!",
                        type="warning",
                    )
                    return

                profiles_info.text = (
                    f"Learned {len(profiles)} tag profiles from user tags"
                )
                profiles_info.update()

                # Find untagged tracks
                user_tags = safe_tagstore.load_user_tags()
                untagged_tracks = [
                    p
                    for p, info in meta.get("tracks", {}).items()
                    if info.get("embedding") and p not in user_tags
                ]

                if not untagged_tracks:
                    ui.notify("No untagged tracks with embeddings found", type="warning")
                    return

                # Generate suggestions
                suggestions = suggest_tags_for_tracks(
                    untagged_tracks,
                    profiles,
                    margin=float(margin.value or 0.0),
                    top_k=3,
                    meta=meta,
                )

                if not suggestions:
                    ui.notify(
                        "No suggestions met confidence thresholds", type="warning"
                    )
                    return

                # Load user model to adjust suggestions
                user_style = user_model.UserTaggingStyle.load()

                # Store in AI suggestions namespace
                suggestion_count = 0
                for track, tag_list in suggestions.items():
                    track_suggestions = {tag: score for tag, score, _ in tag_list}

                    # Adjust based on user preferences
                    adjusted = user_style.adjust_ai_suggestions(track_suggestions)

                    # Only suggest tags user actually uses
                    filtered = {
                        tag: conf
                        for tag, conf in adjusted.items()
                        if user_style.should_suggest_tag(tag, min_usage=2)
                    }

                    if filtered:
                        for tag, conf in filtered.items():
                            safe_tagstore.add_ai_suggestion(track, tag, conf)
                        suggestion_count += 1

                ui.notify(
                    f"Generated {suggestion_count} AI suggestions! Review them below.",
                    type="positive",
                )

                # Trigger suggestion panel refresh
                ui.run_javascript("location.reload()")
            except Exception as e:
                ui.notify(f"Error during learning: {str(e)}", type="negative")
                console.print(f"[red]Learning error: {e}")

        ui.button(
            "Learn & Generate Suggestions",
            icon="auto_awesome",
            on_click=_learn_and_generate,
        ).props("flat").classes("bg-indigo-600 hover:bg-indigo-500 w-full")

        ui.separator().classes("my-3")

        ui.label(
            "AI will learn YOUR tagging style and suggest tags for untagged tracks."
        ).classes("text-gray-500 text-sm")


def _render_active_learning_panel() -> None:
    """Render the active learning panel"""
    with ui.card().classes("w-full bg-[#1a1a1a] border border-[#333] p-4"):
        ui.label("Smart Suggestions: What to Tag Next?").classes(
            "text-xl font-semibold text-gray-200 mb-3"
        )

        strategy_select = (
            ui.select(
                ["margin", "entropy", "least_confidence"],
                value="margin",
                label="Uncertainty strategy",
            )
            .props("dark dense")
            .classes("w-48 mb-2")
        )

        top_k = ui.number(label="Number of suggestions", value=5, min=1, max=20).props(
            "dark dense"
        ).classes("w-32 mb-4")

        results_container = ui.column().classes("w-full gap-2")

        def _suggest_uncertain():
            """Find tracks where AI is most uncertain"""
            try:
                results_container.clear()

                meta = load_meta()
                profiles = learn_tag_profiles(min_samples=3, meta=meta)

                if not profiles:
                    with results_container:
                        ui.label("Learn profiles first").classes("text-gray-500")
                    return

                # Get untagged tracks with embeddings
                user_tags = safe_tagstore.load_user_tags()
                untagged_embeddings = {}

                for path, info in meta.get("tracks", {}).items():
                    if path not in user_tags and info.get("embedding"):
                        import numpy as np

                        try:
                            emb = np.load(info["embedding"])
                            if emb.ndim != 1:
                                emb = emb.reshape(-1)
                            untagged_embeddings[path] = emb
                        except Exception:
                            continue

                if not untagged_embeddings:
                    with results_container:
                        ui.label("No untagged tracks with embeddings").classes(
                            "text-gray-500"
                        )
                    return

                # Get uncertain tracks
                uncertain = active_learning.suggest_tracks_to_tag(
                    untagged_embeddings,
                    profiles,
                    strategy=str(strategy_select.value),
                    top_k=int(top_k.value or 5),
                )

                if not uncertain:
                    with results_container:
                        ui.label("No uncertain tracks found").classes("text-gray-500")
                    return

                with results_container:
                    ui.label(
                        f"These {len(uncertain)} tracks would teach the AI the most:"
                    ).classes("text-gray-300 font-semibold mb-2")

                    for track_info in uncertain:
                        track_name = pathlib.Path(track_info.path).name
                        explanation = active_learning.explain_uncertainty(track_info)

                        with ui.card().classes("w-full bg-[#252525] p-3 border-l-4 border-purple-500"):
                            ui.label(track_name).classes("text-white font-medium mb-1")
                            ui.label(explanation).classes("text-gray-400 text-sm mb-2")

                            # Show top predicted tags
                            with ui.row().classes("gap-2"):
                                for tag, score in track_info.top_tags[:3]:
                                    ui.badge(f"{tag} ({score:.0%})").classes(
                                        "bg-purple-600 text-white"
                                    )
            except Exception as e:
                with results_container:
                    ui.label(f"Error finding uncertain tracks: {str(e)}").classes("text-red-500 text-sm")
                console.print(f"[red]Active learning error: {e}")

        ui.button(
            "Find Uncertain Tracks", icon="help_outline", on_click=_suggest_uncertain
        ).props("flat").classes("bg-purple-600 hover:bg-purple-500 w-full mb-3")

        results_container

        ui.label(
            "Active learning finds tracks where your input would improve the AI most."
        ).classes("text-gray-500 text-sm")


def _render_suggestion_review() -> None:
    """Render the AI suggestion review panel"""
    with ui.card().classes("w-full bg-[#1a1a1a] border border-[#333] p-4"):
        ui.label("Review AI Suggestions").classes(
            "text-xl font-semibold text-gray-200 mb-3"
        )

        min_confidence = ui.slider(min=0, max=1, step=0.05, value=0.5).props(
            "dark label-always"
        ).classes("w-full mb-2")
        ui.label(f"Min confidence: {min_confidence.value:.0%}").classes(
            "text-gray-400 text-sm mb-4"
        )

        suggestions_container = ui.column().classes("w-full gap-3 max-h-[600px] overflow-y-auto")

        def _load_suggestions():
            """Load and display AI suggestions"""
            suggestions_container.clear()

            all_suggestions = safe_tagstore.get_all_ai_suggestions(
                min_confidence=float(min_confidence.value)
            )

            if not all_suggestions:
                with suggestions_container:
                    ui.label("No AI suggestions yet. Generate some first!").classes(
                        "text-gray-500 italic"
                    )
                return

            with suggestions_container:
                for track, tag_scores in list(all_suggestions.items())[:20]:  # Limit to 20
                    track_name = pathlib.Path(track).name

                    with ui.card().classes("w-full bg-[#252525] p-3"):
                        ui.label(track_name).classes("text-white font-medium mb-2")

                        for tag, confidence in sorted(
                            tag_scores.items(), key=lambda x: x[1], reverse=True
                        ):
                            with ui.row().classes("w-full items-center justify-between mb-1"):
                                with ui.row().classes("items-center gap-2"):
                                    ui.badge(tag).classes("bg-blue-600 text-white")
                                    ui.label(f"{confidence:.0%}").classes(
                                        "text-gray-400 text-sm"
                                    )

                                with ui.row().classes("gap-1"):

                                    def make_accept_handler(t=track, tg=tag):
                                        def handler():
                                            try:
                                                safe_tagstore.accept_ai_suggestion(
                                                    t, tg
                                                )

                                                # Update user model
                                                user_style = (
                                                    user_model.UserTaggingStyle.load()
                                                )
                                                user_style.update_from_user_tags(
                                                    t, [tg]
                                                )
                                                user_style.save()

                                                ui.notify(
                                                    f"Added '{tg}' to {pathlib.Path(t).name}",
                                                    type="positive",
                                                )
                                                _load_suggestions()
                                            except Exception as e:
                                                ui.notify(str(e), type="negative")

                                        return handler

                                    def make_reject_handler(t=track, tg=tag):
                                        def handler():
                                            try:
                                                safe_tagstore.reject_ai_suggestion(
                                                    t, tg, reason="User rejected"
                                                )
                                                ui.notify(
                                                    f"Rejected '{tg}'", type="warning"
                                                )
                                                _load_suggestions()
                                            except Exception as e:
                                                ui.notify(str(e), type="negative")

                                        return handler

                                    ui.button(
                                        icon="check", on_click=make_accept_handler()
                                    ).props("flat dense round").classes(
                                        "bg-green-600 hover:bg-green-500 text-xs"
                                    )

                                    ui.button(
                                        icon="close", on_click=make_reject_handler()
                                    ).props("flat dense round").classes(
                                        "bg-red-600 hover:bg-red-500 text-xs"
                                    )

        # Auto-load suggestions on page load
        _load_suggestions()

        # Update button
        ui.button(
            "Refresh Suggestions", icon="refresh", on_click=_load_suggestions
        ).props("flat").classes("bg-gray-700 hover:bg-gray-600 w-full mt-2")

        ui.separator().classes("my-3")

        def _clear_all():
            count = safe_tagstore.clear_all_ai_suggestions()
            ui.notify(f"Cleared {count} suggestions", type="info")
            _load_suggestions()

        ui.button("Clear All Suggestions", icon="delete_sweep", on_click=_clear_all).props(
            "flat"
        ).classes("bg-red-800 hover:bg-red-700 w-full")


def _render_advanced_tools() -> None:
    """Render advanced tools section"""
    with ui.column().classes("w-full gap-4 p-4"):
        # Migration
        with ui.card().classes("w-full bg-[#252525] border border-[#444] p-4"):
            ui.label("Migrate from Old Tag System").classes(
                "text-lg font-semibold text-gray-200 mb-2"
            )
            ui.label(
                "If you used the old tagging system, migrate your tags to the new safe namespace system."
            ).classes("text-gray-400 text-sm mb-3")

            def _migrate():
                result = safe_tagstore.migrate_from_old_tagstore()
                ui.notify(
                    f"Migrated {result['tracks_migrated']} tracks with {result['tags_migrated']} tags",
                    type="positive",
                )

            ui.button("Run Migration", icon="sync_alt", on_click=_migrate).props(
                "flat"
            ).classes("bg-yellow-700 hover:bg-yellow-600")

        # Sync user model
        with ui.card().classes("w-full bg-[#252525] border border-[#444] p-4"):
            ui.label("Sync User Learning Model").classes(
                "text-lg font-semibold text-gray-200 mb-2"
            )
            ui.label(
                "Update the AI's understanding of your tagging style from your current tags."
            ).classes("text-gray-400 text-sm mb-3")

            def _sync_model():
                user_tags = safe_tagstore.load_user_tags()
                user_style = user_model.sync_user_model_from_tags(user_tags)

                correction_log = safe_tagstore.load_correction_history()
                user_style = user_model.sync_user_model_from_corrections(
                    correction_log
                )

                stats = user_style.get_correction_accuracy()
                ui.notify(
                    f"Synced! Acceptance rate: {stats['acceptance_rate']:.0%}",
                    type="positive",
                )

            ui.button("Sync User Model", icon="person", on_click=_sync_model).props(
                "flat"
            ).classes("bg-indigo-700 hover:bg-indigo-600")

        # Validation
        with ui.card().classes("w-full bg-[#252525] border border-[#444] p-4"):
            ui.label("Validate Tag Safety").classes(
                "text-lg font-semibold text-gray-200 mb-2"
            )
            ui.label("Check for any conflicts between user tags and AI suggestions.").classes(
                "text-gray-400 text-sm mb-3"
            )

            validation_result = ui.label("").classes("text-gray-300 text-sm mb-2")

            def _validate():
                issues = safe_tagstore.validate_tag_safety()
                if not issues:
                    validation_result.text = "✓ All checks passed!"
                    validation_result.classes("text-green-500", remove="text-red-500")
                else:
                    validation_result.text = f"⚠ Found {len(issues)} issues:\n" + "\n".join(
                        issues[:5]
                    )
                    validation_result.classes("text-red-500", remove="text-green-500")
                validation_result.update()

            ui.button("Run Validation", icon="verified", on_click=_validate).props(
                "flat"
            ).classes("bg-green-700 hover:bg-green-600")

            validation_result
