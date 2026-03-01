#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
import traceback
from typing import Any

from rbassist.health import audit_meta_health, list_embedding_gaps
from rbassist.rekordbox_audit import audit_rekordbox_library
from rbassist.rekordbox_review import build_review_queues, write_review_queues
from rbassist.utils import read_paths_file, walk_audio


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a background rbassist maintenance pass for one canonical music root."
    )
    parser.add_argument("--repo", default=".", help="Repo root.")
    parser.add_argument("--music-root", required=True, help="Canonical music root.")
    parser.add_argument(
        "--output-dir",
        default="data/runlogs",
        help="Base output directory for maintenance logs and reports.",
    )
    parser.add_argument(
        "--run-prefix",
        default="music_root_maintenance",
        help="Prefix used for this maintenance run's folder.",
    )
    parser.add_argument("--chunk-size", type=int, default=2000, help="Chunk size for pending embed lists.")
    parser.add_argument("--catalog-workers", type=int, default=8, help="Workers for Rekordbox/media cataloging.")
    parser.add_argument("--top-candidates", type=int, default=5, help="Top relink candidates to keep.")
    parser.add_argument("--duration-tolerance-s", type=float, default=2.0, help="Tolerance for duration-based matching.")
    parser.add_argument("--include-embed", action="store_true", help="Run resumable embedding on pending files under the music root.")
    parser.add_argument("--include-analyze", action="store_true", help="Run incremental BPM/key analysis under the music root.")
    parser.add_argument("--include-index", action="store_true", help="Rebuild the recommendation index after ingest phases.")
    parser.add_argument("--device", default="cuda", help="Embed device: cuda|rocm|mps|cpu.")
    parser.add_argument("--embed-workers", type=int, default=8, help="Embed audio decode workers.")
    parser.add_argument("--batch-size", type=int, default=4, help="Embed batch size.")
    parser.add_argument("--resume", action="store_true", help="Resume embedding from checkpoint.")
    parser.add_argument("--checkpoint-every", type=int, default=100, help="Embed checkpoint cadence.")
    parser.add_argument(
        "--checkpoint-file",
        default="",
        help="Optional checkpoint file path for embed phase (repo-relative by default).",
    )
    parser.add_argument("--analyze-workers", type=int, default=12, help="Workers for BPM/key analysis.")
    return parser.parse_args()


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_json(path: pathlib.Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _status_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Music Root Background Maintenance",
        "",
        f"- Generated (UTC): {payload.get('generated_at', '')}",
        f"- Repo: `{payload.get('repo', '')}`",
        f"- Music root: `{payload.get('music_root', '')}`",
        f"- Current phase: `{payload.get('current_phase', '')}`",
        f"- State: `{payload.get('state', '')}`",
        "",
        "## Phases",
        "",
    ]
    for phase in payload.get("phases", []):
        lines.append(
            f"- `{phase.get('name', '')}`: `{phase.get('status', '')}`"
            + (f" | {phase.get('note', '')}" if phase.get("note") else "")
        )
    lines.append("")
    summary = payload.get("summary", {})
    if summary:
        lines.append("## Summary")
        lines.append("")
        for key, value in summary.items():
            lines.append(f"- {key}: `{value}`")
        lines.append("")
    return "\n".join(lines) + "\n"


