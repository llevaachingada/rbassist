# Continuity Log

## How To Use
- Append a new dated entry for every meaningful work session.
- Keep each entry short and operational: what changed, what was learned, what remains next.
- Update `docs/dev/PROJECT_CONTINUITY.md` when the north-star truth changes.

## Entry Template
### YYYY-MM-DD
- Goal:
- Changes made:
- Evidence / outputs:
- Current blockers or risks:
- Next recommended step:

## Entries
### 2026-03-02
- Goal: Preserve continuity for post-ingest rbassist work so future agents can pick up without re-reading the full chat history.
- Changes made: Added `docs/dev/PROJECT_CONTINUITY.md` as a stable mission-and-state brief, and added this rolling continuity log.
- Evidence / outputs: active-root ingest is caught up under `C:\Users\hunte\Music` excluding quarantine; analyze and index have completed; remaining work is metadata hygiene plus Rekordbox reconciliation.
- Current blockers or risks: global `meta.json` still contains `2511` stale paths and `1457` bare/orphan paths; Rekordbox relink tooling is still read-only / review-first.
- Next recommended step: implement the root-first stale cleanup and bare/orphan review flow, then build the backup-first Rekordbox apply-plan tooling.

### 2026-03-02
- Goal: Add a reusable keeper manifest for the four active post-ingest rbassist workstreams.
- Changes made: Added `rbassist/keeper_manifest.py`, `scripts/build_keeper_manifest.py`, and generated `docs/dev/KEEPER_MANIFEST_ACTIVE_FILES.md` plus `docs/dev/keeper_manifest_active_files.json`.
- Evidence / outputs: The generated manifest now captures shared foundations, workstream-specific keeper files, local runtime keepers, and a lightweight live-state summary.
- Current blockers or risks: The manifest is a curated map, not an automatic dependency graph; it should be refreshed when the active workstream files or priorities change.
- Next recommended step: use the manifest while implementing stale cleanup and Rekordbox apply-ready tooling, and update it when new keeper files become central.

### 2026-03-02
- Goal: Implement root-first stale-path triage and backup-first stale cleanup.
- Changes made: Added `triage_stale_meta_paths` and `apply_stale_meta_cleanup` in `rbassist/health.py`; added `scripts/triage_stale_meta_paths.py` and `scripts/apply_stale_meta_cleanup.py`; extended `scripts/audit_meta_health.py` to emit stale-triage counts; added focused tests for triage and apply behavior.
- Evidence / outputs: `8` focused tests passed. Generated `docs/dev/stale_meta_triage_2026-03-02.json`, `docs/dev/stale_meta_cleanup_apply_2026-03-02.json`, `docs/dev/health_audit_with_stale_triage_2026-03-02.json`, and `docs/dev/health_audit_after_stale_cleanup_2026-03-02.json`.
- Current blockers or risks: once the Rekordbox audit report is included, the two outside-root rows that looked archive-safe in a root-only dry run are no longer removable because Rekordbox still references them.
- Next recommended step: implement the richer bare/orphan review and safe-apply flow next, then build Rekordbox apply-plan tooling for the remaining outside-root and inside-root relink candidates.

### 2026-03-02
- Goal: Turn the remaining wishlist into a practical execution sequence instead of a loose backlog.
- Changes made: Added `docs/dev/MASTER_PRODUCT_EXECUTION_PLAN_2026-03-02.md` covering the seven major workstreams in winning order, with outcomes, file targets, acceptance criteria, and immediate next slices.
- Evidence / outputs: The master execution plan now aligns the post-ingest roadmap around metadata truth first, then Rekordbox-safe repair, then duplicate remediation, rollout QA, BPM separation, UI gaps, and benchmarks.
- Current blockers or risks: the plan is broad, so execution discipline matters; backend truth and safety work still need to stay ahead of UI polish.
- Next recommended step: commit the current stale-path hygiene batch, then finish the richer bare/orphan review and safe-apply flow.

### 2026-03-02
- Goal: Begin the richer bare/orphan review and safe-apply flow.
- Changes made: Upgraded `resolve_bare_meta_paths` in `rbassist/health.py` to emit confidence-scored classifications (`high_confidence_unique`, `medium_confidence_unique`, `ambiguous`, `not_found`), candidate details, and strict high-confidence-only apply behavior. Updated `scripts/resolve_bare_meta_paths.py` to support `--min-confidence`, JSON output, and CSV review output.
- Evidence / outputs: Focused suite passed (`6 passed`). Generated `docs/dev/bare_meta_resolution_2026-03-02.json` and `docs/dev/bare_meta_resolution_2026-03-02.csv`.
- Current blockers or risks: bare-path ambiguity is still high because many filenames appear multiple times under the active root.
- Next recommended step: build an apply-safe pass for the high-confidence bare matches and then feed the large ambiguous set into duplicate/remediation and Rekordbox-safe relink planning.
### 2026-03-02
- Goal: Push the NiceGUI surface closer to completion with a focused library/tagging usability pass.
- Changes made: Made
bassist/ui/state.py root-aware for health refreshes, expanded
bassist/ui/components/health_summary.py with scope-aware counts, upgraded
bassist/ui/components/track_table.py with stronger pagination defaults, added quick issue filters plus fixed-fallback beatgrid actions in
bassist/ui/pages/library.py, improved in-app suggestion preview controls in
bassist/ui/pages/tagging.py, and cleaned up the instructions/review text in
bassist/ui/pages/ai_tagging.py.
- Evidence / outputs: python -m compileall passed for the touched UI files, and pytest -q tests/test_ui_state.py tests/test_resolve_bare_meta_paths.py passed (5 passed).
- Current blockers or risks: docs/design/spec_1_rbassist_local_ai_dj_toolkit_architecture.md is still an unrelated tracked change and remains intentionally untouched. The richer bare/orphan resolver work is still uncommitted local work alongside this GUI batch.
- Next recommended step: either commit just the GUI + bare/orphan files together, or continue into the next UI completion slice for beatgrid review polish, tags workflow depth, and large-library table ergonomics.

### 2026-03-24
- Goal: Formalize a two-lane Codex workflow that fits rbassist's mix of discovery work and hardening work.
- Changes made: Updated `AGENTS.md` with discovery vs hardening lane rules, added `docs/dev/AGENT_WORKFLOW_LANES.md`, tightened `.codex/agents/*.toml` around lane handoffs, and added minimal shared agent limits in `.codex/config.toml`.
- Evidence / outputs: the repo workflow now distinguishes discovery (`researcher` -> `feature-planner`) from hardening (`researcher` -> narrow implementer -> `integration-regression-reviewer`) while keeping one shared truth layer in the existing continuity docs and roadmap.
- Current blockers or risks: process overhead is still a risk if future work routes every task through discovery; clear bug fixes and obvious follow-up slices should still skip directly to hardening.
- Next recommended step: use discovery for underdefined wishlist work such as BPM/Rekordbox separation refinements, and use hardening directly for scoped regressions, polish, and approved follow-up slices.

