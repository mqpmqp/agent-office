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


class RuntimeFoundationCliTests(unittest.TestCase):
    maxDiff = None

    def _init(self, root: Path, workspace: str = ".ai/workspaces/demo", *, json_output: bool = True) -> dict[str, object]:
        args = ["runtime", "init", "--workspace", workspace, "--goal", "demo runtime goal"]
        if json_output:
            args.append("--json")
        code, stdout, stderr = run_cli(args, root)
        self.assertEqual(code, 0, stderr)
        self.assertNotIn("Traceback", stdout + stderr)
        return json.loads(stdout) if json_output else {}

    def _plan(self, root: Path, workspace: str = ".ai/workspaces/demo", extra: list[str] | None = None) -> dict[str, object]:
        args = [
            "runtime",
            "plan",
            "--workspace",
            workspace,
            "--task",
            "inspect:Inspect workspace",
            "--task",
            "implement:Implement deterministic local result",
            "--task",
            "review:Review deterministic result",
            "--depends",
            "implement:inspect",
            "--depends",
            "review:implement",
            "--json",
        ]
        if extra:
            args.extend(extra)
        code, stdout, stderr = run_cli(args, root)
        self.assertEqual(code, 0, stderr)
        self.assertNotIn("Traceback", stdout + stderr)
        return json.loads(stdout)

    def _completed_workspace(self, root: Path, workspace: str = ".ai/workspaces/demo") -> None:
        self._init(root, workspace)
        self._plan(root, workspace)
        code, stdout, stderr = run_cli(
            ["runtime", "run", "--workspace", workspace, "--adapter", "local-static", "--execute-local", "--json"],
            root,
        )
        self.assertEqual(code, 0, stderr)
        self.assertEqual(json.loads(stdout)["task_counts"]["completed"], 3)
        self.assertNotIn("Traceback", stdout + stderr)

    def test_init_json_positive_creates_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            payload = self._init(root)
            manifest = root / ".ai" / "workspaces" / "demo" / "manifest.json"
            self.assertTrue(manifest.exists())

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["command"], "runtime init")
        self.assertEqual(payload["workspace"], ".ai/workspaces/demo")
        self.assertEqual(payload["status"], "initialized")
        self.assertEqual(payload["task_graph_path"], ".ai/workspaces/demo/task_graph.json")
        self.assertFalse(payload["external_behavior"]["adapter_external_behavior"])

    def test_init_text_positive(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            code, stdout, stderr = run_cli(["runtime", "init", "--workspace", ".ai/workspaces/demo", "--goal", "demo runtime goal"], root)

        self.assertEqual(code, 0, stderr)
        self.assertIn("AgentOffice runtime foundation", stdout)
        self.assertIn("workspace: .ai/workspaces/demo", stdout)
        self.assertIn("status: initialized", stdout)
        self.assertIn("provider/runtime/adapter execution: not triggered", stdout)
        self.assertNotIn("Traceback", stdout + stderr)

    def test_invalid_workspace_path_and_path_traversal_are_clean_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as outside:
            root = Path(tmpdir)
            absolute_outside = str(Path(outside) / "runtime")
            bad_absolute = run_cli(["runtime", "init", "--workspace", absolute_outside, "--goal", "x", "--json"], root)
            traversal = run_cli(["runtime", "init", "--workspace", ".ai/workspaces/../escape", "--goal", "x", "--json"], root)

        for result, error_code in (
            (bad_absolute, "runtime_workspace_outside_project"),
            (traversal, "runtime_workspace_path_traversal"),
        ):
            code, stdout, stderr = result
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(stdout)["error_code"], error_code)
            self.assertNotIn("Traceback", stdout + stderr)

    def test_symlink_escape_clean_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as outside:
            root = Path(tmpdir)
            link_parent = root / ".ai" / "workspaces"
            link_parent.mkdir(parents=True)
            link = link_parent / "escape"
            try:
                link.symlink_to(Path(outside), target_is_directory=True)
            except (NotImplementedError, OSError) as exc:
                self.skipTest(f"symlink unsupported: {exc}")
            code, stdout, stderr = run_cli(["runtime", "init", "--workspace", ".ai/workspaces/escape/demo", "--goal", "x", "--json"], root)

        self.assertEqual(code, 2)
        self.assertEqual(json.loads(stdout)["error_code"], "runtime_workspace_symlink_escape")
        self.assertNotIn("Traceback", stdout + stderr)

    def test_valid_graph_topological_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init(root)
            payload = self._plan(root)

        self.assertEqual(payload["topological_order"], ["inspect", "implement", "review"])
        self.assertEqual([task["status"] for task in payload["tasks"]], ["pending", "pending", "pending"])
        self.assertEqual([task["role"] for task in payload["tasks"]], ["planner", "worker", "reviewer"])

    def test_duplicate_missing_dependency_and_cycle_are_clean_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init(root)
            cases = [
                (
                    [
                        "runtime",
                        "plan",
                        "--workspace",
                        ".ai/workspaces/demo",
                        "--task",
                        "inspect:Inspect",
                        "--task",
                        "inspect:Duplicate",
                        "--json",
                    ],
                    "runtime_plan_duplicate_task_id",
                ),
                (
                    [
                        "runtime",
                        "plan",
                        "--workspace",
                        ".ai/workspaces/demo",
                        "--task",
                        "inspect:Inspect",
                        "--depends",
                        "inspect:missing",
                        "--json",
                    ],
                    "runtime_plan_missing_dependency",
                ),
                (
                    [
                        "runtime",
                        "plan",
                        "--workspace",
                        ".ai/workspaces/demo",
                        "--task",
                        "a:A",
                        "--task",
                        "b:B",
                        "--depends",
                        "a:b",
                        "--depends",
                        "b:a",
                        "--json",
                    ],
                    "runtime_plan_cycle",
                ),
            ]
            for argv, error_code in cases:
                with self.subTest(error_code=error_code):
                    code, stdout, stderr = run_cli(argv, root)
                    self.assertEqual(code, 2)
                    self.assertEqual(json.loads(stdout)["error_code"], error_code)
                    self.assertNotIn("Traceback", stdout + stderr)

    def test_dry_run_does_not_change_task_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init(root)
            self._plan(root)
            graph_before = (root / ".ai" / "workspaces" / "demo" / "task_graph.json").read_text(encoding="utf-8")
            code, stdout, stderr = run_cli(
                ["runtime", "run", "--workspace", ".ai/workspaces/demo", "--adapter", "local-static", "--dry-run", "--json"],
                root,
            )
            graph_after = (root / ".ai" / "workspaces" / "demo" / "task_graph.json").read_text(encoding="utf-8")

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["would_execute_task_ids"], ["inspect", "implement", "review"])
        self.assertEqual(payload["executed_task_ids"], [])
        self.assertEqual(graph_before, graph_after)
        self.assertNotIn("Traceback", stdout + stderr)

    def test_unsupported_adapter_clean_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init(root)
            self._plan(root)
            code, stdout, stderr = run_cli(
                ["runtime", "run", "--workspace", ".ai/workspaces/demo", "--adapter", "codex", "--dry-run", "--json"],
                root,
            )

        self.assertEqual(code, 2)
        self.assertEqual(json.loads(stdout)["error_code"], "runtime_unsupported_adapter")
        self.assertNotIn("Traceback", stdout + stderr)

    def test_local_static_execute_writes_deterministic_result_memory_and_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init(root)
            self._plan(root)
            code, stdout, stderr = run_cli(
                ["runtime", "run", "--workspace", ".ai/workspaces/demo", "--adapter", "local-static", "--execute-local", "--json"],
                root,
            )
            graph = json.loads((root / ".ai" / "workspaces" / "demo" / "task_graph.json").read_text(encoding="utf-8"))
            status_code, status_stdout, status_stderr = run_cli(["runtime", "status", "--workspace", ".ai/workspaces/demo", "--json"], root)

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["executed_task_ids"], ["inspect", "implement", "review"])
        self.assertEqual(payload["task_counts"]["completed"], 3)
        self.assertEqual(payload["memory_entry_count"], 3)
        self.assertEqual([task["result"]["summary"] for task in graph["tasks"]], [
            "local-static deterministic completed result for inspect",
            "local-static deterministic completed result for implement",
            "local-static deterministic completed result for review",
        ])
        self.assertEqual(status_code, 0, status_stderr)
        status = json.loads(status_stdout)
        self.assertEqual(status["workspace_status"], "completed")
        self.assertEqual(status["completed_task_ids"], ["inspect", "implement", "review"])
        self.assertEqual(status["memory_entry_count"], 3)
        self.assertIn("task_executed:review:completed", status["latest_event_summary"])
        self.assertNotIn("Traceback", stdout + stderr + status_stdout + status_stderr)

    def test_repeated_run_does_not_duplicate_completed_task_until_reset(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init(root)
            self._plan(root)
            first = run_cli(["runtime", "run", "--workspace", ".ai/workspaces/demo", "--adapter", "local-static", "--execute-local", "--json"], root)
            second = run_cli(["runtime", "run", "--workspace", ".ai/workspaces/demo", "--adapter", "local-static", "--execute-local", "--json"], root)
            reset = run_cli(
                ["runtime", "run", "--workspace", ".ai/workspaces/demo", "--adapter", "local-static", "--execute-local", "--reset", "--json"],
                root,
            )

        first_payload = json.loads(first[1])
        second_payload = json.loads(second[1])
        reset_payload = json.loads(reset[1])
        self.assertEqual(first_payload["memory_entry_count"], 3)
        self.assertEqual(second_payload["executed_task_ids"], [])
        self.assertEqual(second_payload["skipped_completed_task_ids"], ["inspect", "implement", "review"])
        self.assertEqual(second_payload["memory_entry_count"], 3)
        self.assertEqual(reset_payload["executed_task_ids"], ["inspect", "implement", "review"])
        self.assertEqual(reset_payload["memory_entry_count"], 6)
        self.assertNotIn("Traceback", "".join(str(part) for part in first + second + reset))

    def test_failure_blocks_dependents(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init(root)
            code, stdout, stderr = run_cli(
                [
                    "runtime",
                    "plan",
                    "--workspace",
                    ".ai/workspaces/demo",
                    "--task",
                    "inspect:Inspect",
                    "--task",
                    "fail:[fail] Deterministic local failure",
                    "--task",
                    "review:Review",
                    "--depends",
                    "fail:inspect",
                    "--depends",
                    "review:fail",
                    "--json",
                ],
                root,
            )
            self.assertEqual(code, 0, stderr)
            run_code, run_stdout, run_stderr = run_cli(
                ["runtime", "run", "--workspace", ".ai/workspaces/demo", "--adapter", "noop", "--execute-local", "--json"],
                root,
            )
            status_code, status_stdout, status_stderr = run_cli(["runtime", "status", "--workspace", ".ai/workspaces/demo", "--json"], root)

        self.assertEqual(run_code, 0, run_stderr)
        payload = json.loads(run_stdout)
        self.assertEqual(payload["executed_task_ids"], ["inspect", "fail"])
        self.assertEqual(payload["failed_task_ids"], ["fail"])
        self.assertEqual(payload["blocked_task_ids"], ["review"])
        self.assertEqual(payload["memory_entry_count"], 2)
        self.assertEqual(status_code, 0, status_stderr)
        status = json.loads(status_stdout)
        self.assertEqual(status["workspace_status"], "failed")
        self.assertEqual(status["failed_task_ids"], ["fail"])
        self.assertEqual(status["blocked_task_ids"], ["review"])
        self.assertNotIn("Traceback", stdout + stderr + run_stdout + run_stderr + status_stdout + status_stderr)

    def test_json_schema_stable_and_text_status_contains_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init(root)
            self._plan(root)
            run_cli(["runtime", "run", "--workspace", ".ai/workspaces/demo", "--adapter", "local-static", "--execute-local", "--json"], root)
            code, stdout, stderr = run_cli(["runtime", "status", "--workspace", ".ai/workspaces/demo"], root)
            json_code, json_stdout, json_stderr = run_cli(["runtime", "status", "--workspace", ".ai/workspaces/demo", "--json"], root)

        self.assertEqual(code, 0, stderr)
        self.assertIn("workspace: .ai/workspaces/demo", stdout)
        self.assertIn("status: completed", stdout)
        self.assertIn("tasks: total=3 pending=0 completed=3 failed=0 blocked=0", stdout)
        self.assertEqual(json_code, 0, json_stderr)
        payload = json.loads(json_stdout)
        for key in ("ok", "command", "schema_version", "workspace", "workspace_status", "task_counts", "memory_entry_count", "latest_event_summary"):
            self.assertIn(key, payload)
        self.assertFalse(payload["external_behavior"]["adapter_external_behavior"])
        self.assertNotIn("Traceback", stdout + stderr + json_stdout + json_stderr)

    def test_packet_replay_evidence_and_close_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._completed_workspace(root)
            packet_code, packet_stdout, packet_stderr = run_cli(["runtime", "packet", "--workspace", ".ai/workspaces/demo", "--json"], root)
            replay_code, replay_stdout, replay_stderr = run_cli(["runtime", "replay", "--workspace", ".ai/workspaces/demo", "--json"], root)
            evidence_path = root / ".ai" / "workspaces" / "demo" / "evidence.json"
            evidence_code, evidence_stdout, evidence_stderr = run_cli(
                ["runtime", "evidence", "--workspace", ".ai/workspaces/demo", "--out", ".ai/workspaces/demo/evidence.json", "--format", "json", "--json"],
                root,
            )
            close_code, close_stdout, close_stderr = run_cli(
                ["runtime", "close", "--workspace", ".ai/workspaces/demo", "--out", ".ai/workspaces/demo/closure_packet.json", "--json"],
                root,
            )
            text_code, text_stdout, text_stderr = run_cli(["runtime", "close", "--workspace", ".ai/workspaces/demo"], root)
            self.assertTrue(evidence_path.exists())
            written = json.loads(evidence_path.read_text(encoding="utf-8"))

        self.assertEqual(packet_code, 0, packet_stderr)
        packet = json.loads(packet_stdout)
        self.assertEqual(packet["kind"], "runtime_lifecycle_packet")
        self.assertEqual(packet["lifecycle"]["workspace_status"], "completed")
        self.assertTrue(packet["lifecycle"]["terminal"])
        self.assertTrue(packet["readback_contract"]["replay_valid"])
        self.assertFalse(packet["external_behavior"]["adapter_external_behavior"])

        self.assertEqual(replay_code, 0, replay_stderr)
        replay = json.loads(replay_stdout)
        self.assertTrue(replay["replay_valid"])
        self.assertTrue(replay["graph_order_valid"])
        self.assertEqual(replay["memory_entry_count"], 3)
        self.assertEqual(replay["event_entry_count"], 3)
        self.assertEqual([item["task_id"] for item in replay["task_statuses"]], ["inspect", "implement", "review"])

        self.assertEqual(evidence_code, 0, evidence_stderr)
        evidence = json.loads(evidence_stdout)
        self.assertEqual(evidence["kind"], "runtime_workspace_evidence")
        self.assertEqual(written["file_digests"]["manifest"]["path"], ".ai/workspaces/demo/manifest.json")
        self.assertEqual(written["packet"]["lifecycle"]["completed_task_ids"], ["inspect", "implement", "review"])

        self.assertEqual(close_code, 0, close_stderr)
        close = json.loads(close_stdout)
        self.assertTrue(close["closure_packet_valid"])
        self.assertTrue(close["closure_ready"])
        self.assertEqual(close["readiness"], "ready")
        self.assertEqual(close["output_path"], ".ai/workspaces/demo/closure_packet.json")
        self.assertEqual(text_code, 0, text_stderr)
        self.assertIn("closure_packet_valid: true", text_stdout)
        self.assertIn("readiness: ready", text_stdout)
        self.assertNotIn("Traceback", packet_stdout + packet_stderr + replay_stdout + replay_stderr + evidence_stdout + evidence_stderr + close_stdout + close_stderr + text_stdout + text_stderr)

    def test_evidence_text_and_output_path_errors_are_clean(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as outside:
            root = Path(tmpdir)
            self._completed_workspace(root)
            text_code, text_stdout, text_stderr = run_cli(
                ["runtime", "evidence", "--workspace", ".ai/workspaces/demo", "--out", ".ai/workspaces/demo/evidence.md", "--format", "text", "--json"],
                root,
            )
            text_artifact = root / ".ai" / "workspaces" / "demo" / "evidence.md"
            text_body = text_artifact.read_text(encoding="utf-8")
            outside_code, outside_stdout, outside_stderr = run_cli(
                ["runtime", "evidence", "--workspace", ".ai/workspaces/demo", "--out", str(Path(outside) / "evidence.json"), "--json"],
                root,
            )
            traversal_code, traversal_stdout, traversal_stderr = run_cli(
                ["runtime", "evidence", "--workspace", ".ai/workspaces/demo", "--out", ".ai/workspaces/demo/../evidence.json", "--json"],
                root,
            )
            symlink_target = root / ".ai" / "workspaces" / "demo" / "target.json"
            symlink_target.write_text("keep\n", encoding="utf-8")
            symlink_path = root / ".ai" / "workspaces" / "demo" / "link.json"
            try:
                symlink_path.symlink_to(symlink_target)
            except (NotImplementedError, OSError) as exc:
                self.skipTest(f"symlink unsupported: {exc}")
            symlink_code, symlink_stdout, symlink_stderr = run_cli(
                ["runtime", "evidence", "--workspace", ".ai/workspaces/demo", "--out", ".ai/workspaces/demo/link.json", "--json"],
                root,
            )

        self.assertEqual(text_code, 0, text_stderr)
        self.assertIn("# AgentOffice Runtime Workspace Evidence", text_body)
        self.assertEqual(json.loads(text_stdout)["evidence_format"], "text")
        cases = [
            (outside_code, outside_stdout, outside_stderr, "runtime_evidence_outside_project"),
            (traversal_code, traversal_stdout, traversal_stderr, "runtime_evidence_path_traversal"),
            (symlink_code, symlink_stdout, symlink_stderr, "runtime_evidence_output_symlink"),
        ]
        for code, stdout, stderr, error_code in cases:
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(stdout)["error_code"], error_code)
            self.assertNotIn("Traceback", stdout + stderr)

    def test_replay_and_close_block_tampered_readback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._completed_workspace(root)
            graph_path = root / ".ai" / "workspaces" / "demo" / "task_graph.json"
            graph = json.loads(graph_path.read_text(encoding="utf-8"))
            graph["tasks"][1]["status"] = "pending"
            graph_path.write_text(json.dumps(graph, indent=2) + "\n", encoding="utf-8")
            replay_code, replay_stdout, replay_stderr = run_cli(["runtime", "replay", "--workspace", ".ai/workspaces/demo", "--json"], root)
            close_code, close_stdout, close_stderr = run_cli(["runtime", "close", "--workspace", ".ai/workspaces/demo", "--json"], root)

        self.assertEqual(replay_code, 2)
        replay = json.loads(replay_stdout)
        self.assertFalse(replay["replay_valid"])
        self.assertTrue(replay["mismatches"])
        self.assertEqual(close_code, 2)
        close = json.loads(close_stdout)
        self.assertFalse(close["closure_packet_valid"])
        self.assertIn("replay_readback_invalid", close["blocking_reasons"])
        self.assertNotIn("Traceback", replay_stdout + replay_stderr + close_stdout + close_stderr)


if __name__ == "__main__":
    unittest.main()
