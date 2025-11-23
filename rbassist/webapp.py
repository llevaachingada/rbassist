from __future__ import annotations

import json
import pathlib
from contextlib import contextmanager
from datetime import datetime
from typing import Dict, List, Tuple, Optional

import numpy as np
import streamlit as st

# Provide a working modal API:
# - Prefer streamlit-modal if available.
# - Fallback to an expander-based pseudo-modal otherwise.
try:  # streamlit-modal path
    from streamlit_modal import Modal  # type: ignore

    @contextmanager
    def _rbassist_modal(title: str):
        m = Modal(title, key=f"modal_{title}")
        m.open()
        if m.is_open():
            with m.container():
                yield

    if not hasattr(st, "modal"):
        st.modal = _rbassist_modal  # type: ignore[attr-defined]
except Exception:
    @contextmanager
    def _fake_modal(title: str):
        with st.expander(title, expanded=True):
            yield

    if not hasattr(st, "modal"):
        st.modal = _fake_modal  # type: ignore[attr-defined]
import hnswlib
import io
import os, shutil, tempfile
import pandas as pd

from rbassist.utils import walk_audio, load_meta, save_meta, tempo_match, camelot_relation
from rbassist.embed import build_embeddings
from rbassist.analyze import analyze_bpm_key
from rbassist.export_xml import write_rekordbox_xml
from rbassist.recommend import IDX
from rbassist.prefs import set_folder_mode, load_prefs, save_prefs
from rbassist.playlists import make_intelligent_playlist, filter_tracks
from rbassist.tagstore import (
    available_tags,
    set_available_tags,
    set_track_tags,
    track_tags,
    sync_meta_from_config,
    bulk_set_track_tags,
)
from rbassist.stems import STEMS, list_cache, clear_cache, have_demucs
from rbassist.duplicates import find_duplicates, cdj_warnings, stage_duplicates
from rbassist.playlist_presets import load_presets, upsert_preset, delete_preset
from rbassist.tag_model import learn_tag_profiles, suggest_tags_for_tracks, evaluate_existing_tags

try:
    from rbassist.features import bass_similarity
except Exception:
    bass_similarity = None  # type: ignore[assignment]


st.set_page_config(page_title="rbassist", layout="wide")
sync_meta_from_config()


@st.cache_data(show_spinner=False)
def list_audio(root: str) -> list[str]:
    return walk_audio([root])


def _load_paths() -> list[str]:
    p = IDX / "paths.json"
    if p.exists():
        return json.load(open(p, "r", encoding="utf-8"))
    return []


def _knn(vec: np.ndarray, k: int = 50):
    index = hnswlib.Index(space="cosine", dim=vec.shape[0])
    index.load_index(str(IDX / "hnsw.idx"))
    index.set_ef(64)
    labels, dists = index.knn_query(vec, k=k)
    return labels[0].tolist(), dists[0].tolist()


@st.cache_data(show_spinner=False)
def track_dataframe() -> pd.DataFrame:
    meta = load_meta()
    rows = []
    for path, info in meta.get("tracks", {}).items():
        tags = info.get("mytags") or []
        suggestion = info.get("tag_suggestions") or {}
        rows.append(
            {
                "Path": path,
                "Artist": info.get("artist", ""),
                "Title": info.get("title", ""),
                "BPM": info.get("bpm", ""),
                "Key": info.get("key", ""),
                "Has Embedding": bool(info.get("embedding")),
                "Has Index": pathlib.Path(info.get("embedding", "")).exists() if info.get("embedding") else False,
                "Analyzed": bool(info.get("bpm")) or bool(info.get("key")),
                "MyTags": ", ".join(tags),
                "#Tags": len(tags),
                "Rating": info.get("rating", ""),
                "Last Suggestion": suggestion.get("generated", ""),
            }
        )
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("Path")
    return df


def _clear_track_dataframe_cache() -> None:
    track_dataframe.clear()  # type: ignore[attr-defined]


def _store_suggestions_meta(
    suggestions: Dict[str, List[Tuple[str, float, float]]],
    low_conf: Dict[str, List[Tuple[str, float, float]]],
    params: Dict[str, object],
) -> None:
    if not suggestions:
        return
    meta = load_meta()
    now = datetime.utcnow().isoformat()
    for path, tags in suggestions.items():
        info = meta["tracks"].setdefault(path, {})
        info["tag_suggestions"] = {
            "generated": now,
            "params": params,
            "candidates": [
                {"tag": tag, "score": float(score), "threshold": float(threshold)}
                for tag, score, threshold in tags
            ],
            "low_confidence": [
                {"tag": tag, "score": float(score), "threshold": float(threshold)}
                for tag, score, threshold in low_conf.get(path, [])
            ],
        }
    save_meta(meta)
    _clear_track_dataframe_cache()


RECOMMEND_PRESETS: Dict[str, Dict[str, float]] = {
    "Balanced": {"ann": 0.6, "samples": 0.25, "bass": 0.15},
    "Energy Boost": {"ann": 0.45, "samples": 0.35, "bass": 0.2},
    "Groove Lock": {"ann": 0.4, "samples": 0.2, "bass": 0.4},
    "Pure ANN": {"ann": 1.0, "samples": 0.0, "bass": 0.0},
}


