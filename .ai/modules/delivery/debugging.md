<!-- AI-Kit v2 adaptation of reusable v1 guidance. -->

---
name: debugging
description: Bug-fix loop — reproduce, isolate, root cause, fix, prove. Load for bug-intent tasks; no reproduction = no fix.
---

# Module: Debugging

## Purpose
The loop for bug-intent work: reproduce → isolate → root cause → fix → prove. Prevents symptom-patching and "fixed on my machine".

## When to Load
Intent = bug (per intent-analysis). Owner: Backend/Frontend/Database per the bug's layer.

## The Loop
1. **Reproduce** — a failing test or exact repro steps BEFORE touching code. Can't reproduce → gather evidence (logs, inputs, versions), don't guess-fix
2. **Isolate** — shrink to the smallest failing case; bisect (input, commit history, config) until the boundary is sharp
3. **Root cause** — explain WHY it fails in one sentence a reviewer can verify. "It works when I change X" is not a root cause
4. **Fix** — smallest change that kills the root cause, within the task's `files:` scope
5. **Prove** — the reproduction test now passes; adjacent regression check runs clean

## Rules
- No reproduction → no fix. A fix without a failing-first test is unverifiable (G2 cannot pass)
- Fixing the symptom while the root cause lives on → escalate instead: report the real cause to Planner if out of scope
- Two unrelated bugs found → second one becomes a new task, never a drive-by fix
- Root cause traces to design → Architect; traces to unclear requirements → user via Intake
- Recurring bug class → entry in `.ai/memory/postmortems.md` with the enforcement that prevents it

## Output
Fix + the failing-first test (now green) + one-line root cause note on the task in tasks.md.
