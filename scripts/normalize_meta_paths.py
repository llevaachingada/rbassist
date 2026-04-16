#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib

from rbassist.health import normalize_meta_paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize and optionally rewrite rbassist meta paths.")
    parser.add_argument("--repo", default=".", help="Repo root.")
    parser.add_argument("--rewrite-from", action="append", default=[], help="Old path root prefix.")
    parser.add_argument("--rewrite-to", action="append", default=[], help="New path root prefix.")
    parser.add_argument("--drop-junk", action="store_true", help="Drop obvious junk entries like __MACOSX / AppleDouble.")
    parser.add_argument("--resolve-collisions", action="store_true", help="Safely merge slash/root duplicate path entries before applying.")
    parser.add_argument("--apply", action="store_true", help="Write changes back to meta.json.")
    parser.add_argument("--out", default="", help="Optional report path.")
    return parser.parse_args()


def build_report(
    repo: pathlib.Path,
    *,
    rewrite_from: list[str],
    rewrite_to: list[str],
    drop_junk: bool,
    resolve_collisions: bool,
    apply_changes: bool,
) -> dict:
    return normalize_meta_paths(
        repo=repo,
        rewrite_from=rewrite_from,
        rewrite_to=rewrite_to,
        drop_junk=drop_junk,
        resolve_collisions=resolve_collisions,
        apply_changes=apply_changes,
    )


def main() -> int:
    args = parse_args()
    repo = pathlib.Path(args.repo).resolve()
    report = build_report(
        repo,
        rewrite_from=args.rewrite_from,
        rewrite_to=args.rewrite_to,
        drop_junk=args.drop_junk,
        resolve_collisions=args.resolve_collisions,
        apply_changes=args.apply,
    )
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