st.title("rbassist - Streamlit UI (open-source)")
with st.sidebar:
    st.markdown("### Workspace")
    root = st.text_input("Audio folder", value=str(pathlib.Path.home()))
    duration = st.number_input("Embed slice (sec)", 10, 180, 60)
    only_new = st.checkbox("Only new/changed", value=True)
    limit = st.number_input("Max files this run (0 = all)", 0, 10000, 0)
    st.divider()
    xml_path = st.text_input("Rekordbox XML output", value="rbassist.xml")
    st.divider()
    do_cues = st.checkbox("Auto Hot/Memory Cues on Analyze", value=True)
    do_rg = st.checkbox("Write ReplayGain tags after Analyze", value=False)
    if "last_mode" not in st.session_state:
        st.session_state.last_mode = "baseline"
    if st.button("Add Folder"):
        st.session_state.show_add_modal = True
    if st.session_state.get("show_add_modal"):
        with st.modal("Add Music Folder"):
            folder = st.text_input("Folder path", value="")
            modes = ["baseline", "stems"]
            idx = 0 if st.session_state.last_mode == "baseline" else 1
            mode = st.radio("Analysis mode", modes, index=idx, horizontal=True)
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Cancel"):
                    st.session_state.show_add_modal = False
            with c2:
                if st.button("Add"):
                    p = pathlib.Path(folder).expanduser()
                    if not p.exists():
                        st.warning("Folder does not exist.")
                    else:
                        set_folder_mode(str(p), mode)
                        st.session_state.last_mode = mode
                        if mode == "stems":
                            if shutil.which("demucs") is None:
                                st.warning("Demucs not found - stems will be skipped until installed.")
                                st.markdown("[Install Demucs guide](https://github.com/facebookresearch/demucs) - or run: `pip install demucs`")
                        st.success("Saved. New scans will honor this mode.")
                        st.session_state.show_add_modal = False
                        st.rerun()

    if not have_demucs():
        st.info("Demucs not detected - stems mode will skip splitting until installed.")
        st.code("pip install demucs", language="bash")

col1, col2, col3, col4 = st.columns(4)

with col1:
    if st.button("Embed (incremental)"):
        files = list_audio(root)
        if limit and limit > 0:
            files = files[: int(limit)]
        with st.status("Embedding...", expanded=True) as status:
            total = len(files)
            st.write(f"Found {total} files")
            if total == 0:
                st.info("No audio files discovered under the selected folder.")
            else:
                progress = st.progress(0.0)
                current = st.empty()

                def _embed_progress(done: int, count: int, path: str) -> None:
                    frac = done / count if count else 1.0
                    progress.progress(min(max(frac, 0.0), 1.0))
                    current.write(f"[{done}/{count}] Embedding: {path}")

                build_embeddings(files, duration_s=int(duration), progress_callback=_embed_progress)
                progress.progress(1.0)
                current.write("Embedding complete.")
            status.update(label="Embeddings complete", state="complete")

with col2:
    if st.button("Analyze BPM/Key"):
        files = list_audio(root)
        if limit and limit > 0:
            files = files[: int(limit)]
        with st.status("Analyzing BPM/Key...", expanded=True) as status:
            total = len(files)
            st.write(f"Found {total} files")
            if total == 0:
                st.info("No audio files discovered under the selected folder.")
            else:
                progress = st.progress(0.0)
                current = st.empty()

                def _analyze_progress(done: int, count: int, path: str) -> None:
                    frac = done / count if count else 1.0
                    progress.progress(min(max(frac, 0.0), 1.0))
                    current.write(f"[{done}/{count}] Analyzing: {path}")

                analyze_bpm_key(
                    files,
                    duration_s=60,
                    only_new=True,
                    add_cues=do_cues,
                    progress_callback=_analyze_progress,
                )
                progress.progress(1.0)
                current.write("Analysis complete.")
            status.update(label="BPM/Key complete", state="complete")
        if do_rg:
            try:
                from rbassist.normalize import normalize_tag
                for p in files:
                    try:
                        _ = normalize_tag(p, target_lufs=-11.0)
                    except Exception:
                        pass
            except Exception:
                st.info("Install pyloudnorm to enable ReplayGain tagging: pip install rbassist[audio]")

with col3:
    if st.button("Build Index"):
        from rbassist.recommend import build_index
        with st.status("Building index...", expanded=True) as status:
            build_index()
            status.update(label="Index complete", state="complete")

with col4:
    if st.button("Export Rekordbox XML"):
        meta = load_meta()
        with st.status("Writing XML...", expanded=True) as status:
            write_rekordbox_xml(meta, out_path=xml_path, playlist_name="rbassist export")
            status.update(label=f"Wrote {xml_path}", state="complete")


st.markdown("---")
st.subheader("Recommendations")

