# rbassist Codex Guide

## Mission

- Keep rbassist reliable and safe for a real DJ library centered on `C:\Users\hunte\Music`.
- Preserve local-library safety: `data/meta.json` is the primary local metadata store, and Rekordbox is a secondary truth source for audit and reconciliation.
- Favor practical, reviewable progress over broad refactors.

## Read First

- This file is the authoritative workspace guide for Codex in this repository. Read and follow it before choosing agent strategy, editing files, or touching local DJ-library state.
- `README.md` for operator-facing commands, workflows, and product shape.
- `docs/dev/PROJECT_CONTINUITY.md` for current mission, grounded state, and working rules.
- `docs/dev/MASTER_PRODUCT_EXECUTION_PLAN_2026-03-02.md` for current workstream order.
- `docs/dev/KEEPER_MANIFEST_ACTIVE_FILES.md` for the active file map and current workstreams.
- `docs/dev/AGENT_WORKFLOW_LANES.md` for when to use discovery vs hardening and what a handoff must contain.
- `docs/dev/CONTINUITY_LOG.md` and `docs/dev/AGENT_HANDOFF_LOG.md` for recent decisions, evidence, and next steps.

## Subagent Model Compatibility

- This ChatGPT account does not support `gpt-5.2-codex`. Do not use named subagent roles that may resolve to `gpt-5.2-codex`, including `researcher`, `feature-planner`, `integration-regression-reviewer`, `worker`, or role-specific implementers.
- When subagents are useful, spawn `agent_type="default"` with an explicit supported model, and put the intended role in the prompt text instead of using the role selector.
- Default subagent choice: use `model="gpt-5.4"` with `reasoning_effort="medium"` for normal repo research, implementation planning, hardening, GUI integration, and regression review.
- Use `model="gpt-5.4"` with `reasoning_effort="high"` for architecture decisions, CUDA/performance diagnosis, rollout planning, and final high-risk review.
- Use `model="gpt-5.4-mini"` only for cheap, narrow, read-only chores where speed matters more than depth.

## Working Rules

- Plan before non-trivial edits.
- Use subagents explicitly for larger work, but only through compatible default agents described above. Default full-stack pattern:
  1. default `gpt-5.4` medium agent prompted as a read-only researcher
  2. default `gpt-5.4` medium or high agent prompted as a feature planner
  3. one narrow default `gpt-5.4` medium implementer when delegation is explicitly allowed
  4. default `gpt-5.4` high agent prompted as an integration/regression reviewer
- Distinguish confirmed facts from assumptions. Cite files, commands, or docs for confirmed facts.
- Prefer the smallest safe vertical slice that proves the change.
- Preserve public CLI and NiceGUI behavior unless the task explicitly changes it.
- Keep implementers narrow. Do not mix CLI/pipeline and GUI work in one pass unless a shared seam makes it necessary.
- Prefer read-only audit, dry run, review queues, then explicit apply for metadata and Rekordbox workflows.
- Treat `data/meta.json`, `data/runlogs`, `data/backups`, `data/archives`, and the music library as user state. Do not mutate them without backup-first and review-first safeguards.
- Avoid unrelated cleanup in a dirty worktree. Never revert user changes you did not make.

## Execution Lanes

- Keep one shared truth layer for both lanes: `README.md`, `docs/dev/PROJECT_CONTINUITY.md`, `docs/dev/MASTER_PRODUCT_EXECUTION_PLAN_2026-03-02.md`, `docs/dev/KEEPER_MANIFEST_ACTIVE_FILES.md`, then the rolling logs.
- Discovery lane: compatible default agent prompted as researcher, then compatible default agent prompted as feature planner. Use it for new features, architecture questions, partial wishlist items, risky cross-surface changes, and any task without clear acceptance criteria.
- Discovery handoff must stay compact and include: problem, confirmed facts, scope boundaries or do-not-touch areas, recommended smallest slice, validation plan, and open risks or questions.
- Hardening lane: compatible default agent prompted as researcher, one narrow default-agent implementer when delegation is explicitly allowed, then compatible default agent prompted as integration/regression reviewer. Use it for clear bug fixes, polish, approved follow-up slices, focused tests, and other well-scoped work.
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
