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


class WorkspaceStoreCliTest(unittest.TestCase):
    def test_init_workspace_json_creates_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            exit_code, stdout, stderr = run_cli([
                "workspace",
                "init",
                "--workspace-id",
                "ws-demo",
                "--root",
                tmp,
                "--json",
            ])

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            payload = json.loads(stdout)
            self.assertEqual(
                payload,
                {
                    "schema_version": 1,
                    "kind": "agentoffice.workspace",
                    "workspace_id": "ws-demo",
                    "status": "active",
                    "runs_dir": "runs",
                },
            )
            self.assertTrue(Path(tmp, ".ai", "workspaces", "ws-demo", "workspace.json").is_file())

    def test_inspect_workspace_json_reads_existing_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_cli(["workspace", "init", "--workspace-id", "ws-demo", "--root", tmp, "--json"])

            exit_code, stdout, stderr = run_cli([
                "workspace",
                "inspect",
                "--workspace-id",
                "ws-demo",
                "--root",
                tmp,
                "--json",
            ])

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(json.loads(stdout)["kind"], "agentoffice.workspace")

    def test_run_create_json_creates_run_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_cli(["workspace", "init", "--workspace-id", "ws-demo", "--root", tmp, "--json"])

            exit_code, stdout, stderr = run_cli([
                "workspace",
                "run-create",
                "--workspace-id",
                "ws-demo",
                "--run-id",
                "run-demo",
                "--root",
                tmp,
                "--json",
            ])

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            payload = json.loads(stdout)
            self.assertEqual(payload["kind"], "agentoffice.run")
            self.assertEqual(payload["workspace_id"], "ws-demo")
            self.assertEqual(payload["run_id"], "run-demo")
            run_root = Path(tmp, ".ai", "workspaces", "ws-demo", "runs", "run-demo")
            self.assertTrue(Path(run_root, "run.json").is_file())
            self.assertTrue(Path(run_root, "packets").is_dir())
            self.assertTrue(Path(run_root, "results").is_dir())
            self.assertTrue(Path(run_root, "evidence").is_dir())

    def test_duplicate_workspace_fails_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_cli(["workspace", "init", "--workspace-id", "ws-demo", "--root", tmp, "--json"])

            exit_code, stdout, stderr = run_cli(["workspace", "init", "--workspace-id", "ws-demo", "--root", tmp])

            self.assertEqual(exit_code, 2)
            self.assertEqual(stdout, "")
            self.assertIn("Workspace already exists", stderr)
            self.assertNotIn("Traceback", stderr)

    def test_duplicate_run_fails_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_cli(["workspace", "init", "--workspace-id", "ws-demo", "--root", tmp, "--json"])
            run_cli(["workspace", "run-create", "--workspace-id", "ws-demo", "--run-id", "run-demo", "--root", tmp])

            exit_code, stdout, stderr = run_cli([
                "workspace",
                "run-create",
                "--workspace-id",
                "ws-demo",
                "--run-id",
                "run-demo",
                "--root",
                tmp,
            ])

            self.assertEqual(exit_code, 2)
            self.assertEqual(stdout, "")
            self.assertIn("Run already exists", stderr)
            self.assertNotIn("Traceback", stderr)

    def test_missing_workspace_inspect_fails_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            exit_code, stdout, stderr = run_cli(["workspace", "inspect", "--workspace-id", "missing", "--root", tmp])

            self.assertEqual(exit_code, 2)
            self.assertEqual(stdout, "")
            self.assertIn("Workspace not found", stderr)
            self.assertNotIn("Traceback", stderr)

    def test_invalid_workspace_id_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for workspace_id in ("../x", "x/y", ".env", "", "a" * 65):
                with self.subTest(workspace_id=workspace_id):
                    exit_code, stdout, stderr = run_cli([
                        "workspace",
                        "init",
                        "--workspace-id",
                        workspace_id,
                        "--root",
                        tmp,
                    ])
                    self.assertEqual(exit_code, 2)
                    self.assertEqual(stdout, "")
                    self.assertIn("Invalid workspace_id", stderr)
                    self.assertNotIn("Traceback", stderr)

    def test_invalid_run_id_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_cli(["workspace", "init", "--workspace-id", "ws-demo", "--root", tmp, "--json"])
            for run_id in ("../x", "x/y", ".env", "", "a" * 65):
                with self.subTest(run_id=run_id):
                    exit_code, stdout, stderr = run_cli([
                        "workspace",
                        "run-create",
                        "--workspace-id",
                        "ws-demo",
                        "--run-id",
                        run_id,
                        "--root",
                        tmp,
                    ])
                    self.assertEqual(exit_code, 2)
                    self.assertEqual(stdout, "")
                    self.assertIn("Invalid run_id", stderr)
                    self.assertNotIn("Traceback", stderr)

    def test_workspace_commands_do_not_read_environment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            commands = (
                argparse.Namespace(workspace_action="init", workspace_id="ws-demo", root=tmp, json=True),
                argparse.Namespace(workspace_action="inspect", workspace_id="ws-demo", root=tmp, json=True),
                argparse.Namespace(
                    workspace_action="run-create",
                    workspace_id="ws-demo",
                    run_id="run-demo",
                    root=tmp,
                    json=True,
                ),
            )
            with patch.object(os, "environ", EnvGuard()), patch.object(cli.os, "environ", EnvGuard()):
                for args in commands:
                    stdout = io.StringIO()
                    with redirect_stdout(stdout):
                        self.assertEqual(cli.cmd_workspace(args), 0)
                    self.assertTrue(stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
