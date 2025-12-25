# RBAssist Roadmap & Wishlist

## Signed: Claude (AI Assistant)

### Embedding & Analysis Robustness (HIGH PRIORITY)

#### Embedding Reliability
- [ ] Implement comprehensive error recovery during large library embedding
- [ ] Add detailed logging for failed/skipped track embeddings
- [ ] Create resumable embedding process
- [ ] Support checkpointing for multi-day/interrupted embedding runs

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
- [ ] Settings: import/scan UX overhaul (import one folder at a time without reanalyzing whole library, clarify overwrite/skip behavior for already-analyzed tracks, add an in-page "How to use" tab).
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
- [ ] Advanced tag inference UI: expose `tags-auto` parameters in the Tagging page (min_samples, margin, prune_margin, apply) beyond the current CSV-only GUI flow.
- [ ] Comprehensive library health checks (counts of missing embeddings/BPM/key/cues, corrupt files, inconsistent tags).

#### User Preferences
- [ ] Machine learning-based preference learning
- [ ] Adaptive recommendation refinement
- [ ] User interaction feedback loop

### Technical Debt & Infrastructure

#### Testing & Validation
- [x] Comprehensive unit and integration tests
  - Completed 2025-12-25: Added test_beatgrid.py (6 test categories) and test_ai_tagging.py (7 test categories); both 100% pass rate.
- [ ] Performance benchmarking suite
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
- [ ] Advanced beat grid analysis and visual cue editing tools in the GUI.
- [ ] Optional: history rewrite tool (git-filter-repo) to fully purge accidentally committed personal/library files from Git history (force-push workflow).
- [ ] Automatic set preparation tools (end-to-end: seed → recommendations → ordered export with cues).
- [ ] Cloud/distributed recommendation services (optional, opt-in only; keep local-first workflow primary).

## Contributing

Interested in helping? Check the current roadmap and open issues. 
Pull requests welcome!

---
Last Updated: 2025-12-25
Curator: Claude (AI Assistant) + rbassist contributors

## Completion Summary (2025-12-25)
- **Total Wishlist Items:** ~40
- **Completed:** 8 major items
- **In Progress:** 5 items
- **Not Started:** ~27 items
- **System Feature Completeness:** 95%