### 2026-03-24
- Goal: Add a read-only Rekordbox playlist expansion flow that turns an existing crate into a larger DJ-ready crate by appending vibe-matched tracks.
- Changes made: Added `rbassist/playlist_expand.py` with Rekordbox DB/XML/manual playlist loading, seed-to-meta path matching, deterministic centroid/coverage candidate ranking, and diversity reranking; wired `rbassist playlist-expand` into `rbassist/cli.py`; added focused coverage in `tests/test_playlist_expand.py`; updated `README.md` to document the new workflow.
- Evidence / outputs: `tests/test_playlist_expand.py` passed (`9 passed`); `python -m compileall rbassist\playlist_expand.py rbassist\cli.py` passed; live DB smoke expansion for `DarkMoon` succeeded with `26` mapped seeds expanded to `30` total, writing preview JSON and Rekordbox XML to temp files.
- Current blockers or risks: XML fallback and manual seed paths are implemented but less battle-tested than the direct DB path; ambiguous Rekordbox playlist names now fail closed, which is safer but means users may need to provide a fuller playlist path.
- Next recommended step: add a UI entry point for crate expansion and a small CLI/help polish pass now that the backend, export flow, and smoke validation are in place.

### 2026-03-24
- Goal: Turn the playlist-expansion pilot into a shared preset/slider workflow across backend, CLI, and the crate-expander UI.
- Changes made: Extended `rbassist/playlist_expand.py` with `tight` / `balanced` / `adventurous` presets, cached `prepare_playlist_expansion(...)` and `rerank_playlist_expansion(...)` flows, `blend` strategy support, richer component scores and diagnostics, and backward-friendly `expand_playlist(...)`; updated `rbassist/cli.py` to expose preset, strategy, key-mode, and advanced weight overrides on `rbassist playlist-expand`; replaced the local scoring path in `rbassist/ui/pages/crate_expander.py` with the shared backend plus preset toggles, advanced controls, and cached reranking; refreshed `README.md`; expanded `tests/test_playlist_expand.py`.
- Evidence / outputs: `tests/test_playlist_expand.py` passed (`11 passed`); `python -m compileall rbassist\playlist_expand.py rbassist\cli.py rbassist\ui\pages\crate_expander.py` passed; `python -m py_compile rbassist\ui\pages\crate_expander.py` passed; live CLI smoke on March 24, 2026 succeeded for `DarkMoon` with `--mode adventurous --strategy blend --key-mode soft --w-tags 0.2`, producing preview JSON and Rekordbox XML in the temp directory and confirming `controls_applied` plus per-track `component_scores`.
- Current blockers or risks: the NiceGUI crate page has compile/import validation but still needs an in-browser smoke check for interaction feel; true section-aware or transition-aware set building is still deferred; tag-heavy modes will be weaker on sparse-tag playlists.
- Next recommended step: do one live NiceGUI smoke pass on the Crate Expander tab, then decide whether to persist crate-expansion UI controls in feature-scoped app state or keep them page-local.

### 2026-03-24
- Goal: Close the non-browser follow-up after the playlist-expansion rollout and explicitly track the next playlist-design step.
- Changes made: added section-aware / transition-aware crate expansion as a follow-up item in `WISHLIST.md`; attempted a browser smoke path for the Crate Expander tab, but stopped it after the local Playwright/npm toolchain proved unreliable on this machine.
- Evidence / outputs: the real product validation remains the passing CLI smoke plus focused Python checks; manual browser smoke is intentionally deferred to the operator for this environment.
- Current blockers or risks: the Playwright CLI bootstrap path is not trustworthy here, so browser-end verification is now a manual step instead of an automated one.
- Next recommended step: manually open the Crate Expander tab, confirm seed search -> generate/rerank -> preset/slider updates behave correctly, then decide whether section-aware or transition-aware expansion should become the next discovery slice.

### 2026-03-24
- Goal: Close the remaining UI workflow gap so the Crate Expander can start from an existing Rekordbox playlist instead of manual seeds only.
- Changes made: added `list_rekordbox_playlists(...)` to `rbassist/playlist_expand.py`; updated `rbassist/ui/pages/crate_expander.py` to browse Rekordbox DB/XML playlists, load a selected playlist into the seed set, and then use the same shared prepare/rerank backend as before; expanded `tests/test_playlist_expand.py` with playlist-listing coverage; refreshed `README.md`.
- Evidence / outputs: `tests/test_playlist_expand.py` passed (`13 passed`); `python -m py_compile rbassist\playlist_expand.py rbassist\ui\pages\crate_expander.py` passed; `python -m compileall rbassist\playlist_expand.py rbassist\ui\pages\crate_expander.py` passed.
- Current blockers or risks: browser-end interaction is still awaiting manual confirmation in this environment, and XML playlist browsing requires an explicit XML path in the UI.
- Next recommended step: manually verify the Crate Expander flow of Refresh playlists -> choose Rekordbox playlist -> Load Playlist As Seeds -> Generate / Rerank.

### 2026-03-24
- Goal: Tighten crate expansion around real DJ crate-building workflows without reopening the scoring architecture.
- Changes made: used discovery-plus-hardening agents plus targeted workflow research to identify two safe follow-ups; updated `rbassist/ui/pages/crate_expander.py` with one-click role-tag lane buttons (`Warm-up`, `Opener`, `Tool`, `Peak-time`, `Closer`) that feed the existing required-tag filter, and updated `rbassist/playlist_expand.py` to apply a deterministic anti-repetition penalty for same-artist / same-title-stem / same-version clustering while preserving read-only Rekordbox behavior; refreshed `README.md`; extended `tests/test_playlist_expand.py`.
- Evidence / outputs: `.venv\Scripts\python.exe -m pytest tests/test_playlist_expand.py` passed (`14 passed`); `.venv\Scripts\python.exe -m py_compile rbassist\playlist_expand.py rbassist\ui\pages\crate_expander.py` passed; `.venv\Scripts\python.exe -m compileall rbassist\playlist_expand.py rbassist\ui\pages\crate_expander.py` passed.
- Current blockers or risks: anti-repetition is still heuristic and metadata-dependent, so sparse or inconsistent artist/title fields will weaken it; section-aware or transition-aware set building remains deferred to a later discovery slice.
- Next recommended step: manually check the Crate Expander lane buttons against real-tagged playlists, then decide whether the next workflow slice should be a “why this track” explainer panel or a section-aware / transition-aware pilot.

