# rbassist Embedding Upgrade Plan
## Handoff Document for Implementation Agent

**Status:** Ready for implementation  
**Branch target:** `embedding-update`  
**Do not alter any existing behavior** until Phase 4 explicitly enables new paths via flags.  
**Author context:** This document was produced by analyzing two PhD-level research reports on audio embedding architectures and performing exhaustive static analysis of the rbassist codebase. Every code reference is verified against the live source.

---

## 0. Ground Truth: What the Code Does Today

Before writing a single line, internalize these facts about the live codebase. Every design decision in this plan flows from them.

### embed.py — the critical wasteful lines

```python
# embed.py:115-117 — MertEmbedder.encode_array
out = self.model(**{k: v.to(self.device) for k, v in inputs.items()}, output_hidden_states=True)
feats = out.hidden_states[-1].squeeze(0)   # [T, 1024]  ← only last of 25 layers used
vec   = feats.mean(dim=0).cpu().numpy().astype(np.float32)  # ← collapsed to one vector
```

```python
# embed.py:131-133 — MertEmbedder.encode_batch
out  = self.model(**{k: v.to(self.device) for k, v in inputs.items()}, output_hidden_states=True)
feats = out.hidden_states[-1]              # [B, T, 1024]  ← same waste, batch form
vecs  = feats.mean(dim=1).cpu().numpy().astype(np.float32)
```

```python
# embed.py:167-181 — embed_with_sampling / embed_with_default_windows
# All intro/core/late segment embeddings are averaged into ONE vector before saving.
return np.mean(np.stack(embs, axis=0), axis=0)
```

**These three patterns are the primary targets of this upgrade.**  
MERT-v1-330M has 25 hidden state layers. The model already computes all of them on every forward pass because `output_hidden_states=True` is set. You are paying for 25 layers and using 1.

### recommend.py — the hard contract

```python
# recommend.py:13
DIM = 1024
```

The HNSW index is built with `dim=1024`. Any new embedding stored as the primary key for HNSW **must remain 1024-d**. This is the only inviolable constraint.

### Current window budget

| Track duration | Windows produced by `_default_windows` |
|---|---|
| < 80s | Single window: full track |
| 80–139s | intro(10s) + core(40s) + late(10s) |
| ≥ 140s | intro(10s) + core(60s) + late(10s) |

Currently all three windows are averaged. We will store them separately.

### Meta.json embedding fields today

```json
{
  "embedding":        "data/embeddings/<hash>.npy",
  "embedding_mert":   "data/embeddings/<hash>_mert.npy",
  "embedding_timbre": "data/embeddings/<hash>_timbre.npy",
  "embedding_source": "baseline | stems:vocals | timbre(0.70/0.30)"
}
```

The `"embedding"` key is the canonical one read by `recommend.py` and `playlist_expand.py`. All new keys must be **additive**. Never remove or rename `"embedding"`.

### Scoring weights today (playlist_expand.py)

```python
ann_centroid      = 0.30
ann_seed_coverage = 0.20
group_match       = 0.16
bpm_match         = 0.12
key_match         = 0.08
tag_match         = 0.14
```

We will add `transition_score` and `layer_mix_score` as optional new components in Phase 3, gated by feature flags.

---

## 1. Research Basis

This plan is grounded in the following convergent findings from two independent deep-research reports and verification against the live codebase.

### 1.1 Layer hierarchy in self-supervised audio models

Self-supervised audio transformers (wav2vec 2.0, HuBERT, WavLM, MERT) exhibit a representational hierarchy across depth:

- **Early layers (1–8):** encode acoustic texture, timbral properties, fine spectral detail — analogous to auditory nerve / cochlear nucleus processing
- **Middle layers (9–16):** encode rhythmic modulation, beat-synchronous patterns, onset structure — analogous to primary auditory cortex
- **Late layers (17–24):** encode semantic music structure, harmonic trajectories, phrase-level organization — analogous to higher associative cortex

This is empirically demonstrated via encoding-model regression against fMRI auditory cortex responses, where different brain regions show peak predictivity at different model depths (see: Tûr et al. 2023, Vaidya et al. 2022, Kell & McDermott 2019 in broader SSL brain alignment literature).

**Consequence for rbassist:** Last-layer-only pooling discards the timbre and rhythm information that live in earlier layers. For DJ mixing — where groove and timbre compatibility matter as much as semantic "lane" — this is a material degradation.

The MERT-v1-330M model card explicitly states: *"Each layer performs differently and we suggest taking the time-reduced features from each layer and then fine-tune on the downstream task with a learnable weighted aggregation."*

### 1.2 Section asymmetry in DJ transitions

DJ mixing is inherently asymmetric: **an outro flows into an intro**, not into another outro. A single mean-pooled vector over intro+core+late cannot represent this directionality. The vector will be dominated by the core (60s vs 10s+10s), meaning intro/outro compatibility is near-invisible to the ANN retrieval stage.

The correct model: store `E_intro`, `E_core`, `E_late` separately and score transitions as:

```
S_transition(A → B) = cos(E_late(A), E_intro(B))
S_body(A, B)        = cos(E_core(A), E_core(B))
```

The ANN index continues to run on `E_core` for speed; section scores are applied in the rerank stage only.

### 1.3 Why not swap the backbone model first

