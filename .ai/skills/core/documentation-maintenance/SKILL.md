---
name: documentation-maintenance
description: Keep user, API, operational, and decision documentation synchronized with delivered behavior.
version: 2.1.0
tier: core
stack: [any]
owner: document
gates: [G3]
related: [architecture-decisions, api-contract]
---

# Skill: documentation-maintenance

## Purpose
Keep documentation synchronized with what the system actually does, so contributors and
users don't make decisions based on stale or contradictory instructions. Documentation
that diverges from behavior is an active liability — it leads to incorrect configurations,
missed migration steps, and hours of debugging "why doesn't this command work?" A docs
update is part of "done" for any change that affects user-visible behavior, a public
interface, an operational procedure, or an architecture decision.

## When to use
Any change that: renames or removes a configuration key, CLI flag, or environment variable;
changes the shape or semantics of a public API endpoint or event; alters a workflow step
that operators or contributors follow; adds a new tool, script, or gate; changes the
behavior of an existing command in `kit.yaml`, `check-*.sh`, or similar; or resolves
an architecture decision that should be recorded. Also run when a review or user report
identifies a discrepancy between documentation and actual behavior.

## Procedure

1. **Identify every doc that is authoritative for the changed behavior.** Do not guess —
   grep for the affected concept: the renamed key, the changed command, the moved file
   path. Typical locations: `README.md`, `AGENTS.md`, `.github/copilot-instructions.md`,
   `.ai/agents/<role>/*.md`, `.ai/skills/*/SKILL.md`, `docs/`, `CHANGELOG.md`, inline
   code comments in public-facing configuration files. A doc you didn't find is a doc
   that will contradict the change.
2. **Update the authoritative description first; examples flow from it.** Start with the
   section that states what something *is* (purpose, schema, gate contract), then update
   examples and commands to match. Going in the reverse order (fixing examples without
   updating the normative description) often leaves contradictions.
3. **Make commands and examples runnable.** Any command block that could be executed by
   a reader should be: tested against the current implementation, using real paths and
   flags that exist, with correct prerequisites stated. If a command depends on a setup
   step (installed tool, environment variable, running service), state that prerequisite
   immediately before the command — not in a separate section the reader might skip.
4. **State version-sensitive assumptions explicitly.** When the documented behavior
   depends on a specific version (Python ≥3.11, Node ≥20, Docker ≥24.0, API v2), write
   the requirement at the point of use, not only in the project's global prerequisites.
   A reader looking at a specific section may not have read the global prerequisites.
5. **Remove or replace contradictory guidance.** When updating a doc, search for other
   places in the same file (and in closely related files) that describe the same behavior.
   A doc that says one thing in Section 2 and the opposite in Section 5 is worse than one
   that only says it once. Use `grep -r` to find all mentions of the changed term across
   the docs directory. Remove stale examples; don't leave them commented out.
6. **Record limitations and known gaps honestly.** If a documented feature has a known
   limitation (works only with single-file inputs, not supported on Windows, requires
   manual setup), document the limitation at the point where a user would encounter it,
   not in a separate "known issues" section that readers skip. An undocumented limitation
   found by a user in production is a higher-trust failure than one documented upfront.
7. **Link to verification evidence for behavior claims.** Any claim that "X does Y" should
   be traceable to either the code that implements it or a test that verifies it. A doc
   that claims a command produces a specific output but has no corresponding test is
   drifting toward inaccuracy. For key behaviors, add or reference the test that proves it.

## Checklist
- [ ] All docs referencing the changed behavior are identified (via grep, not recall)
- [ ] Normative description updated before examples and commands
- [ ] Every command block is tested and uses real paths, flags, and prerequisites
- [ ] Version-sensitive assumptions stated at point of use
- [ ] Contradictory guidance removed from the same file and related files
- [ ] Limitations documented at the point of encounter, not hidden in a separate section
- [ ] Behavior claims are traceable to code or a passing test

## Anti-patterns
- Updating only the doc file that was most recently open, and leaving four other files
  that describe the same feature in the old state — readers will hit the stale docs first.
- Leaving a deprecated example "for reference" with a `# deprecated` comment — it will
  be copied by the next contributor who finds it in a search.
- Writing docs that describe what the feature *should* do rather than what it *does* —
  aspirational documentation misleads users and erodes trust in all documentation.
- Treating documentation updates as optional cleanup to be done "when there's time" —
  shipping a behavior change without updating the docs means the docs are wrong from
  the moment the change lands.

## Output
Updated documentation files with synchronized descriptions, runnable examples, stated
limitations, and removed contradictions. PR includes a brief note listing which docs were
updated and why, traceable to the behavior change.
