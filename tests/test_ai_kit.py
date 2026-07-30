import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / ".ai" / "engine" / "ai_kit.py"


class AiKitCliTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.state = self.root / "state" / "workflow.json"
        self.state.parent.mkdir()

    def tearDown(self):
        self.temp_dir.cleanup()

    def run_cli(self, *arguments, check=True):
        result = subprocess.run(
            [sys.executable, "-B", str(ENGINE), "--state", str(self.state), *arguments],
            cwd=ROOT,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            capture_output=True,
            text=True,
        )
        if check and result.returncode != 0:
            self.fail(f"CLI failed ({result.returncode}): {result.stderr}\n{result.stdout}")
        return result

    def init(self):
        return self.run_cli("init", "--title", "test workflow", "--workflow", "feature")

    def add_task(self, task_id="T1", needs=None, **extra):
        args = [
            "add-task", task_id, "--title", extra.pop("title", task_id),
            "--owner", extra.pop("owner", "backend"), "--phase", extra.pop("phase", "build"),
            "--acceptance", extra.pop("acceptance", "behavior is verified"),
        ]
        if needs:
            args.extend(["--needs", *needs])
        for option, value in extra.items():
            if option == "--depends-on":
                paths = [value] if isinstance(value, str) else value
                for path in paths:
                    args.extend([option, path])
            else:
                args.extend([option, value])
        return self.run_cli(*args)

    def read_state(self):
        return json.loads(self.state.read_text())

    def test_plan_writes_only_to_custom_workspace(self):
        self.run_cli(
            "plan", "--idea", "isolated tests", "--owner", "backend",
            "--acceptance", "test command passes",
        )

        state = self.read_state()
        self.assertEqual([task["id"] for task in state["tasks"]], ["T1", "T2"])
        workspace = self.root
        self.assertTrue((workspace / "tasks" / "tasks.md").exists())
        self.assertNotEqual(self.state, ROOT / ".ai-work" / "state" / "workflow.json")

    def test_dependency_blocks_start_until_upstream_is_complete(self):
        self.init()
        self.add_task("T1")
        self.add_task("T2", needs=["T1"])

        blocked = self.run_cli("transition", "T2", "start", "--actor", "backend", check=False)
        self.assertEqual(blocked.returncode, 2)
        self.assertIn("unfinished dependencies", blocked.stderr)

        self.run_cli("transition", "T1", "start", "--actor", "planner")
        self.run_cli("transition", "T1", "complete", "--actor", "planner")
        self.run_cli("approve", "T1", "--role", "qa", "--reason", "verified")
        self.run_cli("approve", "T1", "--role", "review", "--reason", "approved")
        self.run_cli("transition", "T1", "close", "--actor", "reviewer")
        ready = json.loads(self.run_cli("ready").stdout)
        self.assertEqual([task["id"] for task in ready], ["T2"])

    def test_lifecycle_requires_valid_independent_evidence(self):
        self.init()
        self.add_task("T1")
        self.run_cli("transition", "T1", "start", "--actor", "backend")
        self.run_cli("transition", "T1", "complete", "--actor", "backend")

        missing = self.run_cli(
            "transition", "T1", "qa-pass", "--actor", "qa", check=False
        )
        self.assertEqual(missing.returncode, 2)
        self.assertIn("requires at least one --evidence", missing.stderr)

        qa_evidence = self.root / "qa.json"
        qa_evidence.write_text(json.dumps({"kind": "qa", "task": "T1", "status": "pass"}))
        review_evidence = self.root / "review.json"
        review_evidence.write_text(json.dumps({"kind": "review", "task": "T1", "verdict": "approve"}))
        self.run_cli("transition", "T1", "qa-pass", "--actor", "qa", "--evidence", str(qa_evidence))
        self.run_cli("transition", "T1", "review-approve", "--actor", "reviewer", "--evidence", str(review_evidence))
        self.run_cli("transition", "T1", "close", "--actor", "reviewer")
        self.assertEqual(self.read_state()["tasks"][0]["status"], "done")

    def test_executor_cannot_self_review(self):
        self.init()
        self.add_task("T1")
        self.run_cli("transition", "T1", "start", "--actor", "backend")
        self.run_cli("transition", "T1", "complete", "--actor", "backend")
        evidence = self.root / "qa.json"
        evidence.write_text(json.dumps({"kind": "qa", "task": "T1", "status": "pass"}))
        result = self.run_cli(
            "transition", "T1", "qa-pass", "--actor", "backend", "--evidence", str(evidence), check=False
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("must differ from executor", result.stderr)

    def test_contract_drift_reports_changed_and_missing_files(self):
        self.init()
        contract = self.root / "contract.md"
        contract.write_text("version: 1\n")
        self.add_task("T1", **{"--depends-on": str(contract)})
        clean = json.loads(self.run_cli("drift", "T1").stdout)
        self.assertEqual(clean["contract_stale"], [])

        contract.write_text("version: 2\n")
        changed = json.loads(self.run_cli("drift", "T1").stdout)
        self.assertEqual(changed["contract_stale"], [str(contract)])

        contract.unlink()
        missing = json.loads(self.run_cli("drift", "T1").stdout)
        self.assertEqual(missing["contract_stale"], [str(contract)])

    def test_board_has_all_status_columns_and_is_written_to_workspace(self):
        self.init()
        self.add_task("T1", title="Blocked task")
        self.run_cli("transition", "T1", "block", "--actor", "backend", "--detail", "waiting")

        board = json.loads(self.run_cli("board").stdout)
        expected = {"todo", "in-progress", "implementation-complete", "qa-passed", "review-approved", "done", "blocked"}
        self.assertEqual(set(board), expected)
        self.assertEqual(board["blocked"][0]["blocked_reason"], "waiting")

        markdown = self.run_cli("board", "--format", "markdown", "--write").stdout
        self.assertTrue(markdown.startswith("# AI Planner Board\n"))
        self.assertEqual((self.root / "board.md").read_text(), markdown.rstrip() + "\n")

    def test_update_task_deduplicates_files_and_tags(self):
        self.init()
        self.add_task("T1")
        self.run_cli("update-task", "T1", "--add-files", "src/a.py", "src/a.py", "--add-tags", "unit", "unit")
        task = self.read_state()["tasks"][0]
        self.assertEqual(task["files"], ["src/a.py"])
        self.assertEqual(task["tags"], ["unit"])

    def test_cli_errors_do_not_mutate_state(self):
        self.init()
        self.add_task("T1")
        before = self.state.read_text()
        result = self.run_cli("transition", "T1", "close", "--actor", "backend", check=False)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.state.read_text(), before)

    def test_unblock_clears_reason_and_restores_ready(self):
        self.init()
        self.add_task("T1")
        self.run_cli("transition", "T1", "block", "--actor", "backend", "--detail", "waiting")
        self.assertEqual(json.loads(self.run_cli("ready").stdout), [])

        self.run_cli("transition", "T1", "unblock", "--actor", "scheduler", "--detail", "dependency available")
        task = self.read_state()["tasks"][0]
        self.assertEqual(task["status"], "todo")
        self.assertIsNone(task["blocked_reason"])
        self.assertEqual([item["id"] for item in json.loads(self.run_cli("ready").stdout)], ["T1"])

    def test_reject_requires_reason_and_independent_actor(self):
        self.init()
        self.add_task("T1")
        self.run_cli("transition", "T1", "start", "--actor", "backend")
        self.run_cli("transition", "T1", "complete", "--actor", "backend")
        evidence = self.root / "qa.json"
        evidence.write_text(json.dumps({"kind": "qa", "task": "T1", "status": "pass"}))
        self.run_cli("transition", "T1", "qa-pass", "--actor", "qa", "--evidence", str(evidence))

        missing = self.run_cli("transition", "T1", "reject", "--actor", "reviewer", check=False)
        self.assertEqual(missing.returncode, 2)
        self.assertIn("reject requires --detail", missing.stderr)
        same_role = self.run_cli("transition", "T1", "reject", "--actor", "backend", "--detail", "redo", check=False)
        self.assertEqual(same_role.returncode, 2)
        self.assertIn("must differ from executor", same_role.stderr)

        self.run_cli("transition", "T1", "reject", "--actor", "reviewer", "--detail", "redo")
        task = self.read_state()["tasks"][0]
        self.assertEqual(task["status"], "todo")
        self.assertEqual(task["blocked_reason"], "redo")

    def _preserve_repo_file(self, relative_path):
        path = ROOT / relative_path
        existed = path.exists()
        original = path.read_bytes() if existed else None

        def restore():
            if existed:
                path.write_bytes(original)
            elif path.exists():
                path.unlink()

        self.addCleanup(restore)
        return path

    def _preserve_runner_registry(self):
        return self._preserve_repo_file(".ai/runners.yaml")

    def test_runner_add_list_round_trip_and_force_update(self):
        self._preserve_runner_registry()
        self.run_cli(
            "runner", "add", "test-runner", "--command", " true # {prompt} ",
            "--model", "model-a", "--provider", "provider-a",
            "--description", "keeps # and spaces", "--default",
        )
        listed = json.loads(self.run_cli("runner", "list").stdout)
        self.assertEqual(listed["default_executor"], "test-runner")
        self.assertEqual(listed["runners"]["test-runner"]["command"], " true # {prompt} ")

        self.run_cli("runner", "add", "test-runner", "--command", "updated {prompt}", "--force")
        updated = json.loads(self.run_cli("runner", "list").stdout)
        # --force without --default preserves the existing default_executor.
        self.assertEqual(updated["default_executor"], "test-runner")
        self.assertEqual(updated["runners"]["test-runner"]["command"], "updated {prompt}")

    def test_dispatch_records_runner_model_and_provider(self):
        self._preserve_runner_registry()
        self.run_cli("runner", "add", "harmless", "--command", "true {prompt}", "--model", "m1", "--provider", "p1")
        self.init()
        self.add_task("T1")
        self.run_cli("dispatch", "T1", "--runner", "harmless")
        audit = json.loads((self.root / "dispatch_log_T1.json").read_text())
        self.assertEqual(audit["model"], "m1")
        self.assertEqual(audit["provider"], "p1")
        self.assertEqual(self.read_state()["tasks"][0]["status"], "in-progress")

    def test_dispatch_falls_back_to_default_executor_when_runner_omitted(self):
        self._preserve_runner_registry()
        self.run_cli("runner", "add", "fallback-runner", "--command", "true {prompt}", "--default")
        self.init()
        self.add_task("T1")
        result = json.loads(self.run_cli("dispatch", "T1").stdout)
        self.assertEqual(result["runner"], "fallback-runner")
        self.assertEqual(self.read_state()["tasks"][0]["status"], "in-progress")

    def test_dispatch_requires_runner_or_default_executor(self):
        registry_path = self._preserve_runner_registry()
        registry_path.write_text("runners: {}\n", encoding="utf-8")
        self.init()
        self.add_task("T1")
        refused = self.run_cli("dispatch", "T1", check=False)
        self.assertEqual(refused.returncode, 2)
        self.assertIn("default_executor", refused.stderr)
        self.assertEqual(self.read_state()["tasks"][0]["status"], "todo")

    def test_dispatch_ready_requires_matching_default_executor(self):
        registry_path = self._preserve_runner_registry()
        registry_path.write_text('runners:\n  manual:\n    command: "true {prompt}"\n', encoding="utf-8")
        self.init()
        self.add_task("T1")

        # No default_executor configured at all yet.
        refused = self.run_cli("dispatch-ready", check=False)
        self.assertEqual(refused.returncode, 2)
        self.assertIn("default_executor", refused.stderr)
        self.assertEqual(self.read_state()["tasks"][0]["status"], "todo")

        # --runner naming a registered runner that isn't the default_executor is refused too.
        mismatched = self.run_cli("dispatch-ready", "--runner", "manual", check=False)
        self.assertEqual(mismatched.returncode, 2)
        self.assertIn("default_executor", mismatched.stderr)
        self.assertEqual(self.read_state()["tasks"][0]["status"], "todo")

        unknown = self.run_cli("dispatch-ready", "--runner", "missing", check=False)
        self.assertEqual(unknown.returncode, 2)
        self.assertEqual(self.read_state()["tasks"][0]["status"], "todo")

    def test_dispatch_ready_claims_and_spawns_default_executor(self):
        self._preserve_runner_registry()
        self.run_cli("runner", "add", "automatic", "--command", "true {prompt}", "--default")
        self.init()
        self.add_task("T1")
        result = json.loads(self.run_cli("dispatch-ready").stdout)
        self.assertEqual(result["runner"], "automatic")
        self.assertEqual(result["claimed"], 1)
        self.assertEqual(len(result["spawned"]), 1)
        self.assertEqual(self.read_state()["tasks"][0]["status"], "in-progress")

    def test_dispatch_ready_spawned_process_honors_custom_state_path(self):
        # Regression: the spawned "dispatch" subprocess must receive --state
        # BEFORE the "dispatch" subcommand token (argparse only accepts it on
        # the root parser), or the child silently fails and never writes the
        # per-task dispatch_log audit file into this custom workspace.
        self._preserve_runner_registry()
        self.run_cli("runner", "add", "automatic", "--command", "true {prompt}", "--default")
        self.init()
        self.add_task("T1")
        self.run_cli("dispatch-ready")
        audit_path = self.root / "dispatch_log_T1.json"
        deadline = time.monotonic() + 5
        while not audit_path.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertTrue(audit_path.exists(), "spawned dispatch never wrote its audit log")
        audit = json.loads(audit_path.read_text())
        self.assertEqual(audit["task"], "T1")
        self.assertEqual(audit["exit_code"], 0)

    def test_context_drift_is_reported_only_after_forced_update(self):
        self._preserve_repo_file(".ai/contexts.yaml")
        name = "test-context"
        self.run_cli("context", "add", name, "--path", "tests/*", "--owner", "backend")
        self.init()
        self.add_task("T1", **{"--context": name})
        self.assertFalse(json.loads(self.run_cli("drift", "T1").stdout)["context_stale"])
        self.run_cli("context", "add", name, "--path", "changed/*", "--owner", "backend", "--force")
        self.assertTrue(json.loads(self.run_cli("drift", "T1").stdout)["context_stale"])

    def test_epic_drift_is_reported_only_after_forced_update(self):
        self._preserve_repo_file(".ai/epics.yaml")
        name = "test-epic"
        self.run_cli("epic", "add", name, "--spec", "spec-v1.md", "--owner", "planner")
        self.init()
        self.add_task("T1", **{"--epic": name})
        self.assertFalse(json.loads(self.run_cli("drift", "T1").stdout)["epic_stale"])
        self.run_cli("epic", "add", name, "--spec", "spec-v2.md", "--owner", "planner", "--force")
        self.assertTrue(json.loads(self.run_cli("drift", "T1").stdout)["epic_stale"])

    def test_unreadable_contract_is_unavailable_not_stale(self):
        self.init()
        contract = self.root / "contract.md"
        contract.write_text("version: 1\n")
        self.add_task("T1", **{"--depends-on": [str(contract)]})
        contract.unlink()
        contract.mkdir()
        drift = json.loads(self.run_cli("drift", "T1").stdout)
        self.assertEqual(drift["drift_unavailable"], [str(contract)])
        self.assertEqual(drift["contract_stale"], [])

    def test_board_filters_are_combined_with_and(self):
        self.init()
        self.add_task("T1", **{"--context": "ctx-a", "--epic": "epic-a"})
        self.add_task("T2", **{"--context": "ctx-a", "--epic": "epic-b"})
        self.add_task("T3", **{"--context": "ctx-b", "--epic": "epic-a", "--owner": "frontend"})
        board = json.loads(self.run_cli("board", "--context", "ctx-a", "--epic", "epic-a", "--owner", "backend").stdout)
        self.assertEqual([entry["id"] for entry in board["todo"]], ["T1"])

    def test_board_flags_match_drift_flags(self):
        self._preserve_repo_file(".ai/contexts.yaml")
        self._preserve_repo_file(".ai/epics.yaml")
        self.run_cli("context", "add", "parity-context", "--path", "before/*", "--owner", "backend")
        self.run_cli("epic", "add", "parity-epic", "--spec", "before.md", "--owner", "planner")
        contract = self.root / "changed.md"
        unavailable = self.root / "unavailable.md"
        contract.write_text("before\n")
        unavailable.write_text("before\n")
        self.init()
        self.add_task(
            "T1",
            **{
                "--context": "parity-context",
                "--epic": "parity-epic",
                "--depends-on": [str(contract), str(unavailable)],
            },
        )
        self.run_cli("context", "add", "parity-context", "--path", "after/*", "--owner", "backend", "--force")
        self.run_cli("epic", "add", "parity-epic", "--spec", "after.md", "--owner", "planner", "--force")
        contract.write_text("after\n")
        unavailable.unlink()
        unavailable.mkdir()
        drift = json.loads(self.run_cli("drift", "T1").stdout)
        board = json.loads(self.run_cli("board").stdout)["todo"][0]
        self.assertEqual(set(board["flags"]), {"context-stale", "epic-stale", "contract-stale", "drift-unavailable"})
        self.assertEqual("context-stale" in board["flags"], drift["context_stale"])
        self.assertEqual("epic-stale" in board["flags"], drift["epic_stale"])
        self.assertEqual("contract-stale" in board["flags"], bool(drift["contract_stale"]))
        self.assertEqual("drift-unavailable" in board["flags"], bool(drift["drift_unavailable"]))

    def test_acceptance_flag_accumulates_across_repeated_occurrences(self):
        self.init()
        self.run_cli(
            "add-task", "T1", "--title", "t1", "--owner", "backend", "--phase", "build",
            "--acceptance", "A", "--acceptance", "B", "--acceptance", "C",
        )
        task = self.read_state()["tasks"][0]
        self.assertEqual(task["acceptance"], ["A", "B", "C"])

        self.run_cli(
            "add-task", "T2", "--title", "t2", "--owner", "backend", "--phase", "build",
            "--acceptance", "D", "E", "F",
        )
        second = self.read_state()["tasks"][1]
        self.assertEqual(second["acceptance"], ["D", "E", "F"])

        self.run_cli(
            "update-task", "T1", "--add-acceptance", "G", "--add-acceptance", "H",
        )
        updated = self.read_state()["tasks"][0]
        self.assertEqual(updated["acceptance"], ["A", "B", "C", "G", "H"])

    def test_graph_output_is_dot_text_not_json_quoted(self):
        self.init()
        self.add_task("T1")
        graph = self.run_cli("graph")
        self.assertTrue(graph.stdout.startswith("digraph"))
        self.assertFalse(graph.stdout.startswith('"digraph'))


if __name__ == "__main__":
    unittest.main()
