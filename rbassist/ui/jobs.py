"""Compatibility exports for the NiceGUI job runtime."""

from __future__ import annotations

from rbassist.runtime.jobs import (
    ACTIVE_JOB_STATUSES,
    JobRegistry,
    JobSnapshot,
    complete_job,
    fail_job,
    get_job,
    get_job_registry,
    latest_job,
    list_recent_jobs,
    resolve_active_job,
    start_job,
    update_job,
)

__all__ = [
    "ACTIVE_JOB_STATUSES",
    "JobRegistry",
    "JobSnapshot",
    "complete_job",
    "fail_job",
    "get_job",
    "get_job_registry",
    "latest_job",
    "list_recent_jobs",
    "resolve_active_job",
    "start_job",
    "update_job",
]
