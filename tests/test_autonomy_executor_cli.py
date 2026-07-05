from __future__ import annotations

import io
import json
import subprocess
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


class AutonomyQueueCliTests(unittest.TestCase):
    maxDiff = None

    def test_queue_init_add_status_validate_json_and_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            queue = root / ".ai" / "autonomy" / "queues" / "demo"
            init_json = run_cli(["autonomy", "queue", "init", "--path", str(queue), "--goal", "autonomous-executor", "--json"], root)
            init_text = run_cli(["autonomy", "queue", "status", "--path", str(queue)], root)
            add_one = run_cli(["autonomy", "queue", "add", "--path", str(queue), "--id", "preflight", "--kind", "checkpoint", "--json"], root)
            add_two = run_cli(["autonomy", "queue", "add", "--path", str(queue), "--id", "validate-minimal", "--kind", "validate-suite", "--suite", "minimal", "--depends-on", "preflight", "--json"], root)
            status = run_cli(["autonomy", "queue", "status", "--path", str(queue), "--json"], root)
            validate = run_cli(["autonomy", "queue", "validate", "--path", str(queue), "--json"], root)

        for result in [init_json, init_text, add_one, add_two, status, validate]:
            self.assertEqual(result[0], 0, result[1] + result[2])
            self.assertNotIn("Traceback", result[1] + result[2])
        payload = json.loads(status[1])
        self.assertEqual(payload["queue"]["packet_type"], "agentoffice_autonomy_goal_queue")
        self.assertEqual([task["id"] for task in payload["queue"]["tasks"]], ["preflight", "validate-minimal"])
        self.assertIn("AGENTOFFICE_AUTONOMY_GOAL_QUEUE", init_text[1])
        self.assertTrue(json.loads(validate[1])["ok"])

    def test_queue_rejects_unsafe_paths_and_malformed_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            traversal = run_cli(["autonomy", "queue", "init", "--path", "../outside", "--goal", "x", "--json"], root)
            target = root / "target"
            target.mkdir()
            link = root / "link"
            link.symlink_to(target, target_is_directory=True)
            symlink = run_cli(["autonomy", "queue", "init", "--path", str(link), "--goal", "x", "--json"], root)
            bad = root / ".ai" / "autonomy" / "queues" / "bad"
            bad.mkdir(parents=True)
            (bad / "queue.json").write_text("{bad", encoding="utf-8")
            malformed = run_cli(["autonomy", "queue", "status", "--path", str(bad), "--json"], root)

        self.assertEqual(traversal[0], 2)
        self.assertIn("unsafe_path", traversal[2])
        self.assertEqual(symlink[0], 2)
        self.assertIn("symlink_refused", symlink[2])
        self.assertEqual(malformed[0], 2)
        self.assertIn("malformed_json", malformed[2])
        self.assertNotIn("Traceback", traversal[1] + traversal[2] + symlink[1] + symlink[2] + malformed[1] + malformed[2])

    def test_queue_unknown_kind_is_clean_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            queue = root / "queue"
            init = run_cli(["autonomy", "queue", "init", "--path", str(queue), "--goal", "x", "--json"], root)
            result = run_cli(["autonomy", "queue", "add", "--path", str(queue), "--id", "bad", "--kind", "shell", "--json"], root)

        self.assertEqual(init[0], 0, init[1] + init[2])
        self.assertEqual(result[0], 2)
        self.assertIn("unknown queue task kind", result[2])
        self.assertNotIn("Traceback", result[1] + result[2])


