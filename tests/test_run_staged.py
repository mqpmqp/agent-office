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
from agent_office.adapters.claude import ClaudeAdapter
from agent_office.adapters.codex import CodexAdapter
from agent_office.adapters.grok import GrokAdapter


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

    def test_run_staged_clears_stale_global_artifacts_and_keeps_logs(self) -> None:
        with self._project() as root, patch.dict(os.environ, {}, clear=True), redirect_stdout(io.StringIO()):
            self._write(root / ".ai" / "context" / "gemini-context.md", "STALE_CONTEXT")
            self._write(root / ".ai" / "finalize" / "final-for-claude.md", "STALE_FINAL")
            self._write(root / ".ai" / "logs" / "keep.log", "keep")
            self._write(root / ".ai" / "tasks" / "OTHER" / "task.json", "{}")

            cli.cmd_run_staged(
                argparse.Namespace(
                    task_id="P6-CLEAN-STAGED",
                    dry_run=True,
                    reset=True,
                    real=False,
                    adapter=None,
                    timeout=None,
                )
            )

            global_context_exists = (root / ".ai" / "context").exists()
            global_finalize_exists = (root / ".ai" / "finalize").exists()
            log_exists = (root / ".ai" / "logs" / "keep.log").exists()
            other_task_exists = (root / ".ai" / "tasks" / "OTHER" / "task.json").exists()

        self.assertFalse(global_context_exists)
        self.assertFalse(global_finalize_exists)
        self.assertTrue(log_exists)
        self.assertTrue(other_task_exists)

    def test_run_staged_codex_real_uses_current_task_context(self) -> None:
        env = {
            "AGENTOFFICE_CODEX_MODE": "real",
            "AGENTOFFICE_CODEX_DRY_RUN": "true",
            "OPENAI_API_KEY": "fake-openai-key",
        }
        captured: dict[str, str] = {}
        original = CodexAdapter._build_prompt

        def capture_prompt(self, invocation, max_input_chars):
            prompt, reviewed = original(self, invocation, max_input_chars)
            captured["prompt"] = prompt
            return prompt, reviewed

        with (
            self._project() as root,
            patch.dict(os.environ, env, clear=True),
            patch.object(CodexAdapter, "_build_prompt", capture_prompt),
            redirect_stdout(io.StringIO()),
        ):
            self._write(root / ".ai" / "context" / "gemini-context.md", "STALE_CONTEXT")

            cli.cmd_run_staged(
                argparse.Namespace(
                    task_id="P6-CODEX-STAGING",
                    dry_run=True,
                    reset=True,
                    real=True,
                    adapter="codex",
                    timeout=None,
                )
            )

            staged_context = (root / ".ai" / "context" / "gemini-context.md").read_text(encoding="utf-8")

        self.assertIn("P6-CODEX-STAGING", captured["prompt"])
        self.assertNotIn("STALE_CONTEXT", captured["prompt"])
        self.assertIn("P6-CODEX-STAGING", staged_context)
        self.assertNotIn("STALE_CONTEXT", staged_context)

    def test_run_staged_grok_real_uses_current_task_codex_artifacts(self) -> None:
        env = {
            "AGENTOFFICE_GROK_MODE": "real",
            "AGENTOFFICE_GROK_DRY_RUN": "true",
            "XAI_API_KEY": "fake-xai-key",
        }
        captured: dict[str, dict[str, str]] = {}
        original = GrokAdapter._build_report

        def capture_report(self, invocation, inputs, patch_validation, recommendation):
            captured["inputs"] = dict(inputs)
            return original(self, invocation, inputs, patch_validation, recommendation)

        with (
            self._project() as root,
            patch.dict(os.environ, env, clear=True),
            patch.object(GrokAdapter, "_build_report", capture_report),
            redirect_stdout(io.StringIO()),
        ):
            self._write(root / ".ai" / "context" / "gemini-context.md", "STALE_CONTEXT")
            self._write(root / ".ai" / "codex" / "patch.diff", "STALE_PATCH")
            self._write(root / ".ai" / "codex" / "codex-report.md", "STALE_REPORT")

            cli.cmd_run_staged(
                argparse.Namespace(
                    task_id="P6-GROK-STAGING",
                    dry_run=True,
                    reset=True,
                    real=True,
                    adapter="grok",
                    timeout=None,
                )
            )

            staged_patch = (root / ".ai" / "codex" / "patch.diff").read_text(encoding="utf-8")
            staged_report = (root / ".ai" / "codex" / "codex-report.md").read_text(encoding="utf-8")

        inputs = captured["inputs"]
        self.assertIn("P6-GROK-STAGING", inputs["gemini_context"])
        self.assertIn("P6-GROK-STAGING", inputs["codex_patch"])
        self.assertIn("P6-GROK-STAGING", inputs["codex_report"])
        self.assertNotIn("STALE_CONTEXT", inputs["gemini_context"])
        self.assertNotIn("STALE_PATCH", inputs["codex_patch"])
        self.assertNotIn("STALE_REPORT", inputs["codex_report"])
        self.assertIn("P6-GROK-STAGING", staged_patch)
        self.assertIn("P6-GROK-STAGING", staged_report)

    def test_run_staged_claude_real_uses_current_task_final_packet(self) -> None:
        env = {
            "AGENTOFFICE_CLAUDE_MODE": "real",
            "AGENTOFFICE_CLAUDE_DRY_RUN": "true",
            "ANTHROPIC_API_KEY": "fake-anthropic-key",
        }
        captured: dict[str, dict[str, str]] = {}
        original = ClaudeAdapter._build_report

        def capture_report(self, invocation, inputs, decision, risk_flags):
            captured["inputs"] = dict(inputs)
            return original(self, invocation, inputs, decision, risk_flags)

        with (
            self._project() as root,
            patch.dict(os.environ, env, clear=True),
            patch.object(ClaudeAdapter, "_build_report", capture_report),
            redirect_stdout(io.StringIO()),
        ):
            self._write(root / ".ai" / "context" / "gemini-context.md", "STALE_CONTEXT")
            self._write(root / ".ai" / "codex" / "patch.diff", "STALE_PATCH")
            self._write(root / ".ai" / "codex" / "codex-report.md", "STALE_REPORT")
            self._write(root / ".ai" / "grok" / "redteam-report.md", "STALE_GROK")
            self._write(root / ".ai" / "finalize" / "final-for-claude.md", "STALE_FINAL")

            cli.cmd_run_staged(
                argparse.Namespace(
                    task_id="P6-CLAUDE-STAGING",
                    dry_run=True,
                    reset=True,
                    real=True,
                    adapter="claude",
                    timeout=None,
                )
            )

            staged_final = (root / ".ai" / "finalize" / "final-for-claude.md").read_text(encoding="utf-8")

        inputs = captured["inputs"]
        self.assertIn("P6-CLAUDE-STAGING", inputs["final_packet"])
        self.assertIn("P6-CLAUDE-STAGING", inputs["gemini_context"])
        self.assertIn("P6-CLAUDE-STAGING", inputs["codex_patch"])
        self.assertIn("P6-CLAUDE-STAGING", inputs["codex_report"])
        self.assertNotIn("STALE_FINAL", inputs["final_packet"])
        self.assertNotIn("STALE_CONTEXT", inputs["gemini_context"])
        self.assertNotIn("STALE_PATCH", inputs["codex_patch"])
        self.assertNotIn("STALE_REPORT", inputs["codex_report"])
        self.assertNotIn("STALE_GROK", inputs["grok_report"])
        self.assertIn("P6-CLAUDE-STAGING", staged_final)

    def _project(self):
        return _PatchedProject()

    def _write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


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
