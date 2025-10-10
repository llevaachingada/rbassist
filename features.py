from __future__ import annotations

import numpy as np
import librosa
from typing import Tuple


def _stft_bandpass(S: np.ndarray, sr: int, hop: int, fmin: float, fmax: float) -> np.ndarray:
    freqs = np.linspace(0, sr / 2, S.shape[0])
    mask = (freqs >= fmin) & (freqs <= fmax)
    return S[mask, :]


def samples_score(y: np.ndarray, sr: int) -> float:
    """Heuristic score in [0,1] for presence of midrange 'samples' around break sections."""
    hop = 512
    S = librosa.stft(y, n_fft=2048, hop_length=hop)
    Sm = _stft_bandpass(S, sr, hop, 500.0, 4000.0)
    onset_env = librosa.onset.onset_strength(S=np.abs(Sm), sr=sr, hop_length=hop)
    rms = librosa.feature.rms(S=np.abs(S), hop_length=hop).flatten()
    # smooth rms via harmonic component proxy
    rms_s = librosa.util.normalize(librosa.effects.harmonic(rms, margin=3.0))
    t = librosa.frames_to_time(np.arange(len(onset_env)), sr=sr, hop_length=hop)

    # candidate breaks = local minima below 40th percentile
    thresh = np.percentile(rms_s, 40)
    dif = np.diff(rms_s)
    mins = np.where((rms_s < thresh) & (np.r_[True, dif < 0] & np.r_[dif > 0, True]))[0]
    if mins.size == 0:
        return 0.0
    pick = np.argsort(rms_s[mins])[:2]
    break_frames = mins[pick]

    def count_onsets(center_f: int) -> int:
        w = int(librosa.time_to_frames(8.0, sr=sr, hop_length=hop))
        lo, hi = max(0, center_f - w), min(len(onset_env), center_f + w)
        med = np.median(onset_env)
        return int(np.sum(onset_env[lo:hi] > med))

    total = sum(count_onsets(bf) for bf in break_frames)
    dur = float(t[-1]) if len(t) else 180.0
    norm = total / max(1.0, dur / 180.0)
    alpha = 8.0
    score = float(1.0 - np.exp(-norm / alpha))
    return float(np.clip(score, 0.0, 1.0))


def bass_contour(y: np.ndarray, sr: int) -> Tuple[np.ndarray, float]:
    """Return (contour_hz over time, reliability 0..1) using dominant low-band frequency per frame."""
    hop = 512
    S = librosa.stft(y, n_fft=4096, hop_length=hop, window="hann")
    mag = np.abs(S)
    freqs = np.linspace(0, sr / 2, mag.shape[0])
    band = (freqs >= 40.0) & (freqs <= 200.0)
    Mb = mag[band, :]
    fb = freqs[band]
    idx = np.argmax(Mb, axis=0)
    contour_hz = fb[idx]
    prom = (Mb.max(axis=0) / (np.median(Mb, axis=0) + 1e-6))
    rel = float(np.clip(np.median(prom) / 5.0, 0.0, 1.0))
    # median smoothing via nearest-neighbors filter
    contour_hz = librosa.decompose.nn_filter(contour_hz[None, :], aggregate=np.median, metric="cosine")[0]
    return contour_hz.astype(np.float32), rel


def bass_similarity(seed_contour: np.ndarray, cand_contour: np.ndarray) -> float:
    """Similarity in [0,1] via DTW on log-Hz contours."""
    if seed_contour.size == 0 or cand_contour.size == 0:
        return 0.0
    def prep(c: np.ndarray) -> np.ndarray:
        c = np.log(np.clip(c, 1.0, None))
        return librosa.util.fix_length(c, size=512)
    a, b = prep(seed_contour), prep(cand_contour)
    D, wp = librosa.sequence.dtw(a[:, None], b[:, None], metric="euclidean")
    d = float(D[-1, -1]) / max(1, len(wp))
    return float(np.exp(-d / 2.0))

