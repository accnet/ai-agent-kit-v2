# Plan - v2 workflow engine

Status: active

## Goal
Deliver an executable, dependency-aware multi-agent workflow engine while
preserving all v2 directory contracts. Reuse v1 skills and script logic only
through v2 adapters.

## Architecture
`python .ai/engine/ai_kit.py` is the control-plane CLI. Its canonical state is
`.ai-work/state/workflow.json`; JSONL events are append-only audit history.
Planner creates a validated roadmap/plan/tasks/phases state document.
Scheduler derives runnable tasks from the DAG. Router maps a task owner to the
v2 role contract, technology knowledge, and imported core skills. Executor,
QA, and Reviewer record legal lifecycle transitions through the same CLI.

## Compatibility Rules
- Preserve `.ai/agents/<role>/` and its six-document contract.
- Preserve `.ai/skills/<domain>/<technology>/`; imported v1 skills live under
  the new v2 domain `.ai/skills/core/<skill>/`.
- Preserve `.ai/workflows/`, `.ai/templates/`, and `.ai-work/`.
- Do not invoke v1 scripts directly; adapt their useful behavior to v2 state
  and paths.

## Risks
- A Markdown task list cannot safely represent a DAG runtime. The JSON state is
  canonical; Markdown is a human-readable plan artifact.
- This repository has no application stack. Runtime verification is Python
  unit testing plus a deterministic fixture workflow.
