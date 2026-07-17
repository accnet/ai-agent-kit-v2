<!-- AI-Kit v2 adaptation of reusable v1 guidance. -->

---
name: acceptance
description: Define verifiable "done" for every task, so completion is a fact, not an opinion.
---

# Acceptance Criteria

## Purpose
Define verifiable "done" for every task, so completion is a fact, not an opinion.

## Format
Each criterion must be observable and binary (pass/fail):
```
Given <precondition>, when <action>, then <observable result>
```
Or a concrete check: "endpoint returns 401 without token", "migration rolls back cleanly".

## Rules
- "Works correctly" / "is clean" / "is fast" are NOT criteria — quantify or drop
- Every task gets at least one criterion; user-facing tasks get an error-path criterion too
- Criteria describe behavior, not implementation ("user sees X", not "function Y called")
- If QA can't turn the criterion into a test, rewrite it

## Anti-patterns
- Criterion that requires reading the code to verify
- Criterion that duplicates the task title
- Performance criterion without a number

## Output
Criteria attached to each task in tasks.md; QA derives tests from these verbatim.
