"""Unit tests for the AI-Kit v2 control-plane engine (.ai/engine/ai_kit.py).

Every test runs against a throwaway temp directory: ai_kit.ROOT and the
module-level path constants derived from it are monkeypatched per test so
nothing here ever touches this repository's real .ai-work/, .ai-config/, or
.visualizer/ state.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parents[1] / ".ai" / "engine"
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_DIR))
import ai_kit  # noqa: E402


def ns(**kwargs) -> argparse.Namespace:
    """Build an argparse.Namespace with the fields ai_kit's cmd_* functions expect."""
    defaults = dict(
        state=None, actor=None, detail=None, evidence=None,
        expected_revision=None, agent_id=None, context=None, epic=None,
    )
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


class EngineTestCase(unittest.TestCase):
    """Base case: builds an isolated temp ROOT with the minimal skeleton
    validate()/role_names()/workflow_names() need, and points every
    ai_kit module-level path constant at it."""

    ROLES = ("planner", "backend", "qa", "reviewer")
    WORKFLOWS = ("feature",)

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        for role in self.ROLES:
            (self.root / ".ai" / "agents" / role).mkdir(parents=True, exist_ok=True)
        for workflow in self.WORKFLOWS:
            (self.root / ".ai" / "workflows" / workflow).mkdir(parents=True, exist_ok=True)
        (self.root / ".ai-config").mkdir(parents=True, exist_ok=True)

        self._patched = {
            name: getattr(ai_kit, name)
            for name in ("ROOT", "WORK", "STATE", "CURRENT", "EVENT_LOG", "VISUALIZER_DIR")
        }
        ai_kit.ROOT = self.root
        ai_kit.WORK = self.root / ".ai-work-unused"
        ai_kit.STATE = ai_kit.WORK / "state" / "workflow.json"
        ai_kit.CURRENT = ai_kit.WORK / "state" / "current.json"
        ai_kit.EVENT_LOG = ai_kit.WORK / "logs" / "events.jsonl"
        # Nonexistent by construction: _generate_visualizer_data() no-ops
        # whenever VISUALIZER_DIR doesn't exist, which keeps tests from
        # writing into this repo's real .visualizer/.
        ai_kit.VISUALIZER_DIR = self.root / ".visualizer-unused"

        self.state_file = self.root / "work" / "state" / "workflow.json"

    def tearDown(self) -> None:
        for name, value in self._patched.items():
            setattr(ai_kit, name, value)
        self._tmp.cleanup()

    # -- helpers -----------------------------------------------------------
    def init_workflow(self, title: str = "Test workflow", workflow: str = "feature") -> None:
        ai_kit.cmd_init(ns(state=str(self.state_file), title=title, workflow=workflow,
                           actor="planner", force=False))

    def add_task(self, task_id: str, owner: str = "backend", phase: str = "build",
                 needs: list[str] | None = None, acceptance: list[str] | None = None,
                 **extra) -> dict:
        args = ns(
            state=str(self.state_file), id=task_id, title=f"Task {task_id}", owner=owner,
            phase=phase, needs=needs or [], depends_on=[],
            acceptance=[acceptance or [f"{task_id} works"]],
            files=[], tags=[], actor="planner",
        )
        for key, value in extra.items():
            setattr(args, key, value)
        return ai_kit.cmd_add_task(args)

    def transition(self, task_id: str, action: str, actor: str, **extra) -> dict:
        args = ns(state=str(self.state_file), id=task_id, action=action, actor=actor)
        for key, value in extra.items():
            setattr(args, key, value)
        return ai_kit.cmd_transition(args)

    def write_evidence(self, kind: str, task_id: str, **fields) -> str:
        payload = {"kind": kind, "task": task_id, "ts": ai_kit.now(), **fields}
        path = self.root / "evidence" / f"{kind}_{task_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        return str(path)

    def qa_evidence(self, task_id: str, status: str = "pass") -> str:
        return self.write_evidence("qa", task_id, status=status)

    def review_evidence(self, task_id: str, verdict: str = "approve") -> str:
        return self.write_evidence("review", task_id, verdict=verdict)


