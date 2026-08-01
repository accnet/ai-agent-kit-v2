# Kubernetes Pitfalls

- Missing readiness probes causing traffic to unready pods.
- Resource limits too low/high, causing throttling or noisy-neighbor impact.
- Mutable tags (latest) breaking reproducibility.
- Security context omitted for internet-facing workloads.
