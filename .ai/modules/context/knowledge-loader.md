<!-- AI-Kit v2 adaptation of reusable v1 guidance. -->

---
name: knowledge-loader
description: Load the business rules and architecture decisions that constrain the task — the "why" behind the code.
---

# Knowledge Loader

## Purpose
Load business rules and architecture decisions that constrain the task — the "why" behind the code.

## When to Load
Task touches domain logic, money, permissions, or crosses module boundaries. Skip for pure mechanical changes.

## Sources (in order)
1. `.ai/memory/decisions.md` — cross-feature decisions that bind this task's domain
2. `.ai/memory/conventions.md` — project-specific conventions
3. `.ai/memory/postmortems.md` — lessons relevant to this task's risk area
4. `.ai-work/decisions.md` + `.ai-work/research/` — decisions and research for this feature
5. AGENTS.md / rules.yaml — process constraints

## Graduation Rule (.ai-work/ → knowledge/)
When a feature closes, Documenter moves anything that binds FUTURE work:
- decision constraining other features → `knowledge/decisions.md`
- codebase-specific rule discovered → `knowledge/conventions.md`
- incident/defect with a lesson → `knowledge/postmortems.md`
One-off context stays in `.ai-work/decisions.md`.

## Rules
- Business rule found only in code comments or old chats → extract it into `.ai-work/decisions.md` now (or `features/` via user if it's a requirement)
- Conflicting rules between features → escalate to user; don't pick silently
- Knowledge loaded must be dated/attributed — stale business rules are worse than none
- knowledge/ files are loaded by relevant section, not wholesale (minimal_context applies)

## Output
Short constraint list ("must", "must not", "because") merged into working context at assembly tier 5.
