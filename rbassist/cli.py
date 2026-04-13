from __future__ import annotations
import json
import pathlib
import librosa
import csv
from datetime import datetime
from typing import Any, List, Optional
import typer
from .analyze import analyze_bpm_key
from .utils import load_meta, save_meta, console, walk_audio, pick_device, read_paths_file
from .sampling_profile import load_sampling_params
from .beatgrid import analyze_paths as analyze_beatgrid_paths, BeatgridConfig


# ------------------------------
# Typer CLI
# ------------------------------

app = typer.Typer(no_args_is_help=True, add_completion=False, help="RBassist command line tools")


def _read_paths_file(paths_file: pathlib.Path) -> list[str]:
    """Backward-compatible wrapper around shared paths-file parsing."""
    return read_paths_file(paths_file)


def _normalize_playlist_expansion_choice(value: str, allowed: set[str], *, label: str) -> str:
    clean = str(value or "").lower().strip()
    if clean not in allowed:
        raise ValueError(f"Unsupported {label}: {value}")
    return clean


def _build_playlist_expansion_kwargs(
    *,
    mode: str,
    strategy: str,
    candidate_pool: Optional[int],
    diversity: Optional[float],
    tempo_pct: Optional[float],
    allow_doubletime: Optional[bool],
    key_mode: Optional[str],
    key_filter: bool,
    w_ann_centroid: Optional[float],
    w_ann_seed_coverage: Optional[float],
    w_group_match: Optional[float],
    w_bpm: Optional[float],
    w_key: Optional[float],
    w_tags: Optional[float],
    w_transition: Optional[float],
    require_tags: Optional[List[str]],
    section_scores: bool,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "mode": _normalize_playlist_expansion_choice(
            mode,
            {"tight", "balanced", "adventurous"},
            label="playlist expansion mode",
        ),
        "strategy": _normalize_playlist_expansion_choice(
            strategy,
            {"blend", "centroid", "coverage"},
            label="playlist expansion strategy",
        ),
    }

    if candidate_pool is not None:
        kwargs["candidate_pool"] = max(1, int(candidate_pool))
    if diversity is not None:
        kwargs["diversity"] = max(0.0, min(1.0, float(diversity)))

    filters: dict[str, Any] = {}
    if tempo_pct is not None:
        filters["tempo_pct"] = float(tempo_pct)
    if allow_doubletime is not None:
        filters["allow_doubletime"] = bool(allow_doubletime)
    if key_filter:
        filters["key_mode"] = "filter"
    elif key_mode is not None:
        filters["key_mode"] = _normalize_playlist_expansion_choice(
            key_mode,
            {"off", "soft", "filter"},
            label="playlist expansion key mode",
        )
    if require_tags:
        filters["require_tags"] = [str(tag).strip() for tag in require_tags if str(tag).strip()]
    if filters:
        kwargs["filters"] = filters

    weights: dict[str, Any] = {}
    if w_ann_centroid is not None:
        weights["ann_centroid"] = float(w_ann_centroid)
    if w_ann_seed_coverage is not None:
        weights["ann_seed_coverage"] = float(w_ann_seed_coverage)
    if w_group_match is not None:
        weights["group_match"] = float(w_group_match)
    if w_bpm is not None:
        weights["bpm_match"] = float(w_bpm)
    if w_key is not None:
        weights["key_match"] = float(w_key)
    if w_tags is not None:
        weights["tag_match"] = float(w_tags)
    if w_transition is not None:
        weights["transition_outro_to_intro"] = float(w_transition)
    if weights:
        kwargs["weights"] = weights
    if section_scores:
        kwargs["controls"] = {"use_section_scores": True}

    return kwargs


@app.command("analyze")
def cmd_analyze(
    paths: List[str] = typer.Argument(..., help="One or more files or folders to analyze"),
    duration_s: int = typer.Option(90, help="Max seconds per track to analyze (0 = full)"),
    only_new: bool = typer.Option(True, help="Skip files already analyzed with same signature"),
    force: bool = typer.Option(False, help="Force re-analyze even if cached"),
    cue_profile: str = typer.Option(
        "",
        "--cue-profile",
        help="Optional cue template profile name from config/cue_templates.yml.",
    ),
    overwrite_cues: bool = typer.Option(
        False,
        "--overwrite-cues",
        help="When auto-cues are enabled, replace existing cue data instead of preserving it.",
    ),
    workers: int = typer.Option(12, help="Process workers for BPM/Key (0 = serial)"),
):
    files = walk_audio(paths)
    if not files:
        console.print("[yellow]No audio files found in given paths.")
        raise typer.Exit(code=1)
    analyze_bpm_key(
        files,
        duration_s=duration_s,
        only_new=only_new,
        force=force,
        cue_profile=(cue_profile or None),
        overwrite_cues=overwrite_cues,
        workers=(workers if workers > 0 else None),
    )


