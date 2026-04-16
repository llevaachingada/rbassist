## About rbassist

rbassist is a Windows-first toolchain for DJs who want AI-assisted metadata, fast recommendations, and streamlined Rekordbox workflows without depending on opaque cloud services. The project packages a Typer CLI, a NiceGUI interface, and local data pipelines that run on the same machine as your music library.

### What it does

- Builds audio embeddings with `m-a-p/MERT-v1-330M`, caches them as `.npy` vectors, and stores metadata in `data/meta.json`.
- Indexes those embeddings with HNSWLIB to power fast similarity lookups in both CLI (`rbassist recommend`) and GUI flows.
- Imports Bandcamp CSV tags and Rekordbox My Tags, ties them into a unified `config/tags.yml`, and can reapply or suggest tags automatically.
- Analyzes BPM, Camelot keys, cue suggestions, beatgrid segments, RMS/sample heuristics, and bass contours so transitions and auto-tags respect musical structure.
- Provides a NiceGUI front-end with library browsing, health checks, folder-by-folder ingest, beatgrid preview, and settings for resumable embedding.
- Ships ready-to-use Typer commands for XML export, playlists, DJ Link listener, My Tag import, duplicate detection, and large-library ingest workflows.

### Why it matters

1. **Local control** - all audio stays on your machine; nothing is uploaded.
2. **Repeatable pipelines** - commands like `embed`, `analyze`, `index`, and `tags-auto` can be scripted or resumed for large crates.
3. **Human-friendly review** - CLI progress, NiceGUI tables, JSON reports, and meta snapshots provide a paper trail for automated suggestions.
4. **Interoperability** - outputs such as `rbassist.xml`, `config/tags.yml`, and `data/meta.json` stay simple and portable.

### Architecture Snapshot

| Layer | Tech | Notes |
| --- | --- | --- |
| Embedding | PyTorch + Transformers | MERT-v1-330M with optional CUDA acceleration. |
| Index/Search | HNSWLIB | Cosine similarity ANN queries for top-N recommendations. |
| CLI | Typer | Commands under the `rbassist` entry point. |
| GUI | NiceGUI | Launch with `rbassist ui` or `start.ps1`. |
| Metadata | JSON/YAML | `data/meta.json`, `config/tags.yml`, `data/index`. |

### Typical Workflow

1. `rbassist embed "D:\Music\YourCrate" --device cuda --num-workers 4`
2. `rbassist analyze "D:\Music\YourCrate" --duration-s 60`
3. `rbassist index`
4. `rbassist recommend "Artist - Track" --top 25` or launch `rbassist ui`
5. `rbassist tags-auto --margin 0.05 --apply`
6. `rbassist export-xml --out rbassist.xml`

### Large-Library Notes

- Resumable embedding supports `--paths-file`, `--resume`, `--checkpoint-file`, and `--checkpoint-every`.
- Health tooling lives in `scripts/audit_meta_health.py`, `scripts/list_embedding_gaps.py`, and `scripts/normalize_meta_paths.py`.
- Path repair now supports collision-safe dry runs before any metadata write-back.

### Getting Involved

- **Issue tracking** - Use GitHub Issues for bugs, feature requests, or performance reports and include OS, GPU, and command logs.
- **Pull requests** - Align with the existing Typer and NiceGUI patterns, keep risky features optional, and document new CLI flags.
- **Testing** - Lightweight pytest coverage lives under `tests/`; when touching embedding, analysis, or metadata flows, add small fixtures or focused smoke tests.

### Support

Questions, ideas, or DJ workflow tips? File an issue in the GitHub repo or drop a note in the project discussions tab. The more context you give about your hardware, library size, and desired workflow, the easier it is to tune rbassist for your setup.
