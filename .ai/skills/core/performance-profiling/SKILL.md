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
Measure and improve latency, throughput, memory, and query behavior without speculative optimization.

## When to use
Use when a task matches this domain, before the owning agent claims completion.

## Procedure
Capture a baseline, isolate the bottleneck with profiler or traces, set a measurable budget, change one cause, and compare the same workload after the change.

## Checklist
- [ ] Baseline and workload are recorded
- [ ] Bottleneck evidence exists
- [ ] Budget is measurable
- [ ] Regression check passes

## Anti-patterns
- Marking work complete from intuition instead of recorded evidence.
- Expanding scope without a planned task and owner.

## Output
Record the decision, evidence paths, and residual risk in the workflow state and the appropriate .ai-work report.
