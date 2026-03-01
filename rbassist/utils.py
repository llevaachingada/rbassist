from __future__ import annotations
import os, json, math, pathlib
from typing import Iterable
from datetime import datetime
from rich.console import Console
import torch

console = Console()
ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
EMB = DATA / "embeddings"
IDX = DATA / "index"
META = DATA / "meta.json"

for p in (DATA, EMB, IDX):
    p.mkdir(parents=True, exist_ok=True)

AUDIO_EXTS = {".wav", ".flac", ".mp3", ".m4a", ".aiff", ".aif"}
JUNK_PATH_PARTS = {"__MACOSX"}


def is_audio_path(path: str | pathlib.Path) -> bool:
    return pathlib.Path(path).suffix.lower() in AUDIO_EXTS


def is_junk_path(path: str | pathlib.Path) -> bool:
    p = pathlib.Path(path)
    if p.name.startswith("._"):
        return True
    return any(part in JUNK_PATH_PARTS for part in p.parts)


def normalize_path_string(path: str | pathlib.Path) -> str:
    text = str(path).strip().replace('\\', '/')
    if len(text) >= 2 and text[1] == ':':
        text = text[0].upper() + text[1:]
    return text.rstrip('/')


def resolve_track_path(path: str | pathlib.Path, *, base_dir: pathlib.Path | None = None) -> pathlib.Path:
    p = pathlib.Path(str(path).strip()).expanduser()
    if not p.is_absolute():
        root = base_dir or ROOT
        p = (root / p).resolve()
    else:
        p = p.resolve()
    return p


def make_path_aliases(path: str | pathlib.Path) -> set[str]:
    aliases = {str(path).strip(), normalize_path_string(path)}
    try:
        resolved = resolve_track_path(path)
        aliases.add(str(resolved))
        aliases.add(normalize_path_string(resolved))
    except Exception:
        pass
    return {a for a in aliases if a}


def walk_audio(paths: Iterable[str]) -> list[str]:
    files: list[str] = []
    for p in paths:
        pth = pathlib.Path(p)
        if pth.is_dir():
            for f in pth.rglob('*'):
                if is_audio_path(f) and not is_junk_path(f):
                    files.append(str(f))
        else:
            if is_audio_path(pth) and not is_junk_path(pth):
                files.append(str(p))
    return sorted(files)


def read_paths_file(paths_file: str | pathlib.Path) -> list[str]:
    """Read one path per line from a text file.

    - Ignores blank lines and '#' comments
    - Resolves relative paths against the paths file directory
    """
    pfile = pathlib.Path(paths_file).expanduser()
    raw = pfile.read_text(encoding="utf-8")
    out: list[str] = []
    base = pfile.parent
    for line in raw.splitlines():
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        if (entry.startswith('"') and entry.endswith('"')) or (entry.startswith("'") and entry.endswith("'")):
            entry = entry[1:-1].strip()
        if not entry:
            continue
        p = pathlib.Path(entry)
        if not p.is_absolute():
            p = (base / p).resolve()
        out.append(str(p))
    return out


def load_meta() -> dict:
    """Load meta.json; if corrupt/empty, back it up and reset to defaults."""
    if not META.exists():
        return {"tracks": {}}
    try:
        return json.loads(META.read_text("utf-8"))
    except Exception:
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup = META.with_name(f"meta.json.corrupt_{ts}")
        try:
            backup.write_text(META.read_text("utf-8"), encoding="utf-8")
        except Exception:
            pass
        return {"tracks": {}}


def save_meta(meta: dict) -> None:
    META.write_text(json.dumps(meta, indent=2), encoding="utf-8")


class MetaManager:
    """Lightweight helper to batch meta writes."""

    def __init__(self, meta: dict | None = None):
        self.meta = meta if meta is not None else load_meta()
        self.dirty = False

    def mark_dirty(self) -> None:
        self.dirty = True

    def flush(self) -> None:
        if self.dirty:
            save_meta(self.meta)
            self.dirty = False

    def __enter__(self) -> "MetaManager":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.flush()


def flush_meta(manager: MetaManager) -> None:
    """Explicit flush hook for MetaManager."""
    manager.flush()


def pick_device(user_choice: str | None = None) -> str:
    """Choose best available device, preferring CUDA and warning loudly on CPU fallback."""
    choice = (user_choice or "cuda").lower()
    if choice == "cpu":
        return "cpu"
    if choice in {"cuda", "rocm"}:
        if torch.cuda.is_available():
            return "cuda"
        console.print("[red]CUDA requested but no GPU is available; falling back to CPU.[/red]")
        return "cpu"
    if choice == "mps":
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
        console.print("[red]MPS requested but not available; falling back to CPU.[/red]")
        return "cpu"
    if torch.cuda.is_available():
        return "cuda"
    console.print(f"[red]Unknown device '{user_choice}'; no GPU detected, using CPU.[/red]")
    return "cpu"


def _parse_camelot(k: str | None) -> tuple[int, str] | None:
    if not k:
        return None
    k = k.strip().upper()
    if len(k) < 2:
        return None
    letter = k[-1]
    try:
        num = int(k[:-1])
    except ValueError:
        return None
    if letter not in {"A", "B"}:
        return None
    num = ((num - 1) % 12) + 1
    return num, letter


def _mod12(n: int) -> int:
    return ((n - 1) % 12) + 1


def camelot_relation(seed: str | None, cand: str | None) -> tuple[bool, str]:
    s = _parse_camelot(seed)
    c = _parse_camelot(cand)
    if not s or not c:
        return True, "-"
    sn, sl = s
    cn, cl = c
    if sn == cn and sl == cl:
        return True, "Same Key"
    if sl == cl and (cn == _mod12(sn + 1) or cn == _mod12(sn - 1)):
        return True, "Camelot +/-1"
    if sn == cn and sl != cl:
        return True, "Relative Maj/Min"
    if sl == cl and cn == _mod12(sn + 7):
        return True, "Raising energy (+7)"
    if sl == cl and cn == _mod12(sn + 2):
        return True, "Energy Boost ++ (+2)"
    if sl == "A" and cl == "B" and cn == _mod12(sn + 3):
        return True, "Mood Shifter (min->Maj +3)"
    if sl == "B" and cl == "A" and cn == _mod12(sn - 3):
        return True, "Mood Shifter (Maj->min -3)"
    return False, "-"


def camelot_compat(k1: str | None, k2: str | None) -> bool:
    ok, _ = camelot_relation(k1, k2)
    return ok


def tempo_match(bpm1: float | None, bpm2: float | None, pct: float = 6.0, allow_doubletime: bool = True) -> bool:
    if not bpm1 or not bpm2:
        return True
    if abs(bpm1 - bpm2) <= (pct / 100.0) * bpm1:
        return True
    if allow_doubletime:
        if abs(bpm1 * 2 - bpm2) <= (pct / 100.0) * (bpm1 * 2):
            return True
        if abs(bpm1 / 2 - bpm2) <= (pct / 100.0) * (bpm1 / 2):
            return True
    return False

import hashlib
from pathlib import Path


def file_sig(path: str, chunk_size: int = 8192) -> str:
    h = hashlib.sha1()
    with open(Path(path), "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def file_sig_fast(path: str) -> str:
    st = os.stat(path)
    return f"{st.st_mtime_ns}_{st.st_size}"


def current_file_sig(path: str) -> str:
    return file_sig(path)
