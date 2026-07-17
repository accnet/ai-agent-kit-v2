---
name: refactoring
description: Behavior-preserving structural change — restructure code without altering observable behavior, with tests as the safety net. Use for cleanup, decoupling, or renaming, not for new behavior.
version: 0.1.0
tier: core
stack: [any]
owner: architect
gates: [G3]
related: [.ai/modules/refactoring.md, test-and-validation, code-review]
---

# Skill: refactoring

## Purpose
Improve structure (readability, coupling, naming) while guaranteeing observable behavior is unchanged — a refactor that changes behavior is a feature and must be reclassified.

## When to use
"Clean up", "restructure", "extract", "rename", reducing duplication or coupling — with no intended change to what the system does.

## Procedure
1. **Pin behavior first**: ensure tests cover the area; if not, add characterization tests before touching code.
2. **Small steps**: one structural transformation at a time (extract, inline, move, rename), tests green after each.
3. **No behavior drift**: no new inputs/outputs, no changed error semantics. If behavior must change → stop, reclassify as a feature, write tasks.
4. **Keep the diff reviewable**: mechanical changes separate from judgment changes.
5. **Verify**: full suite green, typecheck/lint clean (G2), then review (G3).

## Checklist
- [ ] Area covered by tests before refactoring (added if missing)
- [ ] Each step keeps tests green; behavior unchanged
- [ ] No public contract change slipped in (else → api-contract + reclassify)
- [ ] Diff is small and reviewable
- [ ] Full suite + typecheck/lint green

## Anti-patterns
- Refactor + behavior change in one commit (untestable, unreviewable)
- Big-bang rewrite with no intermediate green states
- "While I'm here" scope creep

## Output
Restructured code with identical behavior + tasks.md note; no new acceptance criteria beyond "behavior unchanged, suite green".