Both research reports independently agree: **the highest ROI change is not a model swap**. The reasons:

1. MERT-v1-330M is already music-specialized (trained with RVQ-VAE acoustic teacher + CQT music teacher). General audio models (BEATs, AudioMAE) are not music-specialized by default.
2. Model swaps require re-indexing the entire library from scratch, which breaks existing user caches.
3. The information loss from single-layer single-window pooling is recoverable **with zero additional model compute** — the hidden states are already computed.
4. The benchmark harness does not yet exist. You cannot claim a model swap is better without a baseline measurement.

Backbone swaps (BEATs, AudioMAE as a structure branch, Mamba for long-context) are Phase 5+ work, gated on the benchmark harness validating Phase 1–3.

### 1.4 Contrastive learning as the training signal for layer mixing

When learning layer mixture weights, the correct training signal is **playlist co-occurrence**: tracks that appear together in DJ sets should be close in the mixed embedding space. This is a behavioral proxy that does not require human annotation — it is grounded in actual DJ practice.

InfoNCE (NT-Xent) contrastive loss with in-batch negatives:

```
L = -log( exp(sim(z_i, z_j) / τ) / Σ_k exp(sim(z_i, z_k) / τ) )
```

Where positives are (track A, track B) pairs from the same playlist, τ = 0.07, and negatives are all other tracks in the batch. This is the same objective used in SimCLR, MoCo, and CLAP.

**For rbassist specifically:** positives can be constructed from:
- Tracks in the same Rekordbox playlist
- Tracks sharing ≥2 user-assigned `mytags`
- Tracks within the same `group` field

This requires no external dataset — it is entirely library-native.

### 1.5 Two-stage retrieval is the correct architecture

The correct pattern for adding richer similarity without breaking ANN speed:

1. **Stage 1 (ANN, fast):** HNSW cosine on `E_core` → retrieve top-250 candidates
2. **Stage 2 (rerank, slower):** Apply section scores, layer-mix scores, existing feature scores (bass DTW, rhythm DTW, samples), Camelot/BPM gates

This is exactly what `playlist_expand.py` already does with its component scoring system. We are extending Stage 2, not replacing Stage 1.

---

## 2. Architecture Overview

### What we are building

```
Track Atlas (per track, stored in meta.json + .npy files)
├── embedding_core        (1024-d)  → primary HNSW index key [unchanged contract]
├── embedding_intro       (1024-d)  → section rerank: outro(A)→intro(B) scoring
├── embedding_late        (1024-d)  → section rerank: outro(A)→intro(B) scoring
├── embedding_layer_mix   (1024-d)  → optional: replaces embedding_core when flag enabled
└── (future) embedding_barwise  (N×256-d) → Phase 5: structure reranker
```

### Retrieval topology (after upgrade)

```
Seed Track A
    │
    ▼
E_core(A) ──► HNSW index ──► top-250 candidates (Stage 1, unchanged)
                                    │
                                    ▼
                           Per-candidate scoring (Stage 2):
                           ├── cos(E_late(A),  E_intro(B))  × w_transition
                           ├── cos(E_core(A),  E_core(B))   × w_ann_centroid
                           ├── bass_similarity(DTW)          × w_bass
                           ├── rhythm_similarity(DTW)        × w_rhythm
                           ├── bpm_match / key_match / tag_match (existing)
                           └── MMR diversity penalty (existing)
                                    │
                                    ▼
                           Final ranked recommendations
```

### Data flow for new embeddings

```
Audio file
    │
    ▼
librosa.load (mono, native sr)
    │
    ▼
_default_windows(y, sr) → [(intro_start, intro_end),
                            (core_start,  core_end),
                            (late_start,  late_end)]
    │
    ├──► MertEmbedder.encode_section_vectors(intro_seg)
    │        output_hidden_states=True
    │        extract layers: [4, 8, 12, 16, 20, 24]
    │        mean-pool each layer over time → 6 × 1024
    │        project each to 170-d → concat → 1020-d + 4-d pad → 1024-d
    │        OR: just use hidden_states[-1] mean for intro (Phase 1 uses this)
    │
    ├──► same for core_seg → E_core  (1024-d, last layer, backward-compatible)
    │
    └──► same for late_seg → E_late  (1024-d, last layer)
    │
    ▼
Save to data/embeddings/:
    <hash>_core.npy   (float16, 1024-d)
    <hash>_intro.npy  (float16, 1024-d)
    <hash>_late.npy   (float16, 1024-d)
    <hash>.npy        ← kept as-is for backward compat (= E_core)
    │
    ▼
Update meta.json per track:
    "embedding":       <hash>.npy           (unchanged)
    "embedding_core":  <hash>_core.npy      (new, same content as embedding)
    "embedding_intro": <hash>_intro.npy     (new)
    "embedding_late":  <hash>_late.npy      (new)
    "embedding_version": "v2_section"       (new, for cache invalidation)
```

---

## 3. Implementation Phases

Each phase is self-contained, testable, and backward-compatible with the previous. **Do not begin a phase until the previous phase passes its acceptance criteria.**

---

### Phase 1: Section-Aware Embedding Storage

**Goal:** Store intro/core/late as separate vectors. Zero change to recommendation behavior. Zero index rebuild required.

**Files to modify:**
- `rbassist/embed.py`

