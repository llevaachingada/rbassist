# rbassist Advanced Matching Upgrade Plan
## Handoff Document for Implementation Agent

**Status:** Ready for implementation  
**Prerequisite:** Phases 1–4 of `EMBEDDING_UPGRADE_PLAN.md` should be complete or in-progress  
**Branch target:** `embedding-update`  
**Do not alter any existing behavior** — all features are additive and flag-gated.  
**Author context:** This document was produced by analyzing the rbassist codebase, two PhD-level research reports on audio embedding architectures, and targeted web research on learned similarity metrics, tempo translation networks, and psychoacoustic harmony models. Every code reference is verified against the live source. Research citations are at the end.

---

## 0. Ground Truth: What the Code Does Today

Before writing a single line, internalize these integration points. Every design decision in this plan flows from them.

### Cosine similarity is used everywhere — and it's the wrong metric

MERT-v1-330M was trained with **MLM (masked language modeling)** using pseudo-labels from EnCodec codebooks. It was **NOT** trained with a contrastive objective. This means the embedding space was never explicitly optimized so that cosine similarity corresponds to musical similarity. The HuggingFace model card itself states: *"Features extracted by different layers could have various performance depending on tasks."*

Despite this, raw cosine is the sole similarity metric in the entire pipeline:

```python
# recommend.py:82-89 — cosine used for all ANN reranking
def _cosine_01(left: np.ndarray, right: np.ndarray) -> float:
    denom = float(np.linalg.norm(left) * np.linalg.norm(right))
    score = float(np.dot(left, right) / (denom + 1e-9))
    return float(np.clip(score, 0.0, 1.0))

# playlist_expand.py:854-860 — cosine used for centroid + group scoring
def _cosine_similarity(left: np.ndarray, right: np.ndarray) -> float:
    denom = float(np.linalg.norm(left) * np.linalg.norm(right))
    return float(np.dot(left, right) / denom)
```

The `ann_centroid` (0.30) and `group_match` (0.16) weights together account for **46% of the default playlist expansion score** — all computed via raw cosine on an MLM embedding space.

### Camelot matching is binary — compatible or not

```python
# utils.py:189-210 — camelot_relation returns (bool, str)
def camelot_relation(seed: str | None, cand: str | None) -> tuple[bool, str]:
    # ... 7 discrete rules, returns (True/False, rule_name)
```

Used in:
- `recommend.py:284-285` — hard filter (`if camelot_neighbors and not ok_key: continue`)
- `playlist_expand.py` — `key_match` component score (1.0 if compatible, 0.0 if filtered, 0.5 if unknown)

The `key_match` weight is only 0.08 — low because a binary score carries almost no ranking information. A continuous score would justify increasing this weight.

### Tempo matching is a gate, not a score

```python
# utils.py:218-228 — tempo_match returns bool
def tempo_match(bpm1, bpm2, pct=6.0, allow_doubletime=True) -> bool:
```

Used as a hard filter at `recommend.py:287-288`. Tracks outside the BPM window are excluded entirely — there is no "close but not quite" scoring. A track at 127 BPM is treated identically to one at 120 BPM when the seed is 128 BPM (both pass the 6% gate), and a track at 135.2 BPM is excluded entirely despite being a reasonable DJ option.

### Existing scoring pattern to follow

All scoring functions in `features.py` follow this contract:

```python
def bass_similarity(seed_contour: np.ndarray, cand_contour: np.ndarray) -> float:
    """Similarity in [0,1] via DTW on log-Hz contours."""
    # Guard → compute → return [0,1]
```

Every new scoring function in this plan **MUST** follow this pattern:
1. Accept pre-computed feature arrays (not raw audio)
2. Return `float` in `[0, 1]`
3. Handle empty/missing inputs gracefully (return 0.0)
4. Be deterministic

### Hard contracts (inherited from EMBEDDING_UPGRADE_PLAN.md)

| Contract | Value | Location |
|----------|-------|----------|
| HNSW dimension | `DIM = 1024` | `recommend.py:13` |
| Primary embedding key | `"embedding"` in meta.json | Never rename or remove |
| All new meta keys | Additive only | Never break existing consumers |
| All new behavior | Flag-gated, default OFF | CLI flags must default to `False` |

---

## 1. Research Basis

### 1.1 Why raw cosine fails on MLM embeddings

Cosine similarity on MERT embeddings is an **imperfect proxy** because:

