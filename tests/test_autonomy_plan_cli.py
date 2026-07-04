from __future__ import annotations

import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from agent_office import cli


def run_cli(argv: list[str], project_root: Path) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with patch.object(cli, "PROJECT_ROOT", project_root), redirect_stdout(stdout), redirect_stderr(stderr):
        code = cli.main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


def make_git_repo(root: Path) -> tuple[str, str]:
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=root, check=True, capture_output=True, text=True)
    (root / "sample.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "add", "sample.txt"], cwd=root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=root, check=True, capture_output=True, text=True)
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True).stdout.strip()
    (root / "sample.txt").write_text("one\ntwo\n", encoding="utf-8")
    (root / "extra.txt").write_text("extra\n", encoding="utf-8")
    subprocess.run(["git", "add", "sample.txt", "extra.txt"], cwd=root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "head"], cwd=root, check=True, capture_output=True, text=True)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True).stdout.strip()
    return base, head


class AutonomyPlanCliTests(unittest.TestCase):
    maxDiff = None

    def test_autonomy_plan_positive_json_for_all_goals(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            results = {
                goal: run_cli(["autonomy", "plan", "--goal", goal, "--json"], root)
                for goal in ["release-ops", "post-v1", "autonomous-delivery"]
            }

        for goal, result in results.items():
            with self.subTest(goal=goal):
                self.assertEqual(result[0], 0, result[1] + result[2])
                payload = json.loads(result[1])
                self.assertEqual(payload["schema_version"], 1)
                self.assertEqual(payload["packet_type"], "agentoffice_autonomy_mission_plan")
                self.assertEqual(payload["goal"], goal)
                self.assertEqual(payload["status"], "ready")
                self.assertTrue(payload["local_only"])
                self.assertFalse(payload["network_required"])
                self.assertFalse(payload["provider_runtime_adapter_external_behavior"])
                self.assertGreaterEqual(len(payload["phases"]), 1)
                self.assertGreaterEqual(len(payload["validation_commands"]), 3)
                self.assertIn(".env is never read", payload["safety_boundaries"])
                self.assertIn("phase6/mainline is not merged or mutated by autonomy commands", payload["safety_boundaries"])
                self.assertGreaterEqual(len(payload["expected_artifacts"]), 1)
                self.assertGreaterEqual(len(payload["review_handoff"]), 1)
                self.assertGreaterEqual(len(payload["merge_gate_handoff"]), 1)
                self.assertNotIn("Traceback", result[1] + result[2])

    def test_autonomy_plan_positive_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_cli(["autonomy", "plan", "--goal", "autonomous-delivery"], Path(tmpdir))

        self.assertEqual(result[0], 0, result[1] + result[2])
        self.assertIn("AGENTOFFICE_AUTONOMY_MISSION_PLAN", result[1])
        self.assertIn("goal: autonomous-delivery", result[1])
        self.assertIn("phases:", result[1])
        self.assertIn("validation_commands:", result[1])
        self.assertIn("review_handoff:", result[1])
        self.assertIn("merge_gate_handoff:", result[1])
        self.assertNotIn("Traceback", result[1] + result[2])

    def test_autonomy_plan_unknown_goal_is_clean_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_cli(["autonomy", "plan", "--goal", "unknown"], Path(tmpdir))

        self.assertEqual(result[0], 2)
        self.assertIn("unknown autonomy goal", result[2])
        self.assertNotIn("Traceback", result[1] + result[2])

    def test_autonomy_plan_json_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            first = run_cli(["autonomy", "plan", "--goal", "post-v1", "--json"], root)
            second = run_cli(["autonomy", "plan", "--goal", "post-v1", "--json"], root)

        self.assertEqual(first[0], 0, first[1] + first[2])
        self.assertEqual(second[0], 0, second[1] + second[2])
        self.assertEqual(first[1], second[1])
        self.assertNotIn("Traceback", first[1] + first[2] + second[1] + second[2])


class AutonomyLedgerCliTests(unittest.TestCase):
    maxDiff = None

    def test_autonomy_ledger_init_status_checkpoint_report_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            run_path = root / ".ai" / "autonomy" / "runs" / "demo"
            init = run_cli(["autonomy", "init", "--goal", "autonomous-delivery", "--path", str(run_path), "--json"], root)
            status = run_cli(["autonomy", "status", "--path", str(run_path), "--json"], root)
            checkpoint = run_cli(["autonomy", "checkpoint", "--path", str(run_path), "--name", "preflight", "--status", "passed", "--json"], root)
            report = run_cli(["autonomy", "report", "--path", str(run_path), "--json"], root)

        for result in [init, status, checkpoint, report]:
            self.assertEqual(result[0], 0, result[1] + result[2])
            self.assertNotIn("Traceback", result[1] + result[2])
        init_payload = json.loads(init[1])
        self.assertTrue(init_payload["ok"])
        self.assertEqual(init_payload["action"], "init")
        self.assertEqual(init_payload["ledger"]["goal"], "autonomous-delivery")
        self.assertEqual(init_payload["ledger"]["status"], "running")
        checkpoint_payload = json.loads(checkpoint[1])
        self.assertEqual(checkpoint_payload["ledger"]["status"], "passed")
        self.assertEqual(checkpoint_payload["checkpoint"]["name"], "preflight")
        report_payload = json.loads(report[1])
        self.assertEqual(report_payload["summary"]["checkpoint_count"], 1)
        self.assertEqual(report_payload["summary"]["latest_checkpoint"]["status"], "passed")

    def test_autonomy_ledger_text_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            run_path = root / ".ai" / "autonomy" / "runs" / "demo"
            init = run_cli(["autonomy", "init", "--goal", "post-v1", "--path", str(run_path)], root)

        self.assertEqual(init[0], 0, init[1] + init[2])
        self.assertIn("AGENTOFFICE_AUTONOMY_RUN_LEDGER", init[1])
        self.assertIn("action: init", init[1])
        self.assertIn("goal: post-v1", init[1])
        self.assertNotIn("Traceback", init[1] + init[2])

    def test_autonomy_ledger_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_cli(["autonomy", "init", "--goal", "post-v1", "--path", "../outside", "--json"], Path(tmpdir))

        self.assertEqual(result[0], 2)
        self.assertIn("refused traversal", result[2])
        self.assertNotIn("Traceback", result[1] + result[2])

    def test_autonomy_ledger_rejects_symlink_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target = root / "target"
            target.mkdir()
            link = root / "link"
            link.symlink_to(target, target_is_directory=True)
            result = run_cli(["autonomy", "init", "--goal", "post-v1", "--path", str(link), "--json"], root)

        self.assertEqual(result[0], 2)
        self.assertIn("symlink refused", result[2])
        self.assertNotIn("Traceback", result[1] + result[2])

    def test_autonomy_ledger_malformed_ledger_is_clean_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            run_path = root / ".ai" / "autonomy" / "runs" / "demo"
            run_path.mkdir(parents=True)
            (run_path / "ledger.json").write_text("{bad json", encoding="utf-8")
            result = run_cli(["autonomy", "status", "--path", str(run_path), "--json"], root)

        self.assertEqual(result[0], 2)
        self.assertIn("malformed JSON", result[2])
        self.assertNotIn("Traceback", result[1] + result[2])


class AutonomyValidationCliTests(unittest.TestCase):
    maxDiff = None

    def test_autonomy_validate_minimal_records_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            run_path = root / ".ai" / "autonomy" / "runs" / "demo"
            init = run_cli(["autonomy", "init", "--goal", "autonomous-delivery", "--path", str(run_path), "--json"], root)
            completed = subprocess.CompletedProcess(args=["fake"], returncode=0, stdout="ok out", stderr="")
            with patch("agent_office.autonomy.subprocess.run", return_value=completed) as run_mock:
                result = run_cli(["autonomy", "validate", "--path", str(run_path), "--suite", "minimal", "--json"], root)
            self.assertEqual(init[0], 0, init[1] + init[2])
            self.assertEqual(result[0], 0, result[1] + result[2])
            self.assertEqual(run_mock.call_count, 3)
            payload = json.loads(result[1])
            first = payload["validation"]["commands"][0]
            self.assertTrue(Path(first["stdout_path"]).exists())
            self.assertTrue(Path(first["stderr_path"]).exists())
            self.assertEqual(Path(first["stdout_path"]).read_text(encoding="utf-8"), "ok out")

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["validation"]["suite"], "minimal")
        self.assertEqual(payload["validation"]["status"], "passed")
        self.assertEqual(len(payload["validation"]["commands"]), 3)
        self.assertEqual(first["exit_code"], 0)
        self.assertEqual(payload["ledger"]["validation_records"][0]["status"], "passed")
        self.assertNotIn("Traceback", result[1] + result[2])

    def test_autonomy_validate_records_failed_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            run_path = root / ".ai" / "autonomy" / "runs" / "demo"
            init = run_cli(["autonomy", "init", "--goal", "autonomous-delivery", "--path", str(run_path), "--json"], root)
            results = [
                subprocess.CompletedProcess(args=["fake1"], returncode=0, stdout="ok", stderr=""),
                subprocess.CompletedProcess(args=["fake2"], returncode=7, stdout="", stderr="bad"),
                subprocess.CompletedProcess(args=["fake3"], returncode=0, stdout="ok", stderr=""),
            ]
            with patch("agent_office.autonomy.subprocess.run", side_effect=results):
                result = run_cli(["autonomy", "validate", "--path", str(run_path), "--suite", "minimal", "--json"], root)
            payload = json.loads(result[1])
            failed_stderr = Path(payload["validation"]["commands"][1]["stderr_path"]).read_text(encoding="utf-8")

        self.assertEqual(init[0], 0, init[1] + init[2])
        self.assertEqual(result[0], 2)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["validation"]["status"], "failed")
        self.assertEqual(payload["validation"]["commands"][1]["exit_code"], 7)
        self.assertEqual(failed_stderr, "bad")
        self.assertEqual(payload["ledger"]["status"], "failed")
        self.assertNotIn("Traceback", result[1] + result[2])

    def test_autonomy_validate_unknown_suite_is_clean_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            run_path = root / ".ai" / "autonomy" / "runs" / "demo"
            init = run_cli(["autonomy", "init", "--goal", "autonomous-delivery", "--path", str(run_path), "--json"], root)
            result = run_cli(["autonomy", "validate", "--path", str(run_path), "--suite", "unknown", "--json"], root)

        self.assertEqual(init[0], 0, init[1] + init[2])
        self.assertEqual(result[0], 2)
        self.assertIn("unknown validation suite", result[2])
        self.assertNotIn("Traceback", result[1] + result[2])