if "weights" not in st.session_state:
    st.session_state["weights"] = RECOMMEND_PRESETS["Balanced"].copy()
if "weight_preset" not in st.session_state:
    st.session_state["weight_preset"] = "Balanced"

meta_tracks = load_meta()["tracks"]
indexed_paths = _load_paths()
seed_override = st.session_state.pop("recommend_seed_override", None)

with st.expander("Weight presets & sliders", expanded=True):
    preset_names = list(RECOMMEND_PRESETS.keys())
    preset_idx = preset_names.index(st.session_state["weight_preset"]) if st.session_state["weight_preset"] in preset_names else 0
    choice = st.selectbox("Preset", preset_names, index=preset_idx)
    if st.button("Apply preset", key="apply_weight_preset"):
        st.session_state["weights"] = RECOMMEND_PRESETS[choice].copy()
        st.session_state["weight_preset"] = choice
        st.rerun()
    current = st.session_state["weights"]
    ann_val = st.slider("ANN weight", 0.0, 1.0, current.get("ann", 0.0), 0.05)
    samples_val = st.slider("Samples weight", 0.0, 1.0, current.get("samples", 0.0), 0.05)
    bass_val = st.slider("Bass weight", 0.0, 1.0, current.get("bass", 0.0), 0.05)
    st.session_state["weights"] = {"ann": ann_val, "samples": samples_val, "bass": bass_val}

seed_options: List[Tuple[str, Optional[str]]] = [("(Select track)", None)]
for path in indexed_paths:
    info = meta_tracks.get(path, {})
    label_parts = [info.get("artist", ""), info.get("title", "")]
    label = " - ".join([part for part in label_parts if part]).strip()
    if not label:
        label = pathlib.Path(path).name
    seed_options.append((label, path))
default_index = next((idx for idx, opt in enumerate(seed_options) if opt[1] == seed_override), 0)
seed_choice_label, seed_choice_value = st.selectbox(
    "Pick from indexed tracks", seed_options, index=default_index, format_func=lambda opt: opt[0]
)
seed_input = st.text_input("...or search path / Artist - Title", value=seed_override or "")
if seed_choice_value:
    info = meta_tracks.get(seed_choice_value, {})
    st.caption(f"Selected seed: {info.get('artist', '')} - {info.get('title', '')}")

ktop = st.slider("Top N", 5, 50, 20)
tempo_pct = st.slider("Tempo tolerance (%)", 2, 10, 6)
allow_double = st.checkbox("Allow double/half-time matches", value=True)
require_camelot = st.checkbox("Camelot-compatible only", value=True)

if st.button("Recommend"):
    seed_value = seed_choice_value or seed_input.strip()
    if not seed_value:
        st.warning("Enter a seed or choose a track from the dropdown.")
    else:
        if seed_choice_value:
            seed_path = seed_choice_value
        else:
            matches = [
                p
                for p in indexed_paths
                if seed_value.lower() in p.lower()
                or seed_value.lower()
                in (meta_tracks.get(p, {}).get("artist", "") + " - " + meta_tracks.get(p, {}).get("title", "")).lower()
            ]
            if not matches:
                st.warning("Seed not found in index")
                seed_path = None
            else:
                seed_path = matches[0]
        if seed_path:
            seed_info = meta_tracks.get(seed_path, {})
            vec = np.load(seed_info["embedding"]) if seed_info.get("embedding") else None
            if vec is None:
                st.error("Seed has no embedding. Run Embed first.")
            else:
                labels, dists = _knn(vec, k=ktop + 1)
                rows = []
                seed_bpm = seed_info.get("bpm")
                seed_key = seed_info.get("key")
                seed_contour = np.array(
                    seed_info.get("features", {}).get("bass_contour", {}).get("contour", []),
                    dtype=float,
                )
                weights = st.session_state["weights"]
                weight_sum = sum(weights.values())
                for lab, dist in zip(labels, dists):
                    path = indexed_paths[lab]
                    if path == seed_path:
                        continue
                    info = meta_tracks.get(path, {})
                    if any(r["Track"] == path for r in rows):
                        continue
                    cand_key = info.get("key")
                    ok_key, rule = camelot_relation(seed_key, cand_key)
                    if require_camelot and not ok_key:
                        continue
                    if not tempo_match(seed_bpm, info.get("bpm"), pct=float(tempo_pct), allow_doubletime=allow_double):
                        continue
                    samples_score = float(info.get("features", {}).get("samples", 0.0))
                    bass_score = 0.0
                    if weights.get("bass") and bass_similarity is not None:
                        cand_contour = np.array(
                            info.get("features", {}).get("bass_contour", {}).get("contour", []),
                            dtype=float,
                        )
                        if seed_contour.size and cand_contour.size:
                            bass_score = float(bass_similarity(seed_contour, cand_contour))
                    ann_score = 1.0 - float(dist)
                    score = 0.0
                    if weights.get("ann"):
                        score += weights["ann"] * ann_score
                    if weights.get("samples"):
                        score += weights["samples"] * samples_score
                    if weights.get("bass"):
                        score += weights["bass"] * bass_score
                    if weight_sum > 0:
                        score /= weight_sum
                    rows.append(
                        {
                            "Track": path,
                            "Artist": info.get("artist", ""),
                            "Title": info.get("title", ""),
                            "BPM": info.get("bpm", "-"),
                            "Key": cand_key or "-",
                            "KeyRule": rule,
                            "Dist": round(float(dist), 3),
                            "Samples": round(samples_score, 3),
                            "BassSim": round(bass_score, 3),
                            "Score": round(score, 3),
                        }
                    )
                    if len(rows) >= ktop * 2:
                        break
                if not rows:
                    st.info("No matches after filters.")
                else:
                    if weight_sum > 0:
                        rows.sort(key=lambda r: r["Score"], reverse=True)
                    else:
                        rows.sort(key=lambda r: r["Dist"])
                    display = rows[:ktop]
                    st.dataframe(display, use_container_width=True)

