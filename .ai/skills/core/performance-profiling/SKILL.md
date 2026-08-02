---
name: performance-profiling
description: Measure and improve latency, throughput, memory, and query behavior without speculative optimization.
version: 2.1.0
tier: core
stack: [any]
owner: performance
gates: [G2, G3]
related: [observability, test-and-validation]
---

# Skill: performance-profiling

## Purpose
Make performance changes from measured baselines and explicit budgets — not from intuition,
assumptions about which code path is slow, or from optimizing code that isn't on the hot
path. Every optimization should start with a profiling session that names the bottleneck,
and end with a re-measurement that confirms the improvement on the same workload.

## When to use
A task identifies a latency, throughput, memory, or cost regression. An SLO alert fires.
A feature is approaching a known budget limit (query count per request, token budget per
call, memory per process). A code review flags an N+1 query or an O(n²) operation in a
hot path. Do not apply this skill speculatively to code that hasn't been measured.

## Procedure

1. **Define the performance objective and acceptance threshold.** State the metric, the
   current measured value, and the target: "p95 response time for `GET /search` must be
   below 200ms under 100 concurrent users; currently measuring 480ms." Without a specific
   threshold, there is no way to know when the work is done. Record the acceptance threshold
   in the task's acceptance criteria before starting.
2. **Establish a reproducible baseline.** Run the workload that triggers the slow path
   under controlled conditions:
   - Use a consistent dataset size and request pattern (a recorded traffic sample, a
     synthetic load generator, or a benchmark script checked into the repo).
   - Capture: p50/p95/p99 latency, request rate (RPS), error rate, CPU/memory/goroutine
     count (or equivalent), and — for data-heavy paths — query count and total DB time.
   - Record the environment (hardware tier, container size, concurrency settings) so the
     result can be reproduced or compared later.
3. **Profile the hot path to locate the dominant bottleneck.** Use the appropriate profiler
   for the stack:
   - Node.js: `--prof` + `node --prof-process`, clinic.js, or `0x`
   - Python: `cProfile` + `pstats`, `py-spy`, or `austin`
   - Go: `pprof` (CPU, memory, goroutine) via `net/http/pprof`
   - Database queries: `EXPLAIN ANALYZE` (PostgreSQL/MySQL), query plan cache hit ratio
   Do not guess which function is slow from the source code — read the profile. A profile
   that shows 80% of time in a third-party library means the bottleneck is not where you
   expected.
4. **Apply the smallest change that addresses the measured bottleneck.** Common verified
   approaches:
   - Database: add an index on the filtered/sorted column; rewrite to avoid N+1 (batch
     with `IN`/`JOIN`/data-loader); paginate instead of fetching unbounded result sets.
   - CPU: cache an expensive computed value that doesn't change per-request; move work
     off the hot path (lazy evaluation, async, background job).
   - Memory: stream large payloads instead of buffering; fix a reference leak identified
     by the heap profile; reduce allocation rate on the hot path.
   Make only the change the profile points to. Do not refactor surrounding code "while
   you're in there" — it obscures whether the performance change actually caused the
   improvement.
5. **Re-measure with the same workload and environment.** Run the exact same benchmark
   used for the baseline. Capture the same set of metrics. The improvement is real only
   if the numbers are better *on the same workload* — a different dataset size or
   concurrency level makes the comparison meaningless.
6. **Verify no correctness or security regression.** Run the full test suite after the
   change. Common performance optimizations that introduce bugs: caching a value that
   should be recalculated per-request, removing a validation step that was also a
   correctness check, batching queries that should be executed serially for data integrity.
7. **Update monitoring to reflect the new budget.** If the optimization changes the
   expected operating range (e.g., p95 drops from 480ms to 90ms), update the SLO
   threshold and alert threshold accordingly. An alert tuned for the old slow baseline
   will never fire on a real regression against the new fast baseline.

## Checklist
- [ ] Performance objective and acceptance threshold stated before any code change
- [ ] Baseline captured with specific metrics (p50/p95, RPS, DB query count) on a
      reproducible workload
- [ ] Profiler output identifies the dominant bottleneck (not a guess)
- [ ] Change targets only what the profile identified; no unrelated refactors bundled
- [ ] Post-change metrics captured with the same workload and environment
- [ ] Improvement confirmed against the acceptance threshold
- [ ] Full test suite passes; no correctness regressions
- [ ] SLO and alert thresholds updated to reflect new operating range

## Anti-patterns
- Optimizing a code path that isn't on the measured hot path — the profile will tell you
  if this is happening; ignore it at the cost of wasted effort.
- Reporting only average (mean) latency — a mean can look excellent while p99 regresses
  badly; always capture and report percentiles.
- Introducing a cache without an expiry or invalidation strategy — over time, stale data
  causes correctness failures that look like intermittent bugs.
- Trading correctness for speed without explicit approval and a documented trade-off record
  — this is the class of "optimization" that causes the next incident.
- Measuring in a development environment and declaring victory — development environments
  have different CPU speeds, I/O, and concurrency characteristics; measure in an environment
  that resembles production.

## Output
Baseline and post-change metrics (in a task note or `.ai-work/` file), profiler output
identifying the bottleneck, the diff (minimal change addressing the bottleneck), re-measured
metrics confirming improvement, and updated SLO/alert thresholds if the operating range
changed.