**Files to read first (do not modify):**
- `rbassist/recommend.py` — understand DIM=1024 contract
- `rbassist/utils.py` — understand EMB path, load_meta/save_meta
- `rbassist/sampling_profile.py` — understand _default_windows return format

#### 3.1.1 Add `encode_section_vectors` to `MertEmbedder`

Add a new method to `MertEmbedder`. Do **not** modify `encode_array` or `encode_batch` — those are called by existing paths.

```python
def encode_section_vectors(
    self,
    segments: list[tuple[np.ndarray, int]],   # [(intro_audio, sr), (core_audio, sr), (late_audio, sr)]
) -> list[np.ndarray]:
    """
    Encode each segment independently and return one 1024-d vector per segment.
    Uses the same last-hidden-state mean-pool as encode_array to stay comparable.
    Processes as a single batch for GPU efficiency.
    Returns list of float32 arrays, one per segment, shape (1024,).
    Falls back to serial encode_array if batch fails.
    """
```

Implementation notes:
- Resample each segment to SAMPLE_RATE (24000) before batching
- Use `encode_batch` internally — it already handles padding and batching
- Each output vector is the same computation as the current single embedding, just per-section
- Return order must match input order: [intro_vec, core_vec, late_vec]
- On any exception: fall back to `[self.encode_array(y, sr) for y, sr in segments]`

#### 3.1.2 Add `embed_with_section_vectors` function

Add a new module-level function below `embed_with_default_windows`:

```python
def embed_with_section_vectors(
    y: np.ndarray,
    sr: int,
    embedder: MertEmbedder,
    windows: list[tuple[float, float]] | None = None,
) -> dict[str, np.ndarray]:
    """
    Compute per-section embeddings for intro, core, and late windows.

    Returns a dict with keys: "intro", "core", "late", "combined".
    - "core" is identical to what embed_with_default_windows currently returns.
    - "combined" is mean([intro, core, late]) for backward compat.
    - All values are float32 (1024,).

    If fewer than 3 windows exist (short track), all keys point to the same vector.
    """
```

Implementation notes:
- Call `_default_windows(y, sr)` if `windows` is None
- If only 1 window: all four keys point to the same vector
- If 2 windows: intro=windows[0], core=windows[0], late=windows[1], combined=mean
- If 3+ windows: intro=windows[0], core=windows[1], late=windows[-1], combined=mean of all three
- Use `embedder.encode_section_vectors(segments)` for batched GPU efficiency
- The "combined" value must be numerically identical to the current `embed_with_default_windows` output for the same track, so that existing embeddings remain valid

#### 3.1.3 Modify `build_embeddings` to save section files

In `build_embeddings`, after computing the MERT embedding (currently saved as `embedding_mert.npy`), add a branch:

**New behavior when `section_embed=True` (new parameter, default False):**

```python
section_vecs = embed_with_section_vectors(y, sr, embedder, windows)

# Save section files
intro_path = EMB / f"{label}_intro.npy"
core_path  = EMB / f"{label}_core.npy"
late_path  = EMB / f"{label}_late.npy"

np.save(str(intro_path), section_vecs["intro"].astype(np.float16))
np.save(str(core_path),  section_vecs["core"].astype(np.float16))
np.save(str(late_path),  section_vecs["late"].astype(np.float16))

# Update meta — additive only, never overwrite "embedding"
meta["tracks"][path].update({
    "embedding_intro":   str(intro_path),
    "embedding_core":    str(core_path),
    "embedding_late":    str(late_path),
    "embedding_version": "v2_section",
})
# "embedding" key stays unchanged — still points to combined .npy
```

**New `build_embeddings` parameter:**
```python
section_embed: bool = False   # When True, also saves intro/core/late .npy files
```

Add `section_embed` to the CLI command in `cli.py` as `--section-embed / --no-section-embed`, default False.

#### 3.1.4 Acceptance criteria for Phase 1

- [ ] Running `rbassist embed --section-embed /path/to/track.mp3` produces three new `.npy` files per track: `*_intro.npy`, `*_core.npy`, `*_late.npy`
- [ ] `meta.json` gains `embedding_intro`, `embedding_core`, `embedding_late` keys per processed track
- [ ] The existing `embedding` key is unchanged
- [ ] `rbassist index` still works without modification
- [ ] `rbassist recommend` still works without modification  
- [ ] `embed_with_section_vectors(y, sr, embedder)["combined"]` is numerically within 1e-5 of `embed_with_default_windows(y, sr, embedder)` for the same track
- [ ] No existing `.npy` files are overwritten or deleted

---

### Phase 2: Section-Aware Reranking in Recommend and Playlist Expand

**Goal:** Use stored section vectors to compute `transition_score = cos(E_late(A), E_intro(B))` during rerank. Gated by a flag, off by default.

**Files to modify:**
- `rbassist/recommend.py`
- `rbassist/playlist_expand.py`

**Files to read first:**
- `rbassist/features.py` — understand how `bass_similarity` and `rhythm_similarity` are integrated; follow the same pattern
- `rbassist/utils.py` — `load_meta`, `camelot_relation`, `tempo_match`

#### 3.2.1 Add `load_section_embeddings` helper to `recommend.py`

