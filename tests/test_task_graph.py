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
from agent_office.task_graph import TaskGraphError, compute_ready_tasks, create_goal_graph
from agent_office.workspace_store import init_workspace


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


def init_demo_workspace(root: str) -> None:
    init_workspace(Path(root), "ws-demo")


def task(task_id: str, status: str = "created", depends_on: list[str] | None = None) -> dict[str, object]:
    return {
        "task_id": task_id,
        "title": task_id,
        "status": status,
        "depends_on": [] if depends_on is None else depends_on,
        "role": "implementation_agent",
        "required_evidence": [],
    }


class TaskGraphKernelTest(unittest.TestCase):
    def test_create_goal_task_graph_positive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            init_demo_workspace(tmp)

            exit_code, stdout, stderr = run_cli([
                "task-graph",
                "create",
                "--workspace-id",
                "ws-demo",
                "--goal-id",
                "goal-demo",
                "--root",
                tmp,
                "--json",
            ])

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            payload = json.loads(stdout)
            self.assertEqual(payload["kind"], "agentoffice.task_graph_create")
            self.assertEqual(payload["goal"]["kind"], "agentoffice.goal")
            self.assertEqual(payload["task_graph"]["kind"], "agentoffice.task_graph")
            goal_root = Path(tmp, ".ai", "workspaces", "ws-demo", "goals", "goal-demo")
            self.assertTrue(Path(goal_root, "goal.json").is_file())
            self.assertTrue(Path(goal_root, "task_graph.json").is_file())

    def test_ready_computation_with_no_dependencies(self) -> None:
        graph = {"workspace_id": "ws-demo", "goal_id": "goal-demo", "tasks": [task("task-a")]}

        payload = compute_ready_tasks(graph)

        self.assertEqual([item["task_id"] for item in payload["ready_tasks"]], ["task-a"])
        self.assertEqual(payload["blocked_tasks"], [])

    def test_dependency_blocks_task(self) -> None:
        graph = {"workspace_id": "ws-demo", "goal_id": "goal-demo", "tasks": [task("task-a"), task("task-b", depends_on=["task-a"])]}

        payload = compute_ready_tasks(graph)

        self.assertEqual([item["task_id"] for item in payload["ready_tasks"]], ["task-a"])
        self.assertEqual(payload["blocked_tasks"], [{"task_id": "task-b", "reasons": ["dependency_not_accepted:task-a"]}])

    def test_accepted_dependency_unblocks_task(self) -> None:
        graph = {"workspace_id": "ws-demo", "goal_id": "goal-demo", "tasks": [task("task-a", status="accepted"), task("task-b", depends_on=["task-a"])]}

        payload = compute_ready_tasks(graph)

        self.assertEqual([item["task_id"] for item in payload["ready_tasks"]], ["task-b"])
        self.assertEqual(payload["blocked_tasks"], [{"task_id": "task-a", "reasons": ["status:accepted"]}])

    def test_unknown_dependency_reported_as_blocked(self) -> None:
        graph = {"workspace_id": "ws-demo", "goal_id": "goal-demo", "tasks": [task("task-a", depends_on=["missing"])]}

        payload = compute_ready_tasks(graph)

        self.assertEqual(payload["ready_tasks"], [])
        self.assertEqual(payload["blocked_tasks"], [{"task_id": "task-a", "reasons": ["unknown_dependency:missing"]}])

    def test_duplicate_task_id_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            init_demo_workspace(tmp)
            with self.assertRaisesRegex(TaskGraphError, "Duplicate task_id"):
                create_goal_graph(Path(tmp), "ws-demo", "goal-demo", [task("task-a"), task("task-a")])

    def test_invalid_goal_and_task_ids_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            init_demo_workspace(tmp)
            exit_code, stdout, stderr = run_cli(["task-graph", "create", "--workspace-id", "ws-demo", "--goal-id", "../x", "--root", tmp])
            self.assertEqual(exit_code, 2)
            self.assertEqual(stdout, "")
            self.assertIn("Invalid goal_id", stderr)
            self.assertNotIn("Traceback", stderr)

            with self.assertRaisesRegex(TaskGraphError, "Invalid task_id"):
                create_goal_graph(Path(tmp), "ws-demo", "goal-demo", [task("x/y")])

    def test_missing_graph_fails_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            init_demo_workspace(tmp)

            exit_code, stdout, stderr = run_cli(["task-graph", "ready", "--workspace-id", "ws-demo", "--goal-id", "goal-demo", "--root", tmp])

            self.assertEqual(exit_code, 2)
            self.assertEqual(stdout, "")
            self.assertIn("Task graph not found", stderr)
            self.assertNotIn("Traceback", stderr)

    def test_ready_cli_reads_graph_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            init_demo_workspace(tmp)
            create_goal_graph(Path(tmp), "ws-demo", "goal-demo", [task("task-a", status="accepted"), task("task-b", depends_on=["task-a"])])

            exit_code, stdout, stderr = run_cli(["task-graph", "ready", "--workspace-id", "ws-demo", "--goal-id", "goal-demo", "--root", tmp, "--json"])

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            payload = json.loads(stdout)
            self.assertEqual([item["task_id"] for item in payload["ready_tasks"]], ["task-b"])

    def test_task_graph_commands_do_not_read_environment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            init_demo_workspace(tmp)
            commands = (
                argparse.Namespace(task_graph_action="create", workspace_id="ws-demo", goal_id="goal-demo", root=tmp, json=True),
                argparse.Namespace(task_graph_action="ready", workspace_id="ws-demo", goal_id="goal-demo", root=tmp, json=True),
            )
            with patch.object(os, "environ", EnvGuard()), patch.object(cli.os, "environ", EnvGuard()):
                for args in commands:
                    stdout = io.StringIO()
                    with redirect_stdout(stdout):
                        self.assertEqual(cli.cmd_task_graph(args), 0)
                    self.assertTrue(stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
