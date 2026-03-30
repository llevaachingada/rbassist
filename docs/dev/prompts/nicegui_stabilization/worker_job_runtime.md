# Worker Prompt: Shared Job Runtime and Settings

You are the narrow implementer for the shared UI job/runtime layer in the rbassist NiceGUI stabilization sprint.

Read first:

- `AGENTS.md`
- `docs/dev/PROJECT_CONTINUITY.md`
- `docs/dev/AGENT_WORKFLOW_LANES.md`
- `docs/dev/NICEGUI_STABILIZATION_PASS.md`

You are not alone in the codebase. Other workers may be editing nearby files. Do not revert their changes. Adjust to them.

Your owned write scope:

- new `rbassist/ui/jobs.py` or `rbassist/ui/runtime.py`
- `rbassist/ui/state.py`
- `rbassist/ui/pages/settings.py`
- tests directly related to the new job/runtime seam

Primary goals:

- introduce one shared job state model
- move progress ownership out of page-local widget mutation
- have workers update shared job state only
- have the UI render or poll shared job state
- migrate `Settings` pipeline orchestration first

Recommended minimum job model:

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

Do not:

- redesign `Settings`
- change backend product behavior unless required for safe orchestration
- change `data/meta.json` schema
- widen into `Library`, `Cues`, or `Discover` unless required for a tiny shared seam

Desired outcome:

- `Process configured folders` and `Process paths file` no longer feel like direct UI freezes
- progress is driven by shared state rather than widget references inside worker callbacks
- shared runtime seam is reusable by a future non-NiceGUI frontend

Validation:

- `python -m compileall rbassist\\ui`
- focused `pytest` on `tests/test_ui_state.py`
- add a small `tests/test_ui_jobs.py`
- run any smallest necessary targeted test for touched behavior

In your final handoff include:

- what changed
- files touched
- validation run
- residual risks
