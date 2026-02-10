#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import statistics
import subprocess
import sys
import time
from typing import Any


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run rbassist embedding with live telemetry and auto-write a completion summary."
    )
    p.add_argument("--repo", default=".", help="Path to rbassist repo root.")
    p.add_argument(
        "--paths-file",
        required=True,
        help="Text file with one track path per line for rbassist embed.",
    )
    p.add_argument("--device", default="cuda", help="auto|cuda|rocm|mps|cpu")
    p.add_argument("--num-workers", type=int, default=3, help="Audio decode workers.")
    p.add_argument("--batch-size", type=int, default=4, help="Embed batch size argument.")
    p.add_argument("--resume", action="store_true", help="Pass --resume to embed command.")
    p.add_argument(
        "--checkpoint-file",
        default="data/checkpoints/embed_checkpoint_main.json",
        help="Checkpoint file path (absolute or repo-relative).",
    )
    p.add_argument("--checkpoint-every", type=int, default=50, help="Checkpoint cadence.")
    p.add_argument(
        "--telemetry-interval-s",
        type=float,
        default=3.0,
        help="Sampling interval for live telemetry script.",
    )
    p.add_argument(
        "--telemetry-idle-timeout-s",
        type=int,
        default=90,
        help="Idle timeout for telemetry process.",
    )
    p.add_argument(
        "--telemetry-wait-timeout-s",
        type=int,
        default=180,
        help="How long to wait for telemetry process to exit after embed stops.",
    )
    p.add_argument(
        "--max-hours",
        type=float,
        default=0.0,
        help="Optional max wall time in hours (0 disables timeout).",
    )
    p.add_argument(
        "--output-dir",
        default="data/runlogs",
        help="Directory for launcher logs and completion summary.",
    )
    p.add_argument(
        "--report-prefix",
        default="embed_autorun_summary",
        help="Prefix for completion summary files.",
    )
    return p.parse_args()


