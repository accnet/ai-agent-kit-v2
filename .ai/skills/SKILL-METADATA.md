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
