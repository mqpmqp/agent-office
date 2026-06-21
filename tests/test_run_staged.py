from __future__ import annotations

import argparse
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from agent_office import cli


class RunStagedTests(unittest.TestCase):
    def test_run_staged_mock_reset_completes(self) -> None:
        with self._project() as root, patch.dict(os.environ, {}, clear=True):
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = cli.cmd_run_staged(
                    argparse.Namespace(
                        task_id="P6-STAGED-MOCK",
                        dry_run=True,
                        reset=True,
                        real=False,
                        adapter=None,
                        timeout=None,
                    )
                )

            task = json.loads((root / ".ai" / "tasks" / "P6-STAGED-MOCK" / "task.json").read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(task["state"], "APPROVED")
        self.assertIn("== judge ==", output.getvalue())

    def test_run_staged_requires_dry_run(self) -> None:
        with self._project():
            with self.assertRaisesRegex(cli.AgentOfficeError, "requires --dry-run"):
                cli.cmd_run_staged(
                    argparse.Namespace(
                        task_id="P6-NO-DRY",
                        dry_run=False,
                        reset=True,
                        real=False,
                        adapter=None,
                        timeout=None,
                    )
                )

    def test_run_staged_rejects_real_without_adapter(self) -> None:
        with self._project():
            with self.assertRaisesRegex(cli.AgentOfficeError, "requires one explicit --adapter"):
                cli.cmd_run_staged(
                    argparse.Namespace(
                        task_id="P6-REAL-NO-ADAPTER",
                        dry_run=True,
                        reset=True,
                        real=True,
                        adapter=None,
                        timeout=None,
                    )
                )

    def test_run_staged_rejects_adapter_without_real(self) -> None:
        with self._project():
            with self.assertRaisesRegex(cli.AgentOfficeError, "only with --real"):
                cli.cmd_run_staged(
                    argparse.Namespace(
                        task_id="P6-ADAPTER-NO-REAL",
                        dry_run=True,
                        reset=True,
                        real=False,
                        adapter="gemini",
                        timeout=None,
                    )
                )

    def test_run_staged_default_mock_ignores_real_env(self) -> None:
        env = {
            "AGENTOFFICE_GEMINI_MODE": "real",
            "AGENTOFFICE_CODEX_MODE": "real",
            "AGENTOFFICE_GROK_MODE": "real",
            "AGENTOFFICE_CLAUDE_MODE": "real",
            "AGENTOFFICE_GEMINI_DRY_RUN": "true",
            "AGENTOFFICE_CODEX_DRY_RUN": "true",
            "AGENTOFFICE_GROK_DRY_RUN": "true",
            "AGENTOFFICE_CLAUDE_DRY_RUN": "true",
            "GEMINI_API_KEY": "fake-gemini-key",
            "OPENAI_API_KEY": "fake-openai-key",
            "XAI_API_KEY": "fake-xai-key",
            "ANTHROPIC_API_KEY": "fake-anthropic-key",
        }
        with self._project() as root, patch.dict(os.environ, env, clear=True), redirect_stdout(io.StringIO()):
            cli.cmd_run_staged(
                argparse.Namespace(
                    task_id="P6-ENV-IGNORED",
                    dry_run=True,
                    reset=True,
                    real=False,
                    adapter=None,
                    timeout=None,
                )
            )

            task_root = root / ".ai" / "tasks" / "P6-ENV-IGNORED"
            task = json.loads((task_root / "task.json").read_text(encoding="utf-8"))
            task_context_exists = (task_root / "gemini-context.md").exists()
            global_context_exists = (root / ".ai" / "context").exists()
            global_codex_exists = (root / ".ai" / "codex").exists()
            global_grok_exists = (root / ".ai" / "grok").exists()
            global_claude_exists = (root / ".ai" / "claude").exists()

        self.assertEqual(task["state"], "APPROVED")
        self.assertTrue(task_context_exists)
        self.assertFalse(global_context_exists)
        self.assertFalse(global_codex_exists)
        self.assertFalse(global_grok_exists)
        self.assertFalse(global_claude_exists)

    def test_run_staged_allows_one_real_dry_run_adapter(self) -> None:
        env = {
            "AGENTOFFICE_GEMINI_MODE": "real",
            "AGENTOFFICE_GEMINI_DRY_RUN": "true",
            "GEMINI_API_KEY": "fake-gemini-key",
        }
        with self._project() as root, patch.dict(os.environ, env, clear=True), redirect_stdout(io.StringIO()):
            cli.cmd_run_staged(
                argparse.Namespace(
                    task_id="P6-ONE-REAL",
                    dry_run=True,
                    reset=True,
                    real=True,
                    adapter="gemini",
                    timeout=None,
                )
            )

            task = json.loads((root / ".ai" / "tasks" / "P6-ONE-REAL" / "task.json").read_text(encoding="utf-8"))
            global_context_exists = (root / ".ai" / "context" / "gemini-context.md").exists()
            global_codex_exists = (root / ".ai" / "codex").exists()
            global_grok_exists = (root / ".ai" / "grok").exists()
            global_claude_exists = (root / ".ai" / "claude").exists()

        self.assertEqual(task["state"], "APPROVED")
        self.assertTrue(global_context_exists)
        self.assertFalse(global_codex_exists)
        self.assertFalse(global_grok_exists)
        self.assertFalse(global_claude_exists)

    def _project(self):
        return _PatchedProject()


class _PatchedProject:
    def __enter__(self) -> Path:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.root = root
        self._patchers = [
            patch.object(cli, "PROJECT_ROOT", root),
            patch.object(cli, "TASKS_ROOT", root / ".ai" / "tasks"),
        ]
        for patcher in self._patchers:
            patcher.start()
        return root

    def __exit__(self, exc_type, exc, tb) -> None:
        for patcher in reversed(self._patchers):
            patcher.stop()
        self._tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
