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


    def _worker_result(self, workspace: str = ".ai/workspaces/demo", job_id: str = "demo-job", adapter: str = "external-prototype", task_id: str = "inspect", status: str = "completed") -> dict[str, object]:
        return {
            "schema_version": 1,
            "artifact_type": "worker_result",
            "workspace": workspace,
            "job_id": job_id,
            "adapter": adapter,
            "external_execution": False,
            "provider_calls": False,
            "model_calls": False,
            "browser_calls": False,
            "shell_calls": False,
            "task_results": [{"task_id": task_id, "status": status, "summary": "static worker result accepted"}],
            "marker": "AGENT_OFFICE_WORKER_RESULT",
        }

    def _prepare_worker_workspace(self, root: Path, workspace: str = ".ai/workspaces/demo", job_id: str = "demo-job") -> None:
        self._init(root, workspace)
        self._plan(root, workspace)
        code, stdout, stderr = run_cli(["runtime", "job", "create", "--workspace", workspace, "--job-id", job_id, "--json"], root)
        self.assertEqual(code, 0, stderr)
        self.assertNotIn("Traceback", stdout + stderr)


    def _prepare_worker_delivery_bundle(self, root: Path) -> None:
        self._prepare_worker_workspace(root)
        packet = run_cli([
            "runtime", "worker-packet", "--workspace", ".ai/workspaces/demo", "--adapter", "external-prototype", "--job-id", "demo-job", "--out", ".ai/workspaces/demo/worker-invocation-packet.json", "--json"
        ], root)
        self.assertEqual(packet[0], 0, packet[2])
        result_path = root / ".ai" / "workspaces" / "demo" / "worker-result.json"
        result_payload = self._worker_result()
        result_payload["task_results"] = [
            {"task_id": "inspect", "status": "completed", "summary": "static worker result accepted"},
            {"task_id": "implement", "status": "completed", "summary": "static worker result accepted"},
            {"task_id": "review", "status": "completed", "summary": "static worker result accepted"},
        ]
        result_path.write_text(json.dumps(result_payload), encoding="utf-8")
        intake = run_cli([
            "runtime", "worker-result", "intake", "--workspace", ".ai/workspaces/demo", "--packet", ".ai/workspaces/demo/worker-invocation-packet.json", "--result", ".ai/workspaces/demo/worker-result.json", "--json"
        ], root)
        self.assertEqual(intake[0], 0, intake[2])
        audit = run_cli([
            "runtime", "worker-result", "audit-closure", "--workspace", ".ai/workspaces/demo", "--packet", ".ai/workspaces/demo/worker-invocation-packet.json", "--result", ".ai/workspaces/demo/worker-result.json", "--out", ".ai/workspaces/demo/worker-audit-closure.json", "--json"
        ], root)
        self.assertEqual(audit[0], 0, audit[2])
        delivery = run_cli([
            "runtime", "worker-result", "delivery-bundle", "--workspace", ".ai/workspaces/demo", "--packet", ".ai/workspaces/demo/worker-invocation-packet.json", "--result", ".ai/workspaces/demo/worker-result.json", "--audit-closure", ".ai/workspaces/demo/worker-audit-closure.json", "--out", ".ai/workspaces/demo/worker-delivery-bundle.json", "--json"
        ], root)
        self.assertEqual(delivery[0], 0, delivery[2])


    def _prepare_merge_readiness(self, root: Path) -> Path:
        self._prepare_worker_delivery_bundle(root)
        base = root / ".ai" / "workspaces" / "demo"
        reviewer_output = base / "reviewer-output.md"
        reviewer_output.write_text(
            "\n".join([
                "# Static Reviewer Output",
                "verdict: PASS",
                "marker: R23_REVIEW_COMPLETE",
                "review_type: artifact",
                "review_caveat: artifact-only reviewer output",
                "findings_summary: no blockers",
                "reviewed_artifacts: .ai/workspaces/demo/worker-delivery-bundle.json",
                "reviewed_bundle_summary: worker delivery bundle ready",
                "safety_caveat: no provider/model/browser/shell execution",
                "R23_REVIEW_COMPLETE",
            ]),
            encoding="utf-8",
        )
        attestation = run_cli([
            "runtime", "worker-result", "reviewer-attestation", "--reviewer-artifact", ".ai/workspaces/demo/reviewer-output.md", "--marker", "R23_REVIEW_COMPLETE", "--out", ".ai/workspaces/demo/reviewer-attestation.json", "--json"
        ], root)
        self.assertEqual(attestation[0], 0, attestation[2])
        closure = run_cli([
            "runtime", "worker-result", "closure-evidence", "--reviewer-attestation", ".ai/workspaces/demo/reviewer-attestation.json", "--out", ".ai/workspaces/demo/closure-evidence.json", "--json"
        ], root)
        self.assertEqual(closure[0], 0, closure[2])
        merge = run_cli([
            "runtime", "worker-result", "merge-readiness", "--delivery-bundle", ".ai/workspaces/demo/worker-delivery-bundle.json", "--reviewer-attestation", ".ai/workspaces/demo/reviewer-attestation.json", "--closure-evidence", ".ai/workspaces/demo/closure-evidence.json", "--baseline", "base123", "--source-branch", "phase45/r23-r25", "--source-head", "head123", "--target-branch", "phase6/mainline", "--out", ".ai/workspaces/demo/merge-readiness.json", "--json"
        ], root)
        self.assertEqual(merge[0], 0, merge[2])
        return base

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


    def test_worker_gate_external_prototype_json_and_text_positive(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init(root)
            json_result = run_cli(["runtime", "worker-gate", "--workspace", ".ai/workspaces/demo", "--adapter", "external-prototype", "--json"], root)
            text_result = run_cli(["runtime", "worker-gate", "--workspace", ".ai/workspaces/demo", "--adapter", "external-prototype"], root)
            unsupported = run_cli(["runtime", "worker-gate", "--workspace", ".ai/workspaces/demo", "--adapter", "missing", "--json"], root)

        self.assertEqual(json_result[0], 0, json_result[2])
        payload = json.loads(json_result[1])
        self.assertTrue(payload["worker_gate_ready"])
        self.assertFalse(payload["external_execution_allowed"])
        self.assertFalse(payload["external_execution_enabled"])
        self.assertFalse(payload["provider_calls"])
        self.assertFalse(payload["model_calls"])
        self.assertFalse(payload["browser_calls"])
        self.assertFalse(payload["shell_calls"])
        self.assertTrue(payload["requires_explicit_future_authorization"])
        self.assertIn("execution refused", payload["reason"])
        self.assertEqual(text_result[0], 0, text_result[2])
        self.assertIn("worker_gate_ready: true", text_result[1])
        self.assertIn("external_execution_allowed: false", text_result[1])
        self.assertEqual(unsupported[0], 2)
        self.assertEqual(json.loads(unsupported[1])["error_code"], "runtime_worker_adapter_unknown")
        self.assertNotIn("Traceback", json_result[1] + json_result[2] + text_result[1] + text_result[2] + unsupported[1] + unsupported[2])

    def test_worker_packet_json_text_positive_and_path_refusals(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._prepare_worker_workspace(root)
            json_result = run_cli([
                "runtime", "worker-packet", "--workspace", ".ai/workspaces/demo", "--adapter", "external-prototype", "--job-id", "demo-job", "--out", ".ai/workspaces/demo/worker-invocation-packet.json", "--json"
            ], root)
            text_result = run_cli([
                "runtime", "worker-packet", "--workspace", ".ai/workspaces/demo", "--adapter", "external-prototype", "--job-id", "demo-job", "--out", ".ai/workspaces/demo/worker-invocation-packet.txt", "--format", "text", "--json"
            ], root)
            traversal = run_cli([
                "runtime", "worker-packet", "--workspace", ".ai/workspaces/demo", "--adapter", "external-prototype", "--job-id", "demo-job", "--out", ".ai/workspaces/demo/../packet.json", "--json"
            ], root)
            dotenv = run_cli([
                "runtime", "worker-packet", "--workspace", ".ai/workspaces/demo", "--adapter", "external-prototype", "--job-id", "demo-job", "--out", ".env", "--json"
            ], root)
            missing_workspace = run_cli([
                "runtime", "worker-packet", "--workspace", ".ai/workspaces/missing", "--adapter", "external-prototype", "--job-id", "demo-job", "--out", ".ai/workspaces/demo/missing.json", "--json"
            ], root)
            missing_job_root = root / ".ai" / "workspaces" / "missing-job"
            self._init(root, ".ai/workspaces/missing-job")
            self._plan(root, ".ai/workspaces/missing-job")
            missing_job = run_cli([
                "runtime", "worker-packet", "--workspace", ".ai/workspaces/missing-job", "--adapter", "external-prototype", "--job-id", "demo-job", "--out", ".ai/workspaces/missing-job/packet.json", "--json"
            ], root)
            link_target = root / ".ai" / "workspaces" / "demo" / "target.json"
            link_target.write_text("keep\n", encoding="utf-8")
            link = root / ".ai" / "workspaces" / "demo" / "link.json"
            try:
                link.symlink_to(link_target)
            except (NotImplementedError, OSError):
                link = None
            symlink_result = run_cli([
                "runtime", "worker-packet", "--workspace", ".ai/workspaces/demo", "--adapter", "external-prototype", "--job-id", "demo-job", "--out", ".ai/workspaces/demo/link.json", "--json"
            ], root) if link else None
            written = json.loads((root / ".ai" / "workspaces" / "demo" / "worker-invocation-packet.json").read_text(encoding="utf-8"))
            text_body = (root / ".ai" / "workspaces" / "demo" / "worker-invocation-packet.txt").read_text(encoding="utf-8")

        self.assertEqual(json_result[0], 0, json_result[2])
        payload = json.loads(json_result[1])
        self.assertTrue(payload["invocation_ready"])
        self.assertFalse(payload["invocation_allowed"])
        self.assertFalse(payload["external_execution_enabled"])
        self.assertEqual(payload["job_id"], "demo-job")
        self.assertEqual(payload["task_ids"], ["inspect", "implement", "review"])
        self.assertEqual(written["created_by"], "agent_office.runtime")
        self.assertEqual(text_result[0], 0, text_result[2])
        self.assertIn("invocation_allowed: false", text_body)
        self.assertEqual(json.loads(traversal[1])["error_code"], "runtime_worker_packet_path_traversal")
        self.assertEqual(json.loads(dotenv[1])["error_code"], "runtime_worker_packet_dotenv_refused")
        self.assertEqual(json.loads(missing_workspace[1])["error_code"], "runtime_workspace_missing")
        self.assertEqual(json.loads(missing_job[1])["error_code"], "runtime_job_missing")
        if symlink_result:
            self.assertEqual(symlink_result[0], 2)
            self.assertEqual(json.loads(symlink_result[1])["error_code"], "runtime_worker_packet_output_symlink")
        combined = json_result[1] + json_result[2] + text_result[1] + text_result[2] + traversal[1] + traversal[2] + dotenv[1] + dotenv[2] + missing_workspace[1] + missing_workspace[2] + missing_job[1] + missing_job[2]
        if symlink_result:
            combined += symlink_result[1] + symlink_result[2]
        self.assertNotIn("Traceback", combined)

    def test_worker_result_intake_positive_updates_memory_events_and_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._prepare_worker_workspace(root)
            packet = run_cli([
                "runtime", "worker-packet", "--workspace", ".ai/workspaces/demo", "--adapter", "external-prototype", "--job-id", "demo-job", "--out", ".ai/workspaces/demo/worker-invocation-packet.json", "--json"
            ], root)
            result_path = root / ".ai" / "workspaces" / "demo" / "worker-result.json"
            result_payload = self._worker_result()
            result_payload["task_results"] = [
                {"task_id": "inspect", "status": "completed", "summary": "static worker result accepted"},
                {"task_id": "implement", "status": "completed", "summary": "static worker result accepted"},
                {"task_id": "review", "status": "completed", "summary": "static worker result accepted"},
            ]
            result_path.write_text(json.dumps(result_payload), encoding="utf-8")
            intake = run_cli([
                "runtime", "worker-result", "intake", "--workspace", ".ai/workspaces/demo", "--packet", ".ai/workspaces/demo/worker-invocation-packet.json", "--result", ".ai/workspaces/demo/worker-result.json", "--json"
            ], root)
            status = run_cli(["runtime", "status", "--workspace", ".ai/workspaces/demo", "--json"], root)
            replay = run_cli(["runtime", "replay", "--workspace", ".ai/workspaces/demo", "--json"], root)

        self.assertEqual(packet[0], 0, packet[2])
        self.assertEqual(intake[0], 0, intake[2])
        payload = json.loads(intake[1])
        self.assertTrue(payload["intake_accepted"])
        self.assertEqual(payload["updated_task_ids"], ["inspect", "implement", "review"])
        self.assertEqual(payload["task_counts"]["completed"], 3)
        self.assertEqual(payload["memory_entry_count"], 3)
        self.assertEqual(payload["event_entry_count"], 3)
        self.assertEqual(payload["job"]["state"], "completed")
        self.assertEqual(json.loads(status[1])["workspace_status"], "completed")
        self.assertTrue(json.loads(replay[1])["replay_valid"])
        self.assertNotIn("Traceback", packet[1] + packet[2] + intake[1] + intake[2] + status[1] + status[2] + replay[1] + replay[2])

    def test_worker_result_intake_refuses_external_claims_mismatches_and_bad_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._prepare_worker_workspace(root)
            packet_result = run_cli([
                "runtime", "worker-packet", "--workspace", ".ai/workspaces/demo", "--adapter", "external-prototype", "--job-id", "demo-job", "--out", ".ai/workspaces/demo/worker-invocation-packet.json", "--json"
            ], root)
            self.assertEqual(packet_result[0], 0, packet_result[2])
            base = root / ".ai" / "workspaces" / "demo"
            cases = []
            for key, code in (
                ("external_execution", "runtime_worker_result_external_execution_refused"),
                ("provider_calls", "runtime_worker_result_provider_calls_refused"),
                ("model_calls", "runtime_worker_result_model_calls_refused"),
                ("browser_calls", "runtime_worker_result_browser_calls_refused"),
                ("shell_calls", "runtime_worker_result_shell_calls_refused"),
            ):
                payload = self._worker_result()
                payload[key] = True
                cases.append((f"{key}.json", payload, code))
            missing_marker = self._worker_result()
            missing_marker.pop("marker")
            cases.append(("missing-marker.json", missing_marker, "runtime_worker_result_marker_missing"))
            unknown_task = self._worker_result(task_id="missing")
            cases.append(("unknown-task.json", unknown_task, "runtime_worker_result_task_unknown"))
            workspace_mismatch = self._worker_result(workspace=".ai/workspaces/other")
            cases.append(("workspace-mismatch.json", workspace_mismatch, "runtime_worker_result_workspace_mismatch"))
            job_mismatch = self._worker_result(job_id="other-job")
            cases.append(("job-mismatch.json", job_mismatch, "runtime_worker_result_job_mismatch"))
            adapter_mismatch = self._worker_result(adapter="noop")
            cases.append(("adapter-mismatch.json", adapter_mismatch, "runtime_worker_result_adapter_mismatch"))
            bad_status = self._worker_result(status="running")
            cases.append(("bad-status.json", bad_status, "runtime_worker_result_status_invalid"))
            for filename, payload, error_code in cases:
                path = base / filename
                path.write_text(json.dumps(payload), encoding="utf-8")
                with self.subTest(error_code=error_code):
                    result = run_cli([
                        "runtime", "worker-result", "intake", "--workspace", ".ai/workspaces/demo", "--packet", ".ai/workspaces/demo/worker-invocation-packet.json", "--result", f".ai/workspaces/demo/{filename}", "--json"
                    ], root)
                    self.assertEqual(result[0], 2)
                    self.assertEqual(json.loads(result[1])["error_code"], error_code)
                    self.assertNotIn("Traceback", result[1] + result[2])
            malformed = base / "malformed.json"
            malformed.write_text("{", encoding="utf-8")
            malformed_result = run_cli([
                "runtime", "worker-result", "intake", "--workspace", ".ai/workspaces/demo", "--packet", ".ai/workspaces/demo/worker-invocation-packet.json", "--result", ".ai/workspaces/demo/malformed.json", "--json"
            ], root)
            missing_packet = run_cli([
                "runtime", "worker-result", "intake", "--workspace", ".ai/workspaces/demo", "--packet", ".ai/workspaces/demo/missing-packet.json", "--result", ".ai/workspaces/demo/malformed.json", "--json"
            ], root)
            missing_result = run_cli([
                "runtime", "worker-result", "intake", "--workspace", ".ai/workspaces/demo", "--packet", ".ai/workspaces/demo/worker-invocation-packet.json", "--result", ".ai/workspaces/demo/missing-result.json", "--json"
            ], root)
            traversal = run_cli([
                "runtime", "worker-result", "intake", "--workspace", ".ai/workspaces/demo", "--packet", ".ai/workspaces/demo/../worker-invocation-packet.json", "--result", ".ai/workspaces/demo/malformed.json", "--json"
            ], root)
            dotenv = run_cli([
                "runtime", "worker-result", "intake", "--workspace", ".ai/workspaces/demo", "--packet", ".env", "--result", ".ai/workspaces/demo/malformed.json", "--json"
            ], root)

        self.assertEqual(json.loads(malformed_result[1])["error_code"], "runtime_worker_result_invalid")
        self.assertEqual(json.loads(missing_packet[1])["error_code"], "runtime_worker_result_packet_missing")
        self.assertEqual(json.loads(missing_result[1])["error_code"], "runtime_worker_result_missing")
        self.assertEqual(json.loads(traversal[1])["error_code"], "runtime_worker_result_packet_path_traversal")
        self.assertEqual(json.loads(dotenv[1])["error_code"], "runtime_worker_result_packet_dotenv_refused")
        self.assertNotIn("Traceback", malformed_result[1] + malformed_result[2] + missing_packet[1] + missing_packet[2] + missing_result[1] + missing_result[2] + traversal[1] + traversal[2] + dotenv[1] + dotenv[2])


    def test_worker_result_replay_audit_closure_and_delivery_bundle_positive(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._prepare_worker_workspace(root)
            packet = run_cli([
                "runtime", "worker-packet", "--workspace", ".ai/workspaces/demo", "--adapter", "external-prototype", "--job-id", "demo-job", "--out", ".ai/workspaces/demo/worker-invocation-packet.json", "--json"
            ], root)
            result_path = root / ".ai" / "workspaces" / "demo" / "worker-result.json"
            result_payload = self._worker_result()
            result_payload["task_results"] = [
                {"task_id": "inspect", "status": "completed", "summary": "static worker result accepted"},
                {"task_id": "implement", "status": "completed", "summary": "static worker result accepted"},
                {"task_id": "review", "status": "completed", "summary": "static worker result accepted"},
            ]
            result_path.write_text(json.dumps(result_payload), encoding="utf-8")
            intake = run_cli([
                "runtime", "worker-result", "intake", "--workspace", ".ai/workspaces/demo", "--packet", ".ai/workspaces/demo/worker-invocation-packet.json", "--result", ".ai/workspaces/demo/worker-result.json", "--json"
            ], root)
            replay_json = run_cli([
                "runtime", "worker-result", "replay", "--workspace", ".ai/workspaces/demo", "--packet", ".ai/workspaces/demo/worker-invocation-packet.json", "--result", ".ai/workspaces/demo/worker-result.json", "--json"
            ], root)
            replay_text = run_cli([
                "runtime", "worker-result", "replay", "--workspace", ".ai/workspaces/demo", "--packet", ".ai/workspaces/demo/worker-invocation-packet.json", "--result", ".ai/workspaces/demo/worker-result.json"
            ], root)
            audit = run_cli([
                "runtime", "worker-result", "audit-closure", "--workspace", ".ai/workspaces/demo", "--packet", ".ai/workspaces/demo/worker-invocation-packet.json", "--result", ".ai/workspaces/demo/worker-result.json", "--out", ".ai/workspaces/demo/worker-audit-closure.json", "--json"
            ], root)
            audit_text = run_cli([
                "runtime", "worker-result", "audit-closure", "--workspace", ".ai/workspaces/demo", "--packet", ".ai/workspaces/demo/worker-invocation-packet.json", "--result", ".ai/workspaces/demo/worker-result.json", "--out", ".ai/workspaces/demo/worker-audit-closure.txt", "--format", "text", "--json"
            ], root)
            delivery = run_cli([
                "runtime", "worker-result", "delivery-bundle", "--workspace", ".ai/workspaces/demo", "--packet", ".ai/workspaces/demo/worker-invocation-packet.json", "--result", ".ai/workspaces/demo/worker-result.json", "--audit-closure", ".ai/workspaces/demo/worker-audit-closure.json", "--out", ".ai/workspaces/demo/worker-delivery-bundle.json", "--json"
            ], root)
            delivery_text = run_cli([
                "runtime", "worker-result", "delivery-bundle", "--workspace", ".ai/workspaces/demo", "--packet", ".ai/workspaces/demo/worker-invocation-packet.json", "--result", ".ai/workspaces/demo/worker-result.json", "--audit-closure", ".ai/workspaces/demo/worker-audit-closure.json", "--out", ".ai/workspaces/demo/worker-delivery-bundle.txt", "--format", "text", "--json"
            ], root)
            audit_written = json.loads((root / ".ai" / "workspaces" / "demo" / "worker-audit-closure.json").read_text(encoding="utf-8"))
            delivery_written = json.loads((root / ".ai" / "workspaces" / "demo" / "worker-delivery-bundle.json").read_text(encoding="utf-8"))
            audit_text_body = (root / ".ai" / "workspaces" / "demo" / "worker-audit-closure.txt").read_text(encoding="utf-8")
            delivery_text_body = (root / ".ai" / "workspaces" / "demo" / "worker-delivery-bundle.txt").read_text(encoding="utf-8")

        self.assertEqual(packet[0], 0, packet[2])
        self.assertEqual(intake[0], 0, intake[2])
        self.assertEqual(replay_json[0], 0, replay_json[2])
        replay = json.loads(replay_json[1])
        self.assertEqual(replay["kind"], "runtime_worker_result_replay")
        self.assertTrue(replay["replay_ready"])
        self.assertTrue(replay["governance_ready"])
        self.assertEqual(replay["result_completed_task_count"], 3)
        self.assertEqual(replay["memory_update_summary"]["entry_count"], 3)
        self.assertEqual(replay["events_update_summary"]["worker_result_intake_event_count"], 3)
        self.assertFalse(replay["provider_calls"])
        self.assertFalse(replay["model_calls"])
        self.assertFalse(replay["browser_calls"])
        self.assertFalse(replay["shell_calls"])
        self.assertTrue(replay["external_execution_refused"])
        self.assertEqual(replay_text[0], 0, replay_text[2])
        self.assertIn("replay_ready: true", replay_text[1])
        self.assertIn("result_completed_task_count: 3", replay_text[1])
        self.assertEqual(audit[0], 0, audit[2])
        audit_payload = json.loads(audit[1])
        self.assertEqual(audit_payload["kind"], "runtime_worker_audit_closure_packet")
        self.assertTrue(audit_payload["external_execution_refused"])
        self.assertFalse(audit_payload["invocation_allowed"])
        self.assertTrue(audit_payload["replay_ready"])
        self.assertTrue(audit_payload["governance_ready"])
        self.assertEqual(audit_written["replay_summary"]["result_completed_task_count"], 3)
        self.assertEqual(audit_text[0], 0, audit_text[2])
        self.assertIn("external_execution_refused: true", audit_text_body)
        self.assertEqual(delivery[0], 0, delivery[2])
        delivery_payload = json.loads(delivery[1])
        self.assertTrue(delivery_payload["reviewer_ready"])
        self.assertTrue(delivery_payload["delivery_ready"])
        self.assertFalse(delivery_payload["worker_gate_summary"]["provider_calls"])
        self.assertFalse(delivery_payload["invocation_packet_summary"]["invocation_allowed"])
        self.assertEqual(delivery_written["replay_summary"]["result_completed_task_count"], 3)
        self.assertEqual(delivery_text[0], 0, delivery_text[2])
        self.assertIn("delivery_ready: true", delivery_text_body)
        combined = "".join(str(part) for result in (packet, intake, replay_json, replay_text, audit, audit_text, delivery, delivery_text) for part in result)
        self.assertNotIn("Traceback", combined)

    def test_worker_result_replay_audit_delivery_refusals_are_clean(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._prepare_worker_workspace(root)
            packet = run_cli([
                "runtime", "worker-packet", "--workspace", ".ai/workspaces/demo", "--adapter", "external-prototype", "--job-id", "demo-job", "--out", ".ai/workspaces/demo/worker-invocation-packet.json", "--json"
            ], root)
            self.assertEqual(packet[0], 0, packet[2])
            base = root / ".ai" / "workspaces" / "demo"
            good_result = base / "worker-result.json"
            good_result.write_text(json.dumps(self._worker_result()), encoding="utf-8")
            bad_result = base / "bad-result.json"
            bad_result.write_text("{", encoding="utf-8")
            non_utf8_result = base / "non-utf8-result.json"
            non_utf8_result.write_bytes(b"\xff\xfe")
            missing_path = run_cli([
                "runtime", "worker-result", "replay", "--workspace", ".ai/workspaces/demo", "--packet", ".ai/workspaces/demo/worker-invocation-packet.json", "--result", ".ai/workspaces/demo/missing.json", "--json"
            ], root)
            malformed = run_cli([
                "runtime", "worker-result", "replay", "--workspace", ".ai/workspaces/demo", "--packet", ".ai/workspaces/demo/worker-invocation-packet.json", "--result", ".ai/workspaces/demo/bad-result.json", "--json"
            ], root)
            non_utf8 = run_cli([
                "runtime", "worker-result", "replay", "--workspace", ".ai/workspaces/demo", "--packet", ".ai/workspaces/demo/worker-invocation-packet.json", "--result", ".ai/workspaces/demo/non-utf8-result.json", "--json"
            ], root)
            traversal = run_cli([
                "runtime", "worker-result", "audit-closure", "--workspace", ".ai/workspaces/demo", "--packet", ".ai/workspaces/demo/../worker-invocation-packet.json", "--result", ".ai/workspaces/demo/worker-result.json", "--out", ".ai/workspaces/demo/audit.json", "--json"
            ], root)
            dotenv = run_cli([
                "runtime", "worker-result", "delivery-bundle", "--workspace", ".ai/workspaces/demo", "--packet", ".ai/workspaces/demo/worker-invocation-packet.json", "--result", ".ai/workspaces/demo/worker-result.json", "--audit-closure", ".env", "--out", ".ai/workspaces/demo/bundle.json", "--json"
            ], root)
            bad_audit = base / "bad-audit.json"
            bad_audit.write_text(json.dumps({"schema_version": 1, "kind": "runtime_worker_audit_closure_packet", "workspace": ".ai/workspaces/other"}), encoding="utf-8")
            audit_mismatch = run_cli([
                "runtime", "worker-result", "delivery-bundle", "--workspace", ".ai/workspaces/demo", "--packet", ".ai/workspaces/demo/worker-invocation-packet.json", "--result", ".ai/workspaces/demo/worker-result.json", "--audit-closure", ".ai/workspaces/demo/bad-audit.json", "--out", ".ai/workspaces/demo/bundle.json", "--json"
            ], root)
            link_target = base / "target-audit.json"
            link_target.write_text("{}\n", encoding="utf-8")
            link = base / "audit-link.json"
            try:
                link.symlink_to(link_target)
            except (NotImplementedError, OSError):
                link = None
            symlink_result = run_cli([
                "runtime", "worker-result", "audit-closure", "--workspace", ".ai/workspaces/demo", "--packet", ".ai/workspaces/demo/worker-invocation-packet.json", "--result", ".ai/workspaces/demo/worker-result.json", "--out", ".ai/workspaces/demo/audit-link.json", "--json"
            ], root) if link else None

        self.assertEqual(json.loads(missing_path[1])["error_code"], "runtime_worker_result_missing")
        self.assertEqual(json.loads(malformed[1])["error_code"], "runtime_worker_result_invalid")
        self.assertEqual(json.loads(non_utf8[1])["error_code"], "runtime_worker_result_invalid")
        self.assertEqual(json.loads(traversal[1])["error_code"], "runtime_worker_result_packet_path_traversal")
        self.assertEqual(json.loads(dotenv[1])["error_code"], "runtime_worker_delivery_bundle_audit_closure_dotenv_refused")
        self.assertEqual(json.loads(audit_mismatch[1])["error_code"], "runtime_worker_delivery_bundle_workspace_mismatch")
        combined = missing_path[1] + missing_path[2] + malformed[1] + malformed[2] + non_utf8[1] + non_utf8[2] + traversal[1] + traversal[2] + dotenv[1] + dotenv[2] + audit_mismatch[1] + audit_mismatch[2]
        if symlink_result:
            self.assertEqual(json.loads(symlink_result[1])["error_code"], "runtime_worker_audit_closure_output_symlink")
            combined += symlink_result[1] + symlink_result[2]
        self.assertNotIn("Traceback", combined)


    def test_worker_result_reviewer_attestation_closure_evidence_and_merge_readiness_positive(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._prepare_worker_delivery_bundle(root)
            base = root / ".ai" / "workspaces" / "demo"
            reviewer_output = base / "reviewer-output.md"
            reviewer_output.write_text(
                "\n".join([
                    "# Static Reviewer Output",
                    "verdict: PASS",
                    "marker: R20_REVIEW_COMPLETE",
                    "review_type: artifact",
                    "review_caveat: artifact-only reviewer output",
                    "findings_summary: no blockers",
                    "reviewed_artifacts: .ai/workspaces/demo/worker-delivery-bundle.json",
                    "reviewed_bundle_summary: worker delivery bundle ready",
                    "safety_caveat: no provider/model/browser/shell execution",
                    "R20_REVIEW_COMPLETE",
                ]),
                encoding="utf-8",
            )
            attestation_json = run_cli([
                "runtime", "worker-result", "reviewer-attestation", "--reviewer-artifact", ".ai/workspaces/demo/reviewer-output.md", "--marker", "R20_REVIEW_COMPLETE", "--out", ".ai/workspaces/demo/reviewer-attestation.json", "--json"
            ], root)
            attestation_text = run_cli([
                "runtime", "worker-result", "reviewer-attestation", "--reviewer-artifact", ".ai/workspaces/demo/reviewer-output.md", "--marker", "R20_REVIEW_COMPLETE", "--out", ".ai/workspaces/demo/reviewer-attestation.txt", "--format", "text", "--json"
            ], root)
            closure_json = run_cli([
                "runtime", "worker-result", "closure-evidence", "--reviewer-attestation", ".ai/workspaces/demo/reviewer-attestation.json", "--out", ".ai/workspaces/demo/closure-evidence.json", "--json"
            ], root)
            closure_text = run_cli([
                "runtime", "worker-result", "closure-evidence", "--reviewer-attestation", ".ai/workspaces/demo/reviewer-attestation.json", "--out", ".ai/workspaces/demo/closure-evidence.txt", "--format", "text", "--json"
            ], root)
            merge_json = run_cli([
                "runtime", "worker-result", "merge-readiness", "--delivery-bundle", ".ai/workspaces/demo/worker-delivery-bundle.json", "--reviewer-attestation", ".ai/workspaces/demo/reviewer-attestation.json", "--closure-evidence", ".ai/workspaces/demo/closure-evidence.json", "--baseline", "base123", "--source-branch", "phase44/r20-r22", "--source-head", "head123", "--target-branch", "phase6/mainline", "--out", ".ai/workspaces/demo/merge-readiness.json", "--json"
            ], root)
            merge_text = run_cli([
                "runtime", "worker-result", "merge-readiness", "--delivery-bundle", ".ai/workspaces/demo/worker-delivery-bundle.json", "--reviewer-attestation", ".ai/workspaces/demo/reviewer-attestation.json", "--closure-evidence", ".ai/workspaces/demo/closure-evidence.json", "--baseline", "base123", "--source-branch", "phase44/r20-r22", "--source-head", "head123", "--target-branch", "phase6/mainline", "--out", ".ai/workspaces/demo/merge-readiness.txt", "--format", "text", "--json"
            ], root)
            attestation_written = json.loads((base / "reviewer-attestation.json").read_text(encoding="utf-8"))
            attestation_text_body = (base / "reviewer-attestation.txt").read_text(encoding="utf-8")
            closure_written = json.loads((base / "closure-evidence.json").read_text(encoding="utf-8"))
            closure_text_body = (base / "closure-evidence.txt").read_text(encoding="utf-8")
            merge_written = json.loads((base / "merge-readiness.json").read_text(encoding="utf-8"))
            merge_text_body = (base / "merge-readiness.txt").read_text(encoding="utf-8")

        self.assertEqual(attestation_json[0], 0, attestation_json[2])
        attestation = json.loads(attestation_json[1])
        self.assertEqual(attestation["kind"], "runtime_worker_reviewer_attestation_packet")
        self.assertEqual(attestation["verdict"], "pass")
        self.assertEqual(attestation["marker"], "R20_REVIEW_COMPLETE")
        self.assertEqual(attestation["artifact_path"], ".ai/workspaces/demo/reviewer-output.md")
        self.assertGreater(attestation["byte_count"], 0)
        self.assertTrue(attestation["reviewer_attestation_present"])
        self.assertFalse(attestation["provider_calls"])
        self.assertFalse(attestation["model_calls"])
        self.assertFalse(attestation["browser_calls"])
        self.assertFalse(attestation["shell_calls"])
        self.assertEqual(attestation_written["sha256"], attestation["sha256"])
        self.assertEqual(attestation_text[0], 0, attestation_text[2])
        self.assertIn("verdict: pass", attestation_text_body)
        self.assertIn("external_execution_refused: true", attestation_text_body)
        self.assertEqual(closure_json[0], 0, closure_json[2])
        closure = json.loads(closure_json[1])
        self.assertEqual(closure["kind"], "runtime_worker_closure_evidence")
        self.assertTrue(closure["closure_evidence_imported"])
        self.assertTrue(closure["gate_readable"])
        self.assertFalse(closure["invocation_allowed"])
        self.assertEqual(closure_written["reviewer_attestation_source"]["sha256"], closure["reviewer_attestation_source"]["sha256"])
        self.assertEqual(closure_text[0], 0, closure_text[2])
        self.assertIn("closure_evidence_imported: true", closure_text_body)
        self.assertEqual(merge_json[0], 0, merge_json[2])
        merge = json.loads(merge_json[1])
        self.assertEqual(merge["kind"], "runtime_worker_merge_readiness_packet")
        self.assertTrue(merge["external_worker_replay_ready"])
        self.assertTrue(merge["audit_closure_ready"])
        self.assertTrue(merge["reviewer_attestation_present"])
        self.assertTrue(merge["closure_evidence_imported"])
        self.assertTrue(merge["delivery_bundle_ready"])
        self.assertTrue(merge["merge_readiness_ready"])
        self.assertEqual(merge["next_action"], "safe delivery")
        self.assertFalse(merge["invocation_allowed"])
        self.assertTrue(merge["external_execution_refused"])
        self.assertFalse(merge["provider_calls"])
        self.assertFalse(merge["model_calls"])
        self.assertFalse(merge["browser_calls"])
        self.assertFalse(merge["shell_calls"])
        self.assertEqual(merge_written["marker"], "AGENT_OFFICE_MERGE_READINESS_PACKET")
        self.assertEqual(merge_text[0], 0, merge_text[2])
        self.assertIn("next_action: safe delivery", merge_text_body)
        self.assertNotIn("Traceback", attestation_json[1] + attestation_json[2] + attestation_text[1] + attestation_text[2] + closure_json[1] + closure_json[2] + closure_text[1] + closure_text[2] + merge_json[1] + merge_json[2] + merge_text[1] + merge_text[2])

    def test_worker_result_reviewer_attestation_closure_and_merge_refusals_are_clean(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._prepare_worker_delivery_bundle(root)
            base = root / ".ai" / "workspaces" / "demo"
            empty = base / "empty-review.md"
            empty.write_text("", encoding="utf-8")
            missing_marker_file = base / "missing-marker.md"
            missing_marker_file.write_text("verdict: PASS\n", encoding="utf-8")
            malformed = base / "bad-review.json"
            malformed.write_text("{ R20_REVIEW_COMPLETE", encoding="utf-8")
            non_utf8 = base / "non-utf8-review.md"
            non_utf8.write_bytes(b"\xff\xfe")
            missing_artifact = run_cli([
                "runtime", "worker-result", "reviewer-attestation", "--reviewer-artifact", ".ai/workspaces/demo/missing-review.md", "--marker", "R20_REVIEW_COMPLETE", "--out", ".ai/workspaces/demo/attestation.json", "--json"
            ], root)
            empty_result = run_cli([
                "runtime", "worker-result", "reviewer-attestation", "--reviewer-artifact", ".ai/workspaces/demo/empty-review.md", "--marker", "R20_REVIEW_COMPLETE", "--out", ".ai/workspaces/demo/attestation.json", "--json"
            ], root)
            missing_marker = run_cli([
                "runtime", "worker-result", "reviewer-attestation", "--reviewer-artifact", ".ai/workspaces/demo/missing-marker.md", "--marker", "R20_REVIEW_COMPLETE", "--out", ".ai/workspaces/demo/attestation.json", "--json"
            ], root)
            bad_json = run_cli([
                "runtime", "worker-result", "reviewer-attestation", "--reviewer-artifact", ".ai/workspaces/demo/bad-review.json", "--marker", "R20_REVIEW_COMPLETE", "--out", ".ai/workspaces/demo/attestation.json", "--json"
            ], root)
            non_utf8_result = run_cli([
                "runtime", "worker-result", "reviewer-attestation", "--reviewer-artifact", ".ai/workspaces/demo/non-utf8-review.md", "--marker", "R20_REVIEW_COMPLETE", "--out", ".ai/workspaces/demo/attestation.json", "--json"
            ], root)
            traversal = run_cli([
                "runtime", "worker-result", "reviewer-attestation", "--reviewer-artifact", ".ai/workspaces/demo/../review.md", "--marker", "R20_REVIEW_COMPLETE", "--out", ".ai/workspaces/demo/attestation.json", "--json"
            ], root)
            bad_attestation = base / "bad-attestation.json"
            bad_attestation.write_text(json.dumps({"kind": "wrong", "schema_version": 1}), encoding="utf-8")
            bad_closure = run_cli([
                "runtime", "worker-result", "closure-evidence", "--reviewer-attestation", ".ai/workspaces/demo/bad-attestation.json", "--out", ".ai/workspaces/demo/closure-evidence.json", "--json"
            ], root)
            good_review = base / "reviewer-output.json"
            good_review.write_text(json.dumps({
                "verdict": "PASS",
                "marker": "R20_REVIEW_COMPLETE",
                "review_type": "artifact",
                "review_caveat": "artifact-only",
                "findings_summary": "no blockers",
                "reviewed_artifacts": [".ai/workspaces/demo/worker-delivery-bundle.json"],
                "reviewed_bundle_summary": "worker delivery bundle ready",
                "safety_caveat": "no provider/model/browser/shell execution",
            }), encoding="utf-8")
            good_attestation = run_cli([
                "runtime", "worker-result", "reviewer-attestation", "--reviewer-artifact", ".ai/workspaces/demo/reviewer-output.json", "--marker", "R20_REVIEW_COMPLETE", "--out", ".ai/workspaces/demo/reviewer-attestation.json", "--json"
            ], root)
            self.assertEqual(good_attestation[0], 0, good_attestation[2])
            bad_merge = run_cli([
                "runtime", "worker-result", "merge-readiness", "--delivery-bundle", ".ai/workspaces/demo/worker-delivery-bundle.json", "--reviewer-attestation", ".ai/workspaces/demo/reviewer-attestation.json", "--closure-evidence", ".ai/workspaces/demo/missing-closure.json", "--baseline", "base123", "--source-branch", "phase44/r20-r22", "--source-head", "head123", "--target-branch", "phase6/mainline", "--out", ".ai/workspaces/demo/merge-readiness.json", "--json"
            ], root)
            link_target = base / "target-review.md"
            link_target.write_text("verdict: PASS\nR20_REVIEW_COMPLETE\n", encoding="utf-8")
            link = base / "review-link.md"
            try:
                link.symlink_to(link_target)
            except (NotImplementedError, OSError):
                link = None
            symlink_result = run_cli([
                "runtime", "worker-result", "reviewer-attestation", "--reviewer-artifact", ".ai/workspaces/demo/review-link.md", "--marker", "R20_REVIEW_COMPLETE", "--out", ".ai/workspaces/demo/link-attestation.json", "--json"
            ], root) if link else None

        self.assertEqual(json.loads(missing_artifact[1])["error_code"], "runtime_worker_reviewer_artifact_missing")
        self.assertEqual(json.loads(empty_result[1])["error_code"], "runtime_worker_reviewer_artifact_empty")
        self.assertEqual(json.loads(missing_marker[1])["error_code"], "runtime_worker_reviewer_artifact_marker_missing")
        self.assertEqual(json.loads(bad_json[1])["error_code"], "runtime_worker_reviewer_artifact_invalid_json")
        self.assertEqual(json.loads(non_utf8_result[1])["error_code"], "runtime_worker_reviewer_artifact_non_utf8")
        self.assertEqual(json.loads(traversal[1])["error_code"], "runtime_worker_reviewer_artifact_path_traversal")
        self.assertEqual(json.loads(bad_closure[1])["error_code"], "runtime_worker_closure_evidence_attestation_invalid")
        self.assertEqual(json.loads(bad_merge[1])["error_code"], "runtime_worker_merge_readiness_closure_evidence_missing")
        combined = missing_artifact[1] + missing_artifact[2] + empty_result[1] + empty_result[2] + missing_marker[1] + missing_marker[2] + bad_json[1] + bad_json[2] + non_utf8_result[1] + non_utf8_result[2] + traversal[1] + traversal[2] + bad_closure[1] + bad_closure[2] + bad_merge[1] + bad_merge[2]
        if symlink_result:
            self.assertEqual(json.loads(symlink_result[1])["error_code"], "runtime_worker_reviewer_artifact_symlink")
            combined += symlink_result[1] + symlink_result[2]
        self.assertNotIn("Traceback", combined)

    def test_worker_result_r20_r22_help_is_available(self) -> None:
        for argv in (
            ["runtime", "worker-result", "reviewer-attestation", "--help"],
            ["runtime", "worker-result", "closure-evidence", "--help"],
            ["runtime", "worker-result", "merge-readiness", "--help"],
        ):
            with self.subTest(argv=argv):
                stdout = io.StringIO()
                stderr = io.StringIO()
                with self.assertRaises(SystemExit) as raised, redirect_stdout(stdout), redirect_stderr(stderr):
                    cli.main(argv)
                self.assertEqual(raised.exception.code, 0)
                self.assertIn("worker-result", stdout.getvalue())
                self.assertEqual(stderr.getvalue(), "")


    def test_worker_result_delivery_gate_audit_replay_positive(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            base = self._prepare_merge_readiness(root)
            gate_json = run_cli([
                "runtime", "worker-result", "delivery-gate", "--merge-readiness", ".ai/workspaces/demo/merge-readiness.json", "--out", ".ai/workspaces/demo/delivery-gate.json", "--json"
            ], root)
            gate_text = run_cli([
                "runtime", "worker-result", "delivery-gate", "--merge-readiness", ".ai/workspaces/demo/merge-readiness.json", "--out", ".ai/workspaces/demo/delivery-gate.txt", "--format", "text", "--json"
            ], root)
            replay_json = run_cli([
                "runtime", "worker-result", "audit-replay", "--packet", ".ai/workspaces/demo/delivery-gate.json", "--json"
            ], root)
            replay_text = run_cli([
                "runtime", "worker-result", "audit-replay", "--packet", ".ai/workspaces/demo/delivery-gate.json"
            ], root)
            gate_written = json.loads((base / "delivery-gate.json").read_text(encoding="utf-8"))
            gate_text_body = (base / "delivery-gate.txt").read_text(encoding="utf-8")

        self.assertEqual(gate_json[0], 0, gate_json[2])
        gate = json.loads(gate_json[1])
        self.assertEqual(gate["kind"], "runtime_worker_delivery_gate_summary")
        self.assertTrue(gate["delivery_gate_pass"])
        self.assertEqual(gate["gate_status"], "pass")
        self.assertEqual(gate["rejection_reasons"], [])
        self.assertEqual(gate["next_action"], "safe delivery")
        self.assertTrue(gate["reviewer_attestation_present"])
        self.assertTrue(gate["closure_evidence_imported"])
        self.assertTrue(gate["closure_evidence_gate_readable"])
        self.assertTrue(gate["external_worker_replay_ready"])
        self.assertTrue(gate["audit_closure_ready"])
        self.assertTrue(gate["delivery_bundle_ready"])
        self.assertFalse(gate["invocation_allowed"])
        self.assertTrue(gate["external_execution_refused"])
        self.assertFalse(gate["provider_calls"])
        self.assertFalse(gate["model_calls"])
        self.assertFalse(gate["browser_calls"])
        self.assertFalse(gate["shell_calls"])
        self.assertEqual(gate_written["marker"], "AGENT_OFFICE_DELIVERY_GATE_PACKET")
        self.assertEqual(gate_text[0], 0, gate_text[2])
        self.assertIn("delivery_gate_pass: true", gate_text_body)
        self.assertEqual(replay_json[0], 0, replay_json[2])
        replay = json.loads(replay_json[1])
        self.assertEqual(replay["kind"], "runtime_worker_audit_packet_replay")
        self.assertTrue(replay["original_readiness"])
        self.assertEqual(replay["rejection_reasons"], [])
        self.assertTrue(replay["replay_ready"])
        self.assertTrue(replay["governance_ready"])
        self.assertEqual(replay_text[0], 0, replay_text[2])
        self.assertIn("original_readiness: true", replay_text[1])
        self.assertNotIn("Traceback", gate_json[1] + gate_json[2] + gate_text[1] + gate_text[2] + replay_json[1] + replay_json[2] + replay_text[1] + replay_text[2])

    def test_worker_result_delivery_gate_rejection_recovery_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            base = self._prepare_merge_readiness(root)
            good = json.loads((base / "merge-readiness.json").read_text(encoding="utf-8"))
            cases = [
                ("missing-attestation.json", {"reviewer_attestation_present": False, "merge_readiness_ready": False}, "reviewer_attestation_missing"),
                ("missing-closure.json", {"closure_evidence_imported": False, "merge_readiness_ready": False}, "closure_evidence_not_imported"),
                ("invocation-allowed.json", {"invocation_allowed": True, "merge_readiness_ready": False}, "invocation_not_refused"),
                ("execution-not-refused.json", {"external_execution_refused": False, "merge_readiness_ready": False}, "external_execution_not_refused"),
                ("provider-call.json", {"provider_calls": True, "merge_readiness_ready": False}, "provider_calls_not_false"),
                ("model-call.json", {"model_calls": True, "merge_readiness_ready": False}, "model_calls_not_false"),
                ("browser-call.json", {"browser_calls": True, "merge_readiness_ready": False}, "browser_calls_not_false"),
                ("shell-call.json", {"shell_calls": True, "merge_readiness_ready": False}, "shell_calls_not_false"),
            ]
            results = {}
            for filename, updates, expected_reason in cases:
                payload = dict(good)
                payload.update(updates)
                (base / filename).write_text(json.dumps(payload), encoding="utf-8")
                results[expected_reason] = run_cli([
                    "runtime", "worker-result", "delivery-gate", "--merge-readiness", f".ai/workspaces/demo/{filename}", "--out", f".ai/workspaces/demo/{filename}.gate.json", "--json"
                ], root)
            reject_gate = run_cli([
                "runtime", "worker-result", "delivery-gate", "--merge-readiness", ".ai/workspaces/demo/missing-closure.json", "--out", ".ai/workspaces/demo/rejected-delivery-gate.json", "--json"
            ], root)
            rejection = run_cli([
                "runtime", "worker-result", "rejection-packet", "--delivery-gate", ".ai/workspaces/demo/rejected-delivery-gate.json", "--out", ".ai/workspaces/demo/rejection-packet.json", "--json"
            ], root)
            rejection_text = run_cli([
                "runtime", "worker-result", "rejection-packet", "--delivery-gate", ".ai/workspaces/demo/rejected-delivery-gate.json", "--out", ".ai/workspaces/demo/rejection-packet.txt", "--format", "text", "--json"
            ], root)
            replay_rejection = run_cli([
                "runtime", "worker-result", "audit-replay", "--packet", ".ai/workspaces/demo/rejection-packet.json", "--json"
            ], root)
            fixed_closure = run_cli([
                "runtime", "worker-result", "closure-evidence", "--reviewer-attestation", ".ai/workspaces/demo/reviewer-attestation.json", "--out", ".ai/workspaces/demo/fixed-closure-evidence.json", "--json"
            ], root)
            fixed_merge = run_cli([
                "runtime", "worker-result", "merge-readiness", "--delivery-bundle", ".ai/workspaces/demo/worker-delivery-bundle.json", "--reviewer-attestation", ".ai/workspaces/demo/reviewer-attestation.json", "--closure-evidence", ".ai/workspaces/demo/fixed-closure-evidence.json", "--baseline", "base123", "--source-branch", "phase45/r23-r25", "--source-head", "head123", "--target-branch", "phase6/mainline", "--out", ".ai/workspaces/demo/fixed-merge-readiness.json", "--json"
            ], root)
            recovered_gate = run_cli([
                "runtime", "worker-result", "delivery-gate", "--merge-readiness", ".ai/workspaces/demo/fixed-merge-readiness.json", "--out", ".ai/workspaces/demo/recovered-delivery-gate.json", "--json"
            ], root)
            rejection_text_body = (base / "rejection-packet.txt").read_text(encoding="utf-8")

        for expected_reason, result in results.items():
            with self.subTest(expected_reason=expected_reason):
                self.assertEqual(result[0], 0, result[2])
                payload = json.loads(result[1])
                self.assertFalse(payload["delivery_gate_pass"])
                self.assertIn(expected_reason, payload["rejection_reasons"])
                self.assertNotIn("Traceback", result[1] + result[2])
        self.assertEqual(reject_gate[0], 0, reject_gate[2])
        rejected = json.loads(reject_gate[1])
        self.assertFalse(rejected["delivery_gate_pass"])
        self.assertIn("closure_evidence_not_imported", rejected["rejection_reasons"])
        self.assertEqual(rejection[0], 0, rejection[2])
        rejection_payload = json.loads(rejection[1])
        self.assertTrue(rejection_payload["rejected"])
        self.assertIn("closure_evidence_not_imported", rejection_payload["rejection_reasons"])
        self.assertIn("fixed closure evidence import", rejection_payload["next_required_evidence"])
        self.assertEqual(rejection_payload["recovery_status"], "blocked_until_evidence_fixed")
        self.assertEqual(rejection_text[0], 0, rejection_text[2])
        self.assertIn("recovery_status", rejection_text_body)
        self.assertEqual(replay_rejection[0], 0, replay_rejection[2])
        replay = json.loads(replay_rejection[1])
        self.assertFalse(replay["original_readiness"])
        self.assertIn("closure_evidence_not_imported", replay["rejection_reasons"])
        self.assertEqual(replay["recovery_status"], "blocked_until_evidence_fixed")
        self.assertEqual(fixed_closure[0], 0, fixed_closure[2])
        self.assertEqual(fixed_merge[0], 0, fixed_merge[2])
        self.assertEqual(recovered_gate[0], 0, recovered_gate[2])
        recovered = json.loads(recovered_gate[1])
        self.assertTrue(recovered["delivery_gate_pass"])
        self.assertEqual(recovered["rejection_reasons"], [])
        combined = reject_gate[1] + reject_gate[2] + rejection[1] + rejection[2] + rejection_text[1] + rejection_text[2] + replay_rejection[1] + replay_rejection[2] + fixed_closure[1] + fixed_closure[2] + fixed_merge[1] + fixed_merge[2] + recovered_gate[1] + recovered_gate[2]
        self.assertNotIn("Traceback", combined)

    def test_worker_result_delivery_gate_replay_errors_and_help_are_clean(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            base = self._prepare_merge_readiness(root)
            bad_json = base / "bad-packet.json"
            bad_json.write_text("{", encoding="utf-8")
            empty = base / "empty-packet.json"
            empty.write_text("", encoding="utf-8")
            missing_marker_payload = json.loads((base / "merge-readiness.json").read_text(encoding="utf-8"))
            missing_marker_payload.pop("marker")
            (base / "missing-marker.json").write_text(json.dumps(missing_marker_payload), encoding="utf-8")
            missing = run_cli([
                "runtime", "worker-result", "delivery-gate", "--merge-readiness", ".ai/workspaces/demo/missing.json", "--out", ".ai/workspaces/demo/gate.json", "--json"
            ], root)
            malformed = run_cli([
                "runtime", "worker-result", "delivery-gate", "--merge-readiness", ".ai/workspaces/demo/bad-packet.json", "--out", ".ai/workspaces/demo/gate.json", "--json"
            ], root)
            empty_result = run_cli([
                "runtime", "worker-result", "delivery-gate", "--merge-readiness", ".ai/workspaces/demo/empty-packet.json", "--out", ".ai/workspaces/demo/gate.json", "--json"
            ], root)
            missing_marker = run_cli([
                "runtime", "worker-result", "delivery-gate", "--merge-readiness", ".ai/workspaces/demo/missing-marker.json", "--out", ".ai/workspaces/demo/gate.json", "--json"
            ], root)
            traversal = run_cli([
                "runtime", "worker-result", "delivery-gate", "--merge-readiness", ".ai/workspaces/demo/../merge-readiness.json", "--out", ".ai/workspaces/demo/gate.json", "--json"
            ], root)
            bad_replay = run_cli([
                "runtime", "worker-result", "audit-replay", "--packet", ".ai/workspaces/demo/bad-packet.json", "--json"
            ], root)

        self.assertEqual(json.loads(missing[1])["error_code"], "runtime_worker_delivery_gate_merge_readiness_missing")
        self.assertEqual(json.loads(malformed[1])["error_code"], "runtime_worker_delivery_gate_merge_readiness_invalid")
        self.assertEqual(json.loads(empty_result[1])["error_code"], "runtime_worker_delivery_gate_merge_readiness_invalid")
        self.assertEqual(json.loads(missing_marker[1])["error_code"], "runtime_worker_delivery_gate_merge_readiness_marker_missing")
        self.assertEqual(json.loads(traversal[1])["error_code"], "runtime_worker_delivery_gate_merge_readiness_path_traversal")
        self.assertEqual(json.loads(bad_replay[1])["error_code"], "runtime_worker_audit_replay_packet_invalid")
        for argv in (
            ["runtime", "worker-result", "delivery-gate", "--help"],
            ["runtime", "worker-result", "rejection-packet", "--help"],
            ["runtime", "worker-result", "audit-replay", "--help"],
        ):
            with self.subTest(argv=argv):
                stdout = io.StringIO()
                stderr = io.StringIO()
                with self.assertRaises(SystemExit) as raised, redirect_stdout(stdout), redirect_stderr(stderr):
                    cli.main(argv)
                self.assertEqual(raised.exception.code, 0)
                self.assertIn("worker-result", stdout.getvalue())
                self.assertEqual(stderr.getvalue(), "")
        combined = missing[1] + missing[2] + malformed[1] + malformed[2] + empty_result[1] + empty_result[2] + missing_marker[1] + missing_marker[2] + traversal[1] + traversal[2] + bad_replay[1] + bad_replay[2]
        self.assertNotIn("Traceback", combined)

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
        self.assertEqual(adapter["reason"], "external worker prototype is contract-only; execution refused")
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
