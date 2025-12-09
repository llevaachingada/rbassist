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


def walk_audio(paths: Iterable[str]) -> list[str]:
    exts = {".wav", ".flac", ".mp3", ".m4a", ".aiff", ".aif"}
    files: list[str] = []
    for p in paths:
        pth = pathlib.Path(p)
        if pth.is_dir():
            for f in pth.rglob("*"):
                if f.suffix.lower() in exts:
                    files.append(str(f))
        else:
            if pth.suffix.lower() in exts:
                files.append(str(p))
    return sorted(files)


def load_meta() -> dict:
    """Load meta.json; if corrupt/empty, back it up and reset to defaults."""
    if not META.exists():
        return {"tracks": {}}  # path -> info
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
    """Choose best available device, preferring CUDA and warning loudly on CPU fallback.

    - Default / 'cuda': require a visible CUDA GPU; if not present, print a red warning
      so the user knows embeddings will not run on GPU.
    - 'cpu': explicitly request CPU (used only for debugging).
    - 'mps': use Apple MPS if available, otherwise warn and fall back to CPU.
    """
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
    # Unknown choice: treat as 'cuda' preference.
    if torch.cuda.is_available():
        return "cuda"
    console.print(f"[red]Unknown device '{user_choice}'; no GPU detected, using CPU.[/red]")
    return "cpu"

# ------------------------------
# Camelot helpers + rules
# ------------------------------

def _parse_camelot(k: str | None) -> tuple[int, str] | None:
    if not k: return None
    k = k.strip().upper()
    if len(k) < 2: return None
    letter = k[-1]
    try:
        num = int(k[:-1])
    except ValueError:
        return None
    if letter not in {"A", "B"}: return None
    num = ((num - 1) % 12) + 1  # clamp 1..12
    return num, letter


def _mod12(n: int) -> int:
    return ((n - 1) % 12) + 1


def camelot_relation(seed: str | None, cand: str | None) -> tuple[bool, str]:
    """Return (ok, rule_name) according to DJ Camelot mixing rules.
    Rules implemented:
      - Same Key
      - Camelot +/-1 (same letter)
      - Relative Major/Minor (same number, switch letter)
      - Raising energy +7 (same letter, up only)
      - Energy Boost ++ +2 (same letter, up only)
      - Mood Shifter: minor->Major (+3 & change letter) | Major->minor (-3 & change letter)
    If a key is missing or unparseable, return (True, "-") to avoid over-filtering.
    """
    s = _parse_camelot(seed)
    c = _parse_camelot(cand)
    if not s or not c:
        return True, "-"
    sn, sl = s
    cn, cl = c

    # Same key
    if sn == cn and sl == cl:
        return True, "Same Key"

    # Camelot neighbors +/-1 (same letter)
    if sl == cl and (cn == _mod12(sn + 1) or cn == _mod12(sn - 1)):
        return True, "Camelot +/-1"

    # Relative major/minor (same number, switch letter)
    if sn == cn and sl != cl:
        return True, "Relative Maj/Min"

    # Raising energy: +7 (UP only), same letter
    if sl == cl and cn == _mod12(sn + 7):
        return True, "Raising energy (+7)"

    # Energy Boost ++: +2 (UP only), same letter
    if sl == cl and cn == _mod12(sn + 2):
        return True, "Energy Boost ++ (+2)"

    # Mood Shifter: minor->Major (+3 & change letter)
    if sl == "A" and cl == "B" and cn == _mod12(sn + 3):
        return True, "Mood Shifter (min->Maj +3)"

    # Mood Shifter: Major->minor (-3 & change letter)
    if sl == "B" and cl == "A" and cn == _mod12(sn - 3):
        return True, "Mood Shifter (Maj->min -3)"

    return False, "-"


def camelot_compat(k1: str | None, k2: str | None) -> bool:
    ok, _ = camelot_relation(k1, k2)
    return ok


def tempo_match(bpm1: float | None, bpm2: float | None, pct: float = 6.0, allow_doubletime: bool = True) -> bool:
    if not bpm1 or not bpm2: return True
    if abs(bpm1 - bpm2) <= (pct / 100.0) * bpm1:
        return True
    if allow_doubletime:
        if abs(bpm1*2 - bpm2) <= (pct / 100.0) * (bpm1*2): return True
        if abs(bpm1/2 - bpm2) <= (pct / 100.0) * (bpm1/2): return True
    return False
import hashlib
from pathlib import Path

def file_sig(path: str, chunk_size: int = 8192) -> str:
    """
    Return a short signature (SHA1 hash) of the file contents.
    Use when you need a stable, content-true fingerprint (e.g., duplicate detection, cache keys)
    even if file timestamps are unreliable. Accurate but slower on large libraries.
    """
    h = hashlib.sha1()
   
    with open(Path(path), "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def file_sig_fast(path: str) -> str:
    """
    Fast, non-cryptographic file signature based on mtime and size.
    Use when you only need a quick change detector and can tolerate false positives after
    timestamp-only updates (e.g., cheap skip-logic in batch operations).
    """
    st = os.stat(path)
    return f"{st.st_mtime_ns}_{st.st_size}"


def current_file_sig(path: str) -> str:
    """
    Central hook for file signature strategy.
    Defaults to the accurate SHA1-based `file_sig` to avoid missing changes when files move
    or timestamps drift. If future performance needs favor speed over precision, swap to
    `file_sig_fast` here without changing call sites.
    """
    return file_sig(path)
