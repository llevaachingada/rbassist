from __future__ import annotations

import torch


def pick_device(user_choice: str | None = None) -> str:
    """Choose best available device, honoring an explicit user choice when valid."""
    if user_choice:
        choice = user_choice.lower()
        if choice == "cpu":
            return "cpu"
        if choice in {"cuda", "rocm"}:
            if torch.cuda.is_available():
                return "cuda"
            return "cpu"
        if choice == "mps":
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return "mps"
            return "cpu"
    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"
