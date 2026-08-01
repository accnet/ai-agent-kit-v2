# NestJS Core Best Practices

- Validate configuration at boot with `ConfigModule.forRoot({ validationSchema })`
  (Joi/Zod), so a missing env var fails fast at startup instead of mid-request.
- Export only what a module's consumers actually need from `providers`; keep internal
  providers un-exported so other modules can't reach past the module's public surface.
- Test with `Test.createTestingModule(...)` and a mocked/in-memory provider for
  service-level unit tests; reserve a real database for integration tests.
- Give one guard one responsibility (authentication vs. a role check) and compose them,
  rather than one guard doing both.