@app.command("beatgrid")
def cmd_beatgrid(
    paths: List[str] = typer.Argument(..., help="Files or folders to beatgrid"),
    mode: str = typer.Option("fixed", help="fixed | dynamic"),
    drift_pct: float = typer.Option(1.5, help="Tempo drift percent to trigger new segment (dynamic mode)"),
    bars_window: int = typer.Option(16, help="Bars (4/4) per window for drift detection"),
    duration_s: int = typer.Option(0, help="Max seconds per track (0 = full)"),
    backend: str = typer.Option("beatnet", help="beatnet | auto | librosa"),
    model: int = typer.Option(3, help="BeatNet model id (1..3)"),
    device: str = typer.Option("auto", help="cuda|cpu|auto (for BeatNet backend)"),
    overwrite: bool = typer.Option(True, help="Recompute beatgrid even if tempos already exist"),
):
    cfg = BeatgridConfig(
        mode=mode.lower().strip(),
        drift_pct=max(0.1, float(drift_pct)),
        bars_window=max(4, int(bars_window)),
        duration_s=max(0, int(duration_s)),
        backend=backend.lower().strip(),
        model_id=int(model),
        device=None if device == "auto" else device,
    )
    files = walk_audio(paths)
    if not files:
        console.print("[yellow]No audio files found in given paths.")
        raise typer.Exit(code=1)
    analyze_beatgrid_paths(files, cfg=cfg, overwrite=overwrite)


def main() -> None:
    app()


@app.command("embed")
def cmd_embed(
    paths: Optional[List[str]] = typer.Argument(None, help="Files or folders to embed"),
    duration_s: int = typer.Option(120, help="Seconds per track (0=full)"),
    model: str = typer.Option("m-a-p/MERT-v1-330M", help="HF model name for MERT"),
    device: str = typer.Option(
        None,
        help="Compute device: 'cuda' (NVIDIA/ROCm), 'rocm', 'mps', or 'cpu' (auto if omitted)",
    ),
    num_workers: int = typer.Option(8, help="Parallel audio loaders (0=serial; 4-8 typical)"),
    batch_size: Optional[int] = typer.Option(
        None, help="Model batch size (auto: ~4 on GPU, 1 on CPU)"
    ),
    timbre: bool = typer.Option(False, help="Also write a timbre-only embedding using OpenL3"),
    timbre_size: int = typer.Option(512, help="OpenL3 embedding size (128/256/512)"),
    section_embed: bool = typer.Option(
        False,
        "--section-embed/--no-section-embed",
        help="Also save intro/core/late MERT section embeddings for opt-in transition scoring.",
    ),
    layer_mix: bool = typer.Option(
        False,
        "--layer-mix/--no-layer-mix",
        help="Also save an opt-in depth-mixed MERT embedding sidecar.",
    ),
    layer_mix_weights_path: Optional[pathlib.Path] = typer.Option(
        None,
        "--layer-mix-weights",
        file_okay=True,
        dir_okay=False,
        exists=True,
        readable=True,
        help="Optional .npz file with learned layer-mix weights.",
    ),
    paths_file: Optional[pathlib.Path] = typer.Option(
        None,
        "--paths-file",
        file_okay=True,
        dir_okay=False,
        exists=True,
        readable=True,
        help="Optional text file with one file/folder path per line.",
    ),
    resume: bool = typer.Option(
        False,
        "--resume",
        help="Resume from checkpoint and skip already completed tracks.",
    ),
    checkpoint_file: Optional[pathlib.Path] = typer.Option(
        None,
        "--checkpoint-file",
        help="Checkpoint JSON path (default: data/embed_checkpoint.json).",
    ),
    checkpoint_every: int = typer.Option(
        100,
        "--checkpoint-every",
        min=1,
        help="Persist checkpoint state every N processed tracks.",
    ),
):
    # Enforce canonical embedding defaults to keep library consistent.
    if duration_s != 120:
        console.print("[red]Non-default --duration-s is not allowed; embeddings must use the canonical windowing setup (120s cap).[/red]")
        raise typer.Exit(1)
    if timbre_size != 512:
        console.print("[red]Non-default --timbre-size is not allowed; embeddings must use 512-d OpenL3 timbre vectors.[/red]")
        raise typer.Exit(1)
    try:
        from .embed import build_embeddings, DEFAULT_MODEL
    except Exception as e:
        console.print(f"[red]Embed deps missing: install .[ml] and torch. Error: {e}")
        raise typer.Exit(1)
    input_paths: list[str] = []
    if paths:
        input_paths.extend(paths)
    if paths_file is not None:
        try:
            from_file = _read_paths_file(paths_file)
        except Exception as e:
            console.print(f"[red]Failed to read --paths-file {paths_file}: {e}")
            raise typer.Exit(1)
        if not from_file:
            console.print(f"[yellow]No usable entries found in {paths_file}.")
        else:
            console.print(f"[cyan]Loaded {len(from_file)} path entries from {paths_file}")
            input_paths.extend(from_file)
    if not input_paths:
        console.print("[red]Provide at least one path argument or --paths-file.")
        raise typer.Exit(1)
    files = walk_audio(input_paths)
    if not files:
        console.print("[yellow]No audio files found.")
        raise typer.Exit(1)
    # Keep deterministic order and remove duplicates when both positional paths
    # and --paths-file overlap.
    files = list(dict.fromkeys(files))
    build_embeddings(
        files,
        model_name=model or DEFAULT_MODEL,
        duration_s=duration_s,
        device=(device or None),
        num_workers=num_workers,
        batch_size=batch_size,
        timbre=timbre,
        timbre_size=timbre_size,
        resume=resume,
        checkpoint_file=(str(checkpoint_file) if checkpoint_file else None),
        checkpoint_every=checkpoint_every,
        section_embed=section_embed,
        layer_mix=layer_mix,
        layer_mix_weights_path=(str(layer_mix_weights_path) if layer_mix_weights_path else None),
    )


