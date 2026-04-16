#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import pathlib
import re
import statistics
import subprocess
import time
from typing import Any

import psutil


PHASE_PRIORITY = (
    "embed_cli",
    "embed_chunks_driver",
    "analyze",
    "index",
    "gpu_profile",
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Sample GPU/CPU telemetry every few seconds with inferred rbassist phase labels."
    )
    p.add_argument("--repo", default=".", help="Path to rbassist repository root.")
    p.add_argument("--interval-s", type=float, default=3.0, help="Sampling interval in seconds (3-5 recommended).")
    p.add_argument("--duration-s", type=int, default=0, help="Total duration in seconds (0 = until idle timeout).")
    p.add_argument(
        "--idle-timeout-s",
        type=int,
        default=120,
        help="Stop after this many idle seconds when duration is 0.",
    )
    p.add_argument("--output-dir", default="data/runlogs", help="Directory for output files.")
    p.add_argument("--prefix", default="phase_telemetry", help="Output file prefix.")
    return p.parse_args()


def _extract_arg(cmdline: str, flag: str) -> str:
    pat = re.compile(rf"{re.escape(flag)}\s+(\"[^\"]+\"|\S+)")
    m = pat.search(cmdline)
    if not m:
        return ""
    raw = m.group(1).strip()
    if raw.startswith('"') and raw.endswith('"'):
        raw = raw[1:-1]
    return raw


def _cpu_temp_best_effort() -> float | None:
    try:
        temps = psutil.sensors_temperatures()
    except Exception:
        temps = {}
    vals: list[float] = []
    for _, entries in temps.items():
        for ent in entries:
            cur = getattr(ent, "current", None)
            if isinstance(cur, (int, float)):
                vals.append(float(cur))
    if vals:
        return round(statistics.mean(vals), 2)
    return None


def _gpu_metrics() -> dict[str, Any]:
    cmd = [
        "nvidia-smi",
        "--query-gpu=timestamp,utilization.gpu,utilization.memory,memory.used,memory.total,temperature.gpu,power.draw,pstate",
        "--format=csv,noheader,nounits",
    ]
    try:
        line = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL).strip()
        parts = [x.strip() for x in line.split(",")]
        if len(parts) != 8:
            raise RuntimeError("unexpected nvidia-smi output")
        return {
            "gpu_timestamp": parts[0],
            "gpu_util_pct": float(parts[1]),
            "gpu_mem_util_pct": float(parts[2]),
            "gpu_mem_used_mb": float(parts[3]),
            "gpu_mem_total_mb": float(parts[4]),
            "gpu_temp_c": float(parts[5]),
            "gpu_power_w": float(parts[6]),
            "gpu_pstate": parts[7],
        }
    except Exception:
        return {
            "gpu_timestamp": "",
            "gpu_util_pct": None,
            "gpu_mem_util_pct": None,
            "gpu_mem_used_mb": None,
            "gpu_mem_total_mb": None,
            "gpu_temp_c": None,
            "gpu_power_w": None,
            "gpu_pstate": "",
        }


def _infer_phase(proc: psutil.Process) -> tuple[str, str, str]:
    try:
        cmdline = " ".join(proc.cmdline())
    except Exception:
        return ("other", "", "")
    low = cmdline.lower()
    if "rbassist.cli embed" in low:
        paths_file = _extract_arg(cmdline, "--paths-file")
        checkpoint_file = _extract_arg(cmdline, "--checkpoint-file")
        part = ""
        if paths_file:
            m = re.search(r"part(\d+)\.txt$", paths_file.replace("\\", "/"), flags=re.IGNORECASE)
            if m:
                part = f"part{m.group(1)}"
        detail = part or pathlib.Path(paths_file).name if paths_file else ""
        return ("embed_cli", detail, checkpoint_file)
    if "run_embed_chunks.py" in low:
        return ("embed_chunks_driver", "", "")
    if "rbassist.cli analyze" in low:
        return ("analyze", "", "")
    if "rbassist.cli index" in low:
        return ("index", "", "")
    if "profile_embed_gpu.py" in low:
        return ("gpu_profile", "", "")
    return ("other", "", "")


