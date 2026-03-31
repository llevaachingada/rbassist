# RBAssist Roadmap & Wishlist

## Signed: Claude (AI Assistant)

### Embedding & Analysis Robustness (HIGH PRIORITY)

#### Embedding Reliability
- [ ] Implement comprehensive error recovery during large library embedding
- [x] Add detailed logging for failed/skipped track embeddings
  - Completed 2026-02-07: failed track output now writes structured JSONL logs instead of console-only errors.
- [x] Create resumable embedding process
  - Completed 2026-02-07: CLI and UI now support resumable embedding runs.
- [x] Support checkpointing for multi-day/interrupted embedding runs
  - Completed 2026-02-07: `--resume`, `--checkpoint-file`, and `--checkpoint-every` are wired through the active embedding workflow.

#### Performance Optimizations
- [ ] Optimize memory usage for large libraries (100k+ tracks)
- [ ] Implement intelligent batching strategies
- [ ] Add configurable resource throttling
- [ ] Support distributed/multi-machine embedding

#### Error Handling
- [ ] Graceful handling of:
  * Corrupted audio files
  * Unsupported file formats
  * Insufficient system resources
  * Network/storage interruptions

#### UI/UX
- [ ] Library table virtual scrolling / true pagination for 10k+ tracks (current plan: pagination; future: infinite scroll).
- [x] Settings: import/scan UX overhaul (import one folder at a time without reanalyzing whole library, clarify overwrite/skip behavior for already-analyzed tracks, add an in-page "How to use" tab).
  - Completed 2026-02-28: one-folder import, configured-folder vs paths-file runs, preflight summaries, health actions, and in-page guidance are now in Settings.
- [x] Beatgrid waveform preview: refine layout/controls and consider downbeat markers/zoom; current preview shows first ~16 bars on demand.
  - Completed 2025-12-25: Enhanced with beat/downbeat markers (pink dashed/yellow solid), dark theme, BPM/confidence/segments in title, legend.
- [x] Tagging: implement safe_tagstore (user vs AI namespace), active_learning (uncertainty sampling), and optional user_model per docs/tagging_active_learning_plan.md.
  - Completed 2025-12-25: All three components implemented, validated with comprehensive test suite (7/7 tests pass).
- [x] Cues: extend auto-cue logic to folders/batches, allow user-defined cue templates (intro/core/drop/mix-out), and integrate preview/export workflow.
  - Completed 2025-12-25: Batch processing added; music folders + single file processing with progress bar; cue templates already in backend (intro/core/drop/mix-out).

#### Beatgrid Improvements
- [ ] Swap librosa beat tracker for GPU-optional CRNN/DBN (beat+downbeat) to improve syncopated/non-4x4 material.
- [x] Optional auto-beatgrid step in `analyze` pipeline (flagged, defaults to fixed) with confidence-based fallback.
  - Completed 2025-12-25: Added fallback_threshold parameter to analyze_file(); auto-retries with librosa if BeatNet confidence < 0.3 or fails; graceful degradation ensures analysis always completes.
- [ ] UI preview of detected segments + confidence with one-click fallback to fixed BPM.
  - Partial: Preview implemented; one-click fallback not yet (feature exists, could be UI button).

#### Embedding Quality
- [ ] Multi-model embedding ensemble
- [ ] Advanced timbre and rhythm feature extraction
- [ ] Support for more advanced music embedding models
- [ ] Configurable embedding strategies

#### Recommendation Flexibility
- [ ] More sophisticated similarity metrics
- [ ] Support for user-guided recommendation weighting
- [ ] Contextual recommendation adaptation

### Workflow Improvements

#### Library Management
- [x] Intelligent track deduplication UI: wire Tools → Duplicate Finder to `duplicates.find_duplicates` and show KEEP/REMOVE pairs with CDJ warnings.
  - Completed 2025-12-09: Tools page now has working duplicate scanner with exact/fuzzy matching and CDJ warnings.
- [ ] Automated metadata cleanup helpers (artist/title normalization, missing BPM/key reports).
  - Partial 2026-03-01: library health audit, embedding gap scan, collision-safe path repair, and safe bare-path/orphan resolution now exist; artist/title cleanup and manual review tools for ambiguous leftovers still need work.
- [ ] Advanced tag inference UI: expose `tags-auto` parameters in the Tagging page (min_samples, margin, prune_margin, apply) beyond the current CSV-only GUI flow.
- [ ] Comprehensive library health checks (counts of missing embeddings/BPM/key/cues, corrupt files, inconsistent tags).
  - Partial 2026-03-01: counts for missing embeddings/BPM/key/cues plus stale, bare, junk, broken-path, and post-repair orphan issues are now surfaced in scripts and UI; corrupt-file and inconsistent-tag reporting still need finishing.

