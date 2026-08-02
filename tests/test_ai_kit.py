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


class UnterminatedListGuardTests(EngineTestCase):
    """Every YAML reader here is line-based, so a `[...]` array wrapped onto
    a second line is not unsupported-but-obvious: it is silently stored as
    the first line's raw text, and the affected trigger/role simply stops
    matching with no error. These assert it now raises instead."""

    def _registry(self, body: str) -> None:
        (self.root / ".ai-config" / "registry.yaml").write_text(body, encoding="utf-8")

    def test_wrapped_trigger_match_list_raises(self) -> None:
        self._registry(
            "skill_triggers:\n"
            "  demo:\n"
            '    match: ["one", "two",\n'
            '            "three"]\n'
            '    core_skills: ["security-review"]\n'
        )
        with self.assertRaises(ai_kit.EngineError) as ctx:
            ai_kit._load_skill_triggers()
        self.assertIn("demo.match", str(ctx.exception))
        self.assertIn("one line", str(ctx.exception))

    def test_wrapped_owners_list_raises(self) -> None:
        """A wrapped owners list used to fail the regex and drop the role
        entirely, so that role silently routed no technology skills."""
        self._registry("owners:\n  backend: [backend,\n            database]\n")
        with self.assertRaises(ai_kit.EngineError) as ctx:
            ai_kit._load_registry()
        self.assertIn("owners.backend", str(ctx.exception))

    def test_wrapped_skill_meta_list_raises(self) -> None:
        skill_dir = self.root / ".ai" / "skills" / "backend" / "demo"
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "skill.meta.yaml").write_text(
            "name: demo\ndomain: backend\ndocuments: [overview.md,\n           patterns.md]\n",
            encoding="utf-8",
        )
        with self.assertRaises(ai_kit.EngineError) as ctx:
            ai_kit._load_skill_metadata(skill_dir)
        self.assertIn("documents", str(ctx.exception))

    def test_single_line_lists_still_parse(self) -> None:
        self._registry(
            "skill_triggers:\n"
            "  demo:\n"
            '    match: ["one", "two", "three"]\n'
            '    core_skills: ["security-review"]\n'
        )
        triggers = ai_kit._load_skill_triggers()
        self.assertEqual(triggers["demo"]["match"], ["one", "two", "three"])


class VerificationGateTests(EngineTestCase):
    """G2 requires evidence the acceptance criteria hold. With every
    verification command left at kit.yaml's 'true' sentinel, nothing
    functional runs -- verify used to report passed=True on the strength of
    a secret scan alone, which let `pipeline` auto-approve QA, auto-approve
    review, and close the task with no functional evidence at all."""

    def _kit_yaml(self, verification: str) -> None:
        (self.root / ".ai-config" / "kit.yaml").write_text(
            f"project:\n  stack: []\n\nverification:\n{verification}", encoding="utf-8"
        )

    def _task_at_implementation_complete(self) -> None:
        self.init_workflow()
        self.add_task("T1")
        self.transition("T1", "start", actor="backend")
        self.transition("T1", "complete", actor="backend")

    def test_no_configured_checks_is_inconclusive_not_passed(self) -> None:
        self._kit_yaml(
            "  test_command: true\n  typecheck_command: true\n"
            "  build_command: true\n  lint_command: true\n"
        )
        self._task_at_implementation_complete()
        report = ai_kit.cmd_verify(ns(state=str(self.state_file), id="T1"))
        self.assertFalse(report["passed"])
        self.assertTrue(report["inconclusive"])
        self.assertIn("warning", report)
        self.assertTrue(all(c["status"] == "skipped" for c in report["checks"]
                            if c["name"].endswith("_command")))

    def test_a_configured_passing_check_is_conclusive(self) -> None:
        self._kit_yaml(
            "  test_command: true\n  typecheck_command: true\n"
            "  build_command: true\n  lint_command: exit 0\n"
        )
        self._task_at_implementation_complete()
        report = ai_kit.cmd_verify(ns(state=str(self.state_file), id="T1"))
        self.assertTrue(report["passed"])
        self.assertNotIn("inconclusive", report)

    def test_a_configured_failing_check_fails_not_inconclusive(self) -> None:
        """A real failure must stay distinguishable from 'nothing ran'."""
        self._kit_yaml(
            "  test_command: exit 1\n  typecheck_command: true\n"
            "  build_command: true\n  lint_command: true\n"
        )
        self._task_at_implementation_complete()
        report = ai_kit.cmd_verify(ns(state=str(self.state_file), id="T1"))
        self.assertFalse(report["passed"])
        self.assertNotIn("inconclusive", report)


