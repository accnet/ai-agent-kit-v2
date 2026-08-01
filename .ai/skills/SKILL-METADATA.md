# Skill Metadata Contract

Every technology skill directory under `.ai/skills/<domain>/<technology>/` must include
a `skill.meta.yaml` sidecar file. This file provides machine-readable identity and
compatibility information for routing, validation, and tooling.

## Required Fields

| Field | Type | Description |
|---|---|---|
| `skill_name` | string | Human-readable name of the skill |
| `domain` | string | Domain name matching the directory (e.g. `backend`, `ai`) |
| `technology` | string | Technology name matching the directory |
| `owner` | string | Responsible role (must match a role in `.ai-config/registry.yaml`) |
| `version` | string (quoted) | Revision of this skill document, starting at `"1.0"` |
| `reviewed_at` | string (ISO 8601 date) | Date this skill was last reviewed, e.g. `"2026-08-01"` |
| `supported_stack` | list of strings | Stack tags this skill applies to (used by router) |

## Format

Plain YAML without anchors or multi-line values. No external parser required.

```yaml
skill_name: My Technology
domain: backend
technology: my-technology
owner: backend
version: "1.0"
reviewed_at: "2026-08-01"
supported_stack: [my-tech, my-framework]
```

## Validation

`bash .ai/scripts/check-skills.sh` (with `ai` or `all` argument) validates:

1. All required fields are present and non-empty.
2. `reviewed_at` matches the pattern `YYYY-MM-DD`.
3. `domain` matches the directory's second path segment.
4. `technology` matches the directory's third path segment.

## Precedence

Metadata is informational for routing; the router still uses `registry.yaml`
`owners` for role→domain mapping. `supported_stack` supplements the runtime
stack (from `kit.yaml` `project.stack` and task tags) to refine which
technology skills are loaded.
