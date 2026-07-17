---
name: observability
description: Make a change observable in production — structured logs, metrics, traces, and an SLO/alert. Use when shipping a feature or fixing an incident so behavior can be seen and alerted on, not guessed.
version: 0.1.0
tier: core
stack: [any]
owner: backend
gates: [G3]
related: [deployment-infra, debugging, code-review]
---

# Skill: observability

## Purpose
Ensure every meaningful change ships with the signals to see it working — so problems are detected by alerts and diagnosed from telemetry, not from user reports. Observability is part of "done", checked at review (G3).

## When to use
Shipping a feature that adds a code path worth watching, wiring a new service, or after an incident where the missing signal was the real problem.

## Procedure
1. **Logs**: structured (key/value or JSON), one event per meaningful step; include a correlation/request id; never log secrets or PII.
2. **Metrics**: the few that matter — rate, errors, duration (RED) for a request path; saturation for a resource. Name and label consistently with existing metrics.
3. **Traces**: span the critical path across service boundaries so latency and failures are attributable.
4. **SLO + alert**: define what "healthy" means (e.g. error rate / p95 latency) and one actionable alert tied to it — alert on symptoms users feel, not on every cause.
5. **Verify**: trigger the path in a lower env and confirm the signal shows up before relying on it.

## Checklist
- [ ] Structured logs on the new path; correlation id; no secrets/PII
- [ ] RED metrics (rate/errors/duration) emitted and labeled consistently
- [ ] Trace spans cross the relevant service boundaries
- [ ] One actionable, symptom-based alert tied to an SLO
- [ ] Signal verified in a lower environment

## Anti-patterns
- Logging secrets/PII, or unstructured `print`-style logs
- A metric per cause and none for the user-facing symptom
- Noisy alerts on causes → alert fatigue → ignored pages
- "We'll add monitoring later" (it never comes; the incident does)

## Output
Instrumentation in the code + dashboard/alert definitions (or a note pointing to them) + a task note; gaps found become follow-up tasks.
