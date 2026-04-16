from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone
from typing import Any

from .health import audit_meta_health
from .quarantine import load_quarantine_records
from .utils import ROOT

PRIMARY_MUSIC_ROOT = r"C:\Users\hunte\Music"

SHARED_FOUNDATIONS: list[dict[str, str]] = [
    {
        "path": "README.md",
        "kind": "doc",
        "role": "Primary operator-facing workflow and command reference.",
        "why_keep": "Future agents need one stable entry point for how rbassist is meant to run.",
    },
    {
        "path": "WISHLIST.md",
        "kind": "doc",
        "role": "Backlog and delivery-status map for current rbassist priorities.",
        "why_keep": "This is the quickest way to see what is done versus still risky.",
    },
    {
        "path": "docs/dev/PROJECT_CONTINUITY.md",
        "kind": "doc",
        "role": "Stable north-star brief for mission, scope, current truth, and working rules.",
        "why_keep": "This is the first continuity file future agents should read.",
    },
    {
        "path": "docs/dev/CONTINUITY_LOG.md",
        "kind": "doc",
        "role": "Rolling session log for what changed, what was learned, and what remains next.",
        "why_keep": "This preserves short-form continuity between work sessions.",
    },
    {
        "path": "docs/dev/AGENT_HANDOFF_LOG.md",
        "kind": "doc",
        "role": "Detailed implementation chronology for ingest, hygiene, and Rekordbox work.",
        "why_keep": "This prevents future agents from rediscovering the same local-state history.",
    },
    {
        "path": "rbassist/utils.py",
        "kind": "module",
        "role": "Shared path normalization, audio walking, and meta loading helpers.",
        "why_keep": "Most hygiene and rollout work depends on these path semantics staying consistent.",
    },
    {
        "path": "rbassist/quarantine.py",
        "kind": "module",
        "role": "Durable quarantine load/merge/write logic for known-bad assets.",
        "why_keep": "The active root is rollout-ready only because quarantine became durable and reusable.",
    },
]

WORKSTREAMS: list[dict[str, Any]] = [
    {
        "id": "rbassist-meta-hygiene",
        "summary": "Metadata health, stale-path review, safe bare-path repair, and active-root cleanup.",
        "files": [
            ("rbassist/health.py", "module", "Canonical health audit, pending-gap scan, path normalization, and bare-path repair logic."),
            ("scripts/audit_meta_health.py", "script", "CLI entry point for health baselines and before/after hygiene deltas."),
            ("scripts/normalize_meta_paths.py", "script", "Safe path normalization and collision-remediation workflow."),
            ("scripts/resolve_bare_meta_paths.py", "script", "Bare/orphan filename resolver and safe apply wrapper."),
            ("tests/test_audit_meta_health.py", "test", "Health-audit regression coverage."),
            ("tests/test_normalize_meta_paths.py", "test", "Normalization and collision-remediation regression coverage."),
            ("tests/test_resolve_bare_meta_paths.py", "test", "Bare-path resolution regression coverage."),
            ("docs/dev/IMPLEMENTATION_PLAN_HEALTH_AND_UX.md", "doc", "Detailed implementation map for health and import UX work."),
            ("docs/dev/health_gap_normalize_summary_2026-02-28.md", "doc", "Baseline summary of health, path normalization, and gap findings."),
        ],
    },
    {
        "id": "rbassist-rekordbox-safe-relink",
        "summary": "Read-only Rekordbox audit, review queues, and backup-first relink apply readiness.",
        "files": [
            ("rbassist/rekordbox_audit.py", "module", "Live Rekordbox audit, relink suggestions, consolidation planning, and duplicate dry-run logic."),
            ("rbassist/rekordbox_review.py", "module", "Splits large Rekordbox audits into high-confidence, ambiguous, and duplicate review queues."),
            ("rbassist/rekordbox_import.py", "module", "Existing Rekordbox database access and import helpers."),
            ("scripts/rekordbox_audit_library.py", "script", "CLI wrapper for read-only Rekordbox-vs-root auditing."),
            ("scripts/prepare_rekordbox_review_queues.py", "script", "CLI wrapper for review queue generation from audit outputs."),
            ("tests/test_rekordbox_audit.py", "test", "Rekordbox audit regression coverage."),
            ("tests/test_rekordbox_review.py", "test", "Review-queue generation regression coverage."),
        ],
    },
    {
        "id": "rbassist-duplicate-remediation",
        "summary": "Duplicate detection, review queues, and preferred-keeper decisions across root files and Rekordbox references.",
        "files": [
            ("rbassist/duplicates.py", "module", "Meta-based duplicate grouping and staging helpers."),
            ("rbassist/rekordbox_audit.py", "module", "Name-plus-duration duplicate dry-run logic built from the music-root catalog."),
            ("rbassist/rekordbox_review.py", "module", "Exports same-name different-type duplicate review queues."),
            ("scripts/prepare_rekordbox_review_queues.py", "script", "Writes the duplicate review queue outputs."),
            ("tests/test_duplicates_stage.py", "test", "Duplicate staging regression coverage."),
            ("tests/test_rekordbox_audit.py", "test", "Duplicate dry-run regression coverage inside the Rekordbox audit path."),
        ],
    },
    {
        "id": "rbassist-library-rollout-qa",
        "summary": "End-to-end rollout readiness for the active music root: gaps, quarantine, maintenance, analyze, and indexing.",
        "files": [
            ("rbassist/embed.py", "module", "Embedding engine and checkpoint-aware encode path."),
            ("rbassist/analyze.py", "module", "Incremental BPM/key/cues analysis pipeline."),
            ("rbassist/recommend.py", "module", "Recommendation index creation and chunked index maintenance."),
            ("rbassist/health.py", "module", "Health baselines, missing-coverage counts, and root-scoped gap logic."),
            ("scripts/list_embedding_gaps.py", "script", "Root-scoped pending-embed discovery."),
            ("scripts/run_embed_chunks.py", "script", "Chunked subprocess embed supervisor with retry and CPU fallback paths."),
            ("scripts/run_music_root_background_maintenance.py", "script", "Hands-free root maintenance orchestration for audit, embed, analyze, and index phases."),
            ("scripts/update_embed_quarantine.py", "script", "Promotes repeated failed embeds into durable quarantine."),
            ("scripts/summarize_maintenance_run.py", "script", "Condenses maintenance outputs into readable summaries."),
            ("tests/test_run_embed_chunks.py", "test", "Chunked embed supervisor regression coverage."),
            ("tests/test_run_music_root_background_maintenance.py", "test", "Maintenance supervisor regression coverage."),
            ("tests/test_quarantine.py", "test", "Quarantine merge/load/write regression coverage."),
            ("tests/test_recommend_index.py", "test", "Chunked index maintenance regression coverage."),
            ("docs/status/SYSTEM_STATUS_SUMMARY.md", "doc", "High-level system status summary."),
        ],
    },
]