class VerifyExitCodeTests(unittest.TestCase):
    """`ai-kit verify` must exit non-zero unless the report says passed.

    It used to exit 0 for every verdict, because main() only returns non-zero
    on EngineError and cmd_verify reports a verdict rather than raising. That
    made it useless as a shell gate: dispatch-full.sh's
    `if ! "$AI_KIT" verify ...` never fired, so a task whose checks FAILED was
    auto-approved through QA and review and closed at `done` -- the same
    vacuous-gate bug already fixed inside `pipeline`, but in the shell path.

    Driven through the real CLI (subprocess), since the exit code is the whole
    point and an in-process call to cmd_verify would not exercise it.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        for role in ("planner", "backend", "qa", "reviewer"):
            (self.root / ".ai" / "agents" / role).mkdir(parents=True, exist_ok=True)
        (self.root / ".ai" / "workflows" / "feature").mkdir(parents=True, exist_ok=True)
        (self.root / ".ai" / "engine").mkdir(parents=True, exist_ok=True)
        (self.root / ".ai" / "engine" / "ai_kit.py").write_bytes(
            (ENGINE_DIR / "ai_kit.py").read_bytes())
        (self.root / ".ai-config").mkdir(parents=True, exist_ok=True)
        self.state = self.root / "work" / "state" / "workflow.json"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(self.root / ".ai" / "engine" / "ai_kit.py"),
             "--state", str(self.state), *args],
            capture_output=True, text=True, cwd=str(self.root),
        )

    def _prepare(self, verification: str) -> None:
        (self.root / ".ai-config" / "kit.yaml").write_text(
            f"project:\n  stack: []\n\nverification:\n{verification}", encoding="utf-8")
        self._run("init", "--title", "t", "--workflow", "feature", "--actor", "planner")
        self._run("add-task", "T1", "--title", "t", "--owner", "backend",
                  "--phase", "build", "--acceptance", "ok")
        self._run("transition", "T1", "start", "--actor", "backend")
        self._run("transition", "T1", "complete", "--actor", "backend")

    def test_exits_zero_when_passed(self) -> None:
        self._prepare("  test_command: exit 0\n  typecheck_command: true\n"
                      "  build_command: true\n  lint_command: true\n")
        result = self._run("verify", "T1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"passed": true', result.stdout)

    def test_exits_nonzero_when_a_check_fails(self) -> None:
        self._prepare("  test_command: exit 1\n  typecheck_command: true\n"
                      "  build_command: true\n  lint_command: true\n")
        result = self._run("verify", "T1")
        self.assertNotEqual(result.returncode, 0,
                            "verify reported FAIL but exited 0; every shell gate on it is a no-op")
        self.assertIn('"passed": false', result.stdout)

    def test_exits_nonzero_when_inconclusive(self) -> None:
        """Nothing functional ran, so there is no G2 evidence to proceed on."""
        self._prepare("  test_command: true\n  typecheck_command: true\n"
                      "  build_command: true\n  lint_command: true\n")
        result = self._run("verify", "T1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('"inconclusive": true', result.stdout)

    def test_report_is_still_printed_in_full_on_failure(self) -> None:
        """The exit code changed; the stdout contract did not."""
        self._prepare("  test_command: exit 1\n  typecheck_command: true\n"
                      "  build_command: true\n  lint_command: true\n")
        report = json.loads(self._run("verify", "T1").stdout)
        self.assertEqual(report["task"], "T1")
        self.assertTrue(report["checks"])

    def test_other_commands_still_exit_zero(self) -> None:
        """Only verify's exit status is verdict-dependent."""
        self._prepare("  test_command: exit 1\n  typecheck_command: true\n"
                      "  build_command: true\n  lint_command: true\n")
        for command in (("show",), ("ready",), ("status",), ("timeline",)):
            with self.subTest(command=command[0]):
                self.assertEqual(self._run(*command).returncode, 0)


