# Kubernetes Pitfalls

<<<<<<< HEAD
Do not run containers as root unless the workload explicitly requires it; use `securityContext.runAsNonRoot: true`. Do not use `hostNetwork` or `hostPID` without a documented security justification. Do not allow pods to mount the Docker socket. Do not set CPU limits aggressively low — CPU throttling causes latency spikes without OOM kills. Do not use `kubectl edit` on production workloads; all changes must go through version-controlled manifests and CI. Do not store sensitive values in ConfigMaps; use Secrets and restrict access with RBAC.
=======
- Missing readiness probes causing traffic to unready pods.
- Resource limits too low/high, causing throttling or noisy-neighbor impact.
- Mutable tags (latest) breaking reproducibility.
- Security context omitted for internet-facing workloads.
>>>>>>> origin/main
