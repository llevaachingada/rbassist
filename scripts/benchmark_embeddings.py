from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from rich.table import Table

from rbassist.recommend import DIM, load_embedding_safe, load_section_embeddings
from rbassist.features import harmonic_compatibility_from_features
try:
    from rbassist.similarity_head import load_similarity_head
except Exception:
    load_similarity_head = None  # type: ignore
from rbassist.utils import camelot_relation, console, tempo_match

METRIC_KEYS = [
    "camelot_compat_rate",
    "bpm_compat_rate",
    "tag_overlap_mean",
    "intra_list_diversity",
    "transition_score_mean",
    "ann_distance_mean",
]


ROW_DESCRIPTIONS = {
    "A": "ANN only",
    "B": "ANN + tempo/key gates",
    "C": "ANN + tempo/key + baseline rerank",
    "D": "C + section scores",
    "E": "C + layer-mix primary",
    "F": "D + layer-mix primary",
    "G": "C + harmonic scoring",
    "H": "C + learned similarity",
}


def embedding_coverage(meta: dict[str, Any]) -> dict[str, int]:
    tracks = meta.get("tracks", {})
    primary = 0
    section_complete = 0
    layer_mix = 0
    case_buckets: dict[str, list[str]] = {}
    for path, info in tracks.items():
        case_buckets.setdefault(str(path).lower(), []).append(str(path))
        emb = info.get("embedding")
        has_primary = bool(emb and Path(str(emb)).exists())
        if has_primary:
            primary += 1
            if all(
                info.get(key) and Path(str(info.get(key))).exists()
                for key in ("embedding_intro", "embedding_core", "embedding_late")
            ):
                section_complete += 1
        layer_path = info.get("embedding_layer_mix")
        if layer_path and Path(str(layer_path)).exists():
            layer_mix += 1
    case_collision_keys = sum(1 for values in case_buckets.values() if len(values) > 1)
    case_collision_rows = sum(max(0, len(values) - 1) for values in case_buckets.values())
    return {
        "tracks_total": len(tracks),
        "primary_embedding_count": primary,
        "section_embedding_complete_count": section_complete,
        "section_embedding_missing_count": max(0, primary - section_complete),
        "layer_mix_embedding_count": layer_mix,
        "case_collision_key_count": case_collision_keys,
        "case_collision_extra_row_count": case_collision_rows,
    }


def _cosine(left: np.ndarray, right: np.ndarray) -> float:
    if left.size == 0 or right.size == 0:
        return 0.0
    denom = float(np.linalg.norm(left) * np.linalg.norm(right))
    if denom <= 0.0:
        return 0.0
    return float(np.dot(left, right) / (denom + 1e-9))


def _cosine_01(left: np.ndarray, right: np.ndarray) -> float:
    return float(np.clip(_cosine(left, right), 0.0, 1.0))


def _read_seed_file(path: Path) -> list[str]:
    seeds: list[str] = []
    if not path.exists():
        return seeds
    for line in path.read_text(encoding="utf-8").splitlines():
        clean = line.strip()
        if clean and not clean.startswith("#"):
            seeds.append(clean)
    return seeds


def _resolve_seed(seed: str, tracks: dict[str, dict[str, Any]]) -> str | None:
    needle = seed.lower()
    for path, info in tracks.items():
        label = f"{info.get('artist', '')} - {info.get('title', '')}".lower()
        if needle in path.lower() or needle in label:
            return path
    return None


def _load_seed_list(args: argparse.Namespace) -> list[str]:
    seeds = [str(seed).strip() for seed in (args.seeds or []) if str(seed).strip()]
    if args.seeds_file:
        seeds.extend(_read_seed_file(Path(args.seeds_file)))
    config_path = Path("config/benchmark_seeds.txt")
    if not seeds and config_path.exists():
        seeds.extend(_read_seed_file(config_path))
    return list(dict.fromkeys(seeds))


