from __future__ import annotations

import argparse
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from agent_office.cli import cmd_skills
from agent_office.skills_registry import (
    collect_skill_status,
    format_skills_doctor,
    format_skills_table,
    skills_as_dicts,
)


class SkillsRegistryTests(unittest.TestCase):
    def test_collects_valid_skill_and_script_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_registry(root)
            self._write_skill(root, "claude-mem", scripts=["scripts/memory.py"])

            statuses = {status.name: status for status in collect_skill_status(root)}

        self.assertEqual(statuses["claude-mem"].status, "ok")
        self.assertTrue(statuses["claude-mem"].exists)
        self.assertTrue(statuses["claude-mem"].validated)
        self.assertEqual(statuses["claude-mem"].missing_scripts, ())

    def test_missing_skill_is_reported_without_failing_system(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_registry(root)
            statuses = {status.name: status for status in collect_skill_status(root)}

        self.assertEqual(statuses["claude-mem"].status, "missing")
        self.assertFalse(statuses["claude-mem"].exists)
        self.assertFalse(statuses["claude-mem"].validated)

    def test_invalid_frontmatter_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_registry(root)
            skill_root = root / "local-skills" / "claude-mem"
            skill_root.mkdir(parents=True)
            (skill_root / "SKILL.md").write_text("---\nname: wrong\n---\n# Bad\n", encoding="utf-8")
            status = collect_skill_status(root)[0]

        self.assertEqual(status.status, "invalid")
        self.assertIn("SKILL.md frontmatter invalid", status.errors)

    def test_missing_expected_script_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_registry(root)
            self._write_skill(root, "claude-mem")
            status = collect_skill_status(root)[0]

        self.assertEqual(status.status, "invalid")
        self.assertEqual(status.missing_scripts, ("scripts/memory.py",))

    def test_table_and_doctor_do_not_read_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_registry(root)
            self._write_skill(root, "claude-mem", scripts=["scripts/memory.py"])
            (root / ".env").write_text("OPENAI_API_KEY=REAL_SECRET_SHOULD_NOT_APPEAR\n", encoding="utf-8")
            output = format_skills_table(root) + "\n" + format_skills_doctor(root)

        self.assertNotIn("REAL_SECRET_SHOULD_NOT_APPEAR", output)
        self.assertIn("skill | exists | validated | scripts | status | path", output)
        self.assertIn("AgentOffice skills doctor", output)

    def test_skills_json_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_registry(root)
            self._write_skill(root, "claude-mem", scripts=["scripts/memory.py"])
            data = skills_as_dicts(root)

        self.assertEqual(data[0]["name"], "claude-mem")
        self.assertEqual(data[0]["status"], "ok")
        self.assertEqual(data[0]["scripts"], ("scripts/memory.py",))

    def test_cli_skills_table_and_doctor_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_registry(root)
            self._write_skill(root, "claude-mem", scripts=["scripts/memory.py"])

            table_output = io.StringIO()
            with patch("agent_office.cli.PROJECT_ROOT", root), redirect_stdout(table_output):
                exit_code = cmd_skills(argparse.Namespace(skills_action=None, json=False))

            json_output = io.StringIO()
            with patch("agent_office.cli.PROJECT_ROOT", root), redirect_stdout(json_output):
                json_exit_code = cmd_skills(argparse.Namespace(skills_action="doctor", json=True))

        self.assertEqual(exit_code, 0)
        self.assertIn("claude-mem", table_output.getvalue())
        self.assertEqual(json_exit_code, 0)
        parsed = json.loads(json_output.getvalue())
        self.assertEqual(parsed["skills"][0]["name"], "claude-mem")

    def _write_registry(self, root: Path) -> None:
        registry_dir = root / "skills"
        registry_dir.mkdir(parents=True)
        registry = {
            "version": 1,
            "skills": [
                {
                    "name": "claude-mem",
                    "purpose": "Sanitized memory.",
                    "path": str(root / "local-skills" / "claude-mem"),
                    "expected_scripts": ["scripts/memory.py"],
                }
            ],
        }
        (registry_dir / "registry.json").write_text(json.dumps(registry), encoding="utf-8")

    def _write_skill(self, root: Path, name: str, scripts: list[str] | None = None) -> None:
        skill_root = root / "local-skills" / name
        skill_root.mkdir(parents=True)
        (skill_root / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: Test skill.\n---\n# {name}\n",
            encoding="utf-8",
        )
        for script in scripts or []:
            script_path = skill_root / script
            script_path.parent.mkdir(parents=True, exist_ok=True)
            script_path.write_text("#!/usr/bin/env python3\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
