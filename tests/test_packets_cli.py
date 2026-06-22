from __future__ import annotations

import argparse
import io
import json
import os
import tempfile
import unittest
from collections.abc import MutableMapping
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from agent_office import cli
from agent_office.packets import execution_packet_payload
from agent_office.planner import execution_blueprint_payload


class EnvGuard(MutableMapping[str, str]):
    def __getitem__(self, key: str) -> str:
        raise AssertionError(f"environment was read: {key}")

    def __setitem__(self, key: str, value: str) -> None:
        raise AssertionError(f"environment was written: {key}")

    def __delitem__(self, key: str) -> None:
        raise AssertionError(f"environment was deleted: {key}")

    def __iter__(self):
        raise AssertionError("environment was iterated")

    def __len__(self) -> int:
        raise AssertionError("environment length was read")


def run_cli(argv: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = cli.main(argv)
    return exit_code, stdout.getvalue(), stderr.getvalue()


class PacketPayloadTests(unittest.TestCase):
    def test_codex_packet_contract(self) -> None:
        packet = execution_packet_payload("P6-10", "lowest-cost", "codex")

        self.assertEqual(
            list(packet),
            [
                "packet_version",
                "objective",
                "profile",
                "blueprint",
                "actor",
                "instructions",
                "safety_constraints",
                "allowed_actions",
                "forbidden_actions",
                "validation_commands",
                "success_criteria",
                "failure_criteria",
                "handoff_summary",
                "execution_enabled",
                "env_required",
                "provider_calls",
                "runtime_calls",
                "adapter_calls",
            ],
        )
        self.assertEqual(packet["packet_version"], 1)
        self.assertEqual(packet["objective"]["id"], "P6-10")
        self.assertEqual(packet["profile"]["selected"], "lowest-cost")
        self.assertEqual(packet["blueprint"], execution_blueprint_payload("P6-10", "lowest-cost"))
        self.assertEqual(packet["actor"], "codex")
        self.assertFalse(packet["execution_enabled"])
        self.assertFalse(packet["env_required"])
        self.assertFalse(packet["runtime_calls"])
        self.assertFalse(packet["adapter_calls"])
        self.assertIn("Read relevant files before changing code.", packet["instructions"])
        self.assertIn("Implement minimal scoped changes that satisfy the packet objective and existing project style.", packet["instructions"])
        self.assertIn("Run validation commands after implementation.", packet["instructions"])
        self.assertIn("Self-fix on validation failure, then rerun the full validation set.", packet["instructions"])
        self.assertIn("Commit and push branch only after validation passes.", packet["instructions"])
        self.assertIn("read `.env`", packet["forbidden_actions"])
        self.assertIn("print env vars", packet["forbidden_actions"])
        self.assertIn("trigger real provider/runtime/adapter behavior", packet["forbidden_actions"])
        self.assertIn("modify unrelated files", packet["forbidden_actions"])
        self.assertIn("bypass tests", packet["forbidden_actions"])
        self.assertIn("python3 -m agent_office packet --objective P6-10 --profile lowest-cost --actor codex --json", packet["validation_commands"])
        json.dumps(packet)

    def test_reviewer_packet_contract(self) -> None:
        packet = execution_packet_payload("P6-10", "lowest-cost", "reviewer")

        self.assertEqual(packet["actor"], "reviewer")
        self.assertIn("Inspect diff for the packet implementation.", packet["instructions"])
        self.assertIn("Check contract stability across text and JSON outputs.", packet["instructions"])
        self.assertIn("Check safety boundaries for env, provider, runtime, and adapter behavior.", packet["instructions"])
        self.assertIn("Check negative cases for clear nonzero failures without traceback.", packet["instructions"])
        self.assertIn("Verify deterministic JSON suitable for tests.", packet["instructions"])
        self.assertIn("Report risks without modifying code.", packet["instructions"])
        self.assertIn("inspect diff", packet["allowed_actions"])
        self.assertIn("code changes", packet["forbidden_actions"])
        self.assertIn("commits", packet["forbidden_actions"])
        self.assertIn("pushes", packet["forbidden_actions"])
        self.assertIn("`.env` reads", packet["forbidden_actions"])
        self.assertIn("real provider/runtime/adapter behavior", packet["forbidden_actions"])

    def test_judge_packet_contract(self) -> None:
        packet = execution_packet_payload("P6-10", "lowest-cost", "judge")

        self.assertEqual(packet["actor"], "judge")
        self.assertIn("Decide pass/fail for the completed packet work.", packet["instructions"])
        self.assertIn("Confirm validation evidence covers required commands and negative cases.", packet["instructions"])
        self.assertIn("Confirm no boundary breach for env, provider, runtime, or adapter behavior.", packet["instructions"])
        self.assertIn("Approve merge or reject with reasons.", packet["instructions"])
        self.assertIn("implementation changes", packet["forbidden_actions"])
        self.assertIn("silent fixes", packet["forbidden_actions"])
        self.assertIn("bypassing failed validation", packet["forbidden_actions"])
        self.assertIn("pushing without explicit pass", packet["forbidden_actions"])

    def test_unknown_inputs_raise_clear_errors(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown objective: UNKNOWN"):
            execution_packet_payload("UNKNOWN", "lowest-cost", "codex")
        with self.assertRaisesRegex(ValueError, "Unknown provider profile: UNKNOWN"):
            execution_packet_payload("P6-10", "UNKNOWN", "codex")
        with self.assertRaisesRegex(ValueError, "Unknown packet actor: unknown"):
            execution_packet_payload("P6-10", "lowest-cost", "unknown")


class PacketCliTests(unittest.TestCase):
    def test_packet_text_outputs_stable_summary(self) -> None:
        exit_code, stdout, stderr = run_cli(["packet", "--objective", "P6-10", "--profile", "lowest-cost", "--actor", "codex"])

        self.assertEqual(exit_code, 0, stderr)
        self.assertIn("AgentOffice execution packet", stdout)
        self.assertIn("objective: P6-10 - Objective Spec CLI Contract", stdout)
        self.assertIn("profile: lowest-cost", stdout)
        self.assertIn("actor: codex", stdout)
        self.assertIn("execution_enabled: false", stdout)
        self.assertIn("safety_constraints:", stdout)
        self.assertIn("validation_commands:", stdout)
        self.assertIn("success_criteria:", stdout)

    def test_packet_json_outputs_all_actor_contracts(self) -> None:
        for actor in ("codex", "reviewer", "judge"):
            with self.subTest(actor=actor):
                exit_code, stdout, stderr = run_cli(["packet", "--objective", "P6-10", "--profile", "lowest-cost", "--actor", actor, "--json"])

                self.assertEqual(exit_code, 0, stderr)
                self.assertEqual(json.loads(stdout), execution_packet_payload("P6-10", "lowest-cost", actor))

    def test_packet_unknown_objective_returns_error_without_traceback(self) -> None:
        exit_code, stdout, stderr = run_cli(["packet", "--objective", "UNKNOWN", "--profile", "lowest-cost", "--actor", "codex"])

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("Unknown objective: UNKNOWN", stderr)
        self.assertNotIn("Traceback", stderr)

    def test_packet_unknown_profile_returns_error_without_traceback(self) -> None:
        exit_code, stdout, stderr = run_cli(["packet", "--objective", "P6-10", "--profile", "UNKNOWN", "--actor", "codex"])

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("Unknown provider profile: UNKNOWN", stderr)
        self.assertNotIn("Traceback", stderr)

    def test_packet_unknown_actor_returns_error_without_traceback(self) -> None:
        exit_code, stdout, stderr = run_cli(["packet", "--objective", "P6-10", "--profile", "lowest-cost", "--actor", "unknown"])

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("Unknown packet actor: unknown", stderr)
        self.assertNotIn("Traceback", stderr)

    def test_packet_does_not_read_environment(self) -> None:
        stdout = io.StringIO()
        args = argparse.Namespace(objective="P6-10", profile="lowest-cost", actor="codex", json=True)
        with patch.object(os, "environ", EnvGuard()), patch.object(cli.os, "environ", EnvGuard()):
            with redirect_stdout(stdout):
                exit_code = cli.cmd_packet(args)

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout.getvalue())["actor"], "codex")

    def test_packet_does_not_write_files_or_create_ai(self) -> None:
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                exit_code, stdout, stderr = run_cli(["packet", "--objective", "P6-10", "--profile", "lowest-cost", "--actor", "codex"])
            finally:
                os.chdir(original_cwd)

            self.assertEqual(exit_code, 0, stderr)
            self.assertIn("actor: codex", stdout)
            self.assertFalse((Path(tmp) / ".ai").exists())


if __name__ == "__main__":
    unittest.main()
