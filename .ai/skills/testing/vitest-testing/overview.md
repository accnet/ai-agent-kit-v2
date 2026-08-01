# Vitest Testing

Vitest is Vite's native test runner: it shares Vite's config, resolves the same aliases,
and reuses the same transform pipeline, so tests run against the same module graph the
app builds with. Use it for unit, integration, mock-boundary, and coverage testing in any
Vite-based project.

Check the project's `vitest.config.ts` (or the `test` block in `vite.config.ts`) for the
configured environment (`node` vs `jsdom`/`happy-dom`), existing global setup files, and
coverage provider (`v8` or `istanbul`) before adding a new test file.
