# Vite Frontend Patterns

- Read all `import.meta.env.VITE_*` values through one typed module (e.g. `src/env.ts`)
  that validates and re-exports them, instead of accessing `import.meta.env` throughout
  the codebase.
- Use `manualChunks` or route-level dynamic `import()` deliberately for large
  dependencies, rather than letting one vendor chunk grow unbounded.
- Keep `resolve.alias` entries mirrored in `tsconfig.json` paths and any test runner
  config — Vite resolving a path differently than the type checker is a common source of
  "works in the editor, fails to build" bugs.
- Use Vite's `mode` (`vite build --mode staging`) and `.env.[mode]` files for
  environment-specific config, instead of branching on `NODE_ENV` inside app code.
