---
name: accessibility
description: Build and review accessible interfaces with semantic structure, keyboard operation, and assistive technology support.
version: 2.0.0
tier: core
stack: [any]
owner: frontend
gates: [G2, G3]
related: []
---

# Skill: accessibility

## Purpose
Ship accessible UI changes with keyboard, screen-reader, and error-feedback behavior verified as evidence.

## When to use
Any UI, form, navigation, modal, or interaction change that users can see or operate.

## Procedure
1. Identify changed user journeys and interactive elements; list required keyboard and screen-reader outcomes.
2. Apply semantic HTML first; add ARIA only where native semantics are insufficient.
3. Ensure focus order, focus visibility, and focus return for dialogs/menus/dynamic panels.
4. Expose input errors with programmatic association (`aria-describedby`, live regions) and actionable text.
5. Verify manually using keyboard-only flow and at least one screen reader smoke pass for changed paths.

## Checklist
- [ ] All changed controls have accessible names and states.
- [ ] Keyboard-only journey works end-to-end (including escape/close actions).
- [ ] Focus is visible and returns predictably after transient UI closes.
- [ ] Error and status announcements are perceivable to assistive technology.
- [ ] Color contrast and non-color affordances are preserved for changed UI.

## Anti-patterns
- Adding ARIA roles that conflict with native semantics.
- Relying on pointer-only interactions with no keyboard equivalent.
- Treating visual pass as accessibility pass without assistive-tech evidence.

## Output
Changed UI + accessibility verification notes (keyboard and assistive-tech evidence paths).
