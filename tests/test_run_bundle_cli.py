from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from agent_office import cli
from agent_office.run_bundle import RUN_BUNDLE_REQUIRED_FILES, run_bundle_preview_payload


PACKET_ACTORS = ("codex", "reviewer", "judge")


def run_cli(argv: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = cli.main(argv)
    return exit_code, stdout.getvalue(), stderr.getvalue()


class RunBundlePayloadTests(unittest.TestCase):
    maxDiff = None

    def test_static_run_bundle_preview_contract(self) -> None:
        payload = run_bundle_preview_payload("P6-17", "lowest-cost", "P7-STATIC-RUN")

        self.assertEqual(payload["kind"], "static_run_bundle")
        self.assertEqual(payload["schema_version"], 1)
        self.assertFalse(payload["execution_enabled"])
        self.assertEqual(payload["provider_calls"], [])
        self.assertFalse(payload["runtime_calls"])
        self.assertFalse(payload["adapter_calls"])
        self.assertFalse(payload["env_required"])
        self.assertFalse(payload["artifact_writes"])
        run = payload["run"]
        self.assertIsInstance(run, dict)
        self.assertEqual(run["run_id"], "P7-STATIC-RUN")
        self.assertEqual(run["objective"]["id"], "P6-17")
        self.assertEqual(run["profile"]["selected"], "lowest-cost")
        self.assertFalse(run["execution_enabled"])
        self.assertEqual(run["provider_calls"], [])
        self.assertEqual(run["actors"], list(PACKET_ACTORS))
        self.assertEqual(payload["plan"]["objective_id"], "P6-17")
        self.assertEqual(payload["plan"]["selected_profile"], "lowest-cost")
        self.assertEqual(tuple(payload["packets"]), PACKET_ACTORS)
        self.assertEqual(payload["validation"]["required_files"], list(RUN_BUNDLE_REQUIRED_FILES))
        self.assertTrue(payload["validation"]["valid"])
        json.dumps(payload)

    def test_unknown_inputs_raise_clear_errors(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown objective: UNKNOWN"):
            run_bundle_preview_payload("UNKNOWN", "lowest-cost", "BAD")
        with self.assertRaisesRegex(ValueError, "Unknown provider profile: UNKNOWN"):
            run_bundle_preview_payload("P6-17", "UNKNOWN", "BAD")


class RunBundleCliTests(unittest.TestCase):
    maxDiff = None

    def test_run_bundle_json_preview_does_not_write_ai_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            exit_code, stdout, stderr = run_cli(
                [
                    "run-bundle",
                    "--objective",
                    "P6-17",
                    "--profile",
                    "lowest-cost",
                    "--run-id",
                    "P7-STATIC-RUN",
                    "--json",
                ]
            )

            self.assertEqual(exit_code, 0, stderr)
            self.assertFalse((Path(tmpdir) / ".ai").exists())
        payload = json.loads(stdout)
        self.assertEqual(payload, run_bundle_preview_payload("P6-17", "lowest-cost", "P7-STATIC-RUN"))

    def test_run_bundle_out_writes_required_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            exit_code, stdout, stderr = run_cli(
                [
                    "run-bundle",
                    "--objective",
                    "P6-17",
                    "--profile",
                    "lowest-cost",
                    "--run-id",
                    "P7-STATIC-RUN",
                    "--out",
                    ".ai/runs/P7-STATIC-RUN",
                ]
            )

            self.assertEqual(exit_code, 0, stderr)
            self.assertIn("AgentOffice static run bundle", stdout)
            out_root = Path(tmpdir) / ".ai" / "runs" / "P7-STATIC-RUN"
            for relative in RUN_BUNDLE_REQUIRED_FILES:
                self.assertTrue((out_root / relative).is_file(), relative)
            run = json.loads((out_root / "run.json").read_text(encoding="utf-8"))
            self.assertEqual(run["run_id"], "P7-STATIC-RUN")
            self.assertEqual(run["objective"]["id"], "P6-17")
            self.assertEqual(run["profile"]["selected"], "lowest-cost")
            self.assertFalse(run["execution_enabled"])
            self.assertEqual(run["provider_calls"], [])
            self.assertEqual(run["actors"], list(PACKET_ACTORS))

    def test_run_bundle_out_json_writes_and_reports_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            exit_code, stdout, stderr = run_cli(
                [
                    "run-bundle",
                    "--objective",
                    "P6-17",
                    "--profile",
                    "lowest-cost",
                    "--run-id",
                    "P7-STATIC-RUN",
                    "--out",
                    ".ai/runs/P7-STATIC-RUN",
                    "--json",
                ]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertTrue(payload["write_result"]["enabled"])
            self.assertTrue(payload["artifact_writes"])
            self.assertEqual(payload["write_result"]["files_written"], list(RUN_BUNDLE_REQUIRED_FILES))
            self.assertTrue((Path(tmpdir) / ".ai" / "runs" / "P7-STATIC-RUN" / "validation.json").is_file())

    def test_run_bundle_unknown_objective_exits_two_without_traceback(self) -> None:
        exit_code, stdout, stderr = run_cli(
            ["run-bundle", "--objective", "UNKNOWN", "--profile", "lowest-cost", "--run-id", "BAD", "--json"]
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("Unknown objective: UNKNOWN", stderr)
        self.assertNotIn("Traceback", stderr)

    def test_run_bundle_unknown_profile_exits_two_without_traceback(self) -> None:
        exit_code, stdout, stderr = run_cli(
            ["run-bundle", "--objective", "P6-17", "--profile", "UNKNOWN", "--run-id", "BAD", "--json"]
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("Unknown provider profile: UNKNOWN", stderr)
        self.assertNotIn("Traceback", stderr)
