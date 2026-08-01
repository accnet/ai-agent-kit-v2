# Kubernetes Best Practices

- Keep manifests DRY through existing templating approach (Helm/Kustomize).
- Validate RBAC least privilege for service accounts.
- Define PodDisruptionBudget and horizontal scaling behavior where needed.
- Capture rollout and rollback commands in release notes.
