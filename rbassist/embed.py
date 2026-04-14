from __future__ import annotations

import gc
import json
import os
import pathlib
import time
from datetime import datetime, timezone
import numpy as np
import librosa, soundfile as sf
import warnings
from typing import Any, Callable, List, Optional
from transformers import AutoModel, Wav2Vec2FeatureExtractor
import torch
from rich.progress import Progress
from .utils import console, EMB, load_meta, save_meta
from .prefs import mode_for_path
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from .sampling_profile import SamplingParams, pick_windows
from .layer_mix import extract_layer_pools, fixed_weight_mix, learned_mix
try:
    import openl3  # type: ignore
except Exception:
    openl3 = None  # type: ignore

DEFAULT_MODEL = "m-a-p/MERT-v1-330M"
SAMPLE_RATE = 24000  # per model card
os.environ.setdefault("HF_HOME", str(pathlib.Path.home() / ".cache" / "huggingface"))
TIMBRE_SR = 48000
TIMBRE_FRAME_S = 1.0
TIMBRE_OVERLAP = 0.5
W_MERT = 0.7
W_TIMBRE = 0.3

# Quiet known noisy warnings that are not actionable for users.
warnings.filterwarnings(
    "ignore",
    category=UserWarning,
    message="pkg_resources is deprecated as an API",
)


def _resolve_device(requested: str | None) -> str:
    if requested is None:
        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    normalized = requested.lower()
    if normalized == "cuda":
        if torch.cuda.is_available():
            return "cuda"
        console.print("[yellow]CUDA requested but not available; falling back to CPU.")
        return "cpu"
    if normalized in {"rocm", "hip"}:
        if torch.cuda.is_available() and getattr(torch.version, "hip", None):
            return "cuda"
        console.print("[yellow]ROCm requested but not available; falling back to CPU.")
        return "cpu"
    if normalized == "mps":
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
        console.print("[yellow]MPS requested but not available; falling back to CPU.")
        return "cpu"
    if normalized == "cpu":
        return "cpu"

    raise ValueError(f"Unsupported device '{requested}'. Use 'cuda', 'rocm', 'mps', or 'cpu'.")


def _configure_torch_runtime(device: str) -> None:
    """Apply safe runtime tuning for CUDA inference."""
    if device != "cuda":
        return
    try:
        torch.backends.cuda.matmul.allow_tf32 = True
    except Exception:
        pass
    try:
        torch.backends.cudnn.allow_tf32 = True
    except Exception:
        pass
    try:
        torch.backends.cudnn.benchmark = True
    except Exception:
        pass
    try:
        torch.set_float32_matmul_precision("high")
    except Exception:
        pass


def _is_cuda_runtime_error(err: Exception | str) -> bool:
    accelerator_error = getattr(torch, "AcceleratorError", None)
    if accelerator_error is not None and isinstance(err, accelerator_error):
        return True
    text = repr(err).lower()
    return "cuda error" in text or "cudnn" in text or "cublas" in text