```python
def load_section_embeddings(
    track_meta: dict,
    expected_dim: int = DIM,
) -> dict[str, np.ndarray | None]:
    """
    Load intro/core/late embeddings for a track from meta dict.
    Returns dict with keys "intro", "core", "late".
    Any missing or corrupt file returns None for that key.
    Never raises — failures are silent with a warning.
    """
```

Implementation notes:
- Read `track_meta.get("embedding_intro")`, `track_meta.get("embedding_core")`, `track_meta.get("embedding_late")`
- Call `load_embedding_safe(path, expected_dim)` for each — that function already handles None gracefully
- Return `{"intro": arr_or_none, "core": arr_or_none, "late": arr_or_none}`

#### 3.2.2 Add `transition_score` computation to `recommend`

In the `recommend` function, after computing the existing weighted score, add:

```python
if use_section_scores and seed_late is not None:
    cand_section = load_section_embeddings(cand_meta)
    if cand_section["intro"] is not None:
        t_score = float(np.dot(seed_late, cand_section["intro"]) /
                       (np.linalg.norm(seed_late) * np.linalg.norm(cand_section["intro"]) + 1e-9))
        score += weights.get("transition", 0.0) * t_score
```

Where `seed_late` is loaded from the seed track's `embedding_late` field if it exists.

**New parameter to `recommend`:**
```python
use_section_scores: bool = False
```

Default is False. When True and section embeddings exist, `transition_score` is added to the component score. When section embeddings are missing for seed or candidate, fall through silently to existing behavior.

#### 3.2.3 Add `transition_score` to playlist expansion scoring

In `playlist_expand.py`, the component scoring happens in `_compute_component_scores`. Add a new component:

```python
"transition_outro_to_intro": float   # cos(E_late(seed_centroid), E_intro(candidate))
```

For multi-seed expansion, the "seed outro" is computed as the mean of all seed `E_late` vectors (same pattern as centroid for `E_core`).

Add to `PlaylistExpansionWeights`:
```python
transition_outro_to_intro: float = 0.0   # Off by default; enable via presets or UI
```

The preset `"tight"` should set this to `0.18` when section embeddings are available.

**Diagnostic output:** when `transition_score` is computed, include it in the per-candidate diagnostics dict under key `"transition_score"`. The existing codebase already prints component scores in verbose mode — follow that pattern.

#### 3.2.4 Acceptance criteria for Phase 2

- [ ] `rbassist recommend "Track Name" --section-scores` uses transition scoring when section embeddings exist
- [ ] `rbassist recommend "Track Name"` (no flag) behaves identically to pre-Phase-2
- [ ] When a track has no section embeddings, `use_section_scores=True` silently falls back to original scoring
- [ ] `playlist-expand` with `--mode tight` and section-embedded tracks shows `transition_score` in diagnostics
- [ ] Transition score is in [0, 1] (it is a cosine similarity; clamp to avoid numerical issues)
- [ ] No index rebuild required

---

### Phase 3: Depth-Mixed Layer Pooling

**Goal:** Replace `hidden_states[-1]` mean-pool with a weighted combination of layers `{4, 8, 12, 16, 20, 24}`, producing a richer 1024-d vector that preserves hierarchical information. This is the most impactful single change.

**Files to modify:**
- `rbassist/embed.py`

**New file to create:**
- `rbassist/layer_mix.py`

**Files to read first:**
- `rbassist/embed.py` — full `MertEmbedder` class and `build_embeddings`

#### 3.3.1 Create `rbassist/layer_mix.py`

This module handles layer extraction, pooling, projection, and optional learned mixing. It is imported by `embed.py` but has no dependency on any other rbassist module.

```python
"""
Layer mixture module for MERT-v1-330M depth-mixed pooling.

Architecture:
  MERT forward pass (output_hidden_states=True)
    → hidden_states: tuple of 25 tensors, each [B, T, 1024]
    → extract layers at indices: [4, 8, 12, 16, 20, 24]
    → per-layer time-pool: mean over T → [B, 1024] each
    → project each to 170-d via small linear → [B, 170] each (6 × 170 = 1020)
    → pad last dim by 4 zeros → [B, 1024]
    → L2-normalize → final 1024-d vector

OR (simpler fixed-weight variant, no learned projection):
    → weighted sum of layer pools (fixed weights by default)
    → weights: [0.05, 0.10, 0.15, 0.20, 0.25, 0.25]  (earlier=timbre, later=semantic)
    → sum → [B, 1024]
    → L2-normalize
"""

LAYER_TAPS = [4, 8, 12, 16, 20, 24]   # indices into hidden_states tuple
LAYER_WEIGHTS_FIXED = [0.05, 0.10, 0.15, 0.20, 0.25, 0.25]  # must sum to 1.0
```

**Required functions:**

