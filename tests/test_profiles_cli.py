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


class ProfilesCliTests(unittest.TestCase):
    def test_profiles_lists_built_ins_and_default(self) -> None:
        exit_code, stdout, stderr = run_cli(["profiles"])

        self.assertEqual(exit_code, 0, stderr)
        self.assertIn("default: lowest-cost", stdout)
        self.assertIn("available: lowest-cost, mock-ci, multi-vendor", stdout)
        self.assertIn("context: chatgpt-manual", stdout)
        self.assertIn("implement: codex", stdout)
        self.assertIn("review: chatgpt-manual", stdout)
        self.assertIn("judge: chatgpt-manual", stdout)

    def test_profiles_name_shows_selected_profile_roles(self) -> None:
        exit_code, stdout, stderr = run_cli(["profiles", "--name", "multi-vendor"])

        self.assertEqual(exit_code, 0, stderr)
        self.assertIn("default: lowest-cost", stdout)
        self.assertIn("available: lowest-cost, mock-ci, multi-vendor", stdout)
        self.assertIn("multi-vendor", stdout)
        self.assertIn("context: gemini", stdout)
        self.assertIn("implement: codex", stdout)
        self.assertIn("review: grok", stdout)
        self.assertIn("judge: claude", stdout)

    def test_profiles_json_is_parseable_and_safe_metadata_only(self) -> None:
        exit_code, stdout, stderr = run_cli(["profiles", "--json"])

        self.assertEqual(exit_code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["default_profile"], "lowest-cost")
        self.assertEqual(payload["available_profiles"], ["lowest-cost", "mock-ci", "multi-vendor"])
        self.assertEqual(
            payload["profiles"][0],
            {
                "name": "lowest-cost",
                "roles": {
                    "context": "chatgpt-manual",
                    "implement": "codex",
                    "review": "chatgpt-manual",
                    "judge": "chatgpt-manual",
                },
            },
        )
        self.assertNotIn("secret", stdout.lower())
        self.assertNotIn("credential", stdout.lower())
        self.assertNotIn("env", stdout.lower())
        self.assertNotIn("runtime", stdout.lower())

    def test_profiles_json_name_limits_profile_details(self) -> None:
        exit_code, stdout, stderr = run_cli(["profiles", "--name", "mock-ci", "--json"])

        self.assertEqual(exit_code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual([profile["name"] for profile in payload["profiles"]], ["mock-ci"])
        self.assertEqual(set(payload["profiles"][0]["roles"].values()), {"mock"})

    def test_profiles_unknown_name_returns_error(self) -> None:
        exit_code, stdout, stderr = run_cli(["profiles", "--name", "missing"])

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("Unknown provider profile: missing", stderr)

    def test_profiles_command_does_not_read_environment(self) -> None:
        stdout = io.StringIO()
        with patch.object(os, "environ", EnvGuard()), patch.object(cli.os, "environ", EnvGuard()):
            with redirect_stdout(stdout):
                exit_code = cli.cmd_profiles(argparse.Namespace(name="lowest-cost", json=True))

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout.getvalue())["profiles"][0]["name"], "lowest-cost")


if __name__ == "__main__":
    unittest.main()