class MertEmbedder:
    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        device: str | None = None,
        layer_mix: bool = False,
        layer_mix_weights_path: str | None = None,
    ):
        req = _resolve_device(device)
        self.device = req
        self.layer_mix = bool(layer_mix)
        self.layer_mix_weights = self._load_layer_mix_weights(layer_mix_weights_path)
        _configure_torch_runtime(self.device)
        self.model = AutoModel.from_pretrained(model_name, trust_remote_code=True).to(self.device)
        self.processor = Wav2Vec2FeatureExtractor.from_pretrained(model_name, trust_remote_code=True)

    def _load_layer_mix_weights(self, weights_path: str | None) -> dict[str, np.ndarray] | None:
        if not weights_path:
            return None
        try:
            loaded = np.load(weights_path)
            projection = loaded.get("projection_weights")
            if projection is None:
                projection = loaded.get("proj_w")
            mix_weights = loaded.get("mix_weights")
            if projection is None or mix_weights is None:
                console.print(f"[yellow]Layer-mix weights missing required arrays; using fixed weights: {weights_path}")
                return None
            return {
                "projection_weights": np.asarray(projection, dtype=np.float32),
                "mix_weights": np.asarray(mix_weights, dtype=np.float32),
            }
        except Exception as e:
            console.print(f"[yellow]Layer-mix weights unreadable ({weights_path}); using fixed weights: {e}")
            return None

    def _mix_hidden_states(self, hidden_states: tuple) -> np.ndarray:
        pools = extract_layer_pools(hidden_states)
        if self.layer_mix_weights is not None:
            return learned_mix(
                pools,
                self.layer_mix_weights["projection_weights"],
                self.layer_mix_weights["mix_weights"],
            )
        return fixed_weight_mix(pools)

    def encode_array(self, y: np.ndarray, sr: int) -> np.ndarray:
        if sr != SAMPLE_RATE:
            y = librosa.resample(y, orig_sr=sr, target_sr=SAMPLE_RATE)
            sr = SAMPLE_RATE
        inputs = self.processor(y, sampling_rate=sr, return_tensors="pt")
        with torch.inference_mode():
            out = self.model(**{k: v.to(self.device) for k, v in inputs.items()}, output_hidden_states=True)
        if self.layer_mix:
            return self._mix_hidden_states(out.hidden_states)
        feats = out.hidden_states[-1].squeeze(0)  # [T, 1024]
        vec = feats.mean(dim=0).cpu().numpy().astype(np.float32)
        return vec

    def encode_array_full(self, y: np.ndarray, sr: int) -> dict[str, np.ndarray]:
        if sr != SAMPLE_RATE:
            y = librosa.resample(y, orig_sr=sr, target_sr=SAMPLE_RATE)
            sr = SAMPLE_RATE
        inputs = self.processor(y, sampling_rate=sr, return_tensors="pt")
        with torch.inference_mode():
            out = self.model(**{k: v.to(self.device) for k, v in inputs.items()}, output_hidden_states=True)
        feats = out.hidden_states[-1].squeeze(0)
        standard = feats.mean(dim=0).cpu().numpy().astype(np.float32)
        return {
            "standard": standard,
            "layer_mix": self._mix_hidden_states(out.hidden_states),
        }

    def encode_batch(self, items: list[tuple[np.ndarray, int]]) -> list[np.ndarray]:
        """Batch version of encode_array; items are (audio, sr)."""
        if not items:
            return []
        arrays: list[np.ndarray] = []
        for y, sr in items:
            if sr != SAMPLE_RATE:
                y = librosa.resample(y, orig_sr=sr, target_sr=SAMPLE_RATE)
            arrays.append(y)
        inputs = self.processor(arrays, sampling_rate=SAMPLE_RATE, return_tensors="pt", padding=True)
        with torch.inference_mode():
            out = self.model(**{k: v.to(self.device) for k, v in inputs.items()}, output_hidden_states=True)
        if self.layer_mix:
            mixed: list[np.ndarray] = []
            for idx in range(len(items)):
                item_hidden_states = tuple(state[idx : idx + 1] for state in out.hidden_states)
                mixed.append(self._mix_hidden_states(item_hidden_states))
            return mixed
        feats = out.hidden_states[-1]  # [B, T, 1024]
        vecs = feats.mean(dim=1).cpu().numpy().astype(np.float32)
        return [vecs[i] for i in range(len(items))]

    def encode_batch_full(self, items: list[tuple[np.ndarray, int]]) -> list[dict[str, np.ndarray]]:
        if not items:
            return []
        arrays: list[np.ndarray] = []
        for y, sr in items:
            if sr != SAMPLE_RATE:
                y = librosa.resample(y, orig_sr=sr, target_sr=SAMPLE_RATE)
            arrays.append(y)
        inputs = self.processor(arrays, sampling_rate=SAMPLE_RATE, return_tensors="pt", padding=True)
        with torch.inference_mode():
            out = self.model(**{k: v.to(self.device) for k, v in inputs.items()}, output_hidden_states=True)
        feats = out.hidden_states[-1]
        standard_vecs = feats.mean(dim=1).cpu().numpy().astype(np.float32)
        results: list[dict[str, np.ndarray]] = []
        for idx in range(len(items)):
            item_hidden_states = tuple(state[idx : idx + 1] for state in out.hidden_states)
            results.append(
                {
                    "standard": standard_vecs[idx],
                    "layer_mix": self._mix_hidden_states(item_hidden_states),
                }
            )
        return results

    def encode_section_vectors(self, segments: list[tuple[np.ndarray, int]]) -> list[np.ndarray]:
        """Encode each section independently, preserving input order."""
        try:
            return self.encode_batch(segments)
        except Exception as e:
            if _is_cuda_runtime_error(e):
                raise
            return [self.encode_array(y, sr) for y, sr in segments]

    def embed(self, audio_path: str, duration_s: int = 120) -> np.ndarray:
        y, sr = librosa.load(audio_path, sr=None, mono=True)
        if duration_s and y.shape[0] > sr * duration_s:
            y = y[: sr * duration_s]
        return self.encode_array(y, sr)


class TimbreEmbedder:
    """Lightweight timbre-focused encoder using OpenL3 (music-mel)."""

    def __init__(self, embedding_size: int = 512):
        if openl3 is None:
            raise RuntimeError("openl3 not installed; pip install openl3")
        self.embedding_size = embedding_size

    def encode_array(self, y: np.ndarray, sr: int) -> np.ndarray:
        emb, _ = openl3.get_audio_embedding(
            y,
            sr,
            center=True,
            hop_size=None,
            content_type="music",
            embedding_size=self.embedding_size,
        )
        if emb.ndim > 1:
            vec = emb.mean(axis=0)
        else:
            vec = emb
        return np.asarray(vec, dtype=np.float32)


def embed_with_sampling(audio_path: str, embedder: MertEmbedder, params: SamplingParams) -> np.ndarray:
    """Embed multiple segments chosen by sampling profile and average them."""
    y, sr = librosa.load(audio_path, sr=None, mono=True)
    segments = pick_windows(y, sr, params)
    embs: list[np.ndarray] = []
    for start, end in segments:
        s = int(start * sr)
        e = int(end * sr)
        if s >= e or s >= y.shape[0]:
            continue
        seg = y[s:e]
        embs.append(embedder.encode_array(seg, sr))
    if not embs:
        return embedder.encode_array(y, sr)
    return np.mean(np.stack(embs, axis=0), axis=0)


