from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone
from typing import Iterable

from .utils import normalize_path_string


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def quarantine_reason_for_failure(error: str, *, size_bytes: int | None = None) -> str | None:
    text = str(error or '')
    if size_bytes == 0 or 'EOFError()' in text:
        return 'decode_eof'
    if 'NoBackendError()' in text:
        return 'decode_backend'
    if "Kernel size can't be greater than actual input size" in text:
        return 'audio_too_short'
    if 'float division by zero' in text:
        return 'zero_division_audio'
    return None


def load_quarantine_records(path_ref: str | pathlib.Path) -> list[dict]:
    path = pathlib.Path(path_ref)
    if not path.exists():
        return []
    records: list[dict] = []
    for line in path.read_text(encoding='utf-8', errors='ignore').splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except Exception:
            continue
        if isinstance(record, dict) and str(record.get('path', '')).strip():
            records.append(record)
    return records


def load_quarantine_paths(path_ref: str | pathlib.Path) -> list[str]:
    seen: set[str] = set()
    paths: list[str] = []
    for record in load_quarantine_records(path_ref):
        path = str(record.get('path', '')).strip()
        normalized = normalize_path_string(path)
        if not path or normalized in seen:
            continue
        seen.add(normalized)
        paths.append(path)
    return paths


def merge_quarantine_records(existing: Iterable[dict], new: Iterable[dict]) -> list[dict]:
    merged: dict[str, dict] = {}

    def _ingest(record: dict, *, default_time: str) -> None:
        path = str(record.get('path', '')).strip()
        if not path:
            return
        normalized = normalize_path_string(path)
        current = merged.get(normalized)
        if current is None:
            merged[normalized] = {
                'path': path,
                'reason': record.get('reason', 'unknown'),
                'phase': record.get('phase', ''),
                'first_seen': record.get('first_seen') or record.get('timestamp') or default_time,
                'last_seen': record.get('last_seen') or record.get('timestamp') or default_time,
                'attempts': int(record.get('attempts', 1) or 1),
                'size_bytes': record.get('size_bytes'),
                'source': record.get('source', ''),
            }
            return
        current['last_seen'] = record.get('last_seen') or record.get('timestamp') or default_time
        current['attempts'] = int(current.get('attempts', 1) or 1) + int(record.get('attempts', 1) or 1)
        if record.get('reason'):
            current['reason'] = record['reason']
        if record.get('phase'):
            current['phase'] = record['phase']
        if record.get('size_bytes') is not None:
            current['size_bytes'] = record.get('size_bytes')
        if record.get('source'):
            current['source'] = record.get('source')

    now = _utc_now()
    for record in existing:
        _ingest(record, default_time=now)
    for record in new:
        _ingest(record, default_time=now)
    return sorted(merged.values(), key=lambda item: normalize_path_string(item['path']))


def write_quarantine_records(path_ref: str | pathlib.Path, records: Iterable[dict]) -> pathlib.Path:
    path = pathlib.Path(path_ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, ensure_ascii=False) for record in records]
    path.write_text('\n'.join(lines) + ('\n' if lines else ''), encoding='utf-8')
    return path
