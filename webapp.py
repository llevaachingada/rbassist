from __future__ import annotations

import json
import pathlib
import numpy as np
import streamlit as st
from contextlib import contextmanager

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
import tempfile, os
import pandas as pd

from rbassist.utils import walk_audio, load_meta, tempo_match, camelot_relation
from rbassist.embed import build_embeddings
from rbassist.analyze import analyze_bpm_key
from rbassist.export_xml import write_rekordbox_xml
from rbassist.recommend import IDX
from rbassist.prefs import set_folder_mode
from rbassist.playlists import make_intelligent_playlist


st.set_page_config(page_title="rbassist", layout="wide")


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


st.title("rbassist — Streamlit UI (open-source)")
with st.sidebar:
    st.markdown("### Workspace")
    root = st.text_input("Audio folder", value=str(pathlib.Path.home()))
    duration = st.number_input("Embed slice (sec)", 10, 180, 60)
    only_new = st.checkbox("Only new/changed", value=True)
    limit = st.number_input("Max files this run (0 = all)", 0, 10000, 0)
    st.divider()
    xml_path = st.text_input("Rekordbox XML output", value="rbassist.xml")
    st.divider()
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
                            import shutil
                            if shutil.which("demucs") is None:
                                st.warning("Demucs not found—stems will be skipped until installed.")
                        st.success("Saved. New scans will honor this mode.")
                        st.session_state.show_add_modal = False
                        st.experimental_rerun()


col1, col2, col3, col4 = st.columns(4)

with col1:
    if st.button("Embed (incremental)"):
        files = list_audio(root)
        if limit and limit > 0:
            files = files[: int(limit)]
        with st.status("Embedding…", expanded=True) as status:
            st.write(f"Found {len(files)} files")
            build_embeddings(files, duration_s=int(duration))
            status.update(label="Embeddings complete", state="complete")

with col2:
    if st.button("Analyze BPM/Key"):
        files = list_audio(root)
        if limit and limit > 0:
            files = files[: int(limit)]
        with st.status("Analyzing BPM/Key…", expanded=True) as status:
            analyze_bpm_key(files, duration_s=60, only_new=True)
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
        with st.status("Building index…", expanded=True) as status:
            build_index()
            status.update(label="Index complete", state="complete")

with col4:
    if st.button("Export Rekordbox XML"):
        meta = load_meta()
        with st.status("Writing XML…", expanded=True) as status:
            write_rekordbox_xml(meta, out_path=xml_path, playlist_name="rbassist export")
            status.update(label=f"Wrote {xml_path}", state="complete")


st.markdown("---")

seed = st.text_input("Seed path or 'Artist - Title' substring")
ktop = st.slider("Top N", 5, 50, 20)

if st.button("Recommend") and seed:
    meta = load_meta()["tracks"]
    paths = _load_paths()
    matches = [
        p
        for p in paths
        if seed.lower() in p.lower()
        or seed.lower()
        in (meta.get(p, {}).get("artist", "") + " - " + meta.get(p, {}).get("title", "")).lower()
    ]
    if not matches:
        st.warning("Seed not found in index")
    else:
        seed_path = matches[0]
        seed_info = meta.get(seed_path, {})
        vec = np.load(seed_info["embedding"]) if seed_info.get("embedding") else None
        if vec is None:
            st.error("Seed has no embedding. Run Embed first.")
        else:
            labels, dists = _knn(vec, k=ktop + 1)
            rows = []
            seed_bpm = seed_info.get("bpm")
            seed_key = seed_info.get("key")
            for lab, dist in zip(labels, dists):
                path = paths[lab]
                if path == seed_path:
                    continue
                info = meta.get(path, {})
                ok_key, rule = camelot_relation(seed_key, info.get("key"))
                if not ok_key:
                    continue
                if not tempo_match(seed_bpm, info.get("bpm"), pct=6.0, allow_doubletime=True):
                    continue
                rows.append(
                    {
                        "Track": path,
                        "Artist": info.get("artist", ""),
                        "Title": info.get("title", ""),
                        "BPM": info.get("bpm", "-"),
                        "Key": info.get("key", "-"),
                        "KeyRule": rule,
                        "Dist": round(float(dist), 3),
                    }
                )
                if len(rows) >= ktop:
                    break
            if not rows:
                st.info("No matches after filters.")
            else:
                st.dataframe(rows, use_container_width=True)


st.markdown("---")
st.subheader("Intelligent Playlists")
name = st.text_input("Playlist name", value="Intelligent")
mytag = st.text_input("MyTag (optional)")
rating = st.slider("Minimum rating", 0, 5, 4)
since = st.text_input("Since (YYYY-MM-DD)", value="")
until = st.text_input("Until (YYYY-MM-DD)", value="")
out_path2 = st.text_input("Output XML", value="rb_intelligent.xml")
if st.button("Export Intelligent XML"):
    make_intelligent_playlist(
        out_path2,
        name=name,
        my_tag=(mytag or None),
        rating_min=rating if rating > 0 else None,
        since=(since or None),
        until=(until or None),
    )
    st.success(f"Wrote {out_path2}")
    try:
        with open(out_path2, "rb") as f:
            st.download_button("Download XML", data=f, file_name=out_path2, mime="application/xml")
    except Exception:
        pass

st.markdown("---")
st.subheader("Tools")

if st.button("Scan for duplicates"):
    from rbassist.utils import load_meta
    from rbassist.duplicates import find_duplicates, cdj_warnings
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

st.divider()
st.subheader("Folders & Modes")
from rbassist.prefs import load_prefs, save_prefs
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

st.divider()
st.subheader("Mirror Online CSV → Rekordbox XML")
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
        st.success(f"Matched {len(sub['tracks'])} local tracks → {out_csv_xml}")
        try:
            with open(out_csv_xml, "rb") as f:
                st.download_button("Download XML (CSV Mirror)", data=f, file_name=out_csv_xml, mime="application/xml")
        except Exception:
            pass

st.divider()
st.subheader("Bandcamp CSV Import → Meta Tags")
bc_csv = st.file_uploader("Bandcamp CSV", type=["csv"], key="bc_csv_tools")
mapping_yml = st.file_uploader("Mapping YAML", type=["yml","yaml"], key="bc_map_tools")
if st.button("Import Bandcamp CSV", disabled=(bc_csv is None or mapping_yml is None)):
    import subprocess, sys
    if bc_csv is None or mapping_yml is None:
        st.warning("Upload both CSV and mapping YAML.")
    else:
        with tempfile.TemporaryDirectory() as td:
            csv_path = os.path.join(td, "bandcamp.csv")
            map_path = os.path.join(td, "mapping.yml")
            open(csv_path, "wb").write(bc_csv.getvalue())
            open(map_path, "wb").write(mapping_yml.getvalue())
            try:
                cp = subprocess.run([sys.executable, "-m", "rbassist.cli", "bandcamp-import", csv_path, map_path], capture_output=True, text=True, check=True)
                st.success("Bandcamp import complete.")
                st.code(cp.stdout or "ok", language="bash")
            except subprocess.CalledProcessError as e:
                st.error("Bandcamp import failed.")
                st.code(e.stderr or str(e), language="bash")