def _window_slices(y: np.ndarray, sr: int, windows: list[tuple[float, float]]) -> list[np.ndarray]:
    slices: list[np.ndarray] = []
    n = y.shape[0]
    for start_s, end_s in windows:
        s = int(start_s * sr)
        e = int(end_s * sr)
        if s >= e or s >= n:
            continue
        e = min(e, n)
        slices.append(y[s:e])
    return slices


def timbre_embedding_from_windows(
    y: np.ndarray,
    sr: int,
    windows: list[tuple[float, float]],
    timbre_emb: TimbreEmbedder,
) -> np.ndarray | None:
    """Compute OpenL3 timbre embedding over selected windows using 1s frames.

    To reduce CPU load, timbre now focuses on the beginning and end of the track:
      - If multiple windows are provided (intro/core/late), only the first and
        last are used (typically intro and late).
      - Frames use a larger hop (75% of frame length) compared to MERT’s
        coverage, which cuts the number of OpenL3 calls by ~50%.
    """
    if openl3 is None:
        return None
    if y.ndim != 1:
        y = librosa.to_mono(y)
    # resample once for timbre
    if sr != TIMBRE_SR:
        y = librosa.resample(y, orig_sr=sr, target_sr=TIMBRE_SR)
        sr = TIMBRE_SR

    # Focus timbre on intro + late to reduce work while still sampling texture
    selected_windows: list[tuple[float, float]]
    if len(windows) >= 2:
        selected_windows = [windows[0], windows[-1]]
    else:
        selected_windows = windows

    win_vecs: list[np.ndarray] = []
    for start_s, end_s in selected_windows:
        s = int(start_s * sr)
        e = int(end_s * sr)
        if s >= e or s >= y.shape[0]:
            continue
        e = min(e, y.shape[0])
        seg = y[s:e]
        if seg.size == 0:
            continue
        frame_len = int(TIMBRE_FRAME_S * sr)
        # Use a larger hop (e.g., 75% of frame length) to reduce frame count.
        hop = max(1, int(frame_len * 0.75))
        embs: list[np.ndarray] = []
        for i in range(0, max(len(seg) - frame_len, 1), hop):
            frame = seg[i : i + frame_len]
            if frame.size < frame_len:
                pad = np.zeros(frame_len - frame.size, dtype=seg.dtype)
                frame = np.concatenate([frame, pad])
            try:
                ev = timbre_emb.encode_array(frame, sr)
                if ev is None:
                    continue
                if ev.ndim > 1:
                    embs.append(np.mean(ev, axis=0))
                else:
                    embs.append(ev)
            except Exception:
                continue

        if not embs:
            continue
        m = np.mean(np.stack(embs, axis=0), axis=0)
        v = np.var(np.stack(embs, axis=0), axis=0)
        win_vec = np.concatenate([m, v]).astype(np.float32)
        win_vecs.append(win_vec)

    if not win_vecs:
        return None
    return np.mean(np.stack(win_vecs, axis=0), axis=0)


ProgressCallback = Callable[[int, int, str], None]


def _first_non_silent_time(y: np.ndarray, sr: int, threshold: float = 1e-4) -> float:
    """Return the time (s) of the first sample above a small energy threshold."""
    if y.size == 0 or sr <= 0:
        return 0.0
    amp = np.abs(y)
    idx = np.argmax(amp > threshold)
    if amp[idx] <= threshold:
        return 0.0
    return float(idx) / float(sr)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _default_windows(y: np.ndarray, sr: int) -> list[tuple[float, float]]:
    """Intro / core / late slicing with ~80s budget (10 / 60 / 10).

    Rules (simple version from design doc):
      - Intro: 10 s starting at first non‑silent audio.
      - Core: 60 s centered at track midpoint (clamped to [0, T-60]).
      - Late: 10 s ending ~5 s before the end, and not overlapping core.

    Edge cases:
      - T < 80 s: single window over full track.
      - 80 s ≤ T < 140 s: use 10/40/10 pattern (shorter core).
    """
    dur = y.shape[0] / sr if sr > 0 else 0.0
    if dur <= 0:
        return [(0.0, 10.0)]

    # Very short: just embed the whole track once.
    if dur < 80.0:
        return [(0.0, dur)]

    intro_len = 10.0
    late_len = 10.0
    core_len = 60.0 if dur >= 140.0 else 40.0

    # Intro slice
    tA_start = _first_non_silent_time(y, sr)
    tA_end = _clamp(tA_start + intro_len, 0.0, dur)

    # Core slice centered on midpoint
    t_mid = dur / 2.0
    tB_start = _clamp(t_mid - core_len / 2.0, 0.0, max(dur - core_len, 0.0))
    tB_end = _clamp(tB_start + core_len, 0.0, dur)

    # Late slice near the end, avoiding overlap with core (leave 5s margin)
    tC_end = max(dur - 5.0, 0.0)
    tC_start = max(tC_end - late_len, tB_end + 5.0)
    windows: list[tuple[float, float]] = []

    def _add_window(start: float, end: float) -> None:
        if end - start > 1.0 and end > 0.0 and start < dur:
            windows.append((max(start, 0.0), min(end, dur)))

    _add_window(tA_start, tA_end)
    _add_window(tB_start, tB_end)
    _add_window(tC_start, tC_end)

    # Fallback: if something degenerated, at least cover 10 s from start.
    if not windows:
        windows.append((0.0, min(10.0, dur)))
    return windows


