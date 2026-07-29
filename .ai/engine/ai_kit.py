#!/usr/bin/env python3
"""Dependency-free control plane for AI-Kit v2 workflows."""
from __future__ import annotations

import argparse
import os
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / ".ai-work"
STATE = WORK / "state" / "workflow.json"
CURRENT = WORK / "state" / "current.json"
EVENT_LOG = WORK / "logs" / "events.jsonl"
ROLE_DOMAINS = {
    "backend": ["backend", "database", "ai"], "frontend": ["frontend"],
    "database": ["database"], "devops": ["devops"], "release": ["devops"], "qa": ["testing"],
}
CORE_BY_ROLE = {
    "planner": ["requirements-intake", "skill-router"],
    "researcher": ["requirements-intake", "skill-router"],
    "architect": ["refactoring", "api-contract"],
    "backend": ["api-contract", "observability"],
    "frontend": ["frontend-core", "test-and-validation"],
    "database": ["data-migration", "api-contract"],
    "devops": ["deployment-infra", "observability"],
    "qa": ["test-and-validation", "debugging"],
    "reviewer": ["code-review", "api-contract"],
    "security": ["security-review", "threat-modeling"],
    "integration": ["integration-contracts", "webhooks-and-retries"],
    "performance": ["performance-profiling", "observability"],
    "scheduler": ["workflow-orchestration"],
    "router": ["workflow-orchestration", "skill-router"],
    "document": ["documentation-maintenance", "architecture-decisions"],
    "release": ["release-management", "deployment-infra", "github-actions-ci"],
}
TRANSITIONS = {
    "start": ({"todo"}, "in-progress"),
    "complete": ({"in-progress"}, "implementation-complete"),
    "qa-pass": ({"implementation-complete"}, "qa-passed"),
    "review-approve": ({"qa-passed"}, "review-approved"),
    "close": ({"review-approved"}, "done"),
    "block": ({"todo", "in-progress", "implementation-complete", "qa-passed", "review-approved"}, "blocked"),
    "unblock": ({"blocked"}, "todo"),
}


class EngineError(Exception):
    pass


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def state_path(value: str | None) -> Path:
    return Path(value).resolve() if value else STATE


def workspace(path: Path) -> Path:
    """Derive a workspace from state/<workflow>.json or a standalone state file."""
    return path.parent.parent if path.parent.name == "state" else path.parent / path.stem