### 2026-03-24
- Goal: Make recommendation and crate-expansion UI language understandable to normal users without changing ranking behavior.
- Changes made: used the repo's discovery-plus-hardening agent workflow to relabel confusing recommendation and crate-expander columns, add compact “How this works” guidance on both pages, upgrade row-click explanations from minimal toasts into persistent detail panels, and clarify recommendation filter wording in `rbassist/ui/pages/discover.py`, `rbassist/ui/pages/crate_expander.py`, and `rbassist/ui/components/filters.py`; tightened Discover mode-switch and sort behavior so recommendation-only columns do not sit on top of plain library rows.
- Evidence / outputs: `.venv\Scripts\python.exe -m py_compile rbassist\ui\pages\discover.py rbassist\ui\pages\crate_expander.py rbassist\ui\components\filters.py rbassist\ui\components\track_table.py` passed; `.venv\Scripts\python.exe -m compileall rbassist\ui\pages\discover.py rbassist\ui\pages\crate_expander.py rbassist\ui\components\filters.py rbassist\ui\components\track_table.py` passed; high-effort regression reviewer finished with no findings after the final fixes.
- Current blockers or risks: validation for this slice is still code-based; the remaining gap is manual NiceGUI browser smoke for the updated sort behavior, mode switching, and detail panels.
- Next recommended step: manually click through Discover and Crate Expander, then decide whether the next follow-up should be a deeper recommendation detail panel or a section-aware / transition-aware crate-expansion discovery thread.

### 2026-03-30
- Goal: Capture a bridge plan for stabilizing the current NiceGUI app without deepening long-term framework lock-in.
- Changes made: added `docs/dev/NICEGUI_STABILIZATION_PASS.md` with a one-to-two week hardening plan centered on lazy page loading, a shared UI job/runtime layer, `Settings` pipeline migration first, then `Library`/`Cues`/`Discover`, plus launch/session hygiene and focused validation.
- Evidence / outputs: the plan now records concrete file targets, acceptance criteria, deferrals, agent lanes, and validation commands for a short stabilization sprint that also creates seams for a later non-NiceGUI desktop UI.
- Current blockers or risks: the plan is intentionally a hardening bridge, not a desktop migration; value depends on keeping scope tight and refusing NiceGUI-only polish that does not reduce flakiness or create reusable seams.
- Next recommended step: start the first slice in `rbassist/ui/app.py`, add a shared `rbassist/ui/jobs.py` or `rbassist/ui/runtime.py`, then migrate `rbassist/ui/pages/settings.py` onto shared job state before touching lower-priority pages.

### 2026-03-30
- Goal: Make the NiceGUI stabilization sprint easy to execute in a controller-plus-workers pattern without relying on one giant self-splitting prompt.
- Changes made: added `docs/dev/prompts/nicegui_stabilization/` with `README.md`, `controller.md`, `worker_ui_shell.md`, `worker_job_runtime.md`, `worker_library_cues_discover.md`, and `worker_reviewer.md`.
- Evidence / outputs: the repo now has copy-pasteable prompt files for a single controller thread that points to narrow worker threads with clear ownership and validation expectations.
- Current blockers or risks: the prompt pack only helps if workers keep their file scopes narrow and avoid reopening product design or feature work during hardening.
- Next recommended step: start one controller thread from `docs/dev/prompts/nicegui_stabilization/controller.md`, then launch worker threads from the remaining prompt files in the order described by the pack `README.md`.

### 2026-04-12
- Goal: Add a concrete manual go/no-go checklist for the NiceGUI stabilization bridge after shared job runtime follow-ups.
- Changes made: added `docs/dev/NICEGUI_STABILIZATION_SMOKE_CHECKLIST.md` covering shell lazy-load smoke, `Settings` pipeline job reattach, `Library` beatgrid job reattach, `Cues` job reattach, rapid `Discover` refresh coalescing, and second-launch/port behavior.
- Evidence / outputs: the checklist gives future operators and agents a focused manual validation path before deciding whether to stop NiceGUI hardening or do one narrow launch/session hygiene follow-up.
- Current blockers or risks: the checklist is manual by design; it does not replace browser-end validation or resolve unrelated dirty worktree drift.
- Next recommended step: run the checklist in a browser, record pass/fail notes, then either stop NiceGUI stabilization or do only the launch/session hygiene slice in `start.ps1` and `rbassist/cli.py`.

### 2026-03-30
- Goal: Capture crate-expander performance findings and preserve the next optimization slices for a future hardening pass.
- Changes made: benchmarked real playlist expansion at `candidate_pool=1000` vs `2000` using `2024 Novemebr DLs` (`50` mapped/embedded seeds, target total `100`), profiled the hot path in `rbassist/playlist_expand.py`, and added a dedicated performance backlog note to `WISHLIST.md`.
- Evidence / outputs: library snapshot during benchmarking was `13332` tracks with `10008` embeddings; warm benchmark runs were `10.874s` at `1000` and `17.270s` at `2000`, with both runs filling from `50` to `100`; cold multi-run averages were `21.801s` at `1000` and `33.958s` at `2000`; cProfile showed the biggest costs in repeated cosine-similarity math, repeated HNSW/index-path loading, alias-index rebuilding, and repeat-signature text processing.
- Current blockers or risks: the current crate-expansion path is CPU-bound and does not expose a worker knob; widening the candidate pool improves coverage but can substantially increase rerank cost; GPU/CUDA is relevant to embed/analyze paths in the repo but not to the current playlist-expansion path.
- Next recommended step: implement the first ROI slice by caching the HNSW index, `paths.json`, and alias/meta resolution across expansion runs, then do a second slice that pre-normalizes vectors and precomputes repeat signatures before considering worker-parallel coverage queries.

### 2026-03-30
- Goal: Close the remaining crate-expander workflow gap by letting the GUI save an expansion in a Rekordbox-importable format.
- Changes made: updated `rbassist/ui/pages/crate_expander.py` to add a `Save Rekordbox Playlist XML` action, clear copy that the export is a playlist XML file only and does not overwrite the Rekordbox library, a default export folder under `exports/crate_expander`, and post-save folder opening so the saved XML can be dragged into Rekordbox; refreshed `README.md`.
- Evidence / outputs: the UI now has an end-to-end save path from generated expansion result to XML export location without requiring the CLI; the export path reuses the existing `write_expansion_xml(...)` backend.
- Current blockers or risks: the GUI still exports via XML rather than writing directly into the Rekordbox DB, which is safer but still requires a manual import/drag-drop step inside Rekordbox.
- Next recommended step: validate the new save action in the browser, then decide whether the follow-up should be a user-editable export filename/path or keeping the current timestamped safe default.

