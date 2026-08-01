# Docker Compose Local Pitfalls

- Copying production secrets into a local `.env` instead of using throwaway local
  credentials — a leaked laptop or shared screen now exposes real secrets.
- Depending on container start order without health checks, so the app container starts
  before the database is actually accepting connections and fails intermittently.
- Mounting a broad host path (`.:/app` at the repo root) that also pulls host-only files
  (`.git`, a `node_modules` built for the wrong platform) into the container.
- Letting the local compose file drift from what staging/production actually expect
  (different env var names, a missing service), so "works locally" stops predicting
  anything.
