---
name: dependency-management
description: Change dependencies deliberately with compatibility, security, lockfile, license, and rollback awareness.
version: 2.0.0
tier: core
stack: [any]
owner: devops
gates: [G2, G4]
related: []
---

# Skill: dependency-management

## Purpose
Change dependencies deliberately with compatibility, security, lockfile, license, and rollback awareness.

## When to use
Use when a task matches this domain, before the owning agent claims completion.

## Procedure
Review why the dependency is needed, constrain versions, inspect advisories and licenses, update the lockfile, run validation, and record upgrade impact.

## Checklist
- [ ] Need and owner are clear
- [ ] Lockfile is updated
- [ ] Security and license impact checked
- [ ] Rollback version is known

## Anti-patterns
- Marking work complete from intuition instead of recorded evidence.
- Expanding scope without a planned task and owner.

## Output
Record the decision, evidence paths, and residual risk in the workflow state and the appropriate .ai-work report.
