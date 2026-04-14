from __future__ import annotations
import pathlib, numpy as np
import librosa
import warnings
from typing import Callable, Iterable, Optional
from concurrent.futures import ProcessPoolExecutor, as_completed
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn, TaskID
from .utils import current_file_sig, console, MetaManager
try:
    from .features import samples_score, bass_contour, rhythm_contour, chroma_tonnetz_profiles
except Exception:
    samples_score = None  # type: ignore
    bass_contour = None  # type: ignore
    rhythm_contour = None  # type: ignore
    chroma_tonnetz_profiles = None  # type: ignore

# Krumhansl & Kessler key profiles (major/minor)
_MAJ = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88], dtype=float)
_MIN = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17], dtype=float)

# Mapping from pitch class name (sharp) to Camelot
_CAML_MAJ = {
    "C": "8B",
    "C#": "3B",
    "D": "10B",
    "D#": "5B",
    "E": "12B",
    "F": "7B",
    "F#": "2B",
    "G": "9B",
    "G#": "4B",
    "A": "11B",
    "A#": "6B",
    "B": "1B",
}
_CAML_MIN = {
    "C": "5A",
    "C#": "12A",
    "D": "7A",
    "D#": "2A",
    "E": "9A",
    "F": "4A",
    "F#": "11A",
    "G": "6A",
    "G#": "1A",
    "A": "8A",
    "A#": "3A",
    "B": "10A",
}
_PC_TO_NAME_SHARP = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Suppress known, harmless FutureWarnings from librosa API shims (0.10+).
warnings.filterwarnings(
    "ignore",
    category=FutureWarning,
    message="librosa.beat.tempo",
)


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
    best = (0, "maj")
    for pc in range(12):
        maj_s = float(chroma @ np.roll(_MAJ, pc))
        min_s = float(chroma @ np.roll(_MIN, pc))
        if maj_s > best_score:
            best_score, best = maj_s, (pc, "maj")
        if min_s > best_score:
            best_score, best = min_s, (pc, "min")
    pc, mode = best
    name = _PC_TO_NAME_SHARP[pc]
    if mode == "maj":
        camelot = _CAML_MAJ[name]
        full = f"{name} major"
    else:
        camelot = _CAML_MIN[name]
        full = f"{name} minor"
    return camelot, full


def _analyze_single(
    path: str,
    duration_s: int = 90,
    add_cues: bool = True,
    cue_profile: str | None = None,
    harmonic_profiles: bool = False,
) -> tuple[str, dict | None, str | None, str | None]:
    warn: str | None = None
    try:
        y, sr = librosa.load(path, sr=None, mono=True, duration=duration_s if duration_s > 0 else None)
        bpm = _estimate_tempo(y, sr)
        camelot, full = _estimate_key(y, sr)
        result: dict = {
            "bpm": round(float(bpm), 2),
            "key": camelot,
            "key_name": full,
        }
        if add_cues:
            try:
                from .cues import propose_cues

                result["cues"] = propose_cues(y, sr, bpm=result["bpm"], cue_profile=cue_profile)
            except Exception:
                pass
        feats: dict[str, object] = {}
        feature_warnings: list[str] = []
        if samples_score is not None:
            try:
                feats["samples"] = float(samples_score(y, sr))
            except Exception as e:
                feature_warnings.append(f"samples: {e}")
        if bass_contour is not None:
            try:
                contour, rel = bass_contour(y, sr)
                ds = librosa.util.fix_length(contour, size=256).astype(float).tolist()
                feats["bass_contour"] = {"contour": ds, "reliability": float(rel)}
            except Exception as e:
                feature_warnings.append(f"bass_contour: {e}")
        if rhythm_contour is not None:
            try:
                rcont, rrel = rhythm_contour(y, sr)
                feats["rhythm_contour"] = {
                    "contour": librosa.util.fix_length(rcont, size=256).astype(float).tolist(),
                    "reliability": float(rrel),
                }
            except Exception as e:
                feature_warnings.append(f"rhythm_contour: {e}")
        if harmonic_profiles and chroma_tonnetz_profiles is not None:
            try:
                feats.update(chroma_tonnetz_profiles(y, sr))
            except Exception as e:
                feature_warnings.append(f"harmonic_profiles: {e}")
        if feats:
            result["features"] = feats
        if feature_warnings:
            warn = f"Feature extract skip for {path}: " + "; ".join(feature_warnings)
        return path, result, None, warn
    except Exception as e:
        return path, None, str(e), warn


def _store_generated_cues(
    info: dict,
    cues: list[dict],
    *,
    overwrite_cues: bool = False,
) -> bool:
    if not cues:
        return False
    if info.get("cues") and not overwrite_cues:
        return False
    info["cues"] = cues
    return True


