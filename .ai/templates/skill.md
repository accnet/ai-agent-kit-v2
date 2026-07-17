<!-- AI-Kit v2 adaptation of reusable v1 guidance. -->

---
name: <slug>                     # kebab-case, matches the folder .ai/skills/<slug>/
description: <one line — when to use this; read by skill-router for routing>
version: 0.1.0
tier: core                       # core = stack-agnostic | stack = stack-specific
stack: [any]                     # [any] for core; else e.g. [node, typescript] / [python] / [frontend]
owner: any                       # an agent in .ai/agents/ (backend, frontend, database, qa, reviewer, ...) or "any"
gates: [G2, G3]                  # gates this skill primarily serves (G1..G5)
related: []                      # e.g. [.ai/modules/testing.md, api-contract]
---

# Skill: <slug>

## Purpose
<Why this skill exists — one short paragraph. What it makes consistent/safe.>

## When to use
<The trigger conditions. Be concrete so skill-router can match.>

## Procedure
<Numbered steps, or a "## Rules" section instead. Tie steps to gates/artifacts.>

## Checklist
- [ ] <verifiable item>
- [ ] <verifiable item>

## Anti-patterns
- <common mistake this skill prevents>

## Output
<What lands in the repo: code path, artifact, tasks.md note, decision, etc.>
