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

DEFAULT_MODEL = "m-a-p/MERT-v1-330M"
SAMPLE_RATE = 24000  # per model card
os.environ.setdefault("HF_HOME", str(pathlib.Path.home() / ".cache" / "huggingface"))


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
) -> None:
    meta = load_meta()
    emb = MertEmbedder(model_name=model_name, device=device)
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

        def _save_embedding(orig: str, vec: np.ndarray, used: str) -> None:
            out = EMB / (pathlib.Path(orig).stem + ".npy")
            vec_fp16 = vec.astype(np.float16)
            np.save(out, vec_fp16)
            info = meta["tracks"].setdefault(orig, {})
            info.setdefault("artist", pathlib.Path(orig).stem.split(" - ")[0] if " - " in pathlib.Path(orig).stem else "")
            info.setdefault("title", pathlib.Path(orig).stem.split(" - ")[-1])
            info["embedding"] = str(out)
            info["embedding_source"] = used

        # Parallelize I/O + decode; keep model inference batched to reduce GPU overhead
        workers = max(0, int(num_workers))
        done = 0
        batch: list[tuple[str, str, np.ndarray, int, str]] = []

        def _flush_batch() -> None:
            nonlocal done
            if not batch:
                return
            try:
                if sampling is not None:
                    # Should not enter batching when sampling is active, but guard anyway.
                    for orig, src_path, _y, _sr, used in batch:
                        vec = embed_with_sampling(src_path, emb, sampling)
                        _save_embedding(orig, vec, used)
                        done += 1
                        if progress_callback is not None:
                            progress_callback(done, total, orig)
                        else:
                            _tick()
                    batch.clear()
                    return
                vecs = emb.encode_batch([(y, sr) for (_orig, _src, y, sr, _used) in batch])
            except Exception as e:
                console.print(f"[red]Embedding batch failed for {[b[0] for b in batch]}: {e}")
                vecs = [None] * len(batch)

            for (orig, _src, _y, _sr, used), vec in zip(batch, vecs):
                try:
                    if vec is None:
                        continue
                    _save_embedding(orig, vec, used)
                except Exception as se:
                    console.print(f"[red]Embedding failed for {orig}: {se}")
                finally:
                    done += 1
                    if progress_callback is not None:
                        progress_callback(done, total, orig)
                    else:
                        _tick()
            batch.clear()

        if workers > 0:
            with ThreadPoolExecutor(max_workers=workers) as ex:
                future_map = {ex.submit(_load, src): (orig, src, used) for (orig, src, used) in jobs}
                for fut in as_completed(future_map):
                    orig, _src, used = future_map[fut]
                    try:
                        y, sr = fut.result()
                        batch.append((orig, _src, y, sr, used))
                        if len(batch) >= batch_size:
                            _flush_batch()
                    except Exception as e:
                        console.print(f"[red]Embedding failed for {orig}: {e}")
                        done += 1
                        if progress_callback is not None:
                            progress_callback(done, total, orig)
                        else:
                            _tick()
                _flush_batch()
        else:
            # Simple serial path with optional batching
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
                    batch.append((orig, src, y, sr, used))
                    if len(batch) >= batch_size:
                        _flush_batch()
                except Exception as e:
                    console.print(f"[red]Embedding failed for {orig}: {e}")
                    done += 1
                    if progress_callback is not None:
                        progress_callback(done, total, orig)
                    else:
                        _tick()
            _flush_batch()

        save_meta(meta)
    finally:
        if progress is not None:
            progress.stop()
