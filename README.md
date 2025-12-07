REK0RDB0X TOOLS that DJS need ~ compiled by DJ Dumpsterfire aka HUNTER S

Can we build local repositories better and stronger than AlphaTheta's failing software platform?

Pioneer hardware is the golden standard for a reason, but the software backend has been failing us working DJS in the field.
Is there a world where open source players and hardware can be fed by locally customized software? 

rbassist is a Windows-first toolchain for DJs who want AI-assisted metadata, fast recommendations, and streamlined Rekordbox workflows without depending on cloud services. The repo bundles a Typer CLI, Streamlit GUI, and data pipelines that run locally on your GPU.

### Highlights

- Builds embeddings with `m-a-p/MERT-v1-330M` and caches them as `.npy` vectors.
- Indexes embeddings via HNSWLIB for fast similarity lookups (`rbassist recommend`, GUI recommendations panel).
- Imports Bandcamp CSV tags and Rekordbox My Tags, storing them in `config/tags.yml` + `data/meta.json`.
- Analyzes BPM, Camelot key, cues, RMS/sample heuristics, and bass contours.
- Offers Typer commands for embed/analyze/index/tags-auto/export-xml plus GUI equivalents (Streamlit).

### Architecture Snapshot

| Layer | Tech | Notes |
| --- | --- | --- |
| Embedding | PyTorch + Transformers | MERT-v1-330M, CUDA/ROCm optional. |
| Index/Search | HNSWLIB | Cosine ANN queries for recommendations. |
| CLI | Typer | Commands under `rbassist` entry point. |
| GUI | Streamlit | `rbassist/webapp.py`. |
| Metadata | JSON/YAML | `data/meta.json`, `config/tags.yml`, `data/index`. |

### Typical Workflow

1. `rbassist embed "D:\Music\YourCrate" --duration-s 60 --device cuda --num-workers 4`
2. `rbassist analyze "D:\Music\YourCrate" --duration-s 60`
3. `rbassist index`
4. `rbassist recommend "Artist - Track" --top 25` or launch the GUI via `streamlit run rbassist/webapp.py`.
5. `rbassist tags-auto --margin 0.05 --apply` (or edit via GUI Auto Tag Suggestions).
6. `rbassist export-xml --out rbassist.xml` for Rekordbox import.

### Getting Involved

- **Issues/ideas**: file them on GitHub with hardware + command logs.
- **Pull requests**: follow existing Typer/Streamlit patterns, document new flags, add tests when touching analyze/embed/tagstore logic.
- **Support**: share DJ workflow needs in discussions; the more context, the better the tuning advice.

## Install (Windows 11, RTX 4060)

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
2) Build the HNSW index
```powershell
rbassist index
```
3) Get recommendations for a seed track (path or substring)
```powershell
rbassist recommend "Artist - Title" --top 25
```
4) Import Bandcamp tags (update local meta for filtering later)
```powershell
rbassist bandcamp-import .\bandcamp.csv rbassist\config.yml
```
5) Import existing Rekordbox My Tags (optional)
```powershell
rbassist import-mytags "D:\Exports\rekordbox.xml"
```
6) Auto-suggest My Tags for new tracks
```powershell
rbassist tags-auto --margin 0.05
# review suggestions, then apply:
rbassist tags-auto --margin 0.05 --apply
```

Want a browser UI instead of the old Tk window? Install the web extras and launch Streamlit directly:
```powershell
pip install "rbassist[web]"
rbassist-gui  # launches the Streamlit app (same as `rbassist web`)
```

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