class AutonomyQueueNextCliTests(unittest.TestCase):
    def _queue(self, root: Path) -> Path:
        queue = root / "queue"
        result = run_cli(["autonomy", "queue", "init", "--path", str(queue), "--goal", "x", "--json"], root)
        self.assertEqual(result[0], 0, result[1] + result[2])
        return queue

    def test_next_linear_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            queue = self._queue(root)
            run_cli(["autonomy", "queue", "add", "--path", str(queue), "--id", "a", "--kind", "checkpoint", "--json"], root)
            run_cli(["autonomy", "queue", "add", "--path", str(queue), "--id", "b", "--kind", "noop", "--depends-on", "a", "--json"], root)
            next_result = run_cli(["autonomy", "queue", "next", "--path", str(queue), "--json"], root)

        self.assertEqual(next_result[0], 0, next_result[1] + next_result[2])
        payload = json.loads(next_result[1])
        self.assertEqual(payload["next_task"]["id"], "a")
        self.assertEqual(payload["next_action"], "run:a")

    def test_next_fan_in_fan_out_and_failed_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            queue = self._queue(root)
            for task_id in ["a", "b"]:
                run_cli(["autonomy", "queue", "add", "--path", str(queue), "--id", task_id, "--kind", "checkpoint", "--json"], root)
            run_cli(["autonomy", "queue", "add", "--path", str(queue), "--id", "c", "--kind", "noop", "--depends-on", "a", "--depends-on", "b", "--json"], root)
            data = json.loads((queue / "queue.json").read_text(encoding="utf-8"))
            data["tasks"][0]["status"] = "passed"
            data["tasks"][1]["status"] = "failed"
            (queue / "queue.json").write_text(json.dumps(data), encoding="utf-8")
            result = run_cli(["autonomy", "queue", "next", "--path", str(queue), "--json"], root)

        self.assertEqual(result[0], 0, result[1] + result[2])
        payload = json.loads(result[1])
        self.assertEqual(payload["next_action"], "blocked")
        self.assertEqual(payload["blocked_tasks"][0]["reason"], "dependency_failed")

    def test_next_cycle_and_missing_dependency_are_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            queue = self._queue(root)
            data = json.loads((queue / "queue.json").read_text(encoding="utf-8"))
            data["tasks"] = [
                {"id": "a", "kind": "noop", "status": "pending", "depends_on": ["b"], "attempts": 0, "max_attempts": 1, "created_at": None, "updated_at": None, "artifacts": [], "last_error": None},
                {"id": "b", "kind": "noop", "status": "pending", "depends_on": ["a"], "attempts": 0, "max_attempts": 1, "created_at": None, "updated_at": None, "artifacts": [], "last_error": None},
                {"id": "c", "kind": "noop", "status": "pending", "depends_on": ["missing"], "attempts": 0, "max_attempts": 1, "created_at": None, "updated_at": None, "artifacts": [], "last_error": None},
            ]
            (queue / "queue.json").write_text(json.dumps(data), encoding="utf-8")
            result = run_cli(["autonomy", "queue", "next", "--path", str(queue), "--json"], root)

        self.assertEqual(result[0], 2)
        payload = json.loads(result[1])
        self.assertTrue(any("dependency_cycle" in error for error in payload["errors"]))
        self.assertTrue(any("missing_dependency" in error for error in payload["errors"]))
        self.assertNotIn("Traceback", result[1] + result[2])


