"""Main NiceGUI application entry point."""

from __future__ import annotations

from nicegui import ui, app

from .theme import apply_dark_theme
from .state import get_state
from .components.progress import StatusBar


def create_header() -> None:
    """Create the app header with navigation."""
    with ui.header().classes(
        "bg-[#1a1a1a] border-b border-[#333] px-4 py-2 items-center justify-between"
    ):
        with ui.row().classes("items-center gap-2"):
            ui.label("rbassist").classes("text-xl font-bold text-indigo-400")
            ui.label("DJ Toolkit").classes("text-sm text-gray-500")

    with ui.tabs().classes("text-gray-400") as tabs:
        ui.tab("discover", label="Discover", icon="explore")
        ui.tab("crate", label="Crate Expander", icon="playlist_play")
        ui.tab("library", label="Library", icon="library_music")
        ui.tab("tagging", label="Tags", icon="label")
        ui.tab("ai_tagging", label="AI Tags", icon="psychology")
        ui.tab("cues", label="Cues", icon="timeline")
        ui.tab("tools", label="Tools", icon="build")
        ui.tab("settings", label="Settings", icon="settings")

    return tabs


def create_pages(tabs) -> None:
    """Create tab panels for each page."""
    from .pages import discover, library, tagging, tools, settings, cues, crate_expander
    try:
        from .pages import ai_tagging
        has_ai_tagging = True
    except ImportError:
        has_ai_tagging = False

    with ui.tab_panels(tabs, value="discover").classes(
        "w-full flex-1 bg-[#0f0f0f] p-4 pb-12"
    ):
        with ui.tab_panel("discover"):
            discover.render()

        with ui.tab_panel("crate"):
            crate_expander.render()

        with ui.tab_panel("library"):
            library.render()

        with ui.tab_panel("tagging"):
            tagging.render()

        if has_ai_tagging:
            with ui.tab_panel("ai_tagging"):
                ai_tagging.render()
        else:
            with ui.tab_panel("ai_tagging"):
                ui.label("AI Tag Learning").classes("text-2xl font-bold text-white mb-4")
                ui.label("Install scikit-learn to enable AI tag learning: pip install scikit-learn>=1.3.0").classes("text-gray-400")

        with ui.tab_panel("cues"):
            cues.render()

        with ui.tab_panel("tools"):
            tools.render()

        with ui.tab_panel("settings"):
            settings.render()


def setup_app() -> None:
    """Configure the NiceGUI application."""
    # Apply dark theme CSS
    ui.add_head_html(f"<style>{apply_dark_theme()}</style>")

    # Set page config
    ui.page_title("rbassist")

    # Create layout
    tabs = create_header()
    create_pages(tabs)

    # Status bar
    state = get_state()
    status = StatusBar()
    status.update_stats(
        tracks=state.get_track_count(),
        embedded=state.get_embedded_count(),
        device="GPU" if state.device == "cuda" else "CPU",
    )


@ui.page("/")
def index() -> None:
    """Main page route."""
    setup_app()


def run(port: int = 8080, reload: bool = False) -> None:
    """Run the NiceGUI application.

    Args:
        port: Port to run on (default 8080)
        reload: Enable hot reload for development
    """
    ui.run(
        port=port,
        title="rbassist",
        favicon="🎧",
        dark=True,
        reload=reload,
        show=True,
    )


def main() -> None:
    """Entry point for rbassist-ui command."""
    run()


if __name__ in {"__main__", "__mp_main__"}:
    main()