def _candidate_pool(
    tracks: dict[str, dict[str, Any]],
    seed_path: str,
    seed_vec: np.ndarray,
    *,
    embedding_key: str,
    limit: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path, info in tracks.items():
        if path == seed_path:
            continue
        vec = load_embedding_safe(str(info.get(embedding_key) or ""), seed_vec.shape[0])
        if vec is None:
            continue
        sim = _cosine(seed_vec, vec)
        rows.append({"path": path, "info": info, "vector": vec, "ann_distance": 1.0 - sim})
    rows.sort(key=lambda row: (float(row["ann_distance"]), str(row["path"]).lower()))
    return rows[:limit]


def _score_candidate(
    seed_info: dict[str, Any],
    row: dict[str, Any],
    *,
    seed_vec: np.ndarray | None = None,
    use_section_scores: bool,
    use_harmonic_scores: bool = False,
    learned_head: Any = None,
) -> float:
    info = row["info"]
    ann_score = 1.0 - float(row["ann_distance"])
    score = 0.50 * ann_score
    if tempo_match(seed_info.get("bpm"), info.get("bpm"), pct=6.0, allow_doubletime=True):
        score += 0.15
    ok_key, _ = camelot_relation(seed_info.get("key"), info.get("key"))
    if ok_key:
        score += 0.15
    seed_tags = {str(tag) for tag in (seed_info.get("mytags", []) or []) if str(tag).strip()}
    cand_tags = {str(tag) for tag in (info.get("mytags", []) or []) if str(tag).strip()}
    if seed_tags or cand_tags:
        score += 0.20 * (len(seed_tags & cand_tags) / max(1, len(seed_tags | cand_tags)))
    if use_section_scores:
        seed_late = load_section_embeddings(seed_info).get("late")
        cand_intro = load_section_embeddings(info).get("intro")
        if seed_late is not None and cand_intro is not None:
            score += 0.18 * _cosine_01(seed_late, cand_intro)
    if use_harmonic_scores:
        score += 0.12 * harmonic_compatibility_from_features(seed_info, info)
    if learned_head is not None and seed_vec is not None:
        score += 0.30 * learned_head.score(seed_vec, row["vector"])
    return float(score)


def _empty_row_metrics() -> dict[str, float | int | bool | None]:
    return {
        **{key: None for key in METRIC_KEYS},
        "section_scores_requested": False,
        "section_scores_enabled": False,
        "seed_section_late_count": 0,
        "selected_candidate_intro_count": 0,
        "transition_pairs_scored": 0,
    }


def _run_row_for_seed(
    tracks: dict[str, dict[str, Any]],
    seed_path: str,
    *,
    row_name: str,
    top: int,
    candidate_pool: int,
    learned_head: Any = None,
) -> tuple[list[dict[str, Any]], str | None]:
    use_layer_mix = row_name in {"E", "F"}
    use_section_scores = row_name in {"D", "F"}
    use_harmonic_scores = row_name == "G"
    use_learned_scores = row_name == "H"
    use_gates = row_name in {"B", "C", "D", "E", "F", "G", "H"}
    use_rerank = row_name in {"C", "D", "E", "F", "G", "H"}
    embedding_key = "embedding_layer_mix" if use_layer_mix else "embedding"

    seed_info = tracks.get(seed_path, {})
    seed_vec = load_embedding_safe(str(seed_info.get(embedding_key) or ""), DIM)
    if seed_vec is None:
        return [], f"missing {embedding_key}"
    candidates = _candidate_pool(
        tracks,
        seed_path,
        seed_vec,
        embedding_key=embedding_key,
        limit=max(candidate_pool, top),
    )
    filtered: list[dict[str, Any]] = []
    for candidate in candidates:
        info = candidate["info"]
        if use_gates:
            ok_key, _ = camelot_relation(seed_info.get("key"), info.get("key"))
            if not ok_key:
                continue
            if not tempo_match(seed_info.get("bpm"), info.get("bpm"), pct=6.0, allow_doubletime=True):
                continue
        if use_rerank:
            candidate = dict(candidate)
            candidate["score"] = _score_candidate(
                seed_info,
                candidate,
                seed_vec=seed_vec,
                use_section_scores=use_section_scores,
                use_harmonic_scores=use_harmonic_scores,
                learned_head=learned_head if use_learned_scores else None,
            )
        filtered.append(candidate)
    if use_rerank:
        filtered.sort(key=lambda item: (-float(item.get("score", 0.0)), str(item["path"]).lower()))
    else:
        filtered.sort(key=lambda item: (float(item["ann_distance"]), str(item["path"]).lower()))
    return filtered[:top], None


def _metrics_for_results(
    seed_info: dict[str, Any],
    results: list[dict[str, Any]],
    *,
    use_section_scores: bool,
) -> dict[str, float | int | bool | None]:
    metrics = _empty_row_metrics()
    metrics["section_scores_requested"] = bool(use_section_scores)
    if not results:
        return metrics
    key_ok = [camelot_relation(seed_info.get("key"), row["info"].get("key"))[0] for row in results]
    bpm_ok = [tempo_match(seed_info.get("bpm"), row["info"].get("bpm"), pct=6.0, allow_doubletime=True) for row in results]
    seed_tags = {str(tag) for tag in (seed_info.get("mytags", []) or []) if str(tag).strip()}
    tag_scores = []
    for row in results:
        tags = {str(tag) for tag in (row["info"].get("mytags", []) or []) if str(tag).strip()}
        tag_scores.append(len(seed_tags & tags) / max(1, len(seed_tags | tags)) if (seed_tags or tags) else 0.0)
    diversity_values = []
    for idx, left in enumerate(results):
        for right in results[idx + 1 :]:
            diversity_values.append(1.0 - _cosine(left["vector"], right["vector"]))
    seed_late = load_section_embeddings(seed_info).get("late")
    transition_scores = []
    if use_section_scores and seed_late is not None:
        metrics["seed_section_late_count"] = 1
        for row in results:
            cand_intro = load_section_embeddings(row["info"]).get("intro")
            if cand_intro is not None:
                metrics["selected_candidate_intro_count"] = int(metrics["selected_candidate_intro_count"]) + 1
                transition_scores.append(_cosine_01(seed_late, cand_intro))
    metrics["transition_pairs_scored"] = len(transition_scores)
    metrics["section_scores_enabled"] = bool(use_section_scores and transition_scores)
    metrics.update(
        {
            "camelot_compat_rate": float(np.mean(key_ok)),
            "bpm_compat_rate": float(np.mean(bpm_ok)),
            "tag_overlap_mean": float(np.mean(tag_scores)),
            "intra_list_diversity": float(np.mean(diversity_values)) if diversity_values else 0.0,
            "transition_score_mean": float(np.mean(transition_scores)) if transition_scores else None,
            "ann_distance_mean": float(np.mean([float(row["ann_distance"]) for row in results])),
        }
    )
    return metrics


def run_benchmark(
    meta: dict[str, Any],
    seeds: list[str],
    *,
    rows: list[str],
    top: int,
    candidate_pool: int,
    allow_section_rows: bool,
    allow_layer_mix_rows: bool,
    learned_similarity_model: str | None = None,
    learned_similarity_device: str = "cuda",
) -> dict[str, Any]:
    tracks = meta.get("tracks", {})
    resolved = [path for seed in seeds if (path := _resolve_seed(seed, tracks))]
    if not resolved:
        raise ValueError("No benchmark seeds matched tracks in metadata.")
    row_results: dict[str, Any] = {}
    learned_head = None
    if "H" in rows:
        if load_similarity_head is None:
            console.print("[yellow]Skipping learned similarity row H: similarity head support unavailable")
        else:
            learned_head = load_similarity_head(learned_similarity_model or "data/models/similarity_head.pt", device=learned_similarity_device)
    for row_name in rows:
        use_section_scores = row_name in {"D", "F"}
        if row_name in {"D", "F"} and not allow_section_rows:
            row_results[row_name] = {"skipped": True, "reason": "section rows require --section-embeds"}
            console.print(f"[yellow]Skipping row {row_name}: section rows require --section-embeds")
            continue
        if row_name in {"E", "F"} and not allow_layer_mix_rows:
            row_results[row_name] = {"skipped": True, "reason": "layer-mix rows require --layer-mix"}
            console.print(f"[yellow]Skipping row {row_name}: layer-mix rows require --layer-mix")
            continue
        if row_name == "H" and learned_head is None:
            row_results[row_name] = {"skipped": True, "reason": "learned similarity row requires --learned-similarity-model"}
            console.print(f"[yellow]Skipping row {row_name}: {row_results[row_name]['reason']}")
            continue
        per_seed_metrics = []
        skips: list[str] = []
        for seed_path in resolved:
            results, skip_reason = _run_row_for_seed(
                tracks,
                seed_path,
                row_name=row_name,
                top=top,
                candidate_pool=candidate_pool,
                learned_head=learned_head,
            )
            if skip_reason:
                skips.append(f"{seed_path}: {skip_reason}")
                continue
            per_seed_metrics.append(
                _metrics_for_results(
                    tracks.get(seed_path, {}),
                    results,
                    use_section_scores=use_section_scores,
                )
            )
        if not per_seed_metrics:
            row_results[row_name] = {"skipped": True, "reason": "; ".join(skips) or "no usable results"}
            console.print(f"[yellow]Skipping row {row_name}: {row_results[row_name]['reason']}")
            continue
        if use_section_scores:
            section_pairs_scored = sum(int(metrics.get("transition_pairs_scored") or 0) for metrics in per_seed_metrics)
            if section_pairs_scored <= 0:
                row_results[row_name] = {
                    "skipped": True,
                    "reason": "section rows require usable seed late + candidate intro sidecars",
                    "section_scores_requested": True,
                    "section_scores_enabled": False,
                    "seed_section_late_count": sum(int(metrics.get("seed_section_late_count") or 0) for metrics in per_seed_metrics),
                    "selected_candidate_intro_count": sum(
                        int(metrics.get("selected_candidate_intro_count") or 0) for metrics in per_seed_metrics
                    ),
                    "transition_pairs_scored": 0,
                }
                console.print(
                    f"[yellow]Skipping row {row_name}: {row_results[row_name]['reason']}"
                )
                continue
        averaged: dict[str, float | None] = {}
        for key in METRIC_KEYS:
            values = [metrics[key] for metrics in per_seed_metrics if metrics.get(key) is not None]
            averaged[key] = float(np.mean(values)) if values else None
        if use_section_scores:
            averaged.update(
                {
                    "section_scores_requested": True,
                    "section_scores_enabled": True,
                    "seed_section_late_count": sum(
                        int(metrics.get("seed_section_late_count") or 0) for metrics in per_seed_metrics
                    ),
                    "selected_candidate_intro_count": sum(
                        int(metrics.get("selected_candidate_intro_count") or 0) for metrics in per_seed_metrics
                    ),
                    "transition_pairs_scored": sum(
                        int(metrics.get("transition_pairs_scored") or 0) for metrics in per_seed_metrics
                    ),
                }
            )
        row_results[row_name] = averaged
    return {"seeds": resolved, "rows": row_results, "coverage": embedding_coverage(meta)}


def compute_deltas(current: dict[str, Any], prior: dict[str, Any]) -> dict[str, Any]:
    deltas: dict[str, Any] = {}
    prior_rows = prior.get("rows", {})
    for row_name, metrics in current.get("rows", {}).items():
        if not isinstance(metrics, dict) or metrics.get("skipped"):
            continue
        prior_metrics = prior_rows.get(row_name, {})
        row_delta: dict[str, float] = {}
        for key in METRIC_KEYS:
            current_value = metrics.get(key)
            prior_value = prior_metrics.get(key) if isinstance(prior_metrics, dict) else None
            if isinstance(current_value, (int, float)) and isinstance(prior_value, (int, float)):
                row_delta[key] = float(current_value) - float(prior_value)
        if row_delta:
            deltas[row_name] = row_delta
    return deltas


def _print_table(payload: dict[str, Any]) -> None:
    table = Table(title="Embedding Benchmark")
    table.add_column("Row")
    table.add_column("Description")
    for key in METRIC_KEYS:
        table.add_column(key, justify="right")
    for row_name, metrics in payload.get("rows", {}).items():
        if isinstance(metrics, dict) and metrics.get("skipped"):
            table.add_row(row_name, ROW_DESCRIPTIONS.get(row_name, ""), str(metrics.get("reason", "skipped")), *[""] * (len(METRIC_KEYS) - 1))
            continue
        table.add_row(
            row_name,
            ROW_DESCRIPTIONS.get(row_name, ""),
            *[
                "-" if metrics.get(key) is None else f"{float(metrics[key]):.3f}"
                for key in METRIC_KEYS
            ],
        )
    console.print(table)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Benchmark rbassist embedding recommendation rows.")
    parser.add_argument("--meta", default="data/meta.json", help="Path to meta.json.")
    parser.add_argument("--seeds", nargs="*", default=[], help="Seed track path or Artist - Title substrings.")
    parser.add_argument("--seeds-file", default=None, help="Newline-delimited seed file.")
    parser.add_argument("--top", type=int, default=25, help="Top results per seed.")
    parser.add_argument("--candidate-pool", type=int, default=250, help="Candidate pool per seed.")
    parser.add_argument("--out", default=None, help="Output JSON path.")
    parser.add_argument("--compare", default=None, help="Prior benchmark JSON to compare against.")
    parser.add_argument("--rows", default="A,B,C,D,E,F", help="Comma-separated row names.")
    parser.add_argument("--section-embeds", action="store_true", help="Enable rows that use section embeddings.")
    parser.add_argument("--layer-mix", action="store_true", help="Enable rows that use layer-mix embeddings.")
    parser.add_argument("--learned-similarity-model", default=None, help="Enable row H with a trained similarity head.")
    parser.add_argument("--learned-similarity-device", default="cuda", help="Device for row H; CUDA is preferred by default.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    seeds = _load_seed_list(args)
    if not seeds:
        parser.error("Provide --seeds, --seeds-file, or config/benchmark_seeds.txt. Seeds are never auto-selected.")
    meta = json.loads(Path(args.meta).read_text(encoding="utf-8"))
    rows = [row.strip().upper() for row in str(args.rows).split(",") if row.strip()]
    unknown = [row for row in rows if row not in ROW_DESCRIPTIONS]
    if unknown:
        parser.error(f"Unsupported rows: {', '.join(unknown)}")
    result = run_benchmark(
        meta,
        seeds,
        rows=rows,
        top=max(1, int(args.top)),
        candidate_pool=max(1, int(args.candidate_pool)),
        allow_section_rows=bool(args.section_embeds),
        allow_layer_mix_rows=bool(args.layer_mix),
        learned_similarity_model=args.learned_similarity_model,
        learned_similarity_device=args.learned_similarity_device,
    )
    payload = {
        "run_id": datetime.now(timezone.utc).isoformat(),
        "seeds": result["seeds"],
        "coverage": result["coverage"],
        "rows": result["rows"],
        "deltas_vs_prior": None,
    }
    if args.compare:
        prior = json.loads(Path(args.compare).read_text(encoding="utf-8"))
        payload["deltas_vs_prior"] = compute_deltas(payload, prior)
    _print_table(payload)
    out_path = Path(args.out) if args.out else Path("reports") / f"benchmark_{datetime.now().strftime('%Y%m%d')}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    console.print(f"[green]Wrote benchmark JSON -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
