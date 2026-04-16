# rbassist Analysis + Recommendation Platform Context (2026-03-31)

## Audience and intent

This document is a technical handoff for the next agent to evaluate whether rbassist’s current recommendation math is optimal for DJ workflows, and where to improve it with minimal safety risk.

It focuses on:
- how data is produced (embed/analyze/index)
- how recommendations and crate expansion are computed
- the current mathematical objective(s)
- known constraints and failure modes
- a practical evaluation and optimization roadmap

---

## 1) Product posture and safety model

rbassist is intentionally local-first and safety-first for a real DJ library. The operational center of truth is local metadata in `data/meta.json`, with Rekordbox used as a secondary source for audit/reconciliation rather than a primary write target. This safety framing explains why most workflows are read-first, dry-run-first, and fail-closed around ambiguous mapping/relinking decisions.

Why this matters for recommendation math:
- algorithm changes cannot assume perfect metadata cleanliness
- ranking should degrade gracefully when BPM/key/tags/features are sparse
- deterministic, reviewable behavior is preferred over opaque "black-box" optimization

---

## 2) End-to-end workflow graph (holistic)

### A. Ingest + representation
1. **Audio discovery**: recursive audio walk over configured roots.
2. **Embedding**: MERT (`m-a-p/MERT-v1-330M`) on canonical 24 kHz audio with windowed sampling and averaging.
3. **Optional timbre branch**: OpenL3 branch blended into final embedding (`0.7 * MERT + 0.3 * timbre`).
4. **Persistence**: embedding vectors written to `data/embeddings`, references stored in `data/meta.json`.

### B. Metadata analysis
1. **Tempo/key estimation**: librosa onset + chroma/CQT heuristics.
2. **Cue proposal**: optional cue extraction.
3. **Auxiliary features**:
   - samples heuristic score
   - bass contour + reliability
   - rhythm contour + reliability
4. **Persistence** in `data/meta.json` under per-track feature dictionaries.

### C. Search index
1. Collect valid embedding vectors from `meta.json`.
2. Build or incrementally update HNSW cosine index (`data/index/hnsw.idx`).
3. Maintain path label map (`data/index/paths.json`).

### D. Recommendation surfaces
1. **Single-seed recommend** (`rbassist recommend`): ANN retrieval + tempo/key filtering + optional weighted rerank.
2. **Multi-seed sequence recommend**: mean seed vector + ANN retrieval.
3. **Playlist/crate expansion** (`rbassist playlist-expand`, NiceGUI Crate Expander): seed playlist resolution + candidate generation (centroid/coverage/blend) + feature-aware rerank + diversity + anti-repetition penalty.

---

## 3) Core data contract used by ranking

Each track row in `meta["tracks"][path]` can include:
- `embedding`: path to `.npy` vector
- `bpm`, `key`, `key_name`
- `artist`, `title`
- `mytags` (and sometimes tags)
- `features.samples`
- `features.bass_contour.contour`
- `features.rhythm_contour.contour`

Ranking quality is strongly sensitive to coverage of these fields. Embedding coverage is required for ANN; the rest act as rerank constraints/signals.

---

## 4) Current mathematical objectives (what it optimizes today)

## 4.1 Single-seed recommend objective

Pipeline:
1. Resolve seed to canonical track path.
2. Retrieve top `k = top + 50` ANN neighbors by cosine distance.
3. Hard-filter candidates on:
   - Camelot compatibility (if enabled)
   - BPM tolerance / doubletime rule (if enabled)
4. Sort by either:
   - ANN distance ascending (default), or
   - weighted score if any manual weight is non-zero.

Weighted score components currently available:
- `ann`: `1 - distance`
- `samples`: precomputed samples heuristic
- `bass`: DTW contour similarity
- `rhythm`: DTW contour similarity

So mathematically this is a two-stage constrained ranking:
- **Feasible set** = ANN neighbors passing key/tempo constraints
- **Objective** = maximize weighted linear combination of similarity features (or minimize ANN distance if no weights)

## 4.2 Playlist expansion objective

Playlist expansion has a richer objective with two phases.

### Phase 1: candidate generation
- `centroid`: nearest neighbors to mean seed vector
- `coverage`: union of per-seed neighbors scored by support count and best distance
- `blend`: combines both sources in a prepared workspace

### Phase 2: reranking and selection
Candidates receive component scores driven by:
- ANN closeness
- seed-group support/coverage
- BPM compatibility
- harmonic compatibility (`key_mode`: off/soft/filter)
- tag overlap (especially core tags)

