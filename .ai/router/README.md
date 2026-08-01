# Agent Router

Use `python .ai/engine/ai_kit.py route T<n>` to return the assigned v2 role
contract, scoped technology knowledge, imported core skills, and minimal task
context paths. Assignment follows the task owner set by Planner; Router does
not silently reassign work.

Route output includes:

- `skills` (backward-compatible list of selected entrypoints)
- `skill_details` (name/path/entrypoint/documents/selection reasons/loading
  phase/loading order/type)
- `trigger_matches` (registry trigger hits and rationale)
- `loading_instructions` (progressive loading contract)

Use `python .ai/engine/ai_kit.py route T<n> --explain` for token-level and
phase-level selection diagnostics. Trigger rules are configured in
`.ai-config/registry.yaml` under `skill_triggers`.
