---
name: skill-router
description: Entry router for repo-local skills. Use first on any task to classify intent + size, then select which .ai/skills/ to load and the process to follow. Reads .ai/registry.yaml; never loads host-level skills.
version: 0.2.0
tier: core
stack: [any]
owner: any
gates: [G1]
related: [.ai/modules/planning/intent-analysis.md, .ai/registry.yaml]
---

# Skill: skill-router

## Purpose
Decide the process, scope, and which local skills a task needs — before any coding. Repo-canonical routing that depends only on files under `.ai/`.

## When to use
First, on every task, before loading any other skill or touching code.

## Procedure
1. Classify intent and size per `intent-analysis.md`. Any database change (schema OR data) is never trivial (rules.yaml: `db_changes_require_plan`) — require plan/tasks.
2. Route mechanically: `.ai/scripts/skills-for.sh <owner|intent> [stack]` reads `registry.yaml` + `kit.yaml project.stack` and prints the skills to load (core always; stack-specific only if the stack matches).
3. Typical chains: new/changed API logic → `nodejs-api-core` (+ `api-contract` if a signature changes); UI → `frontend-core`; DB change → `data-migration`; any task → `test-and-validation` then `code-review` at G3; defects → `debugging`; ship → `deployment-infra`.
4. Confirm the gate path: G1 plan → implement → G2 tests → G3 review. Fast-path only if the Sizing Gate allows.
5. Write the routing note to `.ai-work/session.md`; load each skill body only when its phase is reached (minimal_context).

## Checklist
- [ ] Intent + size classified; DB changes forced off the fast path
- [ ] Skills selected via `skills-for.sh` (not guessed)
- [ ] Stack-specific skills matched against `kit.yaml project.stack`
- [ ] Routing note written to `.ai-work/session.md`

## Anti-patterns
- Reaching for a host/IDE skill not listed in `.ai/registry.yaml`
- Loading every skill up front instead of per phase
- Skipping the router and guessing which skills apply

## Output
A routing note at the top of `.ai-work/session.md`: intent, size, skills to load, first action.
