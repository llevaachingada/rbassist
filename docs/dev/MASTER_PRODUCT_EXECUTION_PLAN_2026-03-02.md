# Master Product Execution Plan

## Purpose
This is the working product roadmap for finishing the major rbassist feature goals that still matter after active-root ingest catch-up. It turns the current wishlist into an execution sequence.

## Canonical Goal
Make rbassist reliable, safe, and practical for a real DJ library centered on `C:\Users\hunte\Music`, with Rekordbox-aware repair, duplicate cleanup, trustworthy health reporting, safe BPM separation, and a UI that scales to the real library.

## Ground Truth
As of March 2, 2026:
- Root-scoped pending embeds under `C:\Users\hunte\Music`, excluding quarantine: `0`
- Durable embed quarantine: `813`
- Analyze: complete for active root
- Index: complete for active root
- Global metadata still needs hygiene work:
  - stale absolute-path rows: `2511`
  - classified stale absolute-path rows under current triage: `1054`
  - bare/orphan rows: `1457`
- Stale triage with Rekordbox context currently resolves to:
  - duplicate stale candidates: `584`
  - inside-root relink candidates: `465`
  - outside-root Rekordbox candidates: `5`
  - archive-safe removals after Rekordbox context: `0`

## Winning Sequence
1. Finish `rbassist-meta-hygiene`
2. Finish `rbassist-rekordbox-safe-relink`
3. Finish `rbassist-duplicate-remediation`
4. Add `rbassist-library-rollout-qa`
5. Implement BPM/Rekordbox separation
6. Finish UI gaps: tags, beatgrid fallback, large-table UX
7. Add benchmark suite

---

## Phase 1: Finish rbassist-meta-hygiene

### Outcome
`data/meta.json` becomes trustworthy enough that future repair, QA, and export work stop fighting stale and orphaned state.

### Current state
Partially complete:
- health audit exists
- collision-safe normalization exists
- bare/orphan resolution exists
- stale triage/apply primitives now exist

### Remaining work
1. Extend bare/orphan resolution to use confidence-scored classifications:
   - `high_confidence_unique`
   - `medium_confidence_unique`
   - `ambiguous`
   - `not_found`
2. Emit review CSV/JSON files for orphan resolution.
3. Merge richer metadata safely into existing absolute-path records.
4. Add stale-triage outputs that are easier to review in smaller slices.
5. Add archive manifests and post-apply delta summaries for all cleanup flows.

### Main files
- `rbassist/health.py`
- `scripts/audit_meta_health.py`
- `scripts/normalize_meta_paths.py`
- `scripts/resolve_bare_meta_paths.py`
- `scripts/triage_stale_meta_paths.py`
- `scripts/apply_stale_meta_cleanup.py`
- `tests/test_audit_meta_health.py`
- `tests/test_normalize_meta_paths.py`
- `tests/test_resolve_bare_meta_paths.py`
- `tests/test_triage_stale_meta_paths.py`
- `tests/test_apply_stale_meta_cleanup.py`

### Acceptance criteria
- all stale absolute-path rows are classified
- all bare/orphan rows are classified
- only high-confidence fixes auto-apply
- all cleanup flows create backups or archives
- no silent overwrites or blind deletions

### Immediate next slice
Finish the richer bare/orphan review and safe-apply flow.

---

## Phase 2: Finish rbassist-rekordbox-safe-relink

### Outcome
Rekordbox broken links can be repaired with a backup-first, dry-run-first workflow that only writes high-confidence, in-root relinks.

### Current state
Partially complete:
- read-only Rekordbox audit exists
- review queue generation exists
- relink suggestions exist
- consolidation planning exists as read-only report data

### Remaining work
1. Build deterministic apply-plan generation.
2. Build dry-run and apply-safe relink command.
3. Require DB backup before any write.
4. Restrict apply mode to existing in-root targets only.
5. Emit before/after JSON reports for every attempted relink.

### Main files
- `rbassist/rekordbox_audit.py`
- `rbassist/rekordbox_review.py`
- `rbassist/rekordbox_import.py`
- `scripts/rekordbox_audit_library.py`
- `scripts/prepare_rekordbox_review_queues.py`
- `scripts/rekordbox_build_apply_plan.py`
- `scripts/rekordbox_apply_relinks.py`
- `tests/test_rekordbox_audit.py`
- `tests/test_rekordbox_review.py`
- `tests/test_rekordbox_apply_plan.py`
- `tests/test_rekordbox_apply_relinks.py`

### Acceptance criteria
- apply plans are deterministic
- dry-run mode is human-reviewable
- apply fails closed without backup
- only high-confidence existing in-root paths can be written
- ambiguous rows never auto-apply

### Immediate next slice
Build `scripts/rekordbox_build_apply_plan.py` and its tests.

---

## Phase 3: Finish rbassist-duplicate-remediation

### Outcome
Duplicate tracks stop polluting metadata truth, Rekordbox relink decisions, and future library maintenance.

### Current state
Partial:
- meta-based duplicate staging exists
- Rekordbox audit duplicate dry-run exists
- same-name/different-type review queues exist

### Remaining work
1. Add preferred-keeper rules that are reviewable and explicit.
2. Add duplicate review outputs tied to active root and Rekordbox state.
3. Add consolidation manifests for duplicate copies outside preferred library locations.
4. Optionally add UI review flow later, after backend is stable.

