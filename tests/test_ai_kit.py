"""Unit tests for the AI-Kit v2 control-plane engine (.ai/engine/ai_kit.py).

Every test runs against a throwaway temp directory: ai_kit.ROOT and the
module-level path constants derived from it are monkeypatched per test so
nothing here ever touches this repository's real .ai-work/, .ai-config/, or
.visualizer/ state.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parents[1] / ".ai" / "engine"
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


if __name__ == "__main__":
    unittest.main()
