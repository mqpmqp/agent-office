from __future__ import annotations

import argparse
import io
import json
import os
import unittest
from collections.abc import MutableMapping
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from agent_office import cli
from agent_office import framework_types
from agent_office.framework_status import build_framework_status


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


EXPECTED_KEYS = (
    "schema_version",
    "product",
    "architecture_target",
    "mode",
    "runtime_model",
    "provider_calls_enabled",
    "env_reads_allowed",
    "trading_bot_scope",
    "core_objects",
    "next_slices",
    "runtime_trunk",
)

EXPECTED_CORE_OBJECTS = [
    "workspace",
    "goal",
    "task_graph",
    "role",
    "agent",
    "provider",
    "packet",
    "run",
    "runtime_event",
    "actor_result",
    "evidence_bundle",
    "review",
    "gate_decision",
    "archive",
]

EXPECTED_NEXT_SLICES = [
    "workspace_store",
    "runtime_event_log",
    "task_graph_kernel",
    "packet_result_intake",
    "review_gate_v2",
]


class FrameworkStatusSchemaTest(unittest.TestCase):
    def test_schema_keys_and_order_are_stable(self) -> None:
        status = build_framework_status()
        self.assertEqual(tuple(status.keys()), EXPECTED_KEYS)

    def test_schema_values_are_stable(self) -> None:
        status = build_framework_status()
        self.assertEqual(status["schema_version"], 1)
        self.assertEqual(status["product"], "AgentOffice")
        self.assertEqual(status["architecture_target"], "local-first multi-agent office runtime")
        self.assertEqual(status["mode"], "framework_reset")
        self.assertEqual(status["runtime_model"], "deterministic_cli_tick_first")
        self.assertEqual(status["core_objects"], EXPECTED_CORE_OBJECTS)
        self.assertEqual(status["next_slices"], EXPECTED_NEXT_SLICES)
        self.assertEqual(status["runtime_trunk"]["status"], "available")
        self.assertEqual(status["runtime_trunk"]["worker_adapters"], ["local_echo_worker"])
        self.assertIs(status["runtime_trunk"]["provider_calls_enabled"], False)

    def test_safety_invariants_are_false(self) -> None:
        status = build_framework_status()
        self.assertIs(status["provider_calls_enabled"], False)
        self.assertIs(status["env_reads_allowed"], False)
        self.assertIs(status["trading_bot_scope"], False)

    def test_status_is_deterministic(self) -> None:
        self.assertEqual(build_framework_status(), build_framework_status())


class FrameworkStatusCliTest(unittest.TestCase):
    def test_json_output_matches_contract(self) -> None:
        exit_code, stdout, stderr = run_cli(["framework-status", "--json"])
        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertEqual(tuple(payload.keys()), EXPECTED_KEYS)
        self.assertIs(payload["provider_calls_enabled"], False)
        self.assertIs(payload["env_reads_allowed"], False)
        self.assertIs(payload["trading_bot_scope"], False)
        self.assertEqual(payload["core_objects"], EXPECTED_CORE_OBJECTS)
        self.assertEqual(payload["next_slices"], EXPECTED_NEXT_SLICES)
        self.assertEqual(payload["runtime_trunk"]["status"], "available")

    def test_text_output_names_architecture_target(self) -> None:
        exit_code, stdout, stderr = run_cli(["framework-status"])
        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("local-first multi-agent office runtime", stdout)
        self.assertIn("framework_reset", stdout)
        self.assertIn("provider calls enabled: False", stdout)
        self.assertIn("runtime trunk: available", stdout)

    def test_command_does_not_read_environment(self) -> None:
        for json_flag in (True, False):
            stdout = io.StringIO()
            args = argparse.Namespace(json=json_flag)
            with patch.object(os, "environ", EnvGuard()), patch.object(cli.os, "environ", EnvGuard()):
                with redirect_stdout(stdout):
                    exit_code = cli.cmd_framework_status(args)
            self.assertEqual(exit_code, 0)
            self.assertTrue(stdout.getvalue())


class FrameworkTypesTest(unittest.TestCase):
    def test_state_machines_cover_documented_states(self) -> None:
        self.assertIn("goal.created", framework_types.GOAL_STATES)
        self.assertIn("goal.archived", framework_types.GOAL_STATES)
        self.assertIn("task.created", framework_types.TASK_STATES)
        self.assertIn("task.skipped", framework_types.TASK_STATES)
        self.assertTrue(framework_types.is_valid_goal_state("goal.gate_pending"))
        self.assertFalse(framework_types.is_valid_goal_state("goal.exploded"))
        self.assertTrue(framework_types.is_valid_task_state("task.result_received"))
        self.assertFalse(framework_types.is_valid_task_state("task.done"))

    def test_roles_are_vendor_free(self) -> None:
        for role in framework_types.STANDARD_ROLES:
            self.assertTrue(framework_types.is_valid_role(role))
            for provider in ("codex", "claude", "gemini", "grok"):
                self.assertNotIn(provider, role)

    def test_review_and_gate_vocabulary(self) -> None:
        self.assertEqual(framework_types.REVIEW_VERDICTS, ("pass", "conditional_pass", "fail"))
        self.assertEqual(
            framework_types.GATE_DECISIONS,
            ("allow_merge", "block_merge", "require_fix", "require_human"),
        )


if __name__ == "__main__":
    unittest.main()
