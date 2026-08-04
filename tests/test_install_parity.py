"""Installer contract for project-owned AI-Kit configuration.

The source kit tracks only `.ai/install/config/`.  Its installer materializes
that directory as `.ai-config/` in a consuming project and must never require
or recreate a source-repository `.ai-config/` tree.
"""
from __future__ import annotations

import re
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_CONFIG = REPO_ROOT / ".ai" / "install" / "config"
LIVE_VISUALIZER = REPO_ROOT / ".visualizer"
TEMPLATE_VISUALIZER = REPO_ROOT / ".ai" / "install" / "templates" / ".visualizer"

PROJECT_OWNED_CONFIGS = ("contexts.yaml", "epics.yaml")
EXPECTED_CONFIGS = {
    "automation.yaml", "contexts.yaml", "epics.yaml", "kit.yaml",
    "registry.yaml", "rules.yaml", "runners.yaml",
}

class InstallConfigTests(unittest.TestCase):
    def test_source_repository_has_no_project_config_directory(self) -> None:
        self.assertFalse((REPO_ROOT / ".ai-config").exists())

    def test_templates_are_the_complete_canonical_seed_set(self) -> None:
        self.assertEqual({p.name for p in TEMPLATE_CONFIG.glob("*.yaml")}, EXPECTED_CONFIGS)

    def test_installer_materializes_project_config_from_templates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            project.mkdir()
            result = subprocess.run(
                ["bash", str(REPO_ROOT / ".ai" / "install" / "install.sh"), "--target", str(project)],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            installed = project / ".ai-config"
            self.assertEqual({p.name for p in installed.glob("*.yaml")}, EXPECTED_CONFIGS)
            for name in EXPECTED_CONFIGS:
                self.assertEqual((installed / name).read_bytes(), (TEMPLATE_CONFIG / name).read_bytes())

    def test_project_owned_configs_ship_empty(self) -> None:
        """contexts.yaml and epics.yaml describe one specific project. The
        template must not carry real entries -- an earlier release shipped a
        contexts.yaml containing another project's module registry."""
        for name in PROJECT_OWNED_CONFIGS:
            with self.subTest(config=name):
                template = (TEMPLATE_CONFIG / name).read_text(encoding="utf-8")
                entries = [ln for ln in template.splitlines()
                           if re.match(r"^  \S+:", ln) and not ln.lstrip().startswith("#")]
                self.assertEqual(
                    entries, [],
                    f".ai/install/config/{name} ships with real entries {entries}; new "
                    f"projects would inherit another project's data",
                )


class VisualizerParityTests(unittest.TestCase):
    """The visualizer ships to installed projects, so its source files must
    not drift from the template copy. Generated payloads (*.json) are
    gitignored runtime artifacts and are deliberately excluded."""

    @staticmethod
    def _tracked_sources(directory: Path) -> set[str]:
        return {p.name for p in directory.iterdir()
                if p.is_file() and p.suffix != ".json"}

    def test_same_source_file_set(self) -> None:
        self.assertEqual(
            self._tracked_sources(LIVE_VISUALIZER),
            self._tracked_sources(TEMPLATE_VISUALIZER),
            "a visualizer source file exists in one copy but not the other",
        )

    def test_source_files_are_byte_identical(self) -> None:
        for name in sorted(self._tracked_sources(LIVE_VISUALIZER)):
            with self.subTest(file=name):
                self.assertEqual(
                    (LIVE_VISUALIZER / name).read_bytes(),
                    (TEMPLATE_VISUALIZER / name).read_bytes(),
                    f".visualizer/{name} differs from its install-template copy; a new "
                    f"install would get a stale visualizer",
                )

    def test_generated_payloads_are_not_committed(self) -> None:
        """*.json under .visualizer/ are regenerated on every transition; the
        template must never carry a snapshot of this repo's workflow state."""
        stray = sorted(p.name for p in TEMPLATE_VISUALIZER.glob("*.json"))
        self.assertEqual(stray, [], f"generated visualizer payloads in the template: {stray}")


if __name__ == "__main__":
    unittest.main()