class AutonomyReviewPacketCliTests(unittest.TestCase):
    maxDiff = None

    def test_autonomy_review_packet_positive_json_and_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            base, head = make_git_repo(root)
            out = root / "review-packet.md"
            result = run_cli(["autonomy", "review-packet", "--base", base, "--head", head, "--out", str(out), "--json"], root)
            bundle = out.read_text(encoding="utf-8")

        self.assertEqual(result[0], 0, result[1] + result[2])
        payload = json.loads(result[1])
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["base"], base)
        self.assertEqual(payload["head"], head)
        self.assertEqual(payload["commit_count"], 1)
        self.assertGreaterEqual(payload["snapshot_count"], 2)
        self.assertIn("# AgentOffice Autonomy Review Packet", bundle)
        self.assertIn("## Full Diff", bundle)
        self.assertIn("sample.txt", bundle)
        self.assertIn("extra.txt", bundle)
        self.assertIn(".env is never read", bundle)
        self.assertNotIn("Traceback", result[1] + result[2])

    def test_autonomy_review_packet_text_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            base, head = make_git_repo(root)
            out = root / "review-packet.md"
            result = run_cli(["autonomy", "review-packet", "--base", base, "--head", head, "--out", str(out)], root)

        self.assertEqual(result[0], 0, result[1] + result[2])
        self.assertIn("AGENTOFFICE_AUTONOMY_REVIEW_PACKET", result[1])
        self.assertIn(f"base: {base}", result[1])
        self.assertNotIn("Traceback", result[1] + result[2])

    def test_autonomy_review_packet_rejects_unsafe_out(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            base, head = make_git_repo(root)
            traversal = run_cli(["autonomy", "review-packet", "--base", base, "--head", head, "--out", "../packet.md", "--json"], root)
            target = root / "target.md"
            target.write_text("target", encoding="utf-8")
            link = root / "link.md"
            link.symlink_to(target)
            symlink = run_cli(["autonomy", "review-packet", "--base", base, "--head", head, "--out", str(link), "--json"], root)

        self.assertEqual(traversal[0], 2)
        self.assertIn("refused traversal", traversal[2])
        self.assertEqual(symlink[0], 2)
        self.assertIn("symlink refused", symlink[2])
        self.assertNotIn("Traceback", traversal[1] + traversal[2] + symlink[1] + symlink[2])

    def test_autonomy_review_packet_missing_ref_is_clean_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _base, head = make_git_repo(root)
            result = run_cli(["autonomy", "review-packet", "--base", "missing-ref", "--head", head, "--out", str(root / "packet.md"), "--json"], root)

        self.assertEqual(result[0], 2)
        self.assertIn("review_packet_base failed", result[2])
        self.assertNotIn("Traceback", result[1] + result[2])


if __name__ == "__main__":
    unittest.main()
