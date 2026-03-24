# rbassist Codex Guide

## Mission

- Keep rbassist reliable and safe for a real DJ library centered on `C:\Users\hunte\Music`.
- Preserve local-library safety: `data/meta.json` is the primary local metadata store, and Rekordbox is a secondary truth source for audit and reconciliation.
- Favor practical, reviewable progress over broad refactors.

## Read First

- `README.md` for operator-facing commands, workflows, and product shape.
- `docs/dev/PROJECT_CONTINUITY.md` for current mission, grounded state, and working rules.
- `docs/dev/MASTER_PRODUCT_EXECUTION_PLAN_2026-03-02.md` for current workstream order.
- `docs/dev/KEEPER_MANIFEST_ACTIVE_FILES.md` for the active file map and current workstreams.
- `docs/dev/AGENT_WORKFLOW_LANES.md` for when to use discovery vs hardening and what a handoff must contain.
- `docs/dev/CONTINUITY_LOG.md` and `docs/dev/AGENT_HANDOFF_LOG.md` for recent decisions, evidence, and next steps.

## Working Rules

- Plan before non-trivial edits.
- Use subagents explicitly for larger work. Default full-stack pattern:
  1. `researcher`
  2. `feature-planner`
  3. one narrow implementer
  4. `integration-regression-reviewer`
- Distinguish confirmed facts from assumptions. Cite files, commands, or docs for confirmed facts.
- Prefer the smallest safe vertical slice that proves the change.
- Preserve public CLI and NiceGUI behavior unless the task explicitly changes it.
- Keep implementers narrow. Do not mix CLI/pipeline and GUI work in one pass unless a shared seam makes it necessary.
- Prefer read-only audit, dry run, review queues, then explicit apply for metadata and Rekordbox workflows.
- Treat `data/meta.json`, `data/runlogs`, `data/backups`, `data/archives`, and the music library as user state. Do not mutate them without backup-first and review-first safeguards.
- Avoid unrelated cleanup in a dirty worktree. Never revert user changes you did not make.

## Execution Lanes

- Keep one shared truth layer for both lanes: `README.md`, `docs/dev/PROJECT_CONTINUITY.md`, `docs/dev/MASTER_PRODUCT_EXECUTION_PLAN_2026-03-02.md`, `docs/dev/KEEPER_MANIFEST_ACTIVE_FILES.md`, then the rolling logs.
- Discovery lane: `researcher` then `feature-planner`. Use it for new features, architecture questions, partial wishlist items, risky cross-surface changes, and any task without clear acceptance criteria.
- Discovery handoff must stay compact and include: problem, confirmed facts, scope boundaries or do-not-touch areas, recommended smallest slice, validation plan, and open risks or questions.
- Hardening lane: `researcher`, one narrow implementer, then `integration-regression-reviewer`. Use it for clear bug fixes, polish, approved follow-up slices, focused tests, and other well-scoped work.
- Clear bug fixes and obvious follow-ups may skip discovery and go straight to hardening.
- If hardening uncovers a product question or changed assumption, bounce one concrete question back to discovery instead of guessing or reopening the whole design.

## Validation

- Run targeted validation for the area you touched, usually `pytest` on focused tests.
- When focused tests are missing or UI behavior is hard to exercise directly, use the smallest useful fallback such as `python -m compileall rbassist`.
- After edits, summarize:
  - validation performed
  - confirmed results
  - remaining risks or gaps

## Definition Of Done

- The requested change is implemented or the requested repo workflow/docs are updated.
- Confirmed facts, assumptions, and scope boundaries are clear in the handoff.
- Validation appropriate to the touched area has been run or the gap is explicitly called out.
- Remaining risks and follow-up work are summarized.
- If operational truth changed, update `docs/dev/PROJECT_CONTINUITY.md` and append a dated note to `docs/dev/CONTINUITY_LOG.md` or `docs/dev/AGENT_HANDOFF_LOG.md`.
