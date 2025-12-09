from __future__ import annotations

import os, pathlib, numpy as np
import librosa, soundfile as sf
import warnings
from typing import Callable, List, Optional
from transformers import AutoModel, Wav2Vec2FeatureExtractor
import torch
from rich.progress import Progress
from .utils import console, EMB, load_meta, save_meta
from .prefs import mode_for_path
from concurrent.futures import ThreadPoolExecutor, as_completed
from .sampling_profile import SamplingParams, pick_windows
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


class MertEmbedder:
    def __init__(self, model_name: str = DEFAULT_MODEL, device: str | None = None):
        req = _resolve_device(device)
        self.device = req
        self.model = AutoModel.from_pretrained(model_name, trust_remote_code=True).to(self.device)
        self.processor = Wav2Vec2FeatureExtractor.from_pretrained(model_name, trust_remote_code=True)

    def encode_array(self, y: np.ndarray, sr: int) -> np.ndarray:
        if sr != SAMPLE_RATE:
            y = librosa.resample(y, orig_sr=sr, target_sr=SAMPLE_RATE)
            sr = SAMPLE_RATE
        inputs = self.processor(y, sampling_rate=sr, return_tensors="pt")
        with torch.no_grad():
            out = self.model(**{k: v.to(self.device) for k, v in inputs.items()}, output_hidden_states=True)
        feats = out.hidden_states[-1].squeeze(0)  # [T, 1024]
        vec = feats.mean(dim=0).cpu().numpy().astype(np.float32)
        return vec

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
        with torch.no_grad():
            out = self.model(**{k: v.to(self.device) for k, v in inputs.items()}, output_hidden_states=True)
        feats = out.hidden_states[-1]  # [B, T, 1024]
        vecs = feats.mean(dim=1).cpu().numpy().astype(np.float32)
        return [vecs[i] for i in range(len(items))]

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
    embs: list[np.ndarray] = []
    for seg in slices:
        embs.append(embedder.encode_array(seg, sr))
    return np.mean(np.stack(embs, axis=0), axis=0)


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
) -> None:
    meta = load_meta()
    emb = MertEmbedder(model_name=model_name, device=device)
    timbre_emb: TimbreEmbedder | None = None
    if timbre:
        try:
            timbre_emb = TimbreEmbedder(embedding_size=timbre_size)
        except Exception as e:
            console.print(f"[yellow]Timbre embedding disabled: {e}")
            timbre_emb = None
    EMB.mkdir(parents=True, exist_ok=True)
    total = len(paths)

    if sampling is not None and num_workers > 0:
        # Keep sampling runs serial to avoid repeated disk reads per segment per worker.
        num_workers = 0

    # Resolve source paths (respect folder mode/stems) before optional parallel load
    jobs: list[tuple[str, str, str]] = []  # (original_path, src_for_embed, used_label)
    for p in paths:
        if not overwrite:
            info = meta.get("tracks", {}).get(p)
            if info and info.get("embedding") and pathlib.Path(info["embedding"]).exists():
                continue
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
        jobs.append((p, src_path, used))

    def _load(audio_path: str) -> tuple[np.ndarray, int]:
        y, sr = librosa.load(audio_path, sr=None, mono=True)
        if duration_s and y.shape[0] > sr * duration_s:
            y = y[: sr * duration_s]
        return y, sr

    progress: Progress | None = None
    task_id: int | None = None
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

        def _save_embedding(orig: str, vec: np.ndarray, used: str, kind: str = "embedding") -> None:
            suffix = "" if kind == "embedding" else f"_{kind}"
            out = EMB / (pathlib.Path(orig).stem + f"{suffix}.npy")
            vec_fp16 = vec.astype(np.float16)
            np.save(out, vec_fp16)
            info = meta["tracks"].setdefault(orig, {})
            info.setdefault("artist", pathlib.Path(orig).stem.split(" - ")[0] if " - " in pathlib.Path(orig).stem else "")
            info.setdefault("title", pathlib.Path(orig).stem.split(" - ")[-1])
            info[kind] = str(out)
            if kind == "embedding":
                info["embedding_source"] = used

        # Parallelize I/O + decode; keep model inference batched to reduce GPU overhead
        workers = max(0, int(num_workers))
        done = 0
        def _process_one(orig: str, src_path: str, y: np.ndarray, sr: int, used: str) -> None:
            nonlocal done
            try:
                windows: list[tuple[float, float]] = _default_windows(y, sr)
                mert_vec: np.ndarray | None = None
                timbre_vec: np.ndarray | None = None
                if sampling is not None:
                    vec = embed_with_sampling(src_path, emb, sampling)
                    mert_vec = vec
                else:
                    vec = embed_with_default_windows(y, sr, emb, windows=windows)
                    mert_vec = vec
                _save_embedding(orig, vec, used, kind="embedding_mert")

                if timbre_emb is not None:
                    try:
                        timbre_vec = timbre_embedding_from_windows(y, sr, windows, timbre_emb)
                        if timbre_vec is not None:
                            _save_embedding(orig, timbre_vec, used, kind="embedding_timbre")
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

                if combined is not None:
                    _save_embedding(orig, combined, source_label, kind="embedding")
            except Exception as e:
                # Per-file failures should never crash the whole job; some file
                # paths may also contain characters that the Windows console
                # cannot encode. Fall back to a safe representation.
                try:
                    console.print(f"[red]Embedding failed for {orig}: {e!r}")
                except Exception:
                    safe_path = repr(str(orig))
                    console.print(f"[red]Embedding failed for {safe_path}: {e!r}")
            finally:
                done += 1
                if progress_callback is not None:
                    progress_callback(done, total, orig)
                else:
                    _tick()

        if workers > 0:
            with ThreadPoolExecutor(max_workers=workers) as ex:
                future_map = {ex.submit(_load, src): (orig, src, used) for (orig, src, used) in jobs}
                for fut in as_completed(future_map):
                    orig, src_path, used = future_map[fut]
                    try:
                        y, sr = fut.result()
                        _process_one(orig, src_path, y, sr, used)
                    except Exception as e:
                        try:
                            console.print(f"[red]Embedding failed for {orig}: {e!r}")
                        except Exception:
                            safe_path = repr(str(orig))
                            console.print(f"[red]Embedding failed for {safe_path}: {e!r}")
                        done += 1
                        if progress_callback is not None:
                            progress_callback(done, total, orig)
                        else:
                            _tick()
        else:
            for orig, src, used in jobs:
                try:
                    if sampling is not None:
                        vec = embed_with_sampling(src, emb, sampling)
                        _save_embedding(orig, vec, used)
                        done += 1
                        if progress_callback is not None:
                            progress_callback(done, total, orig)
                        else:
                            _tick()
                        continue
                    y, sr = _load(src)
                    _process_one(orig, src, y, sr, used)
                except Exception as e:
                    try:
                        console.print(f"[red]Embedding failed for {orig}: {e!r}")
                    except Exception:
                        safe_path = repr(str(orig))
                        console.print(f"[red]Embedding failed for {safe_path}: {e!r}")
                    done += 1
                    if progress_callback is not None:
                        progress_callback(done, total, orig)
                    else:
                        _tick()

        save_meta(meta)
    finally:
        if progress is not None:
            progress.stop()