### 2026-03-30
- Goal: Land the NiceGUI stabilization hardening pass for shell startup, shared job runtime, batch job responsiveness, and non-blocking recommendation refresh.
- Changes made: moved the app shell to lazy page loading with per-page fallback isolation; added a shared `rbassist/ui/jobs.py` job registry plus shell/runtime binding in `rbassist/ui/components/progress.py`; migrated `rbassist/ui/pages/settings.py`, `rbassist/ui/pages/library.py`, and `rbassist/ui/pages/cues.py` off background widget mutation for long-running flows; made `rbassist/ui/pages/discover.py` refresh recommendations through an async latest-request-wins path; added focused UI regression tests including `tests/test_ui_jobs.py` and `tests/test_ui_discover.py`; removed eager `refresh_health()` from `rbassist/ui/state.py` import-time startup.
- Evidence / outputs: `python -m compileall rbassist\ui` passed; `pytest -q tests/test_ui_app.py tests/test_ui_state.py tests/test_ui_components.py tests/test_ui_jobs.py tests/test_ui_discover.py tests/test_recommend_index.py` passed (`19 passed`).
- Current blockers or risks: validation is still code-based, not a live NiceGUI browser smoke; launch/session hygiene in `start.ps1` and `rbassist/cli.py` is still a follow-up if second-launch or occupied-port friction remains; recommendation refresh is now non-blocking and latest-request-wins, but manual interaction smoke should still confirm button/seed/filter feel in-browser.
- Next recommended step: do one manual browser smoke for shell startup, Settings batch progress, one beatgrid batch, one cue batch, and one rapid seed/filter change in Discover; if launch friction still shows up, take a narrow follow-up slice in `start.ps1` and `rbassist/cli.py`.

### 2026-03-30
- Goal: Make recommendation and crate-expander tempo handling Rekordbox-first without losing RB Assist analysis context.
- Changes made: added shared BPM-source helpers in `rbassist/bpm_sources.py`; updated `rbassist/playlist_expand.py` to prefer Rekordbox BPM for seed and candidate tempo logic while carrying `rbassist_bpm`, `rekordbox_bpm`, mismatch delta, and source metadata forward; updated `rbassist/ui/pages/discover.py`, `rbassist/ui/pages/crate_expander.py`, and `rbassist/ui/components/seed_card.py` to display both BPMs, label the effective source, and flag large mismatches; refreshed `rbassist/ui/state.py` to clear the Rekordbox BPM cache on meta refresh.
- Evidence / outputs: `.venv\Scripts\python.exe -m pytest tests\test_bpm_sources.py tests\test_playlist_expand.py tests\test_ui_discover.py` passed (`19 passed`); `.venv\Scripts\python.exe -m compileall rbassist` passed.
- Current blockers or risks: this slice is still read-only against Rekordbox and treats live DB BPM as the truth only for runtime ranking/display; manual NiceGUI smoke is still needed to confirm the new columns and detail text feel right in Discover and Crate Expander.
- Next recommended step: smoke-test Discover and Crate Expander in the browser against known mismatch tracks, then decide whether the follow-up should be a dedicated BPM mismatch filter/report or extending the same Rekordbox-first tempo policy into CLI recommendation output.

### 2026-03-30
- Goal: Close the remaining NiceGUI stabilization follow-up gaps around recommendation refresh coalescing and page-level job reattachment after reload/reconnect.
- Changes made: added active-job resolution in `rbassist/ui/jobs.py`; updated `rbassist/ui/pages/settings.py`, `rbassist/ui/pages/library.py`, and `rbassist/ui/pages/cues.py` to reattach their progress panels from `latest_job(kind=...)` when the local page job id is missing; tightened `rbassist/ui/pages/discover.py` around a single in-flight refresh task with explicit drain-loop helper checks; extended `tests/test_ui_jobs.py` and `tests/test_ui_discover.py`.
- Evidence / outputs: `python -m compileall rbassist\ui` passed; `pytest -q tests/test_ui_app.py tests/test_ui_state.py tests/test_ui_components.py tests/test_ui_jobs.py tests/test_ui_discover.py tests/test_recommend_index.py` passed (`23 passed`).
- Current blockers or risks: the recommendation work is now coalesced to one active task rather than truly cancelled mid-query; manual NiceGUI smoke is still needed to confirm page panels visibly reattach after a reload and that rapid Discover changes feel calm in-browser.
- Next recommended step: do one browser smoke focused on reloading `Settings`, `Library`, and `Cues` during active jobs plus a rapid seed/filter change pass in `Discover`, then move to launch/session hygiene only if startup friction remains.

### 2026-03-30
- Goal: Close the Crate Expander reconnect failure exposed by the BPM/UI browser smoke and record the remaining follow-up cleanly.
- Changes made: updated `rbassist/ui/pages/crate_expander.py` so Rekordbox playlist refresh/load runs through `asyncio.to_thread(...)` instead of blocking the NiceGUI event loop; moved the initial playlist refresh onto `nicegui.background_tasks.create(...)` so the first render does not spawn an un-awaited coroutine; kept UI notifications and widget updates on the main task; added focused async regression coverage in `tests/test_ui_crate_expander.py`.
- Evidence / outputs: `.venv\Scripts\python.exe -m pytest tests/test_ui_crate_expander.py tests/test_ui_discover.py tests/test_playlist_expand.py tests/test_bpm_sources.py` passed (`23 passed`); `.venv\Scripts\python.exe -m compileall rbassist` passed. Focused browser smoke on Crate Expander no longer showed `Connection lost. Trying to reconnect...`; `Refresh` completed and surfaced `Loaded 352 Rekordbox playlists`.
- Current blockers or risks: the websocket/reconnect failure appears fixed, but the next step in the same smoke still failed at playlist loading with `Failed to load Rekordbox playlist: Playlist not found for source 'db': 135-165 last year 4 stars`. That points to playlist identifier resolution after refresh/load rather than the original UI-thread stall.
- Next recommended step: trace how Crate Expander stores the selected playlist value versus what `load_rekordbox_playlist(...)` expects for Rekordbox DB sources, then add a focused regression test for the selected value shape before changing the loader contract.

### 2026-03-31
- Goal: Create a handoff-grade technical context document for the analysis/recommendation platform so a follow-on agent can evaluate mathematical optimality.
- Changes made: Added `docs/dev/ANALYSIS_RECOMMENDATION_PLATFORM_CONTEXT_2026-03-31.md` with holistic workflow mapping (embed/analyze/index/recommend/playlist-expand), explicit current objective functions, known mathematical limits, and a staged evaluation roadmap.
- Evidence / outputs: New context document includes immediate low-risk experimentation slices (telemetry, benchmark harness, component normalization, hard-filter vs soft-penalty evaluation) aligned with existing safety constraints.
- Current blockers or risks: The repo still lacks a standardized offline ranking benchmark and explicit relevance labels, so claims of "mathematically best" remain untestable until instrumentation/benchmarking is added.
- Next recommended step: implement ranking telemetry and an offline benchmark CLI, then compare baseline presets against calibrated rerank variants on a fixed labeled seed set.