#### BPM & Rekordbox Integration
- [ ] **Separate BPM storage from Rekordbox sync** - Implementation plan: `C:\Users\hunte\.claude\plans\shimmering-stirring-barto.md`
  * BPM data in separate `data/bpm.json` file (never syncs to Rekordbox by default)
  * Config-based export control (`export_bpm_to_rekordbox: false` default)
  * Conflict resolution UI when importing BPM from Rekordbox
  * One-click migration tool with automatic backup
  * Estimated effort: 5-6 days
  * Status: Design complete, awaiting implementation

#### User Preferences
- [ ] Machine learning-based preference learning
- [ ] Adaptive recommendation refinement
- [ ] User interaction feedback loop

### Technical Debt & Infrastructure

#### Testing & Validation
- [x] Comprehensive unit and integration tests
  - Completed 2025-12-25: Added test_beatgrid.py (6 test categories) and test_ai_tagging.py (7 test categories); both 100% pass rate.
- [ ] Performance benchmarking suite
- [ ] Crate Expander performance pass
  - Focus first on CPU-side wins in `rbassist/playlist_expand.py`, not GPU work.
  - Highest-ROI slice: cache the loaded HNSW index, `paths.json`, and the resolved meta/alias lookup across playlist-expansion runs instead of rebuilding or reloading them repeatedly.
  - Next slice: pre-normalize seed/candidate vectors and precompute repeat signatures once per workspace so reranking does less repeated cosine math and text normalization.
  - Later slice: explore batch or parallel per-seed coverage queries for large seed sets, optionally with a worker/config knob if the simpler caching work is not enough.
  - Grounded evidence from 2026-03-30 benchmark on playlist `2024 Novemebr DLs` (`50` mapped/embedded seeds, target total `100`):
    - warm run at `candidate_pool=1000`: `10.874s`, filled to `100`
    - warm run at `candidate_pool=2000`: `17.270s`, filled to `100`
    - cold multi-run average at `1000`: `21.801s`
    - cold multi-run average at `2000`: `33.958s`
  - Profiling note: the current bottlenecks are repeated cosine similarity work, repeated HNSW/index-path loading, alias-index rebuilding, and repeat-signature text processing.
- [ ] Cross-platform compatibility testing

#### Documentation
- [x] Inline code documentation
  - Completed 2025-12-25: Added comprehensive docstrings to beatgrid.py, ai_tagging.py, cues.py.
- [x] Detailed developer and user guides
  - Completed 2025-12-25: Created BEATGRID_ANALYSIS.md, BEATGRID_IMPROVEMENTS.md, FEATURES_COMPLETED.md, QUICK_START.md.
- [ ] Architecture decision records

### Future Exploration

#### Experimental Features
- [ ] DJ-style intelligent playlist generation surfaced in the Discover/Tools pages (front-end for existing `int-pl` logic).
- [ ] Section-aware / transition-aware crate expansion for DJ mixing.
  - Build on the shared `playlist-expand` backend now used by the CLI and Crate Expander tab.
  - Goal: expand one playlist into sections or transition-friendly lanes instead of only a flat append-only crate.
  - Follow this only after the current crate-expansion flow is manually smoke-tested in the browser.
- [ ] Advanced beat grid analysis and visual cue editing tools in the GUI.
- [ ] Optional: history rewrite tool (git-filter-repo) to fully purge accidentally committed personal/library files from Git history (force-push workflow).
- [ ] Automatic set preparation tools (end-to-end: seed → recommendations → ordered export with cues).
- [ ] Cloud/distributed recommendation services (optional, opt-in only; keep local-first workflow primary).

---

## Optimization Research Findings (2026-03-31)
*Full audit across code quality, performance, UI/UX, features, speed, and integrations.*

### Critical Bugs (Fix First — Low Risk, High Value)

- [ ] **Atomic `save_meta()` write** — `utils.py:116` writes meta.json in-place; crash mid-write = corrupt library. Fix: write to `.tmp` then `tmp.replace(META)` (atomic rename, POSIX + Windows).
- [ ] **Unclosed file handles** — `recommend.py:199, 321` use bare `json.load(open(...))` without context manager; leaks file handles on every recommendation call.
- [ ] **Job ID race condition** — `ui/pages/library.py:373` and `ui/pages/cues.py:133` overwrite `job_id` dict if two jobs start quickly; UI silently tracks the wrong job.
- [ ] **Seed validation missing** — `ui/pages/discover.py:336–338` sets seed without checking it exists in the HNSW index; produces cryptic embedding errors instead of a user-friendly message.
- [ ] **`AppState.music_folders` mutation not auto-saved** — `ui/state.py:51–95` allows direct list mutation without saving config; user can change folder, start embed, then lose the setting silently.

### Performance Optimizations (New Findings)

