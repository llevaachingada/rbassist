markdown
# rbassist (starter)

This is a simplified, no-stress starter you can push to GitHub and extend. It:
- builds **MERT-v1-330M** audio embeddings,
- indexes them with **HNSWLIB**,
- prints simple **recommendations**, and
- ingests **Bandcamp CSV tags** into a local meta store for future Rekordbox My Tags writes.

> Rekordbox XML export + My Tags DB writes are not in this minimal starter. We’ll add them next.

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
rbassist embed-build "D:\\Music\\YourCrate"
```
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
rbassist import-tags bandcamp.csv
```

Data lives under `data/` (embeddings, index, meta.json). This repo is safe to sync to GitHub; keep your audio outside the repo.
