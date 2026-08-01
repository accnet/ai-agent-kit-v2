# React Vite Patterns

- Route-level code splitting via `React.lazy(() => import('./Page'))` + `Suspense`, so
  Vite's per-chunk output actually shrinks the initial bundle instead of one flat chunk.
- Keep data loading in a hook or loader function, not inside a presentation component, so
  the component stays testable without mocking `fetch`.
- Read env through `import.meta.env` in exactly one typed config module (e.g.
  `src/config/env.ts`), not scattered across components.
- Handle loading, error, and empty states explicitly for every async view — a component
  that only renders the happy path is incomplete.
- Use the same Vite config (aliases, JSX transform) for Vitest component tests as for the
  app, so a test's module resolution matches production's.
