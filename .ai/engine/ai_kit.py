#!/usr/bin/env python3
"""Dependency-free control plane for AI-Kit v2 workflows."""
from __future__ import annotations

import argparse
import ast
import hashlib
import fnmatch
import os
import json
import re
import shlex
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = Path(__file__).resolve()
WORK = ROOT / ".ai-work"
STATE = WORK / "state" / "workflow.json"
CURRENT = WORK / "state" / "current.json"
EVENT_LOG = WORK / "logs" / "events.jsonl"
VISUALIZER_DIR = ROOT / ".visualizer"
# Per-artifact schema version for the generated .visualizer/*.json payloads.
# Bump an individual entry when that artifact's shape changes in a way a
# consumer must know about (added/removed/retyped top-level field); the
# board/architecture/impact/dag payloads themselves are keyed by task id,
# context name, or fixed field name and are read that way by app.js/dag.html
# (see tests/test_visualizer_contract.py), so schema_version is never mixed
# into those payloads -- it would be misread as a task, module, or column.
# .visualizer/artifacts.json is the one place a consumer checks compatibility
# before parsing the rest, mirroring the handoff JSON's own "schema_version".
# discovered-architecture.json is the one deliberate exception: it is a new,
# self-contained artifact (not a bag keyed by task/module id at its top
# level), so it carries its own top-level "schema_version" field the same
# way the handoff JSON does -- see ARCHITECTURE_DISCOVERY_SCHEMA_VERSION.
VISUALIZER_ARTIFACT_VERSIONS = {
    "board.json": 1,
    "architecture.json": 1,
    "impact.json": 1,
    "events.json": 1,
    "dag.json": 1,
    "discovered-architecture.json": 1,
}
VISUALIZER_MANIFEST_SCHEMA_VERSION = 1
# .ai-work/tasks/<id>.json: the self-contained "task contract" snapshot
# written alongside tasks.md by add-task/plan (see state-schema.md's Task
# contract files section). Bump only when its top-level shape changes.
TASK_CONTRACT_SCHEMA_VERSION = 1
# A plan draft is deliberately separate from workflow.json: it captures the
# evolving result of a human/agent conversation, while workflow.json remains
# the deterministic execution control plane.  Bump only if the draft's
# top-level shape changes.
PLAN_DRAFT_SCHEMA_VERSION = 1
PLAN_DRAFT_STATUSES = {"drafting", "ready", "materialized"}
WORKFLOW_STATE_SCHEMA_VERSION = 4
TASK_LEASE_SECONDS = 30 * 60
CONFIG_FILES = {
    "runners.yaml",
    "automation.yaml",
    "registry.yaml",
    "contexts.yaml",
    "epics.yaml",
    "rules.yaml",
    "kit.yaml",
}
STATUSES = ("todo", "in-progress", "implementation-complete", "qa-passed", "review-approved", "done", "blocked", "superseded", "cancelled")
# Statuses that satisfy a downstream `needs`/plan dependency. `superseded`
# and `cancelled` are terminal-but-not-`done`: the work was deliberately
# abandoned (in favor of another task, or because it's no longer wanted)
# rather than completed, but a dependent must still be able to proceed
# instead of waiting forever on work that will never finish.
DEPENDENCY_SATISFYING_STATUSES = {"done", "superseded", "cancelled"}


def _config_path(name: str) -> Path:
    """Resolve installed project config, or the kit's install template.

    ``.ai-config`` is deliberately project-owned runtime configuration and is
    created only by the installer.  Keeping the canonical seed files under
    ``.ai/install/config`` lets the source repository run its own read-only
    validation without tracking a second live configuration tree.
    """
    if name not in CONFIG_FILES:
        raise EngineError(f"unsupported AI-Kit config: {name}")
    preferred = ROOT / ".ai-config" / name
    return preferred if preferred.exists() else ROOT / ".ai" / "install" / "config" / name


def _writable_config_path(name: str) -> Path:
    """Return a project-owned config path, seeding it from the kit if needed.

    Read operations may use an install template in the source repository;
    mutations must never write that template.  This helper is intentionally
    used only by config-changing commands and materializes `.ai-config/` in
    the target project on first write.
    """
    if name not in CONFIG_FILES:
        raise EngineError(f"unsupported AI-Kit config: {name}")
    path = ROOT / ".ai-config" / name
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    template = ROOT / ".ai" / "install" / "config" / name
    if template.exists():
        path.write_bytes(template.read_bytes())
    return path


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
            else:
                # Without this, a role whose domain list wraps onto a second
                # line simply fails the regex and vanishes from `owners`, so
                # that role silently routes no technology skills at all.
                wrapped = re.match(r"\s+(\w+):\s*(.+)$", line)
                if wrapped:
                    _reject_unterminated_list(wrapped.group(2).strip(), registry_path, f"owners.{wrapped.group(1)}")
    core_names: list[str] = []
    match = re.search(r"names:\s*\[([^\]]*)\]", text)
    if match:
        core_names = [n.strip() for n in match.group(1).split(",") if n.strip()]
    return {"owners": owners, "core_skills": {"names": core_names}}


def _reject_unterminated_list(value: str, source: Path, key: str) -> None:
    """Fail loudly on a ``[...]`` array wrapped across physical lines.

    Every YAML reader in this engine is line-based (no PyYAML dependency),
    so a value that opens ``[`` on one line and closes ``]`` on the next is
    not merely unsupported -- it is silently stored as the first line's raw
    text, producing a list-shaped field that can never match anything, with
    no error at load time. That failure mode is invisible: a
    ``skill_triggers`` entry simply stops firing. Raise instead, naming the
    file and key, so the author sees it immediately.
    """
    if value.startswith("[") and not value.endswith("]"):
        raise EngineError(
            f"{display_path(source)}: value for '{key}' opens '[' but does not close ']' on the "
            f"same line. This engine's YAML readers are line-based, so a multi-line array is "
            f"silently truncated rather than parsed -- keep the whole list on one line."
        )


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
            _reject_unterminated_list(value, path, f"{current}.{field_match.group(1)}")
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


def _parse_role_enabled(value) -> bool:
    """Interpret an automation.yaml 'enabled' scalar. Absent means True."""
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    text = str(value).strip().strip("\"'").lower()
    if text in {"true", "yes", "1", "on"}:
        return True
    if text in {"false", "no", "0", "off"}:
        return False
    raise EngineError(f".ai-config/automation.yaml: invalid 'enabled' value {value!r}; use true/false")


