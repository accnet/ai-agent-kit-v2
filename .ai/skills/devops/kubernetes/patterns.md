# Kubernetes Patterns

<<<<<<< HEAD
Declare all workloads as Deployments or StatefulSets with explicit `replicas`, `resources.requests`, and `resources.limits`. Define liveness and readiness probes for every container. Use ConfigMaps for non-sensitive configuration and Secrets (or an external secrets operator) for credentials. Namespace workloads by environment; never deploy directly to `default`. Use rolling updates with a defined `maxSurge`/`maxUnavailable` strategy. Apply RBAC with least-privilege: create dedicated ServiceAccounts and bind them to minimal Roles.
=======
- Deploy immutable container images by digest/tag policy.
- Set requests/limits and health probes for every workload.
- Use rolling/canary strategies with readiness gates.
- Externalize config via ConfigMap/Secret references, not baked values.
>>>>>>> origin/main
