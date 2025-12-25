from __future__ import annotations
import pathlib
import librosa
import csv
from datetime import datetime
from typing import List, Optional, Dict, Tuple
import typer
from .analyze import analyze_bpm_key
from .utils import load_meta, save_meta, console, walk_audio, pick_device
from .sampling_profile import load_sampling_params
from .beatgrid import analyze_paths as analyze_beatgrid_paths, BeatgridConfig


# ------------------------------
# Typer CLI
# ------------------------------

app = typer.Typer(no_args_is_help=True, add_completion=False, help="RBassist command line tools")


@app.command("analyze")
def cmd_analyze(
    paths: List[str] = typer.Argument(..., help="One or more files or folders to analyze"),
    duration_s: int = typer.Option(90, help="Max seconds per track to analyze (0 = full)"),
    only_new: bool = typer.Option(True, help="Skip files already analyzed with same signature"),
    force: bool = typer.Option(False, help="Force re-analyze even if cached"),
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
    paths: List[str] = typer.Argument(..., help="Files or folders to embed"),
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
    files = walk_audio(paths)
    if not files:
        console.print("[yellow]No audio files found.")
        raise typer.Exit(1)
    build_embeddings(
        files,
        model_name=model or DEFAULT_MODEL,
        duration_s=duration_s,
        device=(device or None),
        num_workers=num_workers,
        batch_size=batch_size,
        timbre=timbre,
        timbre_size=timbre_size,
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
    w_bass: float = typer.Option(0.0, help="Weight: bass contour similarity (0..1)")
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
        weights={"ann": w_ann, "samples": w_samples, "bass": w_bass},
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
        affected_paths = set(suggestions.keys()) | set(low_confidence.keys())
        for path in affected_paths:
            info = tracks_meta.get(path, {})
            current = set(info.get("mytags", []))
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
def cmd_cues(path: str, duration: int = 120):
    from .cues import propose_cues
    from .analyze import _estimate_tempo
    y, sr = librosa.load(path, sr=None, mono=True, duration=duration if duration > 0 else None)
    bpm = _estimate_tempo(y, sr)
    cues = propose_cues(y, sr, bpm=bpm)
    meta = load_meta()
    info = meta["tracks"].setdefault(path, {})
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
