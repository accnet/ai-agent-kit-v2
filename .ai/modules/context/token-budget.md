<!-- AI-Kit v2 adaptation of reusable v1 guidance. -->

---
name: token-budget
description: Keep working context small enough that the model stays sharp on the actual task.
---

# Token Budget

## Purpose
Keep working context small enough that the model stays sharp on the actual task.

## Budget Guideline
- Target: context relevant to the CURRENT task only, roughly ≤ 30% of the window
- Reserve the rest for reasoning, code output, and conversation

## Cutting Order (when over budget)
1. Drop tier 4–5 items (background, misc) entirely
2. Tier 3 conventions → keep rules, drop examples
3. Tier 2 adjacent files → signatures/interfaces only, drop bodies
4. Tier 1 is never cut — if tier 1 alone exceeds budget, the task is too big: back to task-breakdown

## Rules
- Summarize instead of dropping only when the summary is verifiably faithful
- Never trim acceptance criteria or contracts — they define correctness
- Re-budget on every task switch; stale context is silent budget theft

## Output
Final trimmed context set. Feeds context-assembler.
