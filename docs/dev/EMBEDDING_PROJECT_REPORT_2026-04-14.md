# rbassist Embedding And Matching Project Report

Date: 2026-04-14
Branch: `codex/desktop-gui-bridge`
Report based on code through: `3db7e98`

## Executive Summary

This project started as an embedding-quality upgrade for rbassist: the system had a working MERT embedding pipeline, but it collapsed too much musical information into one track-level vector. Over the course of the work, it evolved into a safer multi-stage matching platform:

- The primary HNSW index contract stayed intact: one canonical 1024-dimensional `embedding` per track.
- New richer signals were added beside that primary vector instead of replacing it.
- Section embeddings now let rbassist understand DJ transition direction, especially late/outro into intro.
- Full-library section-sidecar backfill was run safely with checkpointing, resume, profiling hooks, and failed-track quarantine.
- Benchmark and diagnostic reporting were hardened so new signals are measured before being promoted.
- Harmonic chroma/tonnetz profiles are now available as an opt-in continuous key-compatibility signal.
- A read-only playlist-pair dataset exporter now gives the future learned-similarity model a safe training-data foundation.

The main idea stayed consistent: build a better musical atlas around each track without breaking the existing library, metadata, Rekordbox workflow, or recommendation index.

## Where We Started

Before the upgrade, rbassist already had a useful local recommendation foundation:

- `rbassist embed` loaded audio and used `m-a-p/MERT-v1-330M` to create a single 1024-dimensional vector per track.
- `rbassist index` built a cosine HNSW index from the canonical `embedding` field.
- `rbassist recommend` and `playlist-expand` used that vector plus metadata features like BPM, Camelot key, tags, bass contours, and rhythm contours.
- `data/meta.json` was the local truth store. Rekordbox was treated as an important read-only or audit source, not something to mutate casually.

The core weakness was not that MERT was the wrong model. The weakness was that rbassist was using MERT too narrowly:

- It only used the final hidden layer, even though MERT computes many hidden layers.
- It averaged intro, core, and late windows into one vector, losing the fact that DJ transitions are directional.
- It used raw cosine as the default similarity proxy, even though MERT is not trained as a contrastive similarity model.
- Camelot key matching was mostly binary, which made it useful as a gate but thin as a ranking signal.

The hard constraint was also clear from the start: do not break the primary 1024-dimensional embedding contract. That meant no primary-index replacement without proof.

## The Design Turn

The project moved from "replace or improve embeddings" to a two-stage retrieval design:

1. Stage 1 stays fast and stable.
   HNSW still queries the existing 1024-dimensional primary embedding.

2. Stage 2 gets smarter.
   Reranking can optionally use section embeddings, harmonic profiles, future learned similarity, and future tempo translation.

That design mattered because it gave us room to improve quality without forcing a full-library destructive rebuild or breaking the current UI and CLI behavior.

## Timeline Of The Work

### 1. Opt-In Embedding Upgrade

Commit: `8ca9edf` and follow-up hardening commits.

The first major implementation added the initial embedding upgrade surface:

- Section-aware MERT sidecar storage.
- Opt-in recommendation and playlist-expansion transition scoring.
- Opt-in layer-mix sidecar support.
- A benchmark harness and layer-mix training scaffold.

Meaning:

This created the "track atlas" idea. A track is no longer just one vector. It can now have sidecars for intro, core, late, layer-mix, and later harmonic/learned signals. The primary vector remained stable.

### 2. Section Sidecar Rollout And Backfill

The next work focused on making section embeddings safe in the real library:

- Section sidecars were standardized as `_intro.npy`, `_core.npy`, and `_late.npy`.
- `--section-embed --resume` became able to backfill missing section sidecars for tracks that already had primary embeddings.
- The section path reused the section-vector pass instead of doing duplicate MERT work.
- `--missing-section-sidecars` was added so the full library did not require a manually built 9980-track path list.

Live rollout evidence from the continuity log:

- A one-track pilot succeeded and changed only one `data/meta.json` row by adding section sidecar fields.
- A 25-track crate pilot under `C:\Users\hunte\Music\BREAKS\2024 july august` succeeded.
- The full section-sidecar backfill eventually completed with `10005` complete section sidecar sets out of `10008` primary embeddings.
- The remaining three gaps were one CUDA-failed audio file and two stale Demucs paths.

Meaning:

This is where the system became materially more DJ-aware. It can score "does this outro flow into that intro?" instead of only asking "are these whole tracks nearby?"

### 3. Resume, Quarantine, And Failure Recovery

During the full backfill, a CUDA illegal-memory-access fault occurred on:

`C:\Users\hunte\Music\HOUSE  TECH\Halloween 2021 downloads\AITCH - Wait.mp3`

The fix was not to manually edit the checkpoint or metadata. The safer fix was:

