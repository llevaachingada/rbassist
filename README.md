REK0RDB0X TOOLS that DJs need

Can we build local repositories better and stronger than AlphaTheta's failing software platform?

Pioneer hardware is the golden standard for a reason, but the software backend has been failing us working DJS in the field.
Is there a world where open source players and hardware can be fed by locally customized software? 

rbassist is a Windows-first toolchain for DJs who want AI-assisted metadata, fast recommendations, and streamlined Rekordbox workflows without depending on cloud services. The repo bundles a Typer CLI, NiceGUI UI, and data pipelines that run locally on your GPU.

### Highlights

- Builds embeddings with `m-a-p/MERT-v1-330M` and caches them as `.npy` vectors.
- Indexes embeddings via HNSWLIB for fast similarity lookups (`rbassist recommend`, GUI recommendations panel).
- Imports Bandcamp CSV tags and Rekordbox My Tags, storing them in `config/tags.yml` (local, gitignored; see `config/tags.example.yml`) + `data/meta.json`.
- Analyzes BPM, Camelot key, cues, RMS/sample heuristics, and bass contours.
- Offers Typer commands for embed/analyze/index/tags-auto/export-xml plus GUI equivalents (NiceGUI).

### Architecture Snapshot

| Layer | Tech | Notes |
| --- | --- | --- |
| Embedding | PyTorch + Transformers | MERT-v1-330M, CUDA/ROCm optional. |
| Index/Search | HNSWLIB | Cosine ANN queries for recommendations. |
| CLI | Typer | Commands under `rbassist` entry point. |
| GUI | NiceGUI | `rbassist ui` |
| Metadata | JSON/YAML | `data/meta.json`, `config/tags.yml`, `data/index`. |

### Typical Workflow

1. `rbassist embed "D:\Music\YourCrate" --duration-s 60 --device cuda --num-workers 4`
2. `rbassist analyze "D:\Music\YourCrate" --duration-s 60`
3. `rbassist index`
4. `rbassist recommend "Artist - Track" --top 25` or launch the NiceGUI UI via `rbassist ui`.

### Embedding updates (Dec 2025)

- Default embedding now averages intro/core/late slices instead of a single long clip for better coverage.
- Optional timbre branch (OpenL3 music, 48 kHz, 1s/50% overlap) is mixed with MERT at 70/30 when `--timbre` is enabled:
  ```powershell
  rbassist embed "D:\Music" --device cuda --num-workers 4 --timbre --timbre-size 512
  ```
  This writes `*_mert.npy`, `*_timbre.npy`, and the combined `embedding.npy`.
- Streamlit UI has been removed; NiceGUI (`rbassist ui`) is the only GUI.
5. `rbassist tags-auto --margin 0.05 --apply` (or edit via GUI Auto Tag Suggestions).
6. `rbassist export-xml --out rbassist.xml` for Rekordbox import.

### Getting Involved

- **Issues/ideas**: file them on GitHub with hardware + command logs.
- **Pull requests**: follow existing Typer/NiceGUI patterns, document new flags, and add tests when touching analyze/embed/tagstore logic.
- **Support**: share DJ workflow needs in discussions; the more context, the better the tuning advice.

## Install (Windows)

1. **Create venv**
```powershell
py -3.11 -m venv .venv
. .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```
2. **Install Torch (GPU)**
```powershell
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```
3. **Install package**
```powershell
pip install -e .
```

## Use

1) Build embeddings for a folder (reads common audio files)
```powershell
rbassist embed "D:\Music\YourCrate"
```
PowerShell tip: if you see the secondary prompt `>>`, you're still in a continued line (usually due to a missing closing quote). Press Ctrl+C to cancel and retype. You can also `cd` into the folder and run `rbassist embed .` to avoid path quoting.

Speed tips (GPU + parallel I/O):
```powershell
rbassist embed "D:\Music\YourCrate" --device cuda --num-workers 6 --duration-s 120
```
- `--device cuda` uses your NVIDIA GPU or an AMD ROCm build of PyTorch (after installing the matching Torch build below). Use
  `--device mps` for Apple Silicon.
- `--num-workers` parallelizes audio decoding (4-8 typical). Model inference stays serialized for stability.
- `--duration-s` caps per-track analysis while testing.
- Model cache: Hugging Face assets download to `%USERPROFILE%\.cache\huggingface` by default (set via `HF_HOME`). The MERT model is ~1.3 GB; make sure you have space on the download drive.

