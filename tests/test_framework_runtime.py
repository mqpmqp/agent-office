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


class FrameworkRuntimeTrunkBaselineTest(unittest.TestCase):
    def test_baseline_dispatch_review_judge_happy_path_json(self) -> None:
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

    def test_baseline_resume_replay_and_evidence_smoke_path(self) -> None:
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

    def test_baseline_framework_runtime_cli_help_contract(self) -> None:
        help_cases = [
            (["--help"], "framework-runtime"),
            (["framework-runtime", "--help"], "job"),
            (["framework-runtime", "resume", "--help"], "--workspace-id"),
            (["framework-runtime", "evidence", "--help"], "--format"),
            (["framework-runtime", "job", "--help"], "cancel"),
            (["framework-runtime", "job", "create", "--help"], "--objective"),
            (["framework-runtime", "job", "list", "--help"], "--run-id"),
            (["framework-runtime", "job", "show", "--help"], "--job-id"),
            (["framework-runtime", "job", "cancel", "--help"], "--reason"),
            (["framework-runtime", "job", "fail", "--help"], "--reason"),
            (["framework-runtime", "executor", "--help"], "run-once"),
            (["framework-runtime", "executor", "run-once", "--help"], "--job-id"),
            (["framework-runtime", "executor", "loop", "--help"], "--max-iterations"),
            (["framework-runtime", "executor", "status", "--help"], "--run-id"),
            (["framework-runtime", "worker", "--help"], "result-intake"),
            (["framework-runtime", "worker", "adapters", "--help"], "--json"),
            (["framework-runtime", "worker", "result-intake", "--help"], "--summary"),
            (["framework-runtime", "worker", "result-show", "--help"], "--job-id"),
        ]
        for argv, expected in help_cases:
            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as cm:
                    cli.main(argv)
            self.assertEqual(cm.exception.code, 0)
            self.assertIn(expected, stdout.getvalue())
            self.assertEqual(stderr.getvalue(), "")

    def test_baseline_repeated_review_does_not_regress_terminal_task(self) -> None:
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

    def test_baseline_list_inspect_workers_and_text_output(self) -> None:
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

    def test_baseline_structured_errors_and_traversal_rejection(self) -> None:
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

    def test_baseline_status_and_evidence_reject_symlinked_json_children(self) -> None:
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

    def test_baseline_non_utf8_json_state_errors_are_structured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            init_graph_run(tmp)
            graph_path = Path(tmp) / ".ai" / "workspaces" / "ws-demo" / "goals" / "goal-demo" / "task_graph.json"
            graph_path.write_bytes(b"\xff")

            exit_code, stdout, stderr = run_cli(runtime_args(tmp, "status", "--json"))
            self.assertEqual(exit_code, 2)
            self.assertEqual(stdout, "")
            self.assertIn("Invalid UTF-8", stderr)
            self.assertNotIn("Traceback", stderr)

    def test_baseline_non_utf8_event_log_errors_are_structured(self) -> None:
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


    def test_job_lifecycle_create_list_show_json_and_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            init_workspace(base, "ws-demo")
            create_run(base, "ws-demo", "run-demo")

            create_args = [
                "framework-runtime",
                "job",
                "create",
                "--workspace-id",
                "ws-demo",
                "--run-id",
                "run-demo",
                "--job-id",
                "job-a",
                "--objective",
                "Build local job lifecycle",
                "--metadata",
                "owner=codex",
                "--metadata",
                "priority=wp2",
                "--evidence-ref",
                ".ai/workspaces/ws-demo/runs/run-demo/evidence/framework_runtime_evidence.json",
                "--root",
                tmp,
                "--json",
            ]
            exit_code, stdout, stderr = run_cli(create_args)
            self.assertEqual(exit_code, 0, stderr)
            job = json.loads(stdout)
            self.assertEqual(job["kind"], "agentoffice.framework_runtime_job")
            self.assertEqual(job["status"], "pending")
            self.assertEqual(job["created_at"], "transition-0001")
            self.assertEqual(job["updated_at"], "transition-0001")
            self.assertEqual(job["metadata"], {"owner": "codex", "priority": "wp2"})
            self.assertEqual(job["evidence_refs"], [".ai/workspaces/ws-demo/runs/run-demo/evidence/framework_runtime_evidence.json"])
            self.assertFalse(job["provider_calls"])
            self.assertFalse(job["network_calls"])
            self.assertFalse(job["external_worker_calls"])
            self.assertEqual(job["transition_log"][0]["action"], "create")
            self.assertTrue((base / ".ai" / "workspaces" / "ws-demo" / "runs" / "run-demo" / "jobs" / "job-a.json").is_file())

            exit_code, stdout, stderr = run_cli([
                "framework-runtime", "job", "list", "--workspace-id", "ws-demo", "--run-id", "run-demo", "--root", tmp, "--json"
            ])
            self.assertEqual(exit_code, 0, stderr)
            listing = json.loads(stdout)
            self.assertEqual(listing["kind"], "agentoffice.framework_runtime_job_list")
            self.assertEqual(listing["job_count"], 1)
            self.assertEqual(listing["jobs"][0]["job_id"], "job-a")

            exit_code, stdout, stderr = run_cli([
                "framework-runtime", "job", "show", "--workspace-id", "ws-demo", "--run-id", "run-demo", "--job-id", "job-a", "--root", tmp, "--json"
            ])
            self.assertEqual(exit_code, 0, stderr)
            shown = json.loads(stdout)
            self.assertEqual(shown["evidence_refs"], job["evidence_refs"])

            exit_code, stdout, stderr = run_cli([
                "framework-runtime", "job", "show", "--workspace-id", "ws-demo", "--run-id", "run-demo", "--job-id", "job-a", "--root", tmp
            ])
            self.assertEqual(exit_code, 0, stderr)
            self.assertIn("job ws-demo/run-demo/job-a status=pending", stdout)
            self.assertIn("local_static=true", stdout)

    def test_job_lifecycle_cancel_fail_and_error_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            init_workspace(base, "ws-demo")
            create_run(base, "ws-demo", "run-demo")

            for job_id in ("cancel-me", "fail-me"):
                exit_code, stdout, stderr = run_cli([
                    "framework-runtime", "job", "create", "--workspace-id", "ws-demo", "--run-id", "run-demo", "--job-id", job_id,
                    "--objective", f"Objective for {job_id}", "--root", tmp, "--json"
                ])
                self.assertEqual(exit_code, 0, stderr)

            exit_code, stdout, stderr = run_cli([
                "framework-runtime", "job", "cancel", "--workspace-id", "ws-demo", "--run-id", "run-demo", "--job-id", "cancel-me",
                "--reason", "operator stopped", "--root", tmp, "--json"
            ])
            self.assertEqual(exit_code, 0, stderr)
            cancelled = json.loads(stdout)
            self.assertEqual(cancelled["status"], "cancelled")
            self.assertEqual(cancelled["updated_at"], "transition-0002")
            self.assertEqual(cancelled["transition_log"][-1]["reason"], "operator stopped")

            exit_code, stdout, stderr = run_cli([
                "framework-runtime", "job", "fail", "--workspace-id", "ws-demo", "--run-id", "run-demo", "--job-id", "fail-me",
                "--reason", "local failure", "--root", tmp
            ])
            self.assertEqual(exit_code, 0, stderr)
            self.assertIn("status=failed", stdout)

            exit_code, stdout, stderr = run_cli([
                "framework-runtime", "job", "cancel", "--workspace-id", "ws-demo", "--run-id", "run-demo", "--job-id", "cancel-me",
                "--root", tmp, "--json"
            ])
            self.assertEqual(exit_code, 2)
            self.assertEqual(stderr, "")
            error = json.loads(stdout)
            self.assertEqual(error["kind"], "agentoffice.framework_runtime_job_error")
            self.assertEqual(error["action"], "cancel")
            self.assertIn("terminal", error["error"])

            exit_code, stdout, stderr = run_cli([
                "framework-runtime", "job", "show", "--workspace-id", "ws-demo", "--run-id", "run-demo", "--job-id", "missing",
                "--root", tmp, "--json"
            ])
            self.assertEqual(exit_code, 2)
            self.assertEqual(stderr, "")
            self.assertIn("Job not found", json.loads(stdout)["error"])

            exit_code, stdout, stderr = run_cli([
                "framework-runtime", "job", "show", "--workspace-id", "ws-demo", "--run-id", "run-demo", "--job-id", "missing",
                "--root", tmp
            ])
            self.assertEqual(exit_code, 2)
            self.assertEqual(stdout, "")
            self.assertIn("Job not found", stderr)
            self.assertNotIn("Traceback", stderr)

    def test_local_executor_run_once_succeeds_pending_job_and_exports_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            init_workspace(base, "ws-demo")
            create_run(base, "ws-demo", "run-demo")
            create_goal_graph(base, "ws-demo", "goal-demo")

            exit_code, stdout, stderr = run_cli([
                "framework-runtime", "job", "create", "--workspace-id", "ws-demo", "--run-id", "run-demo",
                "--job-id", "job-a", "--objective", "Run local executor", "--root", tmp, "--json"
            ])
            self.assertEqual(exit_code, 0, stderr)
            self.assertEqual(json.loads(stdout)["status"], "pending")

            exit_code, stdout, stderr = run_cli([
                "framework-runtime", "executor", "run-once", "--workspace-id", "ws-demo", "--run-id", "run-demo",
                "--root", tmp, "--json"
            ])
            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["kind"], "agentoffice.framework_runtime_executor_run_once")
            self.assertTrue(payload["progressed"])
            self.assertEqual(payload["job"]["status"], "succeeded")
            self.assertEqual([entry["to_status"] for entry in payload["job"]["transition_log"]], ["pending", "running", "succeeded"])
            self.assertFalse(payload["provider_calls"])
            self.assertFalse(payload["network_calls"])
            self.assertFalse(payload["env_reads"])
            self.assertIn("executor_results/job-a.json", " ".join(payload["job"]["evidence_refs"]))
            self.assertTrue((base / ".ai" / "workspaces" / "ws-demo" / "runs" / "run-demo" / "executor_results" / "job-a.json").is_file())

            exit_code, stdout, stderr = run_cli([
                "framework-runtime", "executor", "status", "--workspace-id", "ws-demo", "--run-id", "run-demo",
                "--root", tmp, "--json"
            ])
            self.assertEqual(exit_code, 0, stderr)
            status = json.loads(stdout)
            self.assertEqual(status["succeeded_count"], 1)
            self.assertEqual(status["pending_count"], 0)
            self.assertEqual(status["executor_results"][0]["status"], "succeeded")

            exit_code, stdout, stderr = run_cli(runtime_args(tmp, "evidence", "--format", "json", "--json"))
            self.assertEqual(exit_code, 0, stderr)
            evidence = json.loads(stdout)
            self.assertEqual(len(evidence["bundle"]["status"]["jobs"]), 1)
            self.assertEqual(len(evidence["bundle"]["status"]["executor_results"]), 1)

            exit_code, stdout, stderr = run_cli([
                "framework-runtime", "replay", "--workspace-id", "ws-demo", "--run-id", "run-demo", "--root", tmp, "--json"
            ])
            self.assertEqual(exit_code, 0, stderr)
            replay = json.loads(stdout)
            event_types = [event["event_type"] for event in replay["events"]]
            self.assertIn("executor.job_started", event_types)
            self.assertIn("executor.job_succeeded", event_types)

    def test_local_executor_loop_drains_pending_jobs_and_keeps_failures_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            init_workspace(base, "ws-demo")
            create_run(base, "ws-demo", "run-demo")

            for job_id, metadata in (("job-ok", []), ("job-fail", ["executor_outcome=failed"])):
                args = [
                    "framework-runtime", "job", "create", "--workspace-id", "ws-demo", "--run-id", "run-demo",
                    "--job-id", job_id, "--objective", f"Objective {job_id}", "--root", tmp, "--json"
                ]
                for item in metadata:
                    args.extend(["--metadata", item])
                exit_code, stdout, stderr = run_cli(args)
                self.assertEqual(exit_code, 0, stderr)

            exit_code, stdout, stderr = run_cli([
                "framework-runtime", "executor", "loop", "--workspace-id", "ws-demo", "--run-id", "run-demo",
                "--root", tmp, "--json"
            ])
            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["kind"], "agentoffice.framework_runtime_executor_loop")
            self.assertEqual(payload["action_count"], 2)
            self.assertTrue(payload["complete"])
            self.assertEqual(payload["status"]["succeeded_count"], 1)
            self.assertEqual(payload["status"]["failed_count"], 1)
            self.assertEqual(payload["status"]["pending_count"], 0)

            exit_code, stdout, stderr = run_cli([
                "framework-runtime", "executor", "run-once", "--workspace-id", "ws-demo", "--run-id", "run-demo",
                "--root", tmp
            ])
            self.assertEqual(exit_code, 0, stderr)
            self.assertIn("progressed=false", stdout)

            exit_code, stdout, stderr = run_cli([
                "framework-runtime", "job", "cancel", "--workspace-id", "ws-demo", "--run-id", "run-demo",
                "--job-id", "job-ok", "--root", tmp, "--json"
            ])
            self.assertEqual(exit_code, 2)
            self.assertIn("terminal", json.loads(stdout)["error"])

    def test_local_executor_command_does_not_read_environment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            init_workspace(base, "ws-demo")
            create_run(base, "ws-demo", "run-demo")
            run_cli([
                "framework-runtime", "job", "create", "--workspace-id", "ws-demo", "--run-id", "run-demo",
                "--job-id", "job-a", "--objective", "Run local executor", "--root", tmp, "--json"
            ])
            args = argparse.Namespace(
                framework_runtime_action="executor",
                framework_runtime_job_action=None,
                framework_runtime_executor_action="run-once",
                workspace_id="ws-demo",
                run_id="run-demo",
                job_id=None,
                root=tmp,
                json=True,
            )
            with patch.object(os, "environ", EnvGuard()), patch.object(cli.os, "environ", EnvGuard()):
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    self.assertEqual(cli.cmd_framework_runtime(args), 0)
                self.assertIn("agentoffice.framework_runtime_executor_run_once", stdout.getvalue())

    def test_worker_adapter_contract_and_result_intake_succeed_pending_job(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            init_workspace(base, "ws-demo")
            create_run(base, "ws-demo", "run-demo")
            create_goal_graph(base, "ws-demo", "goal-demo")

            exit_code, stdout, stderr = run_cli(["framework-runtime", "worker", "adapters", "--json"])
            self.assertEqual(exit_code, 0, stderr)
            contract = json.loads(stdout)
            self.assertEqual(contract["kind"], "agentoffice.framework_runtime_worker_adapter_contract")
            adapter = contract["adapters"][0]
            self.assertEqual(adapter["adapter_id"], "local_worker_adapter_stub")
            self.assertEqual(adapter["supported_result_statuses"], ["failed", "succeeded"])
            self.assertFalse(adapter["execution_enabled"])
            self.assertFalse(adapter["provider_calls"])
            self.assertFalse(adapter["network_calls"])
            self.assertFalse(adapter["codex_worker_connected"])
            self.assertFalse(adapter["claude_worker_connected"])

            exit_code, stdout, stderr = run_cli([
                "framework-runtime", "job", "create", "--workspace-id", "ws-demo", "--run-id", "run-demo",
                "--job-id", "job-a", "--objective", "Intake deterministic worker result", "--root", tmp, "--json"
            ])
            self.assertEqual(exit_code, 0, stderr)

            exit_code, stdout, stderr = run_cli([
                "framework-runtime", "worker", "result-intake", "--workspace-id", "ws-demo", "--run-id", "run-demo",
                "--job-id", "job-a", "--status", "succeeded", "--summary", "local deterministic result",
                "--evidence-ref", "local/evidence/job-a.txt", "--root", tmp, "--json"
            ])
            self.assertEqual(exit_code, 0, stderr)
            intake = json.loads(stdout)
            self.assertEqual(intake["kind"], "agentoffice.framework_runtime_worker_result_intake")
            self.assertEqual(intake["worker_result"]["kind"], "agentoffice.framework_runtime_worker_result")
            self.assertEqual(intake["worker_result"]["status"], "succeeded")
            self.assertEqual(intake["worker_result"]["adapter_id"], "local_worker_adapter_stub")
            self.assertFalse(intake["worker_result"]["provider_calls"])
            self.assertFalse(intake["worker_result"]["network_calls"])
            self.assertFalse(intake["worker_result"]["codex_worker_connected"])
            self.assertFalse(intake["worker_result"]["claude_worker_connected"])
            self.assertEqual(intake["job"]["status"], "succeeded")
            self.assertEqual(intake["job"]["transition_log"][-1]["action"], "worker_result_succeeded")
            self.assertIn("worker_results/job-a.json", " ".join(intake["job"]["evidence_refs"]))
            self.assertIn("local/evidence/job-a.txt", intake["job"]["evidence_refs"])
            self.assertTrue((base / ".ai" / "workspaces" / "ws-demo" / "runs" / "run-demo" / "worker_results" / "job-a.json").is_file())

            exit_code, stdout, stderr = run_cli([
                "framework-runtime", "worker", "result-show", "--workspace-id", "ws-demo", "--run-id", "run-demo",
                "--job-id", "job-a", "--root", tmp, "--json"
            ])
            self.assertEqual(exit_code, 0, stderr)
            shown = json.loads(stdout)
            self.assertEqual(shown["summary"], "local deterministic result")

            exit_code, stdout, stderr = run_cli(runtime_args(tmp, "evidence", "--format", "json", "--json"))
            self.assertEqual(exit_code, 0, stderr)
            evidence = json.loads(stdout)
            self.assertEqual(len(evidence["bundle"]["status"]["worker_results"]), 1)
            self.assertEqual(evidence["bundle"]["worker_contract"]["adapters"][1]["adapter_id"], "local_worker_adapter_stub")

            exit_code, stdout, stderr = run_cli([
                "framework-runtime", "replay", "--workspace-id", "ws-demo", "--run-id", "run-demo", "--root", tmp, "--json"
            ])
            self.assertEqual(exit_code, 0, stderr)
            event_types = [event["event_type"] for event in json.loads(stdout)["events"]]
            self.assertIn("worker_result.received", event_types)
            self.assertIn("worker_result.succeeded", event_types)

    def test_worker_result_intake_rejects_missing_cancelled_duplicate_and_wrong_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            init_workspace(base, "ws-demo")
            create_run(base, "ws-demo", "run-demo")

            exit_code, stdout, stderr = run_cli([
                "framework-runtime", "worker", "result-intake", "--workspace-id", "ws-demo", "--run-id", "run-demo",
                "--job-id", "missing", "--status", "succeeded", "--summary", "missing job", "--root", tmp, "--json"
            ])
            self.assertEqual(exit_code, 2)
            self.assertEqual(stderr, "")
            self.assertIn("Job not found", json.loads(stdout)["error"])

            for job_id in ("cancelled", "accepted"):
                exit_code, stdout, stderr = run_cli([
                    "framework-runtime", "job", "create", "--workspace-id", "ws-demo", "--run-id", "run-demo",
                    "--job-id", job_id, "--objective", f"Objective {job_id}", "--root", tmp, "--json"
                ])
                self.assertEqual(exit_code, 0, stderr)

            exit_code, stdout, stderr = run_cli([
                "framework-runtime", "job", "cancel", "--workspace-id", "ws-demo", "--run-id", "run-demo",
                "--job-id", "cancelled", "--root", tmp, "--json"
            ])
            self.assertEqual(exit_code, 0, stderr)

            exit_code, stdout, stderr = run_cli([
                "framework-runtime", "worker", "result-intake", "--workspace-id", "ws-demo", "--run-id", "run-demo",
                "--job-id", "cancelled", "--status", "succeeded", "--summary", "cancelled job", "--root", tmp, "--json"
            ])
            self.assertEqual(exit_code, 2)
            self.assertIn("terminal", json.loads(stdout)["error"])

            exit_code, stdout, stderr = run_cli([
                "framework-runtime", "worker", "result-intake", "--workspace-id", "ws-demo", "--run-id", "run-demo",
                "--job-id", "accepted", "--adapter-id", "real-codex", "--status", "succeeded",
                "--summary", "wrong adapter", "--root", tmp, "--json"
            ])
            self.assertEqual(exit_code, 2)
            self.assertIn("Unsupported worker adapter", json.loads(stdout)["error"])

            exit_code, stdout, stderr = run_cli([
                "framework-runtime", "worker", "result-intake", "--workspace-id", "ws-demo", "--run-id", "run-demo",
                "--job-id", "accepted", "--status", "failed", "--summary", "deterministic failure", "--root", tmp, "--json"
            ])
            self.assertEqual(exit_code, 0, stderr)
            self.assertEqual(json.loads(stdout)["job"]["status"], "failed")

            exit_code, stdout, stderr = run_cli([
                "framework-runtime", "worker", "result-intake", "--workspace-id", "ws-demo", "--run-id", "run-demo",
                "--job-id", "accepted", "--status", "failed", "--summary", "duplicate", "--root", tmp, "--json"
            ])
            self.assertEqual(exit_code, 2)
            self.assertIn("terminal", json.loads(stdout)["error"])

    def test_worker_result_intake_command_does_not_read_environment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            init_workspace(base, "ws-demo")
            create_run(base, "ws-demo", "run-demo")
            run_cli([
                "framework-runtime", "job", "create", "--workspace-id", "ws-demo", "--run-id", "run-demo",
                "--job-id", "job-a", "--objective", "Worker result intake", "--root", tmp, "--json"
            ])
            args = argparse.Namespace(
                framework_runtime_action="worker",
                framework_runtime_job_action=None,
                framework_runtime_executor_action=None,
                framework_runtime_worker_action="result-intake",
                workspace_id="ws-demo",
                run_id="run-demo",
                job_id="job-a",
                adapter_id="local_worker_adapter_stub",
                status="succeeded",
                summary="local deterministic result",
                evidence_ref=None,
                root=tmp,
                json=True,
            )
            with patch.object(os, "environ", EnvGuard()), patch.object(cli.os, "environ", EnvGuard()):
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    self.assertEqual(cli.cmd_framework_runtime(args), 0)
                self.assertIn("agentoffice.framework_runtime_worker_result_intake", stdout.getvalue())

    def test_baseline_existing_slice_commands_and_legacy_packet_still_work(self) -> None:
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

    def test_baseline_framework_runtime_command_does_not_read_environment(self) -> None:
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
