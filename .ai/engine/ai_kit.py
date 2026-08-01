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
VISUALIZER_DIR = ROOT / ".visualizer"
CONFIG_FILES = {
    "runners.yaml",
    "automation.yaml",
    "registry.yaml",
    "contexts.yaml",
    "epics.yaml",
    "rules.yaml",
    "kit.yaml",
}
STATUSES = ("todo", "in-progress", "implementation-complete", "qa-passed", "review-approved", "done", "blocked")


def _config_path(name: str) -> Path:
    """Resolve project config from the new directory, with legacy fallback."""
    if name not in CONFIG_FILES:
        raise EngineError(f"unsupported AI-Kit config: {name}")
    preferred = ROOT / ".ai-config" / name
    return preferred if preferred.exists() else ROOT / ".ai" / name


def _load_registry() -> dict:
    """Load role→domain and role→core-skill mappings from registry.yaml."""
    registry_path = _config_path("registry.yaml")
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
    path = _config_path(Path(relative_path).name) if Path(relative_path).name in CONFIG_FILES else ROOT / relative_path
    if not path.exists():
        return {}
    entries: dict[str, dict] = {}
    current = None
    in_section = False
    header = f"{top_key}:"
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if line == header:
            in_section = True
            current = None
            continue
        if not line.startswith((" ", "\t")):
            in_section = False
            current = None
            continue
        if not in_section:
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
            elif value.startswith("[") and value.endswith("]"):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    value = [item.strip().strip("\"'") for item in value[1:-1].split(",") if item.strip()]
            entries[current][field_match.group(1)] = value
    return entries


def _load_contexts() -> dict:
    """Load the bounded-context/module registry from .ai-config/contexts.yaml.

    Format:
      contexts:
        ordering:
          path: src/ordering/*
          owner: backend
    `path` is an fnmatch glob (matches the whole relative path, `*` spans
    `/`) checked against each task's `files` when G6 module_boundary is on.
    """
    return _load_yaml_registry(".ai-config/contexts.yaml", "contexts")


def _load_epics() -> dict:
    """Load the epic/specification registry from .ai-config/epics.yaml.

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
    return _load_yaml_registry(".ai-config/epics.yaml", "epics")


def _load_runners() -> dict:
    """Load runner profiles from the structured YAML registry."""
    return _load_yaml_registry(".ai-config/runners.yaml", "runners")


def _load_automation_roles() -> dict:
    """Load and validate the qa/reviewer role -> runner:model mapping.

    Format (.ai-config/automation.yaml):
      roles:
        qa:
          runner: opencode-cli
          model: deepseek-v4-flash
        reviewer:
          runner: opencode-cli
          model: deepseek-v4-pro
    Deliberately does NOT define 'executor' here: runners.yaml's
    default_executor/default_model already is the single source of truth for
    "which runner/model executes a task" (used by plain `dispatch` and
    `dispatch-ready`). Redefining it a second time in automation.yaml would
    let the two drift out of sync with no error; `ai-kit pipeline` instead
    resolves executor via `_resolve_runner(None, None)`, the same fallback
    plain `dispatch` uses. automation.yaml only needs to add the two roles
    (qa, reviewer) that have no equivalent anywhere else in the registry.
    """
    roles = _load_yaml_registry(".ai-config/automation.yaml", "roles")
    for name in ("qa", "reviewer"):
        if name not in roles or not roles[name].get("runner"):
            raise EngineError(
                f".ai-config/automation.yaml is missing role '{name}'; add a 'roles.{name}.runner' "
                f"(and optional 'model') entry naming a runner registered in .ai-config/runners.yaml"
            )
    return roles


def _load_runner_aliases() -> dict[str, str]:
    """Load legacy runner-name aliases from a flat YAML section."""
    path = _config_path("runners.yaml")
    if not path.exists():
        return {}
    aliases: dict[str, str] = {}
    in_section = False
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if line == "runner_aliases:":
            in_section = True
            continue
        if not line.startswith((" ", "\t")):
            in_section = False
            continue
        if not in_section:
            continue
        match = re.match(r"^  (\S+):\s*(.+)$", line)
        if not match:
            continue
        value = match.group(2).strip()
        if value.startswith('"'):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                pass
        aliases[match.group(1)] = str(value)
    return aliases


def _runner_scalar(value: str) -> str:
    """Serialize a runner field without losing spaces, quotes, or ``#``."""
    return json.dumps(value, ensure_ascii=False)


def _default_executor() -> str | None:
    """Read the top-level `default_executor: <name>` scalar from .ai-config/runners.yaml, or None if unset."""
    path = _config_path("runners.yaml")
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


def _default_model() -> str | None:
    """Read the top-level default model paired with default_executor."""
    path = _config_path("runners.yaml")
    if not path.exists():
        return None
    prefix = "default_model:"
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


def _entry_models(entry: dict) -> list[str]:
    """Return the normalized allowlist for grouped or legacy runner entries."""
    models = entry.get("models")
    if isinstance(models, list):
        values = [str(item).strip() for item in models if str(item).strip()]
    elif isinstance(models, str) and models.strip():
        values = [item.strip() for item in models.split(",") if item.strip()]
    elif entry.get("model"):
        values = [item.strip() for item in str(entry["model"]).split(",") if item.strip()]
    else:
        values = []
    return list(dict.fromkeys(values))


def _split_runner_reference(reference: str) -> tuple[str, str | None]:
    if ":" not in reference:
        return reference, None
    runner, model = reference.split(":", 1)
    if not runner or not model:
        raise EngineError(f"invalid runner reference '{reference}'; expected <runner>:<model>")
    return runner, model


