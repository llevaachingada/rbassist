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

### Embedding updates (Dec 2025)
- Default embeddings sample intro/core/late slices and average them.
- Optional timbre branch (OpenL3 music, 48 kHz, 1s/50% overlap) mixes into the main embedding at 70/30 when `--timbre` is used; component files `_mert.npy` and `_timbre.npy` are stored alongside the combined `embedding.npy`.
5. `rbassist tags-auto --margin 0.05 --apply` or review in the GUI’s Auto Tag Suggestions table.
6. `rbassist export-xml --out rbassist.xml` for Rekordbox ingest.

### Getting involved

- **Issue tracking** – Use GitHub Issues for bugs, feature requests, or performance reports (include OS, GPU, and command logs).
- **Pull requests** – Align with the existing Typer/Streamlit patterns, keep features optional, and document new CLI flags in `readme.txt`.
- **Testing** – Lightweight pytest suite under `tests/`; when touching embedding/analyze/tagstore logic, add fixtures or CLI dry-run scripts.

### Support

Questions, ideas, or DJ workflow tips? File an issue in the GitHub repo or drop a note in the project discussions tab. The more context you give (dataset size, hardware, desired outcome), the faster we can help tune rbassist to your setup.