Then final selected additions are passed through diversity rerank (MMR-like) plus anti-repetition penalties based on artist/title-stem/version signatures.

This is effectively a multi-objective tradeoff compressed into weighted scalar scoring plus constrained greedy rerank.

---

## 5) Strong points of current approach

1. **Operationally robust**
   - Works even when optional features are missing.
   - Falls back from ANN to brute force when needed.

2. **DJ-aware constraints baked in**
   - Explicit BPM + Camelot rules are easy to reason about.
   - Presets (`tight`, `balanced`, `adventurous`) encode practical crate-building intent.

3. **Deterministic + tunable**
   - Same inputs and controls give stable outputs.
   - Weight/strategy/filter controls expose behavior without retraining models.

4. **Safety alignment**
   - Read-only playlist loading and conservative mapping logic preserve trust in local state.

---

## 6) Where the math is likely suboptimal today

1. **No learned calibration layer**
   - Weights are hand-tuned, not fit against user outcomes (accept/reject, play history, transition success).

2. **ANN distance calibration drift**
   - Distance scales may vary across crates/genres, but thresholds/weights are global.

3. **Hard filtering can over-prune**
   - Strict BPM/key filters can remove valid creative transitions before rerank can evaluate them.

4. **Linear score mixing limits expressiveness**
   - Interaction terms (e.g., “tempo mismatch acceptable when tag overlap is high and support count is strong”) are not modeled.

5. **Diversity heuristic is local-greedy**
   - MMR-style greedy selection is good but not globally optimal for long crate objectives.

6. **Limited closed-loop evaluation instrumentation**
   - There is no standardized offline ranking benchmark with relevance labels or pairwise preference sets.

---

## 7) Suggested mathematical evaluation framework for the next agent

## 7.1 Define explicit optimization targets

Use at least two objective families:
1. **Relevance objective**: does candidate fit seed/playlist intent?
2. **Set-quality objective**: does final crate have useful diversity/flow?

Potential measurable proxies:
- precision@k, nDCG@k using human-labeled relevant tracks
- catalog coverage and artist/release entropy in expanded crates
- transition compatibility metrics (tempo/key gap distributions)
- repeat-penalty incidence in selected results

## 7.2 Build a reproducible benchmark harness

Construct benchmark bundles from local `meta.json` + curated seed playlists:
- fixed seed sets
- fixed candidate universe snapshots
- frozen control configs
- human adjudication files (relevant/neutral/bad)

Then run A/B comparisons between:
- baseline (current preset)
- candidate scoring variants
- candidate selection variants

## 7.3 Priority experiments (lowest risk to highest)

### Tier 1: no-behavior-break, calibration experiments
- score normalization per component (z-score/minmax within candidate pool)
- dynamic weight rescaling by metadata sparsity
- softening hard filters into penalties in `soft` mode

### Tier 2: objective/rerank upgrades
- pairwise learned-to-rank model on top of existing features
- constrained optimization for crate-level selection (submodular/ILP approximations)

### Tier 3: representation upgrades
- per-genre or per-BPM-band embedding calibration
- transition-conditioned embeddings (sequence-aware) for set-building

---

## 8) Immediate recommendations (practical next slices)

1. **Add ranking telemetry output** (JSON per run): feature vector per candidate, filtered reasons, final score decomposition.
2. **Introduce a benchmark CLI** for offline replay of seed scenarios.
3. **Add per-component normalization** before weighted sum in playlist expansion rerank.
4. **Compare hard-filter vs soft-penalty behavior** in balanced preset on a labeled set.
5. **Document baseline metrics** in one stable report format so future agents can measure true progress.

These steps preserve current UX/CLI semantics while enabling rigorous mathematical improvement.

---

## 9) Constraints and do-not-break boundaries for follow-on agents

- Preserve local-data safety posture (`meta.json` primary; backup/dry-run defaults for repair workflows).
- Preserve deterministic outputs for same inputs unless explicitly versioning scoring behavior.
- Avoid requiring cloud dependencies for core recommendation path.
- Keep CLI + NiceGUI controls consistent with backend defaults/presets.

---

## 10) File map for this domain (starting points)

Core ranking and retrieval:
- `rbassist/recommend.py`
- `rbassist/playlist_expand.py`

Feature production:
- `rbassist/embed.py`
- `rbassist/analyze.py`
- `rbassist/features.py`

