# Vite Frontend Pitfalls

- Putting a secret or server-only credential in a `VITE_`-prefixed variable — Vite inlines
  it into the client bundle, visible to any user via view-source.
- Assuming dev-server behavior (fast refresh, unbundled ESM) matches the production
  build; only `vite build` + `vite preview` exercises the real production path.
- Adding a path alias to `tsconfig.json` only, without mirroring it in `vite.config.ts` —
  the type checker resolves the import but the bundler fails.
- Importing a large library eagerly at the entry point instead of behind a dynamic
  `import()`, defeating code splitting for a rarely-used feature.
