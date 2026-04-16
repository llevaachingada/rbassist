from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class JobDisplay:
    """UI-neutral rendering data for a job-like snapshot."""

    text: str
    busy: bool
    status: str
    phase: str
    progress: float | None


def describe_job(snapshot: Any | None) -> JobDisplay:
    """Convert any job-like snapshot into frontend-neutral display state."""
    if snapshot is None:
        return JobDisplay(text="Ready", busy=False, status="", phase="", progress=None)

    status = str(getattr(snapshot, "status", "") or "").strip().lower()
    phase = str(getattr(snapshot, "phase", "") or "").strip()
    message = str(getattr(snapshot, "message", "") or "").strip()
    progress = getattr(snapshot, "progress", None)

    if status == "running":
        if message:
            text = message
        elif phase:
            text = f"Running {phase}"
        else:
            text = "Working..."
        return JobDisplay(text=text, busy=True, status=status, phase=phase, progress=progress)

    if status == "queued":
        return JobDisplay(text=message or "Queued", busy=True, status=status, phase=phase, progress=progress)

    if status == "failed":
        return JobDisplay(text=message or "Last job failed", busy=False, status=status, phase=phase, progress=progress)

    if status == "completed":
        return JobDisplay(text=message or "Last job completed", busy=False, status=status, phase=phase, progress=progress)

    return JobDisplay(text=message or "Ready", busy=False, status=status, phase=phase, progress=progress)


def job_to_dict(snapshot: Any | None) -> dict[str, Any]:
    """Return a simple dictionary that non-NiceGUI frontends can render."""
    display = describe_job(snapshot)
    return {
        "text": display.text,
        "busy": display.busy,
        "status": display.status,
        "phase": display.phase,
        "progress": display.progress,
    }

