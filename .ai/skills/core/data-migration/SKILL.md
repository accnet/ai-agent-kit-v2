---
name: data-migration
description: Discipline for any database change — schema OR data (migration, DDL, backfill, seed). Reversible up/down, forward-compatible rollout, and destructive/prod steps gated by user approval. Always requires a plan first.
version: 0.1.0
tier: core
stack: [any]
owner: database
gates: [G1, G5]
related: [.ai/modules/database.md, deployment-infra]
---

# Skill: data-migration

## Purpose
Make database changes safe, reversible, and observable — so schema/data evolution never causes downtime or irreversible loss.

## When to use
Any schema change (DDL) or data change (backfill, bulk update, seed). Per rules.yaml `db_changes_require_plan`, this is **never trivial**: a `.ai-work/tasks/tasks.md` (or a `.ai-work/requirements/`) must exist first (Gate G1).

## Procedure
1. **Plan first (G1)**: the change is a task with acceptance criteria; no fast path.
2. **Write up + down**: every migration ships a tested rollback, not a decorative one.
3. **Forward-compatible rollout**: expand → migrate/backfill → contract. Never drop/rename a column in the same release that stops writing it; deploy code that tolerates both shapes first.
4. **Constraints at the DB**: FK/unique/not-null/checks live in the schema; app checks are a second layer.
5. **Large tables**: batch the migration; no unbounded locks.
6. **Approval (G5)**: destructive ops (drop/rename column or table, bulk delete, irreversible migration) require explicit user approval + a backup step first.
7. **Verify**: up and down both run clean on a copy; the app works against the new schema.

## Checklist
- [ ] Plan/task exists before any DB change (G1)
- [ ] Up + down migrations both run clean
- [ ] Rollout is forward-compatible (expand → migrate → contract)
- [ ] Constraints enforced at DB level; large tables batched
- [ ] Destructive/irreversible steps have explicit user approval + backup (G5)

## Anti-patterns
- Editing the schema on a fast path with no plan
- A `down` migration that's empty or untested
- Drop/rename in the same deploy that changes the writer (breaks rollback)
- Backfilling a huge table in one unbounded statement

## Output
Migration files (up + down) + a note in `.ai-work/plan/architecture.md`; rollout + rollback steps for deployment-infra.
