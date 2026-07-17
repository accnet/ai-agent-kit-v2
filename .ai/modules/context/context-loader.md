<!-- AI-Kit v2 adaptation of reusable v1 guidance. -->

---
name: context-loader
description: Gather candidate context sources for the current task, cheaply, before any ranking.
---

# Context Loader

## Purpose
Gather candidate context sources for the current task, cheaply, before any ranking.

## Source Order
1. `.ai-work/brief.md` — always
2. `.ai-work/tasks.md` — current task + its criteria
3. `.ai-work/research/` + `context/*` — requirements and research (read-only)
3b. `.ai-work/plan.md`, `architecture.md`, `decisions.md` — execution context
4. Files named in the task; then their direct imports/dependents
5. `.ai/memory/conventions.md` — project conventions

## Rules
- Scan structure first (paths, signatures, exports), read bodies only when needed
- Prefer interfaces/contracts over implementations at this stage
- Note what was looked for but NOT found — missing context is a finding
- Do not read generated files, lockfiles, or vendored code

## Output
Candidate list: path + one-line reason it might matter. Feeds context-ranking.
