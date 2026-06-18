from __future__ import annotations

import argparse
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_office.adapters.base import AdapterInvocation, AdapterUnavailable
from agent_office.adapters.grok import GrokAdapter, grok_metadata_path, grok_report_path
from agent_office.adapters.modes import load_adapter_mode_config, validate_adapter_mode
from agent_office.cli import TaskPaths, run_adapter
from agent_office.doctor import collect_doctor


class GrokReviewAdapterTests(unittest.TestCase):
    def test_grok_real_without_key_marks_only_grok_env_failed(self) -> None:
        env = {"AGENTOFFICE_GROK_MODE": "real"}
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, env, clear=True):
            report = collect_doctor(Path(tmp))

        rows = {row["adapter"]: row for row in report["adapter_modes"]["rows"]}
        self.assertEqual(rows["grok"]["status"], "env_failed")
        self.assertFalse(rows["grok"]["env_ok"])
        self.assertEqual(rows["gemini"]["status"], "ok")
        self.assertEqual(rows["codex"]["status"], "ok")
        self.assertEqual(rows["claude"]["status"], "ok")

    def test_grok_real_without_key_fallback_to_mock(self) -> None:
        env = {
            "AGENTOFFICE_GROK_MODE": "real",
            "AGENTOFFICE_GROK_FALLBACK_TO_MOCK": "true",
        }
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, env, clear=True):
            root = Path(tmp)
            paths = self._make_task(root, "T-GROK-FALLBACK")
            args = argparse.Namespace(task_id="T-GROK-FALLBACK", mock=False, real=True, adapter="grok", timeout=None)
            result = run_adapter("redteam", args, paths)
            review_exists = paths.grok_review.exists()

        self.assertEqual(result.metadata["fallback_used"], True)
        self.assertIn("fallback_used=true", result.detail)
        self.assertTrue(review_exists)

    def test_grok_real_dry_run_generates_review_only_artifacts_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._make_task(root, "T-GROK-DRY")
            self._make_codex_artifacts(root)
            env = {
                "AGENTOFFICE_GROK_MODE": "real",
                "AGENTOFFICE_GROK_DRY_RUN": "true",
                "XAI_API_KEY": "fake-xai-key",
            }
            adapter = GrokAdapter()

            with patch.dict(os.environ, env, clear=True), patch.object(
                adapter, "_send_real_request", side_effect=AssertionError("network path should not be called")
            ):
                result = adapter.redteam(self._invocation(root, paths))

            report_path = grok_report_path(root)
            metadata_path = grok_metadata_path(root)
            report_exists = report_path.exists()
            metadata_exists = metadata_path.exists()
            task_review_exists = paths.grok_review.exists()
            report_text = report_path.read_text(encoding="utf-8")
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

        self.assertTrue(report_exists)
        self.assertTrue(metadata_exists)
        self.assertFalse(task_review_exists)
        self.assertEqual(result.metadata["adapter"], "grok")
        self.assertEqual(result.metadata["dry_run"], True)
        self.assertEqual(result.metadata["real_request_sent"], False)
        self.assertEqual(result.metadata["report_path"], ".ai/grok/redteam-report.md")
        self.assertIn(metadata["recommendation"], {"PASS_TO_CLAUDE", "REQUEST_CODEX_REVISION", "BLOCK"})
        self.assertIn("# Grok Redteam Report", report_text)
        self.assertIn("did not apply changes", report_text)

    def test_grok_real_dry_run_does_not_read_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._make_task(root, "T-GROK-NOENV")
            self._make_codex_artifacts(root)
            (root / ".env").write_text("XAI_API_KEY=REAL_SECRET_SHOULD_NOT_APPEAR\n", encoding="utf-8")
            env = {
                "AGENTOFFICE_GROK_MODE": "real",
                "AGENTOFFICE_GROK_DRY_RUN": "true",
                "XAI_API_KEY": "fake-xai-key",
            }
            with patch.dict(os.environ, env, clear=True):
                GrokAdapter().redteam(self._invocation(root, paths))
            combined = (
                grok_report_path(root).read_text(encoding="utf-8")
                + grok_metadata_path(root).read_text(encoding="utf-8")
            )

        self.assertNotIn("REAL_SECRET_SHOULD_NOT_APPEAR", combined)

    def test_grok_non_dry_run_rejected_without_allow_flag(self) -> None:
        env = {
            "AGENTOFFICE_GROK_MODE": "real",
            "AGENTOFFICE_GROK_DRY_RUN": "false",
            "XAI_API_KEY": "fake-xai-key",
        }
        config = load_adapter_mode_config("grok", env)
        validation = validate_adapter_mode(config, env)
        self.assertEqual(validation.status, "invalid")
        self.assertTrue(any("ALLOW_NON_DRY_RUN" in error for error in validation.errors))

    def test_grok_cannot_write_outside_ai_grok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(AdapterUnavailable):
                GrokAdapter()._safe_write_text(root, root / "README.md", "bad write")

    def test_grok_cannot_execute_commands_by_default(self) -> None:
        env = {"AGENTOFFICE_GROK_MODE": "real", "XAI_API_KEY": "fake-xai-key"}
        config = load_adapter_mode_config("grok", env)
        self.assertFalse(config.can_execute_commands)

    def test_grok_missing_patch_fails_safely(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._make_task(root, "T-GROK-MISSING-PATCH")
            paths.patch_diff.unlink()
            env = {
                "AGENTOFFICE_GROK_MODE": "real",
                "AGENTOFFICE_GROK_DRY_RUN": "true",
                "XAI_API_KEY": "fake-xai-key",
            }
            with patch.dict(os.environ, env, clear=True):
                with self.assertRaises(AdapterUnavailable) as ctx:
                    GrokAdapter().redteam(self._invocation(root, paths))
        self.assertIn("patch.diff is missing", str(ctx.exception))

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
        paths.brief.write_text("# Brief\n\nReview P5-04 safely.\n", encoding="utf-8")
        paths.gemini_context.write_text("# Gemini Context\n\nMock context.\n", encoding="utf-8")
        paths.codex_report.write_text("# Codex Report\n\nMock report.\n", encoding="utf-8")
        paths.patch_diff.write_text(
            "diff --git a/docs/example.md b/docs/example.md\n"
            "--- /dev/null\n"
            "+++ b/docs/example.md\n"
            "@@ -0,0 +1 @@\n"
            "+Example\n",
            encoding="utf-8",
        )
        return paths

    def _make_codex_artifacts(self, root: Path) -> None:
        codex_dir = root / ".ai" / "codex"
        codex_dir.mkdir(parents=True)
        (codex_dir / "patch.diff").write_text(
            "diff --git a/docs/codex-dry-run-proposal.md b/docs/codex-dry-run-proposal.md\n"
            "--- /dev/null\n"
            "+++ b/docs/codex-dry-run-proposal.md\n"
            "@@ -0,0 +1 @@\n"
            "+Patch proposal\n",
            encoding="utf-8",
        )
        (codex_dir / "codex-report.md").write_text("# Codex Implementation Report\n", encoding="utf-8")
        (codex_dir / "metadata.json").write_text('{"patch_validation_status": "ok"}\n', encoding="utf-8")
        context_dir = root / ".ai" / "context"
        context_dir.mkdir(parents=True)
        (context_dir / "gemini-context.md").write_text("# Gemini Context\n", encoding="utf-8")

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
