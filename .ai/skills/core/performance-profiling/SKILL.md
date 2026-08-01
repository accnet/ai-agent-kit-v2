---
name: performance-profiling
description: Measure and improve latency, throughput, memory, and query behavior without speculative optimization.
version: 2.0.0
tier: core
stack: [any]
owner: performance
gates: [G2, G3]
related: []
---

# Skill: performance-profiling

## Purpose
Make performance changes from measured baselines and explicit budgets, not intuition.

## When to use
Tasks involve latency, throughput, memory, token usage, query volume, or cost-sensitive paths.

## Procedure
1. Define performance objective and baseline measurement (p50/p95 latency, CPU, memory, token/cost).
2. Profile the hot path to identify dominant contributors.
3. Apply the smallest change addressing the measured bottleneck.
4. Re-measure with same workload; compare against baseline and acceptance target.
5. Record trade-offs (quality/cost/complexity) and monitoring implications.

## Checklist
- [ ] Baseline and post-change metrics are captured.
- [ ] Bottleneck evidence points to changed code path.
- [ ] No correctness/security regressions introduced.
- [ ] Monitoring/alerting reflects new budget assumptions.
- [ ] Results are reproducible with documented command/workload.

## Anti-patterns
- Optimizing code paths without profiling evidence.
- Reporting only average latency while p95/p99 regresses.
- Trading correctness for speed without explicit approval.

## Output
Before/after performance evidence with reproducible methodology.