class StateMachineTests(EngineTestCase):
    def test_full_happy_path_reaches_done(self) -> None:
        self.init_workflow()
        self.add_task("T1")
        self.transition("T1", "start", actor="backend")
        self.transition("T1", "complete", actor="backend")
        self.transition("T1", "qa-pass", actor="qa", evidence=[self.qa_evidence("T1")])
        self.transition("T1", "review-approve", actor="reviewer", evidence=[self.review_evidence("T1")])
        task = self.transition("T1", "close", actor="reviewer")
        self.assertEqual(task["status"], "done")

    def test_invalid_transition_from_todo_is_rejected(self) -> None:
        self.init_workflow()
        self.add_task("T1")
        with self.assertRaises(ai_kit.EngineError):
            self.transition("T1", "qa-pass", actor="qa", evidence=[self.qa_evidence("T1")])

    def test_start_blocked_by_unfinished_dependency(self) -> None:
        self.init_workflow()
        self.add_task("T1")
        self.add_task("T2", needs=["T1"])
        with self.assertRaises(ai_kit.EngineError):
            self.transition("T2", "start", actor="backend")

    def test_start_allowed_once_dependency_done(self) -> None:
        self.init_workflow()
        self.add_task("T1")
        self.add_task("T2", needs=["T1"])
        self.transition("T1", "start", actor="backend")
        self.transition("T1", "complete", actor="backend")
        self.transition("T1", "qa-pass", actor="qa", evidence=[self.qa_evidence("T1")])
        self.transition("T1", "review-approve", actor="reviewer", evidence=[self.review_evidence("T1")])
        self.transition("T1", "close", actor="reviewer")
        task = self.transition("T2", "start", actor="backend")
        self.assertEqual(task["status"], "in-progress")

    def test_block_and_reject_require_detail(self) -> None:
        self.init_workflow()
        self.add_task("T1")
        self.transition("T1", "start", actor="backend")
        with self.assertRaises(ai_kit.EngineError):
            self.transition("T1", "block", actor="backend", detail=None)
        task = self.transition("T1", "block", actor="backend", detail="waiting on infra")
        self.assertEqual(task["status"], "blocked")
        self.assertEqual(task["blocked_reason"], "waiting on infra")

    def test_ready_lists_only_runnable_tasks(self) -> None:
        self.init_workflow()
        self.add_task("T1")
        self.add_task("T2", needs=["T1"])
        ready_ids = {item["id"] for item in ai_kit.cmd_ready(ns(state=str(self.state_file)))}
        self.assertEqual(ready_ids, {"T1"})
        self.transition("T1", "start", actor="backend")
        ready_ids = {item["id"] for item in ai_kit.cmd_ready(ns(state=str(self.state_file)))}
        self.assertEqual(ready_ids, set())


class SeparationOfDutiesTests(EngineTestCase):
    def test_executor_cannot_qa_pass_own_work(self) -> None:
        self.init_workflow()
        self.add_task("T1")
        self.transition("T1", "start", actor="backend")
        self.transition("T1", "complete", actor="backend")
        with self.assertRaises(ai_kit.EngineError) as ctx:
            self.transition("T1", "qa-pass", actor="backend", evidence=[self.qa_evidence("T1")])
        self.assertIn("must differ from executor", str(ctx.exception))

    def test_executor_cannot_review_approve_own_work(self) -> None:
        self.init_workflow()
        self.add_task("T1")
        self.transition("T1", "start", actor="backend")
        self.transition("T1", "complete", actor="backend")
        self.transition("T1", "qa-pass", actor="qa", evidence=[self.qa_evidence("T1")])
        with self.assertRaises(ai_kit.EngineError) as ctx:
            self.transition("T1", "review-approve", actor="backend",
                             evidence=[self.review_evidence("T1")])
        self.assertIn("must differ from executor", str(ctx.exception))

    def test_different_actor_may_qa_pass(self) -> None:
        self.init_workflow()
        self.add_task("T1")
        self.transition("T1", "start", actor="backend")
        self.transition("T1", "complete", actor="backend")
        task = self.transition("T1", "qa-pass", actor="qa", evidence=[self.qa_evidence("T1")])
        self.assertEqual(task["status"], "qa-passed")

    def test_separation_check_compares_role_not_agent_instance_suffix(self) -> None:
        """claimed_by may carry a '#agent_id' suffix; the same *role* under a
        different agent id must still be blocked from qa-passing its own work."""
        self.init_workflow()
        self.add_task("T1")
        self.transition("T1", "start", actor="backend", agent_id="worker-1")
        self.transition("T1", "complete", actor="backend")
        with self.assertRaises(ai_kit.EngineError):
            self.transition("T1", "qa-pass", actor="backend", agent_id="worker-2",
                             evidence=[self.qa_evidence("T1")])


