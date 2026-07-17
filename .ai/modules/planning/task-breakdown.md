<!-- AI-Kit v2 adaptation of reusable v1 guidance. -->

---
name: task-breakdown
description: Split planned work into atomic, independently verifiable tasks.
---

# Task Breakdown

## Purpose
Split planned work into atomic, independently verifiable tasks.

## Atomic Task Definition
A task is atomic when it: fits one work session, touches one concern, can be verified alone, and can be rolled back alone.

## Process
1. Walk the design top-down: contracts → data → logic → UI → tests
2. Cut at natural seams (one endpoint, one migration, one component)
3. Mark dependencies between tasks; order them
4. Tag each task: owner agent + scope (S/M/L)

## Rules
- L-sized task → split again; L is a smell, not a size
- A task named "and" (do X and Y) → two tasks
- Cross-cutting tasks (logging, auth) come before the tasks that need them
- Test tasks are not optional appendixes — they pair with implementation tasks
- Every task declares `files:` — the paths it owns; two tasks writing the same file are sequential or merged, never parallel

## Parallelization Safety Checks
Two tasks may run in parallel ONLY if all three pass:
1. **File exclusivity** — their `files:` scopes are disjoint
2. **Interface stability** — neither changes a signature/schema/contract the other depends on
3. **Independence** — neither `needs:` the other (directly or transitively)
Any check fails → serialize (or restructure the split so they pass).

## Output
Ordered task list for tasks.md (IDs unique per file; `.ai/scripts/next-task.sh` parses this):
```
- [ ] T<n> <verb + object> | owner: <agent> | scope: S/M/L | needs: T<i>,T<j> or - | files: <owned paths>
```
