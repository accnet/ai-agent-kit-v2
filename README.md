# AI-Kit v2

AI-Kit v2 is a repository-local operating kit for coding agents. It retains
v2's role folders, workflow families, and technology knowledge while adding
the planning, validation, and review controls proven in v1.

## Quick Start

1. Adapt `project` and `verification` in `.ai-config/kit.yaml` for the host project.
2. Run `bash .ai/scripts/bootstrap.sh` and `bash .ai/scripts/doctor.sh`.
3. Initialize a workflow, add tasks with acceptance criteria, then validate it.

```bash
python .ai/engine/ai_kit.py init --title "My feature" --workflow feature --force
python .ai/engine/ai_kit.py add-task T1 --title "Plan" --owner planner --phase plan --acceptance "Plan reviewed"
python .ai/engine/ai_kit.py add-task T2 --title "Build" --owner backend --phase build --needs T1 --acceptance "Focused tests pass"
python .ai/engine/ai_kit.py ready
python .ai/engine/ai_kit.py route T1
python .ai/engine/ai_kit.py route T1 --explain
```

Move a task through `start`, `complete`, `qa-pass`, `review-approve`, and
`close`; the engine rejects illegal transitions. All transitions are persisted
to `.ai-work/state/workflow.json` and audit events to `.ai-work/logs/events.jsonl`.

The kit is tool-agnostic. `AGENTS.md` is the authoritative instruction file.

## Skill Routing And Metadata

- `route T<n>` now returns:
  - backward-compatible `skills` entrypoints
  - `skill_details` with each selected skill's path, entrypoint, full document
    list, selection reasons, and loading phase/order
  - `trigger_matches` and `loading_instructions`
- `route T<n> --explain` adds routing diagnostics (`role_domains`, task tokens,
  phase order, and selection counts).
- Technology skills use `skill.meta.yaml`; schema is documented in
  `.ai/skills/SKILL-METADATA.md`.

## Gate Rules Configuration

Gate behaviour is controlled by `.ai-config/rules.yaml`. The engine reads it
on every validation and applies the settings without requiring a restart.

```yaml
# .ai-config/rules.yaml
planning_first: true           # G1: enforce plan-phase dependencies
minimal_context: true          # load only minimal task context
review_required: true          # G3: require review evidence before done
db_changes_require_plan: true  # db/migration work always needs a plan
no_secrets_in_commits: true    # G4: prevent secret commits
destructive_operations_require_approval: true  # G5: require explicit approval
```

Toggle a rule to `false` to disable its enforcement:

```yaml
# Disable G1 planning gate during rapid prototyping
planning_first: false
# Disable G3 review gate for documentation-only tasks
review_required: false
```

When the file is missing or unreadable, every rule silently defaults to
`true` (maximum safety). The engine uses regex-based parsing with no
external dependencies (no PyYAML required).

## Install Into A Project

Copy this repository's `.ai/` directory into the target project root (so the
project ends up with a top-level `.ai/` folder), then run the installer from
inside that project. It materializes root-level adapter files (`AGENTS.md`,
`CLAUDE.md`, `.cursor/`, `.windsurf/`, etc.) from `.ai/install/templates/` and
seeds `.ai-config/` from `.ai/install/config/`, without touching the kit's
`.ai-work` session state:

```bash
bash .ai/install/install.sh --dry-run
bash .ai/install/install.sh
```

On Windows PowerShell:

```powershell
.\.ai\install\install.ps1 -DryRun
.\.ai\install\install.ps1
```

Both installers stop before replacing a different managed file. Use
`--force` or `-Force` only after reviewing the conflicts. Pass `--target` or
`-Target` to install into a directory other than the parent of `.ai/`.

## Layout

- `.ai/engine/`: dependency-free Python control plane: state, DAG scheduler,
  lifecycle, router, and audit events.
- `.ai/agents/`: v2 role contracts, split into six concise documents.
- `.ai/skills/`: technology reference material, grouped by domain.
- `.ai/workflows/`: feature, bugfix, migration, release, and research paths.
- `.ai/modules/`: gates and operating standards.
- `.ai/scripts/`: v2 adapters for v1 bootstrap, scheduling, state, context,
  skill validation, and commit-hygiene automation.
- `.ai/install/`: installer, root-adapter templates, and `.ai-config/` seed
  files used to onboard a host project.
- `.ai-config/`: project-owned configuration (`kit.yaml`, `rules.yaml`,
  `runners.yaml`, `contexts.yaml`, `epics.yaml`, `registry.yaml`,
  `automation.yaml`); never overwritten by re-installs.
- `.ai-work/`: current plan, tasks, and ephemeral state.

## Skill Validation Modes

`bash .ai/scripts/check-skills.sh` defaults to `all` and enforces:

- required documents and non-empty content
- placeholder marker rejection
- metadata contract/path alignment (`skill.meta.yaml`)
- core `SKILL.md` front matter contract

Additional modes:

- `bash .ai/scripts/check-skills.sh core` — core skills only
- `bash .ai/scripts/check-skills.sh ai` — AI technology skills plus AI-trigger
  core skills

## Compatibility with v1

v1's lifecycle controls are adapted rather than copied over its incompatible
layout. Its twelve reusable core skills are preserved under
`.ai/skills/core/<skill>/SKILL.md` with source attribution and v2 adapters.
Its scripts inform the v2 wrappers, which operate on `.ai-work` workflow state
instead of v1's `.project` files. No v2 path is removed or renamed.
