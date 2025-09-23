from __future__ import annotations
import os, json, math, pathlib
from typing import Iterable
from rich.console import Console

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
    if META.exists():
        return json.loads(META.read_text("utf-8"))
    return {"tracks": {}}  # path -> info

def save_meta(meta: dict) -> None:
    META.write_text(json.dumps(meta, indent=2), encoding="utf-8")

def camelot_compat(k1: str | None, k2: str | None) -> bool:
    if not k1 or not k2:
        return True
    try:
        n1, m1 = int(k1[:-1]), k1[-1].upper()
        n2, m2 = int(k2[:-1]), k2[-1].upper()
        if k1 == k2: return True
        if m1 == m2 and abs(n1 - n2) == 1: return True
        if n1 == n2 and m1 != m2: return True
    except Exception:
        return True
    return False

def tempo_match(bpm1: float | None, bpm2: float | None, pct: float = 6.0, allow_doubletime: bool = True) -> bool:
    if not bpm1 or not bpm2: return True
    if abs(bpm1 - bpm2) <= (pct / 100.0) * bpm1: return True
    if allow_doubletime:
        if abs(bpm1*2 - bpm2) <= (pct/100.0) * (bpm1*2): return True
        if abs(bpm1/2 - bpm2) <= (pct/100.0) * (bpm1/2): return True
    return False
