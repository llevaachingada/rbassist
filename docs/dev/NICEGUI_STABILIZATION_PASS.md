# NiceGUI Stabilization Pass

## Purpose

This document is the implementation plan for a short hardening sprint on the current NiceGUI UI.

The goal is not to perfect NiceGUI or expand feature scope. The goal is to:

- reduce "lost connection / reconnecting" during ordinary local use
- keep the UI responsive while long-running jobs are active
- make launch and session behavior less brittle
- build reusable seams that help the later non-NiceGUI desktop rewrite

This is a bridge sprint, not a redesign sprint.

## Why This Sprint Exists

The current UI still has a few structural problems that are worth fixing before a desktop rewrite:

- the app shell still pays too much startup cost in `rbassist/ui/app.py`
- page files still own too much workflow orchestration
- long-running jobs still mix background work with direct widget updates
- recommendation refresh still blocks the direct UI path
- launch flow is still browser/server-first instead of desktop-first

Those issues make the current app feel more fragile than it needs to, and they also make a later GUI migration harder.

## Product Rules

Every stabilization change must satisfy at least one of these:

1. reduce current flakiness or blocking behavior now
2. create a reusable seam for a future non-NiceGUI frontend

Preferred changes do both.

## Non-Goals

Do not spend this sprint on:

- PySide, WPF, WinUI, Tauri, or any other replacement GUI
- visual redesign
- new tabs or new product features
- deep state redesign beyond what shared job state needs
- full table virtualization
- major AI tagging redesign
- `data/meta.json` schema changes
- Rekordbox write-path expansion

## Success Criteria

By the end of this pass, the current app should:

- show the app shell quickly instead of eagerly doing expensive page work
- keep long-running flows responsive for `embed`, `analyze`, `index`, `beatgrid`, `cues`, and `recommend`
- show one shared job/progress surface with persistent phase text and status
- survive a brief client reconnect without losing the logical job state
- fail more clearly around port, launch, or busy-session issues
- avoid making NiceGUI coupling deeper than it already is

## Architecture Guardrails

Use these guardrails while editing:

- Keep page files thin.
- Move orchestration and progress ownership out of page callbacks.
- Workers should update shared job state only.
- UI should read and render shared job state.
- Do not introduce new NiceGUI-only progress abstractions that cannot survive a future GUI swap.
- Prefer shared runtime helpers over bespoke fixes per page.

The target shape after this sprint is:

- backend modules remain unchanged where possible
- a shared UI runtime or job layer sits between frontend and backend
- NiceGUI pages mostly render state and trigger shared operations
- a future desktop frontend can reuse the same job model and orchestration seams

## Priority Hotspots

These are the first files to target:

- `rbassist/ui/app.py`
- `rbassist/ui/state.py`
- `rbassist/ui/pages/settings.py`
- `rbassist/ui/pages/library.py`
- `rbassist/ui/pages/discover.py`
- `rbassist/ui/pages/cues.py`
- `rbassist/cli.py`
- `start.ps1`

## Recommended Shared Seams

This sprint should introduce one small shared runtime layer, for example:

- `rbassist/ui/jobs.py`
- or `rbassist/ui/runtime.py`

Minimum shared responsibilities:

- job registry
- job lifecycle state
- progress snapshots
- status messages
- timestamps
- error/result payloads

Recommended job fields:

- `job_id`
- `kind`
- `status`
- `phase`
- `message`
- `progress`
- `started_at`
- `finished_at`
- `error`
- `result`

Recommended statuses:

- `queued`
- `running`
- `completed`
- `failed`
- `cancelled`

## Workstreams

### Workstream 1: UI Shell and Startup Hardening

Primary files:

- `rbassist/ui/app.py`
- `rbassist/ui/components/progress.py`

Tasks:

- stop building every heavy page up front
- lazy-load page content on first activation
- keep the shell, tabs, and status area visible immediately
- preserve the existing page-isolation fallback behavior

Acceptance criteria:

- shell appears quickly
- switching tabs only loads what is needed
- one broken page does not kill the rest of the app

### Workstream 2: Shared Job and Progress Runtime

Primary files:

- new `rbassist/ui/jobs.py` or `rbassist/ui/runtime.py`
- `rbassist/ui/state.py`

Tasks:

- introduce one shared job model
- workers update shared state only
- UI polls and renders shared state
- remove direct widget mutation from background worker code

Acceptance criteria:

- long-running tasks no longer depend on live widget references in worker code
- reconnecting clients can still see current logical job state
- progress and phase text are consistent across pages

### Workstream 3: Settings Pipeline Migration

Primary files:

- `rbassist/ui/pages/settings.py`

Tasks:

- migrate embed/analyze/index/beatgrid orchestration onto the shared job runtime
- preserve current safety defaults
- keep existing backend calls where possible
- expose a stable phase sequence to the shared job surface

Acceptance criteria:

- "Process configured folders" no longer feels like a freeze
- "Process paths file" no longer feels like a freeze
- progress is driven by shared job state

### Workstream 4: Library and Cues Migration

Primary files:

- `rbassist/ui/pages/library.py`
- `rbassist/ui/pages/cues.py`

Tasks:

- move beatgrid batch status handling to the shared job runtime
- move cue generation batch status handling to the shared job runtime
- keep single-file and folder workflows working

Acceptance criteria:

- beatgrid and cue runs stay responsive
- progress survives a page change or reconnect logically
- worker paths no longer mutate UI controls directly

### Workstream 5: Discover Responsiveness

Primary files:

- `rbassist/ui/pages/discover.py`