def embed_with_default_windows(
    y: np.ndarray,
    sr: int,
    embedder: MertEmbedder,
    windows: Optional[list[tuple[float, float]]] = None,
) -> np.ndarray:
    if windows is None:
        windows = _default_windows(y, sr)
    slices = _window_slices(y, sr, windows)
    if not slices:
        return embedder.encode_array(y, sr)
    try:
        embs = embedder.encode_batch([(seg, sr) for seg in slices])
    except Exception as e:
        if _is_cuda_runtime_error(e):
            raise
        # Fallback keeps behavior stable if batched encode fails on edge inputs.
        embs = [embedder.encode_array(seg, sr) for seg in slices]
    return np.mean(np.stack(embs, axis=0), axis=0)


def embed_with_section_vectors(
    y: np.ndarray,
    sr: int,
    embedder: MertEmbedder,
    windows: Optional[list[tuple[float, float]]] = None,
) -> dict[str, np.ndarray]:
    """Compute intro/core/late section vectors plus the existing combined vector."""
    if windows is None:
        windows = _default_windows(y, sr)
    slices = _window_slices(y, sr, windows)
    if not slices:
        vec = embedder.encode_array(y, sr)
        return {"intro": vec, "core": vec, "late": vec, "combined": vec}

    try:
        embs = embedder.encode_section_vectors([(seg, sr) for seg in slices])
    except Exception as e:
        if _is_cuda_runtime_error(e):
            raise
        embs = [embedder.encode_array(seg, sr) for seg in slices]
    if not embs:
        vec = embedder.encode_array(y, sr)
        return {"intro": vec, "core": vec, "late": vec, "combined": vec}

    combined = np.mean(np.stack(embs, axis=0), axis=0).astype(np.float32)
    if len(embs) == 1:
        intro = core = late = embs[0]
    elif len(embs) == 2:
        intro = embs[0]
        core = embs[0]
        late = embs[1]
    else:
        intro = embs[0]
        core = embs[1]
        late = embs[-1]
    return {
        "intro": np.asarray(intro, dtype=np.float32),
        "core": np.asarray(core, dtype=np.float32),
        "late": np.asarray(late, dtype=np.float32),
        "combined": combined,
    }


def embed_with_default_windows_full(
    y: np.ndarray,
    sr: int,
    embedder: MertEmbedder,
    windows: Optional[list[tuple[float, float]]] = None,
) -> dict[str, np.ndarray]:
    if windows is None:
        windows = _default_windows(y, sr)
    slices = _window_slices(y, sr, windows)
    if not slices:
        return embedder.encode_array_full(y, sr)
    try:
        rows = embedder.encode_batch_full([(seg, sr) for seg in slices])
    except Exception as e:
        if _is_cuda_runtime_error(e):
            raise
        rows = [embedder.encode_array_full(seg, sr) for seg in slices]
    standard = np.mean(np.stack([row["standard"] for row in rows], axis=0), axis=0).astype(np.float32)
    layer_mixed = np.mean(np.stack([row["layer_mix"] for row in rows], axis=0), axis=0).astype(np.float32)
    layer_norm = float(np.linalg.norm(layer_mixed))
    if layer_norm > 0.0:
        layer_mixed = (layer_mixed / layer_norm).astype(np.float32, copy=False)
    return {"standard": standard, "layer_mix": layer_mixed}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_runtime_path(path_ref: str | None, default_path: pathlib.Path) -> pathlib.Path:
    if path_ref is None:
        return default_path
    p = pathlib.Path(path_ref)
    if p.is_absolute():
        return p
    return (pathlib.Path.cwd() / p).resolve()


