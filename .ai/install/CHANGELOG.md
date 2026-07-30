# Changelog

## [Unreleased]

### Added

- `reject` transition: sends `implementation-complete`/`qa-passed` tasks back
  to `todo` when QA/review finds work that must be redone, distinct from
  `block` (external impediments). Requires a `detail` and an actor different
  from `claimed_by`.
- `update-task` command: amends `acceptance`/`files`/`tags` on an existing
  task after creation, for tightening scope post-rejection without hand-editing
  `workflow.json`.
- `blocked_reason` field: set by `block`, shown in `tasks.md`, persists through
  `unblock` (cleared only on `start`).
- Bounded-context/module support: optional `task.context`, registered via
  `.ai/contexts.yaml` (`context add`/`context list`); gate **G6**
  (`module_boundary`, opt-in via `.ai/rules.yaml`) rejects a task whose
  `files` fall outside its context's registered path glob. `--context` filters
  `status`/`ready`/`graph`.
- Epic/blueprint rollups: optional `task.epic`; `ai-kit epics` reports
  per-epic totals and `percent_done`; `--epic` filters `status`/`ready`.
- Parallel-agent support: `--agent-id` on `transition`/`dispatch`/
  `dispatch-ready` records `claimed_by` as `role#agent_id` so concurrent
  agents sharing one role stay distinguishable (QA/review self-review guard
  compares the role portion only); `_retry_transition` retries a losing claim
  on `state changed concurrently`; new `dispatch-ready --runner X [--limit N]
  [--context C] [--epic E]` atomically claims and fans out N ready tasks to
  background runner processes.
- `verify` now prints a warning and reports `"warning"` when all four
  `*_command` entries in `.ai/kit.yaml` are still the placeholder `true`,
  since in that case only the security gate ran.
- Runner prompts are now shell-quoted (`shlex.quote`) before substitution to
  harden against injection from task titles/details.
- Configurable gates: G1 (planning_first) and G3 (review_required) can now be
  toggled via `.ai/rules.yaml` without engine changes.
- Documentation: AGENTS.md now has a "Configurable Gates" table; README.md has
  a "Gate Rules Configuration" section with usage examples.
- Engine comments added to `_load_rules()` and `validate()` explaining the
  rules integration contract.

### Fixed

- `install.sh`/`install.ps1`: `SOURCE` path resolution now accounts for both
  scripts living two directories deep (`.ai/install/`) — a prior refactor
  moved them from the kit root without updating the path math, so installs
  silently found none of the managed paths (`AGENTS.md`, `.ai`, `.claude`,
  ...) and copied nothing.
- `install.sh`/`install.ps1`: gitignored build artifacts and local config
  (`.ai/engine/__pycache__/*.pyc`, `.claude/settings.local.json`) no longer
  ship to installed projects; filtering is via `git check-ignore` on the
  working tree, so untracked-but-real files (e.g. an uncommitted `AGENTS.md`)
  still install correctly.
- `install.sh`: symlinked files inside a managed directory (e.g.
  `.agents/AGENTS.md`) were silently skipped because `find -type f` doesn't
  match symlinks; now matches `-type f -o -type l`.
- `check-kit.sh`: dropped the hard requirement for root-level `GEMINI.md`/
  `ANTIGRAVITY.md`, which a prior refactor intentionally removed as stubs —
  the check was failing on every fresh install (and on this repo itself).
- `.ai/contexts.yaml`: reset to an empty template; it previously shipped this
  repo's own demo `billing`/`ordering` contexts to every new install.