def _resolve_runner(explicit: str | None, requested_model: str | None = None) -> tuple[str, dict, str | None]:
    """Resolve runner and model, or fall back to default_executor/default_model.

    Returns (name, entry, model). Raises EngineError if neither an explicit runner
    nor a configured default_executor is available, if the configured
    default_executor doesn't name a registered runner (misconfiguration), or
    if the resolved name isn't registered.
    """
    runners = _load_runners()
    aliases = _load_runner_aliases()
    default_executor = _default_executor()
    name = explicit or default_executor
    if not name:
        raise EngineError(
            "no --runner given and no default_executor configured in .ai-config/runners.yaml; "
            "pass --runner explicitly or set one via 'ai-kit runner add <name> --default'"
        )
    alias_target = aliases.get(name)
    if alias_target:
        name, alias_model = _split_runner_reference(alias_target)
        if requested_model and alias_model and requested_model != alias_model:
            raise EngineError(f"runner alias '{explicit}' fixes model '{alias_model}', not '{requested_model}'")
        requested_model = requested_model or alias_model
    else:
        name, reference_model = _split_runner_reference(name)
        if requested_model and reference_model and requested_model != reference_model:
            raise EngineError(f"runner reference '{explicit}' fixes model '{reference_model}', not '{requested_model}'")
        requested_model = requested_model or reference_model
    if name not in runners:
        available = ", ".join([*runners.keys(), *aliases.keys()])
        raise EngineError(f"unknown runner profile or alias: {explicit or default_executor}. Available: {available}")
    entry = runners[name]
    models = _entry_models(entry)
    selected_model = requested_model
    if selected_model is None and name == default_executor:
        selected_model = _default_model()
    if selected_model is None and len(models) == 1:
        selected_model = models[0]
    if selected_model is None and len(models) > 1:
        raise EngineError(f"runner '{name}' supports multiple models; pass --model explicitly")
    if selected_model is not None and not models:
        raise EngineError(f"runner '{name}' does not declare selectable models")
    if selected_model is not None and selected_model not in models:
        raise EngineError(f"model '{selected_model}' is not configured for runner '{name}'. Available: {', '.join(models)}")
    if selected_model is None and "{model}" in entry.get("command", ""):
        raise EngineError(f"runner '{name}' command requires a model but no model was selected")
    if models and "{model}" not in entry.get("command", ""):
        raise EngineError(f"runner '{name}' declares models but its command is missing the {{model}} placeholder")
    return name, entry, selected_model