Resumable embedding for long runs:
```powershell
# Use a prepared path list and checkpoint every 50 tracks
rbassist embed --paths-file .\.tmp\pending_embedding_paths.part001.txt --checkpoint-every 50

# Resume after interruption (default checkpoint: data/embed_checkpoint.json)
rbassist embed --paths-file .\.tmp\pending_embedding_paths.part001.txt --resume --checkpoint-every 50

# Backfill intro/core/late sidecars for already-primary-embedded tracks
rbassist embed --missing-section-sidecars --section-embed --resume --checkpoint-file data\runlogs\section_embed_backfill_checkpoint.json --checkpoint-every 25

# Restrict the same backfill to a reviewed crate or path list
rbassist embed "C:\Users\you\Music\BREAKS" --missing-section-sidecars --section-embed --resume --checkpoint-file data\runlogs\section_embed_breaks_checkpoint.json --checkpoint-every 25

# Optional profiling for future tuning; writes one JSON object per processed track
rbassist embed --paths-file .\.tmp\profile_slice.txt --section-embed --resume --profile-embed-out data\runlogs\embed_profile_slice.jsonl

# Optional harmonic profile cache for continuous key scoring experiments
rbassist analyze "D:\Music\YourCrate" --duration-s 60 --harmonic-profiles
```

Notes:
- Before any large backfill that will update `data/meta.json`, make or verify a fresh metadata backup in `data/backups` and start with a reviewed crate or paths file before scaling to the full library.
- `--paths-file` accepts one file/folder path per line (`# comments` and blank lines allowed).
- `--checkpoint-file` lets you override the checkpoint location.
- Failed tracks are written to a structured JSONL log next to the checkpoint file.
- `--missing-section-sidecars` scans `data/meta.json` for tracks with an existing primary embedding file but missing one of `embedding_intro`, `embedding_core`, or `embedding_late`; with paths or `--paths-file`, it restricts the scan to that scope and implies `--resume` so primary embeddings are not rewritten.
- When `--missing-section-sidecars --resume` finds failed paths in the checkpoint, it skips them by default so one bad file cannot stop a full-library backfill again. Use `--retry-checkpoint-failures` only when intentionally retrying quarantined failures.
- `--profile-embed-out` is opt-in and records per-track JSONL timing for audio decode, sample counts, MERT flattened item count, actual MERT batch size, save/checkpoint/meta writes, device, and embedding mode flags. Use it on a small fixed slice before changing loader or batching behavior.
- `--harmonic-profiles` is opt-in and additive: it stores cached `chroma_profile` and `tonnetz_profile` values under each track's `features` without changing the default Camelot key behavior.

Library health and path repair workflow:
```powershell
# Audit current metadata health
python scripts/audit_meta_health.py --repo .

# Scan your configured music roots for actual embedding gaps
python scripts/list_embedding_gaps.py --repo . --music-root "C:\Users\you\Music\BREAKS"

# Dry-run path repair and collision-safe dedupe
python scripts/normalize_meta_paths.py --repo . --rewrite-from "C:/Users/OldUser/Music" --rewrite-to "C:/Users/you/Music" --drop-junk --resolve-collisions

# Resolve bare filename/orphan entries that have exactly one match under your music roots
python scripts/resolve_bare_meta_paths.py --repo . --music-root "C:\Users\you\Music"

# Audit Rekordbox's current library against your canonical music root (read-only)
python scripts/rekordbox_audit_library.py --music-root "C:\Users\you\Music" --out data/runlogs/rekordbox_audit.json

# Split that audit into smaller human-review queues
python scripts/prepare_rekordbox_review_queues.py --audit-report data/runlogs/rekordbox_audit.json --out-dir data/runlogs/rekordbox_review_queues --prefix rekordbox_music_root

# Run a background maintenance pass for one canonical music root
python scripts/run_music_root_background_maintenance.py --music-root "C:\Users\you\Music"
```