@app.command("reanalyze")
def cmd_reanalyze(
    input: pathlib.Path = typer.Argument(..., exists=True, file_okay=False, dir_okay=True, readable=True, help="Root music folder"),
    profile: Optional[str] = typer.Option(None, help="Sampling profile name from config/sampling.yml (defaults to sampling_profile value)"),
    device: str = typer.Option("auto", help="Compute device: auto|cuda|rocm|mps|cpu"),
    workers: int = typer.Option(8, help="Parallel audio loaders (0=serial)"),
    rebuild_index: bool = typer.Option(True, help="Rebuild HNSW index after embeddings"),
    analyze_bpm: bool = typer.Option(True, help="Run BPM/Key analysis after embeddings"),
    overwrite: bool = typer.Option(False, help="Overwrite existing embeddings/BPM/Key info"),
    analyze_workers: int = typer.Option(12, help="Process workers for BPM/Key (0 = serial)"),
    timbre: bool = typer.Option(False, help="Also write timbre embeddings (OpenL3) and blend them into main embeddings"),
    timbre_size: int = typer.Option(512, help="OpenL3 embedding size (128/256/512)"),
):
    from .embed import build_embeddings

    params = load_sampling_params(profile or "")
    dev = pick_device(None if device == "auto" else device)
    files = walk_audio([str(input)])
    if not files:
        console.print("[yellow]No audio files found under input path.")
        raise typer.Exit(1)
    build_embeddings(
        files,
        duration_s=0,
        device=dev,
        num_workers=workers,
        sampling=params,
        overwrite=overwrite,
        timbre=timbre,
        timbre_size=timbre_size,
    )
    if analyze_bpm:
        analyze_bpm_key(
            files,
            duration_s=90,
            only_new=not overwrite,
            force=overwrite,
            workers=(analyze_workers if analyze_workers > 0 else None),
        )
    if rebuild_index:
        try:
            from .recommend import build_index
            build_index()
        except Exception as e:
            console.print(f"[yellow]Index rebuild skipped: {e}")


@app.command("index")
def cmd_index(
    incremental: bool = typer.Option(False, "--incremental", help="Incremental index build (add new embeddings)")
):
    try:
        from .recommend import build_index
    except Exception as e:
        console.print(f"[red]Index deps missing (hnswlib). Error: {e}")
        raise typer.Exit(1)
    build_index(incremental=incremental)


@app.command("recommend")
def cmd_recommend(
    seed: str = typer.Argument(..., help="Seed path or 'Artist - Title' substring"),
    top: int = typer.Option(25, help="Top N results"),
    tempo_pct: float = typer.Option(6.0, help="Tempo tolerance percent"),
    allow_doubletime: bool = typer.Option(True, help="Match 2x/0.5x tempos"),
    camelot_neighbors: bool = typer.Option(True, help="Filter by Camelot compatibility"),
    w_ann: float = typer.Option(0.0, help="Weight: ANN base score"),
    w_samples: float = typer.Option(0.0, help="Weight: samples score (0..1)"),
    w_bass: float = typer.Option(0.0, help="Weight: bass contour similarity (0..1)"),
    w_transition: float = typer.Option(0.0, help="Weight: outro-to-intro section transition score (0..1)"),
    section_scores: bool = typer.Option(False, "--section-scores", help="Use section embeddings when present."),
):
    try:
        from .recommend import recommend as do_rec
    except Exception as e:
        console.print(f"[red]Recommend deps missing (hnswlib). Error: {e}")
        raise typer.Exit(1)
    do_rec(
        seed,
        top=top,
        tempo_pct=tempo_pct,
        allow_doubletime=allow_doubletime,
        camelot_neighbors=camelot_neighbors,
        weights={"ann": w_ann, "samples": w_samples, "bass": w_bass, "transition": w_transition},
        use_section_scores=section_scores,
    )