class MaintenanceRun:
    def __init__(self, *, repo: pathlib.Path, music_root: pathlib.Path, run_dir: pathlib.Path):
        self.repo = repo
        self.music_root = music_root
        self.run_dir = run_dir
        self.status_path = run_dir / "status.json"
        self.status_md_path = run_dir / "status.md"
        self.phase_log = run_dir / "phase_log.jsonl"
        self.payload: dict[str, Any] = {
            "generated_at": _utc_now(),
            "repo": str(repo),
            "music_root": str(music_root),
            "current_phase": "init",
            "state": "running",
            "phases": [],
            "summary": {},
        }
        self._flush()

    def _flush(self) -> None:
        _write_json(self.status_path, self.payload)
        self.status_md_path.write_text(_status_markdown(self.payload), encoding="utf-8")

    def _log_phase_event(self, payload: dict[str, Any]) -> None:
        self.phase_log.parent.mkdir(parents=True, exist_ok=True)
        with self.phase_log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def phase_start(self, name: str, note: str = "") -> None:
        self.payload["current_phase"] = name
        phases = self.payload.setdefault("phases", [])
        phases.append({"name": name, "status": "running", "started_at": _utc_now(), "note": note})
        self._log_phase_event({"timestamp": _utc_now(), "phase": name, "event": "start", "note": note})
        self._flush()

    def phase_done(self, name: str, note: str = "") -> None:
        for phase in reversed(self.payload.get("phases", [])):
            if phase.get("name") == name and phase.get("status") == "running":
                phase["status"] = "completed"
                phase["completed_at"] = _utc_now()
                if note:
                    phase["note"] = note
                break
        self._log_phase_event({"timestamp": _utc_now(), "phase": name, "event": "completed", "note": note})
        self._flush()

    def phase_failed(self, name: str, error: str) -> None:
        for phase in reversed(self.payload.get("phases", [])):
            if phase.get("name") == name and phase.get("status") == "running":
                phase["status"] = "failed"
                phase["completed_at"] = _utc_now()
                phase["note"] = error
                break
        self.payload["state"] = "failed"
        self.payload["current_phase"] = name
        self._log_phase_event({"timestamp": _utc_now(), "phase": name, "event": "failed", "error": error})
        self._flush()

    def set_summary(self, **kwargs: Any) -> None:
        self.payload.setdefault("summary", {}).update(kwargs)
        self._flush()

    def finish(self) -> None:
        self.payload["state"] = "completed"
        self.payload["current_phase"] = "done"
        self.payload["generated_at"] = _utc_now()
        self._flush()


def _checkpoint_path(repo: pathlib.Path, run_dir: pathlib.Path, path_ref: str) -> pathlib.Path:
    if path_ref:
        p = pathlib.Path(path_ref)
        return p if p.is_absolute() else (repo / p).resolve()
    return (run_dir / "embed_checkpoint.json").resolve()


def _load_embed_builder():
    from rbassist.embed import build_embeddings

    return build_embeddings


def _load_analyzer():
    from rbassist.analyze import analyze_bpm_key

    return analyze_bpm_key


