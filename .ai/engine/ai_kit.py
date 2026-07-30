#!/usr/bin/env python3
"""Dependency-free control plane for AI-Kit v2 workflows."""
from __future__ import annotations

import argparse
import hashlib
import fnmatch
import os
import json
import re
import shlex
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = Path(__file__).resolve()
WORK = ROOT / ".ai-work"
STATE = WORK / "state" / "workflow.json"
CURRENT = WORK / "state" / "current.json"
EVENT_LOG = WORK / "logs" / "events.jsonl"
STATUSES = ("todo", "in-progress", "implementation-complete", "qa-passed", "review-approved", "done", "blocked")
def _load_registry() -> dict:
    """Load role→domain and role→core-skill mappings from registry.yaml."""
    registry_path = ROOT / ".ai" / "registry.yaml"
    if not registry_path.exists():
        return {"owners": {}, "core_skills": {"names": []}}
    text = registry_path.read_text(encoding="utf-8")
    # Lightweight YAML parsing for owners and core_skills (no pyyaml dep)
    owners: dict[str, list[str]] = {}
    in_owners = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("owners:"):
            in_owners = True; continue
        if in_owners:
            if not line.startswith(" ") and not line.startswith("\t"):
                in_owners = False; continue
            match = re.match(r"\s+(\w+):\s*\[([^\]]*)\]", line)
            if match:
                role = match.group(1)
                domains = [d.strip() for d in match.group(2).split(",") if d.strip()]
                owners[role] = domains
    core_names: list[str] = []
    match = re.search(r"names:\s*\[([^\]]*)\]", text)
    if match:
        core_names = [n.strip() for n in match.group(1).split(",") if n.strip()]
    return {"owners": owners, "core_skills": {"names": core_names}}


def _load_yaml_registry(relative_path: str, top_key: str) -> dict:
    """Minimal indented-YAML reader shared by the context/epic registries.

    Format:
      <top_key>:
        <name>:
          <field>: <value>
          ...
    """
    path = ROOT / relative_path
    if not path.exists():
        return {}
    entries: dict[str, dict] = {}
    current = None
    header = f"{top_key}:"
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.strip().startswith("#") or line.startswith(header):
            continue
        name_match = re.match(r"^  (\S+):\s*$", line)
        if name_match:
            current = name_match.group(1)
            entries[current] = {}
            continue
        field_match = re.match(r"^    (\w+):\s*(.+)$", line)
        if field_match and current:
            value = field_match.group(2).strip()
            # Registry writers use JSON double-quoted scalars when a value may
            # contain YAML-significant characters (or intentional whitespace).
            # JSON is a strict, dependency-free subset for these scalar values.
            if value.startswith('"'):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    pass
            entries[current][field_match.group(1)] = value
    return entries


def _load_contexts() -> dict:
    """Load the bounded-context/module registry from .ai/contexts.yaml.

    Format:
      contexts:
        ordering:
          path: src/ordering/*
          owner: backend
    `path` is an fnmatch glob (matches the whole relative path, `*` spans
    `/`) checked against each task's `files` when G6 module_boundary is on.
    """
    return _load_yaml_registry(".ai/contexts.yaml", "contexts")


def _load_epics() -> dict:
    """Load the epic/specification registry from .ai/epics.yaml.

    Format:
      epics:
        checkout-revamp:
          spec: .ai-work/plan/checkout-revamp-spec.md
          owner: planner
          revision: 1
    Registering an epic here is optional — `task.epic` works as a free-form
    tag with no registry entry, same as `context`. Registering it enables
    `epic_revision` drift tracking (see `_epic_revision`, `cmd_drift`).
    """
    return _load_yaml_registry(".ai/epics.yaml", "epics")


def _load_runners() -> dict:
    """Load runner profiles from the structured YAML registry."""
    return _load_yaml_registry(".ai/runners.yaml", "runners")


def _runner_scalar(value: str) -> str:
    """Serialize a runner field without losing spaces, quotes, or ``#``."""
    return json.dumps(value, ensure_ascii=False)


def _default_executor() -> str | None:
    """Read the top-level `default_executor: <name>` scalar from .ai/runners.yaml, or None if unset."""
    path = ROOT / ".ai" / "runners.yaml"
    if not path.exists():
        return None
    prefix = "default_executor:"
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(prefix):
            value = line[len(prefix):].strip()
            if value.startswith('"'):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    pass
            return value or None
    return None


def _resolve_runner(explicit: str | None) -> tuple[str, dict]:
    """Resolve an explicit --runner, or fall back to the configured default_executor.

    Returns (name, entry). Raises EngineError if neither an explicit runner
    nor a configured default_executor is available, if the configured
    default_executor doesn't name a registered runner (misconfiguration), or
    if the resolved name isn't registered.
    """
    runners = _load_runners()
    default_executor = _default_executor()
    if default_executor and default_executor not in runners:
        raise EngineError(f"configured default_executor '{default_executor}' is not a registered runner in .ai/runners.yaml")
    name = explicit or default_executor
    if not name:
        raise EngineError(
            "no --runner given and no default_executor configured in .ai/runners.yaml; "
            "pass --runner explicitly or set one via 'ai-kit runner add <name> --default'"
        )
    if name not in runners:
        raise EngineError(f"unknown runner profile: {name}. Available: {', '.join(runners.keys())}")
    return name, runners[name]


def _write_runners(runners: dict[str, dict], default_executor: str | None) -> None:
    path = ROOT / ".ai" / "runners.yaml"
    lines = []
    if default_executor:
        lines.append(f"default_executor: {_runner_scalar(default_executor)}")
        lines.append("")
    lines.append("runners:")
    for name, fields in sorted(runners.items()):
        lines.append(f"  {name}:")
        lines.append(f"    command: {_runner_scalar(fields['command'])}")
        for key in ("model", "provider", "description"):
            if fields.get(key) is not None and fields.get(key) != "":
                lines.append(f"    {key}: {_runner_scalar(str(fields[key]))}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _git_head() -> str | None:
    """Return the repo's current HEAD commit hash, or None outside git / before the first commit."""
    import subprocess as _sp
    try:
        result = _sp.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5)
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def _context_revision(name: str | None) -> int | None:
    """Return the registered revision of a context, or None if unset/unregistered."""
    if not name:
        return None
    contexts = _load_contexts()
    if name not in contexts or "revision" not in contexts[name]:
        return None
    try:
        return int(contexts[name]["revision"])
    except ValueError:
        return None


