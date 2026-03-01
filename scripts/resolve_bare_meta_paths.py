#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib

from rbassist.health import default_music_roots, resolve_bare_meta_paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve bare/orphan meta.json track paths against real music files.")
    parser.add_argument("--repo", default=".", help="Repo root.")
    parser.add_argument("--music-root", action="append", default=[], help="Music root to scan. Repeatable.")
    parser.add_argument("--apply", action="store_true", help="Write safe bare-path fixes back to meta.json.")
    parser.add_argument("--out", default="", help="Optional JSON output path.")
    return parser.parse_args()


def build_report(repo: pathlib.Path, roots: list[str], *, apply_changes: bool) -> dict:
    effective_roots = roots or default_music_roots()
    return resolve_bare_meta_paths(repo=repo, roots=effective_roots, apply_changes=apply_changes)


def main() -> int:
    args = parse_args()
    repo = pathlib.Path(args.repo).resolve()
    roots = [str(pathlib.Path(root).expanduser()) for root in args.music_root]
    report = build_report(repo, roots, apply_changes=args.apply)
    text = json.dumps(report, indent=2)
    if args.out:
        out = pathlib.Path(args.out)
        if not out.is_absolute():
            out = repo / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
