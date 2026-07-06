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
from agent_office.packet_result import PacketResultError, read_actor_result
from agent_office.runtime_events import append_event, list_events
from agent_office.task_graph import create_goal_graph
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


def init_graph_run(root: str) -> None:
    base = Path(root)
    init_workspace(base, "ws-demo")
    create_run(base, "ws-demo", "run-demo")
    create_goal_graph(base, "ws-demo", "goal-demo")


def emit_packet(root: str, task_id: str = "task-a") -> tuple[int, str, str]:
    return run_cli([
        "packet",
        "emit",
        "--workspace-id",
        "ws-demo",
        "--run-id",
        "run-demo",
        "--goal-id",
        "goal-demo",
        "--task-id",
        task_id,
        "--root",
        root,
        "--json",
    ])


def intake_result(root: str) -> tuple[int, str, str]:
    return run_cli([
        "actor-result",
        "intake",
        "--workspace-id",
        "ws-demo",
        "--run-id",
        "run-demo",
        "--packet-id",
        "pkt_task-a",
        "--actor",
        "manual",
        "--status",
        "completed",
        "--summary",
        "done",
        "--root",
        root,
        "--json",
    ])


class PacketResultCliTest(unittest.TestCase):
    def test_packet_emit_positive_from_existing_task_graph(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            init_graph_run(tmp)

            exit_code, stdout, stderr = emit_packet(tmp)

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            payload = json.loads(stdout)
            self.assertEqual(payload["kind"], "agentoffice.packet")
            self.assertEqual(payload["packet_id"], "pkt_task-a")
            self.assertEqual(payload["role"], "implementation_agent")
            self.assertEqual(payload["objective"], "Task A")
            self.assertEqual(payload["allowed_files"], [])
            self.assertIn("read .env", payload["forbidden_actions"])
            self.assertTrue(Path(tmp, ".ai", "workspaces", "ws-demo", "runs", "run-demo", "packets", "pkt_task-a.json").is_file())

    def test_packet_list_positive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            init_graph_run(tmp)
            emit_packet(tmp)

            exit_code, stdout, stderr = run_cli(["packet", "list", "--workspace-id", "ws-demo", "--run-id", "run-demo", "--root", tmp, "--json"])

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            payload = json.loads(stdout)
            self.assertEqual(payload["kind"], "agentoffice.packet_list")
            self.assertEqual([packet["packet_id"] for packet in payload["packets"]], ["pkt_task-a"])

    def test_actor_result_intake_positive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            init_graph_run(tmp)
            emit_packet(tmp)

            exit_code, stdout, stderr = intake_result(tmp)

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            payload = json.loads(stdout)
            self.assertEqual(payload["kind"], "agentoffice.actor_result")
            self.assertEqual(payload["result_id"], "res_task-a")
            self.assertEqual(payload["packet_id"], "pkt_task-a")
            self.assertEqual(payload["actor"], "manual")
            self.assertEqual(payload["status"], "completed")
            self.assertEqual(payload["summary"], "done")
            self.assertTrue(Path(tmp, ".ai", "workspaces", "ws-demo", "runs", "run-demo", "results", "res_task-a.json").is_file())

    def test_actor_result_list_positive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            init_graph_run(tmp)
            emit_packet(tmp)
            intake_result(tmp)

            exit_code, stdout, stderr = run_cli(["actor-result", "list", "--workspace-id", "ws-demo", "--run-id", "run-demo", "--root", tmp, "--json"])

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            payload = json.loads(stdout)
            self.assertEqual(payload["kind"], "agentoffice.actor_result_list")
            self.assertEqual([result["result_id"] for result in payload["results"]], ["res_task-a"])

    def test_missing_workspace_or_run_fails_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            exit_code, stdout, stderr = emit_packet(tmp)
            self.assertEqual(exit_code, 2)
            self.assertEqual(stdout, "")
            self.assertIn("Workspace not found", stderr)
            self.assertNotIn("Traceback", stderr)

            init_workspace(Path(tmp), "ws-demo")
            create_goal_graph(Path(tmp), "ws-demo", "goal-demo")
            exit_code, stdout, stderr = emit_packet(tmp)
            self.assertEqual(exit_code, 2)
            self.assertEqual(stdout, "")
            self.assertIn("Run not found", stderr)
            self.assertNotIn("Traceback", stderr)

    def test_missing_task_graph_or_unknown_task_fails_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            init_workspace(Path(tmp), "ws-demo")
            create_run(Path(tmp), "ws-demo", "run-demo")

            exit_code, stdout, stderr = emit_packet(tmp)
            self.assertEqual(exit_code, 2)
            self.assertEqual(stdout, "")
            self.assertIn("Task graph not found", stderr)
            self.assertNotIn("Traceback", stderr)

            create_goal_graph(Path(tmp), "ws-demo", "goal-demo")
            exit_code, stdout, stderr = emit_packet(tmp, task_id="missing")
            self.assertEqual(exit_code, 2)
            self.assertEqual(stdout, "")
            self.assertIn("Task not found", stderr)
            self.assertNotIn("Traceback", stderr)

    def test_duplicate_packet_emit_fails_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            init_graph_run(tmp)
            emit_packet(tmp)
            packet_path = Path(tmp, ".ai", "workspaces", "ws-demo", "runs", "run-demo", "packets", "pkt_task-a.json")
            before = packet_path.read_text(encoding="utf-8")

            exit_code, stdout, stderr = emit_packet(tmp)

            self.assertEqual(exit_code, 2)
            self.assertEqual(stdout, "")
            self.assertIn("Packet already exists", stderr)
            self.assertEqual(packet_path.read_text(encoding="utf-8"), before)
            self.assertNotIn("Traceback", stderr)

    def test_duplicate_result_intake_fails_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            init_graph_run(tmp)
            emit_packet(tmp)
            intake_result(tmp)
            result_path = Path(tmp, ".ai", "workspaces", "ws-demo", "runs", "run-demo", "results", "res_task-a.json")
            before = result_path.read_text(encoding="utf-8")

            exit_code, stdout, stderr = intake_result(tmp)

            self.assertEqual(exit_code, 2)
            self.assertEqual(stdout, "")
            self.assertIn("Actor result already exists", stderr)
            self.assertEqual(result_path.read_text(encoding="utf-8"), before)
            self.assertNotIn("Traceback", stderr)

    def test_invalid_ids_reject_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            init_graph_run(tmp)
            cases = (
                (["packet", "emit", "--workspace-id", "../x", "--run-id", "run-demo", "--goal-id", "goal-demo", "--task-id", "task-a", "--root", tmp], "Invalid workspace_id"),
                (["packet", "emit", "--workspace-id", "ws-demo", "--run-id", "x/y", "--goal-id", "goal-demo", "--task-id", "task-a", "--root", tmp], "Invalid run_id"),
                (["packet", "emit", "--workspace-id", "ws-demo", "--run-id", "run-demo", "--goal-id", ".env", "--task-id", "task-a", "--root", tmp], "Invalid goal_id"),
                (["packet", "emit", "--workspace-id", "ws-demo", "--run-id", "run-demo", "--goal-id", "goal-demo", "--task-id", "x/y", "--root", tmp], "Invalid task_id"),
                (["actor-result", "intake", "--workspace-id", "ws-demo", "--run-id", "run-demo", "--packet-id", "../x", "--actor", "manual", "--status", "completed", "--summary", "done", "--root", tmp], "Invalid packet_id"),
            )
            for args, expected in cases:
                with self.subTest(expected=expected):
                    exit_code, stdout, stderr = run_cli(args)
                    self.assertEqual(exit_code, 2)
                    self.assertEqual(stdout, "")
                    self.assertIn(expected, stderr)
                    self.assertNotIn("Traceback", stderr)

            with self.assertRaisesRegex(PacketResultError, "Invalid result_id"):
                read_actor_result(Path(tmp), "ws-demo", "run-demo", "../x")

    def test_runtime_events_append_only_when_event_log_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            init_graph_run(tmp)
            append_event(Path(tmp), "ws-demo", "run-demo", "run.created", "runtime")

            emit_packet(tmp)
            intake_result(tmp)

            events = list_events(Path(tmp), "ws-demo", "run-demo")
            self.assertEqual([event["event_id"] for event in events], ["evt_000001", "evt_000002", "evt_000003"])
            self.assertEqual([event["event_type"] for event in events], ["run.created", "packet.emitted", "actor_result.received"])

    def test_packet_and_actor_result_commands_do_not_read_environment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            init_graph_run(tmp)
            commands = (
                argparse.Namespace(packet_action="emit", workspace_id="ws-demo", run_id="run-demo", goal_id="goal-demo", task_id="task-a", root=tmp, json=True),
                argparse.Namespace(packet_action="list", workspace_id="ws-demo", run_id="run-demo", root=tmp, json=True),
                argparse.Namespace(actor_result_action="intake", workspace_id="ws-demo", run_id="run-demo", packet_id="pkt_task-a", actor="manual", status="completed", summary="done", root=tmp, json=True),
                argparse.Namespace(actor_result_action="list", workspace_id="ws-demo", run_id="run-demo", root=tmp, json=True),
            )
            with patch.object(os, "environ", EnvGuard()), patch.object(cli.os, "environ", EnvGuard()):
                for args in commands:
                    stdout = io.StringIO()
                    with redirect_stdout(stdout):
                        if hasattr(args, "packet_action"):
                            self.assertEqual(cli.cmd_packet(args), 0)
                        else:
                            self.assertEqual(cli.cmd_actor_result(args), 0)
                    self.assertTrue(stdout.getvalue())

    def test_legacy_packet_command_still_works(self) -> None:
        exit_code, stdout, stderr = run_cli(["packet", "--objective", "P6-10", "--profile", "lowest-cost", "--actor", "codex", "--json"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(json.loads(stdout)["actor"], "codex")


if __name__ == "__main__":
    unittest.main()