```python
def extract_layer_pools(
    hidden_states: tuple,        # from model output, len=25 for MERT-330M
    layer_taps: list[int] = LAYER_TAPS,
    pool: str = "mean",          # "mean" | "mean+var"
) -> np.ndarray:
    """
    Extract specified hidden state layers, pool over time, return as numpy.
    
    pool="mean":     returns array shape (len(layer_taps), 1024)
    pool="mean+var": returns array shape (len(layer_taps), 2048)  — mean concat var
    
    All computations on CPU after moving from GPU.
    """


def fixed_weight_mix(
    layer_pools: np.ndarray,          # (N_layers, 1024)
    weights: list[float] = LAYER_WEIGHTS_FIXED,
) -> np.ndarray:
    """
    Weighted sum of layer pools. Returns (1024,) float32.
    Weights are normalized internally to sum to 1.0.
    Output is L2-normalized.
    """


def learned_mix(
    layer_pools: np.ndarray,          # (N_layers, 1024)
    projection_weights: np.ndarray,   # (N_layers, 1024, out_dim)
    mix_weights: np.ndarray,          # (N_layers,) softmax weights
) -> np.ndarray:
    """
    Learned projection + mixture. Used when a trained mixing head is available.
    Returns (out_dim,) float32, L2-normalized.
    This function is called by MertEmbedder when layer_mix_weights_path is set.
    """
```

#### 3.3.2 Extend `MertEmbedder` with layer-mix support

Add two new optional constructor parameters:

```python
class MertEmbedder:
    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        device: str | None = None,
        layer_mix: bool = False,               # NEW: enable depth-mixed pooling
        layer_mix_weights_path: str | None = None,   # NEW: path to learned weights .npz
    ):
```

When `layer_mix=True`:
- `encode_array` and `encode_batch` call `extract_layer_pools` then `fixed_weight_mix` (or `learned_mix` if weights file provided)
- Output is still (1024,) float32 — contract unchanged
- The existing `hidden_states[-1]` path remains as the `layer_mix=False` default

**Do not modify the `layer_mix=False` code path in any way.**

#### 3.3.3 Add `embedding_layer_mix` field to `build_embeddings`

Add parameter:
```python
layer_mix: bool = False   # When True, also saves a layer-mixed embedding
```

When `layer_mix=True`:
- Instantiate a second `MertEmbedder(layer_mix=True)` — or reuse the same model if you pass the hidden states through
- Actually: more efficient to modify the embedder to return both last-layer and layer-mix from the same forward pass. See below.

**Efficient implementation — single forward pass:**

Add `encode_array_full` to `MertEmbedder`:

```python
def encode_array_full(
    self,
    y: np.ndarray,
    sr: int,
) -> dict[str, np.ndarray]:
    """
    Single forward pass returning both standard and layer-mixed embeddings.
    Keys: "standard" (1024,), "layer_mix" (1024,).
    Only runs the model once.
    """
```

This avoids paying for two forward passes when both outputs are needed. The standard vector is `hidden_states[-1].mean(dim=0)` and the layer-mix is `fixed_weight_mix(extract_layer_pools(hidden_states))`.

Save to meta:
```python
"embedding_layer_mix": str(layer_mix_path),   # data/embeddings/<hash>_layer_mix.npy
```

#### 3.3.4 Layer mix training stub (not required for Phase 3 completion)

Create `scripts/train_layer_mix.py` as a training stub. This is a placeholder for Phase 4 fine-tuning. It does not need to work end-to-end in Phase 3 — it just needs to exist with the correct interface documented.

```python
"""
Train a learned layer-mixture head using playlist co-occurrence as the training signal.

Positives: track pairs from the same Rekordbox playlist or sharing >=2 mytags.
Negatives: in-batch random pairs.
Loss: InfoNCE (NT-Xent) with temperature τ=0.07.

Usage:
    python scripts/train_layer_mix.py \
        --meta data/meta.json \
        --rekordbox path/to/collection.xml \
        --out data/layer_mix_weights.npz \
        --epochs 5 \
        --batch-size 64

Architecture:
    Input:  6 × 1024 layer pools (pre-extracted, cached)
    Head:   Linear(6144 → 1024) + GELU + Linear(1024 → 1024)
    Output: L2-normalized 1024-d vector
    Loss:   InfoNCE

Training data construction:
    1. Load all tracks with embedding_layer_mix computed (Phase 3 above)
    2. Load Rekordbox XML → enumerate playlists → collect (track_A, track_B) pairs
    3. Also collect pairs from same mytags groups
    4. Deduplicate + shuffle
    5. DataLoader with batch_size=64, drop_last=True

Saving:
    np.savez(out, mix_weights=softmax_weights, proj_w=proj_matrix, proj_b=proj_bias)
"""
```

#### 3.3.5 Acceptance criteria for Phase 3

- [ ] `rbassist embed --layer-mix /path/to/track.mp3` produces `*_layer_mix.npy` alongside existing files
- [ ] `meta.json` gains `embedding_layer_mix` key per processed track
- [ ] Layer-mix vector is (1024,) float32, L2-normalized
- [ ] `encode_array_full` calls the model exactly once per audio segment
- [ ] `layer_mix=False` (default) produces byte-identical output to pre-Phase-3
- [ ] `scripts/train_layer_mix.py` exists with docstring and argument skeleton
- [ ] No HNSW index rebuild required (layer-mix vector is not indexed yet)

---

### Phase 4: Benchmark Harness

**Goal:** Build the evaluation harness **before** promoting any new embedding type to primary. Without this, you cannot claim improvement.

**New file to create:**
- `scripts/benchmark_embeddings.py`

**Files to read first:**
- `rbassist/recommend.py` — understand `recommend()` function signature
- `rbassist/playlist_expand.py` — understand `expand_playlist()` and `ExpansionResult`
- `rbassist/utils.py` — `load_meta`, `camelot_relation`

