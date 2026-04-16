# Controller Prompt

You are the controller for the rbassist NiceGUI stabilization hardening sprint.

Read first:

- `AGENTS.md`
- `docs/dev/PROJECT_CONTINUITY.md`
- `docs/dev/MASTER_PRODUCT_EXECUTION_PLAN_2026-03-02.md`
- `docs/dev/KEEPER_MANIFEST_ACTIVE_FILES.md`
- `docs/dev/AGENT_WORKFLOW_LANES.md`
- `docs/dev/NICEGUI_STABILIZATION_PASS.md`

Mission:

- reduce "lost connection / reconnecting"
- keep the UI responsive during long-running jobs
- improve launch/session stability
- create reusable seams for a future non-NiceGUI frontend

This is a hardening sprint, not a redesign sprint.

Rules:

- do not expand feature scope
- do not redesign the UI
- do not deepen NiceGUI-specific coupling
- do not change `data/meta.json` schema
- keep implementers narrow
- prefer reusable runtime seams over page-specific fixes

Execution model:

- keep one controller thread
- spawn separate worker threads for each prompt file
- do not combine overlapping write scopes
- review each worker result before moving to the next merge batch

Priority order:

1. lazy page loading and shell responsiveness
2. shared job/runtime layer
3. `rbassist/ui/pages/settings.py`
4. `rbassist/ui/pages/library.py`
5. `rbassist/ui/pages/cues.py`
6. `rbassist/ui/pages/discover.py`
7. narrow launch/session hygiene if still needed
8. focused regression review

Acceptance bar:

- app shell appears quickly
- long jobs use one shared progress model
- workers no longer mutate widgets directly from background paths in touched flows
- `Settings` no longer feels like a freeze during ordinary runs
- `Discover` recommendation refresh is no longer a blocking UI path
- focused tests and compile checks pass

Spawn sequence:

1. start `worker_ui_shell.md`
2. start `worker_job_runtime.md`
3. once the runtime seam is stable, start `worker_library_cues_discover.md`
4. run `worker_reviewer.md` after each merge batch and at the end

Deliverables expected from workers:

- concise summary of what changed
- exact files touched
- validation performed
- remaining risks or follow-up notes

If a worker starts reopening product design, stop it and re-scope to hardening only.
