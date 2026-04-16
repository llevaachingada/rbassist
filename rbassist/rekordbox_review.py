from __future__ import annotations

import csv
import json
import pathlib
from typing import Any


def build_review_queues(report: dict[str, Any]) -> dict[str, Any]:
    relink_suggestions = report.get("relink_suggestion_report", {}).get("suggestions", []) or []
    duplicate_groups = report.get("duplicate_dry_run_report", {}).get("groups", []) or []

    high_confidence = [
        {
            "id": item.get("id", ""),
            "source_path": item.get("source_path", ""),
            "title": item.get("title", ""),
            "artist": item.get("artist", ""),
            "row_length": item.get("row_length", 0.0),
            "target_path": (item.get("best_candidate") or {}).get("path", ""),
            "target_duration": (item.get("best_candidate") or {}).get("duration"),
            "target_size": (item.get("best_candidate") or {}).get("size"),
            "score": (item.get("best_candidate") or {}).get("score"),
            "reasons": (item.get("best_candidate") or {}).get("reasons", []),
        }
        for item in relink_suggestions
        if item.get("classification") == "high_confidence_unique" and item.get("best_candidate")
    ]

    ambiguous = [
        {
            "id": item.get("id", ""),
            "source_path": item.get("source_path", ""),
            "title": item.get("title", ""),
            "artist": item.get("artist", ""),
            "row_length": item.get("row_length", 0.0),
            "candidates": item.get("candidates", []),
        }
        for item in relink_suggestions
        if item.get("classification") == "ambiguous"
    ]

    same_name_diff_type = [
        {
            "stem_key": item.get("stem_key", ""),
            "keep_path": (item.get("keep") or {}).get("path", ""),
            "keep_extension": (item.get("keep") or {}).get("extension", ""),
            "extensions": item.get("extensions", []),
            "duration_span": item.get("duration_span", []),
            "paths": [candidate.get("path", "") for candidate in item.get("candidates", [])],
        }
        for item in duplicate_groups
        if len(item.get("extensions", [])) > 1
    ]

    return {
        "counts": {
            "high_confidence_relinks_total": len(high_confidence),
            "ambiguous_relinks_total": len(ambiguous),
            "same_name_different_type_groups_total": len(same_name_diff_type),
        },
        "high_confidence_relinks": high_confidence,
        "ambiguous_relinks": ambiguous,
        "same_name_different_type_duplicates": same_name_diff_type,
    }


def _write_json(path: pathlib.Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_csv(path: pathlib.Path, rows: list[dict[str, Any]], *, fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            flat = dict(row)
            for key, value in list(flat.items()):
                if isinstance(value, (list, dict)):
                    flat[key] = json.dumps(value, ensure_ascii=False)
            writer.writerow({name: flat.get(name, "") for name in fieldnames})


def _write_markdown(path: pathlib.Path, *, title: str, rows: list[dict[str, Any]], bullets: list[tuple[str, str]]) -> None:
    lines = [f"# {title}", ""]
    if not rows:
        lines.append("- No rows.")
    else:
        for row in rows:
            lines.append("- " + " | ".join(f"{label}: `{row.get(key, '')}`" for label, key in bullets))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_review_queues(queues: dict[str, Any], *, out_dir: str | pathlib.Path, prefix: str) -> dict[str, str]:
    out_path = pathlib.Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    prefix = prefix.strip() or "rekordbox_review"

    outputs: dict[str, str] = {}

    high_conf = queues.get("high_confidence_relinks", [])
    high_conf_json = out_path / f"{prefix}_high_confidence_relinks.json"
    high_conf_csv = out_path / f"{prefix}_high_confidence_relinks.csv"
    high_conf_md = out_path / f"{prefix}_high_confidence_relinks.md"
    _write_json(high_conf_json, {"counts": {"rows": len(high_conf)}, "rows": high_conf})
    _write_csv(
        high_conf_csv,
        high_conf,
        fieldnames=["id", "source_path", "target_path", "score", "row_length", "target_duration", "target_size", "title", "artist", "reasons"],
    )
    _write_markdown(
        high_conf_md,
        title="High Confidence Rekordbox Relinks",
        rows=high_conf,
        bullets=[("Score", "score"), ("Source", "source_path"), ("Target", "target_path"), ("Title", "title")],
    )
    outputs["high_confidence_relinks_json"] = str(high_conf_json)
    outputs["high_confidence_relinks_csv"] = str(high_conf_csv)
    outputs["high_confidence_relinks_md"] = str(high_conf_md)

    diff_type = queues.get("same_name_different_type_duplicates", [])
    diff_json = out_path / f"{prefix}_same_name_different_type_duplicates.json"
    diff_csv = out_path / f"{prefix}_same_name_different_type_duplicates.csv"
    diff_md = out_path / f"{prefix}_same_name_different_type_duplicates.md"
    _write_json(diff_json, {"counts": {"rows": len(diff_type)}, "rows": diff_type})
    _write_csv(
        diff_csv,
        diff_type,
        fieldnames=["stem_key", "keep_path", "keep_extension", "extensions", "duration_span", "paths"],
    )
    _write_markdown(
        diff_md,
        title="Same Name Different Type Duplicate Groups",
        rows=diff_type,
        bullets=[("Stem", "stem_key"), ("Keep", "keep_path"), ("Types", "extensions")],
    )
    outputs["same_name_different_type_duplicates_json"] = str(diff_json)
    outputs["same_name_different_type_duplicates_csv"] = str(diff_csv)
    outputs["same_name_different_type_duplicates_md"] = str(diff_md)

    ambiguous = queues.get("ambiguous_relinks", [])
    ambiguous_json = out_path / f"{prefix}_ambiguous_relinks.json"
    _write_json(ambiguous_json, {"counts": {"rows": len(ambiguous)}, "rows": ambiguous})
    outputs["ambiguous_relinks_json"] = str(ambiguous_json)

    summary = out_path / f"{prefix}_summary.json"
    _write_json(summary, {"counts": queues.get("counts", {}), "outputs": outputs})
    outputs["summary_json"] = str(summary)
    return outputs
