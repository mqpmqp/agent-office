from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_office.adapters.base import AdapterInvocation, AdapterUnavailable
from agent_office.adapters.gemini import GeminiAdapter, gemini_context_output_path
from agent_office.cli import TaskPaths
from agent_office.doctor import collect_doctor


class GeminiContextAdapterTests(unittest.TestCase):
    def test_gemini_real_without_key_marks_only_gemini_env_failed(self) -> None:
        env = {"AGENTOFFICE_GEMINI_MODE": "real"}
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, env, clear=True):
            report = collect_doctor(Path(tmp))

        rows = {row["adapter"]: row for row in report["adapter_modes"]["rows"]}
        self.assertEqual(rows["gemini"]["status"], "env_failed")
        self.assertFalse(rows["gemini"]["env_ok"])
        self.assertEqual(rows["codex"]["status"], "ok")
        self.assertEqual(rows["grok"]["status"], "ok")
        self.assertEqual(rows["claude"]["status"], "ok")

    def test_gemini_real_dry_run_generates_global_context_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._make_task(root, "T-GEMINI-DRY")
            (root / "README.md").write_text("# AgentOffice\n\nTest README.\n", encoding="utf-8")
            (root / "agent_office").mkdir()
            (root / "agent_office" / "__init__.py").write_text("__version__ = 'test'\n", encoding="utf-8")
            env = {
                "AGENTOFFICE_GEMINI_MODE": "real",
                "AGENTOFFICE_GEMINI_DRY_RUN": "true",
                "GEMINI_API_KEY": "fake-gemini-key",
            }
            adapter = GeminiAdapter()

            with patch.dict(os.environ, env, clear=True), patch.object(
                adapter, "_send_real_request", side_effect=AssertionError("network path should not be called")
            ):
                result = adapter.context(self._invocation(root, paths))

            output_path = gemini_context_output_path(root)
            output_exists = output_path.exists()
            content = output_path.read_text(encoding="utf-8")

        self.assertTrue(output_exists)
        self.assertEqual(result.metadata["adapter"], "gemini")
        self.assertEqual(result.metadata["mode"], "real")
        self.assertEqual(result.metadata["dry_run"], True)
        self.assertEqual(result.metadata["fallback_used"], False)
        self.assertEqual(result.metadata["real_request_sent"], False)
        self.assertEqual(result.metadata["output_path"], ".ai/context/gemini-context.md")
        self.assertIn("# Gemini Context", content)
        self.assertIn("## Non-Goals", content)
        self.assertIn("Gemini is not implementing code", content)

    def test_gemini_real_dry_run_does_not_read_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._make_task(root, "T-GEMINI-NOENV")
            (root / ".env").write_text("GEMINI_API_KEY=REAL_SECRET_SHOULD_NOT_APPEAR\n", encoding="utf-8")
            (root / ".env.example").write_text("GEMINI_API_KEY=\n", encoding="utf-8")
            env = {
                "AGENTOFFICE_GEMINI_MODE": "real",
                "AGENTOFFICE_GEMINI_DRY_RUN": "true",
                "GEMINI_API_KEY": "fake-gemini-key",
            }
            with patch.dict(os.environ, env, clear=True):
                GeminiAdapter().context(self._invocation(root, paths))
            content = gemini_context_output_path(root).read_text(encoding="utf-8")

        self.assertNotIn("REAL_SECRET_SHOULD_NOT_APPEAR", content)

    def test_gemini_non_dry_run_rejected_without_allow_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._make_task(root, "T-GEMINI-REJECT")
            env = {
                "AGENTOFFICE_GEMINI_MODE": "real",
                "AGENTOFFICE_GEMINI_DRY_RUN": "false",
                "GEMINI_API_KEY": "fake-gemini-key",
            }
            with patch.dict(os.environ, env, clear=True):
                with self.assertRaises(AdapterUnavailable) as ctx:
                    GeminiAdapter().context(self._invocation(root, paths))
        self.assertIn("ALLOW_NON_DRY_RUN", str(ctx.exception))

    def test_gemini_cannot_write_outside_context_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            adapter = GeminiAdapter()
            with self.assertRaises(AdapterUnavailable):
                adapter._safe_write_context(root, root / "README.md", "bad write")

    def test_gemini_cannot_execute_commands_by_default(self) -> None:
        env = {"AGENTOFFICE_GEMINI_MODE": "real", "GEMINI_API_KEY": "fake-gemini-key"}
        with patch.dict(os.environ, env, clear=True):
            from agent_office.adapters.modes import load_adapter_mode_config

            config = load_adapter_mode_config("gemini")
        self.assertFalse(config.can_execute_commands)

    def _make_task(self, root: Path, task_id: str) -> TaskPaths:
        task_root = root / ".ai" / "tasks" / task_id
        task_root.mkdir(parents=True)
        paths = TaskPaths(
            root=task_root,
            task_json=task_root / "task.json",
            brief=task_root / "brief.md",
            gemini_context=task_root / "gemini-context.md",
            codex_report=task_root / "codex-report.md",
            patch_diff=task_root / "patch.diff",
            grok_review=task_root / "grok-review.md",
            final_for_claude=task_root / "final-for-claude.md",
            claude_decision=task_root / "claude-decision.md",
        )
        paths.brief.write_text("# Brief\n\nImplement P5-02 safely.\n", encoding="utf-8")
        return paths

    def _invocation(self, root: Path, paths: TaskPaths) -> AdapterInvocation:
        return AdapterInvocation(
            task_id=paths.root.name,
            project_root=root,
            paths=paths,
            timeout_seconds=120,
            max_rework_rounds=2,
            final_for_claude_limit=4000,
        )


if __name__ == "__main__":
    unittest.main()
