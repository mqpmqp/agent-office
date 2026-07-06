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


def runtime_args(root: str, action: str, *extra: str) -> list[str]:
    return [
        "framework-runtime",
        action,
        "--workspace-id",
        "ws-demo",
        "--run-id",
        "run-demo",
        "--goal-id",
        "goal-demo",
        "--root",
        root,
        *extra,
    ]


class FrameworkRuntimeTrunkTest(unittest.TestCase):
    def test_dispatch_review_judge_happy_path_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            init_graph_run(tmp)

            exit_code, stdout, stderr = run_cli(runtime_args(tmp, "dispatch", "--task-id", "task-a", "--json"))
            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            dispatch = json.loads(stdout)
            self.assertEqual(dispatch["kind"], "agentoffice.framework_runtime_dispatch")
            self.assertEqual(dispatch["worker_adapter"], "local_echo_worker")
            self.assertIs(dispatch["provider_calls"], False)
            self.assertEqual(dispatch["actor_result"]["kind"], "agentoffice.actor_result")
            self.assertEqual(dispatch["actor_result"]["worker"]["mode"], "deterministic_local_stub")

            exit_code, stdout, stderr = run_cli(runtime_args(tmp, "review", "--result-id", "res_task-a", "--json"))
            self.assertEqual(exit_code, 0)
            review = json.loads(stdout)["review"]
            self.assertEqual(review["kind"], "agentoffice.framework_runtime_review")
            self.assertEqual(review["verdict"], "pass")
            self.assertIs(review["local_stub"], True)

            exit_code, stdout, stderr = run_cli(runtime_args(tmp, "judge", "--review-id", "rev_task-a", "--json"))
            self.assertEqual(exit_code, 0)
            judge = json.loads(stdout)["judge"]
            self.assertEqual(judge["kind"], "agentoffice.framework_runtime_judge")
            self.assertEqual(judge["decision"], "accepted")

            exit_code, stdout, stderr = run_cli(runtime_args(tmp, "status", "--json"))
            self.assertEqual(exit_code, 0)
            status = json.loads(stdout)
            self.assertEqual(status["tasks"][0]["status"], "accepted")
            self.assertEqual(status["tasks"][1]["status"], "created")
            self.assertGreaterEqual(len(status["events"]), 6)

    def test_resume_completes_incomplete_run_and_replay_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            init_graph_run(tmp)

            exit_code, stdout, stderr = run_cli(runtime_args(tmp, "resume", "--json"))
            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            resume = json.loads(stdout)
            self.assertEqual(resume["kind"], "agentoffice.framework_runtime_resume")
            self.assertTrue(resume["complete"])
            self.assertEqual(resume["incomplete_tasks"], [])
            self.assertGreaterEqual(resume["action_count"], 6)

            exit_code, stdout, stderr = run_cli(["framework-runtime", "replay", "--workspace-id", "ws-demo", "--run-id", "run-demo", "--root", tmp, "--json"])
            self.assertEqual(exit_code, 0)
            replay = json.loads(stdout)
            self.assertEqual(replay["kind"], "agentoffice.framework_runtime_replay")
            self.assertTrue(replay["read_only"])
            self.assertGreater(replay["event_count"], 0)

            exit_code, stdout, stderr = run_cli(runtime_args(tmp, "evidence", "--format", "json", "--json"))
            self.assertEqual(exit_code, 0)
            evidence = json.loads(stdout)
            self.assertEqual(evidence["kind"], "agentoffice.framework_runtime_evidence_export")
            self.assertEqual(evidence["bundle"]["kind"], "agentoffice.framework_runtime_evidence_bundle")
            self.assertTrue(Path(evidence["artifact_path"]).is_file())

            exit_code, stdout, stderr = run_cli(runtime_args(tmp, "evidence", "--format", "text"))
            self.assertEqual(exit_code, 0)
            self.assertIn("evidence ws-demo/run-demo/goal-demo format=text", stdout)

    def test_repeated_review_does_not_regress_terminal_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            init_graph_run(tmp)
            run_cli(runtime_args(tmp, "dispatch", "--task-id", "task-a", "--json"))
            run_cli(runtime_args(tmp, "review", "--result-id", "res_task-a", "--json"))
            run_cli(runtime_args(tmp, "judge", "--review-id", "rev_task-a", "--json"))

            exit_code, stdout, stderr = run_cli(runtime_args(tmp, "review", "--result-id", "res_task-a", "--json"))
            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            payload = json.loads(stdout)
            self.assertEqual(payload["task"]["status"], "accepted")

            exit_code, stdout, stderr = run_cli(runtime_args(tmp, "status", "--json"))
            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(stdout)["tasks"][0]["status"], "accepted")

    def test_list_inspect_workers_and_text_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            init_graph_run(tmp)
            run_cli(runtime_args(tmp, "resume", "--json"))

            exit_code, stdout, stderr = run_cli(["framework-runtime", "workers"])
            self.assertEqual(exit_code, 0)
            self.assertIn("worker local_echo_worker", stdout)
            self.assertIn("provider_calls=False", stdout)

            exit_code, stdout, stderr = run_cli(["framework-runtime", "list", "--workspace-id", "ws-demo", "--root", tmp])
            self.assertEqual(exit_code, 0)
            self.assertIn("runtime run ws-demo/run-demo/goal-demo complete=true", stdout)

            exit_code, stdout, stderr = run_cli(runtime_args(tmp, "inspect", "--task-id", "task-a"))
            self.assertEqual(exit_code, 0)
            self.assertIn("inspect task=task-a status=accepted", stdout)

    def test_structured_errors_and_traversal_rejection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            exit_code, stdout, stderr = run_cli(runtime_args(tmp, "dispatch", "--json"))
            self.assertEqual(exit_code, 2)
            self.assertEqual(stdout, "")
            self.assertIn("Workspace not found", stderr)
            self.assertNotIn("Traceback", stderr)

            init_graph_run(tmp)
            exit_code, stdout, stderr = run_cli(runtime_args(tmp, "dispatch", "--task-id", "missing", "--json"))
            self.assertEqual(exit_code, 2)
            self.assertEqual(stdout, "")
            self.assertIn("Task is not ready for dispatch", stderr)
            self.assertNotIn("Traceback", stderr)

            exit_code, stdout, stderr = run_cli([
                "framework-runtime",
                "dispatch",
                "--workspace-id",
                "../x",
                "--run-id",
                "run-demo",
                "--goal-id",
                "goal-demo",
                "--root",
                tmp,
                "--json",
            ])
            self.assertEqual(exit_code, 2)
            self.assertIn("Invalid workspace_id", stderr)
            self.assertNotIn("Traceback", stderr)

            exit_code, stdout, stderr = run_cli(runtime_args(str(Path(tmp) / ".." / Path(tmp).name), "dispatch", "--json"))
            self.assertEqual(exit_code, 2)
            self.assertIn("Invalid root", stderr)
            self.assertNotIn("Traceback", stderr)

    def test_runtime_status_and_evidence_reject_symlinked_json_children(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside_tmp:
            init_graph_run(tmp)
            outside = Path(outside_tmp) / "outside.json"
            outside.write_text('{"kind":"outside_secret","value":"dummy"}\n', encoding="utf-8")
            packets = Path(tmp) / ".ai" / "workspaces" / "ws-demo" / "runs" / "run-demo" / "packets"
            symlink_path = packets / "leak.json"
            try:
                os.symlink(outside, symlink_path)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"symlink not available: {exc}")

            exit_code, stdout, stderr = run_cli(runtime_args(tmp, "status", "--json"))
            self.assertEqual(exit_code, 2)
            self.assertEqual(stdout, "")
            self.assertIn("Refusing to read symlink JSON file", stderr)
            self.assertNotIn("outside_secret", stdout + stderr)
            self.assertNotIn("Traceback", stderr)

            exit_code, stdout, stderr = run_cli(runtime_args(tmp, "evidence", "--format", "json", "--json"))
            self.assertEqual(exit_code, 2)
            self.assertEqual(stdout, "")
            self.assertIn("Refusing to read symlink JSON file", stderr)
            self.assertNotIn("outside_secret", stdout + stderr)
            self.assertNotIn("Traceback", stderr)

    def test_non_utf8_json_state_errors_are_structured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            init_graph_run(tmp)
            graph_path = Path(tmp) / ".ai" / "workspaces" / "ws-demo" / "goals" / "goal-demo" / "task_graph.json"
            graph_path.write_bytes(b"\xff")

            exit_code, stdout, stderr = run_cli(runtime_args(tmp, "status", "--json"))
            self.assertEqual(exit_code, 2)
            self.assertEqual(stdout, "")
            self.assertIn("Invalid UTF-8", stderr)
            self.assertNotIn("Traceback", stderr)

    def test_non_utf8_event_log_errors_are_structured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            init_graph_run(tmp)
            event_path = Path(tmp) / ".ai" / "workspaces" / "ws-demo" / "runs" / "run-demo" / "events.jsonl"
            event_path.write_bytes(b"\xff")

            exit_code, stdout, stderr = run_cli([
                "framework-runtime",
                "replay",
                "--workspace-id",
                "ws-demo",
                "--run-id",
                "run-demo",
                "--root",
                tmp,
                "--json",
            ])
            self.assertEqual(exit_code, 2)
            self.assertEqual(stdout, "")
            self.assertIn("Invalid UTF-8", stderr)
            self.assertNotIn("Traceback", stderr)

    def test_existing_slice_commands_and_legacy_packet_still_work(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            exit_code, stdout, stderr = run_cli(["workspace", "init", "--workspace-id", "ws-demo", "--root", tmp, "--json"])
            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(stdout)["kind"], "agentoffice.workspace")
            self.assertEqual(stderr, "")

            exit_code, stdout, stderr = run_cli(["workspace", "run-create", "--workspace-id", "ws-demo", "--run-id", "run-demo", "--root", tmp, "--json"])
            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(stdout)["kind"], "agentoffice.run")

            exit_code, stdout, stderr = run_cli(["task-graph", "create", "--workspace-id", "ws-demo", "--goal-id", "goal-demo", "--root", tmp, "--json"])
            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(stdout)["kind"], "agentoffice.task_graph_create")

            exit_code, stdout, stderr = run_cli(["packet", "emit", "--workspace-id", "ws-demo", "--run-id", "run-demo", "--goal-id", "goal-demo", "--task-id", "task-a", "--root", tmp, "--json"])
            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(stdout)["kind"], "agentoffice.packet")

            exit_code, stdout, stderr = run_cli(["actor-result", "intake", "--workspace-id", "ws-demo", "--run-id", "run-demo", "--packet-id", "pkt_task-a", "--actor", "manual", "--status", "completed", "--summary", "done", "--root", tmp, "--json"])
            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(stdout)["kind"], "agentoffice.actor_result")

            exit_code, stdout, stderr = run_cli(["packet", "--objective", "P6-10", "--profile", "lowest-cost", "--actor", "codex", "--json"])
            self.assertEqual(exit_code, 0)
            self.assertIn("execution_enabled", json.loads(stdout))

    def test_framework_runtime_command_does_not_read_environment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            init_graph_run(tmp)
            args = argparse.Namespace(
                framework_runtime_action="dispatch",
                workspace_id="ws-demo",
                run_id="run-demo",
                goal_id="goal-demo",
                task_id="task-a",
                root=tmp,
                json=True,
            )
            with patch.object(os, "environ", EnvGuard()), patch.object(cli.os, "environ", EnvGuard()):
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    self.assertEqual(cli.cmd_framework_runtime(args), 0)
                self.assertIn("agentoffice.framework_runtime_dispatch", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
