#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib

from rbassist.health import audit_meta_health, default_music_roots


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit rbassist meta health.")
    parser.add_argument("--repo", default=".", help="Repo root.")
    parser.add_argument("--root", action="append", default=[], help="Active music root. Repeat for multiple roots.")
    parser.add_argument("--rekordbox-report", default="", help="Optional Rekordbox audit JSON to enrich stale classification counts.")
    parser.add_argument("--out", default="", help="Optional JSON output path.")
    return parser.parse_args()


def _load_json(path_ref: str) -> dict | None:
    if not path_ref:
        return None
    path = pathlib.Path(path_ref)
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def build_report(repo: pathlib.Path, *, roots: list[str], rekordbox_report: dict | None) -> dict:
    chosen_roots = roots or default_music_roots()
    return audit_meta_health(repo=repo, roots=chosen_roots, rekordbox_report=rekordbox_report)


def main() -> int:
    args = parse_args()
    repo = pathlib.Path(args.repo).resolve()
    report = build_report(repo, roots=args.root, rekordbox_report=_load_json(args.rekordbox_report))
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