class EvidenceGateTests(EngineTestCase):
    def _to_implementation_complete(self) -> None:
        self.add_task("T1")
        self.transition("T1", "start", actor="backend")
        self.transition("T1", "complete", actor="backend")

    def test_qa_pass_requires_evidence_argument(self) -> None:
        self.init_workflow()
        self._to_implementation_complete()
        with self.assertRaises(ai_kit.EngineError) as ctx:
            self.transition("T1", "qa-pass", actor="qa", evidence=None)
        self.assertIn("requires at least one --evidence", str(ctx.exception))

    def test_qa_pass_rejects_missing_evidence_file(self) -> None:
        self.init_workflow()
        self._to_implementation_complete()
        with self.assertRaises(ai_kit.EngineError):
            self.transition("T1", "qa-pass", actor="qa",
                             evidence=[str(self.root / "nope.json")])

    def test_qa_pass_rejects_evidence_for_wrong_task(self) -> None:
        self.init_workflow()
        self._to_implementation_complete()
        self.add_task("T2")
        wrong_evidence = self.qa_evidence("T2")
        with self.assertRaises(ai_kit.EngineError):
            self.transition("T1", "qa-pass", actor="qa", evidence=[wrong_evidence])

    def test_qa_pass_rejects_non_passing_evidence(self) -> None:
        self.init_workflow()
        self._to_implementation_complete()
        failing = self.qa_evidence("T1", status="fail")
        with self.assertRaises(ai_kit.EngineError) as ctx:
            self.transition("T1", "qa-pass", actor="qa", evidence=[failing])
        self.assertIn("not passing", str(ctx.exception))

    def test_review_approve_rejects_non_approve_verdict(self) -> None:
        self.init_workflow()
        self._to_implementation_complete()
        self.transition("T1", "qa-pass", actor="qa", evidence=[self.qa_evidence("T1")])
        rejected = self.review_evidence("T1", verdict="reject")
        with self.assertRaises(ai_kit.EngineError) as ctx:
            self.transition("T1", "review-approve", actor="reviewer", evidence=[rejected])
        self.assertIn("not approved", str(ctx.exception))

    def test_qa_pass_rejects_non_json_evidence(self) -> None:
        self.init_workflow()
        self._to_implementation_complete()
        text_file = self.root / "notes.txt"
        text_file.write_text("looks good to me", encoding="utf-8")
        with self.assertRaises(ai_kit.EngineError):
            self.transition("T1", "qa-pass", actor="qa", evidence=[str(text_file)])


class ValidateInvariantTests(EngineTestCase):
    def test_unknown_dependency_rejected(self) -> None:
        self.init_workflow()
        with self.assertRaises(ai_kit.EngineError):
            self.add_task("T1", needs=["ghost"])

    def test_self_dependency_rejected(self) -> None:
        self.init_workflow()
        with self.assertRaises(ai_kit.EngineError):
            self.add_task("T1", needs=["T1"])

    def test_dependency_cycle_rejected(self) -> None:
        self.init_workflow()
        self.add_task("T1")
        self.add_task("T2", needs=["T1"])
        # Manually rewrite state on disk to introduce a cycle (T1 <- T2 <- T1)
        # since add_task's own validate() call would refuse to create it.
        state = json.loads(self.state_file.read_text(encoding="utf-8"))
        state["tasks"][0]["needs"] = ["T2"]
        self.state_file.write_text(json.dumps(state), encoding="utf-8")
        with self.assertRaises(ai_kit.EngineError) as ctx:
            ai_kit.cmd_ready(ns(state=str(self.state_file)))
        self.assertIn("cycle", str(ctx.exception))

    def test_unknown_owner_rejected(self) -> None:
        self.init_workflow()
        with self.assertRaises(ai_kit.EngineError):
            self.add_task("T1", owner="nonexistent-role")

    def test_missing_acceptance_rejected(self) -> None:
        self.init_workflow()
        with self.assertRaises(ai_kit.EngineError):
            args = ns(state=str(self.state_file), id="T1", title="T1", owner="backend",
                       phase="build", needs=[], depends_on=[], acceptance=[[]],
                       files=[], tags=[], actor="planner")
            ai_kit.cmd_add_task(args)

    def test_g3_review_required_blocks_done_without_review_evidence(self) -> None:
        """rules.yaml's review_required gate (G3) is enforced by validate(),
        which runs at the top of every command -- so a task forced to 'done'
        without review evidence fails on the next read, not silently."""
        (self.root / ".ai-config" / "rules.yaml").write_text(
            "review_required: true\n", encoding="utf-8"
        )
        self.init_workflow()
        self.add_task("T1")
        state = json.loads(self.state_file.read_text(encoding="utf-8"))
        state["tasks"][0]["status"] = "done"
        self.state_file.write_text(json.dumps(state), encoding="utf-8")
        with self.assertRaises(ai_kit.EngineError) as ctx:
            ai_kit.cmd_ready(ns(state=str(self.state_file)))
        self.assertIn("G3 review_required", str(ctx.exception))

    def test_g3_review_required_can_be_disabled_via_rules_yaml(self) -> None:
        (self.root / ".ai-config" / "rules.yaml").write_text(
            "review_required: false\n", encoding="utf-8"
        )
        self.init_workflow()
        self.add_task("T1")
        state = json.loads(self.state_file.read_text(encoding="utf-8"))
        state["tasks"][0]["status"] = "done"
        self.state_file.write_text(json.dumps(state), encoding="utf-8")
        # Should not raise now that the gate is off.
        ai_kit.cmd_ready(ns(state=str(self.state_file)))


