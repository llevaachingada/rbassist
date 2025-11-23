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

DEFAULT_MODEL = "m-a-p/MERT-v1-330M"
SAMPLE_RATE = 24000  # per model card

class MertEmbedder:
    def __init__(self, model_name: str = DEFAULT_MODEL, device: str | None = None):
        req = device or ("cuda" if torch.cuda.is_available() else "cpu")
        if req == "cuda" and not torch.cuda.is_available():
            console.print("[yellow]CUDA requested but not available; falling back to CPU.")
            req = "cpu"
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

    def embed(self, audio_path: str, duration_s: int = 120) -> np.ndarray:
        y, sr = librosa.load(audio_path, sr=None, mono=True)
        if duration_s and y.shape[0] > sr * duration_s:
            y = y[: sr * duration_s]
        return self.encode_array(y, sr)


ProgressCallback = Callable[[int, int, str], None]


def build_embeddings(
    paths: List[str],
    model_name: str = DEFAULT_MODEL,
    duration_s: int = 120,
    progress_callback: Optional[ProgressCallback] = None,
    device: Optional[str] = None,
    num_workers: int = 0,
) -> None:
    meta = load_meta()
    emb = MertEmbedder(model_name=model_name, device=device)
    EMB.mkdir(parents=True, exist_ok=True)
    total = len(paths)

    # Resolve source paths (respect folder mode/stems) before optional parallel load
    jobs: list[tuple[str, str, str]] = []  # (original_path, src_for_embed, used_label)
    for p in paths:
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
    if progress_callback is None:
        progress = Progress(transient=True)
        progress.start()
        task_id = progress.add_task("Embedding", total=total)

    def _tick():
        if progress is not None and task_id is not None:
            progress.advance(task_id)

    # Parallelize I/O + decode; keep model inference serialized to avoid GPU thrash
    workers = max(0, int(num_workers))
    done = 0
    if workers > 0:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            future_map = {ex.submit(_load, src): (orig, src, used) for (orig, src, used) in jobs}
            for fut in as_completed(future_map):
                orig, src, used = future_map[fut]
                try:
                    y, sr = fut.result()
                    vec = emb.encode_array(y, sr)
                    out = EMB / (pathlib.Path(orig).stem + ".npy")
                    np.save(out, vec)
                    info = meta["tracks"].setdefault(orig, {})
                    info.setdefault("artist", pathlib.Path(orig).stem.split(" - ")[0] if " - " in pathlib.Path(orig).stem else "")
                    info.setdefault("title", pathlib.Path(orig).stem.split(" - ")[-1])
                    info["embedding"] = str(out)
                    info["embedding_source"] = used
                except Exception as e:
                    console.print(f"[red]Embedding failed for {orig}: {e}")
                finally:
                    done += 1
                    if progress_callback is not None:
                        progress_callback(done, total, orig)
                    else:
                        _tick()
    else:
        # Simple serial path
        for idx, (orig, src, used) in enumerate(jobs, start=1):
            try:
                if progress_callback is not None:
                    progress_callback(idx, total, orig)
                vec = emb.embed(src, duration_s=duration_s)
                out = EMB / (pathlib.Path(orig).stem + ".npy")
                np.save(out, vec)
                info = meta["tracks"].setdefault(orig, {})
                info.setdefault("artist", pathlib.Path(orig).stem.split(" - ")[0] if " - " in pathlib.Path(orig).stem else "")
                info.setdefault("title", pathlib.Path(orig).stem.split(" - ")[-1])
                info["embedding"] = str(out)
                info["embedding_source"] = used
            except Exception as e:
                console.print(f"[red]Embedding failed for {orig}: {e}")
            finally:
                if progress_callback is None:
                    _tick()

    save_meta(meta)
    if progress is not None:
        progress.stop()
