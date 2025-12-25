"""Beatgrid estimation (fixed or dynamic) with optional tempo drift detection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Optional, Sequence, Tuple

import numpy as np
import librosa

from .utils import console, MetaManager, walk_audio


@dataclass
class BeatgridConfig:
    """Configuration for beatgrid analysis."""

    mode: str = "fixed"  # "fixed" or "dynamic"
    drift_pct: float = 1.5  # trigger new segment if local tempo drifts by this percent
    bars_window: int = 16  # bars to measure drift over (assume 4/4 -> bars*4 beats)
    duration_s: int = 0  # 0 = full track; otherwise truncate for speed
    hop_length: int = 512
    backend: str = "auto"  # auto | beatnet | librosa
    model_id: int = 3  # BeatNet model selector
    device: Optional[str] = None  # cuda|cpu|auto


class BeatBackend:
    def run(self, path: str, cfg: BeatgridConfig) -> Tuple[np.ndarray, np.ndarray, float]:
        """Return (beat_times, downbeat_times, confidence)."""
        raise NotImplementedError


class LibrosaBackend(BeatBackend):
    def run(self, path: str, cfg: BeatgridConfig) -> Tuple[np.ndarray, np.ndarray, float]:
        y, sr = librosa.load(path, sr=None, mono=True, duration=cfg.duration_s if cfg.duration_s > 0 else None)
        if y.size == 0 or sr is None or sr <= 0:
            return np.asarray([]), np.asarray([]), 0.0
        onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=cfg.hop_length)
        tempo, beat_frames = librosa.beat.beat_track(
            onset_envelope=onset_env,
            sr=sr,
            hop_length=cfg.hop_length,
            units="frames",
        )
        beat_times = librosa.frames_to_time(beat_frames, sr=sr, hop_length=cfg.hop_length)
        conf = _confidence(onset_env, beat_frames)
        return beat_times, np.asarray([]), conf


class BeatNetBackend(BeatBackend):
    def __init__(self, model_id: int = 3, device: str | None = None):
        self.model_id = model_id
        self.device = device

    def run(self, path: str, cfg: BeatgridConfig) -> Tuple[np.ndarray, np.ndarray, float]:
        # Import lazily to avoid hard failure when dependency is absent.
        try:
            from BeatNet.BeatNet import BeatNet as BN  # type: ignore
        except Exception as e:
            raise RuntimeError(f"BeatNet unavailable: {e}")
        # Prefer CUDA if available
        dev = (cfg.device or self.device or "auto").lower()
        try:
            import torch

            if dev in {"auto", "cuda"} and torch.cuda.is_available():
                dev = "cuda"
            else:
                dev = "cpu"
        except Exception:
            dev = "cpu"
        try:
            bn = BN(model=self.model_id, mode="offline", inference_model="DBN", device=dev)
            out = bn.process(audio_path=path)
        except Exception as e:
            raise RuntimeError(f"BeatNet failed: {e}")
        if out is None or len(out) == 0:
            return np.asarray([]), np.asarray([]), 0.0
        arr = np.asarray(out)
        beat_times = arr[:, 0].astype(float)
        downbeats = beat_times[arr[:, 1] > 0] if arr.shape[1] > 1 else np.asarray([])
        return beat_times, downbeats, 1.0


def _pick_backend(cfg: BeatgridConfig) -> Tuple[BeatBackend, list[str]]:
    warnings: list[str] = []
    backend = cfg.backend.lower()
    if backend in {"auto", "beatnet"}:
        try:
            return BeatNetBackend(model_id=cfg.model_id, device=cfg.device), warnings
        except Exception as e:
            warnings.append(str(e))
            if backend == "beatnet":
                raise
    return LibrosaBackend(), warnings


def _bpm_from_intervals(intervals: np.ndarray) -> float:
    if intervals.size == 0:
        return 0.0
    med = np.median(intervals)
    if med <= 0:
        return 0.0
    return float(60.0 / med)


def _segment_beats(
    beat_times: np.ndarray,
    cfg: BeatgridConfig,
    downbeat_times: Optional[np.ndarray] = None,
) -> list[dict]:
    """Split beat sequence into tempo segments when drift exceeds threshold."""
    if beat_times.size == 0:
        return []

    # Compute base BPM from median inter-beat interval
    intervals = np.diff(beat_times)
    base_bpm = _bpm_from_intervals(intervals)
    if cfg.mode == "fixed" or base_bpm <= 0:
        return [
            {"inizio_sec": 0.0, "bpm": base_bpm if base_bpm > 0 else 0.0, "metro": "4/4", "battito": 1}
        ]

    beats_per_win = max(4, cfg.bars_window * 4)
    segments: list[dict] = []

    start_idx = 0
    # initial BPM using first window or whole set if short
    win_end = min(len(beat_times), beats_per_win)
    seg_bpm = _bpm_from_intervals(np.diff(beat_times[start_idx:win_end]))
    battito = 1

    i = beats_per_win
    while i < len(beat_times):
        window = beat_times[max(0, i - beats_per_win) : i]
        local_bpm = _bpm_from_intervals(np.diff(window))
        if seg_bpm > 0 and abs(local_bpm - seg_bpm) / seg_bpm * 100.0 > cfg.drift_pct:
            segments.append(
                {"inizio_sec": float(beat_times[start_idx]), "bpm": seg_bpm, "metro": "4/4", "battito": battito}
            )
            start_idx = max(0, i - beats_per_win)
            seg_bpm = local_bpm
            battito = 1
        i += 1

    # Final segment
    segments.append(
        {"inizio_sec": float(beat_times[start_idx]), "bpm": seg_bpm, "metro": "4/4", "battito": battito}
    )
    return segments


def _confidence(onset_env: np.ndarray, beat_frames: np.ndarray) -> float:
    """Crude confidence metric: mean onset strength at beat positions / global max."""
    if onset_env.size == 0:
        return 0.0
    if beat_frames.size == 0:
        return 0.0
    vals = []
    for f in beat_frames:
        if 0 <= f < len(onset_env):
            vals.append(float(onset_env[f]))
    if not vals:
        return 0.0
    peak = float(np.max(onset_env)) if np.max(onset_env) > 0 else 1.0
    return float(np.clip(np.mean(vals) / peak, 0.0, 1.0))


def analyze_file(path: str, cfg: BeatgridConfig) -> tuple[str, dict | None, str | None, list[str]]:
    """Return (path, result, error, warnings). Result includes tempos list and confidence."""
    warnings: list[str] = []
    try:
        backend, notes = _pick_backend(cfg)
        warnings.extend(notes)
        beat_times, downbeats, conf = backend.run(path, cfg)
        if beat_times.size == 0:
            return path, None, "no beats detected", warnings
        segments = _segment_beats(beat_times, cfg, downbeat_times=downbeats if downbeats.size else None)
        bpm_est = _bpm_from_intervals(np.diff(beat_times))
        return path, {"tempos": segments, "confidence": conf, "bpm_est": bpm_est}, None, warnings
    except Exception as e:
        return path, None, str(e), warnings


ProgressCallback = Callable[[int, int, str], None]


def analyze_paths(
    paths: Iterable[str],
    cfg: Optional[BeatgridConfig] = None,
    progress_callback: Optional[ProgressCallback] = None,
    overwrite: bool = True,
) -> None:
    """Run beatgrid analysis for paths, writing tempos into meta.json."""
    cfg = cfg or BeatgridConfig()
    files = walk_audio(paths)
    total = len(files)
    if not files:
        console.print("[yellow]No audio files found for beatgrid.[/yellow]")
        return

    with MetaManager() as mm:
        meta = mm.meta
        done = 0
        for p in files:
            if not overwrite:
                info = meta.get("tracks", {}).get(p)
                if info and info.get("tempos"):
                    done += 1
                    if progress_callback:
                        progress_callback(done, total, p)
                    continue

            path, result, err, warns = analyze_file(p, cfg)
            for w in warns:
                console.print(f"[yellow]{w}")
            if err or result is None:
                console.print(f"[red]Beatgrid failed for {path}: {err}")
            else:
                info = meta["tracks"].setdefault(path, {})
                if "tempos" in result:
                    info["tempos"] = result["tempos"]
                if "bpm_est" in result and result["bpm_est"]:
                    info.setdefault("bpm_grid_est", result["bpm_est"])
                info["beatgrid_mode"] = cfg.mode
                info["beatgrid_backend"] = cfg.backend
                info["beatgrid_confidence"] = result.get("confidence", 0.0)
                mm.mark_dirty()
            done += 1
            if progress_callback:
                progress_callback(done, total, path)
        # MetaManager flushes on exit
