<!-- AI-Kit v2 adaptation of reusable v1 guidance. -->

---
name: frontend
description: UI implementation standards (framework-agnostic). Load for frontend tasks; pairs with the frontend-core skill.
---

# Module: Frontend

## Purpose
Implementation standards for UI work, independent of framework.

## When to Load
Any task owned by the Frontend agent.

## Standards
- **States**: every data-driven view implements loading / empty / error / success — designed, not defaulted
- **Reuse**: search existing components before writing a new one; extend before duplicating
- **Data**: API calls isolated in one layer; components never fetch inline; types mirror the contract exactly
- **Accessibility**: interactive elements are keyboard-reachable and labeled; color is never the only signal
- **State management**: local by default; lift only when shared; global only for truly app-wide state
- **Copy**: user-facing strings centralized, no hardcoded text in markup

## Checklist (per task)
- [ ] All four view states implemented
- [ ] No duplicated component logic
- [ ] Types match the API contract (no `any` bridges)
- [ ] Keyboard + label accessibility verified
- [ ] Component tests cover state transitions

## Output
UI code + tests consistent with existing component conventions.
