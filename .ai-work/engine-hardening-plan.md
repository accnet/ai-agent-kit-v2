# Plan - workflow engine hardening

## Goal
Make workflow execution safe for parallel agents, evidence-backed, workspace
isolated, and self-validating from the CLI through CI.

## Tasks
- [x] T1 Isolate workspace artifacts and audit logs per workflow state.
- [x] T2 Enforce role, workflow, phase, evidence, and module-skill contracts.
- [x] T3 Add atomic persistence, revision checks, and force snapshots.
- [x] T4 Make stack/task routing explicit and minimize returned context.
- [x] T5 Separate durable artifacts from ephemeral runtime state.
- [x] T6 Add CLI and regression tests, then run full validation.