def _epic_revision(name: str | None) -> int | None:
    """Return the registered specification revision of an epic, or None if unset/unregistered."""
    if not name:
        return None
    epics = _load_epics()
    if name not in epics or "revision" not in epics[name]:
        return None
    try:
        return int(epics[name]["revision"])
    except ValueError:
        return None


def _contract_path(path: str) -> Path:
    """Resolve a dependency path from the repository root or an absolute path."""
    candidate = Path(path)
    return candidate if candidate.is_absolute() else ROOT / candidate


def _flatten_repeated(groups: list[list[str]] | None) -> list[str]:
    """Flatten a nargs='+' + action='append' value: each flag occurrence contributes
    one group, so repeating the flag accumulates instead of overwriting the previous
    occurrence (the plain nargs='+' footgun this replaces)."""
    return [item for group in (groups or []) for item in group]


def _contract_hashes(paths: list[str]) -> dict[str, str]:
    """Hash declared contract files at task creation time."""
    hashes = {}
    for path in paths:
        file_path = _contract_path(path)
        if not file_path.is_file():
            raise EngineError(f"depends-on path does not exist or is not a file: {path}")
        try:
            hashes[path] = hashlib.sha256(file_path.read_bytes()).hexdigest()
        except OSError as exc:
            raise EngineError(f"cannot read depends-on path: {path}") from exc
    return hashes


def _load_rules() -> dict:
    """Load gate rules from .ai/rules.yaml. Returns sensible defaults when the file is missing or malformed.

    This function enables configurable gates (G1, G3) by reading boolean flags
    from a YAML-like file at .ai/rules.yaml. It uses regex parsing (no PyYAML
    dependency) and returns safe defaults (all True) on any error. Each line is
    expected as ``key: value``. Supported values: true/yes/on, false/no/off.
    """
    defaults = {
        "planning_first": True,       # G1 - enforce plan-phase dependencies
        "minimal_context": True,      # load only minimal task context
        "review_required": True,      # G3 - require review evidence before done
        "db_changes_require_plan": True,  # db/migration work always needs a plan
        "no_secrets_in_commits": True,    # G4 - prevent secret commits
        "destructive_operations_require_approval": True,  # G5 - require explicit approval
        "module_boundary": False,     # G6 - task files must stay inside its declared context path (opt-in)
    }
    rules_path = ROOT / ".ai" / "rules.yaml"
    if not rules_path.exists():
        return dict(defaults)
    try:
        text = rules_path.read_text(encoding="utf-8")
    except Exception:
        return dict(defaults)
    result = dict(defaults)
    for line in text.splitlines():
        line = line.strip().lstrip("\ufeff")  # Strip BOM + whitespace
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^(\w[\w_]*):\s*(.+)$", line)
        if match:
            key = match.group(1)
            value = match.group(2).strip()
            if value.lower() in ("true", "yes", "on"):
                result[key] = True
            elif value.lower() in ("false", "no", "off"):
                result[key] = False
            else:
                result[key] = value
    return result


# Legacy fallbacks used only if registry.yaml is absent
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
    "reject": ({"implementation-complete", "qa-passed"}, "todo"),
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
    return {"version": 2, "revision": 0, "title": title, "workflow": workflow, "created_at": now(), "tasks": [], "phases": [], "events": []}


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
    # Migrate older tasks that lack claimed_by, context, epic, or provenance fields
    for task in state.get("tasks", []):
        if "claimed_by" not in task:
            task["claimed_by"] = None
        task.setdefault("context", None)
        task.setdefault("epic", None)
        task.setdefault("base_commit", None)
        task.setdefault("context_revision", None)
        task.setdefault("epic_revision", None)
        task.setdefault("depends_on", [])
        task.setdefault("contract_hashes", {})
    missing = set()  # reset after migration
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

    # T2: Integrate rules.yaml gates into validation
    # _load_rules() reads .ai/rules.yaml at runtime, so operators can toggle
    # gates without modifying the engine. All rules default to True (safe) when
    # the config file is missing, malformed, or unreadable.
    rules = _load_rules()

    # G1 - Plan: configurable via rules.yaml `planning_first` key
    # When planning_first is true, tasks past "todo" in non-plan phases
    # must have all their plan-phase dependencies completed first.
    # Set `planning_first: false` in .ai/rules.yaml to skip this check.
    if rules.get("planning_first", True):
        for task in state["tasks"]:
            past_todo = task["status"] not in {"todo", "blocked"}
            if past_todo and task["phase"] != "plan":
                plan_deps = [dep for dep in task["needs"] if tasks[dep].get("phase") == "plan"]
                if plan_deps and not all(tasks[dep]["status"] == "done" for dep in plan_deps):
                    offender = next(dep for dep in plan_deps if tasks[dep]["status"] != "done")
                    raise EngineError(
                        f"G1 planning_first: task {task['id']} ({task['status']}) "
                        f"needs plan dependency {offender} ({tasks[offender]['status']}) completed"
                    )

    # G3 - Review: configurable via rules.yaml `review_required` key
    # When review_required is true, tasks at "done" must carry review evidence
    # proving they passed through review-approve. The evidence file is validated
    # by _parse_evidence_kind() which reads the `kind` field from the JSON payload.
    # Set `review_required: false` in .ai/rules.yaml to skip this check.
    if rules.get("review_required", True):
        for task in state["tasks"]:
            if task["status"] == "done":
                has_review = any(
                    _parse_evidence_kind(p) == "review" for p in (task.get("evidence") or [])
                )
                if not has_review:
                    raise EngineError(
                        f"G3 review_required: task {task['id']} is done but has no review evidence"
                    )

    # G6 - Module boundary: configurable via rules.yaml `module_boundary` key (default off).
    # When on, a task that declares a `context` may only touch files inside that
    # context's registered path glob (.ai/contexts.yaml), so two agents working in
    # different contexts (e.g. api vs database) in parallel can't silently collide.
    if rules.get("module_boundary", False):
        contexts = _load_contexts()
        for task in state["tasks"]:
            ctx_name = task.get("context")
            if not ctx_name:
                continue
            if ctx_name not in contexts:
                raise EngineError(f"G6 module_boundary: task {task['id']} has unknown context: {ctx_name}")
            pattern = contexts[ctx_name].get("path")
            if pattern:
                offenders = [f for f in task.get("files", []) if not fnmatch.fnmatch(f, pattern)]
                if offenders:
                    raise EngineError(
                        f"G6 module_boundary: task {task['id']} (context {ctx_name}) touches files "
                        f"outside {pattern}: {', '.join(offenders)}"
                    )


