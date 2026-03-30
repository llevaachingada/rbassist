# Worker Prompt: Library, Cues, and Discover

You are the narrow implementer for follow-on responsiveness work after the shared job/runtime seam exists.

Read first:

- `AGENTS.md`
- `docs/dev/PROJECT_CONTINUITY.md`
- `docs/dev/AGENT_WORKFLOW_LANES.md`
- `docs/dev/NICEGUI_STABILIZATION_PASS.md`

You are not alone in the codebase. Other workers may be editing nearby files. Do not revert their changes. Adjust to them.

Prerequisite:

- the shared `rbassist/ui/jobs.py` or `rbassist/ui/runtime.py` seam should already exist or be stable enough to consume

Your owned write scope:

- `rbassist/ui/pages/library.py`
- `rbassist/ui/pages/cues.py`
- `rbassist/ui/pages/discover.py`
- small tests directly related to these flows if needed

Primary goals:

- move beatgrid batch status handling onto the shared job/runtime seam
- move cue generation status handling onto the shared job/runtime seam
- move recommendation refresh off the direct UI path
- make latest recommendation request win when users change seed or filters rapidly

Do not:

- redesign these pages
- change recommendation ranking behavior unless required for safe async handling
- widen into unrelated tagging or crate-expander work
- add feature scope

Desired outcome:

- `Library` beatgrid flows stay responsive
- `Cues` flows stay responsive
- `Discover` recommendation refresh no longer feels like a freeze
- worker paths in these flows do not mutate widgets directly

Validation:

- `python -m compileall rbassist\\ui`
- focused `pytest` on touched UI tests
- run `pytest -q tests/test_recommend_index.py` if recommendation wiring changes in a meaningful way
- run the smallest useful targeted checks for beatgrid/cues if their orchestration changes

In your final handoff include:

- what changed
- files touched
- validation run
- residual risks
