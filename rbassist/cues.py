from __future__ import annotations

from dataclasses import dataclass

import librosa
import numpy as np

from .cue_templates import CueTemplate, CueTemplateEntry, load_cue_template


@dataclass(frozen=True)
class CueAnchors:
    duration_s: float
    beat_s: float
    first_downbeat: float
    first_drop: float
    second_drop: float | None
    break_start: float
    hot_b_start: float
    mix_out_start: float
    end_guard_start: float


def _bars_to_seconds(bars: int | float, bpm: float) -> float:
    if bpm <= 0:
        return 0.0
    return float(bars) * 4.0 * (60.0 / bpm)


def _quantize_to_grid(value_s: float, anchor_s: float, beat_s: float) -> float:
    if beat_s <= 0:
        return max(0.0, float(value_s))
    steps = round((float(value_s) - anchor_s) / beat_s)
    return max(0.0, anchor_s + (steps * beat_s))


def _clamp_loop_start(start_s: float, length_s: float, duration_s: float) -> float:
    if length_s <= 0:
        return max(0.0, float(start_s))
    return max(0.0, min(float(start_s), max(0.0, duration_s - length_s)))


def _detect_first_downbeat(y: np.ndarray, sr: int) -> float:
    onset = librosa.onset.onset_strength(y=y, sr=sr, aggregate=np.median)
    times = librosa.times_like(onset, sr=sr)
    if onset.size == 0:
        return 0.0
    threshold = float(np.percentile(onset, 75))
    strong = np.flatnonzero(onset >= threshold)
    idx = int(strong[0]) if strong.size else int(np.argmax(onset))
    return float(times[idx])


def detect_drop(y: np.ndarray, sr: int) -> float:
    onset_env = librosa.onset.onset_strength(y=y, sr=sr, aggregate=np.median)
    times = librosa.times_like(onset_env, sr=sr)
    if onset_env.size == 0:
        return 0.0
    mask = times > 15.0
    if not np.any(mask):
        return float(times[int(np.argmax(onset_env))])
    idx = int(np.argmax(onset_env[mask]))
    return float(times[mask][idx])


def _detect_second_drop(y: np.ndarray, sr: int, *, first_drop: float, min_gap_s: float, anchor_s: float, beat_s: float) -> float | None:
    onset_env = librosa.onset.onset_strength(y=y, sr=sr, aggregate=np.median)
    times = librosa.times_like(onset_env, sr=sr)
    if onset_env.size == 0:
        return None
    mask = times >= (first_drop + max(beat_s * 8.0, min_gap_s))
    if not np.any(mask):
        return None
    later_strength = onset_env[mask]
    later_times = times[mask]
    threshold = float(np.percentile(later_strength, 85))
    strong = np.flatnonzero(later_strength >= threshold)
    if strong.size == 0:
        idx = int(np.argmax(later_strength))
    else:
        idx = int(strong[0])
    candidate = float(later_times[idx])
    if candidate <= first_drop + min_gap_s:
        return None
    return _quantize_to_grid(candidate, anchor_s, beat_s)


def _build_loop(name: str, num: int, start_s: float, bars: int, bpm: float, anchors: CueAnchors) -> dict | None:
    length_s = _bars_to_seconds(bars, bpm)
    if length_s <= anchors.beat_s:
        return None
    start = _quantize_to_grid(start_s, anchors.first_downbeat, anchors.beat_s)
    start = _clamp_loop_start(start, length_s, anchors.duration_s)
    end = min(anchors.duration_s, start + length_s)
    if end <= start + 1e-6:
        return None
    return {
        "name": name,
        "type": 4,
        "num": num,
        "start": start,
        "end": end,
    }


def _build_point(name: str, num: int, start_s: float, anchors: CueAnchors) -> dict:
    point = _quantize_to_grid(start_s, anchors.first_downbeat, anchors.beat_s)
    point = max(0.0, min(point, anchors.duration_s))
    return {
        "name": name,
        "type": 0,
        "num": num,
        "start": point,
        "end": point,
    }


def _build_from_template_entries(
    *,
    anchors: CueAnchors,
    bpm: float,
    template: CueTemplate,
    entries: tuple[CueTemplateEntry, ...],
) -> list[dict]:
    anchor_map = {
        "first_downbeat": anchors.first_downbeat,
        "later_mix_in": anchors.hot_b_start,
        "break_start": anchors.break_start,
        "first_drop": anchors.first_drop,
        "second_drop": anchors.second_drop,
        "mix_out": anchors.mix_out_start,
        "end_guard": anchors.end_guard_start,
    }

    cues: list[dict] = []
    for entry in entries:
        anchor = anchor_map.get(entry.anchor)
        if anchor is None:
            continue

        if entry.kind == "memory_point":
            cues.append(_build_point(entry.name, -1, anchor, anchors))
            continue

        if entry.kind == "hot_point":
            slot = entry.slot if entry.slot is not None else template.slot_for(entry.cue_id, -1)
            cues.append(_build_point(entry.name, slot, anchor, anchors))
            continue

        if entry.kind == "hot_loop":
            slot = entry.slot if entry.slot is not None else template.slot_for(entry.cue_id, -1)
            bars = entry.bars if entry.bars is not None else template.bars_for(entry.cue_id, 16)
            cue = _build_loop(entry.name, slot, anchor, bars, bpm, anchors)
            if cue is not None:
                cues.append(cue)

    cues.sort(key=lambda cue: (float(cue.get("start", 0.0)), int(cue.get("num", -1)), cue.get("name", "")))
    return cues


