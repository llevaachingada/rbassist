from __future__ import annotations
import json, pathlib, numpy as np
from typing import List
import hnswlib
from rich.table import Table
from .utils import EMB, IDX, META, console, camelot_relation, tempo_match, load_meta

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
        console.print("[yellow]No embeddings found. Run: rbassist embed-build ...")
        return
    idx = HnswIndex(dim=len(vectors[0]))
    idx.build(vectors, labels)
    (IDX / "hnsw.idx").parent.mkdir(parents=True, exist_ok=True)
    idx.save(str(IDX / "hnsw.idx"))
    json.dump(paths, open(IDX / "paths.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    console.print(f"[green]Indexed {len(paths)} tracks → {IDX / 'hnsw.idx'}")


def _tempo_note(seed_bpm: float | None, cand_bpm: float | None, pct: float, allow_doubletime: bool) -> str:
    if not seed_bpm or not cand_bpm:
        return ""
    ratio = cand_bpm / seed_bpm if seed_bpm else 1.0
    if abs(ratio - 1.0) <= (pct / 100.0):
        return "≈"
    if allow_doubletime and 1.94 <= ratio <= 2.06:
        return "2×"
    if allow_doubletime and 0.47 <= ratio <= 0.53:
        return "½×"
    return ""


def recommend(seed: str, top: int = 25, tempo_pct: float = 6.0, allow_doubletime: bool = True, camelot_neighbors: bool = True):
    idxfile = IDX / "hnsw.idx"
    paths_map = json.load(open(IDX / "paths.json", "r", encoding="utf-8"))
    meta_all = load_meta()["tracks"]

    matches = [p for p in paths_map if seed.lower() in p.lower() or seed.lower() in (meta_all.get(p,{}).get("artist","") + " - " + meta_all.get(p,{}).get("title","" )).lower()]
    if not matches:
        console.print(f"[red]Seed not found: {seed}")
        return
    seed_path = matches[0]
    seed_info = meta_all.get(seed_path, {})
    seed_vec = np.load(seed_info["embedding"])  # (1024,)

    seed_bpm = seed_info.get("bpm")
    seed_key = seed_info.get("key")

    # query ANN
    index = hnswlib.Index(space="cosine", dim=seed_vec.shape[0])
    index.load_index(str(idxfile))
    index.set_ef(64)
    labels, dists = index.knn_query(seed_vec, k=top+1)
    labels, dists = labels[0].tolist(), dists[0].tolist()

    title = f"Recommendations for {seed_path}"
    if seed_bpm or seed_key:
        title += f"  (seed: {seed_bpm if seed_bpm else '-'} BPM | {seed_key if seed_key else '-'})"

    table = Table(title=title)
    table.add_column("Rank", justify="right")
    table.add_column("Track")
    table.add_column("Artist")
    table.add_column("Title")
    table.add_column("BPM", justify="right")
    table.add_column("Key")
    table.add_column("KeyRule")
    table.add_column("Dist", justify="right")

    rank = 1
    for label, dist in zip(labels, dists):
        path = paths_map[label]
        if path == seed_path:
            continue
        info = meta_all.get(path, {})
        cand_bpm = info.get("bpm")
        cand_key = info.get("key")

        ok_key, rule_name = camelot_relation(seed_key, cand_key) if camelot_neighbors else (True, "-")
        if camelot_neighbors and not ok_key:
            continue
        if not tempo_match(seed_bpm, cand_bpm, pct=tempo_pct, allow_doubletime=allow_doubletime):
            continue

        table.add_row(
            str(rank),
            path,
            info.get("artist",""),
            info.get("title",""),
            f"{cand_bpm:.1f}" if isinstance(cand_bpm, (int, float)) else "-",
            cand_key or "-",
            rule_name,
            f"{dist:.3f}",
        )
        rank += 1
        if rank > top:
            break

    console.print(table)