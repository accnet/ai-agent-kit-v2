# Nuxt Best Practices

<<<<<<< HEAD
Enable TypeScript (`typescript.strict: true`) and use typed composables. Avoid `<ClientOnly>` wrappers for critical UI content — they suppress SSR hydration and hurt SEO. Test pages with Vitest + `@nuxt/test-utils` or Playwright for E2E. Use `definePageMeta` for layout, middleware, and route validation declarations. Lazy-load heavy components with `<LazyMyComponent>`. Set appropriate Cache-Control headers for SSG/ISR pages. Validate form data server-side in `server/api/` routes, not only on the client.
=======
- Guard browser-only APIs behind client checks.
- Validate route params and query state before data fetching.
- Use typed APIs/composables where project tooling allows.
- Add component/page tests for critical journeys and error states.
>>>>>>> origin/main
