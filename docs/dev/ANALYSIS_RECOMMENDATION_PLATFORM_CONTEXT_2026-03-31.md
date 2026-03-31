# Analysis + Recommendation Platform Context (Handoff Brief)

Date: 2026-03-31  
Audience: next agent performing mathematical validity / optimization review.

## 1) Why this exists

This document is a **holistic background + workflow brief** for rbassist's analysis and recommendation stack so a successor agent can evaluate whether current scoring/ranking behavior is mathematically optimal for DJ crate expansion and seed-track recommendation.

Project continuity confirms that ingest throughput is mostly complete and that current product focus is reliability/safety plus recommendation/crate-quality improvements, not raw embedding catch-up. That means model/ranking quality and performance now matter more than first-pass ingestion throughput.

## 2) Product/architecture summary (analysis + recommendation surfaces)

The active stack is local-first and uses:

- **Embedding:** MERT (`m-a-p/MERT-v1-330M`) with optional OpenL3 timbre branch.
- **Analysis features:** BPM, Camelot key, cues, and optional heuristics (samples score, bass contour, rhythm contour).
- **Retrieval:** HNSW (cosine space) index over track vectors.
- **Recommendation surfaces:**
  - single-seed recommendation (`rbassist recommend`)
  - sequence recommendation (`rbassist recommend-sequence`)
  - playlist expansion/crate builder (`rbassist playlist-expand` + NiceGUI Crate Expander page) using shared backend.

The roadmap and continuity logs show explicit evolution from simple ANN retrieval to a **hybrid reranking system** with presets, weighted components, filtering controls, diversity/MMR-like selection, and anti-repetition penalties.

## 3) Data + state contracts that drive correctness

### 3.1 Primary metadata contract

- `data/meta.json` is treated as primary local metadata truth.
- Rekordbox is intentionally secondary truth for audit/reconciliation.

This matters mathematically because ranking features (BPM/key/tags/title/artist) are read from meta rows, so stale/incomplete metadata directly changes scores and filter behavior.

### 3.2 Required fields used by ranking

At minimum, useful recommendation requires:

- `embedding` path and loadable vector for seed and candidates
- optional but influential: `bpm`, `key`, `mytags`, and feature contours

In practice the system is robust to missing fields (it falls back), but that lowers component signal and effectively over-weights ANN proximity.

## 4) End-to-end workflow (how information flows)

## 4.1 Embed stage (`rbassist/embed.py`)

- Resolves compute device with safe fallback (`cuda`/`rocm`/`mps`/`cpu`).
- Encodes audio through MERT hidden-state mean pooling.
- Canonical default is 120s bounded pass with deterministic constraints from CLI.
- Supports multi-window sampling profiles and optional timbre embedding branch.
- When timbre is enabled, OpenL3 output is blended with MERT (70/30).

Current design intent: robust local embedding generation with bounded compute and deterministic defaults.

## 4.2 Analysis stage (`rbassist/analyze.py` + `rbassist/features.py`)

- Estimates tempo from onset envelope median tempo.
- Estimates key via chroma vs Krumhansl/Kessler profiles, maps to Camelot.
- Optionally adds cues.
- Optionally enriches with heuristic features:
  - samples score
  - bass contour (+ reliability)
  - rhythm contour (+ reliability)

These features are not always present. Current rankers use them opportunistically, so missingness creates per-track feature sparsity.

## 4.3 Index stage (`rbassist/recommend.py`)

- Builds or incrementally grows HNSW index.
- Uses chunked vector insertion for stability.
- Uses safe embedding load + dimension checks.
- Persists label/path mapping in `data/index/paths.json`.

Incremental path is tuned for practical maintenance (resize with slack, append new labels).

## 4.4 Single-seed recommendation (`rbassist/recommend.py`)

Pipeline:

1. Resolve seed track.
2. Load seed vector and seed metadata.
3. ANN query (`k = top + 50`) on cosine index.
4. Candidate filter gates:
   - optional Camelot compatibility
   - tempo match with optional half/double-time
5. Optional weighted rerank using:
   - ANN relevance (`1 - dist`)
   - samples score
   - bass contour similarity
   - rhythm contour similarity
6. Return top N table.

Important: if no weights are supplied, ordering defaults to pure ANN distance after hard filters.

## 4.5 Playlist expansion (`rbassist/playlist_expand.py`)

This is currently the most advanced recommendation logic.

### Phase A: prepare candidate workspace

- Resolve seed tracks from Rekordbox/manual inputs.
- Require at least 3 mapped seed tracks and at least one seed embedding.
- Compute seed statistics: centroid, median BPM, seed keys, core tags, seed vectors.
- Generate two candidate pools:
  - centroid ANN hits
  - seed-coverage ANN hits (per-seed nearest neighbors with support counts)
- Merge both pools into `PreparedCandidate` objects.
- Precompute component scores per candidate.

### Phase B: rerank + select

- Apply strategy selector (`blend`, `centroid`, `coverage`).
- Apply optional filters (key mode, required tags).
- Compute weighted base score across normalized components:
  - ann_centroid
  - ann_seed_coverage
  - group_match
  - bpm_match
  - key_match
  - tag_match
- Greedy rerank loop applies:
  - diversity penalty via max similarity to selected/seed vectors (MMR-like)
  - anti-repetition penalty using artist/title/version signature heuristics
- Emits diagnostics for transparency (selected counts, applied controls, normalized weights, anti-repetition totals).

### Preset behavior

- `tight`: stricter tempo/key, lower diversity.
- `balanced`: default mix.
- `adventurous`: looser filters, higher diversity and tag exploration.

## 5) Current vectors and product thinking (as evidenced in repo)