- [ ] **Pre-cache embeddings on brute-force fallback** — `playlist_expand.py:1020` loads a `.npy` file from disk *per candidate* during brute-force fallback (5,000 disk reads per query). Fix: load all embeddings into a dict at fallback init; add LRU cache on `load_embedding_safe()`.
- [ ] **Session-level `load_meta()` cache** — `health.py` calls `load_meta()` at lines 278, 610, 793, 955 independently; `playlist_expand.py` at 661, 1593, 1891. In a typical pipeline, meta.json loads 5–10× unnecessarily. Fix: `_meta_cache = None; def get_meta(force_reload=False)`.
- [ ] **True batch inference in `embed.py`** — `embed.py:707–761` submits futures one-at-a-time; `batch_size` param is effectively ignored in the parallel path. Fix: collect N audio arrays before model inference; expected 3–5× GPU throughput improvement.
- [ ] **HNSWLIB upfront capacity allocation** — `recommend.py:30–37` calls `resize_index()` incrementally (256→512→1024→...), rebuilding the HNSW graph each time. Fix: estimate total (`len(meta_tracks) * 1.2`) and pre-allocate in one call.
- [ ] **HNSW index cached across expansion runs** — index is reloaded from disk on every `playlist-expand` call (cold run penalty: 10–20s). Fix: `CachedIndexManager` that holds index in memory and invalidates on `meta.json` mtime change (50% cold run reduction expected).
- [ ] **Batch vectorized cosine in playlist expansion** — `playlist_expand.py` scores candidates against seeds in a per-seed loop; pre-stack all candidate vectors and do one batch dot product against seed centroid. Expected: 20–30% CPU reduction.
- [ ] **HNSWLIB index version metadata** — `recommend.py:89–107` loads index without version check; old format or dimension change causes silent full rebuild. Fix: store `{"version": 2, "embedding_dim": 1024, "model": "..."}` in `paths.json`, validate on load.

### Code Condensation

- [ ] **Extract `_extract_track_metadata()` helper** — `playlist_expand.py:461–563` has three nearly-identical playlist loaders (`_from_db`, `_from_xml`, `_from_manual`); 60+ lines of duplicated path-normalize + field-extract logic.
- [ ] **Alias index built once per session** — `playlist_expand.py:303–363` does O(n) linear string search through `paths_map` in two separate places. Fix: build `alias_index` dict once at session start.
- [ ] **Extract checkpoint flush helper in `embed.py`** — same increment→check→flush pattern at lines 518–565 and 700–706.
- [ ] **Remove `demucs` dead dependency** — listed in `pyproject.toml` stems extra but never imported anywhere in the codebase.

### Data Layer

- [ ] **Metadata versioning / schema migration** — `meta.json` has no `meta_version` field; breaking field changes silently corrupt old exports. Fix: add `"meta_version": "2"` and migration functions in `utils.py`.
- [ ] **Embedding hash validation** — `recommend.py:66–77` loads embedding with no check that the `.npy` matches the track; stale files load silently. Fix: store `embedding_hash` in meta, validate on load.
- [ ] **Consider SQLite for meta store (medium-term)** — for 13k+ track libraries, flat JSON re-serializes the entire store on every save. SQLite enables per-track ACID transactions, concurrent reader support, and `WHERE bpm BETWEEN 120 AND 130` queries. Keep `meta.json` as export format; use SQLite as runtime store.

### UI/UX (New Findings)

- [ ] **Waveform / spectrogram preview in Discover** — zero audio context on the recommendations page. Use librosa spectrogram or ffmpeg thumbnail for inline 3–5 sec preview on row hover.
- [ ] **Camelot wheel widget** — key filtering is currently plain checkboxes; replace with an SVG/canvas Camelot wheel showing current seed key and compatible neighbors.
- [ ] **BPM / Key color-coded badges** — library table shows plain text BPM/key; add color-coded badges (e.g., red for missing analysis, green for analyzed) and BPM range quick-filter buttons.
- [ ] **Drag-to-playlist basket UI** — "Add to Playlist" in Discover is a stub. Implement multi-select, shopping-cart-style basket, export to Rekordbox XML using existing `export_xml.py`.
- [ ] **Virtual scrolling for large track tables** — `library.py:603` and `discover.py:237` do full table redraws on every filter/sort. For 10k+ libraries this causes 100–200ms lag. Implement `ui.virtual_scroller` or server-side pagination.
- [ ] **Extract `BatchJobRunner` component** — `library.py:339–427` and `cues.py:105–228` both duplicate the start→progress→refresh→complete pattern. Extract into `rbassist/ui/components/batch_job_runner.py`.
- [ ] **Read-write locks on `AppState`** — `state.py:27–179` has no thread safety; concurrent UI reads while embed writes can deliver stale data. Add locks to `refresh_meta()` and `save_settings()`.
- [ ] **"Why this track?" explainer panel** — show top 3 component scores (ANN distance, bass sim, rhythm sim, tag match) per recommendation row.

