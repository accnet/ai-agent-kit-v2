# NestJS Core Patterns

- Controllers only translate HTTP to/from DTOs and call one provider method; no business
  logic and no direct repository access in a controller.
- Validate every incoming DTO with `class-validator` decorators plus a global
  `ValidationPipe({ whitelist: true, forbidNonWhitelisted: true })`.
- Authorize via `@UseGuards(AuthGuard, RolesGuard)`, not an `if` check buried inside a
  service method — guards are visible in the route signature, ad hoc checks are not.
- Map domain/provider errors to HTTP responses through an `ExceptionFilter`, so a database
  error never leaks its native shape to a client.
- Keep providers request-scoped only when they must hold per-request state (e.g. tenant
  context); the default singleton scope is cheaper, and request scope has a real
  per-request instantiation cost.
