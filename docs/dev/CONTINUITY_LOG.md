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
- Changes made: Made bassist/ui/state.py root-aware for health refreshes, expanded bassist/ui/components/health_summary.py with scope-aware counts, upgraded bassist/ui/components/track_table.py with stronger pagination defaults, added quick issue filters plus fixed-fallback beatgrid actions in bassist/ui/pages/library.py, improved in-app suggestion preview controls in bassist/ui/pages/tagging.py, and cleaned up the instructions/review text in bassist/ui/pages/ai_tagging.py.
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

### 2026-03-30
- Goal: Capture crate-expander performance findings and preserve the next optimization slices for a future hardening pass.
- Changes made: benchmarked real playlist expansion at `candidate_pool=1000` vs `2000` using `2024 Novemebr DLs` (`50` mapped/embedded seeds, target total `100`), profiled the hot path in `rbassist/playlist_expand.py`, and added a dedicated performance backlog note to `WISHLIST.md`.
- Evidence / outputs: library snapshot during benchmarking was `13332` tracks with `10008` embeddings; warm benchmark runs were `10.874s` at `1000` and `17.270s` at `2000`, with both runs filling from `50` to `100`; cold multi-run averages were `21.801s` at `1000` and `33.958s` at `2000`; cProfile showed the biggest costs in repeated cosine-similarity math, repeated HNSW/index-path loading, alias-index rebuilding, and repeat-signature text processing.
- Current blockers or risks: the current crate-expansion path is CPU-bound and does not expose a worker knob; widening the candidate pool improves coverage but can substantially increase rerank cost; GPU/CUDA is relevant to embed/analyze paths in the repo but not to the current playlist-expansion path.
- Next recommended step: implement the first ROI slice by caching the HNSW index, `paths.json`, and alias/meta resolution across expansion runs, then do a second slice that pre-normalizes vectors and precomputes repeat signatures before considering worker-parallel coverage queries.

### 2026-03-31
- Goal: Comprehensive optimization audit across all dimensions — code quality, performance, UI/UX, features, speed, and external integrations.
- Changes made: deep research pass across entire codebase (60+ modules, all UI pages, WISHLIST, MASTER_PLAN, pyproject.toml); findings written to `WISHLIST.md` (new "Optimization Research Findings" section, ~35 new items) and this log; `AGENT_HANDOFF_LOG.md` updated with detailed findings.
- Evidence / outputs: three parallel research agents covered (1) code quality + performance bottlenecks, (2) UI/UX + integration gaps, (3) features + wishlist + architecture gaps. All findings are now tracked in WISHLIST.md.
- Key findings:
  - **Critical data loss risk**: `save_meta()` in `utils.py:116` is non-atomic; one-liner fix (temp + rename).
  - **File handle leaks**: `recommend.py:199, 321` use bare `open()` without context manager.
  - **Hot-loop disk I/O**: `playlist_expand.py:1020` brute-force fallback does 5,000 `np.load()` calls per query.
  - **Embed batching broken**: `embed.py` `batch_size` param ignored in parallel path; 3–5× GPU throughput left on table.
  - **HNSW cold load**: index reloaded per expansion run; `CachedIndexManager` would cut cold run time 50%.
  - **No recommendation diversity**: ANN naturally clusters similar tracks; MMR reranking is the fix.
  - **60+ lines duplicated** in playlist loaders (`playlist_expand.py:461–563`).
  - **UI race conditions**: job ID dict overwritten on concurrent starts; `AppState` has no thread locks.
  - **No DJ-centric UI features**: waveform preview, Camelot wheel, drag-to-playlist all missing.
  - **No external integrations**: Serato, Traktor, Discogs, AcoustID all unimplemented; Spotify skeleton has no UI.
  - **Heuristic mood/energy classifier** could be built on existing features in ~1 day.
  - **Architecture gaps**: global hardcoded paths block multi-root; no event bus; no DI; no config layer.
- Current blockers or risks: audit is research-only; no code changed this session. Prioritization of ~35 new items still needed before implementation begins.
- Next recommended step: start with the three zero-risk critical fixes (atomic save_meta, file handle leaks, job ID race), then implement HNSW index caching as the highest-ROI performance improvement.
