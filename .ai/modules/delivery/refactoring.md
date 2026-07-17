<!-- AI-Kit v2 adaptation of reusable v1 guidance. -->

---
name: refactoring
description: Behavior-preserving restructuring — safety net first, small steps, no mixed diffs. Load for refactor-intent tasks.
---

# Module: Refactoring

## Purpose
The discipline for refactor-intent work: change structure, never behavior — provably.

## When to Load
Intent = refactor (per intent-analysis).

## Invariant
Observable behavior stays identical: same inputs → same outputs, same errors, same side effects. If any behavior changes, this is a feature — stop, reclassify (intent-analysis rule).

## Process
1. **Safety net first** — verify tests cover the code being restructured; coverage gaps → write characterization tests (pin CURRENT behavior, even if ugly) before touching anything
2. **Small steps** — one mechanical transformation at a time (extract, rename, move, inline); each step compiles and passes tests; commit per step or per coherent group
3. **No mixed diffs** — refactor commits contain zero behavior changes, zero drive-by fixes; bug found mid-refactor → new task
4. **Re-run the full net** — suite green after every step, not just at the end

## Rules
- Refactor without a safety net is gambling, not engineering — G2 requires tests pass, and here "pass" means pass BEFORE and AFTER
- Public contract (API/schema) changes are never "refactoring" — they're features with migration plans
- Scope creep is the failure mode: `files:` scope in the task is a hard boundary
- Improving code you happen to pass by ("boy-scouting") outside task scope → note it for Planner, don't do it

## Output
Structurally improved code, identical behavior, green suite at every commit, tasks.md updated.