Tasks:

- move recommendation refresh off the direct UI path
- add visible running state
- make latest request win when seed or filters change rapidly
- avoid stale recommendation updates landing after a newer request

Acceptance criteria:

- recommendation refresh no longer feels like a freeze
- row-click and page interaction stay responsive during ranking

### Workstream 6: Launch and Session Hygiene

Primary files:

- `start.ps1`
- `rbassist/cli.py`
- maybe `rbassist/ui/app.py`

Tasks:

- improve occupied-port handling
- improve second-launch behavior
- support clearer launch status text
- optionally support no-auto-open behavior for calmer startup
- fail faster and clearer when a busy environment causes obvious launch friction

Acceptance criteria:

- second launch does not look broken
- launch errors are clearer
- operator has fewer manual recovery steps

## Recommended Two-Week Schedule

### Week 1

Day 1:

- confirm blocking paths and worker-thread UI mutation paths
- finalize file touch sets
- start shell lazy-loading work

Day 2:

- land the shared job runtime skeleton
- add minimal unit tests for job lifecycle and snapshots

Day 3:

- migrate the `Settings` pipeline to shared job state
- keep backend calls intact

Day 4:

- finish `Settings`
- add one persistent jobs/status surface in the shell

Day 5:

- migrate `Library` beatgrid flows
- migrate `Cues` flows

### Week 2

Day 6:

- finish `Library` and `Cues`
- stabilize reconnect-safe job rendering

Day 7:

- migrate `Discover` recommendation refresh to the shared runtime
- add latest-request-wins behavior

Day 8:

- tighten launch behavior in `start.ps1` and any needed CLI flags

Day 9:

- targeted regression pass
- compile checks
- focused smoke workflows

Day 10:

- final cleanup
- remaining bug fixes
- short handoff notes and next-step recommendations

## Fast One-Week Version

If this must fit inside one aggressive week, cut scope to:

1. lazy page loading in `rbassist/ui/app.py`
2. shared job runtime
3. `Settings` pipeline migration
4. one persistent jobs/status surface

That is the highest-leverage subset.

## Agent Lanes

### Researcher

Goal:

- confirm every blocking path
- confirm every worker-thread widget mutation path
- confirm every page that should be lazy-loaded first

Deliverable:

- one short findings memo

No edits.

### Feature Planner

Goal:

- turn findings into small parallel slices

Deliverable:

- one compact execution brief with file touch sets, validation commands, and deferrals

No redesign.

### UI Shell Implementer

Own:

- `rbassist/ui/app.py`
- maybe `rbassist/ui/components/progress.py`

Deliverable:

- lazy-loaded shell
- persistent jobs/status area
- page isolation still works

### Job Runner Implementer

Own:

- new `rbassist/ui/jobs.py` or `rbassist/ui/runtime.py`
- `rbassist/ui/state.py`
- `rbassist/ui/pages/settings.py`
- `rbassist/ui/pages/library.py`
- `rbassist/ui/pages/cues.py`

Deliverable:

- shared job model
- progress driven from shared state
- no direct worker-thread widget mutation

### Discover Implementer

Own:

- `rbassist/ui/pages/discover.py`

Deliverable:

- non-blocking recommendation refresh
- latest request wins

### Integration and Regression Reviewer

Own:

- `tests/test_ui_app.py`
- `tests/test_ui_state.py`
- `tests/test_ui_components.py`
- add `tests/test_ui_jobs.py`

Deliverable:

- focused green test run
- compile checks
- one smoke workflow summary

## Validation Plan

Focused validation after each slice:

- `python -m compileall rbassist\\ui`
- `pytest -q tests/test_ui_app.py tests/test_ui_state.py tests/test_ui_components.py`

Additional validation once the shared job layer exists:

- `pytest -q tests/test_ui_jobs.py`

Reuse relevant backend checks where touched behavior depends on them:

- `pytest -q tests/test_recommend_index.py`
- `pytest -q tests/test_beatgrid.py`
- `pytest -q tests/test_embed_resume.py`
- `pytest -q tests/test_run_embed_chunks.py`

Manual smoke expectations:

- app launches and shell appears quickly
- long-running `Settings` pipeline shows shared progress without freezing the page
- one beatgrid or cue run stays responsive
- one recommendation refresh stays responsive

## Minimum New Tests

Add only the smallest useful tests:

- job lifecycle transitions
- progress snapshot updates
- lazy page load or deferred render behavior
- settings orchestration reporting via shared job state
- discover latest-request-wins behavior
- launch helper behavior if launch logic changes

## Deferrals

Leave these for the later desktop rewrite or later focused slices:

- full non-NiceGUI migration
- deep multi-window correctness
- replacing all `tkinter` dialogs
- large-table virtualization
- visual polish beyond clear responsiveness gains
- broad extraction of every page-owned behavior

## Done Means

This sprint is done when:

- the shell loads quickly enough to feel immediate
- long-running jobs show one coherent progress model
- the common reconnect weirdness is materially reduced
- `Settings` no longer owns ad hoc worker-thread UI updates
- `Library`, `Cues`, and `Discover` follow the same runtime pattern where touched
- launch behavior is less brittle
- focused validation passes
- future agents can continue from this document without replaying chat history

## Immediate First Slice

Start here:

1. lazy page loading in `rbassist/ui/app.py`
2. new shared job runtime
3. migrate `rbassist/ui/pages/settings.py`
4. add one persistent jobs/status surface

That is the fastest visible improvement and the best bridge to a future non-NiceGUI frontend.
