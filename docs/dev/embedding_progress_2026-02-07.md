# Embedding Progress Update (2026-02-07)

## Summary

Continuation of the resumable embedding project on **Saturday, February 7, 2026**.

## Runs Completed

1. Wave 3 (`data/pending_embedding_paths.wave3_300.txt`)
   - checkpoint: `data/embed_checkpoint_wave3.json`
   - result: `queued=296`, `succeeded=287`, `failed=9`
   - failed log: `data/embed_checkpoint_wave3_failed.jsonl`

2. Wave 4 (`data/pending_embedding_paths.wave4_60.txt`)
   - checkpoint: `data/embed_checkpoint_wave4.json`
   - result: `queued=56`, `succeeded=50`, `failed=6`
   - failed log: `data/embed_checkpoint_wave4_failed.jsonl`

3. Wave 5 (`data/pending_embedding_paths.wave5_200.txt`)
   - checkpoint: `data/embed_checkpoint_wave5.json`
   - result: `queued=196`, `succeeded=196`, `failed=0`

## Pipeline Improvements Applied During This Session

1. Fixed pending-list false positives caused by normalized-path collisions (`C:\...` vs `C:/...`) in gap analysis logic.
2. Excluded known non-audio artifacts from queue generation:
   - AppleDouble files (`._*`)
   - `__MACOSX` archive metadata paths
3. Added exclude-list support to pending-list generation and created:
   - `data/embed_exclude_paths.txt` (known corrupted files from failed logs)

## Metrics

Baseline pending before this continuation:
- `pending_embedding_total=10656`

After wave 5 + queue cleanup:
- `pending_embedding_total=7159`
- Net reduction this continuation: **3497**

Embedding health snapshot (`audit_meta_health.py`) after wave 5:
- `tracks_total=13976`
- `embedding_ok=3665`
- `embedding_gap_total=10311` (meta-only perspective)

Gap scan snapshot (music-root scan, exclude list enabled):
- `audio_files_scanned=10830`
- `pending_embedding_total=7159`
- `missing_meta_total=4727`
- `missing_embedding_ref_total=2432`

## Operational Files

- Current pending list: `data/pending_embedding_paths.txt`
- Current chunks: `data/pending_embedding_paths.part001.txt` ... `part004.txt`
- Exclude list: `data/embed_exclude_paths.txt`

## Next Command

Use this to continue chunked processing:

```powershell
python scripts/run_embed_chunks.py --repo "C:\Users\hunte\Music\rbassist" --chunk-glob "data/pending_embedding_paths.part*.txt" --checkpoint-dir data/checkpoints --checkpoint-every 50 --num-workers 2
```
