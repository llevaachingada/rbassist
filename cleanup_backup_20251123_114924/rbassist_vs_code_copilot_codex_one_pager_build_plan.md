# rbassist × VS Code (Copilot/Codex) — one‑pager build plan

This is the shortest, most actionable path to get everything we’ve discussed wired up with GitHub Copilot Chat (aka “Codex”) inside Visual Studio Code.

---

## 0) Goal snapshot
**MVP**
- Build MERT‑v1‑330 embeddings for your audio, index with HNSW, return *weighted* recommendations with simple filters (tempo window, Camelot neighbors, double‑time), plus a first pass of **Harmonic + Rhythm + Drop alignment** signals.
- Streamlit GUI with a **Weights** panel (Harmonic, Rhythm, Drop, Samples, Bassline) and quick actions: **Embed (incremental)**, **Analyze BPM/Key**, **Build Index**, **Recommend**. Buttons for **Bandcamp Import**, **Dup‑check**, **CSV Mirror**.
- CLI parity for headless runs.

**Next**
- Samples & Bassline matching (onsets/peaks + low‑freq energy and MFCC/Chroma sketches), Rekordbox My Tags write‑back, XML/DB sync.

---

## 1) Repo sanity (expected layout)
```
rbassist/
  pyproject.toml
  rbassist/
    __init__.py
    versions.py
    cli.py
    embed.py
    recommend.py
    bandcamp.py
    gui.py            # (new)
    utils.py
  config/
    tags.yml
    recommend.yml
  data/               # auto‑created (embeddings, index, meta.json)
```

> If any files are missing, Copilot tasks below will generate them.

---

## 2) First‑time install (Windows, RTX)
**PowerShell — keep single‑line**
- Create venv + upgrade pip:  
`py -3.11 -m venv .venv; . .\.venv\Scripts\Activate.ps1; python -m pip install --upgrade pip`
- Install PyTorch CUDA (adjust CUDA version if needed):  
`pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121`
- Install package in editable mode with extras you’ll use today:  
`pip install -e .[web,ml,ann,audio]`

> Optional: `pip install -e .[stems]` if you want Demucs buttons active immediately.

---

## 3) VS Code setup files
Create these under `.vscode/`.

**settings.json**
```json
{
  "python.defaultInterpreterPath": ".venv/Scripts/python.exe",
  "editor.formatOnSave": true,
  "python.formatting.provider": "black",
  "python.analysis.typeCheckingMode": "basic"
}
```

**extensions.json** (recommended)
```json
{ "recommendations": [
  "GitHub.copilot-chat", "ms-python.python", "ms-python.vscode-pylance", "charliermarsh.ruff"
]}
```

**tasks.json** (one‑click commands)
```json
{
  "version": "2.0.0",
  "tasks": [
    {"label": "Embed (incremental)", "type": "shell", "command": "rbassist embed-build \"${input:audioRoot}\" --duration 120"},
    {"label": "Analyze BPM/Key", "type": "shell", "command": "python -m rbassist.tools.analyze_bpm_key \"${input:audioRoot}\""},
    {"label": "Build Index", "type": "shell", "command": "rbassist index"},
    {"label": "Recommend (seed)", "type": "shell", "command": "rbassist recommend \"${input:seed}\" --top 50"},
    {"label": "Run GUI", "type": "shell", "command": "python -m rbassist.gui"}
  ],
  "inputs": [
    {"id": "audioRoot", "type": "promptString", "description": "Folder or file (audio)"},
    {"id": "seed", "type": "promptString", "description": "Seed path or 'Artist - Title' substring"}
  ]
}
```

**launch.json** (F5 to open GUI)
```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "rbassist GUI",
      "type": "python",
      "request": "launch",
      "module": "rbassist.gui"
    }
  ]
}
```

---

## 4) Copilot Chat (Codex) work orders — paste line‑by‑line
Use these *exact* prompts in Copilot Chat inside VS Code. Each task is bite‑sized and testable.

**A. Create GUI skeleton (Streamlit)**
> Create `rbassist/gui.py` with a Streamlit app that:
> - has a sidebar with sliders: Harmonic, Rhythm, Drop, Samples, Bassline (0–1, default 0.4/0.3/0.2/0.05/0.05). Persist selections in `st.session_state`.
> - top buttons: “Embed (incremental)”, “Analyze BPM/Key”, “Build Index”, “Recommend”.
> - an **Add Music Folder** modal: text input for path, radio for mode (`baseline`/`stems`); if `stems` and `demucs` is missing, show a non‑blocking warning; save the selection and rerun.
> - a “Bandcamp Import” file uploader (CSV) + config selector, then runs the importer and shows a summary.
> - a “Dup‑check” button that surfaces likely dupes (same artist/title within ±1s duration or >0.98 audio similarity).
> - a “CSV Mirror” button that exports current recommendations to `data/recoYYYYMMDD_HHMM.csv` with columns: path, artist, title, bpm, key, dist, weights.
> - status panes for each long‑running action.

**B. Implement embedding**
> Create `rbassist/embed.py`:
> - `MertEmbedder(model="m-a-p/MERT-v1-330M", device=auto)` loads model + feature extractor with `trust_remote_code=True`; resample to 24kHz; if `duration_s>0`, crop; return 1024‑d float32 vector (mean over last hidden state).
> - `build_embeddings(paths, duration_s=120)` saves `data/embeddings/<stem>.npy`, updates `data/meta.json` with `{artist,title,key,bpm,embedding}` placeholders if missing.
> - Handle CUDA/CPU automatically; catch exceptions per file and continue.