def _parse_evidence_kind(path: str) -> str | None:
    """Extract the kind field from an evidence JSON file path. Returns None on failure."""
    try:
        evidence_path = Path(path)
        if not evidence_path.is_absolute():
            evidence_path = ROOT / evidence_path
        if evidence_path.exists():
            payload = json.loads(evidence_path.read_text(encoding="utf-8"))
            return payload.get("kind")
    except Exception:
        return None
    return None


def sync_phases(state: dict) -> None:
    names = sorted({task["phase"] for task in state["tasks"]})
    phases = []
    for name in names:
        tasks = [task for task in state["tasks"] if task["phase"] == name]
        status = "complete" if tasks and all(task["status"] == "done" for task in tasks) else "open" if any(runnable(task, task_map(state)) for task in tasks) else "planned"
        phases.append({"id": name, "status": status, "tasks": [task["id"] for task in tasks]})
    state["phases"] = phases


def sync_tasks_md(state: dict, state_path: Path) -> None:
    """Sync .ai-work/tasks/tasks.md with current workflow state."""
    tasks_dir = workspace(state_path) / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    tasks_md = tasks_dir / "tasks.md"
    lines = ["# Tasks", ""]
    for task in state["tasks"]:
        status_mark = "x" if task["status"] == "done" else " "
        needs = f" | needs: {','.join(task['needs'])}" if task["needs"] else ""
        if task.get("context"):
            rev = f"@r{task['context_revision']}" if task.get("context_revision") is not None else ""
            context = f" | context: {task['context']}{rev}"
        else:
            context = ""
        if task.get("epic"):
            epic_rev = f"@r{task['epic_revision']}" if task.get("epic_revision") is not None else ""
            epic = f" | epic: {task['epic']}{epic_rev}"
        else:
            epic = ""
        base = f" | base: {task['base_commit'][:7]}" if task.get("base_commit") else ""
        depends_on = f" | depends_on: {','.join(task['depends_on'])}" if task.get("depends_on") else ""
        lines.append(f"- [{status_mark}] {task['id']} {task['title']} | owner: {task['owner']}{needs} | phase: {task['phase']}{context}{epic}{base}{depends_on}")
        for criterion in task["acceptance"]:
            lines.append(f"  - Accept: {criterion}")
        lines.append(f"  - Status: {task['status']}")
        if task.get("blocked_reason"):
            lines.append(f"  - Note: {task['blocked_reason']}")
    tasks_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


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
    acceptance = _flatten_repeated(args.acceptance)
    if not acceptance:
        raise EngineError("add-task requires at least one --acceptance criterion")
    context = getattr(args, "context", None)
    context_revision = _context_revision(context)
    epic = getattr(args, "epic", None)
    depends_on = args.depends_on or []
    task = {"id": args.id, "title": args.title, "owner": args.owner, "phase": args.phase, "needs": args.needs or [], "status": "todo", "acceptance": acceptance, "files": args.files or [], "tags": args.tags or [], "attempts": 0, "evidence": [], "blocked_reason": None, "claimed_by": None, "context": context, "epic": epic, "base_commit": _git_head(), "context_revision": context_revision, "epic_revision": _epic_revision(epic), "depends_on": depends_on, "contract_hashes": _contract_hashes(depends_on)}
    state["tasks"].append(task)
    validate(state)
    sync_phases(state)
    sync_tasks_md(state, path)
    event(state, path, "add-task", task, args.actor, None, "todo", "task added")
    save(state, path, state["revision"])
    return task


def cmd_update_task(args: argparse.Namespace) -> dict:
    path, state = state_path(args.state), load(state_path(args.state)); validate(state)
    task = task_map(state).get(args.id)
    if not task:
        raise EngineError(f"unknown task: {args.id}")
    add_acceptance = _flatten_repeated(args.add_acceptance)
    if not add_acceptance and not args.add_files and not args.add_tags:
        raise EngineError("update-task requires at least one of --add-acceptance, --add-files, --add-tags")
    detail_parts = []
    if add_acceptance:
        task["acceptance"].extend(add_acceptance)
        detail_parts.append("acceptance: " + "; ".join(add_acceptance))
    if args.add_files:
        task["files"].extend(f for f in args.add_files if f not in task["files"])
        detail_parts.append("files: " + ", ".join(args.add_files))
    if args.add_tags:
        task["tags"].extend(t for t in args.add_tags if t not in task["tags"])
        detail_parts.append("tags: " + ", ".join(args.add_tags))
    sync_phases(state)
    sync_tasks_md(state, path)
    event(state, path, "update-task", task, args.actor, task["status"], task["status"], " | ".join(detail_parts))
    save(state, path, state["revision"])
    return task


def cmd_ready(args: argparse.Namespace) -> list:
    state = load(state_path(args.state)); validate(state); tasks = task_map(state)
    context = getattr(args, "context", None)
    epic = getattr(args, "epic", None)
    return [
        {"id": task["id"], "title": task["title"], "owner": task["owner"], "phase": task["phase"], "context": task.get("context"), "epic": task.get("epic")}
        for task in state["tasks"]
        if runnable(task, tasks) and (not context or task.get("context") == context) and (not epic or task.get("epic") == epic)
    ]


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
    if args.action in {"block", "reject"} and not args.detail:
        raise EngineError(f"{args.action} requires --detail")
    if args.action in {"qa-pass", "review-approve", "reject"}:
        # P0-4: Executor must not QA/review/reject their own work. claimed_by may
        # carry a per-agent-instance suffix ("role#agent_id"); compare on the role
        # alone so this still blocks self-review when multiple agents share a role.
        claimed_role = task["claimed_by"].split("#", 1)[0] if task.get("claimed_by") else None
        if claimed_role and args.actor == claimed_role:
            raise EngineError(f"{args.action} actor '{args.actor}' must differ from executor '{task['claimed_by']}'")
    if args.action in {"qa-pass", "review-approve"}:
        if not args.evidence:
            raise EngineError(f"{args.action} requires at least one --evidence path")
        validate_evidence(task, args.action, args.evidence)
    old = task["status"]; task["status"] = target
    if args.action in {"block", "reject"}:
        task["blocked_reason"] = args.detail
    elif args.action in {"start", "unblock"}:
        task["blocked_reason"] = None
    if args.evidence:
        task["evidence"].extend(args.evidence)
    if args.action == "start":
        task["attempts"] += 1
        agent_id = getattr(args, "agent_id", None)
        task["claimed_by"] = f"{args.actor}#{agent_id}" if agent_id else args.actor
    sync_phases(state)
    sync_tasks_md(state, path)
    event(state, path, args.action, task, args.actor, old, target, args.detail or "")
    requested_revision = getattr(args, "expected_revision", None)
    expected = requested_revision if requested_revision is not None else state["revision"]
    save(state, path, expected)
    return task