def _load_index_builder():
    from rbassist.recommend import build_index

    return build_index


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    args = parse_args()
    repo = pathlib.Path(args.repo).resolve()
    music_root = pathlib.Path(args.music_root).resolve()
    if not music_root.exists():
        raise SystemExit(f"Music root not found: {music_root}")

    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base_out = pathlib.Path(args.output_dir)
    if not base_out.is_absolute():
        base_out = (repo / base_out).resolve()
    run_dir = base_out / f"{args.run_prefix}_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)

    run = MaintenanceRun(repo=repo, music_root=music_root, run_dir=run_dir)

    try:
        run.phase_start("health_audit", "Auditing current rbassist metadata health.")
        baseline = audit_meta_health(repo=repo)
        _write_json(run_dir / "health_audit_before.json", baseline)
        run.set_summary(
            tracks_total=baseline.get("counts", {}).get("tracks_total", 0),
            bare_path_total=baseline.get("counts", {}).get("bare_path_total", 0),
            stale_track_path_total=baseline.get("counts", {}).get("stale_track_path_total", 0),
            embedding_gap_total=baseline.get("counts", {}).get("embedding_gap_total", 0),
        )
        run.phase_done("health_audit", f"Wrote {run_dir / 'health_audit_before.json'}")

        run.phase_start("embedding_gap_scan", "Scanning only the canonical music root for real embedding gaps.")
        gap_prefix = run_dir / "pending_embedding_paths"
        gap_report = list_embedding_gaps(
            repo=repo,
            roots=[str(music_root)],
            out_prefix=gap_prefix,
            chunk_size=max(1, int(args.chunk_size)),
        )
        _write_json(run_dir / "embedding_gap_report.json", gap_report)
        run.set_summary(
            pending_embedding_total=gap_report.get("counts", {}).get("pending_embedding_total", 0),
            scanned_audio_files=gap_report.get("counts", {}).get("audio_files_scanned", 0),
        )
        run.phase_done("embedding_gap_scan", f"Pending embeddings: {gap_report.get('counts', {}).get('pending_embedding_total', 0)}")

        run.phase_start("rekordbox_audit", "Auditing live Rekordbox master.db against the canonical music root.")
        rb_report = audit_rekordbox_library(
            music_root=music_root,
            duration_tolerance_s=max(0.1, float(args.duration_tolerance_s)),
            top_candidates=max(1, int(args.top_candidates)),
            catalog_workers=max(1, int(args.catalog_workers)),
        )
        _write_json(run_dir / "rekordbox_audit.json", rb_report)
        queues = build_review_queues(rb_report)
        queue_outputs = write_review_queues(queues, out_dir=run_dir / "rekordbox_review_queues", prefix="rekordbox_music_root")
        run.set_summary(
            rekordbox_tracks_total=rb_report.get("rekordbox_tracks_total", 0),
            inside_root_existing_total=rb_report.get("rekordbox_audit", {}).get("counts", {}).get("inside_root_existing_total", 0),
            high_confidence_relinks_total=queues.get("counts", {}).get("high_confidence_relinks_total", 0),
            ambiguous_relinks_total=queues.get("counts", {}).get("ambiguous_relinks_total", 0),
            same_name_different_type_groups_total=queues.get("counts", {}).get("same_name_different_type_groups_total", 0),
        )
        _write_json(run_dir / "rekordbox_review_queue_outputs.json", queue_outputs)
        run.phase_done("rekordbox_audit", f"High-confidence relinks: {queues.get('counts', {}).get('high_confidence_relinks_total', 0)}")

        pending_paths_file = pathlib.Path(gap_report.get("output_paths_file", "")) if gap_report.get("output_paths_file") else None

        if args.include_embed:
            run.phase_start("embed", "Running resumable embedding on pending files inside the canonical music root.")
            build_embeddings = _load_embed_builder()
            pending_paths = read_paths_file(pending_paths_file) if pending_paths_file and pending_paths_file.exists() else []
            if not pending_paths:
                run.phase_done("embed", "No pending embeddings for this music root.")
            else:
                checkpoint_path = _checkpoint_path(repo, run_dir, args.checkpoint_file)
                build_embeddings(
                    pending_paths,
                    device=args.device,
                    num_workers=max(0, int(args.embed_workers)),
                    batch_size=max(1, int(args.batch_size)),
                    resume=bool(args.resume),
                    checkpoint_file=str(checkpoint_path),
                    checkpoint_every=max(1, int(args.checkpoint_every)),
                )
                run.phase_done("embed", f"Embedded pending paths using checkpoint {checkpoint_path}")

        if args.include_analyze:
            run.phase_start("analyze", "Running incremental BPM/key analysis under the canonical music root.")
            music_files = walk_audio([str(music_root)])
            analyze_bpm_key = _load_analyzer()
            analyze_bpm_key(
                music_files,
                duration_s=90,
                only_new=True,
                force=False,
                workers=max(0, int(args.analyze_workers)) or None,
            )
            run.phase_done("analyze", f"Analyzed {len(music_files)} files incrementally.")

        if args.include_index:
            run.phase_start("index", "Rebuilding the recommendation index.")
            build_index = _load_index_builder()
            build_index(incremental=True)
            run.phase_done("index", "Incremental index rebuild completed.")

        run.phase_start("final_health_audit", "Refreshing the final health summary after maintenance.")
        final_report = audit_meta_health(repo=repo)
        _write_json(run_dir / "health_audit_after.json", final_report)
        run.set_summary(
            final_tracks_total=final_report.get("counts", {}).get("tracks_total", 0),
            final_embedding_gap_total=final_report.get("counts", {}).get("embedding_gap_total", 0),
            final_stale_track_path_total=final_report.get("counts", {}).get("stale_track_path_total", 0),
        )
        run.phase_done("final_health_audit", f"Wrote {run_dir / 'health_audit_after.json'}")

    except Exception as exc:
        error = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        run.phase_failed(run.payload.get("current_phase", "unknown"), error)
        raise
    else:
        run.finish()
        print(json.dumps({"run_dir": str(run_dir), "status": str(run.status_path)}, indent=2))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