def _read_checkpoint_progress(path_ref: str, repo: pathlib.Path) -> dict[str, Any]:
    if not path_ref:
        return {}
    p = pathlib.Path(path_ref)
    if not p.is_absolute():
        p = (repo / p).resolve()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    counters = data.get("counters", {}) if isinstance(data, dict) else {}
    return {
        "checkpoint_file": str(p),
        "checkpoint_status": data.get("status"),
        "checkpoint_updated_at": data.get("updated_at"),
        "checkpoint_succeeded": counters.get("succeeded"),
        "checkpoint_failed": counters.get("failed"),
        "checkpoint_skipped_existing": counters.get("skipped_existing"),
        "checkpoint_skipped_checkpoint": counters.get("skipped_checkpoint"),
    }


def _pick_target_process() -> tuple[psutil.Process | None, str, str, str]:
    candidates: list[tuple[int, psutil.Process, str, str, str]] = []
    for proc in psutil.process_iter(attrs=["pid", "name", "cmdline"]):
        try:
            if proc.info.get("name", "").lower() not in {"python.exe", "python", "powershell.exe", "powershell"}:
                continue
            cmdline = " ".join(proc.info.get("cmdline") or [])
            if not cmdline:
                continue
            phase, detail, ck = _infer_phase(proc)
            if phase == "other":
                continue
            prio = PHASE_PRIORITY.index(phase) if phase in PHASE_PRIORITY else 99
            candidates.append((prio, proc, phase, detail, ck))
        except Exception:
            continue
    if not candidates:
        return (None, "idle", "", "")
    candidates.sort(key=lambda x: x[0])
    _, proc, phase, detail, ck = candidates[0]
    return (proc, phase, detail, ck)


def _phase_summary(samples: list[dict[str, Any]], phase: str) -> dict[str, Any]:
    rows = [s for s in samples if s.get("phase") == phase]
    if not rows:
        return {"phase": phase, "samples": 0}
    g = [float(s["gpu_util_pct"]) for s in rows if s.get("gpu_util_pct") is not None]
    t = [float(s["gpu_temp_c"]) for s in rows if s.get("gpu_temp_c") is not None]
    c = [float(s["cpu_total_pct"]) for s in rows if s.get("cpu_total_pct") is not None]
    return {
        "phase": phase,
        "samples": len(rows),
        "gpu_avg_pct": round(statistics.mean(g), 2) if g else None,
        "gpu_max_pct": round(max(g), 2) if g else None,
        "gpu_temp_avg_c": round(statistics.mean(t), 2) if t else None,
        "gpu_temp_max_c": round(max(t), 2) if t else None,
        "cpu_total_avg_pct": round(statistics.mean(c), 2) if c else None,
        "cpu_total_max_pct": round(max(c), 2) if c else None,
    }


