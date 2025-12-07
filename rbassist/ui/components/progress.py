"""Progress indicator components."""

from __future__ import annotations

from nicegui import ui


class ProgressPanel:
    """Progress bar with status label."""

    def __init__(self, title: str = "Progress"):
        self.title = title
        self._visible = False

        with ui.card().classes("w-full bg-[#1a1a1a] border border-[#333]") as self.container:
            self.container.visible = False
            with ui.row().classes("w-full items-center gap-4"):
                self.label = ui.label(title).classes("text-gray-300 font-medium")
                self.count = ui.label("").classes("text-gray-400 text-sm")
            self.progress = ui.linear_progress(value=0, show_value=False).props("dark color=indigo")
            self.detail = ui.label("").classes("text-xs text-gray-500 mt-1")

    def show(self) -> None:
        """Show progress panel."""
        self.container.visible = True
        self._visible = True

    def hide(self) -> None:
        """Hide progress panel."""
        self.container.visible = False
        self._visible = False

    def update(self, done: int, total: int, current: str = "") -> None:
        """Update progress state."""
        if not self._visible:
            self.show()

        self.count.text = f"{done}/{total}"
        self.progress.value = done / total if total > 0 else 0
        self.detail.text = current

    def complete(self, message: str = "Complete") -> None:
        """Mark as complete."""
        self.progress.value = 1.0
        self.count.text = message
        self.detail.text = ""

    def reset(self) -> None:
        """Reset to initial state."""
        self.progress.value = 0
        self.count.text = ""
        self.detail.text = ""
        self.hide()


class StatusBar:
    """Bottom status bar showing library stats."""

    def __init__(self):
        with ui.row().classes(
            "fixed bottom-0 left-0 right-0 h-8 bg-[#1a1a1a] border-t border-[#333] "
            "px-4 items-center gap-6 text-sm text-gray-400 z-50"
        ):
            self.status_dot = ui.icon("circle", size="xs").classes("text-green-500")
            self.status_text = ui.label("Ready")
            ui.label("|").classes("text-gray-600")
            self.track_count = ui.label("0 tracks")
            self.embed_count = ui.label("0 embedded")
            self.device_label = ui.label("CPU")

    def update_stats(self, tracks: int, embedded: int, device: str = "CPU") -> None:
        """Update status bar statistics."""
        self.track_count.text = f"{tracks:,} tracks"
        self.embed_count.text = f"{embedded:,} embedded"
        self.device_label.text = device

    def set_status(self, text: str, busy: bool = False) -> None:
        """Update status text and indicator."""
        self.status_text.text = text
        if busy:
            self.status_dot.classes(remove="text-green-500", add="text-amber-500")
        else:
            self.status_dot.classes(remove="text-amber-500", add="text-green-500")
