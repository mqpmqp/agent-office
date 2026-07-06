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
from agent_office.workspace_store import create_run, init_workspace


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


def create_workspace_run(root: str) -> None:
    init_workspace(Path(root), "ws-demo")
    create_run(Path(root), "ws-demo", "run-demo")


class RuntimeEventCliTest(unittest.TestCase):
    def test_append_first_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            create_workspace_run(tmp)

            exit_code, stdout, stderr = run_cli([
                "runtime-event",
                "append",
                "--workspace-id",
                "ws-demo",
                "--run-id",
                "run-demo",
                "--event-type",
                "run.created",
                "--actor",
                "runtime",
                "--root",
                tmp,
                "--json",
            ])

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            payload = json.loads(stdout)
            self.assertEqual(payload["event_id"], "evt_000001")
            self.assertEqual(payload["task_id"], None)
            self.assertEqual(payload["payload"], {})
            self.assertEqual(payload["evidence_refs"], [])

    def test_append_second_event_has_stable_sequence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            create_workspace_run(tmp)
            run_cli(["runtime-event", "append", "--workspace-id", "ws-demo", "--run-id", "run-demo", "--event-type", "run.created", "--actor", "runtime", "--root", tmp, "--json"])

            exit_code, stdout, stderr = run_cli(["runtime-event", "append", "--workspace-id", "ws-demo", "--run-id", "run-demo", "--event-type", "run.ready", "--actor", "runtime", "--root", tmp, "--json"])

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(json.loads(stdout)["event_id"], "evt_000002")

    def test_list_events_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            create_workspace_run(tmp)
            run_cli(["runtime-event", "append", "--workspace-id", "ws-demo", "--run-id", "run-demo", "--event-type", "run.created", "--actor", "runtime", "--root", tmp, "--json"])
            run_cli(["runtime-event", "append", "--workspace-id", "ws-demo", "--run-id", "run-demo", "--event-type", "run.ready", "--actor", "runtime", "--root", tmp, "--json"])

            exit_code, stdout, stderr = run_cli(["runtime-event", "list", "--workspace-id", "ws-demo", "--run-id", "run-demo", "--root", tmp, "--json"])

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            payload = json.loads(stdout)
            self.assertEqual(payload["kind"], "agentoffice.runtime_event_list")
            self.assertEqual([event["event_id"] for event in payload["events"]], ["evt_000001", "evt_000002"])

    def test_missing_workspace_or_run_fails_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            exit_code, stdout, stderr = run_cli(["runtime-event", "append", "--workspace-id", "missing", "--run-id", "run-demo", "--event-type", "run.created", "--actor", "runtime", "--root", tmp])
            self.assertEqual(exit_code, 2)
            self.assertEqual(stdout, "")
            self.assertIn("Missing file", stderr)
            self.assertNotIn("Traceback", stderr)

            init_workspace(Path(tmp), "ws-demo")
            exit_code, stdout, stderr = run_cli(["runtime-event", "list", "--workspace-id", "ws-demo", "--run-id", "missing", "--root", tmp])
            self.assertEqual(exit_code, 2)
            self.assertEqual(stdout, "")
            self.assertIn("Run not found", stderr)
            self.assertNotIn("Traceback", stderr)

    def test_invalid_event_type_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            create_workspace_run(tmp)
            exit_code, stdout, stderr = run_cli(["runtime-event", "append", "--workspace-id", "ws-demo", "--run-id", "run-demo", "--event-type", "../x", "--actor", "runtime", "--root", tmp])

            self.assertEqual(exit_code, 2)
            self.assertEqual(stdout, "")
            self.assertIn("Invalid event_type", stderr)
            self.assertNotIn("Traceback", stderr)

    def test_invalid_workspace_or_run_id_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for args, expected in (
                (["runtime-event", "list", "--workspace-id", "../x", "--run-id", "run-demo", "--root", tmp], "Invalid workspace_id"),
                (["runtime-event", "list", "--workspace-id", "ws-demo", "--run-id", "x/y", "--root", tmp], "Invalid run_id"),
            ):
                with self.subTest(expected=expected):
                    exit_code, stdout, stderr = run_cli(args)
                    self.assertEqual(exit_code, 2)
                    self.assertEqual(stdout, "")
                    self.assertIn(expected, stderr)
                    self.assertNotIn("Traceback", stderr)

    def test_append_only_behavior_preserves_existing_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            create_workspace_run(tmp)
            event_file = Path(tmp, ".ai", "workspaces", "ws-demo", "runs", "run-demo", "events.jsonl")
            run_cli(["runtime-event", "append", "--workspace-id", "ws-demo", "--run-id", "run-demo", "--event-type", "run.created", "--actor", "runtime", "--root", tmp, "--json"])
            first_line = event_file.read_text(encoding="utf-8").splitlines()[0]

            run_cli(["runtime-event", "append", "--workspace-id", "ws-demo", "--run-id", "run-demo", "--event-type", "run.ready", "--actor", "runtime", "--root", tmp, "--json"])

            lines = event_file.read_text(encoding="utf-8").splitlines()
            self.assertEqual(lines[0], first_line)
            self.assertEqual(len(lines), 2)

    def test_runtime_event_commands_do_not_read_environment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            create_workspace_run(tmp)
            commands = (
                argparse.Namespace(runtime_event_action="append", workspace_id="ws-demo", run_id="run-demo", event_type="run.created", actor="runtime", root=tmp, json=True),
                argparse.Namespace(runtime_event_action="list", workspace_id="ws-demo", run_id="run-demo", root=tmp, json=True),
            )
            with patch.object(os, "environ", EnvGuard()), patch.object(cli.os, "environ", EnvGuard()):
                for args in commands:
                    stdout = io.StringIO()
                    with redirect_stdout(stdout):
                        self.assertEqual(cli.cmd_runtime_event(args), 0)
                    self.assertTrue(stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
