"""Main NiceGUI application entry point."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
import logging
from types import ModuleType

from nicegui import app, ui

from .components.progress import StatusBar
from .state import get_state
from .theme import apply_dark_theme


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PageSpec:
    key: str
    label: str
    icon: str
    module_name: str
    help_text: str = ""


PAGE_SPECS = [
    PageSpec("discover", "Discover", "explore", "discover"),
    PageSpec("crate", "Crate Expander", "playlist_play", "crate_expander"),
    PageSpec("library", "Library", "library_music", "library"),
    PageSpec("tagging", "Tags", "label", "tagging"),
    PageSpec(
        "ai_tagging",
        "AI Tags",
        "psychology",
        "ai_tagging",
        "Install scikit-learn to enable AI tag learning if this page is unavailable.",
    ),
    PageSpec("cues", "Cues", "timeline", "cues"),
    PageSpec("tools", "Tools", "build", "tools"),
    PageSpec("settings", "Settings", "settings", "settings"),
]


def _load_page_module(module_name: str) -> tuple[ModuleType | None, str | None]:
    """Import a UI page module without allowing one failure to kill the whole app."""
    try:
        return import_module(f"{__package__}.pages.{module_name}"), None
    except Exception as exc:  # pragma: no cover - exercised via tests with mocks
        logger.exception("Failed to import UI page '%s'", module_name)
        return None, f"{type(exc).__name__}: {exc}"


def _render_page_fallback(spec: PageSpec, error: str) -> None:
    """Render a friendly fallback card when a page cannot be loaded."""
    with ui.card().classes("bg-[#1a1a1a] border border-[#333] p-4 w-full"):
        ui.label(f"{spec.label} unavailable").classes("text-lg font-semibold text-amber-300")
        ui.label(
            "The rest of the UI is still available. This page failed to load and was isolated by the app shell."
        ).classes("text-gray-300 text-sm")
        if spec.help_text:
            ui.label(spec.help_text).classes("text-indigo-300 text-sm mt-2")
        ui.label(error).classes("text-gray-500 text-xs mt-3 font-mono")


def _render_page(spec: PageSpec) -> None:
    """Render one page, degrading to a fallback card on import or render failure."""
    module, error = _load_page_module(spec.module_name)
    if module is None or error:
        _render_page_fallback(spec, error or "Unknown page load error.")
        return

    try:
        module.render()
    except Exception as exc:  # pragma: no cover - hard to exercise without full UI runtime
        logger.exception("Failed to render UI page '%s'", spec.module_name)
        _render_page_fallback(spec, f"{type(exc).__name__}: {exc}")


def create_header() -> ui.tabs:
    """Create the app header with navigation."""
    with ui.header().classes(
        "bg-[#1a1a1a] border-b border-[#333] px-4 py-2 items-center justify-between"
    ):
        with ui.row().classes("items-center gap-2"):
            ui.label("rbassist").classes("text-xl font-bold text-indigo-400")
            ui.label("DJ Toolkit").classes("text-sm text-gray-500")

    with ui.tabs().classes("text-gray-400") as tabs:
        for spec in PAGE_SPECS:
            ui.tab(spec.key, label=spec.label, icon=spec.icon)

    return tabs


def create_pages(tabs: ui.tabs) -> None:
    """Create tab panels for each page."""
    with ui.tab_panels(tabs, value="discover").classes(
        "w-full flex-1 bg-[#0f0f0f] p-4 pb-12"
    ):
        for spec in PAGE_SPECS:
            with ui.tab_panel(spec.key):
                _render_page(spec)


def setup_app() -> None:
    """Configure the NiceGUI application."""
    ui.add_head_html(f"<style>{apply_dark_theme()}</style>")
    ui.page_title("rbassist")

    tabs = create_header()
    create_pages(tabs)

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


def run(port: int = 8080, reload: bool = False, show: bool = True) -> None:
    """Run the NiceGUI application.

    Args:
        port: Port to run on (default 8080)
        reload: Enable hot reload for development
        show: Open the browser automatically
    """
    ui.run(
        port=port,
        title="rbassist",
        dark=True,
        reload=reload,
        show=show,
    )


def main() -> None:
    """Entry point for rbassist-ui command."""
    run()


if __name__ in {"__main__", "__mp_main__"}:
    main()
