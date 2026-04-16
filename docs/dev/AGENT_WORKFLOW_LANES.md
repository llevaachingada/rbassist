# Agent Workflow Lanes

## Purpose

- Keep one shared project truth while letting rbassist use two different execution lanes:
  - discovery for underdefined ideas
  - hardening for implementation and regression control

## Shared Backbone

- Both lanes use the same source of truth:
  - `README.md`
  - `docs/dev/PROJECT_CONTINUITY.md`
  - `docs/dev/MASTER_PRODUCT_EXECUTION_PLAN_2026-03-02.md`
  - `docs/dev/KEEPER_MANIFEST_ACTIVE_FILES.md`
  - `docs/dev/CONTINUITY_LOG.md`
  - `docs/dev/AGENT_HANDOFF_LOG.md`
- Do not create separate continuity docs or competing plans for each lane.

## Discovery Lane

- Agents: `researcher` -> `feature-planner`
- Use when:
  - the feature idea is new or fuzzy
  - acceptance criteria are missing
  - the work crosses CLI, GUI, pipeline, or metadata safety boundaries
  - the wishlist item is partial, experimental, or still design-level
- Discovery covers the first half of the D4 loop:
  - Discover: ground the problem in repo facts, user intent, and current constraints
  - Design: choose the smallest safe next slice and name the tradeoffs
- Discovery should also label the maturity of the next step:
  - `Spike`: answer a design question or prove feasibility
  - `Pilot`: ship one guarded vertical slice
  - `Scale`: expand a proven approach more broadly

## Hardening Lane

- Agents: `researcher` -> one narrow implementer -> `integration-regression-reviewer`
- Use when:
  - the task is a clear bug fix
  - the scope is already approved
  - discovery already produced a handoff
  - the work is a focused follow-up slice, polish pass, or targeted test gap
- Hardening covers the second half of the D4 loop:
  - Develop: implement the approved slice with the narrowest useful touch set
  - Defend: verify behavior, review regressions, and fail closed on unclear scope
- Hardening should not reopen broad product design. If a real product question appears, send one concrete blocker back to discovery.

## Handoff Contract

- Discovery hands hardening a compact note with:
  - problem to solve
  - confirmed facts and evidence
  - constraints or do-not-touch areas
  - recommended smallest slice
  - validation plan
  - open risks or questions
- Hardening hands back:
  - what changed
  - what was validated
  - any changed assumptions
  - remaining risks or follow-up questions

## Routing Rules

- Start in discovery for new feature concepts such as BPM/Rekordbox separation refinements or exploratory large-library UX changes.
- Start in hardening for scoped regressions such as a stale-path cleanup bug, a broken CLI flag, or a focused NiceGUI polish pass with clear acceptance criteria.
- Not every task needs both lanes. Use the smallest lane that keeps the work safe and understandable.
