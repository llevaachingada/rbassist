from __future__ import annotations

import argparse
import json
import pathlib
import random
from typing import Any

import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset, random_split

from rbassist.recommend import load_embedding_safe
from rbassist.similarity_head import SimilarityHead, pick_similarity_device


class PairDataset(Dataset):
    def __init__(self, rows: list[dict[str, Any]], *, expected_dim: int = 1024) -> None:
        self.rows = rows
        self.expected_dim = int(expected_dim)

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        row = self.rows[index]
        left = load_embedding_safe(str(row.get("left_embedding") or ""), self.expected_dim)
        right = load_embedding_safe(str(row.get("right_embedding") or ""), self.expected_dim)
        if left is None or right is None:
            raise ValueError(f"Missing embedding for pair row {index}")
        label = float(row.get("label", 0.0))
        return (
            torch.from_numpy(left.astype(np.float32, copy=False)),
            torch.from_numpy(right.astype(np.float32, copy=False)),
            torch.tensor(np.clip(label, 0.0, 1.0), dtype=torch.float32),
        )


def _read_jsonl(path: pathlib.Path, *, expected_dim: int, max_rows: int | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        clean = line.strip()
        if not clean:
            continue
        row = json.loads(clean)
        left = pathlib.Path(str(row.get("left_embedding") or ""))
        right = pathlib.Path(str(row.get("right_embedding") or ""))
        if not left.exists() or not right.exists():
            continue
        try:
            left_shape = np.load(left, mmap_mode="r").reshape(-1).shape[0]
            right_shape = np.load(right, mmap_mode="r").reshape(-1).shape[0]
        except Exception:
            continue
        if left_shape != expected_dim or right_shape != expected_dim:
            continue
        rows.append(row)
        if max_rows and len(rows) >= max_rows:
            break
    if len(rows) < 4:
        raise ValueError(f"Need at least 4 usable pair rows with embeddings in {path}")
    return rows


def _evaluate(model: SimilarityHead, loader: DataLoader, *, device: str) -> float:
    model.eval()
    losses: list[float] = []
    loss_fn = torch.nn.BCELoss()
    with torch.no_grad():
        for left, right, label in loader:
            left = left.to(device)
            right = right.to(device)
            label = label.to(device)
            pred = model(left, right)
            losses.append(float(loss_fn(pred, label).detach().cpu().item()))
    return float(np.mean(losses)) if losses else float("inf")


def train(args: argparse.Namespace) -> dict[str, Any]:
    random.seed(int(args.seed))
    torch.manual_seed(int(args.seed))
    rows = _read_jsonl(pathlib.Path(args.pairs), expected_dim=int(args.embed_dim), max_rows=args.max_rows)
    dataset = PairDataset(rows, expected_dim=int(args.embed_dim))
    valid_count = max(2, int(round(len(dataset) * float(args.valid_fraction))))
    valid_count = min(valid_count, max(2, len(dataset) - 2))
    train_count = len(dataset) - valid_count
    generator = torch.Generator().manual_seed(int(args.seed))
    train_set, valid_set = random_split(dataset, [train_count, valid_count], generator=generator)
    device = pick_similarity_device(args.device)
    model = SimilarityHead(embed_dim=args.embed_dim, hidden=args.hidden, bottleneck=args.bottleneck).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=float(args.lr), weight_decay=float(args.weight_decay))
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(1, int(args.epochs)))
    loss_fn = torch.nn.BCELoss()
    train_loader = DataLoader(train_set, batch_size=args.batch_size, shuffle=True, drop_last=len(train_set) > int(args.batch_size))
    valid_loader = DataLoader(valid_set, batch_size=args.batch_size, shuffle=False, drop_last=False)
    best_state: dict[str, torch.Tensor] | None = None
    best_valid = float("inf")
    stale_epochs = 0
    history: list[dict[str, float | int]] = []

    for epoch in range(1, int(args.epochs) + 1):
        model.train()
        train_losses: list[float] = []
        for left, right, label in train_loader:
            left = left.to(device)
            right = right.to(device)
            label = label.to(device)
            optimizer.zero_grad(set_to_none=True)
            pred = model(left, right)
            loss = loss_fn(pred, label)
            loss.backward()
            optimizer.step()
            train_losses.append(float(loss.detach().cpu().item()))
        scheduler.step()
        valid_loss = _evaluate(model, valid_loader, device=device)
        train_loss = float(np.mean(train_losses)) if train_losses else float("inf")
        history.append({"epoch": epoch, "train_loss": train_loss, "valid_loss": valid_loss})
        print(json.dumps({"epoch": epoch, "train_loss": train_loss, "valid_loss": valid_loss, "device": device}))
        if valid_loss < best_valid:
            best_valid = valid_loss
            best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
            stale_epochs = 0
        else:
            stale_epochs += 1
            if stale_epochs >= int(args.patience):
                break

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "state_dict": best_state or model.state_dict(),
            "config": {
                "embed_dim": int(args.embed_dim),
                "hidden": int(args.hidden),
                "bottleneck": int(args.bottleneck),
            },
            "metadata": {
                "pairs": str(pathlib.Path(args.pairs)),
                "rows_total": len(rows),
                "train_rows": train_count,
                "valid_rows": valid_count,
                "best_valid_loss": best_valid,
                "device": device,
                "history": history,
            },
        },
        out,
    )
    return {"out": str(out), "rows_total": len(rows), "best_valid_loss": best_valid, "device": device}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train the opt-in rbassist learned similarity head.")
    parser.add_argument("--pairs", default="data/training/playlist_pairs.jsonl", help="Playlist-pair JSONL dataset.")
    parser.add_argument("--out", default="data/models/similarity_head.pt", help="Output model checkpoint.")
    parser.add_argument("--device", default="cuda", help="Training device. Default prefers CUDA, falls back to CPU.")
    parser.add_argument("--embed-dim", type=int, default=1024, help="Embedding dimension.")
    parser.add_argument("--hidden", type=int, default=512, help="Hidden layer width.")
    parser.add_argument("--bottleneck", type=int, default=128, help="Bottleneck layer width.")
    parser.add_argument("--batch-size", type=int, default=256, help="Training batch size.")
    parser.add_argument("--epochs", type=int, default=30, help="Maximum epochs.")
    parser.add_argument("--patience", type=int, default=5, help="Early-stopping patience.")
    parser.add_argument("--lr", type=float, default=1e-3, help="AdamW learning rate.")
    parser.add_argument("--weight-decay", type=float, default=1e-4, help="AdamW weight decay.")
    parser.add_argument("--valid-fraction", type=float, default=0.2, help="Validation split fraction.")
    parser.add_argument("--seed", type=int, default=1337, help="Random seed.")
    parser.add_argument("--max-rows", type=int, default=None, help="Optional maximum usable rows.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    result = train(args)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