class LocalScriptContractTests(unittest.TestCase):
    """The helper scripts in .ai/scripts/ are the kit's local QA surface."""

    SCRIPTS = REPO_ROOT / ".ai" / "scripts"

    def test_new_task_and_next_task_are_not_duplicates(self) -> None:
        """new-task.sh used to be a byte-for-byte duplicate of next-task.sh:
        it ran `ai-kit ready`, listing existing work and creating nothing,
        despite its name."""
        new_task = (self.SCRIPTS / "new-task.sh").read_text(encoding="utf-8")
        next_task = (self.SCRIPTS / "next-task.sh").read_text(encoding="utf-8")
        self.assertNotEqual(new_task, next_task)
        self.assertIn("add-task", new_task, "new-task.sh should create a task")
        self.assertIn("ready", next_task, "next-task.sh should list ready work")

    def test_new_task_rejects_missing_arguments(self) -> None:
        result = subprocess.run(["bash", str(self.SCRIPTS / "new-task.sh"), "T9"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("usage:", result.stderr)

    def test_dispatch_full_gates_on_the_verify_verdict(self) -> None:
        """Guards the fix: the script must not treat verify's output as a
        pass without checking it."""
        script = (self.SCRIPTS / "dispatch-full.sh").read_text(encoding="utf-8")
        self.assertIn('"passed": true', script,
                      "dispatch-full.sh must inspect the verify verdict, not just its exit code")


class RealRegistryTriggerTests(unittest.TestCase):
    """Exercises the REAL .ai-config/registry.yaml and its install-template
    copy, not a synthetic fixture -- because the bug this guards against
    lives in the YAML content itself. _load_yaml_registry() is a simple
    line-based parser: a `match`/`core_skills`/`technology_skills` array
    split across multiple physical lines is silently mis-parsed into a
    single unmatchable string, with no error. A synthetic single-line
    fixture (see RoutingAndSkillMetadataTests) would never catch that
    regression, since nothing forces it to stay in sync with how someone
    actually edits the real file.
    """

    REGISTRY_FILES = (
        REPO_ROOT / ".ai-config" / "registry.yaml",
        REPO_ROOT / ".ai" / "install" / "config" / "registry.yaml",
    )

    # AGENTS.md's mandatory-concerns table, plus the split-out AI-cost
    # trigger: each entry is (trigger id, a phrase it must match, a core
    # skill it must pull in).
    EXPECTED_TRIGGERS = [
        ("auth-security", "oauth", "security-review"),
        ("auth-security", "credential", "threat-modeling"),
        ("ui-interaction", "button", "accessibility"),
        ("ui-interaction", "accessibility", "frontend-core"),
        ("dependency-change", "upgrade", "dependency-management"),
        ("performance-latency", "latency", "performance-profiling"),
        ("performance-latency", "throughput", "observability"),
        ("ai-cost-token", "token budget", "performance-profiling"),
        ("ai-cost-token", "llm cost", "observability"),
        ("coordination-handoff", "handoff", "workflow-orchestration"),
        ("coordination-handoff", "parallel task", "workflow-orchestration"),
        ("user-journey-boundary", "user journey", "e2e-testing"),
        ("user-journey-boundary", "public api", "contract-testing"),
        ("architecture-tradeoff", "cross-cutting", "architecture-decisions"),
        ("architecture-tradeoff", "trade-off", "architecture-decisions"),
    ]

    def _load_triggers_from(self, registry_path: Path) -> dict:
        """Parse skill_triggers from an arbitrary registry.yaml using the
        engine's own real parser, by staging it where _config_path expects
        the active project's config (so this exercises the exact code path
        `route` uses in production, not a reimplementation of it)."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".ai-config").mkdir()
            (root / ".ai-config" / "registry.yaml").write_bytes(registry_path.read_bytes())
            saved_root = ai_kit.ROOT
            ai_kit.ROOT = root
            try:
                return ai_kit._load_skill_triggers()
            finally:
                ai_kit.ROOT = saved_root

    def test_expected_triggers_present_with_working_match_terms(self) -> None:
        for registry_path in self.REGISTRY_FILES:
            triggers = self._load_triggers_from(registry_path)
            for trigger_id, phrase, core_skill in self.EXPECTED_TRIGGERS:
                with self.subTest(registry=registry_path.relative_to(REPO_ROOT), trigger=trigger_id, phrase=phrase):
                    self.assertIn(trigger_id, triggers, f"trigger '{trigger_id}' missing from {registry_path}")
                    trigger = triggers[trigger_id]
                    self.assertIn(
                        phrase, trigger["match"],
                        f"'{phrase}' not in {trigger_id}.match -- if this trigger's YAML array was "
                        f"line-wrapped, the parser silently drops everything after the first line",
                    )
                    self.assertIn(core_skill, trigger["core_skills"])

    def test_auth_trigger_does_not_pull_in_ai_cost_skills(self) -> None:
        """Regression: a single "latency-cost-token" trigger used to match
        bare "token", so an OAuth task mentioning "token refresh" pulled in
        ai/ai-cost-management purely by accident."""
        for registry_path in self.REGISTRY_FILES:
            triggers = self._load_triggers_from(registry_path)
            auth_matches = triggers["auth-security"]["match"]
            for term in auth_matches:
                for ai_trigger_id in ("ai-cost-token",):
                    ai_terms = triggers[ai_trigger_id]["match"]
                    self.assertFalse(
                        any(term in ai_term or ai_term in term for ai_term in ai_terms),
                        f"auth-security match term '{term}' overlaps with {ai_trigger_id} "
                        f"match terms {ai_terms} in {registry_path}",
                    )

    def test_performance_latency_trigger_has_no_ai_technology_skills(self) -> None:
        """The generic Performance row in AGENTS.md's mandatory-concerns
        table does not require AI skills; only ai-cost-token (LLM-specific
        token/cost phrasing) should pull those in."""
        for registry_path in self.REGISTRY_FILES:
            triggers = self._load_triggers_from(registry_path)
            self.assertEqual(triggers["performance-latency"]["technology_skills"], [])
            self.assertTrue(triggers["ai-cost-token"]["technology_skills"])

    def test_no_dead_ai_triggers_block(self) -> None:
        """ai_triggers: was documented in skill-router/SKILL.md as live
        engine behavior ("routes the ai domain... automatically when the
        stack includes an AI technology") but no script or engine code ever
        read it -- skills-for.sh and _load_registry() both resolve AI
        routing from the static owners: list instead. Removed as dead
        config; this pins it gone so it can't quietly come back without
        someone also wiring it up."""
        for registry_path in self.REGISTRY_FILES:
            text = registry_path.read_text(encoding="utf-8")
            self.assertNotIn("ai_triggers:", text, f"dead ai_triggers: block reintroduced in {registry_path}")

    def test_owners_section_matches_between_registry_copies(self) -> None:
        """Regression: the install-template copy was missing 'ai' from
        owners.{architect,qa,security,integration,performance} even though
        the live .ai-config/registry.yaml had it -- a fresh install would
        route less than the repo it was copied from."""
        live_owners = self._load_owners_from(self.REGISTRY_FILES[0])
        template_owners = self._load_owners_from(self.REGISTRY_FILES[1])
        self.assertEqual(live_owners, template_owners)

    def _load_owners_from(self, registry_path: Path) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".ai-config").mkdir()
            (root / ".ai-config" / "registry.yaml").write_bytes(registry_path.read_bytes())
            saved_root = ai_kit.ROOT
            ai_kit.ROOT = root
            try:
                return ai_kit._load_registry()["owners"]
            finally:
                ai_kit.ROOT = saved_root


class RegistryEndToEndRoutingTests(EngineTestCase):
    """Runs cmd_route against the REAL registry.yaml and REAL .ai/skills
    tree (only the workflow state file is isolated), so these assert what
    an actual `ai-kit route` invocation would return -- not what a
    synthetic fixture says it should."""

    def setUp(self) -> None:
        super().setUp()
        # Point role/skill/config lookups at the real repo; only the
        # workflow state itself stays in the isolated temp dir.
        ai_kit.ROOT = REPO_ROOT

    def _route(self, task_id: str) -> dict:
        return ai_kit.cmd_route(ns(state=str(self.state_file), id=task_id))

    def test_auth_task_routes_to_security(self) -> None:
        self.init_workflow()
        self.add_task("T1", title="Add OAuth login endpoint with token refresh", owner="backend")
        skills = self._route("T1")["skills"]
        self.assertTrue(any("security-review" in s for s in skills), skills)
        self.assertTrue(any("threat-modeling" in s for s in skills), skills)
        self.assertFalse(any("/ai/" in s for s in skills), f"unexpected AI skills: {skills}")

    def test_ui_task_routes_to_accessibility(self) -> None:
        self.init_workflow()
        self.add_task("T1", title="Redesign checkout button and modal interaction", owner="frontend")
        skills = self._route("T1")["skills"]
        self.assertTrue(any("accessibility" in s for s in skills), skills)

    def test_dependency_task_routes_to_dependency_management(self) -> None:
        self.init_workflow()
        self.add_task("T1", title="Bump lodash and axios to latest versions", owner="devops")
        skills = self._route("T1")["skills"]
        self.assertTrue(any("dependency-management" in s for s in skills), skills)

    def test_generic_latency_task_does_not_pull_ai_skills(self) -> None:
        self.init_workflow()
        self.add_task("T1", title="Optimize slow dashboard query p95 latency", owner="backend")
        skills = self._route("T1")["skills"]
        self.assertTrue(any("performance-profiling" in s for s in skills), skills)
        self.assertFalse(any("/ai/" in s for s in skills), f"unexpected AI skills: {skills}")

    def test_llm_cost_task_still_pulls_ai_skills(self) -> None:
        self.init_workflow()
        self.add_task("T1", title="Reduce LLM token budget and inference cost per request", owner="backend")
        skills = self._route("T1")["skills"]
        self.assertTrue(any("ai-cost-management" in s for s in skills), skills)
        self.assertTrue(any("llm-observability" in s for s in skills), skills)

    def test_parallel_handoff_task_routes_to_workflow_orchestration(self) -> None:
        self.init_workflow()
        self.add_task("T1", title="Coordinate three parallel workers with a handoff after retry", owner="backend")
        skills = self._route("T1")["skills"]
        self.assertTrue(any("workflow-orchestration" in s for s in skills), skills)

    def test_user_journey_task_routes_to_e2e_and_contract_testing(self) -> None:
        self.init_workflow()
        self.add_task("T1", title="Verify the checkout user journey across the public API boundary", owner="qa")
        skills = self._route("T1")["skills"]
        self.assertTrue(any("e2e-testing" in s for s in skills), skills)
        self.assertTrue(any("contract-testing" in s for s in skills), skills)

    def test_architecture_tradeoff_task_routes_to_architecture_decisions(self) -> None:
        self.init_workflow()
        self.add_task("T1", title="Decide on a cross-cutting architectural trade-off for caching", owner="architect")
        skills = self._route("T1")["skills"]
        self.assertTrue(any("architecture-decisions" in s for s in skills), skills)

    def test_ai_owner_roles_get_ai_domain_skills_when_relevant(self) -> None:
        """Regression: the install-template copy of registry.yaml was missing
        'ai' from owners.{architect,qa,security,integration,performance},
        even though the live .ai-config/registry.yaml had it -- a fresh
        install silently routed less than the repo it was copied from."""
        self.init_workflow()
        for role in ("architect", "qa", "security", "integration", "performance"):
            registry = ai_kit._load_registry()
            self.assertIn("ai", registry["owners"].get(role, []), f"role '{role}' missing 'ai' in owners")


if __name__ == "__main__":
    unittest.main()
