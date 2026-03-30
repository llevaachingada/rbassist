# Worker Prompt: UI Shell

You are the narrow implementer for UI shell responsiveness in the rbassist NiceGUI stabilization sprint.

Read first:

- `AGENTS.md`
- `docs/dev/PROJECT_CONTINUITY.md`
- `docs/dev/AGENT_WORKFLOW_LANES.md`
- `docs/dev/NICEGUI_STABILIZATION_PASS.md`

You are not alone in the codebase. Other workers may be editing nearby files. Do not revert their changes. Adjust to them.

Your owned write scope:

- `rbassist/ui/app.py`
- `rbassist/ui/components/progress.py`
- tests directly related to shell behavior if needed

Primary goals:

- stop building every heavy page up front
- keep the shell, tabs, and status area visible immediately
- preserve page isolation when one page import or render fails
- add only the smallest shell-level status surface needed for the shared runtime

Do not:

- redesign the visual layout
- add new product features
- touch page business logic unless absolutely required by the shell
- widen into backend orchestration work

Desired outcome:

- page content loads lazily on first activation or otherwise avoids heavy eager startup cost
- shell startup feels materially lighter
- one broken page does not take down the rest of the app

Validation:

- `python -m compileall rbassist\\ui`
- focused `pytest` on `tests/test_ui_app.py`
- add or update only small shell-level tests as needed

In your final handoff include:

- what changed
- files touched
- validation run
- residual risks
