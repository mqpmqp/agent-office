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

    def test_profiles_plan_requires_name(self) -> None:
        exit_code, stdout, stderr = run_cli(["profiles", "--plan"])

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("--plan requires --name", stderr)

    def test_profiles_plan_text_shows_static_preview(self) -> None:
        exit_code, stdout, stderr = run_cli(["profiles", "--name", "lowest-cost", "--plan"])

        self.assertEqual(exit_code, 0, stderr)
        self.assertIn("AgentOffice profile plan preview", stdout)
        self.assertIn("profile: lowest-cost", stdout)
        self.assertIn("default_profile: lowest-cost", stdout)
        self.assertIn("is_default: true", stdout)
        self.assertIn("execution_enabled: false", stdout)
        self.assertIn("provider_calls: false", stdout)
        self.assertIn("artifact_writes: false", stdout)
        self.assertIn("context: chatgpt-manual (manual)", stdout)
        self.assertIn("implement: codex (local-cli)", stdout)
        self.assertIn("review: chatgpt-manual (manual)", stdout)
        self.assertIn("judge: chatgpt-manual (manual)", stdout)

    def test_profiles_plan_json_is_parseable_and_safe_metadata_only(self) -> None:
        exit_code, stdout, stderr = run_cli(["profiles", "--name", "lowest-cost", "--plan", "--json"])

        self.assertEqual(exit_code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(
            payload,
            {
                "profile": "lowest-cost",
                "default_profile": "lowest-cost",
                "is_default": True,
                "execution_enabled": False,
                "provider_calls": False,
                "artifact_writes": False,
                "roles": [
                    {"role": "context", "provider": "chatgpt-manual", "execution": "manual"},
                    {"role": "implement", "provider": "codex", "execution": "local-cli"},
                    {"role": "review", "provider": "chatgpt-manual", "execution": "manual"},
                    {"role": "judge", "provider": "chatgpt-manual", "execution": "manual"},
                ],
            },
        )
        self.assert_no_forbidden_plan_keys(payload)

    def test_profiles_plan_json_uses_provider_execution_categories(self) -> None:
        exit_code, stdout, stderr = run_cli(["profiles", "--name", "multi-vendor", "--plan", "--json"])

        self.assertEqual(exit_code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["profile"], "multi-vendor")
        self.assertFalse(payload["is_default"])
        self.assertEqual(
            payload["roles"],
            [
                {"role": "context", "provider": "gemini", "execution": "optional-provider"},
                {"role": "implement", "provider": "codex", "execution": "local-cli"},
                {"role": "review", "provider": "grok", "execution": "optional-provider"},
                {"role": "judge", "provider": "claude", "execution": "optional-provider"},
            ],
        )

    def test_profiles_plan_does_not_read_environment(self) -> None:
        stdout = io.StringIO()
        args = argparse.Namespace(name="lowest-cost", json=True, plan=True)
        with patch.object(os, "environ", EnvGuard()), patch.object(cli.os, "environ", EnvGuard()):
            with redirect_stdout(stdout):
                exit_code = cli.cmd_profiles(args)

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout.getvalue())["profile"], "lowest-cost")

    def test_profiles_plan_does_not_write_files_or_create_ai(self) -> None:
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                exit_code, stdout, stderr = run_cli(["profiles", "--name", "lowest-cost", "--plan"])
            finally:
                os.chdir(original_cwd)

            self.assertEqual(exit_code, 0, stderr)
            self.assertIn("profile: lowest-cost", stdout)
            self.assertFalse((Path(tmp) / ".ai").exists())

    def test_profiles_command_does_not_read_environment(self) -> None:
        stdout = io.StringIO()
        with patch.object(os, "environ", EnvGuard()), patch.object(cli.os, "environ", EnvGuard()):
            with redirect_stdout(stdout):
                exit_code = cli.cmd_profiles(argparse.Namespace(name="lowest-cost", json=True))

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout.getvalue())["profiles"][0]["name"], "lowest-cost")

    def assert_no_forbidden_plan_keys(self, value: object) -> None:
        forbidden = ("secret", "token", "password", "credential", "env", "environment", "runtime", "api_key", ".env")
        keys: list[str] = []

        def collect_keys(item: object) -> None:
            if isinstance(item, dict):
                for key, child in item.items():
                    keys.append(str(key))
                    collect_keys(child)
            elif isinstance(item, list):
                for child in item:
                    collect_keys(child)

        collect_keys(value)
        for key in keys:
            self.assertFalse(any(term in key.lower() for term in forbidden), key)


if __name__ == "__main__":
    unittest.main()
