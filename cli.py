from __future__ import annotations
import pathlib, numpy as np
import librosa
from typing import Iterable, List
import typer
from .utils import load_meta, save_meta, file_sig, console, walk_audio

# Krumhansl & Kessler key profiles (major/minor)
_MAJ = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88], dtype=float)
_MIN = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17], dtype=float)

# Mapping from pitch class name (sharp) to Camelot
_CAML_MAJ = {
    'C':'8B','C#':'3B','D':'10B','D#':'5B','E':'12B','F':'7B',
    'F#':'2B','G':'9B','G#':'4B','A':'11B','A#':'6B','B':'1B'
}
_CAML_MIN = {
    'C':'5A','C#':'12A','D':'7A','D#':'2A','E':'9A','F':'4A',
    'F#':'11A','G':'6A','G#':'1A','A':'8A','A#':'3A','B':'10A'
}
_PC_TO_NAME_SHARP = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']


def _estimate_tempo(y: np.ndarray, sr: int) -> float:
    # robust onset envelope + median tempo
    oe = librosa.onset.onset_strength(y=y, sr=sr)
    t = librosa.beat.tempo(onset_envelope=oe, sr=sr, aggregate='median')
    return float(t.item()) if np.ndim(t) else float(t)


def _estimate_key(y: np.ndarray, sr: int) -> tuple[str, str]:
    # average chroma; compare to rotated key profiles
    C = librosa.feature.chroma_cqt(y=y, sr=sr)
    chroma = C.mean(axis=1)
    if np.linalg.norm(chroma) > 0:
        chroma = chroma / np.linalg.norm(chroma)
    best_score = -1e9
    best = (0, 'maj')
    for pc in range(12):
        maj_s = float(chroma @ np.roll(_MAJ, pc))
        min_s = float(chroma @ np.roll(_MIN, pc))
        if maj_s > best_score:
            best_score, best = maj_s, (pc, 'maj')
        if min_s > best_score:
            best_score, best = min_s, (pc, 'min')
    pc, mode = best
    name = _PC_TO_NAME_SHARP[pc]
    if mode == 'maj':
        camelot = _CAML_MAJ[name]
        full = f"{name} major"
    else:
        camelot = _CAML_MIN[name]
        full = f"{name} minor"
    return camelot, full


def analyze_bpm_key(paths: Iterable[str], duration_s: int = 90, only_new: bool = True, force: bool = False) -> None:
    meta = load_meta()
    to_do = []
    for p in paths:
        info = meta['tracks'].setdefault(p, {})
        sig = file_sig(p)
        have = ('bpm' in info and 'key' in info)
        if force:
            to_do.append(p)
        elif only_new:
            if have and info.get('sig_bpmkey') == sig:
                continue
            to_do.append(p)
        else:
            if not have:
                to_do.append(p)
    if not to_do:
        console.print('[green]No BPM/Key work to do.')
        return
    for p in to_do:
        try:
            y, sr = librosa.load(p, sr=None, mono=True, duration=duration_s if duration_s>0 else None)
            bpm = _estimate_tempo(y, sr)
            camelot, full = _estimate_key(y, sr)
            info = meta['tracks'].setdefault(p, {})
            info['bpm'] = round(float(bpm), 2)
            info['key'] = camelot
            info['key_name'] = full
            info['sig_bpmkey'] = file_sig(p)
            # best-effort title/artist from filename if missing
            stem = pathlib.Path(p).stem
            if ' - ' in stem:
                a, t = stem.split(' - ', 1)
                info.setdefault('artist', a)
                info.setdefault('title', t)
            else:
                info.setdefault('title', stem)
        except Exception as e:
            console.print(f"[red]BPM/Key failed for {p}: {e}")
        finally:
            save_meta(meta)
    save_meta(meta)
    console.print(f"[green]Analyzed {len(to_do)} files (BPM + Key).")


# ------------------------------
# Typer CLI
# ------------------------------

app = typer.Typer(no_args_is_help=True, add_completion=False, help="RBassist command line tools")


@app.command("analyze")
def cmd_analyze(
    paths: List[str] = typer.Argument(..., help="One or more files or folders to analyze"),
    duration_s: int = typer.Option(90, help="Max seconds per track to analyze (0 = full)"),
    only_new: bool = typer.Option(True, help="Skip files already analyzed with same signature"),
    force: bool = typer.Option(False, help="Force re-analyze even if cached")
):
    files = walk_audio(paths)
    if not files:
        console.print("[yellow]No audio files found in given paths.")
        raise typer.Exit(code=1)
    try:
        from .analyze import analyze_bpm_key as run_analyze
    except Exception:
        # Fallback to local implementation if needed
        run_analyze = analyze_bpm_key
    run_analyze(files, duration_s=duration_s, only_new=only_new, force=force)


def main() -> None:
    app()


if __name__ == "__main__":
    main()

# ------------------------------
# Additional Commands
# ------------------------------

@app.command("embed")
def cmd_embed(
    paths: List[str] = typer.Argument(..., help="Files or folders to embed"),
    duration_s: int = typer.Option(120, help="Seconds per track (0=full)"),
    model: str = typer.Option("m-a-p/MERT-v1-330M", help="HF model name for MERT")
):
    try:
        from .embed import build_embeddings, DEFAULT_MODEL
    except Exception as e:
        console.print(f"[red]Embed deps missing: install .[ml] and torch. Error: {e}")
        raise typer.Exit(1)
    files = walk_audio(paths)
    if not files:
        console.print("[yellow]No audio files found.")
        raise typer.Exit(1)
    build_embeddings(files, model_name=model or DEFAULT_MODEL, duration_s=duration_s)


@app.command("index")
def cmd_index():
    try:
        from .recommend import build_index
    except Exception as e:
        console.print(f"[red]Index deps missing (hnswlib). Error: {e}")
        raise typer.Exit(1)
    build_index()


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


@app.command("bandcamp-import")
def cmd_bandcamp_import(csv_path: str, config_path: str):
    from .bandcamp import import_bandcamp
    meta = load_meta()
    updated = import_bandcamp(csv_path, config_path, meta)
    save_meta(updated)
    console.print("[green]Bandcamp CSV imported into meta tags.")


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


@app.command("web")
def cmd_web():
    import subprocess, sys
    try:
        import streamlit  # noqa: F401
    except Exception:
        console.print("[red]Install Streamlit first: pip install streamlit")
        raise typer.Exit(1)
    subprocess.run([sys.executable, "-m", "streamlit", "run", "rbassist/webapp.py"])  # nosec


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
def cmd_dup():
    from .duplicates import find_duplicates, cdj_warnings
    meta = load_meta()
    pairs = find_duplicates(meta)
    console.print(f"[cyan]Duplicates: {len(pairs)}")
    for keep, lose in pairs:
        console.print(f"[yellow]KEEP[/yellow] {keep}  ->  [red]REMOVE[/red] {lose}")
        for w in cdj_warnings(keep):
            console.print(f"  [magenta]{w}")


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
