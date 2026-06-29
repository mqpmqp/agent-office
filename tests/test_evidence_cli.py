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
    completed = subprocess.run(["git", *args], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
    return completed.stdout.strip()


class EvidenceCliTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.validation_commands = (CaptureCommand("validation ok", ("python3", "-c", "print('validation ok')")),)
        self.smoke_return = ([CaptureCommand("smoke ok", ("python3", "-c", "print('smoke ok')"))], ["NO_EXISTING_RUN_DIRECTORY_FOUND"])

    def _repo(self, root: Path) -> tuple[str, str]:
        git(root, "init")
        git(root, "checkout", "-b", "phase23/p21-p23-evidence-release-batch")
        (root / "README.md").write_text("# Temp AgentOffice\n", encoding="utf-8")
        (root / "file.txt").write_text("base\n", encoding="utf-8")
        git(root, "add", "README.md", "file.txt")
        git(root, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "base")
        base = git(root, "rev-parse", "HEAD")
        (root / "file.txt").write_text("review\n", encoding="utf-8")
        git(root, "add", "file.txt")
        git(root, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "review")
        review = git(root, "rev-parse", "HEAD")
        return base, review

    def _export_review_artifact(self, root: Path, out: Path) -> None:
        base, review = self._repo(root)
        argv = [
            "review-artifact",
            "export",
            "--base",
            base,
            "--review",
            review,
            "--branch",
            "phase23/p21-p23-evidence-release-batch",
            "--out",
            str(out),
            "--title",
            "P23 Evidence Test Artifact",
            "--gate-mode",
            "codex_interim",
            "--claude-status",
            "pending",
            "--codex-self-check-status",
            "pass",
            "--json",
        ]
        with patch.object(cli, "PROJECT_ROOT", root), patch.object(
            review_artifact, "VALIDATION_COMMANDS", self.validation_commands
        ), patch.object(review_artifact, "build_smoke_commands", return_value=self.smoke_return):
            code, stdout, stderr = run_cli(argv)
        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertTrue(payload["valid"])

    def test_registry_help_and_list_root_contracts(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with self.assertRaises(SystemExit) as raised, redirect_stdout(stdout), redirect_stderr(stderr):
            cli.main(["review-artifact", "registry", "--help"])
        self.assertEqual(raised.exception.code, 0)
        self.assertIn("list", stdout.getvalue())
        self.assertIn("inspect", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            empty = root / "empty"
            empty.mkdir()
            artifact = root / "artifact.md"
            artifact.write_text("# local artifact\n", encoding="utf-8")
            digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
            Path(f"{artifact}.sha256").write_text(f"{digest}  artifact.md\n", encoding="utf-8")
            missing = root / "missing"
            with patch.object(cli, "PROJECT_ROOT", root):
                code, stdout, stderr = run_cli(
                    [
                        "review-artifact",
                        "registry",
                        "list",
                        "--root",
                        str(empty),
                        "--root",
                        str(missing),
                        "--root",
                        str(root),
                        "--json",
                    ]
                )

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertTrue(payload["valid"])
        for key in ("valid", "command", "artifacts", "counts", "warnings", "errors", "scanned_paths"):
            self.assertIn(key, payload)
        self.assertGreaterEqual(payload["counts"]["total"], 2)
        self.assertTrue(any(item["path"] == str(artifact) and item["sha256_verified"] is True for item in payload["artifacts"]))
        self.assertTrue(any("root_missing" in warning for warning in payload["warnings"]))
        self.assertTrue(any("root_empty" in warning for warning in payload["warnings"]))
        self.assertNotIn("Traceback", stdout + stderr)

    def test_registry_inspect_handles_missing_bad_json_non_utf8_and_sha_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            bad_json = root / "bad.json"
            bad_json.write_text("{not json", encoding="utf-8")
            non_utf8 = root / "non_utf8.md"
            non_utf8.write_bytes(b"\xff\xfe")
            mismatch = root / "mismatch.md"
            mismatch.write_text("# mismatch\n", encoding="utf-8")
            Path(f"{mismatch}.sha256").write_text(f"{'0' * 64}  mismatch.md\n", encoding="utf-8")
            missing = root / "missing.md"
            with patch.object(cli, "PROJECT_ROOT", root):
                results = [
                    run_cli(["review-artifact", "registry", "inspect", "--path", str(path), "--json"])
                    for path in (bad_json, non_utf8, mismatch, missing)
                ]

        for code, stdout, stderr in results:
            self.assertEqual(code, 0, stderr)
            payload = json.loads(stdout)
            for key in ("valid", "command", "artifact", "warnings", "errors"):
                self.assertIn(key, payload)
            self.assertNotIn("Traceback", stdout + stderr)
        self.assertTrue(any("bad_json" in warning for warning in json.loads(results[0][1])["warnings"]))
        self.assertIn("non_utf8_content", json.loads(results[1][1])["warnings"])
        self.assertIn("sha256_mismatch", json.loads(results[2][1])["errors"])
        self.assertIn("missing_path", json.loads(results[3][1])["errors"])

    def test_lifecycle_status_and_verify_use_existing_review_artifact_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as export_dir:
            root = Path(tmpdir)
            out = Path(export_dir) / "artifact.md"
            self._export_review_artifact(root, out)
            with patch.object(cli, "PROJECT_ROOT", root):
                status_code, status_stdout, status_stderr = run_cli(
                    ["review-artifact", "lifecycle", "status", "--root", export_dir, "--json"]
                )
                verify_code, verify_stdout, verify_stderr = run_cli(
                    ["review-artifact", "lifecycle", "verify", "--root", export_dir, "--json"]
                )

        self.assertEqual(status_code, 0, status_stderr)
        status_payload = json.loads(status_stdout)
        for key in (
            "valid",
            "command",
            "counts",
            "known_artifacts",
            "closure_artifacts",
            "report_artifacts",
            "sha256_files",
            "verified_artifacts",
            "pending_like_artifacts",
            "real_closure_count",
            "fixture_only_count",
            "pending_closed_count",
            "warnings",
            "errors",
            "scanned_paths",
        ):
            self.assertIn(key, status_payload)
        self.assertEqual(status_payload["counts"]["known_artifacts"], 2)
        self.assertEqual(status_payload["counts"]["pending_like_artifacts"], 1)

        self.assertEqual(verify_code, 0, verify_stderr)
        verify_payload = json.loads(verify_stdout)
        for key in ("valid", "command", "checked", "verified", "invalid", "skipped", "counts", "warnings", "errors", "scanned_paths"):
            self.assertIn(key, verify_payload)
        self.assertEqual(verify_payload["counts"]["checked_count"], 1)
        self.assertEqual(verify_payload["counts"]["verified_count"], 1)
        self.assertEqual(verify_payload["counts"]["invalid_count"], 0)
        self.assertEqual(verify_payload["verified"][0]["extracted_fields"]["gate_mode"], "codex_interim")
        self.assertNotIn("Traceback", status_stdout + status_stderr + verify_stdout + verify_stderr)

    def test_lifecycle_verify_does_not_fail_whole_command_on_unverifiable_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifact = root / "not-review.md"
            artifact.write_text("# Not a review artifact\n", encoding="utf-8")
            Path(f"{artifact}.sha256").write_text(f"{'0' * 64}  not-review.md\n", encoding="utf-8")
            with patch.object(cli, "PROJECT_ROOT", root):
                code, stdout, stderr = run_cli(["review-artifact", "lifecycle", "verify", "--root", str(root), "--json"])

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertFalse(payload["valid"])
        self.assertEqual(payload["counts"]["invalid_count"], 1)
        self.assertIn("missing_file_marker_absent", payload["invalid"][0]["errors"])
        self.assertNotIn("Traceback", stdout + stderr)

    def test_export_evidence_help_and_deterministic_package(self) -> None:
        help_stdout = io.StringIO()
        help_stderr = io.StringIO()
        with self.assertRaises(SystemExit) as raised, redirect_stdout(help_stdout), redirect_stderr(help_stderr):
            cli.main(["export-evidence", "--help"])
        self.assertEqual(raised.exception.code, 0)
        self.assertIn("--out", help_stdout.getvalue())
        self.assertEqual(help_stderr.getvalue(), "")

        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as export_dir, tempfile.TemporaryDirectory() as package_dir:
            root = Path(tmpdir)
            out = Path(export_dir) / "artifact.md"
            self._export_review_artifact(root, out)
            package = Path(package_dir)
            (package / "keep.txt").write_text("do not delete\n", encoding="utf-8")
            with patch.object(cli, "PROJECT_ROOT", root):
                first_code, first_stdout, first_stderr = run_cli(
                    ["export-evidence", "--out", str(package), "--root", export_dir, "--json"]
                )
                first_manifest = (package / "manifest.json").read_text(encoding="utf-8")
                first_readme = (package / "README.md").read_text(encoding="utf-8")
                second_code, second_stdout, second_stderr = run_cli(
                    ["export-evidence", "--out", str(package), "--root", export_dir, "--json"]
                )
                second_manifest = (package / "manifest.json").read_text(encoding="utf-8")
                second_readme = (package / "README.md").read_text(encoding="utf-8")
                keep_exists = (package / "keep.txt").is_file()

        self.assertEqual(first_code, 0, first_stderr)
        self.assertEqual(second_code, 0, second_stderr)
        self.assertEqual(first_manifest, second_manifest)
        self.assertEqual(first_readme, second_readme)
        self.assertTrue(keep_exists)
        payload = json.loads(second_stdout)
        manifest = payload["manifest"]
        for key in (
            "schema_version",
            "generated_by",
            "repo",
            "commit",
            "branch",
            "command_map",
            "validation_commands",
            "safety_boundaries",
            "known_limitations",
            "registry_summary",
            "lifecycle_summary",
            "example_artifact_validation",
            "files",
            "warnings",
            "errors",
        ):
            self.assertIn(key, manifest)
        self.assertIn("system overview", first_readme.lower())
        self.assertIn("reviewer instructions", first_readme.lower())
        self.assertNotIn("Traceback", first_stdout + first_stderr + second_stdout + second_stderr)


if __name__ == "__main__":
    unittest.main()
