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

from agent_office import cli, doctor
from agent_office.doctor import collect_doctor, collect_profile_plan_audit, format_profile_plan_audit


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


def run_doctor_module(argv: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = doctor.main(argv)
    return exit_code, stdout.getvalue(), stderr.getvalue()


class DoctorProfilesTests(unittest.TestCase):
    def test_collect_profile_plan_audit_contract(self) -> None:
        audit = collect_profile_plan_audit()

        self.assertEqual(audit["status"], "ok")
        self.assertEqual(audit["default_profile"], "lowest-cost")
        self.assertEqual(audit["available_profiles"], ["lowest-cost", "mock-ci", "multi-vendor"])
        self.assertEqual(audit["profiles_checked"], 3)
        self.assertFalse(audit["execution_enabled"])
        self.assertFalse(audit["provider_calls"])
        self.assertFalse(audit["artifact_writes"])
        self.assertEqual(audit["errors"], [])
        self.assertEqual([row["profile"] for row in audit["rows"]], ["lowest-cost", "mock-ci", "multi-vendor"])
        self.assertEqual([role["role"] for role in audit["rows"][0]["roles"]], ["context", "implement", "review", "judge"])

    def test_format_profile_plan_audit_table(self) -> None:
        table = format_profile_plan_audit(collect_profile_plan_audit())

        self.assertIn("profile | default | execution_enabled | provider_calls | artifact_writes | roles | status", table)
        self.assertIn("lowest-cost | true | false | false | false", table)
        self.assertIn("context:chatgpt-manual(manual)", table)
        self.assertIn("multi-vendor | false | false | false | false", table)

    def test_cmd_doctor_profiles_json_is_static_and_safe(self) -> None:
        stdout = io.StringIO()
        args = argparse.Namespace(adapter=None, adapters=False, profiles=True, json=True)
        with patch.object(os, "environ", EnvGuard()), patch.object(cli.os, "environ", EnvGuard()), patch.object(doctor.os, "environ", EnvGuard()):
            with redirect_stdout(stdout):
                exit_code = cli.cmd_doctor(args)

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["available_profiles"], ["lowest-cost", "mock-ci", "multi-vendor"])
        self.assertEqual([row["profile"] for row in payload["rows"]], ["lowest-cost", "mock-ci", "multi-vendor"])
        self.assertFalse(payload["provider_calls"])

    def test_cli_doctor_profiles_table_does_not_create_ai(self) -> None:
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                exit_code, stdout, stderr = run_cli(["doctor", "--profiles"])
            finally:
                os.chdir(original_cwd)

            self.assertEqual(exit_code, 0, stderr)
            self.assertIn("mock-ci | false | false | false | false", stdout)
            self.assertFalse((Path(tmp) / ".ai").exists())

    def test_module_doctor_profiles_matches_root_cli_contract(self) -> None:
        exit_code, stdout, stderr = run_doctor_module(["--profiles"])

        self.assertEqual(exit_code, 0, stderr)
        self.assertIn("profile | default | execution_enabled | provider_calls | artifact_writes | roles | status", stdout)
        self.assertIn("multi-vendor", stdout)

    def test_collect_doctor_includes_profile_plan_audit(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            report = collect_doctor(Path.cwd())

        self.assertEqual(report["profiles"]["status"], "ok")
        self.assertEqual(report["profiles"]["profiles_checked"], 3)
        self.assertFalse(report["profiles"]["provider_calls"])


