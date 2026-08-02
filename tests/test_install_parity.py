"""Parity between what this repo runs and what the installer ships.

The kit keeps two copies of several things: the live config the repo itself
uses (`.ai-config/`, `.visualizer/`) and the copies `install.sh` seeds new
projects from (`.ai/install/config/`, `.ai/install/templates/.visualizer/`).
Nothing structural forces them to agree, and they have silently drifted more
than once -- most consequentially when the template's `registry.yaml` was
missing `ai` from `owners` for five roles, so a freshly installed project
routed strictly less than the repo it was copied from, with no error anywhere.

These tests pin the parts that must match while allowing the parts that are
deliberately project-owned to diverge. `kit.yaml` is the notable exception:
its whole purpose is per-project configuration (this repo declares a real
stack and test command; the template ships unconfigured sentinels so a fresh
install is honestly reported as un-onboarded by doctor.sh), so only its
*shape* is compared, never its values.
"""
from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ENGINE_DIR = REPO_ROOT / ".ai" / "engine"
sys.path.insert(0, str(ENGINE_DIR))
import ai_kit  # noqa: E402

LIVE_CONFIG = REPO_ROOT / ".ai-config"
TEMPLATE_CONFIG = REPO_ROOT / ".ai" / "install" / "config"
LIVE_VISUALIZER = REPO_ROOT / ".visualizer"
TEMPLATE_VISUALIZER = REPO_ROOT / ".ai" / "install" / "templates" / ".visualizer"

# Config files that must be byte-identical between the two copies. These hold
# kit-wide routing/policy that a project has no reason to fork on install.
IDENTICAL_CONFIGS = ("registry.yaml", "rules.yaml", "runners.yaml", "automation.yaml")

# Config files that are project-owned: the template seeds an empty/neutral
# version and the project fills it in. Compared on shape only, or not at all.
SHAPE_ONLY_CONFIGS = ("kit.yaml",)
PROJECT_OWNED_CONFIGS = ("contexts.yaml", "epics.yaml")


def top_level_keys(text: str) -> set[str]:
    return {m.group(1) for m in re.finditer(r"^([A-Za-z_][\w-]*):", text, re.MULTILINE)}


class ConfigParityTests(unittest.TestCase):
    def test_both_config_directories_hold_the_same_file_set(self) -> None:
        live = {p.name for p in LIVE_CONFIG.glob("*.yaml")}
        template = {p.name for p in TEMPLATE_CONFIG.glob("*.yaml")}
        self.assertEqual(
            live, template,
            "install.sh seeds .ai-config/ from .ai/install/config/, so a file present in "
            "one and not the other is either unshipped config or an orphan template",
        )

    def test_policy_configs_are_byte_identical(self) -> None:
        for name in IDENTICAL_CONFIGS:
            with self.subTest(config=name):
                live = (LIVE_CONFIG / name).read_bytes()
                template = (TEMPLATE_CONFIG / name).read_bytes()
                self.assertEqual(
                    live, template,
                    f".ai-config/{name} and .ai/install/config/{name} differ; a new install "
                    f"would behave differently from this repo. Copy the live file over the "
                    f"template (or vice versa) so the two stay in sync.",
                )

    def test_project_owned_configs_match_in_shape_not_content(self) -> None:
        """kit.yaml legitimately differs (this repo is onboarded, the template
        is not), but a section added to one must be added to the other."""
        for name in SHAPE_ONLY_CONFIGS:
            with self.subTest(config=name):
                live = top_level_keys((LIVE_CONFIG / name).read_text(encoding="utf-8"))
                template = top_level_keys((TEMPLATE_CONFIG / name).read_text(encoding="utf-8"))
                self.assertEqual(
                    live, template,
                    f"{name} top-level sections diverged between the live config and the "
                    f"install template",
                )

    def test_registry_routing_sections_agree_semantically(self) -> None:
        """Byte-parity above already covers registry.yaml, but assert the
        parsed routing data too: this is the drift that actually bit (the
        template was missing `ai` from owners for five roles), and it is
        worth failing on the meaning rather than only on the bytes."""
        live = self._parsed(LIVE_CONFIG / "registry.yaml")
        template = self._parsed(TEMPLATE_CONFIG / "registry.yaml")
        self.assertEqual(live["owners"], template["owners"])
        self.assertEqual(live["triggers"], template["triggers"])

    @staticmethod
    def _parsed(registry_path: Path) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".ai-config").mkdir()
            (root / ".ai-config" / "registry.yaml").write_bytes(registry_path.read_bytes())
            saved = ai_kit.ROOT
            ai_kit.ROOT = root
            try:
                return {
                    "owners": ai_kit._load_registry()["owners"],
                    "triggers": {
                        name: (sorted(t["match"]), sorted(t["core_skills"]), sorted(t["technology_skills"]))
                        for name, t in ai_kit._load_skill_triggers().items()
                    },
                }
            finally:
                ai_kit.ROOT = saved

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
