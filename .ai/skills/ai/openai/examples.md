# OpenAI Integration Evidence

Verification: a unit test mocks the OpenAI client and asserts the service returns a typed result; a test for the retry path confirms back-off on a mocked 429 response; `usage.total_tokens` is logged for each production call; structured output is validated against the declared JSON schema; no API key appears in committed files or logs.
