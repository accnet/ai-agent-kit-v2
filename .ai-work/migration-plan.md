# Plan - retire v1 and complete v2

Status: active

## Goal
Complete v2 runtime orchestration: convert an idea into a seeded plan, route
only stack-relevant skills, require QA/review evidence, and align guidance with
the canonical workflow state.

## Rules
- Preserve v2 nested agents, skills, workflows, engine, and `.ai-work` state.
- State transitions remain the sole lifecycle authority.
- The planner produces a draft only; it never invents business requirements.

## Tasks
- [x] T1 Add an idea-to-plan command with explicit assumptions and task seed.
- [x] T2 Add stack-aware routing and a consistent skill output contract.
- [x] T3 Require evidence for QA and review transitions.
- [x] T4 Align agent guidance/templates with canonical workflow state.
- [x] T5 Extend tests and validate the completed flow.
