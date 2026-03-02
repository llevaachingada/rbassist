# Keeper Manifest: Active Files

- Generated (UTC): `2026-03-02T08:40:23Z`
- Repo root: `C:\Users\hunte\Music\rbassist`
- Primary music root: `C:\Users\hunte\Music`

## Purpose

- Keep the active rbassist files discoverable for the four post-ingest workstreams.
- Separate tracked keeper files from local runtime state while keeping both easy to find.
- Give future agents one curated map instead of making them rediscover the repo layout from scratch.

## Current State

- tracks_total: `13331`
- embedding_gap_total: `3323`
- stale_track_path_total: `2511`
- bare_path_total: `1457`
- missing_bpm_total: `3328`
- missing_key_total: `3328`
- missing_cues_total: `3329`
- missing_mytags_total: `9073`
- quarantine_total: `813`

## Shared Foundations

- `README.md`: Primary operator-facing workflow and command reference.
- `WISHLIST.md`: Backlog and delivery-status map for current rbassist priorities.
- `docs/dev/PROJECT_CONTINUITY.md`: Stable north-star brief for mission, scope, current truth, and working rules.
- `docs/dev/CONTINUITY_LOG.md`: Rolling session log for what changed, what was learned, and what remains next.
- `docs/dev/AGENT_HANDOFF_LOG.md`: Detailed implementation chronology for ingest, hygiene, and Rekordbox work.
- `rbassist/utils.py`: Shared path normalization, audio walking, and meta loading helpers.
- `rbassist/quarantine.py`: Durable quarantine load/merge/write logic for known-bad assets.

## rbassist-meta-hygiene

- Summary: Metadata health, stale-path review, safe bare-path repair, and active-root cleanup.
- `rbassist/health.py` [exists] - Canonical health audit, pending-gap scan, path normalization, and bare-path repair logic.
- `scripts/audit_meta_health.py` [exists] - CLI entry point for health baselines and before/after hygiene deltas.
- `scripts/normalize_meta_paths.py` [exists] - Safe path normalization and collision-remediation workflow.
- `scripts/resolve_bare_meta_paths.py` [exists] - Bare/orphan filename resolver and safe apply wrapper.
- `tests/test_audit_meta_health.py` [exists] - Health-audit regression coverage.
- `tests/test_normalize_meta_paths.py` [exists] - Normalization and collision-remediation regression coverage.
- `tests/test_resolve_bare_meta_paths.py` [exists] - Bare-path resolution regression coverage.
- `docs/dev/IMPLEMENTATION_PLAN_HEALTH_AND_UX.md` [exists] - Detailed implementation map for health and import UX work.
- `docs/dev/health_gap_normalize_summary_2026-02-28.md` [exists] - Baseline summary of health, path normalization, and gap findings.

## rbassist-rekordbox-safe-relink

- Summary: Read-only Rekordbox audit, review queues, and backup-first relink apply readiness.
- `rbassist/rekordbox_audit.py` [exists] - Live Rekordbox audit, relink suggestions, consolidation planning, and duplicate dry-run logic.
- `rbassist/rekordbox_review.py` [exists] - Splits large Rekordbox audits into high-confidence, ambiguous, and duplicate review queues.
- `rbassist/rekordbox_import.py` [exists] - Existing Rekordbox database access and import helpers.
- `scripts/rekordbox_audit_library.py` [exists] - CLI wrapper for read-only Rekordbox-vs-root auditing.
- `scripts/prepare_rekordbox_review_queues.py` [exists] - CLI wrapper for review queue generation from audit outputs.
- `tests/test_rekordbox_audit.py` [exists] - Rekordbox audit regression coverage.
- `tests/test_rekordbox_review.py` [exists] - Review-queue generation regression coverage.

## rbassist-duplicate-remediation

- Summary: Duplicate detection, review queues, and preferred-keeper decisions across root files and Rekordbox references.
- `rbassist/duplicates.py` [exists] - Meta-based duplicate grouping and staging helpers.
- `rbassist/rekordbox_audit.py` [exists] - Name-plus-duration duplicate dry-run logic built from the music-root catalog.
- `rbassist/rekordbox_review.py` [exists] - Exports same-name different-type duplicate review queues.
- `scripts/prepare_rekordbox_review_queues.py` [exists] - Writes the duplicate review queue outputs.
- `tests/test_duplicates_stage.py` [exists] - Duplicate staging regression coverage.
- `tests/test_rekordbox_audit.py` [exists] - Duplicate dry-run regression coverage inside the Rekordbox audit path.

## rbassist-library-rollout-qa

- Summary: End-to-end rollout readiness for the active music root: gaps, quarantine, maintenance, analyze, and indexing.
- `rbassist/embed.py` [exists] - Embedding engine and checkpoint-aware encode path.
- `rbassist/analyze.py` [exists] - Incremental BPM/key/cues analysis pipeline.
- `rbassist/recommend.py` [exists] - Recommendation index creation and chunked index maintenance.
- `rbassist/health.py` [exists] - Health baselines, missing-coverage counts, and root-scoped gap logic.
- `scripts/list_embedding_gaps.py` [exists] - Root-scoped pending-embed discovery.
- `scripts/run_embed_chunks.py` [exists] - Chunked subprocess embed supervisor with retry and CPU fallback paths.
- `scripts/run_music_root_background_maintenance.py` [exists] - Hands-free root maintenance orchestration for audit, embed, analyze, and index phases.
- `scripts/update_embed_quarantine.py` [exists] - Promotes repeated failed embeds into durable quarantine.
- `scripts/summarize_maintenance_run.py` [exists] - Condenses maintenance outputs into readable summaries.
- `tests/test_run_embed_chunks.py` [exists] - Chunked embed supervisor regression coverage.
- `tests/test_run_music_root_background_maintenance.py` [exists] - Maintenance supervisor regression coverage.
- `tests/test_quarantine.py` [exists] - Quarantine merge/load/write regression coverage.
- `tests/test_recommend_index.py` [exists] - Chunked index maintenance regression coverage.
- `docs/status/SYSTEM_STATUS_SUMMARY.md` [exists] - High-level system status summary.

## Local Runtime Keepers

- `data/meta.json` [exists] - Local library metadata store backing health, ingest, and export workflows.
- `data/quarantine_embed.jsonl` [exists] - Durable embed quarantine for known-bad assets.
- `data/backups` [exists] - Backup directory for metadata repair operations.
- `data/archives` [not present here] - Archive directory for removed or triaged metadata rows.
- `data/runlogs` [exists] - Operational logs, audits, status files, and review queues from live runs.

