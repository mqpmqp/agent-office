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


class AutonomyPlanCliTests(unittest.TestCase):
    maxDiff = None

    def test_autonomy_plan_positive_json_for_all_goals(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            results = {
                goal: run_cli(["autonomy", "plan", "--goal", goal, "--json"], root)
                for goal in ["release-ops", "post-v1", "autonomous-delivery"]
            }

        for goal, result in results.items():
            with self.subTest(goal=goal):
                self.assertEqual(result[0], 0, result[1] + result[2])
                payload = json.loads(result[1])
                self.assertEqual(payload["schema_version"], 1)
                self.assertEqual(payload["packet_type"], "agentoffice_autonomy_mission_plan")
                self.assertEqual(payload["goal"], goal)
                self.assertEqual(payload["status"], "ready")
                self.assertTrue(payload["local_only"])
                self.assertFalse(payload["network_required"])
                self.assertFalse(payload["provider_runtime_adapter_external_behavior"])
                self.assertGreaterEqual(len(payload["phases"]), 1)
                self.assertGreaterEqual(len(payload["validation_commands"]), 3)
                self.assertIn(".env is never read", payload["safety_boundaries"])
                self.assertIn("phase6/mainline is not merged or mutated by autonomy commands", payload["safety_boundaries"])
                self.assertGreaterEqual(len(payload["expected_artifacts"]), 1)
                self.assertGreaterEqual(len(payload["review_handoff"]), 1)
                self.assertGreaterEqual(len(payload["merge_gate_handoff"]), 1)
                self.assertNotIn("Traceback", result[1] + result[2])

    def test_autonomy_plan_positive_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_cli(["autonomy", "plan", "--goal", "autonomous-delivery"], Path(tmpdir))

        self.assertEqual(result[0], 0, result[1] + result[2])
        self.assertIn("AGENTOFFICE_AUTONOMY_MISSION_PLAN", result[1])
        self.assertIn("goal: autonomous-delivery", result[1])
        self.assertIn("phases:", result[1])
        self.assertIn("validation_commands:", result[1])
        self.assertIn("review_handoff:", result[1])
        self.assertIn("merge_gate_handoff:", result[1])
        self.assertNotIn("Traceback", result[1] + result[2])

    def test_autonomy_plan_unknown_goal_is_clean_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_cli(["autonomy", "plan", "--goal", "unknown"], Path(tmpdir))

        self.assertEqual(result[0], 2)
        self.assertIn("unknown autonomy goal", result[2])
        self.assertNotIn("Traceback", result[1] + result[2])

    def test_autonomy_plan_json_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            first = run_cli(["autonomy", "plan", "--goal", "post-v1", "--json"], root)
            second = run_cli(["autonomy", "plan", "--goal", "post-v1", "--json"], root)

        self.assertEqual(first[0], 0, first[1] + first[2])
        self.assertEqual(second[0], 0, second[1] + second[2])
        self.assertEqual(first[1], second[1])
        self.assertNotIn("Traceback", first[1] + first[2] + second[1] + second[2])


if __name__ == "__main__":
    unittest.main()
