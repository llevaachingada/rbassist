from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from rbassist.ui_services.jobs import describe_job

SMART_QUOTES = {"'", '"', "\u2018", "\u2019", "\u201c", "\u201d"}
SMART_QUOTE_PATTERN = "\"([^\"]+)\"|\u201c([^\u201d]+)\u201d|'([^']+)'|\u2018([^\u2019]+)\u2019"


@dataclass(frozen=True, slots=True)
class SettingsPipelineRequest:
    scope_label: str
    files_total: int
    embed_total: int
    analysis_total: int
    beatgrid_total: int
    overwrite: bool
    skip_analyzed: bool
    use_timbre: bool
    resume_embed: bool
    duration_s: int
    workers: int
    batch_size: int
    device: str | None
    add_cues: bool
    beatgrid_enabled: bool
    beatgrid_overwrite: bool
    checkpoint_file: str
    checkpoint_every: int

    def result_payload(self) -> dict[str, Any]:
        return {
            "scope": self.scope_label,
            "files_total": self.files_total,
            "embed_total": self.embed_total,
            "analysis_total": self.analysis_total,
            "beatgrid_total": self.beatgrid_total,
        }

    def preflight_text(self) -> str:
        return (
            f"**Preflight:** {self.files_total} files found, {self.embed_total} will embed, "
            f"{self.analysis_total} will analyze, {self.beatgrid_total} will beatgrid, "
            f"overwrite={'ON' if self.overwrite else 'OFF'}, resume={'ON' if self.resume_embed else 'OFF'}"
        )

    def running_text(self) -> str:
        return (
            f"Running pipeline on {self.scope_label}: {self.files_total} track(s) "
            f"({self.embed_total} embed, {self.analysis_total} analyze)..."
        )

    def completed_text(self) -> str:
        return "Embed + Analyze + Index complete"

    def failed_text(self) -> str:
        return "Pipeline failed"


@dataclass(frozen=True, slots=True)
class SettingsPipelineView:
    progress_visible: bool
    progress_value: float
    status_text: str
    phase_text: str
    error_text: str
    history_text: str


def parse_folder_inputs(raw: str) -> list[str]:
    if not raw:
        return []

    def _strip_quotes(value: str) -> str:
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in SMART_QUOTES:
            return value[1:-1]
        if value[:1] in SMART_QUOTES:
            value = value[1:]
        if value[-1:] in SMART_QUOTES:
            value = value[:-1]
        return value.strip()

    def _extract_quoted(line: str) -> list[str]:
        matches = re.findall(SMART_QUOTE_PATTERN, line)
        out: list[str] = []
        for a, b, c, d in matches:
            candidate = a or b or c or d
            if candidate:
                out.append(candidate)
        return out

    def _looks_like_path(line: str) -> bool:
        line = line.strip()
        return bool(re.match(r"^[A-Za-z]:[\\/]", line)) or line.startswith("\\\\") or line.startswith("/")

    tokens: list[str] = []
    for line in raw.replace("\r", "\n").split("\n"):
        line = line.strip()
        if not line:
            continue
        quoted = _extract_quoted(line)
        if quoted:
            parts = quoted
        elif ";" in line:
            parts = [part for part in line.split(";") if part.strip()]
        elif _looks_like_path(line):
            parts = [line]
        else:
            try:
                parts = shlex.split(line, posix=False)
            except ValueError:
                parts = [line]
            if len(parts) == 1:
                extra_quoted = _extract_quoted(line)
                if len(extra_quoted) > 1:
                    parts = extra_quoted
        for part in parts:
            for piece in part.split(";"):
                piece = _strip_quotes(piece)
                if piece:
                    tokens.append(piece)
    return tokens


def build_settings_pipeline_request(
    *,
    scope_label: str,
    files_total: int,
    embed_total: int,
    analysis_total: int,
    beatgrid_total: int,
    overwrite: bool,
    skip_analyzed: bool,
    use_timbre: bool,
    resume_embed: bool,
    duration_s: int,
    workers: int,
    batch_size: int,
    device: str | None,
    add_cues: bool,
    beatgrid_enabled: bool,
    beatgrid_overwrite: bool,
    checkpoint_file: str,
    checkpoint_every: int,
) -> SettingsPipelineRequest:
    return SettingsPipelineRequest(
        scope_label=str(scope_label),
        files_total=max(0, int(files_total)),
        embed_total=max(0, int(embed_total)),
        analysis_total=max(0, int(analysis_total)),
        beatgrid_total=max(0, int(beatgrid_total)),
        overwrite=bool(overwrite),
        skip_analyzed=bool(skip_analyzed),
        use_timbre=bool(use_timbre),
        resume_embed=bool(resume_embed),
        duration_s=max(0, int(duration_s)),
        workers=max(0, int(workers)),
        batch_size=max(1, int(batch_size)),
        device=str(device) if device else None,
        add_cues=bool(add_cues),
        beatgrid_enabled=bool(beatgrid_enabled),
        beatgrid_overwrite=bool(beatgrid_overwrite),
        checkpoint_file=str(checkpoint_file).strip(),
        checkpoint_every=max(1, int(checkpoint_every)),
    )


def build_settings_pipeline_view(snapshot: Any | None, recent_jobs: Sequence[Any]) -> SettingsPipelineView:
    display = describe_job(snapshot)
    if snapshot is None:
        progress_visible = False
        progress_value = 0.0
        status_text = "Idle"
        phase_text = "No shared job started yet."
        error_text = ""
    else:
        progress_visible = True
        progress_value = float(display.progress or 0.0)
        status_text = str(getattr(snapshot, "message", "") or "Idle")
        phase_text = f"Phase: {getattr(snapshot, 'phase', '') or '-'} | Status: {getattr(snapshot, 'status', '')}"
        error_text = f"Error: {getattr(snapshot, 'error', '')}" if getattr(snapshot, "error", None) else ""

    if recent_jobs:
        history_text = "Recent settings jobs: " + " | ".join(
            f"{getattr(job, 'status', '')}:{getattr(job, 'phase', '') or '-'}"
            for job in recent_jobs
        )
    else:
        history_text = "Recent settings jobs: none yet."

    return SettingsPipelineView(
        progress_visible=progress_visible,
        progress_value=progress_value,
        status_text=status_text,
        phase_text=phase_text,
        error_text=error_text,
        history_text=history_text,
    )
