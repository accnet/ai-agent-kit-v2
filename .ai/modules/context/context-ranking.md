<!-- AI-Kit v2 adaptation of reusable v1 guidance. -->

---
name: context-ranking
description: Order candidate context by relevance so the token budget cuts the right things.
---

# Context Ranking

## Purpose
Order candidate context by relevance so token-budget cuts the right things.

## Ranking Tiers
1. **Contract** — the task's acceptance criteria, target file(s), direct interfaces
2. **Adjacent** — direct callers/callees, schema of touched tables, paired tests
3. **Convention** — knowledge/conventions.md entries, similar existing implementations (one example is enough)
4. **Background** — architecture notes, business rules touching this domain
5. **Everything else** — drop

## Rules
- One good example beats three similar ones — dedupe aggressively at tier 3
- Recency matters: recently changed files outrank stale ones within a tier
- The file being edited is always rank 1, full content
- Doubt between two tiers → lower tier (cheaper to re-load than to drown)

## Output
Ranked candidate list with tier labels. Feeds token-budget.
