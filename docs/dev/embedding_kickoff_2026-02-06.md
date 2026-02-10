# Embedding Kickoff Plan (2026-02-06)

## Scope

Start the large-library embedding recovery using the new resumable controls:

- `--paths-file`
- `--resume`
- `--checkpoint-file`
- `--checkpoint-every`
- structured failed-track logging (JSONL)

Repository: `C:\Users\hunte\Music\rbassist`

## Baseline Findings

Initial audit before kickoff (`audit_meta_health.py`):

- `tracks_total`: 13,464
- `embedding_ok`: 3,082
- `embedding_gap_total`: 10,382
- `missing_embedding_ref`: 10,382
- `embedding_file_missing`: 0

Initial gap scan (`list_embedding_gaps.py --music-root C:\Users\hunte\Music`):

- `audio_files_scanned`: 12,116
- `pending_embedding_total`: 10,704
- `missing_meta_total`: 6,494
- `missing_embedding_ref_total`: 4,210
- `stale_meta_paths_total`: 3,817
- chunk files generated: `data/pending_embedding_paths.part001.txt` ... `part006.txt`

## Blocker Found + Resolved

Embedding startup failed on model import due to incompatible environment packages:

- `torch`: `2.8.0+cpu`
- `torchvision`: `0.2.0` (too old, missing `InterpolationMode`)

Action taken:

- uninstalled broken `torchvision` package (`python -m pip uninstall -y torchvision`)

After removal, MERT embedding startup works.

## Kickoff Execution Completed

1. Smoke run (10-path list, resumable):
   - command: `python -m rbassist.cli embed --paths-file data/pending_embedding_paths.smoke10.txt --resume --checkpoint-file data/embed_checkpoint_smoke.json --checkpoint-every 2 --num-workers 1`
   - result: `queued=9`, `succeeded=9`, `failed=0`

2. Wave 1 run (first 50 pending paths):
   - command: `python -m rbassist.cli embed --paths-file data/pending_embedding_paths.wave1_50.txt --resume --checkpoint-file data/embed_checkpoint_wave1.json --checkpoint-every 5 --num-workers 2`
   - result: `queued=39`, `succeeded=39`, `failed=0`, `skipped(existing)=10`

Artifacts:

- `data/embed_checkpoint_smoke.json`
- `data/embed_checkpoint_wave1.json`
- `data/pending_embedding_paths.txt` (regenerated)
- `data/pending_embedding_paths.part001.txt` ... `part006.txt`

## Current State After Kickoff

Post-kickoff audit (`audit_meta_health.py`):

- `tracks_total`: 13,499
- `embedding_ok`: 3,130
- `embedding_gap_total`: 10,369

Post-kickoff gap scan:

- `pending_embedding_total`: 10,656
- `missing_meta_total`: 6,480
- `missing_embedding_ref_total`: 4,176

Net progress in this kickoff:

- `pending_embedding_total`: down by 48
- checkpointed resumable workflow validated on real files

## Concrete Next Implementation Steps

1. Run chunked backlog processing end-to-end with per-chunk checkpoints:
   - `python scripts/run_embed_chunks.py --repo C:\Users\hunte\Music\rbassist --chunk-glob "data/pending_embedding_paths.part*.txt" --checkpoint-dir data/checkpoints --checkpoint-every 50 --num-workers 2`

2. Keep failure triage loop tight after each chunk:
   - inspect `*_failed.jsonl` files
   - rerun failed subsets with a dedicated paths file

3. Address `missing_meta_total` in parallel:
   - continue embedding from `pending_embedding_paths.*` lists, which auto-creates new track entries

4. Add stale-meta hygiene workflow:
   - review `stale_meta_paths_total` (3,817)
   - decide policy (retain archive entries vs prune dead paths)

5. Re-run health audits after each chunk batch and append deltas to this file.

## Notes

- Current embedding runs are CPU mode on this machine.
- Warnings about `audioread` fallback and `nnAudio` are non-blocking for current runs.
- Canonical duration guard is enforced; non-default `--duration-s` is rejected.
