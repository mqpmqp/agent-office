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


class PlannerPayloadTests(unittest.TestCase):
    def test_lowest_cost_blueprint_contract(self) -> None:
        payload = execution_blueprint_payload("P6-10", "lowest-cost")

        self.assertEqual(
            list(payload),
            [
                "kind",
                "schema_version",
                "objective_id",
                "objective_name",
                "objective_summary",
                "selected_profile",
                "default_profile",
                "is_default",
                "execution_enabled",
                "provider_calls",
                "runtime_calls",
                "adapter_calls",
                "env_required",
                "safety_constraints",
                "validation_commands",
                "next_actor",
                "next_action_summary",
            ],
        )
        self.assertEqual(payload["kind"], "execution_blueprint")
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["objective_id"], "P6-10")
        self.assertEqual(payload["objective_name"], "Objective Spec CLI Contract")
        self.assertIn("provider-safe objective spec surface", payload["objective_summary"])
        self.assertEqual(payload["selected_profile"], "lowest-cost")
        self.assertEqual(payload["default_profile"], "lowest-cost")
        self.assertTrue(payload["is_default"])
        self.assertFalse(payload["execution_enabled"])
        self.assertEqual(
            payload["provider_calls"],
            [
                {"role": "context", "provider": "chatgpt-manual", "execution_category": "manual", "call_enabled": False},
                {"role": "implement", "provider": "codex", "execution_category": "local-cli", "call_enabled": False},
                {"role": "review", "provider": "chatgpt-manual", "execution_category": "manual", "call_enabled": False},
                {"role": "judge", "provider": "chatgpt-manual", "execution_category": "manual", "call_enabled": False},
            ],
        )
        self.assertFalse(payload["runtime_calls"])
        self.assertFalse(payload["adapter_calls"])
        self.assertFalse(payload["env_required"])
        self.assertIn("do_not_call_providers", payload["safety_constraints"])
        self.assertIn("python3 -m agent_office objectives --validate", payload["validation_commands"])
        self.assertIn("python3 -m agent_office plan --objective P6-10 --profile lowest-cost --json", payload["validation_commands"])
        self.assertEqual(payload["next_actor"], "human_or_codex")
        json.dumps(payload)

    def test_p6_16_lowest_cost_blueprint_contract(self) -> None:
        payload = execution_blueprint_payload("P6-16", "lowest-cost")

        self.assertEqual(payload["kind"], "execution_blueprint")
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["objective_id"], "P6-16")
        self.assertEqual(payload["objective_name"], "Static Multi-Objective Registry")
        self.assertIn("static multi-objective registry", payload["objective_summary"])
        self.assertEqual(payload["selected_profile"], "lowest-cost")
        self.assertEqual(payload["default_profile"], "lowest-cost")
        self.assertTrue(payload["is_default"])
        self.assertFalse(payload["execution_enabled"])
        self.assertFalse(payload["runtime_calls"])
        self.assertFalse(payload["adapter_calls"])
        self.assertFalse(payload["env_required"])
        self.assertIn("do_not_call_providers", payload["safety_constraints"])
        self.assertIn("python3 -m agent_office objectives --show P6-16", payload["validation_commands"])
        self.assertIn("python3 -m agent_office plan --objective P6-16 --profile lowest-cost --json", payload["validation_commands"])
        self.assertNotIn("python3 -m agent_office plan --objective P6-10 --profile lowest-cost --json", payload["validation_commands"])
        self.assertEqual(payload["next_actor"], "human_or_codex")
        json.dumps(payload)

    def test_p6_17_lowest_cost_blueprint_contract(self) -> None:
        payload = execution_blueprint_payload("P6-17", "lowest-cost")

        self.assertEqual(payload["kind"], "execution_blueprint")
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["objective_id"], "P6-17")
        self.assertEqual(payload["objective_name"], "Static Objective Registry Extension")
        self.assertIn("static objective spec", payload["objective_summary"])
        self.assertEqual(payload["selected_profile"], "lowest-cost")
        self.assertEqual(payload["default_profile"], "lowest-cost")
        self.assertTrue(payload["is_default"])
        self.assertFalse(payload["execution_enabled"])
        self.assertFalse(payload["runtime_calls"])
        self.assertFalse(payload["adapter_calls"])
        self.assertFalse(payload["env_required"])
        self.assertIn("do_not_call_providers", payload["safety_constraints"])
        self.assertIn("python3 -m agent_office objectives --phase P6-17 --json", payload["validation_commands"])
        self.assertIn("python3 -m agent_office objectives --show P6-17", payload["validation_commands"])
        self.assertIn("python3 -m agent_office plan --objective P6-17 --profile lowest-cost --json", payload["validation_commands"])
        self.assertNotIn("python3 -m agent_office plan --objective P6-16 --profile lowest-cost --json", payload["validation_commands"])
        self.assertEqual(payload["next_actor"], "human_or_codex")
        json.dumps(payload)

    def test_p6_18_lowest_cost_blueprint_contract(self) -> None:
        payload = execution_blueprint_payload("P6-18", "lowest-cost")

        self.assertEqual(payload["kind"], "execution_blueprint")
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["objective_id"], "P6-18")
        self.assertEqual(payload["objective_name"], "Static Objective Progression")
        self.assertIn("static objective progression", payload["objective_summary"])
        self.assertEqual(payload["selected_profile"], "lowest-cost")
        self.assertEqual(payload["default_profile"], "lowest-cost")
        self.assertTrue(payload["is_default"])
        self.assertFalse(payload["execution_enabled"])
        self.assertFalse(payload["runtime_calls"])
        self.assertFalse(payload["adapter_calls"])
        self.assertFalse(payload["env_required"])
        self.assertIn("do_not_call_providers", payload["safety_constraints"])
        self.assertIn("python3 -m agent_office objectives --phase P6-18 --json", payload["validation_commands"])
        self.assertIn("python3 -m agent_office objectives --show P6-18", payload["validation_commands"])
        self.assertIn("python3 -m agent_office plan --objective P6-18 --profile lowest-cost --json", payload["validation_commands"])
        self.assertNotIn("python3 -m agent_office plan --objective P6-17 --profile lowest-cost --json", payload["validation_commands"])
        self.assertEqual(payload["next_actor"], "human_or_codex")
        json.dumps(payload)

    def test_unknown_objective_raises_clear_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown objective: UNKNOWN"):
            execution_blueprint_payload("UNKNOWN", "lowest-cost")

    def test_unknown_profile_raises_clear_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown provider profile: UNKNOWN"):
            execution_blueprint_payload("P6-10", "UNKNOWN")


