# Desktop GUI Migration Contract

## Purpose

This document defines the bridge contract between rbassist's backend workflows and any future non-NiceGUI frontend.

The goal is to let us chip away at a real Windows GUI without breaking the current NiceGUI app.

## Strategy

Use an additive bridge:

- keep `rbassist/ui/` as the current working NiceGUI frontend
- add `rbassist/ui_services/` for GUI-neutral view models and orchestration seams
- add `rbassist/runtime/` for shared non-GUI runtime state such as job snapshots
- add `rbassist/desktop/` only for small read-only desktop proof-of-life spikes
- move one page-owned workflow at a time into `ui_services`

Do not fork the repo for this work. Use a `codex/` branch and keep slices small.

## Guardrails

- `rbassist/ui_services/` must not import NiceGUI.
- `rbassist/ui_services/` must not import PySide.
- `rbassist/runtime/` must not import NiceGUI or PySide.
- `rbassist/desktop/` must not mutate `data/meta.json` in proof-of-life mode.
- Keep NiceGUI behavior working after every slice.
- Avoid schema changes to `data/meta.json`.
- Prefer plain dataclasses, dictionaries, and lists as service return values.
- Preserve read-only Rekordbox defaults unless a later plan explicitly approves writes.

## Current Frontend Surfaces

### Discover

Inputs:

- seed track path
- metadata dictionary
- filters
- weights
- HNSW index path and `paths.json`

Outputs:

- recommendation rows
- library browse rows
- row detail text
- refresh state decisions

Bridge service target:

- `rbassist/ui_services/discover.py`

### Library

Inputs:

- metadata dictionary
- optional row limit

Outputs:

- summary counts
- preview rows
- health table rows
- issue counts and flags

Bridge service target:

- `rbassist/ui_services/library.py`

### Jobs

Inputs:

- generic job-like snapshot

Outputs:

- UI-neutral status text
- busy flag
- job view dictionary

Bridge service target:

- `rbassist/ui_services/jobs.py`
- `rbassist/runtime/jobs.py` owns the actual shared job registry
- `rbassist/ui/jobs.py` remains a compatibility export for the current NiceGUI pages

### Cues

Inputs:

- metadata dictionary
- selected paths
- overwrite flag
- job-like snapshots

Outputs:

- cue batch target plan
- progress panel view model
- recent-job history text

Bridge service target:

- `rbassist/ui_services/cues.py`

### Settings

Inputs:

- folder path text
- pipeline counts and options
- job-like snapshots

Outputs:

- parsed folder path list
- preflight and running status text
- pipeline result payload
- progress panel view model

Bridge service target:

- `rbassist/ui_services/settings.py`

### Desktop Proof Of Life

Inputs:

- local `data/meta.json`
- optional preview row limit

Outputs:

- read-only desktop overview
- small table preview
- read-only Overview / Library / Discover preview tabs
- shared job status summary
- read-only Library health issue summary
- Discover readiness message based on read-only library counts
- no writes

Bridge target:

- `rbassist/desktop/app.py`

## First Safe Extraction

The first extraction should be `Discover`, because it is user-visible and expensive but can be kept read-only.

Minimum safe first extraction:

- recommendation row computation
- library browse row shaping
- detail text generation
- latest-request helper decisions

NiceGUI should still own:

- widgets
- notifications
- table updates
- async task scheduling

## Desktop Proof-Of-Life Scope

The first desktop proof-of-life should only:

- open a PySide window if PySide6 is installed
- show total track count
- show embedded count
- show a small read-only preview table
- display a clear message if PySide6 is not installed

It must not:

- write metadata
- access Rekordbox DB
- run embed/analyze/index
- attempt feature parity

## Done Criteria For This Bridge Slice

- NiceGUI `Discover` still imports and compiles.
- `ui_services` tests pass without NiceGUI.
- desktop proof-of-life imports without PySide6 installed.
- PySide6 is optional.
- no `data/` files are touched.

## Service Extraction Checklist

Every new page extraction should keep this shape:

- move pure row shaping, label text, count summaries, target planning, and status view models into `rbassist/ui_services/`
- keep NiceGUI widgets, notifications, async task scheduling, and explicit write actions inside `rbassist/ui/`
- return plain dataclasses, lists, dictionaries, and strings from service helpers
- add focused tests that import the service without importing NiceGUI or PySide
- add at least one page-level test or delegation test when page behavior changes
- run `python -m compileall` for touched packages and focused `pytest` for touched tests

## Bridge Progress

As of 2026-04-12:

- `Discover` delegates recommendation rows, library browse rows, row detail text, and refresh helper decisions to `rbassist/ui_services/discover.py`.
- `Library` delegates health table row modeling and issue counts to `rbassist/ui_services/library.py`.
- `Cues` delegates target planning and progress/status view modeling to `rbassist/ui_services/cues.py`.
- `Settings` delegates folder input parsing, pipeline preflight/status text, result payload shaping, and progress panel view modeling to `rbassist/ui_services/settings.py`.
- shared job snapshots live in `rbassist/runtime/jobs.py`, with `rbassist/ui/jobs.py` kept as a compatibility export.
- `rbassist/ui/__init__.py` lazily exposes `run` and `main` so importing `rbassist.ui.jobs` no longer loads the NiceGUI app.
- `rbassist/desktop/app.py` is a read-only shell with Overview, shared job summary, Library preview plus health issue summary, and Discover readiness tabs.
