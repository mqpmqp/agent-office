from __future__ import annotations

import argparse
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_office.adapters.base import AdapterInvocation, AdapterUnavailable
from agent_office.adapters.claude import ClaudeAdapter, claude_metadata_path, claude_report_path
from agent_office.adapters.modes import load_adapter_mode_config, validate_adapter_mode
from agent_office.cli import TaskPaths, run_adapter
from agent_office.doctor import collect_doctor


class ClaudeFinalAdapterTests(unittest.TestCase):
    def test_claude_remains_mock_by_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            config = load_adapter_mode_config("claude")
        self.assertEqual(config.mode, "mock")
        self.assertTrue(config.enabled)

    def test_claude_real_without_key_marks_only_claude_env_failed(self) -> None:
        env = {"AGENTOFFICE_CLAUDE_MODE": "real"}
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, env, clear=True):
            report = collect_doctor(Path(tmp))

        rows = {row["adapter"]: row for row in report["adapter_modes"]["rows"]}
        self.assertEqual(rows["claude"]["status"], "env_failed")
        self.assertFalse(rows["claude"]["env_ok"])
        self.assertEqual(rows["gemini"]["status"], "ok")
        self.assertEqual(rows["codex"]["status"], "ok")
        self.assertEqual(rows["grok"]["status"], "ok")

    def test_claude_real_without_key_fallback_to_mock(self) -> None:
        env = {
            "AGENTOFFICE_CLAUDE_MODE": "real",
            "AGENTOFFICE_CLAUDE_FALLBACK_TO_MOCK": "true",
        }
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, env, clear=True):
            root = Path(tmp)
            paths = self._make_task(root, "T-CLAUDE-FALLBACK")
            args = argparse.Namespace(
                task_id="T-CLAUDE-FALLBACK",
                mock=False,
                real=True,
                adapter="claude",
                timeout=None,
                dry_run=False,
            )
            result = run_adapter("final", args, paths)
            decision_exists = paths.claude_decision.exists()

        self.assertEqual(result.metadata["fallback_used"], True)
        self.assertIn("fallback_used=true", result.detail)
        self.assertTrue(decision_exists)

    def test_claude_real_dry_run_generates_final_judge_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._make_task(root, "T-CLAUDE-DRY")
            self._make_staged_artifacts(root)
            env = {
                "AGENTOFFICE_CLAUDE_MODE": "real",
                "AGENTOFFICE_CLAUDE_DRY_RUN": "true",
                "ANTHROPIC_API_KEY": "fake-anthropic-key",
            }
            adapter = ClaudeAdapter()

            with patch.dict(os.environ, env, clear=True), patch.object(
                adapter, "_send_real_request", side_effect=AssertionError("network path should not be called")
            ):
                result = adapter.final(self._invocation(root, paths))

            report_path = claude_report_path(root)
            metadata_path = claude_metadata_path(root)
            report_exists = report_path.exists()
            metadata_exists = metadata_path.exists()
            task_decision_exists = paths.claude_decision.exists()
            report_text = report_path.read_text(encoding="utf-8")
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

        self.assertTrue(report_exists)
        self.assertTrue(metadata_exists)
        self.assertFalse(task_decision_exists)
        self.assertEqual(result.metadata["adapter"], "claude")
        self.assertEqual(result.metadata["role"], "final_judge")
        self.assertEqual(result.metadata["dry_run"], True)
        self.assertEqual(result.metadata["real_request_sent"], False)
        self.assertEqual(result.metadata["report_path"], ".ai/claude/final-judge.md")
        self.assertEqual(metadata["decision"], "APPROVE")
        self.assertIn("# Claude Final Judge", report_text)
        self.assertIn("## Decision", report_text)
        self.assertIn("did not apply changes", report_text)

    def test_claude_real_dry_run_does_not_read_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._make_task(root, "T-CLAUDE-NOENV")
            self._make_staged_artifacts(root)
            (root / ".env").write_text("ANTHROPIC_API_KEY=REAL_SECRET_SHOULD_NOT_APPEAR\n", encoding="utf-8")
            env = {
                "AGENTOFFICE_CLAUDE_MODE": "real",
                "AGENTOFFICE_CLAUDE_DRY_RUN": "true",
                "ANTHROPIC_API_KEY": "fake-anthropic-key",
            }
            with patch.dict(os.environ, env, clear=True):
                ClaudeAdapter().final(self._invocation(root, paths))
            combined = (
                claude_report_path(root).read_text(encoding="utf-8")
                + claude_metadata_path(root).read_text(encoding="utf-8")
            )

        self.assertNotIn("REAL_SECRET_SHOULD_NOT_APPEAR", combined)

    def test_claude_non_dry_run_rejected_without_allow_flag(self) -> None:
        env = {
            "AGENTOFFICE_CLAUDE_MODE": "real",
            "AGENTOFFICE_CLAUDE_DRY_RUN": "false",
            "ANTHROPIC_API_KEY": "fake-anthropic-key",
        }
        config = load_adapter_mode_config("claude", env)
        validation = validate_adapter_mode(config, env)
        self.assertEqual(validation.status, "invalid")
        self.assertTrue(any("ALLOW_NON_DRY_RUN" in error for error in validation.errors))

    def test_claude_cannot_write_outside_ai_claude(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(AdapterUnavailable):
                ClaudeAdapter()._safe_write_text(root, root / "README.md", "bad write")

    def test_claude_cannot_execute_commands_by_default(self) -> None:
        env = {"AGENTOFFICE_CLAUDE_MODE": "real", "ANTHROPIC_API_KEY": "fake-anthropic-key"}
        config = load_adapter_mode_config("claude", env)
        self.assertFalse(config.can_execute_commands)

    def test_claude_does_not_apply_patches_or_modify_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._make_task(root, "T-CLAUDE-NOAPPLY")
            self._make_staged_artifacts(root)
            readme = root / "README.md"
            readme.write_text("# AgentOffice\n", encoding="utf-8")
            before = readme.read_text(encoding="utf-8")
            env = {
                "AGENTOFFICE_CLAUDE_MODE": "real",
                "AGENTOFFICE_CLAUDE_DRY_RUN": "true",
                "ANTHROPIC_API_KEY": "fake-anthropic-key",
            }
            with patch.dict(os.environ, env, clear=True):
                ClaudeAdapter().final(self._invocation(root, paths))
            after = readme.read_text(encoding="utf-8")

        self.assertEqual(before, after)

    def test_claude_decision_is_constrained(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._make_task(root, "T-CLAUDE-DECISION")
            self._make_staged_artifacts(root)
            (root / ".ai" / "grok" / "metadata.json").write_text(
                json.dumps({"recommendation": "REQUEST_CODEX_REVISION", "risk_flags": ["needs_tests"]}) + "\n",
                encoding="utf-8",
            )
            env = {
                "AGENTOFFICE_CLAUDE_MODE": "real",
                "AGENTOFFICE_CLAUDE_DRY_RUN": "true",
                "ANTHROPIC_API_KEY": "fake-anthropic-key",
            }
            with patch.dict(os.environ, env, clear=True):
                result = ClaudeAdapter().final(self._invocation(root, paths))
            metadata = json.loads(claude_metadata_path(root).read_text(encoding="utf-8"))

        self.assertIn(metadata["decision"], {"APPROVE", "REQUEST_CHANGES", "REJECT"})
        self.assertEqual(metadata["decision"], "REQUEST_CHANGES")
        self.assertEqual(result.decision, "REQUEST_CHANGES")

    def test_claude_reviews_staged_gemini_codex_and_grok_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._make_task(root, "T-CLAUDE-ARTIFACTS")
            self._make_staged_artifacts(root)
            env = {
                "AGENTOFFICE_CLAUDE_MODE": "real",
                "AGENTOFFICE_CLAUDE_DRY_RUN": "true",
                "ANTHROPIC_API_KEY": "fake-anthropic-key",
            }
            with patch.dict(os.environ, env, clear=True):
                ClaudeAdapter().final(self._invocation(root, paths))
            report = claude_report_path(root).read_text(encoding="utf-8")

        self.assertIn(".ai/context/gemini-context.md", report)
        self.assertIn(".ai/codex/patch.diff", report)
        self.assertIn(".ai/codex/codex-report.md", report)
        self.assertIn(".ai/grok/redteam-report.md", report)

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
        paths.brief.write_text("# Brief\n\nJudge P5-05 safely.\n", encoding="utf-8")
        paths.final_for_claude.write_text("# Final For Claude\n\nProceed unless staged risks block.\n", encoding="utf-8")
        return paths

    def _make_staged_artifacts(self, root: Path) -> None:
        context_dir = root / ".ai" / "context"
        context_dir.mkdir(parents=True)
        (context_dir / "gemini-context.md").write_text("# Gemini Context\n\nSafe context.\n", encoding="utf-8")

        codex_dir = root / ".ai" / "codex"
        codex_dir.mkdir(parents=True)
        (codex_dir / "patch.diff").write_text(
            "diff --git a/docs/example.md b/docs/example.md\n"
            "--- /dev/null\n"
            "+++ b/docs/example.md\n"
            "@@ -0,0 +1 @@\n"
            "+Example\n",
            encoding="utf-8",
        )
        (codex_dir / "codex-report.md").write_text("# Codex Implementation Report\n", encoding="utf-8")
        (codex_dir / "metadata.json").write_text('{"patch_validation_status": "ok"}\n', encoding="utf-8")

        grok_dir = root / ".ai" / "grok"
        grok_dir.mkdir(parents=True)
        (grok_dir / "redteam-report.md").write_text("# Grok Redteam Report\n\nRecommendation: PASS_TO_CLAUDE\n", encoding="utf-8")
        (grok_dir / "metadata.json").write_text(
            json.dumps({"recommendation": "PASS_TO_CLAUDE", "risk_flags": []}) + "\n",
            encoding="utf-8",
        )

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
