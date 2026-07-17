<!-- AI-Kit v2 adaptation of reusable v1 guidance. -->

---
name: plan-assembly
description: Assemble intent, breakdown, and acceptance criteria into the final tasks.md.
---

# Plan Assembly

## Purpose
Assemble intent, breakdown, and acceptance criteria into the final tasks.md.

## Process
1. Header: intent label + one-sentence goal + out-of-scope list
2. Open questions (blockers first) — plan is DRAFT until these are resolved
3. Ordered task list from task-breakdown, each with acceptance criteria
4. Standing tail tasks: Review → QA → Docs → Release gate

## Plan Quality Gates
- Sum of tasks = the brief; nothing missing, nothing extra
- First task is startable right now (no unresolved dependency)
- Riskiest/most uncertain task scheduled as early as possible
- Every task has owner, scope, and acceptance criteria

## Rules
- Draft plan with open blockers → get answers before implementation starts
- Plan changes during execution → edit tasks.md explicitly, never drift silently
- Completed tasks are never deleted — checked off, kept as record

## Output
`.ai-work/tasks.md` — the single source of truth for execution state.
