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
from agent_office.objectives import (
    OBJECTIVE_SPEC_REQUIRED_FIELDS,
    default_objective_phase,
    objective_detail_payload,
    objective_listing_payload,
    objective_registry_validation_payload,
    list_objective_phases,
    objective_spec_payload,
)


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


class ObjectiveSpecPayloadTests(unittest.TestCase):
    def test_default_phase_is_p6_10(self) -> None:
        self.assertEqual(default_objective_phase(), "P6-10")
        self.assertEqual(list_objective_phases(), ("P6-10",))

    def test_p6_10_objective_spec_payload_contract(self) -> None:
        payload = objective_spec_payload("P6-10")

        self.assertEqual(list(payload), list(OBJECTIVE_SPEC_REQUIRED_FIELDS))
        self.assertEqual(payload["kind"], "objective_spec")
        self.assertEqual(payload["phase"], "P6-10")
        self.assertEqual(payload["status"], "ready")
        self.assertIn("provider-safe objective spec surface", payload["objective"])
        self.assertEqual(payload["source_phases"], ["P6-06", "P6-07", "P6-08", "P6-09"])
        self.assertEqual(
            payload["cli_contract"],
            [
                "python3 -m agent_office objectives --phase P6-10",
                "python3 -m agent_office objectives --phase P6-10 --json",
            ],
        )
        self.assertEqual(payload["json_contract"]["schema_version"], 1)
        self.assertEqual(payload["json_contract"]["required_fields"], list(OBJECTIVE_SPEC_REQUIRED_FIELDS))
        self.assertIn("python3 -m agent_office profiles --name lowest-cost --plan --audit --json", payload["validation"])
        self.assertIn("python3 -m agent_office objectives --phase P6-10 --json", payload["validation"])
        self.assertEqual(
            payload["safety"],
            {
                "env_file_read": False,
                "env_vars_printed": False,
                "provider_calls": False,
                "runtime_execution": False,
                "adapter_execution": False,
                "artifact_writes": False,
            },
        )

    def test_unknown_phase_raises(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown objective phase: P6-99"):
            objective_spec_payload("P6-99")

    def test_objective_listing_payload_contract(self) -> None:
        payload = objective_listing_payload()

        self.assertEqual(list(payload), ["kind", "default_phase", "objectives"])
        self.assertEqual(payload["kind"], "objective_listing")
        self.assertEqual(payload["default_phase"], "P6-10")
        self.assertEqual(
            payload["objectives"],
            [
                {
                    "phase": "P6-10",
                    "title": "Objective Spec CLI Contract",
                    "status": "ready",
                    "objective": objective_spec_payload("P6-10")["objective"],
                }
            ],
        )

    def test_objective_detail_payload_uses_objective_id(self) -> None:
        self.assertEqual(objective_detail_payload("P6-10"), objective_spec_payload("P6-10"))
        with self.assertRaisesRegex(ValueError, "Unknown objective: UNKNOWN"):
            objective_detail_payload("UNKNOWN")

    def test_objective_registry_validation_payload_contract(self) -> None:
        payload = objective_registry_validation_payload()

        self.assertEqual(
            list(payload),
            ["kind", "default_phase", "objectives_checked", "checks", "errors", "status"],
        )
        self.assertEqual(payload["kind"], "objective_registry_validation")
        self.assertEqual(payload["default_phase"], "P6-10")
        self.assertEqual(payload["objectives_checked"], 1)
        self.assertEqual([check["name"] for check in payload["checks"]], [
            "objective_ids_unique",
            "required_fields_present",
            "output_order_stable",
            "json_serializable",
            "static_safe_registry",
        ])
        self.assertEqual([check["status"] for check in payload["checks"]], ["pass", "pass", "pass", "pass", "pass"])
        self.assertEqual(payload["errors"], [])
        self.assertEqual(payload["status"], "pass")
        json.dumps(payload)


class ObjectiveSpecCliTests(unittest.TestCase):
    def test_objectives_text_outputs_p6_10_contract(self) -> None:
        exit_code, stdout, stderr = run_cli(["objectives", "--phase", "P6-10"])

        self.assertEqual(exit_code, 0, stderr)
        self.assertIn("AgentOffice objective spec", stdout)
        self.assertIn("phase: P6-10", stdout)
        self.assertIn("cli_contract:", stdout)
        self.assertIn("json_contract:", stdout)
        self.assertIn("python3 -m agent_office objectives --phase P6-10 --json", stdout)
        self.assertIn("provider_calls: false", stdout)

    def test_objectives_json_is_machine_readable_contract(self) -> None:
        exit_code, stdout, stderr = run_cli(["objectives", "--phase", "P6-10", "--json"])

        self.assertEqual(exit_code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload, objective_spec_payload("P6-10"))

    def test_objectives_show_text_outputs_single_objective(self) -> None:
        exit_code, stdout, stderr = run_cli(["objectives", "--show", "P6-10"])

        self.assertEqual(exit_code, 0, stderr)
        self.assertIn("AgentOffice objective spec", stdout)
        self.assertIn("phase: P6-10", stdout)
        self.assertIn("title: Objective Spec CLI Contract", stdout)
        self.assertIn("provider_calls: false", stdout)

    def test_objectives_show_json_is_machine_readable_contract(self) -> None:
        exit_code, stdout, stderr = run_cli(["objectives", "--show", "P6-10", "--json"])

        self.assertEqual(exit_code, 0, stderr)
        self.assertEqual(json.loads(stdout), objective_detail_payload("P6-10"))

    def test_objectives_defaults_to_p6_10(self) -> None:
        exit_code, stdout, stderr = run_cli(["objectives", "--json"])

        self.assertEqual(exit_code, 0, stderr)
        self.assertEqual(json.loads(stdout)["phase"], "P6-10")

    def test_objectives_unknown_phase_returns_error(self) -> None:
        exit_code, stdout, stderr = run_cli(["objectives", "--phase", "P6-99"])

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("Unknown objective phase: P6-99", stderr)

    def test_objectives_unknown_show_returns_error_without_traceback(self) -> None:
        exit_code, stdout, stderr = run_cli(["objectives", "--show", "UNKNOWN"])

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("Unknown objective: UNKNOWN", stderr)
        self.assertNotIn("Traceback", stderr)

    def test_objectives_validate_text_outputs_registry_checks(self) -> None:
        exit_code, stdout, stderr = run_cli(["objectives", "--validate"])

        self.assertEqual(exit_code, 0, stderr)
        self.assertIn("Objective registry validation", stdout)
        self.assertIn("status: pass", stdout)
        self.assertIn("objective_ids_unique: pass", stdout)
        self.assertIn("provider/runtime/adapter execution: not triggered", stdout)

    def test_objectives_validate_json_is_machine_readable_contract(self) -> None:
        exit_code, stdout, stderr = run_cli(["objectives", "--validate", "--json"])

        self.assertEqual(exit_code, 0, stderr)
        self.assertEqual(json.loads(stdout), objective_registry_validation_payload())

    def test_objectives_list_text_outputs_defined_objectives(self) -> None:
        exit_code, stdout, stderr = run_cli(["objectives", "--list"])

        self.assertEqual(exit_code, 0, stderr)
        self.assertIn("AgentOffice objectives", stdout)
        self.assertIn("default_phase: P6-10", stdout)
        self.assertIn("  - phase: P6-10", stdout)
        self.assertIn("title: Objective Spec CLI Contract", stdout)
        self.assertIn("status: ready", stdout)
        self.assertIn("provider-safe objective spec surface", stdout)

    def test_objectives_list_json_is_machine_readable_contract(self) -> None:
        exit_code, stdout, stderr = run_cli(["objectives", "--list", "--json"])

        self.assertEqual(exit_code, 0, stderr)
        self.assertEqual(json.loads(stdout), objective_listing_payload())

    def test_objectives_does_not_read_environment(self) -> None:
        stdout = io.StringIO()
        args = argparse.Namespace(phase="P6-10", json=True)
        with patch.object(os, "environ", EnvGuard()), patch.object(cli.os, "environ", EnvGuard()):
            with redirect_stdout(stdout):
                exit_code = cli.cmd_objectives(args)

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout.getvalue())["phase"], "P6-10")

    def test_objectives_validate_does_not_read_environment(self) -> None:
        stdout = io.StringIO()
        args = argparse.Namespace(phase=None, show=None, json=True, list=False, validate=True)
        with patch.object(os, "environ", EnvGuard()), patch.object(cli.os, "environ", EnvGuard()):
            with redirect_stdout(stdout):
                exit_code = cli.cmd_objectives(args)

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout.getvalue())["kind"], "objective_registry_validation")

    def test_objectives_list_does_not_read_environment(self) -> None:
        stdout = io.StringIO()
        args = argparse.Namespace(phase=None, json=True, list=True)
        with patch.object(os, "environ", EnvGuard()), patch.object(cli.os, "environ", EnvGuard()):
            with redirect_stdout(stdout):
                exit_code = cli.cmd_objectives(args)

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout.getvalue())["kind"], "objective_listing")

    def test_objectives_does_not_write_files_or_create_ai(self) -> None:
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                exit_code, stdout, stderr = run_cli(["objectives", "--phase", "P6-10"])
            finally:
                os.chdir(original_cwd)

            self.assertEqual(exit_code, 0, stderr)
            self.assertIn("phase: P6-10", stdout)
            self.assertFalse((Path(tmp) / ".ai").exists())


if __name__ == "__main__":
    unittest.main()
