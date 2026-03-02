# Project Continuity

## Purpose
This file is the stable north-star brief for rbassist. Future agents should read this first, then read `docs/dev/AGENT_HANDOFF_LOG.md` for the detailed timeline.

## Mission
Make rbassist reliable and safe for a real DJ library centered on `C:\Users\hunte\Music`, with Rekordbox-aware auditing and repair, while avoiding destructive changes to local library data.

## Canonical Scope
- Primary music root: `C:\Users\hunte\Music`
- Primary repo: `C:\Users\hunte\Music\rbassist`
- Primary local metadata: `data/meta.json`
- Known-bad asset quarantine: `data/quarantine_embed.jsonl`
- Rekordbox is a secondary truth source for repair and reconciliation, not the primary source of truth.

## Current Grounded State
As of March 2, 2026:
- Root-scoped pending embeds under `C:\Users\hunte\Music`, excluding quarantine: `0`
- Durable embed quarantine count: `813`
- Analyze: complete for the active root
- Index: complete for the active root
- Remaining work is mostly metadata hygiene and Rekordbox reconciliation, not raw ingest throughput

Global `meta.json` hygiene counts still worth addressing:
- stale track paths: `2511`
- bare/orphan paths: `1457`
- global embedding-gap total: `3323`

## Current Priorities
1. Root-first stale/path cleanup
2. Bare/orphan review and safe apply
3. Rekordbox apply-ready relink tooling
4. Duplicate remediation and consolidation planning
5. Rollout QA artifacts that let future agents judge readiness quickly

## Working Rules
- Treat `C:\Users\hunte\Music` as the canonical library root.
- Do not push local library data such as `data/meta.json`, `data/runlogs`, or backup/archive artifacts.
- Avoid destructive actions against Rekordbox or local metadata without backup-first safeguards.
- Prefer read-only audit, review queues, dry runs, then explicit apply.
- If new work changes the operational truth, update this file and append a dated note to `docs/dev/AGENT_HANDOFF_LOG.md`.

## Continuity Files
- `docs/dev/PROJECT_CONTINUITY.md`: stable mission, scope, and current truth
- `docs/dev/CONTINUITY_LOG.md`: rolling progress log with decisions and next steps
- `docs/dev/AGENT_HANDOFF_LOG.md`: detailed implementation chronology

## Definition Of Good Progress
A good change should leave behind:
- a measurable before/after report or test result
- a short dated handoff note
- clear next steps for the next agent
