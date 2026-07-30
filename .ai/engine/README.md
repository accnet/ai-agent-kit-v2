# AI-Kit v2 Control Plane

The control plane is a dependency-free Python CLI for multi-agent workflow
coordination. It is intentionally deterministic: Markdown describes work for
humans, while `.ai-work/state/workflow.json` is the canonical runtime state.

## Commands

```bash
python .ai/engine/ai_kit.py init --title "Add audit trail" --workflow feature
python .ai/engine/ai_kit.py plan --idea "Add audit trail" --owner backend --acceptance "Audit event is persisted"
python .ai/engine/ai_kit.py add-task T1 --title "Design state" --owner planner --phase plan --acceptance "schema approved"
python .ai/engine/ai_kit.py add-task T2 --title "Implement engine" --owner backend --phase build --needs T1 --acceptance "tests pass"
python .ai/engine/ai_kit.py validate
python .ai/engine/ai_kit.py ready
python .ai/engine/ai_kit.py route T1
python .ai/engine/ai_kit.py status
python .ai/engine/ai_kit.py graph
python .ai/engine/ai_kit.py timeline
python .ai/engine/ai_kit.py blocked
python .ai/engine/ai_kit.py onboard
python .ai/engine/ai_kit.py transition T1 start --actor planner
python .ai/engine/ai_kit.py transition T1 complete --actor planner --detail "Plan approved"
python .ai/engine/ai_kit.py transition T1 reject --actor qa --detail "Ceiling collision does not end game"
python .ai/engine/ai_kit.py update-task T1 --add-acceptance "Bird hitting the ceiling ends the game" --actor qa
python .ai/engine/ai_kit.py verify T1
python .ai/engine/ai_kit.py context add ordering --path "src/ordering/*" --owner backend
python .ai/engine/ai_kit.py runner add local --command 'true {prompt}' --description "Local test runner"
python .ai/engine/ai_kit.py runner list
python .ai/engine/ai_kit.py add-task T3 --title "Ship order API" --owner backend --phase build --acceptance "..." --context ordering --epic checkout-revamp
python .ai/engine/ai_kit.py add-task T4 --title "Read API contract" --owner backend --phase build --acceptance "..." --depends-on .ai/engine/state-schema.md --depends-on .ai/engine/README.md
python .ai/engine/ai_kit.py epics
python .ai/engine/ai_kit.py dispatch-ready --runner claude --limit 3 --context ordering
python .ai/engine/ai_kit.py context add ordering --path "src/ordering/**/*" --owner backend --force
python .ai/engine/ai_kit.py epic add checkout-revamp --spec .ai-work/plan/checkout-revamp-spec.md --owner planner
python .ai/engine/ai_kit.py epic add checkout-revamp --spec .ai-work/plan/checkout-revamp-spec.md --owner planner --force
python .ai/engine/ai_kit.py drift T3
python .ai/engine/ai_kit.py board --context ordering --format markdown --write
```

`complete` means implementation complete. A task becomes `done` only after
`qa-pass`, `review-approve`, and `close`. QA and review actions require an
existing JSON evidence artifact. QA requires `{"kind":"qa","task":"T1","status":"pass"}`;
review requires `{"kind":"review","task":"T1","verdict":"approve"}`. All state mutations append an event
to `.ai-work/logs/events.jsonl`.

`reject` sends an `implementation-complete` or `qa-passed` task back to
`todo` when QA/review finds work that must be redone (distinct from `block`,
which is for external impediments, not rejected work). Pair it with
`update-task` to tighten acceptance criteria before redispatching. `verify`
runs the `test_command`/`lint_command`/`typecheck_command`/`build_command`
configured in `.ai/kit.yaml` plus the security gate; if all four commands
are still the placeholder `true` (nothing configured), it prints a stderr
warning and sets `"warning"` in its JSON report, since in that case only the
security gate ran and functional correctness was never actually checked.

`onboard` previews detected host stack, source directories, and verification
commands. Use `onboard --apply` only after reviewing the output; it backs up
`.ai/kit.yaml` before updating it. A custom `--state /path/name.json` uses
`/path/name/` as its isolated artifact and audit workspace.

