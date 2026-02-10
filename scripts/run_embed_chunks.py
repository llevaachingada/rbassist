#!/usr/bin/env python3
"""Run rbassist embedding over chunked path files with resumable checkpoints.

Example:
    python scripts/run_embed_chunks.py \
      --repo C:/Users/hunte/Music/rbassist \
      --chunk-glob "data/pending_embedding_paths.part*.txt" \
      --checkpoint-dir data/checkpoints \
      --num-workers 2
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run rbassist embed against chunk files with per-chunk checkpoints."
    )
    parser.add_argument(
        "--repo",
        default=".",
        help="Path to rbassist repository root (default: current directory).",
    )
    parser.add_argument(
        "--chunk-glob",
        default="data/pending_embedding_paths.part*.txt",
        help="Glob pattern (relative to repo) selecting chunk path files.",
    )
    parser.add_argument(
        "--checkpoint-dir",
        default="data/checkpoints",
        help="Directory (relative to repo) for chunk checkpoint files.",
    )
    parser.add_argument(
        "--checkpoint-every",
        type=int,
        default=100,
        help="Checkpoint write cadence passed to `rbassist embed`.",
    )
    parser.add_argument(
        "--num-workers",
        type=int,
        default=8,
        help="Number of audio loader workers for `rbassist embed`.",
    )
    parser.add_argument(
        "--device",
        default="auto",
        choices=("auto", "cuda", "rocm", "mps", "cpu"),
        help="Device to pass to `rbassist embed` (auto omits --device).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=0,
        help="Optional embed batch size (0 uses rbassist default auto-batch).",
    )
    parser.add_argument(
        "--start-index",
        type=int,
        default=1,
        help="Start chunk index (1-based, after sorting).",
    )
    parser.add_argument(
        "--end-index",
        type=int,
        default=0,
        help="End chunk index inclusive (0 means process all).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without running them.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = Path(args.repo).resolve()
    chunk_pattern = str((repo / args.chunk_glob).as_posix())
    chunk_files = sorted(repo.glob(args.chunk_glob))

    if not chunk_files:
        raise FileNotFoundError(f"No chunk files found for pattern: {chunk_pattern}")

    start_idx = max(1, int(args.start_index))
    end_idx = int(args.end_index)
    if end_idx <= 0:
        end_idx = len(chunk_files)
    end_idx = min(end_idx, len(chunk_files))

    if start_idx > end_idx:
        raise ValueError(
            f"Invalid range start-index={start_idx}, end-index={end_idx} for {len(chunk_files)} chunks."
        )

    selected = chunk_files[start_idx - 1 : end_idx]
    checkpoint_dir = (repo / args.checkpoint_dir).resolve()
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    print(f"Repo: {repo}")
    print(f"Chunk files selected: {len(selected)} / {len(chunk_files)}")
    print(f"Checkpoint dir: {checkpoint_dir}")

    for idx, chunk_path in enumerate(selected, start=start_idx):
        checkpoint_path = checkpoint_dir / f"embed_checkpoint_part{idx:03d}.json"
        cmd = [
            "python",
            "-m",
            "rbassist.cli",
            "embed",
            "--paths-file",
            str(chunk_path),
            "--resume",
            "--checkpoint-file",
            str(checkpoint_path),
            "--checkpoint-every",
            str(max(1, int(args.checkpoint_every))),
            "--num-workers",
            str(max(0, int(args.num_workers))),
        ]
        if args.device != "auto":
            cmd.extend(["--device", args.device])
        if int(args.batch_size) > 0:
            cmd.extend(["--batch-size", str(int(args.batch_size))])

        print(f"\n[{idx}/{len(chunk_files)}] {chunk_path.name}")
        print(" ".join(cmd))
        if args.dry_run:
            continue

        result = subprocess.run(cmd, cwd=str(repo))
        if result.returncode != 0:
            print(
                f"Chunk failed (index={idx}, file={chunk_path.name}). "
                f"Resume later with --start-index {idx}."
            )
            return result.returncode

    print("\nAll selected chunks finished.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
