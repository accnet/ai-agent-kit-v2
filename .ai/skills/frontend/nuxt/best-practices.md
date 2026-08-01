# Nuxt Best Practices

Enable TypeScript (`typescript.strict: true`) and use typed composables. Avoid `<ClientOnly>` wrappers for critical UI content — they suppress SSR hydration and hurt SEO. Test pages with Vitest + `@nuxt/test-utils` or Playwright for E2E. Use `definePageMeta` for layout, middleware, and route validation declarations. Lazy-load heavy components with `<LazyMyComponent>`. Set appropriate Cache-Control headers for SSG/ISR pages. Validate form data server-side in `server/api/` routes, not only on the client.
