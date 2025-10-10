from __future__ import annotations
import numpy as np
import librosa


def _bars_to_seconds(bars: int, bpm: float) -> float:
    return (bars * 4.0) * (60.0 / bpm)


def detect_drop(y: np.ndarray, sr: int) -> float:
    onset_env = librosa.onset.onset_strength(y=y, sr=sr, aggregate=np.median)
    times = librosa.times_like(onset_env, sr=sr)
    mask = times > 15.0
    if not np.any(mask):
        return float(times[np.argmax(onset_env)])
    idx = np.argmax(onset_env[mask])
    return float(times[mask][idx])


def propose_cues(y: np.ndarray, sr: int, bpm: float) -> list[dict]:
    loop_bars = 16 if bpm >= 122 else 8

    drop_t = detect_drop(y, sr)
    c_end = max(0.0, drop_t - 0.1)
    c_start = max(0.0, c_end - _bars_to_seconds(loop_bars, bpm))

    onset = librosa.onset.onset_strength(y=y, sr=sr)
    times = librosa.times_like(onset, sr=sr)
    first_kick_t = float(times[np.argmax(onset > np.percentile(onset, 75))]) if onset.size else 0.0

    a_start = max(0.0, first_kick_t + _bars_to_seconds(2, bpm))
    a_end = a_start + _bars_to_seconds(loop_bars, bpm)

    b_center = a_end + (c_start - a_end) * 0.5 if c_start > a_end else a_end + _bars_to_seconds(8, bpm)
    b_start = max(0.0, b_center - _bars_to_seconds(loop_bars / 2, bpm))
    b_end = b_start + _bars_to_seconds(loop_bars, bpm)

    cues = [
        {"name": "A", "type": 0, "num": -1, "start": a_start, "end": a_end},
        {"name": "B", "type": 0, "num": -1, "start": b_start, "end": b_end},
        {"name": "C", "type": 0, "num": -1, "start": c_start, "end": c_end},
        {"name": "D", "type": 0, "num": -1, "start": drop_t, "end": drop_t},
        {"name": "Drop (Mem)", "type": 1, "num": -1, "start": drop_t, "end": drop_t},
    ]

    mixout = drop_t + _bars_to_seconds(32, bpm)
    cues.append({"name": "Mix-out", "type": 1, "num": -1, "start": mixout, "end": mixout})
    return cues

