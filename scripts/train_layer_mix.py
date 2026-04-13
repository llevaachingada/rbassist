"""
Train a learned layer-mixture head using playlist co-occurrence as the training signal.

Positives: track pairs from the same Rekordbox playlist or sharing >=2 mytags.
Negatives: in-batch random pairs.
Loss: InfoNCE (NT-Xent) with temperature tau=0.07.

Usage:
    python scripts/train_layer_mix.py \
        --meta data/meta.json \
        --rekordbox path/to/collection.xml \
        --out data/layer_mix_weights.npz \
        --epochs 5 \
        --batch-size 64

Architecture:
    Input:  6 x 1024 layer pools (pre-extracted, cached)
    Head:   Linear(6144 -> 1024) + GELU + Linear(1024 -> 1024)
    Output: L2-normalized 1024-d vector
    Loss:   InfoNCE

Training data construction:
    1. Load all tracks with embedding_layer_mix computed.
    2. Load Rekordbox XML and collect pairs from each playlist.
    3. Also collect pairs from tracks sharing at least two My Tags.
    4. Deduplicate and shuffle.
    5. Train with batch_size=64 and drop_last=True.

Saving:
    np.savez(out, mix_weights=softmax_weights, proj_w=proj_matrix, proj_b=proj_bias)
"""

from __future__ import annotations

import argparse
from pathlib import Path

from rbassist.utils import console


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train a learned MERT layer-mix head.")
    parser.add_argument("--meta", default="data/meta.json", help="Path to rbassist meta.json.")
    parser.add_argument("--rekordbox", default=None, help="Optional Rekordbox XML export for playlist positives.")
    parser.add_argument("--out", default="data/layer_mix_weights.npz", help="Output .npz path for learned weights.")
    parser.add_argument("--epochs", type=int, default=5, help="Training epochs.")
    parser.add_argument("--batch-size", type=int, default=64, help="Contrastive batch size.")
    parser.add_argument("--temperature", type=float, default=0.07, help="InfoNCE temperature.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    console.print("[yellow]Layer-mix training is a scaffold only; no weights were written.")
    console.print(f"[cyan]meta={Path(args.meta)} out={Path(args.out)} epochs={args.epochs} batch_size={args.batch_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
