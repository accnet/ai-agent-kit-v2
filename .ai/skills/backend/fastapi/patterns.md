# FastAPI Patterns

- Keep route handlers thin; delegate business logic to services.
- Use dependency injection for auth, DB sessions, and shared clients.
- Define request/response models explicitly and keep backward compatibility in mind.
- Add exception handlers mapping domain errors to stable API responses.
