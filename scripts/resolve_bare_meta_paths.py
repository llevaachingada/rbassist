#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import pathlib

from rbassist.health import default_music_roots, resolve_bare_meta_paths


CSV_FIELDS = [
    "source_bare_path",
    "candidate_path",
    "classification",
    "confidence",
    "match_reasons",
    "action_taken",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve bare/orphan meta.json track paths against real music files.")
    parser.add_argument("--repo", default=".", help="Repo root.")
    parser.add_argument("--music-root", action="append", default=[], help="Music root to scan. Repeatable.")
    parser.add_argument("--min-confidence", type=float, default=0.92, help="Minimum confidence required for auto-apply.")
    parser.add_argument("--apply", action="store_true", help="Write only high-confidence bare-path fixes back to meta.json.")
    parser.add_argument("--out", default="", help="Back-compat alias for JSON output path.")
    parser.add_argument("--out-json", default="", help="Optional JSON output path.")
    parser.add_argument("--out-csv", default="", help="Optional CSV review output path.")
    return parser.parse_args()


def build_report(repo: pathlib.Path, roots: list[str], *, apply_changes: bool, min_confidence: float) -> dict:
    effective_roots = roots or default_music_roots()
    return resolve_bare_meta_paths(
        repo=repo,
        roots=effective_roots,
        apply_changes=apply_changes,
        min_confidence=min_confidence,
    )


def _resolve_out(repo: pathlib.Path, raw: str) -> pathlib.Path:
    path = pathlib.Path(raw)
    if not path.is_absolute():
        path = repo / path
    return path


def _write_csv(path: pathlib.Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            flat = dict(row)
            if isinstance(flat.get("match_reasons"), list):
                flat["match_reasons"] = json.dumps(flat["match_reasons"], ensure_ascii=False)
            writer.writerow({key: flat.get(key, "") for key in CSV_FIELDS})


def main() -> int:
    args = parse_args()
    repo = pathlib.Path(args.repo).resolve()
    roots = [str(pathlib.Path(root).expanduser()) for root in args.music_root]
    report = build_report(repo, roots, apply_changes=args.apply, min_confidence=args.min_confidence)
    text = json.dumps(report, indent=2)

    out_json = args.out_json or args.out
    if out_json:
        out = _resolve_out(repo, out_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    if args.out_csv:
        _write_csv(_resolve_out(repo, args.out_csv), report.get("entries", []))
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
