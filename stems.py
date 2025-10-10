from __future__ import annotations
import pathlib, subprocess, shutil
from .utils import console, DATA

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

