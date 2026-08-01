# NestJS Core Pitfalls

- Injecting a TypeORM/Prisma repository directly into a controller, skipping the service
  layer that should own the business rule.
- Global mutable state (a module-level variable) shared across requests, which breaks
  under concurrent requests at the default singleton scope.
- Letting an ORM/database error escape all the way to the HTTP response, exposing the
  database engine and schema shape to a client.
- Trusting a client-supplied `userId`/`tenantId` in the request body instead of reading it
  from the authenticated principal a guard already validated.
