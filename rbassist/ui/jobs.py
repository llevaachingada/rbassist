from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from threading import RLock
from typing import Any
from uuid import uuid4


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clamp_progress(progress: float | None) -> float | None:
    if progress is None:
        return None
    return max(0.0, min(1.0, float(progress)))


@dataclass(frozen=True)
class JobSnapshot:
    job_id: str
    kind: str
    status: str
    phase: str
    message: str
    progress: float | None
    started_at: str
    finished_at: str | None = None
    error: str | None = None
    result: dict[str, Any] | None = None


class JobRegistry:
    """Thread-safe job snapshots for long-running UI work."""

    def __init__(self, *, max_jobs: int = 25) -> None:
        self._lock = RLock()
        self._jobs: dict[str, JobSnapshot] = {}
        self._order: list[str] = []
        self._max_jobs = max(1, int(max_jobs))

    def start(
        self,
        kind: str,
        *,
        phase: str = "queued",
        message: str = "",
        progress: float | None = 0.0,
        status: str = "running",
        result: dict[str, Any] | None = None,
    ) -> JobSnapshot:
        snapshot = JobSnapshot(
            job_id=uuid4().hex,
            kind=kind,
            status=status,
            phase=phase,
            message=message,
            progress=_clamp_progress(progress),
            started_at=_utc_now(),
            result=result,
        )
        with self._lock:
            self._jobs[snapshot.job_id] = snapshot
            self._order = [snapshot.job_id, *[job_id for job_id in self._order if job_id != snapshot.job_id]]
            self._trim()
        return snapshot

    def get(self, job_id: str | None) -> JobSnapshot | None:
        if not job_id:
            return None
        with self._lock:
            return self._jobs.get(job_id)

    def update(
        self,
        job_id: str,
        *,
        status: str | None = None,
        phase: str | None = None,
        message: str | None = None,
        progress: float | None = None,
        error: str | None = None,
        result: dict[str, Any] | None = None,
        finished: bool = False,
    ) -> JobSnapshot | None:
        with self._lock:
            snapshot = self._jobs.get(job_id)
            if snapshot is None:
                return None
            updated = replace(
                snapshot,
                status=status or snapshot.status,
                phase=phase if phase is not None else snapshot.phase,
                message=message if message is not None else snapshot.message,
                progress=_clamp_progress(progress) if progress is not None else snapshot.progress,
                error=error if error is not None else snapshot.error,
                result=result if result is not None else snapshot.result,
                finished_at=_utc_now() if finished else snapshot.finished_at,
            )
            self._jobs[job_id] = updated
            self._order = [job_id, *[existing for existing in self._order if existing != job_id]]
            return updated

    def complete(
        self,
        job_id: str,
        *,
        phase: str = "completed",
        message: str = "Completed",
        result: dict[str, Any] | None = None,
    ) -> JobSnapshot | None:
        return self.update(
            job_id,
            status="completed",
            phase=phase,
            message=message,
            progress=1.0,
            result=result,
            finished=True,
        )

    def fail(
        self,
        job_id: str,
        *,
        phase: str = "failed",
        message: str = "Failed",
        error: str,
        result: dict[str, Any] | None = None,
    ) -> JobSnapshot | None:
        return self.update(
            job_id,
            status="failed",
            phase=phase,
            message=message,
            error=error,
            result=result,
            finished=True,
        )

    def list_recent(self, *, kind: str | None = None, limit: int = 5) -> list[JobSnapshot]:
        with self._lock:
            snapshots = [self._jobs[job_id] for job_id in self._order if job_id in self._jobs]
        if kind:
            snapshots = [snapshot for snapshot in snapshots if snapshot.kind == kind]
        return snapshots[: max(1, int(limit))]

    def latest(self, *, kind: str | None = None) -> JobSnapshot | None:
        snapshots = self.list_recent(kind=kind, limit=1)
        return snapshots[0] if snapshots else None

    def _trim(self) -> None:
        if len(self._order) <= self._max_jobs:
            return
        stale_ids = self._order[self._max_jobs :]
        self._order = self._order[: self._max_jobs]
        for job_id in stale_ids:
            self._jobs.pop(job_id, None)


_REGISTRY = JobRegistry()


def get_job_registry() -> JobRegistry:
    return _REGISTRY


def start_job(kind: str, **kwargs: Any) -> JobSnapshot:
    return _REGISTRY.start(kind, **kwargs)


def get_job(job_id: str | None) -> JobSnapshot | None:
    return _REGISTRY.get(job_id)


def update_job(job_id: str, **kwargs: Any) -> JobSnapshot | None:
    return _REGISTRY.update(job_id, **kwargs)


def complete_job(job_id: str, **kwargs: Any) -> JobSnapshot | None:
    return _REGISTRY.complete(job_id, **kwargs)


def fail_job(job_id: str, **kwargs: Any) -> JobSnapshot | None:
    return _REGISTRY.fail(job_id, **kwargs)


def list_recent_jobs(*, kind: str | None = None, limit: int = 5) -> list[JobSnapshot]:
    return _REGISTRY.list_recent(kind=kind, limit=limit)


def latest_job(*, kind: str | None = None) -> JobSnapshot | None:
    return _REGISTRY.latest(kind=kind)
