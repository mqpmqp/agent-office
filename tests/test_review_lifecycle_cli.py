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

    def test_default_validation_commands_include_review_lifecycle_suite(self) -> None:
        commands = [" ".join(command.argv) for command in review_lifecycle.DEFAULT_VALIDATION_COMMANDS]
        self.assertIn("python3 -m unittest tests.test_review_lifecycle_cli", commands)
        self.assertIn("python3 -m agent_office review codex-deliver --help", commands)
        self.assertIn("python3 -m agent_office review reviewed-delivery --help", commands)

    def test_validation_fixture_capture_records_review_lifecycle_command_and_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as export_dir, tempfile.TemporaryDirectory() as fixture_dir:
            root = Path(tmpdir)
            baseline, head, report = self._repo(root)
            out = Path(export_dir) / "bundle.md"
            prompt = Path(export_dir) / "prompt.md"
            fixture = Path(fixture_dir)
            for command in review_lifecycle.DEFAULT_VALIDATION_COMMANDS:
                stem = review_lifecycle._slug(command.name)
                (fixture / f"{stem}.exit").write_text("0\n", encoding="utf-8")
                (fixture / f"{stem}.stdout").write_text(f"captured {command.name}\n", encoding="utf-8")
            with patch.object(cli, "PROJECT_ROOT", root):
                code, stdout, stderr = run_cli(self._bundle_args(baseline, head, report, out, prompt, "--validation-fixture-dir", str(fixture), "--json"))
            bundle = out.read_text(encoding="utf-8")

        self.assertEqual(code, 0, stderr)
        self.assertTrue(json.loads(stdout)["ok"])
        self.assertIn("### tests.test_review_lifecycle_cli", bundle)
        self.assertIn("argv: python3 -m unittest tests.test_review_lifecycle_cli", bundle)
        self.assertIn("captured tests.test_review_lifecycle_cli", bundle)
        self.assertNotIn("Traceback", stdout + stderr + bundle)

    def test_default_validation_commands_do_not_reenter_review_bundle_validation(self) -> None:
        for command in review_lifecycle.DEFAULT_VALIDATION_COMMANDS:
            joined = " ".join(command.argv)
            with self.subTest(command=command.name):
                self.assertNotIn("review bundle --run-validation", joined)
                self.assertNotIn("--run-validation", joined)
                self.assertNotIn("--merge-authorized", joined)
                self.assertNotIn("--push-authorized", joined)

    def test_codex_deliver_safe_mode_creates_stable_report_without_merge_or_push(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as export_dir:
            root = Path(tmpdir)
            baseline, head, _report = self._repo(root)
            git(root, "branch", "phase6/mainline", baseline)
            out = Path(export_dir) / "codex-deliver.md"
            with patch.object(cli, "PROJECT_ROOT", root):
                code, stdout, stderr = run_cli([
                    "review", "codex-deliver", "--source", "phase31/phase-lifecycle-review-system", "--target", "phase6/mainline",
                    "--expected-source-head", head, "--expected-target-head", baseline, "--phase", "P34", "--run-id", "P34-TEST",
                    "--out", str(out), "--json",
                ])
            payload = json.loads(stdout)
            text = out.read_text(encoding="utf-8")
            target_after = git(root, "rev-parse", "phase6/mainline")

        self.assertEqual(code, 0, stderr)
        self.assertEqual(target_after, baseline)
        expected_keys = {
            "ok", "command", "phase", "run_id", "source_branch", "source_head", "expected_source_head", "target_branch",
            "target_expected_head", "origin_source_head", "origin_target_head", "tracked_tree_clean", "untracked_artifacts_allowed",
            "changed_files", "diff_stat", "diff_check_status", "validation_command_list", "pre_merge_validation_status",
            "post_merge_validation_status", "merge_authorization_status", "push_authorization_status", "merge_planned", "push_planned",
            "merge_executed", "push_executed", "execution_status", "execution_failed_step", "final_target_head",
            "final_origin_target_status", "safety_boundary_checklist", "readiness", "blocking_reasons", "outputs",
        }
        self.assertTrue(expected_keys.issubset(payload))
        self.assertEqual(payload["command"], "review codex-deliver")
        self.assertEqual(payload["readiness"], "ready")
        self.assertFalse(payload["merge_gate_ready"])
        self.assertIn("merge_authorization_missing", payload["blocking_reasons"])
        self.assertIn("push_authorization_missing", payload["blocking_reasons"])
        self.assertFalse(payload["merge_planned"])
        self.assertFalse(payload["push_planned"])
        self.assertFalse(payload["merge_executed"])
        self.assertFalse(payload["push_executed"])
        self.assertEqual(payload["execution_status"], "safe_mode")
        self.assertIn("P34_CODEX_DELIVERY_RUNNER_COMPLETE", text)
        self.assertIn("Safe mode generated this report only", text)
        self.assertIn("no Claude merge packet generated", text)
        self.assertNotIn("Traceback", stdout + stderr + text)

    def test_codex_deliver_authorized_mode_requires_both_authorizations(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as export_dir:
            root = Path(tmpdir)
            baseline, head, _report = self._repo(root)
            git(root, "branch", "phase6/mainline", baseline)
            out = Path(export_dir) / "codex-deliver.md"
            with patch.object(cli, "PROJECT_ROOT", root):
                code, stdout, stderr = run_cli([
                    "review", "codex-deliver", "--source", "phase31/phase-lifecycle-review-system", "--target", "phase6/mainline",
                    "--expected-source-head", head, "--expected-target-head", baseline, "--merge-authorized", "--out", str(out), "--json",
                ])
            payload = json.loads(stdout)
            target_after = git(root, "rev-parse", "phase6/mainline")

        self.assertEqual(code, 0, stderr)
        self.assertEqual(target_after, baseline)
        self.assertEqual(payload["merge_authorization_status"], "authorized")
        self.assertEqual(payload["push_authorization_status"], "not_authorized")
        self.assertTrue(payload["merge_planned"])
        self.assertFalse(payload["push_planned"])
        self.assertFalse(payload["merge_gate_ready"])
        self.assertFalse(payload["merge_executed"])
        self.assertFalse(payload["push_executed"])
        self.assertEqual(payload["execution_status"], "blocked")
        self.assertIn("push_authorization_missing", payload["blocking_reasons"])
        self.assertNotIn("merge_authorization_missing", payload["blocking_reasons"])

    def test_codex_deliver_authorized_mode_executes_merge_and_push(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as remote_dir, tempfile.TemporaryDirectory() as export_dir:
            root = Path(tmpdir)
            baseline, head, _report = self._repo(root)
            git(root, "branch", "phase6/mainline", baseline)
            remote = Path(remote_dir) / "origin.git"
            subprocess.run(["git", "init", "--bare", str(remote)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            git(root, "remote", "add", "origin", str(remote))
            git(root, "push", "origin", "phase31/phase-lifecycle-review-system", "phase6/mainline")
            git(root, "fetch", "origin")
            out = Path(export_dir) / "codex-deliver-authorized.md"
            with patch.object(cli, "PROJECT_ROOT", root):
                code, stdout, stderr = run_cli([
                    "review", "codex-deliver", "--source", "phase31/phase-lifecycle-review-system", "--target", "phase6/mainline",
                    "--expected-source-head", head, "--expected-target-head", baseline, "--merge-authorized", "--push-authorized",
                    "--out", str(out), "--json",
                ])
            payload = json.loads(stdout)
            text = out.read_text(encoding="utf-8")
            target_after = git(root, "rev-parse", "phase6/mainline")
            origin_after = git(root, "rev-parse", "origin/phase6/mainline")
            parents = git(root, "rev-list", "--parents", "-n", "1", "phase6/mainline").split()[1:]

        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload["merge_authorization_status"], "authorized")
        self.assertEqual(payload["push_authorization_status"], "authorized")
        self.assertTrue(payload["merge_gate_ready"])
        self.assertTrue(payload["merge_planned"])
        self.assertTrue(payload["push_planned"])
        self.assertTrue(payload["merge_executed"])
        self.assertTrue(payload["push_executed"])
        self.assertEqual(payload["execution_status"], "executed")
        self.assertNotEqual(target_after, baseline)
        self.assertEqual(payload["final_target_head"], target_after)
        self.assertEqual(payload["final_origin_target_status"], origin_after)
        self.assertEqual(origin_after, target_after)
        self.assertEqual(set(parents), {baseline, head})
        self.assertIn("Authorized mode executed merge and push", text)
        self.assertNotIn("Traceback", stdout + stderr + text)

    def test_codex_deliver_head_mismatch_blocks_readiness_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as export_dir:
            root = Path(tmpdir)
            baseline, _head, _report = self._repo(root)
            git(root, "branch", "phase6/mainline", baseline)
            out = Path(export_dir) / "codex-deliver.md"
            with patch.object(cli, "PROJECT_ROOT", root):
                code, stdout, stderr = run_cli([
                    "review", "codex-deliver", "--source", "phase31/phase-lifecycle-review-system", "--target", "phase6/mainline",
                    "--expected-source-head", baseline, "--expected-target-head", baseline, "--out", str(out), "--json",
                ])
            payload = json.loads(stdout)

        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload["readiness"], "blocked")
        self.assertIn("source_head_mismatch", payload["readiness_blocking_reasons"])
        self.assertNotIn("Traceback", stdout + stderr)

    def test_reviewed_delivery_e2e_contract_from_review_output_to_codex_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as remote_dir, tempfile.TemporaryDirectory() as export_dir:
            root = Path(tmpdir)
            baseline, head, report = self._repo(root)
            git(root, "branch", "phase6/mainline", baseline)
            remote = Path(remote_dir) / "origin.git"
            subprocess.run(["git", "init", "--bare", str(remote)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            git(root, "remote", "add", "origin", str(remote))
            git(root, "push", "origin", "phase31/phase-lifecycle-review-system", "phase6/mainline")
            git(root, "fetch", "origin")

            export_root = Path(export_dir)
            bundle = export_root / "bundle.md"
            prompt = export_root / "prompt.md"
            impl_report = export_root / "implementation-report.md"
            impl_report.write_text(report.read_text(encoding="utf-8"), encoding="utf-8")
            review = export_root / "claude-review.md"
            attestation = export_root / "attestation.md"
            packet = export_root / "merge-packet.md"
            safe_report = export_root / "codex-deliver-safe.md"
            missing_auth_report = export_root / "codex-deliver-missing-auth.md"
            readiness_fail_report = export_root / "codex-deliver-readiness-fail.md"
            stale_target_report = export_root / "codex-deliver-stale-target.md"
            authorized_report = export_root / "codex-deliver-authorized.md"

            with patch.object(cli, "PROJECT_ROOT", root), patch.object(review_lifecycle, "DEFAULT_VALIDATION_COMMANDS", self.validation_commands):
                bundle_code, bundle_stdout, bundle_stderr = run_cli(self._bundle_args(
                    baseline, head, report, bundle, prompt, "--run-validation", "--json"
                ))
            self.assertEqual(bundle_code, 0, bundle_stderr)
            bundle_payload = json.loads(bundle_stdout)
            self.assertTrue(bundle_payload["ok"])
            self.assertEqual(bundle_payload["validation_success"], True)

            review.write_text(
                """verdict: pass
artifact-based caveat: reviewed static artifact evidence only
files reviewed: README.md, P31_PHASE_LIFECYCLE_REVIEW_SYSTEM_REPORT.md
validation artifacts reviewed: bundle validation fixture
blocker findings: none
major findings: none
P31_ARTIFACT_REVIEW_COMPLETE
""",
                encoding="utf-8",
            )
            with patch.object(cli, "PROJECT_ROOT", root):
                attest_code, attest_stdout, attest_stderr = run_cli([
                    "review", "attest", "--review-report", str(review), "--expected-marker", "P31_ARTIFACT_REVIEW_COMPLETE",
                    "--expected-verdict", "pass", "--out", str(attestation), "--json",
                ])
                packet_code, packet_stdout, packet_stderr = run_cli([
                    "review", "merge-packet", "--baseline", baseline, "--source-branch", "phase31/phase-lifecycle-review-system",
                    "--source-commit", head, "--implementation-report", str(report), "--review-bundle", str(bundle),
                    "--review-attestation", str(attestation), "--out", str(packet), "--merge-marker", "P36_E2E_MERGE_READY", "--json",
                ])
                safe_code, safe_stdout, safe_stderr = run_cli([
                    "review", "codex-deliver", "--source", "phase31/phase-lifecycle-review-system", "--target", "phase6/mainline",
                    "--expected-source-head", head, "--expected-target-head", baseline, "--out", str(safe_report), "--json",
                ])
                missing_auth_code, missing_auth_stdout, missing_auth_stderr = run_cli([
                    "review", "codex-deliver", "--source", "phase31/phase-lifecycle-review-system", "--target", "phase6/mainline",
                    "--expected-source-head", head, "--expected-target-head", baseline, "--merge-authorized",
                    "--out", str(missing_auth_report), "--json",
                ])
                readiness_fail_code, readiness_fail_stdout, readiness_fail_stderr = run_cli([
                    "review", "codex-deliver", "--source", "phase31/phase-lifecycle-review-system", "--target", "phase6/mainline",
                    "--expected-source-head", baseline, "--expected-target-head", baseline, "--merge-authorized", "--push-authorized",
                    "--out", str(readiness_fail_report), "--json",
                ])
            self.assertEqual(attest_code, 0, attest_stderr)
            attest_payload = json.loads(attest_stdout)
            self.assertEqual(attest_payload["status"], "pass")
            self.assertIn("status: pass", attestation.read_text(encoding="utf-8"))
            self.assertEqual(packet_code, 0, packet_stderr)
            packet_payload = json.loads(packet_stdout)
            packet_text = packet.read_text(encoding="utf-8")
            self.assertEqual(packet_payload["attestation_status"], "pass")
            self.assertIn("review attestation status: pass", packet_text)
            self.assertIn("did not execute merge", packet_text)

            safe_payload = json.loads(safe_stdout)
            missing_auth_payload = json.loads(missing_auth_stdout)
            readiness_fail_payload = json.loads(readiness_fail_stdout)
            self.assertEqual(safe_code, 0, safe_stderr)
            self.assertEqual(missing_auth_code, 0, missing_auth_stderr)
            self.assertEqual(readiness_fail_code, 0, readiness_fail_stderr)
            self.assertEqual(git(root, "rev-parse", "phase6/mainline"), baseline)
            self.assertEqual(git(root, "rev-parse", "origin/phase6/mainline"), baseline)
            self.assertFalse(safe_payload["merge_executed"])
            self.assertFalse(safe_payload["push_executed"])
            self.assertEqual(safe_payload["execution_status"], "safe_mode")
            self.assertFalse(missing_auth_payload["merge_gate_ready"])
            self.assertFalse(missing_auth_payload["merge_executed"])
            self.assertFalse(missing_auth_payload["push_executed"])
            self.assertIn("push_authorization_missing", missing_auth_payload["blocking_reasons"])
            self.assertEqual(readiness_fail_payload["readiness"], "blocked")
            self.assertFalse(readiness_fail_payload["merge_executed"])
            self.assertFalse(readiness_fail_payload["push_executed"])
            self.assertIn("source_head_mismatch", readiness_fail_payload["readiness_blocking_reasons"])

            git(root, "checkout", "phase6/mainline")
            (root / "STALE_TARGET.md").write_text("target moved\n", encoding="utf-8")
            git(root, "add", "STALE_TARGET.md")
            git(root, "commit", "-m", "move target")
            stale_head = git(root, "rev-parse", "phase6/mainline")
            git(root, "push", "origin", "phase6/mainline")
            with patch.object(cli, "PROJECT_ROOT", root):
                stale_code, stale_stdout, stale_stderr = run_cli([
                    "review", "codex-deliver", "--source", "phase31/phase-lifecycle-review-system", "--target", "phase6/mainline",
                    "--expected-source-head", head, "--expected-target-head", baseline, "--merge-authorized", "--push-authorized",
                    "--out", str(stale_target_report), "--json",
                ])
            stale_payload = json.loads(stale_stdout)
            self.assertEqual(stale_code, 0, stale_stderr)
            self.assertEqual(stale_payload["readiness"], "blocked")
            self.assertFalse(stale_payload["merge_executed"])
            self.assertFalse(stale_payload["push_executed"])
            self.assertIn("target_head_mismatch", stale_payload["readiness_blocking_reasons"])
            self.assertEqual(git(root, "rev-parse", "phase6/mainline"), stale_head)
            self.assertEqual(git(root, "rev-parse", "origin/phase6/mainline"), stale_head)

            with patch.object(cli, "PROJECT_ROOT", root):
                authorized_code, authorized_stdout, authorized_stderr = run_cli([
                    "review", "codex-deliver", "--source", "phase31/phase-lifecycle-review-system", "--target", "phase6/mainline",
                    "--expected-source-head", head, "--expected-target-head", stale_head, "--merge-authorized", "--push-authorized",
                    "--out", str(authorized_report), "--json",
                ])
            authorized_payload = json.loads(authorized_stdout)
            authorized_text = authorized_report.read_text(encoding="utf-8")
            final_target = git(root, "rev-parse", "phase6/mainline")
            final_origin = git(root, "rev-parse", "origin/phase6/mainline")
            parents = git(root, "rev-list", "--parents", "-n", "1", "phase6/mainline").split()[1:]

        self.assertEqual(authorized_code, 0, authorized_stderr)
        self.assertTrue(authorized_payload["merge_gate_ready"])
        self.assertTrue(authorized_payload["merge_executed"])
        self.assertTrue(authorized_payload["push_executed"])
        self.assertEqual(authorized_payload["execution_status"], "executed")
        self.assertEqual(authorized_payload["final_target_head"], final_target)
        self.assertEqual(authorized_payload["final_origin_target_status"], final_origin)
        self.assertEqual(final_target, final_origin)
        self.assertEqual(set(parents), {stale_head, head})
        self.assertIn("merge_executed: true", authorized_text)
        self.assertIn("push_executed: true", authorized_text)
        self.assertNotIn("Traceback", "".join([
            bundle_stdout, bundle_stderr, attest_stdout, attest_stderr, packet_stdout, packet_stderr,
            safe_stdout, safe_stderr, missing_auth_stdout, missing_auth_stderr, readiness_fail_stdout,
            readiness_fail_stderr, stale_stdout, stale_stderr, authorized_stdout, authorized_stderr,
        ]))

    def test_reviewed_delivery_orchestration_json_text_and_delivery_gates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as remote_dir, tempfile.TemporaryDirectory() as export_dir:
            root = Path(tmpdir)
            baseline, head, report = self._repo(root)
            git(root, "branch", "phase6/mainline", baseline)
            remote = Path(remote_dir) / "origin.git"
            subprocess.run(["git", "init", "--bare", str(remote)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            git(root, "remote", "add", "origin", str(remote))
            git(root, "push", "origin", "phase31/phase-lifecycle-review-system", "phase6/mainline")
            git(root, "fetch", "origin")

            export_root = Path(export_dir)
            bundle = export_root / "bundle.md"
            prompt = export_root / "prompt.md"
            impl_report = export_root / "implementation-report.md"
            impl_report.write_text(report.read_text(encoding="utf-8"), encoding="utf-8")
            review = export_root / "claude-review.md"
            review.write_text(
                """verdict: pass
artifact-based caveat: reviewed static artifact evidence only
files reviewed: README.md, P31_PHASE_LIFECYCLE_REVIEW_SYSTEM_REPORT.md
validation artifacts reviewed: bundle validation fixture
blocker findings: none
major findings: none
P31_ARTIFACT_REVIEW_COMPLETE
""",
                encoding="utf-8",
            )
            with patch.object(cli, "PROJECT_ROOT", root), patch.object(review_lifecycle, "DEFAULT_VALIDATION_COMMANDS", self.validation_commands):
                bundle_code, _bundle_stdout, bundle_stderr = run_cli(self._bundle_args(
                    baseline, head, report, bundle, prompt, "--run-validation", "--json"
                ))
            self.assertEqual(bundle_code, 0, bundle_stderr)

            def reviewed_delivery_args(out_dir: Path, *extra: str, expected_source: str = head, expected_target: str = baseline, review_path: Path = review) -> list[str]:
                return [
                    "review", "reviewed-delivery", "--source", "phase31/phase-lifecycle-review-system", "--target", "phase6/mainline",
                    "--expected-source-head", expected_source, "--expected-target-head", expected_target,
                    "--implementation-report", str(impl_report), "--review-bundle", str(bundle), "--review-report", str(review_path),
                    "--expected-marker", "P31_ARTIFACT_REVIEW_COMPLETE", "--out-dir", str(out_dir), "--run-id", out_dir.name,
                    "--mkdirs", *extra,
                ]

            with patch.object(cli, "PROJECT_ROOT", root):
                safe_code, safe_stdout, safe_stderr = run_cli(reviewed_delivery_args(export_root / "safe", "--json"))
                text_code, text_stdout, text_stderr = run_cli(reviewed_delivery_args(export_root / "text"))
                missing_auth_code, missing_auth_stdout, missing_auth_stderr = run_cli(reviewed_delivery_args(export_root / "missing-auth", "--merge-authorized", "--json"))
                readiness_fail_code, readiness_fail_stdout, readiness_fail_stderr = run_cli(reviewed_delivery_args(
                    export_root / "readiness-fail", "--merge-authorized", "--push-authorized", "--json", expected_source=baseline
                ))
            safe_payload = json.loads(safe_stdout)
            text_report = text_stdout
            missing_auth_payload = json.loads(missing_auth_stdout)
            readiness_fail_payload = json.loads(readiness_fail_stdout)

            self.assertEqual(safe_code, 0, safe_stderr)
            self.assertEqual(safe_payload["status"], "preview")
            self.assertEqual(safe_payload["attestation_status"], "pass")
            self.assertEqual(safe_payload["merge_packet_status"], "pass")
            self.assertEqual(safe_payload["delivery_execution_status"], "safe_mode")
            self.assertFalse(safe_payload["merge_executed"])
            self.assertFalse(safe_payload["push_executed"])
            self.assertTrue(Path(safe_payload["outputs"]["attestation"]).is_file())
            self.assertTrue(Path(safe_payload["outputs"]["merge_packet"]).is_file())
            self.assertTrue(Path(safe_payload["outputs"]["codex_delivery_report"]).is_file())
            self.assertEqual(text_code, 0, text_stderr)
            self.assertIn("AgentOffice reviewed delivery workflow complete", text_report)
            self.assertIn("status: preview", text_report)
            self.assertEqual(missing_auth_code, 0, missing_auth_stderr)
            self.assertEqual(missing_auth_payload["status"], "blocked")
            self.assertFalse(missing_auth_payload["merge_executed"])
            self.assertFalse(missing_auth_payload["push_executed"])
            self.assertIn("push_authorization_missing", missing_auth_payload["blocking_reasons"])
            self.assertEqual(readiness_fail_code, 0, readiness_fail_stderr)
            self.assertEqual(readiness_fail_payload["status"], "blocked")
            self.assertFalse(readiness_fail_payload["merge_executed"])
            self.assertFalse(readiness_fail_payload["push_executed"])
            self.assertIn("source_head_mismatch", readiness_fail_payload["readiness_blocking_reasons"])
            self.assertEqual(git(root, "rev-parse", "phase6/mainline"), baseline)
            self.assertEqual(git(root, "rev-parse", "origin/phase6/mainline"), baseline)

            git(root, "checkout", "phase6/mainline")
            (root / "STALE_TARGET.md").write_text("target moved\n", encoding="utf-8")
            git(root, "add", "STALE_TARGET.md")
            git(root, "commit", "-m", "move target")
            stale_head = git(root, "rev-parse", "phase6/mainline")
            git(root, "push", "origin", "phase6/mainline")
            with patch.object(cli, "PROJECT_ROOT", root):
                stale_code, stale_stdout, stale_stderr = run_cli(reviewed_delivery_args(
                    export_root / "stale", "--merge-authorized", "--push-authorized", "--json", expected_target=baseline
                ))
            stale_payload = json.loads(stale_stdout)
            self.assertEqual(stale_code, 0, stale_stderr)
            self.assertEqual(stale_payload["status"], "blocked")
            self.assertFalse(stale_payload["merge_executed"])
            self.assertFalse(stale_payload["push_executed"])
            self.assertIn("target_head_mismatch", stale_payload["readiness_blocking_reasons"])
            self.assertEqual(git(root, "rev-parse", "phase6/mainline"), stale_head)
            self.assertEqual(git(root, "rev-parse", "origin/phase6/mainline"), stale_head)

            with patch.object(cli, "PROJECT_ROOT", root):
                authorized_code, authorized_stdout, authorized_stderr = run_cli(reviewed_delivery_args(
                    export_root / "authorized", "--merge-authorized", "--push-authorized", "--json", expected_target=stale_head
                ))
            authorized_payload = json.loads(authorized_stdout)
            final_target = git(root, "rev-parse", "phase6/mainline")
            final_origin = git(root, "rev-parse", "origin/phase6/mainline")
            authorized_report = Path(authorized_payload["outputs"]["codex_delivery_report"]).read_text(encoding="utf-8")

        self.assertEqual(authorized_code, 0, authorized_stderr)
        self.assertEqual(authorized_payload["status"], "delivered")
        self.assertTrue(authorized_payload["merge_gate_ready"])
        self.assertTrue(authorized_payload["merge_executed"])
        self.assertTrue(authorized_payload["push_executed"])
        self.assertEqual(authorized_payload["delivery_execution_status"], "executed")
        self.assertEqual(final_target, final_origin)
        self.assertEqual(authorized_payload["final_target_head"], final_target)
        self.assertEqual(authorized_payload["final_origin_target_status"], final_origin)
        self.assertIn("merge_executed: true", authorized_report)
        self.assertIn("push_executed: true", authorized_report)
        self.assertNotIn("Traceback", "".join([
            safe_stdout, safe_stderr, text_stdout, text_stderr, missing_auth_stdout, missing_auth_stderr,
            readiness_fail_stdout, readiness_fail_stderr, stale_stdout, stale_stderr, authorized_stdout, authorized_stderr,
        ]))

    def test_reviewed_delivery_evidence_bundle_json_and_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as remote_dir, tempfile.TemporaryDirectory() as export_dir:
            root = Path(tmpdir)
            baseline, head, report = self._repo(root)
            git(root, "branch", "phase6/mainline", baseline)
            remote = Path(remote_dir) / "origin.git"
            subprocess.run(["git", "init", "--bare", str(remote)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            git(root, "remote", "add", "origin", str(remote))
            git(root, "push", "origin", "phase31/phase-lifecycle-review-system", "phase6/mainline")
            git(root, "fetch", "origin")
            export_root = Path(export_dir)
            bundle = export_root / "bundle.md"
            prompt = export_root / "prompt.md"
            review = export_root / "claude-review.md"
            review.write_text(
                """verdict: pass
artifact-based caveat: reviewed static artifact evidence only
files reviewed: README.md, P31_PHASE_LIFECYCLE_REVIEW_SYSTEM_REPORT.md
validation artifacts reviewed: bundle validation fixture
blocker findings: none
major findings: none
P31_ARTIFACT_REVIEW_COMPLETE
""",
                encoding="utf-8",
            )
            with patch.object(cli, "PROJECT_ROOT", root), patch.object(review_lifecycle, "DEFAULT_VALIDATION_COMMANDS", self.validation_commands):
                bundle_code, _bundle_stdout, bundle_stderr = run_cli(self._bundle_args(baseline, head, report, bundle, prompt, "--run-validation", "--json"))
            self.assertEqual(bundle_code, 0, bundle_stderr)

            def args(out_dir: Path, evidence: Path, fmt: str, *extra: str) -> list[str]:
                return [
                    "review", "reviewed-delivery", "--source", "phase31/phase-lifecycle-review-system", "--target", "phase6/mainline",
                    "--expected-source-head", head, "--expected-target-head", baseline,
                    "--implementation-report", str(report), "--review-bundle", str(bundle), "--review-report", str(review),
                    "--expected-marker", "P31_ARTIFACT_REVIEW_COMPLETE", "--out-dir", str(out_dir), "--run-id", out_dir.name,
                    "--mkdirs", "--evidence-bundle-out", str(evidence), "--evidence-bundle-format", fmt, *extra,
                ]

            json_dir = export_root / "json"
            text_dir = export_root / "text"
            json_evidence = json_dir / "evidence.json"
            text_evidence = text_dir / "evidence.md"
            with patch.object(cli, "PROJECT_ROOT", root):
                json_code, json_stdout, json_stderr = run_cli(args(json_dir, json_evidence, "json", "--json"))
                text_code, text_stdout, text_stderr = run_cli(args(text_dir, text_evidence, "text"))
            json_payload = json.loads(json_stdout)
            evidence_payload = json.loads(json_evidence.read_text(encoding="utf-8"))
            text_bundle = text_evidence.read_text(encoding="utf-8")

        self.assertEqual(json_code, 0, json_stderr)
        self.assertEqual(text_code, 0, text_stderr)
        self.assertEqual(json_payload["outputs"]["evidence_bundle"], str(json_evidence))
        self.assertEqual(json_payload["evidence_bundle_readiness"], "ready")
        self.assertEqual(evidence_payload["readiness"]["verdict"], "ready")
        self.assertFalse(evidence_payload["execution"]["merge_executed"])
        self.assertFalse(evidence_payload["execution"]["push_executed"])
        self.assertEqual(evidence_payload["source"]["branch"], "phase31/phase-lifecycle-review-system")
        self.assertEqual(evidence_payload["source"]["head"], head)
        self.assertEqual(evidence_payload["target"]["before"], baseline)
        self.assertEqual(evidence_payload["target"]["final_target"], baseline)
        self.assertEqual(evidence_payload["target"]["final_origin"], baseline)
        self.assertIn("REVIEWED_DELIVERY_EVIDENCE_BUNDLE_COMPLETE", text_bundle)
        self.assertIn("readiness_verdict: ready", text_bundle)
        self.assertIn("Safety Boundary Summary", text_bundle)
        self.assertIn("do not read .env", text_bundle)
        self.assertIn("merge_executed: false", text_bundle)
        self.assertIn("push_executed: false", text_bundle)
        self.assertIn("evidence_bundle", text_stdout)
        self.assertNotIn("Traceback", json_stdout + json_stderr + text_stdout + text_stderr + text_bundle)

    def test_reviewed_delivery_evidence_bundle_clean_errors_and_default_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as remote_dir, tempfile.TemporaryDirectory() as export_dir:
            root = Path(tmpdir)
            baseline, head, report = self._repo(root)
            git(root, "branch", "phase6/mainline", baseline)
            remote = Path(remote_dir) / "origin.git"
            subprocess.run(["git", "init", "--bare", str(remote)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            git(root, "remote", "add", "origin", str(remote))
            git(root, "push", "origin", "phase31/phase-lifecycle-review-system", "phase6/mainline")
            git(root, "fetch", "origin")
            export_root = Path(export_dir)
            bundle = export_root / "bundle.md"
            bundle.write_text("review bundle\n", encoding="utf-8")
            review = export_root / "claude-review.md"
            review.write_text("verdict: pass\nblocker findings: none\nmajor findings: none\nP31_ARTIFACT_REVIEW_COMPLETE\n", encoding="utf-8")
            out_dir = export_root / "safe"
            out_dir.mkdir()
            base_args = [
                "review", "reviewed-delivery", "--source", "phase31/phase-lifecycle-review-system", "--target", "phase6/mainline",
                "--expected-source-head", head, "--expected-target-head", baseline,
                "--implementation-report", str(report), "--review-bundle", str(bundle), "--review-report", str(review),
                "--expected-marker", "P31_ARTIFACT_REVIEW_COMPLETE", "--out-dir", str(out_dir), "--run-id", "safe",
                "--json",
            ]
            with patch.object(cli, "PROJECT_ROOT", root):
                missing_parent = run_cli([*base_args, "--evidence-bundle-out", str(out_dir / "missing" / "evidence.json")])
                outside_root = run_cli([*base_args, "--evidence-bundle-out", str(export_root / "outside.json")])
                default_code, default_stdout, default_stderr = run_cli(base_args)

        self.assertEqual(missing_parent[0], 2)
        self.assertEqual(json.loads(missing_parent[1])["error_code"], "reviewed_delivery_evidence_parent_missing")
        self.assertEqual(outside_root[0], 2)
        self.assertEqual(json.loads(outside_root[1])["error_code"], "reviewed_delivery_evidence_output_outside_allowed_roots")
        self.assertEqual(default_code, 0, default_stderr)
        self.assertNotIn("evidence_bundle", json.loads(default_stdout)["outputs"])
        self.assertNotIn("Traceback", missing_parent[1] + missing_parent[2] + outside_root[1] + outside_root[2] + default_stdout + default_stderr)

    def test_reviewed_delivery_evidence_bundle_readiness_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as remote_dir, tempfile.TemporaryDirectory() as export_dir:
            root = Path(tmpdir)
            baseline, head, report = self._repo(root)
            git(root, "branch", "phase6/mainline", baseline)
            remote = Path(remote_dir) / "origin.git"
            subprocess.run(["git", "init", "--bare", str(remote)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            git(root, "remote", "add", "origin", str(remote))
            git(root, "push", "origin", "phase31/phase-lifecycle-review-system", "phase6/mainline")
            git(root, "fetch", "origin")
            export_root = Path(export_dir)
            bundle = export_root / "bundle.md"
            bundle.write_text("review bundle\n", encoding="utf-8")
            review = export_root / "claude-review.md"
            review.write_text("verdict: pass\nblocker findings: none\nmajor findings: none\nP31_ARTIFACT_REVIEW_COMPLETE\n", encoding="utf-8")

            def args(out_dir: Path, evidence: Path, *extra: str) -> list[str]:
                return [
                    "review", "reviewed-delivery", "--source", "phase31/phase-lifecycle-review-system", "--target", "phase6/mainline",
                    "--expected-source-head", head, "--expected-target-head", baseline,
                    "--implementation-report", str(report), "--review-bundle", str(bundle), "--review-report", str(review),
                    "--expected-marker", "P31_ARTIFACT_REVIEW_COMPLETE", "--out-dir", str(out_dir), "--run-id", out_dir.name,
                    "--mkdirs", "--evidence-bundle-out", str(evidence), "--json", *extra,
                ]

            partial_auth_dir = export_root / "partial-auth"
            origin_mismatch_dir = export_root / "origin-mismatch"
            with patch.object(cli, "PROJECT_ROOT", root):
                partial_auth = run_cli(args(partial_auth_dir, partial_auth_dir / "evidence.json", "--merge-authorized"))
            git(root, "push", "origin", f"{head}:phase6/mainline")
            with patch.object(cli, "PROJECT_ROOT", root):
                origin_mismatch = run_cli(args(origin_mismatch_dir, origin_mismatch_dir / "evidence.json"))

        partial_auth_payload = json.loads(partial_auth[1])
        origin_mismatch_payload = json.loads(origin_mismatch[1])
        self.assertEqual(partial_auth[0], 2)
        self.assertEqual(partial_auth_payload["error_code"], "reviewed_delivery_evidence_readiness_failed")
        self.assertIn("authorized_merge_not_executed", partial_auth_payload["details"]["blocking_reasons"])
        self.assertIn("authorized_push_not_executed", partial_auth_payload["details"]["blocking_reasons"])
        self.assertFalse((Path(export_dir) / "partial-auth" / "evidence.json").exists())
        self.assertEqual(origin_mismatch[0], 2)
        self.assertEqual(origin_mismatch_payload["error_code"], "reviewed_delivery_evidence_readiness_failed")
        self.assertIn("final_target_origin_mismatch", origin_mismatch_payload["details"]["blocking_reasons"])
        self.assertFalse((Path(export_dir) / "origin-mismatch" / "evidence.json").exists())
        self.assertNotIn("Traceback", partial_auth[1] + partial_auth[2] + origin_mismatch[1] + origin_mismatch[2])

    def test_reviewed_delivery_bad_or_missing_review_output_is_stable_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as export_dir:
            root = Path(tmpdir)
            baseline, head, report = self._repo(root)
            git(root, "branch", "phase6/mainline", baseline)
            bundle = Path(export_dir) / "bundle.md"
            bundle.write_text("review bundle\n", encoding="utf-8")
            impl_report = Path(export_dir) / "implementation-report.md"
            impl_report.write_text(report.read_text(encoding="utf-8"), encoding="utf-8")
            bad_review = Path(export_dir) / "bad-review.md"
            bad_review.write_text("verdict: pass\n", encoding="utf-8")
            missing_review = Path(export_dir) / "missing-review.md"

            def args(review_path: Path, out_name: str) -> list[str]:
                return [
                    "review", "reviewed-delivery", "--source", "phase31/phase-lifecycle-review-system", "--target", "phase6/mainline",
                    "--expected-source-head", head, "--expected-target-head", baseline,
                    "--implementation-report", str(impl_report), "--review-bundle", str(bundle), "--review-report", str(review_path),
                    "--expected-marker", "P31_ARTIFACT_REVIEW_COMPLETE", "--out-dir", str(Path(export_dir) / out_name),
                    "--mkdirs", "--json",
                ]

            with patch.object(cli, "PROJECT_ROOT", root):
                missing_code, missing_stdout, missing_stderr = run_cli(args(missing_review, "missing"))
                bad_code, bad_stdout, bad_stderr = run_cli(args(bad_review, "bad"))

        self.assertEqual(missing_code, 2)
        self.assertEqual(json.loads(missing_stdout)["error_code"], "review_attest_missing_report")
        self.assertEqual(bad_code, 2)
        self.assertEqual(json.loads(bad_stdout)["error_code"], "review_attest_marker_missing")
        self.assertNotIn("Traceback", missing_stdout + missing_stderr + bad_stdout + bad_stderr)

    def test_codex_gate_positive_creates_readiness_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as export_dir:
            root = Path(tmpdir)
            baseline, head, _report = self._repo(root)
            out = Path(export_dir) / "codex-gate.md"
            with patch.object(cli, "PROJECT_ROOT", root):
                code, stdout, stderr = run_cli([
                    "review", "codex-gate", "--baseline", baseline, "--head", head, "--branch", "phase31/phase-lifecycle-review-system",
                    "--out", str(out), "--json",
                ])
            payload = json.loads(stdout)
            text = out.read_text(encoding="utf-8")

        self.assertEqual(code, 0, stderr)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["command"], "review codex-gate")
        self.assertEqual(payload["outputs"]["codex_gate"], str(out))
        self.assertEqual(payload["claude_path"], "optional_legacy_lower_level")
        self.assertIn("Codex implementation", payload["workflow"])
        self.assertIn("CODEX_ONLY_DELIVERY_LANE_READY", text)
        self.assertIn("Codex-only is the default delivery lane", text)
        self.assertIn("optional/legacy/lower-level", text)
        self.assertIn("Required Validation Checklist", text)
        self.assertIn("did not execute merge", text)
        self.assertNotIn("Traceback", stdout + stderr + text)

    def test_codex_gate_dirty_tree_and_dotenv_output_refusal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            baseline, head, _report = self._repo(root)
            (root / "README.md").write_text("dirty\n", encoding="utf-8")
            with patch.object(cli, "PROJECT_ROOT", root):
                dirty = run_cli(["review", "codex-gate", "--baseline", baseline, "--head", head, "--branch", "phase31/phase-lifecycle-review-system", "--out", str(root / "gate.md"), "--json"])
                dotenv = run_cli(["review", "codex-gate", "--baseline", baseline, "--head", head, "--branch", "phase31/phase-lifecycle-review-system", "--out", str(root / ".env" / "gate.md"), "--allow-dirty", "--json"])

        self.assertEqual(dirty[0], 2)
        self.assertEqual(json.loads(dirty[1])["error_code"], "review_codex_gate_dirty_tree")
        self.assertEqual(dotenv[0], 2)
        self.assertEqual(json.loads(dotenv[1])["error_code"], "review_codex_gate_dotenv_refused")
        self.assertNotIn("Traceback", dirty[1] + dirty[2] + dotenv[1] + dotenv[2])

    def test_readme_documents_codex_only_default_and_legacy_claude_path(self) -> None:
        text = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
        self.assertIn("Codex implementation -> codex-deliver safe report -> full validation -> authorized merge gate -> push mainline", text)
        self.assertIn("review codex-deliver --help", text)
        self.assertIn("review codex-gate --help", text)
        self.assertIn("review reviewed-delivery --help", text)
        self.assertIn("optional/legacy/lower-level", text)
        self.assertIn("not the default mandatory path", text)
        self.assertIn("Codex-only does not mean skipping validation", text)
        self.assertIn("--merge-authorized", text)
        self.assertIn("--push-authorized", text)

    def test_review_help_is_available(self) -> None:
        for argv in (["review", "--help"], ["review", "bundle", "--help"], ["review", "prompt", "--help"], ["review", "attest", "--help"], ["review", "merge-packet", "--help"], ["review", "codex-gate", "--help"], ["review", "reviewed-delivery", "--help"], ["review", "codex-deliver", "--help"]):
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
