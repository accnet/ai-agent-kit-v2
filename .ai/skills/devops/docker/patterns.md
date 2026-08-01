# Docker Patterns

- **Multi-stage builds**: a `builder` stage with the full toolchain
  (compilers, dev dependencies) produces the artifact; a slim final stage
  (`FROM node:20-alpine`, `distroless`, or similar) copies only the built
  output (`COPY --from=builder /app/dist ./dist`). Keeps the shipped image
  free of build tools and dev dependencies.
- **Order layers by change frequency.** `COPY package*.json ./` +
  `RUN npm ci` *before* `COPY . .` — dependency layers stay cached across
  builds where only source changed, instead of reinstalling on every
  build.
- **Non-root `USER`.** Create and switch to an unprivileged user before
  `CMD`/`ENTRYPOINT`; only the build stage needs root for package
  installation.
- **`ENTRYPOINT` + `CMD` split**: `ENTRYPOINT` fixes the executable,
  `CMD` supplies default, overridable arguments — lets `docker run image
  --flag` override behavior without rebuilding the image.
- **`HEALTHCHECK`** for anything orchestrated by Docker Compose or Swarm
  restart policies, so a hung-but-running process is detected instead of
  looking healthy indefinitely.
- **Pin the base image tag (and consider a digest)**: `FROM node:20.11-alpine`
  or `FROM node:20.11-alpine@sha256:...` instead of `FROM node:latest`,
  which can change the toolchain version under you between builds.
- **`.dockerignore`** mirrors `.gitignore` at minimum (`node_modules`,
  `.git`, build artifacts) — without it, `COPY . .` invalidates the cache
  and bloats context on every change to any ignored file.