class AutonomyRunnerTemplateReportCliTests(unittest.TestCase):
    def test_run_goal_checkpoint_noop_manual_and_resume(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            queue = root / "queue"
            run_cli(["autonomy", "queue", "init", "--path", str(queue), "--goal", "x", "--json"], root)
            run_cli(["autonomy", "queue", "add", "--path", str(queue), "--id", "checkpoint", "--kind", "checkpoint", "--json"], root)
            run_cli(["autonomy", "queue", "add", "--path", str(queue), "--id", "noop", "--kind", "noop", "--depends-on", "checkpoint", "--json"], root)
            run_cli(["autonomy", "queue", "add", "--path", str(queue), "--id", "manual", "--kind", "manual", "--depends-on", "noop", "--json"], root)
            first = run_cli(["autonomy", "run-goal", "--path", str(queue), "--max-steps", "2", "--json"], root)
            second = run_cli(["autonomy", "resume", "--path", str(queue), "--max-steps", "2", "--json"], root)

        self.assertEqual(first[0], 0, first[1] + first[2])
        payload = json.loads(first[1])
        self.assertEqual([step["task_id"] for step in payload["steps"]], ["checkpoint", "noop"])
        self.assertEqual(second[0], 2)
        self.assertEqual(json.loads(second[1])["steps"][0]["failure_class"], "manual_block")
        self.assertNotIn("Traceback", first[1] + first[2] + second[1] + second[2])

    def test_failure_classification(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            retryable = run_cli(["autonomy", "classify", "--kind", "validation_failed", "--attempts", "0", "--max-attempts", "2", "--json"], root)
            unsafe = run_cli(["autonomy", "classify", "--kind", "unsafe_path", "--json"], root)
            partial = run_cli(["autonomy", "classify", "--kind", "partial_remote_state", "--json"], root)
            manual = run_cli(["autonomy", "classify", "--kind", "manual_block", "--json"], root)

        self.assertTrue(json.loads(retryable[1])["retryable"])
        self.assertFalse(json.loads(unsafe[1])["retryable"])
        self.assertFalse(json.loads(partial[1])["retryable"])
        self.assertFalse(json.loads(manual[1])["retryable"])

    def test_goal_templates_and_materialize(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            templates = [run_cli(["autonomy", "goal-template", "--name", name, "--json"], root) for name in ["release-cycle", "feature-merge", "longrun-development"]]
            queue = root / "feature"
            materialized = run_cli(["autonomy", "queue", "init", "--path", str(queue), "--template", "feature-merge", "--json"], root)

        for result in templates:
            self.assertEqual(result[0], 0, result[1] + result[2])
            self.assertGreaterEqual(len(json.loads(result[1])["tasks"]), 5)
        self.assertEqual(materialized[0], 0, materialized[1] + materialized[2])
        self.assertEqual(json.loads(materialized[1])["queue"]["tasks"][0]["id"], "checkpoint")

    def test_goal_report_and_out_safety(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            queue = root / "queue"
            run_cli(["autonomy", "queue", "init", "--path", str(queue), "--template", "longrun-development", "--json"], root)
            out = root / "goal-report.md"
            result = run_cli(["autonomy", "goal-report", "--path", str(queue), "--out", str(out), "--json"], root)
            traversal = run_cli(["autonomy", "goal-report", "--path", str(queue), "--out", "../bad.md", "--json"], root)
            target = root / "target.md"
            target.write_text("x", encoding="utf-8")
            link = root / "link.md"
            link.symlink_to(target)
            symlink = run_cli(["autonomy", "goal-report", "--path", str(queue), "--out", str(link), "--json"], root)
            report_text = out.read_text(encoding="utf-8")

        self.assertEqual(result[0], 0, result[1] + result[2])
        self.assertIn("AgentOffice Autonomy Goal Report", report_text)
        self.assertEqual(traversal[0], 2)
        self.assertIn("unsafe_path", traversal[2])
        self.assertEqual(symlink[0], 2)
        self.assertIn("symlink_refused", symlink[2])

    def test_runner_validate_suite_uses_local_validation_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            queue = root / "queue"
            run_cli(["autonomy", "queue", "init", "--path", str(queue), "--goal", "validation", "--json"], root)
            run_cli(["autonomy", "queue", "add", "--path", str(queue), "--id", "validate-minimal", "--kind", "validate-suite", "--suite", "minimal", "--json"], root)
            with patch("agent_office.autonomy_executor.autonomy_validate_payload") as validate:
                def fake_validate(path: str, suite: str, project_root: Path) -> dict[str, object]:
                    validation_dir = Path(path) / "validation" / "fake"
                    validation_dir.mkdir(parents=True)
                    stdout = validation_dir / "stdout.txt"
                    stderr = validation_dir / "stderr.txt"
                    stdout.write_text("ok", encoding="utf-8")
                    stderr.write_text("", encoding="utf-8")
                    return {
                        "ok": True,
                        "validation": {
                            "commands": [
                                {"stdout_path": str(stdout), "stderr_path": str(stderr), "exit_code": 0}
                            ]
                        },
                    }

                validate.side_effect = fake_validate
                result = run_cli(["autonomy", "run-goal", "--path", str(queue), "--max-steps", "1", "--json"], root)
                ledger_exists = (queue / "validation-ledgers" / "validate-minimal" / "ledger.json").exists()

        self.assertEqual(result[0], 0, result[1] + result[2])
        payload = json.loads(result[1])
        self.assertEqual(payload["steps"][0]["task_id"], "validate-minimal")
        self.assertTrue(ledger_exists)
        self.assertTrue(any(artifact["type"] == "validation_ledger" for artifact in payload["queue"]["artifacts"]))

    def test_runner_release_state_and_github_plan_are_local_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            queue = root / "queue"
            run_cli(["autonomy", "queue", "init", "--path", str(queue), "--goal", "release", "--json"], root)
            run_cli(["autonomy", "queue", "add", "--path", str(queue), "--id", "release-state", "--kind", "release-state", "--json"], root)
            run_cli(["autonomy", "queue", "add", "--path", str(queue), "--id", "github-plan", "--kind", "github-release-plan", "--depends-on", "release-state", "--json"], root)
            result = run_cli(["autonomy", "run-goal", "--path", str(queue), "--max-steps", "2", "--json"], root)

        self.assertEqual(result[0], 0, result[1] + result[2])
        payload = json.loads(result[1])
        self.assertEqual([step["task_id"] for step in payload["steps"]], ["release-state", "github-plan"])
        self.assertTrue(any(artifact["type"] == "release-state" for artifact in payload["queue"]["artifacts"]))
        self.assertTrue(any(artifact["type"] == "github-release-plan" for artifact in payload["queue"]["artifacts"]))


if __name__ == "__main__":
    unittest.main()
