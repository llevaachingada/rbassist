#!/usr/bin/env python3
"""Run rbassist embedding over chunked path files with resumable checkpoints.

This runner treats GPU chunk workers as disposable. If a chunk fails with a
CUDA fault, it will retry smaller sub-chunks first and then fall back to CPU
for the smallest retry set instead of poisoning one long-lived process.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CUDA_ERROR_MARKERS = (
    'acceleratorerror',
    'cuda error',
    'invalid program counter',
    'illegal memory access',
    'cudnn',
    'cublas',
)


@dataclass
class ChunkAttemptResult:
    status: str
    returncode: int
    checkpoint_path: Path
    failed_log_path: Path | None
    checkpoint: dict[str, Any]
    error_counts: dict[str, int]
    queued: int
    succeeded: int
    failed: int
    output: str
    device: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run rbassist embed against chunk files with per-chunk checkpoints."
    )
    parser.add_argument(
        "--repo",
        default=".",
        help="Path to rbassist repository root (default: current directory).",
    )
    parser.add_argument(
        "--chunk-glob",
        default="data/pending_embedding_paths.part*.txt",
        help="Glob pattern (relative to repo) selecting chunk path files.",
    )
    parser.add_argument(
        "--checkpoint-dir",
        default="data/checkpoints",
        help="Directory (relative to repo) for chunk checkpoint files.",
    )
    parser.add_argument(
        "--checkpoint-every",
        type=int,
        default=100,
        help="Checkpoint write cadence passed to `rbassist embed`.",
    )
    parser.add_argument(
        "--num-workers",
        type=int,
        default=8,
        help="Number of audio loader workers for `rbassist embed`.",
    )
    parser.add_argument(
        "--device",
        default="auto",
        choices=("auto", "cuda", "rocm", "mps", "cpu"),
        help="Device to pass to `rbassist embed` (auto omits --device).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=0,
        help="Optional embed batch size (0 uses rbassist default auto-batch).",
    )
    parser.add_argument(
        "--start-index",
        type=int,
        default=1,
        help="Start chunk index (1-based, after sorting).",
    )
    parser.add_argument(
        "--end-index",
        type=int,
        default=0,
        help="End chunk index inclusive (0 means process all).",
    )
    parser.add_argument(
        "--min-chunk-size",
        type=int,
        default=250,
        help="Minimum chunk size before switching from split retries to CPU fallback.",
    )
    parser.add_argument(
        "--max-split-depth",
        type=int,
        default=3,
        help="Maximum recursive split depth for CUDA-faulted chunks.",
    )
    parser.add_argument(
        "--disable-cpu-fallback",
        action="store_true",
        help="Do not retry CUDA-faulted chunks on CPU once they reach the minimum split size.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without running them.",
    )
    return parser.parse_args()


def _is_cuda_error_text(text: str) -> bool:
    lowered = str(text or '').lower()
    return any(marker in lowered for marker in CUDA_ERROR_MARKERS)


def _read_chunk_paths(chunk_path: Path) -> list[str]:
    paths: list[str] = []
    for line in chunk_path.read_text(encoding='utf-8').splitlines():
        entry = line.strip()
        if not entry or entry.startswith('#'):
            continue
        if (entry.startswith('"') and entry.endswith('"')) or (entry.startswith("'") and entry.endswith("'")):
            entry = entry[1:-1].strip()
        if entry:
            paths.append(entry)
    return paths


def _write_chunk_paths(path: Path, paths: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(paths) + ('\n' if paths else ''), encoding='utf-8')
    return path


def _load_checkpoint(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _failed_log_path(checkpoint_path: Path, checkpoint: dict[str, Any]) -> Path:
    path_ref = checkpoint.get('failed_log')
    if path_ref:
        return Path(str(path_ref))
    return checkpoint_path.with_name(f'{checkpoint_path.stem}_failed.jsonl')


def _count_failed_errors(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    counts: dict[str, int] = {}
    for line in path.read_text(encoding='utf-8', errors='ignore').splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except Exception:
            continue
        error = str(record.get('error', 'unknown'))
        counts[error] = counts.get(error, 0) + 1
    return counts


def _checkpoint_path_for_chunk(checkpoint_dir: Path, chunk_path: Path, *, suffix: str = '') -> Path:
    safe_stem = chunk_path.stem.replace(' ', '_')
    return checkpoint_dir / f'embed_checkpoint_{safe_stem}{suffix}.json'


def _build_embed_cmd(
    *,
    repo: Path,
    chunk_path: Path,
    checkpoint_path: Path,
    checkpoint_every: int,
    num_workers: int,
    device: str,
    batch_size: int,
) -> list[str]:
    cmd = [
        sys.executable,
        '-m',
        'rbassist.cli',
        'embed',
        '--paths-file',
        str(chunk_path),
        '--resume',
        '--checkpoint-file',
        str(checkpoint_path),
        '--checkpoint-every',
        str(max(1, int(checkpoint_every))),
        '--num-workers',
        str(max(0, int(num_workers))),
    ]
    if device != 'auto':
        cmd.extend(['--device', device])
    if int(batch_size) > 0:
        cmd.extend(['--batch-size', str(int(batch_size))])
    return cmd


def _classify_attempt(
    *,
    returncode: int,
    output: str,
    checkpoint_path: Path,
    device: str,
) -> ChunkAttemptResult:
    checkpoint = _load_checkpoint(checkpoint_path)
    counters = checkpoint.get('counters', {}) if isinstance(checkpoint.get('counters'), dict) else {}
    queued = int(counters.get('queued', checkpoint.get('paths_queued', 0)) or 0)
    succeeded = int(counters.get('succeeded', checkpoint.get('paths_completed', 0)) or 0)
    failed = int(counters.get('failed', checkpoint.get('paths_failed', 0)) or 0)
    failed_log = _failed_log_path(checkpoint_path, checkpoint)
    error_counts = _count_failed_errors(failed_log)
    recovery = checkpoint.get('recovery', {}) if isinstance(checkpoint.get('recovery'), dict) else {}
    has_cuda = _is_cuda_error_text(output) or any(_is_cuda_error_text(err) for err in error_counts)
    if any(int(recovery.get(key, 0) or 0) > 0 for key in ('cuda_retries', 'cuda_retry_failures', 'cuda_rebuild_failures')):
        has_cuda = True
    fatal_cuda = has_cuda and failed > 0 and succeeded == 0

    if returncode != 0:
        status = 'cuda_fault' if has_cuda else 'crash'
    elif checkpoint.get('status') == 'completed':
        if fatal_cuda:
            status = 'cuda_fault'
        elif failed > 0:
            status = 'completed_with_failures'
        else:
            status = 'ok'
    elif has_cuda:
        status = 'cuda_fault'
    else:
        status = 'crash'

    return ChunkAttemptResult(
        status=status,
        returncode=returncode,
        checkpoint_path=checkpoint_path,
        failed_log_path=failed_log if failed_log.exists() else None,
        checkpoint=checkpoint,
        error_counts=error_counts,
        queued=queued,
        succeeded=succeeded,
        failed=failed,
        output=output,
        device=device,
    )


def _run_chunk_attempt(
    *,
    repo: Path,
    chunk_path: Path,
    checkpoint_path: Path,
    checkpoint_every: int,
    num_workers: int,
    device: str,
    batch_size: int,
    dry_run: bool,
) -> ChunkAttemptResult:
    cmd = _build_embed_cmd(
        repo=repo,
        chunk_path=chunk_path,
        checkpoint_path=checkpoint_path,
        checkpoint_every=checkpoint_every,
        num_workers=num_workers,
        device=device,
        batch_size=batch_size,
    )
    print(' '.join(cmd))
    if dry_run:
        return ChunkAttemptResult(
            status='ok',
            returncode=0,
            checkpoint_path=checkpoint_path,
            failed_log_path=None,
            checkpoint={},
            error_counts={},
            queued=len(_read_chunk_paths(chunk_path)),
            succeeded=0,
            failed=0,
            output='',
            device=device,
        )

    proc = subprocess.run(cmd, cwd=str(repo), capture_output=True, text=True)
    combined_output = (proc.stdout or '') + ('\n' + proc.stderr if proc.stderr else '')
    if proc.stdout:
        print(proc.stdout, end='')
    if proc.stderr:
        print(proc.stderr, end='', file=sys.stderr)
    return _classify_attempt(
        returncode=proc.returncode,
        output=combined_output,
        checkpoint_path=checkpoint_path,
        device=device,
    )


def _split_chunk_file(chunk_path: Path, paths: list[str], *, checkpoint_dir: Path, depth: int) -> tuple[Path, Path]:
    retry_dir = checkpoint_dir / 'retry_chunks'
    midpoint = max(1, len(paths) // 2)
    left = paths[:midpoint]
    right = paths[midpoint:]
    if not right:
        right = left[-1:]
        left = left[:-1]
    left_path = retry_dir / f'{chunk_path.stem}.d{depth + 1}a.txt'
    right_path = retry_dir / f'{chunk_path.stem}.d{depth + 1}b.txt'
    return _write_chunk_paths(left_path, left), _write_chunk_paths(right_path, right)


def _process_chunk(
    *,
    repo: Path,
    chunk_path: Path,
    checkpoint_dir: Path,
    checkpoint_every: int,
    num_workers: int,
    batch_size: int,
    device: str,
    min_chunk_size: int,
    max_split_depth: int,
    disable_cpu_fallback: bool,
    dry_run: bool,
    stats: dict[str, int],
    depth: int = 0,
) -> int:
    checkpoint_suffix = '' if device == 'cpu' else f'.{device}'
    checkpoint_path = _checkpoint_path_for_chunk(checkpoint_dir, chunk_path, suffix=checkpoint_suffix)
    result = _run_chunk_attempt(
        repo=repo,
        chunk_path=chunk_path,
        checkpoint_path=checkpoint_path,
        checkpoint_every=checkpoint_every,
        num_workers=num_workers,
        device=device,
        batch_size=batch_size,
        dry_run=dry_run,
    )

    if result.status == 'ok':
        stats['ok_chunks'] = stats.get('ok_chunks', 0) + 1
        return 0
    if result.status == 'completed_with_failures':
        stats['partial_chunks'] = stats.get('partial_chunks', 0) + 1
        print(
            f"Chunk completed with file-level failures: {chunk_path.name} "
            f"(failed={result.failed}, succeeded={result.succeeded})"
        )
        return 0

    chunk_paths = _read_chunk_paths(chunk_path)
    if result.status == 'cuda_fault' and device != 'cpu':
        stats['cuda_fault_chunks'] = stats.get('cuda_fault_chunks', 0) + 1
        if depth < max_split_depth and len(chunk_paths) > max(1, int(min_chunk_size)):
            left_path, right_path = _split_chunk_file(chunk_path, chunk_paths, checkpoint_dir=checkpoint_dir, depth=depth)
            stats['split_retries'] = stats.get('split_retries', 0) + 1
            print(
                f"CUDA fault in {chunk_path.name}; retrying smaller chunks "
                f"({left_path.name}, {right_path.name})."
            )
            left_rc = _process_chunk(
                repo=repo,
                chunk_path=left_path,
                checkpoint_dir=checkpoint_dir,
                checkpoint_every=checkpoint_every,
                num_workers=num_workers,
                batch_size=batch_size,
                device=device,
                min_chunk_size=min_chunk_size,
                max_split_depth=max_split_depth,
                disable_cpu_fallback=disable_cpu_fallback,
                dry_run=dry_run,
                stats=stats,
                depth=depth + 1,
            )
            right_rc = _process_chunk(
                repo=repo,
                chunk_path=right_path,
                checkpoint_dir=checkpoint_dir,
                checkpoint_every=checkpoint_every,
                num_workers=num_workers,
                batch_size=batch_size,
                device=device,
                min_chunk_size=min_chunk_size,
                max_split_depth=max_split_depth,
                disable_cpu_fallback=disable_cpu_fallback,
                dry_run=dry_run,
                stats=stats,
                depth=depth + 1,
            )
            return left_rc or right_rc

        if not disable_cpu_fallback:
            stats['cpu_fallback_attempts'] = stats.get('cpu_fallback_attempts', 0) + 1
            print(f"CUDA fault in {chunk_path.name}; retrying same chunk on CPU.")
            cpu_rc = _process_chunk(
                repo=repo,
                chunk_path=chunk_path,
                checkpoint_dir=checkpoint_dir,
                checkpoint_every=checkpoint_every,
                num_workers=0,
                batch_size=1,
                device='cpu',
                min_chunk_size=min_chunk_size,
                max_split_depth=max_split_depth,
                disable_cpu_fallback=True,
                dry_run=dry_run,
                stats=stats,
                depth=depth,
            )
            if cpu_rc == 0:
                stats['cpu_fallback_recovered'] = stats.get('cpu_fallback_recovered', 0) + 1
            return cpu_rc

    stats['failed_chunks'] = stats.get('failed_chunks', 0) + 1
    print(
        f"Chunk failed (status={result.status}, device={device}, file={chunk_path.name}). "
        f"Resume later with --start-index matching this chunk."
    )
    return result.returncode or 1


def main() -> int:
    args = parse_args()
    repo = Path(args.repo).resolve()
    chunk_pattern = str((repo / args.chunk_glob).as_posix())
    chunk_files = sorted(repo.glob(args.chunk_glob))

    if not chunk_files:
        raise FileNotFoundError(f"No chunk files found for pattern: {chunk_pattern}")

    start_idx = max(1, int(args.start_index))
    end_idx = int(args.end_index)
    if end_idx <= 0:
        end_idx = len(chunk_files)
    end_idx = min(end_idx, len(chunk_files))

    if start_idx > end_idx:
        raise ValueError(
            f"Invalid range start-index={start_idx}, end-index={end_idx} for {len(chunk_files)} chunks."
        )

    selected = chunk_files[start_idx - 1 : end_idx]
    checkpoint_dir = (repo / args.checkpoint_dir).resolve()
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    print(f"Repo: {repo}")
    print(f"Chunk files selected: {len(selected)} / {len(chunk_files)}")
    print(f"Checkpoint dir: {checkpoint_dir}")

    stats: dict[str, int] = {
        'ok_chunks': 0,
        'partial_chunks': 0,
        'cuda_fault_chunks': 0,
        'split_retries': 0,
        'cpu_fallback_attempts': 0,
        'cpu_fallback_recovered': 0,
        'failed_chunks': 0,
    }

    for idx, chunk_path in enumerate(selected, start=start_idx):
        print(f"\n[{idx}/{len(chunk_files)}] {chunk_path.name}")
        rc = _process_chunk(
            repo=repo,
            chunk_path=chunk_path,
            checkpoint_dir=checkpoint_dir,
            checkpoint_every=max(1, int(args.checkpoint_every)),
            num_workers=max(0, int(args.num_workers)),
            batch_size=int(args.batch_size),
            device=args.device,
            min_chunk_size=max(1, int(args.min_chunk_size)),
            max_split_depth=max(0, int(args.max_split_depth)),
            disable_cpu_fallback=bool(args.disable_cpu_fallback),
            dry_run=bool(args.dry_run),
            stats=stats,
            depth=0,
        )
        if rc != 0:
            print(f"Stopping after failed chunk index={idx}, file={chunk_path.name}.")
            print(json.dumps(stats, indent=2))
            return rc

    print("\nAll selected chunks finished.")
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