with st.expander("Playlist browser & matching", expanded=False):
    col_pl_a, col_pl_b = st.columns([3, 2])
    with col_pl_a:
        tag_filter = st.selectbox("Filter by MyTag", ["(All)"] + available_tags(), key="playlist_tag_filter")
        rating_filter = st.slider("Minimum rating", 0, 5, 0, key="playlist_rating_filter")
        since_filter = st.text_input("Since (YYYY-MM-DD)", key="playlist_since")
        until_filter = st.text_input("Until (YYYY-MM-DD)", key="playlist_until")
        filtered = filter_tracks(
            my_tag=None if tag_filter == "(All)" else tag_filter,
            rating_min=rating_filter if rating_filter > 0 else None,
            since=since_filter or None,
            until=until_filter or None,
        )
        if filtered:
            table_rows = []
            for path in filtered:
                info = meta_tracks.get(path, {})
                table_rows.append(
                    {
                        "Path": path,
                        "Artist": info.get("artist", ""),
                        "Title": info.get("title", ""),
                        "BPM": info.get("bpm", ""),
                        "Key": info.get("key", ""),
                        "MyTags": ", ".join(info.get("mytags", [])),
                    }
                )
            playlist_df = pd.DataFrame(table_rows)
            st.dataframe(playlist_df, use_container_width=True, hide_index=True)
            selected_playlist_track = st.selectbox(
                "Choose track for matching",
                ["(Select)"] + [row["Path"] for row in table_rows],
                key="playlist_track_select",
            )
            if selected_playlist_track != "(Select)":
                st.caption("Click below to push this track into the matching panel.")
                if st.button("Use selected track as seed", key="playlist_use_seed"):
                    st.session_state["recommend_seed_override"] = selected_playlist_track
                    st.rerun()
        else:
            st.info("No tracks matched the current filters.")
    with col_pl_b:
        presets = load_presets()
        if presets:
            preset_names = ["(None)"] + [p["name"] for p in presets]
            preset_choice = st.selectbox("Preset preview", preset_names, key="playlist_preset_choice")
            if preset_choice != "(None)":
                preset = next((p for p in presets if p["name"] == preset_choice), None)
                if preset:
                    preset_tracks = filter_tracks(
                        my_tag=(preset.get("mytag") or None),
                        rating_min=preset.get("rating_min"),
                        since=preset.get("since") or None,
                        until=preset.get("until") or None,
                    )
                    st.write(f"{len(preset_tracks)} track(s) matched preset '{preset_choice}'.")
                    if preset_tracks:
                        preview_rows = []
                        for path in preset_tracks[:50]:
                            info = meta_tracks.get(path, {})
                            preview_rows.append(
                                {
                                    "Path": path,
                                    "Artist": info.get("artist", ""),
                                    "Title": info.get("title", ""),
                                    "MyTags": ", ".join(info.get("mytags", [])),
                                }
                            )
                        st.dataframe(pd.DataFrame(preview_rows), use_container_width=True, hide_index=True)
                        chosen = st.selectbox(
                            "Preset track to match",
                            ["(Select)"] + preset_tracks,
                            key="playlist_preset_track",
                        )
                        if chosen != "(Select)":
                            if st.button("Use preset track as seed", key="playlist_preset_use"):
                                st.session_state["recommend_seed_override"] = chosen
                                st.rerun()
        else:
            st.info("No playlist presets saved yet.")


st.markdown("---")
st.subheader("Intelligent Playlists")

playlist_defaults = {
    "pl_name": "Intelligent",
    "pl_mytag": "",
    "pl_rating": 4,
    "pl_since": "",
    "pl_until": "",
    "pl_output": "rb_intelligent.xml",
    "pl_preset_name": "New Preset",
    "pl_selected_preset": "(None)",
}
for key, val in playlist_defaults.items():
    st.session_state.setdefault(key, val)

presets = load_presets()
preset_choices = ["(None)"] + [p["name"] for p in presets]
if st.session_state["pl_selected_preset"] not in preset_choices:
    st.session_state["pl_selected_preset"] = "(None)"
selected_preset = st.selectbox("Preset", preset_choices, index=preset_choices.index(st.session_state["pl_selected_preset"]))

