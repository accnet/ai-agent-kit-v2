from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ai_kit_approval_modes", ROOT / ".ai/engine/ai_kit.py")
assert SPEC and SPEC.loader
ENGINE = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(ENGINE)


class ApprovalModeTests(unittest.TestCase):
    def test_manual_mode_surfaces_awaiting_qa(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "workflow.json"
            state = ENGINE.new_state("approval", "feature")
            state["tasks"] = [{"id":"T1","title":"approval","owner":"backend","phase":"build","needs":[],"status":"implementation-complete","acceptance":["review"],"files":[],"tags":[],"attempts":1,"evidence":[],"blocked_reason":None,"claimed_by":"backend#a","context":None,"epic":None,"base_commit":None,"context_revision":None,"epic_revision":None,"upstream_context_revisions":{},"depends_on":[],"contract_hashes":{},"contract_revision":None,"contract_hash":None,"superseded_by":None}]
            ENGINE.sync_phases(state); ENGINE.save(state, state_path)
            with patch.object(ENGINE, "_load_automation_roles", return_value={"qa":{"enabled":False}, "reviewer":{"enabled":False}}):
                report = ENGINE.cmd_status(argparse.Namespace(state=str(state_path), context=None, epic=None))
            self.assertEqual(report["approval_mode"]["mode"], "manual")
            self.assertEqual(report["approval_mode"]["awaiting"][0]["status"], "awaiting-manual-qa")


if __name__ == "__main__": unittest.main()