def _retry_transition(args: argparse.Namespace, retries: int = 4, backoff: float = 0.15) -> dict:
    """Run cmd_transition, retrying on lost optimistic-concurrency races.

    save() re-reads the on-disk revision at write time, so two processes
    racing to claim the same task never corrupt state — the loser just gets
    a "state changed concurrently" EngineError. This retries that loser a
    few times (cmd_transition reloads state fresh each call, so every retry
    re-checks preconditions like status/runnable against current disk state,
    not stale in-memory data) so callers doing multi-task fan-out don't have
    to hand-roll their own retry loop.
    """
    last_err: EngineError | None = None
    for attempt in range(retries):
        try:
            return cmd_transition(args)
        except EngineError as exc:
            if "state changed concurrently" not in str(exc):
                raise
            last_err = exc
            time.sleep(backoff * (attempt + 1))
    raise last_err


def cmd_plan(args: argparse.Namespace) -> dict:
    path = state_path(args.state)
    if path.exists() and not args.force:
        raise EngineError(f"state already exists: {path}; use --force to replace")
    state = new_state(args.idea, args.workflow)
    base_commit = _git_head()
    context = getattr(args, "context", None)
    epic = getattr(args, "epic", None)
    depends_on = args.depends_on or []
    contract_hashes = _contract_hashes(depends_on)
    acceptance = _flatten_repeated(args.acceptance)
    plan_task = {"id": "T1", "title": "Confirm scope and plan: " + args.idea, "owner": "planner", "phase": "plan", "needs": [], "status": "todo", "acceptance": ["Scope, exclusions, risks, and acceptance criteria confirmed"], "files": [".ai-work/roadmap/roadmap.md", ".ai-work/plan/plan.md", ".ai-work/tasks/tasks.md"], "tags": ["planning"], "attempts": 0, "evidence": [], "blocked_reason": None, "claimed_by": None, "base_commit": base_commit, "context_revision": None, "epic_revision": None, "depends_on": [], "contract_hashes": {}}
    build_task = {"id": "T2", "title": args.idea, "owner": args.owner, "phase": args.phase, "needs": ["T1"], "status": "todo", "acceptance": acceptance, "files": args.files or [], "tags": args.tags or [], "attempts": 0, "evidence": [], "blocked_reason": None, "claimed_by": None, "context": context, "epic": epic, "base_commit": base_commit, "context_revision": _context_revision(context), "epic_revision": _epic_revision(epic), "depends_on": depends_on, "contract_hashes": contract_hashes}
    state["tasks"] = [plan_task, build_task]; validate(state); sync_phases(state)
    root = workspace(path)
    root.joinpath("roadmap").mkdir(parents=True, exist_ok=True); root.joinpath("plan").mkdir(parents=True, exist_ok=True); root.joinpath("tasks").mkdir(parents=True, exist_ok=True)
    root.joinpath("roadmap/roadmap.md").write_text(f"# Roadmap\n\nGoal: {args.idea}\n\n1. Confirm scope, risks, and acceptance criteria.\n2. Implement in phase `{args.phase}` and verify evidence.\n", encoding="utf-8")
    root.joinpath("plan/plan.md").write_text(f"# Plan\n\nGoal: {args.idea}\n\nScope: {args.scope or 'pending Planner confirmation'}\nOut of scope: {args.out_of_scope or 'none recorded'}\nRisks: {', '.join(args.risks or ['none recorded'])}\nAssumptions: {args.assumptions or 'none recorded'}\nTags: {', '.join(args.tags or ['none'])}\n\nImplementation owner: {args.owner}\n", encoding="utf-8")
    sync_tasks_md(state, path)
    event(state, path, "plan", None, args.actor, None, None, "idea converted to draft plan")
    save(state, path)
    return {"state": display_path(path), "workspace": display_path(root), "tasks": ["T1", "T2"], "assumptions": args.assumptions or "none recorded"}


def cmd_route(args: argparse.Namespace) -> dict:
    state = load(state_path(args.state)); validate(state)
    task = task_map(state).get(args.id)
    if not task:
        raise EngineError(f"unknown task: {args.id}")
    role = task["owner"]
    registry = _load_registry()
    domains = registry["owners"].get(role, ROLE_DOMAINS.get(role, []))
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