Runner profiles live in `.ai/runners.yaml`. Each profile has a required
`command` template and optional `model`, `provider`, and `description`
fields. A top-level `default_executor: <name>` scalar names the one profile
`dispatch-ready` is allowed to run automatically. `runner add` refuses to
overwrite an existing profile unless `--force` is supplied; `--default` sets
(overwrites) `default_executor` to the profile being added. `runner list`
returns `{"default_executor": ..., "runners": {...}}`.
`--runner` is optional on both `dispatch` and `dispatch-ready`, falling back
to `default_executor` when omitted. Explicit `dispatch <id> --runner X`
always runs any named profile. `dispatch-ready` only ever runs the
configured `default_executor` — passing `--runner X` where `X` differs from
it is an error, checked before claiming any task. Use explicit `dispatch`
to run a profile that isn't the default.

`context` (registered via `.ai/contexts.yaml`) scopes tasks to a service or
bounded context (`api`, `ui`, `database`, ...); `--context` filters
`status`/`ready`/`graph`, and gate G6 (`module_boundary: true` in
`.ai/rules.yaml`, off by default) rejects a task whose `files` fall outside
its context's registered path glob. `epic` groups tasks belonging to one
blueprint across services; `ai-kit epics` reports `percent_done` per epic.
Use these together on a large multi-service project: give each service its
own context so G6 keeps agents from touching each other's files, and tag
every task from the same blueprint with one `epic` to track it as a unit.

For running multiple agents in parallel, `dispatch-ready --runner X
[--limit N] [--context C] [--epic E]` claims up to N ready tasks and spawns
each one's runner as a background process, so they execute concurrently
instead of one `dispatch` call blocking the next. Claiming is race-safe:
`save()` rejects a write whose expected revision is stale, and
`_retry_transition` retries a losing claim a few times before giving up, so
two orchestrators racing over the same ready tasks never double-claim one.
Pass `--agent-id` (to `transition`, `dispatch`, or `dispatch-ready`) to give
each concurrent agent instance a distinct identity — it's recorded as
`claimed_by: "role#agent_id"` so the audit trail can tell apart multiple
agents sharing one role.

Every task also records `base_commit` (git HEAD at creation),
`context_revision` (its context's `.ai/contexts.yaml` revision at creation),
and `epic_revision` (its epic's Specification revision in `.ai/epics.yaml`
at creation) automatically. `context add ... --force` bumps a context's
revision when its path/owner changes; `epic add <name> --spec <path>
[--owner <role>] --force` does the same for an epic's Specification doc.
`ai-kit drift <task-id>` then reports whether a task's context or epic has
gone stale since it was planned, and lists files that changed (`git diff
--name-only`) since its `base_commit`. This is informational only — it
never blocks a transition — meant to be checked before dispatch/review on a
task that's been sitting a while, especially one whose Specification or a
contract it depends on may have moved since it was created.

Tasks may also declare repeatable `--depends-on <path>` contract/interface
files. At creation, each path is read directly and stored in
`contract_hashes` as `path -> sha256(file contents)`; no registry file is
needed. `ai-kit drift <task-id>` reports `contract_stale`, the paths whose
current content hash differs from the recorded hash or whose file is missing,
and `drift_unavailable`, declared paths that errored on read (for example a
path replaced by a directory) rather than being cleanly missing or changed.
An unchanged dependency is not reported stale. `validate()` supplies empty
`depends_on` and `contract_hashes` fields when migrating older task state.

`ai-kit board [--context C] [--epic E] [--owner O] [--write]
[--format json|markdown]` renders a read-only planner board grouped by every
workflow status. Filters are exact and combinable. JSON keeps all seven status
keys; Markdown omits empty sections and is emitted raw. Entries include
`id`, `title`, `owner_display`, `context`, `epic`, optional `blocked_reason`,
and read-time flags for blocked, stale context/epic/contracts, or unavailable
drift reads. The board and `drift` use the same drift computation. `--write`
also creates `.ai-work/board.md`; it never changes `workflow.json` or its
revision.

Run `bash .ai/scripts/test-kit.sh` to exercise the engine's own behavior:
`tests/test_ai_kit.py` (stdlib `unittest`, no third-party deps) drives the
CLI as a subprocess against isolated tempfile-based `--state` paths, covering
the task lifecycle, self-review guard, block/unblock/reject, context/epic/
contract drift, board filters and board/drift flag parity, and the `graph`
raw-output regression. It never touches this repo's real `.ai-work` state or
leaves residue in `.ai/contexts.yaml`/`.ai/epics.yaml`.
