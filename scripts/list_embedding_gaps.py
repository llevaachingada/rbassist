#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib

from rbassist.health import list_embedding_gaps


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan music roots and emit embedding gaps.")
    parser.add_argument("--repo", default=".", help="Repo root.")
    parser.add_argument("--music-root", action="append", default=[], help="Music root to scan. Repeatable.")
    parser.add_argument("--exclude-file", default="", help="Optional text file with paths to exclude.")
    parser.add_argument("--out-prefix", default="data/pending_embedding_paths", help="Output prefix, repo-relative by default.")
    parser.add_argument("--chunk-size", type=int, default=2000, help="Chunk size for part files.")
    return parser.parse_args()


def build_report(
    repo: pathlib.Path,
    roots: list[str],
    exclude_file: str = "",
    out_prefix: str = "data/pending_embedding_paths",
    chunk_size: int = 2000,
) -> dict:
    return list_embedding_gaps(
        repo=repo,
        roots=roots,
        exclude_file=exclude_file,
        out_prefix=out_prefix,
        chunk_size=chunk_size,
    )


def main() -> int:
    args = parse_args()
    repo = pathlib.Path(args.repo).resolve()
    if not args.music_root:
        raise SystemExit("Provide at least one --music-root")
    roots = [str(pathlib.Path(path).expanduser()) for path in args.music_root]
    report = build_report(
        repo,
        roots,
        exclude_file=args.exclude_file,
        out_prefix=args.out_prefix,
        chunk_size=args.chunk_size,
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
