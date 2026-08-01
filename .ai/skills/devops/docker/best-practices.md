# Docker Best Practices

- Pin the base image to a specific version tag, not `latest`; bump it as a
  deliberate, reviewed change.
- Run the final-stage process as a non-root `USER`; drop capabilities the
  container doesn't need instead of running privileged.
- Keep the shipped image minimal: multi-stage build so compilers, dev
  dependencies, and package-manager caches never reach the runtime image.
- Combine `RUN` steps that install-then-clean in a single layer (e.g.
  `apt-get update && apt-get install -y x && rm -rf /var/lib/apt/lists/*`)
  — cleanup in a later `RUN` doesn't shrink earlier layers, since Docker
  layers are additive.
- Pass secrets via build secrets (`--secret` / `RUN --mount=type=secret`)
  or runtime environment injection, never via `ARG`/`ENV` baked into a
  layer — both are visible in the image's history and any pushed layer.
- Set explicit resource limits (`--memory`, `--cpus`, or the Compose/K8s
  equivalent) in any orchestrated environment instead of relying on the
  host's defaults.
- Add a `HEALTHCHECK` (or the orchestrator's readiness/liveness probe
  equivalent) so restarts and load-balancer routing react to real
  application health, not just process-exists.