Notes:
- Use the dry run first; it reports stale paths, bare filename entries, junk AppleDouble files, and collision-safe merge groups.
- `--resolve-collisions` safely merges slash-style and moved-root duplicates before apply.
- `resolve_bare_meta_paths.py` only auto-repairs uniquely matched bare filenames; ambiguous and missing filenames stay untouched for manual follow-up.
- `rekordbox_audit_library.py` is read-only: it audits broken/outside-root Rekordbox paths, suggests relinks into your canonical music root, builds a consolidation move plan, and reports same-name-plus-duration duplicate groups.
- `prepare_rekordbox_review_queues.py` turns the large Rekordbox audit into smaller review files for high-confidence relinks, ambiguous relinks, and same-name/different-type duplicate groups.
- `run_music_root_background_maintenance.py` writes a self-contained run folder with `status.json`, `status.md`, audit outputs, gap scan results, and Rekordbox review queues. Add `--include-embed --include-analyze --include-index --resume` when you want a longer unattended maintenance pass.
- Add `--apply` only after reviewing the JSON report.
2) Build the HNSW index
```powershell
rbassist index
```
3) Get recommendations for a seed track (path or substring)
```powershell
rbassist recommend "Artist - Title" --top 25
```
4) Expand an existing Rekordbox playlist into a larger crate
```powershell
rbassist playlist-expand --playlist "DarkMoon" --target-total 30 --mode balanced --preview-json .\data\runlogs\darkmoon_expand.json --out-xml .\exports\darkmoon_expanded.xml
```
This is read-only against Rekordbox and `data/meta.json`, and it fails closed if fewer than 3 mapped tracks with embeddings are available.
Presets now include `tight`, `balanced`, and `adventurous`; advanced overrides include `--strategy blend|centroid|coverage`, `--key-mode off|soft|filter`, and weight flags such as `--w-ann-centroid`, `--w-group-match`, and `--w-tags`.
Use `--harmonic-key-score` only after harmonic profiles have been cached; it replaces the soft `key_match` component with continuous chroma/tonnetz compatibility where profiles exist and falls back to Camelot when they do not.
The NiceGUI `Crate Expander` tab now uses the same shared backend with Rekordbox playlist loading, preset toggles, advanced sliders, quick role-tag lane buttons such as `Warm-up` and `Peak-time`, and cached reranking so slider changes reuse the prepared candidate pool instead of rebuilding ANN every time. Its advanced controls can also opt into cached profile harmony and section-flow scoring when those sidecars exist.
The Crate Expander UI can also save the current expansion as a Rekordbox playlist XML file under `exports/crate_expander/`; this writes a playlist XML only and does not overwrite or mutate your Rekordbox library. After saving, the export folder opens so you can drag the XML into Rekordbox to import the new playlist.
Added-track selection also applies a small anti-repetition penalty to reduce same-artist / same-version clustering in the appended crate.

Build a read-only playlist-pair dataset for future learned-similarity training:
```powershell
python scripts\export_playlist_pairs.py --source db --out data\training\playlist_pairs.jsonl --summary data\training\playlist_pairs_summary.json
```
Use `--dry-run` first to print counts without writing the JSONL dataset. The exporter only writes the requested output files; it does not mutate `data/meta.json`, embeddings, indexes, or Rekordbox. Smart playlists and individual playlist load failures are skipped by default during discovery so one bad Rekordbox playlist does not stop the export.

Train and test the opt-in learned similarity reranker:
```powershell
# CUDA is preferred by default; the trainer falls back to CPU if CUDA is unavailable.
python scripts\train_similarity_head.py --pairs data\training\playlist_pairs.jsonl --out data\models\similarity_head.pt --device cuda

# Use the trained head only when explicitly requested.
rbassist recommend "Artist - Title" --learned-similarity --w-learned-sim 0.30 --similarity-device cuda

# Compare baseline, section, harmonic, and learned rows for listening review.
python scripts\benchmark_embeddings.py --seeds-file config\benchmark_seeds.txt --rows C,D,G,H --section-embeds --learned-similarity-model data\models\similarity_head.pt
```
The learned model does not replace the HNSW index or the primary `embedding` field. If the model file is missing, recommendation and benchmark flows fall back cleanly instead of failing.
The NiceGUI Discover tab exposes the same idea as opt-in controls: Profile harmony uses cached chroma/tonnetz profiles, and Learned fit uses the trained playlist-pair model only when enabled. CUDA is the default learned-model device.

5) Import Bandcamp tags (update local meta for filtering later)
```powershell
rbassist bandcamp-import .\bandcamp.csv rbassist\config.yml
```
6) Import existing Rekordbox My Tags (optional)
```powershell
rbassist import-mytags "D:\Exports\rekordbox.xml"
```
7) Import Rekordbox 6+ My Tags directly from the encrypted database (no XML export)
```powershell
rbassist rekordbox-import-mytags-db
```
Make sure Rekordbox is closed first; this opens `master.db` in read-only mode via `pyrekordbox` and merges MyTags into `data/meta.json` keyed by file path.

8) Auto-suggest My Tags for new tracks
```powershell
rbassist tags-auto --margin 0.05
# review suggestions, then apply:
rbassist tags-auto --margin 0.05 --apply
```

Want the GUI?
```powershell
rbassist ui
# or on Windows:
.\start.ps1
```

NiceGUI is the only maintained GUI path in this repo.

Data lives under `data/` (embeddings, index, meta.json). This repo is safe to sync to GitHub; keep your audio outside the repo.

### Keep your workspace tidy (Windows/Mac/Linux)

If your `rbassist` folder has accumulated ZIPs, scripts, shortcuts, or loose `rbassist.xml` exports (as in the screenshot you shared), you can normalize it without touching your music files:

```powershell
# Dry run in the folder that looks messy (no files are moved yet)
python scripts/organize_workspace.py C:\Users\you\Music\rbassist

# Apply the moves into subfolders like exports/, archives/, scripts/, notes/
python scripts/organize_workspace.py C:\Users\you\Music\rbassist --apply
```

