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
python .ai/engine/ai_kit.py add-task T3 --title "Ship order API" --owner backend --phase build --acceptance "..." --context ordering --epic checkout-revamp
python .ai/engine/ai_kit.py epics
python .ai/engine/ai_kit.py dispatch-ready --runner claude --limit 3 --context ordering
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