class PlannerCliTests(unittest.TestCase):
    def test_plan_text_outputs_static_blueprint(self) -> None:
        exit_code, stdout, stderr = run_cli(["plan", "--objective", "P6-10", "--profile", "lowest-cost"])

        self.assertEqual(exit_code, 0, stderr)
        self.assertIn("AgentOffice execution blueprint", stdout)
        self.assertIn("objective_id: P6-10", stdout)
        self.assertIn("selected_profile: lowest-cost", stdout)
        self.assertIn("execution_enabled: false", stdout)
        self.assertIn("context: chatgpt-manual (manual); call_enabled=false", stdout)
        self.assertIn("runtime_calls: false", stdout)
        self.assertIn("adapter_calls: false", stdout)
        self.assertIn("env_required: false", stdout)
        self.assertIn("next_actor: human_or_codex", stdout)

    def test_plan_json_is_deterministic_blueprint(self) -> None:
        exit_code, stdout, stderr = run_cli(["plan", "--objective", "P6-10", "--profile", "lowest-cost", "--json"])

        self.assertEqual(exit_code, 0, stderr)
        self.assertEqual(json.loads(stdout), execution_blueprint_payload("P6-10", "lowest-cost"))

    def test_plan_json_outputs_p6_16_blueprint(self) -> None:
        exit_code, stdout, stderr = run_cli(["plan", "--objective", "P6-16", "--profile", "lowest-cost", "--json"])

        self.assertEqual(exit_code, 0, stderr)
        self.assertEqual(json.loads(stdout), execution_blueprint_payload("P6-16", "lowest-cost"))

    def test_plan_json_outputs_p6_17_blueprint(self) -> None:
        exit_code, stdout, stderr = run_cli(["plan", "--objective", "P6-17", "--profile", "lowest-cost", "--json"])

        self.assertEqual(exit_code, 0, stderr)
        self.assertEqual(json.loads(stdout), execution_blueprint_payload("P6-17", "lowest-cost"))

    def test_plan_json_outputs_p6_18_blueprint(self) -> None:
        exit_code, stdout, stderr = run_cli(["plan", "--objective", "P6-18", "--profile", "lowest-cost", "--json"])

        self.assertEqual(exit_code, 0, stderr)
        self.assertEqual(json.loads(stdout), execution_blueprint_payload("P6-18", "lowest-cost"))

    def test_plan_text_outputs_p6_16_blueprint(self) -> None:
        exit_code, stdout, stderr = run_cli(["plan", "--objective", "P6-16", "--profile", "lowest-cost"])

        self.assertEqual(exit_code, 0, stderr)
        self.assertIn("AgentOffice execution blueprint", stdout)
        self.assertIn("objective_id: P6-16", stdout)
        self.assertIn("objective_name: Static Multi-Objective Registry", stdout)
        self.assertIn("execution_enabled: false", stdout)
        self.assertIn("runtime_calls: false", stdout)
        self.assertIn("adapter_calls: false", stdout)

    def test_plan_text_outputs_p6_17_blueprint(self) -> None:
        exit_code, stdout, stderr = run_cli(["plan", "--objective", "P6-17", "--profile", "lowest-cost"])

        self.assertEqual(exit_code, 0, stderr)
        self.assertIn("AgentOffice execution blueprint", stdout)
        self.assertIn("objective_id: P6-17", stdout)
        self.assertIn("objective_name: Static Objective Registry Extension", stdout)
        self.assertIn("execution_enabled: false", stdout)
        self.assertIn("runtime_calls: false", stdout)
        self.assertIn("adapter_calls: false", stdout)

    def test_plan_text_outputs_p6_18_blueprint(self) -> None:
        exit_code, stdout, stderr = run_cli(["plan", "--objective", "P6-18", "--profile", "lowest-cost"])

        self.assertEqual(exit_code, 0, stderr)
        self.assertIn("AgentOffice execution blueprint", stdout)
        self.assertIn("objective_id: P6-18", stdout)
        self.assertIn("objective_name: Static Objective Progression", stdout)
        self.assertIn("execution_enabled: false", stdout)
        self.assertIn("runtime_calls: false", stdout)
        self.assertIn("adapter_calls: false", stdout)

    def test_plan_unknown_objective_returns_error_without_traceback(self) -> None:
        exit_code, stdout, stderr = run_cli(["plan", "--objective", "UNKNOWN", "--profile", "lowest-cost"])

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("Unknown objective: UNKNOWN", stderr)
        self.assertNotIn("Traceback", stderr)

    def test_plan_unknown_profile_returns_error_without_traceback(self) -> None:
        exit_code, stdout, stderr = run_cli(["plan", "--objective", "P6-10", "--profile", "UNKNOWN"])

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("Unknown provider profile: UNKNOWN", stderr)
        self.assertNotIn("Traceback", stderr)

    def test_plan_does_not_read_environment(self) -> None:
        stdout = io.StringIO()
        args = argparse.Namespace(objective="P6-10", profile="lowest-cost", json=True)
        with patch.object(os, "environ", EnvGuard()), patch.object(cli.os, "environ", EnvGuard()):
            with redirect_stdout(stdout):
                exit_code = cli.cmd_plan(args)

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout.getvalue())["kind"], "execution_blueprint")

    def test_plan_does_not_write_files_or_create_ai(self) -> None:
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                exit_code, stdout, stderr = run_cli(["plan", "--objective", "P6-10", "--profile", "lowest-cost"])
            finally:
                os.chdir(original_cwd)

            self.assertEqual(exit_code, 0, stderr)
            self.assertIn("objective_id: P6-10", stdout)
            self.assertFalse((Path(tmp) / ".ai").exists())


if __name__ == "__main__":
    unittest.main()