### Recommendation Engine

- [ ] **MMR diversity weighting** — ANN search naturally clusters similar tracks; no uniqueness/discovery tuning. Implement Maximal Marginal Relevance (MMR) reranking with a `--diversity` parameter.
- [ ] **Context-aware recommendations** — ignores set position, energy trajectory, time-of-day preferences. Add session context (warm-up vs. peak vs. closing) to weighting.
- [ ] **Serendipity parameter** — no way to trade off similarity vs. discovery. Add `--serendipity` knob that injects controlled randomness into ANN results.

### Auto-Classification (New Feature)

- [ ] **Heuristic mood/energy classifier (low effort)** — use existing features (bass contour amplitude, rhythm regularity, tempo) to score energy/mood heuristically. No training data needed; ~1 day effort. Store as provisional AI tags in `safe_tagstore`.
- [ ] **ML-based genre/mood classification (medium effort)** — fine-tune a lightweight classifier on top of existing MERT embeddings using user-applied tags as training labels. ~5 days.
- [ ] **Expose `samples_score()` heuristic in UI/recommendations** — `embed.py` computes break-section scores but they are not surfaced in the recommendation engine or UI.

### CLI Improvements

- [ ] **Progress output for all long-running commands** — `embed`, `analyze`, `beatgrid`, `index` run silently for 30+ min on large libraries. Add `--progress` flag (on by default) showing ETA, files/sec, current file.
- [ ] **`--dry-run` flags** — `export-xml`, `tags-auto --apply`, and `playlist-expand` lack dry-run. Add flag showing what would change without writing.
- [ ] **`--resume` for `analyze` and `beatgrid`** — only `embed` has checkpoint/resume today. `analyze` and `beatgrid` lose all progress on interrupt.
- [ ] **Command grouping** — 12+ flat top-level commands; restructure as `rbassist pipeline ...`, `rbassist metadata ...`, `rbassist io ...` sub-apps.
- [ ] **Shell tab completion** — Typer supports `--install-completion` natively; wire it in.
- [ ] **Extended help / quickstart command** — `rbassist quickstart` showing step-by-step first-run workflow.

### External Tool Integrations

- [ ] **Serato DJ Pro import** — parse `.plist` profile + JSON crates; import crates, metadata, hot cues. New files: `rbassist/serato_import.py`, `rbassist/ui/pages/serato_sync.py`, `tests/test_serato_import.py`.
- [ ] **Traktor Pro 3 import** — parse `.nml` XML collection + `.tls` track lists; import playlists, beatgrid, cue points. New files: `rbassist/traktor_import.py`, `rbassist/ui/pages/traktor_sync.py`, `tests/test_traktor_import.py`.
- [ ] **Spotify two-way sync (finish skeleton)** — `sync_online.py:35–54` has a partial skeleton with no UI and no two-way sync. Build full UI flow in `rbassist/ui/pages/spotify_sync.py`, add conflict resolution.
- [ ] **Discogs API integration** — batch album art + genre/release metadata enrichment. New: `rbassist/discogs_enrichment.py`, `rbassist/ui/pages/metadata_enrichment.py`, `data/discogs_cache.json`.
- [ ] **MusicBrainz / AcoustID fingerprinting** — fingerprint-based track identification and metadata correction. New: `rbassist/acoustid_lookup.py`, `rbassist/ui/pages/audio_fingerprinting.py`.
- [ ] **Last.fm scrobbling + similar artists** — track plays, listening history, similar-artist discovery feed. New: `rbassist/lastfm_api.py`.

### Architecture (Long-term)

- [ ] **Global path constants need refactor** — `EMB`, `IDX`, `DATA`, `ROOT` hardcoded in `utils.py`; blocks multi-root library support and is not thread-safe.
- [ ] **Add event bus / change propagation** — meta.json changes don't propagate to UI; all pages must manually poll/refresh. An event bus would allow targeted invalidation.
- [ ] **Dependency injection for UI pages** — pages import modules directly, making them impossible to mock in tests. Introduce injectable service layer.
- [ ] **Config layer for scattered constants** — `W_MERT = 0.7`, `SAMPLE_RATE = 24000`, `TIMBRE_FRAME_S = 1.0`, etc. are in multiple modules; centralize in a `config.py` or `.rbassistrc`.

## Contributing

Interested in helping? Check the current roadmap and open issues. 
Pull requests welcome!

---
Last Updated: 2026-03-31
Curator: Claude (AI Assistant) + rbassist contributors

## Completion Summary (2026-03-31)
- **Total Wishlist Items:** ~75 (was ~40)
- **Completed:** 12 major items
- **In Progress:** 6 items
- **Not Started:** ~57 items (includes ~35 new items from 2026-03-31 audit)
- **System Feature Completeness:** 70%
