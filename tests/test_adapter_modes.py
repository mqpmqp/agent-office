from __future__ import annotations

import argparse
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from agent_office.adapters.modes import (
    ADAPTER_MODE_NAMES,
    format_adapter_mode_table,
    load_adapter_mode_config,
    load_adapter_mode_registry,
    validate_adapter_mode,
)
from agent_office.cli import TaskPaths, run_adapter
from agent_office.doctor import main as doctor_main


class AdapterModeTests(unittest.TestCase):
    def test_default_all_mock(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            registry = load_adapter_mode_registry()
        self.assertEqual(set(registry), set(ADAPTER_MODE_NAMES))
        self.assertTrue(all(config.mode == "mock" for config in registry.values()))

    def test_claude_remains_mock_by_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            config = load_adapter_mode_config("claude")
        self.assertEqual(config.mode, "mock")
        self.assertTrue(config.enabled)

    def test_codex_remains_mock_by_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            config = load_adapter_mode_config("codex")
        self.assertEqual(config.mode, "mock")
        self.assertTrue(config.enabled)

    def test_grok_remains_mock_by_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            config = load_adapter_mode_config("grok")
        self.assertEqual(config.mode, "mock")
        self.assertTrue(config.enabled)

    def test_gemini_real_without_env_marks_env_failed(self) -> None:
        env = {"AGENTOFFICE_GEMINI_MODE": "real"}
        config = load_adapter_mode_config("gemini", env)
        validation = validate_adapter_mode(config, env)
        self.assertEqual(validation.status, "env_failed")
        self.assertFalse(validation.env_ok)
        self.assertIn("GEMINI_API_KEY", validation.errors[0])

    def test_gemini_real_dry_run_with_env_validates(self) -> None:
        env = {
            "AGENTOFFICE_GEMINI_MODE": "real",
            "GEMINI_API_KEY": "fake-key",
            "AGENTOFFICE_GEMINI_DRY_RUN": "true",
        }
        config = load_adapter_mode_config("gemini", env)
        validation = validate_adapter_mode(config, env)
        self.assertTrue(config.dry_run)
        self.assertTrue(validation.env_ok)
        self.assertEqual(validation.status, "ok")
        self.assertEqual(validation.errors, ())

    def test_real_mode_without_dry_run_rejected_unless_allowed(self) -> None:
        env = {
            "AGENTOFFICE_GEMINI_MODE": "real",
            "GEMINI_API_KEY": "fake-key",
            "AGENTOFFICE_GEMINI_DRY_RUN": "false",
        }
        config = load_adapter_mode_config("gemini", env)
        validation = validate_adapter_mode(config, env)
        self.assertEqual(validation.status, "invalid")
        self.assertTrue(any("ALLOW_NON_DRY_RUN" in error for error in validation.errors))

        allowed_env = dict(env)
        allowed_env["AGENTOFFICE_GEMINI_ALLOW_NON_DRY_RUN"] = "true"
        allowed_config = load_adapter_mode_config("gemini", allowed_env)
        allowed_validation = validate_adapter_mode(allowed_config, allowed_env)
        self.assertFalse(any("ALLOW_NON_DRY_RUN" in error for error in allowed_validation.errors))

    def test_no_adapter_can_execute_commands_by_default(self) -> None:
        env = {
            "AGENTOFFICE_GEMINI_MODE": "real",
            "AGENTOFFICE_CODEX_MODE": "real",
            "AGENTOFFICE_GROK_MODE": "real",
            "AGENTOFFICE_CLAUDE_MODE": "real",
            "GEMINI_API_KEY": "fake-gemini-key",
            "OPENAI_API_KEY": "fake-openai-key",
            "XAI_API_KEY": "fake-xai-key",
            "ANTHROPIC_API_KEY": "fake-anthropic-key",
        }
        registry = load_adapter_mode_registry(env)
        self.assertTrue(all(not config.can_execute_commands for config in registry.values()))

        explicit_env = dict(env)
        explicit_env["AGENTOFFICE_CLAUDE_CAN_EXECUTE_COMMANDS"] = "true"
        explicit_config = load_adapter_mode_config("claude", explicit_env)
        self.assertTrue(explicit_config.can_execute_commands)

    def test_fallback_to_mock_works(self) -> None:
        env = {
            "AGENTOFFICE_GEMINI_MODE": "real",
            "AGENTOFFICE_GEMINI_FALLBACK_TO_MOCK": "true",
        }
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, env, clear=True):
            root = Path(tmp)
            task_root = root / ".ai" / "tasks" / "T-FALLBACK"
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
            paths.brief.write_text("# Brief\n", encoding="utf-8")
            args = argparse.Namespace(task_id="T-FALLBACK", mock=False, real=True, adapter="gemini", timeout=None)
            result = run_adapter("context", args, paths)
            context_exists = paths.gemini_context.exists()

        self.assertEqual(result.metadata["fallback_used"], True)
        self.assertIn("fallback_used=true", result.detail)
        self.assertTrue(context_exists)

    def test_doctor_adapters_table(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            table = format_adapter_mode_table()
        self.assertIn("adapter | mode | dry_run | env_ok | fallback | status", table)
        self.assertIn("gemini | mock | false | true | false | ok", table)

        output = io.StringIO()
        with patch.dict(os.environ, {}, clear=True), redirect_stdout(output):
            exit_code = doctor_main(["--adapters"])
        self.assertEqual(exit_code, 0)
        self.assertIn("claude | mock | false | true | false | ok", output.getvalue())


if __name__ == "__main__":
    unittest.main()
