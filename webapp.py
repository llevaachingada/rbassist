from __future__ import annotations
import json, pathlib, numpy as np
import streamlit as st
import hnswlib
from rbassist.utils import walk_audio, load_meta, tempo_match, camelot_relation
from rbassist.embed import build_embeddings
from rbassist.analyze import analyze_bpm_key
from rbassist.export_xml import write_rekordbox_xml
from rbassist.recommend import IDX

st.set_page_config(page_title="rbassist", layout="wide")

@st.cache_data(show_spinner=False)
def list_audio(root: str) -> list[str]:
    return walk_audio([root])


def _load_paths():
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
    # resolve seed
    matches = [p for p in paths if seed.lower() in p.lower() or seed.lower() in (meta.get(p,{}).get("artist","") + " - " + meta.get(p,{}).get("title","" )).lower()]
    if not matches:
        st.warning("Seed not found in index")
    else:
        seed_path = matches[0]
        seed_info = meta.get(seed_path, {})
        vec = np.load(seed_info["embedding"]) if seed_info.get("embedding") else None
        if vec is None:
            st.error("Seed has no embedding. Run Embed first.")
        else:
            labels, dists = _knn(vec, k=ktop+1)
            rows = []
            seed_bpm = seed_info.get("bpm")
            seed_key = seed_info.get("key")
            for lab, dist in zip(labels, dists):
                path = paths[lab]
                if path == seed_path:  # skip self
                    continue
                info = meta.get(path, {})
                ok_key, rule = camelot_relation(seed_key, info.get("key"))
                if not ok_key:
                    continue
                if not tempo_match(seed_bpm, info.get("bpm"), pct=6.0, allow_doubletime=True):
                    continue
                rows.append({
                    "Track": path,
                    "Artist": info.get("artist",""),
                    "Title": info.get("title",""),
                    "BPM": info.get("bpm","-"),
                    "Key": info.get("key","-"),
                    "KeyRule": rule,
                    "Dist": round(float(dist),3)
                })
                if len(rows) >= ktop:
                    break
            if not rows:
                st.info("No matches after filters.")
            else:
                st.dataframe(rows, use_container_width=True)