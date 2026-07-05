from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from agent_office import cli


def run_cli(argv: list[str], project_root: Path) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with patch.object(cli, "PROJECT_ROOT", project_root), redirect_stdout(stdout), redirect_stderr(stderr):
        code = cli.main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


class LocalMultiAgentRuntimeCliTests(unittest.TestCase):
    maxDiff = None

    def _workspace(self, root: Path) -> str:
        workspace = ".ai/local-runtime/demo"
        result = run_cli(["runtime", "workspace", "init", "--workspace", workspace, "--run-id", "run-demo", "--json"], root)
        self.assertEqual(result[0], 0, result[1] + result[2])
        self.assertNotIn("Traceback", result[1] + result[2])
        return workspace

    def test_workspace_init_status_json_contract_and_text_smoke(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            workspace = self._workspace(root)
            status = run_cli(["runtime", "workspace", "status", "--workspace", workspace, "--json"], root)
            text = run_cli(["runtime", "workspace", "inspect", "--workspace", workspace], root)
            payload = json.loads(status[1])

        self.assertEqual(status[0], 0, status[1] + status[2])
        self.assertEqual(payload["packet_type"], "agentoffice_local_multi_agent_runtime_v1")
        self.assertEqual(payload["run_id"], "run-demo")
        for key in ("goal_queue_path", "agent_outputs_path", "memory_path", "scheduler_ledger_path", "executor_ledger_path", "reports_path", "handoff_packet_path"):
            self.assertIn(key, payload["paths"])
        self.assertEqual(text[0], 0, text[1] + text[2])
        self.assertIn("AGENTOFFICE_LOCAL_MULTI_AGENT_RUNTIME_V1", text[1])

    def test_memory_write_list_inspect_summarize(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            workspace = self._workspace(root)
            write = run_cli([
                "runtime", "memory", "write", "--workspace", workspace, "--goal-id", "plan-objective", "--agent-role", "planner", "--kind", "note", "--content", "Plan the local runtime safely.", "--source-command", "unit-test", "--json"
            ], root)
            listing = run_cli(["runtime", "memory", "list", "--workspace", workspace, "--agent-role", "planner", "--json"], root)
            inspect = run_cli(["runtime", "memory", "inspect", "--workspace", workspace, "--memory-id", "mem-0001", "--json"], root)
            summarize = run_cli(["runtime", "memory", "summarize", "--workspace", workspace, "--json"], root)

        for result in (write, listing, inspect, summarize):
            self.assertEqual(result[0], 0, result[1] + result[2])
            self.assertNotIn("Traceback", result[1] + result[2])
        self.assertEqual(json.loads(write[1])["record"]["created_at"], "deterministic-static-v1")
        self.assertEqual(json.loads(listing[1])["record_count"], 1)
        self.assertEqual(json.loads(inspect[1])["record"]["goal_id"], "plan-objective")
        self.assertEqual(json.loads(summarize[1])["summary"]["by_role"], {"planner": 1})

    def test_scheduler_classifies_ready_blocked_failed_skipped_and_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            workspace = self._workspace(root)
            queue = root / ".ai" / "local-runtime" / "demo" / "goal-queue.json"
            queue.write_text(json.dumps({
                "schema_version": 1,
                "packet_type": "agentoffice_local_plan_graph",
                "run_id": "run-demo",
                "objective": "classification",
                "goals": [
                    {"goal_id": "done", "agent_role": "planner", "status": "completed", "depends_on": []},
                    {"goal_id": "ready", "agent_role": "executor", "status": "pending", "depends_on": ["done"]},
                    {"goal_id": "failed", "agent_role": "executor", "status": "failed", "depends_on": []},
                    {"goal_id": "blocked", "agent_role": "reviewer", "status": "pending", "depends_on": ["failed"]},
                    {"goal_id": "skipped", "agent_role": "reviewer", "status": "skipped", "depends_on": []},
                    {"goal_id": "running", "agent_role": "scheduler", "status": "running", "depends_on": []},
                ],
                "dependency_edges": [],
                "generated_at": "deterministic-static-v1",
            }), encoding="utf-8")
            result = run_cli(["runtime", "scheduler", "--workspace", workspace, "--json"], root)
            payload = json.loads(result[1])
            queue.write_text(json.dumps({
                "schema_version": 1,
                "packet_type": "agentoffice_local_plan_graph",
                "run_id": "run-demo",
                "objective": "bad",
                "goals": [
                    {"goal_id": "a", "agent_role": "planner", "status": "pending", "depends_on": ["b"]},
                    {"goal_id": "b", "agent_role": "executor", "status": "pending", "depends_on": ["a"]},
                    {"goal_id": "c", "agent_role": "executor", "status": "pending", "depends_on": ["missing"]},
                ],
                "dependency_edges": [],
                "generated_at": "deterministic-static-v1",
            }), encoding="utf-8")
            bad = run_cli(["runtime", "scheduler", "--workspace", workspace, "--json"], root)

        self.assertEqual(result[0], 0, result[1] + result[2])
        self.assertEqual(payload["counts"]["ready"], 1)
        self.assertEqual(payload["counts"]["blocked"], 1)
        self.assertEqual(payload["counts"]["failed"], 1)
        self.assertEqual(payload["counts"]["skipped"], 1)
        self.assertEqual(payload["counts"]["running"], 1)
        self.assertEqual(bad[0], 2)
        bad_payload = json.loads(bad[1])
        self.assertTrue(any(error.startswith("missing_dependency") for error in bad_payload["errors"]))
        self.assertTrue(any(error.startswith("circular_dependency") for error in bad_payload["errors"]))
        self.assertNotIn("Traceback", bad[1] + bad[2])

    def test_planner_is_deterministic_and_explain_text_smoke(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            workspace = self._workspace(root)
            args = ["runtime", "planner", "--workspace", workspace, "--objective", "Ship local runtime", "--explain", "--json"]
            first = run_cli(args, root)
            second = run_cli(args, root)
            text = run_cli(["runtime", "planner", "--workspace", workspace, "--objective", "Ship local runtime", "--explain"], root)

        self.assertEqual(first[0], 0, first[1] + first[2])
        self.assertEqual(json.loads(first[1])["plan_graph"], json.loads(second[1])["plan_graph"])
        self.assertIn("AGENTOFFICE_LOCAL_MULTI_AGENT_RUNTIME_V1", text[1])
        self.assertIn("provider/runtime/adapter execution: not triggered", text[1])

    def test_parallel_executor_bounded_dry_run_and_failure_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            workspace = self._workspace(root)
            run_cli(["runtime", "planner", "--workspace", workspace, "--objective", "Parallel dry-run", "--json"], root)
            queue = root / ".ai" / "local-runtime" / "demo" / "goal-queue.json"
            data = json.loads(queue.read_text(encoding="utf-8"))
            for goal in data["goals"]:
                goal["depends_on"] = []
            queue.write_text(json.dumps(data), encoding="utf-8")
            result = run_cli(["runtime", "parallel", "--workspace", workspace, "--max-workers", "2", "--fail-goal", "inspect-workspace", "--json"], root)
            payload = json.loads(result[1])
            failure_ledger = json.loads((root / ".ai" / "local-runtime" / "demo" / "executor-failures.json").read_text(encoding="utf-8"))

        self.assertEqual(result[0], 0, result[1] + result[2])
        self.assertTrue(payload["dry_run"])
        self.assertLessEqual(len(payload["results"]), 2)
        self.assertEqual(failure_ledger["failures"][0]["goal_id"], "inspect-workspace")

    def test_orchestrator_dry_run_resume_and_packets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            workspace = self._workspace(root)
            orchestrate = run_cli(["runtime", "orchestrate", "--workspace", workspace, "--objective", "Orchestrate local agents", "--max-workers", "2", "--json"], root)
            resume = run_cli(["runtime", "orchestrate", "--workspace", workspace, "--resume", "--json"], root)
            handoff = root / ".ai" / "local-runtime" / "demo" / "handoff-packet.json"
            report = root / ".ai" / "local-runtime" / "demo" / "reports" / "final-runtime-report.json"
            handoff_exists = handoff.exists()
            report_exists = report.exists()

        self.assertEqual(orchestrate[0], 0, orchestrate[1] + orchestrate[2])
        payload = json.loads(orchestrate[1])
        self.assertEqual(payload["operator_ready_summary"], "ready_for_review")
        self.assertTrue(handoff_exists)
        self.assertTrue(report_exists)
        self.assertEqual(resume[0], 0, resume[1] + resume[2])
        self.assertIn("recovery_summary", json.loads(resume[1]))

    def test_invalid_missing_bad_json_and_symlink_paths_fail_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            missing = run_cli(["runtime", "workspace", "status", "--workspace", ".ai/local-runtime/missing", "--json"], root)
            traversal = run_cli(["runtime", "workspace", "init", "--workspace", "../outside", "--run-id", "bad", "--json"], root)
            target = root / "target"
            target.mkdir()
            link = root / "link"
            link.symlink_to(target, target_is_directory=True)
            symlink = run_cli(["runtime", "workspace", "init", "--workspace", str(link), "--run-id", "bad", "--json"], root)
            workspace = self._workspace(root)
            memory = root / ".ai" / "local-runtime" / "demo" / "memory.jsonl"
            memory.write_text("{bad\n", encoding="utf-8")
            bad_json = run_cli(["runtime", "memory", "list", "--workspace", workspace, "--json"], root)

        for result in (missing, traversal, symlink, bad_json):
            self.assertEqual(result[0], 2)
            self.assertNotIn("Traceback", result[1] + result[2])
        self.assertIn("runtime_workspace_missing", missing[1])
        self.assertIn("runtime_workspace_path_traversal", traversal[1])
        self.assertIn("runtime_workspace_symlink_refused", symlink[1])
        self.assertIn("runtime_memory_jsonl_unreadable", bad_json[1])


if __name__ == "__main__":
    unittest.main()
