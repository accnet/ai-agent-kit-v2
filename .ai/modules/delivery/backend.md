<!-- AI-Kit v2 adaptation of reusable v1 guidance. -->

---
name: backend
description: Server-side implementation standards (framework-agnostic). Load for backend tasks; pairs with the nodejs-api-core skill for Node/TS.
---

# Module: Backend

## Purpose
Implementation standards for server-side work, independent of framework (framework specifics come from existing code + .ai/memory/conventions.md).

## When to Load
Any task owned by the Backend agent.

## Standards
- **Boundaries**: validate at the edge (request), trust inside; one place per concern
- **Errors**: every failure path returns a defined, typed error; no swallowed exceptions; no leaking internals in messages
- **Auth**: every endpoint declares its auth requirement explicitly — "none" must be written, not implied
- **Logging**: log decisions and failures with context (ids, not payloads); never log secrets/PII
- **Transactions**: multi-step writes are atomic or explicitly compensated
- **Config**: environment-dependent values come from config, never inline

## Checklist (per task)
- [ ] Input validated at the boundary
- [ ] Failure paths defined and tested
- [ ] Auth requirement explicit
- [ ] No secrets/PII in logs or code
- [ ] Unit tests cover logic branches, not just the happy path

## Output
Code + tests conforming to the project's conventions.