def _parse_telemetry_paths(output: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("CSV="):
            found["csv"] = line.split("=", 1)[1].strip()
        elif line.startswith("JSONL="):
            found["jsonl"] = line.split("=", 1)[1].strip()
        elif line.startswith("MD="):
            found["md"] = line.split("=", 1)[1].strip()
    return found


def _safe_int(v: Any) -> int:
    try:
        return int(v)
    except Exception:
        return 0


def _safe_float(v: Any) -> float | None:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except Exception:
        return None


def _load_checkpoint(path: pathlib.Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _count_jsonl_lines(path: pathlib.Path) -> int:
    if not path.exists():
        return 0
    n = 0
    with path.open("r", encoding="utf-8", errors="ignore") as fh:
        for _ in fh:
            n += 1
    return n


def _summarize_telemetry_csv(csv_path: pathlib.Path) -> dict[str, Any]:
    if not csv_path.exists():
        return {"rows": 0, "phase_stats": []}
    import csv

    rows = list(csv.DictReader(csv_path.open("r", encoding="utf-8", newline="")))
    phase_names = sorted({str(r.get("phase", "") or "") for r in rows})
    phase_stats: list[dict[str, Any]] = []
    for phase in phase_names:
        subset = [r for r in rows if str(r.get("phase", "") or "") == phase]
        gpu = [_safe_float(r.get("gpu_util_pct")) for r in subset]
        temp = [_safe_float(r.get("gpu_temp_c")) for r in subset]
        power = [_safe_float(r.get("gpu_power_w")) for r in subset]
        cpu = [_safe_float(r.get("cpu_total_pct")) for r in subset]
        gpu_v = [v for v in gpu if v is not None]
        temp_v = [v for v in temp if v is not None]
        power_v = [v for v in power if v is not None]
        cpu_v = [v for v in cpu if v is not None]
        phase_stats.append(
            {
                "phase": phase,
                "samples": len(subset),
                "gpu_avg_pct": round(statistics.mean(gpu_v), 2) if gpu_v else None,
                "gpu_max_pct": round(max(gpu_v), 2) if gpu_v else None,
                "gpu_temp_avg_c": round(statistics.mean(temp_v), 2) if temp_v else None,
                "gpu_temp_max_c": round(max(temp_v), 2) if temp_v else None,
                "gpu_power_avg_w": round(statistics.mean(power_v), 2) if power_v else None,
                "gpu_power_max_w": round(max(power_v), 2) if power_v else None,
                "cpu_total_avg_pct": round(statistics.mean(cpu_v), 2) if cpu_v else None,
                "cpu_total_max_pct": round(max(cpu_v), 2) if cpu_v else None,
            }
        )
    return {"rows": len(rows), "phase_stats": phase_stats}


def _to_repo_path(path_ref: str, repo: pathlib.Path) -> pathlib.Path:
    p = pathlib.Path(path_ref)
    if p.is_absolute():
        return p
    return (repo / p).resolve()


def _write_markdown(md_path: pathlib.Path, payload: dict[str, Any]) -> None:
    telemetry = payload.get("telemetry_summary", {})
    lines: list[str] = []
    lines.append("# Embed Auto-Run Completion Summary")
    lines.append("")
    lines.append(f"- Generated (UTC): {payload.get('generated_at')}")
    lines.append(f"- Repo: `{payload.get('repo')}`")
    lines.append(f"- Paths file: `{payload.get('paths_file')}`")
    lines.append(f"- Device: `{payload.get('device')}`")
    lines.append(f"- Workers / Batch: `{payload.get('num_workers')}` / `{payload.get('batch_size')}`")
    lines.append(f"- Resume: `{payload.get('resume')}`")
    lines.append(f"- Runtime seconds: `{payload.get('runtime_s')}`")
    lines.append(f"- Embed return code: `{payload.get('embed_returncode')}`")
    lines.append(f"- Timed out: `{payload.get('timed_out')}`")
    lines.append("")
    ck = payload.get("checkpoint_summary", {})
    lines.append("## Checkpoint")
    lines.append("")
    lines.append(f"- Checkpoint file: `{ck.get('checkpoint_file')}`")
    lines.append(f"- Status: `{ck.get('status')}`")
    lines.append(f"- Succeeded: `{ck.get('succeeded')}`")
    lines.append(f"- Failed: `{ck.get('failed')}`")
    lines.append(f"- Skipped existing: `{ck.get('skipped_existing')}`")
    lines.append(f"- Skipped checkpoint: `{ck.get('skipped_checkpoint')}`")
    lines.append(f"- Failed log lines: `{ck.get('failed_log_lines')}`")
    lines.append("")
    lines.append("## Telemetry")
    lines.append("")
    lines.append(f"- CSV: `{payload.get('telemetry_csv', '')}`")
    lines.append(f"- JSONL: `{payload.get('telemetry_jsonl', '')}`")
    lines.append(f"- MD: `{payload.get('telemetry_md', '')}`")
    lines.append(f"- Sample rows: `{telemetry.get('rows', 0)}`")
    lines.append("")
    lines.append("| Phase | Samples | GPU avg % | GPU max % | GPU temp max C | GPU power max W | CPU total avg % |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for ps in telemetry.get("phase_stats", []):
        lines.append(
            "| {phase} | {samples} | {gavg} | {gmax} | {tmax} | {pmax} | {cavg} |".format(
                phase=ps.get("phase", ""),
                samples=ps.get("samples", 0),
                gavg=ps.get("gpu_avg_pct", "n/a"),
                gmax=ps.get("gpu_max_pct", "n/a"),
                tmax=ps.get("gpu_temp_max_c", "n/a"),
                pmax=ps.get("gpu_power_max_w", "n/a"),
                cavg=ps.get("cpu_total_avg_pct", "n/a"),
            )
        )
    lines.append("")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    repo = pathlib.Path(args.repo).resolve()
    out_dir = (repo / args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    started = time.time()

    telemetry_prefix = f"telemetry_{args.report_prefix}_{run_id}"
    telemetry_cmd = [
        sys.executable,
        "scripts/live_phase_telemetry.py",
        "--repo",
        str(repo),
        "--interval-s",
        str(max(0.5, float(args.telemetry_interval_s))),
        "--idle-timeout-s",
        str(max(20, int(args.telemetry_idle_timeout_s))),
        "--output-dir",
        str(args.output_dir),
        "--prefix",
        telemetry_prefix,
    ]
    telemetry_proc = subprocess.Popen(
        telemetry_cmd,
        cwd=str(repo),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    checkpoint_file = _to_repo_path(args.checkpoint_file, repo)
    checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
    embed_cmd = [
        sys.executable,
        "-m",
        "rbassist.cli",
        "embed",
        "--paths-file",
        str(_to_repo_path(args.paths_file, repo)),
        "--checkpoint-file",
        str(checkpoint_file),
        "--checkpoint-every",
        str(max(1, int(args.checkpoint_every))),
        "--num-workers",
        str(max(0, int(args.num_workers))),
        "--batch-size",
        str(max(1, int(args.batch_size))),
    ]
    if args.resume:
        embed_cmd.append("--resume")
    if args.device and args.device != "auto":
        embed_cmd.extend(["--device", args.device])

    embed_proc = subprocess.Popen(embed_cmd, cwd=str(repo))
    timed_out = False
    max_seconds = float(args.max_hours) * 3600.0 if float(args.max_hours) > 0 else 0.0

    while True:
        rc = embed_proc.poll()
        if rc is not None:
            break
        elapsed = time.time() - started
        if max_seconds > 0 and elapsed > max_seconds:
            timed_out = True
            embed_proc.terminate()
            try:
                embed_proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                embed_proc.kill()
                embed_proc.wait(timeout=10)
            break
        time.sleep(5)

    embed_returncode = embed_proc.returncode if embed_proc.returncode is not None else 1

    # Let telemetry exit naturally after idle timeout; then force-stop if needed.
    telemetry_stdout = ""
    try:
        telemetry_stdout, _ = telemetry_proc.communicate(timeout=max(10, int(args.telemetry_wait_timeout_s)))
    except subprocess.TimeoutExpired:
        telemetry_proc.terminate()
        try:
            telemetry_stdout, _ = telemetry_proc.communicate(timeout=20)
        except subprocess.TimeoutExpired:
            telemetry_proc.kill()
            telemetry_stdout, _ = telemetry_proc.communicate(timeout=10)

    telemetry_paths = _parse_telemetry_paths(telemetry_stdout or "")
    telemetry_csv = pathlib.Path(telemetry_paths.get("csv", "")) if telemetry_paths.get("csv") else pathlib.Path("")
    telemetry_summary = _summarize_telemetry_csv(telemetry_csv) if telemetry_csv else {"rows": 0, "phase_stats": []}

    ck_data = _load_checkpoint(checkpoint_file)
    ck_counters = ck_data.get("counters", {}) if isinstance(ck_data, dict) else {}
    failed_log = checkpoint_file.with_name(f"{checkpoint_file.stem}_failed.jsonl")

    payload: dict[str, Any] = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "repo": str(repo),
        "run_id": run_id,
        "paths_file": str(_to_repo_path(args.paths_file, repo)),
        "device": args.device,
        "num_workers": int(args.num_workers),
        "batch_size": int(args.batch_size),
        "resume": bool(args.resume),
        "checkpoint_file": str(checkpoint_file),
        "runtime_s": round(time.time() - started, 2),
        "embed_returncode": embed_returncode,
        "timed_out": timed_out,
        "telemetry_csv": telemetry_paths.get("csv", ""),
        "telemetry_jsonl": telemetry_paths.get("jsonl", ""),
        "telemetry_md": telemetry_paths.get("md", ""),
        "checkpoint_summary": {
            "checkpoint_file": str(checkpoint_file),
            "status": ck_data.get("status"),
            "succeeded": _safe_int(ck_counters.get("succeeded")),
            "failed": _safe_int(ck_counters.get("failed")),
            "skipped_existing": _safe_int(ck_counters.get("skipped_existing")),
            "skipped_checkpoint": _safe_int(ck_counters.get("skipped_checkpoint")),
            "failed_log_file": str(failed_log),
            "failed_log_lines": _count_jsonl_lines(failed_log),
        },
        "telemetry_summary": telemetry_summary,
    }

    json_path = out_dir / f"{args.report_prefix}_{run_id}.json"
    md_path = out_dir / f"{args.report_prefix}_{run_id}.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_markdown(md_path, payload)

    print(f"SUMMARY_JSON={json_path}")
    print(f"SUMMARY_MD={md_path}")
    return embed_returncode


if __name__ == "__main__":
    raise SystemExit(main())