def cmd_context_add(args: argparse.Namespace) -> dict:
    path = ROOT / ".ai" / "contexts.yaml"
    contexts = _load_contexts()
    if args.name in contexts and not args.force:
        raise EngineError(f"context already registered: {args.name}; use --force to update it (bumps revision)")
    # revision increments on every update so tasks recorded against a stale
    # context (a moved/renamed path glob, a changed owner) can be detected.
    revision = int(contexts[args.name].get("revision", 1)) + 1 if args.name in contexts else 1
    contexts[args.name] = {"path": args.path, "owner": args.owner, "revision": str(revision)}
    lines = ["contexts:"]
    for name, fields in sorted(contexts.items()):
        lines.append(f"  {name}:")
        lines.append(f"    path: {fields['path']}")
        lines.append(f"    owner: {fields['owner']}")
        lines.append(f"    revision: {fields.get('revision', 1)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"name": args.name, "path": args.path, "owner": args.owner, "revision": revision}


def cmd_context_list(args: argparse.Namespace) -> dict:
    return _load_contexts()


def cmd_runner_add(args: argparse.Namespace) -> dict:
    runners = _load_runners()
    if args.name in runners and not args.force:
        raise EngineError(f"runner already registered: {args.name}; use --force to update it")
    runners[args.name] = {
        "command": args.command,
        "model": args.model or "",
        "provider": args.provider or "",
        "description": args.description or "",
    }
    default_executor = args.name if args.default else _default_executor()
    _write_runners(runners, default_executor)
    return {"name": args.name, "default_executor": default_executor, **runners[args.name]}


def cmd_runner_list(args: argparse.Namespace) -> dict:
    return {"default_executor": _default_executor(), "runners": _load_runners()}


def cmd_epic_add(args: argparse.Namespace) -> dict:
    """Register (or, with --force, re-register) an epic's Specification doc.

    Mirrors cmd_context_add: revision starts at 1 and bumps on every --force
    update, so tasks planned against an older spec revision become
    detectable as stale via `ai-kit drift`. Registration is optional — `epic`
    still works as a free-form tag with no entry here.
    """
    path = ROOT / ".ai" / "epics.yaml"
    epics = _load_epics()
    if args.name in epics and not args.force:
        raise EngineError(f"epic already registered: {args.name}; use --force to update it (bumps revision)")
    revision = int(epics[args.name].get("revision", 1)) + 1 if args.name in epics else 1
    epics[args.name] = {"spec": args.spec, "owner": args.owner or "", "revision": str(revision)}
    lines = ["epics:"]
    for name, fields in sorted(epics.items()):
        lines.append(f"  {name}:")
        lines.append(f"    spec: {fields['spec']}")
        if fields.get("owner"):
            lines.append(f"    owner: {fields['owner']}")
        lines.append(f"    revision: {fields.get('revision', 1)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"name": args.name, "spec": args.spec, "owner": args.owner, "revision": revision}


def cmd_epic_list(args: argparse.Namespace) -> dict:
    return _load_epics()


def _drift_flags(task: dict) -> dict:
    """Compute read-time drift signals without mutating workflow state.

    Missing contract files remain ``contract-stale`` for compatibility. A
    path that exists but cannot be read is reported as unavailable instead.
    The same result is consumed by both ``drift`` and ``board``.
    """
    contract_stale = []
    drift_unavailable = []
    for path in task.get("depends_on", []):
        file_path = _contract_path(path)
        recorded = task.get("contract_hashes", {}).get(path)
        if not file_path.exists():
            current = None
        else:
            try:
                current = hashlib.sha256(file_path.read_bytes()).hexdigest()
            except OSError:
                drift_unavailable.append(path)
                continue
        if recorded != current:
            contract_stale.append(path)

    context_stale = False
    context = task.get("context")
    if context:
        planned = task.get("context_revision")
        current = _context_revision(context)
        context_stale = planned is not None and current is not None and current != planned

    epic_stale = False
    epic = task.get("epic")
    if epic:
        planned = task.get("epic_revision")
        current = _epic_revision(epic)
        epic_stale = planned is not None and current is not None and current != planned

    return {
        "context_stale": context_stale,
        "epic_stale": epic_stale,
        "contract_stale": contract_stale,
        "drift_unavailable": drift_unavailable,
    }


def cmd_drift(args: argparse.Namespace) -> dict:
    """Report whether a task's plan-time base_commit/context_revision are stale.

    Informational only, never blocks a transition — blueprints and contracts
    change legitimately during development. Use this before dispatch/review
    to decide whether a task needs a re-plan.
    """
    import subprocess as _sp
    state = load(state_path(args.state)); validate(state)
    task = task_map(state).get(args.id)
    if not task:
        raise EngineError(f"unknown task: {args.id}")
    report: dict = {"task": task["id"]}
    flags = _drift_flags(task)
    contract_stale = flags["contract_stale"]
    report["contract_stale"] = contract_stale
    report["drift_unavailable"] = flags["drift_unavailable"]

    base_commit = task.get("base_commit")
    report["base_commit"] = base_commit
    if base_commit:
        head = _git_head()
        report["current_head"] = head
        report["commits_since_base"] = bool(head and head != base_commit)
        if head and head != base_commit:
            result = _sp.run(["git", "-C", str(ROOT), "diff", "--name-only", base_commit, head], capture_output=True, text=True)
            report["files_changed_since_base"] = [f for f in result.stdout.splitlines() if f]

    ctx_name = task.get("context")
    if ctx_name:
        current_revision = _context_revision(ctx_name)
        planned_revision = task.get("context_revision")
        report["context"] = ctx_name
        report["context_revision_at_plan"] = planned_revision
        report["context_revision_current"] = current_revision
        report["context_stale"] = flags["context_stale"]

    epic_name = task.get("epic")
    if epic_name:
        current_epic_revision = _epic_revision(epic_name)
        planned_epic_revision = task.get("epic_revision")
        report["epic"] = epic_name
        report["epic_revision_at_plan"] = planned_epic_revision
        report["epic_revision_current"] = current_epic_revision
        report["epic_stale"] = flags["epic_stale"]
    return report


def cmd_epics(args: argparse.Namespace) -> list:
    state = load(state_path(args.state)); validate(state)
    groups: dict[str, dict] = {}
    for task in state["tasks"]:
        epic = task.get("epic")
        if not epic:
            continue
        group = groups.setdefault(epic, {"total": 0, "done": 0, "counts": {status: 0 for status in STATUSES}})
        group["total"] += 1
        group["counts"][task["status"]] += 1
        if task["status"] == "done":
            group["done"] += 1
    return [
        {"epic": name, "total": g["total"], "done": g["done"], "percent_done": round(100 * g["done"] / g["total"], 1), "counts": g["counts"]}
        for name, g in sorted(groups.items())
    ]


def cmd_status(args: argparse.Namespace) -> dict:
    state = load(state_path(args.state)); validate(state)
    context = getattr(args, "context", None)
    epic = getattr(args, "epic", None)
    scoped = [
        task for task in state["tasks"]
        if (not context or task.get("context") == context) and (not epic or task.get("epic") == epic)
    ]
    counts = {status: 0 for status in STATUSES}
    for task in scoped: counts[task["status"]] += 1
    result = {"title": state["title"], "revision": state["revision"], "counts": counts, "phases": sync_phases(state) or state["phases"]}
    if context: result["context"] = context
    if epic: result["epic"] = epic
    return result


def _board_entry(task: dict) -> dict:
    drift = _drift_flags(task)
    flags = []
    if task["status"] == "blocked":
        flags.append("blocked")
    if drift["context_stale"]:
        flags.append("context-stale")
    if drift["epic_stale"]:
        flags.append("epic-stale")
    if drift["contract_stale"]:
        flags.append("contract-stale")
    if drift["drift_unavailable"]:
        flags.append("drift-unavailable")
    entry = {
        "id": task["id"],
        "title": task["title"],
        "owner_display": task.get("claimed_by") or task["owner"],
        "context": task.get("context"),
        "epic": task.get("epic"),
        "flags": flags,
    }
    if task["status"] == "blocked":
        entry["blocked_reason"] = task.get("blocked_reason")
    return entry


def _render_board_markdown(board: dict) -> str:
    lines = ["# AI Planner Board", ""]
    for status in STATUSES:
        entries = board[status]
        if not entries:
            continue
        lines.extend([f"## {status}", ""])
        for entry in entries:
            details = [f"owner: {entry['owner_display']}"]
            if entry["context"]:
                details.append(f"context: {entry['context']}")
            if entry["epic"]:
                details.append(f"epic: {entry['epic']}")
            if entry["flags"]:
                details.append(f"flags: {', '.join(entry['flags'])}")
            if "blocked_reason" in entry:
                details.append(f"blocked_reason: {entry['blocked_reason'] or ''}")
            lines.append(f"- **{entry['id']}** {entry['title']} ({'; '.join(details)})")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def cmd_board(args: argparse.Namespace) -> dict | str:
    state_path_value = state_path(args.state)
    state = load(state_path_value); validate(state)
    context = getattr(args, "context", None)
    epic = getattr(args, "epic", None)
    owner = getattr(args, "owner", None)
    scoped = [
        task for task in state["tasks"]
        if (not context or task.get("context") == context)
        and (not epic or task.get("epic") == epic)
        and (not owner or task.get("owner") == owner)
    ]
    board = {status: [] for status in STATUSES}
    for task in scoped:
        board[task["status"]].append(_board_entry(task))
    markdown = _render_board_markdown(board)
    if args.write:
        output_path = workspace(state_path_value) / "board.md"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")
    if args.format == "markdown":
        return markdown
    return board


def cmd_timeline(args: argparse.Namespace) -> list:
    state = load(state_path(args.state)); validate(state)
    return state["events"]


def cmd_blocked(args: argparse.Namespace) -> list:
    state = load(state_path(args.state)); validate(state)
    return [{"id": task["id"], "title": task["title"], "reason": task["blocked_reason"]} for task in state["tasks"] if task["status"] == "blocked"]


def cmd_graph(args: argparse.Namespace) -> str:
    state = load(state_path(args.state)); validate(state)
    context = getattr(args, "context", None)
    tasks = [t for t in state["tasks"] if not context or t.get("context") == context]
    included = {t["id"] for t in tasks}
    lines = ["digraph workflow {"]
    for task in tasks:
        lines.append(f'  "{task["id"]}" [label="{task["id"]}: {task["title"]}"];')
        lines.extend(f'  "{dep}" -> "{task["id"]}";' for dep in task["needs"] if dep in included)
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
    import subprocess as _sp
    state = load(state_path(args.state)); validate(state)
    task = task_map(state).get(args.id)
    if not task:
        raise EngineError(f"unknown task: {args.id}")
    runner_name, runner = _resolve_runner(args.runner)
    template = runner["command"]
    # The State Manager, not the runner, owns lifecycle transitions: claim the
    # task (todo -> in-progress) here so the runner only ever needs to report
    # completion, matching the single `complete` transition it is prompted for.
    if task["status"] == "todo":
        start_args = argparse.Namespace(state=args.state, id=task["id"], action="start", actor=task["owner"], detail=f"auto-started for dispatch to runner '{runner_name}'", evidence=None, expected_revision=None, agent_id=getattr(args, "agent_id", None))
        task = _retry_transition(start_args)
    elif task["status"] != "in-progress":
        raise EngineError(f"cannot dispatch {task['id']} from status {task['status']} (must be todo or in-progress)")
    prompt = f"Bạn là {task['owner']}. Thực thi task {task['id']} theo yêu cầu trong .ai-work/tasks/tasks.md. Không vi phạm AGENTS.md. Xong việc gọi lệnh: bash .ai/scripts/ai-kit transition {task['id']} complete --actor {task['owner']} --detail 'Hoàn thành bởi {runner_name}'"
    # Runner templates hold {prompt} unquoted; shlex.quote is the single
    # place quoting happens, so a template can never double-quote it.
    cmd = template.replace("{prompt}", shlex.quote(prompt))
    print(f"Dispatching task {task['id']} to runner '{runner_name}'...", file=sys.stderr)
    result = _sp.run(cmd, shell=True, cwd=str(ROOT))
    # Audit log
    audit = {
        "ts": now(), "task": task["id"], "runner": runner_name,
        "model": runner.get("model") or None,
        "provider": runner.get("provider") or None,
        "command": cmd, "exit_code": result.returncode,
    }
    audit_path = workspace(state_path(args.state)) / f"dispatch_log_{task['id']}.json"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    if result.returncode != 0:
        raise EngineError(f"Runner {runner_name} exited with code {result.returncode}")
    return {"task": task["id"], "runner": runner_name, "status": "dispatched"}


def cmd_dispatch_ready(args: argparse.Namespace) -> dict:
    """Claim up to --limit ready tasks and dispatch each to a background runner.

    Claiming (the todo -> in-progress transition) happens sequentially here,
    through _retry_transition, so two dispatch-ready invocations racing over
    the same ready tasks never double-claim one. Once a task is claimed its
    runner process is spawned with Popen (not waited on), so N claimed tasks
    actually execute concurrently instead of one after another.
    """
    import subprocess as _sp
    state = load(state_path(args.state)); validate(state)
    runners = _load_runners()
    default_executor = _default_executor()
    if not default_executor:
        raise EngineError(
            "no default_executor configured in .ai/runners.yaml; "
            "set one via 'ai-kit runner add <name> --default', or use "
            "'ai-kit dispatch <id> --runner <name>' for explicit dispatch"
        )
    if default_executor not in runners:
        raise EngineError(f"configured default_executor '{default_executor}' is not a registered runner in .ai/runners.yaml")
    if args.runner and args.runner != default_executor:
        raise EngineError(
            f"dispatch-ready only runs the configured default_executor ('{default_executor}'), "
            f"not '{args.runner}'; use 'ai-kit dispatch <id> --runner {args.runner}' for explicit dispatch"
        )
    runner_name = default_executor
    runner = runners[runner_name]
    tasks = task_map(state)
    candidates = [t for t in state["tasks"] if runnable(t, tasks)]
    if args.context:
        candidates = [t for t in candidates if t.get("context") == args.context]
    if args.epic:
        candidates = [t for t in candidates if t.get("epic") == args.epic]
    limit = args.limit if args.limit else len(candidates)
    claimed = []
    for task in candidates[:limit]:
        agent_id = args.agent_id or uuid.uuid4().hex[:8]
        start_args = argparse.Namespace(state=args.state, id=task["id"], action="start", actor=task["owner"], detail=f"auto-claimed by dispatch-ready for runner '{runner_name}'", evidence=None, expected_revision=None, agent_id=agent_id)
        try:
            _retry_transition(start_args)
        except EngineError:
            continue  # lost the claim race, or no longer runnable; skip rather than substitute another task
        claimed.append({"task": task["id"], "agent_id": agent_id})
    log_dir = workspace(state_path(args.state)) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    spawned = []
    for entry in claimed:
        # --state is a root-parser option and must precede the "dispatch"
        # subcommand token, or argparse's subparser rejects it as unrecognized.
        cmd = ["bash", str(ROOT / ".ai" / "scripts" / "ai-kit")]
        if args.state:
            cmd += ["--state", args.state]
        cmd += ["dispatch", entry["task"], "--runner", runner_name, "--agent-id", entry["agent_id"]]
        # Redirect the child's stdout/stderr to its own log file instead of
        # inheriting this process's fds: an inherited pipe stays open (and a
        # caller reading dispatch-ready's own output can hang or see
        # interleaved/corrupted data) until every spawned child also exits,
        # which defeats the point of a non-blocking fan-out.
        log_path = log_dir / f"dispatch_{entry['task']}.log"
        with log_path.open("w", encoding="utf-8") as log_handle:
            proc = _sp.Popen(cmd, cwd=str(ROOT), stdout=log_handle, stderr=_sp.STDOUT, close_fds=True)
        spawned.append({"task": entry["task"], "agent_id": entry["agent_id"], "pid": proc.pid, "log": display_path(log_path)})
    return {"runner": runner_name, "candidates": len(candidates), "claimed": len(claimed), "spawned": spawned}


def cmd_verify(args: argparse.Namespace) -> dict:
    """Run verification checks and produce a report. Does NOT auto-approve."""
    import subprocess as _sp
    state = load(state_path(args.state)); validate(state)
    task = task_map(state).get(args.id)
    if not task:
        raise EngineError(f"unknown task: {args.id}")
    report = {"task": task["id"], "checks": [], "passed": True}
    print(f"Verifying task {task['id']}...", file=sys.stderr)
    manifest = ROOT / ".ai" / "kit.yaml"
    executed_quality_checks = 0
    if manifest.exists():
        text = manifest.read_text(encoding="utf-8")
        for key in ("test_command", "lint_command", "typecheck_command", "build_command"):
            match = re.search(rf"{key}:\s*(.+)", text)
            if match:
                cmd = match.group(1).strip()
                if cmd == "true":
                    report["checks"].append({"name": key, "status": "skipped"})
                    continue
                executed_quality_checks += 1
                print(f"  Running {key}: {cmd}", file=sys.stderr)
                result = _sp.run(cmd, shell=True, cwd=str(ROOT), capture_output=True, text=True)
                check = {"name": key, "command": cmd, "exit_code": result.returncode, "status": "pass" if result.returncode == 0 else "fail"}
                if result.returncode != 0:
                    check["stderr"] = result.stderr[-500:] if result.stderr else ""
                    report["passed"] = False
                report["checks"].append(check)
    if executed_quality_checks == 0:
        warning = (
            "no test/lint/typecheck/build command is configured in .ai/kit.yaml "
            "(all are 'true' or missing) — verify only ran security gates and did "
            "NOT check functional correctness. Run 'ai-kit onboard --apply' or edit "
            ".ai/kit.yaml's verification section for a real project."
        )
        report["warning"] = warning
        print(f"  WARNING: {warning}", file=sys.stderr)
    gates = ROOT / ".ai" / "scripts" / "check-gates.sh"
    if gates.exists():
        print("  Running security gates (G4)...", file=sys.stderr)
        result = _sp.run(["bash", str(gates), "all"], cwd=str(ROOT), capture_output=True, text=True)
        check = {"name": "security-gates", "exit_code": result.returncode, "status": "pass" if result.returncode == 0 else "fail"}
        if result.returncode != 0:
            check["stderr"] = result.stderr[-500:] if result.stderr else ""
            report["passed"] = False
        report["checks"].append(check)
    verdict = "PASS" if report["passed"] else "FAIL"
    print(f"Verification {verdict}. Use 'ai-kit approve {task['id']} --role qa' to finalize.", file=sys.stderr)
    return report


def cmd_show(args: argparse.Namespace) -> dict:
    state = load(state_path(args.state)); validate(state); sync_phases(state)
    return state


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="ai-kit", description=__doc__)
    root.add_argument("--state", help="override workflow state path")
    root.add_argument("--json", action="store_true", help="always print JSON")
    sub = root.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init"); init.add_argument("--title", required=True); init.add_argument("--workflow", required=True); init.add_argument("--actor", default="planner"); init.add_argument("--force", action="store_true"); init.set_defaults(fn=cmd_init)
    add = sub.add_parser("add-task"); add.add_argument("id"); add.add_argument("--title", required=True); add.add_argument("--owner", required=True); add.add_argument("--phase", required=True); add.add_argument("--needs", nargs="*"); add.add_argument("--depends-on", action="append", default=[], metavar="PATH"); add.add_argument("--acceptance", nargs="+", action="append", required=True); add.add_argument("--files", nargs="*"); add.add_argument("--tags", nargs="*"); add.add_argument("--context"); add.add_argument("--epic"); add.add_argument("--actor", default="planner"); add.set_defaults(fn=cmd_add_task)
    update = sub.add_parser("update-task"); update.add_argument("id"); update.add_argument("--add-acceptance", nargs="+", action="append"); update.add_argument("--add-files", nargs="*"); update.add_argument("--add-tags", nargs="*"); update.add_argument("--actor", default="planner"); update.set_defaults(fn=cmd_update_task)
    ready = sub.add_parser("ready"); ready.add_argument("--context"); ready.add_argument("--epic"); ready.set_defaults(fn=cmd_ready)
    plan = sub.add_parser("plan"); plan.add_argument("--idea", required=True); plan.add_argument("--workflow", default="feature"); plan.add_argument("--owner", required=True); plan.add_argument("--acceptance", nargs="+", action="append", required=True); plan.add_argument("--files", nargs="*"); plan.add_argument("--tags", nargs="*"); plan.add_argument("--phase", default="build"); plan.add_argument("--context"); plan.add_argument("--epic"); plan.add_argument("--depends-on", action="append", default=[], metavar="PATH"); plan.add_argument("--scope"); plan.add_argument("--out-of-scope"); plan.add_argument("--risks", nargs="*"); plan.add_argument("--assumptions"); plan.add_argument("--actor", default="planner"); plan.add_argument("--force", action="store_true"); plan.set_defaults(fn=cmd_plan)
    trans = sub.add_parser("transition"); trans.add_argument("id"); trans.add_argument("action", choices=TRANSITIONS); trans.add_argument("--actor", required=True); trans.add_argument("--detail"); trans.add_argument("--evidence", nargs="+"); trans.add_argument("--expected-revision", type=int); trans.add_argument("--agent-id", help="unique identity of the agent instance, appended to claimed_by as 'actor#agent_id' for audit when multiple agents share a role"); trans.set_defaults(fn=cmd_transition)
    approve = sub.add_parser("approve"); approve.add_argument("id"); approve.add_argument("--role", choices=["qa", "review"], required=True); approve.add_argument("--status"); approve.add_argument("--reason", required=True); approve.set_defaults(fn=cmd_approve)
    verify = sub.add_parser("verify"); verify.add_argument("id"); verify.set_defaults(fn=cmd_verify)
    dispatch = sub.add_parser("dispatch"); dispatch.add_argument("id"); dispatch.add_argument("--runner"); dispatch.add_argument("--agent-id"); dispatch.set_defaults(fn=cmd_dispatch)
    dispatch_ready = sub.add_parser("dispatch-ready"); dispatch_ready.add_argument("--runner"); dispatch_ready.add_argument("--limit", type=int); dispatch_ready.add_argument("--context"); dispatch_ready.add_argument("--epic"); dispatch_ready.add_argument("--agent-id"); dispatch_ready.set_defaults(fn=cmd_dispatch_ready)
    route = sub.add_parser("route"); route.add_argument("id"); route.set_defaults(fn=cmd_route)
    status = sub.add_parser("status"); status.add_argument("--context"); status.add_argument("--epic"); status.set_defaults(fn=cmd_status)
    timeline = sub.add_parser("timeline"); timeline.set_defaults(fn=cmd_timeline)
    blocked = sub.add_parser("blocked"); blocked.set_defaults(fn=cmd_blocked)
    graph = sub.add_parser("graph"); graph.add_argument("--context"); graph.set_defaults(fn=cmd_graph)
    board = sub.add_parser("board"); board.add_argument("--context"); board.add_argument("--epic"); board.add_argument("--owner"); board.add_argument("--write", action="store_true"); board.add_argument("--format", choices=["json", "markdown"], default="json"); board.set_defaults(fn=cmd_board)
    context = sub.add_parser("context"); context_sub = context.add_subparsers(dest="context_command", required=True)
    context_add = context_sub.add_parser("add"); context_add.add_argument("name"); context_add.add_argument("--path", required=True); context_add.add_argument("--owner", required=True); context_add.add_argument("--force", action="store_true", help="update an existing context, bumping its revision"); context_add.set_defaults(fn=cmd_context_add)
    context_list = context_sub.add_parser("list"); context_list.set_defaults(fn=cmd_context_list)
    runner = sub.add_parser("runner"); runner_sub = runner.add_subparsers(dest="runner_command", required=True)
    runner_add = runner_sub.add_parser("add"); runner_add.add_argument("name"); runner_add.add_argument("--command", required=True); runner_add.add_argument("--model"); runner_add.add_argument("--provider"); runner_add.add_argument("--description"); runner_add.add_argument("--default", action="store_true"); runner_add.add_argument("--force", action="store_true"); runner_add.set_defaults(fn=cmd_runner_add)
    runner_list = runner_sub.add_parser("list"); runner_list.set_defaults(fn=cmd_runner_list)
    epics = sub.add_parser("epics"); epics.set_defaults(fn=cmd_epics)
    epic = sub.add_parser("epic"); epic_sub = epic.add_subparsers(dest="epic_command", required=True)
    epic_add = epic_sub.add_parser("add"); epic_add.add_argument("name"); epic_add.add_argument("--spec", required=True, help="path to the epic's Specification doc"); epic_add.add_argument("--owner"); epic_add.add_argument("--force", action="store_true", help="update an existing epic's spec, bumping its revision"); epic_add.set_defaults(fn=cmd_epic_add)
    epic_list = epic_sub.add_parser("list"); epic_list.set_defaults(fn=cmd_epic_list)
    drift = sub.add_parser("drift"); drift.add_argument("id"); drift.set_defaults(fn=cmd_drift)
    onboard = sub.add_parser("onboard"); onboard.add_argument("--apply", action="store_true"); onboard.set_defaults(fn=cmd_onboard)
    show = sub.add_parser("show"); show.set_defaults(fn=cmd_show)
    valid = sub.add_parser("validate"); valid.set_defaults(fn=lambda args: (validate(load(state_path(args.state))) or {"valid": True}))
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        output = args.fn(args)
        print(output if isinstance(output, str) else json.dumps(output, indent=2))
        return 0
    except EngineError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
