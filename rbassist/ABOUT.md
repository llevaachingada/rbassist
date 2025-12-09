## About rbassist

rbassist is a Windows-first toolchain for DJs who want AI-assisted metadata, fast recommendations, and streamlined Rekordbox workflows without depending on opaque cloud services. The project packages a Typer CLI, Streamlit control panel, and a set of data pipelines that run entirely on a local GPU (tested on RTX 4060-class laptops).

### What it does

- Builds audio embeddings with `m-a-p/MERT-v1-330M`, caches them as `.npy` vectors, and stores metadata in `data/meta.json`.
- Indexes those embeddings with HNSWLIB to power lightning-fast similarity lookups in both CLI (`rbassist recommend`) and GUI.
- Imports Bandcamp CSV tags and Rekordbox My Tag exports, ties them into a unified `config/tags.yml`, and can reapply/suggest tags automatically.
- Analyzes BPM, Camelot keys, cue suggestions, RMS/sample heuristics, and bass contours so transitions and auto-tags respect musical structure.
- Provides a Streamlit front-end with folder management, embed/analyze controls, duplicates finder, stem-splitting helpers, and library browser.
- Ships ready-to-use Typer commands for XML export, playlists, DJ Link listener, My Tag importer, intelligent playlist presets, and high-volume auto-tagging.

### Why it matters

1. **Local control** – all audio stays on your machine; nothing is uploaded. This keeps private edits or unreleased promos secure.
2. **Repeatable pipelines** – every command (`embed`, `analyze`, `index`, `tags-auto`, etc.) can be scripted/batched, so large crates can be refreshed overnight.
3. **Human-friendly review** – CLI progress bars, Streamlit tables, CSV exports, and meta snapshots give you a paper trail for every automated suggestion.
4. **Interoperability** – outputs (`rbassist.xml`, config/tags.yml, data/meta.json`) are simple text/JSON files that plug into Rekordbox and other library tools.

### Architecture snapshot

| Layer | Tech | Notes |
| --- | --- | --- |
| Embedding | PyTorch + Transformers | MERT-v1-330M with optional CUDA acceleration. |
| Index/Search | HNSWLIB | Cosine similarity, ANN queries for top-N recs. |
| CLI | Typer | Commands under `rbassist` entry-point. |
| GUI | Streamlit | Runs `rbassist/webapp.py`, mirrors CLI functionality. |
| Metadata | JSON/YAML | `data/meta.json`, `config/tags.yml`, `data/index`. |

### Typical workflow

1. `rbassist embed "D:\Music\YourCrate" --duration-s 60 --device cuda --num-workers 4`
2. `rbassist analyze "D:\Music\YourCrate" --duration-s 60`
3. `rbassist index`
4. `rbassist recommend "Artist - Track" --top 25` or start the NiceGUI UI via `rbassist ui`

### Embedding defaults (Dec 2025)
- **Slicing policy:** per track, rbassist spends ~80 seconds of audio budget using three fixed slices: 10s intro, 60s core (40s on medium-length tracks), and 10s late. The intro starts at the first non-silent audio, the core slice is centered on the track midpoint (clamped to stay inside the file), and the late slice sits near the end with 5s of headroom and no overlap with the core.
- **Edge cases:** tracks shorter than ~80s are embedded as a single full-track window; medium tracks use a 10/40/10 pattern; very long tracks still use the same 80s budget to capture overall “vibe” rather than full coverage.
- **Layer / pooling policy:** MERT embeddings use the model’s upper layers with mean pooling over each slice, and then mean-pool across the three slices into a single 1024-d vector.
- **Timbre branch:** an OpenL3 “music” model at 48 kHz with 1.0s frames and 50% overlap produces a timbre embedding for the same windows. Each slice aggregates mean and variance to form a 1024-d timbre vector (mean || variance), and rbassist blends MERT and timbre at fixed weights 70/30 (W_MERT / W_TIMBRE). Component files `_mert.npy` and `_timbre.npy` are saved alongside the combined `embedding.npy`.
- **Hard defaults:** the core parameters (slice durations, OpenL3 frame/hop, and 512-d timbre size) are treated as canonical; CLI/UI guardrails prevent running with non-default duration or timbre size so that a library’s embeddings remain consistent over time.
5. `rbassist tags-auto --margin 0.05 --apply` or review in the GUI’s Auto Tag Suggestions table.
6. `rbassist export-xml --out rbassist.xml` for Rekordbox ingest.

### Getting involved

- **Issue tracking** – Use GitHub Issues for bugs, feature requests, or performance reports (include OS, GPU, and command logs).
- **Pull requests** – Align with the existing Typer/Streamlit patterns, keep features optional, and document new CLI flags in `readme.txt`.
- **Testing** – Lightweight pytest suite under `tests/`; when touching embedding/analyze/tagstore logic, add fixtures or CLI dry-run scripts.

### Support

Questions, ideas, or DJ workflow tips? File an issue in the GitHub repo or drop a note in the project discussions tab. The more context you give (dataset size, hardware, desired outcome), the faster we can help tune rbassist to your setup.