### 2026-04-12
- Goal: Start the non-NiceGUI desktop migration safely without forking or breaking the current NiceGUI shell.
- Changes made: added `docs/dev/DESKTOP_GUI_MIGRATION_CONTRACT.md`; introduced GUI-neutral `rbassist/ui_services/` seams for Discover recommendation rows, library snapshots, and job display models; rewired `rbassist/ui/pages/discover.py` to delegate ranking, library-row shaping, and detail text to the service layer while preserving NiceGUI-owned widgets and async refresh scheduling; added the optional read-only PySide proof-of-life in `rbassist/desktop/app.py`; exposed a `desktop` extra and `rbassist-desktop-preview` script; added focused service and delegation tests.
- Evidence / outputs: `python -m compileall rbassist\ui_services rbassist\desktop rbassist\ui\pages\discover.py` passed; `pytest -q tests/test_ui_services.py tests/test_ui_discover.py tests/test_ui_app.py tests/test_ui_state.py tests/test_ui_components.py tests/test_ui_jobs.py tests/test_recommend_index.py` passed (`31 passed`); two subagent reviews found no blocking issues and called out the remaining `rbassist/ui/__init__.py` NiceGUI import coupling as a later seam.
- Current blockers or risks: the desktop preview is intentionally read-only and not feature-complete; PySide runtime was not manually launched in a real window; `rbassist/ui/__init__.py` still eagerly imports the NiceGUI app, so page-package imports are not yet headless-safe.
- Next recommended step: pick one next page-owned surface, likely Library or Cues, and extract its view-model/service seam using the same pattern before adding real desktop interactions.

### 2026-04-12
- Goal: Knock out the next desktop-bridge slices while keeping the NiceGUI app as the working shell.
- Changes made: made `rbassist/ui/__init__.py` lazy so importing `rbassist.ui.jobs` no longer loads the NiceGUI app; moved the shared job registry to `rbassist/runtime/jobs.py` while keeping `rbassist/ui/jobs.py` as a compatibility export; extended `rbassist/ui_services/library.py` with Library page health row modeling and wired `rbassist/ui/pages/library.py` to it; added `rbassist/ui_services/cues.py` for cue target planning and progress panel view modeling and wired `rbassist/ui/pages/cues.py` to it; expanded `rbassist/desktop/app.py` into a read-only tabbed shell with Overview, Library preview, and Discover preview sections; updated `docs/dev/DESKTOP_GUI_MIGRATION_CONTRACT.md` with the runtime seam and extraction checklist.
- Evidence / outputs: four subagents handled Library, Cues, desktop shell, and import-seam review; `python -m compileall rbassist\runtime rbassist\ui_services rbassist\desktop rbassist\ui` passed; `pytest -q tests/test_desktop_app.py tests/test_ui_services.py tests/test_ui_jobs.py tests/test_ui_discover.py tests/test_ui_app.py tests/test_ui_state.py tests/test_ui_components.py tests/test_recommend_index.py` passed (`37 passed`); import checks confirmed `rbassist.ui.jobs` does not load `rbassist.ui.app`/`nicegui` and `rbassist.desktop.app` does not load `rbassist.utils`/`PySide6` at module import.
- Current blockers or risks: validation is still code-level plus stubbed PySide tests, not a real desktop window smoke; Settings remains the largest page-owned workflow still coupled to NiceGUI; Cues write execution still intentionally lives in the NiceGUI page.
- Next recommended step: extract Settings pipeline request/status modeling into `ui_services`, then wire the desktop shell's Library/Discover previews to more of the existing service outputs before adding any write-capable desktop actions.

### 2026-04-12
- Goal: Continue the unattended desktop-bridge pass without breaking the existing NiceGUI GUI.
- Changes made: added `rbassist/ui_services/settings.py` for Settings folder parsing, pipeline preflight/running/completion text, result payload shaping, and progress panel view modeling; wired `rbassist/ui/pages/settings.py` to those helpers while keeping NiceGUI widgets, long-running process orchestration, and metadata writes in the page; expanded `rbassist/desktop/app.py` with a read-only shared-job summary and Discover readiness model; added `tests/test_bridge_boundaries.py`, `tests/test_ui_services_settings.py`, and `docs/dev/DESKTOP_BRIDGE_SMOKE_CHECKLIST.md`; updated `docs/dev/DESKTOP_GUI_MIGRATION_CONTRACT.md` for the Settings seam and desktop readiness/job panels.
- Evidence / outputs: four subagents handled Settings extraction, desktop job/readiness enrichment, boundary/smoke docs, and regression-risk review; `python -m compileall rbassist\ui rbassist\runtime rbassist\ui_services rbassist\desktop` passed; `pytest -q tests/test_ui_app.py tests/test_ui_components.py tests/test_ui_crate_expander.py tests/test_ui_discover.py tests/test_ui_jobs.py tests/test_ui_services.py tests/test_ui_services_settings.py tests/test_ui_state.py tests/test_bridge_boundaries.py tests/test_desktop_app.py tests/test_recommend_index.py` passed (`47 passed`, `2` boundary subtests); import checks confirmed `rbassist.ui.jobs` still does not load `rbassist.ui.app`/`nicegui` and `rbassist.desktop.app` still does not load `rbassist.utils`/`PySide6`.
- Current blockers or risks: validation is still not a live browser or live PySide window smoke; Settings execution remains intentionally in NiceGUI and will need another seam before desktop can run pipelines; desktop Discover is readiness-only, not a ranking UI.
- Next recommended step: run the manual `docs/dev/DESKTOP_BRIDGE_SMOKE_CHECKLIST.md`, then extract one more execution-request seam for Settings before adding any desktop write-capable actions.

### 2026-04-12
- Goal: Fix the automated smoke finding that the NiceGUI Library page could fail to import when `matplotlib` is unavailable.
- Changes made: moved the `matplotlib.pyplot` import in `rbassist/ui/pages/library.py` into the waveform preview worker and added a friendly preview failure message when `matplotlib` is missing, so the Library page itself remains import-safe; added a subprocess regression in `tests/test_ui_app.py` that blocks `matplotlib` and imports `rbassist.ui.pages.library`.
- Evidence / outputs: `python -m compileall rbassist\ui rbassist\runtime rbassist\ui_services rbassist\desktop` passed; `pytest -q tests/test_ui_app.py tests/test_ui_components.py tests/test_ui_crate_expander.py tests/test_ui_discover.py tests/test_ui_jobs.py tests/test_ui_services.py tests/test_ui_services_settings.py tests/test_ui_state.py tests/test_bridge_boundaries.py tests/test_desktop_app.py tests/test_recommend_index.py` passed (`48 passed`, `2` boundary subtests); page import smoke over all `PAGE_SPECS` passed with zero failures; desktop model smoke returned preview rows and readiness state; import-light checks still showed no eager NiceGUI/PySide load.
- Current blockers or risks: live browser and live PySide smoke still remain manual; waveform preview still requires `matplotlib` at click time, but missing dependency no longer prevents the Library page from loading.
- Next recommended step: run one real NiceGUI browser smoke across Discover, Library, Cues, and Settings; if that passes, continue bridge work only on service seams and avoid write-capable desktop actions.