def main() -> int:
    args = parse_args()
    repo = pathlib.Path(args.repo).resolve()
    out_dir = (repo / args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    jsonl_path = out_dir / f"{args.prefix}_{ts}.jsonl"
    csv_path = out_dir / f"{args.prefix}_{ts}.csv"
    md_path = out_dir / f"{args.prefix}_{ts}.md"

    # Prime cpu percent meters.
    psutil.cpu_percent(interval=None)
    proc_cpu_cache: dict[int, psutil.Process] = {}

    fieldnames = [
        "timestamp_utc",
        "phase",
        "phase_detail",
        "pid",
        "cpu_total_pct",
        "cpu_proc_pct",
        "cpu_temp_c",
        "gpu_timestamp",
        "gpu_util_pct",
        "gpu_mem_util_pct",
        "gpu_mem_used_mb",
        "gpu_mem_total_mb",
        "gpu_temp_c",
        "gpu_power_w",
        "gpu_pstate",
        "checkpoint_file",
        "checkpoint_status",
        "checkpoint_updated_at",
        "checkpoint_succeeded",
        "checkpoint_failed",
        "checkpoint_skipped_existing",
        "checkpoint_skipped_checkpoint",
    ]

    samples: list[dict[str, Any]] = []
    started = time.time()
    idle_since = time.time()

    with csv_path.open("w", newline="", encoding="utf-8") as csv_f, jsonl_path.open("w", encoding="utf-8") as jsonl_f:
        writer = csv.DictWriter(csv_f, fieldnames=fieldnames)
        writer.writeheader()

        while True:
            now = time.time()
            if args.duration_s > 0 and (now - started) >= args.duration_s:
                break

            proc, phase, phase_detail, ck_ref = _pick_target_process()
            active = phase != "idle"
            if active:
                idle_since = now
            elif args.duration_s == 0 and (now - idle_since) >= args.idle_timeout_s:
                break

            pid = None
            cpu_proc = None
            if proc is not None:
                pid = proc.pid
                if pid not in proc_cpu_cache:
                    proc_cpu_cache[pid] = proc
                    try:
                        proc.cpu_percent(interval=None)
                    except Exception:
                        pass
                try:
                    cpu_proc = round(proc.cpu_percent(interval=None), 2)
                except Exception:
                    cpu_proc = None

            gpu = _gpu_metrics()
            ck = _read_checkpoint_progress(ck_ref, repo)
            row = {
                "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                "phase": phase,
                "phase_detail": phase_detail,
                "pid": pid,
                "cpu_total_pct": round(psutil.cpu_percent(interval=None), 2),
                "cpu_proc_pct": cpu_proc,
                "cpu_temp_c": _cpu_temp_best_effort(),
                **gpu,
                **ck,
            }
            writer.writerow(row)
            jsonl_f.write(json.dumps(row, ensure_ascii=False) + "\n")
            csv_f.flush()
            jsonl_f.flush()
            samples.append(row)
            time.sleep(max(0.5, float(args.interval_s)))

    phases = sorted({s.get("phase", "unknown") for s in samples})
    summary = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "repo": str(repo),
        "interval_s": args.interval_s,
        "duration_s": round(time.time() - started, 2),
        "sample_count": len(samples),
        "jsonl": str(jsonl_path),
        "csv": str(csv_path),
        "phase_summaries": [_phase_summary(samples, p) for p in phases],
    }

    lines = [
        "# Phase Telemetry Report",
        "",
        f"- Generated (UTC): {summary['generated_at']}",
        f"- Interval: `{summary['interval_s']}s`",
        f"- Duration: `{summary['duration_s']}s`",
        f"- Samples: `{summary['sample_count']}`",
        f"- CSV: `{csv_path}`",
        f"- JSONL: `{jsonl_path}`",
        "",
        "| Phase | Samples | GPU avg % | GPU max % | GPU temp avg C | GPU temp max C | CPU total avg % | CPU total max % |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for ps in summary["phase_summaries"]:
        lines.append(
            "| {phase} | {samples} | {gavg} | {gmax} | {tavg} | {tmax} | {cavg} | {cmax} |".format(
                phase=ps.get("phase"),
                samples=ps.get("samples"),
                gavg=ps.get("gpu_avg_pct", "n/a"),
                gmax=ps.get("gpu_max_pct", "n/a"),
                tavg=ps.get("gpu_temp_avg_c", "n/a"),
                tmax=ps.get("gpu_temp_max_c", "n/a"),
                cavg=ps.get("cpu_total_avg_pct", "n/a"),
                cmax=ps.get("cpu_total_max_pct", "n/a"),
            )
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"CSV={csv_path}")
    print(f"JSONL={jsonl_path}")
    print(f"MD={md_path}")
    for ps in summary["phase_summaries"]:
        print(
            "PHASE {phase}: samples={samples} gpu_avg={gavg} gpu_max={gmax} temp_max={tmax} cpu_avg={cavg}".format(
                phase=ps.get("phase"),
                samples=ps.get("samples"),
                gavg=ps.get("gpu_avg_pct"),
                gmax=ps.get("gpu_max_pct"),
                tmax=ps.get("gpu_temp_max_c"),
                cavg=ps.get("cpu_total_avg_pct"),
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
