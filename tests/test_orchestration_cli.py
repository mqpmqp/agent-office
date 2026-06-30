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
            files_present = {filename: (out / filename).is_file() for filename in REQUIRED_FILES}
            role_packets_present = {role: (out / f"{role}_packet.md").is_file() for role in PACKET_ROLES}

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertTrue(payload["valid"])
        self.assertEqual(payload["mode"], "static")
        self.assertFalse(payload["external_call_made"])
        self.assertEqual(payload["provider_calls"], [])
        self.assertEqual(list(manifest)[:6], ["schema_version", "orchestration_id", "mode", "task", "created_at", "external_call_made"])
        self.assertFalse(manifest["external_call_made"])
        self.assertEqual(manifest["provider_calls"], [])
        self.assertIn("task_understanding", manifest)
        self.assertIn("decomposition", manifest)
        self.assertIn("task_graph", manifest)
        self.assertTrue(manifest["task_graph"]["nodes"])
        self.assertTrue(manifest["task_graph"]["edges"])
        self.assertTrue(manifest["task_graph"]["execution_order"])
        for filename in REQUIRED_FILES:
            self.assertTrue(files_present[filename], filename)
        for role in PACKET_ROLES:
            self.assertTrue(role_packets_present[role], role)
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