def _has_harmonic_profiles(info: dict) -> bool:
    feats = info.get("features", {})
    if not isinstance(feats, dict):
        return False
    return (
        isinstance(feats.get("chroma_profile"), list)
        and len(feats.get("chroma_profile", [])) == 12
        and isinstance(feats.get("tonnetz_profile"), list)
        and len(feats.get("tonnetz_profile", [])) == 6
    )


def analyze_bpm_key(
    paths: Iterable[str],
    duration_s: int = 90,
    only_new: bool = True,
    force: bool = False,
    add_cues: bool = True,
    overwrite_cues: bool = False,
    cue_profile: str | None = None,
    harmonic_profiles: bool = False,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    workers: int | None = None,
) -> None:
    with MetaManager() as meta_mgr:
        meta = meta_mgr.meta
        sig_cache: dict[str, str] = {}
        to_do: list[str] = []
        for p in paths:
            info = meta["tracks"].setdefault(p, {})
            sig = current_file_sig(p)
            sig_cache[p] = sig
            have = ("bpm" in info and "key" in info)
            if force:
                to_do.append(p)
            elif only_new:
                if have and info.get("sig_bpmkey") == sig and (not harmonic_profiles or _has_harmonic_profiles(info)):
                    continue
                to_do.append(p)
            else:
                if not have or (harmonic_profiles and not _has_harmonic_profiles(info)):
                    to_do.append(p)
        if not to_do:
            console.print("[green]No BPM/Key work to do.")
            return
        total = len(to_do)
        progress: Progress | None = None
        task_id: TaskID | None = None
        try:
            if progress_callback is None:
                progress = Progress(
                    "{task.description}",
                    BarColumn(bar_width=None),
                    TextColumn("{task.completed}/{task.total}"),
                    TimeRemainingColumn(),
                )
                progress.start()
                task_id = progress.add_task("Analyzing", total=total)

            done = 0

            def _tick(path: str) -> None:
                nonlocal done
                done += 1
                if progress_callback is not None:
                    progress_callback(done, total, path)
                elif progress is not None and task_id is not None:
                    progress.advance(task_id)

            def _apply_result(path: str, result: dict | None, warn: str | None, err: str | None) -> None:
                if warn:
                    console.print(f"[yellow]{warn}")
                if err or result is None:
                    console.print(f"[red]BPM/Key failed for {path}: {err}")
                    _tick(path)
                    return
                info = meta["tracks"].setdefault(path, {})
                sig = sig_cache.get(path)
                have_bpm_key = "bpm" in info and "key" in info
                profile_only = bool(
                    harmonic_profiles
                    and not force
                    and have_bpm_key
                    and sig
                    and info.get("sig_bpmkey") == sig
                )
                changed = False
                if not profile_only:
                    for key in ("bpm", "key", "key_name"):
                        if info.get(key) != result.get(key):
                            info[key] = result[key]
                            changed = True
                    if sig and info.get("sig_bpmkey") != sig:
                        info["sig_bpmkey"] = sig
                        changed = True
                    stem = pathlib.Path(path).stem
                    if " - " in stem:
                        a, t = stem.split(" - ", 1)
                        if "artist" not in info:
                            info["artist"] = a
                            changed = True
                        if "title" not in info:
                            info["title"] = t
                            changed = True
                    elif "title" not in info:
                        info["title"] = stem
                        changed = True
                    if add_cues and "cues" in result:
                        changed = _store_generated_cues(
                            info,
                            result["cues"],
                            overwrite_cues=overwrite_cues,
                        ) or changed
                if "features" in result:
                    if not isinstance(info.get("features"), dict):
                        info["features"] = {}
                        changed = True
                    feats = info["features"]
                    for k, v in result["features"].items():
                        if k not in feats:
                            feats[k] = v
                            changed = True
                if changed:
                    meta_mgr.mark_dirty()
                _tick(path)

            use_workers = workers if workers and workers > 1 else None
            if use_workers:
                with ProcessPoolExecutor(max_workers=use_workers) as ex:
                    future_map = {
                        ex.submit(_analyze_single, p, duration_s, add_cues, cue_profile, harmonic_profiles): p
                        for p in to_do
                    }
                    for fut in as_completed(future_map):
                        path = future_map[fut]
                        try:
                            _path, result, err, warn = fut.result()
                        except Exception as e:
                            _apply_result(path, None, None, str(e))
                            continue
                        _apply_result(path, result, warn, err)
            else:
                for p in to_do:
                    _path, result, err, warn = _analyze_single(p, duration_s, add_cues, cue_profile, harmonic_profiles)
                    _apply_result(p, result, warn, err)

            console.print(f"[green]Analyzed {len(to_do)} files (BPM + Key).")
        finally:
            if progress is not None:
                progress.stop()