def _load_automation_roles() -> dict:
    """Load and validate the qa/reviewer role -> runner:model mapping.

    Format (.ai-config/automation.yaml):
      roles:
        qa:
          enabled: true
          runner: opencode-cli
          model: deepseek-v4-flash
        reviewer:
          enabled: false
          runner: opencode-cli
          model: deepseek-v4-pro
    'enabled' (optional, default true) toggles whether post-completion
    automation (`ai-kit pipeline` / the opt-in post_completion trigger)
    auto-dispatches that role to its configured runner at all. Set it to
    'false' to leave a task parked at the status just before that role's
    verdict -- `implementation-complete` for qa, `qa-passed` for review --
    instead of spawning a CLI subprocess for it. That parked state is the
    handoff point for a human or an interactive session (not a dispatched
    subprocess) to verify by hand via `ai-kit approve`/`transition`; see
    `_run_post_completion`'s manual-wait branches. 'runner' is required only
    when the role is enabled -- a disabled role may omit it, since there is
    nothing to dispatch to.
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
        if name not in roles:
            raise EngineError(
                f".ai-config/automation.yaml is missing role '{name}'; add a 'roles.{name}.runner' "
                f"(and optional 'model') entry naming a runner registered in .ai-config/runners.yaml, "
                f"or 'roles.{name}.enabled: false' to verify it manually instead"
            )
        roles[name]["enabled"] = _parse_role_enabled(roles[name].get("enabled"))
        if roles[name]["enabled"] and not roles[name].get("runner"):
            raise EngineError(
                f".ai-config/automation.yaml role '{name}' is enabled but has no 'runner'; add one, "
                f"or set 'roles.{name}.enabled: false' to verify it manually instead"
            )
        for backup_key in ("backup_runner", "backup_model"):
            if backup_key in roles[name] and not isinstance(roles[name][backup_key], str):
                raise EngineError(f".ai-config/automation.yaml: role '{name}' has invalid '{backup_key}'")
    return roles


def _load_post_completion_config() -> dict:
    """Load the opt-in post-completion automation switch.

    Format (.ai-config/automation.yaml):
      post_completion:
        enabled: true
    A missing file, missing section, or malformed value all default to
    'enabled: false' so dispatch/transition/pipeline behavior is unchanged
    unless an operator explicitly opts in.
    """
    path = _config_path("automation.yaml")
    if not path.exists():
        return {"enabled": False}
    enabled = False
    retry_on_rejection = False
    max_retries = 0
    dispatch_ready_on_close = False
    dispatch_ready_limit = 1
    backup_after_retries = 1
    in_section = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line == "post_completion:":
            in_section = True
            continue
        if in_section:
            if not line.startswith((" ", "\t")):
                break
            match = re.match(r"^\s+enabled:\s*(\S+)", line)
            if match:
                enabled = match.group(1).strip().strip('"\'').lower() in {"true", "yes", "1"}
            match = re.match(r"^\s+retry_on_rejection:\s*(\S+)", line)
            if match:
                retry_on_rejection = match.group(1).strip().strip('"\'').lower() in {"true", "yes", "1"}
            match = re.match(r"^\s+max_retries:\s*(\d+)", line)
            if match:
                max_retries = min(5, max(0, int(match.group(1))))
            match = re.match(r"^\s+dispatch_ready_on_close:\s*(\S+)", line)
            if match:
                dispatch_ready_on_close = match.group(1).strip().strip('"\'').lower() in {"true", "yes", "1"}
            match = re.match(r"^\s+dispatch_ready_limit:\s*(\d+)", line)
            if match:
                dispatch_ready_limit = min(50, max(1, int(match.group(1))))
            match = re.match(r"^\s+backup_after_retries:\s*(\d+)", line)
            if match:
                backup_after_retries = min(5, max(1, int(match.group(1))))
    return {
        "enabled": enabled,
        "retry_on_rejection": retry_on_rejection,
        "max_retries": max_retries if retry_on_rejection else 0,
        "dispatch_ready_on_close": dispatch_ready_on_close,
        "dispatch_ready_limit": dispatch_ready_limit,
        "backup_after_retries": backup_after_retries,
    }


def _post_completion_enabled() -> bool:
    return bool(_load_post_completion_config().get("enabled"))


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
    path = _writable_config_path("runners.yaml")
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
        "file_conflict_check": True,  # G7 - block starting a task whose files overlap an active task outside its needs graph
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
    "planner": ["requirements-intake", "requirement-decomposer", "skill-router"],
    "researcher": ["requirements-intake", "skill-router"],
    "architect": ["refactoring", "api-contract", "system-designer"],
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
    "reclaim": ({"in-progress"}, "in-progress"),
    "complete": ({"in-progress"}, "implementation-complete"),
    "qa-pass": ({"implementation-complete"}, "qa-passed"),
    "review-approve": ({"qa-passed"}, "review-approved"),
    "close": ({"review-approved"}, "done"),
    "block": ({"todo", "in-progress", "implementation-complete", "qa-passed", "review-approved"}, "blocked"),
    "unblock": ({"blocked"}, "todo"),
    "reject": ({"implementation-complete", "qa-passed"}, "todo"),
    # A controlled way to retire a task whose objective was already met by
    # another task (or is no longer wanted) without hand-editing status to
    # "done" (which would corrupt the audit trail) or leaving it stuck at
    # "todo" forever. Both require --detail (why); "supersede" additionally
    # requires --by <task-id> naming the task that replaced this one, so the
    # replacement relationship is recorded, not just implied.
    "supersede": ({"todo", "in-progress", "blocked"}, "superseded"),
    "cancel": ({"todo", "in-progress", "blocked"}, "cancelled"),
}


class EngineError(Exception):
    pass


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _lease_expiry() -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=TASK_LEASE_SECONDS)).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _lease_is_expired(value: str | None) -> bool:
    if not value:
        return True
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")) <= datetime.now(timezone.utc)
    except ValueError:
        return True


def state_path(value: str | None) -> Path:
    return Path(value).resolve() if value else STATE


def workspace(path: Path) -> Path:
    """Derive a workspace from state/<workflow>.json or a standalone state file."""
    return path.parent.parent if path.parent.name == "state" else path.parent / path.stem


def _dispatch_audit_path(state_file: Path, task_id: str, role: str | None = None) -> Path:
    """Canonical location for structured dispatch audit metadata.

    Runner stdout/stderr belongs in ``logs/``; this JSON records the command,
    runner identity, handoff, and exit code, so it lives in the separate
    workspace ``dispatch/`` collection instead of cluttering its root.
    """
    name = f"{role}_{task_id}" if role else task_id
    return workspace(state_file) / "dispatch" / f"{name}.json"


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
    return {"version": WORKFLOW_STATE_SCHEMA_VERSION, "workflow_id": uuid.uuid4().hex, "revision": 0, "title": title, "workflow": workflow, "created_at": now(), "tasks": [], "phases": [], "events": []}


def configured_stack() -> set[str]:
    manifest = _config_path("kit.yaml")
    match = re.search(r"^\s*stack:\s*\[([^]]*)\]", manifest.read_text(encoding="utf-8"), re.MULTILINE)
    return {item.strip().lower() for item in match.group(1).split(",") if item.strip()} if match else set()


def configured_source_dirs() -> list[str]:
    """kit.yaml's `project.source_dirs`, the scan scope architecture
    discovery is confined to -- the same list `onboard`/`analyze` propose."""
    manifest = _config_path("kit.yaml")
    if not manifest.exists():
        return []
    match = re.search(r"^\s*source_dirs:\s*\[([^]]*)\]", manifest.read_text(encoding="utf-8"), re.MULTILINE)
    return [item.strip() for item in match.group(1).split(",") if item.strip()] if match else []


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
        _reject_unterminated_list(value.strip(), meta_path, key.strip())
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


def _load_stack_skills() -> dict[str, list[str]]:
    """Load registry.yaml's `stack_skills:` map of skill path -> stack tags.

    Routing otherwise matches a technology skill only when the skill's own
    directory name (or its domain) appears in the task's tokens, which leaves
    every skill whose name differs from its tag unreachable via
    `kit.yaml project.stack`: `docker-compose-local` declares
    `stack: [docker, compose]`, `nestjs-core` declares `[nestjs]`, and so on.
    This section already encodes the intended mapping -- it simply was not
    read by anything.

    Written in flow style (`name: {path: ..., stack: [a, b]}`), so it needs
    its own small parser rather than the indented-block reader above.
    """
    path = _config_path("registry.yaml")
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    if "stack_skills:" not in text:
        return {}
    section = text.split("stack_skills:", 1)[1]
    mapping: dict[str, list[str]] = {}
    for line in section.splitlines():
        if line and not line.startswith((" ", "\t")):
            break  # next top-level key
        match = re.match(r"^  (\S+):\s*\{path:\s*([^,}]+),\s*stack:\s*\[([^\]]*)\]\s*\}", line)
        if match:
            skill_path = match.group(2).strip().rstrip("/")
            tags = [tag.strip().lower() for tag in match.group(3).split(",") if tag.strip()]
            if tags:
                mapping[skill_path] = tags
    return mapping


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
    parts.extend(task.get("acceptance") or [])
    return " ".join(str(part) for part in parts).lower()


def _tokenize_task(task: dict) -> set[str]:
    tokens: set[str] = set(configured_stack())
    tokens.update(str(tag).lower() for tag in (task.get("tags") or []))
    for value in [task.get("title") or "", " ".join(task.get("acceptance") or [])]:
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
        # ``-1`` is an explicit create-only precondition.  It is used by
        # draft creation/materialization so a race can never overwrite an
        # already-created plan or workflow state.
        if expected_revision == -1 and disk_revision is not None:
            raise EngineError(f"state already exists: {path}")
        if expected_revision not in {None, -1} and disk_revision != expected_revision:
            raise EngineError(f"state changed concurrently (expected revision {expected_revision}, found {disk_revision})")
        state["revision"] = (disk_revision or 0) + 1
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        lock.unlink(missing_ok=True)
    if path == STATE:
        active = [task["id"] for task in state["tasks"] if task["status"] == "in-progress"]
        summary = {"version": 1, "workflow_state": display_path(path), "workflow_id": state.get("workflow_id"), "title": state["title"], "workflow": state["workflow"], "active_tasks": active, "updated_at": now()}
        CURRENT.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


def task_map(state: dict) -> dict:
    return {task["id"]: task for task in state["tasks"]}


def validate(state: dict) -> None:
    required = {"version", "revision", "title", "workflow", "tasks", "phases", "events"}
    missing = required - set(state)
    if missing:
        raise EngineError(f"state missing keys: {', '.join(sorted(missing))}")
    state.setdefault("workflow_id", uuid.uuid5(uuid.NAMESPACE_URL, f"ai-kit:{state.get('title')}:{state.get('created_at', '')}").hex)
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
        task.setdefault("superseded_by", None)
        task.setdefault("contract_revision", None)
        task.setdefault("contract_hash", None)
        task.setdefault("claim_id", None)
        task.setdefault("claim_expires_at", None)
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
        if task["status"] not in STATUSES:
            raise EngineError(f"task {task['id']} has invalid status")
        if task["status"] == "superseded" and not task.get("superseded_by"):
            raise EngineError(f"task {task['id']} is superseded but has no superseded_by task recorded")
        if task.get("superseded_by") and task["superseded_by"] not in tasks:
            raise EngineError(f"task {task['id']} superseded_by references unknown task: {task['superseded_by']}")
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
            past_todo = task["status"] not in {"todo", "blocked", "superseded", "cancelled"}
            if past_todo and task["phase"] != "plan":
                plan_deps = [dep for dep in task["needs"] if tasks[dep].get("phase") == "plan"]
                if plan_deps and not all(tasks[dep]["status"] in DEPENDENCY_SATISFYING_STATUSES for dep in plan_deps):
                    offender = next(dep for dep in plan_deps if tasks[dep]["status"] not in DEPENDENCY_SATISFYING_STATUSES)
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
        status = "complete" if tasks and all(task["status"] in DEPENDENCY_SATISFYING_STATUSES for task in tasks) else "open" if any(runnable(task, task_map(state)) for task in tasks) else "planned"
        phases.append({"id": name, "status": status, "tasks": [task["id"] for task in tasks]})
    state["phases"] = phases


def sync_tasks_md(state: dict, state_path: Path) -> None:
    """Sync .ai-work/tasks/tasks.md with current workflow state."""
    tasks_dir = workspace(state_path) / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    tasks_md = tasks_dir / "tasks.md"
    lines = ["# Tasks", ""]
    for task in state["tasks"]:
        status_mark = "x" if task["status"] == "done" else "~" if task["status"] in {"superseded", "cancelled"} else " "
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
        if task.get("superseded_by"):
            lines.append(f"  - Superseded by: {task['superseded_by']}")
    tasks_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def runnable(task: dict, tasks: dict) -> bool:
    return task["status"] == "todo" and all(tasks[dep]["status"] in DEPENDENCY_SATISFYING_STATUSES for dep in task["needs"])


def _transitive_needs(task_id: str, tasks: dict) -> set[str]:
    """All task ids `task_id` (transitively) needs -- its full upstream dependency set."""
    seen: set[str] = set()
    stack = list(tasks.get(task_id, {}).get("needs", []))
    while stack:
        dep = stack.pop()
        if dep in seen or dep not in tasks:
            continue
        seen.add(dep)
        stack.extend(tasks[dep].get("needs", []))
    return seen


def _file_conflicts(task: dict, state: dict) -> list[dict]:
    """Other non-terminal tasks whose `files` overlap `task`'s files with no
    needs relationship (in either direction) connecting the two.

    A declared `needs` edge already orders two tasks safely (G1 blocks the
    dependent from starting first); this only flags the case `needs` does
    NOT cover -- two tasks that touch the same file(s) with no ordering
    between them at all, which is exactly what lets two agents (or two
    dispatch calls) race on the same file. Declaring `needs` when adding a
    task is the fix; this is the safety net for when that declaration is
    missing or wrong, e.g. a task added by a different agent/process that
    didn't know about the overlap.
    """
    task_files = set(task.get("files") or [])
    if not task_files:
        return []
    tasks = task_map(state)
    upstream = _transitive_needs(task["id"], tasks)
    conflicts = []
    for other in state["tasks"]:
        if other["id"] == task["id"] or other["status"] != "in-progress":
            continue
        overlap = task_files & set(other.get("files") or [])
        if not overlap:
            continue
        if other["id"] in upstream or task["id"] in _transitive_needs(other["id"], tasks):
            continue
        conflicts.append({"task": other["id"], "status": other["status"], "files": sorted(overlap)})
    return conflicts


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
        if action == "qa-pass":
            _validate_qa_checks(task, payload, item)
        if action == "review-approve" and payload.get("verdict") != "approve":
            raise EngineError(f"review evidence is not approved: {item}")


def _validate_qa_checks(task: dict, payload: dict, source: str) -> None:
    """Validate the optional structured `checks` list on QA evidence.

    Real-world QA often mixes results that mean very different things for a
    'pass' verdict: a failure the task's own change introduced, a failure
    that already existed on the target environment before this task touched
    anything (a "baseline failure"), and a check that simply doesn't apply
    to this task's scope. Treating all three the same as "the suite failed,
    therefore no pass" blocks legitimate work forever; treating them all the
    same as "some other check failed, so it's fine" silently rubber-stamps
    real regressions. `checks` (optional, backward compatible with plain
    {"status": "pass"} evidence) lets a QA agent record each check's
    classification explicitly instead of collapsing that judgment call into
    a single boolean.
    """
    checks = payload.get("checks")
    if checks is None:
        return
    if not isinstance(checks, list):
        raise EngineError(f"QA evidence 'checks' for task {task['id']} must be a list: {source}")
    for check in checks:
        if not isinstance(check, dict):
            raise EngineError(f"QA evidence 'checks' entries for task {task['id']} must be objects: {source}")
        name = check.get("name")
        result = check.get("result")
        if not name or result not in {"pass", "fail"}:
            raise EngineError(
                f"QA evidence check for task {task['id']} needs a 'name' and a 'result' of 'pass' or "
                f"'fail': {source}"
            )
        if result == "pass":
            continue
        classification = check.get("classification")
        if classification not in {"task", "baseline", "not-applicable"}:
            raise EngineError(
                f"QA evidence check '{name}' for task {task['id']} failed and must set 'classification' to "
                f"'task' (caused by this task's change), 'baseline' (pre-existing, unrelated failure), or "
                f"'not-applicable' (check does not apply to this task): {source}"
            )
        if classification == "task":
            raise EngineError(
                f"QA evidence check '{name}' for task {task['id']} is classified as a task-caused failure; "
                f"the task cannot qa-pass until it is fixed or the classification is corrected: {source}"
            )
        if classification == "not-applicable" and not str(check.get("note") or "").strip():
            raise EngineError(
                f"QA evidence check '{name}' for task {task['id']} is classified as not-applicable and "
                f"requires a 'note' explaining why: {source}"
            )
        if classification == "baseline":
            # This is the crux of the gate: a pre-existing baseline failure
            # is never auto-accepted just because the task's own executor
            # (or QA acting alone) says so. A distinct reviewer must
            # separately confirm it, structurally recorded, not merely
            # implied by the evidence's overall 'pass' status.
            confirmation = check.get("reviewer_confirmation")
            if (
                not isinstance(confirmation, dict)
                or not str(confirmation.get("actor") or "").strip()
                or not str(confirmation.get("note") or "").strip()
            ):
                raise EngineError(
                    f"QA evidence check '{name}' for task {task['id']} is classified as a baseline failure "
                    f"and requires a separate reviewer_confirmation object with a non-empty 'actor' and "
                    f"'note' -- a baseline failure is never automatically treated as a pass: {source}"
                )


def event(state: dict, path: Path, action: str, task: dict | None, actor: str, old: str | None, new: str | None, detail: str) -> dict:
    item = {"ts": now(), "action": action, "task": task["id"] if task else None, "actor": actor, "from": old, "to": new, "detail": detail}
    state["events"].append(item)
    event_log = workspace(path) / "logs" / "events.jsonl"
    event_log.parent.mkdir(parents=True, exist_ok=True)
    with event_log.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item) + "\n")
    return item


def _visualizer_manifest() -> dict:
    """The one file a consumer checks for compatibility before parsing any
    other .visualizer/*.json payload -- see VISUALIZER_ARTIFACT_VERSIONS."""
    manifest = {
        "schema_version": VISUALIZER_MANIFEST_SCHEMA_VERSION,
        "generated_at": now(),
        "artifacts": dict(VISUALIZER_ARTIFACT_VERSIONS),
    }
    _validate_visualizer_manifest(manifest)
    return manifest


def _validate_visualizer_manifest(manifest: dict) -> None:
    if not isinstance(manifest.get("schema_version"), int):
        raise EngineError("visualizer manifest: schema_version must be an int")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        raise EngineError("visualizer manifest: artifacts must be a non-empty object")
    for filename, version in artifacts.items():
        if not isinstance(filename, str) or not filename.endswith(".json"):
            raise EngineError(f"visualizer manifest: invalid artifact filename {filename!r}")
        if not isinstance(version, int):
            raise EngineError(f"visualizer manifest: artifact version for {filename!r} must be an int")


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
            "discovered-architecture.json": _discovered_architecture_with_tasks(None),
            "artifacts.json": _visualizer_manifest(),
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
        entry = _board_entry(task, state_path_value)
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
        "discovered-architecture.json": _discovered_architecture_with_tasks(state),
        "artifacts.json": _visualizer_manifest(),
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


def _task_contract_dict(task: dict, revision: int, created_at: str, updated_at: str) -> dict:
    """Build the definitional snapshot for a task's contract file.

    Deliberately scoped to the fields a runner needs to know WHAT the task
    is (title, ownership, dependencies, acceptance) -- not lifecycle state
    (status, attempts, claimed_by, evidence), which stays exclusively in
    workflow.json. See AGENTS.md's Task Contract model / state-schema.md's
    "Task contract files" section for the ownership split.
    """
    return {
        "schema_version": TASK_CONTRACT_SCHEMA_VERSION,
        "task_id": task["id"],
        "revision": revision,
        "title": task["title"],
        "owner": task["owner"],
        "phase": task["phase"],
        "needs": task["needs"],
        "depends_on": task.get("depends_on", []),
        "acceptance": task["acceptance"],
        "files": task["files"],
        "tags": task.get("tags", []),
        "context": task.get("context"),
        "epic": task.get("epic"),
        "base_commit": task.get("base_commit"),
        "created_at": created_at,
        "updated_at": updated_at,
    }


def _task_contract_payload(contract: dict) -> bytes:
    return (json.dumps(contract, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _build_task_contract(task: dict, revision: int, created_at: str, updated_at: str | None = None) -> tuple[bytes, str]:
    """Build a contract's on-disk bytes and content hash without writing anything.

    Split from the write step so a caller can compute the hash to store in
    workflow.json's task record *before* committing to that state -- and
    write both in a way where the recorded hash always matches exactly what
    lands on disk, since both come from this one serialization.
    """
    contract = _task_contract_dict(task, revision, created_at, updated_at or created_at)
    payload = _task_contract_payload(contract)
    return payload, hashlib.sha256(payload).hexdigest()


def _write_contract_payload(payload: bytes, task_id: str, state_file: Path) -> Path:
    contract_path = workspace(state_file) / "tasks" / f"{task_id}.json"
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = contract_path.with_suffix(contract_path.suffix + ".tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, contract_path)
    return contract_path


def _existing_contract_created_at(task_id: str, state_file: Path) -> str | None:
    """Read the original created_at off an existing contract file, if any.

    update-task needs this so bumping a contract's revision preserves its
    original creation timestamp instead of resetting it on every edit; a
    missing or unreadable file (task predates contract tracking, or was
    deleted) is not an error here -- the caller treats it as "no prior
    contract" and stamps a fresh created_at.
    """
    contract_path = workspace(state_file) / "tasks" / f"{task_id}.json"
    if not contract_path.exists():
        return None
    try:
        return json.loads(contract_path.read_text(encoding="utf-8")).get("created_at")
    except (json.JSONDecodeError, OSError):
        return None


def _resolve_task_definition(task_id: str, state: dict, state_file: Path) -> dict:
    """Return the task dict routing/dispatch/pipeline should read.

    Prefers the contract file's (.ai-work/tasks/<id>.json) definitional
    fields -- title, owner, phase, needs, depends_on, acceptance, files,
    tags, context, epic, base_commit -- over workflow.json's copy of the
    same fields when a contract exists, per state-schema.md's Task contract
    files split. Lifecycle fields (status, attempts, claimed_by, evidence,
    blocked_reason) always come from workflow.json regardless, since the
    contract file never carries them. Falls back to the workflow.json task
    unchanged when no contract file exists yet, so this cannot break tasks
    created before contract files existed (see the migration gap noted in
    state-schema.md).
    """
    task = task_map(state).get(task_id)
    if not task:
        raise EngineError(f"unknown task: {task_id}")
    contract_path = workspace(state_file) / "tasks" / f"{task_id}.json"
    if not contract_path.exists():
        return task
    try:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EngineError(f"invalid task contract JSON: {display_path(contract_path)}: {exc}") from exc
    merged = dict(task)
    for field in ("title", "owner", "phase", "needs", "depends_on", "acceptance", "files", "tags", "context", "epic", "base_commit"):
        if field in contract:
            merged[field] = contract[field]
    return merged


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
    task = {"id": args.id, "title": args.title, "owner": args.owner, "phase": args.phase, "needs": args.needs or [], "status": "todo", "acceptance": acceptance, "files": args.files or [], "tags": args.tags or [], "attempts": 0, "evidence": [], "blocked_reason": None, "claimed_by": None, "context": context, "epic": epic, "base_commit": _git_head(), "context_revision": context_revision, "epic_revision": _epic_revision(epic), "upstream_context_revisions": _upstream_context_revisions(context), "depends_on": depends_on, "contract_hashes": _contract_hashes(depends_on), "contract_revision": None, "contract_hash": None}
    timestamp = now()
    contract_payload, contract_hash = _build_task_contract(task, 1, timestamp)
    task["contract_revision"] = 1
    task["contract_hash"] = contract_hash
    state["tasks"].append(task)
    validate(state)
    sync_phases(state)
    sync_tasks_md(state, path)
    event(state, path, "add-task", task, args.actor, None, "todo", "task added")
    save(state, path, state["revision"])
    _write_contract_payload(contract_payload, task["id"], path)
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
    # Contract fields (acceptance/files/tags) just changed, so the contract
    # file is stale the instant this returns unless it's rewritten here too
    # -- bump its revision, preserve its original created_at, and record the
    # new hash in workflow.json so drift/board can detect a hand-edited or
    # otherwise out-of-sync contract file later (see _task_contract_drift).
    next_revision = (task.get("contract_revision") or 0) + 1
    created_at = _existing_contract_created_at(task["id"], path) or now()
    contract_payload, contract_hash = _build_task_contract(task, next_revision, created_at, now())
    task["contract_revision"] = next_revision
    task["contract_hash"] = contract_hash
    sync_phases(state)
    sync_tasks_md(state, path)
    event(state, path, "update-task", task, args.actor, task["status"], task["status"], " | ".join(detail_parts))
    save(state, path, state["revision"])
    _write_contract_payload(contract_payload, task["id"], path)
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
    if args.action == "reclaim":
        if not _lease_is_expired(task.get("claim_expires_at")):
            raise EngineError(f"task {args.id} is still leased to {task.get('claimed_by')}; reclaim only after expiry")
        if not getattr(args, "agent_id", None):
            raise EngineError("reclaim requires --agent-id")
    if args.action == "start" and _load_rules().get("file_conflict_check", True):
        conflicts = _file_conflicts(task, state)
        if conflicts:
            described = "; ".join(f"{c['task']} ({c['status']}, files: {', '.join(c['files'])})" for c in conflicts)
            raise EngineError(
                f"G7 file_conflict_check: task {task['id']} shares files with active task(s) not "
                f"reachable via needs in either direction: {described}. Declare a needs dependency "
                f"between them, wait for the other task to finish, or set 'file_conflict_check: false' "
                f"in .ai-config/rules.yaml to disable this gate"
            )
    if args.action in {"block", "reject", "supersede", "cancel"} and not args.detail:
        raise EngineError(f"{args.action} requires --detail")
    if args.action == "supersede":
        by_id_arg = getattr(args, "by", None)
        if not by_id_arg:
            raise EngineError("supersede requires --by <replacing-task-id>")
        if by_id_arg not in task_map(state):
            raise EngineError(f"supersede --by references unknown task: {by_id_arg}")
        if by_id_arg == task["id"]:
            raise EngineError(f"task {task['id']} cannot be superseded by itself")
    if args.action in {"qa-pass", "review-approve", "reject"}:
        # P0-4: Executor must not QA/review/reject their own work. claimed_by may
        # carry a per-agent-instance suffix ("role#agent_id"); compare on the role
        # alone so this still blocks self-review when multiple agents share a role.
        claimed_role = task["claimed_by"].split("#", 1)[0] if task.get("claimed_by") else None
        if claimed_role and args.actor == claimed_role:
            raise EngineError(f"{args.action} actor '{args.actor}' must differ from executor '{task['claimed_by']}'")
    if args.action in {"complete", "block"} and task.get("claim_id"):
        claim_id = getattr(args, "claim_id", None)
        agent_id = getattr(args, "agent_id", None)
        expected_agent = (task.get("claimed_by") or "").partition("#")[2]
        if claim_id != task["claim_id"] or not agent_id or agent_id != expected_agent:
            raise EngineError(
                f"{args.action} requires the active --claim-id and --agent-id for task {args.id}; "
                "use reclaim after the lease expires"
            )
    if args.action in {"qa-pass", "review-approve"}:
        if not args.evidence:
            raise EngineError(f"{args.action} requires at least one --evidence path")
        validate_evidence(task, args.action, args.evidence)
    old = task["status"]; task["status"] = target
    if args.action in {"block", "reject", "supersede", "cancel"}:
        task["blocked_reason"] = args.detail
    elif args.action in {"start", "reclaim", "unblock"}:
        task["blocked_reason"] = None
    if args.action == "supersede":
        task["superseded_by"] = getattr(args, "by", None)
    if args.evidence:
        task["evidence"].extend(args.evidence)
    if args.action in {"start", "reclaim"}:
        task["attempts"] += 1
        agent_id = getattr(args, "agent_id", None)
        # Explicit agent dispatches receive an enforceable lease. Preserve the
        # pre-v4 manual CLI path for existing operators/tests that intentionally
        # start work without an agent instance; dispatch always supplies one.
        if agent_id:
            task["claimed_by"] = f"{args.actor}#{agent_id}"
            task["claim_id"] = uuid.uuid4().hex
            task["claim_expires_at"] = _lease_expiry()
        else:
            task["claimed_by"] = args.actor
            task["claim_id"] = None
            task["claim_expires_at"] = None
    sync_phases(state)
    sync_tasks_md(state, path)
    event(state, path, args.action, task, args.actor, old, target, args.detail or "")
    requested_revision = getattr(args, "expected_revision", None)
    expected = requested_revision if requested_revision is not None else state["revision"]
    save(state, path, expected)
    _auto_generate_visualizer_data(path)
    if args.action == "complete" and _post_completion_enabled():
        # Opt-in only (.ai-config/automation.yaml: post_completion.enabled):
        # chain verify -> independent QA -> independent review -> close so a
        # caller never has to remember to run `ai-kit pipeline` by hand. Best
        # effort: failures are recorded as events, not raised, because the
        # `complete` transition the caller asked for already succeeded above.
        try:
            _run_post_completion(task["id"], args.state, agent_id=getattr(args, "agent_id", None))
        except EngineError as exc:
            state = load(path)
            failed_task = task_map(state).get(task["id"])
            event(state, path, "post-completion-failed", failed_task, "system", None, None, f"unexpected error: {exc}")
            save(state, path, state["revision"])
        state = load(path)
        task = task_map(state).get(task["id"])
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
    plan_task = {"id": "T1", "title": "Confirm scope and plan: " + args.idea, "owner": "planner", "phase": "plan", "needs": [], "status": "todo", "acceptance": ["Scope, exclusions, risks, and acceptance criteria confirmed"], "files": [".ai-work/roadmap/roadmap.md", ".ai-work/plan/plan.md", ".ai-work/tasks/tasks.md"], "tags": ["planning"], "attempts": 0, "evidence": [], "blocked_reason": None, "claimed_by": None, "base_commit": base_commit, "context_revision": None, "epic_revision": None, "depends_on": [], "contract_hashes": {}, "contract_revision": None, "contract_hash": None}
    build_task = {"id": "T2", "title": args.idea, "owner": args.owner, "phase": args.phase, "needs": ["T1"], "status": "todo", "acceptance": acceptance, "files": args.files or [], "tags": args.tags or [], "attempts": 0, "evidence": [], "blocked_reason": None, "claimed_by": None, "context": context, "epic": epic, "base_commit": base_commit, "context_revision": _context_revision(context), "epic_revision": _epic_revision(epic), "upstream_context_revisions": _upstream_context_revisions(context), "depends_on": depends_on, "contract_hashes": contract_hashes, "contract_revision": None, "contract_hash": None}
    timestamp = now()
    plan_payload, plan_hash = _build_task_contract(plan_task, 1, timestamp)
    plan_task["contract_revision"] = 1
    plan_task["contract_hash"] = plan_hash
    build_payload, build_hash = _build_task_contract(build_task, 1, timestamp)
    build_task["contract_revision"] = 1
    build_task["contract_hash"] = build_hash
    state["tasks"] = [plan_task, build_task]; validate(state); sync_phases(state)
    root = workspace(path)
    root.joinpath("roadmap").mkdir(parents=True, exist_ok=True); root.joinpath("plan").mkdir(parents=True, exist_ok=True); root.joinpath("tasks").mkdir(parents=True, exist_ok=True)
    root.joinpath("roadmap/roadmap.md").write_text(f"# Roadmap\n\nGoal: {args.idea}\n\n1. Confirm scope, risks, and acceptance criteria.\n2. Implement in phase `{args.phase}` and verify evidence.\n", encoding="utf-8")
    root.joinpath("plan/plan.md").write_text(f"# Plan\n\nGoal: {args.idea}\n\nScope: {args.scope or 'pending Planner confirmation'}\nOut of scope: {args.out_of_scope or 'none recorded'}\nRisks: {', '.join(args.risks or ['none recorded'])}\nAssumptions: {args.assumptions or 'none recorded'}\nTags: {', '.join(args.tags or ['none'])}\n\nImplementation owner: {args.owner}\n", encoding="utf-8")
    sync_tasks_md(state, path)
    event(state, path, "plan", None, args.actor, None, None, "idea converted to draft plan")
    save(state, path)
    _write_contract_payload(plan_payload, "T1", path)
    _write_contract_payload(build_payload, "T2", path)
    _auto_generate_visualizer_data(path)
    return {"state": display_path(path), "workspace": display_path(root), "tasks": ["T1", "T2"], "assumptions": args.assumptions or "none recorded"}


def _plan_draft_path(plan_id: str) -> Path:
    """Return a safe, deterministic location for a collaborative plan draft."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", plan_id):
        raise EngineError("plan draft id must contain only letters, digits, '.', '_' or '-' and cannot start with punctuation")
    # The override keeps subprocess tests fully isolated from the repository's
    # disposable .ai-work state. Production callers use the default path.
    root = Path(os.environ["AI_KIT_PLAN_DRAFT_DIR"]).resolve() if os.environ.get("AI_KIT_PLAN_DRAFT_DIR") else WORK / "requirements" / "plans"
    return root / f"{plan_id}.json"


def _draft_event(draft: dict, action: str, actor: str, detail: str) -> None:
    draft.setdefault("history", []).append({"ts": now(), "action": action, "actor": actor, "detail": detail})


def _validate_plan_draft_shape(draft: dict, path: Path) -> None:
    required = {"schema_version", "id", "title", "workflow", "status", "revision", "brief", "tasks", "history", "materialization"}
    missing = required - set(draft)
    if missing:
        raise EngineError(f"plan draft {display_path(path)} missing keys: {', '.join(sorted(missing))}")
    if draft["schema_version"] != PLAN_DRAFT_SCHEMA_VERSION:
        raise EngineError(
            f"plan draft {display_path(path)} uses unsupported schema_version {draft['schema_version']} "
            f"(expected {PLAN_DRAFT_SCHEMA_VERSION})"
        )
    if draft["status"] not in PLAN_DRAFT_STATUSES:
        raise EngineError(f"plan draft {draft['id']} has invalid status {draft['status']!r}")
    if draft["workflow"] not in workflow_names():
        raise EngineError(f"plan draft {draft['id']} has unknown workflow {draft['workflow']!r}")
    if not isinstance(draft["brief"], dict) or not isinstance(draft["tasks"], list) or not isinstance(draft["history"], list):
        raise EngineError(f"plan draft {draft['id']} has invalid brief, tasks, or history shape")


def _load_plan_draft(plan_id: str) -> tuple[Path, dict]:
    path = _plan_draft_path(plan_id)
    if not path.exists():
        raise EngineError(f"plan draft not found: {display_path(path)}; run 'plan-draft create {plan_id}' first")
    draft = load(path)
    _validate_plan_draft_shape(draft, path)
    return path, draft


def _write_plan_draft_markdown(draft: dict) -> Path:
    """Write the human-facing projection; JSON remains the authoritative draft."""
    path = _plan_draft_path(draft["id"]).with_suffix(".md")
    brief = draft["brief"]
    lines = [
        f"# Plan draft: {draft['title']}",
        "",
        f"- ID: `{draft['id']}`",
        f"- Revision: {draft['revision']}",
        f"- Status: {draft['status']}",
        f"- Workflow: {draft['workflow']}",
        "",
        "## Problem",
        "",
        brief.get("problem") or "Not recorded.",
        "",
        "## Scope",
        "",
    ]
    for key, heading in (("scope", "Scope"), ("out_of_scope", "Out of scope"), ("acceptance", "Acceptance criteria"), ("assumptions", "Assumptions"), ("open_questions", "Open questions")):
        if key != "scope":
            lines.extend([f"## {heading}", ""])
        values = brief.get(key) or []
        lines.extend([f"- {value}" for value in values] or ["- None recorded."])
        lines.append("")
    lines.extend(["## Proposed tasks", ""])
    for task in draft["tasks"]:
        needs = f"; needs: {', '.join(task['needs'])}" if task.get("needs") else ""
        lines.append(f"- `{task['id']}` — {task['title']} (owner: {task['owner']}; phase: {task['phase']}{needs})")
        lines.extend([f"  - Accept: {criterion}" for criterion in task.get("acceptance", [])])
    if not draft["tasks"]:
        lines.append("- No tasks proposed yet.")
    lines.append("")
    if draft.get("materialization"):
        materialization = draft["materialization"]
        lines.extend(["## Materialization", "", f"- State: `{materialization['state']}`", f"- Source revision: {materialization['source_revision']}", ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".md.tmp")
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return path


def _save_plan_draft(draft: dict, path: Path, expected_revision: int | None) -> None:
    draft["updated_at"] = now()
    save(draft, path, expected_revision)
    _write_plan_draft_markdown(draft)


def _assert_draft_editable(draft: dict) -> None:
    if draft["status"] != "drafting":
        raise EngineError(
            f"plan draft {draft['id']} is {draft['status']}; reopen it before changing the proposed plan"
        )


def _draft_task_index(draft: dict) -> dict[str, dict]:
    for task in draft["tasks"]:
        task_id = task.get("id")
        if not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", task_id):
            raise EngineError(f"plan draft {draft['id']} has unsafe proposed task id {task_id!r}")
    tasks = {task.get("id"): task for task in draft["tasks"]}
    if None in tasks or len(tasks) != len(draft["tasks"]):
        raise EngineError(f"plan draft {draft['id']} has duplicate or missing proposed task ids")
    return tasks


def _draft_task_from_args(args: argparse.Namespace) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", args.task_id):
        raise EngineError("plan draft task id must contain only letters, digits, '.', '_' or '-' and cannot start with punctuation")
    acceptance = _flatten_repeated(args.acceptance)
    if not acceptance:
        raise EngineError("plan-draft add-task requires at least one --acceptance criterion")
    return {
        "id": args.task_id,
        "title": args.title,
        "owner": args.owner,
        "phase": args.phase,
        "needs": args.needs or [],
        "acceptance": acceptance,
        "files": args.files or [],
        "tags": args.tags or [],
        "context": args.context,
        "epic": args.epic,
        "depends_on": args.depends_on or [],
    }


def _draft_to_runtime_task(task: dict, base_commit: str | None) -> tuple[dict, bytes]:
    context = task.get("context")
    depends_on = task.get("depends_on") or []
    runtime = {
        "id": task["id"], "title": task["title"], "owner": task["owner"], "phase": task["phase"],
        "needs": task.get("needs") or [], "status": "todo", "acceptance": task["acceptance"],
        "files": task.get("files") or [], "tags": task.get("tags") or [], "attempts": 0,
        "evidence": [], "blocked_reason": None, "claimed_by": None, "context": context,
        "epic": task.get("epic"), "base_commit": base_commit,
        "context_revision": _context_revision(context), "epic_revision": _epic_revision(task.get("epic")),
        "upstream_context_revisions": _upstream_context_revisions(context), "depends_on": depends_on,
        "contract_hashes": _contract_hashes(depends_on), "contract_revision": None, "contract_hash": None,
        "superseded_by": None,
    }
    payload, contract_hash = _build_task_contract(runtime, 1, now())
    runtime["contract_revision"] = 1
    runtime["contract_hash"] = contract_hash
    return runtime, payload


def _validate_draft_ready(draft: dict) -> None:
    brief = draft["brief"]
    errors = []
    if not str(draft.get("title") or "").strip():
        errors.append("title is required")
    if not str(brief.get("problem") or "").strip():
        errors.append("brief.problem is required")
    if not brief.get("scope"):
        errors.append("brief.scope needs at least one item")
    if not brief.get("acceptance"):
        errors.append("brief.acceptance needs at least one criterion")
    if brief.get("open_questions"):
        errors.append("all open questions must be resolved before finalizing")
    if not draft["tasks"]:
        errors.append("at least one proposed task is required")
    try:
        tasks = _draft_task_index(draft)
    except EngineError as exc:
        errors.append(str(exc))
        tasks = {}
    contexts = _load_contexts()
    for task_id, task in tasks.items():
        for key in ("title", "owner", "phase", "acceptance", "needs", "files", "tags", "depends_on"):
            if key not in task:
                errors.append(f"task {task_id} missing {key}")
        if task.get("owner") not in role_names():
            errors.append(f"task {task_id} has unknown owner {task.get('owner')!r}")
        if not str(task.get("title") or "").strip() or not str(task.get("phase") or "").strip():
            errors.append(f"task {task_id} needs title and phase")
        if not task.get("acceptance"):
            errors.append(f"task {task_id} needs acceptance criteria")
        unknown_needs = set(task.get("needs") or []) - set(tasks)
        if unknown_needs:
            errors.append(f"task {task_id} has unknown dependencies: {', '.join(sorted(unknown_needs))}")
        if task_id in (task.get("needs") or []):
            errors.append(f"task {task_id} cannot depend on itself")
        if task.get("context") and task["context"] not in contexts:
            errors.append(f"task {task_id} has unregistered context {task['context']!r}")
    if not errors:
        candidate = new_state(draft["title"], draft["workflow"])
        try:
            candidate["tasks"] = [_draft_to_runtime_task(task, None)[0] for task in draft["tasks"]]
            validate(candidate)
        except EngineError as exc:
            errors.append(str(exc))
    if errors:
        raise EngineError("plan draft is not ready: " + "; ".join(errors))


def _draft_digest(draft: dict) -> str:
    """Digest the plan definition, excluding mutable audit/materialization metadata."""
    definition = {
        "schema_version": draft["schema_version"], "id": draft["id"], "title": draft["title"],
        "workflow": draft["workflow"], "brief": draft["brief"], "tasks": draft["tasks"],
    }
    encoded = json.dumps(definition, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _matching_materialized_state(path: Path, draft: dict) -> bool:
    if not path.exists():
        return False
    try:
        state = load(path)
        validate(state)
    except EngineError:
        return False
    source = state.get("source_plan") or {}
    materialization = draft.get("materialization") or {}
    expected_ids = [task["id"] for task in draft["tasks"]]
    return (
        source.get("id") == draft["id"]
        and source.get("revision") == materialization.get("source_revision")
        and source.get("digest") == materialization.get("digest")
        and [task["id"] for task in state["tasks"]] == expected_ids
    )


def cmd_plan_draft_create(args: argparse.Namespace) -> dict:
    path = _plan_draft_path(args.id)
    if path.exists():
        raise EngineError(f"plan draft already exists: {display_path(path)}")
    if args.workflow not in workflow_names():
        raise EngineError(f"unknown workflow: {args.workflow}")
    draft = {
        "schema_version": PLAN_DRAFT_SCHEMA_VERSION, "id": args.id, "title": args.title,
        "workflow": args.workflow, "status": "drafting", "revision": 0, "created_at": now(),
        "updated_at": now(),
        "brief": {
            "problem": args.problem, "scope": args.scope or [], "out_of_scope": args.out_of_scope or [],
            "acceptance": _flatten_repeated(args.acceptance), "assumptions": args.assumption or [],
            "open_questions": args.open_question or [],
        },
        "tasks": [], "history": [], "materialization": None,
    }
    _draft_event(draft, "create", args.actor, "draft created from conversation")
    _save_plan_draft(draft, path, -1)
    return {"draft": display_path(path), "markdown": display_path(path.with_suffix('.md')), "revision": draft["revision"], "status": draft["status"]}


def cmd_plan_draft_update(args: argparse.Namespace) -> dict:
    path, draft = _load_plan_draft(args.id)
    _assert_draft_editable(draft)
    if args.expected_revision != draft["revision"]:
        raise EngineError(f"stale plan draft revision: expected {args.expected_revision}, found {draft['revision']}")
    brief = draft["brief"]
    changes = []
    if args.title:
        draft["title"] = args.title; changes.append("title")
    if args.problem:
        brief["problem"] = args.problem; changes.append("problem")
    for key, value in (("scope", args.set_scope), ("out_of_scope", args.set_out_of_scope), ("acceptance", _flatten_repeated(args.set_acceptance))):
        if value is not None and (key != "acceptance" or args.set_acceptance is not None):
            brief[key] = value; changes.append(key)
    for key, values in (("scope", args.add_scope), ("out_of_scope", args.add_out_of_scope), ("acceptance", _flatten_repeated(args.add_acceptance)), ("assumptions", args.add_assumption), ("open_questions", args.add_open_question)):
        if values:
            brief[key].extend(value for value in values if value not in brief[key]); changes.append(f"add {key}")
    for question in args.resolve_open_question or []:
        if question not in brief["open_questions"]:
            raise EngineError(f"open question not found: {question}")
        brief["open_questions"].remove(question); changes.append("resolve open question")
    if not changes:
        raise EngineError("plan-draft update requires at least one field change")
    _draft_event(draft, "update", args.actor, args.summary)
    _save_plan_draft(draft, path, args.expected_revision)
    return {"draft": draft["id"], "revision": draft["revision"], "changed": changes, "summary": args.summary}


def cmd_plan_draft_add_task(args: argparse.Namespace) -> dict:
    path, draft = _load_plan_draft(args.id)
    _assert_draft_editable(draft)
    if args.expected_revision != draft["revision"]:
        raise EngineError(f"stale plan draft revision: expected {args.expected_revision}, found {draft['revision']}")
    tasks = _draft_task_index(draft)
    if args.task_id in tasks:
        raise EngineError(f"plan draft task already exists: {args.task_id}; use plan-draft update-task")
    task = _draft_task_from_args(args)
    draft["tasks"].append(task)
    _draft_event(draft, "add-task", args.actor, f"proposed task {args.task_id} added")
    _save_plan_draft(draft, path, args.expected_revision)
    return {"draft": draft["id"], "revision": draft["revision"], "task": task}


def cmd_plan_draft_update_task(args: argparse.Namespace) -> dict:
    path, draft = _load_plan_draft(args.id)
    _assert_draft_editable(draft)
    if args.expected_revision != draft["revision"]:
        raise EngineError(f"stale plan draft revision: expected {args.expected_revision}, found {draft['revision']}")
    task = _draft_task_index(draft).get(args.task_id)
    if not task:
        raise EngineError(f"unknown plan draft task: {args.task_id}")
    changes = []
    for field in ("title", "owner", "phase", "context", "epic"):
        value = getattr(args, field)
        if value is not None:
            task[field] = value; changes.append(field)
    for field, value in (("needs", args.set_needs), ("acceptance", _flatten_repeated(args.set_acceptance)), ("files", args.set_files), ("tags", args.set_tags), ("depends_on", args.set_depends_on)):
        if value is not None and (field != "acceptance" or args.set_acceptance is not None):
            task[field] = value; changes.append(field)
    if not changes:
        raise EngineError("plan-draft update-task requires at least one field change")
    _draft_event(draft, "update-task", args.actor, args.summary)
    _save_plan_draft(draft, path, args.expected_revision)
    return {"draft": draft["id"], "revision": draft["revision"], "task": task, "changed": changes}


def cmd_plan_draft_finalize(args: argparse.Namespace) -> dict:
    path, draft = _load_plan_draft(args.id)
    _assert_draft_editable(draft)
    if args.expected_revision != draft["revision"]:
        raise EngineError(f"stale plan draft revision: expected {args.expected_revision}, found {draft['revision']}")
    if not args.confirmed_by_user:
        raise EngineError("plan-draft finalize requires --confirmed-by-user after the Planner presents the plan and receives explicit user approval")
    _validate_draft_ready(draft)
    draft["status"] = "ready"
    _draft_event(draft, "finalize", args.actor, "user-approved draft is ready; Planner must now ask whether to create tasks")
    _save_plan_draft(draft, path, args.expected_revision)
    return {"draft": draft["id"], "revision": draft["revision"], "status": draft["status"], "tasks": [task["id"] for task in draft["tasks"]]}


def cmd_plan_draft_reopen(args: argparse.Namespace) -> dict:
    path, draft = _load_plan_draft(args.id)
    if draft["status"] != "ready":
        raise EngineError(f"only a ready plan draft can be reopened (current status: {draft['status']})")
    if args.expected_revision != draft["revision"]:
        raise EngineError(f"stale plan draft revision: expected {args.expected_revision}, found {draft['revision']}")
    draft["status"] = "drafting"
    _draft_event(draft, "reopen", args.actor, args.reason)
    _save_plan_draft(draft, path, args.expected_revision)
    return {"draft": draft["id"], "revision": draft["revision"], "status": draft["status"]}


def cmd_plan_draft_materialize(args: argparse.Namespace) -> dict:
    draft_path, draft = _load_plan_draft(args.id)
    state_file = state_path(args.state)
    if not args.create_tasks:
        raise EngineError("plan-draft materialize requires --create-tasks after the Planner receives a separate explicit user request to create the task DAG")
    if draft["status"] == "materialized":
        if _matching_materialized_state(state_file, draft):
            return {"draft": draft["id"], "status": "materialized", "state": display_path(state_file), "tasks": [task["id"] for task in draft["tasks"]], "idempotent": True}
        raise EngineError("materialized plan draft does not match the requested workflow state; inspect its materialization record")
    if draft["status"] != "ready":
        raise EngineError("plan draft must be finalized (status ready) before materialization")
    _validate_draft_ready(draft)
    source_revision = draft["revision"]
    digest = _draft_digest(draft)
    if state_file.exists():
        # Recovery after the workflow file was atomically written but the
        # process stopped before the draft could be marked materialized.
        existing = load(state_file)
        validate(existing)
        source = existing.get("source_plan") or {}
        if source == {"id": draft["id"], "revision": source_revision, "digest": digest, "draft": display_path(draft_path)}:
            draft["status"] = "materialized"
            draft["materialization"] = {"state": display_path(state_file), "source_revision": source_revision, "digest": digest}
            _draft_event(draft, "materialize-recovery", args.actor, "recovered existing matching workflow state")
            _save_plan_draft(draft, draft_path, source_revision)
            return {"draft": draft["id"], "status": "materialized", "state": display_path(state_file), "tasks": [task["id"] for task in draft["tasks"]], "recovered": True}
        raise EngineError(f"workflow state already exists: {display_path(state_file)}; materialization never overwrites a workflow")
    state = new_state(draft["title"], draft["workflow"])
    state["source_plan"] = {"id": draft["id"], "revision": source_revision, "digest": digest, "draft": display_path(draft_path)}
    base_commit = _git_head()
    contracts = []
    for task in draft["tasks"]:
        runtime, payload = _draft_to_runtime_task(task, base_commit)
        state["tasks"].append(runtime)
        contracts.append((runtime["id"], payload))
    validate(state)
    sync_phases(state)
    materialization_event = {
        "ts": now(), "action": "materialize-plan-draft", "task": None, "actor": args.actor,
        "from": None, "to": None, "detail": f"materialized {draft['id']} revision {source_revision}",
    }
    state["events"].append(materialization_event)
    # Create-only save gives the DAG one atomic control-plane commit and
    # refuses a concurrent writer instead of replacing its workflow.
    save(state, state_file, -1)
    # These are derived artifacts.  They are intentionally written only after
    # the create-only workflow save succeeds, so a racing workflow cannot have
    # its own workspace artifacts touched by this materialization attempt.
    sync_tasks_md(state, state_file)
    event_log = workspace(state_file) / "logs" / "events.jsonl"
    event_log.parent.mkdir(parents=True, exist_ok=True)
    with event_log.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(materialization_event) + "\n")
    for task_id, payload in contracts:
        _write_contract_payload(payload, task_id, state_file)
    _auto_generate_visualizer_data(state_file)
    draft["status"] = "materialized"
    draft["materialization"] = {"state": display_path(state_file), "source_revision": source_revision, "digest": digest}
    _draft_event(draft, "materialize", args.actor, f"created workflow {display_path(state_file)}")
    _save_plan_draft(draft, draft_path, source_revision)
    return {"draft": draft["id"], "status": "materialized", "state": display_path(state_file), "tasks": [task["id"] for task in draft["tasks"]], "idempotent": False}


def cmd_plan_draft_show(args: argparse.Namespace) -> dict:
    _path, draft = _load_plan_draft(args.id)
    return draft


def cmd_route(args: argparse.Namespace) -> dict:
    state_file = state_path(args.state)
    state = load(state_file); validate(state)
    task = _resolve_task_definition(args.id, state, state_file)
    # A route always carries the current project snapshot. On a cache hit this
    # performs only the bounded fingerprint check, not repository discovery.
    project_context, project_context_cache = _load_or_refresh_project_context(state_file)
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

    stack_skills = _load_stack_skills()
    for skill_dir in domain_candidates:
        skill_name = skill_dir.name.lower()
        domain_name = skill_dir.parent.name.lower()
        # A skill is in scope when the task's tokens name the skill directly,
        # name its domain, or match one of the stack tags registry.yaml's
        # stack_skills declares for it (e.g. `docker`/`compose` selecting
        # docker-compose-local, whose directory name is neither).
        declared_tags = stack_skills.get(skill_dir.relative_to(ROOT).as_posix(), [])
        matched_tags = [tag for tag in declared_tags if tag in tokens]
        if skill_name in tokens:
            add_technology(skill_dir, f"task-skill:{skill_name}", "role-technology")
        elif matched_tags:
            add_technology(skill_dir, f"stack:{','.join(sorted(matched_tags))}", "role-technology")

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
    root = workspace(state_file)
    snapshot_path = _project_context_snapshot_path(state_file)
    context_paths = [display_path(snapshot_path), display_path(root / "plan" / "plan.md"), display_path(root / "tasks" / "tasks.md"), ".ai/engine/state-schema.md", *task["files"]]
    response = {
        "task": task["id"],
        "owner": role,
        "tags": task["tags"],
        "role_contract": (Path(".ai") / "agents" / role).as_posix(),
        "skills": skills,
        "context": list(dict.fromkeys(context_paths)),
        "project_context": {
            "path": display_path(snapshot_path),
            "schema_version": project_context["schema_version"],
            "fingerprint": project_context["context_snapshot"]["fingerprint"],
            "cache_status": project_context_cache,
        },
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
    path = _writable_config_path("contexts.yaml")
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
    path = _writable_config_path("epics.yaml")
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
            edges.append({"from": dep, "to": task_id, "unlocked": by_id[dep]["status"] in DEPENDENCY_SATISFYING_STATUSES})

    return {
        "tasks": dag_tasks,
        "edges": edges,
        "waves": (max(layer_cache.values()) + 1) if layer_cache else 0,
        "ready": ready_ids,
        "critical_path": critical_path,
    }


def _task_contract_drift(task: dict, state_file: Path) -> str | None:
    """Detect whether a task's own contract file (.ai-work/tasks/<id>.json)
    still matches the hash workflow.json recorded for it.

    ``add-task``/``plan``/``update-task`` are the only writers of a contract
    file and always update workflow.json's ``contract_hash`` in the same
    write, so a mismatch here means the file was edited by hand (or
    otherwise changed) outside those commands -- this is the read-time
    detection half of "don't hand-edit a contract file" (state-schema.md);
    nothing blocks the edit itself, the same as ``contract_stale`` below
    never blocks on a stale depends-on file.

    Returns ``None`` when clean, including a task that predates contract
    tracking (no ``contract_hash`` recorded, nothing to compare against).
    Otherwise a short reason: ``"missing"`` (hash recorded but the file is
    gone), ``"unavailable"`` (exists but unreadable), or ``"hash_mismatch"``.
    """
    recorded_hash = task.get("contract_hash")
    if recorded_hash is None:
        return None
    contract_path = workspace(state_file) / "tasks" / f"{task['id']}.json"
    if not contract_path.exists():
        return "missing"
    try:
        current_hash = hashlib.sha256(contract_path.read_bytes()).hexdigest()
    except OSError:
        return "unavailable"
    return None if current_hash == recorded_hash else "hash_mismatch"


def _drift_flags(task: dict, state_file: Path) -> dict:
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
        "task_contract_drift": _task_contract_drift(task, state_file),
    }


def cmd_drift(args: argparse.Namespace) -> dict:
    """Report whether a task's plan-time base_commit/context_revision are stale.

    Informational only, never blocks a transition — blueprints and contracts
    change legitimately during development. Use this before dispatch/review
    to decide whether a task needs a re-plan.
    """
    import subprocess as _sp
    state_file = state_path(args.state)
    state = load(state_file); validate(state)
    task = task_map(state).get(args.id)
    if not task:
        raise EngineError(f"unknown task: {args.id}")
    report: dict = {"task": task["id"]}
    flags = _drift_flags(task, state_file)
    contract_stale = flags["contract_stale"]
    report["contract_stale"] = contract_stale
    report["drift_unavailable"] = flags["drift_unavailable"]
    report["upstream_context_stale"] = flags["upstream_context_stale"]
    report["task_contract_drift"] = flags["task_contract_drift"]

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


def cmd_backfill_contracts(args: argparse.Namespace) -> dict:
    """Materialize/repair .ai-work/tasks/<id>.json for tasks lacking one.

    Buckets each task by its `_task_contract_drift` status:
    - no `contract_hash` recorded yet (a pre-feature task, e.g. this repo's
      T1-T9): write a fresh revision-1 contract. This is the step-5
      migration referenced in state-schema.md's Task contract files
      section -- `update-task` already backfills a task's first contract as
      a side effect the next time it touches acceptance/files/tags; this
      covers tasks nothing ever calls `update-task` on before dispatch.
    - `contract_hash` recorded but the file is gone ("missing" drift):
      rewritten unconditionally -- there is nothing to protect, the file
      simply doesn't exist.
    - `contract_hash` recorded and the file exists but no longer matches
      ("hash_mismatch", i.e. hand-edited): left alone and reported under
      "protected" unless `--force`, since overwriting would silently
      discard that edit. "unavailable" (exists but unreadable) is treated
      the same way -- not ours to overwrite blind.
    - already matching: reported under "up_to_date", untouched.

    Idempotent and scoped to one task with `--id`, or every task in the
    state by default. A single `workflow.json` save covers every task
    touched in one call, rather than one save per task.
    """
    state_file = state_path(args.state)
    state = load(state_file); validate(state)
    only_id = getattr(args, "id", None)
    if only_id and only_id not in task_map(state):
        raise EngineError(f"unknown task: {only_id}")
    migrated, restored, regenerated, protected, up_to_date = [], [], [], [], []
    for task in state["tasks"]:
        if only_id and task["id"] != only_id:
            continue
        drift = _task_contract_drift(task, state_file)
        if task.get("contract_hash") is None:
            bucket = migrated
        elif drift == "missing":
            bucket = restored
        elif drift == "hash_mismatch" and args.force:
            bucket = regenerated
        elif drift in ("hash_mismatch", "unavailable"):
            protected.append(task["id"])
            continue
        else:
            up_to_date.append(task["id"])
            continue
        next_revision = (task.get("contract_revision") or 0) + 1
        created_at = _existing_contract_created_at(task["id"], state_file) or now()
        payload, digest = _build_task_contract(task, next_revision, created_at, now())
        task["contract_revision"] = next_revision
        task["contract_hash"] = digest
        _write_contract_payload(payload, task["id"], state_file)
        bucket.append(task["id"])
    touched = migrated + restored + regenerated
    if touched:
        event(
            state, state_file, "backfill-contracts", None, args.actor, None, None,
            f"migrated: {', '.join(migrated) or 'none'}; restored: {', '.join(restored) or 'none'}; "
            f"regenerated: {', '.join(regenerated) or 'none'}",
        )
        save(state, state_file, state["revision"])
        _auto_generate_visualizer_data(state_file)
    return {"migrated": migrated, "restored": restored, "regenerated": regenerated, "protected": protected, "up_to_date": up_to_date}


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


def cmd_activate(args: argparse.Namespace) -> dict:
    """Select one isolated workflow for tools that use the default state."""
    path = Path(args.workflow_state).resolve()
    state = load(path); validate(state)
    active = [task["id"] for task in state["tasks"] if task["status"] == "in-progress"]
    summary = {"version": 1, "workflow_state": display_path(path), "workflow_id": state["workflow_id"], "title": state["title"], "workflow": state["workflow"], "active_tasks": active, "updated_at": now()}
    CURRENT.parent.mkdir(parents=True, exist_ok=True)
    CURRENT.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


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
    # Status is an inspection command and must stay usable for a newly
    # initialized/minimal workspace that has not configured automation yet.
    # Dispatch/pipeline still validate this configuration when they need it.
    try:
        roles = _load_automation_roles()
    except EngineError:
        roles = {"qa": {"enabled": False}, "reviewer": {"enabled": False}}
    enabled = [role for role in ("qa", "reviewer") if roles[role]["enabled"]]
    mode = "autonomous" if len(enabled) == 2 else "assisted" if enabled else "manual"
    awaiting = []
    for task in scoped:
        if task["status"] == "implementation-complete" and not roles["qa"]["enabled"]:
            awaiting.append({"task": task["id"], "role": "qa", "status": "awaiting-manual-qa"})
        elif task["status"] == "qa-passed" and not roles["reviewer"]["enabled"]:
            awaiting.append({"task": task["id"], "role": "review", "status": "awaiting-manual-review"})
    role_config = {name: {"enabled": roles[name]["enabled"], "runner": roles[name].get("runner"), "model": roles[name].get("model")} for name in ("qa", "reviewer")}
    result = {"title": state["title"], "workflow_id": state["workflow_id"], "revision": state["revision"], "counts": counts, "phases": sync_phases(state) or state["phases"], "approval_mode": {"mode": mode, "roles": role_config, "enabled_roles": enabled, "awaiting": awaiting}}
    if context: result["context"] = context
    if epic: result["epic"] = epic
    return result


def _board_entry(task: dict, state_file: Path) -> dict:
    drift = _drift_flags(task, state_file)
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
    if drift["task_contract_drift"]:
        flags.append(f"task-contract-{drift['task_contract_drift'].replace('_', '-')}")
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
        board[task["status"]].append(_board_entry(task, state_path_value))
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


COMPOSE_FILENAMES = ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")

# Image name fragment -> the technology skill / stack tag it implies. Used to
# recognize a datastore declared as a Compose service.
DATASTORE_IMAGES = {
    "postgres": "postgresql",
    "postgis": "postgresql",
    "pgvector": "pgvector",
    "mysql": "mysql",
    "mariadb": "mysql",
    "redis": "redis",
    "qdrant": "qdrant",
}


def _detect_container_runtime() -> dict:
    """Detect whether this project runs its services -- notably its database --
    in containers, by reading the repo rather than asking.

    Whether the database is a Compose service or a host process decides where
    a migration actually executes (`docker compose exec db ...` vs a direct
    connection) and which host a connection string should point at. That is
    discoverable from docker-compose.yml, so it belongs in configuration
    resolved once at onboard time, not in a question repeated every task.
    """
    compose_file = next((name for name in COMPOSE_FILENAMES if (ROOT / name).is_file()), None)
    runtime: dict = {
        "dockerfile": (ROOT / "Dockerfile").is_file(),
        "compose_file": compose_file,
        "database_in_compose": False,
        "database_services": [],
    }
    if not compose_file:
        return runtime
    # Deliberately a shallow scan, not a YAML parse: this only needs to know
    # which datastore images appear, and the engine ships without PyYAML.
    text = (ROOT / compose_file).read_text(encoding="utf-8", errors="replace")
    service = None
    for line in text.splitlines():
        name_match = re.match(r"^  ([A-Za-z0-9._-]+):\s*$", line)
        if name_match:
            service = name_match.group(1)
            continue
        image_match = re.match(r"^\s+image:\s*[\"']?([^\"'\s]+)", line)
        if image_match and service:
            image = image_match.group(1).lower()
            for fragment, tech in DATASTORE_IMAGES.items():
                if fragment in image:
                    runtime["database_in_compose"] = True
                    runtime["database_services"].append(
                        {"service": service, "image": image_match.group(1), "technology": tech}
                    )
                    break
    return runtime


def cmd_onboard(args: argparse.Namespace) -> dict:
    stacks, sources, commands = [], [], {}
    if (ROOT / "package.json").exists():
        stacks.append("node"); sources.append("src"); commands["test_command"] = "npm test"
    if (ROOT / "composer.json").exists():
        stacks.extend(["php", "laravel"]); sources.append("app"); commands["test_command"] = "php artisan test"
    if (ROOT / "pyproject.toml").exists() or (ROOT / "requirements.txt").exists():
        stacks.append("python"); sources.append("src"); commands["test_command"] = "pytest -q"
    runtime = _detect_container_runtime()
    if runtime["dockerfile"] or runtime["compose_file"]:
        stacks.append("docker")
    if runtime["compose_file"]:
        stacks.append("compose")
    # Adding the detected datastore to the stack is what actually routes its
    # technology skill (and docker-compose-local) into database tasks.
    stacks.extend(entry["technology"] for entry in runtime["database_services"])
    if not stacks: stacks, sources = ["any"], ["."]
    proposal = {"stack": sorted(set(stacks)), "source_dirs": sorted(set(sources)),
                "verification": commands, "container_runtime": runtime}
    if args.apply:
        manifest = _writable_config_path("kit.yaml")
        backup = manifest.with_suffix(".yaml.bak")
        backup.write_text(manifest.read_text(encoding="utf-8"), encoding="utf-8")
        text = manifest.read_text(encoding="utf-8")
        text = re.sub(r"stack:\s*\[[^]]*\]", "stack: [" + ", ".join(proposal["stack"]) + "]", text)
        text = re.sub(r"source_dirs:\s*\[[^]]*\]", "source_dirs: [" + ", ".join(proposal["source_dirs"]) + "]", text)
        for key, value in commands.items(): text = re.sub(rf"{key}:.*", f"{key}: {value}", text)
        manifest.write_text(text, encoding="utf-8")
        proposal["applied"] = True
    return proposal


ANALYZE_SCHEMA_VERSION = 2
PROJECT_CONTEXT_SNAPSHOT_SCHEMA_VERSION = 1
# These are the small, explicit project inputs the analyzer reads.  Their
# hashes, plus Git's revision/diff fingerprint, let us decide whether a saved
# project-context snapshot is still usable without walking source trees.
ANALYSIS_INPUT_PATHS = (
    ".ai-config/kit.yaml",
    ".ai-config/contexts.yaml",
    "package.json",
    "composer.json",
    "pyproject.toml",
    "requirements.txt",
    "Dockerfile",
    *COMPOSE_FILENAMES,
)


def _sha256_file(path: Path) -> str | None:
    """Return a file-content digest, or a stable absence marker input."""
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_capture(*args: str) -> str | None:
    """Read a small Git metadata value without falling back to a tree scan."""
    try:
        completed = subprocess.run(
            ["git", *args], cwd=ROOT, text=True, capture_output=True, check=False
        )
    except OSError:
        return None
    return completed.stdout if completed.returncode == 0 else None


def _project_context_fingerprint() -> tuple[str, dict]:
    """Fingerprint analyzer inputs using config/marker hashes and Git metadata.

    `git diff --raw HEAD` compares the index and working tree to one commit;
    it returns blob metadata rather than loading a full textual patch and does
    not make the Python engine enumerate or open every source file. Its digest
    covers both the changed paths and their contents, so a second edit to the
    same tracked file cannot incorrectly reuse the previous snapshot.
    """
    files = {relative: _sha256_file(ROOT / relative) for relative in ANALYSIS_INPUT_PATHS}
    head = _git_capture("rev-parse", "--verify", "HEAD")
    diff = _git_capture("diff", "--raw", "--no-ext-diff", "HEAD", "--")
    inputs = {
        "files": files,
        "git_head": head.strip() if head else None,
        "tracked_worktree_diff": hashlib.sha256(diff.encode("utf-8")).hexdigest() if diff is not None else None,
    }
    encoded = json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest(), inputs


def _project_context_snapshot_path(state_file: Path) -> Path:
    return workspace(state_file) / "analysis" / "project-summary.json"


def _read_valid_project_context_snapshot(state_file: Path, fingerprint: str) -> dict | None:
    path = _project_context_snapshot_path(state_file)
    try:
        snapshot = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    metadata = snapshot.get("context_snapshot")
    if not isinstance(metadata, dict):
        return None
    if snapshot.get("schema_version") != ANALYZE_SCHEMA_VERSION:
        return None
    if metadata.get("schema_version") != PROJECT_CONTEXT_SNAPSHOT_SCHEMA_VERSION:
        return None
    return snapshot if metadata.get("fingerprint") == fingerprint else None


def _build_project_context_snapshot(fingerprint: str, inputs: dict) -> dict:
    onboard_proposal = cmd_onboard(argparse.Namespace(apply=False))
    contexts = _load_contexts()
    modules = {
        name: {"path": info.get("path"), "owner": info.get("owner"), "depends_on": list(info.get("depends_on") or [])}
        for name, info in contexts.items()
    }
    ownership: dict[str, list[str]] = {}
    for name, info in contexts.items():
        ownership.setdefault(info.get("owner") or "unowned", []).append(name)

    risks = []
    for name, info in contexts.items():
        if not info.get("owner"):
            risks.append({"kind": "unowned_context", "context": name, "detail": "no owner declared in contexts.yaml"})
        for dependency in info.get("depends_on") or []:
            if dependency not in contexts:
                risks.append({
                    "kind": "dangling_dependency", "context": name,
                    "detail": f"depends_on unknown context '{dependency}' -- contexts.yaml may have been hand-edited",
                })
    if not onboard_proposal.get("verification"):
        risks.append({"kind": "no_verification_command", "detail": "no test/lint/build command detected; verify will report inconclusive"})

    return {
        "schema_version": ANALYZE_SCHEMA_VERSION,
        "generated_at": now(),
        "context_snapshot": {
            "schema_version": PROJECT_CONTEXT_SNAPSHOT_SCHEMA_VERSION,
            "fingerprint": fingerprint,
            "inputs": inputs,
        },
        "stack": onboard_proposal["stack"],
        "container_runtime": onboard_proposal["container_runtime"],
        "modules": modules,
        "ownership": ownership,
        "risks": risks,
    }


def _load_or_refresh_project_context(state_file: Path, *, refresh: bool = False) -> tuple[dict, str]:
    fingerprint, inputs = _project_context_fingerprint()
    snapshot = None if refresh else _read_valid_project_context_snapshot(state_file, fingerprint)
    if snapshot is not None:
        return snapshot, "hit"

    snapshot = _build_project_context_snapshot(fingerprint, inputs)
    path = _project_context_snapshot_path(state_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return snapshot, "refreshed"


def cmd_analyze(args: argparse.Namespace) -> dict:
    """Project Analyzer + Knowledge Graph Builder: a read-only static-analysis
    snapshot combining stack/runtime detection (same detection `onboard`
    uses) with the module and ownership graph declared in
    `.ai-config/contexts.yaml`, plus a short list of static-analysis risk
    signals.

    This is deliberately scoped to what the repo's own config actually
    declares -- a bounded-context/module graph and its owners -- not a
    language-aware entity/API extractor. There is no parser here for
    arbitrary source languages, and this function must not grow one; a task
    that needs that is a new, separately-scoped capability with its own
    tests, not a quiet expansion of this one.
    """
    summary, cache_status = _load_or_refresh_project_context(
        state_path(getattr(args, "state", None)), refresh=getattr(args, "refresh", False)
    )
    # `cache` describes this command result only; the durable snapshot's
    # fingerprint and inputs live in `context_snapshot` above.
    return {**summary, "cache": {"status": cache_status}}


# ── ARCHITECTURE DISCOVERY ───────────────────────────────────────────────
#
# `.ai-config/contexts.yaml` stays the source of truth for bounded
# contexts/modules: this section only *adds* a read-only, best-effort scan
# for the feature modules underneath those contexts (or underneath the
# project's configured source_dirs, when nothing has been declared yet), so
# the Architecture Visualizer can render real project structure instead of
# only the handful of top-level contexts a project happens to have
# registered. It never writes to contexts.yaml or any source file.
ARCHITECTURE_DISCOVERY_SCHEMA_VERSION = 1

# Directory names a discovery scan never descends into: build output,
# dependency caches, VCS metadata, and other conventionally-generated or
# runtime content that is never a hand-authored feature module.
DISCOVERY_IGNORE_DIRS = {
    ".git", "node_modules", "dist", "build", "out", "__pycache__",
    ".venv", "venv", "env", "data", ".env", ".ai-work", ".visualizer",
    "coverage", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".next",
    ".turbo", "vendor", "target", ".tox",
}
DISCOVERY_SOURCE_EXTENSIONS = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py"}
DISCOVERY_TS_EXTENSIONS = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
REACT_FEATURE_BUCKETS = ("pages", "components", "features", "services", "contexts")


def _discovery_gitignore_patterns() -> list[str]:
    """Best-effort .gitignore patterns so discovery never descends into
    project-declared ignored content. Deliberately not a full gitignore
    matcher (no negation semantics, no anchoring rules) -- good enough to
    skip an obviously-ignored directory name or glob, not a replacement for
    git itself."""
    gitignore = ROOT / ".gitignore"
    if not gitignore.exists():
        return []
    patterns = []
    for line in gitignore.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and not stripped.startswith("!"):
            patterns.append(stripped.strip("/"))
    return patterns


def _discovery_is_ignored(rel_path: Path, patterns: list[str]) -> bool:
    parts = rel_path.parts
    if any(part in DISCOVERY_IGNORE_DIRS for part in parts):
        return True
    rel_str = rel_path.as_posix()
    for pattern in patterns:
        if pattern and (fnmatch.fnmatch(rel_str, pattern) or any(fnmatch.fnmatch(part, pattern) for part in parts)):
            return True
    return False


def _discovery_has_source_files(directory: Path, patterns: list[str]) -> bool:
    if not directory.is_dir():
        return False
    for path in directory.rglob("*"):
        if not path.is_file() or path.suffix not in DISCOVERY_SOURCE_EXTENSIONS:
            continue
        try:
            rel = path.relative_to(ROOT)
        except ValueError:
            continue
        if not _discovery_is_ignored(rel.parent, patterns):
            return True
    return False


def _discover_nestjs_modules(source_root: Path, patterns: list[str]) -> list[dict]:
    """NestJS convention: a directory containing `*.module.ts` is a feature
    module named after the file (`downloads.module.ts` -> `downloads`)."""
    modules = []
    if not source_root.is_dir():
        return modules
    for module_file in sorted(source_root.rglob("*.module.ts")):
        rel_dir = module_file.parent.relative_to(ROOT)
        if _discovery_is_ignored(rel_dir, patterns):
            continue
        name = re.sub(r"\.module$", "", module_file.stem)
        modules.append({"name": name, "path": rel_dir.as_posix(), "confidence": 0.95, "framework": "nestjs"})
    return modules


def _discover_react_modules(source_root: Path, patterns: list[str]) -> list[dict]:
    """React/Vite convention: each directory directly under one of
    src/{pages,components,features,services,contexts} that itself contains
    source files is a feature module."""
    modules = []
    src_dir = source_root / "src"
    if not src_dir.is_dir():
        return modules
    for bucket in REACT_FEATURE_BUCKETS:
        bucket_dir = src_dir / bucket
        if not bucket_dir.is_dir():
            continue
        for child in sorted(p for p in bucket_dir.iterdir() if p.is_dir()):
            rel = child.relative_to(ROOT)
            if _discovery_is_ignored(rel, patterns) or not _discovery_has_source_files(child, patterns):
                continue
            modules.append({"name": child.name, "path": rel.as_posix(), "confidence": 0.75, "framework": "react"})
    return modules


def _discover_python_packages(source_root: Path, patterns: list[str]) -> list[dict]:
    """Python convention: any directory with `__init__.py` (other than the
    source root itself) is a package/module."""
    modules = []
    if not source_root.is_dir():
        return modules
    for init_file in sorted(source_root.rglob("__init__.py")):
        package_dir = init_file.parent
        if package_dir == source_root:
            continue
        rel = package_dir.relative_to(ROOT)
        if _discovery_is_ignored(rel, patterns):
            continue
        modules.append({"name": package_dir.name, "path": rel.as_posix(), "confidence": 0.7, "framework": "python"})
    return modules


def _discover_generic_modules(source_root: Path, patterns: list[str]) -> list[dict]:
    """Fallback for stacks with no recognized convention: first- and
    second-level directories that contain source files, lowest confidence."""
    modules = []
    if not source_root.is_dir():
        return modules
    for level1 in sorted(p for p in source_root.iterdir() if p.is_dir()):
        rel1 = level1.relative_to(ROOT)
        if _discovery_is_ignored(rel1, patterns):
            continue
        if _discovery_has_source_files(level1, patterns):
            modules.append({"name": level1.name, "path": rel1.as_posix(), "confidence": 0.4, "framework": "generic"})
            continue
        for level2 in sorted(p for p in level1.iterdir() if p.is_dir()):
            rel2 = level2.relative_to(ROOT)
            if _discovery_is_ignored(rel2, patterns):
                continue
            if _discovery_has_source_files(level2, patterns):
                modules.append({"name": level2.name, "path": rel2.as_posix(), "confidence": 0.35, "framework": "generic"})
    return modules


def _discover_feature_modules(source_dirs: list[str]) -> tuple[list[dict], list[dict]]:
    """Runs every framework detector across every configured source dir, then
    falls back to the generic heuristic only for a source dir where no
    framework detector found anything. Returns (modules, warnings); modules
    are deduplicated by path (highest-confidence match wins), with a
    duplicate_module_path warning when two different names claim one path."""
    patterns = _discovery_gitignore_patterns()
    warnings: list[dict] = []
    by_path: dict[str, dict] = {}
    for source_dir in source_dirs:
        source_root = ROOT / source_dir
        if not source_root.exists():
            warnings.append({"kind": "source_root_missing", "detail": f"configured source dir does not exist: {source_dir}"})
            continue
        found = (
            _discover_nestjs_modules(source_root, patterns)
            + _discover_react_modules(source_root, patterns)
            + _discover_python_packages(source_root, patterns)
        )
        if not found:
            found = _discover_generic_modules(source_root, patterns)
        for module in found:
            existing = by_path.get(module["path"])
            if existing and existing["name"] != module["name"]:
                warnings.append({
                    "kind": "duplicate_module_path",
                    "detail": f"path '{module['path']}' discovered as both '{existing['name']}' and '{module['name']}'",
                })
            if not existing or module["confidence"] > existing["confidence"]:
                by_path[module["path"]] = module
    return list(by_path.values()), warnings


def _extract_ts_relative_imports(file_path: Path) -> list[str]:
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    specs: set[str] = set()
    for pattern in (
        r'''from\s+["'](\.[^"']+)["']''',
        r'''\bimport\s+["'](\.[^"']+)["']''',
        r'''require\(\s*["'](\.[^"']+)["']\s*\)''',
    ):
        specs.update(re.findall(pattern, text))
    return sorted(specs)


def _extract_python_imports(file_path: Path) -> list[tuple[str, int]]:
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8", errors="replace"))
    except (SyntaxError, OSError, ValueError, RecursionError):
        return []
    specs: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            specs.extend((alias.name, 0) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            specs.append((node.module or "", node.level or 0))
    return specs


def _discovery_owning_module(rel_path: Path, path_to_name: dict[str, str]) -> str | None:
    """Longest-path-prefix match: the most specific module claims a file."""
    rel_str = rel_path.as_posix()
    best: tuple[str, str] | None = None
    for path, name in path_to_name.items():
        if rel_str == path or rel_str.startswith(path + "/"):
            if best is None or len(path) > len(best[0]):
                best = (path, name)
    return best[1] if best else None


def _resolve_ts_dependency(file_path: Path, spec: str, path_to_name: dict[str, str]) -> tuple[str | None, float]:
    target = (file_path.parent / spec).resolve()
    try:
        rel = target.relative_to(ROOT)
    except ValueError:
        return None, 0.0
    name = _discovery_owning_module(rel, path_to_name)
    return (name, 0.85) if name else (None, 0.0)


def _resolve_python_dependency(
    file_path: Path, spec: str, level: int, source_roots: list[Path], path_to_name: dict[str, str],
) -> tuple[str | None, float]:
    if level > 0:
        base = file_path.parent
        for _ in range(level - 1):
            base = base.parent
        target = base / Path(spec.replace(".", "/")) if spec else base
        try:
            rel = target.relative_to(ROOT)
        except ValueError:
            return None, 0.0
        name = _discovery_owning_module(rel, path_to_name)
        return (name, 0.85) if name else (None, 0.0)
    if not spec:
        return None, 0.0
    parts = spec.split(".")
    for root in source_roots:
        candidate = root.joinpath(*parts)
        try:
            rel = candidate.relative_to(ROOT)
        except ValueError:
            continue
        name = _discovery_owning_module(rel, path_to_name)
        if name:
            return name, 0.6
    return None, 0.0


def _discover_dependencies(modules: list[dict], source_roots: list[Path]) -> list[dict]:
    """Best-effort internal dependency edges from relative TS/JS imports and
    Python imports (relative, or absolute-but-resolving-inside a configured
    source root). An import that cannot be resolved to a discovered/declared
    module path -- an external package, a stdlib module, an unresolvable
    absolute import -- is silently dropped rather than guessed at, per the
    'do not invent relationships' requirement."""
    path_to_name = {module["path"]: module["name"] for module in modules}
    edges: dict[tuple[str, str], dict] = {}

    def _record(source_name: str, target: str | None, confidence: float) -> None:
        if not target or target == source_name or confidence <= 0:
            return
        key = (source_name, target)
        if key not in edges or confidence > edges[key]["confidence"]:
            edges[key] = {"from": source_name, "to": target, "kind": "source-import", "confidence": confidence}

    for module in modules:
        module_dir = ROOT / module["path"]
        if not module_dir.is_dir():
            continue
        for file_path in module_dir.rglob("*"):
            if not file_path.is_file():
                continue
            if file_path.suffix in DISCOVERY_TS_EXTENSIONS:
                for spec in _extract_ts_relative_imports(file_path):
                    target, confidence = _resolve_ts_dependency(file_path, spec, path_to_name)
                    _record(module["name"], target, confidence)
            elif file_path.suffix == ".py":
                for spec, level in _extract_python_imports(file_path):
                    target, confidence = _resolve_python_dependency(file_path, spec, level, source_roots, path_to_name)
                    _record(module["name"], target, confidence)
    return sorted(edges.values(), key=lambda edge: (edge["from"], edge["to"]))


def _map_task_to_module(task: dict, modules: dict[str, dict]) -> str | None:
    """Module a task belongs to, in the required priority order: (1) an
    exact `task.context` match, (2) the most specific module whose path is a
    prefix of (or glob-matches) one of `task.files`, (3) unmapped. Never a
    substring/name comparison, which could match unrelated modules that
    happen to share a word."""
    context = task.get("context")
    if context and context in modules:
        return context
    best: tuple[str, str] | None = None
    for file_path in task.get("files") or []:
        for name, info in modules.items():
            path = info.get("path")
            if not path:
                continue
            if file_path == path or file_path.startswith(path + "/") or fnmatch.fnmatch(file_path, path):
                if best is None or len(path) > len(best[0]):
                    best = (path, name)
    return best[1] if best else None


def _build_discovered_architecture() -> dict:
    """Builds the discovered-architecture.json payload in memory. Declared
    contexts are read as-is (and keep full override authority over name,
    owner, path, dependencies -- nothing here mutates contexts.yaml);
    discovered feature modules are attached underneath the declared context
    whose path glob contains them, or flagged as unowned/out-of-context via
    warnings when no declared context claims them."""
    contexts = _load_contexts()
    for name, info in contexts.items():
        path_value = info.get("path")
        if path_value is not None and not isinstance(path_value, str):
            raise EngineError(f"invalid .ai-config/contexts.yaml: context '{name}' path must be a string glob, got {path_value!r}")

    source_dirs = configured_source_dirs() or ["."]
    modules_found, warnings = _discover_feature_modules(source_dirs)
    source_roots = [ROOT / directory for directory in source_dirs]

    contexts_out: dict[str, dict] = {}
    for name, info in contexts.items():
        contexts_out[name] = {
            "path": info.get("path"),
            "owner": info.get("owner"),
            "depends_on": list(info.get("depends_on") or []),
        }
        if not info.get("owner"):
            warnings.append({"kind": "module_missing_owner", "detail": f"declared context '{name}' has no owner"})
        if not info.get("path"):
            warnings.append({"kind": "invalid_glob", "detail": f"declared context '{name}' has no path glob"})
        for dependency in info.get("depends_on") or []:
            if dependency not in contexts:
                warnings.append({"kind": "dangling_dependency", "detail": f"context '{name}' depends_on unknown context '{dependency}'"})

    modules_out: dict[str, dict] = {}
    for name, info in contexts_out.items():
        modules_out[name] = {
            "name": name, "path": info["path"], "owner": info["owner"],
            "source": "declared", "kind": "bounded-context", "parent": None, "confidence": 1.0,
        }
    context_globs = [(info["path"], name, info.get("owner")) for name, info in contexts_out.items() if info.get("path")]

    for module in sorted(modules_found, key=lambda m: m["path"]):
        name = module["name"]
        if name in modules_out:
            original = name
            counter = 2
            while name in modules_out:
                name = f"{original}-{counter}"
                counter += 1
            warnings.append({
                "kind": "duplicate_module_path",
                "detail": f"discovered module name '{original}' collides with an existing module; renamed to '{name}' (path {module['path']})",
            })

        parent = owner = None
        for glob_path, context_name, context_owner in context_globs:
            if fnmatch.fnmatch(module["path"], glob_path) or fnmatch.fnmatch(module["path"] + "/", glob_path):
                parent, owner = context_name, context_owner
                break
        if parent is None:
            warnings.append({"kind": "module_outside_context", "detail": f"discovered module '{name}' ({module['path']}) is not inside any declared bounded context"})
        if not owner:
            warnings.append({"kind": "module_missing_owner", "detail": f"discovered module '{name}' ({module['path']}) has no owner"})

        modules_out[name] = {
            "name": name, "path": module["path"], "owner": owner, "source": "discovered",
            "kind": "feature", "parent": parent, "confidence": module["confidence"], "framework": module["framework"],
        }

    discovered_only = [m for m in modules_out.values() if m["source"] == "discovered"]
    edges = _discover_dependencies(discovered_only, source_roots)
    for edge in edges:
        if edge["to"] not in modules_out:
            warnings.append({"kind": "dangling_dependency", "detail": f"discovered dependency from '{edge['from']}' to unresolved module '{edge['to']}'"})
    for name, info in contexts_out.items():
        for dependency in info.get("depends_on") or []:
            if dependency in contexts_out:
                edges.append({"from": name, "to": dependency, "kind": "declared", "confidence": 1.0})

    return {
        "schema_version": ARCHITECTURE_DISCOVERY_SCHEMA_VERSION,
        "generated_at": now(),
        "contexts": contexts_out,
        "modules": modules_out,
        "edges": edges,
        "warnings": warnings,
    }


def _discovered_architecture_with_tasks(state: dict | None) -> dict:
    """Attaches task <-> module mapping (see `_map_task_to_module`) to a
    freshly built discovered-architecture artifact. Only emits
    module_without_tasks warnings when a workflow actually has tasks, so an
    empty/uninitialized project is not flagged for a condition it cannot
    yet meet."""
    artifact = _build_discovered_architecture()
    tasks = state["tasks"] if state else []
    for name, info in artifact["modules"].items():
        related = sorted({task["id"] for task in tasks if _map_task_to_module(task, artifact["modules"]) == name})
        info["related_tasks"] = related
        if tasks and not related and info["source"] == "discovered":
            artifact["warnings"].append({"kind": "module_without_tasks", "detail": f"module '{name}' has no related task"})
    return artifact


def cmd_architecture_discover(args: argparse.Namespace) -> dict:
    """`ai-kit architecture discover`: read-only scan producing
    `.visualizer/discovered-architecture.json`. Never touches
    `.ai-config/contexts.yaml` or any source file. Raises EngineError (exit
    code 2) only for a genuinely invalid configuration (e.g. a hand-edited
    contexts.yaml with a non-string path); an unreadable source file or an
    unmatched framework convention is reported as a warning in the artifact
    instead of failing the command."""
    state_path_value = state_path(getattr(args, "state", None))
    state = None
    if state_path_value.exists():
        state = load(state_path_value)
        validate(state)
    artifact = _discovered_architecture_with_tasks(state)
    if VISUALIZER_DIR.exists():
        (VISUALIZER_DIR / "discovered-architecture.json").write_text(
            json.dumps(artifact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    return artifact


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


def _post_completion_lock_path(task_id: str, state_arg: str | None) -> Path:
    return workspace(state_path(state_arg)) / "locks" / f"post_completion_{task_id}.lock"


def _acquire_task_lock(lock_path: Path) -> bool:
    """Best-effort exclusive file lock so two concurrent post-completion
    triggers for the same task never run their pipelines at the same time.
    Removes a lock whose recorded process no longer exists, then retries the
    acquire. Returns False (without blocking) if the lock is still held.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            owner_pid = int(lock_path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return False
        try:
            os.kill(owner_pid, 0)
        except ProcessLookupError:
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass
            return _acquire_task_lock(lock_path)
        except PermissionError:
            pass
        return False
    with os.fdopen(fd, "w") as handle:
        handle.write(str(os.getpid()))
    return True


def _release_task_lock(lock_path: Path) -> None:
    try:
        lock_path.unlink()
    except FileNotFoundError:
        pass


def _dispatch_approval(task_id: str, role: str, state_arg: str | None, agent_id: str | None = None) -> dict:
    """Dispatch an independent QA or review pass to the runner configured
    for `role` in .ai-config/automation.yaml -- mirrors cmd_dispatch's
    executor flow instead of fabricating a verdict in-process. The engine
    never calls cmd_approve() on the runner's behalf: the dispatched runner
    is required to render its own verdict and call
    `ai-kit approve ... --role {role}` (pass/approve) or
    `ai-kit transition ... reject` (fail/reject) itself before this returns
    successfully; if the task's status hasn't moved when the runner process
    exits, that's treated as a failure to act, not an implicit pass.
    """
    import subprocess as _sp
    if role not in {"qa", "review"}:
        raise EngineError(f"unsupported approval role: {role}")
    expected_status = "implementation-complete" if role == "qa" else "qa-passed"
    pass_status = "qa-passed" if role == "qa" else "review-approved"
    role_key = "qa" if role == "qa" else "reviewer"

    path = state_path(state_arg)
    state = load(path); validate(state)
    task = task_map(state).get(task_id)
    if not task:
        raise EngineError(f"unknown task: {task_id}")
    if task["status"] != expected_status:
        raise EngineError(f"cannot dispatch {role} approval for {task_id} from status {task['status']} (expected {expected_status})")

    roles = _load_automation_roles()
    if not roles[role_key]["enabled"]:
        raise EngineError(
            f"role '{role_key}' is disabled in .ai-config/automation.yaml (roles.{role_key}.enabled: false); "
            f"it must be verified manually via 'ai-kit approve {task_id} --role {role} ...', not dispatched"
        )
    exec_runner, _exec_entry, exec_model = _resolve_runner(None, None)
    config = _load_post_completion_config()
    task_attempts = task.get("attempts", 0)
    use_backup = task_attempts > config["backup_after_retries"]
    runner_key = "backup_runner" if use_backup and roles[role_key].get("backup_runner") else "runner"
    model_key = "backup_model" if use_backup and roles[role_key].get("backup_model") else "model"
    runner_name, runner, model = _resolve_runner(roles[role_key][runner_key], roles[role_key].get(model_key))
    if (runner_name, model) == (exec_runner, exec_model):
        raise EngineError(
            f".ai-config/automation.yaml: role '{role_key}' resolves to the same identity as 'executor' "
            f"({runner_name}/{model}); {role} must run under a different runner or model"
        )
    agent_id = agent_id or uuid.uuid4().hex[:8]

    state_flag = f" --state {state_arg}" if state_arg else ""
    verdict_flag = "--status" if role == "qa" else "--verdict"
    pass_value = "pass" if role == "qa" else "approve"
    fail_value = "fail" if role == "qa" else "reject"
    approve_cmd = (
        f"bash .ai/scripts/ai-kit{state_flag} approve {task_id} --role {role} "
        f"{verdict_flag} {pass_value} --reason '<your findings>' --runner {runner_name} "
        f"--model {model or ''} --agent-id {agent_id}"
    )
    reject_cmd = (
        f"bash .ai/scripts/ai-kit{state_flag} transition {task_id} reject --actor {role_key} "
        f"--detail '<your findings>'"
    )
    handoff = {
        "schema_version": 1,
        "role": role,
        "task": {
            "id": task["id"], "title": task["title"], "owner": task["owner"],
            "acceptance": task["acceptance"], "files": task["files"], "evidence": list(task.get("evidence", [])),
        },
        "execution": {"runner": runner_name, "model": model, "agent_id": agent_id},
        "instructions": (
            f"You are performing an independent {role} of task {task['id']}, separate from the executor "
            f"that implemented it. Inspect the change against the acceptance criteria above; do not trust "
            f"the executor's own claim of completion. If it meets the criteria, run exactly: `{approve_cmd}` "
            f"(this writes your own evidence JSON with kind/{verdict_flag.lstrip('--')}/runner/model/agent_id "
            f"and advances the task). Otherwise, run: `{reject_cmd}`. Do not fabricate a pass/approve verdict."
        ),
    }
    handoff_path = workspace(path) / "handoffs" / f"{role}_{task_id}.json"
    handoff_path.parent.mkdir(parents=True, exist_ok=True)
    handoff_path.write_text(json.dumps(handoff, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    prompt = (
        f"You are the {role} reviewer for task {task['id']}. Read {display_path(handoff_path)} "
        f"and follow its instructions exactly. Do not violate AGENTS.md."
    )
    cmd = _render_runner_command(runner["command"], prompt, model)
    print(f"Dispatching {role} approval for {task_id} to runner '{runner_name}/{model}'...", file=sys.stderr)
    # shell=True: same G4 threat model as cmd_dispatch above (template comes
    # from .ai-config/runners.yaml). stdin is closed for the same
    # non-interactive-only reason documented in runners.yaml.
    result = _sp.run(cmd, shell=True, cwd=str(ROOT), stdin=_sp.DEVNULL)
    audit = {
        "ts": now(), "task": task_id, "role": role, "runner": runner_name, "model": model,
        "command": cmd, "exit_code": result.returncode, "handoff_file": display_path(handoff_path),
    }
    audit_path = _dispatch_audit_path(path, task_id, role)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    if result.returncode != 0:
        raise EngineError(f"{role} runner {runner_name} exited with code {result.returncode}")

    state = load(path)
    task = task_map(state).get(task_id)
    if task["status"] not in {pass_status, "todo", "blocked"}:
        raise EngineError(
            f"{role} runner {runner_name} exited 0 but task {task_id} is still '{task['status']}' "
            f"(expected '{pass_status}' on approval, or 'todo'/'blocked' on rejection); the runner must "
            f"call 'ai-kit approve' or 'ai-kit transition reject' before returning"
        )
    return task


def _retry_rejected_task(task_id: str, state_arg: str | None, agent_id: str | None, lock_path: Path) -> dict | None:
    """Re-dispatch a rejected task when bounded retry automation is enabled."""
    config = _load_post_completion_config()
    path = state_path(state_arg)
    state = load(path); validate(state)
    task = task_map(state).get(task_id)
    if (
        not config["retry_on_rejection"]
        or task is None
        or task["status"] != "todo"
        or task.get("attempts", 0) > config["max_retries"]
    ):
        return None
    retry_number = task.get("attempts", 0)
    event(state, path, "post-completion-retry", task, "system", "todo", "todo", f"retry {retry_number}/{config['max_retries']} after QA/review rejection")
    save(state, path, state["revision"])
    _release_task_lock(lock_path)
    cmd_dispatch(argparse.Namespace(state=state_arg, id=task_id, runner=None, model=None, agent_id=agent_id))
    return _run_post_completion(task_id, state_arg, agent_id=agent_id)


def _run_post_completion(task_id: str, state_arg: str | None, agent_id: str | None = None) -> dict:
    """Run verify -> independent QA -> independent review -> close.

    Idempotent and resumable: a task already at 'done' is a safe no-op; a
    task parked at 'qa-passed' or 'review-approved' (e.g. a prior run
    stopped partway, or was rejected and re-completed) resumes from the
    next unfinished phase instead of repeating QA/review that already ran.
    Serialized per task via a lock file (released in `finally`) so two
    concurrent triggers for the same task only ever produce one pipeline
    run; a duplicate call while one is already in flight is a safe no-op.

    'verify' always runs (it is deterministic checks, not a judgment call).
    QA and review each only dispatch a CLI runner when
    `.ai-config/automation.yaml`'s `roles.qa`/`roles.reviewer` has
    `enabled: true` (the default). A disabled role stops the chain right
    before it, leaving the task parked at `implementation-complete` (qa
    disabled) or `qa-passed` (review disabled) with a `post-completion-
    manual-<role>` event recorded -- the expected next step is a human or an
    interactive session verifying by hand via `ai-kit approve`/`transition`.
    """
    lock_path = _post_completion_lock_path(task_id, state_arg)
    if not _acquire_task_lock(lock_path):
        return {"task": task_id, "post_completion": "already-running"}
    try:
        path = state_path(state_arg)
        state = load(path); validate(state)
        task = task_map(state).get(task_id)
        if not task:
            raise EngineError(f"unknown task: {task_id}")
        if task["status"] == "done":
            return {"task": task_id, "post_completion": "noop-already-done"}
        if task["status"] not in {"implementation-complete", "qa-passed", "review-approved"}:
            return {"task": task_id, "post_completion": f"noop-status-{task['status']}"}

        roles = _load_automation_roles()
        event(state, path, "post-completion-start", task, "system", task["status"], task["status"], "automated post-completion pipeline started")
        save(state, path, state["revision"])

        if task["status"] == "implementation-complete":
            print(f"[post-completion] {task_id}: verifying...", file=sys.stderr)
            report = cmd_verify(argparse.Namespace(state=state_arg, id=task_id))
            if not report["passed"] or report.get("inconclusive"):
                state = load(path); task = task_map(state).get(task_id)
                reason = "verify failed" if not report["passed"] else "verify inconclusive (no test/lint/typecheck/build configured)"
                event(state, path, "post-completion-failed", task, "system", task["status"], task["status"], f"{reason}; task remains at implementation-complete")
                save(state, path, state["revision"])
                return {"task": task_id, "post_completion": "verify-failed", "report": report}

            if not roles["qa"]["enabled"]:
                state = load(path); task = task_map(state).get(task_id)
                event(state, path, "post-completion-manual-qa", task, "system", task["status"], task["status"], "roles.qa.enabled is false; verify(passed) done, waiting for manual 'ai-kit approve --role qa'")
                save(state, path, state["revision"])
                return {"task": task_id, "post_completion": "qa-manual", "status": task["status"]}

            print(f"[post-completion] {task_id}: dispatching QA...", file=sys.stderr)
            try:
                task = _dispatch_approval(task_id, "qa", state_arg, agent_id=agent_id)
            except EngineError as exc:
                state = load(path); task = task_map(state).get(task_id)
                event(state, path, "post-completion-failed", task, "system", task["status"], task["status"], f"qa dispatch error: {exc}")
                save(state, path, state["revision"])
                return {"task": task_id, "post_completion": "qa-error", "error": str(exc)}
            if task["status"] != "qa-passed":
                retry_result = _retry_rejected_task(task_id, state_arg, agent_id, lock_path)
                if retry_result is not None:
                    return retry_result
                return {"task": task_id, "post_completion": "qa-rejected", "status": task["status"]}

        if task["status"] == "qa-passed":
            if not roles["reviewer"]["enabled"]:
                state = load(path); task = task_map(state).get(task_id)
                event(state, path, "post-completion-manual-review", task, "system", task["status"], task["status"], "roles.reviewer.enabled is false; qa-passed, waiting for manual 'ai-kit approve --role review'")
                save(state, path, state["revision"])
                return {"task": task_id, "post_completion": "review-manual", "status": task["status"]}

            print(f"[post-completion] {task_id}: dispatching review...", file=sys.stderr)
            try:
                task = _dispatch_approval(task_id, "review", state_arg, agent_id=agent_id)
            except EngineError as exc:
                state = load(path); task = task_map(state).get(task_id)
                event(state, path, "post-completion-failed", task, "system", task["status"], task["status"], f"review dispatch error: {exc}")
                save(state, path, state["revision"])
                return {"task": task_id, "post_completion": "review-error", "error": str(exc)}
            if task["status"] != "review-approved":
                retry_result = _retry_rejected_task(task_id, state_arg, agent_id, lock_path)
                if retry_result is not None:
                    return retry_result
                return {"task": task_id, "post_completion": "review-rejected", "status": task["status"]}

        if task["status"] == "review-approved":
            print(f"[post-completion] {task_id}: closing...", file=sys.stderr)
            close_args = argparse.Namespace(
                state=state_arg, id=task_id, action="close", actor="system",
                detail="Auto-closed by post-completion automation", evidence=None,
                expected_revision=None, agent_id=None,
            )
            task = _retry_transition(close_args)
            if _load_post_completion_config().get("dispatch_ready_on_close"):
                dispatch_result = cmd_dispatch_ready(argparse.Namespace(
                    state=state_arg,
                    runner=None,
                    model=None,
                    limit=_load_post_completion_config()["dispatch_ready_limit"],
                    context=None,
                    epic=None,
                    agent_id=None,
                ))
                state = load(path)
                task = task_map(state).get(task_id)
                event(
                    state,
                    path,
                    "post-completion-dispatch-ready",
                    task,
                    "system",
                    task["status"],
                    task["status"],
                    f"dispatched {len(dispatch_result.get('spawned', []))} ready task(s)",
                )
                save(state, path, state["revision"])

        return {"task": task_id, "post_completion": "done", "status": task["status"]}
    finally:
        _release_task_lock(lock_path)


def cmd_pipeline(args: argparse.Namespace) -> dict:
    """Advance one task through dispatch -> verify -> QA -> review -> close.

    Executor identity comes from runners.yaml's default_executor/default_model
    (the same fallback plain `dispatch` uses); qa/reviewer identities come
    from .ai-config/automation.yaml. Refuses to proceed if QA or review would run
    under the exact same (runner, model) as the executor -- the point of a
    separate approval phase is a second, independent look. QA and review are
    each dispatched to their own configured runner (see _dispatch_approval),
    which must render and record its own verdict; this command never
    fabricates one.
    Synchronous: each phase blocks until the assigned runner returns; there is
    no background scheduler or auto-trigger. Resume-capable: if the task is
    already past dispatch (e.g. a previous run stopped at a failed verify, or
    was rejected and re-completed), this skips straight to the first unfinished
    phase instead of re-dispatching the executor. There is no automatic retry
    across phases -- a stalled or failed phase stops here and reports why;
    resume by re-running after fixing the cause.

    A role with `roles.<qa|reviewer>.enabled: false` in automation.yaml is
    never dispatched or identity-checked here -- `_run_post_completion` parks
    the task right before that role's verdict instead (`qa-manual` /
    `review-manual`), which this command reports back as a normal (non-error)
    result rather than "pipeline stopped", since a disabled role is an
    intentional handoff to manual verification, not a failure.
    """
    state_file = state_path(args.state)
    state = load(state_file); validate(state)
    task = _resolve_task_definition(args.id, state, state_file)
    roles = _load_automation_roles()
    exec_runner, _exec_entry, exec_model = _resolve_runner(None, None)
    qa_runner = qa_model = rev_runner = rev_model = None
    if roles["qa"]["enabled"]:
        qa_runner, _qa_entry, qa_model = _resolve_runner(roles["qa"]["runner"], roles["qa"].get("model"))
        if (qa_runner, qa_model) == (exec_runner, exec_model):
            raise EngineError(
                f".ai-config/automation.yaml: role 'qa' resolves to the same identity as 'executor' "
                f"({qa_runner}/{qa_model}); QA must run under a different runner or model"
            )
    if roles["reviewer"]["enabled"]:
        rev_runner, _rev_entry, rev_model = _resolve_runner(roles["reviewer"]["runner"], roles["reviewer"].get("model"))
        if (rev_runner, rev_model) == (exec_runner, exec_model):
            raise EngineError(
                f".ai-config/automation.yaml: role 'reviewer' resolves to the same identity as 'executor' "
                f"({rev_runner}/{rev_model}); review must run under a different runner or model"
            )

    if task["status"] in {"todo", "in-progress"}:
        print(f"[pipeline] {task['id']}: dispatching to executor {exec_runner}/{exec_model}...", file=sys.stderr)
        cmd_dispatch(argparse.Namespace(state=args.state, id=task["id"], runner=exec_runner, model=exec_model, agent_id=args.agent_id))
    else:
        print(f"[pipeline] {task['id']}: resuming from status {task['status']}...", file=sys.stderr)

    result = _run_post_completion(task["id"], args.state, agent_id=args.agent_id)
    state = load(state_path(args.state))
    task = task_map(state).get(task["id"])
    if result.get("post_completion") in {"qa-manual", "review-manual"}:
        return {
            "task": task["id"] if task else args.id, "status": task["status"] if task else "unknown",
            "post_completion": result["post_completion"],
            "executor": f"{exec_runner}/{exec_model}",
            "qa": f"{qa_runner}/{qa_model}" if qa_runner else "manual",
            "reviewer": f"{rev_runner}/{rev_model}" if rev_runner else "manual",
        }
    if not task or task["status"] != "done":
        status = task["status"] if task else "unknown"
        raise EngineError(
            f"pipeline stopped for {args.id} at status '{status}' ({result.get('post_completion')}); "
            f"inspect the report/events above, fix, then re-run 'ai-kit pipeline {args.id}'"
        )
    return {
        "task": task["id"], "status": "done",
        "executor": f"{exec_runner}/{exec_model}",
        "qa": f"{qa_runner}/{qa_model}" if qa_runner else "manual",
        "reviewer": f"{rev_runner}/{rev_model}" if rev_runner else "manual",
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
    lease_flag = f" --agent-id {agent_id} --claim-id {task.get('claim_id')}" if agent_id and task.get("claim_id") else ""
    instructions = (
        f"Execute the task per the acceptance criteria above. Do not violate AGENTS.md. "
        f"When done, run: bash .ai/scripts/ai-kit{state_flag} transition {task['id']} "
        f"complete --actor {task['owner']}{lease_flag} --detail 'Completed by {runner_label}'"
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
    state_file = state_path(args.state)
    state = load(state_file); validate(state)
    task = _resolve_task_definition(args.id, state, state_file)
    runner_name, runner, selected_model = _resolve_runner(args.runner, args.model)
    template = runner["command"]
    agent_id = getattr(args, "agent_id", None) or uuid.uuid4().hex[:12]
    # The State Manager, not the runner, owns lifecycle transitions: claim the
    # task (todo -> in-progress) here so the runner only ever needs to report
    # completion, matching the single `complete` transition it is prompted for.
    if task["status"] == "todo":
        start_args = argparse.Namespace(state=args.state, id=task["id"], action="start", actor=task["owner"], detail=f"auto-started for dispatch to runner '{runner_name}'", evidence=None, expected_revision=None, agent_id=agent_id, claim_id=None, by=None)
        _retry_transition(start_args)
        # Re-resolve rather than reuse _retry_transition's return: that
        # return is the raw workflow.json task (lifecycle-updated status
        # only), which would silently drop the contract-file overlay above.
        task = _resolve_task_definition(task["id"], load(state_file), state_file)
    elif task["status"] != "in-progress":
        raise EngineError(f"cannot dispatch {task['id']} from status {task['status']} (must be todo or in-progress)")
    state_flag = f" --state {args.state}" if args.state else ""
    runner_label = f"{runner_name}/{selected_model}" if selected_model else runner_name
    lease_flag = f" --agent-id {agent_id} --claim-id {task.get('claim_id')}" if task.get("claim_id") else ""
    handoff_path = None
    route_payload = cmd_route(argparse.Namespace(state=args.state, id=task["id"], explain=False))
    if runner.get("input") == "json-file":
        handoff_path = _write_task_handoff(task, route_payload, args.state, runner_name, runner, selected_model, agent_id)
        handoff_display = display_path(handoff_path)
        prompt = f"You are {task['owner']}. Read and execute the task JSON at {handoff_display}. Do not violate AGENTS.md. When done, run: bash .ai/scripts/ai-kit{state_flag} transition {task['id']} complete --actor {task['owner']}{lease_flag} --detail 'Completed by {runner_label}'"
    else:
        tasks_md = display_path(workspace(state_file) / "tasks" / "tasks.md")
        prompt = f"You are {task['owner']}. Execute task {task['id']} per the requirements in {tasks_md}. Do not violate AGENTS.md. When done, run: bash .ai/scripts/ai-kit{state_flag} transition {task['id']} complete --actor {task['owner']}{lease_flag} --detail 'Completed by {runner_label}'"
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
    audit_path = _dispatch_audit_path(state_file, task["id"])
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
        # G2 requires evidence that the acceptance criteria actually hold. With
        # every verification command left at kit.yaml's 'true' sentinel, nothing
        # functional ran, so there is no such evidence -- reporting PASS here
        # would let `pipeline` auto-approve QA, auto-approve review, and close
        # the task on the strength of a secret-scan alone. Report it as
        # inconclusive (not passed, but distinguishable from a real failure) so
        # callers must either configure verification or approve manually with a
        # human-supplied reason.
        warning = (
            "no test/lint/typecheck/build command is configured in .ai-config/kit.yaml "
            "(all are 'true' or missing) — verify only ran security gates and did "
            "NOT check functional correctness. Run 'ai-kit onboard --apply' or edit "
            ".ai-config/kit.yaml's verification section for a real project."
        )
        report["warning"] = warning
        # No test/lint/typecheck/build command actually ran, so a "passed"
        # verdict here is inconclusive, not a real green signal. Standalone
        # `ai-kit verify` still reports it (unchanged CLI behavior); callers
        # that auto-advance a task on verify success (post-completion
        # automation) must treat inconclusive the same as a failure.
        report["inconclusive"] = True
        report["passed"] = False
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
    verdict = "PASS" if report["passed"] else ("INCONCLUSIVE" if report.get("inconclusive") else "FAIL")
    print(f"Verification {verdict}. Use 'ai-kit approve {task['id']} --role qa' to finalize.", file=sys.stderr)
    return report


def cmd_show(args: argparse.Namespace) -> dict:
    """Show the whole workflow state, or a single task's full detail.

    `ai-kit show` (no id) keeps its original whole-state dump for scripts
    that already depend on it. `ai-kit show <id>` is the debugging entry
    point advertised by the CLI: it resolves the task plus its dependency
    graph (both directions), acceptance criteria, evidence, drift flags, and
    its own event history in one call, so a user debugging a stuck lifecycle
    does not have to cross-reference `timeline`/`drift`/`graph` by hand.
    """
    state_file = state_path(args.state)
    state = load(state_file); validate(state); sync_phases(state)
    task_id = getattr(args, "id", None)
    if not task_id:
        return state
    tasks = task_map(state)
    task = tasks.get(task_id)
    if not task:
        raise EngineError(f"unknown task: {task_id}")
    needs = [
        {"id": dep, "title": tasks[dep]["title"], "status": tasks[dep]["status"]}
        if dep in tasks else {"id": dep, "title": None, "status": "unknown"}
        for dep in task.get("needs", [])
    ]
    dependents = [
        {"id": other["id"], "title": other["title"], "status": other["status"]}
        for other in state["tasks"] if task_id in other.get("needs", [])
    ]
    events = [e for e in state["events"] if e.get("task") == task_id]
    return {
        "task": task,
        "needs": needs,
        "dependents": dependents,
        "acceptance": task.get("acceptance", []),
        "evidence": task.get("evidence", []),
        "drift": _drift_flags(task, state_file),
        "events": events,
        "events_recent": events[-10:],
    }


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
    plan_draft = sub.add_parser("plan-draft", help="create, revise, finalize, and materialize a collaborative plan draft")
    plan_draft_sub = plan_draft.add_subparsers(dest="plan_draft_command", required=True)
    draft_create = plan_draft_sub.add_parser("create"); draft_create.add_argument("id"); draft_create.add_argument("--title", required=True); draft_create.add_argument("--workflow", default="feature"); draft_create.add_argument("--problem", required=True); draft_create.add_argument("--scope", action="append", default=[]); draft_create.add_argument("--out-of-scope", action="append", default=[]); draft_create.add_argument("--acceptance", nargs="+", action="append", default=[]); draft_create.add_argument("--assumption", action="append", default=[]); draft_create.add_argument("--open-question", action="append", default=[]); draft_create.add_argument("--actor", default="planner"); draft_create.set_defaults(fn=cmd_plan_draft_create)
    draft_update = plan_draft_sub.add_parser("update"); draft_update.add_argument("id"); draft_update.add_argument("--expected-revision", type=int, required=True); draft_update.add_argument("--summary", required=True); draft_update.add_argument("--title"); draft_update.add_argument("--problem"); draft_update.add_argument("--set-scope", nargs="*"); draft_update.add_argument("--set-out-of-scope", nargs="*"); draft_update.add_argument("--set-acceptance", nargs="+", action="append"); draft_update.add_argument("--add-scope", action="append"); draft_update.add_argument("--add-out-of-scope", action="append"); draft_update.add_argument("--add-acceptance", nargs="+", action="append"); draft_update.add_argument("--add-assumption", action="append"); draft_update.add_argument("--add-open-question", action="append"); draft_update.add_argument("--resolve-open-question", action="append"); draft_update.add_argument("--actor", default="planner"); draft_update.set_defaults(fn=cmd_plan_draft_update)
    draft_add_task = plan_draft_sub.add_parser("add-task"); draft_add_task.add_argument("id"); draft_add_task.add_argument("task_id"); draft_add_task.add_argument("--expected-revision", type=int, required=True); draft_add_task.add_argument("--title", required=True); draft_add_task.add_argument("--owner", required=True); draft_add_task.add_argument("--phase", required=True); draft_add_task.add_argument("--needs", nargs="*"); draft_add_task.add_argument("--depends-on", action="append", default=[], metavar="PATH"); draft_add_task.add_argument("--acceptance", nargs="+", action="append", required=True); draft_add_task.add_argument("--files", nargs="*"); draft_add_task.add_argument("--tags", nargs="*"); draft_add_task.add_argument("--context"); draft_add_task.add_argument("--epic"); draft_add_task.add_argument("--actor", default="planner"); draft_add_task.set_defaults(fn=cmd_plan_draft_add_task)
    draft_update_task = plan_draft_sub.add_parser("update-task"); draft_update_task.add_argument("id"); draft_update_task.add_argument("task_id"); draft_update_task.add_argument("--expected-revision", type=int, required=True); draft_update_task.add_argument("--summary", required=True); draft_update_task.add_argument("--title"); draft_update_task.add_argument("--owner"); draft_update_task.add_argument("--phase"); draft_update_task.add_argument("--context"); draft_update_task.add_argument("--epic"); draft_update_task.add_argument("--set-needs", nargs="*"); draft_update_task.add_argument("--set-depends-on", action="append", default=None, metavar="PATH"); draft_update_task.add_argument("--set-acceptance", nargs="+", action="append"); draft_update_task.add_argument("--set-files", nargs="*"); draft_update_task.add_argument("--set-tags", nargs="*"); draft_update_task.add_argument("--actor", default="planner"); draft_update_task.set_defaults(fn=cmd_plan_draft_update_task)
    draft_finalize = plan_draft_sub.add_parser("finalize"); draft_finalize.add_argument("id"); draft_finalize.add_argument("--expected-revision", type=int, required=True); draft_finalize.add_argument("--confirmed-by-user", action="store_true", help="required after the Planner has shown the plan and the user explicitly approved it"); draft_finalize.add_argument("--actor", default="planner"); draft_finalize.set_defaults(fn=cmd_plan_draft_finalize)
    draft_reopen = plan_draft_sub.add_parser("reopen"); draft_reopen.add_argument("id"); draft_reopen.add_argument("--expected-revision", type=int, required=True); draft_reopen.add_argument("--reason", required=True); draft_reopen.add_argument("--actor", default="planner"); draft_reopen.set_defaults(fn=cmd_plan_draft_reopen)
    draft_materialize = plan_draft_sub.add_parser("materialize"); draft_materialize.add_argument("id"); draft_materialize.add_argument("--create-tasks", action="store_true", help="required after a separate explicit user request to create the task DAG"); draft_materialize.add_argument("--actor", default="planner"); draft_materialize.set_defaults(fn=cmd_plan_draft_materialize)
    draft_show = plan_draft_sub.add_parser("show"); draft_show.add_argument("id"); draft_show.set_defaults(fn=cmd_plan_draft_show)
    trans = sub.add_parser("transition"); trans.add_argument("id"); trans.add_argument("action", choices=TRANSITIONS); trans.add_argument("--actor", required=True); trans.add_argument("--detail"); trans.add_argument("--evidence", nargs="+"); trans.add_argument("--expected-revision", type=int); trans.add_argument("--agent-id", help="unique identity of the agent instance recorded in the task lease"); trans.add_argument("--claim-id", help="opaque task lease required to complete or block claimed work"); trans.add_argument("--by", metavar="TASK-ID", help="required for 'supersede': the task id that replaced this one"); trans.set_defaults(fn=cmd_transition)
    approve = sub.add_parser("approve"); approve.add_argument("id"); approve.add_argument("--role", choices=["qa", "review"], required=True); approve.add_argument("--status"); approve.add_argument("--reason", required=True); approve.add_argument("--runner"); approve.add_argument("--model"); approve.add_argument("--agent-id"); approve.set_defaults(fn=cmd_approve)
    verify = sub.add_parser("verify"); verify.add_argument("id"); verify.set_defaults(fn=cmd_verify)
    dispatch = sub.add_parser("dispatch"); dispatch.add_argument("id"); dispatch.add_argument("--runner"); dispatch.add_argument("--model"); dispatch.add_argument("--agent-id"); dispatch.set_defaults(fn=cmd_dispatch)
    dispatch_ready = sub.add_parser("dispatch-ready"); dispatch_ready.add_argument("--runner"); dispatch_ready.add_argument("--model"); dispatch_ready.add_argument("--limit", type=int); dispatch_ready.add_argument("--context"); dispatch_ready.add_argument("--epic"); dispatch_ready.add_argument("--agent-id"); dispatch_ready.set_defaults(fn=cmd_dispatch_ready)
    pipeline = sub.add_parser("pipeline"); pipeline.add_argument("id"); pipeline.add_argument("--agent-id"); pipeline.set_defaults(fn=cmd_pipeline)
    route = sub.add_parser("route"); route.add_argument("id"); route.add_argument("--explain", action="store_true"); route.set_defaults(fn=cmd_route)
    activate = sub.add_parser("activate", help="select an isolated workflow as the active workspace"); activate.add_argument("workflow_state"); activate.set_defaults(fn=cmd_activate)
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
    backfill_contracts = sub.add_parser("backfill-contracts"); backfill_contracts.add_argument("id", nargs="?", help="task id to backfill; omit to cover every task in the state"); backfill_contracts.add_argument("--force", action="store_true", help="also regenerate a contract file that was hand-edited (hash_mismatch), discarding the edit"); backfill_contracts.add_argument("--actor", default="planner"); backfill_contracts.set_defaults(fn=cmd_backfill_contracts)
    onboard = sub.add_parser("onboard"); onboard.add_argument("--apply", action="store_true"); onboard.set_defaults(fn=cmd_onboard)
    analyze = sub.add_parser("analyze"); analyze.add_argument("--refresh", action="store_true", help="rebuild the project context snapshot even when its fingerprint is valid"); analyze.set_defaults(fn=cmd_analyze)
    architecture = sub.add_parser("architecture"); architecture_sub = architecture.add_subparsers(dest="architecture_command", required=True)
    architecture_discover = architecture_sub.add_parser("discover"); architecture_discover.set_defaults(fn=cmd_architecture_discover)
    show = sub.add_parser("show"); show.add_argument("id", nargs="?", help="task id to show full detail for; omit to dump the whole workflow state"); show.set_defaults(fn=cmd_show)
    valid = sub.add_parser("validate"); valid.set_defaults(fn=lambda args: (validate(load(state_path(args.state))) or {"valid": True}))
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        output = args.fn(args)
        print(output if isinstance(output, str) else json.dumps(output, indent=2))
        # `verify` reports a verdict rather than raising, so returning 0
        # unconditionally made it useless as a shell gate: dispatch-full.sh's
        # `if ! ai-kit verify ...` never fired, and a task whose checks FAILED
        # was auto-approved through QA and review and closed. The full report
        # is still printed either way; only the exit status changes, so a
        # caller reading stdout is unaffected while `if !`/`&&`/`set -e` now
        # behave the way any shell author would assume.
        if isinstance(output, dict) and args.fn is cmd_verify and not output.get("passed"):
            return 1
        return 0
    except EngineError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
