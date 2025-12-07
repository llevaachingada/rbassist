"""Dark theme configuration for rbassist UI."""

from __future__ import annotations

# Color palette - dark theme optimized for DJ use
COLORS = {
    "bg_primary": "#0f0f0f",      # Near black background
    "bg_secondary": "#1a1a1a",    # Card backgrounds
    "bg_tertiary": "#252525",     # Hover states
    "accent": "#6366f1",          # Indigo (primary action)
    "accent_hover": "#818cf8",    # Lighter indigo
    "success": "#22c55e",         # Green
    "warning": "#f59e0b",         # Amber
    "error": "#ef4444",           # Red
    "text_primary": "#f5f5f5",    # White text
    "text_secondary": "#a3a3a3",  # Gray text
    "border": "#333333",          # Subtle borders
}

# Tailwind-style class presets
CARD_CLASSES = "bg-[#1a1a1a] border border-[#333333] rounded-lg p-4"
BUTTON_PRIMARY = "bg-indigo-600 hover:bg-indigo-500 text-white font-medium"
BUTTON_SECONDARY = "bg-[#252525] hover:bg-[#333333] text-gray-200"
INPUT_CLASSES = "bg-[#1a1a1a] border-[#333333] text-white"


def apply_dark_theme() -> str:
    """Return CSS for dark theme styling."""
    return """
    :root {
        --nicegui-default-padding: 1rem;
    }
    body {
        background-color: #0f0f0f !important;
        color: #f5f5f5 !important;
    }
    .q-table {
        background-color: #1a1a1a !important;
    }
    .q-table th {
        background-color: #252525 !important;
        color: #f5f5f5 !important;
    }
    .q-table td {
        color: #e5e5e5 !important;
    }
    .q-table tbody tr:hover {
        background-color: #252525 !important;
    }
    .q-tab {
        color: #a3a3a3 !important;
    }
    .q-tab--active {
        color: #818cf8 !important;
    }
    .q-field__native, .q-field__input {
        color: #f5f5f5 !important;
    }
    .q-card {
        background-color: #1a1a1a !important;
        border: 1px solid #333333 !important;
    }
    .q-linear-progress {
        background-color: #333333 !important;
    }
    .q-linear-progress__track {
        background-color: #333333 !important;
    }
    """