col_load, col_delete, col_batch = st.columns(3)
with col_load:
    if st.button("Load preset", disabled=selected_preset == "(None)"):
        preset = next((p for p in presets if p["name"] == selected_preset), None)
        if preset:
            st.session_state["pl_name"] = preset["name"]
            st.session_state["pl_mytag"] = preset.get("mytag", "")
            st.session_state["pl_rating"] = int(preset.get("rating_min", 0) or 0)
            st.session_state["pl_since"] = preset.get("since", "")
            st.session_state["pl_until"] = preset.get("until", "")
            st.session_state["pl_output"] = preset.get("output", f"{preset['name']}.xml")
            st.session_state["pl_preset_name"] = preset["name"]
            st.rerun()
with col_delete:
    if st.button("Delete preset", disabled=selected_preset == "(None)"):
        delete_preset(selected_preset)
        st.success(f"Deleted preset {selected_preset}")
        st.session_state["pl_selected_preset"] = "(None)"
        st.rerun()
with col_batch:
    if st.button("Export all presets", disabled=not presets):
        for preset in presets:
            make_intelligent_playlist(
                preset.get("output", f"{preset['name']}.xml"),
                name=preset.get("name", "Preset"),
                my_tag=(preset.get("mytag") or None),
                rating_min=int(preset.get("rating_min", 0) or 0) or None,
                since=(preset.get("since") or None),
                until=(preset.get("until") or None),
            )
        st.success(f"Exported {len(presets)} presets.")

name = st.text_input("Playlist name", key="pl_name")
mytag = st.text_input("MyTag (optional)", key="pl_mytag")
rating = st.slider("Minimum rating", 0, 5, st.session_state["pl_rating"], key="pl_rating")
since = st.text_input("Since (YYYY-MM-DD)", key="pl_since")
until = st.text_input("Until (YYYY-MM-DD)", key="pl_until")
out_path2 = st.text_input("Output XML", key="pl_output")

if st.button("Export Intelligent XML"):
    rating_opt = st.session_state["pl_rating"] if st.session_state["pl_rating"] > 0 else None
    make_intelligent_playlist(
        st.session_state["pl_output"],
        name=st.session_state["pl_name"],
        my_tag=(st.session_state["pl_mytag"] or None),
        rating_min=rating_opt,
        since=(st.session_state["pl_since"] or None),
        until=(st.session_state["pl_until"] or None),
    )
    st.success(f"Wrote {st.session_state['pl_output']}")
    try:
        with open(st.session_state["pl_output"], "rb") as f:
            st.download_button(
                "Download XML",
                data=f,
                file_name=st.session_state["pl_output"],
                mime="application/xml",
            )
    except Exception:
        pass

st.session_state.setdefault("pl_preset_name", st.session_state["pl_name"])
preset_name_input = st.text_input("Preset name", key="pl_preset_name")
if st.button("Save preset"):
    upsert_preset(
        {
            "name": preset_name_input or st.session_state["pl_name"],
            "output": st.session_state["pl_output"],
            "mytag": st.session_state["pl_mytag"],
            "rating_min": st.session_state["pl_rating"],
            "since": st.session_state["pl_since"],
            "until": st.session_state["pl_until"],
        }
    )
    st.success(f"Saved preset {preset_name_input or st.session_state['pl_name']}")
    st.session_state["pl_selected_preset"] = preset_name_input or st.session_state["pl_name"]
    st.rerun()

st.markdown("---")
st.subheader("Tools")

if st.button("Scan for duplicates"):
    meta = load_meta()
    pairs = find_duplicates(meta)
    rows = []
    for keep, lose in pairs:
        warns = "; ".join(cdj_warnings(keep))
        rows.append({"keep": keep, "remove": lose, "keep_warnings": warns})
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True)
    if not df.empty:
        csv_buf = io.StringIO()
        df.to_csv(csv_buf, index=False)
        st.download_button("Download duplicates.csv", data=csv_buf.getvalue(), file_name="duplicates.csv", mime="text/csv")
    else:
        st.info("No duplicate groups detected.")

st.markdown("#### Duplicate staging")
stage_dest = st.text_input("Staging folder", value=str(pathlib.Path("data/dup_stage")))
stage_move = st.checkbox("Move files instead of copy", value=False)
col_prev, col_stage = st.columns(2)
if col_prev.button("Preview staging plan"):
    preview = stage_duplicates(load_meta(), stage_dest, move=stage_move, dry_run=True)
    if preview:
        st.write(f"{len(preview)} files would be staged.")
        st.code("\n".join(f"{src} -> {dst}" for src, dst in preview[:10]), language="text")
        if len(preview) > 10:
            st.caption(f"...and {len(preview) - 10} more")
    else:
        st.info("No duplicates to stage.")
if col_stage.button("Stage duplicates now"):
    staged = stage_duplicates(load_meta(), stage_dest, move=stage_move, dry_run=False)
    if staged:
        action = "Moved" if stage_move else "Copied"
        st.success(f"{action} {len(staged)} files to {stage_dest}")
    else:
        st.info("No duplicates staged.")

