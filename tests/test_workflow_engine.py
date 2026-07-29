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


if __name__ == "__main__":
    unittest.main()
