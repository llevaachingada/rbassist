from __future__ import annotations
import numpy as np


def measure_lufs(path: str) -> float:
    import pyloudnorm as pyln  # type: ignore
    import soundfile as sf

    audio, sr = sf.read(path, always_2d=False)
    if getattr(audio, "ndim", 1) > 1:
        audio = np.mean(audio, axis=1)
    meter = pyln.Meter(sr)
    return float(meter.integrated_loudness(audio))


def write_replaygain_tags(path: str, track_gain_db: float, track_peak: float = 1.0) -> None:
    try:
        from mutagen import File as MFile  # type: ignore
    except Exception:
        return
    mf = MFile(path)
    if mf is None:
        return
    mf["replaygain_track_gain"] = f"{track_gain_db:.2f} dB"
    mf["replaygain_track_peak"] = f"{track_peak:.6f}"
    mf.save()


def normalize_tag(path: str, target_lufs: float = -11.0) -> float:
    cur = measure_lufs(path)
    gain = float(target_lufs - cur)
    write_replaygain_tags(path, gain)
    return gain

