#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
from collections import Counter
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write a concise summary for a maintenance run folder.")
    parser.add_argument("--run-dir", required=True, help="Path to the maintenance run directory.")
    parser.add_argument(
        "--output",
        default="",
        help="Optional output markdown file path (defaults to maintenance_summary.md inside the run dir).",
    )
    return parser.parse_args()


def _load_json(path: pathlib.Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _failure_summary(failed_log: pathlib.Path) -> dict[str, Any]:
    phase_counts = Counter()
    error_counts = Counter()
    if not failed_log.exists():
        return {"phase_counts": {}, "error_counts": {}, "failed_total": 0}
    for line in failed_log.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        phase_counts[rec.get("phase", "unknown")] += 1
        error_counts[rec.get("error", "unknown")] += 1
    return {
        "phase_counts": dict(phase_counts),
        "error_counts": dict(error_counts.most_common(10)),
        "failed_total": sum(phase_counts.values()),
    }


def build_summary(run_dir: pathlib.Path) -> str:
    status = _load_json(run_dir / "status.json")
    lines = [
        "# Maintenance Run Summary",
        "",
        f"- Run dir: `{run_dir}`",
        f"- State: `{status.get('state', '')}`",
        f"- Current phase: `{status.get('current_phase', '')}`",
        "",
        "## Phases",
        "",
    ]
    for phase in status.get("phases", []):
        line = f"- `{phase.get('name', '')}`: `{phase.get('status', '')}`"
        if phase.get("note"):
            line += f" | {phase.get('note')}"
        lines.append(line)
    summary = status.get("summary", {})
    if summary:
        lines.extend(["", "## Status Summary", ""])
        for key, value in summary.items():
            lines.append(f"- {key}: `{value}`")

    checkpoint = run_dir / "embed_checkpoint.json"
    if checkpoint.exists():
        checkpoint_data = _load_json(checkpoint)
        lines.extend(["", "## Embed Checkpoint", ""])
        for key in ("device", "paths_total", "paths_completed", "paths_failed"):
            if key in checkpoint_data:
                lines.append(f"- {key}: `{checkpoint_data[key]}`")
        recovery = checkpoint_data.get("recovery", {})
        if recovery:
            lines.extend(["", "## CUDA Recovery", ""])
            for key, value in recovery.items():
                lines.append(f"- {key}: `{value}`")
        failed_log_path = checkpoint_data.get("failed_log")
        if failed_log_path:
            failed_summary = _failure_summary(pathlib.Path(failed_log_path))
            lines.extend(["", "## Failure Summary", ""])
            lines.append(f"- failed_total: `{failed_summary['failed_total']}`")
            if failed_summary["phase_counts"]:
                lines.append("- phase_counts:")
                for key, value in failed_summary["phase_counts"].items():
                    lines.append(f"  - {key}: `{value}`")
            if failed_summary["error_counts"]:
                lines.append("- top_errors:")
                for key, value in failed_summary["error_counts"].items():
                    lines.append(f"  - {value}: `{key}`")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    run_dir = pathlib.Path(args.run_dir).resolve()
    output = pathlib.Path(args.output).resolve() if args.output else run_dir / "maintenance_summary.md"
    output.write_text(build_summary(run_dir), encoding="utf-8")
    print(json.dumps({"run_dir": str(run_dir), "summary": str(output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
