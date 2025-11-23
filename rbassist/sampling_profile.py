from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import yaml

try:
    from scipy.signal import find_peaks
except Exception:
    find_peaks = None  # type: ignore

try:
    import librosa
except Exception:
    librosa = None


@dataclass
class SamplingParams:
    start_skip_s: float = 10
    main_len_s: float = 90
    tail_region: float = 0.70
    n_tail: int = 2
    tail_len_s: float = 30
    min_gap_s: float = 10
    force_tail_in_last_60s: bool = True
    energy_onset_align: bool = True


def _feature_curves(y: np.ndarray, sr: int, frame: int = 4096, hop: int = 1024):
    if librosa is None:
        raise RuntimeError("librosa required for sampling features")
    onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    times = librosa.times_like(onset, sr=sr, hop_length=hop)
    return times, onset


def _pick_main_start(times: np.ndarray, onset: np.ndarray, duration_s: float, p: SamplingParams) -> float:
    if librosa is None or not p.energy_onset_align or find_peaks is None:
        return min(p.start_skip_s, max(0.0, duration_s - 5.0))
    x = (onset - onset.min()) / (onset.ptp() + 1e-9)
    mask = times >= p.start_skip_s
    t_sel = times[mask]
    x_sel = x[mask]
    thr = np.percentile(x_sel, 75)
    step = np.median(np.diff(t_sel)) if len(t_sel) > 1 else 0.1
    dist = max(1, int(5 / step))
    peaks, _ = find_peaks(x_sel, height=thr, distance=dist)
    idx = peaks[0] if len(peaks) else int(np.argmax(x_sel))
    return float(t_sel[idx])


def _pick_tails(times: np.ndarray, onset: np.ndarray, duration_s: float, p: SamplingParams):
    if find_peaks is None:
        raise RuntimeError("scipy required for sampling features")
    start_t = duration_s * p.tail_region
    mask = times >= start_t
    t_sel = times[mask]
    x = onset[mask]
    x = (x - x.min()) / (x.ptp() + 1e-9)
    step = np.median(np.diff(t_sel)) if len(t_sel) > 1 else 0.1
    dist = max(1, int(p.min_gap_s / step))
    peaks, props = find_peaks(x, height=np.percentile(x, 60), distance=dist)
    ts = list(t_sel[peaks])
    hs = list(props.get("peak_heights", []))
    order = np.argsort(hs)[::-1]
    out = []
    for i in order:
        t0 = float(min(ts[i], duration_s - p.tail_len_s - 1.0))
        if all(abs(t0 - s) >= p.min_gap_s for s, _ in out):
            out.append((t0, t0 + p.tail_len_s))
        if len(out) >= p.n_tail:
            break
    if p.force_tail_in_last_60s and duration_s > 90 and out:
        need = all(t0 < duration_s - 60 for t0, _ in out)
        if need:
            t0 = max(duration_s - 60, duration_s - p.tail_len_s - 1)
            out[-1] = (t0, t0 + p.tail_len_s)
    return out


def pick_windows(audio_path: str, params: SamplingParams) -> list[tuple[float, float]]:
    if librosa is None:
        raise RuntimeError("librosa required for sampling features")
    y, sr = librosa.load(audio_path, sr=11025, mono=True)
    duration_s = len(y) / sr
    times, onset = _feature_curves(y, sr)
    s0 = _pick_main_start(times, onset, duration_s, params)
    e0 = min(s0 + params.main_len_s, max(0.0, duration_s - 5.0))
    tails = _pick_tails(times, onset, duration_s, params)
    return [(s0, e0), *tails]


def load_sampling_params(profile: str, config_path: Optional[str | Path] = None) -> SamplingParams:
    """Load SamplingParams from config/sampling.yml (or provided path)."""
    cfg_path = Path(config_path) if config_path else Path(__file__).resolve().parents[1] / "config" / "sampling.yml"
    data: Dict[str, Any] = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    profiles = data.get("profiles", {})
    default_name = data.get("sampling_profile")
    name = profile or default_name
    if not name or name not in profiles:
        raise ValueError(f"Sampling profile '{name}' not found in {cfg_path}")
    cfg = profiles[name]
    return SamplingParams(
        start_skip_s=float(cfg.get("start_skip_s", 10)),
        main_len_s=float(cfg.get("main_len_s", 90)),
        tail_region=float(cfg.get("tail_region", 0.70)),
        n_tail=int(cfg.get("n_tail", 2)),
        tail_len_s=float(cfg.get("tail_len_s", 30)),
        min_gap_s=float(cfg.get("min_gap_s", 10)),
        force_tail_in_last_60s=bool(cfg.get("force_tail_in_last_60s", True)),
        energy_onset_align=bool(cfg.get("energy_onset_align", True)),
    )