def display_path(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def role_names() -> set[str]:
    return {path.name for path in (ROOT / ".ai" / "agents").iterdir() if path.is_dir()}


def workflow_names() -> set[str]:
    return {path.name for path in (ROOT / ".ai" / "workflows").iterdir() if path.is_dir()}


def new_state(title: str, workflow: str) -> dict:
    return {"version": 1, "revision": 0, "title": title, "workflow": workflow, "created_at": now(), "tasks": [], "phases": [], "events": []}


def configured_stack() -> set[str]:
    manifest = ROOT / ".ai" / "kit.yaml"
    match = re.search(r"^\s*stack:\s*\[([^]]*)\]", manifest.read_text(encoding="utf-8"), re.MULTILINE)
    return {item.strip() for item in match.group(1).split(",") if item.strip()} if match else set()


def load(path: Path) -> dict:
    if not path.exists():
        raise EngineError(f"state not found: {path}; run init first")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EngineError(f"invalid JSON state: {exc}") from exc


def save(state: dict, path: Path, expected_revision: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_suffix(path.suffix + ".lock")
    deadline = time.monotonic() + 5
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise EngineError(f"state is locked: {path}")
            time.sleep(0.05)
    try:
        disk_revision = None
        if path.exists():
            disk_revision = json.loads(path.read_text(encoding="utf-8")).get("revision", 0)
        if expected_revision is not None and disk_revision != expected_revision:
            raise EngineError(f"state changed concurrently (expected revision {expected_revision}, found {disk_revision})")
        state["revision"] = (disk_revision or 0) + 1
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        lock.unlink(missing_ok=True)
    if path == STATE:
        active = [task["id"] for task in state["tasks"] if task["status"] == "in-progress"]
        summary = {"version": 1, "workflow_state": display_path(path), "title": state["title"], "workflow": state["workflow"], "active_tasks": active, "updated_at": now()}
        CURRENT.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


def task_map(state: dict) -> dict:
    return {task["id"]: task for task in state["tasks"]}


def validate(state: dict) -> None:
    required = {"version", "revision", "title", "workflow", "tasks", "phases", "events"}
    missing = required - set(state)
    if missing:
        raise EngineError(f"state missing keys: {', '.join(sorted(missing))}")
    tasks = task_map(state)
    if state["workflow"] not in workflow_names():
        raise EngineError(f"unknown workflow: {state['workflow']}")
    if len(tasks) != len(state["tasks"]):
        raise EngineError("task IDs must be unique")
    for task in state["tasks"]:
        for key in ("id", "title", "owner", "phase", "needs", "status", "acceptance", "files", "attempts", "evidence", "tags"):
            if key not in task:
                raise EngineError(f"task {task.get('id', '?')} missing {key}")
        if task["status"] not in {"todo", "in-progress", "implementation-complete", "qa-passed", "review-approved", "done", "blocked"}:
            raise EngineError(f"task {task['id']} has invalid status")
        if task["owner"] not in role_names():
            raise EngineError(f"task {task['id']} has unknown owner: {task['owner']}")
        if not task["phase"].strip() or not task["acceptance"]:
            raise EngineError(f"task {task['id']} needs phase and acceptance criteria")
        unknown = set(task["needs"]) - set(tasks)
        if unknown:
            raise EngineError(f"task {task['id']} has unknown dependency: {', '.join(sorted(unknown))}")
        if task["id"] in task["needs"]:
            raise EngineError(f"task {task['id']} cannot depend on itself")
    seen, active = set(), set()
    def visit(task_id: str) -> None:
        if task_id in active:
            raise EngineError(f"dependency cycle detected at {task_id}")
        if task_id not in seen:
            active.add(task_id)
            for dep in tasks[task_id]["needs"]:
                visit(dep)
            active.remove(task_id)
            seen.add(task_id)
    for task_id in tasks:
        visit(task_id)


def sync_phases(state: dict) -> None:
    names = sorted({task["phase"] for task in state["tasks"]})
    phases = []
    for name in names:
        tasks = [task for task in state["tasks"] if task["phase"] == name]
        status = "complete" if tasks and all(task["status"] == "done" for task in tasks) else "open" if any(runnable(task, task_map(state)) for task in tasks) else "planned"
        phases.append({"id": name, "status": status, "tasks": [task["id"] for task in tasks]})
    state["phases"] = phases


def runnable(task: dict, tasks: dict) -> bool:
    return task["status"] == "todo" and all(tasks[dep]["status"] == "done" for dep in task["needs"])


def validate_evidence(task: dict, action: str, paths: list[str]) -> None:
    expected_kind = "qa" if action == "qa-pass" else "review"
    for item in paths:
        evidence = Path(item)
        if not evidence.is_absolute():
            evidence = ROOT / evidence
        if not evidence.exists() or evidence.suffix != ".json":
            raise EngineError(f"{action} evidence must be an existing JSON file: {item}")
        try:
            payload = json.loads(evidence.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise EngineError(f"invalid evidence JSON: {item}") from exc
        if payload.get("kind") != expected_kind or payload.get("task") != task["id"]:
            raise EngineError(f"evidence does not match {expected_kind} task {task['id']}: {item}")
        if action == "qa-pass" and payload.get("status") != "pass":
            raise EngineError(f"QA evidence is not passing: {item}")
        if action == "review-approve" and payload.get("verdict") != "approve":
            raise EngineError(f"review evidence is not approved: {item}")


def event(state: dict, path: Path, action: str, task: dict | None, actor: str, old: str | None, new: str | None, detail: str) -> dict:
    item = {"ts": now(), "action": action, "task": task["id"] if task else None, "actor": actor, "from": old, "to": new, "detail": detail}
    state["events"].append(item)
    event_log = workspace(path) / "logs" / "events.jsonl"
    event_log.parent.mkdir(parents=True, exist_ok=True)
    with event_log.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item) + "\n")
    return item


def cmd_init(args: argparse.Namespace) -> dict:
    path = state_path(args.state)
    if path.exists() and not args.force:
        raise EngineError(f"state already exists: {path}; use --force to replace")
    if args.workflow not in workflow_names():
        raise EngineError(f"unknown workflow: {args.workflow}")
    if path.exists() and args.force:
        snapshots = workspace(path) / "snapshots"; snapshots.mkdir(parents=True, exist_ok=True)
        snapshots.joinpath(f"workflow-{now().replace(':', '-')}.json").write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    state = new_state(args.title, args.workflow)
    event(state, path, "init", None, args.actor, None, None, "workflow initialized")
    save(state, path)
    return state


def cmd_add_task(args: argparse.Namespace) -> dict:
    path, state = state_path(args.state), load(state_path(args.state))
    task_ids = task_map(state)
    if args.id in task_ids:
        raise EngineError(f"task already exists: {args.id}")
    if not args.acceptance:
        raise EngineError("add-task requires at least one --acceptance criterion")
    task = {"id": args.id, "title": args.title, "owner": args.owner, "phase": args.phase, "needs": args.needs or [], "status": "todo", "acceptance": args.acceptance, "files": args.files or [], "tags": args.tags or [], "attempts": 0, "evidence": [], "blocked_reason": None}
    state["tasks"].append(task)
    validate(state)
    sync_phases(state)
    event(state, path, "add-task", task, args.actor, None, "todo", "task added")
    save(state, path, state["revision"])
    return task


def cmd_ready(args: argparse.Namespace) -> list:
    state = load(state_path(args.state)); validate(state); tasks = task_map(state)
    return [{"id": task["id"], "title": task["title"], "owner": task["owner"], "phase": task["phase"]} for task in state["tasks"] if runnable(task, tasks)]


def cmd_transition(args: argparse.Namespace) -> dict:
    path, state = state_path(args.state), load(state_path(args.state)); validate(state)
    task = task_map(state).get(args.id)
    if not task:
        raise EngineError(f"unknown task: {args.id}")
    allowed, target = TRANSITIONS[args.action]
    if task["status"] not in allowed:
        raise EngineError(f"cannot {args.action} {args.id} from {task['status']}")
    if args.action == "start" and not runnable(task, task_map(state)):
        raise EngineError(f"task {args.id} is blocked by unfinished dependencies")
    if args.action == "block" and not args.detail:
        raise EngineError("block requires --detail")
    if args.action in {"qa-pass", "review-approve"}:
        if not args.evidence:
            raise EngineError(f"{args.action} requires at least one --evidence path")
        validate_evidence(task, args.action, args.evidence)
    old = task["status"]; task["status"] = target
    task["blocked_reason"] = args.detail if target == "blocked" else None
    if args.evidence:
        task["evidence"].extend(args.evidence)
    task["attempts"] += 1 if args.action == "start" else 0
    sync_phases(state); event(state, path, args.action, task, args.actor, old, target, args.detail or "")
    requested_revision = getattr(args, "expected_revision", None)
    expected = requested_revision if requested_revision is not None else state["revision"]
    save(state, path, expected)
    return task


def cmd_plan(args: argparse.Namespace) -> dict:
    path = state_path(args.state)
    if path.exists() and not args.force:
        raise EngineError(f"state already exists: {path}; use --force to replace")
    state = new_state(args.idea, args.workflow)
    plan_task = {"id": "T1", "title": "Confirm scope and plan: " + args.idea, "owner": "planner", "phase": "plan", "needs": [], "status": "todo", "acceptance": ["Scope, exclusions, risks, and acceptance criteria confirmed"], "files": [".ai-work/roadmap/roadmap.md", ".ai-work/plan/plan.md", ".ai-work/tasks/tasks.md"], "tags": ["planning"], "attempts": 0, "evidence": [], "blocked_reason": None}
    build_task = {"id": "T2", "title": args.idea, "owner": args.owner, "phase": args.phase, "needs": ["T1"], "status": "todo", "acceptance": args.acceptance, "files": args.files or [], "tags": args.tags or [], "attempts": 0, "evidence": [], "blocked_reason": None}
    state["tasks"] = [plan_task, build_task]; validate(state); sync_phases(state)
    root = workspace(path)
    root.joinpath("roadmap").mkdir(parents=True, exist_ok=True); root.joinpath("plan").mkdir(parents=True, exist_ok=True); root.joinpath("tasks").mkdir(parents=True, exist_ok=True)
    root.joinpath("roadmap/roadmap.md").write_text(f"# Roadmap\n\nGoal: {args.idea}\n\n1. Confirm scope, risks, and acceptance criteria.\n2. Implement in phase `{args.phase}` and verify evidence.\n", encoding="utf-8")
    root.joinpath("plan/plan.md").write_text(f"# Plan\n\nGoal: {args.idea}\n\nScope: {args.scope or 'pending Planner confirmation'}\nOut of scope: {args.out_of_scope or 'none recorded'}\nRisks: {', '.join(args.risks or ['none recorded'])}\nAssumptions: {args.assumptions or 'none recorded'}\nTags: {', '.join(args.tags or ['none'])}\n\nImplementation owner: {args.owner}\n", encoding="utf-8")
    root.joinpath("tasks/tasks.md").write_text(f"# Tasks\n\n- [ ] T1 Confirm scope and plan | owner: planner | phase: plan\n- [ ] T2 {args.idea} | owner: {args.owner} | needs: T1 | phase: build\n  - Accept: " + "\n  - Accept: ".join(args.acceptance) + "\n", encoding="utf-8")
    event(state, path, "plan", None, args.actor, None, None, "idea converted to draft plan")
    save(state, path)
    return {"state": display_path(path), "workspace": display_path(root), "tasks": ["T1", "T2"], "assumptions": args.assumptions or "none recorded"}


def cmd_route(args: argparse.Namespace) -> dict:
    state = load(state_path(args.state)); validate(state)
    task = task_map(state).get(args.id)
    if not task:
        raise EngineError(f"unknown task: {args.id}")
    role = task["owner"]
    domains = ROLE_DOMAINS.get(role, [])
    skill_root = ROOT / ".ai" / "skills"
    skills = []
    stack = configured_stack() | set(task.get("tags", []))
    for domain in domains:
        folder = skill_root / domain
        if folder.exists():
            for path in sorted(folder.glob("*/overview.md")):
                if not stack or path.parent.name in stack or domain in stack:
                    skills.append(path.relative_to(ROOT).as_posix())
    skills.extend((skill_root / "core" / name / "SKILL.md").relative_to(ROOT).as_posix() for name in CORE_BY_ROLE.get(role, ["skill-router"]) if (skill_root / "core" / name / "SKILL.md").exists())
    root = workspace(state_path(args.state))
    return {"task": task["id"], "owner": role, "tags": task["tags"], "role_contract": (Path(".ai") / "agents" / role).as_posix(), "skills": skills, "context": [display_path(root / "plan" / "plan.md"), display_path(root / "tasks" / "tasks.md"), ".ai/engine/state-schema.md"] + task["files"]}


def cmd_status(args: argparse.Namespace) -> dict:
    state = load(state_path(args.state)); validate(state)
    counts = {status: 0 for status in ("todo", "in-progress", "implementation-complete", "qa-passed", "review-approved", "done", "blocked")}
    for task in state["tasks"]: counts[task["status"]] += 1
    return {"title": state["title"], "revision": state["revision"], "counts": counts, "phases": sync_phases(state) or state["phases"]}


def cmd_timeline(args: argparse.Namespace) -> list:
    state = load(state_path(args.state)); validate(state)
    return state["events"]


def cmd_blocked(args: argparse.Namespace) -> list:
    state = load(state_path(args.state)); validate(state)
    return [{"id": task["id"], "title": task["title"], "reason": task["blocked_reason"]} for task in state["tasks"] if task["status"] == "blocked"]


def cmd_graph(args: argparse.Namespace) -> str:
    state = load(state_path(args.state)); validate(state)
    lines = ["digraph workflow {"]
    for task in state["tasks"]:
        lines.append(f'  "{task["id"]}" [label="{task["id"]}: {task["title"]}"];')
        lines.extend(f'  "{dep}" -> "{task["id"]}";' for dep in task["needs"])
    return "\n".join(lines + ["}"])


def cmd_onboard(args: argparse.Namespace) -> dict:
    stacks, sources, commands = [], [], {}
    if (ROOT / "package.json").exists():
        stacks.append("node"); sources.append("src"); commands["test_command"] = "npm test"
    if (ROOT / "composer.json").exists():
        stacks.extend(["php", "laravel"]); sources.append("app"); commands["test_command"] = "php artisan test"
    if (ROOT / "pyproject.toml").exists() or (ROOT / "requirements.txt").exists():
        stacks.append("python"); sources.append("src"); commands["test_command"] = "pytest -q"
    if not stacks: stacks, sources = ["any"], ["."]
    proposal = {"stack": sorted(set(stacks)), "source_dirs": sorted(set(sources)), "verification": commands}
    if args.apply:
        manifest = ROOT / ".ai" / "kit.yaml"
        backup = manifest.with_suffix(".yaml.bak")
        backup.write_text(manifest.read_text(encoding="utf-8"), encoding="utf-8")
        text = manifest.read_text(encoding="utf-8")
        text = re.sub(r"stack:\s*\[[^]]*\]", "stack: [" + ", ".join(proposal["stack"]) + "]", text)
        text = re.sub(r"source_dirs:\s*\[[^]]*\]", "source_dirs: [" + ", ".join(proposal["source_dirs"]) + "]", text)
        for key, value in commands.items(): text = re.sub(rf"{key}:.*", f"{key}: {value}", text)
        manifest.write_text(text, encoding="utf-8")
        proposal["applied"] = True
    return proposal


def cmd_approve(args: argparse.Namespace) -> dict:
    state = load(state_path(args.state)); validate(state)
    task = task_map(state).get(args.id)
    if not task:
        raise EngineError(f"unknown task: {args.id}")
    action = "qa-pass" if args.role == "qa" else "review-approve"
    status = args.status or ("pass" if args.role == "qa" else "approve")
    verdict_key = "status" if args.role == "qa" else "verdict"
    payload = {"kind": args.role, "task": task["id"], "ts": now(), verdict_key: status, "reason": args.reason}
    root = workspace(state_path(args.state))
    evidence_path = root / f"{args.role}_evidence_{task['id']}.json"
    evidence_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    args.action = action
    args.evidence = [evidence_path.as_posix()]
    args.detail = args.reason
    args.actor = args.role
    return cmd_transition(args)


def cmd_dispatch(args: argparse.Namespace) -> dict:
    state = load(state_path(args.state)); validate(state)
    task = task_map(state).get(args.id)
    if not task:
        raise EngineError(f"unknown task: {args.id}")
    runners_file = ROOT / ".ai" / "runners.json"
    runners = json.loads(runners_file.read_text(encoding="utf-8")) if runners_file.exists() else {}
    if args.runner not in runners:
        raise EngineError(f"unknown runner profile: {args.runner}. Available: {', '.join(runners.keys())}")
    template = runners[args.runner]
    prompt = f"Bạn là {task['owner']}. Thực thi task {task['id']} theo yêu cầu trong .ai-work/tasks/tasks.md. Không vi phạm AGENTS.md. Xong việc gọi lệnh: bash .ai/scripts/ai-kit transition {task['id']} complete --actor {task['owner']} --detail 'Hoàn thành bởi {args.runner}'"
    cmd = template.replace("{prompt}", prompt.replace("'", "'\\''"))
    print(f"Dispatching task {task['id']} to runner '{args.runner}'...", file=sys.stderr)
    res = os.system(cmd)
    if res != 0:
        raise EngineError(f"Runner {args.runner} exited with code {res}")
    return {"task": task["id"], "runner": args.runner, "status": "dispatched"}


def cmd_verify(args: argparse.Namespace) -> dict:
    state = load(state_path(args.state)); validate(state)
    task = task_map(state).get(args.id)
    if not task:
        raise EngineError(f"unknown task: {args.id}")
    
    print(f"Verifying task {task['id']}...", file=sys.stderr)
    
    manifest = ROOT / ".ai" / "kit.yaml"
    if manifest.exists():
        text = manifest.read_text(encoding="utf-8")
        import re
        match = re.search(r"test_command:\s*(.+)", text)
        if match:
            cmd = match.group(1).strip()
            if cmd != "true":
                print(f"Running tests: {cmd}", file=sys.stderr)
                res = os.system(cmd)
                if res != 0:
                    raise EngineError(f"Tests failed (exit code {res})")
                    
    gates = ROOT / ".ai" / "scripts" / "check-gates.sh"
    if gates.exists():
        print("Checking security gates (G4)...", file=sys.stderr)
        res = os.system(f"bash {gates} all")
        if res != 0:
            raise EngineError(f"Security gates failed (exit code {res})")
            
    print("Verification passed! Automatically approving task as QA...", file=sys.stderr)
    args.role = "qa"
    args.status = "pass"
    args.reason = "Automated verification passed successfully"
    return cmd_approve(args)


def cmd_show(args: argparse.Namespace) -> dict:
    state = load(state_path(args.state)); validate(state); sync_phases(state)
    return state


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="ai-kit", description=__doc__)
    root.add_argument("--state", help="override workflow state path")
    root.add_argument("--json", action="store_true", help="always print JSON")
    sub = root.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init"); init.add_argument("--title", required=True); init.add_argument("--workflow", required=True); init.add_argument("--actor", default="planner"); init.add_argument("--force", action="store_true"); init.set_defaults(fn=cmd_init)
    add = sub.add_parser("add-task"); add.add_argument("id"); add.add_argument("--title", required=True); add.add_argument("--owner", required=True); add.add_argument("--phase", required=True); add.add_argument("--needs", nargs="*"); add.add_argument("--acceptance", nargs="+", required=True); add.add_argument("--files", nargs="*"); add.add_argument("--tags", nargs="*"); add.add_argument("--actor", default="planner"); add.set_defaults(fn=cmd_add_task)
    ready = sub.add_parser("ready"); ready.set_defaults(fn=cmd_ready)
    plan = sub.add_parser("plan"); plan.add_argument("--idea", required=True); plan.add_argument("--workflow", default="feature"); plan.add_argument("--owner", required=True); plan.add_argument("--acceptance", nargs="+", required=True); plan.add_argument("--files", nargs="*"); plan.add_argument("--tags", nargs="*"); plan.add_argument("--phase", default="build"); plan.add_argument("--scope"); plan.add_argument("--out-of-scope"); plan.add_argument("--risks", nargs="*"); plan.add_argument("--assumptions"); plan.add_argument("--actor", default="planner"); plan.add_argument("--force", action="store_true"); plan.set_defaults(fn=cmd_plan)
    trans = sub.add_parser("transition"); trans.add_argument("id"); trans.add_argument("action", choices=TRANSITIONS); trans.add_argument("--actor", required=True); trans.add_argument("--detail"); trans.add_argument("--evidence", nargs="+"); trans.add_argument("--expected-revision", type=int); trans.set_defaults(fn=cmd_transition)
    approve = sub.add_parser("approve"); approve.add_argument("id"); approve.add_argument("--role", choices=["qa", "review"], required=True); approve.add_argument("--status"); approve.add_argument("--reason", required=True); approve.set_defaults(fn=cmd_approve)
    verify = sub.add_parser("verify"); verify.add_argument("id"); verify.set_defaults(fn=cmd_verify)
    dispatch = sub.add_parser("dispatch"); dispatch.add_argument("id"); dispatch.add_argument("--runner", required=True); dispatch.set_defaults(fn=cmd_dispatch)
    route = sub.add_parser("route"); route.add_argument("id"); route.set_defaults(fn=cmd_route)
    status = sub.add_parser("status"); status.set_defaults(fn=cmd_status)
    timeline = sub.add_parser("timeline"); timeline.set_defaults(fn=cmd_timeline)
    blocked = sub.add_parser("blocked"); blocked.set_defaults(fn=cmd_blocked)
    graph = sub.add_parser("graph"); graph.set_defaults(fn=cmd_graph)
    onboard = sub.add_parser("onboard"); onboard.add_argument("--apply", action="store_true"); onboard.set_defaults(fn=cmd_onboard)
    show = sub.add_parser("show"); show.set_defaults(fn=cmd_show)
    valid = sub.add_parser("validate"); valid.set_defaults(fn=lambda args: (validate(load(state_path(args.state))) or {"valid": True}))
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        output = args.fn(args)
        print(json.dumps(output, indent=2))
        return 0
    except EngineError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
