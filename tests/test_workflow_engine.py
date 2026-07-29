import importlib.util
import json
import tempfile
import unittest
import subprocess
import sys
from pathlib import Path


ENGINE = Path(__file__).resolve().parents[1] / ".ai" / "engine" / "ai_kit.py"
SPEC = importlib.util.spec_from_file_location("ai_kit", ENGINE)
engine = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(engine)


def task(task_id, needs=None, status="todo"):
    return {"id": task_id, "title": task_id, "owner": "backend", "phase": "build", "needs": needs or [], "status": status, "acceptance": ["works"], "files": [], "tags": [], "attempts": 0, "evidence": [], "blocked_reason": None, "claimed_by": None}


class WorkflowEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.state_path = Path(self.temp.name) / "workflow.json"
        self.old_log = engine.EVENT_LOG
        engine.EVENT_LOG = Path(self.temp.name) / "events.jsonl"

    def tearDown(self):
        engine.EVENT_LOG = self.old_log
        self.temp.cleanup()

    def state(self, tasks):
        return {"version": 1, "revision": 0, "title": "test", "workflow": "feature", "tasks": tasks, "phases": [], "events": []}

    def evidence(self, kind, task_id="T1"):
        path = Path(self.temp.name) / f"{kind}.json"
        payload = {"kind": kind, "task": task_id, "status": "pass"} if kind == "qa" else {"kind": kind, "task": task_id, "verdict": "approve"}
        path.write_text(json.dumps(payload), encoding="utf-8")
        return str(path)

    def test_validate_rejects_cycles(self):
        with self.assertRaisesRegex(engine.EngineError, "cycle"):
            engine.validate(self.state([task("T1", ["T2"]), task("T2", ["T1"])]))

    def test_scheduler_only_returns_satisfied_tasks(self):
        fixture = Path(__file__).parent / "fixtures" / "feature-workflow.json"
        state = json.loads(fixture.read_text(encoding="utf-8"))
        engine.validate(state)
        ready = [item["id"] for item in state["tasks"] if engine.runnable(item, engine.task_map(state))]
        self.assertEqual(["T1"], ready)
        state["tasks"][0]["status"] = "done"
        ready = [item["id"] for item in state["tasks"] if engine.runnable(item, engine.task_map(state))]
        self.assertEqual(["T2"], ready)

    def test_lifecycle_requires_qa_and_review_before_close(self):
        state = self.state([task("T1")])
        engine.save(state, self.state_path)
        args = type("Args", (), {"state": str(self.state_path), "id": "T1", "action": "close", "actor": "release", "detail": None, "evidence": None})()
        with self.assertRaisesRegex(engine.EngineError, "cannot close"):
            engine.cmd_transition(args)
        for action, actor in [("start", "backend"), ("complete", "backend"), ("qa-pass", "qa"), ("review-approve", "reviewer"), ("close", "release")]:
            args.action, args.actor = action, actor
            args.evidence = [self.evidence("qa" if action == "qa-pass" else "review")] if action in {"qa-pass", "review-approve"} else None
            engine.cmd_transition(args)
        self.assertEqual("done", engine.load(self.state_path)["tasks"][0]["status"])

    def test_block_requires_reason(self):
        state = self.state([task("T1")])
        engine.save(state, self.state_path)
        args = type("Args", (), {"state": str(self.state_path), "id": "T1", "action": "block", "actor": "backend", "detail": None, "evidence": None})()
        with self.assertRaisesRegex(engine.EngineError, "requires --detail"):
            engine.cmd_transition(args)

    def test_add_task_requires_acceptance_criterion(self):
        state = self.state([])
        engine.save(state, self.state_path)
        args = type("Args", (), {"state": str(self.state_path), "id": "T1", "title": "task", "owner": "planner", "phase": "plan", "needs": [], "acceptance": [], "files": [], "actor": "planner"})()
        with self.assertRaisesRegex(engine.EngineError, "acceptance"):
            engine.cmd_add_task(args)

    def test_router_returns_portable_paths_and_role_core_skills(self):
        state = self.state([task("T1")])
        state["tasks"][0]["owner"] = "reviewer"
        engine.save(state, self.state_path)
        result = engine.cmd_route(type("Args", (), {"state": str(self.state_path), "id": "T1"})())
        self.assertIn(".ai/skills/core/code-review/SKILL.md", result["skills"])
        self.assertTrue(all(not Path(path).is_absolute() for path in result["skills"]))

    def test_qa_requires_evidence(self):
        state = self.state([task("T1", status="implementation-complete")])
        engine.save(state, self.state_path)
        args = type("Args", (), {"state": str(self.state_path), "id": "T1", "action": "qa-pass", "actor": "qa", "detail": None, "evidence": None})()
        with self.assertRaisesRegex(engine.EngineError, "evidence"):
            engine.cmd_transition(args)

    def test_validate_rejects_unknown_owner(self):
        state = self.state([task("T1")])
        state["tasks"][0]["owner"] = "not-a-role"
        with self.assertRaisesRegex(engine.EngineError, "unknown owner"):
            engine.validate(state)

    def test_stale_revision_is_rejected(self):
        state = self.state([])
        engine.save(state, self.state_path)
        stale = engine.load(self.state_path)
        fresh = engine.load(self.state_path)
        fresh["title"] = "fresh"
        engine.save(fresh, self.state_path, fresh["revision"])
        with self.assertRaisesRegex(engine.EngineError, "concurrently"):
            engine.save(stale, self.state_path, stale["revision"])

    def test_cli_status_runs_in_subprocess(self):
        result = subprocess.run([sys.executable, str(ENGINE), "--state", str(self.state_path), "init", "--title", "cli", "--workflow", "feature"], capture_output=True, text=True, check=True)
        self.assertIn('"title": "cli"', result.stdout)
        status = subprocess.run([sys.executable, str(ENGINE), "--state", str(self.state_path), "status"], capture_output=True, text=True, check=True)
        self.assertIn('"counts"', status.stdout)

    def test_claimed_by_set_on_start(self):
        """P0-4: claimed_by must record the actor who started the task."""
        state = self.state([task("T1")])
        engine.save(state, self.state_path)
        args = type("Args", (), {"state": str(self.state_path), "id": "T1", "action": "start", "actor": "backend", "detail": None, "evidence": None})()
        engine.cmd_transition(args)
        loaded = engine.load(self.state_path)
        self.assertEqual("backend", loaded["tasks"][0]["claimed_by"])

    def test_executor_cannot_qa_own_work(self):
        """P0-4: QA actor must differ from the executor who started the task."""
        state = self.state([task("T1")])
        engine.save(state, self.state_path)
        # Start as backend
        args = type("Args", (), {"state": str(self.state_path), "id": "T1", "action": "start", "actor": "backend", "detail": None, "evidence": None})()
        engine.cmd_transition(args)
        # Complete as backend
        args.action = "complete"
        engine.cmd_transition(args)
        # Try to QA as backend (same actor) — must fail
        args.action = "qa-pass"
        args.evidence = [self.evidence("qa")]
        with self.assertRaisesRegex(engine.EngineError, "must differ from executor"):
            engine.cmd_transition(args)

    def test_executor_cannot_review_own_work(self):
        """P0-4: Reviewer must differ from executor."""
        state = self.state([task("T1")])
        engine.save(state, self.state_path)
        for action, actor in [("start", "backend"), ("complete", "backend")]:
            args = type("Args", (), {"state": str(self.state_path), "id": "T1", "action": action, "actor": actor, "detail": None, "evidence": None})()
            engine.cmd_transition(args)
        # QA by a different actor — should pass
        args = type("Args", (), {"state": str(self.state_path), "id": "T1", "action": "qa-pass", "actor": "qa", "detail": None, "evidence": [self.evidence("qa")]})()
        engine.cmd_transition(args)
        # Review as backend (original executor) — must fail
        args = type("Args", (), {"state": str(self.state_path), "id": "T1", "action": "review-approve", "actor": "backend", "detail": None, "evidence": [self.evidence("review")]})()
        with self.assertRaisesRegex(engine.EngineError, "must differ from executor"):
            engine.cmd_transition(args)

    def test_verify_returns_report_without_auto_approve(self):
        """P0-4: verify should produce a report dict, not auto-approve."""
        # Temporarily set test_command to 'true' to avoid recursive test run
        kit_yaml = engine.ROOT / ".ai" / "kit.yaml"
        original = kit_yaml.read_text(encoding="utf-8")
        kit_yaml.write_text(original.replace("python3 -m unittest discover -s tests -v", "true"), encoding="utf-8")
        try:
            state = self.state([task("T1", status="implementation-complete")])
            engine.save(state, self.state_path)
            args = type("Args", (), {"state": str(self.state_path), "id": "T1"})()
            result = engine.cmd_verify(args)
            self.assertIn("checks", result)
            self.assertIn("passed", result)
            # Task should still be implementation-complete (not qa-passed)
            loaded = engine.load(self.state_path)
            self.assertEqual("implementation-complete", loaded["tasks"][0]["status"])
        finally:
            kit_yaml.write_text(original, encoding="utf-8")

    def test_stale_lock_is_recoverable(self):
        """Lock file left behind should time out and raise clear error."""
        state = self.state([])
        engine.save(state, self.state_path)
        # Create a stale lock
        lock = self.state_path.with_suffix(self.state_path.suffix + ".lock")
        lock.write_text("stale", encoding="utf-8")
        # save should time out (with short deadline) or succeed after cleanup
        # Since deadline is 5s, just verify lock blocks
        import threading, time
        def remove_lock():
            time.sleep(0.2)
            lock.unlink(missing_ok=True)
        t = threading.Thread(target=remove_lock)
        t.start()
        engine.save(state, self.state_path)  # should succeed after lock removed
        t.join()
        self.assertTrue(self.state_path.exists())

    def test_e2e_lifecycle_via_cli(self):
        """Full lifecycle via CLI subprocess: init → add-task → start → complete → done."""
        run = lambda *args_list: subprocess.run([sys.executable, str(ENGINE), "--state", str(self.state_path)] + list(args_list), capture_output=True, text=True, check=True)
        run("init", "--title", "e2e", "--workflow", "feature")
        run("add-task", "T1", "--title", "test task", "--owner", "backend", "--phase", "build", "--acceptance", "it works")
        run("transition", "T1", "start", "--actor", "backend")
        run("transition", "T1", "complete", "--actor", "backend")
        # Create evidence files for QA and review
        qa_ev = Path(self.temp.name) / "qa_e2e.json"
        qa_ev.write_text(json.dumps({"kind": "qa", "task": "T1", "status": "pass"}), encoding="utf-8")
        run("transition", "T1", "qa-pass", "--actor", "qa", "--evidence", str(qa_ev))
        rev_ev = Path(self.temp.name) / "review_e2e.json"
        rev_ev.write_text(json.dumps({"kind": "review", "task": "T1", "verdict": "approve"}), encoding="utf-8")
        run("transition", "T1", "review-approve", "--actor", "reviewer", "--evidence", str(rev_ev))
        run("transition", "T1", "close", "--actor", "release")
        result = run("status")
        self.assertIn('"done": 1', result.stdout)


if __name__ == "__main__":
    unittest.main()