class ConcurrencyTests(EngineTestCase):
    def test_stale_expected_revision_is_rejected(self) -> None:
        self.init_workflow()
        self.add_task("T1")
        state = json.loads(self.state_file.read_text(encoding="utf-8"))
        stale_revision = state["revision"]
        # A concurrent writer bumps the revision first.
        self.add_task("T2")
        with self.assertRaises(ai_kit.EngineError) as ctx:
            self.transition("T1", "start", actor="backend", expected_revision=stale_revision)
        self.assertIn("changed concurrently", str(ctx.exception))

    def test_matching_expected_revision_succeeds(self) -> None:
        self.init_workflow()
        self.add_task("T1")
        state = json.loads(self.state_file.read_text(encoding="utf-8"))
        current_revision = state["revision"]
        task = self.transition("T1", "start", actor="backend", expected_revision=current_revision)
        self.assertEqual(task["status"], "in-progress")

    def test_retry_transition_recovers_from_lost_race(self) -> None:
        """_retry_transition reloads state fresh on each attempt, so a caller
        racing another writer eventually succeeds instead of raising."""
        self.init_workflow()
        self.add_task("T1")
        state = json.loads(self.state_file.read_text(encoding="utf-8"))
        stale_revision = state["revision"]
        self.add_task("T2")  # simulate a concurrent write that bumps the revision
        args = ns(state=str(self.state_file), id="T1", action="start", actor="backend",
                   expected_revision=stale_revision)
        with self.assertRaises(ai_kit.EngineError):
            ai_kit.cmd_transition(args)  # direct call still fails
        args.expected_revision = None
        task = ai_kit._retry_transition(args)
        self.assertEqual(task["status"], "in-progress")