- Add failed-path checkpoint quarantine.
- Skip checkpoint-failed paths by default on `--missing-section-sidecars --resume`.
- Add `--retry-checkpoint-failures` for intentional retries.
- Resume from the same checkpoint and finish the rest.

Meaning:

This turned a fragile long-running GPU process into an operational workflow. One bad track no longer blocks thousands of good tracks.

### 4. Profiling Before Optimization

An opt-in profiler was added:

`--profile-embed-out`

It writes JSONL stage timings only when requested, including:

- load audio decode time
- decoded and trimmed samples
- duration cap
- source sample rate
- MERT flattened item count
- actual MERT batch size
- device
- section/layer/timbre flags
- MERT encode timing
- save timing
- checkpoint timing
- meta write timing

Meaning:

This deliberately postponed speculative optimization. Instead of guessing whether decode, batching, thermal behavior, or model architecture was the bottleneck, the code now has an evidence hook.

### 5. Benchmark And Section Rerank Hardening

Commit: `9c27db8`

Before moving to more advanced matching, the benchmark and diagnostics were tightened:

- Section benchmark rows now skip when section sidecars are requested but effectively unavailable.
- Diagnostics distinguish requested section scores from actually applied scores.
- Tight preset behavior was preserved when only adding section controls.
- Tests were expanded around section reranking, benchmark behavior, playlist expansion, and profiler output.

Meaning:

This made it harder for the system to fool us. A benchmark row can no longer look meaningful if there are no usable section pairs behind it.

### 6. Advanced Matching Plan

Commit: `c66e9e9`

Research then widened the roadmap into `ADVANCED_MATCHING_PLAN.md`:

- Learned similarity metrics for MERT embeddings.
- Tempo translation networks.
- Psychoacoustic harmonic compatibility beyond Camelot.

The key discovery was that raw cosine similarity is not the endgame for MERT. MERT is trained with an MLM-style objective, not a contrastive musical-similarity objective. That made learned similarity a high-value future target. The plan still recommended a safe order:

1. Harden benchmark and section truth layer.
2. Implement harmonic profiles first because librosa already supports them.
3. Build a read-only playlist-pair dataset.
4. Add learned similarity as an opt-in reranker.
5. Keep tempo translation as a later spike.

Meaning:

This changed the next phase from "just keep adding embeddings" to "build a better scoring stack." The goal became better musical judgment, not just more vectors.

### 7. Harmonic Profile Scoring

Commit: `6a6c9d4`

The first advanced matching implementation added opt-in chroma/tonnetz harmonic scoring:

- `chroma_profile`: 12 floats under `features`.
- `tonnetz_profile`: 6 floats under `features`.
- `rbassist analyze --harmonic-profiles`
- `rbassist embed --harmonic-profiles`
- `rbassist recommend --w-harmony`
- `rbassist playlist-expand --harmonic-key-score`

Important hardening:

- Default behavior stays unchanged.
- Camelot stays available and unchanged.
- Playlist expansion falls back to Camelot if harmonic profiles are missing.
- Profile-only analyze backfills avoid rewriting existing BPM, key, or cue state when the file signature already matches.

Meaning:

Key compatibility became a continuous opt-in score rather than only a binary compatibility relation. This should eventually let the ranking distinguish "technically compatible" from "really harmonically close."

### 8. Playlist-Pair Dataset Foundation

Commit: `3db7e98`

The next safe slice added the read-only dataset foundation for learned similarity:

- `rbassist/playlist_pairs.py`
- `scripts/export_playlist_pairs.py`
- `tests/test_playlist_pairs.py`

The exporter creates JSONL pair labels from resolved playlists:

- Adjacent same-playlist pairs: label `1.0`
- Same-playlist non-adjacent pairs: label `0.7`
- Different-playlist negatives:
  - `0.0` when BPM/key evidence says likely incompatible
  - `0.2` when tempo is similar but key is incompatible
  - `0.3` when tempo and Camelot are compatible, because it may be a false negative

It skips unresolved tracks and tracks without primary embeddings. It writes only requested output files and does not mutate `data/meta.json`, embeddings, indexes, checkpoints, or Rekordbox.

Meaning:

This gives the future learned similarity model local, DJ-behavior-derived training data without starting training prematurely.

## What The System Looks Like Now

At the current branch head, rbassist has these embedding and matching layers:

### Primary Embedding

- Field: `embedding`
- Shape: 1024-dimensional vector
- Role: canonical HNSW index input
- Status: unchanged contract

### Section Sidecars

- Fields: `embedding_intro`, `embedding_core`, `embedding_late`
- Shape: 1024-dimensional vectors
- Role: opt-in transition scoring, especially late/outro into intro
- Status: full-library backfill mostly complete, with three known remaining gaps

### Layer-Mix Sidecar

- Field: `embedding_layer_mix`
- Role: opt-in experimental sidecar
- Status: scaffolded, not promoted to primary ranking

