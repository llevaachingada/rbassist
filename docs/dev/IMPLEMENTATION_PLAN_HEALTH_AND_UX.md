# Health + UX Implementation Plan

Generated: 2026-02-28

## Current Focus
1. Health audit + path normalization
2. UI health dashboard + import UX cleanup

## Phase 1: Health Audit + Path Normalization
- Add shared path normalization helpers in `rbassist/utils.py`
- Add `scripts/audit_meta_health.py`
- Add `scripts/list_embedding_gaps.py`
- Add `scripts/normalize_meta_paths.py`
- Add `scripts/resolve_bare_meta_paths.py`
- Add tests for audit/gap/normalize flows
- Current status: implemented, validated, and baseline artifacts generated. Collision-aware path remediation is live, and a first safe bare-path/orphan apply pass has already reduced `data/meta.json` from `9,949` rows to `8,825` canonical rows.

## Phase 2: UI Health Dashboard + Import UX Cleanup
- Add health summary component for UI
- Surface health counts in Library page
- Add health actions + preflight summary to Settings page
- Clarify one-folder import workflow
- Surface overwrite/resume/checkpoint behavior clearly
- Current status: implemented for the current ingest/repair workflow. Health cards, actions, filters, collision-safe path repair, and clearer import scope controls are live; remaining polish is secondary UI refinement.

## Acceptance Criteria
- One command can explain library health
- One UI screen can explain library health
- Import actions show preflight counts before processing
- Path drift and junk files are visible instead of hidden

## Handoff Notes
- Keep this file updated after each implementation chunk
- Record blockers, changed files, and next steps in `docs/dev/AGENT_HANDOFF_LOG.md`
- Remaining Phase 1 cleanup target: review the unresolved `1,457` bare-path/orphan rows, which are now limited to ambiguous filename matches or tracks no longer found under the scanned music roots.
