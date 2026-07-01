from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from agent_office import cli
from agent_office.orchestration import PACKET_ROLES, REQUIRED_FILES, classify_task


def run_cli(argv: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = cli.main(argv)
    return exit_code, stdout.getvalue(), stderr.getvalue()


class OrchestrationCliTests(unittest.TestCase):
    maxDiff = None

    def test_orchestrate_run_creates_complete_static_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "ao-orch"
            code, stdout, stderr = run_cli(
                [
                    "orchestrate",
                    "run",
                    "--task",
                    "Improve this project safely",
                    "--mode",
                    "static",
                    "--out",
                    str(out),
                    "--json",
                ]
            )
            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            phase_report = (out / "phase_report.md").read_text(encoding="utf-8")
            files_present = {filename: (out / filename).is_file() for filename in REQUIRED_FILES}
            role_packets_present = {role: (out / f"{role}_packet.md").is_file() for role in PACKET_ROLES}

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertTrue(payload["valid"])
        self.assertEqual(payload["mode"], "static")
        self.assertFalse(payload["external_call_made"])
        self.assertEqual(payload["provider_calls"], [])
        self.assertEqual(list(manifest)[:6], ["schema_version", "orchestration_id", "mode", "task", "external_call_made", "provider_calls"])
        self.assertNotIn("created_at", manifest)
        self.assertNotIn("Commit:" + " pending", phase_report)
        self.assertFalse(manifest["external_call_made"])
        self.assertEqual(manifest["provider_calls"], [])
        self.assertIn("task_understanding", manifest)
        self.assertIn("decomposition", manifest)
        self.assertIn("task_graph", manifest)
        self.assertIn("source_state", manifest)
        self.assertIn("generated_artifacts", manifest)
        self.assertIn("validation_commands", manifest)
        self.assertEqual(manifest["generated_artifacts"]["phase_report_path"], "phase_report.md")
        self.assertIn("source_commit", manifest["source_state"])
        self.assertIn("baseline_commit", manifest["source_state"])
        self.assertIn(manifest["source_state"]["state"], {"clean", "dirty", "unavailable"})
        self.assertEqual(payload["phase_report_path"], str(out / "phase_report.md"))
        self.assertIn("source_commit", payload)
        self.assertIn("baseline_commit", payload)
        self.assertIn("validation_commands", payload)
        self.assertIn("Review phase_report.md", payload["review_gate_hint"])
        self.assertTrue(manifest["task_graph"]["nodes"])
        self.assertTrue(manifest["task_graph"]["edges"])
        self.assertTrue(manifest["task_graph"]["execution_order"])
        for filename in REQUIRED_FILES:
            self.assertTrue(files_present[filename], filename)
        for role in PACKET_ROLES:
            self.assertTrue(role_packets_present[role], role)
        self.assertIn("## Source State", phase_report)
        self.assertIn("- source_commit:", phase_report)
        self.assertIn("- baseline_commit:", phase_report)
        self.assertIn("## Validation", phase_report)
        self.assertIn("## Next Action", phase_report)
        self.assertIn("## Known Follow-ups", phase_report)
        self.assertIn("phase_report_path: phase_report.md", phase_report)
        self.assertNotIn("Traceback", stdout + stderr)

    def test_orchestrate_run_text_output_includes_reviewable_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "ao-orch"
            code, stdout, stderr = run_cli(
                ["orchestrate", "run", "--task", "Review text output", "--mode", "static", "--out", str(out)]
            )

        self.assertEqual(code, 0, stderr)
        self.assertIn("source_state:", stdout)
        self.assertIn("source_commit:", stdout)
        self.assertIn("baseline_commit:", stdout)
        self.assertIn("phase_report_path:", stdout)
        self.assertIn("review_gate_hint:", stdout)
        self.assertNotIn("Commit:" + " pending", stdout)

    def test_orchestrate_run_dirty_source_state_is_explicit_not_placeholder(self) -> None:
        dirty_state = {
            "available": True,
            "source_branch": "feature/example",
            "source_commit": "abc123",
            "state": "dirty",
            "baseline_ref": "origin/phase6/mainline",
            "baseline_commit": "def456",
            "tracked_dirty": True,
            "pending_change_state": "tracked_changes_pending",
            "pending_change_count": 1,
            "pending_changes": [" M agent_office/orchestration.py"],
        }
        with tempfile.TemporaryDirectory() as tmpdir, patch("agent_office.orchestration._git_source_state", return_value=dirty_state):
            out = Path(tmpdir) / "ao-orch"
            code, stdout, stderr = run_cli(
                ["orchestrate", "run", "--task", "Review dirty state", "--mode", "static", "--out", str(out), "--json"]
            )
            payload = json.loads(stdout)
            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            phase_report = (out / "phase_report.md").read_text(encoding="utf-8")

        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload["source_state"], "dirty")
        self.assertEqual(payload["source_commit"], "abc123")
        self.assertEqual(payload["baseline_commit"], "def456")
        self.assertTrue(manifest["source_state"]["tracked_dirty"])
        self.assertEqual(manifest["source_state"]["pending_change_state"], "tracked_changes_pending")
        self.assertIn("pending_change_state: tracked_changes_pending", phase_report)
        self.assertIn(" M agent_office/orchestration.py", phase_report)
        self.assertNotIn("Commit:" + " pending", phase_report)

    def test_orchestrate_run_is_byte_reproducible_for_same_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            first = root / "first"
            second = root / "second"
            task = "Review reproducibility polish before merge"
            first_result = run_cli(["orchestrate", "run", "--task", task, "--mode", "static", "--out", str(first), "--json"])
            second_result = run_cli(["orchestrate", "run", "--task", task, "--mode", "static", "--out", str(second), "--json"])
            first_files = sorted(path.relative_to(first).as_posix() for path in first.rglob("*") if path.is_file())
            second_files = sorted(path.relative_to(second).as_posix() for path in second.rglob("*") if path.is_file())
            file_bytes = {filename: ((first / filename).read_bytes(), (second / filename).read_bytes()) for filename in first_files}

        self.assertEqual(first_result[0], 0, first_result[2])
        self.assertEqual(second_result[0], 0, second_result[2])
        self.assertEqual(first_files, second_files)
        self.assertEqual(first_files, sorted(REQUIRED_FILES))
        for filename, (first_content, second_content) in file_bytes.items():
            self.assertEqual(first_content, second_content, filename)

    def test_orchestrate_run_refuses_symlink_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target = root / "target"
            target.mkdir()
            link = root / "link"
            try:
                link.symlink_to(target, target_is_directory=True)
            except (NotImplementedError, OSError) as exc:
                self.skipTest(f"symlink creation not supported: {exc}")
            code, stdout, stderr = run_cli(["orchestrate", "run", "--task", "Review symlink safety", "--mode", "static", "--out", str(link), "--json"])

        self.assertEqual(code, 2)
        payload = json.loads(stdout)
        self.assertFalse(payload["valid"])
        self.assertIn("output_path_symlink_refused", payload["errors"])
        self.assertNotIn("Traceback", stdout + stderr)

    def test_task_classification_rules(self) -> None:
        cases = {
            "Review this change before merge": "code_review",
            "Debug traceback from failing test": "debugging",
            "Fix the CLI parser safely": "software_change",
            "Research options for queue storage": "research",
            "Plan the roadmap and scope": "planning",
            "Update README docs": "documentation",
            "Handle the thing": "unknown",
        }
        for task, expected in cases.items():
            with self.subTest(task=task):
                self.assertEqual(classify_task(task), expected)

    def test_orchestrate_inspect_valid_missing_and_invalid_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            out = root / "valid"
            run_cli(["orchestrate", "run", "--task", "Review this change safely", "--mode", "static", "--out", str(out), "--json"])
            valid_result = run_cli(["orchestrate", "inspect", "--path", str(out), "--json"])
            missing_result = run_cli(["orchestrate", "inspect", "--path", str(root / "missing"), "--json"])
            invalid = root / "invalid"
            invalid.mkdir()
            (invalid / "manifest.json").write_text("{not json", encoding="utf-8")
            invalid_result = run_cli(["orchestrate", "inspect", "--path", str(invalid), "--json"])

        valid_code, valid_stdout, valid_stderr = valid_result
        self.assertEqual(valid_code, 0, valid_stderr)
        valid_payload = json.loads(valid_stdout)
        self.assertTrue(valid_payload["valid"])
        self.assertEqual(valid_payload["task_type"], "code_review")
        self.assertFalse(valid_payload["external_call_made"])
        for code, stdout, stderr in (missing_result, invalid_result):
            self.assertEqual(code, 2)
            payload = json.loads(stdout)
            self.assertFalse(payload["valid"])
            self.assertTrue(payload["errors"])
            self.assertNotIn("Traceback", stdout + stderr)

    def test_orchestrate_validate_good_missing_file_and_malformed_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            out = root / "valid"
            run_cli(["orchestrate", "run", "--task", "Fix the failing command", "--mode", "static", "--out", str(out), "--json"])
            good_result = run_cli(["orchestrate", "validate", "--path", str(out), "--json"])
            (out / "judge_packet.md").unlink()
            missing_file_result = run_cli(["orchestrate", "validate", "--path", str(out), "--json"])
            bad = root / "bad"
            bad.mkdir()
            (bad / "manifest.json").write_text("{bad json", encoding="utf-8")
            malformed_result = run_cli(["orchestrate", "validate", "--path", str(bad), "--json"])

        good_code, good_stdout, good_stderr = good_result
        self.assertEqual(good_code, 0, good_stderr)
        self.assertTrue(json.loads(good_stdout)["valid"])
        for code, stdout, stderr in (missing_file_result, malformed_result):
            self.assertEqual(code, 2)
            payload = json.loads(stdout)
            self.assertFalse(payload["valid"])
            self.assertTrue(payload["errors"])
            self.assertNotIn("Traceback", stdout + stderr)

    def test_orchestrate_run_reports_output_directory_errors_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            parent = root / "not-a-directory"
            parent.write_text("x", encoding="utf-8")
            code, stdout, stderr = run_cli(
                [
                    "orchestrate",
                    "run",
                    "--task",
                    "Review output failure",
                    "--mode",
                    "static",
                    "--out",
                    str(parent / "child"),
                    "--json",
                ]
            )

        self.assertEqual(code, 2)
        payload = json.loads(stdout)
        self.assertFalse(payload["valid"])
        self.assertIn("output_directory_create_failed", "\n".join(payload["errors"]))
        self.assertNotIn("Traceback", stdout + stderr)

    def test_static_mode_safety_and_forbidden_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "run_adapter", side_effect=AssertionError("provider called")):
            root = Path(tmpdir)
            (root / ".env").write_text("SECRET_SHOULD_NOT_APPEAR=1\n", encoding="utf-8")
            out = root / "ao-orch"
            code, stdout, stderr = run_cli(
                ["orchestrate", "run", "--task", "Implement a small safe change", "--mode", "static", "--out", str(out), "--json"]
            )
            manifest_text = (out / "manifest.json").read_text(encoding="utf-8")
            packet_text = (out / "implementer_packet.md").read_text(encoding="utf-8")
            manifest = json.loads(manifest_text)

        self.assertEqual(code, 0, stderr)
        self.assertFalse(manifest["external_call_made"])
        self.assertEqual(manifest["provider_calls"], [])
        self.assertFalse(manifest["safety"]["dotenv_read"])
        for forbidden in (
            "do not read .env",
            "do not print env vars",
            "do not claim tests passed unless test output is provided",
            "do not make external provider calls in static mode",
            "do not merge/push/tag unless explicitly authorized",
        ):
            self.assertIn(forbidden, packet_text)
        self.assertNotIn("SECRET_SHOULD_NOT_APPEAR", manifest_text + packet_text + stdout + stderr)
        self.assertNotIn("Traceback", stdout + stderr)


if __name__ == "__main__":
    unittest.main()