User-facing entry points:
- `rbassist/cli.py`
- `rbassist/ui/pages/discover.py`
- `rbassist/ui/pages/crate_expander.py`

Project continuity and roadmap context:
- `README.md`
- `docs/dev/PROJECT_CONTINUITY.md`
- `docs/dev/MASTER_PRODUCT_EXECUTION_PLAN_2026-03-02.md`
- `docs/dev/KEEPER_MANIFEST_ACTIVE_FILES.md`
- `docs/dev/AGENT_WORKFLOW_LANES.md`

---

## 11) Handoff summary for "is this mathematically best?"

Short answer: **not yet**—but the current design is a strong, safe heuristic baseline with clear seams for formal optimization.

The right next move is not a deep refactor; it is to instrument and benchmark the existing scoring stack first, then introduce calibrated/learned ranking layers only where they show measurable gains against DJ-relevant metrics.

---

## 12) Embedding strategy research retry (2026-04-12)

This addendum retries the representation-learning part of the handoff. The earlier report explained the recommendation math but did not go deep enough on whether the current MERT embedding strategy is the right representation layer for DJ similarity and crate expansion.

### 12.1 Current implementation facts

Current rbassist embedding behavior:
- Default model: `m-a-p/MERT-v1-330M`.
- Input rate: audio is resampled to 24 kHz before MERT inference.
- Pooling: `MertEmbedder.encode_array` requests `output_hidden_states=True`, takes the final hidden state only, and mean-pools over time into one vector.
- Default track sampling: long tracks are represented by intro/core/late windows rather than one contiguous clip. The current long-track budget is roughly 10 s intro, 60 s core, and 10 s late; tracks from 80-140 s use a shorter 10/40/10 pattern; short tracks use the whole track.
- Persistence: vectors are saved as `float16` `.npy` files; `meta.json` stores the embedding path and source label.
- Optional timbre branch: when enabled, OpenL3 is run on selected windows and saved separately. If its vector shape matches MERT, the final vector is `0.7 * MERT + 0.3 * timbre`; otherwise the code falls back to a timbre-only final vector.
- Retrieval: recommendations and playlist expansion query an HNSW cosine index, then rerank/penalize with BPM, Camelot key, tag overlap, seed coverage, diversity, and anti-repetition logic.

That means the current mathematical representation is: one global audio vector per track, produced by final-layer MERT time pooling over selected windows, optionally replaced/blended with an OpenL3-derived timbre vector. This is a useful baseline, but it is not yet a validated optimum.

### 12.2 What the external research changes

**MERT remains a defensible baseline.** The MERT paper describes a music-specific self-supervised model trained with masked language modeling, using acoustic RVQ-VAE and musical CQT teacher signals. The v5 arXiv record says it was accepted by ICLR 2024 and reports strong performance across 14 music-understanding tasks. The Hugging Face model card lists `MERT-v1-330M` as a 330M-parameter, 24-layer, 1024-dim, 75 Hz, 24 kHz model trained on 160K hours, so rbassist's model choice is well grounded for local audio similarity.

**The current layer-pooling choice is the biggest open question.** The MERT model card explicitly says different transformer layers can perform differently by task and demonstrates reducing all 25 hidden-state layers over time, then optionally learning a weighted layer average. rbassist currently takes only `hidden_states[-1]`. That is not wrong, but it is an untested choice. The next agent should benchmark last-layer pooling against last-N-layer pooling and a frozen/learned scalar layer mix before changing ranking weights.

**The current track-level average may blur DJ-relevant structure.** Intro/core/late averaging is better than a single beginning clip, but DJ usage often cares about phase: mix-in texture, peak/drop body, breakdown, and mix-out compatibility. A single averaged vector can collapse a useful intro with an incompatible drop, or vice versa. The safer representation upgrade is not fine-tuning first; it is storing per-window vectors and letting recommendation modes choose centroid, max similarity to any window, or phase-aware scoring.

**OpenL3 should be treated as late-fusion unless calibrated.** OpenL3 is an older audio/image embedding family based on Look, Listen and Learn; its docs describe 1-second audio embedding frames, 48 kHz resampling, and 512 or 6144 dimensional embeddings. It can add useful timbre/texture signal, but raw-vector blending with MERT assumes the two vector spaces are commensurate. That should be tested against normalized score-level fusion first: compute MERT cosine and OpenL3 cosine separately, normalize within the candidate pool, then combine scores.

