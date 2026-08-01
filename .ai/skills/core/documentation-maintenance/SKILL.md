---
name: documentation-maintenance
description: Keep user, API, operational, and decision documentation synchronized with delivered behavior.
version: 2.0.0
tier: core
stack: [any]
owner: document
gates: [G3]
related: []
---

# Skill: documentation-maintenance

## Purpose
Keep user/API/operational/decision documentation synchronized with delivered behavior and constraints.

## When to use
Any change affecting public interfaces, workflows, operational procedures, architecture decisions, or developer usage.

## Procedure
1. Identify authoritative docs touched by the behavior change (README, AGENTS, router docs, API references).
2. Update contracts, examples, commands, and caveats to match implementation exactly.
3. Call out version-sensitive assumptions and environment prerequisites.
4. Link docs to verification evidence and known limitations.
5. Remove stale guidance that conflicts with current behavior.

## Checklist
- [ ] All changed behavior has matching documentation updates.
- [ ] Examples/commands are runnable and current.
- [ ] Constraints, trigger precedence, and gate requirements are explicit.
- [ ] No contradictory instructions remain across docs.
- [ ] Residual limitations are documented honestly.

## Anti-patterns
- Shipping behavior changes while leaving old docs in place.
- Copying generic guidance without repository-local references.
- Documenting capabilities that have no executable evidence.

## Output
Synchronized documentation set with traceable links to code and tests.