@app.command("recommend-sequence")
def cmd_recommend_sequence(
    seeds: List[str] = typer.Argument(..., help="One or more seed paths or substrings"),
    top: int = typer.Option(25, help="Top N results to return"),
):
    try:
        from .recommend import recommend_sequence as do_rec_seq
    except Exception as e:
        console.print(f"[red]Recommend deps missing (hnswlib). Error: {e}")
        raise typer.Exit(1)
    do_rec_seq(seeds, top=top)


@app.command("playlist-expand")
def cmd_playlist_expand(
    playlist: str = typer.Option(..., "--playlist", help="Rekordbox playlist name or folder path"),
    target_total: Optional[int] = typer.Option(
        None,
        "--target-total",
        min=1,
        help="Desired final total including mapped seed tracks.",
    ),
    add_count: Optional[int] = typer.Option(
        None,
        "--add-count",
        min=1,
        help="How many new tracks to append to the mapped seed playlist.",
    ),
    source: str = typer.Option("db", "--source", help="Seed source: db | xml"),
    xml_path: Optional[pathlib.Path] = typer.Option(
        None,
        "--xml-path",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Optional Rekordbox XML file used when --source xml or as an explicit fallback if DB loading fails.",
    ),
    mode: str = typer.Option("balanced", help="Expansion mode: tight | balanced | adventurous"),
    strategy: str = typer.Option("blend", help="Expansion strategy: blend | centroid | coverage"),
    candidate_pool: Optional[int] = typer.Option(
        None,
        "--candidate-pool",
        min=25,
        help="How many ANN candidates to fetch before reranking (omit to use the mode preset).",
    ),
    diversity: Optional[float] = typer.Option(
        None,
        "--diversity",
        min=0.0,
        max=1.0,
        help="MMR-style diversity weight for added tracks (omit to use the mode preset).",
    ),
    tempo_pct: Optional[float] = typer.Option(
        None, help="Tempo tolerance percent override (omit to use the mode preset)."
    ),
    allow_doubletime: Optional[bool] = typer.Option(
        None,
        "--allow-doubletime/--no-allow-doubletime",
        help="Allow 2x/0.5x tempo matches inside the playlist envelope (omit to use the mode preset).",
    ),
    key_mode: Optional[str] = typer.Option(
        None,
        "--key-mode",
        help="Key handling override: off | soft | filter (omit to use the mode preset).",
    ),
    key_filter: bool = typer.Option(
        False,
        "--key-filter",
        help="Require Camelot-compatible keys as a hard filter instead of a soft score boost.",
    ),
    w_ann_centroid: Optional[float] = typer.Option(None, help="Override weight: ANN centroid match."),
    w_ann_seed_coverage: Optional[float] = typer.Option(None, help="Override weight: ANN seed coverage."),
    w_group_match: Optional[float] = typer.Option(None, help="Override weight: group-to-seed match."),
    w_bpm: Optional[float] = typer.Option(None, help="Override weight: BPM match."),
    w_key: Optional[float] = typer.Option(None, help="Override weight: key match."),
    w_tags: Optional[float] = typer.Option(None, help="Override weight: tag match."),
    w_transition: Optional[float] = typer.Option(None, help="Override weight: outro-to-intro transition match."),
    section_scores: bool = typer.Option(
        False,
        "--section-scores",
        help="Use intro/late section embeddings when available during reranking.",
    ),
    require_tag: List[str] = typer.Option(
        None,
        "--require-tag",
        help="Require each added track to include this My Tag. Repeat for multiple tags.",
    ),
    preview_json: Optional[pathlib.Path] = typer.Option(
        None,
        "--preview-json",
        help="Optional JSON preview path for the expansion result and diagnostics.",
    ),
    out_xml: Optional[pathlib.Path] = typer.Option(
        None,
        "--out-xml",
        help="Optional Rekordbox XML export path for seed tracks plus additions.",
    ),
    name: Optional[str] = typer.Option(
        None,
        "--name",
        help="Playlist name to use for the XML export (defaults to '<playlist> Expanded').",
    ),
):
    if (target_total is None) == (add_count is None):
        console.print("[red]Provide exactly one of --target-total or --add-count.[/red]")
        raise typer.Exit(1)

    try:
        from .playlist_expand import load_rekordbox_playlist, expand_playlist, write_expansion_xml
    except Exception as e:
        console.print(f"[red]Playlist expansion deps missing or failed to import. Error: {e}[/red]")
        raise typer.Exit(1)

    playlist_source = source.strip().lower()
    if playlist_source not in {"db", "xml"}:
        console.print("[red]--source must be either 'db' or 'xml'.[/red]")
        raise typer.Exit(1)
    if playlist_source == "xml" and xml_path is None:
        console.print("[red]--xml-path is required when --source xml is selected.[/red]")
        raise typer.Exit(1)

    try:
        if playlist_source == "db":
            try:
                seed_playlist = load_rekordbox_playlist(playlist, source="db")
            except Exception as db_exc:
                if xml_path is None:
                    raise
                console.print(
                    f"[yellow]DB playlist load failed ({db_exc}); falling back to XML: {xml_path}[/yellow]"
                )
                seed_playlist = load_rekordbox_playlist(
                    playlist,
                    source="xml",
                    xml_path=str(xml_path),
                )
        else:
            seed_playlist = load_rekordbox_playlist(
                playlist,
                source="xml",
                xml_path=str(xml_path) if xml_path else None,
            )
    except Exception as e:
        console.print(f"[red]Failed to load Rekordbox playlist '{playlist}': {e}[/red]")
        raise typer.Exit(1)

    try:
        expand_kwargs = _build_playlist_expansion_kwargs(
            mode=mode,
            strategy=strategy,
            candidate_pool=candidate_pool,
            diversity=diversity,
            tempo_pct=tempo_pct,
            allow_doubletime=allow_doubletime,
            key_mode=key_mode,
            key_filter=key_filter,
            w_ann_centroid=w_ann_centroid,
            w_ann_seed_coverage=w_ann_seed_coverage,
            w_group_match=w_group_match,
            w_bpm=w_bpm,
            w_key=w_key,
            w_tags=w_tags,
            w_transition=w_transition,
            require_tags=require_tag,
            section_scores=section_scores,
        )
        result = expand_playlist(
            seed_playlist,
            add_count=add_count,
            target_total=target_total,
            **expand_kwargs,
        )
    except Exception as e:
        console.print(f"[red]Playlist expansion failed: {e}[/red]")
        raise typer.Exit(1)

    diag = result.diagnostics
    console.print(
        "[green]Expanded playlist[/green] "
        f"'{seed_playlist.name}' via {seed_playlist.source} "
        f"({diag.get('clean_seed_tracks_total', 0)} mapped seeds, "
        f"{diag.get('added_tracks_total', 0)} additions, "
        f"{diag.get('combined_tracks_total', 0)} total)."
    )
    console.print(
        f"[cyan]Requested[/cyan] add_count={diag.get('requested_add_count')} "
        f"target_total={diag.get('requested_target_total')} "
        f"strategy={diag.get('strategy')} mode={diag.get('mode')}"
    )
    if diag.get("seed_loader_diagnostics"):
        loader = diag["seed_loader_diagnostics"]
        console.print(
            f"[cyan]Seed loader[/cyan] total={loader.get('seed_tracks_total', 0)} "
            f"matched={loader.get('matched_total', 0)} "
            f"unmapped={loader.get('unmapped_total', 0)} "
            f"missing_embedding={loader.get('missing_embedding_total', 0)}"
        )

    if preview_json is not None:
        preview_json.parent.mkdir(parents=True, exist_ok=True)
        preview_json.write_text(
            json.dumps(result.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        console.print(f"[green]Wrote preview JSON -> {preview_json}[/green]")

    if out_xml is not None:
        playlist_name = name or f"{seed_playlist.name} Expanded"
        write_expansion_xml(result, out_path=str(out_xml), playlist_name=playlist_name)
        console.print(f"[green]Wrote Rekordbox XML -> {out_xml}[/green]")


@app.command("bandcamp-import")
def cmd_bandcamp_import(csv_path: str, config_path: str):
    from .bandcamp import import_bandcamp
    meta = load_meta()
    updated = import_bandcamp(csv_path, config_path, meta)
    save_meta(updated)
    console.print("[green]Bandcamp CSV imported into meta tags.")


@app.command("import-mytags")
def cmd_import_mytags(
    xml_paths: List[str] = typer.Argument(..., help="One or more Rekordbox XML exports with My Tags"),
    only_existing: bool = typer.Option(True, help="Skip tracks not present in rbassist meta"),
):
    from .tagstore import import_rekordbox_tags

    if not xml_paths:
        console.print("[red]Provide at least one Rekordbox XML path.")
        raise typer.Exit(1)

    total_imported = 0
    failures = 0
    for xml_path in xml_paths:
        try:
            count = import_rekordbox_tags(xml_path, only_existing=only_existing)
        except FileNotFoundError:
            console.print(f"[red]XML not found: {xml_path}")
            failures += 1
            continue
        except Exception as e:
            console.print(f"[red]Failed to import My Tags from {xml_path}: {e}")
            failures += 1
            continue
        total_imported += count
        if count:
            console.print(f"[green]{xml_path}: imported My Tags for {count} track(s).")
        else:
            console.print(f"[yellow]{xml_path}: no matching My Tags found.")

    if total_imported:
        console.print(f"[green]Total tracks updated: {total_imported}")
    if failures and not total_imported:
        raise typer.Exit(1)


@app.command("rekordbox-import-mytags-db")
def cmd_rekordbox_import_mytags_db() -> None:
    """
    Import Rekordbox 6+ MyTags directly from the encrypted master.db using
    pyrekordbox (no XML export required).

    Rekordbox should be closed while this runs to avoid database locks.
    """
    try:
        from .rekordbox_import import import_rekordbox_mytags_from_db
    except Exception as e:
        console.print(
            "[red]Rekordbox DB import requires the 'pyrekordbox' dependency and a compatible SQLCipher setup. "
            f"Error: {e}[/red]"
        )
        raise typer.Exit(1)

    try:
        added = import_rekordbox_mytags_from_db()
    except Exception as e:
        console.print(f"[red]Rekordbox MyTag DB import failed: {e}[/red]")
        raise typer.Exit(1)

    if not added:
        console.print("[yellow]No new MyTag assignments were imported from Rekordbox.[/yellow]")



@app.command("tags-auto")
def cmd_tags_auto(
    targets: Optional[List[str]] = typer.Argument(None, help="Optional files/folders to score (omit = all untagged tracks)"),
    min_samples: int = typer.Option(3, help="Minimum tagged tracks required per label"),
    margin: float = typer.Option(0.0, help="Lower confidence threshold by this amount"),
    top: int = typer.Option(3, help="Max tags to report per track (0 = all)"),
    apply: bool = typer.Option(False, "--apply", help="Persist suggested tags into config/meta"),
    include_tagged: bool = typer.Option(False, help="Also evaluate tracks that already have My Tags"),
    prune_margin: float = typer.Option(0.0, help="Suggest removal if existing tag score < threshold - value"),
    csv_out: Optional[str] = typer.Option(None, "--csv", help="Write suggestions to CSV (preview mode)"),
    save_suggestions: bool = typer.Option(False, help="Store suggestion results in meta for later review"),
):
    from .tag_model import learn_tag_profiles, suggest_tags_for_tracks, evaluate_existing_tags
    from .tagstore import bulk_set_track_tags

    meta = load_meta()
    profiles = learn_tag_profiles(min_samples=min_samples, meta=meta)
    if not profiles:
        console.print("[red]No tagged tracks available to learn from. Import or assign My Tags first.")
        raise typer.Exit(1)

    if targets:
        files = walk_audio(targets)
        if not files:
            console.print("[yellow]No audio files found in the provided targets.")
            raise typer.Exit(1)
        missing = [p for p in files if p not in meta["tracks"] or not meta["tracks"][p].get("embedding")]
        if missing:
            console.print(f"[yellow]{len(missing)} file(s) lack embeddings or meta. Run 'rbassist embed' first.")
        track_paths = [p for p in files if p in meta["tracks"]]
    else:
        track_paths = [
            p for p, info in meta["tracks"].items()
            if (include_tagged or not info.get("mytags")) and info.get("embedding")
        ]

    if not track_paths:
        console.print("[yellow]No tracks to evaluate.")
        raise typer.Exit(1)

    suggestions = suggest_tags_for_tracks(track_paths, profiles, margin=margin, top_k=top, meta=meta)
    if not suggestions:
        console.print("[yellow]No tag suggestions met the confidence threshold.")
    existing_scores = evaluate_existing_tags(track_paths, profiles, meta=meta)

    low_confidence: Dict[str, List[Tuple[str, float, float]]] = {}
    if prune_margin > 0.0:
        for path, rows in existing_scores.items():
            drops = [(tag, score, thr) for tag, score, thr in rows if score < (thr - prune_margin)]
            if drops:
                low_confidence[path] = drops

    if suggestions:
        console.print("[bold cyan]Suggested My Tags[/bold cyan]")
        for path, tags in suggestions.items():
            console.print(f"[cyan]{path}")
            for tag, score, threshold in tags:
                delta = score - threshold
                console.print(f"  -> [green]{tag}[/green] score={score:.3f} (threshold {threshold:.3f}, Δ{delta:.3f})")
    if prune_margin > 0.0:
        if low_confidence:
            console.print("[bold magenta]Low-confidence existing tags (candidates for removal)[/bold magenta]")
            for path, rows in low_confidence.items():
                console.print(f"[magenta]{path}")
                for tag, score, threshold in rows:
                    deficit = threshold - score
                    console.print(f"  -> [red]{tag}[/red] score={score:.3f} (threshold {threshold:.3f}, deficit {deficit:.3f})")
        else:
            console.print("[green]No existing tags fell below the prune margin.")

    if csv_out:
        rows: List[List[object]] = []
        for path, tags in suggestions.items():
            for tag, score, thr in tags:
                rows.append(["suggest", path, tag, score, thr, score - thr])
        for path, tags in low_confidence.items():
            for tag, score, thr in tags:
                rows.append(["prune", path, tag, score, thr, score - thr])
        with open(csv_out, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["type", "path", "tag", "score", "threshold", "delta"])
            writer.writerows(rows)
        console.print(f"[green]Wrote suggestion preview -> {csv_out}")

    if save_suggestions and (suggestions or low_confidence):
        meta_for_save = load_meta()
        now = datetime.utcnow().isoformat()
        for path, tags in suggestions.items():
            info = meta_for_save["tracks"].setdefault(path, {})
            info["tag_suggestions"] = {
                "generated": now,
                "params": {
                    "min_samples": min_samples,
                    "margin": margin,
                    "top": top,
                    "prune_margin": prune_margin,
                    "include_tagged": include_tagged,
                },
                "candidates": [
                    {"tag": tag, "score": float(score), "threshold": float(thr)}
                    for tag, score, thr in tags
                ],
                "low_confidence": [
                    {"tag": tag, "score": float(score), "threshold": float(thr)}
                    for tag, score, thr in low_confidence.get(path, [])
                ],
            }
        save_meta(meta_for_save)
        console.print("[green]Suggestion snapshot stored in meta (tag_suggestions).")

    if apply:
        updates: Dict[str, List[str]] = {}
        tracks_meta = meta.get("tracks", {})
        from . import safe_tagstore as _safe_tagstore

        effective_current_tags = _safe_tagstore.load_effective_user_tags(meta=meta)
        affected_paths = set(suggestions.keys()) | set(low_confidence.keys())
        for path in affected_paths:
            info = tracks_meta.get(path, {})
            current = set(effective_current_tags.get(path, info.get("mytags", [])))
            add_tags = {tag for tag, _score, _thr in suggestions.get(path, [])}
            updated = current | add_tags
            if prune_margin > 0.0:
                drop_tags = {tag for tag, _score, _thr in low_confidence.get(path, [])}
                updated -= drop_tags
            if updated != current:
                updates[path] = sorted(updated)
        if updates:
            applied = bulk_set_track_tags(updates, only_existing=False)
            console.print(f"[green]Applied tag updates to {applied} track(s).")
        else:
            console.print("[yellow]No tag changes required.")


@app.command("export-xml")
def cmd_export_xml(out: str = typer.Option("rbassist.xml"), name: str = typer.Option("rbassist export")):
    from .export_xml import write_rekordbox_xml
    meta = load_meta()
    write_rekordbox_xml(meta, out_path=out, playlist_name=name)
    console.print(f"[green]Wrote {out}")


@app.command("djlink-listen")
def cmd_djlink():
    try:
        from .djlink import run
    except Exception as e:
        console.print(f"[red]{e}")
        raise typer.Exit(1)
    run()


@app.command("cues")
def cmd_cues(
    path: str,
    duration: int = 120,
    cue_profile: str = typer.Option(
        "",
        "--cue-profile",
        help="Optional cue template profile name from config/cue_templates.yml.",
    ),
    overwrite: bool = typer.Option(
        False,
        "--overwrite",
        help="Replace existing cue data for the target track.",
    ),
):
    from .cues import propose_cues
    from .analyze import _estimate_tempo
    meta = load_meta()
    info = meta["tracks"].setdefault(path, {})
    if info.get("cues") and not overwrite:
        console.print("[yellow]Track already has cues. Re-run with --overwrite to replace them.")
        return
    y, sr = librosa.load(path, sr=None, mono=True, duration=duration if duration > 0 else None)
    bpm = _estimate_tempo(y, sr)
    cues = propose_cues(y, sr, bpm=bpm, cue_profile=(cue_profile or None))
    info.setdefault("bpm", round(float(bpm), 2))
    info["cues"] = cues
    save_meta(meta)
    console.print(f"[green]Wrote cues for {path}")


@app.command("int-pl")
def cmd_intelligent_playlist(out: str = "rb_intelligent.xml",
                             name: str = "Intelligent",
                             my_tag: str = "", rating_min: int = 0,
                             since: str = "", until: str = ""):
    from .playlists import make_intelligent_playlist
    make_intelligent_playlist(out, name=name,
                              my_tag=(my_tag or None),
                              rating_min=(rating_min if rating_min > 0 else None),
                              since=(since or None), until=(until or None))
    console.print(f"[green]Wrote intelligent playlist -> {out}")


@app.command("dup-check")
def cmd_dup(exact: bool = typer.Option(False, "--exact", help="Use content hash for exact duplicates")):
    from .duplicates import find_duplicates, cdj_warnings
    meta = load_meta()
    pairs = find_duplicates(meta, exact=exact)
    console.print(f"[cyan]Duplicates: {len(pairs)}")
    for keep, lose in pairs:
        console.print(f"[yellow]KEEP[/yellow] {keep}  ->  [red]REMOVE[/red] {lose}")
        for w in cdj_warnings(keep):
            console.print(f"  [magenta]{w}")


@app.command("dup-stage")
def cmd_dup_stage(
    dest: pathlib.Path = typer.Option(pathlib.Path("data/dup_stage"), help="Folder to stage duplicates into."),
    move: bool = typer.Option(False, help="Move files instead of copying."),
    dry_run: bool = typer.Option(False, help="List actions without touching files."),
    exact: bool = typer.Option(False, "--exact", help="Use content hash for exact duplicates"),
):
    from .duplicates import stage_duplicates

    meta = load_meta()
    staged = stage_duplicates(meta, str(dest), move=move, dry_run=dry_run, exact=exact)
    if dry_run:
        console.print(f"[cyan]Would stage {len(staged)} files -> {dest}")
    else:
        console.print(f"[green]Staged {len(staged)} files -> {dest}")
    for src, tgt in staged[:20]:
        console.print(f"  {src} -> {tgt}")
    if len(staged) > 20:
        console.print(f"...and {len(staged) - 20} more")


@app.command("normalize")
def cmd_norm(path: str, target_lufs: float = -11.0):
    try:
        from .normalize import normalize_tag
    except Exception as e:
        console.print(f"[red]Install pyloudnorm to use normalization. Error: {e}")
        raise typer.Exit(1)
    g = normalize_tag(path, target_lufs=target_lufs)
    console.print(f"[green]{path} -> ReplayGain {g:+.2f} dB to reach {target_lufs} LUFS")


@app.command("mirror-csv")
def cmd_mirror_csv(csv_path: str, out_xml: str = "rb_from_csv.xml", name: str = "CSV Playlist"):
    from .sync_online import import_csv_playlist
    from .export_xml import write_rekordbox_xml
    meta = load_meta()
    paths = import_csv_playlist(csv_path)
    sub = {"tracks": {p: meta["tracks"][p] for p in paths if p in meta["tracks"]}}
    write_rekordbox_xml(sub, out_xml, name)
    console.print(f"[green]Wrote {len(sub['tracks'])} tracks -> {out_xml}")


@app.command("features")
def cmd_features(root: str, limit: int = 0, duration_s: int = 90):
    """Backfill lightweight features (samples, bassline) into metadata for a folder."""
    try:
        from .features import samples_score, bass_contour  # noqa: F401
    except Exception as e:
        console.print(f"[red]Feature deps missing (librosa/numpy). Error: {e}")
        raise typer.Exit(1)
    files = walk_audio([root])
    if limit and limit > 0:
        files = files[:limit]
    from .analyze import analyze_bpm_key as _noop  # reuse loader path; features now computed during analyze
    # Run through analyze_bpm_key with only_new=True to compute features for new files
    _noop(files, duration_s=duration_s, only_new=False, force=False)
    console.print(f"[green]Feature backfill attempted for {len(files)} files")


@app.command("ui")
def cmd_ui(
    port: int = typer.Option(8080, help="Port to run the UI server on"),
    reload: bool = typer.Option(False, help="Enable hot reload for development"),
):
    """Launch the NiceGUI desktop interface."""
    try:
        from .ui import run
    except ImportError as e:
        console.print(f"[red]UI dependencies not installed. Run: pip install -e '.[ui]'")
        console.print(f"[red]Error: {e}")
        raise typer.Exit(1)
    run(port=port, reload=reload)


# Add AI tag learning commands as a sub-command group
try:
    from .ai_tag_cli import app as ai_tag_app
    app.add_typer(ai_tag_app, name="ai-tag")
except ImportError:
    # Dependencies not installed, skip
    pass


if __name__ == "__main__":
    main()