- MERT's pre-training objective (masked acoustic token prediction) optimizes for *reconstruction*, not for *similarity*. Two tracks can be equidistant from a third in embedding space but have wildly different musical compatibility.
- The SBERT literature (Reimers & Gurevych, 2019) demonstrated that even BERT embeddings — also MLM-trained — produce poor cosine similarity rankings until a contrastive fine-tuning head is added.
- The PAMT system (arXiv 2509.04985) showed that adding a learned projection head on top of frozen MERT-v0 with InfoNCE loss (tau=0.1) significantly improved perceptual audio similarity tasks.
- The RecSys 2024 comparative study found that MusiCNN (a tiny 200-d **supervised** model) outperforms all SSL models including MERT for recommendation — suggesting that the *metric* matters more than the *backbone*.

**Implication:** A lightweight learned scoring head on frozen MERT embeddings is likely the single highest-ROI change for recommendation quality.

### 1.2 Tempo translation networks

The paper "Similar but Faster" (Kirchhoff et al., ICASSP 2024, arXiv 2401.08902) demonstrated:

- A 2-layer MLP can predict what an embedding would look like at a different tempo with **40x speedup** over re-embedding time-stretched audio.
- Training is entirely self-supervised: time-stretch audio by random factor tau, embed both versions, train MLP to predict the stretched embedding from (original embedding, tau).
- The stretch range [0.75, 1.5] covers typical DJ pitch adjustments (+/- 50% extreme, +/- 6% typical).
- For MERT (larger than the paper's MULE model), the speedup is estimated at **1000–2000x** per embedding translation.

**Implication:** Query the same HNSW index at multiple tempos in ~10ms total, versus ~10–20s to actually time-stretch and re-embed.

### 1.3 Psychoacoustic harmony beyond Camelot

Three validated approaches replace binary key matching with continuous compatibility:

1. **Chroma distribution matching** — Extract the full 12-element pitch class profile per track. Compare via cosine similarity or Earth Mover's Distance on the circular chroma space. Handles modal ambiguity, key estimation errors, and non-Western scales. Validated by Gómez (2006) and the MIREX key detection literature.

2. **Tonnetz similarity** — `librosa.feature.tonnetz` projects chroma onto a 6-d tonal centroid space encoding fifth, minor-third, and major-third relationships. Euclidean or cosine distance in tonnetz space correlates with perceived consonance. Already in the librosa dependency tree.

3. **Tonal Interval Space (TIS)** — A 6-d complex vector from the DFT of the chroma vector, with perceptual weights. The `TIVlib` library implements this. More mathematically rigorous than tonnetz but requires an additional dependency.

**The relationship to Camelot:** Continuous harmonic compatibility **subsumes** Camelot. Camelot-compatible pairs generally score 0.7+ on the continuous metric, but the continuous metric also finds compatible pairs Camelot misses and distinguishes between Camelot-compatible pairs (some 0.95, others 0.72).

---

## 2. Architecture Overview

### Data flow with all three upgrades active

```
                         ┌──────────────────────────────┐
                         │     TRAINING (offline)        │
                         │                               │
                         │  Playlist co-occurrence pairs  │
                         │         ↓                      │
                         │  Similarity MLP trainer        │
                         │         ↓                      │
                         │  similarity_head.pt            │
                         │                               │
                         │  Library tracks + BPMs         │
                         │         ↓                      │
                         │  Tempo translation trainer     │
                         │         ↓                      │
                         │  tempo_translate.pt            │
                         └──────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────┐
  │                    EMBED TIME (per track)                    │
  │                                                             │
  │  audio.wav ──→ MERT ──→ embedding (1024-d)     [existing]  │
  │            ──→ librosa.chroma_cqt ──→ chroma_profile (12-d) │
  │            ──→ librosa.tonnetz    ──→ tonnetz_profile (6-d)  │
  │                                                             │
  │  Stored in meta.json:                                       │
  │    "chroma_profile": [12 floats]    ← NEW                  │
  │    "tonnetz_profile": [6 floats]    ← NEW                  │
  └─────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────┐
  │                    RECOMMEND TIME (per query)                │
  │                                                             │
  │  Stage 1 (ANN, fast):                                       │
  │    seed_vec ──→ HNSW query ──→ top-250 candidates           │
  │    [optional] seed_vec + tau ──→ tempo_translate             │
  │      ──→ translated_vecs ──→ HNSW query at N tempos         │
  │      ──→ merge candidate pools                              │
  │                                                             │
  │  Stage 2 (rerank, per-candidate):                           │
  │    similarity_head(seed_vec, cand_vec)  → learned_sim       │
  │    harmonic_compat(seed_chroma/tonnetz,                     │
  │                    cand_chroma/tonnetz) → harmony_score      │
  │    transition_score(seed_late, cand_intro) → trans_score     │
  │    bass_similarity(...)  → bass_score                       │
  │    rhythm_similarity(...)  → rhythm_score                   │
  │    bpm_match / tag_match / ...  → existing scores           │
  │                                                             │
  │    final_score = weighted_sum(all_component_scores)          │
  └─────────────────────────────────────────────────────────────┘
```

---

## 3. Implementation Phases

### Phase A: Harmonic Profile Extraction & Scoring

**Goal:** Replace binary Camelot key_match with a continuous harmonic compatibility score. Zero new dependencies (uses librosa, already installed).

#### A.1 — Extract and store harmonic profiles during embed

Add to `embed.py`'s embedding pipeline (after MERT embedding is computed):

```python
# Extract chroma and tonnetz profiles from audio
# Use CQT chroma for better frequency resolution
chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=512, n_chroma=12)
chroma_profile = chroma.mean(axis=1)  # (12,)
chroma_profile = chroma_profile / (chroma_profile.sum() + 1e-10)  # L1-normalize

tonnetz = librosa.feature.tonnetz(y=librosa.effects.harmonic(y), sr=sr)
tonnetz_profile = tonnetz.mean(axis=1)  # (6,)
```

**New meta.json keys** (per track, additive):
```json
{
  "chroma_profile": [0.12, 0.03, 0.08, ...],
  "tonnetz_profile": [0.15, -0.22, 0.08, -0.11, 0.19, -0.05]
}
```

Storage cost: 18 floats per track = 72 bytes. Negligible.

**CLI flag:** `--harmonic-profiles / --no-harmonic-profiles` on `rbassist embed`, default `False`.

#### A.2 — New scoring function in features.py

Create `harmonic_compatibility` following the existing pattern:

```python
def harmonic_compatibility(
    seed_chroma: np.ndarray,
    seed_tonnetz: np.ndarray,
    cand_chroma: np.ndarray,
    cand_tonnetz: np.ndarray,
) -> float:
    """Continuous harmonic compatibility score in [0, 1].

    Combines chroma cosine similarity (captures key/mode overlap)
    with tonnetz cosine similarity (captures tonal interval relationships).
    Weighted 40/60 in favor of tonnetz because it encodes interval
    quality (5ths, 3rds) that matter most for DJ mixing.
    """
    if seed_chroma.size == 0 or cand_chroma.size == 0:
        return 0.0
    if seed_tonnetz.size == 0 or cand_tonnetz.size == 0:
        return 0.0

    # Chroma cosine similarity
    denom_c = float(np.linalg.norm(seed_chroma) * np.linalg.norm(cand_chroma))
    chroma_sim = float(np.dot(seed_chroma, cand_chroma) / (denom_c + 1e-9)) if denom_c > 0 else 0.0

    # Tonnetz cosine similarity
    denom_t = float(np.linalg.norm(seed_tonnetz) * np.linalg.norm(cand_tonnetz))
    tonnetz_sim = float(np.dot(seed_tonnetz, cand_tonnetz) / (denom_t + 1e-9)) if denom_t > 0 else 0.0

    score = 0.4 * chroma_sim + 0.6 * tonnetz_sim
    return float(np.clip(score, 0.0, 1.0))
```

**Do NOT remove the existing `camelot_relation` function.** Keep Camelot as a fast pre-filter. The continuous score supplements it for ranking — it tells you *how* compatible two Camelot-compatible tracks are.

#### A.3 — Wire into recommend.py and playlist_expand.py

In `recommend.py`, add a new weight key:

```python
w_harmony = float(weights.get("harmony", 0.0))
```

In the candidate scoring loop (after line 309), add:

```python
if w_harmony:
    seed_chroma = np.array(seed_info.get("chroma_profile", []), dtype=np.float32)
    seed_tonnetz = np.array(seed_info.get("tonnetz_profile", []), dtype=np.float32)
    cand_chroma = np.array(info.get("chroma_profile", []), dtype=np.float32)
    cand_tonnetz = np.array(info.get("tonnetz_profile", []), dtype=np.float32)
    if seed_chroma.size == 12 and cand_chroma.size == 12:
        score += w_harmony * harmonic_compatibility(
            seed_chroma, seed_tonnetz, cand_chroma, cand_tonnetz
        )
```

In `playlist_expand.py`, add `harmonic_match` to `PlaylistExpansionWeights` with default `0.0`.

**CLI flags:** `--w-harmony` on `rbassist recommend`, default `0.0`.

#### A.4 — Acceptance criteria

- [ ] `rbassist embed --harmonic-profiles` stores `chroma_profile` (12 floats) and `tonnetz_profile` (6 floats) per track
- [ ] Tracks without harmonic profiles gracefully return 0.0 from `harmonic_compatibility`
- [ ] `rbassist recommend --w-harmony 0.15` uses the continuous score in reranking
- [ ] Two tracks in the same key (e.g., both 8A) score > 0.7
- [ ] Two tracks in Camelot +1 (e.g., 8A and 9A) score > 0.6
- [ ] Two tracks in tritone relationship (e.g., 8A and 2A) score < 0.4
- [ ] Existing Camelot filtering still works when `--camelot-neighbors` is enabled
- [ ] Unit test: `test_harmonic_compatibility.py` validates score ranges for known key pairs

---

### Phase B: Learned Similarity Head

**Goal:** Train a lightweight MLP that scores embedding pairs better than raw cosine. Sits in Stage 2 (reranking) — does NOT touch the HNSW index.

#### B.1 — Architecture: `rbassist/similarity_head.py`

```python
"""Learned pairwise similarity scoring on frozen MERT embeddings."""

import torch
import torch.nn as nn

class SimilarityHead(nn.Module):
    """MLP that scores (seed_embedding, candidate_embedding) -> [0, 1].

    Input representation: [|u - v|; u * v] (2048-d)
      - Element-wise difference captures "how far apart" in each dimension
      - Element-wise product captures "do they co-activate the same features"
      - Omits raw concatenation [u; v] to halve parameters without
        significant performance loss (SBERT ablation finding)
    """

    def __init__(self, embed_dim: int = 1024, hidden: int = 512, bottleneck: int = 128):
        super().__init__()
        input_dim = embed_dim * 2  # |u-v| concat u*v
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden),
            nn.BatchNorm1d(hidden),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(hidden, bottleneck),
            nn.BatchNorm1d(bottleneck),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(bottleneck, 1),
            nn.Sigmoid(),
        )

    def forward(self, u: torch.Tensor, v: torch.Tensor) -> torch.Tensor:
        diff = torch.abs(u - v)
        prod = u * v
        x = torch.cat([diff, prod], dim=-1)
        return self.net(x).squeeze(-1)
```

**Parameter count:** ~1.1M trainable. Trains in seconds on CPU for small datasets.

**Why this architecture:**
- Element-wise difference is the most informative single component per the SBERT ablation
- Element-wise product captures co-activation patterns
- 512→128 bottleneck forces compact similarity representation
- BatchNorm + Dropout(0.1) prevents overfitting on small playlist datasets
- Sigmoid output gives natural [0,1] score compatible with existing weight system

#### B.2 — Training data construction: `scripts/train_similarity_head.py`

**Positive pairs** — from Rekordbox playlists:

| Pair type | Label | Source |
|-----------|-------|--------|
| Adjacent tracks in same playlist | 1.0 | Captures DJ transition intent |
| Same-playlist, non-adjacent | 0.7 | Captures broad stylistic match |
| Tracks sharing ≥2 mytags | 0.8 | User-curated compatibility signal |

**Negative pairs** — stratified by difficulty:

| Pair type | Label | Purpose |
|-----------|-------|---------|
| Different playlist, different BPM range (>15%), different key | 0.0 | Confident negatives |
| Different playlist, similar BPM, different key | 0.2 | Medium negatives (might still be compatible) |
| Different playlist, similar BPM, compatible key | 0.3 | Uncertain negatives (the "many valid pairs" problem) |

**Why graded labels instead of binary:** Two tracks might be perfectly DJ-compatible but never appear in the same playlist simply because the DJ hasn't paired them yet. Graded labels (BCE regression) soften the false-negative penalty for these ambiguous pairs.

**Loss function:** Binary cross-entropy with graded labels.

```python
loss = F.binary_cross_entropy(model(u, v), label)
```

**Training recipe:**
```
optimizer:     AdamW, lr=1e-3, weight_decay=1e-4
batch_size:    256
epochs:        30 (early stopping on validation loss, patience=5)
scheduler:     CosineAnnealingLR, T_max=30
validation:    20% held-out playlist pairs
```

**Minimum training data:** ~2,000 playlist-derived pairs. A library of 50+ playlists with 10+ tracks each is sufficient.

#### B.3 — Inference integration

The trained head is a `.pt` file stored in `data/models/similarity_head.pt`.

**Numpy-only inference** (no torch dependency at recommend time):

```python
def load_similarity_head(path: str) -> dict:
    """Load trained weights as numpy arrays for torch-free inference."""
    state = torch.load(path, map_location="cpu")
    return {k: v.numpy() for k, v in state.items()}

def similarity_score(u: np.ndarray, v: np.ndarray, weights: dict) -> float:
    """Score a pair using the learned head. Returns [0, 1]."""
    diff = np.abs(u - v)
    prod = u * v
    x = np.concatenate([diff, prod])
    # Forward through stored weight matrices
    # (manual implementation of the Sequential layers using numpy)
    ...
    return float(score)
```

Alternatively, keep torch and just call `model(torch.from_numpy(u), torch.from_numpy(v))` — this adds ~0.5ms per pair, which is fine for the top-250 reranking pool.

#### B.4 — Score calibration

The MLP's sigmoid output may not be well-calibrated against existing [0,1] scores (bass_similarity, rhythm_similarity, etc.). Two options:

**Option 1 — Isotonic regression (recommended, ~500+ validation pairs):**
```python
from sklearn.isotonic import IsotonicRegression
ir = IsotonicRegression(y_min=0, y_max=1, out_of_bounds='clip')
ir.fit(raw_scores, ground_truth_labels)
# Save: pickle ir, load at inference time
calibrated = ir.transform(model_output)
```

**Option 2 — Temperature scaling (simpler, ~100 validation pairs):**
```python
calibrated = sigmoid(logit(raw_score) / temperature)
# Fit temperature to minimize NLL on validation set
```

Store the calibrator alongside the model in `data/models/similarity_calibrator.pkl`.

#### B.5 — Wire into the scoring system

In `recommend.py`, add:
```python
w_learned = float(weights.get("learned_sim", 0.0))
```

Replace or supplement the `w_ann * (1.0 - dist)` term:
```python
if w_learned and similarity_head is not None:
    score += w_learned * similarity_score(seed_vec, cand_vec, head_weights)
```

In `playlist_expand.py`, add `learned_similarity` to `PlaylistExpansionWeights` with default `0.0`. When active, it can replace or blend with `ann_centroid`:
```python
# Optionally replace raw cosine centroid score:
if use_learned_similarity and similarity_head is not None:
    scores["ann_centroid"] = similarity_score(cand_vec, seed_centroid, head_weights)
```

**CLI flag:** `--learned-similarity / --no-learned-similarity` on `rbassist recommend`, default `False`. Requires `data/models/similarity_head.pt` to exist.

#### B.6 — Acceptance criteria

- [ ] `scripts/train_similarity_head.py` reads Rekordbox playlists, constructs training pairs, trains the MLP, saves to `data/models/similarity_head.pt`
- [ ] Training completes in <5 minutes on CPU for a 5000-track library
- [ ] `rbassist recommend --learned-similarity --w-learned-sim 0.3` uses the head for reranking
- [ ] When `similarity_head.pt` is missing, falls back gracefully to raw cosine with a warning
- [ ] Calibrated output distribution is roughly uniform over [0.2, 0.9] (not clustered at 0.5)
- [ ] Unit test: `test_similarity_head.py` validates MLP forward pass shape and [0,1] output range
- [ ] A/B comparison: for a known seed track, compare top-10 from raw cosine vs learned metric and verify the learned metric surfaces more musically coherent results (manual inspection)

---

### Phase C: Tempo Translation Network

**Goal:** Enable tempo-invariant similarity search by translating embeddings across BPM ranges without re-embedding time-stretched audio.

#### C.1 — Architecture: `rbassist/tempo_translate.py`

```python
"""Lightweight MLP that predicts MERT embeddings at shifted tempos."""

import torch
import torch.nn as nn

class TempoTranslator(nn.Module):
    """Predicts what a MERT embedding would look like at a different tempo.

    Input: embedding z (1024-d) concatenated with stretch factor tau (scalar)
    Output: translated embedding z' (1024-d)

    Uses residual formulation: z' = z + f(z, tau)
    so that tau=1.0 naturally produces z' ≈ z (the network learns the delta).
    """

    def __init__(self, embed_dim: int = 1024, hidden: int = 2048):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(embed_dim + 1, hidden),
            nn.LayerNorm(hidden),
            nn.GELU(),
            nn.Linear(hidden, hidden),
            nn.LayerNorm(hidden),
            nn.GELU(),
            nn.Linear(hidden, embed_dim),
        )

    def forward(self, z: torch.Tensor, tau: torch.Tensor) -> torch.Tensor:
        """
        z:   (B, 1024) — batch of embeddings
        tau: (B, 1)    — stretch factors (1.0 = no change)
        """
        x = torch.cat([z, tau], dim=-1)
        delta = self.net(x)
        return z + delta  # residual: learn the change, not the absolute
```

**Why residual:** For tau near 1.0, z' should be very close to z. The network only needs to learn the *delta* caused by tempo change, which is a much simpler function than the absolute mapping.

**Why GELU + LayerNorm:** The paper uses an unspecified MLP. LayerNorm (instead of BatchNorm) works better for varying batch sizes at inference. GELU is standard for transformer-adjacent models.

**Parameter count:** ~6.3M trainable. Still lightweight compared to MERT's 330M.

#### C.2 — Training: `scripts/train_tempo_translate.py`

**Training is entirely self-supervised — no labels needed.**

```
For each track in the library:
  1. Load audio, compute MERT embedding z (cached in data/embeddings/)
  2. Sample tau from log-uniform distribution over [0.75, 1.5]
  3. Time-stretch audio: y_stretched = librosa.effects.time_stretch(y, rate=tau)
  4. Compute MERT embedding of stretched audio: z_target
  5. Train f(z, tau) to predict z_target
```

**Loss:** Dual loss (following the paper):
```python
loss = F.mse_loss(z_pred, z_target) + (1.0 - F.cosine_similarity(z_pred, z_target).mean())
```

MSE captures absolute position in embedding space. Cosine loss preserves direction (important because HNSW uses cosine distance).

**Training recipe:**
```
optimizer:      AdamW, lr=1e-3
batch_size:     128
scheduler:      CosineAnnealingLR with 2000-step warmup
tau_range:      [0.75, 1.5] log-uniform
epochs:         50 (or 100k steps, whichever comes first)
validation:     10% held-out tracks, measure cosine similarity of predicted vs actual
```

**Data requirements:**
- Each track generates multiple training examples (different tau values, different time offsets).
- With 10 tau samples × 3 temporal windows per track, 5000 tracks = 150,000 training examples.
- **The expensive step** is computing MERT embeddings of time-stretched audio (~0.5–1.0s per embedding on GPU). For 5000 tracks × 10 tau values = 50,000 MERT forward passes = ~7–14 hours on a single GPU. This is a one-time cost.

**Optimization:** Pre-compute all (z, tau, z_target) triplets and save to a `.npz` file. Then training the MLP itself takes only minutes.

#### C.3 — Inference integration

The trained model is stored at `data/models/tempo_translate.pt`.

**Approach: Multi-tempo query (recommended)**

Query the SAME HNSW index at multiple translated tempos:

```python
def tempo_aware_recommend(
    seed_vec: np.ndarray,
    seed_bpm: float,
    target_bpms: list[float],
    translator: TempoTranslator,
    hnsw_index,
    k_per_query: int = 50,
) -> list[tuple[int, float]]:
    """Query HNSW at multiple tempo translations, merge results."""
    all_candidates = {}
    for target_bpm in target_bpms:
        tau = target_bpm / seed_bpm
        z_translated = translator.predict(seed_vec, tau)  # ~0.5ms
        labels, dists = hnsw_index.knn_query(z_translated, k=k_per_query)
        for lab, dist in zip(labels[0], dists[0]):
            if lab not in all_candidates or dist < all_candidates[lab]:
                all_candidates[lab] = dist
    return sorted(all_candidates.items(), key=lambda x: x[1])
```

**Default target BPMs:** Generate from seed BPM at 2% increments:
```python
target_bpms = [seed_bpm * (1 + i * 0.02) for i in range(-5, 6)]
# e.g., for 128 BPM: [115.2, 117.8, 120.3, 122.9, 125.4, 128.0, 130.6, 133.1, 135.7, 138.2, 140.8]
```

This queries HNSW 11 times with 11 translated embeddings. Total time: ~6ms for translations + ~11ms for HNSW queries = ~17ms. Compare to actually time-stretching audio and re-embedding: ~11 seconds.

**No index modification needed.** This queries the existing HNSW index with translated query vectors.

#### C.4 — CLI integration

```
rbassist recommend <seed> --tempo-translate --tempo-range 0.9,1.1
```

- `--tempo-translate`: Enable multi-tempo querying (requires `data/models/tempo_translate.pt`)
- `--tempo-range`: Min,max stretch factors (default: 0.9,1.1 = +/-10%)
- `--tempo-steps`: Number of query points (default: 11)

When `--tempo-translate` is active, the `--tempo-pct` gate is **relaxed** (increased to the tempo-range bounds) because the translation network now handles tempo matching in embedding space rather than as a hard BPM filter.

#### C.5 — Acceptance criteria

- [ ] `scripts/train_tempo_translate.py` generates training data from the library and trains the translator
- [ ] Translator predicts z' from (z, tau=1.0) with cosine similarity > 0.99 to z (identity check)
- [ ] Translator predicts z' from (z, tau=0.9) with cosine similarity > 0.85 to actual time-stretched embedding
- [ ] `rbassist recommend --tempo-translate` queries at multiple tempos and surfaces tracks outside the normal BPM window
- [ ] When `tempo_translate.pt` is missing, falls back gracefully to standard single-query with a warning
- [ ] Total query time with 11 tempo steps < 50ms (on GPU) or < 200ms (on CPU)
- [ ] Unit test: `test_tempo_translate.py` validates forward pass shape, residual identity property, and [0.75, 1.5] tau range

---

## 4. File-by-File Change Manifest

### New files

| File | Phase | Purpose |
|------|-------|---------|
| `rbassist/similarity_head.py` | B | MLP architecture + numpy inference wrapper |
| `rbassist/tempo_translate.py` | C | Translator architecture + inference wrapper |
| `scripts/train_similarity_head.py` | B | Training script for learned similarity |
| `scripts/train_tempo_translate.py` | C | Training script for tempo translator |
| `tests/test_harmonic_compatibility.py` | A | Tests for chroma/tonnetz scoring |
| `tests/test_similarity_head.py` | B | Tests for MLP forward pass and score range |
| `tests/test_tempo_translate.py` | C | Tests for translator forward pass and identity |

### Modified files

| File | Phase | Changes |
|------|-------|---------|
| `rbassist/features.py` | A | Add `harmonic_compatibility()` function |
| `rbassist/embed.py` | A | Extract chroma + tonnetz profiles, store in meta.json |
| `rbassist/recommend.py` | A, B, C | Add `w_harmony`, `w_learned_sim`, `--tempo-translate` |
| `rbassist/playlist_expand.py` | A, B | Add `harmonic_match` and `learned_similarity` weight keys |
| `rbassist/cli.py` | A, B, C | Add CLI flags for all three features |
| `rbassist/utils.py` | — | No changes (keep camelot_relation as-is) |
| `rbassist/layer_mix.py` | — | No changes |

---

## 5. Test Requirements

### Phase A tests (`test_harmonic_compatibility.py`)

```python
def test_same_key_scores_high():
    """Two identical chroma profiles should score > 0.9."""

def test_tritone_scores_low():
    """Chroma profiles 6 semitones apart should score < 0.4."""

def test_camelot_plus_one_scores_moderate():
    """Adjacent Camelot keys should score 0.6–0.85."""

def test_empty_input_returns_zero():
    """Missing profiles should return 0.0, not crash."""

def test_score_range():
    """Output must be in [0, 1] for random inputs."""
```

### Phase B tests (`test_similarity_head.py`)

```python
def test_forward_pass_shape():
    """MLP(1024, 1024) -> scalar in [0, 1]."""

def test_identical_inputs_score_high():
    """similarity_head(v, v) should be > 0.8."""

def test_random_inputs_score_moderate():
    """Random embeddings should score 0.3–0.7 (not degenerate)."""

def test_numpy_inference_matches_torch():
    """Numpy-only inference matches torch forward pass within 1e-5."""

def test_missing_model_graceful_fallback():
    """When .pt file missing, falls back to cosine with warning."""
```

### Phase C tests (`test_tempo_translate.py`)

```python
def test_identity_tau():
    """translate(z, tau=1.0) should be close to z (cosine > 0.99)."""

def test_forward_pass_shape():
    """Translator(1024, tau) -> (1024,)."""

def test_tau_range():
    """Should accept tau in [0.75, 1.5] without error."""

def test_residual_small_for_small_tau():
    """For tau close to 1.0, the delta should be small."""

def test_missing_model_graceful_fallback():
    """When .pt file missing, falls back to single-query with warning."""
```

---

## 6. Implementation Agent Instructions

### Read order

1. This document (you're reading it)
2. `EMBEDDING_UPGRADE_PLAN.md` — understand the existing upgrade plan and ensure no conflicts
3. `rbassist/features.py` — your pattern template for scoring functions
4. `rbassist/recommend.py` — understand the full scoring pipeline (lines 214–332)
5. `rbassist/playlist_expand.py` — understand `PlaylistExpansionWeights` and `_compute_component_scores`
6. `rbassist/embed.py` — understand where to add chroma/tonnetz extraction
7. `rbassist/cli.py` — understand how CLI flags are wired to function arguments

### Implementation order

**Phase A first** — it has zero new dependencies, zero training requirements, and immediately improves key matching. Ship it, verify it works, then move on.

**Phase B second** — it needs playlist data for training but the architecture is simple. The scoring improvement affects 46% of the default weight budget.

**Phase C last** — it has the highest compute cost (generating training data requires time-stretching + re-embedding thousands of tracks) but the payoff is large for DJ workflows.

### Naming conventions

- Scoring functions: `thing_similarity()` or `thing_compatibility()` returning `float` in `[0, 1]`
- Weight keys: `snake_case`, added to existing dataclass with default `0.0`
- CLI flags: `--kebab-case`, default `False` for enable/disable, `0.0` for weights
- Model files: `data/models/<name>.pt`
- Test files: `tests/test_<module_name>.py`

### Pattern to follow for all new scoring functions

```python
def new_score(seed_feature: np.ndarray, cand_feature: np.ndarray) -> float:
    """One-line description. Returns [0, 1]."""
    if seed_feature.size == 0 or cand_feature.size == 0:
        return 0.0
    # ... compute ...
    return float(np.clip(result, 0.0, 1.0))
```

### Critical constraints

1. **Never modify `camelot_relation`** — it works correctly. The harmonic score supplements it, not replaces it.
2. **Never make the learned similarity head mandatory** — always fall back to raw cosine when the model file is missing.
3. **Never modify the HNSW index** for tempo translation — translate the *query*, not the index.
4. **All new meta.json keys are additive** — never remove or rename existing keys.
5. **All new CLI flags default to OFF** — the user must explicitly opt in.
6. **All training scripts must work without a GPU** (slower is fine, broken is not).

---

## 7. Quick Reference: Constants & Locations

| Constant | Value | Location |
|----------|-------|----------|
| HNSW DIM | 1024 | `recommend.py:13` |
| Chroma bins | 12 | librosa default |
| Tonnetz dims | 6 | librosa default |
| Similarity head input | 2048 (1024 × 2) | `similarity_head.py` |
| Similarity head hidden | 512 → 128 | `similarity_head.py` |
| Tempo translator hidden | 2048 | `tempo_translate.py` |
| Tau range | [0.75, 1.5] | `tempo_translate.py` |
| Default tempo steps | 11 | CLI default |
| Model storage | `data/models/` | New directory |
| Existing weights path | `data/` | `utils.py:10-12` |

---

## 8. Dependency Impact

| Dependency | Phase | Status | Install |
|------------|-------|--------|---------|
| `librosa` | A | Already installed | — |
| `numpy` | A, B, C | Already installed | — |
| `torch` | B, C (training only) | Already installed | — |
| `scikit-learn` | B (calibration) | Likely installed | `pip install scikit-learn` |
| `scipy` | A (optional, for EMD) | Already installed (librosa dep) | — |

**No new mandatory dependencies.** scikit-learn is only needed for the optional isotonic regression calibrator in Phase B. If not installed, temperature scaling (pure numpy) can be used instead.

---

## 9. Research Citations

| # | Reference | Used in |
|---|-----------|---------|
| 1 | Kirchhoff et al., "Similar but Faster: Manipulation of Tempo in Music Audio Embeddings," ICASSP 2024, arXiv:2401.08902 | Phase C architecture, training recipe, tau range |
| 2 | Reimers & Gurevych, "Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks," EMNLP 2019 | Phase B pair representation ([u; v; \|u-v\|]) |
| 3 | Ferraro et al., "Contrastive Learning with Playlist Information for Music Recommender Systems," ICASSP 2023, arXiv:2304.12257 | Phase B training data construction (playlist co-occurrence as positives) |
| 4 | PAMT, "Training a Perceptual Audio Model for Auditory Similarity," arXiv:2509.04985 | Phase B precedent for learned head on frozen MERT |
| 5 | Chuang et al., "Debiased Contrastive Learning," NeurIPS 2020 | Phase B negative sampling (handling false negatives) |
| 6 | Gómez, "Tonal Description of Music Audio Signals," PhD Thesis, Universitat Pompeu Fabra, 2006 | Phase A chroma-based key estimation and comparison |
| 7 | Bernardes et al., "A Multi-Level Tonal Interval Space for Modelling Pitch Relatedness and Musical Consonance," J. New Music Research, 2016 | Phase A TIS theory |
| 8 | Harte et al., "Detecting Harmonic Change in Musical Audio," ACM MM 2006 | Phase A tonnetz/chroma computation |
| 9 | Sethares, "Tuning, Timbre, Spectrum, Scale," 1993 (Springer, 2nd ed. 2005) | Phase A roughness model (future extension) |
| 10 | Li et al., "Is Cosine-Similarity of Embeddings Really About Similarity?," arXiv:2403.05440, 2024 | Section 1.1 — why cosine on MLM embeddings is problematic |
| 11 | Comparative Analysis of Pretrained Audio Representations in Music Recommender Systems, RecSys 2024, arXiv:2409.08987 | Section 1.1 — MusiCNN outperforming SSL models for recommendation |
| 12 | MERT-v1-330M Model Card, HuggingFace m-a-p/MERT-v1-330M | Sections 0, 1.1 — MLM training objective, layer hierarchy |
