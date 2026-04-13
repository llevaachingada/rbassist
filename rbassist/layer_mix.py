from __future__ import annotations

import numpy as np

LAYER_TAPS = [4, 8, 12, 16, 20, 24]
LAYER_WEIGHTS_FIXED = [0.05, 0.10, 0.15, 0.20, 0.25, 0.25]


def _to_numpy(value) -> np.ndarray:
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value)


def _normalize(vec: np.ndarray) -> np.ndarray:
    out = np.asarray(vec, dtype=np.float32)
    norm = float(np.linalg.norm(out))
    if norm <= 0.0:
        return out
    return (out / norm).astype(np.float32, copy=False)


def extract_layer_pools(
    hidden_states: tuple,
    layer_taps: list[int] = LAYER_TAPS,
    pool: str = "mean",
) -> np.ndarray:
    """Extract tapped hidden-state layers and pool each layer over time.

    Returns (len(layer_taps), D) for ``pool="mean"`` and (len(layer_taps), 2D)
    for ``pool="mean+var"``. Batched model outputs use the first batch item; callers
    that need every batch item should pass per-item hidden states.
    """
    if pool not in {"mean", "mean+var"}:
        raise ValueError("pool must be 'mean' or 'mean+var'")

    pooled: list[np.ndarray] = []
    total_layers = len(hidden_states)
    for tap in layer_taps:
        if tap < 0 or tap >= total_layers:
            raise ValueError(f"Layer tap {tap} out of range for {total_layers} hidden states")
        arr = _to_numpy(hidden_states[tap])
        if arr.ndim == 3:
            arr = arr[0]
        if arr.ndim != 2:
            raise ValueError(f"Expected hidden state with shape [T, D] or [B, T, D], got {arr.shape}")
        mean = arr.mean(axis=0)
        if pool == "mean+var":
            layer_vec = np.concatenate([mean, arr.var(axis=0)], axis=0)
        else:
            layer_vec = mean
        pooled.append(np.asarray(layer_vec, dtype=np.float32))
    return np.stack(pooled, axis=0).astype(np.float32, copy=False)


def fixed_weight_mix(
    layer_pools: np.ndarray,
    weights: list[float] = LAYER_WEIGHTS_FIXED,
) -> np.ndarray:
    """Return a fixed weighted, L2-normalized layer mix as a float32 vector."""
    pools = np.asarray(layer_pools, dtype=np.float32)
    if pools.ndim != 2:
        raise ValueError(f"Expected layer_pools with shape [N, D], got {pools.shape}")
    w = np.asarray(weights, dtype=np.float32).reshape(-1)
    if pools.shape[0] != w.shape[0]:
        raise ValueError(f"Expected {pools.shape[0]} weights, got {w.shape[0]}")
    total = float(w.sum())
    if total <= 0.0:
        raise ValueError("Layer mix weights must sum to a positive value")
    w = w / total
    mixed = np.sum(pools * w[:, None], axis=0)
    return _normalize(mixed)


def learned_mix(
    layer_pools: np.ndarray,
    projection_weights: np.ndarray,
    mix_weights: np.ndarray,
) -> np.ndarray:
    """Apply learned per-layer projections and a weighted mixture."""
    pools = np.asarray(layer_pools, dtype=np.float32)
    proj = np.asarray(projection_weights, dtype=np.float32)
    weights = np.asarray(mix_weights, dtype=np.float32).reshape(-1)
    if pools.ndim != 2:
        raise ValueError(f"Expected layer_pools with shape [N, D], got {pools.shape}")
    if proj.ndim != 3:
        raise ValueError(f"Expected projection_weights with shape [N, D, O], got {proj.shape}")
    if proj.shape[0] != pools.shape[0] or proj.shape[1] != pools.shape[1]:
        raise ValueError("projection_weights shape must match layer_pools")
    if weights.shape[0] != pools.shape[0]:
        raise ValueError(f"Expected {pools.shape[0]} mix weights, got {weights.shape[0]}")
    weights = np.exp(weights - np.max(weights))
    weights = weights / max(float(weights.sum()), 1e-9)
    projected = np.einsum("nd,ndo->no", pools, proj)
    mixed = np.sum(projected * weights[:, None], axis=0)
    return _normalize(mixed)
