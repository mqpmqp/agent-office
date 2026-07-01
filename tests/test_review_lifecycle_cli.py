from __future__ import annotations

import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from agent_office import cli, review_lifecycle
from agent_office.review_lifecycle import CaptureCommand


def run_cli(argv: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = cli.main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(["git", *args], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
    return completed.stdout.strip()


class ReviewLifecycleCliTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.validation_commands = (CaptureCommand("validation ok", ("python3", "-c", "print('validation ok')")),)

    def _repo(self, root: Path) -> tuple[str, str, Path]:
        git(root, "init")
        git(root, "checkout", "-b", "phase31/phase-lifecycle-review-system")
        git(root, "config", "user.name", "Test")
        git(root, "config", "user.email", "test@example.com")
        (root / "README.md").write_text("# AgentOffice\n\nbase\n", encoding="utf-8")
        git(root, "add", "README.md")
        git(root, "commit", "-m", "base")
        baseline = git(root, "rev-parse", "HEAD")
        report = root / "P31_PHASE_LIFECYCLE_REVIEW_SYSTEM_REPORT.md"
        report.write_text("# P31 Report\n\nMarker: P31_PHASE_LIFECYCLE_REVIEW_SYSTEM_COMPLETE\n", encoding="utf-8")
        (root / "README.md").write_text("# AgentOffice\n\nphase lifecycle review system\n", encoding="utf-8")
        git(root, "add", "README.md", report.name)
        git(root, "commit", "-m", "review")
        head = git(root, "rev-parse", "HEAD")
        return baseline, head, report

    def _bundle_args(self, baseline: str, head: str, report: Path, out: Path, prompt: Path, *extra: str) -> list[str]:
        return [
            "review",
            "bundle",
            "--baseline",
            baseline,
            "--head",
            head,
            "--branch",
            "phase31/phase-lifecycle-review-system",
            "--report",
            str(report),
            "--out",
            str(out),
            "--prompt-out",
            str(prompt),
            "--title",
            "P31 Phase Lifecycle Review System",
            "--bundle-marker",
            "P31_REVIEW_ARTIFACT_BUNDLE_COMPLETE",
            "--review-marker",
            "P31_ARTIFACT_REVIEW_COMPLETE",
            "--focus",
            "review contract, JSON/text stability, validation evidence, safety",
            *extra,
        ]

    def test_bundle_positive_creates_review_bundle_and_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as export_dir:
            root = Path(tmpdir)
            baseline, head, report = self._repo(root)
            out = Path(export_dir) / "bundle.md"
            prompt = Path(export_dir) / "prompt.md"
            with patch.object(cli, "PROJECT_ROOT", root), patch.object(review_lifecycle, "DEFAULT_VALIDATION_COMMANDS", self.validation_commands):
                code, stdout, stderr = run_cli(self._bundle_args(baseline, head, report, out, prompt, "--run-validation", "--json"))
            bundle = out.read_text(encoding="utf-8")
            prompt_text = prompt.read_text(encoding="utf-8")

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["command"], "review bundle")
        self.assertEqual(payload["outputs"]["bundle"], str(out))
        self.assertIn("P31_REVIEW_ARTIFACT_BUNDLE_COMPLETE", bundle)
        self.assertIn("bundle_schema_version", bundle)
        self.assertIn("Marker: P31_PHASE_LIFECYCLE_REVIEW_SYSTEM_COMPLETE", bundle)
        self.assertIn("## Diff Stat", bundle)
        self.assertIn("## Name Status", bundle)
        self.assertIn("## Full Diff", bundle)
        self.assertIn("diff --git", bundle)
        self.assertIn("## Validation Captured Output Sections", bundle)
        self.assertIn("validation ok", bundle)
        self.assertIn("artifact-based review", bundle)
        self.assertIn("review contract, JSON/text stability", bundle)
        self.assertIn("P31_ARTIFACT_REVIEW_COMPLETE", prompt_text)
        self.assertNotIn("Traceback", stdout + stderr + bundle + prompt_text)

    def test_prompt_positive_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as export_dir:
            root = Path(tmpdir)
            baseline, head, report = self._repo(root)
            bundle = Path(export_dir) / "bundle.md"
            bundle.write_text("artifact bundle", encoding="utf-8")
            prompt = Path(export_dir) / "prompt.md"
            with patch.object(cli, "PROJECT_ROOT", root):
                code, stdout, stderr = run_cli([
                    "review", "prompt", "--baseline", baseline, "--head", head, "--branch", "phase31/phase-lifecycle-review-system",
                    "--report", str(report), "--bundle", str(bundle), "--out", str(prompt), "--review-marker", "P31_ARTIFACT_REVIEW_COMPLETE", "--json",
                ])
            text = prompt.read_text(encoding="utf-8")

        self.assertEqual(code, 0, stderr)
        self.assertTrue(json.loads(stdout)["ok"])
        self.assertIn("artifact-based review", text)
        self.assertIn("P31_ARTIFACT_REVIEW_COMPLETE", text)
        for phrase in ("verdict", "artifact-based caveat", "files reviewed", "validation artifacts reviewed", "blocker findings", "contract risks", "safety risks", "regression risks", "final confidence"):
            self.assertIn(phrase, text)
        self.assertIn("Do not claim you ran tests", text)
        self.assertNotIn("I ran", text)

    def test_attestation_positive_and_negative_verdicts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            cases = {
                "pass": ("verdict: pass\nblocker findings: none\nP31_ARTIFACT_REVIEW_COMPLETE\n", 0, None),
                "missing_marker": ("verdict: pass\n", 2, "review_attest_marker_missing"),
                "fail": ("verdict: fail\nP31_ARTIFACT_REVIEW_COMPLETE\n", 2, "review_attest_verdict_mismatch"),
                "conditional": ("verdict: conditional pass\nP31_ARTIFACT_REVIEW_COMPLETE\n", 2, "review_attest_verdict_mismatch"),
                "ambiguous": ("verdict: pass\nverdict: fail\nP31_ARTIFACT_REVIEW_COMPLETE\n", 2, "review_attest_ambiguous_verdict"),
            }
            for name, (text, expected_code, error_code) in cases.items():
                with self.subTest(name=name):
                    review = root / f"{name}.md"
                    out = root / f"{name}-attestation.md"
                    review.write_text(text, encoding="utf-8")
                    code, stdout, stderr = run_cli(["review", "attest", "--review-report", str(review), "--expected-marker", "P31_ARTIFACT_REVIEW_COMPLETE", "--expected-verdict", "pass", "--out", str(out), "--json"])
                    self.assertEqual(code, expected_code, stderr)
                    payload = json.loads(stdout)
                    self.assertNotIn("Traceback", stdout + stderr)
                    if expected_code == 0:
                        self.assertTrue(payload["ok"])
                        self.assertEqual(payload["detected_verdict"], "pass")
                        self.assertIn("status: pass", out.read_text(encoding="utf-8"))
                    else:
                        self.assertFalse(payload["ok"])
                        self.assertEqual(payload["error_code"], error_code)

    def test_attestation_missing_review_report_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            missing = Path(tmpdir) / "missing.md"
            out = Path(tmpdir) / "attestation.md"
            code, stdout, stderr = run_cli(["review", "attest", "--review-report", str(missing), "--expected-marker", "P31_ARTIFACT_REVIEW_COMPLETE", "--out", str(out), "--json"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(stdout)["error_code"], "review_attest_missing_report")
        self.assertNotIn("Traceback", stdout + stderr)

    def test_attestation_non_utf8_review_report_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            review = root / "review.md"
            review.write_bytes(b"\xff\xfe")
            out = root / "attestation.md"
            code, stdout, stderr = run_cli(["review", "attest", "--review-report", str(review), "--expected-marker", "P31_ARTIFACT_REVIEW_COMPLETE", "--out", str(out), "--json"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(stdout)["error_code"], "review_attest_unreadable_report")
        self.assertNotIn("Traceback", stdout + stderr)

    def test_merge_packet_positive(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as export_dir:
            root = Path(tmpdir)
            baseline, head, report = self._repo(root)
            bundle = Path(export_dir) / "bundle.md"
            bundle.write_text("review bundle", encoding="utf-8")
            review = Path(export_dir) / "claude.md"
            review.write_text("verdict: pass\nblocker findings: none\nP31_ARTIFACT_REVIEW_COMPLETE\n", encoding="utf-8")
            attestation = Path(export_dir) / "attestation.md"
            packet = Path(export_dir) / "packet.md"
            with patch.object(cli, "PROJECT_ROOT", root):
                attest_code, _stdout, attest_stderr = run_cli(["review", "attest", "--review-report", str(review), "--expected-marker", "P31_ARTIFACT_REVIEW_COMPLETE", "--out", str(attestation), "--json"])
                self.assertEqual(attest_code, 0, attest_stderr)
                code, stdout, stderr = run_cli([
                    "review", "merge-packet", "--baseline", baseline, "--source-branch", "phase31/phase-lifecycle-review-system", "--source-commit", head,
                    "--implementation-report", str(report), "--review-bundle", str(bundle), "--review-attestation", str(attestation), "--out", str(packet),
                    "--merge-marker", "P31_MERGE_GATE_PASS_MAINLINE_SYNCED", "--json",
                ])
            text = packet.read_text(encoding="utf-8")

        self.assertEqual(code, 0, stderr)
        self.assertTrue(json.loads(stdout)["ok"])
        self.assertIn(baseline, text)
        self.assertIn(head, text)
        self.assertIn("review attestation status: pass", text)
        self.assertIn("Expected Pre-Merge Validation List", text)
        self.assertIn("Expected Post-Merge Validation List", text)
        self.assertIn("do not read .env", text)
        self.assertIn("git merge --no-ff", text)
        self.assertIn("git push origin phase6/mainline", text)
        self.assertIn("did not execute merge", text)

    def test_output_symlink_refusals_are_stable_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as export_dir:
            root = Path(tmpdir)
            baseline, head, report = self._repo(root)
            target = Path(export_dir) / "target.md"
            target.write_text("keep", encoding="utf-8")
            link = Path(export_dir) / "link.md"
            try:
                link.symlink_to(target)
            except (NotImplementedError, OSError) as exc:
                self.skipTest(f"symlink unsupported: {exc}")
            prompt_target = Path(export_dir) / "prompt-target.md"
            prompt_target.write_text("keep", encoding="utf-8")
            prompt_link = Path(export_dir) / "prompt-link.md"
            prompt_link.symlink_to(prompt_target)
            bundle = Path(export_dir) / "bundle.md"
            bundle.write_text("bundle", encoding="utf-8")
            with patch.object(cli, "PROJECT_ROOT", root):
                bundle_code, bundle_stdout, bundle_stderr = run_cli(self._bundle_args(baseline, head, report, link, Path(export_dir) / "prompt.md", "--json"))
                prompt_code, prompt_stdout, prompt_stderr = run_cli(["review", "prompt", "--baseline", baseline, "--head", head, "--branch", "phase31/phase-lifecycle-review-system", "--report", str(report), "--bundle", str(bundle), "--out", str(prompt_link), "--review-marker", "P31_ARTIFACT_REVIEW_COMPLETE", "--json"])

        self.assertEqual(bundle_code, 2)
        self.assertEqual(json.loads(bundle_stdout)["error_code"], "review_bundle_output_symlink")
        self.assertEqual(prompt_code, 2)
        self.assertEqual(json.loads(prompt_stdout)["error_code"], "review_prompt_output_symlink")
        self.assertNotIn("Traceback", bundle_stdout + bundle_stderr + prompt_stdout + prompt_stderr)

    def test_missing_report_bad_refs_dirty_tree_and_dotenv_refusal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as export_dir:
            root = Path(tmpdir)
            baseline, head, report = self._repo(root)
            missing = root / "missing.md"
            dotenv = root / ".env"
            dotenv.write_text("SECRET=do-not-read\n", encoding="utf-8")
            with patch.object(cli, "PROJECT_ROOT", root):
                missing_result = run_cli(self._bundle_args(baseline, head, missing, Path(export_dir) / "m.md", Path(export_dir) / "m-prompt.md", "--json"))
                bad_base = run_cli(self._bundle_args("missing", head, report, Path(export_dir) / "b.md", Path(export_dir) / "b-prompt.md", "--json"))
                bad_head = run_cli(self._bundle_args(baseline, "missing", report, Path(export_dir) / "h.md", Path(export_dir) / "h-prompt.md", "--json"))
                dotenv_result = run_cli(self._bundle_args(baseline, head, dotenv, Path(export_dir) / "e.md", Path(export_dir) / "e-prompt.md", "--json"))
                (root / "README.md").write_text("dirty\n", encoding="utf-8")
                dirty = run_cli(self._bundle_args(baseline, head, report, Path(export_dir) / "d.md", Path(export_dir) / "d-prompt.md", "--json"))

        expectations = [
            (missing_result, "review_bundle_missing_report"),
            (bad_base, "review_invalid_baseline_commit"),
            (bad_head, "review_invalid_head_commit"),
            (dotenv_result, "review_bundle_dotenv_report"),
            (dirty, "review_bundle_dirty_tree"),
        ]
        for result, error_code in expectations:
            with self.subTest(error_code=error_code):
                code, stdout, stderr = result
                self.assertEqual(code, 2)
                self.assertEqual(json.loads(stdout)["error_code"], error_code)
                self.assertNotIn("Traceback", stdout + stderr)

    def test_validation_failure_writes_partial_and_returns_stable_json(self) -> None:
        failing = (CaptureCommand("validation fails", ("python3", "-c", "import sys; print('bad'); sys.exit(7)")),)
        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as export_dir:
            root = Path(tmpdir)
            baseline, head, report = self._repo(root)
            out = Path(export_dir) / "bundle.md"
            prompt = Path(export_dir) / "prompt.md"
            with patch.object(cli, "PROJECT_ROOT", root), patch.object(review_lifecycle, "DEFAULT_VALIDATION_COMMANDS", failing):
                code, stdout, stderr = run_cli(self._bundle_args(baseline, head, report, out, prompt, "--run-validation", "--json"))
            payload = json.loads(stdout)
            partial = Path(payload["details"]["partial_bundle"])
            partial_text = partial.read_text(encoding="utf-8")

        self.assertEqual(code, 1)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error_code"], "review_bundle_validation_failed")
        self.assertFalse(out.exists())
        self.assertFalse(prompt.exists())
        self.assertIn("status: incomplete_failed_validation", partial_text)
        self.assertIn("exit_code: 7", partial_text)
        self.assertIn("bad", partial_text)
        self.assertNotIn("Traceback", stdout + stderr + partial_text)

    def test_bundle_is_deterministic_for_fixed_inputs_and_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as export_dir:
            root = Path(tmpdir)
            baseline, head, report = self._repo(root)
            first_dir = Path(export_dir) / "first"
            second_dir = Path(export_dir) / "second"
            first_dir.mkdir()
            second_dir.mkdir()
            first = first_dir / "bundle.md"
            second = second_dir / "bundle.md"
            first_prompt = first_dir / "prompt.md"
            second_prompt = second_dir / "prompt.md"
            with patch.object(cli, "PROJECT_ROOT", root), patch.object(review_lifecycle, "DEFAULT_VALIDATION_COMMANDS", self.validation_commands):
                first_result = run_cli(self._bundle_args(baseline, head, report, first, first_prompt, "--run-validation", "--json"))
                second_result = run_cli(self._bundle_args(baseline, head, report, second, second_prompt, "--run-validation", "--json"))
            first_text = first.read_text(encoding="utf-8")
            second_text = second.read_text(encoding="utf-8")

        self.assertEqual(first_result[0], 0, first_result[2])
        self.assertEqual(second_result[0], 0, second_result[2])
        self.assertEqual(first_text, second_text)

    def test_review_help_is_available(self) -> None:
        for argv in (["review", "--help"], ["review", "bundle", "--help"], ["review", "prompt", "--help"], ["review", "attest", "--help"], ["review", "merge-packet", "--help"]):
            with self.subTest(argv=argv):
                stdout = io.StringIO()
                stderr = io.StringIO()
                with self.assertRaises(SystemExit) as raised, redirect_stdout(stdout), redirect_stderr(stderr):
                    cli.main(argv)
                self.assertEqual(raised.exception.code, 0)
                self.assertIn("review", stdout.getvalue())
                self.assertEqual(stderr.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
