from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ai_kit_context_routing", ROOT / ".ai/engine/ai_kit.py")
assert SPEC and SPEC.loader
ENGINE = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(ENGINE)


class ContextRoutingTests(unittest.TestCase):
    def test_ai_directory_path_is_not_a_semantic_routing_trigger(self):
        task = {"title":"Cache context", "tags":[], "files":[".ai/engine/ai_kit.py"], "acceptance":["Cache is valid"]}
        self.assertNotIn("ai", ENGINE._tokenize_task(task))
        self.assertNotIn(".ai", ENGINE._task_text(task))


if __name__ == "__main__": unittest.main()
