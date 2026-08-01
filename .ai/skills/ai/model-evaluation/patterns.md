# Model Evaluation Patterns

- Maintain a versioned benchmark set with representative and adversarial cases.
- Score outputs with deterministic metrics where possible (exact match/schema pass) and rubric scores where needed.
- Compare candidate vs baseline with acceptance thresholds.
- Record evaluation metadata: model, prompt version, dataset version, timestamp.
