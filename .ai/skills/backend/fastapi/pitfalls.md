# FastAPI Pitfalls

- Response model drift from actual payload.
- Implicit DB session lifecycle causing connection leaks.
- Exposing internal error details in HTTP responses.
- Middleware order changes breaking auth/cors behavior.
