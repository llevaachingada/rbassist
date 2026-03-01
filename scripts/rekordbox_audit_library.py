#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
import sys

from rbassist.rekordbox_audit import audit_rekordbox_library, dump_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only Rekordbox library audit against a canonical music root.")
    parser.add_argument("--music-root", required=True, help="Canonical music root to treat as the source of truth.")
    parser.add_argument(
        "--consolidate-root",
        default="",
        help="Optional suggested destination root for outside-root files that should be moved under the music root.",
    )
    parser.add_argument("--duration-tolerance-s", type=float, default=2.0, help="Duplicate/relink duration tolerance in seconds.")
    parser.add_argument("--top-candidates", type=int, default=5, help="How many relink candidates to keep per Rekordbox row.")
    parser.add_argument("--catalog-workers", type=int, default=8, help="Worker threads for media cataloging.")
    parser.add_argument("--out", default="", help="Optional JSON output path.")
    return parser.parse_args()


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    args = parse_args()
    report = audit_rekordbox_library(
        music_root=args.music_root,
        consolidate_root=(args.consolidate_root or None),
        duration_tolerance_s=max(0.1, float(args.duration_tolerance_s)),
        top_candidates=max(1, int(args.top_candidates)),
        catalog_workers=max(1, int(args.catalog_workers)),
    )
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.out:
        out = dump_report(report, pathlib.Path(args.out))
        print(f"WROTE={out}")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