**MuQ is the most obvious 2025-era sidecar benchmark.** MuQ uses Mel Residual Vector Quantization and reports stronger results than previous self-supervised music representation models, with MuQ-MuLan adding a contrastive music-text embedding model. Its official repo also uses 24 kHz audio and releases a roughly 300M MuQ model plus a MuQ-MuLan model. That makes MuQ a practical sidecar experiment because it can be compared to MERT without redesigning the rest of rbassist's ANN/rerank stack.

**Text-audio models are additive, not a replacement for seed-audio similarity.** MuLan and CLAP-style models are valuable for query-by-description, tag lane expansion, and "warm-up / peak-time / dark / vocal" role prompts. They should not replace MERT for seed-to-seed audio similarity until a local benchmark shows better playlist leave-one-out behavior. MuLan is especially relevant conceptually because it was trained to link music audio with free-form natural-language descriptions, but rbassist's current need is mostly audio-to-audio continuity.

### 12.3 Recommended benchmark matrix

Keep the current embedding as baseline `E0`. Add candidates as sidecar embeddings or sidecar scores so no existing library state is overwritten:

| ID | Candidate | What it tests | Risk |
| --- | --- | --- | --- |
| `E0` | Current MERT final layer + intro/core/late mean | Existing production baseline | None |
| `E1` | MERT mean of last 4 layers | Whether final layer is too task-specific | Low |
| `E2` | MERT learned/frozen scalar mix over all layers | Whether layer aggregation helps rbassist labels | Medium if learned |
| `E3` | Per-window MERT vectors with query-time aggregation | Whether DJ phase matters | Low/medium storage cost |
| `E4` | MERT score + OpenL3 score late fusion | Whether timbre helps without vector-space mixing | Low |
| `E5` | MuQ sidecar embedding | Whether newer SSL music embedding improves MIR similarity | Medium dependency/model cost |
| `E6` | MuQ-MuLan or MuLan text-audio score | Whether tag/prompt lanes improve expansion | Medium, separate UX path |

Use a fixed seed playlist benchmark before any production switch:
- leave-one-out recovery from curated playlists: remove one seed track, rank the catalog, measure whether held-out tracks appear high
- precision/nDCG against manually accepted/rejected candidate sets
- transition metrics: BPM/key compatibility distributions, plus penalties for over-filtering valid creative transitions
- diversity metrics: artist/title-stem entropy, duplicate/version penalty incidence, and crate coverage
- runtime/storage metrics: embedding time per track, index size, query latency, and UI rerank responsiveness

### 12.4 Practical next implementation slice

1. Add embedding metadata fields before changing math: `embedding_schema_version`, `model_id`, `sample_rate`, `window_profile`, `layer_pooling`, `pooling_strategy`, `timbre_branch`, `dtype`, and `created_at`.
2. Add a read-only benchmark command that can replay seed playlists against a frozen `meta.json`/`paths.json` snapshot and emit per-candidate score decompositions.
3. Add an experimental embedding writer that stores MERT per-window vectors beside the existing final vector, without changing `info["embedding"]`.
4. Add late-fusion scoring for MERT/OpenL3 as an experiment flag in playlist expansion, normalizing component scores within the candidate pool.
5. Only after benchmark evidence, decide whether to migrate the default embedding path or keep sidecar embeddings for specific recommendation modes.

### 12.5 Research-grounded conclusion

The best next mathematical question is not "is MERT good?" It is "which MERT representation and aggregation policy is best for DJ playlist similarity?"

Keep MERT-v1-330M as the baseline because it is music-specific, local, already integrated, and aligned with the current 24 kHz pipeline. Do not fine-tune first. The highest-signal next work is layer-pooling comparison, phase-aware multi-vector storage, OpenL3 score-level calibration, and a MuQ sidecar benchmark.

Sources used for this retry:
- [MERT arXiv paper](https://arxiv.org/abs/2306.00107)
- [MERT-v1-330M Hugging Face model card](https://huggingface.co/m-a-p/MERT-v1-330M)
- [OpenL3 documentation](https://openl3.readthedocs.io/en/stable/tutorial.html)
- [MARBLE benchmark OpenReview page](https://openreview.net/forum?id=2s7ZZUhEGS&noteId=6pMj2WRAfG)
- [MuQ arXiv paper](https://arxiv.org/abs/2501.01108)
- [MuQ official repository](https://github.com/tencent-ailab/MuQ)
- [MuLan Google Research publication page](https://research.google/pubs/mulan-a-joint-embedding-of-music-audio-and-natural-language/)
- [Microsoft CLAP repository](https://github.com/microsoft/CLAP)
