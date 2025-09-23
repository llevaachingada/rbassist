from __future__ import annotations
import json, pathlib, numpy as np
from typing import List, Tuple
import hnswlib
from rich.table import Table
from rich.console import Console
from .utils import EMB, IDX, META, console, camelot_compat, tempo_match, load_meta

DIM = 1024

class HnswIndex:
    def __init__(self, dim: int = DIM, space: str = "cosine"):
        self.index = hnswlib.Index(space=space, dim=dim)
        self._built = False

    def build(self, vectors: List[np.ndarray], labels: List[int], M: int = 32, efC: int = 200):
        self.index.init_index(max_elements=len(vectors), ef_construction=efC, M=M)
        self.index.add_items(np.vstack(vectors), np.array(labels))
        self.index.set_ef(64)
        self._built = True

    def save(self, path: str):
        self.index.save_index(path)

    def load(self, path: str):
        self.index.load_index(path)
        self._built = True


def build_index() -> None:
    meta = load_meta()
    vectors, labels, paths = [], [], []
    for i, (path, info) in enumerate(meta.get("tracks", {}).items()):
        epath = info.get("embedding")
        if not epath or not pathlib.Path(epath).exists():
            continue
        vectors.append(np.load(epath))
        labels.append(i)
        paths.append(path)
    if not vectors:
        console.print("[yellow]No embeddings found. Run: rbassist embed build ...")
        return
    idx = HnswIndex(dim=len(vectors[0]))
    idx.build(vectors, labels)
    (IDX / "hnsw.idx").parent.mkdir(parents=True, exist_ok=True)
    idx.save(str(IDX / "hnsw.idx"))
    json.dump(paths, open(IDX / "paths.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    console.print(f"[green]Indexed {len(paths)} tracks → {IDX / 'hnsw.idx'}")


def recommend(seed: str, top: int = 25, tempo_pct: float = 6.0, allow_doubletime: bool = True, camelot_neighbors: bool = True):
    idxfile = IDX / "hnsw.idx"
    paths_map = json.load(open(IDX / "paths.json", "r", encoding="utf-8"))
    meta = load_meta()["tracks"]
    # resolve seed path
    matches = [p for p in paths_map if seed.lower() in p.lower() or seed.lower() in (meta.get(p,{}).get("artist","") + " - " + meta.get(p,{}).get("title","" )).lower()]
    if not matches:
        console.print(f"[red]Seed not found: {seed}")
        return
    seed_path = matches[0]
    seed_vec = np.load(meta[seed_path]["embedding"])  # (1024,)

    # query
    index = hnswlib.Index(space="cosine", dim=seed_vec.shape[0])
    index.load_index(str(idxfile))
    index.set_ef(64)
    labels, dists = index.knn_query(seed_vec, k=top+1)
    labels, dists = labels[0].tolist(), dists[0].tolist()

    # Build table
    table = Table(title=f"Recommendations for {seed_path}")
    table.add_column("Rank", justify="right")
    table.add_column("Track")
    table.add_column("Artist")
    table.add_column("Title")
    table.add_column("Dist")

    rank = 1
    for label, dist in zip(labels, dists):
        path = paths_map[label]
        if path == seed_path:  # skip self
            continue
        info = meta.get(path, {})
        # Simple filters (if bpm/key exist in meta)
        seed_info = meta.get(seed_path, {})
        if camelot_neighbors and not camelot_compat(seed_info.get("key"), info.get("key")):
            continue
        if not tempo_match(seed_info.get("bpm"), info.get("bpm"), pct=tempo_pct, allow_doubletime=allow_doubletime):
            continue
        table.add_row(str(rank), path, info.get("artist",""), info.get("title",""), f"{dist:.3f}")
        rank += 1
        if rank > top:
            break
    console.print(table)
