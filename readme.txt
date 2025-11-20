markdown
# rbassist (starter)

This is a simplified, no-stress starter you can push to GitHub and extend. It:
- builds **MERT-v1-330M** audio embeddings,
- indexes them with **HNSWLIB**,
- prints simple **recommendations**, and
- ingests **Bandcamp CSV tags** into a local meta store for future Rekordbox My Tags writes.

> Rekordbox XML export + My Tags DB writes are not in this minimal starter. We'll add them next.

Need a deeper overview? See [ABOUT.md](ABOUT.md) for the architecture snapshot, workflow, and contribution guide.

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
- `--device cuda` uses your NVIDIA GPU (after installing CUDA Torch below).
- `--num-workers` parallelizes audio decoding (4-8 typical). Model inference stays serialized for stability.
- `--duration-s` caps per-track analysis while testing.
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

## One-time setup for speed/features

Install CUDA build of PyTorch (GPU):
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