class DagPayloadTests(EngineTestCase):
    """_generate_dag_payload() backs the visualizer's DAG tab: edges, layering
    (wave number), lifecycle stage, ready set, and the weighted critical path."""

    def _load_state(self) -> dict:
        return json.loads(self.state_file.read_text(encoding="utf-8"))

    def test_empty_workflow_yields_empty_dag(self) -> None:
        self.init_workflow()
        dag = ai_kit._generate_dag_payload(self._load_state())
        self.assertEqual(dag, {"tasks": [], "edges": [], "waves": 0, "ready": [], "critical_path": []})

    def test_layering_and_edges_on_a_branching_graph(self) -> None:
        # T0 -> T1 -> T2, plus a parallel T3 depending on T0 only.
        self.init_workflow()
        self.add_task("T0")
        self.add_task("T1", needs=["T0"])
        self.add_task("T2", needs=["T1"])
        self.add_task("T3", needs=["T0"])
        dag = ai_kit._generate_dag_payload(self._load_state())
        by_id = {t["id"]: t for t in dag["tasks"]}
        self.assertEqual(by_id["T0"]["layer"], 0)
        self.assertEqual(by_id["T1"]["layer"], 1)
        self.assertEqual(by_id["T2"]["layer"], 2)
        self.assertEqual(by_id["T3"]["layer"], 1)
        self.assertEqual(dag["waves"], 3)
        self.assertIn({"from": "T0", "to": "T1", "unlocked": False}, dag["edges"])
        self.assertIn({"from": "T1", "to": "T2", "unlocked": False}, dag["edges"])
        self.assertIn({"from": "T0", "to": "T3", "unlocked": False}, dag["edges"])
        self.assertEqual(dag["ready"], ["T0"])

    def test_unlocked_flips_once_upstream_is_done(self) -> None:
        self.init_workflow()
        self.add_task("T0")
        self.add_task("T1", needs=["T0"])
        self.transition("T0", "start", actor="backend")
        self.transition("T0", "complete", actor="backend")
        self.transition("T0", "qa-pass", actor="qa", evidence=[self.qa_evidence("T0")])
        self.transition("T0", "review-approve", actor="reviewer", evidence=[self.review_evidence("T0")])
        self.transition("T0", "close", actor="reviewer")
        dag = ai_kit._generate_dag_payload(self._load_state())
        edge = next(e for e in dag["edges"] if e["from"] == "T0" and e["to"] == "T1")
        self.assertTrue(edge["unlocked"])
        self.assertIn("T1", dag["ready"])
        by_id = {t["id"]: t for t in dag["tasks"]}
        self.assertEqual(by_id["T0"]["stage"], 5)
        self.assertIn("todo", by_id["T0"]["history"])
        self.assertIn("done", by_id["T0"]["history"])

    def test_blocked_task_has_no_stage_but_max_weight(self) -> None:
        self.init_workflow()
        self.add_task("T0")
        self.transition("T0", "start", actor="backend")
        self.transition("T0", "block", actor="backend", detail="waiting on infra")
        dag = ai_kit._generate_dag_payload(self._load_state())
        task = dag["tasks"][0]
        self.assertEqual(task["stage"], -1)
        self.assertEqual(task["blocked_reason"], "waiting on infra")

    def test_critical_path_prefers_chain_with_more_remaining_work(self) -> None:
        # T0 -> T1 -> T2  (long chain, all still `todo`)
        # T0 -> T3        (short chain)
        # Finishing T0 shouldn't make the short branch "critical" just
        # because it touches a completed task; the long chain still has
        # more remaining stages and should win.
        self.init_workflow()
        self.add_task("T0")
        self.add_task("T1", needs=["T0"])
        self.add_task("T2", needs=["T1"])
        self.add_task("T3", needs=["T0"])
        self.transition("T0", "start", actor="backend")
        self.transition("T0", "complete", actor="backend")
        self.transition("T0", "qa-pass", actor="qa", evidence=[self.qa_evidence("T0")])
        self.transition("T0", "review-approve", actor="reviewer", evidence=[self.review_evidence("T0")])
        self.transition("T0", "close", actor="reviewer")
        dag = ai_kit._generate_dag_payload(self._load_state())
        self.assertEqual(dag["critical_path"], ["T1", "T2"])

    def test_diamond_dependency_layers_by_longest_path(self) -> None:
        # T0 -> T1 -> T3
        # T0 -> T2 -> T3   (T3 needs both T1 and T2; longest path wins)
        self.init_workflow()
        self.add_task("T0")
        self.add_task("T1", needs=["T0"])
        self.add_task("T2", needs=["T0"])
        self.add_task("T3", needs=["T1", "T2"])
        dag = ai_kit._generate_dag_payload(self._load_state())
        by_id = {t["id"]: t for t in dag["tasks"]}
        self.assertEqual(by_id["T3"]["layer"], 2)
        self.assertEqual(dag["waves"], 3)


