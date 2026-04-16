# NiceGUI Stabilization Smoke Checklist

## Purpose

Use this checklist after the NiceGUI stabilization slices land.

The goal is to decide whether the bridge hardening is good enough to stop coding on NiceGUI and move toward launch/session hygiene or the future non-NiceGUI frontend path.

This is a manual browser smoke checklist. It is not a request for more NiceGUI feature work.

## Before Starting

1. Confirm focused validation passes:

   ```powershell
   python -m compileall rbassist\ui
   pytest -q tests/test_ui_app.py tests/test_ui_state.py tests/test_ui_components.py tests/test_ui_jobs.py tests/test_ui_discover.py tests/test_recommend_index.py
   ```

2. Start the app:

   ```powershell
   rbassist ui
   ```

3. Use the current configured music folders unless the test needs a small explicit folder.

## Go / No-Go Rules

Go if:

- the shell opens quickly enough to feel responsive
- tabs load lazily without obvious blank or broken states
- shared job status updates while long jobs run
- refreshing or reconnecting does not lose the logical active job
- `Discover` does not freeze during rapid seed/filter changes

No-go if:

- the browser repeatedly shows "lost connection / reconnecting" during ordinary local use
- a running job disappears from both shell and page-level status after reload
- rapid `Discover` changes spawn visible stale result flips or leave the page stuck busy
- one page failure takes down the rest of the app
- a second launch or stuck port blocks the operator with unclear recovery

## Smoke 1: Shell Startup and Lazy Loading

Steps:

1. Launch `rbassist ui`.
2. Watch initial shell load.
3. Click each tab once: `Discover`, `Crate Expander`, `Library`, `Tags`, `AI Tags`, `Cues`, `Tools`, `Settings`.
4. Return to `Discover` and `Settings`.

Expected:

- tabs and bottom status bar appear before heavy page work
- each page loads on first activation
- already-loaded tabs do not re-run expensive startup work unnecessarily
- one slow page does not make the whole shell feel dead

Pass / fail:

- Pass:
- Fail notes:

## Smoke 2: Settings Pipeline Job State

Use the smallest safe target available. Prefer a tiny test folder or paths file if one exists.

Steps:

1. Open `Settings`.
2. Start `Process configured folders` or `Process paths file`.
3. Confirm the page-level pipeline status updates with phase and progress.
4. Confirm the bottom status bar updates with the active job message.
5. Reload the browser page while the job is active, or open a second browser tab to the same URL.
6. Return to `Settings`.

Expected:

- the pipeline does not freeze the UI
- the page panel reattaches to the active `settings_pipeline` job
- the bottom status bar still shows active job state
- completion or failure is visible and understandable

Pass / fail:

- Pass:
- Fail notes:

## Smoke 3: Library Beatgrid Job State

Use one file or the smallest safe folder target.

Steps:

1. Open `Library`.
2. Start a beatgrid single-file run or a very small batch.
3. Confirm page-level beatgrid progress appears.
4. Confirm the bottom status bar reflects the active job.
5. Reload or switch away and back during the run.

Expected:

- beatgrid work does not freeze the page
- page panel reattaches to the active `library_beatgrid` job
- completion or failure is visible

Pass / fail:

- Pass:
- Fail notes:

## Smoke 4: Cues Job State

Use one file or the smallest safe folder target.

Steps:

1. Open `Cues`.
2. Start cue generation for a single file or small folder.
3. Confirm page-level cue progress appears.
4. Confirm the bottom status bar reflects the active job.
5. Reload or switch away and back during the run.

Expected:

- cue generation does not freeze the page
- page panel reattaches to the active `cues_generation` job
- completion or failure is visible

Pass / fail:

- Pass:
- Fail notes:

## Smoke 5: Discover Rapid Refresh Coalescing

Steps:

1. Open `Discover`.
2. Select a seed track.
3. Change filters rapidly several times.
4. Change seed or use a result as the next seed quickly.
5. Watch the table, refresh status, and bottom status bar.

Expected:

- the UI stays responsive while ranking runs
- the refresh button and status do not get stuck busy
- stale result sets do not land after a newer seed/filter request
- the latest request wins
- no repeated reconnect banner appears during ordinary local use

Pass / fail:

- Pass:
- Fail notes:

## Smoke 6: Second Launch / Port Behavior

Run this only after the main UI smoke checks, because launch/session hygiene may still be a follow-up slice.

Steps:

1. Leave `rbassist ui` running.
2. Start `rbassist ui` again in a second terminal.
3. Observe the terminal and browser behavior.

Expected:

- if second launch is not yet hardened, record the exact failure
- operator recovery should be clear enough to decide whether `start.ps1` / `cli.py` needs the launch hygiene slice

Pass / fail:

- Pass:
- Fail notes:

## Decision

Choose one:

- Go: current NiceGUI bridge hardening is good enough; stop NiceGUI stabilization work and move toward desktop migration prep.
- Follow-up: do one narrow launch/session hygiene slice in `start.ps1` and `rbassist/cli.py`.
- Fix: address a specific blocking regression found above, then rerun only the failed smoke.

Decision:

Notes:

