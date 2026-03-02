#!/usr/bin/env python3
from __future__ import annotations

import argparse
import pathlib

from rbassist.keeper_manifest import write_keeper_manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the rbassist keeper manifest for active workstream files.")
    parser.add_argument("--repo", default=".", help="Repo root.")
    parser.add_argument("--out-json", default="docs/dev/keeper_manifest_active_files.json", help="JSON output path, repo-relative by default.")
    parser.add_argument("--out-md", default="docs/dev/KEEPER_MANIFEST_ACTIVE_FILES.md", help="Markdown output path, repo-relative by default.")
    parser.add_argument("--include-live-state", action="store_true", help="Include a lightweight live-state summary from data/meta.json and quarantine.")
    return parser.parse_args()


def _resolve_output(repo: pathlib.Path, raw: str) -> pathlib.Path:
    path = pathlib.Path(raw)
    if not path.is_absolute():
        path = repo / path
    return path


def main() -> int:
    args = parse_args()
    repo = pathlib.Path(args.repo).resolve()
    outputs = write_keeper_manifest(
        repo=repo,
        out_json=_resolve_output(repo, args.out_json),
        out_md=_resolve_output(repo, args.out_md),
        include_live_state=args.include_live_state,
    )
    print(f"WROTE_JSON={outputs['json']}")
    print(f"WROTE_MD={outputs['md']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
