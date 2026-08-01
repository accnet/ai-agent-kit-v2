<<<<<<< HEAD
# Kubernetes Evidence

Verification: `kubectl apply --dry-run=server -f manifests/` exits 0, `kubectl get pods -n <namespace>` shows all pods Running/Ready, readiness probe succeeds before traffic is routed (checked via endpoint status), and a `kubectl rollout undo` restores the previous version within the defined rollout timeout.
=======
# Kubernetes Examples

- Add liveness/readiness probes and conservative resource requests.
- Rollout with progressive traffic shift and watch error rate/latency.
- Evidence: manifest diff + rollout status + post-deploy SLO checks.
>>>>>>> origin/main
