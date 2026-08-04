"""Contract coverage for the structured dispatch-audit directory."""

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
ENGINE_PATH = ROOT / ".ai" / "engine" / "ai_kit.py"
SPEC = importlib.util.spec_from_file_location("ai_kit_dispatch_paths", ENGINE_PATH)
assert SPEC and SPEC.loader
ENGINE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ENGINE)


class DispatchAuditPathTests(unittest.TestCase):
    def test_executor_qa_and_review_audits_share_the_dispatch_directory(self) -> None:
        state = Path("/tmp/ai-kit-test/workflow.json")
        root = Path("/tmp/ai-kit-test/workflow/dispatch")

        self.assertEqual(ENGINE._dispatch_audit_path(state, "T3"), root / "T3.json")
        self.assertEqual(ENGINE._dispatch_audit_path(state, "T3", "qa"), root / "qa_T3.json")
        self.assertEqual(ENGINE._dispatch_audit_path(state, "T3", "review"), root / "review_T3.json")
        self.assertNotIn("dispatch_log", str(ENGINE._dispatch_audit_path(state, "T3")))


if __name__ == "__main__":
    unittest.main()