### Harmonic Profiles

- Fields: `features.chroma_profile`, `features.tonnetz_profile`
- Shape: 12 floats and 6 floats
- Role: opt-in continuous harmonic/key compatibility
- Status: implemented, not live-backfilled across the library yet

### Playlist-Pair Labels

- Script: `scripts/export_playlist_pairs.py`
- Role: future training data for a learned similarity head
- Status: implemented as read-only exporter, no model training yet

## Why These Changes Matter

The changes mean rbassist is moving from a one-vector search tool toward a multi-evidence DJ recommendation engine.

The original system asked:

"Which tracks are close to this track's single MERT vector?"

The current system can increasingly ask:

"Which tracks are close enough in the primary embedding, flow well from outro to intro, make harmonic sense, fit the crate context, and reflect actual playlist behavior?"

That is a much better shape for DJ work.

## Safety And Reliability Lessons

The project also changed how we run long operations:

- Backups before live metadata backfills.
- Checkpoints for long embedding jobs.
- Resume by checkpoint instead of restarting.
- Failed-track quarantine instead of hand-editing metadata.
- Profiling before decode or micro-batch optimization.
- Read-only dataset and Rekordbox workflows before any apply path.
- Explicit tests around every new flag-gated behavior.

The most important operational lesson was the failed CUDA backfill. The system did not need a panic reset. It needed to preserve the checkpoint, quarantine the bad path, and continue.

## Current Validation Snapshot

The latest explicit validation suite passed:

```powershell
python -m pytest tests/test_playlist_pairs.py tests/test_harmonic_compatibility.py tests/test_embed_resume.py tests/test_embed_sections.py tests/test_section_rerank.py tests/test_layer_mix.py tests/test_benchmark_embeddings.py tests/test_recommend_index.py tests/test_playlist_expand.py
```

Result: `62 passed`

Compile validation passed:

```powershell
python -m compileall rbassist scripts tests\test_playlist_pairs.py tests\test_harmonic_compatibility.py tests\test_recommend_index.py
```

CLI help validation passed for:

- `rbassist analyze`
- `rbassist embed`
- `rbassist recommend`
- `rbassist playlist-expand`
- `scripts/export_playlist_pairs.py`

Known local validation quirk:

- Broad `python -m pytest` and `python -m pytest tests` hit a local pytest capture teardown error after collecting only two items. The explicit target suite is the current reliable validation source.

## What Is Still Not Done

The following are intentionally not promoted or complete yet:

- The failed `AITCH - Wait.mp3` track still needs a one-track diagnostic, likely with profiling and possibly CPU fallback.
- Two stale Demucs paths remain metadata/path hygiene follow-up rather than embedding failures.
- Harmonic profiles are implemented but still need a reviewed crate backfill before they affect real recommendations broadly.
- Learned similarity is not trained or integrated yet. The dataset exporter is the foundation.
- Tempo translation is still deferred. It has the highest compute cost and should wait until the learned-similarity path is better established.
- Layer-mix remains opt-in and experimental.
- The primary HNSW index has not been replaced, by design.

## Recommended Next Moves

1. Run a harmonic profile pilot on a reviewed crate:

```powershell
rbassist analyze "C:\Users\hunte\Music\<reviewed crate>" --harmonic-profiles
```

Then compare:

```powershell
rbassist recommend "Artist - Track" --w-harmony 0.15
rbassist playlist-expand --playlist "<playlist>" --harmonic-key-score --preview-json data\runlogs\harmonic_expand_preview.json
```

2. Dry-run playlist-pair export:

```powershell
python scripts\export_playlist_pairs.py --source db --dry-run --max-playlists 10
```

If counts look sane, export:

```powershell
python scripts\export_playlist_pairs.py --source db --out data\training\playlist_pairs.jsonl --summary data\training\playlist_pairs_summary.json
```

3. Run the one-track diagnostic for the quarantined CUDA failure:

```powershell
python -m rbassist.cli embed "C:\Users\hunte\Music\HOUSE  TECH\Halloween 2021 downloads\AITCH - Wait.mp3" --section-embed --profile-embed-out data\runlogs\aitch_wait_profile.jsonl --device cuda
```

If CUDA still fails, retry as a deliberate CPU diagnostic, not as part of a full-library backfill.

4. After the pair dataset is inspected, implement the learned similarity head as an opt-in reranker.

## Bottom Line

The project has moved from a single-vector recommendation system into a cautious, evidence-driven matching platform. The most valuable thing preserved is the stability of the existing library and index. The most valuable thing added is the ability to grow richer musical judgment around that stable base.

The system is not "finished" in the sense of having a trained learned metric or tempo translator. But it is now much better prepared for those things: safer rollout mechanics, better diagnostics, section-aware sidecars, harmonic scoring, and the beginning of library-native training data.