1. **Safety and determinism first**: defaults and workflows avoid destructive writes and prefer reviewable artifacts.
2. **Shared backend for CLI + GUI**: crate expansion logic consolidated in `playlist_expand.py` to reduce drift.
3. **Hybrid ranking over pure ANN**: explicit move toward multi-component scoring and explainability diagnostics.
4. **Diversity/anti-repetition as practical DJ constraints**: not just nearest-neighbor closeness.
5. **Performance is now a known bottleneck vector** for large candidate pools; continuity notes repeated index loading + cosine work + signature processing as hot spots.
6. **Future direction is section-aware/transition-aware sequencing**, but current system is append-style crate growth.

## 6) Mathematical formulation of current scoring

## 6.1 Candidate component score

For candidate `c`, current crate-expansion base score is approximately:

\[
S_{base}(c) = \sum_i w_i \cdot f_i(c)
\]

where components include:

- `f_ann_centroid` = cosine similarity(candidate, seed centroid)
- `f_ann_seed_coverage` = support_count / seed_count
- `f_group_match` = mean of top-k seed similarities
- `f_bpm_match` = piecewise similarity within tempo tolerance (with optional x2/x0.5 folds)
- `f_key_match` = Camelot relation score (when enabled)
- `f_tag_match` = Jaccard overlap on seed core tags

weights are normalized to sum to 1.

## 6.2 Final greedy selection objective

At each selection step, system approximates:

\[
S_{final}(c) = S_{base}(c) - \lambda \cdot \max_{s \in Selected \cup Seeds} \text{sim}(c, s) - P_{repeat}(c)
\]

where:

- `\lambda` is diversity control (`0..1`)
- `P_repeat` is heuristic anti-repetition penalty from title/artist/version signatures

Selection is greedy across candidates until `add_count` reached.

This is a practical MMR-like heuristic, not a globally optimized set objective.

## 7) What is strong already

- Sensible decomposition into retrieval + reranking + constrained selection.
- Clear operator controls (mode/strategy/weights/key mode/tempo/tags/diversity).
- Deterministic enough for reproducible DJ workflows.
- Diagnostics emitted in output JSON make post-hoc analysis possible.

## 8) Mathematical gaps / risk areas for next-agent review

1. **No learned calibration between components**
   - Weight defaults are heuristic, not fitted against outcomes.
2. **Feature missingness bias**
   - Missing tags/key/features reduce component influence unpredictably.
3. **Greedy selection vs global optimum**
   - MMR-like greedy may miss better full-set utility.
4. **Tempo/key scoring shape is hand-crafted**
   - Could be replaced by smoother probabilistic compatibility models.
5. **Candidate generation ceiling**
   - Fixed pool may truncate long-tail good candidates for diverse sets.
6. **No formal offline metric suite in-tree yet**
   - Limits confidence when changing weights/objectives.

## 9) Recommended mathematical evaluation plan (handoff-ready)

## 9.1 Define objective metrics first

For each generated crate:

- relevance proxy: mean seed similarity
- coverage proxy: fraction of seeds with >=1 close supported addition
- diversity proxy: average pairwise dissimilarity among additions
- transition safety proxy: BPM/key compatibility violation rate
- repetition proxy: same-artist/version clustering rate

## 9.2 Build replay harness on saved diagnostics

Use existing preview JSON diagnostics from playlist expansion to replay scoring offline and compare:

- current heuristic weights/presets
- calibrated linear models
- alternative diversification objective (e.g., facility-location + constraints)

## 9.3 Ablation matrix

Run controlled ablations:

- ANN only
- ANN + tempo/key filters
- full component score without diversity
- full score + diversity
- full score + diversity + anti-repetition

This quantifies each mechanism's marginal value.

## 9.4 Candidate-pool sensitivity

Evaluate pool sizes (e.g., 250/500/1000/2000) for quality-runtime tradeoff, since current continuity data already shows meaningful runtime growth at higher pools.

## 9.5 Robustness checks

- sparse metadata scenarios (missing key/tags)
- genre-specific subsets
- small-seed (3 tracks) vs large-seed (50 tracks) behavior

## 10) Concrete near-term improvements (without full redesign)

1. Cache shared ANN/index/path map objects across expansion runs.
2. Pre-normalize vectors and cache repeat signatures.
3. Add an offline benchmark script producing a stable scorecard per algorithm variant.
4. Add confidence flags to each added track (e.g., high/medium/low) based on component agreement.
5. Separate hard constraints from soft scores explicitly in diagnostics.

## 11) Scope boundaries for successor agent

### In-scope for mathematical reviewer

- scoring function behavior
- diversification objective quality
- component calibration and normalization
- metric design and benchmark harness

### Out-of-scope unless explicitly requested

- destructive metadata rewrite flows
- Rekordbox write/apply flows
- major UI framework migrations

## 12) Key files to read first (ordered)

1. `rbassist/playlist_expand.py` (primary ranking + selection logic)
2. `rbassist/recommend.py` (index + single-seed reranking)
3. `rbassist/analyze.py` and `rbassist/features.py` (analysis feature provenance)
4. `rbassist/embed.py` (embedding generation choices)
5. `tests/test_playlist_expand.py` and `tests/test_recommend_index.py` (behavioral invariants)
6. `docs/dev/CONTINUITY_LOG.md` and `WISHLIST.md` (current optimization vectors)

## 13) Bottom-line assessment

The current platform is a **reasonable heuristic hybrid recommender** tuned for practical DJ constraints, with strong safety and transparency characteristics. It is likely **good enough operationally** but **not yet mathematically optimal** in a strict sense because weights/objectives are hand-tuned and not benchmark-calibrated against explicit quality metrics. The most valuable next step is an offline evaluation harness with ablations and calibrated scoring comparisons, built on the existing diagnostics-rich workflow.
