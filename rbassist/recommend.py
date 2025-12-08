from __future__ import annotations
import json, pathlib, numpy as np
from typing import List, Dict, Optional
import hnswlib
from rich.table import Table
from .utils import EMB, IDX, META, console, camelot_relation, tempo_match, load_meta
try:
    from .features import bass_similarity, rhythm_similarity
except Exception:
    bass_similarity = None  # type: ignore
    rhythm_similarity = None  # type: ignore

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


def load_embedding_safe(path: str, expected_dim: int | None = None) -> np.ndarray | None:
    """Load embedding with shape validation; returns None on failure."""
    try:
        arr = np.load(path)
    except Exception as e:
        console.print(f"[yellow]Skip embedding {path}: {e}")
        return None
    vec = np.asarray(arr).reshape(-1)
    if expected_dim is not None and vec.shape[0] != expected_dim:
        console.print(f"[yellow]Skip embedding {path}: expected dim {expected_dim}, got {vec.shape[0]}")
        return None
    return vec.astype(np.float32, copy=False)


def build_index(incremental: bool = False) -> None:
    meta = load_meta()
    idxfile = IDX / "hnsw.idx"
    mapfile = IDX / "paths.json"
    paths_map: list[str] = []
    index: hnswlib.Index | None = None
    expected_dim: int | None = None

    if incremental and idxfile.exists() and mapfile.exists():
        try:
            paths_map = json.load(open(mapfile, "r", encoding="utf-8"))
            index = hnswlib.Index(space="cosine", dim=DIM)
            index.load_index(str(idxfile))
            index.set_ef(64)
            ids = index.get_ids_list()
            if ids:
                sample = index.get_items(ids[:1])
                if sample is not None and sample.size:
                    expected_dim = int(sample.shape[1])
            if expected_dim is None:
                expected_dim = DIM
        except Exception as e:
            console.print(f"[yellow]Incremental load failed; rebuilding full: {e}")
            paths_map = []
            index = None
            incremental = False

    if not incremental:
        vectors, labels, paths = [], [], []
        for path, info in meta.get("tracks", {}).items():
            epath = info.get("embedding")
            if not epath or not pathlib.Path(epath).exists():
                continue
            vec = load_embedding_safe(epath, expected_dim)
            if vec is None:
                continue
            if expected_dim is None:
                expected_dim = vec.shape[0]
            labels.append(len(paths))
            paths.append(path)
            vectors.append(vec)
        if not vectors:
            console.print("[yellow]No embeddings found. Run: rbassist embed ...")
            return
        dim = expected_dim or DIM
        idx = HnswIndex(dim=dim)
        idx.build(vectors, labels)
        (IDX / "hnsw.idx").parent.mkdir(parents=True, exist_ok=True)
        idx.save(str(idxfile))
        json.dump(paths, open(mapfile, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        console.print(f"[green]Indexed {len(paths)} tracks -> {idxfile}")
        return

    # Incremental: add new embeddings to existing index
    label_lookup = {p: i for i, p in enumerate(paths_map)}
    new_vectors: list[np.ndarray] = []
    new_labels: list[int] = []
    new_paths: list[str] = []
    start_label = len(paths_map)

    for path, info in meta.get("tracks", {}).items():
        epath = info.get("embedding")
        if not epath or not pathlib.Path(epath).exists():
            continue
        if path in label_lookup:
            continue
        vec = load_embedding_safe(epath, expected_dim or DIM)
        if vec is None:
            continue
        new_vectors.append(vec)
        new_labels.append(start_label + len(new_vectors) - 1)
        new_paths.append(path)

    if not new_vectors:
        console.print(f"[green]Index up to date; {len(paths_map)} track(s).")
        return

    index.add_items(np.vstack(new_vectors), np.array(new_labels))
    paths_map.extend(new_paths)
    (IDX / "hnsw.idx").parent.mkdir(parents=True, exist_ok=True)
    index.save_index(str(idxfile))
    json.dump(paths_map, open(mapfile, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    console.print(f"[green]Added {len(new_vectors)} new embedding(s); total {len(paths_map)} track(s).")


def _tempo_note(seed_bpm: float | None, cand_bpm: float | None, pct: float, allow_doubletime: bool) -> str:
    if not seed_bpm or not cand_bpm:
        return ""
    ratio = cand_bpm / seed_bpm if seed_bpm else 1.0
    if abs(ratio - 1.0) <= (pct / 100.0):
        return "~"
    if allow_doubletime and 1.94 <= ratio <= 2.06:
        return "2x"
    if allow_doubletime and 0.47 <= ratio <= 0.53:
        return "1/2x"
    return ""


def recommend(
    seed: str,
    top: int = 25,
    tempo_pct: float = 6.0,
    allow_doubletime: bool = True,
    camelot_neighbors: bool = True,
    weights: Optional[Dict[str, float]] = None,
):
    idxfile = IDX / "hnsw.idx"
    paths_map = json.load(open(IDX / "paths.json", "r", encoding="utf-8"))
    meta_all = load_meta()["tracks"]

    seed_path = _resolve_seed(seed, paths_map, meta_all)
    if not seed_path:
        console.print(f"[red]Seed not found: {seed}")
        return
    seed_info = meta_all.get(seed_path, {})
    seed_vec = load_embedding_safe(seed_info["embedding"])  # (1024,)
    if seed_vec is None:
        console.print(f"[red]Seed embedding missing or invalid: {seed_info.get('embedding')}")
        return

    seed_bpm = seed_info.get("bpm")
    seed_key = seed_info.get("key")

    # query ANN
    index = hnswlib.Index(space="cosine", dim=seed_vec.shape[0])
    index.load_index(str(idxfile))
    index.set_ef(64)
    labels, dists = index.knn_query(seed_vec, k=top + 50)  # fetch a wider pool for re-rank
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

    # optional weighted re-rank
    weights = weights or {}
    w_ann = float(weights.get("ann", 0.0))
    w_samples = float(weights.get("samples", 0.0))
    w_bass = float(weights.get("bass", 0.0))
    w_rhythm = float(weights.get("rhythm", 0.0))

    # load seed features for bass and rhythm
    seed_c = np.array(seed_info.get("features", {}).get("bass_contour", {}).get("contour", []), dtype=float)
    seed_r = np.array(seed_info.get("features", {}).get("rhythm_contour", {}).get("contour", []), dtype=float)

    # collect candidates first
    cands = []
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
        score = 0.0
        # base ANN score: invert distance
        score += w_ann * float(1.0 - float(dist))
        # samples score from candidate features
        samp = float(info.get("features", {}).get("samples", 0.0))
        score += w_samples * samp
        # bass similarity
        if w_bass and bass_similarity is not None:
            c_cont = np.array(info.get("features", {}).get("bass_contour", {}).get("contour", []), dtype=float)
            if seed_c.size and c_cont.size:
                score += w_bass * float(bass_similarity(seed_c, c_cont))
        # rhythm similarity
        if w_rhythm and rhythm_similarity is not None:
            r_cont = np.array(info.get("features", {}).get("rhythm_contour", {}).get("contour", []), dtype=float)
            if seed_r.size and r_cont.size:
                score += w_rhythm * float(rhythm_similarity(seed_r, r_cont))
        cands.append((path, info, cand_bpm, cand_key, rule_name, dist, score))

    # sort: if any weight provided, sort by score desc; else by ANN distance asc
    if any([w_ann, w_samples, w_bass, w_rhythm]):
        cands.sort(key=lambda x: x[6], reverse=True)
    else:
        cands.sort(key=lambda x: x[5])

    rank = 1
    for path, info, cand_bpm, cand_key, rule_name, dist, _score in cands[:top]:
        table.add_row(
            str(rank),
            path,
            info.get("artist", ""),
            info.get("title", ""),
            f"{cand_bpm:.1f}" if isinstance(cand_bpm, (int, float)) else "-",
            cand_key or "-",
            rule_name,
            f"{dist:.3f}",
        )
        rank += 1

    console.print(table)


def _resolve_seed(seed: str, paths_map: list[str], meta_all: dict) -> str | None:
    matches = [
        p
        for p in paths_map
        if seed.lower() in p.lower()
        or seed.lower() in (meta_all.get(p, {}).get("artist", "") + " - " + meta_all.get(p, {}).get("title", "")).lower()
    ]
    return matches[0] if matches else None


def recommend_sequence(
    seeds: list[str],
    top: int = 25,
    pool: int = 100,
) -> None:
    if not seeds:
        console.print("[red]Provide at least one seed.")
        return
    idxfile = IDX / "hnsw.idx"
    paths_map = json.load(open(IDX / "paths.json", "r", encoding="utf-8"))
    meta_all = load_meta()["tracks"]

    resolved: list[str] = []
    vecs: list[np.ndarray] = []
    for seed in seeds:
        p = _resolve_seed(seed, paths_map, meta_all)
        if not p:
            console.print(f"[yellow]Seed not found: {seed}")
            continue
        info = meta_all.get(p, {})
        vec = load_embedding_safe(info.get("embedding"))
        if vec is None:
            console.print(f"[yellow]Seed has no embedding: {p}")
            continue
        resolved.append(p)
        vecs.append(vec)
    if not vecs:
        console.print("[red]No valid seeds with embeddings.")
        return
    mat = np.stack(vecs, axis=0)
    combined = mat.mean(axis=0)

    index = hnswlib.Index(space="cosine", dim=combined.shape[0])
    index.load_index(str(idxfile))
    index.set_ef(64)
    labels, dists = index.knn_query(combined, k=min(pool, len(paths_map)))
    labels, dists = labels[0].tolist(), dists[0].tolist()

    seen = set(resolved)
    rows = []
    for lab, dist in zip(labels, dists):
        path = paths_map[lab]
        if path in seen:
            continue
        info = meta_all.get(path, {})
        rows.append((path, info, dist))
        if len(rows) >= top:
            break

    table = Table(title=f"Sequence recommendations from seeds: {', '.join(resolved)}")
    table.add_column("Rank", justify="right")
    table.add_column("Track")
    table.add_column("Artist")
    table.add_column("Title")
    table.add_column("Dist", justify="right")

    for idx, (path, info, dist) in enumerate(rows, start=1):
        table.add_row(
            str(idx),
            path,
            info.get("artist", ""),
            info.get("title", ""),
            f"{dist:.3f}",
        )
    console.print(table)