### 2026-04-13
- Goal: Move the read-only desktop shell closer to a useful Windows GUI without touching existing NiceGUI workflows.
- Changes made: expanded `rbassist/desktop/app.py` to include a read-only Library health summary built from the existing `rbassist/ui_services/library.py` page model, so the desktop Library tab now surfaces issue-row totals and top health categories alongside the preview table; updated `tests/test_desktop_app.py` and `docs/dev/DESKTOP_GUI_MIGRATION_CONTRACT.md`.
- Evidence / outputs: `python -m compileall rbassist\ui rbassist\runtime rbassist\ui_services rbassist\desktop` passed; `pytest -q tests/test_ui_app.py tests/test_ui_components.py tests/test_ui_crate_expander.py tests/test_ui_discover.py tests/`
`next desktop slice read-only by adding Library health filters/details or Discover seed-readiness from service outputs before considering any desktop actions that launch background work.

### 2026-04-12
- Goal: Implement the opt-in embedding upgrade plan without changing the canonical index contract.
- Changes made: added section-aware MERT sidecar embedding storage, opt-in recommendation and playlist-expansion transition scoring, opt-in layer-mix sidecar support, and scaffolded layer-mix training plus embedding benchmark scripts.
- Evidence / outputs: `python -m pytest tests/test_embed_resume.py tests/test_embed_sections.py tests/test_section_rerank.py tests/test_layer_mix.py tests/test_benchmark_embeddings.py tests/test_recommend_index.py tests/test_playlist_expand.py` passed (`34 passed`); `python -m compileall rbassist scripts\benchmark_embeddings.py scripts\train_layer_mix.py` passed.
- Current blockers or risks: Phase 5 promotion remains blocked until benchmark evidence exists; layer-mix is stored only as an opt-in sidecar and is not used for HNSW indexing.
- Next recommended step: run `rbassist embed --section-embed --layer-mix` on a small reviewed crate, then use `scripts/benchmark_embeddings.py` with explicit golden seeds before considering any primary-index promotion.

### 2026-04-13
- Goal: Harden and pilot the Phase 1 embedding-upgrade rollout path against live library state.
- Changes made: section sidecar writes now use `_intro.npy`, `_core.npy`, and `_late.npy` suffixes; `--section-embed --resume` can backfill missing section sidecars for already embedded tracks without rewriting primary embeddings or existing sidecars; the common section-embed path reuses the section-vector pass for the combined primary vector instead of doing a duplicate MERT pass; removed stale conflict markers from continuity docs while preserving existing content.
- Evidence / outputs: `python -m pytest tests/test_embed_sections.py tests/test_embed_resume.py` passed (`10 passed`); `python -m pytest tests/test_embed_resume.py tests/test_embed_sections.py tests/test_section_rerank.py tests/test_layer_mix.py tests/test_benchmark_embeddings.py tests/test_recommend_index.py tests/test_playlist_expand.py` passed (`37 passed`); `python -m compileall rbassist scripts\benchmark_embeddings.py scripts\train_layer_mix.py` passed; `git diff --check` passed after conflict-marker cleanup.
- Live pilot: backed up metadata to `data/backups/meta_before_section_embed_pilot_20260413_040024.json`; wrote `data/runlogs/section_embed_pilot_paths_20260413.txt` with one existing embedded track; ran `python -m rbassist.cli embed --paths-file data\runlogs\section_embed_pilot_paths_20260413.txt --section-embed --resume --checkpoint-file data\runlogs\section_embed_pilot_checkpoint_20260413.json --checkpoint-every 1`; result was `queued=1`, `succeeded=1`, `failed=0`, device `cuda`.
- Live pilot result: only one `data/meta.json` track row changed, adding `embedding_intro`, `embedding_core`, `embedding_late`, and `embedding_version=v2_section`; primary `embedding` and `_embedding_mert` files retained their February 28 timestamps; section gap count changed from `10008` to `10007`.
- Current blockers or risks: full-library section rollout has not been run yet; same-stem embedding filename collisions remain an existing risk of the current embedding store.
- Next recommended step: scale from the one-track pilot to a small reviewed crate using `rbassist embed --section-embed --resume --paths-file <small-reviewed-crate.txt> --checkpoint-file data/runlogs/section_embed_crate_checkpoint.json --checkpoint-every 25`, inspect changed meta rows, then schedule the full backfill if clean.

### 2026-04-13
- Goal: Expand the section-embedding rollout and harden transition-score observability.
- Changes made: backfilled section sidecars for a 25-track slice under `C:\Users\hunte\Music\BREAKS\2024 july august`; added playlist-expansion diagnostics for section-score coverage and transition-score counts/means; added benchmark coverage reporting for primary embeddings, complete section sidecars, layer-mix sidecars, and case-colliding track keys; hardened benchmark seed loading so explicit `--seeds` / `--seeds-file` runs no longer auto-create `config/benchmark_seeds.txt`.
- Evidence / outputs: backed up metadata to `data/backups/meta_before_section_embed_crate25_20260413_041442.json`; wrote `data/runlogs/section_embed_crate25_paths_20260413.txt`; ran `python -m rbassist.cli embed --paths-file data\runlogs\section_embed_crate25_paths_20260413.txt --section-embed --resume --checkpoint-file data\runlogs\section_embed_crate25_checkpoint_20260413.json --checkpoint-every 5`; result was `queued=25`, `succeeded=25`, `failed=0`, device `cuda`.
- Verification: exactly 25 `data/meta.json` rows changed, all from the crate path file; primary embedding paths did not change; complete section sidecar coverage increased to `26`, with `9982` primary-embedded tracks still missing at least one section sidecar.
- Benchmark smoke: wrote `data/runlogs/section_embed_crate25_benchmark_seeds_20260413.txt`; ran `python scripts\benchmark_embeddings.py --seeds-file data\runlogs\section_embed_crate25_benchmark_seeds_20260413.txt --rows C,D --section-embeds --top 10 --candidate-pool 50 --out reports\benchmark_section_crate25_20260413.json`; output coverage was `10008` primary embeddings, `26` section-complete, `0` layer-mix, and `3` case-collision key groups; row D still had no transition mean because section coverage is too sparse in the candidate pool; repeat smoke confirmed `config/benchmark_seeds.txt` stayed absent.
- Validation: `python -m pytest tests/test_section_rerank.py` passed (`5 passed`); `python -m pytest tests/test_benchmark_embeddings.py` passed (`5 passed`); `python -m pytest tests/test_embed_resume.py tests/test_embed_sections.py tests/test_section_rerank.py tests/test_benchmark_embeddings.py tests/test_recommend_index.py tests/test_playlist_expand.py` passed (`36 passed`); `python -m compileall rbassist scripts\benchmark_embeddings.py scripts\train_layer_mix.py` passed; `git diff --check` passed with only line-ending warnings.
- Current blockers or risks: transition scoring is still not meaningful for broad recommendation benchmarks until section sidecar coverage is much higher; same-stem sidecar naming collision risk remains; `data/meta.json` has case-colliding track keys that benchmarks now report.
- Next recommended step: backfill the rest of `C:\Users\hunte\Music\BREAKS\2024 july august` or another reviewed crate, then rerun C/D with enough section-covered candidates to produce a non-null `transition_score_mean`.

### 2026-04-13
- Goal: Make full section-sidecar backfill operable without hand-building a 9982-track path list.
- Changes made: added `rbassist embed --missing-section-sidecars`, which scans `data/meta.json` for tracks whose primary embedding file exists but whose intro/core/late sidecar set is incomplete; the selector implies `--section-embed` and `--resume`, skips stale/missing audio paths, and can be restricted by positional paths or `--paths-file`; documented the workflow in `README.md`.
- Evidence / outputs: the selector is queue-only and reuses the existing checkpointed section backfill path in `rbassist/embed.py`, so primary embeddings remain untouched under the default non-overwrite behavior.
- Validation: `python -m pytest tests/test_embed_resume.py` passed (`7 passed`); `python -m pytest tests/test_embed_resume.py tests/test_embed_sections.py tests/test_section_rerank.py tests/test_benchmark_embeddings.py tests/test_recommend_index.py tests/test_playlist_expand.py` passed (`39 passed`); `python -m compileall rbassist scripts\benchmark_embeddings.py scripts\train_layer_mix.py` passed; `python -m rbassist.cli embed --help` passed; `git diff --check` passed with only line-ending warnings.
- Live full backfill status: backed up metadata to `data/backups/meta_before_section_embed_full_20260413_042813.json`; started `python -m rbassist.cli embed --missing-section-sidecars --section-embed --resume --checkpoint-file data\runlogs\section_embed_full_checkpoint_20260413.json --checkpoint-every 25 --device cuda --num-workers 8`; checkpoint status at `2026-04-13T22:58:13.677109+00:00` was `running`, `1675/9980` completed, `0` failed, and `0` CUDA retries.
- Current blockers or risks: the full-library section-sidecar backfill is still running and should not be duplicated by a second embed process; if interrupted, resume the same command with the same checkpoint file.
- Next recommended step: let the current checkpointed process finish, then rerun the embedding benchmark C/D rows and verify complete section sidecar coverage before any ranking promotion.

### 2026-04-13
- Goal: Add opt-in embedding-stage profiling before making decode or MERT batching changes.
- Changes made: added `rbassist embed --profile-embed-out <jsonl>` and `build_embeddings(..., profile_embed_out=...)`; profile rows are written only when requested and include decode timing, decoded/trimmed samples, duration cap, source sample rate, MERT flattened item count, actual MERT batch size, device, section/layer/timbre flags, MERT encode timing, save timing, checkpoint timing, and meta write timing.
- Evidence / outputs: no loader behavior, decode windowing, or MERT micro-batching was changed in this slice; the profiler is intended to gather evidence before applying those optimizations.
- Validation: `python -m compileall rbassist\embed.py rbassist\cli.py` passed; `python -m pytest tests/test_embed_sections.py tests/test_embed_resume.py` passed (`14 passed`); `python -m pytest tests/test_embed_resume.py tests/test_embed_sections.py tests/test_section_rerank.py tests/test_benchmark_embeddings.py tests/test_recommend_index.py tests/test_playlist_expand.py` passed (`41 passed`); `python -m compileall rbassist scripts\benchmark_embeddings.py scripts\train_layer_mix.py` passed; `python -m rbassist.cli embed --help` passed; `git diff --check` passed with only line-ending warnings.
- Current blockers or risks: profile output has not yet been collected on a real fixed slice because the full section backfill is still running; avoid running a second embedding job concurrently.
- Next recommended step: after the active backfill finishes, run a small fixed slice with `--profile-embed-out data\runlogs\embed_profile_<slice>.jsonl`, then decide whether the decode-duration patch is justified.

### 2026-04-13
- Goal: Make the failed full section-sidecar backfill resumable without re-triggering the same CUDA crash.
- Changes made: added checkpoint failed-path quarantine for `rbassist embed --missing-section-sidecars --resume`; failed checkpoint paths are skipped by default, with `--retry-checkpoint-failures` available for intentional retries.
- Evidence / outputs: the stopped backfill checkpoint remained usable at `5650/9980` completed with one unique failed path, `C:\Users\hunte\Music\HOUSE  TECH\Halloween 2021 downloads\AITCH - Wait.mp3`; no manual checkpoint or `data/meta.json` edits were made.
- Validation: `python -m pytest tests/test_embed_resume.py tests/test_embed_sections.py` passed (`16 passed`); `python -m pytest tests/test_embed_resume.py tests/test_embed_sections.py tests/test_section_rerank.py tests/test_benchmark_embeddings.py tests/test_recommend_index.py tests/test_playlist_expand.py` passed (`43 passed`); `python -m rbassist.cli embed --help` passed; `python -m compileall rbassist\embed.py rbassist\cli.py` passed; `git diff --check` passed with only line-ending warnings.
- Resume status: restarted the full backfill as PID `23560` with `python -m rbassist.cli embed --missing-section-sidecars --section-embed --resume --checkpoint-file data\runlogs\section_embed_full_checkpoint_20260413.json --checkpoint-every 25 --device cuda --num-workers 8`; stdout/stderr are `data/runlogs/section_embed_full_resume_20260414_stdout.log` and `data/runlogs/section_embed_full_resume_20260414_stderr.log`; the resume selected `4330` remaining section-gap tracks, skipped `1` checkpoint-failed track, and skipped `2` stale audio paths.
- Completion status: PID `23560` finished cleanly; checkpoint status is `completed`, resumed queue `queued=4329`, `succeeded=4329`, `failed=0`, with the original failed path still quarantined. Read-only coverage check found `10008` primary embeddings, `10005` complete section sidecar sets, and `3` remaining section gaps: `C:\Users\hunte\Music\HOUSE  TECH\Halloween 2021 downloads\AITCH - Wait.mp3` plus two stale `D:\My Drive\demucs_separated\...` paths.
- Benchmark smoke: ran `python scripts\benchmark_embeddings.py --seeds-file data\runlogs\section_embed_crate25_benchmark_seeds_20260413.txt --rows C,D --section-embeds --top 10 --candidate-pool 50 --out reports\benchmark_section_full_20260414.json`; coverage in the report is `10005` section-complete, and C/D now produce `transition_score_mean=0.5316157023375183`.
- Current blockers or risks: the failed `AITCH - Wait.mp3` track still needs a later one-track diagnostic, likely with profile output and possibly CPU fallback; two stale demucs paths remain metadata/path hygiene follow-up rather than section embedding failures.
- Next recommended step: run a one-track diagnostic for `C:\Users\hunte\Music\HOUSE  TECH\Halloween 2021 downloads\AITCH - Wait.mp3`, then decide whether to retry it on CPU or quarantine it permanently.

### 2026-04-13
- Goal: Harden the Rekordbox boundary for Crate Expander playlist loading and playlist XML export without touching live Rekordbox state or local library metadata.
- Changes made: Crate Expander now stores DB playlist selections by stable Rekordbox playlist ID (`db:<id>`) while showing the readable playlist path; playlist loading maps the selected ID back to an integer before calling the shared backend and carries the path only as diagnostic context. The shared DB resolver now unwraps ID lookups consistently. Rekordbox XML export now creates missing parent folders and writes via temp-file replacement so failed writes do not leave partial playlist XML files.
- Evidence / outputs: added regressions covering DB playlist IDs, playlist names containing slashes such as `radio 10/22`, and nested export folders. This remains read-only against Rekordbox; XML export still writes a standalone playlist XML file only.
- Validation: `.venv\Scripts\python.exe -m pytest tests\test_ui_crate_expander.py tests\test_playlist_expand.py tests\test_cues.py` passed (`24 passed`); `.venv\Scripts\python.exe -m compileall rbassist` passed.
- Current blockers or risks: this hardens the Crate Expander import/export seam, but broader Rekordbox reconciliation/apply tooling remains intentionally review-first and was not widened in this pass.
- Next recommended step: run a live Crate Expander browser smoke by refreshing Rekordbox playlists, loading a DB playlist with a slash-bearing name, generating a crate, saving XML, and dragging the exported playlist XML into Rekordbox.

### 2026-04-14
- Goal: Complete Phase 0 hardening for the embedding benchmark and section-score rollout before starting harmonic profiles or learned-metric work.
- Changes made: `scripts/benchmark_embeddings.py` now skips section rows when `--section-embeds` is enabled but usable seed-late/candidate-intro sidecars are effectively absent, and it records explicit section-row diagnostics (`section_scores_requested`, `section_scores_enabled`, `seed_section_late_count`, `selected_candidate_intro_count`, `transition_pairs_scored`). `rbassist/playlist_expand.py` now preserves the active preset when a minimal controls dict only requests section scores, so `mode="tight"` keeps its preset weights and key filter while still adding the intended `0.18` transition weight. Section diagnostics now distinguish requested versus actually applied scores. Tests were sharpened to assert the non-section recommend path does not call section loaders, to cover the benchmark skip/diagnostic behavior, and to assert profiler rows include `device`. `README.md` now includes a backup-first reminder before large metadata-changing backfills and uses the profiler’s exact terminology (`MERT flattened item count`, `actual MERT batch size`).
- Evidence / outputs: this was a repo-only hardening slice; no library data, checkpoints, or Rekordbox state were mutated.
- Validation: `python -m pytest tests/test_section_rerank.py tests/test_benchmark_embeddings.py tests/test_playlist_expand.py tests/test_embed_sections.py` passed (`37 passed`); `python -m compileall rbassist\playlist_expand.py scripts\benchmark_embeddings.py tests\test_playlist_expand.py tests\test_section_rerank.py tests\test_embed_sections.py` passed; `git diff --check` passed with only Windows line-ending warnings.
- Current blockers or risks: benchmark rows still do not report explicit overlap/delta versus baseline row `C`; harmonic profiles remain the recommended next implementation slice, with learned similarity after a read-only playlist-pair dataset builder and tempo translation still deferred to a later spike.
- Next recommended step: implement additive harmonic profile caching under `features` and an opt-in soft `key_match` replacement that falls back to Camelot when profiles are missing.

### 2026-04-14
- Goal: Start the `ADVANCED_MATCHING_PLAN.md` implementation order with the smallest safe harmonic-profile slice before learned similarity or tempo translation work.
- Changes made: added opt-in chroma/tonnetz profile extraction, additive analyze/embed caching under `features`, opt-in `recommend --w-harmony`, and opt-in `playlist-expand --harmonic-key-score` that uses continuous harmonic compatibility for soft key scoring while falling back to Camelot when profiles are missing. Profile-only analyze backfills now avoid rewriting existing BPM/key/cue state when the file signature already matches.
- Evidence / outputs: this was a repo-only implementation slice; no live `data/meta.json`, checkpoints, audio files, or Rekordbox state were mutated.
- Validation: `python -m pytest tests/test_embed_resume.py tests/test_embed_sections.py tests/test_section_rerank.py tests/test_layer_mix.py tests/test_benchmark_embeddings.py tests/test_recommend_index.py tests/test_playlist_expand.py tests/test_harmonic_compatibility.py` passed (`56 passed`); `python -m compileall rbassist scripts tests` passed; CLI help for `analyze`, `embed`, `recommend`, and `playlist-expand` passed. Broad `python -m pytest` and `python -m pytest tests` hit a local pytest capture teardown error after collecting only two items, so explicit test targets remain the validation source of truth for this slice.
- Current blockers or risks: harmonic profile extraction is still opt-in and needs a reviewed crate backfill before it can affect real recommendations; learned similarity, playlist-pair dataset building, and tempo translation remain later slices.
- Next recommended step: run `rbassist analyze <reviewed crate> --harmonic-profiles` on a small crate, then compare `recommend --w-harmony` and `playlist-expand --harmonic-key-score` outputs before widening the profile cache.

### 2026-04-14
- Goal: Add the read-only playlist-pair dataset foundation for the future learned similarity head without starting model training yet.
- Changes made: added `rbassist/playlist_pairs.py` and `scripts/export_playlist_pairs.py` to export JSONL pair labels from resolved Rekordbox playlists using adjacent positives (`1.0`), same-playlist weak positives (`0.7`), and deterministic different-playlist negatives (`0.0`, `0.2`, or `0.3` depending on BPM/Camelot ambiguity). The exporter skips unresolved or unembedded tracks and supports `--dry-run`.
- Evidence / outputs: this is a read-only dataset-export slice for library state; it writes only the explicitly requested output/summary files and does not mutate `data/meta.json`, embeddings, indexes, checkpoints, or Rekordbox.
- Validation: `python -m pytest tests/test_playlist_pairs.py` passed (`6 passed`); `python -m compileall rbassist\playlist_pairs.py scripts\export_playlist_pairs.py tests\test_playlist_pairs.py` passed; `python scripts\export_playlist_pairs.py --help` passed.
- Current blockers or risks: this does not train or integrate a learned similarity head yet; generated labels still need a small dry-run inspection before model training.
- Next recommended step: run `python scripts\export_playlist_pairs.py --source db --dry-run --max-playlists 10`, inspect counts, then export to `data/training/playlist_pairs.jsonl` if the playlist coverage looks sane.
