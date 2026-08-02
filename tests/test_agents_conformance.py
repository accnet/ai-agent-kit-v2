"""Conformance tests: AGENTS.md's normative claims vs. what the engine does.

This kit's recurring failure mode is not ordinary bugs -- it is documentation
declaring a capability the engine never implements. Four separate instances
were found and fixed by hand:

  * `.ai/workflows/feature/manifest.json` declared allowed_transitions and
    gate_requirements; no code ever read the file.
  * `registry.yaml`'s `ai_triggers:` block was described in
    skill-router/SKILL.md as live stack-conditional routing; no code ever
    read it either.
  * Six of the ten rows in AGENTS.md's mandatory-concerns table had no
    trigger behind them, so those concerns never routed regardless of task
    content.
  * The install template's CI ran a test suite the installer does not ship.

AGENTS.md itself forbids exactly this ("Do not describe a prompt convention
as an engine capability without this evidence"), so the rule deserves an
executable check rather than reviewer vigilance. These tests parse the two
routing tables straight out of AGENTS.md and assert the registry actually
implements every row -- meaning a future row cannot be documented as
mandatory without an implementation behind it, and a trigger cannot be
renamed or narrowed until it silently stops firing.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ENGINE_DIR = REPO_ROOT / ".ai" / "engine"
sys.path.insert(0, str(ENGINE_DIR))
import ai_kit  # noqa: E402

AGENTS_MD = REPO_ROOT / "AGENTS.md"
MANDATORY_MARKER = "These concerns are mandatory when their trigger is present:"
AI_MARKER = "AI trigger routing (registry-backed) is mandatory when matched by task content:"


def parse_table(marker: str) -> list[tuple[str, str]]:
    """Return [(trigger description, requirement cell)] for the markdown table
    that follows `marker` in AGENTS.md."""
    text = AGENTS_MD.read_text(encoding="utf-8")
    if marker not in text:
        raise AssertionError(f"AGENTS.md no longer contains the marker: {marker!r}")
    body = text.split(marker, 1)[1]
    rows: list[tuple[str, str]] = []
    for line in body.splitlines():
        if line.startswith("|") and "---" not in line:
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) == 2 and not cells[0].lower().startswith("trigger"):
                rows.append((cells[0], cells[1]))
        elif rows and not line.startswith("|"):
            break
    return rows


def candidate_phrases(description: str) -> list[str]:
    """Split a table's prose trigger description into probe phrases.

    The description is prose ("Auth, untrusted input, sensitive data,
    permissions"), not a keyword list, so not every fragment is expected to
    match -- the assertion below is that at least one does.
    """
    return [p.strip().lower() for p in re.split(r",|/| or ", description) if len(p.strip()) > 2]


def skills_reachable_for(phrase: str) -> tuple[set[str], set[str]]:
    """(core skills, technology skill names) the registry routes for a phrase.

    Mirrors cmd_route's trigger matching: a trigger fires when one of its
    match terms appears in the task text.
    """
    core: set[str] = set()
    tech: set[str] = set()
    for trigger in ai_kit._load_skill_triggers().values():
        if any(term and term in phrase for term in trigger["match"]):
            core.update(trigger["core_skills"])
            tech.update(ref.split("/")[-1] for ref in trigger["technology_skills"])
    return core, tech


class MandatoryConcernsTableTests(unittest.TestCase):
    """Every row of AGENTS.md's general mandatory-concerns table must be
    reachable through the trigger registry."""

    def setUp(self) -> None:
        self.rows = parse_table(MANDATORY_MARKER)

    def test_table_is_still_parseable(self) -> None:
        """If AGENTS.md is restructured and this stops finding rows, the rest
        of the suite would pass vacuously."""
        self.assertGreaterEqual(len(self.rows), 10, f"parsed only {len(self.rows)} rows")

    def test_every_named_skill_exists(self) -> None:
        """Catches a renamed or deleted skill that the table still names."""
        for description, requirement in self.rows:
            for skill in re.findall(r"`([^`]+)`", requirement):
                with self.subTest(row=description, skill=skill):
                    self.assertTrue(
                        (REPO_ROOT / ".ai" / "skills" / "core" / skill / "SKILL.md").is_file(),
                        f"AGENTS.md requires core skill '{skill}' for '{description}', "
                        f"but .ai/skills/core/{skill}/SKILL.md does not exist",
                    )

    def test_every_row_is_reachable_through_a_trigger(self) -> None:
        """The core assertion: for each row, some phrasing drawn from the
        row's own description must route to all the skills it requires."""
        for description, requirement in self.rows:
            required = set(re.findall(r"`([^`]+)`", requirement))
            working = [p for p in candidate_phrases(description)
                       if required <= skills_reachable_for(p)[0]]
            with self.subTest(row=description):
                self.assertTrue(
                    working,
                    f"AGENTS.md declares '{description}' mandatory (requires {sorted(required)}), "
                    f"but no phrasing from that description routes to those skills. "
                    f"Add or widen a skill_triggers entry in registry.yaml, or the row is "
                    f"documentation with no implementation behind it.",
                )


class AiTriggerTableTests(unittest.TestCase):
    """Same contract for AGENTS.md's AI trigger routing table, which names
    both core skills and AI technology skills per row."""

    def setUp(self) -> None:
        self.rows = parse_table(AI_MARKER)

    def test_table_is_still_parseable(self) -> None:
        self.assertGreaterEqual(len(self.rows), 7, f"parsed only {len(self.rows)} rows")

    def test_every_row_is_reachable_through_a_trigger(self) -> None:
        for description, requirement in self.rows:
            core_part = re.search(r"Core ([^;]+)", requirement)
            ai_part = re.search(r"AI ([^;]+)", requirement)
            need_core = set(re.findall(r"`([^`]+)`", core_part.group(1))) if core_part else set()
            need_ai = set(re.findall(r"`([^`]+)`", ai_part.group(1))) if ai_part else set()
            working = []
            for phrase in candidate_phrases(description):
                core, tech = skills_reachable_for(phrase)
                # AI rows list alternatives ("openai OR llm-application"), so
                # require an intersection rather than the full set.
                if need_core <= core and (not need_ai or tech & need_ai):
                    working.append(phrase)
            with self.subTest(row=description):
                self.assertTrue(
                    working,
                    f"AGENTS.md declares AI routing for '{description}' mandatory "
                    f"(core={sorted(need_core)}, ai={sorted(need_ai)}), but no phrasing from "
                    f"that description routes to them.",
                )

    def test_ai_technology_skills_named_in_the_table_exist(self) -> None:
        ai_root = REPO_ROOT / ".ai" / "skills" / "ai"
        known = {d.name for d in ai_root.iterdir() if d.is_dir()}
        # Names appearing after "AI " in a requirement cell; skip the core ones
        # and the prose qualifiers around them.
        for description, requirement in self.rows:
            ai_part = re.search(r"AI ([^;]+)", requirement)
            if not ai_part:
                continue
            for name in re.findall(r"`([^`]+)`", ai_part.group(1)):
                if "/" in name:  # e.g. `database/pgvector`
                    continue
                with self.subTest(row=description, skill=name):
                    self.assertIn(
                        name, known,
                        f"AGENTS.md names AI skill '{name}' for '{description}', "
                        f"but .ai/skills/ai/{name}/ does not exist",
                    )


class DeclaredCapabilityTests(unittest.TestCase):
    """Pins the specific documented-but-unimplemented artifacts that were
    removed, so they cannot quietly return without an implementation."""

    def test_no_workflow_manifest_json(self) -> None:
        """manifest.json declared transitions/gates the engine never read;
        TRANSITIONS in ai_kit.py is the single source of truth."""
        stray = sorted((REPO_ROOT / ".ai" / "workflows").rglob("manifest.json"))
        self.assertEqual(stray, [], f"dead workflow manifest(s) reintroduced: {stray}")

    def test_skill_router_does_not_claim_ai_triggers(self) -> None:
        """skill-router/SKILL.md described `ai_triggers` as live routing while
        no code read it."""
        doc = (REPO_ROOT / ".ai" / "skills" / "core" / "skill-router" / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("ai_triggers", doc)

    def test_engine_reads_every_registry_section_agents_md_relies_on(self) -> None:
        """`skill_triggers` and `owners` are the two registry sections the
        routing tables depend on; both must actually be parsed."""
        source = (ENGINE_DIR / "ai_kit.py").read_text(encoding="utf-8")
        self.assertIn('"skill_triggers"', source)
        self.assertIn('owners:', source)


if __name__ == "__main__":
    unittest.main()
