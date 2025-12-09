"""Centralized state management for rbassist UI."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rbassist.utils import load_meta, DATA, IDX, ROOT, pick_device

# UI config file
UI_CONFIG = ROOT / "config" / "ui_settings.json"


def load_ui_config() -> dict:
    """Load UI settings from config file."""
    if UI_CONFIG.exists():
        try:
            return json.loads(UI_CONFIG.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_ui_config(config: dict) -> None:
    """Save UI settings to config file."""
    UI_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    UI_CONFIG.write_text(json.dumps(config, indent=2), encoding="utf-8")


@dataclass
class AppState:
    """Global application state."""

    # Library metadata
    meta: dict = field(default_factory=dict)

    # Recommendations state
    seed_track: str | None = None
    recommendations: list[dict] = field(default_factory=list)

    # Filter weights
    weights: dict = field(default_factory=lambda: {
        "ann": 0.6,
        "samples": 0.1,
        "bass": 0.1,
        "rhythm": 0.1,
        "bpm": 0.05,
        "key": 0.05,
        "tags": 0.0,
    })

    # Filter settings
    filters: dict = field(default_factory=lambda: {
        "tempo_pct": 6.0,
        "camelot": True,
        "doubletime": True,
        "bpm_max_diff": 0.0,  # 0 = disabled, otherwise hard limit in BPM
        "allowed_key_relations": [],  # empty = all allowed, or ["same", "relative", "neighbor"]
        "require_tags": [],  # must have all these tags
        "prefer_tags": [],  # soft preference for these tags
    })

    # Workspace settings
    music_folders: list[str] = field(default_factory=list)
    device: str = pick_device("cuda")
    duration_s: int = 90
    workers: int = 4
    batch_size: int = 4
    auto_cues: bool = True
    skip_analyzed: bool = True
    use_timbre: bool = True
    embed_overwrite: bool = True

    @property
    def music_folder(self) -> str:
        """Backward-compatible single-folder accessor."""
        return self.music_folders[0] if self.music_folders else ""

    @music_folder.setter
    def music_folder(self, value: str) -> None:
        """Set a single music folder (clears existing list)."""
        if value:
            self.music_folders = [str(Path(value))]
        else:
            self.music_folders = []

    def refresh_meta(self) -> None:
        """Reload metadata from disk."""
        self.meta = load_meta()

    def get_track_count(self) -> int:
        """Total tracks in library."""
        return len(self.meta.get("tracks", {}))

    def get_embedded_count(self) -> int:
        """Tracks with embeddings."""
        tracks = self.meta.get("tracks", {})
        return sum(1 for t in tracks.values() if t.get("embedding"))

    def get_analyzed_count(self) -> int:
        """Tracks with BPM/key analysis."""
        tracks = self.meta.get("tracks", {})
        return sum(1 for t in tracks.values() if t.get("bpm") and t.get("key"))

    def get_indexed_paths(self) -> list[str]:
        """Return list of indexed track paths."""
        paths_file = IDX / "paths.json"
        if paths_file.exists():
            return json.loads(paths_file.read_text(encoding="utf-8"))
        return []

    def has_index(self) -> bool:
        """Check if HNSW index exists."""
        return (IDX / "hnsw.idx").exists()

    def load_settings(self) -> None:
        """Load settings from config file."""
        config = load_ui_config()
        if config:
            folders = config.get("music_folders")
            # Backward compatibility: accept single string key
            if folders is None:
                legacy = config.get("music_folder", "")
                folders = [legacy] if legacy else []
            # Normalize to list[str]
            if isinstance(folders, str):
                folders = [folders] if folders else []
            self.music_folders = [str(Path(p)) for p in folders if p]
            self.device = config.get("device", pick_device("cuda"))
            self.duration_s = config.get("duration_s", 120)
            self.workers = config.get("workers", 4)
            self.batch_size = config.get("batch_size", 4)
            self.auto_cues = config.get("auto_cues", True)
            self.skip_analyzed = config.get("skip_analyzed", True)
            self.use_timbre = config.get("use_timbre", False)
            self.embed_overwrite = config.get("embed_overwrite", False)

            # Load filter presets
            if "weights" in config:
                self.weights.update(config["weights"])
            if "filters" in config:
                self.filters.update(config["filters"])

    def save_settings(self) -> None:
        """Save settings to config file."""
        config = {
            "music_folders": self.music_folders,
            # legacy key retained for compatibility with older configs
            "music_folder": self.music_folders[0] if self.music_folders else "",
            "device": self.device,
            "duration_s": self.duration_s,
            "workers": self.workers,
            "batch_size": self.batch_size,
            "auto_cues": self.auto_cues,
            "skip_analyzed": self.skip_analyzed,
            "use_timbre": self.use_timbre,
            "embed_overwrite": self.embed_overwrite,
            "weights": self.weights,
            "filters": self.filters,
        }
        save_ui_config(config)


# Global singleton state
state = AppState()
state.refresh_meta()
state.load_settings()


def get_state() -> AppState:
    """Get the global app state."""
    return state
