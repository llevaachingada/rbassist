#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
import sys

from rbassist.rekordbox_review import build_review_queues, write_review_queues


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Split a Rekordbox audit report into smaller review queues.")
    parser.add_argument("--audit-report", required=True, help="Path to a JSON report from scripts/rekordbox_audit_library.py")
    parser.add_argument("--out-dir", required=True, help="Directory for review queue artifacts")
    parser.add_argument("--prefix", default="rekordbox_review", help="Filename prefix for the generated queues")
    return parser.parse_args()


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    args = parse_args()
    report = json.loads(pathlib.Path(args.audit_report).read_text(encoding="utf-8"))
    queues = build_review_queues(report)
    outputs = write_review_queues(queues, out_dir=args.out_dir, prefix=args.prefix)
    payload = {"counts": queues["counts"], "outputs": outputs}
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