#### 3.4.1 What the benchmark measures

The benchmark runs a fixed set of "golden" seed tracks through the recommendation pipeline under different configurations and records metrics that can be compared across runs.

**Metrics to compute:**

| Metric | Definition | Why it matters |
|---|---|---|
| `camelot_compat_rate` | % of top-25 results with compatible Camelot key | Harmonic mixing quality |
| `bpm_compat_rate` | % of top-25 results within ±6% BPM | Groove compatibility |
| `tag_overlap_mean` | Mean Jaccard overlap of mytags between seed and results | Semantic consistency |
| `intra_list_diversity` | Mean pairwise cosine distance among returned tracks | Avoids repetitive output |
| `transition_score_mean` | Mean cos(E_late(seed), E_intro(result)) when section embeddings exist | DJ transition quality |
| `ann_distance_mean` | Mean ANN cosine distance of top-25 | Embedding proximity |

**Ablation matrix rows (must be rows in the benchmark output table):**

```
A: ANN only (no reranking, no filters)
B: ANN + tempo/key gates
C: ANN + tempo/key + full component weights (current baseline)
D: C + section scores (Phase 2)
E: C + layer-mix embedding as primary vector (Phase 3)
F: D + E (section scores + layer-mix)
```

#### 3.4.2 Benchmark script interface

```
python scripts/benchmark_embeddings.py \
    --meta data/meta.json \
    --seeds "Artist - Track 1" "Artist - Track 2" ... \
    --seeds-file path/to/seeds.txt \       # newline-delimited, # = comment
    --top 25 \
    --candidate-pool 250 \
    --out reports/benchmark_YYYYMMDD.json \
    --compare reports/benchmark_previous.json \   # optional: show delta vs prior run
    --rows A,B,C,D,E,F \                  # which ablation rows to run
    --section-embeds \                    # enable section-score rows
    --layer-mix                           # enable layer-mix rows
```

**Output format (JSON):**
```json
{
  "run_id": "2026-04-12T10:00:00",
  "seeds": [...],
  "rows": {
    "A": {"camelot_compat_rate": 0.72, "bpm_compat_rate": 0.68, ...},
    "B": {"camelot_compat_rate": 0.81, "bpm_compat_rate": 0.84, ...},
    "C": {...},
    "D": {...},
    "E": {...},
    "F": {...}
  },
  "deltas_vs_prior": {...}   // null if no --compare given
}
```

Also print a Rich table to terminal showing all rows side by side.

#### 3.4.3 Golden seed selection guidance

The benchmark is only meaningful if the seed set is stable and representative. Document in the script:

1. Seeds should be tracks the user knows well and can subjectively evaluate
2. Aim for 10–20 seeds covering different genres, tempos, and energy levels within the library
3. Seed paths are written to a `config/benchmark_seeds.txt` file at first run and reused subsequently
4. Never auto-select seeds — the user must provide them

#### 3.4.4 Acceptance criteria for Phase 4

- [ ] `python scripts/benchmark_embeddings.py --seeds "Artist - Track" --rows A,B,C` runs without error on a library with standard embeddings
- [ ] Rows D, E, F gracefully skip (with a warning) if section/layer-mix embeddings are not present
- [ ] Output JSON is valid and loadable
- [ ] `--compare` flag computes and prints deltas correctly
- [ ] Each metric is computed from actual recommendation output, not mocked

---

### Phase 5: Promote Layer-Mix to Primary (Gate on Benchmark)

**Goal:** Once the benchmark shows `row E` or `row F` improves over `row C` on at least 3 of 6 metrics without regressing on any metric by more than 5 points, promote `embedding_layer_mix` to be the primary HNSW index key.

**Files to modify:**
- `rbassist/recommend.py` (change which embedding key is loaded for indexing)
- `rbassist/embed.py` (change `build_embeddings` default so new tracks get layer-mix as primary)
- `rbassist/cli.py` (add `--use-layer-mix-index` flag to `index` command)

**This phase requires a full index rebuild.** The implementation agent must:

1. Add `--index-key` parameter to `rbassist index` command:
   ```
   rbassist index --index-key embedding_layer_mix
   ```
2. `build_index` reads the specified key from meta instead of hardcoded `"embedding"`
3. Old index is backed up, not deleted: `data/index/hnsw_backup_YYYYMMDD.idx`
4. After rebuild, run benchmark row comparison: must verify improvement before merging

**Do not do this phase without benchmark evidence.**

---

### Phase 6: Barwise Structure Reranker (Future)

This phase is documented as intent only. Do not implement without completing Phases 1–5 and validating the benchmark.

**Concept:** For each track, compute a sequence of N bar-level embeddings (e.g., 16 bars × 256-d). Use DTW alignment on this sequence to score "structural compatibility" — matching drops to drops, breakdowns to breakdowns. Apply only to top-50 candidates (compute budget constraint).

**Why deferred:**
- Requires beat-synchronous segmentation (BeatNet already exists in the repo — use it)
- Requires a compressed representation for efficient storage (16 bars × 256-d = 4KB per track)
- DTW on token sequences at top-50 scale adds ~200ms latency — acceptable but needs profiling
- Must be validated by the benchmark harness before touching playlist expansion weights

