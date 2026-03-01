# Safe Path Repair Apply Summary

Generated: 2026-03-01

## Commands Run

```powershell
python scripts/normalize_meta_paths.py --repo . --rewrite-from "C:/Users/TTSAdmin/Music" --rewrite-to "C:/Users/hunte/Music" --drop-junk --resolve-collisions --apply --out docs/dev/normalize_meta_paths_apply_2026-03-01.json
python scripts/audit_meta_health.py --repo . --out docs/dev/health_audit_after_safe_path_repair_2026-03-01.json
```

## Backup

- `data/backups/meta_before_safe_path_repair_20260228_173406.json`

## Apply Counts

- Dropped junk entries: `13`
- Changed paths: `6,127`
- Prefix rewrites: `205`
- Bare-path review-only entries preserved: `2,582`
- Collision groups resolved: `5,532`
- Duplicate entries merged: `5,712`
- Groups with field-level conflicts: `927`

## Audit Delta

- Tracks total: `15,674 -> 9,949`
- Duplicate normalized path keys: `5,547 -> 0`
- Junk paths: `13 -> 0`
- Stale track paths: `4,475 -> 3,634`
- Embedding gap total: `4,506 -> 3,649`
- Missing BPM total: `13,937 -> 8,213`
- Missing key total: `13,973 -> 8,248`
- Missing cues total: `13,938 -> 8,214`
- Missing My Tags total: `7,772 -> 4,714`

## Notes

- The large drop in total track count is expected because duplicate slash-style and legacy-root variants were merged into canonical Windows paths.
- Remaining stale entries are mostly bare-path/orphan records that still need a separate remediation pass.
- No broken embedding paths were introduced by the repair.
