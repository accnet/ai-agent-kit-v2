# Changelog

## [Unreleased]

### Added

- Configurable gates: G1 (planning_first) and G3 (review_required) can now be
  toggled via `.ai/rules.yaml` without engine changes.
- Documentation: AGENTS.md now has a "Configurable Gates" table; README.md has
  a "Gate Rules Configuration" section with usage examples.
- Engine comments added to `_load_rules()` and `validate()` explaining the
  rules integration contract.
