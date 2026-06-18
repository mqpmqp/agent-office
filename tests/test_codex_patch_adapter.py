from __future__ import annotations

import argparse
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_office.adapters.base import AdapterInvocation, AdapterUnavailable
from agent_office.adapters.codex import CodexAdapter, codex_metadata_path, codex_patch_path, codex_report_path
from agent_office.adapters.modes import load_adapter_mode_config, validate_adapter_mode
from agent_office.adapters.patch_validator import validate_patch_diff
from agent_office.cli import TaskPaths, run_adapter
from agent_office.doctor import collect_doctor


class CodexPatchAdapterTests(unittest.TestCase):
    def test_codex_real_without_key_marks_only_codex_env_failed(self) -> None:
        env = {"AGENTOFFICE_CODEX_MODE": "real"}
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, env, clear=True):
            report = collect_doctor(Path(tmp))

        rows = {row["adapter"]: row for row in report["adapter_modes"]["rows"]}
        self.assertEqual(rows["codex"]["status"], "env_failed")
        self.assertFalse(rows["codex"]["env_ok"])
        self.assertEqual(rows["gemini"]["status"], "ok")
        self.assertEqual(rows["grok"]["status"], "ok")
        self.assertEqual(rows["claude"]["status"], "ok")

    def test_codex_real_without_key_fallback_to_mock(self) -> None:
        env = {
            "AGENTOFFICE_CODEX_MODE": "real",
            "AGENTOFFICE_CODEX_FALLBACK_TO_MOCK": "true",
        }
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, env, clear=True):
            root = Path(tmp)
            paths = self._make_task(root, "T-CODEX-FALLBACK")
            args = argparse.Namespace(task_id="T-CODEX-FALLBACK", mock=False, real=True, adapter="codex", timeout=None)
            result = run_adapter("implement", args, paths)
            report_exists = paths.codex_report.exists()
            patch_exists = paths.patch_diff.exists()

        self.assertEqual(result.metadata["fallback_used"], True)
        self.assertIn("fallback_used=true", result.detail)
        self.assertTrue(report_exists)
        self.assertTrue(patch_exists)

    def test_codex_real_dry_run_generates_patch_only_artifacts_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._make_task(root, "T-CODEX-DRY")
            (root / ".ai" / "context").mkdir(parents=True)
            (root / ".ai" / "context" / "gemini-context.md").write_text("# Gemini Context\n", encoding="utf-8")
            (root / "README.md").write_text("# AgentOffice\n", encoding="utf-8")
            env = {
                "AGENTOFFICE_CODEX_MODE": "real",
                "AGENTOFFICE_CODEX_DRY_RUN": "true",
                "OPENAI_API_KEY": "fake-openai-key",
            }
            adapter = CodexAdapter()

            with patch.dict(os.environ, env, clear=True), patch.object(
                adapter, "_send_real_request", side_effect=AssertionError("network path should not be called")
            ):
                result = adapter.implement(self._invocation(root, paths))

            patch_path = codex_patch_path(root)
            report_path = codex_report_path(root)
            metadata_path = codex_metadata_path(root)
            patch_exists = patch_path.exists()
            report_exists = report_path.exists()
            metadata_exists = metadata_path.exists()
            task_report_exists = paths.codex_report.exists()
            task_patch_exists = paths.patch_diff.exists()
            patch_text = patch_path.read_text(encoding="utf-8")
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

        self.assertTrue(patch_exists)
        self.assertTrue(report_exists)
        self.assertTrue(metadata_exists)
        self.assertFalse(task_report_exists)
        self.assertFalse(task_patch_exists)
        self.assertEqual(result.metadata["adapter"], "codex")
        self.assertEqual(result.metadata["dry_run"], True)
        self.assertEqual(result.metadata["real_request_sent"], False)
        self.assertEqual(result.metadata["patch_path"], ".ai/codex/patch.diff")
        self.assertEqual(metadata["patch_validation_status"], "ok")
        self.assertIn("diff --git", patch_text)

    def test_codex_real_dry_run_does_not_read_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._make_task(root, "T-CODEX-NOENV")
            (root / ".env").write_text("OPENAI_API_KEY=REAL_SECRET_SHOULD_NOT_APPEAR\n", encoding="utf-8")
            env = {
                "AGENTOFFICE_CODEX_MODE": "real",
                "AGENTOFFICE_CODEX_DRY_RUN": "true",
                "OPENAI_API_KEY": "fake-openai-key",
            }
            with patch.dict(os.environ, env, clear=True):
                CodexAdapter().implement(self._invocation(root, paths))
            combined = (
                codex_patch_path(root).read_text(encoding="utf-8")
                + codex_report_path(root).read_text(encoding="utf-8")
                + codex_metadata_path(root).read_text(encoding="utf-8")
            )

        self.assertNotIn("REAL_SECRET_SHOULD_NOT_APPEAR", combined)

    def test_codex_non_dry_run_rejected_without_allow_flag(self) -> None:
        env = {
            "AGENTOFFICE_CODEX_MODE": "real",
            "AGENTOFFICE_CODEX_DRY_RUN": "false",
            "OPENAI_API_KEY": "fake-openai-key",
        }
        config = load_adapter_mode_config("codex", env)
        validation = validate_adapter_mode(config, env)
        self.assertEqual(validation.status, "invalid")
        self.assertTrue(any("ALLOW_NON_DRY_RUN" in error for error in validation.errors))

    def test_codex_cannot_write_outside_ai_codex(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(AdapterUnavailable):
                CodexAdapter()._safe_write_text(root, root / "README.md", "bad write")

    def test_codex_cannot_execute_commands_by_default(self) -> None:
        env = {"AGENTOFFICE_CODEX_MODE": "real", "OPENAI_API_KEY": "fake-openai-key"}
        config = load_adapter_mode_config("codex", env)
        self.assertFalse(config.can_execute_commands)

    def test_patch_validator_rejects_unsafe_patches(self) -> None:
        cases = [
            ("diff --git a/.env b/.env\n--- a/.env\n+++ b/.env\n@@ -0,0 +1 @@\n+X=1\n", "env_file"),
            ("diff --git a/README.md b/README.md\n--- a/README.md\n+++ b/README.md\n@@ -0,0 +1 @@\n+OPENAI_API_KEY=sk-123456789012abcdef\n", "secret_addition"),
            ("diff --git a/tests/test_guard.py b/tests/test_guard.py\n--- a/tests/test_guard.py\n+++ b/tests/test_guard.py\n@@ -1 +0,0 @@\n-def test_safety_guard(): pass\n", "guard_test_delete"),
            ("diff --git a/.env.example b/.env.example\n--- a/.env.example\n+++ b/.env.example\n@@ -1 +1 @@\n+AGENTOFFICE_CODEX_DRY_RUN=false\n", "weaken_safety_defaults"),
            ("diff --git a/.env.example b/.env.example\n--- a/.env.example\n+++ b/.env.example\n@@ -1 +1 @@\n+AGENTOFFICE_CODEX_ALLOW_NON_DRY_RUN=true\n", "weaken_safety_defaults"),
            ("diff --git a/.env.example b/.env.example\n--- a/.env.example\n+++ b/.env.example\n@@ -1 +1 @@\n+AGENTOFFICE_CODEX_CAN_EXECUTE_COMMANDS=true\n", "weaken_safety_defaults"),
        ]
        for patch_text, expected_flag in cases:
            with self.subTest(expected_flag=expected_flag):
                result = validate_patch_diff(patch_text)
                self.assertEqual(result.status, "rejected")
                self.assertIn(expected_flag, result.risk_flags)

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
        paths.brief.write_text("# Brief\n\nImplement P5-03 safely.\n", encoding="utf-8")
        paths.gemini_context.write_text("# Gemini Context\n\nMock context.\n", encoding="utf-8")
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
