#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib

from rbassist.quarantine import (
    load_quarantine_records,
    merge_quarantine_records,
    quarantine_reason_for_failure,
    write_quarantine_records,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Update durable embed quarantine from a failed-log JSONL file.')
    parser.add_argument('--failed-log', required=True, help='Path to embed_checkpoint_failed.jsonl')
    parser.add_argument('--quarantine-file', default='data/quarantine_embed.jsonl', help='Output quarantine JSONL path.')
    parser.add_argument('--repo', default='.', help='Repo root for resolving relative quarantine paths.')
    return parser.parse_args()


def build_new_records(failed_log: pathlib.Path) -> list[dict]:
    records: list[dict] = []
    if not failed_log.exists():
        return records
    for line in failed_log.read_text(encoding='utf-8', errors='ignore').splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except Exception:
            continue
        path = pathlib.Path(str(record.get('path', '')).strip())
        size_bytes = None
        try:
            size_bytes = path.stat().st_size
        except Exception:
            pass
        reason = quarantine_reason_for_failure(record.get('error', ''), size_bytes=size_bytes)
        if not reason:
            continue
        records.append(
            {
                'path': str(path),
                'reason': reason,
                'phase': record.get('phase', ''),
                'timestamp': record.get('timestamp', ''),
                'attempts': 1,
                'size_bytes': size_bytes,
                'source': str(failed_log),
            }
        )
    return records


def main() -> int:
    args = parse_args()
    repo = pathlib.Path(args.repo).resolve()
    failed_log = pathlib.Path(args.failed_log).resolve()
    quarantine_file = pathlib.Path(args.quarantine_file)
    if not quarantine_file.is_absolute():
        quarantine_file = (repo / quarantine_file).resolve()

    existing = load_quarantine_records(quarantine_file)
    new_records = build_new_records(failed_log)
    merged = merge_quarantine_records(existing, new_records)
    output = write_quarantine_records(quarantine_file, merged)
    print(json.dumps({
        'failed_log': str(failed_log),
        'quarantine_file': str(output),
        'existing_records': len(existing),
        'new_records': len(new_records),
        'merged_records': len(merged),
    }, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
