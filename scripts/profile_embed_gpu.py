#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import statistics
import subprocess
import time
from typing import Any


GPU_QUERY_FIELDS = [
    "timestamp",
    "utilization.gpu",
    "utilization.memory",
    "memory.used",
    "memory.total",
    "temperature.gpu",
    "power.draw",
    "pstate",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Profile GPU telemetry during rbassist embedding phases.")
    p.add_argument("--repo", default=".", help="Path to rbassist repo root.")
    p.add_argument(
        "--bench-file",
        default="data/bench_paths_cuda6h_8.txt",
        help="Text file with one audio path per line for benchmark phases.",
    )
    p.add_argument("--output-dir", default="data/runlogs", help="Directory for JSON/MD outputs.")
    p.add_argument("--report-prefix", default="embedding_gpu_report", help="Output file prefix.")
    p.add_argument("--sample-interval", type=float, default=1.0, help="GPU sample interval in seconds.")
    p.add_argument("--device", default="cuda", help="Device passed to rbassist embed (default: cuda).")
    p.add_argument("--batch-size", type=int, default=4, help="Batch size passed to embed CLI.")
    return p.parse_args()


def quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    idx = (len(values) - 1) * q
    lo = int(idx)
    hi = min(lo + 1, len(values) - 1)
    frac = idx - lo
    return values[lo] * (1.0 - frac) + values[hi] * frac


def query_gpu_once() -> dict[str, Any] | None:
    cmd = [
        "nvidia-smi",
        f"--query-gpu={','.join(GPU_QUERY_FIELDS)}",
        "--format=csv,noheader,nounits",
    ]
    try:
        line = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None
    parts = [x.strip() for x in line.split(",")]
    if len(parts) != len(GPU_QUERY_FIELDS):
        return None
    try:
        return {
            "timestamp": parts[0],
            "gpu_util": float(parts[1]),
            "mem_util": float(parts[2]),
            "mem_used_mb": float(parts[3]),
            "mem_total_mb": float(parts[4]),
            "temp_c": float(parts[5]),
            "power_w": float(parts[6]),
            "pstate": parts[7],
        }
    except Exception:
        return None


def summarize_samples(samples: list[dict[str, Any]]) -> dict[str, Any]:
    if not samples:
        return {"samples": 0}
    gpu_vals = sorted(s["gpu_util"] for s in samples)
    temp_vals = sorted(s["temp_c"] for s in samples)
    power_vals = sorted(s["power_w"] for s in samples)
    mem_vals = sorted(s["mem_used_mb"] for s in samples)
    return {
        "samples": len(samples),
        "gpu_avg": round(statistics.mean(gpu_vals), 2),
        "gpu_p95": round(quantile(gpu_vals, 0.95), 2),
        "gpu_max": round(max(gpu_vals), 2),
        "temp_avg_c": round(statistics.mean(temp_vals), 2),
        "temp_max_c": round(max(temp_vals), 2),
        "power_avg_w": round(statistics.mean(power_vals), 2),
        "power_max_w": round(max(power_vals), 2),
        "mem_avg_mb": round(statistics.mean(mem_vals), 2),
        "mem_max_mb": round(max(mem_vals), 2),
        "pstates": sorted({s["pstate"] for s in samples}),
    }


def extract_summary_line(stdout: str, stderr: str) -> str:
    merged = f"{stdout}\n{stderr}"
    for line in merged.splitlines():
        if "Embedding summary:" in line:
            return line.strip()
    for line in merged.splitlines():
        t = line.strip()
        if t:
            return t[:240]
    return ""


def run_phase(name: str, cmd: list[str], cwd: pathlib.Path, interval: float) -> dict[str, Any]:
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    t0 = time.time()
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    samples: list[dict[str, Any]] = []
    while proc.poll() is None:
        s = query_gpu_once()
        if s is not None:
            s["elapsed_s"] = round(time.time() - t0, 3)
            samples.append(s)
        time.sleep(max(0.2, interval))
    stdout, stderr = proc.communicate()
    duration_s = round(time.time() - t0, 3)
    return {
        "phase": name,
        "started_at": started,
        "duration_s": duration_s,
        "returncode": proc.returncode,
        "command": cmd,
        "summary_line": extract_summary_line(stdout or "", stderr or ""),
        "stdout_tail": (stdout or "")[-4000:],
        "stderr_tail": (stderr or "")[-4000:],
        "gpu_summary": summarize_samples(samples),
        "gpu_samples": samples,
    }


def write_report(md_path: pathlib.Path, payload: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# Embedding GPU Telemetry Report")
    lines.append("")
    lines.append(f"- Generated (UTC): {payload['generated_at']}")
    lines.append(f"- Repo: `{payload['repo']}`")
    lines.append(f"- Bench file: `{payload['bench_file']}`")
    lines.append("")
    lines.append("| Phase | RC | Dur(s) | GPU avg | GPU p95 | GPU max | Temp avg | Temp max | Power avg | Power max | Samples |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for ph in payload["phases"]:
        gs = ph.get("gpu_summary", {})
        lines.append(
            "| {phase} | {rc} | {dur} | {gavg} | {gp95} | {gmax} | {tavg} | {tmax} | {pavg} | {pmax} | {n} |".format(
                phase=ph["phase"],
                rc=ph["returncode"],
                dur=ph["duration_s"],
                gavg=gs.get("gpu_avg", "n/a"),
                gp95=gs.get("gpu_p95", "n/a"),
                gmax=gs.get("gpu_max", "n/a"),
                tavg=gs.get("temp_avg_c", "n/a"),
                tmax=gs.get("temp_max_c", "n/a"),
                pavg=gs.get("power_avg_w", "n/a"),
                pmax=gs.get("power_max_w", "n/a"),
                n=gs.get("samples", 0),
            )
        )
    lines.append("")
    for ph in payload["phases"]:
        lines.append(f"## {ph['phase']}")
        lines.append("")
        lines.append(f"- Return code: `{ph['returncode']}`")
        lines.append(f"- Duration: `{ph['duration_s']}s`")
        if ph.get("summary_line"):
            lines.append(f"- Embed summary: `{ph['summary_line']}`")
        gs = ph.get("gpu_summary", {})
        if gs.get("samples", 0) > 0:
            lines.append(
                f"- GPU: avg `{gs.get('gpu_avg')}%`, p95 `{gs.get('gpu_p95')}%`, max `{gs.get('gpu_max')}%`"
            )
            lines.append(
                f"- Temp: avg `{gs.get('temp_avg_c')}C`, max `{gs.get('temp_max_c')}C`; "
                f"Power avg `{gs.get('power_avg_w')}W`, max `{gs.get('power_max_w')}W`"
            )
            lines.append(f"- P-states seen: `{', '.join(gs.get('pstates', []))}`")
        else:
            lines.append("- No GPU samples captured for this phase.")
        lines.append("")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    repo = pathlib.Path(args.repo).resolve()
    out_dir = (repo / args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    bench_file = (repo / args.bench_file).resolve()
    if not bench_file.exists():
        raise FileNotFoundError(f"Bench file not found: {bench_file}")
    bench_paths = [ln.strip() for ln in bench_file.read_text(encoding="utf-8", errors="ignore").splitlines() if ln.strip()]
    if not bench_paths:
        raise RuntimeError(f"Bench file has no usable paths: {bench_file}")

    one_track = out_dir / "bench_paths_one_track.txt"
    one_track.write_text(bench_paths[0] + "\n", encoding="utf-8")

    ck_dir = repo / "data" / "checkpoints"
    ck_dir.mkdir(parents=True, exist_ok=True)
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    phases = [
        (
            "warmup_1track_w4",
            [
                "python",
                "-m",
                "rbassist.cli",
                "embed",
                "--paths-file",
                str(one_track),
                "--device",
                args.device,
                "--num-workers",
                "4",
                "--batch-size",
                str(max(1, args.batch_size)),
                "--checkpoint-file",
                str(ck_dir / f"profile_{ts}_warmup.json"),
                "--checkpoint-every",
                "1",
            ],
        ),
        (
            "steady_8track_w4",
            [
                "python",
                "-m",
                "rbassist.cli",
                "embed",
                "--paths-file",
                str(bench_file),
                "--device",
                args.device,
                "--num-workers",
                "4",
                "--batch-size",
                str(max(1, args.batch_size)),
                "--checkpoint-file",
                str(ck_dir / f"profile_{ts}_w4.json"),
                "--checkpoint-every",
                "3",
            ],
        ),
        (
            "steady_8track_w2",
            [
                "python",
                "-m",
                "rbassist.cli",
                "embed",
                "--paths-file",
                str(bench_file),
                "--device",
                args.device,
                "--num-workers",
                "2",
                "--batch-size",
                str(max(1, args.batch_size)),
                "--checkpoint-file",
                str(ck_dir / f"profile_{ts}_w2.json"),
                "--checkpoint-every",
                "3",
            ],
        ),
    ]

    phase_results: list[dict[str, Any]] = []
    for name, cmd in phases:
        phase_results.append(run_phase(name=name, cmd=cmd, cwd=repo, interval=args.sample_interval))

    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "repo": str(repo),
        "bench_file": str(bench_file),
        "phases": phase_results,
    }
    json_path = out_dir / f"{args.report_prefix}_{ts}.json"
    md_path = out_dir / f"{args.report_prefix}_{ts}.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    write_report(md_path, payload)

    print(f"JSON_REPORT={json_path}")
    print(f"MD_REPORT={md_path}")
    for phase in phase_results:
        gs = phase.get("gpu_summary", {})
        print(
            f"PHASE {phase['phase']}: rc={phase['returncode']} dur={phase['duration_s']}s "
            f"gpu_avg={gs.get('gpu_avg')} gpu_max={gs.get('gpu_max')} temp_max={gs.get('temp_max_c')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