def _write_runners(
    runners: dict[str, dict],
    default_executor: str | None,
    default_model: str | None,
    aliases: dict[str, str],
) -> None:
    path = _config_path("runners.yaml")
    lines = []
    if default_executor:
        lines.append(f"default_executor: {_runner_scalar(default_executor)}")
        if default_model:
            lines.append(f"default_model: {_runner_scalar(default_model)}")
        lines.append("")
    lines.append("runners:")
    for name, fields in sorted(runners.items()):
        lines.append(f"  {name}:")
        lines.append(f"    command: {_runner_scalar(fields['command'])}")
        if fields.get("models"):
            models = _entry_models(fields)
            lines.append(f"    models: {json.dumps(models, ensure_ascii=False)}")
        for key in ("model", "provider", "description", "input"):
            if fields.get(key) is not None and fields.get(key) != "":
                lines.append(f"    {key}: {_runner_scalar(str(fields[key]))}")
    if aliases:
        lines.extend(["", "runner_aliases:"])
        for name, target in sorted(aliases.items()):
            lines.append(f"  {name}: {_runner_scalar(target)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _render_runner_command(template: str, prompt: str, model: str | None) -> str:
    """Render prompt/model placeholders with shell-safe quoting."""
    command = template.replace("{prompt}", shlex.quote(prompt))
    if model is not None:
        command = command.replace("{model}", shlex.quote(model))
    if "{model}" in command:
        raise EngineError("runner command still contains {model}; select a model before dispatch")
    return command


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
    except (TypeError, ValueError):
        return None


def _context_upstreams(name: str | None, contexts: dict | None = None) -> list[str]:
    """Return a context's declared upstream modules in deterministic order."""
    if not name:
        return []
    contexts = contexts if contexts is not None else _load_contexts()
    if name not in contexts:
        return []
    return list(dict.fromkeys(contexts[name].get("depends_on", []) or []))


def _upstream_context_revisions(name: str | None, contexts: dict | None = None) -> dict[str, int]:
    contexts = contexts if contexts is not None else _load_contexts()
    revisions = {}
    for upstream in _context_upstreams(name, contexts):
        revision = contexts.get(upstream, {}).get("revision")
        try:
            revisions[upstream] = int(revision)
        except (TypeError, ValueError):
            continue
    return revisions


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
    """Load gate rules from .ai-config/rules.yaml. Returns sensible defaults when the file is missing or malformed.

    This function enables configurable gates (G1, G3) by reading boolean flags
    from a YAML-like file at .ai-config/rules.yaml. It uses regex parsing (no PyYAML
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
    rules_path = _config_path("rules.yaml")
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
    manifest = _config_path("kit.yaml")
    match = re.search(r"^\s*stack:\s*\[([^]]*)\]", manifest.read_text(encoding="utf-8"), re.MULTILINE)
    return {item.strip().lower() for item in match.group(1).split(",") if item.strip()} if match else set()


def _parse_inline_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None:
        return []
    text = str(value).strip()
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except json.JSONDecodeError:
            inner = text[1:-1]
            return [item.strip().strip("\"'") for item in inner.split(",") if item.strip()]
    return [text] if text else []


def _load_skill_metadata(skill_dir: Path) -> dict:
    defaults = {
        "name": skill_dir.name,
        "domain": skill_dir.parent.name,
        "version": "0.0.0",
        "status": "active",
        "owner": "unknown",
        "reviewed_at": "",
        "reviewers": [],
        "depends_on": [],
        "triggers": [],
        "documents": ["overview.md", "patterns.md", "best-practices.md", "pitfalls.md", "examples.md"],
        "deprecated": False,
        "entrypoint": (skill_dir / "overview.md").relative_to(ROOT).as_posix(),
        "path": skill_dir.relative_to(ROOT).as_posix(),
    }
    meta_path = skill_dir / "skill.meta.yaml"
    if not meta_path.exists():
        return defaults
    fields: dict[str, object] = {}
    for raw_line in meta_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()
    metadata = dict(defaults)
    metadata["name"] = str(fields.get("name") or metadata["name"]).strip()
    metadata["domain"] = str(fields.get("domain") or metadata["domain"]).strip()
    metadata["version"] = str(fields.get("version") or metadata["version"]).strip()
    metadata["status"] = str(fields.get("status") or metadata["status"]).strip()
    metadata["owner"] = str(fields.get("owner") or metadata["owner"]).strip()
    metadata["reviewed_at"] = str(fields.get("reviewed_at") or metadata["reviewed_at"]).strip()
    metadata["reviewers"] = _parse_inline_list(fields.get("reviewers"))
    metadata["depends_on"] = _parse_inline_list(fields.get("depends_on"))
    metadata["triggers"] = [item.lower() for item in _parse_inline_list(fields.get("triggers"))]
    metadata["documents"] = _parse_inline_list(fields.get("documents")) or defaults["documents"]
    metadata["deprecated"] = str(fields.get("deprecated", "false")).lower() == "true"
    metadata["entrypoint"] = str(fields.get("entrypoint") or metadata["entrypoint"]).strip()
    metadata["path"] = str(fields.get("path") or metadata["path"]).strip()
    return metadata


def _load_skill_triggers() -> dict[str, dict]:
    triggers = _load_yaml_registry(".ai-config/registry.yaml", "skill_triggers")
    normalized: dict[str, dict] = {}
    for trigger_id, payload in triggers.items():
        normalized[trigger_id] = {
            "id": trigger_id,
            "match": [item.lower() for item in _parse_inline_list(payload.get("match"))],
            "core_skills": _parse_inline_list(payload.get("core_skills")),
            "technology_skills": _parse_inline_list(payload.get("technology_skills")),
            "reason": str(payload.get("reason") or "").strip(),
        }
    return normalized


def _task_text(task: dict) -> str:
    parts = [task.get("title") or ""]
    parts.extend(task.get("tags") or [])
    parts.extend(task.get("files") or [])
    parts.extend(task.get("acceptance") or [])
    return " ".join(str(part) for part in parts).lower()


def _tokenize_task(task: dict) -> set[str]:
    tokens: set[str] = set(configured_stack())
    tokens.update(str(tag).lower() for tag in (task.get("tags") or []))
    for value in [task.get("title") or "", " ".join(task.get("files") or [])]:
        for token in re.findall(r"[a-z0-9][a-z0-9_-]{1,}", value.lower()):
            tokens.add(token)
    return tokens


def _resolve_technology_skill(root: Path, ref: str) -> Path | None:
    candidate = root / ref
    if candidate.exists():
        return candidate
    if "/" in ref:
        candidate = root / ".ai" / "skills" / ref
        if candidate.exists():
            return candidate
    return None


def _technology_skill_doc_paths(skill_dir: Path, metadata: dict) -> list[str]:
    docs = metadata.get("documents") or []
    if not docs:
        docs = ["overview.md", "patterns.md", "best-practices.md", "pitfalls.md", "examples.md"]
    resolved: list[str] = []
    for doc in docs:
        doc_path = skill_dir / doc
        if doc_path.exists():
            resolved.append(doc_path.relative_to(ROOT).as_posix())
    return resolved


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
        task.setdefault("upstream_context_revisions", {})
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
    # _load_rules() reads .ai-config/rules.yaml at runtime, so operators can toggle
    # gates without modifying the engine. All rules default to True (safe) when
    # the config file is missing, malformed, or unreadable.
    rules = _load_rules()

    # G1 - Plan: configurable via rules.yaml `planning_first` key
    # When planning_first is true, tasks past "todo" in non-plan phases
    # must have all their plan-phase dependencies completed first.
    # Set `planning_first: false` in .ai-config/rules.yaml to skip this check.
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
    # Set `review_required: false` in .ai-config/rules.yaml to skip this check.
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
    # context's registered path glob (.ai-config/contexts.yaml), so two agents working in
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


def _generate_visualizer_data(state_arg: str | Path | None = None) -> dict:
    if not VISUALIZER_DIR.exists():
        return {}
    state_path_value = state_path(str(state_arg) if state_arg is not None else None)
    if not state_path_value.exists():
        payloads = {
            "board.json": {status: [] for status in STATUSES},
            "architecture.json": _load_contexts(),
            "impact.json": {},
            "events.json": [],
            "dag.json": {"tasks": [], "edges": [], "waves": 0, "ready": [], "critical_path": []},
        }
        for filename, payload in payloads.items():
            (VISUALIZER_DIR / filename).write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
        return payloads
    state = load(state_path_value)
    validate(state)
    board = {status: [] for status in STATUSES}
    for task in state["tasks"]:
        entry = _board_entry(task)
        entry["tags"] = task.get("tags", [])
        entry["files"] = task.get("files", [])
        entry["acceptance_count"] = len(task.get("acceptance", []))
        board[task["status"]].append(entry)

    architecture = _load_contexts()
    impact = {}
    for name in architecture:
        impact[name] = cmd_context_impact(argparse.Namespace(state=str(state_path_value), name=name, _state=state))

    events = []
    if EVENT_LOG.exists():
        lines = [line.strip() for line in EVENT_LOG.read_text(encoding="utf-8").splitlines() if line.strip()]
        for line in lines[-200:]:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    VISUALIZER_DIR.mkdir(parents=True, exist_ok=True)
    payloads = {
        "board.json": board,
        "architecture.json": architecture,
        "impact.json": impact,
        "events.json": events,
        "dag.json": _generate_dag_payload(state),
    }
    for filename, payload in payloads.items():
        (VISUALIZER_DIR / filename).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payloads


def _auto_generate_visualizer_data(path: Path) -> None:
    try:
        _generate_visualizer_data(path)
    except Exception as exc:
        print(f"WARNING: visualizer regeneration failed: {exc}", file=sys.stderr)


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
    _auto_generate_visualizer_data(path)
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
    task = {"id": args.id, "title": args.title, "owner": args.owner, "phase": args.phase, "needs": args.needs or [], "status": "todo", "acceptance": acceptance, "files": args.files or [], "tags": args.tags or [], "attempts": 0, "evidence": [], "blocked_reason": None, "claimed_by": None, "context": context, "epic": epic, "base_commit": _git_head(), "context_revision": context_revision, "epic_revision": _epic_revision(epic), "upstream_context_revisions": _upstream_context_revisions(context), "depends_on": depends_on, "contract_hashes": _contract_hashes(depends_on)}
    state["tasks"].append(task)
    validate(state)
    sync_phases(state)
    sync_tasks_md(state, path)
    event(state, path, "add-task", task, args.actor, None, "todo", "task added")
    save(state, path, state["revision"])
    _auto_generate_visualizer_data(path)
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
    _auto_generate_visualizer_data(path)
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
    _auto_generate_visualizer_data(path)
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
    build_task = {"id": "T2", "title": args.idea, "owner": args.owner, "phase": args.phase, "needs": ["T1"], "status": "todo", "acceptance": acceptance, "files": args.files or [], "tags": args.tags or [], "attempts": 0, "evidence": [], "blocked_reason": None, "claimed_by": None, "context": context, "epic": epic, "base_commit": base_commit, "context_revision": _context_revision(context), "epic_revision": _epic_revision(epic), "upstream_context_revisions": _upstream_context_revisions(context), "depends_on": depends_on, "contract_hashes": contract_hashes}
    state["tasks"] = [plan_task, build_task]; validate(state); sync_phases(state)
    root = workspace(path)
    root.joinpath("roadmap").mkdir(parents=True, exist_ok=True); root.joinpath("plan").mkdir(parents=True, exist_ok=True); root.joinpath("tasks").mkdir(parents=True, exist_ok=True)
    root.joinpath("roadmap/roadmap.md").write_text(f"# Roadmap\n\nGoal: {args.idea}\n\n1. Confirm scope, risks, and acceptance criteria.\n2. Implement in phase `{args.phase}` and verify evidence.\n", encoding="utf-8")
    root.joinpath("plan/plan.md").write_text(f"# Plan\n\nGoal: {args.idea}\n\nScope: {args.scope or 'pending Planner confirmation'}\nOut of scope: {args.out_of_scope or 'none recorded'}\nRisks: {', '.join(args.risks or ['none recorded'])}\nAssumptions: {args.assumptions or 'none recorded'}\nTags: {', '.join(args.tags or ['none'])}\n\nImplementation owner: {args.owner}\n", encoding="utf-8")
    sync_tasks_md(state, path)
    event(state, path, "plan", None, args.actor, None, None, "idea converted to draft plan")
    save(state, path)
    _auto_generate_visualizer_data(path)
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
    tokens = _tokenize_task(task)
    task_text = _task_text(task)
    trigger_registry = _load_skill_triggers()

    selected_tech: dict[str, dict] = {}
    selected_core: dict[str, dict] = {}
    trigger_matches: list[dict] = []

    def add_core(name: str, reason: str, phase: str) -> None:
        path = skill_root / "core" / name / "SKILL.md"
        if not path.exists():
            return
        key = path.relative_to(ROOT).as_posix()
        current = selected_core.get(key)
        if not current:
            selected_core[key] = {
                "name": name,
                "path": (skill_root / "core" / name).relative_to(ROOT).as_posix(),
                "entrypoint": key,
                "documents": [key],
                "selection_reasons": [reason],
                "loading_phase": phase,
                "type": "core",
            }
            return
        if reason not in current["selection_reasons"]:
            current["selection_reasons"].append(reason)
        if current["loading_phase"].startswith("role") and phase.startswith("trigger"):
            current["loading_phase"] = phase

    def add_technology(skill_dir: Path, reason: str, phase: str) -> None:
        metadata = _load_skill_metadata(skill_dir)
        entrypoint = metadata.get("entrypoint") or (skill_dir / "overview.md").relative_to(ROOT).as_posix()
        key = str(entrypoint)
        docs = _technology_skill_doc_paths(skill_dir, metadata)
        current = selected_tech.get(key)
        if not current:
            selected_tech[key] = {
                "name": f"{skill_dir.parent.name}/{skill_dir.name}",
                "path": metadata.get("path") or skill_dir.relative_to(ROOT).as_posix(),
                "entrypoint": key,
                "documents": docs,
                "selection_reasons": [reason],
                "loading_phase": phase,
                "type": "technology",
                "metadata": metadata,
            }
            return
        if reason not in current["selection_reasons"]:
            current["selection_reasons"].append(reason)
        for doc in docs:
            if doc not in current["documents"]:
                current["documents"].append(doc)
        if current["loading_phase"].startswith("role") and phase.startswith("trigger"):
            current["loading_phase"] = phase

    # Base role core skills.
    for name in CORE_BY_ROLE.get(role, ["skill-router"]):
        add_core(name, f"role:{role}", "role-core")

    # Base technology from role-owned domains, filtered by stack/tags and metadata triggers.
    domain_candidates: list[Path] = []
    for domain in domains:
        folder = skill_root / domain
        if not folder.exists():
            continue
        domain_candidates.extend(sorted(path for path in folder.iterdir() if path.is_dir()))

    for skill_dir in domain_candidates:
        skill_name = skill_dir.name.lower()
        domain_name = skill_dir.parent.name.lower()
        should_include = (
            skill_name in tokens
            or domain_name in tokens
        )
        if should_include:
            add_technology(skill_dir, f"role-domain:{domain_name}", "role-technology")

    # Trigger-driven concerns from registry.
    for trigger_id, trigger in trigger_registry.items():
        terms = trigger.get("match") or []
        hits = [term for term in terms if term and term in task_text]
        if not hits:
            continue
        reason = trigger.get("reason") or f"trigger:{trigger_id}"
        trigger_matches.append({"id": trigger_id, "matches": hits, "reason": reason})
        for core_skill in trigger.get("core_skills") or []:
            add_core(core_skill, reason, "trigger-core")
        for tech_ref in trigger.get("technology_skills") or []:
            # llm-model trigger dynamically chooses openai vs general application skill.
            if trigger_id == "llm-model" and tech_ref == "ai/openai":
                if not {"openai", "gpt"} & tokens and "openai" not in task_text and "gpt" not in task_text:
                    continue
            if trigger_id == "llm-model" and tech_ref == "ai/llm-application":
                if {"openai", "gpt"} & tokens or "openai" in task_text or "gpt" in task_text:
                    continue
            resolved = _resolve_technology_skill(ROOT, tech_ref)
            if resolved:
                add_technology(resolved, reason, "trigger-technology")

    # RAG trigger-specific database skill selection.
    rag_selected = any(item["id"] == "rag-retrieval" for item in trigger_matches)
    if rag_selected and ("pgvector" in tokens or "postgresql" in tokens):
        resolved = _resolve_technology_skill(ROOT, "database/pgvector")
        if resolved:
            add_technology(resolved, "RAG stack indicates pgvector backend", "trigger-database")
    if rag_selected and "qdrant" in tokens:
        resolved = _resolve_technology_skill(ROOT, "database/qdrant")
        if resolved:
            add_technology(resolved, "RAG stack indicates qdrant backend", "trigger-database")

    phase_order = {"role-core": 1, "role-technology": 2, "trigger-core": 3, "trigger-technology": 4, "trigger-database": 5}
    all_details = list(selected_core.values()) + list(selected_tech.values())
    all_details.sort(key=lambda item: (phase_order.get(item["loading_phase"], 9), item["entrypoint"]))
    for idx, item in enumerate(all_details, start=1):
        item["loading_order"] = idx

    skills = [item["entrypoint"] for item in all_details]
    root = workspace(state_path(args.state))
    response = {
        "task": task["id"],
        "owner": role,
        "tags": task["tags"],
        "role_contract": (Path(".ai") / "agents" / role).as_posix(),
        "skills": skills,
        "context": [display_path(root / "plan" / "plan.md"), display_path(root / "tasks" / "tasks.md"), ".ai/engine/state-schema.md"] + task["files"],
        "skill_details": all_details,
        "trigger_matches": trigger_matches,
        "loading_instructions": [
            "Read each selected entrypoint first: technology skills start with overview.md, core skills start with SKILL.md.",
            "Then load phase-specific documents in order: patterns.md -> best-practices.md -> pitfalls.md -> examples.md when needed for the assigned phase.",
            "Load only the selected skills listed in this route output; do not pull unrelated domains."
        ],
    }
    if getattr(args, "explain", False):
        response["explain"] = {
            "role_domains": domains,
            "task_tokens": sorted(tokens),
            "phase_order": phase_order,
            "selection_summary": {
                "core_count": len(selected_core),
                "technology_count": len(selected_tech),
            },
        }
    return response


def cmd_context_add(args: argparse.Namespace) -> dict:
    path = _config_path("contexts.yaml")
    contexts = _load_contexts()
    if args.name in contexts and not args.force:
        raise EngineError(f"context already registered: {args.name}; use --force to update it (bumps revision)")
    requested_dependencies = getattr(args, "depends_on", None)
    dependencies = list(dict.fromkeys(requested_dependencies)) if requested_dependencies is not None else list(contexts.get(args.name, {}).get("depends_on", []) or [])
    if args.name in dependencies:
        raise EngineError(f"context cannot depend on itself: {args.name}")
    for dependency in dependencies:
        if dependency not in contexts:
            raise EngineError(f"unknown context dependency: {dependency}")
    candidate = dict(contexts)
    candidate[args.name] = {"depends_on": dependencies}
    seen: set[str] = set()
    active: set[str] = set()

    def visit(module: str) -> None:
        if module in active:
            raise EngineError(f"context dependency cycle detected at {module}")
        if module in seen:
            return
        active.add(module)
        for dependency in candidate.get(module, {}).get("depends_on", []) or []:
            visit(dependency)
        active.remove(module)
        seen.add(module)

    for module in candidate:
        visit(module)
    # revision increments on every update so tasks recorded against a stale
    # context (a moved/renamed path glob, a changed owner) can be detected.
    revision = int(contexts[args.name].get("revision", 1)) + 1 if args.name in contexts else 1
    contexts[args.name] = {"path": args.path, "owner": args.owner, "revision": str(revision)}
    if dependencies:
        contexts[args.name]["depends_on"] = dependencies
    lines = ["contexts:"]
    for name, fields in sorted(contexts.items()):
        lines.append(f"  {name}:")
        lines.append(f"    path: {fields['path']}")
        lines.append(f"    owner: {fields['owner']}")
        lines.append(f"    revision: {fields.get('revision', 1)}")
        if fields.get("depends_on"):
            lines.append(f"    depends_on: {json.dumps(fields['depends_on'], ensure_ascii=False)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"name": args.name, "path": args.path, "owner": args.owner, "revision": revision, "depends_on": dependencies}


def cmd_context_list(args: argparse.Namespace) -> dict:
    return _load_contexts()


def cmd_context_impact(args: argparse.Namespace) -> dict:
    contexts = _load_contexts()
    if args.name not in contexts:
        raise EngineError(f"unknown context: {args.name}")
    direct = sorted(name for name, fields in contexts.items() if args.name in (fields.get("depends_on") or []))
    all_dependents: list[str] = []
    seen: set[str] = set()
    queue = list(direct)
    while queue:
        dependent = queue.pop(0)
        if dependent in seen:
            continue
        seen.add(dependent)
        all_dependents.append(dependent)
        queue.extend(sorted(name for name, fields in contexts.items() if dependent in (fields.get("depends_on") or [])))
    state = getattr(args, "_state", None)
    if state is None:
        state = load(state_path(args.state))
    validate(state)
    affected = [task["id"] for task in state["tasks"] if task.get("status") != "done" and task.get("context") in {args.name, *all_dependents}]
    return {"name": args.name, "direct_dependents": direct, "all_dependents": all_dependents, "affected_tasks": affected}


def cmd_runner_add(args: argparse.Namespace) -> dict:
    runners = _load_runners()
    aliases = _load_runner_aliases()
    requested_model = getattr(args, "model", None)
    requested_models = getattr(args, "models", None)
    requested_default_model = getattr(args, "default_model", None)
    if requested_model and requested_models:
        raise EngineError("use either --model or --models, not both")
    if requested_models:
        requested_models = list(dict.fromkeys(requested_models))
        if "{model}" not in args.command:
            raise EngineError("--models requires a command containing the {model} placeholder")
    if args.name in runners and not args.force:
        raise EngineError(f"runner already registered: {args.name}; use --force to update it")
    runners[args.name] = {
        "command": args.command,
        "provider": args.provider or "",
        "description": args.description or "",
    }
    if requested_models:
        runners[args.name]["models"] = requested_models
    elif requested_model:
        runners[args.name]["model"] = requested_model
    default_executor = args.name if args.default else _default_executor()
    default_model = requested_default_model if requested_default_model is not None else _default_model()
    if args.default and requested_default_model is None:
        models = _entry_models(runners[args.name])
        default_model = models[0] if len(models) == 1 else None
    if default_model and default_executor:
        target_name, target_reference_model = _split_runner_reference(default_executor)
        target_name = aliases.get(target_name, target_name)
        target_name, alias_model = _split_runner_reference(target_name)
        target_entry = runners.get(target_name)
        target_models = _entry_models(target_entry or {})
        if target_models and default_model not in target_models:
            raise EngineError(
                f"default_model '{default_model}' is not configured for default_executor '{default_executor}'"
            )
    if args.default and len(_entry_models(runners[args.name])) > 1 and not default_model:
        raise EngineError("--default requires --default-model when the runner has multiple models")
    _write_runners(runners, default_executor, default_model, aliases)
    return {"name": args.name, "default_executor": default_executor, "default_model": default_model, **runners[args.name]}


def cmd_runner_list(args: argparse.Namespace) -> dict:
    return {
        "default_executor": _default_executor(),
        "default_model": _default_model(),
        "runner_aliases": _load_runner_aliases(),
        "runners": _load_runners(),
    }


def cmd_epic_add(args: argparse.Namespace) -> dict:
    """Register (or, with --force, re-register) an epic's Specification doc.

    Mirrors cmd_context_add: revision starts at 1 and bumps on every --force
    update, so tasks planned against an older spec revision become
    detectable as stale via `ai-kit drift`. Registration is optional — `epic`
    still works as a free-form tag with no entry here.
    """
    path = _config_path("epics.yaml")
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


# Index of each status in the kit's linear 6-step lifecycle (todo -> ... ->
# done). `blocked` has no place on this axis -- it's an orthogonal branch,
# not a stage -- and is represented separately as -1.
STAGE_INDEX = {
    "todo": 0,
    "in-progress": 1,
    "implementation-complete": 2,
    "qa-passed": 3,
    "review-approved": 4,
    "done": 5,
}


def _task_stage(status: str) -> int:
    return STAGE_INDEX.get(status, -1)


def _remaining_stages(status: str) -> int:
    """Stages left until 'done', used as each task's weight on the critical path.

    A blocked task's true remaining distance is unknown (its last active
    stage isn't tracked), so it's weighted at the maximum (5) -- treated as
    unresolved work rather than assumed to be nearly finished.
    """
    if status == "blocked":
        return 5
    return 5 - STAGE_INDEX.get(status, 0)


def _task_history(state: dict) -> dict[str, dict[str, str]]:
    """First timestamp each task reached each status, from the in-memory event log.

    state["events"] is the full append-only history for this workflow (see
    `event()`), so this needs no separate read of events.jsonl and stays
    correct for whichever --state file is in play.
    """
    history: dict[str, dict[str, str]] = {}
    for item in state.get("events", []):
        task_id, to_status, ts = item.get("task"), item.get("to"), item.get("ts")
        if not task_id or not to_status or not ts:
            continue
        bucket = history.setdefault(task_id, {})
        if to_status not in bucket:
            bucket[to_status] = ts
    return history


def _generate_dag_payload(state: dict) -> dict:
    """Task-dependency DAG for the visualizer: edges, longest-path layering
    (`layer`, i.e. wave number), lifecycle `stage`, per-task first-reached
    timestamps, and the precomputed ready set / critical path so the UI
    doesn't have to recompute graph algorithms client-side.
    """
    tasks = state["tasks"]
    by_id = task_map(state)

    layer_cache: dict[str, int] = {}

    def layer_of(task_id: str) -> int:
        if task_id not in layer_cache:
            needs = by_id[task_id]["needs"]
            layer_cache[task_id] = 0 if not needs else 1 + max(layer_of(dep) for dep in needs)
        return layer_cache[task_id]

    weight_cache: dict[str, int] = {}
    critical_parent: dict[str, str | None] = {}

    def weight_of(task_id: str) -> int:
        if task_id not in weight_cache:
            task = by_id[task_id]
            best_dep, best_dep_weight = None, 0
            for dep in task["needs"]:
                dep_weight = weight_of(dep)
                if dep_weight > best_dep_weight:
                    best_dep, best_dep_weight = dep, dep_weight
            weight_cache[task_id] = _remaining_stages(task["status"]) + best_dep_weight
            critical_parent[task_id] = best_dep
        return weight_cache[task_id]

    for task_id in by_id:
        layer_of(task_id)
        weight_of(task_id)

    critical_path: list[str] = []
    if weight_cache:
        node = max(weight_cache, key=lambda t: weight_cache[t])
        while node:
            critical_path.append(node)
            node = critical_parent[node]
        critical_path.reverse()

    history = _task_history(state)
    dag_tasks = []
    edges = []
    ready_ids = []
    for task in tasks:
        task_id = task["id"]
        is_ready = runnable(task, by_id)
        if is_ready:
            ready_ids.append(task_id)
        dag_tasks.append({
            "id": task_id,
            "title": task["title"],
            "owner": task["owner"],
            "context": task.get("context"),
            "epic": task.get("epic"),
            "phase": task["phase"],
            "status": task["status"],
            "stage": _task_stage(task["status"]),
            "needs": task["needs"],
            "layer": layer_of(task_id),
            "ready": is_ready,
            "blocked_reason": task.get("blocked_reason"),
            "history": history.get(task_id, {}),
        })
        for dep in task["needs"]:
            edges.append({"from": dep, "to": task_id, "unlocked": by_id[dep]["status"] == "done"})

    return {
        "tasks": dag_tasks,
        "edges": edges,
        "waves": (max(layer_cache.values()) + 1) if layer_cache else 0,
        "ready": ready_ids,
        "critical_path": critical_path,
    }


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
        "upstream_context_stale": sorted(
            name for name, planned in (task.get("upstream_context_revisions") or {}).items()
            if _context_revision(name) != planned
        ),
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
    report["upstream_context_stale"] = flags["upstream_context_stale"]

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


def cmd_visualizer_generate(args: argparse.Namespace) -> dict:
    return _generate_visualizer_data(getattr(args, "state", None))


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
        manifest = _config_path("kit.yaml")
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
    # Identity fields are optional (manual `ai-kit approve` calls omit them);
    # `ai-kit pipeline` passes them so evidence records which runner/model
    # actually rendered the QA/review verdict, per-agent-instance via agent_id.
    runner = getattr(args, "runner", None)
    model = getattr(args, "model", None)
    agent_id = getattr(args, "agent_id", None)
    if runner:
        payload["runner"] = runner
    if model:
        payload["model"] = model
    if agent_id:
        payload["agent_id"] = agent_id
    root = workspace(state_path(args.state))
    evidence_dir = root / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = evidence_dir / f"{args.role}_evidence_{task['id']}.json"
    evidence_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    args.action = action
    args.evidence = [evidence_path.as_posix()]
    args.detail = args.reason
    args.actor = f"{args.role}#{agent_id}" if agent_id else args.role
    return cmd_transition(args)


def cmd_pipeline(args: argparse.Namespace) -> dict:
    """Advance one task through dispatch -> verify -> QA -> review -> close.

    Executor identity comes from runners.yaml's default_executor/default_model
    (the same fallback plain `dispatch` uses); qa/reviewer identities come
    from .ai-config/automation.yaml. Refuses to proceed if QA or review would run
    under the exact same (runner, model) as the executor -- the point of a
    separate approval phase is a second, independent look.
    This is a synchronous, manually-invoked chain (no background scheduler,
    no auto-trigger, no retry/resume across phases) by design for this phase
    of automation; a stalled/failed phase just stops here and reports why.
    """
    state = load(state_path(args.state)); validate(state)
    task = task_map(state).get(args.id)
    if not task:
        raise EngineError(f"unknown task: {args.id}")
    roles = _load_automation_roles()
    exec_runner, _exec_entry, exec_model = _resolve_runner(None, None)
    qa_runner, _qa_entry, qa_model = _resolve_runner(roles["qa"]["runner"], roles["qa"].get("model"))
    rev_runner, _rev_entry, rev_model = _resolve_runner(roles["reviewer"]["runner"], roles["reviewer"].get("model"))
    if (qa_runner, qa_model) == (exec_runner, exec_model):
        raise EngineError(
            f".ai-config/automation.yaml: role 'qa' resolves to the same identity as 'executor' "
            f"({qa_runner}/{qa_model}); QA must run under a different runner or model"
        )
    if (rev_runner, rev_model) == (exec_runner, exec_model):
        raise EngineError(
            f".ai-config/automation.yaml: role 'reviewer' resolves to the same identity as 'executor' "
            f"({rev_runner}/{rev_model}); review must run under a different runner or model"
        )

    print(f"[pipeline] {task['id']}: dispatching to executor {exec_runner}/{exec_model}...", file=sys.stderr)
    cmd_dispatch(argparse.Namespace(state=args.state, id=task["id"], runner=exec_runner, model=exec_model, agent_id=args.agent_id))

    print(f"[pipeline] {task['id']}: verifying...", file=sys.stderr)
    report = cmd_verify(argparse.Namespace(state=args.state, id=task["id"]))
    if not report["passed"]:
        raise EngineError(
            f"pipeline stopped: verify failed for {task['id']}; inspect the report above, fix, "
            f"then re-run 'ai-kit pipeline {task['id']}' (task remains at implementation-complete)"
        )

    print(f"[pipeline] {task['id']}: QA approval via {qa_runner}/{qa_model}...", file=sys.stderr)
    qa_agent_id = uuid.uuid4().hex[:8]
    cmd_approve(argparse.Namespace(
        state=args.state, id=task["id"], role="qa", status=None,
        reason=f"Auto-approved by pipeline ({qa_runner}/{qa_model})",
        runner=qa_runner, model=qa_model, agent_id=qa_agent_id,
    ))

    print(f"[pipeline] {task['id']}: review approval via {rev_runner}/{rev_model}...", file=sys.stderr)
    rev_agent_id = uuid.uuid4().hex[:8]
    cmd_approve(argparse.Namespace(
        state=args.state, id=task["id"], role="review", status=None,
        reason=f"Auto-approved by pipeline ({rev_runner}/{rev_model})",
        runner=rev_runner, model=rev_model, agent_id=rev_agent_id,
    ))

    print(f"[pipeline] {task['id']}: closing...", file=sys.stderr)
    cmd_transition(argparse.Namespace(
        state=args.state, id=task["id"], action="close", actor="system",
        detail="Auto-closed by ai-kit pipeline", evidence=None, expected_revision=None, agent_id=None,
    ))
    return {
        "task": task["id"], "status": "done",
        "executor": f"{exec_runner}/{exec_model}",
        "qa": f"{qa_runner}/{qa_model}",
        "reviewer": f"{rev_runner}/{rev_model}",
    }


def _write_task_handoff(
    task: dict,
    route_payload: dict,
    state_arg: str | None,
    runner_name: str,
    runner: dict,
    model: str | None,
    agent_id: str | None,
) -> Path:
    """Write a JSON snapshot of a task for 'input: json-file' runners.

    Lets the runner CLI read the task directly instead of re-discovering it
    from tasks.md; the agent still self-reports completion via
    'ai-kit transition complete' exactly as with prompt-mode runners.
    """
    runner_label = f"{runner_name}/{model}" if model else runner_name
    state_flag = f" --state {state_arg}" if state_arg else ""
    instructions = (
        f"Execute the task per the acceptance criteria above. Do not violate AGENTS.md. "
        f"When done, run: bash .ai/scripts/ai-kit{state_flag} transition {task['id']} "
        f"complete --actor {task['owner']} --detail 'Completed by {runner_label}'"
    )
    handoff = {
        "schema_version": 1,
        "task": {
            "id": task["id"], "title": task["title"], "owner": task["owner"],
            "phase": task["phase"], "acceptance": task["acceptance"],
            "files": task["files"], "needs": task["needs"], "tags": task["tags"],
            "context": task.get("context"), "epic": task.get("epic"),
            "depends_on": task.get("depends_on", []),
        },
        "execution": {
            "runner": runner_name, "provider": runner.get("provider") or None,
            "model": model, "agent_id": agent_id,
        },
        "routing": {
            "skills": route_payload.get("skills", []),
            "skill_details": route_payload.get("skill_details", []),
            "loading_instructions": route_payload.get("loading_instructions", []),
        },
        "instructions": instructions,
    }
    handoff_path = workspace(state_path(state_arg)) / "handoffs" / f"{task['id']}.json"
    handoff_path.parent.mkdir(parents=True, exist_ok=True)
    handoff_path.write_text(json.dumps(handoff, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return handoff_path


def cmd_dispatch(args: argparse.Namespace) -> dict:
    import subprocess as _sp
    state = load(state_path(args.state)); validate(state)
    task = task_map(state).get(args.id)
    if not task:
        raise EngineError(f"unknown task: {args.id}")
    runner_name, runner, selected_model = _resolve_runner(args.runner, args.model)
    template = runner["command"]
    # The State Manager, not the runner, owns lifecycle transitions: claim the
    # task (todo -> in-progress) here so the runner only ever needs to report
    # completion, matching the single `complete` transition it is prompted for.
    if task["status"] == "todo":
        start_args = argparse.Namespace(state=args.state, id=task["id"], action="start", actor=task["owner"], detail=f"auto-started for dispatch to runner '{runner_name}'", evidence=None, expected_revision=None, agent_id=getattr(args, "agent_id", None))
        task = _retry_transition(start_args)
    elif task["status"] != "in-progress":
        raise EngineError(f"cannot dispatch {task['id']} from status {task['status']} (must be todo or in-progress)")
    state_flag = f" --state {args.state}" if args.state else ""
    runner_label = f"{runner_name}/{selected_model}" if selected_model else runner_name
    handoff_path = None
    route_payload = cmd_route(argparse.Namespace(state=args.state, id=task["id"], explain=False))
    if runner.get("input") == "json-file":
        handoff_path = _write_task_handoff(task, route_payload, args.state, runner_name, runner, selected_model, getattr(args, "agent_id", None))
        handoff_display = display_path(handoff_path)
        prompt = f"You are {task['owner']}. Read and execute the task JSON at {handoff_display}. Do not violate AGENTS.md. When done, run: bash .ai/scripts/ai-kit{state_flag} transition {task['id']} complete --actor {task['owner']} --detail 'Completed by {runner_label}'"
    else:
        tasks_md = display_path(workspace(state_path(args.state)) / "tasks" / "tasks.md")
        prompt = f"You are {task['owner']}. Execute task {task['id']} per the requirements in {tasks_md}. Do not violate AGENTS.md. When done, run: bash .ai/scripts/ai-kit{state_flag} transition {task['id']} complete --actor {task['owner']} --detail 'Completed by {runner_label}'"
    # Runner templates hold {prompt} unquoted; shlex.quote is the single
    # place quoting happens, so a template can never double-quote it.
    cmd = _render_runner_command(template, prompt, selected_model)
    print(f"Dispatching task {task['id']} to runner '{runner_label}'...", file=sys.stderr)
    # shell=True is required: `template` is a shell command string from
    # .ai-config/runners.yaml, not an argv list, so it can't be handed to
    # subprocess without a shell (see G4 in AGENTS.md: write access to
    # runners.yaml is equivalent to arbitrary shell execution here).
    result = _sp.run(cmd, shell=True, cwd=str(ROOT), stdin=_sp.DEVNULL)
    # Audit log
    audit = {
        "ts": now(), "task": task["id"], "runner": runner_name,
        "model": selected_model,
        "provider": runner.get("provider") or None,
        "command": cmd, "exit_code": result.returncode,
        "input_mode": runner.get("input") or "prompt",
        "handoff_file": display_path(handoff_path) if handoff_path else None,
    }
    audit_path = workspace(state_path(args.state)) / f"dispatch_log_{task['id']}.json"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    if result.returncode != 0:
        raise EngineError(f"Runner {runner_name} exited with code {result.returncode}")
    return {"task": task["id"], "runner": runner_name, "status": "dispatched", "skills": route_payload.get("skills", [])}


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
    default_executor = _default_executor()
    if not default_executor:
        raise EngineError(
            "no default_executor configured in .ai-config/runners.yaml; "
            "set one via 'ai-kit runner add <name> --default', or use "
            "'ai-kit dispatch <id> --runner <name>' for explicit dispatch"
        )
    if args.runner and args.runner != default_executor:
        raise EngineError(
            f"dispatch-ready only runs the configured default_executor ('{default_executor}'), "
            f"not '{args.runner}'; use 'ai-kit dispatch <id> --runner {args.runner}' for explicit dispatch"
        )
    configured_default_model = _default_model()
    if args.model and configured_default_model and args.model != configured_default_model:
        raise EngineError(
            f"dispatch-ready only runs the configured default_model ('{configured_default_model}'), "
            f"not '{args.model}'; use explicit dispatch for another model"
        )
    runner_name, runner, selected_model = _resolve_runner(args.runner, args.model)
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
        if selected_model is not None:
            cmd += ["--model", selected_model]
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
    manifest = _config_path("kit.yaml")
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
                # shell=True is required: `cmd` is a shell command string
                # from .ai-config/kit.yaml (test_command/lint_command/...),
                # not an argv list -- same G4 threat model as dispatch's
                # runner command above: treat write access to kit.yaml as
                # equivalent to arbitrary shell execution.
                result = _sp.run(cmd, shell=True, cwd=str(ROOT), capture_output=True, text=True)
                check = {"name": key, "command": cmd, "exit_code": result.returncode, "status": "pass" if result.returncode == 0 else "fail"}
                if result.returncode != 0:
                    check["stderr"] = result.stderr[-500:] if result.stderr else ""
                    report["passed"] = False
                report["checks"].append(check)
    if executed_quality_checks == 0:
        warning = (
            "no test/lint/typecheck/build command is configured in .ai-config/kit.yaml "
            "(all are 'true' or missing) — verify only ran security gates and did "
            "NOT check functional correctness. Run 'ai-kit onboard --apply' or edit "
            ".ai-config/kit.yaml's verification section for a real project."
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
    approve = sub.add_parser("approve"); approve.add_argument("id"); approve.add_argument("--role", choices=["qa", "review"], required=True); approve.add_argument("--status"); approve.add_argument("--reason", required=True); approve.add_argument("--runner"); approve.add_argument("--model"); approve.add_argument("--agent-id"); approve.set_defaults(fn=cmd_approve)
    verify = sub.add_parser("verify"); verify.add_argument("id"); verify.set_defaults(fn=cmd_verify)
    dispatch = sub.add_parser("dispatch"); dispatch.add_argument("id"); dispatch.add_argument("--runner"); dispatch.add_argument("--model"); dispatch.add_argument("--agent-id"); dispatch.set_defaults(fn=cmd_dispatch)
    dispatch_ready = sub.add_parser("dispatch-ready"); dispatch_ready.add_argument("--runner"); dispatch_ready.add_argument("--model"); dispatch_ready.add_argument("--limit", type=int); dispatch_ready.add_argument("--context"); dispatch_ready.add_argument("--epic"); dispatch_ready.add_argument("--agent-id"); dispatch_ready.set_defaults(fn=cmd_dispatch_ready)
    pipeline = sub.add_parser("pipeline"); pipeline.add_argument("id"); pipeline.add_argument("--agent-id"); pipeline.set_defaults(fn=cmd_pipeline)
    route = sub.add_parser("route"); route.add_argument("id"); route.add_argument("--explain", action="store_true"); route.set_defaults(fn=cmd_route)
    status = sub.add_parser("status"); status.add_argument("--context"); status.add_argument("--epic"); status.set_defaults(fn=cmd_status)
    timeline = sub.add_parser("timeline"); timeline.set_defaults(fn=cmd_timeline)
    blocked = sub.add_parser("blocked"); blocked.set_defaults(fn=cmd_blocked)
    graph = sub.add_parser("graph"); graph.add_argument("--context"); graph.set_defaults(fn=cmd_graph)
    board = sub.add_parser("board"); board.add_argument("--context"); board.add_argument("--epic"); board.add_argument("--owner"); board.add_argument("--write", action="store_true"); board.add_argument("--format", choices=["json", "markdown"], default="json"); board.set_defaults(fn=cmd_board)
    context = sub.add_parser("context"); context_sub = context.add_subparsers(dest="context_command", required=True)
    context_add = context_sub.add_parser("add"); context_add.add_argument("name"); context_add.add_argument("--path", required=True); context_add.add_argument("--owner", required=True); context_add.add_argument("--depends-on", action="append", default=None, metavar="MODULE"); context_add.add_argument("--force", action="store_true", help="update an existing context, bumping its revision"); context_add.set_defaults(fn=cmd_context_add)
    context_list = context_sub.add_parser("list"); context_list.set_defaults(fn=cmd_context_list)
    context_impact = context_sub.add_parser("impact"); context_impact.add_argument("name"); context_impact.set_defaults(fn=cmd_context_impact)
    visualizer = sub.add_parser("visualizer"); visualizer_sub = visualizer.add_subparsers(dest="visualizer_command", required=True)
    visualizer_generate = visualizer_sub.add_parser("generate"); visualizer_generate.set_defaults(fn=cmd_visualizer_generate)
    runner = sub.add_parser("runner"); runner_sub = runner.add_subparsers(dest="runner_command", required=True)
    runner_add = runner_sub.add_parser("add"); runner_add.add_argument("name"); runner_add.add_argument("--command", required=True); runner_add.add_argument("--model"); runner_add.add_argument("--models", nargs="+"); runner_add.add_argument("--provider"); runner_add.add_argument("--description"); runner_add.add_argument("--default-model"); runner_add.add_argument("--default", action="store_true"); runner_add.add_argument("--force", action="store_true"); runner_add.set_defaults(fn=cmd_runner_add)
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
