from __future__ import annotations

import hashlib
import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from agent_office import cli, review_artifact
from agent_office.review_artifact import CaptureCommand


def run_cli(argv: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = cli.main(argv)
    return exit_code, stdout.getvalue(), stderr.getvalue()


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


class ReviewArtifactCliTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.validation_commands = (
            CaptureCommand("validation ok", ("python3", "-c", "print('validation ok')")),
        )
        self.smoke_return = (
            [CaptureCommand("smoke ok", ("python3", "-c", "print('smoke ok')"))],
            ["NO_EXISTING_RUN_DIRECTORY_FOUND"],
        )

    def _repo(self, root: Path) -> tuple[str, str]:
        git(root, "init")
        git(root, "checkout", "-b", "phase14/p14-claude-review-artifact-exporter")
        (root / "README.md").write_text("# Temp AgentOffice\n", encoding="utf-8")
        (root / "keep.txt").write_text("base\n", encoding="utf-8")
        (root / "delete.txt").write_text("delete me\n", encoding="utf-8")
        git(root, "add", "README.md", "keep.txt", "delete.txt")
        git(root, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "base")
        base = git(root, "rev-parse", "HEAD")
        (root / "keep.txt").write_text("review\n", encoding="utf-8")
        (root / "new.txt").write_text("new file\n", encoding="utf-8")
        (root / "delete.txt").unlink()
        git(root, "add", "-A")
        git(root, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "review")
        review = git(root, "rev-parse", "HEAD")
        return base, review

    def _export(self, root: Path, out: Path, base: str, review: str, *, json_mode: bool = True) -> tuple[int, str, str]:
        argv = [
            "review-artifact",
            "export",
            "--base",
            base,
            "--review",
            review,
            "--branch",
            "phase14/p14-claude-review-artifact-exporter",
            "--out",
            str(out),
            "--title",
            "P14 Claude Review Artifact Exporter",
        ]
        if json_mode:
            argv.append("--json")
        with patch.object(cli, "PROJECT_ROOT", root), patch.object(review_artifact, "VALIDATION_COMMANDS", self.validation_commands), patch.object(
            review_artifact, "build_smoke_commands", return_value=self.smoke_return
        ):
            return run_cli(argv)

    def test_review_artifact_export_json_writes_markdown_and_sha256(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as export_dir:
            root = Path(tmpdir)
            base, review = self._repo(root)
            out = Path(export_dir) / "artifact.md"

            exit_code, stdout, stderr = self._export(root, out, base, review)

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            artifact = out.read_text(encoding="utf-8")
            sidecar = Path(f"{out}.sha256").read_text(encoding="utf-8")
            digest = hashlib.sha256(out.read_bytes()).hexdigest()

        self.assertEqual(payload["kind"], "review_artifact_export")
        self.assertTrue(payload["valid"])
        self.assertEqual(payload["base"], base)
        self.assertEqual(payload["review"], review)
        self.assertEqual(payload["artifact_basename"], "artifact.md")
        self.assertEqual(payload["sha256_basename"], "artifact.md.sha256")
        self.assertEqual(payload["sha256_verify_command"], f"cd {out.parent} && sha256sum -c artifact.md.sha256")
        self.assertEqual(payload["sha256"], digest)
        self.assertEqual(sidecar, f"{digest}  artifact.md\n")
        self.assertTrue(payload["validation_success"])
        self.assertTrue(payload["smoke_success"])
        self.assertEqual(payload["missing_file_markers"], 0)
        self.assertEqual(payload["empty_section_markers"], 0)
        for section in payload["sections"]:
            self.assertIn(f"## {section}", artifact)
        self.assertIn("MISSING_FILE_MARKERS: 0", artifact)
        self.assertIn("EMPTY_SECTION_MARKERS: 0", artifact)
        self.assertIn("validation_success: true", artifact)
        self.assertIn("git diff --name-status", artifact)
        self.assertIn("diff --git", artifact)
        self.assertIn("### keep.txt", artifact)
        self.assertIn("review", artifact)
        self.assertIn("### new.txt", artifact)
        self.assertIn("### delete.txt", artifact)
        self.assertIn("snapshot_state: deleted", artifact)
        self.assertIn("## Validation outputs", artifact)
        self.assertIn("validation ok", artifact)
        self.assertIn("## Smoke outputs", artifact)
        self.assertIn("NO_EXISTING_RUN_DIRECTORY_FOUND", artifact)
        self.assertIn("REPORT_NOT_FOUND", artifact)
        self.assertIn("# Temp AgentOffice", artifact)

    def test_review_artifact_text_output_contains_verification_and_powershell_hint(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as export_dir:
            root = Path(tmpdir)
            base, review = self._repo(root)
            out = Path(export_dir) / "artifact.md"

            exit_code, stdout, stderr = self._export(root, out, base, review, json_mode=False)

        self.assertEqual(exit_code, 0, stderr)
        self.assertIn("Review artifact exported", stdout)
        self.assertIn(f"Verification command: cd {out.parent} && sha256sum -c artifact.md.sha256", stdout)
        self.assertIn("PowerShell download", stdout)
        self.assertIn("validation_success: true", stdout)

    def test_review_artifact_missing_commit_is_stable_json_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as export_dir:
            root = Path(tmpdir)
            base, _review = self._repo(root)
            out = Path(export_dir) / "artifact.md"
            with patch.object(cli, "PROJECT_ROOT", root):
                exit_code, stdout, stderr = run_cli(
                    [
                        "review-artifact",
                        "export",
                        "--base",
                        base,
                        "--review",
                        "missing",
                        "--branch",
                        "phase14/p14-claude-review-artifact-exporter",
                        "--out",
                        str(out),
                        "--title",
                        "P14",
                        "--json",
                    ]
                )

        self.assertEqual(exit_code, 2)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertFalse(payload["valid"])
        self.assertEqual(payload["blocking_reasons"], ["invalid_commit"])
        self.assertNotIn("Traceback", stdout + stderr)

    def test_review_artifact_output_path_errors_are_stable_json_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            base, review = self._repo(root)
            existing_dir = root / "exports"
            existing_dir.mkdir()
            cases = [
                (existing_dir, "invalid_output"),
                (root / "missing" / "artifact.md", "invalid_output"),
                (root / ".ai" / "runs" / "artifact.md", "unsafe_path"),
            ]
            for out, reason in cases:
                with self.subTest(out=out):
                    with patch.object(cli, "PROJECT_ROOT", root):
                        exit_code, stdout, stderr = run_cli(
                            [
                                "review-artifact",
                                "export",
                                "--base",
                                base,
                                "--review",
                                review,
                                "--branch",
                                "phase14/p14-claude-review-artifact-exporter",
                                "--out",
                                str(out),
                                "--title",
                                "P14",
                                "--json",
                            ]
                        )
                    self.assertEqual(exit_code, 2)
                    self.assertEqual(stderr, "")
                    payload = json.loads(stdout)
                    self.assertEqual(payload["blocking_reasons"], [reason])
                    self.assertNotIn("Traceback", stdout + stderr)

    def test_review_artifact_refuses_symlink_out_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as export_dir:
            root = Path(tmpdir)
            base, review = self._repo(root)
            target = Path(export_dir) / "target.md"
            target.write_text("do not overwrite", encoding="utf-8")
            link = Path(export_dir) / "link.md"
            try:
                link.symlink_to(target)
            except (NotImplementedError, OSError) as exc:
                self.skipTest(f"symlink unsupported: {exc}")
            with patch.object(cli, "PROJECT_ROOT", root):
                exit_code, stdout, stderr = run_cli(
                    [
                        "review-artifact",
                        "export",
                        "--base",
                        base,
                        "--review",
                        review,
                        "--branch",
                        "phase14/p14-claude-review-artifact-exporter",
                        "--out",
                        str(link),
                        "--title",
                        "P14",
                        "--json",
                    ]
                )
            target_text = target.read_text(encoding="utf-8")

        self.assertEqual(exit_code, 2)
        self.assertEqual(stderr, "")
        self.assertEqual(target_text, "do not overwrite")
        payload = json.loads(stdout)
        self.assertEqual(payload["blocking_reasons"], ["unsafe_path"])
        self.assertNotIn("Traceback", stdout + stderr)

    def test_review_artifact_validation_failure_is_captured_not_hard_failure(self) -> None:
        failing_validation = (CaptureCommand("validation fails", ("python3", "-c", "import sys; print('bad'); sys.exit(7)")),)
        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as export_dir:
            root = Path(tmpdir)
            base, review = self._repo(root)
            out = Path(export_dir) / "artifact.md"
            with patch.object(cli, "PROJECT_ROOT", root), patch.object(review_artifact, "VALIDATION_COMMANDS", failing_validation), patch.object(
                review_artifact, "build_smoke_commands", return_value=self.smoke_return
            ):
                exit_code, stdout, stderr = run_cli(
                    [
                        "review-artifact",
                        "export",
                        "--base",
                        base,
                        "--review",
                        review,
                        "--branch",
                        "phase14/p14-claude-review-artifact-exporter",
                        "--out",
                        str(out),
                        "--title",
                        "P14",
                        "--json",
                    ]
                )
            artifact = out.read_text(encoding="utf-8")

        self.assertEqual(exit_code, 0, stderr)
        payload = json.loads(stdout)
        self.assertFalse(payload["validation_success"])
        self.assertIn("validation_success=false; see Validation outputs section", payload["warnings"])
        self.assertIn("validation_success: false", artifact)
        self.assertIn("exit_code: 7", artifact)
        self.assertIn("bad", artifact)
        self.assertNotIn("Traceback", stdout + stderr)

    def test_review_artifact_does_not_mutate_repo_or_write_ai_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as export_dir:
            root = Path(tmpdir)
            base, review = self._repo(root)
            (root / "P13_UNRELATED_REPORT.md").write_text("old report", encoding="utf-8")
            before = git(root, "status", "--short", "--untracked-files=no")
            out = Path(export_dir) / "artifact.md"

            exit_code, stdout, stderr = self._export(root, out, base, review)
            after = git(root, "status", "--short", "--untracked-files=no")
            artifact = out.read_text(encoding="utf-8")

        self.assertEqual(exit_code, 0, stderr)
        self.assertEqual(before, after)
        self.assertFalse((root / ".ai" / "runs").exists())
        self.assertNotIn("old report", artifact)
        self.assertIn("REPORT_NOT_FOUND", artifact)
        payload = json.loads(stdout)
        self.assertTrue(payload["valid"])


if __name__ == "__main__":
    unittest.main()
