# NiceGUI Stabilization Prompt Pack

## Recommended Usage

Use one controller thread.

From that controller thread, spawn separate worker threads or agents for each implementation lane.

Do not run the whole sprint from one giant implementation prompt.

Do not put multiple implementers with overlapping write scopes into the same worker thread.

## Why This Layout

This repo works best when:

- one controller keeps the overall plan and sequence
- each implementer owns a narrow file set
- one reviewer checks regressions after merge batches

That keeps the work hands-off without letting the sprint sprawl.

## Files

- `controller.md`
- `worker_ui_shell.md`
- `worker_job_runtime.md`
- `worker_library_cues_discover.md`
- `worker_reviewer.md`

## Recommended Execution Order

1. Start the controller thread with `controller.md`.
2. Spawn the UI shell worker with `worker_ui_shell.md`.
3. Spawn the job runtime worker with `worker_job_runtime.md`.
4. After the shared job/runtime seam is stable, spawn the library/cues/discover worker with `worker_library_cues_discover.md`.
5. Run the reviewer with `worker_reviewer.md` after each merge batch, and again at the end.

## Thread Model

Best model:

- one top-level controller thread
- one separate thread per worker
- one separate thread for the reviewer

Do not use one long self-splitting implementation prompt for this sprint.

## Primary Plan Reference

Use this prompt pack together with:

- `docs/dev/NICEGUI_STABILIZATION_PASS.md`

## Scope Rules

This is a hardening sprint, not a redesign sprint.

Keep the scope to:

- lazy page loading and startup responsiveness
- shared job/progress runtime
- `Settings` migration first
- `Library`, `Cues`, and `Discover` migration after that
- launch/session hygiene only if it stays narrow

Do not add feature work or visual redesign.