Notes:
- The helper is conservative: it only scans the top level of the folder you pass (no recursion) so tracks inside artist/album directories are untouched.
- It routes common RB Assist artifacts into subfolders (`exports/` for `rbassist.xml`, `archives/` for `*.zip`, `scripts/` for `*.ps1`/`*.bat`, `notes/` for `*.txt`/`*.md`, `shortcuts/` for `.lnk`, `temp/` for `TEMP_*`).
- Keep your git clone under a clean path (e.g., `C:\src\rbassist`) and point the CLI/GUI at your music folder (e.g., `C:\Users\you\Music`) to avoid mixing source code with library artifacts.

## Checking which commits are ahead/behind

If you want to sanity-check whether your local clone, Visual Studio, and any forks are in sync:

1. Configure the remotes you want to compare (example):
   ```bash
   git remote add origin git@github.com:you/rbassist.git
   git remote add upstream git@github.com:original-author/rbassist.git
   ```
2. Use the helper to see how far your current branch is ahead/behind its remote twin (defaults to `origin`), or to compare a specific branch name:
   ```bash
   scripts/git-sync-status.sh           # compare against origin/<current-branch>
   scripts/git-sync-status.sh upstream  # compare against upstream/<current-branch>
   scripts/git-sync-status.sh origin main  # compare local main to origin/main even if checked out elsewhere
   ```
   The script fetches the remote, reports ahead/behind counts, and prints the latest commits on both sides so you can line up with ChatGPT/Codex/VS.
   - If you are in a detached HEAD state, pass the branch name explicitly (e.g., `scripts/git-sync-status.sh origin main`).
   - The helper expects a local branch to compare; if it warns that the branch is missing, create/switch to one or track the remote with `git switch -c <branch> --track <remote>/<branch>`.
3. To compare two specific commits/branches directly:
   ```bash
   git log --oneline --decorate --graph --boundary <lhs>.. <rhs>
   git diff <lhs>...<rhs>   # three-dot shows changes that would be merged
   ```
4. Run `git status -sb` to confirm the tracking branch and check for any untracked files that might explain differences across environments.
5. Share the `git rev-parse HEAD` hashes from each environment to confirm you are on the same commit.

## One-time setup for speed/features

Install CUDA build of PyTorch (NVIDIA GPU):
```powershell
pip install --upgrade --index-url https://download.pytorch.org/whl/cu121 torch torchvision torchaudio
```

Install nnAudio (optional; enables fast CQT paths used by chroma features):
```powershell
pip install nnAudio
```

Quick GPU sanity check in Python:
```python
import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))
```

## Troubleshooting messages

- `feature_extractor_cqt requires the libray 'nnAudio'`
  - nnAudio isn't installed; chroma-CQT falls back to the slower path. Install `nnAudio`.
- `Warning: Xing stream size off by more than 1%`
  - Harmless VBR MP3 header oddity. Ignore unless files consistently fail.
- `Illegal Audio-MPEG-Header ... Trying to resync ... Skipped N bytes`
  - Slightly corrupt MP3 frame. The decoder resynced; usually fine.

Optional repair for noisy MP3 headers (lossless re-mux):
```powershell
Get-ChildItem "D:\Music\YourCrate" -Recurse -Filter *.mp3 | ForEach-Object {
  ffmpeg -v warning -err_detect ignore_err -i $_.FullName -c copy ($_.DirectoryName + "\" + $_.BaseName + ".fixed.mp3")
}
```

## Auto-tag workflow

1. Export your Rekordbox collection (with My Tags) to XML.
2. Run `rbassist import-mytags path\to\rekordbox.xml` to mirror those tags into `config/tags.yml` and `data/meta.json`.
3. Run `rbassist tags-auto` to score untagged tracks against the learned centroids.
4. Add `--margin` to loosen the threshold or `--include-tagged` to re-score already tagged tracks.
5. When the preview looks good, append `--apply` to write the suggestions back to config + meta.
   - Extras: `--csv suggestions.csv` exports a review file; `--save-suggestions` stores the preview inside `data/meta.json`; `--prune-margin 0.1 --apply` removes existing tags that fall below the learned confidence.

Install ROCm build of PyTorch (AMD GPU on Linux):
```bash
pip install --upgrade --index-url https://download.pytorch.org/whl/rocm6.0 torch torchvision torchaudio
```
The ROCm wheels are published for Linux; on Windows and macOS, RB Assist will fall back to CPU unless CUDA (NVIDIA) or MPS support is available.

ROCm does not require a separate fork of RB Assist -- the same code and CLI work with either CUDA or ROCm builds of PyTorch. Use `--device cuda` or `--device rocm` to request the AMD GPU; the tool will fall back to CPU with a warning if ROCm is not available.