def build_cues(
    *,
    duration_s: float,
    bpm: float,
    first_downbeat_t: float,
    drop_t: float,
    second_drop_t: float | None = None,
    break_start_t: float | None = None,
    later_mix_in_t: float | None = None,
    mix_out_t: float | None = None,
    end_guard_t: float | None = None,
    template: CueTemplate | None = None,
    template_entries: list[CueTemplateEntry] | tuple[CueTemplateEntry, ...] | None = None,
) -> list[dict]:
    template = template or load_cue_template()
    beat_s = max(0.1, 60.0 / max(float(bpm), 1.0))

    break_start_t = break_start_t if break_start_t is not None else max(
        first_downbeat_t,
        drop_t - _bars_to_seconds(template.hot_c_bars, bpm),
    )
    later_mix_in_t = later_mix_in_t if later_mix_in_t is not None else (
        first_downbeat_t + _bars_to_seconds(template.mix_in_gap_bars, bpm)
    )
    mix_out_t = mix_out_t if mix_out_t is not None else max(
        drop_t + _bars_to_seconds(16, bpm),
        duration_s - _bars_to_seconds(template.mix_out_lead_bars, bpm),
    )
    end_guard_t = end_guard_t if end_guard_t is not None else (
        duration_s - _bars_to_seconds(template.end_guard_lead_bars, bpm)
    )

    anchors = CueAnchors(
        duration_s=float(duration_s),
        beat_s=beat_s,
        first_downbeat=_quantize_to_grid(first_downbeat_t, 0.0, beat_s),
        first_drop=_quantize_to_grid(drop_t, first_downbeat_t, beat_s),
        second_drop=(
            _quantize_to_grid(second_drop_t, first_downbeat_t, beat_s)
            if second_drop_t is not None
            else None
        ),
        break_start=_quantize_to_grid(break_start_t, first_downbeat_t, beat_s),
        hot_b_start=_quantize_to_grid(later_mix_in_t, first_downbeat_t, beat_s),
        mix_out_start=_quantize_to_grid(max(first_downbeat_t, mix_out_t), first_downbeat_t, beat_s),
        end_guard_start=_quantize_to_grid(max(first_downbeat_t, end_guard_t), first_downbeat_t, beat_s),
    )
    entries = tuple(template_entries) if template_entries is not None else template.entries
    return _build_from_template_entries(
        anchors=anchors,
        bpm=bpm,
        template=template,
        entries=entries,
    )


def estimate_cue_anchors(y: np.ndarray, sr: int, bpm: float, *, template: CueTemplate) -> CueAnchors:
    duration_s = float(len(y) / sr) if sr > 0 else 0.0
    beat_s = max(0.1, 60.0 / max(float(bpm), 1.0))
    first_downbeat = _quantize_to_grid(_detect_first_downbeat(y, sr), 0.0, beat_s)
    first_drop = _quantize_to_grid(detect_drop(y, sr), first_downbeat, beat_s)

    break_start = max(
        first_downbeat,
        first_drop - _bars_to_seconds(template.hot_c_bars, bpm),
    )
    break_start = _quantize_to_grid(break_start, first_downbeat, beat_s)

    hot_b_start = first_downbeat + _bars_to_seconds(template.mix_in_gap_bars, bpm)
    latest_hot_b = max(first_downbeat, break_start - _bars_to_seconds(template.hot_b_bars, bpm))
    hot_b_start = min(hot_b_start, latest_hot_b)
    if hot_b_start <= first_downbeat:
        hot_b_start = first_downbeat + _bars_to_seconds(template.hot_a_bars, bpm)
    hot_b_start = _quantize_to_grid(hot_b_start, first_downbeat, beat_s)

    mix_out_start = max(
        first_drop + _bars_to_seconds(16, bpm),
        duration_s - _bars_to_seconds(template.mix_out_lead_bars, bpm),
    )
    mix_out_start = _quantize_to_grid(max(first_downbeat, mix_out_start), first_downbeat, beat_s)

    end_guard_start = duration_s - _bars_to_seconds(template.end_guard_lead_bars, bpm)
    end_guard_start = _quantize_to_grid(max(first_downbeat, end_guard_start), first_downbeat, beat_s)

    second_drop = None
    if template.include_second_drop_memory:
        second_drop = _detect_second_drop(
            y,
            sr,
            first_drop=first_drop,
            min_gap_s=_bars_to_seconds(template.second_drop_bars_after_first, bpm),
            anchor_s=first_downbeat,
            beat_s=beat_s,
        )

    return CueAnchors(
        duration_s=duration_s,
        beat_s=beat_s,
        first_downbeat=first_downbeat,
        first_drop=first_drop,
        second_drop=second_drop,
        break_start=break_start,
        hot_b_start=hot_b_start,
        mix_out_start=mix_out_start,
        end_guard_start=end_guard_start,
    )


def propose_cues(
    y: np.ndarray,
    sr: int,
    bpm: float,
    *,
    cue_profile: str | None = None,
    template: CueTemplate | None = None,
) -> list[dict]:
    template = template or load_cue_template(cue_profile)
    anchors = estimate_cue_anchors(y, sr, bpm, template=template)
    return _build_from_template_entries(
        anchors=anchors,
        bpm=bpm,
        template=template,
        entries=template.entries,
    )
