# Vite Frontend Best Practices

- Validate required `VITE_*` variables at startup (throw with a clear message) rather
  than letting a missing one surface as `undefined` deep inside a component.
- Run `vite build` and inspect the output bundle/chunk sizes whenever a change touches
  dependencies, dynamic imports, or `manualChunks`.
- Keep dev-only tooling (mock servers, debug overlays) behind a `mode` check so it can
  never ship in a production build.
- Pin the Vite major version and re-verify config after upgrading — plugin APIs and
  default behaviors change across majors.
