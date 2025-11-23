from __future__ import annotations
import pathlib, numpy as np
import librosa
from typing import Callable, Iterable, Optional
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn
from .utils import load_meta, save_meta, file_sig, console
try:
    from .features import samples_score, bass_contour
except Exception:
    samples_score = None  # type: ignore
    bass_contour = None  # type: ignore

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
    t = librosa.beat.tempo(onset_envelope=oe, sr=sr, aggregate=np.median)
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


def analyze_bpm_key(
    paths: Iterable[str],
    duration_s: int = 90,
    only_new: bool = True,
    force: bool = False,
    add_cues: bool = True,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> None:
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
    total = len(to_do)
    progress: Progress | None = None
    task_id: TaskID | None = None
    if progress_callback is None:
        progress = Progress(
            "{task.description}",
            BarColumn(bar_width=None),
            TextColumn("{task.completed}/{task.total}"),
            TimeRemainingColumn(),
        )
        progress.start()
        task_id = progress.add_task("Analyzing", total=total)

    def _tick(idx: int, path: str):
        if progress_callback is not None:
            progress_callback(idx, total, path)
        elif progress is not None and task_id is not None:
            progress.advance(task_id)

    for idx, p in enumerate(to_do, start=1):
        try:
            _tick(idx, p)
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
            # auto-cues proposal (best-effort)
            if add_cues:
                try:
                    from .cues import propose_cues
                    info['cues'] = propose_cues(y, sr, bpm=info['bpm'])
                except Exception:
                    pass
            # lightweight features cache (optional)
            try:
                feats = info.setdefault('features', {})
                if samples_score is not None and 'samples' not in feats:
                    feats['samples'] = float(samples_score(y, sr))
                if bass_contour is not None and 'bass_contour' not in feats:
                    contour, rel = bass_contour(y, sr)
                    ds = librosa.util.fix_length(contour, size=256).astype(float).tolist()
                    feats['bass_contour'] = { 'contour': ds, 'reliability': float(rel) }
            except Exception as e:
                console.print(f"[yellow]Feature extract skip for {p}: {e}")
        except Exception as e:
            console.print(f"[red]BPM/Key failed for {p}: {e}")
        finally:
            save_meta(meta)
    save_meta(meta)
    console.print(f"[green]Analyzed {len(to_do)} files (BPM + Key).")
    if progress is not None:
        progress.stop()
