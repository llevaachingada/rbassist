from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from rbassist.ui_services.jobs import describe_job


@dataclass(frozen=True, slots=True)
class CueBatchPlan:
    total_paths: int
    target_paths: list[str]
    overwrite_existing: bool


@dataclass(frozen=True, slots=True)
class CuePageView:
    progress_visible: bool
    progress_value: float
    status_text: str
    phase_text: str
    history_text: str


def plan_cue_targets(
    meta: Mapping[str, Any],
    paths: Sequence[str],
    *,
    overwrite_existing: bool,
) -> CueBatchPlan:
    """Return the cue-generation target set without touching UI state."""
    tracks = meta.get("tracks", {}) if isinstance(meta, Mapping) else {}
    total_paths = len(paths)

    if overwrite_existing:
        target_paths = [str(path) for path in paths]
    else:
        target_paths = []
        for path in paths:
            info = tracks.get(path, {})
            if not isinstance(info, Mapping):
                info = {}
            if not info.get("cues"):
                target_paths.append(str(path))

    return CueBatchPlan(
        total_paths=total_paths,
        target_paths=target_paths,
        overwrite_existing=overwrite_existing,
    )


def build_cue_page_view(snapshot: Any | None, recent_jobs: Sequence[Any]) -> CuePageView:
    """Build the read-only view model for the cues page status panel."""
    display = describe_job(snapshot)
    if snapshot is None:
        progress_visible = False
        progress_value = 0.0
        status_text = "No active cue job."
        phase_text = ""
    else:
        progress_visible = True
        progress_value = float(display.progress or 0.0)
        status_text = str(getattr(snapshot, "message", "") or "Idle")
        phase_text = f"Phase: {display.phase or '-'} | Status: {display.status}"

    if recent_jobs:
        history_text = "Recent cue jobs: " + " | ".join(
            f"{getattr(job, 'status', '')}:{getattr(job, 'phase', '') or '-'}"
            for job in recent_jobs
        )
    else:
        history_text = "Recent cue jobs: none yet."

    return CuePageView(
        progress_visible=progress_visible,
        progress_value=progress_value,
        status_text=status_text,
        phase_text=phase_text,
        history_text=history_text,
    )