**Research signal:** A 2026 paper on Music Structure Analysis (MSA) demonstrates that barwise deep embeddings + downstream unsupervised segmentation (CBM method) outperform handcrafted features for boundary detection without supervised structure labels. This is the academic foundation for this phase.

---

## 4. Contracts and Invariants — Never Violate These

The following are hard constraints. Any implementation that violates one is incorrect regardless of performance improvement.

| Contract | Where enforced | What happens if violated |
|---|---|---|
| `"embedding"` key in meta.json always points to a valid 1024-d `.npy` | `recommend.py`, `playlist_expand.py` | Recommendations break for all tracks |
| `DIM = 1024` in `recommend.py` | `HnswIndex.build()` | Index fails to load |
| All new meta keys are **additive** — never remove existing keys | `build_embeddings` | Breaks backward compat for users who haven't re-embedded |
| `layer_mix=False` (default) produces byte-identical output to pre-Phase-3 | `MertEmbedder.encode_array` | Silent embedding drift invalidates all existing cached vectors |
| Section score flags default to `False` | `recommend`, `playlist_expand` | Behavior change without user consent |
| `.npy` files are saved as `float16` | All embed save paths | Doubles storage for no gain |
| Checkpoint resume still works after Phase 1 changes | `build_embeddings` | Long embed runs cannot recover from interruption |
| No existing `.npy` file is overwritten unless `overwrite=True` | `build_embeddings` | User loses manually curated embeddings |

---

## 5. File-by-File Change Manifest

| File | Phase | Change type | Notes |
|---|---|---|---|
| `rbassist/embed.py` | 1 | Extend | Add `encode_section_vectors`, `embed_with_section_vectors`, `section_embed` param to `build_embeddings` |
| `rbassist/embed.py` | 3 | Extend | Add `layer_mix` param to `MertEmbedder.__init__`, add `encode_array_full` |
| `rbassist/layer_mix.py` | 3 | Create | New module: `extract_layer_pools`, `fixed_weight_mix`, `learned_mix` |
| `rbassist/recommend.py` | 2 | Extend | Add `load_section_embeddings`, `use_section_scores` param to `recommend` |
| `rbassist/playlist_expand.py` | 2 | Extend | Add `transition_outro_to_intro` to weights, add to `_compute_component_scores` |
| `rbassist/cli.py` | 1,2,3 | Extend | Add `--section-embed`, `--layer-mix`, `--section-scores` flags |
| `scripts/benchmark_embeddings.py` | 4 | Create | Full benchmark harness |
| `scripts/train_layer_mix.py` | 3 | Create | Training stub (interface only) |
| `config/sampling.yml` | — | No change | Do not touch |
| `rbassist/features.py` | — | No change | Do not touch |
| `rbassist/playlist_expand.py` presets | 2 | Extend | Add `transition_outro_to_intro=0.18` to `"tight"` preset when section embeds present |

---

## 6. Testing Requirements Per Phase

### Phase 1 tests

Write tests in `tests/test_embed_sections.py`:

```python
def test_section_vectors_have_correct_shape():
    """embed_with_section_vectors returns dict with intro/core/late/combined all (1024,)"""

def test_section_combined_matches_existing():
    """combined vector is within 1e-5 of embed_with_default_windows for same input"""

def test_short_track_all_sections_equal():
    """Track < 80s: all four section keys return same vector"""

def test_meta_keys_are_additive():
    """After build_embeddings(section_embed=True), original 'embedding' key unchanged"""

def test_section_npy_are_float16():
    """Saved section .npy files are dtype float16"""
```

### Phase 2 tests

Write tests in `tests/test_section_rerank.py`:

```python
def test_transition_score_range():
    """transition_score is in [0, 1]"""

def test_transition_score_missing_section_graceful():
    """When embedding_intro missing for candidate, score=0, no exception"""

def test_recommend_without_flag_unchanged():
    """recommend(..., use_section_scores=False) output identical to pre-Phase-2"""
```

### Phase 3 tests

Write tests in `tests/test_layer_mix.py`:

```python
def test_extract_layer_pools_shape():
    """extract_layer_pools returns (6, 1024) for 6 taps"""

def test_fixed_weight_mix_normalized():
    """fixed_weight_mix output is L2-normalized (norm ≈ 1.0)"""

def test_layer_mix_false_identical_to_original():
    """MertEmbedder(layer_mix=False).encode_array produces same result as before"""

def test_encode_array_full_single_forward_pass():
    """encode_array_full returns both 'standard' and 'layer_mix' keys"""
```

### Phase 4 tests

```python
def test_benchmark_runs_row_abc():
    """benchmark_embeddings --rows A,B,C runs on fixture library without error"""

def test_benchmark_output_json_valid():
    """Output JSON has correct schema with all metric keys"""

def test_benchmark_compare_computes_deltas():
    """--compare flag computes signed deltas correctly"""
```

---

## 7. Implementation Agent Instructions

### Read before writing any code

In this exact order:

1. Read `rbassist/embed.py` in full — especially lines 101–360
2. Read `rbassist/recommend.py` in full
3. Read `rbassist/playlist_expand.py` lines 1–200 (data classes, weights, presets)
4. Read `rbassist/utils.py` — `load_meta`, `save_meta`, `EMB`, `IDX`, `META` paths
5. Read `rbassist/features.py` — understand how `bass_similarity` is structured so you can follow the same pattern for `transition_score`
6. Read `rbassist/cli.py` — find the `embed` command to understand how parameters are added

