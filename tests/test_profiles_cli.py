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

    def test_profiles_plan_unknown_name_returns_error(self) -> None:
        exit_code, stdout, stderr = run_cli(["profiles", "--name", "missing", "--plan"])

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("Unknown provider profile: missing", stderr)

    def test_profiles_plan_without_name_shows_all_static_previews(self) -> None:
        exit_code, stdout, stderr = run_cli(["profiles", "--plan"])

        self.assertEqual(exit_code, 0, stderr)
        self.assertIn("AgentOffice profile plan previews", stdout)
        self.assertIn("default_profile: lowest-cost", stdout)
        self.assertIn("available_profiles: lowest-cost, mock-ci, multi-vendor", stdout)
        self.assertEqual(stdout.count("selected_profile:"), 3)
        self.assertIn("selected_profile: lowest-cost", stdout)
        self.assertIn("selected_profile: mock-ci", stdout)
        self.assertIn("selected_profile: multi-vendor", stdout)

    def test_profiles_plan_text_shows_static_preview(self) -> None:
        exit_code, stdout, stderr = run_cli(["profiles", "--name", "lowest-cost", "--plan"])

        self.assertEqual(exit_code, 0, stderr)
        self.assertIn("AgentOffice profile plan preview", stdout)
        self.assertIn("selected_profile: lowest-cost", stdout)
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
                "selected_profile": "lowest-cost",
                "default_profile": "lowest-cost",
                "is_default": True,
                "execution_enabled": False,
                "provider_calls": False,
                "artifact_writes": False,
                "roles": [
                    {"role": "context", "provider": "chatgpt-manual", "execution_category": "manual"},
                    {"role": "implement", "provider": "codex", "execution_category": "local-cli"},
                    {"role": "review", "provider": "chatgpt-manual", "execution_category": "manual"},
                    {"role": "judge", "provider": "chatgpt-manual", "execution_category": "manual"},
                ],
            },
        )
        self.assert_no_forbidden_plan_keys(payload)

    def test_profiles_plan_audit_text_shows_contract_status(self) -> None:
        exit_code, stdout, stderr = run_cli(["profiles", "--name", "lowest-cost", "--plan", "--audit"])

        self.assertEqual(exit_code, 0, stderr)
        self.assertIn("Profile plan contract audit", stdout)
        self.assertIn("selected_profile: lowest-cost", stdout)
        self.assertIn("default_profile: lowest-cost", stdout)
        self.assertIn("is_default: true", stdout)
        self.assertIn("execution_enabled: false", stdout)
        self.assertIn("provider_calls_count: 0", stdout)
        self.assertIn("contract_status: pass", stdout)
        self.assertIn("selected_profile_present: pass", stdout)
        self.assertIn("provider_calls_empty: pass", stdout)
        self.assertIn("provider/runtime/adapter execution: not triggered", stdout)

    def test_profiles_plan_audit_json_is_machine_readable_contract(self) -> None:
        exit_code, stdout, stderr = run_cli(["profiles", "--name", "lowest-cost", "--plan", "--audit", "--json"])

        self.assertEqual(exit_code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["kind"], "profile_plan_contract_audit")
        self.assertEqual(payload["selected_profile"], "lowest-cost")
        self.assertEqual(payload["default_profile"], "lowest-cost")
        self.assertTrue(payload["is_default"])
        self.assertFalse(payload["execution_enabled"])
        self.assertEqual(payload["provider_calls"], [])
        self.assertEqual(payload["contract"]["schema_version"], 1)
        self.assertIn("dotenv_read", payload["contract"]["forbidden_runtime_behavior"])
        self.assertEqual([check["status"] for check in payload["checks"]], ["pass", "pass", "pass", "pass", "pass"])
        self.assertEqual(payload["status"], "pass")

    def test_profiles_plan_audit_without_name_reports_all_profiles(self) -> None:
        exit_code, stdout, stderr = run_cli(["profiles", "--plan", "--audit", "--json"])

        self.assertEqual(exit_code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["kind"], "profile_plan_contract_audits")
        self.assertEqual(payload["default_profile"], "lowest-cost")
        self.assertEqual(payload["available_profiles"], ["lowest-cost", "mock-ci", "multi-vendor"])
        self.assertEqual(payload["provider_calls"], [])
        self.assertEqual(payload["status"], "pass")
        self.assertEqual(
            [audit["selected_profile"] for audit in payload["audits"]],
            ["lowest-cost", "mock-ci", "multi-vendor"],
        )

    def test_profiles_plan_json_without_name_lists_all_static_previews(self) -> None:
        exit_code, stdout, stderr = run_cli(["profiles", "--plan", "--json"])

        self.assertEqual(exit_code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(
            list(payload),
            ["default_profile", "available_profiles", "execution_enabled", "provider_calls", "artifact_writes", "plans"],
        )
        self.assertEqual(payload["default_profile"], "lowest-cost")
        self.assertEqual(payload["available_profiles"], ["lowest-cost", "mock-ci", "multi-vendor"])
        self.assertFalse(payload["execution_enabled"])
        self.assertFalse(payload["provider_calls"])
        self.assertFalse(payload["artifact_writes"])
        self.assertEqual(
            [plan["selected_profile"] for plan in payload["plans"]],
            ["lowest-cost", "mock-ci", "multi-vendor"],
        )
        self.assertEqual(payload["plans"][1]["roles"][0], {"role": "context", "provider": "mock", "execution_category": "mock"})
        self.assert_no_forbidden_plan_keys(payload)

    def test_profiles_plan_json_uses_provider_execution_categories(self) -> None:
        exit_code, stdout, stderr = run_cli(["profiles", "--name", "multi-vendor", "--plan", "--json"])

        self.assertEqual(exit_code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["selected_profile"], "multi-vendor")
        self.assertFalse(payload["is_default"])
        self.assertEqual(
            payload["roles"],
            [
                {"role": "context", "provider": "gemini", "execution_category": "optional-provider"},
                {"role": "implement", "provider": "codex", "execution_category": "local-cli"},
                {"role": "review", "provider": "grok", "execution_category": "optional-provider"},
                {"role": "judge", "provider": "claude", "execution_category": "optional-provider"},
            ],
        )

    def test_profiles_plan_does_not_read_environment(self) -> None:
        stdout = io.StringIO()
        args = argparse.Namespace(name="lowest-cost", json=True, plan=True)
        with patch.object(os, "environ", EnvGuard()), patch.object(cli.os, "environ", EnvGuard()):
            with redirect_stdout(stdout):
                exit_code = cli.cmd_profiles(args)

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout.getvalue())["selected_profile"], "lowest-cost")

    def test_profiles_plan_audit_does_not_read_environment(self) -> None:
        stdout = io.StringIO()
        args = argparse.Namespace(name="lowest-cost", json=True, plan=True, audit=True)
        with patch.object(os, "environ", EnvGuard()), patch.object(cli.os, "environ", EnvGuard()):
            with redirect_stdout(stdout):
                exit_code = cli.cmd_profiles(args)

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["selected_profile"], "lowest-cost")
        self.assertEqual(payload["provider_calls"], [])
        self.assertEqual(payload["status"], "pass")

    def test_profiles_plan_all_does_not_read_environment(self) -> None:
        stdout = io.StringIO()
        args = argparse.Namespace(name=None, json=True, plan=True)
        with patch.object(os, "environ", EnvGuard()), patch.object(cli.os, "environ", EnvGuard()):
            with redirect_stdout(stdout):
                exit_code = cli.cmd_profiles(args)

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout.getvalue())["plans"][0]["selected_profile"], "lowest-cost")

    def test_profiles_plan_does_not_write_files_or_create_ai(self) -> None:
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                exit_code, stdout, stderr = run_cli(["profiles", "--name", "lowest-cost", "--plan"])
            finally:
                os.chdir(original_cwd)

            self.assertEqual(exit_code, 0, stderr)
            self.assertIn("selected_profile: lowest-cost", stdout)
            self.assertFalse((Path(tmp) / ".ai").exists())

    def test_profiles_plan_all_does_not_write_files_or_create_ai(self) -> None:
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                exit_code, stdout, stderr = run_cli(["profiles", "--plan"])
            finally:
                os.chdir(original_cwd)

            self.assertEqual(exit_code, 0, stderr)
            self.assertIn("AgentOffice profile plan previews", stdout)
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
