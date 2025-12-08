## Changelog (working notes)

### 2025-12-08
- Embeddings: Default MERT now uses intro/core/late windows; optional OpenL3 timbre branch (48 kHz, 1s/50% overlap, mean+var pooling) mixed 70/30 into the main embedding. Component files saved as `_mert.npy`, `_timbre.npy`, and combined `embedding.npy`.
- CLI: `rbassist embed` accepts `--timbre/--timbre-size`. Sampling mode unchanged.
- UI: Streamlit webapp removed; NiceGUI (`rbassist ui`) is the sole GUI.
- Docs: README/ABOUT updated to point to NiceGUI and note embedding changes.
- UI settings: Added one-click “Embed + Analyze + Index” pipeline button (respects overwrite/timbre toggles) in Settings; new state flags `use_timbre` and `embed_overwrite` persisted.
- UI pipeline: Added linear progress + status text for the pipeline button (embed → analyze → index) with per-stage updates and ETA-style counters based on completed steps.
- Defaults: Duration cap now 90s; timbre and overwrite default to ON to keep embeddings consistent after rebuilds.
- UX: Library shows current folder/index/timbre/overwrite flags; Discover blocks when index is missing. Settings shows read-only flags and clearer duration label.
- Library: Single primary button now runs Embed + Analyze + Index; secondary buttons for Analyze + Index (recovery if embed already done) and Rebuild Index.