with st.expander("Demucs cache & helpers", expanded=False):
    caches = list_cache()
    if caches:
        cache_df = pd.DataFrame(caches)
        st.dataframe(cache_df, use_container_width=True)
        selected_caches = st.multiselect("Caches to clear", [c["cache"] for c in caches])
        col_sel, col_all = st.columns(2)
        if col_sel.button("Clear selected caches", disabled=not selected_caches):
            removed = clear_cache(selected_caches)
            st.success(f"Cleared {removed} cache directories.")
            st.rerun()
        if col_all.button("Clear all caches", disabled=not caches):
            removed = clear_cache(None)
            st.success(f"Cleared {removed} cache directories.")
            st.rerun()
    else:
        st.info("No cached stems yet.")
    if not have_demucs():
        st.warning("Demucs is not installed. Use the command below to enable stems processing.")
        st.code("pip install demucs", language="bash")
    st.caption(f"Cache root: {STEMS}")

st.markdown("---")
st.subheader("Auto Tag Suggestions")

auto_state = st.session_state.setdefault("auto_tags", {})
col_params = st.columns(4)
with col_params[0]:
    auto_min_samples = st.number_input("Min tagged tracks", min_value=1, max_value=50, value=3, key="auto_min_samples")
with col_params[1]:
    auto_margin = st.slider("Margin (+)", 0.0, 0.5, 0.05, 0.01, key="auto_margin")
with col_params[2]:
    auto_top = st.number_input("Top tags per track", min_value=0, max_value=10, value=3, key="auto_top")
with col_params[3]:
    auto_prune = st.slider("Prune deficit", 0.0, 0.5, 0.10, 0.01, key="auto_prune_margin")

auto_include_tagged = st.checkbox("Include already tagged tracks", value=False, key="auto_include_tagged")
auto_filter_text = st.text_input("Path contains (optional)", value="", key="auto_filter_text")
available = available_tags()
auto_tag_filter = st.multiselect("Existing MyTag filter (optional)", available, key="auto_tag_filter")

if st.button("Run suggestions", key="auto_run_btn"):
    meta = load_meta()
    profiles = learn_tag_profiles(min_samples=int(auto_min_samples), meta=meta)
    if not profiles:
        st.warning("No tagged tracks available to learn from. Import or assign My Tags first.")
    else:
        track_targets = [
            path for path, info in meta["tracks"].items()
            if (auto_include_tagged or not info.get("mytags")) and info.get("embedding")
        ]
        if auto_filter_text:
            needle = auto_filter_text.lower()
            track_targets = [p for p in track_targets if needle in p.lower()]
        if auto_tag_filter:
            track_targets = [
                p for p in track_targets
                if any(tag in (meta["tracks"][p].get("mytags") or []) for tag in auto_tag_filter)
            ]
        suggestions = suggest_tags_for_tracks(
            track_targets,
            profiles,
            margin=float(auto_margin),
            top_k=int(auto_top),
            meta=meta,
        )
        existing_scores = evaluate_existing_tags(track_targets, profiles, meta=meta)
        low_conf: Dict[str, List[Tuple[str, float, float]]] = {}
        if auto_prune > 0.0:
            for path, rows in existing_scores.items():
                drops = [(tag, score, thr) for tag, score, thr in rows if score < (thr - auto_prune)]
                if drops:
                    low_conf[path] = drops
        auto_state["params"] = {
            "min_samples": int(auto_min_samples),
            "margin": float(auto_margin),
            "top": int(auto_top),
            "prune_margin": float(auto_prune),
            "include_tagged": auto_include_tagged,
            "filter_text": auto_filter_text,
            "tag_filter": auto_tag_filter,
            "count_targets": len(track_targets),
        }
        auto_state["suggestions"] = suggestions
        auto_state["low_confidence"] = low_conf
        _clear_track_dataframe_cache()
        if suggestions:
            st.success(f"Generated suggestions for {len(suggestions)} track(s).")
        else:
            st.info("No tag suggestions met the current thresholds.")

