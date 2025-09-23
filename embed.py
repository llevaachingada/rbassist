from __future__ import annotations
import os, pathlib, numpy as np
import librosa, soundfile as sf
from typing import List
from transformers import AutoModel, Wav2Vec2FeatureExtractor
import torch
from rich.progress import track
from .utils import console, EMB, load_meta, save_meta

DEFAULT_MODEL = "m-a-p/MERT-v1-330M"
SAMPLE_RATE = 24000  # per model card

class MertEmbedder:
    def __init__(self, model_name: str = DEFAULT_MODEL, device: str | None = None):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = AutoModel.from_pretrained(model_name, trust_remote_code=True).to(self.device)
        self.processor = Wav2Vec2FeatureExtractor.from_pretrained(model_name, trust_remote_code=True)

    def embed(self, audio_path: str, duration_s: int = 120) -> np.ndarray:
        y, sr = librosa.load(audio_path, sr=None, mono=True)
        if duration_s and y.shape[0] > sr * duration_s:
            y = y[: sr * duration_s]
        if sr != SAMPLE_RATE:
            y = librosa.resample(y, orig_sr=sr, target_sr=SAMPLE_RATE)
            sr = SAMPLE_RATE
        inputs = self.processor(y, sampling_rate=sr, return_tensors="pt")
        with torch.no_grad():
            out = self.model(**{k: v.to(self.device) for k, v in inputs.items()}, output_hidden_states=True)
        # Last hidden state mean over time → 1024-d
        feats = out.hidden_states[-1].squeeze(0)  # [T, 1024]
        vec = feats.mean(dim=0).cpu().numpy().astype(np.float32)
        return vec


def build_embeddings(paths: List[str], model_name: str = DEFAULT_MODEL, duration_s: int = 120) -> None:
    meta = load_meta()
    emb = MertEmbedder(model_name=model_name)
    EMB.mkdir(parents=True, exist_ok=True)
    for p in track(paths, description="Embedding"):
        try:
            vec = emb.embed(p, duration_s=duration_s)
            out = EMB / (pathlib.Path(p).stem + ".npy")
            np.save(out, vec)
            # store meta
            info = meta["tracks"].setdefault(p, {})
            info.setdefault("artist", pathlib.Path(p).stem.split(" - ")[0] if " - " in pathlib.Path(p).stem else "")
            info.setdefault("title", pathlib.Path(p).stem.split(" - ")[-1])
            info["embedding"] = str(out)
        except Exception as e:
            console.print(f"[red]Embedding failed for {p}: {e}")
    save_meta(meta)