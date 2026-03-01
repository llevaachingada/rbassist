#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib

from rbassist.health import audit_meta_health


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit rbassist meta health.")
    parser.add_argument("--repo", default=".", help="Repo root.")
    parser.add_argument("--out", default="", help="Optional JSON output path.")
    return parser.parse_args()


def build_report(repo: pathlib.Path) -> dict:
    return audit_meta_health(repo=repo)


def main() -> int:
    args = parse_args()
    repo = pathlib.Path(args.repo).resolve()
    report = build_report(repo)
    text = json.dumps(report, indent=2)
    if args.out:
        out = pathlib.Path(args.out)
        if not out.is_absolute():
            out = repo / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"WROTE={out}")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
