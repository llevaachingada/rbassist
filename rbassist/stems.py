from __future__ import annotations

import pathlib
import shutil
import subprocess
import time
from typing import Dict, List

from .utils import DATA, console

STEMS = DATA / "stems"
STEMS.mkdir(parents=True, exist_ok=True)


def have_demucs() -> bool:
    return shutil.which("demucs") is not None


def split_stems(path: str, model: str = "htdemucs") -> dict[str, str]:
    """
    Split a track into stems with Demucs. Returns mapping of stem->wav path.
    Caches to data/stems/<track>_<model>/<stem>.wav
    """
    p = pathlib.Path(path).resolve()
    outdir = STEMS / (p.stem + f"_{model}")
    cached = {k: str(outdir / f"{k}.wav") for k in ("vocals", "drums", "bass", "other")}
    if all((outdir / f"{k}.wav").exists() for k in ("vocals", "drums", "bass", "other")):
        return {k: v for k, v in cached.items() if pathlib.Path(v).exists()}
    if not have_demucs():
        raise RuntimeError("Demucs not installed. Install with: pip install demucs")

    outdir.mkdir(parents=True, exist_ok=True)
    cmd = ["demucs", "-n", model, "-o", str(outdir), str(p)]
    console.print(f"[cyan]Demucs split -> {p.name}")
    subprocess.run(cmd, check=True)

    # Normalize produced file names into our fixed names
    mapping: dict[str, str] = {}
    for f in outdir.rglob("*.wav"):
        low = f.name.lower()
        for k in ("vocals", "drums", "bass", "other"):
            if k in low:
                target = outdir / f"{k}.wav"
                if f != target:
                    try:
                        target.write_bytes(f.read_bytes())
                    except Exception:
                        pass
                mapping[k] = str(target)
    return mapping


def cached_for_path(path: str, model: str = "htdemucs") -> bool:
    p = pathlib.Path(path)
    slug = p.stem + f"_{model}"
    outdir = STEMS / slug
    return outdir.exists() and all((outdir / f"{stem}.wav").exists() for stem in ("vocals", "drums", "bass", "other"))


def list_cache() -> List[Dict[str, str]]:
    entries: List[Dict[str, str]] = []
    if not STEMS.exists():
        return entries
    for folder in sorted(STEMS.iterdir()):
        if not folder.is_dir():
            continue
        wavs = list(folder.glob("*.wav"))
        stems_present = sorted(f.stem for f in wavs)
        updated = time.strftime("%Y-%m-%d %H:%M", time.localtime(folder.stat().st_mtime))
        if "_" in folder.name:
            source, model = folder.name.rsplit("_", 1)
        else:
            source, model = folder.name, ""
        entries.append(
            {
                "cache": folder.name,
                "source": source,
                "model": model or "?",
                "stems": ", ".join(stems_present) if stems_present else "(empty)",
                "count": str(len(stems_present)),
                "path": str(folder),
                "updated": updated,
            }
        )
    return entries


def clear_cache(names: List[str] | None = None) -> int:
    removed = 0
    if names:
        targets = [STEMS / name for name in names]
    else:
        targets = list(STEMS.iterdir()) if STEMS.exists() else []
    for target in targets:
        if target.exists() and target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
            removed += 1
    return removed