def _load_checkpoint_state(path: pathlib.Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        console.print(f"[yellow]Checkpoint unreadable ({path}): {e}")
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _write_checkpoint_state(path: pathlib.Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _elapsed_since(start: float) -> float:
    return round(time.perf_counter() - start, 6)


def build_embeddings(
    paths: List[str],
    model_name: str = DEFAULT_MODEL,
    duration_s: int = 120,
    progress_callback: Optional[ProgressCallback] = None,
    device: Optional[str] = None,
    num_workers: int = 0,
    sampling: Optional[SamplingParams] = None,
    overwrite: bool = True,
    batch_size: Optional[int] = None,
    timbre: bool = False,
    timbre_size: int = 512,
    resume: bool = False,
    checkpoint_file: Optional[str] = None,
    checkpoint_every: int = 100,
    section_embed: bool = False,
    layer_mix: bool = False,
    layer_mix_weights_path: Optional[str] = None,
    profile_embed_out: Optional[str] = None,
) -> None:
    meta = load_meta()
    embedder_kwargs: dict[str, Any] = {}
    if layer_mix_weights_path:
        embedder_kwargs["layer_mix_weights_path"] = layer_mix_weights_path
    emb = MertEmbedder(model_name=model_name, device=device, **embedder_kwargs)
    timbre_emb: TimbreEmbedder | None = None
    if timbre:
        try:
            timbre_emb = TimbreEmbedder(embedding_size=timbre_size)
        except Exception as e:
            console.print(f"[yellow]Timbre embedding disabled: {e}")
            timbre_emb = None
    EMB.mkdir(parents=True, exist_ok=True)
    checkpoint_every = max(1, int(checkpoint_every))
    checkpoint_path = _resolve_runtime_path(checkpoint_file, EMB.parent / "embed_checkpoint.json")
    failed_log_path = checkpoint_path.with_name(f"{checkpoint_path.stem}_failed.jsonl")
    profile_path = _resolve_runtime_path(profile_embed_out, pathlib.Path("embed_profile.jsonl")) if profile_embed_out else None

    checkpoint_seed = _load_checkpoint_state(checkpoint_path) if resume else {}
    completed_paths: set[str] = set()
    failed_paths: set[str] = set()
    if isinstance(checkpoint_seed.get("completed_paths"), list):
        completed_paths = {str(p) for p in checkpoint_seed["completed_paths"]}
    if isinstance(checkpoint_seed.get("failed_paths"), list):
        failed_paths = {str(p) for p in checkpoint_seed["failed_paths"]}

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    started_at = _utc_now_iso()
    counters = {
        "requested": len(paths),
        "queued": 0,
        "succeeded": 0,
        "failed": 0,
        "skipped_checkpoint": 0,
        "skipped_existing": 0,
    }
    recovery = {
        "cuda_retries": 0,
        "cuda_retry_successes": 0,
        "cuda_retry_failures": 0,
        "cuda_rebuild_failures": 0,
    }
    checkpoint_mutations = 0
    # Persist meta periodically so crash/abort does not lose an entire chunk.
    meta_mutations = 0
    meta_flush_every = max(25, checkpoint_every * 5)

    if sampling is not None and num_workers > 0:
        # Keep sampling runs serial to avoid repeated disk reads per segment per worker.
        num_workers = 0

    # Resolve source paths (respect folder mode/stems) before optional parallel load
    jobs: list[tuple[str, str, str, bool, bool]] = []
    # (original_path, src_for_embed, used_label, write_primary, allow_section_overwrite)
    section_keys = ("embedding_intro", "embedding_core", "embedding_late")

    def _track_has_vector_file(track_info: dict | None, key: str) -> bool:
        if not track_info:
            return False
        value = track_info.get(key)
        return bool(value and pathlib.Path(value).exists())

    for p in paths:
        info = meta.get("tracks", {}).get(p)
        existing_embedding = _track_has_vector_file(info, "embedding")
        needs_section_backfill = bool(
            section_embed
            and existing_embedding
            and any(not _track_has_vector_file(info, key) for key in section_keys)
        )
        if resume and p in completed_paths and not needs_section_backfill:
            counters["skipped_checkpoint"] += 1
            continue
        if existing_embedding and (resume or not overwrite) and not needs_section_backfill:
            counters["skipped_existing"] += 1
            if resume:
                completed_paths.add(p)
            continue
        backfill_sections_only = bool(needs_section_backfill and (resume or not overwrite))
        write_primary = bool((not existing_embedding) or (overwrite and not backfill_sections_only))
        allow_section_overwrite = bool(overwrite and not backfill_sections_only)
        src_path = p
        used = "baseline"
        try:
            mode = mode_for_path(p)
            if mode == "stems":
                try:
                    from .stems import split_stems
                    parts = split_stems(p)
                    if parts.get("vocals"):
                        src_path = parts["vocals"]
                        used = "stems:vocals"
                except Exception as se:
                    console.print(f"[yellow]Stems skipped for {p}: {se}")
        except Exception as e:
            console.print(f"[yellow]Mode check failed for {p}: {e}")
        jobs.append((p, src_path, used, write_primary, allow_section_overwrite))
    counters["queued"] = len(jobs)
    total = len(jobs)

    def _append_profile(event: dict[str, Any]) -> None:
        if profile_path is None:
            return
        event = {
            "timestamp": _utc_now_iso(),
            "run_id": run_id,
            **event,
        }
        try:
            profile_path.parent.mkdir(parents=True, exist_ok=True)
            with profile_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(event, ensure_ascii=False) + "\n")
        except Exception as profile_err:
            console.print(f"[yellow]Failed to append embed profile ({profile_path}): {profile_err}")

    def _load(audio_path: str) -> tuple[np.ndarray, int, dict[str, Any]]:
        started = time.perf_counter()
        y, sr = librosa.load(audio_path, sr=None, mono=True)
        decoded_samples = int(y.shape[0])
        if duration_s and y.shape[0] > sr * duration_s:
            y = y[: sr * duration_s]
        return y, sr, {
            "load_audio_s": _elapsed_since(started),
            "decoded_samples": decoded_samples,
            "trimmed_samples": int(y.shape[0]),
            "duration_cap_s": int(duration_s or 0),
            "source_sample_rate": int(sr),
        }

    def _checkpoint_payload(status: str) -> dict:
        return {
            "version": 1,
            "status": status,
            "run_id": run_id,
            "started_at": started_at,
            "updated_at": _utc_now_iso(),
            "model_name": model_name,
            "duration_s": duration_s,
            "device": emb.device,
            "resume": bool(resume),
            "overwrite": bool(overwrite),
            "checkpoint_every": checkpoint_every,
            "paths_total": counters["requested"],
            "paths_queued": counters["queued"],
            "paths_completed": len(completed_paths),
            "paths_failed": len(failed_paths),
            "counters": counters,
            "recovery": recovery,
            "completed_paths": sorted(completed_paths),
            "failed_paths": sorted(failed_paths),
            "failed_log": str(failed_log_path),
        }

    def _flush_checkpoint(force: bool = False, status: str = "running") -> dict[str, Any]:
        nonlocal checkpoint_mutations, meta_mutations
        write_checkpoint = force or checkpoint_mutations >= checkpoint_every
        write_meta = force or meta_mutations >= meta_flush_every
        timings = {
            "checkpoint_written": bool(write_checkpoint),
            "meta_written": bool(write_meta),
            "checkpoint_write_s": 0.0,
            "meta_write_s": 0.0,
        }
        if not write_checkpoint and not write_meta:
            return timings
        if write_checkpoint:
            started = time.perf_counter()
            _write_checkpoint_state(checkpoint_path, _checkpoint_payload(status=status))
            timings["checkpoint_write_s"] = _elapsed_since(started)
            checkpoint_mutations = 0
        if write_meta:
            started = time.perf_counter()
            save_meta(meta)
            timings["meta_write_s"] = _elapsed_since(started)
            meta_mutations = 0
        return timings

    def _log_failure(path: str, src_path: str, phase: str, err: Exception | str) -> None:
        nonlocal checkpoint_mutations, meta_mutations
        counters["failed"] += 1
        failed_paths.add(path)
        event = {
            "timestamp": _utc_now_iso(),
            "run_id": run_id,
            "path": path,
            "source_path": src_path,
            "phase": phase,
            "error": repr(err),
        }
        try:
            failed_log_path.parent.mkdir(parents=True, exist_ok=True)
            with failed_log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(event, ensure_ascii=False) + "\n")
        except Exception as log_err:
            console.print(f"[yellow]Failed to append failure log ({failed_log_path}): {log_err}")
        try:
            console.print(f"[red]Embedding failed for {path}: {err!r}")
        except Exception:
            safe_path = repr(str(path))
            console.print(f"[red]Embedding failed for {safe_path}: {err!r}")
        checkpoint_mutations += 1
        meta_mutations += 1
        _flush_checkpoint()

    def _mark_completed(path: str) -> dict[str, Any]:
        nonlocal checkpoint_mutations, meta_mutations
        counters["succeeded"] += 1
        completed_paths.add(path)
        failed_paths.discard(path)
        checkpoint_mutations += 1
        meta_mutations += 1
        return _flush_checkpoint()

    def _rebuild_cuda_embedder() -> None:
        nonlocal emb
        old_emb = emb
        try:
            del old_emb
        except Exception:
            pass
        gc.collect()
        if torch.cuda.is_available():
            try:
                torch.cuda.synchronize()
            except Exception:
                pass
            try:
                torch.cuda.empty_cache()
            except Exception:
                pass
            try:
                torch.cuda.ipc_collect()
            except Exception:
                pass
        emb = MertEmbedder(model_name=model_name, device="cuda", **embedder_kwargs)

    if total == 0:
        console.print("[green]No embedding work to do.")
        _flush_checkpoint(force=True, status="completed")
        return

    progress: Progress | None = None
    task_id: int | None = None
    run_status = "running"
    try:
        effective_batch = 1
        if sampling is not None:
            # Sampling path performs its own per-segment embedding; keep serial.
            effective_batch = 1
        else:
            effective_batch = 4 if emb.device != "cpu" else 1
        batch_size = effective_batch if batch_size is None else max(1, int(batch_size))

        if progress_callback is None:
            progress = Progress(transient=True)
            progress.start()
            task_id = progress.add_task("Embedding", total=total)

        def _tick():
            if progress is not None and task_id is not None:
                progress.advance(task_id)

        def _save_embedding(
            orig: str,
            vec: np.ndarray,
            used: str,
            kind: str = "embedding",
            allow_overwrite: bool = True,
        ) -> None:
            info = meta["tracks"].setdefault(orig, {})
            section_suffixes = {
                "embedding_intro": "_intro",
                "embedding_core": "_core",
                "embedding_late": "_late",
            }
            suffix = section_suffixes.get(kind, "" if kind == "embedding" else f"_{kind}")
            out = EMB / (pathlib.Path(orig).stem + f"{suffix}.npy")
            existing = info.get(kind)
            existing_path = pathlib.Path(existing) if existing else None
            target = out
            if existing_path is not None and existing_path.exists() and not allow_overwrite:
                target = existing_path
            elif out.exists() and not allow_overwrite:
                target = out
            else:
                vec_fp16 = vec.astype(np.float16)
                np.save(out, vec_fp16)
            info.setdefault("artist", pathlib.Path(orig).stem.split(" - ")[0] if " - " in pathlib.Path(orig).stem else "")
            info.setdefault("title", pathlib.Path(orig).stem.split(" - ")[-1])
            info[kind] = str(target)
            if kind == "embedding":
                info["embedding_source"] = used

        # Parallelize I/O + decode; keep model inference batched to reduce GPU overhead
        workers = max(0, int(num_workers))
        done = 0
        def _process_one(
            orig: str,
            src_path: str,
            y: np.ndarray,
            sr: int,
            load_profile: dict[str, Any],
            used: str,
            write_primary: bool,
            allow_section_overwrite: bool,
        ) -> None:
            nonlocal done
            def _run_once(active_emb: MertEmbedder) -> None:
                windows: list[tuple[float, float]] = _default_windows(y, sr)
                flattened_item_count = len(_window_slices(y, sr, windows)) if sampling is None else None
                actual_mert_batch_size = flattened_item_count if sampling is None else None
                mert_vec: np.ndarray | None = None
                timbre_vec: np.ndarray | None = None
                section_vecs: dict[str, np.ndarray] | None = None
                mert_encode_s = 0.0
                timbre_encode_s = 0.0
                save_s = 0.0

                def _save_profiled(
                    save_orig: str,
                    save_vec: np.ndarray,
                    save_used: str,
                    *,
                    kind: str = "embedding",
                    allow_overwrite: bool = True,
                ) -> None:
                    nonlocal save_s
                    started = time.perf_counter()
                    _save_embedding(
                        save_orig,
                        save_vec,
                        save_used,
                        kind=kind,
                        allow_overwrite=allow_overwrite,
                    )
                    save_s += time.perf_counter() - started

                if sampling is not None:
                    started = time.perf_counter()
                    vec = embed_with_sampling(src_path, active_emb, sampling)
                    mert_encode_s += time.perf_counter() - started
                    mert_vec = vec
                elif layer_mix:
                    started = time.perf_counter()
                    full_vecs = embed_with_default_windows_full(y, sr, active_emb, windows=windows)
                    mert_encode_s += time.perf_counter() - started
                    vec = full_vecs["standard"]
                    mert_vec = vec
                    _save_profiled(
                        orig,
                        full_vecs["layer_mix"],
                        used,
                        kind="embedding_layer_mix",
                        allow_overwrite=overwrite,
                    )
                else:
                    if section_embed:
                        started = time.perf_counter()
                        section_vecs = embed_with_section_vectors(y, sr, active_emb, windows=windows)
                        mert_encode_s += time.perf_counter() - started
                        vec = section_vecs["combined"]
                    else:
                        started = time.perf_counter()
                        vec = embed_with_default_windows(y, sr, active_emb, windows=windows)
                        mert_encode_s += time.perf_counter() - started
                    mert_vec = vec
                if write_primary:
                    _save_profiled(
                        orig,
                        vec,
                        used,
                        kind="embedding_mert",
                        allow_overwrite=overwrite,
                    )

                if section_embed:
                    if section_vecs is None:
                        started = time.perf_counter()
                        section_vecs = embed_with_section_vectors(y, sr, active_emb, windows=windows)
                        mert_encode_s += time.perf_counter() - started
                    _save_profiled(
                        orig,
                        section_vecs["intro"],
                        used,
                        kind="embedding_intro",
                        allow_overwrite=allow_section_overwrite,
                    )
                    _save_profiled(
                        orig,
                        section_vecs["core"],
                        used,
                        kind="embedding_core",
                        allow_overwrite=allow_section_overwrite,
                    )
                    _save_profiled(
                        orig,
                        section_vecs["late"],
                        used,
                        kind="embedding_late",
                        allow_overwrite=allow_section_overwrite,
                    )
                    section_complete = all(
                        _track_has_vector_file(meta["tracks"].get(orig), key) for key in section_keys
                    )
                    if section_complete:
                        meta["tracks"].setdefault(orig, {})["embedding_version"] = "v2_section"

                if timbre_emb is not None and write_primary:
                    try:
                        started = time.perf_counter()
                        timbre_vec = timbre_embedding_from_windows(y, sr, windows, timbre_emb)
                        timbre_encode_s += time.perf_counter() - started
                        if timbre_vec is not None:
                            _save_profiled(
                                orig,
                                timbre_vec,
                                used,
                                kind="embedding_timbre",
                                allow_overwrite=overwrite,
                            )
                    except Exception as te:
                        console.print(f"[yellow]Timbre embed failed for {orig}: {te}")

                combined = mert_vec
                source_label = used
                if timbre_vec is not None:
                    if combined is not None and combined.shape == timbre_vec.shape:
                        combined = (W_MERT * combined) + (W_TIMBRE * timbre_vec)
                        source_label = f"{used}+timbre({W_MERT:.2f}/{W_TIMBRE:.2f})"
                    else:
                        combined = timbre_vec
                        source_label = "timbre_only"

                if combined is not None and write_primary:
                    _save_profiled(
                        orig,
                        combined,
                        source_label,
                        kind="embedding",
                        allow_overwrite=overwrite,
                    )
                return {
                    "mert_flattened_item_count": flattened_item_count,
                    "actual_mert_batch_size": actual_mert_batch_size,
                    "mert_encode_s": round(mert_encode_s, 6),
                    "timbre_encode_s": round(timbre_encode_s, 6),
                    "save_s": round(save_s, 6),
                }

            try:
                profile_event = _run_once(emb)
                checkpoint_profile = _mark_completed(orig)
                if profile_path is not None:
                    _append_profile(
                        {
                            "event": "track",
                            "path": orig,
                            "source_path": src_path,
                            "source_label": used,
                            "device": emb.device,
                            "section_embed": bool(section_embed),
                            "layer_mix": bool(layer_mix),
                            "timbre": bool(timbre_emb is not None),
                            "sampling": bool(sampling is not None),
                            "write_primary": bool(write_primary),
                            "allow_section_overwrite": bool(allow_section_overwrite),
                            **load_profile,
                            **profile_event,
                            **checkpoint_profile,
                        }
                    )
            except Exception as e:
                if emb.device == "cuda" and _is_cuda_runtime_error(e):
                    recovery["cuda_retries"] += 1
                    try:
                        _rebuild_cuda_embedder()
                    except Exception as rebuild_err:
                        recovery["cuda_rebuild_failures"] += 1
                        _log_failure(
                            orig,
                            src_path,
                            "embed_cuda_rebuild",
                            f"initial={e!r}; rebuild={rebuild_err!r}",
                        )
                    else:
                        try:
                            profile_event = _run_once(emb)
                            recovery["cuda_retry_successes"] += 1
                            console.print(f"[yellow]Recovered CUDA embedder and retried {orig}")
                            checkpoint_profile = _mark_completed(orig)
                            if profile_path is not None:
                                _append_profile(
                                    {
                                        "event": "track",
                                        "path": orig,
                                        "source_path": src_path,
                                        "source_label": used,
                                        "device": emb.device,
                                        "section_embed": bool(section_embed),
                                        "layer_mix": bool(layer_mix),
                                        "timbre": bool(timbre_emb is not None),
                                        "sampling": bool(sampling is not None),
                                        "write_primary": bool(write_primary),
                                        "allow_section_overwrite": bool(allow_section_overwrite),
                                        "cuda_retried": True,
                                        **load_profile,
                                        **profile_event,
                                        **checkpoint_profile,
                                    }
                                )
                            return
                        except Exception as retry_err:
                            recovery["cuda_retry_failures"] += 1
                            _log_failure(
                                orig,
                                src_path,
                                "embed_retry",
                                f"initial={e!r}; retry={retry_err!r}",
                            )
                else:
                    # Per-file failures should never crash the whole run.
                    _log_failure(orig, src_path, "embed", e)
            finally:
                done += 1
                if progress_callback is not None:
                    progress_callback(done, total, orig)
                else:
                    _tick()

        if workers > 0:
            # Bound in-flight decode futures to prevent very large RAM spikes on
            # long chunk files while keeping the GPU fed.
            with ThreadPoolExecutor(max_workers=workers) as ex:
                max_in_flight = max(workers, int(batch_size or 1) * workers)
                jobs_iter = iter(jobs)
                in_flight: dict = {}

                def _submit_more() -> None:
                    while len(in_flight) < max_in_flight:
                        try:
                            orig, src_path, used, write_primary, allow_section_overwrite = next(jobs_iter)
                        except StopIteration:
                            break
                        fut = ex.submit(_load, src_path)
                        in_flight[fut] = (orig, src_path, used, write_primary, allow_section_overwrite)

                _submit_more()
                while in_flight:
                    completed, _ = wait(tuple(in_flight.keys()), return_when=FIRST_COMPLETED)
                    for fut in completed:
                        orig, src_path, used, write_primary, allow_section_overwrite = in_flight.pop(fut)
                        try:
                            y, sr, load_profile = fut.result()
                            _process_one(
                                orig,
                                src_path,
                                y,
                                sr,
                                load_profile,
                                used,
                                write_primary,
                                allow_section_overwrite,
                            )
                        except Exception as e:
                            _log_failure(orig, src_path, "decode", e)
                            done += 1
                            if progress_callback is not None:
                                progress_callback(done, total, orig)
                            else:
                                _tick()
                    _submit_more()
        else:
            for orig, src, used, write_primary, allow_section_overwrite in jobs:
                try:
                    if sampling is not None:
                        vec = embed_with_sampling(src, emb, sampling)
                        _save_embedding(orig, vec, used, allow_overwrite=overwrite)
                        _mark_completed(orig)
                        done += 1
                        if progress_callback is not None:
                            progress_callback(done, total, orig)
                        else:
                            _tick()
                        continue
                    y, sr, load_profile = _load(src)
                    _process_one(orig, src, y, sr, load_profile, used, write_primary, allow_section_overwrite)
                except Exception as e:
                    _log_failure(orig, src, "serial", e)
                    done += 1
                    if progress_callback is not None:
                        progress_callback(done, total, orig)
                    else:
                        _tick()

        save_meta(meta)
        run_status = "completed"
        console.print(
            "[cyan]Embedding summary: "
            f"queued={counters['queued']}, "
            f"succeeded={counters['succeeded']}, "
            f"failed={counters['failed']}, "
            f"skipped(checkpoint)={counters['skipped_checkpoint']}, "
            f"skipped(existing)={counters['skipped_existing']}"
        )
        if recovery["cuda_retries"] > 0:
            console.print(
                "[cyan]CUDA recovery: "
                f"retries={recovery['cuda_retries']}, "
                f"retry_successes={recovery['cuda_retry_successes']}, "
                f"retry_failures={recovery['cuda_retry_failures']}, "
                f"rebuild_failures={recovery['cuda_rebuild_failures']}"
            )
        console.print(f"[cyan]Checkpoint: {checkpoint_path}")
        if counters["failed"] > 0:
            console.print(f"[yellow]Failed-track log: {failed_log_path}")
    finally:
        _flush_checkpoint(force=True, status=run_status)
        if progress is not None:
            progress.stop()