if auto_state.get("suggestions"):
    suggest_rows = []
    for path, rows in auto_state["suggestions"].items():
        for tag, score, threshold in rows:
            suggest_rows.append(
                {
                    "Apply": True,
                    "Path": path,
                    "Tag": tag,
                    "Score": round(float(score), 3),
                    "Threshold": round(float(threshold), 3),
                    "Delta": round(float(score - threshold), 3),
                }
            )
    st.markdown("**Suggested additions**")
    edited_suggestions = st.data_editor(
        pd.DataFrame(suggest_rows),
        use_container_width=True,
        key="auto_suggestion_editor",
        num_rows="fixed",
        hide_index=True,
    )
    drop_rows = []
    for path, rows in auto_state.get("low_confidence", {}).items():
        for tag, score, threshold in rows:
            drop_rows.append(
                {
                    "Drop": True,
                    "Path": path,
                    "Tag": tag,
                    "Score": round(float(score), 3),
                    "Threshold": round(float(threshold), 3),
                    "Deficit": round(float(threshold - score), 3),
                }
            )
    if drop_rows:
        st.markdown("**Low-confidence existing tags**")
        edited_drops = st.data_editor(
            pd.DataFrame(drop_rows),
            use_container_width=True,
            key="auto_drop_editor",
            num_rows="fixed",
            hide_index=True,
        )
    else:
        edited_drops = pd.DataFrame(columns=["Drop", "Path", "Tag"])

    col_auto_apply, col_auto_save, col_auto_clear = st.columns([2, 2, 1])
    if col_auto_apply.button("Apply selected tag updates", key="auto_apply_btn"):
        add_map: Dict[str, set[str]] = {}
        for row in edited_suggestions.to_dict("records"):
            if row.get("Apply"):
                add_map.setdefault(row["Path"], set()).add(row["Tag"])
        drop_map: Dict[str, set[str]] = {}
        for row in edited_drops.to_dict("records"):
            if row.get("Drop"):
                drop_map.setdefault(row["Path"], set()).add(row["Tag"])
        if not add_map and not drop_map:
            st.info("Nothing selected to apply.")
        else:
            meta_now = load_meta()
            updates: Dict[str, List[str]] = {}
            for path in set(list(add_map.keys()) + list(drop_map.keys())):
                info = meta_now["tracks"].get(path, {})
                current = set(info.get("mytags", []))
                updated = current | add_map.get(path, set())
                updated -= drop_map.get(path, set())
                if updated != current:
                    updates[path] = sorted(updated)
            if updates:
                bulk_set_track_tags(updates, only_existing=False)
                st.success(f"Updated My Tags for {len(updates)} track(s).")
                _clear_track_dataframe_cache()
            else:
                st.info("No changes required after evaluation.")

    if col_auto_save.button("Save snapshot to meta", key="auto_save_btn"):
        _store_suggestions_meta(
            auto_state.get("suggestions", {}),
            auto_state.get("low_confidence", {}),
            auto_state.get("params", {}),
        )
        st.success("Suggestion snapshot stored in metadata.")

    if col_auto_clear.button("Clear", key="auto_clear_btn"):
        st.session_state["auto_tags"] = {}
        st.rerun()

st.divider()
st.subheader("Track MyTags")
meta_all = load_meta()
track_choices = sorted(meta_all.get("tracks", {}).keys())
if track_choices:
    selected_track = st.selectbox("Track", track_choices, key="tag_track_select")
    current_tags = track_tags(selected_track)
    tag_options = available_tags()
    selected_tags = st.multiselect("Assign MyTags", tag_options, default=current_tags, key="tag_assign")
    new_tag_value = st.text_input("New tag (optional)", key="tag_new_value")
    col_tag_save, col_tag_clear = st.columns(2)
    if col_tag_save.button("Save tags"):
        combined = list(dict.fromkeys(selected_tags + ([new_tag_value.strip()] if new_tag_value.strip() else [])))
        if new_tag_value.strip():
            set_available_tags([new_tag_value.strip()])
        set_track_tags(selected_track, combined)
        st.success("Updated tags.")
        st.rerun()
    if col_tag_clear.button("Clear tags", disabled=not current_tags):
        set_track_tags(selected_track, [])
        st.success("Cleared tags.")
        st.rerun()
else:
    st.info("No tracks in metadata yet. Run Embed/Analyze to populate tracks.")

with st.expander("Available tag library", expanded=False):
    library_tags = available_tags()
    st.write(", ".join(library_tags) or "No tags defined.")
    add_tag = st.text_input("Add tag to library", key="tag_library_add")
    if st.button("Add library tag"):
        if add_tag.strip():
            set_available_tags([add_tag.strip()])
            st.success(f"Added tag '{add_tag.strip()}'.")
            st.rerun()

st.divider()
st.subheader("Library Browser")
library_df = track_dataframe()
if library_df.empty:
    st.info("No tracks indexed yet. Run embed/analyze to populate the library.")
else:
    col_metrics = st.columns(4)
    col_metrics[0].metric("Tracks", f"{len(library_df):,}")
    col_metrics[1].metric("Embeddings", f"{int(library_df['Has Embedding'].sum())}")
    col_metrics[2].metric("Analyzed", f"{int(library_df['Analyzed'].sum())}")
    col_metrics[3].metric("Tagged", f"{int((library_df['#Tags'] > 0).sum())}")

    search_text = st.text_input("Search path / artist / title", key="library_search")
    surf_tags = st.multiselect("Filter by MyTag", available_tags(), key="library_tag_filter")
    view_df = library_df.copy()
    if search_text:
        needle = search_text.lower()
        view_df = view_df[
            view_df["Path"].str.lower().str.contains(needle)
            | view_df["Artist"].str.lower().str.contains(needle)
            | view_df["Title"].str.lower().str.contains(needle)
        ]
    if surf_tags:
        view_df = view_df[
            view_df["MyTags"].apply(lambda t: all(tag in t.split(", ") for tag in surf_tags))
        ]
    st.dataframe(view_df, use_container_width=True, hide_index=True)

    detail_track = st.selectbox("Track details", ["(Select track)"] + view_df["Path"].tolist(), key="library_detail")
    if detail_track and detail_track != "(Select track)":
        meta_detail = load_meta()["tracks"].get(detail_track, {})
        st.json(meta_detail)

