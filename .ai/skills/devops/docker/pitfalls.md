# Docker Pitfalls

- **`COPY . .` before installing dependencies** busts the dependency-layer
  cache on every source change, turning every build into a full
  reinstall — copy manifest files and install first, source last.
- **Secrets baked into layers via `ARG`/`ENV`.** Even if removed in a later
  layer, `docker history` (and any registry mirror of the pushed image)
  still exposes the value from the layer it was set in.
- **`latest` tag in any environment that needs reproducibility.** A
  rebuild months later can silently pull a different major version of the
  base image.
- **Running as root by default** — the Dockerfile default `USER` is root
  unless set explicitly; a container escape or path-traversal bug then
  gets root inside the container for free.
- **No `HEALTHCHECK`** on a service other containers depend on via
  `depends_on:` — plain `depends_on` (without a `condition:
  service_healthy`) only waits for the container to *start*, not for the
  app inside it to be ready, causing race-condition failures on cold start.
- **Not pruning apt/package caches in the same `RUN` layer** as the
  install — a later `RUN rm -rf /var/lib/apt/lists/*` doesn't shrink the
  layer that already contains the cache.
- **Ignoring `.dockerignore`.** Without it, the build context includes
  `.git`, `node_modules`, and local env files, slowing every build and
  risking accidental inclusion of secrets/local config in the image.
- **Building without `--platform` in a mixed-arch environment** (Apple
  Silicon dev machines, ARM production hosts) — an image built for the
  wrong architecture fails at container start with an exec format error,
  not at build time.
