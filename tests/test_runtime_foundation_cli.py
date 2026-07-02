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


    def test_governance_json_text_positive_and_closure_alias(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._completed_workspace(root)
            closure_code, closure_stdout, closure_stderr = run_cli(
                ["runtime", "closure-packet", "--workspace", ".ai/workspaces/demo", "--out", ".ai/workspaces/demo/runtime-closure-packet.json", "--json"],
                root,
            )
            json_code, json_stdout, json_stderr = run_cli(
                [
                    "runtime",
                    "governance",
                    "--workspace",
                    ".ai/workspaces/demo",
                    "--closure-packet",
                    ".ai/workspaces/demo/runtime-closure-packet.json",
                    "--evidence-out",
                    ".ai/workspaces/demo/runtime-governance-evidence.json",
                    "--format",
                    "json",
                    "--json",
                ],
                root,
            )
            text_code, text_stdout, text_stderr = run_cli(
                [
                    "runtime",
                    "governance",
                    "--workspace",
                    ".ai/workspaces/demo",
                    "--closure-packet",
                    ".ai/workspaces/demo/runtime-closure-packet.json",
                    "--evidence-out",
                    ".ai/workspaces/demo/runtime-governance-evidence.txt",
                    "--format",
                    "text",
                ],
                root,
            )
            written = json.loads((root / ".ai" / "workspaces" / "demo" / "runtime-governance-evidence.json").read_text(encoding="utf-8"))
            text_body = (root / ".ai" / "workspaces" / "demo" / "runtime-governance-evidence.txt").read_text(encoding="utf-8")

        self.assertEqual(closure_code, 0, closure_stderr)
        self.assertEqual(json.loads(closure_stdout)["kind"], "runtime_closure_packet")
        self.assertEqual(json_code, 0, json_stderr)
        payload = json.loads(json_stdout)
        self.assertTrue(payload["runtime_governance_ready"])
        self.assertTrue(payload["closure_ready"])
        self.assertTrue(payload["replay_valid"])
        self.assertEqual(payload["completed_task_ids"], ["inspect", "implement", "review"])
        self.assertEqual(payload["explicit_boundary"], ["local/static/deterministic runtime only", "not real multi-agent runtime"])
        self.assertEqual(written["closure_packet_hash"], payload["closure_packet_hash"])
        self.assertEqual(text_code, 0, text_stderr)
        self.assertIn("runtime_governance_ready: true", text_stdout)
        self.assertIn("# AgentOffice Runtime Governance Evidence", text_body)
        self.assertIn("not real multi-agent runtime", text_body)
        self.assertNotIn("Traceback", closure_stdout + closure_stderr + json_stdout + json_stderr + text_stdout + text_stderr + text_body)

    def test_governance_clean_errors_and_not_ready_readback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._completed_workspace(root)
            close_code, close_stdout, close_stderr = run_cli(
                ["runtime", "close", "--workspace", ".ai/workspaces/demo", "--out", ".ai/workspaces/demo/closure.json", "--json"],
                root,
            )
            self.assertEqual(close_code, 0, close_stderr)
            missing = run_cli(
                [
                    "runtime",
                    "governance",
                    "--workspace",
                    ".ai/workspaces/demo",
                    "--closure-packet",
                    ".ai/workspaces/demo/missing.json",
                    "--evidence-out",
                    ".ai/workspaces/demo/gov.json",
                    "--json",
                ],
                root,
            )
            bad_path = root / ".ai" / "workspaces" / "demo" / "bad.json"
            bad_path.write_text("{not json", encoding="utf-8")
            invalid = run_cli(
                [
                    "runtime",
                    "governance",
                    "--workspace",
                    ".ai/workspaces/demo",
                    "--closure-packet",
                    ".ai/workspaces/demo/bad.json",
                    "--evidence-out",
                    ".ai/workspaces/demo/gov.json",
                    "--json",
                ],
                root,
            )
            traversal = run_cli(
                [
                    "runtime",
                    "governance",
                    "--workspace",
                    ".ai/workspaces/demo",
                    "--closure-packet",
                    ".ai/workspaces/demo/closure.json",
                    "--evidence-out",
                    ".ai/workspaces/demo/../gov.json",
                    "--json",
                ],
                root,
            )
            dotenv = run_cli(
                [
                    "runtime",
                    "governance",
                    "--workspace",
                    ".ai/workspaces/demo",
                    "--closure-packet",
                    ".ai/workspaces/demo/closure.json",
                    "--evidence-out",
                    ".ai/workspaces/demo/.env",
                    "--json",
                ],
                root,
            )
            closure_path = root / ".ai" / "workspaces" / "demo" / "closure.json"
            closure = json.loads(closure_path.read_text(encoding="utf-8"))
            closure["closure_ready"] = False
            closure_path.write_text(json.dumps(closure, indent=2) + "\n", encoding="utf-8")
            not_ready = run_cli(
                [
                    "runtime",
                    "governance",
                    "--workspace",
                    ".ai/workspaces/demo",
                    "--closure-packet",
                    ".ai/workspaces/demo/closure.json",
                    "--evidence-out",
                    ".ai/workspaces/demo/not-ready-governance.json",
                    "--json",
                ],
                root,
            )
            not_ready_artifact_exists = (root / ".ai" / "workspaces" / "demo" / "not-ready-governance.json").is_file()

        cases = [
            (missing, "runtime_governance_closure_packet_missing"),
            (invalid, "runtime_governance_closure_packet_invalid"),
            (traversal, "runtime_governance_path_traversal"),
            (dotenv, "runtime_governance_dotenv_refused"),
        ]
        for result, error_code in cases:
            code, stdout, stderr = result
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(stdout)["error_code"], error_code)
            self.assertNotIn("Traceback", stdout + stderr)
        self.assertEqual(not_ready[0], 2)
        not_ready_payload = json.loads(not_ready[1])
        self.assertFalse(not_ready_payload["runtime_governance_ready"])
        self.assertIn("closure_not_ready", not_ready_payload["blocking_reasons"])
        self.assertTrue(not_ready_artifact_exists)
        self.assertNotIn("Traceback", not_ready[1] + not_ready[2])

    def test_governance_symlink_output_refusals_are_clean(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._completed_workspace(root)
            close_code, close_stdout, close_stderr = run_cli(
                ["runtime", "close", "--workspace", ".ai/workspaces/demo", "--out", ".ai/workspaces/demo/closure.json", "--json"],
                root,
            )
            self.assertEqual(close_code, 0, close_stderr)
            target = root / ".ai" / "workspaces" / "demo" / "target.json"
            target.write_text("keep\n", encoding="utf-8")
            output_link = root / ".ai" / "workspaces" / "demo" / "gov-link.json"
            symlink_parent = root / ".ai" / "workspaces" / "demo" / "link-parent"
            real_parent = root / ".ai" / "workspaces" / "demo" / "real-parent"
            real_parent.mkdir()
            try:
                output_link.symlink_to(target)
                symlink_parent.symlink_to(real_parent, target_is_directory=True)
            except (NotImplementedError, OSError) as exc:
                self.skipTest(f"symlink unsupported: {exc}")
            symlink_output = run_cli(
                [
                    "runtime",
                    "governance",
                    "--workspace",
                    ".ai/workspaces/demo",
                    "--closure-packet",
                    ".ai/workspaces/demo/closure.json",
                    "--evidence-out",
                    ".ai/workspaces/demo/gov-link.json",
                    "--json",
                ],
                root,
            )
            symlink_parent_result = run_cli(
                [
                    "runtime",
                    "governance",
                    "--workspace",
                    ".ai/workspaces/demo",
                    "--closure-packet",
                    ".ai/workspaces/demo/closure.json",
                    "--evidence-out",
                    ".ai/workspaces/demo/link-parent/gov.json",
                    "--json",
                ],
                root,
            )

        self.assertEqual(symlink_output[0], 2)
        self.assertEqual(json.loads(symlink_output[1])["error_code"], "runtime_governance_output_symlink")
        self.assertEqual(symlink_parent_result[0], 2)
        self.assertEqual(json.loads(symlink_parent_result[1])["error_code"], "runtime_governance_parent_symlink")
        self.assertNotIn("Traceback", symlink_output[1] + symlink_output[2] + symlink_parent_result[1] + symlink_parent_result[2])

    def test_job_create_status_cancel_fail_resume_and_status_stability(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init(root)
            self._plan(root)
            create = run_cli(["runtime", "job", "create", "--workspace", ".ai/workspaces/demo", "--job-id", "demo-job", "--json"], root)
            first_status = run_cli(["runtime", "job", "status", "--workspace", ".ai/workspaces/demo", "--job-id", "demo-job", "--json"], root)
            second_status = run_cli(["runtime", "job", "status", "--workspace", ".ai/workspaces/demo", "--job-id", "demo-job", "--json"], root)
            cancel = run_cli(["runtime", "job", "cancel", "--workspace", ".ai/workspaces/demo", "--job-id", "demo-job", "--json"], root)
            cancelled_run = run_cli(["runtime", "run", "--workspace", ".ai/workspaces/demo", "--adapter", "local-static", "--execute-local", "--json"], root)
            cancelled_resume = run_cli(["runtime", "job", "resume", "--workspace", ".ai/workspaces/demo", "--job-id", "demo-job", "--json"], root)

            self._init(root, ".ai/workspaces/fail-job")
            self._plan(root, ".ai/workspaces/fail-job")
            fail_create = run_cli(["runtime", "job", "create", "--workspace", ".ai/workspaces/fail-job", "--job-id", "fail-job", "--json"], root)
            fail = run_cli(["runtime", "job", "fail", "--workspace", ".ai/workspaces/fail-job", "--job-id", "fail-job", "--reason", "test failure", "--json"], root)
            failed_run = run_cli(["runtime", "run", "--workspace", ".ai/workspaces/fail-job", "--adapter", "local-static", "--execute-local", "--json"], root)
            resume = run_cli(["runtime", "job", "resume", "--workspace", ".ai/workspaces/fail-job", "--job-id", "fail-job", "--json"], root)
            text_status = run_cli(["runtime", "job", "status", "--workspace", ".ai/workspaces/fail-job", "--job-id", "fail-job"], root)

        create_payload = json.loads(create[1])
        first_payload = json.loads(first_status[1])
        second_payload = json.loads(second_status[1])
        cancel_payload = json.loads(cancel[1])
        fail_payload = json.loads(fail[1])
        resume_payload = json.loads(resume[1])
        self.assertEqual(create[0], 0, create[2])
        self.assertEqual(create_payload["state"], "created")
        self.assertTrue(create_payload["resume_allowed"])
        self.assertEqual(first_status[0], 0, first_status[2])
        self.assertEqual(second_status[0], 0, second_status[2])
        self.assertEqual(first_payload["updated_at_or_static_timestamp"], second_payload["updated_at_or_static_timestamp"])
        self.assertEqual(cancel[0], 0, cancel[2])
        self.assertEqual(cancel_payload["state"], "cancelled")
        self.assertEqual(cancelled_run[0], 2)
        self.assertEqual(json.loads(cancelled_run[1])["error_code"], "runtime_job_cancelled")
        self.assertEqual(cancelled_resume[0], 2)
        self.assertEqual(json.loads(cancelled_resume[1])["error_code"], "runtime_job_resume_not_allowed")
        self.assertEqual(fail_create[0], 0, fail_create[2])
        self.assertEqual(fail[0], 0, fail[2])
        self.assertEqual(fail_payload["state"], "failed")
        self.assertEqual(fail_payload["failure_reason"], "test failure")
        self.assertEqual(failed_run[0], 2)
        self.assertEqual(json.loads(failed_run[1])["error_code"], "runtime_job_failed")
        self.assertEqual(resume[0], 0, resume[2])
        self.assertEqual(resume_payload["state"], "running")
        self.assertIn("job_id: fail-job", text_status[1])
        self.assertIn("job_state: running", text_status[1])
        self.assertNotIn("Traceback", "".join(str(part) for result in (create, first_status, second_status, cancel, cancelled_run, cancelled_resume, fail_create, fail, failed_run, resume, text_status) for part in result))

    def test_job_run_updates_completion_and_failure_blocks_downstream(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init(root)
            self._plan(root)
            run_cli(["runtime", "job", "create", "--workspace", ".ai/workspaces/demo", "--job-id", "complete-job", "--json"], root)
            complete_run = run_cli(["runtime", "run", "--workspace", ".ai/workspaces/demo", "--adapter", "local-static", "--execute-local", "--json"], root)
            complete_status = run_cli(["runtime", "job", "status", "--workspace", ".ai/workspaces/demo", "--job-id", "complete-job", "--json"], root)

            self._init(root, ".ai/workspaces/failure")
            plan_code, plan_stdout, plan_stderr = run_cli(
                [
                    "runtime",
                    "plan",
                    "--workspace",
                    ".ai/workspaces/failure",
                    "--task",
                    "inspect:Inspect",
                    "--task",
                    "fail:[fail] deterministic failure",
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
            self.assertEqual(plan_code, 0, plan_stderr)
            run_cli(["runtime", "job", "create", "--workspace", ".ai/workspaces/failure", "--job-id", "failed-job", "--json"], root)
            failed_run = run_cli(["runtime", "run", "--workspace", ".ai/workspaces/failure", "--adapter", "local-static", "--execute-local", "--json"], root)
            failed_status = run_cli(["runtime", "job", "status", "--workspace", ".ai/workspaces/failure", "--job-id", "failed-job", "--json"], root)

        complete_payload = json.loads(complete_run[1])
        complete_job = json.loads(complete_status[1])
        failed_payload = json.loads(failed_run[1])
        failed_job = json.loads(failed_status[1])
        self.assertEqual(complete_run[0], 0, complete_run[2])
        self.assertEqual(complete_payload["job"]["state"], "completed")
        self.assertEqual(complete_job["state"], "completed")
        self.assertFalse(complete_job["resume_allowed"])
        self.assertEqual(failed_run[0], 0, failed_run[2])
        self.assertEqual(failed_payload["failed_task_ids"], ["fail"])
        self.assertEqual(failed_payload["blocked_task_ids"], ["review"])
        self.assertEqual(failed_payload["job"]["state"], "failed")
        self.assertEqual(failed_job["state"], "failed")
        self.assertIn("workspace_status=failed", failed_job["failure_reason"])
        self.assertNotIn("Traceback", complete_run[1] + complete_run[2] + complete_status[1] + complete_status[2] + plan_stdout + plan_stderr + failed_run[1] + failed_run[2] + failed_status[1] + failed_status[2])

    def test_external_worker_adapter_prototype_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init(root)
            self._plan(root)
            listed = run_cli(["runtime", "worker-adapter", "--list", "--json"], root)
            described = run_cli(["runtime", "worker-adapter", "--name", "external-prototype", "--describe", "--json"], root)
            dry_run = run_cli(["runtime", "run", "--workspace", ".ai/workspaces/demo", "--adapter", "external-prototype", "--dry-run", "--json"], root)
            execute = run_cli(["runtime", "run", "--workspace", ".ai/workspaces/demo", "--adapter", "external-prototype", "--execute-local", "--json"], root)
            unsupported = run_cli(["runtime", "run", "--workspace", ".ai/workspaces/demo", "--adapter", "codex", "--dry-run", "--json"], root)

        listed_payload = json.loads(listed[1])
        described_payload = json.loads(described[1])
        dry_payload = json.loads(dry_run[1])
        names = [item["name"] for item in listed_payload["adapters"]]
        self.assertEqual(listed[0], 0, listed[2])
        self.assertEqual(names, ["external-prototype", "local-static", "noop"])
        self.assertEqual(described[0], 0, described[2])
        adapter = described_payload["adapter"]
        self.assertFalse(adapter["external_execution_enabled"])
        self.assertFalse(adapter["provider_calls"])
        self.assertFalse(adapter["model_calls"])
        self.assertFalse(adapter["shell_calls"])
        self.assertFalse(adapter["browser_calls"])
        self.assertEqual(adapter["reason"], "prototype interface only")
        self.assertEqual(dry_run[0], 0, dry_run[2])
        self.assertEqual(dry_payload["worker_adapter"]["name"], "external-prototype")
        self.assertEqual(dry_payload["would_execute_task_ids"], ["inspect", "implement", "review"])
        self.assertFalse(dry_payload["external_behavior"]["adapter_external_behavior"])
        self.assertEqual(execute[0], 2)
        self.assertEqual(json.loads(execute[1])["error_code"], "runtime_external_prototype_execute_refused")
        self.assertEqual(unsupported[0], 2)
        self.assertEqual(json.loads(unsupported[1])["error_code"], "runtime_unsupported_adapter")
        self.assertNotIn("Traceback", "".join(str(part) for result in (listed, described, dry_run, execute, unsupported) for part in result))


if __name__ == "__main__":
    unittest.main()