### Do not do these things

- Do not modify `_default_windows` — it is correct and tested
- Do not modify `encode_array` or `encode_batch` when `layer_mix=False`
- Do not change the `DIM = 1024` constant
- Do not rename or remove any existing meta.json fields
- Do not rebuild the HNSW index unless explicitly doing Phase 5
- Do not add any dependency that is not already in `pyproject.toml`
- Do not add a new embedding type as the default for existing embed runs — it must be opt-in via flags
- Do not write `print()` — use `console.print()` from `rbassist.utils`
- Do not hardcode paths — use the `EMB`, `IDX`, `META`, `DATA` constants from `rbassist.utils`

### Pattern to follow for all new weighted scores

Follow the exact pattern established by `bass_similarity` in `recommend.py`:

```python
# 1. Guard: only compute if both seed and candidate have the required data
if bass_similarity is not None and seed_bass is not None and cand_bass is not None:
    # 2. Compute the score (always [0,1])
    b_score = bass_similarity(seed_bass, cand_bass)
    # 3. Add to total with weight
    score += weights.get("bass", 0.0) * b_score
```

All new scores must follow this pattern: guard → compute → weighted add.

### Naming conventions

Follow existing conventions exactly:

- Embedding files: `<hash>_<suffix>.npy` (e.g., `abc123_intro.npy`, `abc123_layer_mix.npy`)
- Meta keys: `embedding_<suffix>` (e.g., `embedding_intro`, `embedding_layer_mix`)
- Function names: `snake_case`, verb-first (e.g., `encode_section_vectors`, `load_section_embeddings`)
- CLI flags: `--kebab-case` with `--no-` prefix for boolean negations
- Weight keys in dicts: `snake_case` strings matching the component name

### Commit strategy

One commit per phase, after all acceptance criteria pass. Commit message format:
```
feat(embed): Phase N — <one-line description>

- <bullet: what changed>
- <bullet: what did NOT change (backward compat confirmation)>
- <bullet: acceptance criteria met>
```

---

## 8. Quick Reference: Key Constants and Their Locations

| Symbol | Value | File | Line approx |
|---|---|---|---|
| `DEFAULT_MODEL` | `"m-a-p/MERT-v1-330M"` | embed.py | 24 |
| `SAMPLE_RATE` | `24000` | embed.py | 25 |
| `W_MERT` | `0.7` | embed.py | 31 |
| `W_TIMBRE` | `0.3` | embed.py | 32 |
| `DIM` | `1024` | recommend.py | 13 |
| `INDEX_ADD_CHUNK` | `2000` | recommend.py | 14 |
| `LAYER_TAPS` | `[4,8,12,16,20,24]` | layer_mix.py (new) | — |
| `LAYER_WEIGHTS_FIXED` | `[.05,.10,.15,.20,.25,.25]` | layer_mix.py (new) | — |
| `EMB` | `data/embeddings/` | utils.py | ~25 |
| `IDX` | `data/index/` | utils.py | ~26 |
| `META` | `data/meta.json` | utils.py | ~27 |

---

## 9. Research Citations

These findings directly inform the design decisions above.

**Layer hierarchy → multi-layer pooling rationale:**
- Tûr, Vaidya et al.: SSL audio models predict fMRI auditory cortex with layer-depth preference matching cortical hierarchy. Different brain regions prefer different model depths. → Use multiple layers, not just the last.
- MERT model card (m-a-p/MERT-v1-330M): explicitly recommends learnable weighted aggregation across layers.

**Section asymmetry → intro/core/late storage:**
- DJ mixing practice: transitions are outro→intro, not body→body. A single averaged vector masks this.
- rbassist research reports (reports 10 & 11): independently converge on section-aware embedding as the single highest-ROI change.

**Fixed layer weights rationale:**
- Early layers (4, 8): acoustic texture, timbral envelope — weight conservatively (0.05, 0.10)
- Middle layers (12, 16): rhythmic modulation, beat-synchronous patterns — weight moderately (0.15, 0.20)
- Late layers (20, 24): semantic music structure, harmonic trajectory — weight most heavily (0.25, 0.25)
- Sum = 1.0. This weighting is a reasonable prior; learned weights (Phase 3 training stub) will supersede it.

**Contrastive training signal → playlist co-occurrence:**
- InfoNCE/NT-Xent: SimCLR (Chen et al. 2020), MoCo (He et al. 2020), CLAP (Wu et al. 2023) all validate contrastive loss for self-supervised representation learning.
- Library-native positives: no external annotation needed — use Rekordbox playlists and mytags.

**Two-stage retrieval → ANN then rerank:**
- Standard in production recommendation systems; rbassist already uses this pattern (HNSW → component score rerank). We extend Stage 2, not Stage 1.

**Barwise embeddings → Phase 6 rationale:**
- 2026 MSA evaluation study: barwise deep embeddings + CBM segmentation outperform handcrafted features for music structure analysis. Validates the Phase 6 direction but does not require immediate implementation.

---

*End of handoff document. Phases 1–4 are fully specified and ready for implementation. Phase 5 requires benchmark evidence. Phase 6 is intent-only.*
