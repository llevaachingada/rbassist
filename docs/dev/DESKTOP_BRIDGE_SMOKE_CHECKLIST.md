# Desktop Bridge Smoke Checklist

Use this after a bridge slice to make sure the existing NiceGUI GUI still works and the read-only desktop shell stays safe.

## Before You Start

- stay on the feature branch
- do not edit `data/meta.json`, `data/runlogs`, backups, or archives during smoke
- use the current NiceGUI GUI as the source of truth for writes
- use the desktop shell only for read-only proof of life

## NiceGUI Smoke

1. Start the current NiceGUI app the normal way.
2. Open `Discover`, `Library`, and `Cues`.
3. Confirm each page loads without the reconnect loop or blank shell behavior.
4. Trigger one small action in each area, but only if it is already part of the existing workflow.
5. Confirm the UI stays responsive while jobs run and the status area keeps updating.
6. Reload the page once during an active job and confirm the job status reattaches instead of disappearing.

## Desktop Shell Smoke

1. Start the read-only desktop preview only if `PySide6` is installed.
2. Confirm the window opens with the overview counts visible.
3. Confirm the Library tab shows a read-only preview table.
4. Confirm the Discover tab shows a read-only placeholder, not a live write workflow.
5. Close and reopen the window once to confirm startup is stable.
6. Confirm the shell never writes to `data/meta.json`.

## Stop Conditions

- if the NiceGUI GUI crashes, stop and investigate before continuing the bridge slice
- if the desktop shell tries to write metadata, stop immediately
- if a slice changes the public workflow shape in NiceGUI, note it in the continuity log before moving on
