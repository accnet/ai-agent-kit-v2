# Vue Evidence

Verification: `vue-tsc --noEmit` reports no type errors, a Vitest component test mounts the component and asserts rendered output, a Pinia store unit test confirms state mutations, and a Playwright test navigates a route that requires auth and verifies the guard redirects unauthenticated users.