**C. HNSW index + recommend**
> Create `rbassist/recommend.py`:
> - `build_index()` loads every `.npy` from meta, builds `hnswlib` index (`space=cosine`, `M=32`, `efConstruction=200`) and saves `data/index/hnsw.idx` plus `paths.json`.
> - `recommend(seed, *, top=50, tempo_pct=6.0, allow_doubletime=True, camelot_neighbors=True, weights=None)`:
>    1) resolve `seed` to a path via substring over path or `Artist - Title`.
>    2) knn query for `top+1`; skip self.
>    3) filter by simple **tempo_match** and **camelot_compat** (helpers in `utils.py`).
>    4) compute a **blended score** from sub‑signals (see section 5) using `weights` from GUI.
>    5) return a `pandas.DataFrame` and also pretty‑print a rich table.

**D. Bandcamp importer**
> Create `rbassist/bandcamp.py` with `import_bandcamp(csv_path, config_path, meta)`:
> - load YAML mapping (columns → fields); merge `genre/subgenre/tags` into `meta[tracks][path]` by matching `Artist - Title` (case‑insensitive), dedupe tags.

**E. CLI commands**
> Create `rbassist/cli.py` using Typer with commands: `embed-build`, `index`, `recommend`, `import-tags`.

**F. Glue utils**
> Create `rbassist/utils.py` helpers:
> - `walk_audio(paths)`; `load_meta()`/`save_meta()`; `camelot_compat(k1,k2)`; `tempo_match(bpm1,bpm2,pct,allow_doubletime)`; constants for `DATA`, `EMB`, `IDX`, `META` dirs.

**G. Wire GUI ↔ core**
> In `gui.py`, call `build_embeddings`, `analyze_bpm_key` (placeholder), `build_index`, `recommend(weights=...)`, and display a sortable table with “Copy to Clipboard” button.

---

## 5) The 3 starter signals (then Samples/Bassline)
Implement simple, fast versions first; refine later.

- **Harmonic**: key proximity via Camelot neighbors (exact match = 1.0; same number opposite mode = 0.9; neighboring number same mode = 0.85; else 0.5). Also penalize spectral centroid distance over 120s window (normalize 0–1).
- **Rhythm**: compare **onset strength envelope** (librosa.onset.onset_strength) downsampled to 2 Hz; compute cosine similarity.
- **Drop**: detect top‑3 local maxima of low‑frequency RMS (30–120 Hz band‑pass via FFT) and compare positions (seconds) with tolerance ±6s; score = fraction matched.
- **Blend**: `score = wH*H + wR*R + wD*D + wS*Samples + wB*Bassline` (the last two are 0 until implemented). Final distance = `(1 - score)` combined with HNSW cosine distance using a small mixing factor.

**Later**
- **Samples**: MFCC 20‑dim mean + variance over 1s hops; cosine similarity.
- **Bassline**: chroma‑cqt in 55–220Hz band + autocorrelation for periodicity; DTW alignment to get similarity.

---

## 6) Analyze BPM/Key (placeholder CLI)
Create a simple tool we can improve:
```python
# rbassist/tools/analyze_bpm_key.py
import sys, json, pathlib, librosa
from rbassist.utils import load_meta, save_meta

paths = []
root = pathlib.Path(sys.argv[1])
if root.is_dir():
    paths = [str(p) for p in root.rglob("*") if p.suffix.lower() in {".wav",".flac",".mp3",".m4a",".aiff",".aif"}]
else:
    paths = [str(root)]
meta = load_meta()
for p in paths:
    try:
        y, sr = librosa.load(p, sr=None, mono=True)
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        key = None  # TODO: lightweight key estimate
        info = meta.setdefault("tracks", {}).setdefault(p, {})
        info.setdefault("artist", pathlib.Path(p).stem.split(" - ")[0] if " - " in pathlib.Path(p).stem else "")
        info.setdefault("title", pathlib.Path(p).stem.split(" - ")[-1])
        info["bpm"] = float(tempo)
        info.setdefault("key", key)
    except Exception:
        pass
save_meta(meta)
print("BPM/Key updated for", len(paths), "files")
```

---

## 7) Streamlit UX spec (minimum)
- **Sidebar**: Folder selector(s), analysis mode; Weights (sliders), Filters (tempo ±%, allow double‑time, Camelot neighbors).
- **Main**: Action buttons row; results table with copy/export; activity log.
- **Notifications**: Non‑blocking warnings for missing Demucs or Torch CUDA; success toasts.

---

## 8) Testing & quality bar (quick wins)
- Unit‑ish tests for `camelot_compat`, `tempo_match`, and drop detector.
- A small `tests/audio/` with 3–5 short clips to keep CI fast.
- Ruff/Black on save; type hints in all new code.

---

## 9) Daily loop
1) Code: Run a Copilot prompt above → let it draft → review and edit.
2) Run: `Tasks: Run Task → Run GUI` or CLI tasks.
3) Commit: meaningful messages; push to GitHub.
4) Iterate: adjust weights in GUI; export CSV mirror; write notes.

---

## 10) Handy commands (1‑liners)
- Re‑install after edits:  
`pip install -e .`
- Build embeddings for a folder:  
`rbassist embed-build "D:\Music\YourCrate" --duration 120`
- Build index:  
`rbassist index`
- Recommend by seed:  
`rbassist recommend "Artist - Title" --top 25`

---

### That’s it.
Start with Section 4 (Copilot work orders) and run Section 3 tasks as you go. The GUI will let you feel the weights immediately; the CLI keeps headless runs simple. 