### Main files
- `rbassist/duplicates.py`
- `rbassist/rekordbox_audit.py`
- `rbassist/rekordbox_review.py`
- `scripts/prepare_rekordbox_review_queues.py`
- `scripts/rekordbox_plan_consolidation.py`
- `tests/test_duplicates_stage.py`
- `tests/test_rekordbox_audit.py`

### Acceptance criteria
- duplicate groups are reviewable in smaller artifacts
- preferred keeper logic is deterministic
- no automated deletes or file moves in the first pass
- duplicate review can feed back into hygiene and relink workflows

### Immediate next slice
Add explicit preferred-keeper planning and consolidation-manifest generation.

---

## Phase 4: Add rbassist-library-rollout-qa

### Outcome
One command and one report can tell us whether the active root is operationally ready.

### Current state
Partial:
- maintenance runner exists
- health audit exists
- summarize script exists
- continuity files now exist

### Remaining work
1. Add a formal rollout-readiness report.
2. Include active-root pending coverage, quarantine totals, stale/bare counts, Rekordbox parity counts, and duplicate review counts.
3. Make the maintenance summary point to the right artifacts automatically.
4. Add one stable report format for future agents.

### Main files
- `rbassist/health.py`
- `rbassist/keeper_manifest.py`
- `scripts/audit_meta_health.py`
- `scripts/summarize_maintenance_run.py`
- `scripts/run_music_root_background_maintenance.py`
- `docs/dev/PROJECT_CONTINUITY.md`
- `docs/dev/CONTINUITY_LOG.md`

### Acceptance criteria
- a rollout-readiness report exists and is reproducible
- it reflects active-root truth, not just global meta counts
- future agents can understand readiness without replaying prior runs

### Immediate next slice
Add a dedicated rollout-readiness JSON + Markdown report generator.

---

## Phase 5: Implement BPM/Rekordbox Separation

### Outcome
BPM handling becomes safe by default and no longer risks accidental Rekordbox mutation.

### Current state
Design exists in `WISHLIST.md`, implementation not started.

### Remaining work
1. Add separate BPM store, likely `data/bpm.json`.
2. Keep export to Rekordbox off by default.
3. Add import/conflict handling for BPM coming from Rekordbox.
4. Add migration and backup tool.
5. Make UI and CLI behavior explicit.

### Main files
- `rbassist/analyze.py`
- `rbassist/export_xml.py`
- `rbassist/rekordbox_import.py`
- `rbassist/cli.py`
- `rbassist/ui/pages/settings.py`
- `rbassist/ui/pages/library.py`
- new BPM store helper module

### Acceptance criteria
- BPM is stored locally and safely by default
- Rekordbox export is opt-in
- conflicts are visible, not silent
- migration path includes backup

### Immediate next slice
Draft and implement the BPM store contract before any UI work.

---

## Phase 6: Finish UI Gaps

### Outcome
The product becomes easier to use on the real library without losing the safety work from earlier phases.

### Current state
Mixed:
- Settings import UX improved
- health summary exists
- beatgrid preview exists
- tagging backend is stronger than the current UI
- library table still needs large-library UX improvements

### Remaining work
1. Tagging UI:
   - expose advanced tag inference controls
   - make review/apply flow less CSV-dependent
2. Beatgrid UI:
   - add one-click fallback to fixed BPM / fallback mode
   - improve confidence/action affordances
3. Large-table UX:
   - real pagination or virtual scrolling
   - better problem filters for stale/bare/missing metadata

### Main files
- `rbassist/ui/pages/tagging.py`
- `rbassist/ui/pages/ai_tagging.py`
- `rbassist/ui/pages/library.py`
- `rbassist/ui/pages/tools.py`
- `rbassist/ui/components/track_table.py`
- `rbassist/ui/components/health_summary.py`
- `rbassist/beatgrid.py`

### Acceptance criteria
- advanced tags can be tuned in-app
- beatgrid fallback is obvious and safe
- the library page remains usable with 10k+ rows

### Immediate next slice
Solve the library table scaling problem after metadata truth is stronger.

---

## Phase 7: Add Benchmark Suite

### Outcome
Performance and stability tuning stop being guesswork and become repeatable.

### Current state
Ad hoc benchmarks and local reports exist, but no standardized suite.

### Remaining work
1. Standard benchmark command set for embed/analyze/index.
2. Worker and batch-size sweeps.
3. GPU/CPU telemetry snapshots.
4. Machine-specific recommended defaults output.
5. Store results in a stable format for comparison.

### Main files
- `scripts/profile_embed_gpu.py`
- `scripts/live_phase_telemetry.py`
- `scripts/run_embed_chunks.py`
- new benchmark runner scripts and result schema
- docs for benchmark interpretation

### Acceptance criteria
- benchmark runs are reproducible
- recommended settings for this machine are documented
- regressions are easier to spot over time

### Immediate next slice
Build a single benchmark harness that wraps the existing profiling scripts.

---

## Execution Rules
- Complete each phase in backend-first order before widening the UI.
- Prefer dry-run, review, and backup-first workflows for anything touching local state or Rekordbox.
- Keep `C:\Users\hunte\Music` as the canonical active scope.
- Update continuity files whenever operational truth changes.
- Preserve local-only data as local-only.

## Recommended Immediate Next Build
1. Commit the current stale-path hygiene batch.
2. Finish the richer bare/orphan review and safe-apply flow.
3. Then move directly into Rekordbox apply-plan tooling.

This order keeps the foundation strong and reduces the chance that later UI or Rekordbox work gets built on muddy metadata.
