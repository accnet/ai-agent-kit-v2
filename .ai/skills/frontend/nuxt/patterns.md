# Nuxt Patterns

<<<<<<< HEAD
Place pages under `pages/`, shared UI components under `components/` (auto-imported), server API routes under `server/api/` (Nuxt 3). Use composables for reactive state shared across components. Prefer `useAsyncData` / `useFetch` over raw fetch calls to benefit from SSR hydration and caching. Centralise environment variables in `runtimeConfig`; access them via `useRuntimeConfig()` rather than `process.env` in component code. Use Nuxt modules for cross-cutting concerns (authentication, i18n, image optimisation) rather than custom plugins when a maintained module exists.
=======
- Keep page components focused on composition; extract reusable logic to composables.
- Use server routes or backend APIs for privileged operations; avoid exposing secrets client-side.
- Cache and prefetch strategically for SSR hydration performance.
- Centralize runtime config access and environment-specific toggles.
>>>>>>> origin/main