LOCAL_RUNTIME_KEEPERS: list[dict[str, str]] = [
    {
        "path": "data/meta.json",
        "kind": "runtime-data",
        "role": "Local library metadata store backing health, ingest, and export workflows.",
        "why_keep": "Nearly every active workstream reads from or writes to this local state.",
    },
    {
        "path": "data/quarantine_embed.jsonl",
        "kind": "runtime-data",
        "role": "Durable embed quarantine for known-bad assets.",
        "why_keep": "This file keeps repeated bad assets from poisoning unattended runs.",
    },
    {
        "path": "data/backups",
        "kind": "runtime-dir",
        "role": "Backup directory for metadata repair operations.",
        "why_keep": "Safe cleanup and relink work should always leave recoverable state behind.",
    },
    {
        "path": "data/archives",
        "kind": "runtime-dir",
        "role": "Archive directory for removed or triaged metadata rows.",
        "why_keep": "Future hygiene work needs reversible archival, not silent deletion.",
    },
    {
        "path": "data/runlogs",
        "kind": "runtime-dir",
        "role": "Operational logs, audits, status files, and review queues from live runs.",
        "why_keep": "This is the live evidence trail for rollout QA and Rekordbox review work.",
    },
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _path_exists(repo: pathlib.Path, path_ref: str) -> bool:
    return (repo / path_ref).exists()


def _entry(repo: pathlib.Path, path: str, kind: str, role: str, why_keep: str = "") -> dict[str, Any]:
    return {
        "path": path,
        "kind": kind,
        "role": role,
        "why_keep": why_keep,
        "exists": _path_exists(repo, path),
    }


def _live_state(repo: pathlib.Path) -> dict[str, Any]:
    report = audit_meta_health(repo=repo)
    counts = report.get("counts", {})
    quarantine_total = len(load_quarantine_records(repo / "data" / "quarantine_embed.jsonl"))
    return {
        "available": True,
        "primary_music_root": PRIMARY_MUSIC_ROOT,
        "tracks_total": counts.get("tracks_total", 0),
        "embedding_gap_total": counts.get("embedding_gap_total", 0),
        "stale_track_path_total": counts.get("stale_track_path_total", 0),
        "bare_path_total": counts.get("bare_path_total", 0),
        "missing_bpm_total": counts.get("missing_bpm_total", 0),
        "missing_key_total": counts.get("missing_key_total", 0),
        "missing_cues_total": counts.get("missing_cues_total", 0),
        "missing_mytags_total": counts.get("missing_mytags_total", 0),
        "quarantine_total": quarantine_total,
    }


def build_keeper_manifest(*, repo: pathlib.Path | None = None, include_live_state: bool = False) -> dict[str, Any]:
    repo = (repo or ROOT).resolve()
    shared = [_entry(repo, item["path"], item["kind"], item["role"], item["why_keep"]) for item in SHARED_FOUNDATIONS]
    workstreams: list[dict[str, Any]] = []
    inventory: dict[str, dict[str, Any]] = {}

    def register(owner: str, item: dict[str, Any]) -> None:
        current = inventory.get(item["path"])
        if current is None:
            inventory[item["path"]] = {
                "path": item["path"],
                "kind": item["kind"],
                "exists": item["exists"],
                "owners": [owner],
                "roles": [item["role"]],
            }
            return
        current["exists"] = current["exists"] or item["exists"]
        if owner not in current["owners"]:
            current["owners"].append(owner)
        if item["role"] not in current["roles"]:
            current["roles"].append(item["role"])

    for item in shared:
        register("shared-foundation", item)

    for spec in WORKSTREAMS:
        files = [_entry(repo, path, kind, role) for path, kind, role in spec["files"]]
        for item in files:
            register(spec["id"], item)
        workstreams.append({
            "id": spec["id"],
            "summary": spec["summary"],
            "keeper_files": files,
        })

    runtime = [_entry(repo, item["path"], item["kind"], item["role"], item["why_keep"]) for item in LOCAL_RUNTIME_KEEPERS]
    state = _live_state(repo) if include_live_state else None
    active_inventory = sorted(inventory.values(), key=lambda item: item["path"])

    return {
        "schema_version": 1,
        "generated_at": _utc_now(),
        "repo_root": str(repo),
        "scope": {
            "primary_music_root": PRIMARY_MUSIC_ROOT,
            "focus": "Repo-level keeper manifest for the four active post-ingest rbassist workstreams.",
        },
        "summary": {
            "workstream_total": len(workstreams),
            "shared_foundation_total": len(shared),
            "active_file_inventory_total": len(active_inventory),
            "local_runtime_keeper_total": len(runtime),
            "missing_tracked_keeper_total": sum(1 for item in active_inventory if not item["exists"]),
        },
        "current_state": state,
        "shared_foundations": shared,
        "workstreams": workstreams,
        "local_runtime_keepers": runtime,
        "active_file_inventory": active_inventory,
    }


def build_keeper_manifest_markdown(manifest: dict[str, Any]) -> str:
    lines = [
        "# Keeper Manifest: Active Files",
        "",
        f"- Generated (UTC): `{manifest.get('generated_at', '')}`",
        f"- Repo root: `{manifest.get('repo_root', '')}`",
        f"- Primary music root: `{(manifest.get('scope') or {}).get('primary_music_root', '')}`",
        "",
        "## Purpose",
        "",
        "- Keep the active rbassist files discoverable for the four post-ingest workstreams.",
        "- Separate tracked keeper files from local runtime state while keeping both easy to find.",
        "- Give future agents one curated map instead of making them rediscover the repo layout from scratch.",
        "",
    ]
    current_state = manifest.get("current_state") or {}
    if current_state:
        lines.extend(["## Current State", ""])
        for key in [
            "tracks_total",
            "embedding_gap_total",
            "stale_track_path_total",
            "bare_path_total",
            "missing_bpm_total",
            "missing_key_total",
            "missing_cues_total",
            "missing_mytags_total",
            "quarantine_total",
        ]:
            lines.append(f"- {key}: `{current_state.get(key)}`")
        lines.append("")
    lines.extend(["## Shared Foundations", ""])
    for item in manifest.get("shared_foundations", []):
        lines.append(f"- `{item['path']}`: {item['role']}")
    lines.append("")
    for workstream in manifest.get("workstreams", []):
        lines.extend([f"## {workstream['id']}", ""])
        lines.append(f"- Summary: {workstream['summary']}")
        for item in workstream.get("keeper_files", []):
            exists_text = "exists" if item.get("exists") else "missing"
            lines.append(f"- `{item['path']}` [{exists_text}] - {item['role']}")
        lines.append("")
    lines.extend(["## Local Runtime Keepers", ""])
    for item in manifest.get("local_runtime_keepers", []):
        exists_text = "exists" if item.get("exists") else "not present here"
        lines.append(f"- `{item['path']}` [{exists_text}] - {item['role']}")
    lines.append("")
    return "\n".join(lines) + "\n"


def write_keeper_manifest(
    *,
    repo: pathlib.Path | None = None,
    out_json: pathlib.Path | None = None,
    out_md: pathlib.Path | None = None,
    include_live_state: bool = False,
) -> dict[str, pathlib.Path]:
    repo = (repo or ROOT).resolve()
    manifest = build_keeper_manifest(repo=repo, include_live_state=include_live_state)
    out_json = out_json or (repo / "docs" / "dev" / "keeper_manifest_active_files.json")
    out_md = out_md or (repo / "docs" / "dev" / "KEEPER_MANIFEST_ACTIVE_FILES.md")
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    out_md.write_text(build_keeper_manifest_markdown(manifest), encoding="utf-8")
    return {"json": out_json, "md": out_md}
