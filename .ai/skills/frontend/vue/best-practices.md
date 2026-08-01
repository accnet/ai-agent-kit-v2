# Vue Best Practices

<<<<<<< HEAD
Enable strict TypeScript in the project (Volar + `vue-tsc`). Use `v-bind` shorthand (`:`) and `v-on` shorthand (`@`). Always provide a `key` attribute on `v-for` elements. Avoid accessing DOM directly; use template refs (`ref()`) when direct manipulation is necessary. Test components with Vitest + `@vue/test-utils`; test stores independently. Lazy-load route components with `defineAsyncComponent` or `import()` in the router to reduce the initial bundle. Use `watch` with `{ immediate: false }` by default and only enable `immediate` when the initial run is required.
=======
- Use computed properties for derived state and watchers only for side effects.
- Validate incoming props and guard optional fields.
- Keep template semantics accessible (labels, roles, keyboard flow).
- Minimize global mutable state and document state ownership.
>>>>>>> origin/main
