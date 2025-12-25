## Changelog (working notes)

### 2025-12-08
- Embeddings: Default MERT now uses intro/core/late windows; optional OpenL3 timbre branch (48 kHz, 1s/50% overlap, mean+var pooling) mixed 70/30 into the main embedding. Component files saved as `_mert.npy`, `_timbre.npy`, and combined `embedding.npy`.
- CLI: `rbassist embed` accepts `--timbre/--timbre-size`. Sampling mode unchanged.
- UI: Streamlit webapp removed; NiceGUI (`rbassist ui`) is the sole GUI.
- Docs: README/ABOUT updated to point to NiceGUI and note embedding changes.
- UI settings: Added one-click "Embed + Analyze + Index" pipeline button (respects overwrite/timbre toggles) in Settings; new state flags `use_timbre` and `embed_overwrite` persisted.
- UI pipeline: Added linear progress + status text for the pipeline button (embed + analyze + index) with per-stage updates and ETA-style counters based on completed steps.
- Defaults: Duration cap now 90s; timbre and overwrite default to ON to keep embeddings consistent after rebuilds.
- UX: Library shows current folder/index/timbre/overwrite flags; Discover blocks when index is missing. Settings shows read-only flags and clearer duration label.
- Library: Single primary button now runs Embed + Analyze + Index; secondary buttons for Analyze + Index (recovery if embed already done) and Rebuild Index.

### 2025-12-09
- Embedding windows: Default `_default_windows` now follows a fixed 80s budget (10s intro, 60s or 40s core, 10s late) with first-non-silent intro, midpoint-centered core, and late slice 5s before the end; short/medium track edge cases handled explicitly.
- Timbre branch: Confirmed OpenL3 settings in code/docs (48 kHz, 1.0s frames, 50% overlap, mean+var pooling) and enforced canonical 512-d timbre size; CLI/UI guard against non-default duration/timbre to keep embeddings consistent.
  - Load reduction: Timbre now evaluates only intro and late slices (dropping the core slice) and uses a sparser 1s/75% hop framing, cutting CPU work by roughly half while still sampling beginning/end texture.
- Analyze pipeline: Restored full BPM/Key/feature/cue analysis (`analyze_bpm_key`, `_analyze_single`) including bass/rhythm contours and optional auto-cues; GUI Settings now passes `add_cues` through and these cues are emitted in Rekordbox XML.
- UI robustness: Hardened Settings "Embed + Analyze + Index" against tab closes by wrapping progress updates and notifications in `try/except RuntimeError`; long runs continue even if the client disconnects.
- Rekordbox export (GUI): Tools page "Export Rekordbox XML" now calls `export_xml.write_rekordbox_xml` and writes `rbassist.xml` in the project root, mirroring `rbassist export-xml` behavior.
- Tag suggestions (GUI): Tagging page "Learn Profiles" / "Preview Suggestions (CSV)" now call `tag_model.learn_tag_profiles` and `suggest_tags_for_tracks`, writing a review CSV to `data/tag_suggestions.csv`; an "Apply Suggestions" flow, guarded by an explicit checkbox, merges accepted suggestions into My Tags via `bulk_set_track_tags`.
- Rekordbox tag import (GUI): Tagging page "Import Rekordbox XML" wired to `tagstore.import_rekordbox_tags` with browser file picker and success/error notifications.
- Duplicate finder (GUI): Tools page "Scan for Duplicates" now calls `duplicates.find_duplicates` (exact/fuzzy) and `cdj_warnings`, showing KEEP/REMOVE pairs in a review table without touching files; users can act on the suggestions in their file manager.
- UI honesty: Library "Analyze Library" button now nudges users to Settings "Embed + Analyze + Index" instead of calling a stub pipeline; remaining "coming soon" buttons in Discover/Tools are explicitly marked as such instead of silently no-oping.

### 2025-12-24
- Beatgrid backend: Added `rbassist.beatgrid` with fixed (default) and dynamic modes. Dynamic splits tempo segments when drift exceeds a configurable percent over a bars window; writes `tempos`, `beatgrid_mode`, and a confidence score into `meta.json`.
- CLI: New `rbassist beatgrid <files|folders>` command with `--mode fixed|dynamic`, `--drift-pct`, `--bars-window`, and optional `--duration-s` cap.
- UI: Library page now exposes a Beatgrid card (mode toggle, drift %, bars, duration) with buttons to process music folders or a single picked file; runs in a background thread and refreshes meta on completion.
- Beatgrid backend (GPU optional): Added BeatNet CRNN/DBN support when installed; `--backend auto|beatnet|librosa` and backend picker in the UI default to auto (tries BeatNet, falls back to librosa). Writes `beatgrid_backend` and confidence to meta.
- Settings: added beatgrid toggles (enable/overwrite) in pipeline; pipeline now optionally runs beatgrid after analyze. Library shows Beatgrid status column and export-to-Rekordbox button.
- Library UI: Beatgrid card defaults to BeatNet, adds helper text, and includes a waveform preview (first ~16 bars) with beat markers. Library table now has pagination and search (artist/title/MyTags) without the old 500-row cap.
