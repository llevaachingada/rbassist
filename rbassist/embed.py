from __future__ import annotations

import os, pathlib, numpy as np
import librosa, soundfile as sf
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
    windows = pick_windows(audio_path, params)
    vecs: list[np.ndarray] = []
    for start, end in windows:
        try:
            y, sr = librosa.load(audio_path, sr=None, mono=True, offset=start, duration=(end - start))
            vecs.append(embedder.encode_array(y, sr))
        except Exception as e:
            console.print(f"[yellow]Sampling segment failed for {audio_path} [{start:.1f}-{end:.1f}s]: {e}")
    if not vecs:
        # Fallback: full embed
        return embedder.embed(audio_path)
    return np.mean(np.stack(vecs, axis=0), axis=0)


def _first_non_silent_time(y: np.ndarray, sr: int, top_db: float = 40.0) -> float:
    """Estimate start time of first non-silent region."""
    try:
        intervals = librosa.effects.split(y, top_db=top_db)
        if intervals.size:
            return float(intervals[0, 0] / sr)
    except Exception:
        pass
    return 0.0


def _default_windows(y: np.ndarray, sr: int) -> list[tuple[float, float]]:
    """
    Pick intro/core/late windows for embedding according to staged rules:
      - Short (<80s): single full-track window.
      - Medium (80–140s): ~10s intro, ~40s core, ~10s late.
      - Long: 10s intro, 60s core (centered), 10s late near end, no overlap.
    """
    T = len(y) / sr if sr else 0.0
    if T <= 0:
        return []

    # Short tracks: single pass.
    if T < 80.0:
        return [(0.0, T)]

    # Helper to clamp bounds.
    def _clamp(start: float, end: float) -> tuple[float, float]:
        s = max(0.0, min(start, T))
        e = max(s, min(end, T))
        return s, e

    t_first = _first_non_silent_time(y, sr)

    if T < 140.0:
        # Medium tracks: intro/core/late but shorter core window.
        intro = _clamp(t_first, t_first + 10.0)
        t_mid = T / 2.0
        core = _clamp(t_mid - 20.0, t_mid + 20.0)
        tC_end = max(core[1] + 5.0, T - 5.0)
        late = _clamp(tC_end - 10.0, tC_end)
        return [intro, core, late]

    # Long/regular tracks.
    intro = _clamp(t_first, t_first + 10.0)

    t_mid = T / 2.0
    core_start = max(0.0, min(t_mid - 30.0, T - 60.0))
    core = _clamp(core_start, core_start + 60.0)

    tC_end = max(core[1] + 5.0, T - 5.0)
    late = _clamp(tC_end - 10.0, tC_end)

    windows = [intro, core]
    # Avoid adding a degenerate late window.
    if late[1] - late[0] > 1e-3 and late[0] < T:
        windows.append(late)
    return windows


def embed_with_default_windows(y: np.ndarray, sr: int, embedder: MertEmbedder, windows: Optional[list[tuple[float, float]]] = None) -> np.ndarray:
    """Embed using intro/core/late windows and average the vectors."""
    windows = windows if windows is not None else _default_windows(y, sr)
    if not windows:
        return embedder.encode_array(y, sr)

    segments: list[tuple[np.ndarray, int]] = []
    for start, end in windows:
        s = int(start * sr)
        e = int(end * sr)
        if e <= s or s >= len(y):
            continue
        seg = y[s:e]
        if seg.size == 0:
            continue
        segments.append((seg, sr))

    if not segments:
        return embedder.encode_array(y, sr)

    vecs = embedder.encode_batch(segments)
    vecs = [v for v in vecs if v is not None]
    if not vecs:
        return embedder.encode_array(y, sr)
    return np.mean(np.stack(vecs, axis=0), axis=0)


def timbre_embedding_from_windows(y: np.ndarray, sr: int, windows: list[tuple[float, float]], emb: TimbreEmbedder) -> Optional[np.ndarray]:
    """Compute timbre embedding: per-window, 1s frames @48kHz with 50% overlap, mean+var pooling."""
    if not windows:
        return None
    if openl3 is None:
        return None

    if sr != TIMBRE_SR:
        y = librosa.resample(y, orig_sr=sr, target_sr=TIMBRE_SR)
        sr = TIMBRE_SR

    frame_len = int(TIMBRE_SR * TIMBRE_FRAME_S)
    hop = int(frame_len * (1.0 - TIMBRE_OVERLAP))
    if hop <= 0:
        hop = max(1, frame_len // 2)

    win_vecs: list[np.ndarray] = []
    for start, end in windows:
        s = int(start * sr)
        e = int(end * sr)
        if e <= s or s >= len(y):
            continue
        seg = y[s:e]
        if seg.size == 0:
            continue

        frames: list[np.ndarray] = []
        pos = 0
        while pos + frame_len <= len(seg):
            frames.append(seg[pos : pos + frame_len])
            pos += hop
        if not frames:
            frames.append(librosa.util.fix_length(seg, frame_len))

        embs: list[np.ndarray] = []
        for f in frames:
            try:
                ev, _ = openl3.get_audio_embedding(
                    f,
                    sr,
                    center=False,
                    hop_size=None,
                    content_type="music",
                    embedding_size=emb.embedding_size,
                )
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
                console.print(f"[red]Embedding failed for {orig}: {e}")
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
                        console.print(f"[red]Embedding failed for {orig}: {e}")
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
                    console.print(f"[red]Embedding failed for {orig}: {e}")
                    done += 1
                    if progress_callback is not None:
                        progress_callback(done, total, orig)
                    else:
                        _tick()

        save_meta(meta)
    finally:
        if progress is not None:
            progress.stop()
