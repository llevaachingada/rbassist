# Health + Gap + Normalize Baseline

Generated: 2026-02-28

## Health Audit Baseline
- Source: `docs/dev/health_audit_baseline_2026-02-28.json`
- Tracks total: `15,674`
- Embedding gap total: `4,506`
- Stale track paths: `4,475`
- Bare path entries: `2,582`
- Junk paths: `13`

## Gap Scan Baseline
- Output list: `data/pending_embedding_paths.txt`
- Output JSON: `data/pending_embedding_paths.json`
- Music roots scanned: configured folders from `config/ui_settings.json`
- Audio files scanned: `937`
- Pending embedding total: `0`
- Stale meta paths outside scanned roots: `13,925`

Interpretation:
- The configured Settings folders are only a slice of the larger library state in `data/meta.json`.
- There is no immediate embedding backlog inside the currently configured roots.
- The larger completeness problem is metadata/path drift, not active embedding work.

## Normalize Dry Run Baseline
- Report: `docs/dev/normalize_meta_paths_dryrun_2026-02-28.json`
- Dropped junk candidates: `13`
- Changed paths if normalized: `6,127`
- Prefix rewrites from `C:/Users/TTSAdmin/Music` to `C:/Users/hunte/Music`: `205`
- Bare-path review-only entries: `2,582`
- Collision groups detected: `5,532`
- Duplicate entries inside those groups: `5,712`
- Collision groups safely resolved in the dry run: `5,532`
- Groups with field-level conflicts kept for review: `927`

Interpretation:
- Most collisions are slash-style/case variants, with a smaller legacy-root layer from `C:/Users/TTSAdmin/Music`.
- Collision remediation is now built into the path-repair flow and can conservatively merge those groups during apply.
- Field-level conflicts are retained conservatively in favor of the richer canonical entry, and they remain visible in the dry-run JSON for review.

## Current Safety Guardrails
- UI and script path repair now dry-run collision-safe merges before apply.
- The older stale artifact `docs/dev/normalize_meta_paths_dry_run_2026-02-28.json` was removed so only the canonical collision-aware report remains.
- Health dashboard now surfaces stale paths, bare paths, junk paths, and suggested rewrite pairs.
- Library page now supports health-based filtering for missing embedding, missing analysis, missing cues, stale paths, bare paths, and junk paths.

## Post-Apply Result (2026-03-01)
- Apply report: `docs/dev/normalize_meta_paths_apply_2026-03-01.json`
- Post-repair audit: `docs/dev/health_audit_after_safe_path_repair_2026-03-01.json`
- Backup: `data/backups/meta_before_safe_path_repair_20260228_173406.json`

Delta from the original baseline:
- Duplicate normalized path keys: `5,547 -> 0`
- Junk paths: `13 -> 0`
- Stale track paths: `4,475 -> 3,634`
- Embedding gap total: `4,506 -> 3,649`
- Missing BPM total: `13,937 -> 8,213`
- Missing key total: `13,973 -> 8,248`
- Missing cues total: `13,938 -> 8,214`

Interpretation:
- The safe repair removed duplicate path variants and merged metadata into canonical Windows paths.
- Remaining stale entries are now dominated by true bare-path/orphan records rather than slash-style duplicates.
- The next cleanup target should be resolving or quarantining the remaining bare-path entries.

## Post-Bare-Path Apply Result (2026-03-01)
- Apply report: `docs/dev/resolve_bare_meta_paths_apply_2026-03-01.json`
- Post-repair audit: `docs/dev/health_audit_after_bare_path_repair_2026-03-01.json`
- Backup: `data/backups/meta_before_bare_path_repair_20260228_174117.json`

Delta from the post-path-repair state:
- Tracks total: `9,949 -> 8,825`
- Bare path entries: `2,582 -> 1,457`
- Stale track paths: `3,634 -> 2,509`
- Embedding gap total: `3,649 -> 2,525`
- Missing BPM total: `8,213 -> 7,089`
- Missing key total: `8,248 -> 7,124`
- Missing cues total: `8,214 -> 7,090`

Interpretation:
- The new bare-path resolver safely merged `1,124` orphan filename rows into existing absolute-path records and promoted `1` uniquely matched orphan into a new absolute-path record.
- The remaining `1,457` orphan rows are intentionally unresolved because their filenames were ambiguous across multiple folders or no current file could be found under the scanned music roots.
- The next cleanup target should be an ambiguity review flow plus expanded root coverage for paths outside `C:\Users\hunte\Music` such as legacy external folders.