class RoutingAndSkillMetadataTests(EngineTestCase):
    def _write_skill(self, relative: str) -> None:
        skill_dir = self.root / relative
        skill_dir.mkdir(parents=True, exist_ok=True)
        docs = {
            "overview.md": "# Overview\n",
            "patterns.md": "# Patterns\n",
            "best-practices.md": "# Best\n",
            "pitfalls.md": "# Pitfalls\n",
            "examples.md": "# Examples\n",
        }
        for name, body in docs.items():
            (skill_dir / name).write_text(body, encoding="utf-8")
        (skill_dir / "skill.meta.yaml").write_text(
            "\n".join(
                [
                    f"name: {skill_dir.name}",
                    f"domain: {skill_dir.parent.name}",
                    "version: 1.0.0",
                    "status: active",
                    "owner: backend",
                    "reviewed_at: 2026-08-01",
                    "reviewers: [reviewer, backend]",
                    "depends_on: []",
                    "triggers: []",
                    "documents: [overview.md, patterns.md, best-practices.md, pitfalls.md, examples.md]",
                    "deprecated: false",
                    f"entrypoint: {relative}/overview.md",
                    f"path: {relative}",
                ]
            ) + "\n",
            encoding="utf-8",
        )

    def _write_core_skill(self, name: str) -> None:
        core_path = self.root / ".ai" / "skills" / "core" / name
        core_path.mkdir(parents=True, exist_ok=True)
        (core_path / "SKILL.md").write_text(
            "\n".join(
                [
                    "---",
                    f"name: {name}",
                    "description: test core skill",
                    "version: 1.0.0",
                    "tier: core",
                    "stack: [any]",
                    "owner: reviewer",
                    "gates: [G2]",
                    "related: []",
                    "---",
                    "",
                    f"# Skill: {name}",
                    "",
                    "## Purpose",
                    "test",
                ]
            ) + "\n",
            encoding="utf-8",
        )

    def setUp(self) -> None:
        super().setUp()
        for core_name in [
            "skill-router",
            "api-contract",
            "observability",
            "threat-modeling",
            "security-review",
            "performance-profiling",
            "test-and-validation",
            "e2e-testing",
            "integration-contracts",
            "contract-testing",
            "webhooks-and-retries",
            "architecture-decisions",
        ]:
            self._write_core_skill(core_name)
        for rel in [
            ".ai/skills/ai/openai",
            ".ai/skills/ai/llm-application",
            ".ai/skills/ai/ai-safety",
            ".ai/skills/ai/rag",
            ".ai/skills/ai/embeddings",
            ".ai/skills/ai/vector-search",
            ".ai/skills/ai/model-evaluation",
            ".ai/skills/database/pgvector",
            ".ai/skills/database/qdrant",
            ".ai/skills/frontend/vue",
        ]:
            self._write_skill(rel)

        (self.root / ".ai-config" / "kit.yaml").write_text(
            "project:\n  stack: [rag, pgvector]\n", encoding="utf-8"
        )
        (self.root / ".ai-config" / "registry.yaml").write_text(
            "\n".join(
                [
                    "owners:",
                    "  backend: [backend, database, ai]",
                    "skill_triggers:",
                    "  prompt-injection:",
                    "    match: [\"prompt injection\"]",
                    "    core_skills: [\"threat-modeling\", \"security-review\"]",
                    "    technology_skills: [\"ai/ai-safety\"]",
                    "    reason: \"Prompt attack risk\"",
                    "  rag-retrieval:",
                    "    match: [\"rag\", \"retrieval\"]",
                    "    core_skills: []",
                    "    technology_skills: [\"ai/rag\", \"ai/embeddings\", \"ai/vector-search\", \"ai/model-evaluation\"]",
                    "    reason: \"RAG path\"",
                    "  llm-model:",
                    "    match: [\"llm\"]",
                    "    core_skills: [\"performance-profiling\", \"observability\"]",
                    "    technology_skills: [\"ai/openai\", \"ai/llm-application\"]",
                    "    reason: \"LLM path\"",
                ]
            ) + "\n",
            encoding="utf-8",
        )

    def test_route_trigger_selection_and_structured_documents(self) -> None:
        self.init_workflow()
        self.add_task(
            "T1",
            owner="backend",
            tags=["rag", "pgvector", "llm"],
            acceptance=["Handle prompt injection safely"],
            files=["src/retrieval.py"],
        )
        state = ai_kit.cmd_route(ns(state=str(self.state_file), id="T1", explain=True))
        self.assertIn("skills", state)
        self.assertIn("skill_details", state)
        self.assertIn("trigger_matches", state)
        self.assertIn("explain", state)
        entries = {item["name"]: item for item in state["skill_details"]}
        self.assertIn("ai/ai-safety", entries)
        self.assertIn("ai/rag", entries)
        self.assertIn("database/pgvector", entries)
        self.assertIn("threat-modeling", entries)
        self.assertIn("security-review", entries)
        self.assertEqual(entries["ai/rag"]["documents"][0], ".ai/skills/ai/rag/overview.md")
        orders = [item["loading_order"] for item in state["skill_details"]]
        self.assertEqual(orders, sorted(orders))
        trigger_ids = {item["id"] for item in state["trigger_matches"]}
        self.assertTrue({"prompt-injection", "rag-retrieval", "llm-model"} <= trigger_ids)

    def test_route_excludes_unrelated_ai_skills_when_no_trigger(self) -> None:
        self.init_workflow()
        self.add_task("T2", owner="backend", tags=["mysql"], acceptance=["schema update"], files=["db/schema.sql"])
        payload = ai_kit.cmd_route(ns(state=str(self.state_file), id="T2", explain=False))
        names = {item["name"] for item in payload["skill_details"]}
        self.assertIn("api-contract", names)
        self.assertNotIn("ai/ai-safety", names)
        self.assertNotIn("database/qdrant", names)

    def test_handoff_payload_contains_selected_skills(self) -> None:
        self.init_workflow()
        task = self.add_task("T3", owner="backend", tags=["llm"], acceptance=["safe output"])
        route_payload = ai_kit.cmd_route(ns(state=str(self.state_file), id="T3", explain=False))
        handoff = ai_kit._write_task_handoff(
            task=task,
            route_payload=route_payload,
            state_arg=str(self.state_file),
            runner_name="dummy",
            runner={"provider": "test"},
            model="test-model",
            agent_id="agent1",
        )
        data = json.loads(Path(handoff).read_text(encoding="utf-8"))
        self.assertIn("routing", data)
        self.assertIn("skills", data["routing"])
        self.assertIn("skill_details", data["routing"])
        selected_names = {item["name"] for item in data["routing"]["skill_details"]}
        self.assertTrue({"ai/openai", "ai/llm-application"} & selected_names)


class CheckSkillsScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        scripts = self.root / ".ai" / "scripts"
        scripts.mkdir(parents=True, exist_ok=True)
        source = Path(__file__).resolve().parents[1] / ".ai" / "scripts" / "check-skills.sh"
        shutil.copy2(source, scripts / "check-skills.sh")
        self.script = scripts / "check-skills.sh"
        self._mk_core("skill-router")
        self._mk_core("threat-modeling")
        self._mk_core("security-review")
        self._mk_core("performance-profiling")
        self._mk_core("observability")
        self._mk_core("test-and-validation")
        self._mk_core("e2e-testing")
        self._mk_core("integration-contracts")
        self._mk_core("contract-testing")
        self._mk_core("webhooks-and-retries")
        self._mk_core("architecture-decisions")
        self._mk_tech("ai", "openai")
        self._mk_tech("backend", "python")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _mk_core(self, name: str, malformed: bool = False) -> None:
        path = self.root / ".ai" / "skills" / "core" / name
        path.mkdir(parents=True, exist_ok=True)
        if malformed:
            text = "---\nname: bad\n---\n"
        else:
            text = (
                "---\n"
                f"name: {name}\n"
                "description: test\n"
                "version: 1.0.0\n"
                "tier: core\n"
                "stack: [any]\n"
                "owner: reviewer\n"
                "gates: [G2]\n"
                "related: []\n"
                "---\n\n"
                f"# Skill: {name}\n"
            )
        (path / "SKILL.md").write_text(text, encoding="utf-8")

    def _mk_tech(self, domain: str, name: str, placeholder: bool = False, broken_meta: bool = False) -> None:
        path = self.root / ".ai" / "skills" / domain / name
        path.mkdir(parents=True, exist_ok=True)
        body = "PLACEHOLDER text\n" if placeholder else "# content\n"
        for doc in ["overview.md", "patterns.md", "best-practices.md", "pitfalls.md", "examples.md"]:
            (path / doc).write_text(body, encoding="utf-8")
        if broken_meta:
            meta = "name: bad\n"
        else:
            meta = (
                f"name: {name}\n"
                f"domain: {domain}\n"
                "version: 1.0.0\n"
                "status: active\n"
                "owner: backend\n"
                "reviewed_at: 2026-08-01\n"
                "reviewers: [reviewer]\n"
                "depends_on: []\n"
                "triggers: []\n"
                "documents: [overview.md, patterns.md, best-practices.md, pitfalls.md, examples.md]\n"
                "deprecated: false\n"
                f"entrypoint: .ai/skills/{domain}/{name}/overview.md\n"
                f"path: .ai/skills/{domain}/{name}\n"
            )
        (path / "skill.meta.yaml").write_text(meta, encoding="utf-8")

    def _run(self, mode: str | None = None) -> subprocess.CompletedProcess:
        cmd = ["bash", str(self.script)]
        if mode:
            cmd.append(mode)
        return subprocess.run(cmd, cwd=self.root, capture_output=True, text=True)

    def test_default_mode_is_all_and_detects_placeholder(self) -> None:
        self._mk_tech("database", "redis", placeholder=True)
        result = self._run()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("contains placeholder markers", result.stderr)

    def test_ai_mode_ignores_non_ai_technology_failures(self) -> None:
        self._mk_tech("database", "redis", placeholder=True)
        result = self._run("ai")
        self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_core_mode_fails_on_malformed_front_matter(self) -> None:
        self._mk_core("release-management", malformed=True)
        result = self._run("core")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing front matter field", result.stderr)

    def test_all_mode_fails_on_broken_metadata(self) -> None:
        self._mk_tech("devops", "terraform", broken_meta=True)
        result = self._run("all")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing required field", result.stderr)


