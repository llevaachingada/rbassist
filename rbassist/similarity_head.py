from __future__ import annotations

from dataclasses import dataclass
import pathlib
from typing import Any

import numpy as np
import torch
from torch import nn


DEFAULT_SIMILARITY_MODEL = pathlib.Path("data/models/similarity_head.pt")


class SimilarityHead(nn.Module):
    """Pairwise MLP for frozen 1024-d audio embeddings."""

    def __init__(self, embed_dim: int = 1024, hidden: int = 512, bottleneck: int = 128) -> None:
        super().__init__()
        self.embed_dim = int(embed_dim)
        self.net = nn.Sequential(
            nn.Linear(self.embed_dim * 2, hidden),
            nn.BatchNorm1d(hidden),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(hidden, bottleneck),
            nn.BatchNorm1d(bottleneck),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(bottleneck, 1),
            nn.Sigmoid(),
        )

    def forward(self, left: torch.Tensor, right: torch.Tensor) -> torch.Tensor:
        diff = torch.abs(left - right)
        prod = left * right
        return self.net(torch.cat([diff, prod], dim=-1)).squeeze(-1)


def pick_similarity_device(requested: str | None = None) -> str:
    """Prefer CUDA by default for training/inference, with CPU fallback."""
    choice = str(requested or "cuda").lower().strip()
    if choice == "cpu":
        return "cpu"
    if choice in {"cuda", "gpu", "auto", ""}:
        return "cuda" if torch.cuda.is_available() else "cpu"
    if choice == "mps":
        return "mps" if hasattr(torch.backends, "mps") and torch.backends.mps.is_available() else "cpu"
    return "cuda" if torch.cuda.is_available() else "cpu"


@dataclass
class LoadedSimilarityHead:
    model: SimilarityHead
    device: str
    path: pathlib.Path

    def score(self, left: np.ndarray, right: np.ndarray) -> float:
        return similarity_score(left, right, self.model, device=self.device)


def _checkpoint_config(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict) and isinstance(payload.get("config"), dict):
        return dict(payload["config"])
    return {}


def load_similarity_head(
    path: str | pathlib.Path = DEFAULT_SIMILARITY_MODEL,
    *,
    device: str | None = None,
) -> LoadedSimilarityHead | None:
    model_path = pathlib.Path(path)
    if not model_path.exists():
        return None
    runtime_device = pick_similarity_device(device)
    payload = torch.load(model_path, map_location=runtime_device)
    config = _checkpoint_config(payload)
    model = SimilarityHead(
        embed_dim=int(config.get("embed_dim", 1024)),
        hidden=int(config.get("hidden", 512)),
        bottleneck=int(config.get("bottleneck", 128)),
    )
    state = payload.get("state_dict") if isinstance(payload, dict) else payload
    model.load_state_dict(state)
    model.to(runtime_device)
    model.eval()
    return LoadedSimilarityHead(model=model, device=runtime_device, path=model_path)


def similarity_score(
    left: np.ndarray,
    right: np.ndarray,
    model: SimilarityHead,
    *,
    device: str | None = None,
) -> float:
    left_vec = np.asarray(left, dtype=np.float32).reshape(-1)
    right_vec = np.asarray(right, dtype=np.float32).reshape(-1)
    if left_vec.size == 0 or right_vec.size == 0 or left_vec.shape != right_vec.shape:
        return 0.0
    runtime_device = pick_similarity_device(device)
    model.to(runtime_device)
    model.eval()
    with torch.no_grad():
        left_tensor = torch.from_numpy(left_vec).unsqueeze(0).to(runtime_device)
        right_tensor = torch.from_numpy(right_vec).unsqueeze(0).to(runtime_device)
        score = model(left_tensor, right_tensor)
    return float(np.clip(float(score.detach().cpu().item()), 0.0, 1.0))
