# Nuxt Pitfalls

Do not access `window` or `document` at module level — they are undefined during SSR; guard with `if (process.client)` or `onMounted`. Do not store sensitive values in `publicRuntimeConfig` / `runtimeConfig.public` — they are exposed to the browser. Do not mutate `useRoute()` state directly; use `navigateTo()` for navigation. Avoid blocking `useAsyncData` with heavyweight server calls on every request for pages that could use SSG or ISR. Do not register plugins that have side effects on both client and server without a guard (`process.server` / `process.client`).