st.divider()
st.subheader("Folders & Modes")
prefs = load_prefs()
folders = prefs.get("folders", [])
with st.form("edit_folders"):
    new_rows = []
    for idx, row in enumerate(folders):
        c1, c2, c3 = st.columns([6, 3, 1])
        with c1:
            pth = st.text_input(f"Path {idx}", value=row.get("path", ""), key=f"fm_path_{idx}")
        with c2:
            mode = st.selectbox(f"Mode {idx}", ["baseline", "stems"], index=0 if row.get("mode")!="stems" else 1, key=f"fm_mode_{idx}")
        with c3:
            rm = st.checkbox("Remove", value=False, key=f"fm_rm_{idx}")
        if not rm and pth:
            new_rows.append({"path": pth, "mode": mode})
    add = st.checkbox("Add empty row")
    if add:
        new_rows.append({"path": "", "mode": "baseline"})
    submitted = st.form_submit_button("Save Folders & Modes")
    if submitted:
        prefs["folders"] = [r for r in new_rows if r.get("path")]  # drop empties
        save_prefs(prefs)
        st.success("Saved folder modes.")

bulk_options = [row.get("path") for row in folders if row.get("path")]
if bulk_options:
    st.markdown("#### Bulk mode update")
    bulk_selected = st.multiselect("Select folders", bulk_options, key="bulk_mode_select")
    col_bulk_a, col_bulk_b = st.columns(2)
    if col_bulk_a.button("Set to baseline", disabled=not bulk_selected):
        for path in bulk_selected:
            set_folder_mode(path, "baseline")
        st.success(f"Updated {len(bulk_selected)} folder(s) to baseline.")
        st.rerun()
    if col_bulk_b.button("Set to stems", disabled=not bulk_selected):
        for path in bulk_selected:
            set_folder_mode(path, "stems")
        st.success(f"Updated {len(bulk_selected)} folder(s) to stems.")
        st.rerun()

st.divider()
st.subheader("Mirror Online CSV -> Rekordbox XML")
csv_file = st.file_uploader("CSV with columns: artist, title", type=["csv"], key="csv_mirror")
name_csv = st.text_input("Playlist name (CSV Mirror)", value="Online Mirror")
out_csv_xml = st.text_input("Output XML (CSV Mirror)", value="rb_from_csv.xml")
if st.button("Mirror CSV to XML", disabled=csv_file is None):
    if csv_file is None:
        st.warning("Upload a CSV first.")
    else:
        from rbassist.sync_online import import_csv_playlist
        meta = load_meta()
        with tempfile.TemporaryDirectory() as td:
            csv_path = os.path.join(td, "online.csv")
            open(csv_path, "wb").write(csv_file.getvalue())
            paths = import_csv_playlist(csv_path)
            sub = {"tracks": {p: meta["tracks"][p] for p in paths if p in meta["tracks"]}}
            write_rekordbox_xml(sub, out_csv_xml, name_csv)
        st.success(f"Matched {len(sub['tracks'])} local tracks -> {out_csv_xml}")
        try:
            with open(out_csv_xml, "rb") as f:
                st.download_button("Download XML (CSV Mirror)", data=f, file_name=out_csv_xml, mime="application/xml")
        except Exception:
            pass

st.subheader("Bandcamp CSV Import -> Meta Tags")
bc_csv = st.file_uploader("Bandcamp CSV", type=["csv"], key="bc_csv_tools")
mapping_yml = st.file_uploader("Mapping YAML (optional)", type=["yml","yaml"], key="bc_map_tools")
if st.button("Import Bandcamp CSV", disabled=(bc_csv is None)):
    import subprocess, sys
    if bc_csv is None:
        st.warning("Upload a Bandcamp CSV first.")
    else:
        with tempfile.TemporaryDirectory() as td:
            csv_path = os.path.join(td, "bandcamp.csv")
            map_path = os.path.join(td, "mapping.yml")
            open(csv_path, "wb").write(bc_csv.getvalue())
            if mapping_yml is not None:
                open(map_path, "wb").write(mapping_yml.getvalue())
            else:
                default_map = "columns:\n  artist: artist\n  title: title\n  tags: tags\n  genre: genre\n  subgenre: subgenre\n"
                open(map_path, "w", encoding="utf-8").write(default_map)
            try:
                cp = subprocess.run([sys.executable, "-m", "rbassist.cli", "bandcamp-import", csv_path, map_path], capture_output=True, text=True, check=True)
                st.success("Bandcamp import complete.")
                st.code(cp.stdout or "ok", language="bash")
            except subprocess.CalledProcessError as e:
                st.error("Bandcamp import failed.")
                st.code(e.stderr or str(e), language="bash")
