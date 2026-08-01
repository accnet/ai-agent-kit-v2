<<<<<<< HEAD
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
=======
# Skill Metadata Schema

Technology skills under `.ai/skills/<domain>/<technology>/` must include
`skill.meta.yaml`.

## Required fields

- `name`: technology directory name
- `domain`: top-level skill domain directory name
- `version`: semantic version of this skill knowledge pack
- `owner`: primary role responsible for maintaining the skill
- `reviewed_at`: ISO date for the latest review (`YYYY-MM-DD`)
- `entrypoint`: repository-relative path to the primary document (normally
  `overview.md`)
- `path`: repository-relative path to the skill directory
- `documents`: ordered list of available documents for progressive loading

## Optional fields

- `status`: lifecycle state (`active`, `draft`, `experimental`, `deprecated`)
- `reviewers`: roles or maintainers who reviewed this skill
- `depends_on`: other skills this skill expects to be loaded first
- `triggers`: trigger keywords or trigger IDs that commonly select this skill
- `deprecated`: boolean marker for compatibility-only skills

## Document contract

`documents` must enumerate the repository files that exist for the skill.
Standard technology skills use:

- `overview.md`
- `patterns.md`
- `best-practices.md`
- `pitfalls.md`
- `examples.md`

## Validation expectations

`bash .ai/scripts/check-skills.sh all` validates:

- metadata file exists for every technology skill
- required fields are present and non-empty
- `path`, `domain`, and `name` match the filesystem location
- `entrypoint` exists and is under `path`
- every listed `documents` file exists and is non-empty
- optional fields (`status`, `reviewers`, `depends_on`, `triggers`,
  `deprecated`) are well-formed when present
>>>>>>> origin/main
