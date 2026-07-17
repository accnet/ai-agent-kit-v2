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
```

`complete` means implementation complete. A task becomes `done` only after
`qa-pass`, `review-approve`, and `close`. QA and review actions require an
existing JSON evidence artifact. QA requires `{"kind":"qa","task":"T1","status":"pass"}`;
review requires `{"kind":"review","task":"T1","verdict":"approve"}`. All state mutations append an event
to `.ai-work/logs/events.jsonl`.

`onboard` previews detected host stack, source directories, and verification
commands. Use `onboard --apply` only after reviewing the output; it backs up
`.ai/kit.yaml` before updating it. A custom `--state /path/name.json` uses
`/path/name/` as its isolated artifact and audit workspace.