class SkillMetadataTests(unittest.TestCase):
    """Verify skill.meta.yaml exists and has correct content for all technology skills."""

    SKILLS_ROOT = REPO_ROOT / ".ai" / "skills"
    REQUIRED_FIELDS = ("name", "domain", "version", "owner", "reviewed_at",
                       "documents", "entrypoint", "path")

    def _tech_dirs(self) -> list[Path]:
        dirs = []
        for domain_dir in self.SKILLS_ROOT.iterdir():
            if not domain_dir.is_dir() or domain_dir.name == "core":
                continue
            for tech_dir in domain_dir.iterdir():
                if tech_dir.is_dir():
                    dirs.append(tech_dir)
        return sorted(dirs)

    def test_all_tech_skills_have_meta(self) -> None:
        missing = [d for d in self._tech_dirs() if not (d / "skill.meta.yaml").exists()]
        self.assertEqual(missing, [], f"Missing skill.meta.yaml in: {missing}")

    def test_meta_has_required_fields(self) -> None:
        for tech_dir in self._tech_dirs():
            meta = (tech_dir / "skill.meta.yaml").read_text(encoding="utf-8")
            for field in self.REQUIRED_FIELDS:
                self.assertIn(f"{field}:", meta,
                              f"{tech_dir.relative_to(REPO_ROOT)}/skill.meta.yaml missing field '{field}'")

    def test_reviewed_at_format(self) -> None:
        pattern = re.compile(r"^reviewed_at:\s*['\"]?(\d{4}-\d{2}-\d{2})['\"]?", re.MULTILINE)
        for tech_dir in self._tech_dirs():
            meta = (tech_dir / "skill.meta.yaml").read_text(encoding="utf-8")
            m = pattern.search(meta)
            self.assertIsNotNone(m, f"{tech_dir.name}/skill.meta.yaml: reviewed_at missing or wrong format")

    def test_domain_matches_directory(self) -> None:
        for tech_dir in self._tech_dirs():
            expected_domain = tech_dir.parent.name
            meta = (tech_dir / "skill.meta.yaml").read_text(encoding="utf-8")
            m = re.search(r"^domain:\s*['\"]?(\S+?)['\"]?\s*$", meta, re.MULTILINE)
            self.assertIsNotNone(m, f"{tech_dir.name}: domain field not found")
            self.assertEqual(m.group(1), expected_domain,
                             f"{tech_dir.name}: domain '{m.group(1)}' != dir '{expected_domain}'")

    def test_name_matches_directory(self) -> None:
        for tech_dir in self._tech_dirs():
            expected_name = tech_dir.name
            meta = (tech_dir / "skill.meta.yaml").read_text(encoding="utf-8")
            m = re.search(r"^name:\s*['\"]?(\S+?)['\"]?\s*$", meta, re.MULTILINE)
            self.assertIsNotNone(m, f"{tech_dir.name}: name field not found")
            self.assertEqual(m.group(1), expected_name,
                             f"{tech_dir.name}: name '{m.group(1)}' != dir '{expected_name}'")


class SkillContentTests(unittest.TestCase):
    """Verify that technology skill documents contain no placeholder markers."""

    SKILLS_ROOT = REPO_ROOT / ".ai" / "skills"
    PLACEHOLDER_PATTERN = re.compile(r"PLACEHOLDER|not yet written|generic kit template", re.IGNORECASE)

    def _tech_docs(self) -> list[Path]:
        docs = []
        for domain_dir in self.SKILLS_ROOT.iterdir():
            if not domain_dir.is_dir() or domain_dir.name == "core":
                continue
            for tech_dir in domain_dir.iterdir():
                if not tech_dir.is_dir():
                    continue
                for doc in ("overview", "patterns", "best-practices", "pitfalls", "examples"):
                    path = tech_dir / f"{doc}.md"
                    if path.exists():
                        docs.append(path)
        return sorted(docs)

    def test_no_placeholder_in_skill_docs(self) -> None:
        flagged = []
        for path in self._tech_docs():
            text = path.read_text(encoding="utf-8")
            if self.PLACEHOLDER_PATTERN.search(text):
                flagged.append(str(path.relative_to(REPO_ROOT)))
        self.assertEqual(flagged, [], f"Placeholder content found in: {flagged}")


if __name__ == "__main__":
    unittest.main()
