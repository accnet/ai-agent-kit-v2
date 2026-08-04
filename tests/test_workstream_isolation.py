from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ai_kit_workstreams", ROOT / ".ai/engine/ai_kit.py")
assert SPEC and SPEC.loader
ENGINE = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(ENGINE)


class WorkstreamIsolationTests(unittest.TestCase):
    def test_states_with_same_local_task_id_have_distinct_workflow_namespaces(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second = root / "one.json", root / "two.json"
            one, two = ENGINE.new_state("one", "feature"), ENGINE.new_state("two", "feature")
            ENGINE.save(one, first); ENGINE.save(two, second)
            self.assertNotEqual(one["workflow_id"], two["workflow_id"])
            current = root / "current.json"
            with patch.object(ENGINE, "CURRENT", current):
                selected = ENGINE.cmd_activate(argparse.Namespace(workflow_state=str(second)))
                self.assertEqual(selected["workflow_id"], two["workflow_id"])
                self.assertEqual(ENGINE.load(current)["workflow_state"], str(second))


if __name__ == "__main__": unittest.main()
