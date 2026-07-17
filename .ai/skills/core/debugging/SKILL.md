---
name: debugging
description: Structured defect/regression workflow — reproduce, isolate, diagnose, fix, and lock with a regression test. Use when behavior diverges from expected and the cause isn't obvious.
version: 0.1.0
tier: core
stack: [any]
owner: qa
gates: [G2]
related: [.ai/modules/debugging.md, test-and-validation]
---

# Skill: debugging

## Purpose
Turn "it's broken" into a reproducible, isolated, and permanently-fixed defect — so the same bug can't come back silently.

## When to use
A failing test, a stack trace, a "works in staging but not prod", or any observed behavior that diverges from expected.

## Procedure
1. **Reproduce** deterministically. Capture the exact input/state/steps; write a failing test that encodes it (this becomes the regression test).
2. **Isolate**: bisect (code, commit, config, data) until the smallest trigger is known. Note what does NOT reproduce it.
3. **Diagnose** the root cause, not the symptom. State the causal chain in one sentence.
4. **Fix** the cause; keep the change scoped to the defect (out-of-scope cleanup → a separate task).
5. **Lock**: the regression test now passes (G2); run the focused suite, then the full suite.
6. **Record** the root cause + fix in the task note; if it reveals a systemic gap, add a `.ai/memory/postmortems.md` entry.

## Checklist
- [ ] Deterministic reproduction captured as a failing test
- [ ] Root cause identified (not just the symptom)
- [ ] Fix scoped to the defect; no unrelated changes
- [ ] Regression test passes; full suite green (G2)
- [ ] Root cause noted; systemic issues → postmortems.md

## Anti-patterns
- Fixing the symptom (swallowing an error) instead of the cause
- "Fixed" with no regression test — it will regress
- Widening scope mid-fix; shotgun edits with no isolation

## Output
The fix + a committed regression test + a task note; optional postmortem entry.
