from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from agent_office import cli
from agent_office.run_bundle import RUN_BUNDLE_REQUIRED_FILES, run_bundle_preview_payload


PACKET_ACTORS = ("codex", "reviewer", "judge")


def run_cli(argv: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = cli.main(argv)
    return exit_code, stdout.getvalue(), stderr.getvalue()


class RunBundlePayloadTests(unittest.TestCase):
    maxDiff = None

    def test_static_run_bundle_preview_contract(self) -> None:
        payload = run_bundle_preview_payload("P6-17", "lowest-cost", "P7-STATIC-RUN")

        self.assertEqual(payload["kind"], "static_run_bundle")
        self.assertEqual(payload["schema_version"], 1)
        self.assertFalse(payload["execution_enabled"])
        self.assertEqual(payload["provider_calls"], [])
        self.assertFalse(payload["runtime_calls"])
        self.assertFalse(payload["adapter_calls"])
        self.assertFalse(payload["env_required"])
        self.assertFalse(payload["artifact_writes"])
        run = payload["run"]
        self.assertIsInstance(run, dict)
        self.assertEqual(run["run_id"], "P7-STATIC-RUN")
        self.assertEqual(run["objective"]["id"], "P6-17")
        self.assertEqual(run["profile"]["selected"], "lowest-cost")
        self.assertFalse(run["execution_enabled"])
        self.assertEqual(run["provider_calls"], [])
        self.assertEqual(run["actors"], list(PACKET_ACTORS))
        self.assertEqual(payload["plan"]["objective_id"], "P6-17")
        self.assertEqual(payload["plan"]["selected_profile"], "lowest-cost")
        self.assertEqual(tuple(payload["packets"]), PACKET_ACTORS)
        self.assertEqual(payload["validation"]["required_files"], list(RUN_BUNDLE_REQUIRED_FILES))
        self.assertTrue(payload["validation"]["valid"])
        json.dumps(payload)

    def test_unknown_inputs_raise_clear_errors(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown objective: UNKNOWN"):
            run_bundle_preview_payload("UNKNOWN", "lowest-cost", "BAD")
        with self.assertRaisesRegex(ValueError, "Unknown provider profile: UNKNOWN"):
            run_bundle_preview_payload("P6-17", "UNKNOWN", "BAD")


class RunBundleCliTests(unittest.TestCase):
    maxDiff = None

    def test_run_bundle_preview_action_accepts_profiles_smoke_alias_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            first_code, first_stdout, first_stderr = run_cli(
                [
                    "run-bundle",
                    "preview",
                    "--objective",
                    "P6-PROFILES",
                    "--profile",
                    "lowest-cost",
                    "--json",
                ]
            )
            second_code, second_stdout, second_stderr = run_cli(
                [
                    "run-bundle",
                    "preview",
                    "--objective",
                    "P6-PROFILES",
                    "--profile",
                    "lowest-cost",
                    "--json",
                ]
            )
            self.assertFalse((Path(tmpdir) / ".ai").exists())

        self.assertEqual(first_code, 0, first_stderr)
        self.assertEqual(second_code, 0, second_stderr)
        self.assertEqual(first_stdout, second_stdout)
        payload = json.loads(first_stdout)
        self.assertEqual(payload["kind"], "static_run_bundle")
        self.assertEqual(payload["run"]["run_id"], "P6-PROFILES")
        self.assertEqual(payload["run"]["objective"]["id"], "P6-17")
        self.assertEqual(payload["plan"]["objective_id"], "P6-17")
        self.assertEqual(payload["plan"]["selected_profile"], "lowest-cost")
        self.assertFalse(payload["execution_enabled"])
        self.assertEqual(payload["provider_calls"], [])
        self.assertFalse(payload["artifact_writes"])
        self.assertEqual(payload["validation"]["required_files"], list(RUN_BUNDLE_REQUIRED_FILES))
        self.assertTrue(payload["validation"]["valid"])

    def test_run_bundle_implicit_build_rejects_profiles_smoke_alias_without_traceback(self) -> None:
        exit_code, stdout, stderr = run_cli(
            [
                "run-bundle",
                "--objective",
                "P6-PROFILES",
                "--profile",
                "lowest-cost",
                "--run-id",
                "MYBUILD",
                "--json",
            ]
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("Unknown objective: P6-PROFILES", stderr)
        self.assertNotIn("Traceback", stderr)

    def test_run_bundle_preview_action_writes_full_bundle_and_reports_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            exit_code, stdout, stderr = run_cli(
                [
                    "run-bundle",
                    "preview",
                    "--objective",
                    "P6-17",
                    "--profile",
                    "lowest-cost",
                    "--out",
                    ".ai/runs/P8-PREVIEW-FIX",
                    "--json",
                ]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            out_root = Path(tmpdir) / ".ai" / "runs" / "P8-PREVIEW-FIX"
            for relative in RUN_BUNDLE_REQUIRED_FILES:
                self.assertTrue((out_root / relative).is_file(), relative)

        self.assertTrue(payload["artifact_writes"])
        self.assertTrue(payload["write_result"]["enabled"])
        self.assertEqual(payload["write_result"]["files_written"], list(RUN_BUNDLE_REQUIRED_FILES))
        self.assertEqual(payload["run"]["run_id"], "P6-17")
        self.assertEqual(payload["run"]["objective"]["id"], "P6-17")

    def test_run_bundle_preview_action_preserves_explicit_run_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            exit_code, stdout, stderr = run_cli(
                [
                    "run-bundle",
                    "preview",
                    "--objective",
                    "P6-17",
                    "--profile",
                    "lowest-cost",
                    "--run-id",
                    "CUSTOM-RID",
                    "--json",
                ]
            )
            self.assertFalse((Path(tmpdir) / ".ai").exists())

        self.assertEqual(exit_code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["run"]["run_id"], "CUSTOM-RID")
        self.assertEqual(payload["run"]["objective"]["id"], "P6-17")
        self.assertFalse(payload["artifact_writes"])

    def test_run_bundle_preview_action_requires_objective_and_profile_without_traceback(self) -> None:
        exit_code, stdout, stderr = run_cli(["run-bundle", "preview", "--objective", "P6-PROFILES", "--json"])

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("run-bundle preview requires --objective and --profile", stderr)
        self.assertNotIn("Traceback", stderr)

    def test_run_bundle_json_preview_does_not_write_ai_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            exit_code, stdout, stderr = run_cli(
                [
                    "run-bundle",
                    "--objective",
                    "P6-17",
                    "--profile",
                    "lowest-cost",
                    "--run-id",
                    "P7-STATIC-RUN",
                    "--json",
                ]
            )

            self.assertEqual(exit_code, 0, stderr)
            self.assertFalse((Path(tmpdir) / ".ai").exists())
        payload = json.loads(stdout)
        self.assertEqual(payload, run_bundle_preview_payload("P6-17", "lowest-cost", "P7-STATIC-RUN"))

    def test_run_bundle_out_writes_required_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            exit_code, stdout, stderr = run_cli(
                [
                    "run-bundle",
                    "--objective",
                    "P6-17",
                    "--profile",
                    "lowest-cost",
                    "--run-id",
                    "P7-STATIC-RUN",
                    "--out",
                    ".ai/runs/P7-STATIC-RUN",
                ]
            )

            self.assertEqual(exit_code, 0, stderr)
            self.assertIn("AgentOffice static run bundle", stdout)
            out_root = Path(tmpdir) / ".ai" / "runs" / "P7-STATIC-RUN"
            for relative in RUN_BUNDLE_REQUIRED_FILES:
                self.assertTrue((out_root / relative).is_file(), relative)
            run = json.loads((out_root / "run.json").read_text(encoding="utf-8"))
            self.assertEqual(run["run_id"], "P7-STATIC-RUN")
            self.assertEqual(run["objective"]["id"], "P6-17")
            self.assertEqual(run["profile"]["selected"], "lowest-cost")
            self.assertFalse(run["execution_enabled"])
            self.assertEqual(run["provider_calls"], [])
            self.assertEqual(run["actors"], list(PACKET_ACTORS))

    def test_run_bundle_out_json_writes_and_reports_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            exit_code, stdout, stderr = run_cli(
                [
                    "run-bundle",
                    "--objective",
                    "P6-17",
                    "--profile",
                    "lowest-cost",
                    "--run-id",
                    "P7-STATIC-RUN",
                    "--out",
                    ".ai/runs/P7-STATIC-RUN",
                    "--json",
                ]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertTrue(payload["write_result"]["enabled"])
            self.assertTrue(payload["artifact_writes"])
            self.assertEqual(payload["write_result"]["files_written"], list(RUN_BUNDLE_REQUIRED_FILES))
            self.assertTrue((Path(tmpdir) / ".ai" / "runs" / "P7-STATIC-RUN" / "validation.json").is_file())

    def test_run_bundle_unknown_objective_exits_two_without_traceback(self) -> None:
        exit_code, stdout, stderr = run_cli(
            ["run-bundle", "--objective", "UNKNOWN", "--profile", "lowest-cost", "--run-id", "BAD", "--json"]
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("Unknown objective: UNKNOWN", stderr)
        self.assertNotIn("Traceback", stderr)

    def test_run_bundle_unknown_profile_exits_two_without_traceback(self) -> None:
        exit_code, stdout, stderr = run_cli(
            ["run-bundle", "--objective", "P6-17", "--profile", "UNKNOWN", "--run-id", "BAD", "--json"]
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("Unknown provider profile: UNKNOWN", stderr)
        self.assertNotIn("Traceback", stderr)


class RunBundleInspectValidateCliTests(unittest.TestCase):
    maxDiff = None

    def _write_bundle(self, project_root: Path) -> Path:
        exit_code, _stdout, stderr = run_cli(
            [
                "run-bundle",
                "--objective",
                "P6-17",
                "--profile",
                "lowest-cost",
                "--run-id",
                "P7-STATIC-RUN",
                "--out",
                ".ai/runs/P7-STATIC-RUN",
            ]
        )
        self.assertEqual(exit_code, 0, stderr)
        return project_root / ".ai" / "runs" / "P7-STATIC-RUN"

    def test_run_bundle_inspect_and_validate_text_and_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            self._write_bundle(Path(tmpdir))

            inspect_code, inspect_stdout, inspect_stderr = run_cli(
                ["run-bundle", "inspect", "--path", ".ai/runs/P7-STATIC-RUN"]
            )
            self.assertEqual(inspect_code, 0, inspect_stderr)
            self.assertIn("AgentOffice static run bundle inspection", inspect_stdout)
            self.assertIn("run_id: P7-STATIC-RUN", inspect_stdout)
            self.assertIn("packets/judge.json: present", inspect_stdout)

            inspect_json_code, inspect_json_stdout, inspect_json_stderr = run_cli(
                ["run-bundle", "inspect", "--path", ".ai/runs/P7-STATIC-RUN", "--json"]
            )
            self.assertEqual(inspect_json_code, 0, inspect_json_stderr)
            inspection = json.loads(inspect_json_stdout)
            self.assertEqual(inspection["kind"], "static_run_bundle_inspection")
            self.assertEqual(inspection["run_id"], "P7-STATIC-RUN")
            self.assertEqual(inspection["objective"]["id"], "P6-17")
            self.assertEqual(inspection["profile"]["selected"], "lowest-cost")
            self.assertFalse(inspection["execution_enabled"])
            self.assertEqual(inspection["provider_calls"], [])
            self.assertEqual(inspection["actors"], list(PACKET_ACTORS))

            validate_code, validate_stdout, validate_stderr = run_cli(
                ["run-bundle", "validate", "--path", ".ai/runs/P7-STATIC-RUN"]
            )
            self.assertEqual(validate_code, 0, validate_stderr)
            self.assertIn("AgentOffice static run bundle validation", validate_stdout)
            self.assertIn("valid: true", validate_stdout)
            self.assertIn("execution_enabled_false: pass", validate_stdout)

            validate_json_code, validate_json_stdout, validate_json_stderr = run_cli(
                ["run-bundle", "validate", "--path", ".ai/runs/P7-STATIC-RUN", "--json"]
            )
            self.assertEqual(validate_json_code, 0, validate_json_stderr)
            validation = json.loads(validate_json_stdout)
            self.assertEqual(validation["kind"], "static_run_bundle_validation_result")
            self.assertTrue(validation["valid"])
            self.assertEqual(validation["run_id"], "P7-STATIC-RUN")
            self.assertEqual(validation["objective"], "P6-17")
            self.assertEqual(validation["profile"], "lowest-cost")
            self.assertEqual(validation["external_behavior"]["artifact_writes"], False)

    def test_run_bundle_list_and_status_text_and_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            self._write_bundle(Path(tmpdir))

            list_code, list_stdout, list_stderr = run_cli(["run-bundle", "list", "--root", ".ai/runs"])
            self.assertEqual(list_code, 0, list_stderr)
            self.assertIn("AgentOffice static run bundle catalog", list_stdout)
            self.assertIn("P7-STATIC-RUN: ready", list_stdout)

            list_json_code, list_json_stdout, list_json_stderr = run_cli(
                ["run-bundle", "list", "--root", ".ai/runs", "--json"]
            )
            self.assertEqual(list_json_code, 0, list_json_stderr)
            catalog = json.loads(list_json_stdout)
            self.assertEqual(catalog["kind"], "static_run_bundle_catalog")
            self.assertEqual(catalog["count"], 1)
            self.assertEqual(catalog["bundles"][0]["run_id"], "P7-STATIC-RUN")
            self.assertEqual(catalog["bundles"][0]["status"], "ready")

            status_code, status_stdout, status_stderr = run_cli(
                ["run-bundle", "status", "--path", ".ai/runs/P7-STATIC-RUN"]
            )
            self.assertEqual(status_code, 0, status_stderr)
            self.assertIn("AgentOffice static run bundle status", status_stdout)
            self.assertIn("run_id: P7-STATIC-RUN", status_stdout)
            self.assertIn("status: ready", status_stdout)

            status_json_code, status_json_stdout, status_json_stderr = run_cli(
                ["run-bundle", "status", "--path", ".ai/runs/P7-STATIC-RUN", "--json"]
            )
            self.assertEqual(status_json_code, 0, status_json_stderr)
            status = json.loads(status_json_stdout)
            self.assertEqual(status["kind"], "static_run_bundle_status")
            self.assertEqual(status["run_id"], "P7-STATIC-RUN")
            self.assertEqual(status["objective"]["id"], "P6-17")
            self.assertEqual(status["profile"]["selected"], "lowest-cost")
            self.assertEqual(status["actors"], list(PACKET_ACTORS))
            self.assertFalse(status["execution_enabled"])
            self.assertEqual(status["provider_calls"], [])
            self.assertEqual(status["required_files"], list(RUN_BUNDLE_REQUIRED_FILES))
            self.assertEqual(status["status"], "ready")
            self.assertEqual(status["errors"], [])
            self.assertFalse(status["external_behavior"]["artifact_writes"])

    def test_run_bundle_list_missing_root_exits_two_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            exit_code, stdout, stderr = run_cli(["run-bundle", "list", "--root", ".ai/runs", "--json"])

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("Run bundle root is not a directory", stderr)
        self.assertNotIn("Traceback", stderr)

    def test_run_bundle_status_missing_path_exits_two_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            exit_code, stdout, stderr = run_cli(["run-bundle", "status", "--path", ".ai/runs/MISSING", "--json"])

        self.assertEqual(exit_code, 2)
        self.assertEqual(stderr, "")
        status = json.loads(stdout)
        self.assertEqual(status["status"], "invalid")
        self.assertIn("Run bundle path is not a directory", status["errors"][0])
        self.assertNotIn("Traceback", stdout)

    def test_run_bundle_status_bad_bundle_exits_two_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            bundle = self._write_bundle(Path(tmpdir))
            (bundle / "packets" / "judge.json").unlink()
            exit_code, stdout, stderr = run_cli(["run-bundle", "status", "--path", ".ai/runs/P7-STATIC-RUN", "--json"])

        self.assertEqual(exit_code, 2)
        self.assertEqual(stderr, "")
        status = json.loads(stdout)
        self.assertEqual(status["status"], "invalid")
        self.assertIn("Missing run bundle file: packets/judge.json", status["errors"])
        self.assertNotIn("Traceback", stdout)

    def _write_artifact(self, project_root: Path, relative: str, content: str = "artifact") -> Path:
        artifact = project_root / relative
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text(content, encoding="utf-8")
        return artifact

    def assert_exit_two_without_traceback(self, argv: list[str]) -> tuple[str, str]:
        exit_code, stdout, stderr = run_cli(argv)
        self.assertEqual(exit_code, 2)
        self.assertNotIn("Traceback", stdout)
        self.assertNotIn("Traceback", stderr)
        return stdout, stderr

    def test_run_bundle_intake_results_and_status_json_for_all_actors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            project_root = Path(tmpdir)
            bundle = self._write_bundle(project_root)
            expected_hashes = {}

            for actor in PACKET_ACTORS:
                content = f"{actor} local result artifact"
                artifact = self._write_artifact(project_root, f"artifacts/{actor}.txt", content)
                expected_hashes[actor] = hashlib.sha256(content.encode("utf-8")).hexdigest()
                exit_code, stdout, stderr = run_cli(
                    [
                        "run-bundle",
                        "intake",
                        "--path",
                        ".ai/runs/P7-STATIC-RUN",
                        "--actor",
                        actor,
                        "--artifact",
                        str(artifact.relative_to(project_root)),
                        "--json",
                    ]
                )

                self.assertEqual(exit_code, 0, stderr)
                payload = json.loads(stdout)
                self.assertEqual(payload["kind"], "static_actor_result_intake")
                self.assertEqual(payload["actor"], actor)
                self.assertFalse(payload["execution_enabled"])
                self.assertEqual(payload["provider_calls"], [])
                self.assertFalse(payload["external_behavior"]["provider_calls"])
                self.assertFalse(payload["external_behavior"]["runtime_calls"])
                self.assertFalse(payload["external_behavior"]["adapter_calls"])
                self.assertTrue(payload["external_behavior"]["artifact_writes"])
                self.assertEqual(payload["result"]["artifact"]["path"], f"artifacts/{actor}.txt")
                self.assertEqual(payload["result"]["artifact"]["sha256"], expected_hashes[actor])
                self.assertTrue((bundle / "results" / f"{actor}.json").is_file())

            results_code, results_stdout, results_stderr = run_cli(
                ["run-bundle", "results", "--path", ".ai/runs/P7-STATIC-RUN", "--json"]
            )
            self.assertEqual(results_code, 0, results_stderr)
            results_payload = json.loads(results_stdout)
            self.assertEqual(results_payload["kind"], "static_actor_results")
            self.assertFalse(results_payload["execution_enabled"])
            self.assertEqual(results_payload["provider_calls"], [])
            self.assertFalse(results_payload["external_behavior"]["artifact_writes"])
            self.assertEqual([item["actor"] for item in results_payload["results"]], list(PACKET_ACTORS))
            self.assertEqual(results_payload["result_presence"], {actor: True for actor in PACKET_ACTORS})

            status_code, status_stdout, status_stderr = run_cli(
                ["run-bundle", "status", "--path", ".ai/runs/P7-STATIC-RUN", "--json"]
            )
            self.assertEqual(status_code, 0, status_stderr)
            status_payload = json.loads(status_stdout)
            self.assertEqual(status_payload["status"], "ready")
            self.assertEqual(status_payload["result_presence"], {actor: True for actor in PACKET_ACTORS})

    def test_run_bundle_status_list_and_results_do_not_write_result_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            project_root = Path(tmpdir)
            bundle = self._write_bundle(project_root)
            self.assertFalse((bundle / "results").exists())

            commands = [
                ["run-bundle", "status", "--path", ".ai/runs/P7-STATIC-RUN", "--json"],
                ["run-bundle", "list", "--root", ".ai/runs", "--json"],
                ["run-bundle", "handoff", "--path", ".ai/runs/P7-STATIC-RUN", "--json"],
                ["run-bundle", "review", "--path", ".ai/runs/P7-STATIC-RUN", "--json"],
                ["run-bundle", "results", "--path", ".ai/runs/P7-STATIC-RUN", "--json"],
            ]
            for command in commands:
                exit_code, _stdout, stderr = run_cli(command)
                self.assertEqual(exit_code, 0, stderr)

            self.assertFalse((bundle / "results").exists())

    def test_run_bundle_handoff_json_contract_is_static_and_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            project_root = Path(tmpdir)
            bundle = self._write_bundle(project_root)
            before = self._bundle_file_snapshot(bundle)

            first_code, first_stdout, first_stderr = run_cli(
                ["run-bundle", "handoff", "--path", ".ai/runs/P7-STATIC-RUN", "--json"]
            )
            second_code, second_stdout, second_stderr = run_cli(
                ["run-bundle", "handoff", "--path", ".ai/runs/P7-STATIC-RUN", "--json"]
            )
            after = self._bundle_file_snapshot(bundle)

        self.assertEqual(first_code, 0, first_stderr)
        self.assertEqual(second_code, 0, second_stderr)
        self.assertEqual(first_stdout, second_stdout)
        self.assertEqual(before, after)
        payload = json.loads(first_stdout)
        self.assertEqual(
            list(payload),
            [
                "kind",
                "handoff_schema_version",
                "schema_version",
                "path",
                "run_id",
                "objective",
                "profile",
                "objective_summary",
                "profile_summary",
                "required_files",
                "expected_files",
                "files",
                "actor_packet_identities",
                "actor_readiness",
                "result_presence",
                "validation_commands",
                "execution_enabled",
                "provider_calls",
                "execution_boundary",
                "safety_flags",
                "external_behavior_triggered",
                "artifact_content_executed",
                "read_only",
                "non_goals",
                "reviewer_guidance",
                "judge_guidance",
                "external_behavior",
            ],
        )
        self.assertEqual(payload["kind"], "static_run_bundle_handoff")
        self.assertEqual(payload["handoff_schema_version"], 1)
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["run_id"], "P7-STATIC-RUN")
        self.assertEqual(payload["objective"]["id"], "P6-17")
        self.assertEqual(payload["profile"]["selected"], "lowest-cost")
        self.assertEqual(payload["required_files"], list(RUN_BUNDLE_REQUIRED_FILES))
        self.assertEqual(payload["expected_files"], list(RUN_BUNDLE_REQUIRED_FILES))
        self.assertEqual(list(payload["actor_packet_identities"]), list(PACKET_ACTORS))
        self.assertEqual(list(payload["actor_readiness"]), list(PACKET_ACTORS))
        for actor in PACKET_ACTORS:
            self.assertEqual(payload["actor_packet_identities"][actor]["actor"], actor)
            self.assertEqual(payload["actor_packet_identities"][actor]["objective"], "P6-17")
            self.assertEqual(payload["actor_packet_identities"][actor]["profile"], "lowest-cost")
            self.assertTrue(payload["actor_readiness"][actor]["packet_present"])
            self.assertTrue(payload["actor_readiness"][actor]["ready_for_reviewer"])
            self.assertFalse(payload["actor_readiness"][actor]["result_present"])
            self.assertFalse(payload["actor_readiness"][actor]["ready_for_judge"])
        self.assertEqual(payload["result_presence"], {actor: False for actor in PACKET_ACTORS})
        self.assertIn("python3 -m agent_office run-bundle validate --path .ai/runs/P7-STATIC-RUN --json", payload["validation_commands"])
        self.assertFalse(payload["execution_enabled"])
        self.assertEqual(payload["provider_calls"], [])
        self.assertFalse(payload["execution_boundary"]["external_behavior_triggered"])
        self.assertFalse(payload["execution_boundary"]["artifact_content_executed"])
        self.assertTrue(payload["safety_flags"]["read_only"])
        self.assertTrue(payload["safety_flags"]["no_env_read_expected"])
        self.assertTrue(payload["safety_flags"]["no_provider_runtime_adapter_expected"])
        self.assertTrue(payload["read_only"])
        self.assertFalse(payload["external_behavior"]["artifact_writes"])
        self.assertIn("Do not execute actors from this handoff.", payload["non_goals"])
        self.assertIn("Confirm required files and actor result presence before review.", payload["reviewer_guidance"])
        self.assertIn("Decide only from static bundle evidence and reviewer findings.", payload["judge_guidance"])

    def test_run_bundle_handoff_text_contract_is_static_and_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            project_root = Path(tmpdir)
            bundle = self._write_bundle(project_root)
            before = self._bundle_file_snapshot(bundle)

            first_code, first_stdout, first_stderr = run_cli(["run-bundle", "handoff", "--path", ".ai/runs/P7-STATIC-RUN"])
            second_code, second_stdout, second_stderr = run_cli(["run-bundle", "handoff", "--path", ".ai/runs/P7-STATIC-RUN"])
            after = self._bundle_file_snapshot(bundle)

        self.assertEqual(first_code, 0, first_stderr)
        self.assertEqual(second_code, 0, second_stderr)
        self.assertEqual(first_stdout, second_stdout)
        self.assertEqual(before, after)
        lines = first_stdout.rstrip("\n").splitlines()
        self.assertEqual(
            lines,
            [
                "AgentOffice static run bundle handoff",
                "schema_version: 1",
                "handoff_schema_version: 1",
                f"path: {bundle}",
                "run_id: P7-STATIC-RUN",
                "objective: P6-17 - Static Objective Registry Extension",
                "profile: lowest-cost (default=lowest-cost; is_default=true)",
                "objective_summary: Add P6-17 as a static objective spec that proves the multi-objective registry can extend objectives, plan, packet, packet validation, and packet golden fixtures without file discovery, environment reads, provider calls, runtime calls, adapter calls, or artifact writes.",
                "required_files:",
                "  - run.json",
                "  - plan.json",
                "  - packets/codex.json",
                "  - packets/reviewer.json",
                "  - packets/judge.json",
                "  - validation.json",
                "  - README.md",
                "expected_files:",
                "  - run.json",
                "  - plan.json",
                "  - packets/codex.json",
                "  - packets/reviewer.json",
                "  - packets/judge.json",
                "  - validation.json",
                "  - README.md",
                "file_summary:",
                "  - run.json: present; kind=json; parsed=true",
                "  - plan.json: present; kind=json; parsed=true",
                "  - packets/codex.json: present; kind=json; parsed=true",
                "  - packets/reviewer.json: present; kind=json; parsed=true",
                "  - packets/judge.json: present; kind=json; parsed=true",
                "  - validation.json: present; kind=json; parsed=true",
                "  - README.md: present; kind=markdown; parsed=true",
                "actor_packet_identities:",
                "  - codex: packet_version=1; objective=P6-17; profile=lowest-cost; execution_enabled=false; env_required=false; runtime_calls=false; adapter_calls=false",
                "  - reviewer: packet_version=1; objective=P6-17; profile=lowest-cost; execution_enabled=false; env_required=false; runtime_calls=false; adapter_calls=false",
                "  - judge: packet_version=1; objective=P6-17; profile=lowest-cost; execution_enabled=false; env_required=false; runtime_calls=false; adapter_calls=false",
                "actor_readiness:",
                "  - codex: packet_present=true; result_present=false; ready_for_reviewer=true; ready_for_judge=false",
                "  - reviewer: packet_present=true; result_present=false; ready_for_reviewer=true; ready_for_judge=false",
                "  - judge: packet_present=true; result_present=false; ready_for_reviewer=true; ready_for_judge=false",
                "result_presence:",
                "  - codex: false",
                "  - reviewer: false",
                "  - judge: false",
                "validation_commands:",
                "  - python3 -m compileall agent_office tests",
                "  - python3 -m unittest",
                "  - python3 -m unittest discover -s tests -p 'test_*.py'",
                "  - python3 -m agent_office doctor --adapters",
                "  - ./scripts/verify.sh",
                "  - ./scripts/smoke-test.sh P6-PROFILES",
                "  - python3 -m agent_office run-staged P6-PROFILES --dry-run --reset",
                "  - python3 -m agent_office objectives --validate --json",
                "  - python3 -m agent_office objectives --phase P6-17",
                "  - python3 -m agent_office objectives --phase P6-17 --json",
                "  - python3 -m agent_office objectives --show P6-17",
                "  - python3 -m agent_office objectives --show P6-17 --json",
                "  - python3 -m agent_office plan --objective P6-17 --profile lowest-cost",
                "  - python3 -m agent_office plan --objective P6-17 --profile lowest-cost --json",
                "  - python3 -m agent_office packet --objective P6-17 --profile lowest-cost --actor codex --json",
                "  - python3 -m agent_office packet --objective P6-17 --profile lowest-cost --actor reviewer --json",
                "  - python3 -m agent_office packet --objective P6-17 --profile lowest-cost --actor judge --json",
                "  - python3 -m agent_office packet --objective P6-17 --profile lowest-cost --actor codex --validate --json",
                "  - python3 -m agent_office packet --objective P6-17 --profile lowest-cost --actor reviewer --validate --json",
                "  - python3 -m agent_office packet --objective P6-17 --profile lowest-cost --actor judge --validate --json",
                "  - python3 -m agent_office objectives --validate",
                "  - python3 -m agent_office run-bundle validate --path .ai/runs/P7-STATIC-RUN --json",
                "  - python3 -m agent_office run-bundle status --path .ai/runs/P7-STATIC-RUN --json",
                "  - python3 -m agent_office run-bundle handoff --path .ai/runs/P7-STATIC-RUN --json",
                "execution_boundary:",
                "  execution_enabled: false",
                "  provider_calls: []",
                "  runtime_calls: false",
                "  adapter_calls: false",
                "  real_runner: false",
                "  external_behavior_triggered: false",
                "  artifact_content_executed: false",
                "safety_flags:",
                "  no_env_read_expected: true",
                "  no_env_vars_printed_expected: true",
                "  no_provider_runtime_adapter_expected: true",
                "  no_real_runner_expected: true",
                "  read_only: true",
                "reviewer_guidance:",
                "  - Confirm required files and actor result presence before review.",
                "  - Use validation_commands as the local read-only review checklist.",
                "  - Report missing or invalid evidence without modifying the bundle.",
                "judge_guidance:",
                "  - Decide only from static bundle evidence and reviewer findings.",
                "  - Reject or request changes if required files, actor readiness, or safety flags are incomplete.",
                "external_behavior:",
                "  env_reads: false",
                "  env_var_printing: false",
                "  provider_calls: false",
                "  runtime_calls: false",
                "  adapter_calls: false",
                "  artifact_writes: false",
                "  real_runner: false",
                "read_only: true",
                "artifact_content_executed: false",
                "provider/runtime/adapter execution: not triggered",
            ],
        )

    def test_run_bundle_handoff_text_reports_result_presence_without_reading_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            project_root = Path(tmpdir)
            self._write_bundle(project_root)
            expected_hashes = {}
            for actor in PACKET_ACTORS:
                content = f"{actor} result"
                artifact = self._write_artifact(project_root, f"artifacts/{actor}.txt", content)
                expected_hashes[actor] = hashlib.sha256(content.encode("utf-8")).hexdigest()
                exit_code, _stdout, stderr = run_cli(
                    [
                        "run-bundle",
                        "intake",
                        "--path",
                        ".ai/runs/P7-STATIC-RUN",
                        "--actor",
                        actor,
                        "--artifact",
                        str(artifact.relative_to(project_root)),
                        "--json",
                    ]
                )
                self.assertEqual(exit_code, 0, stderr)
                artifact.unlink()

            exit_code, stdout, stderr = run_cli(["run-bundle", "handoff", "--path", ".ai/runs/P7-STATIC-RUN"])

        self.assertEqual(exit_code, 0, stderr)
        for actor in PACKET_ACTORS:
            self.assertIn(
                f"  - {actor}: packet_present=true; result_present=true; ready_for_reviewer=true; ready_for_judge=true",
                stdout,
            )
            self.assertIn(f"  - {actor}: true", stdout)
            self.assertIn(f"path=artifacts/{actor}.txt", stdout)
            self.assertIn(f"sha256={expected_hashes[actor]}", stdout)

    def test_run_bundle_handoff_reports_result_presence_without_reading_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            project_root = Path(tmpdir)
            self._write_bundle(project_root)
            artifacts = []
            for actor in PACKET_ACTORS:
                artifact = self._write_artifact(project_root, f"artifacts/{actor}.txt", f"{actor} result")
                artifacts.append(artifact)
                exit_code, _stdout, stderr = run_cli(
                    [
                        "run-bundle",
                        "intake",
                        "--path",
                        ".ai/runs/P7-STATIC-RUN",
                        "--actor",
                        actor,
                        "--artifact",
                        str(artifact.relative_to(project_root)),
                        "--json",
                    ]
                )
                self.assertEqual(exit_code, 0, stderr)
            for artifact in artifacts:
                artifact.unlink()

            exit_code, stdout, stderr = run_cli(["run-bundle", "handoff", "--path", ".ai/runs/P7-STATIC-RUN", "--json"])

        self.assertEqual(exit_code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["result_presence"], {actor: True for actor in PACKET_ACTORS})
        for actor in PACKET_ACTORS:
            self.assertTrue(payload["actor_readiness"][actor]["result_present"])
            self.assertTrue(payload["actor_readiness"][actor]["ready_for_judge"])
            self.assertIn("artifact", payload["actor_readiness"][actor])

    def test_run_bundle_review_json_contract_is_static_and_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            project_root = Path(tmpdir)
            bundle = self._write_bundle(project_root)
            before = self._bundle_file_snapshot(bundle)

            first_code, first_stdout, first_stderr = run_cli(
                ["run-bundle", "review", "--path", ".ai/runs/P7-STATIC-RUN", "--json"]
            )
            second_code, second_stdout, second_stderr = run_cli(
                ["run-bundle", "review", "--path", ".ai/runs/P7-STATIC-RUN", "--json"]
            )
            after = self._bundle_file_snapshot(bundle)

        self.assertEqual(first_code, 0, first_stderr)
        self.assertEqual(second_code, 0, second_stderr)
        self.assertEqual(first_stdout, second_stdout)
        self.assertEqual(before, after)
        payload = json.loads(first_stdout)
        self.assertEqual(
            list(payload),
            [
                "kind",
                "review_schema_version",
                "schema_version",
                "path",
                "run_id",
                "objective",
                "profile",
                "review_goal",
                "readiness",
                "required_review_files",
                "actor_evidence",
                "validation",
                "status",
                "reviewer_commands",
                "reviewer_contract",
                "safety_flags",
                "execution_boundary",
                "external_behavior",
                "read_only",
                "execution_enabled",
                "provider_calls",
                "known_limitations",
            ],
        )
        self.assertEqual(payload["kind"], "static_run_bundle_review_packet")
        self.assertEqual(payload["review_schema_version"], 1)
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["run_id"], "P7-STATIC-RUN")
        self.assertEqual(payload["objective"]["id"], "P6-17")
        self.assertEqual(payload["profile"]["selected"], "lowest-cost")
        self.assertEqual(
            payload["readiness"],
            {
                "bundle_valid": True,
                "status": "ready",
                "packets_ready_for_reviewer": True,
                "actor_results_complete": False,
                "claude_review_ready": True,
                "judge_ready": False,
            },
        )
        self.assertEqual([item["path"] for item in payload["required_review_files"]], list(RUN_BUNDLE_REQUIRED_FILES))
        self.assertEqual([item["actor"] for item in payload["actor_evidence"]], list(PACKET_ACTORS))
        for item in payload["actor_evidence"]:
            actor = item["actor"]
            self.assertEqual(item["packet_file"], f"packets/{actor}.json")
            self.assertTrue(item["packet_ready"])
            self.assertFalse(item["result_present"])
            self.assertEqual(item["result_file"], f"results/{actor}.json")
            self.assertIsNone(item["artifact"])
            self.assertTrue(item["review_focus"])
        self.assertTrue(payload["validation"]["valid"])
        self.assertEqual(payload["status"], {"state": "ready", "errors": []})
        self.assertIn(
            "python3 -m agent_office run-bundle review --path .ai/runs/P7-STATIC-RUN --json",
            payload["reviewer_commands"],
        )
        self.assertIn("must_review", payload["reviewer_contract"])
        self.assertIn("must_preserve", payload["reviewer_contract"])
        self.assertTrue(payload["safety_flags"]["read_only"])
        self.assertFalse(payload["execution_boundary"]["external_behavior_triggered"])
        self.assertFalse(payload["external_behavior"]["artifact_writes"])
        self.assertTrue(payload["read_only"])
        self.assertFalse(payload["execution_enabled"])
        self.assertEqual(payload["provider_calls"], [])
        self.assertIn("does not execute actors", payload["known_limitations"][0])

    def test_run_bundle_review_text_contract_is_static_and_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            project_root = Path(tmpdir)
            bundle = self._write_bundle(project_root)
            before = self._bundle_file_snapshot(bundle)

            first_code, first_stdout, first_stderr = run_cli(["run-bundle", "review", "--path", ".ai/runs/P7-STATIC-RUN"])
            second_code, second_stdout, second_stderr = run_cli(["run-bundle", "review", "--path", ".ai/runs/P7-STATIC-RUN"])
            after = self._bundle_file_snapshot(bundle)

        self.assertEqual(first_code, 0, first_stderr)
        self.assertEqual(second_code, 0, second_stderr)
        self.assertEqual(first_stdout, second_stdout)
        self.assertEqual(before, after)
        self.assertIn("AgentOffice static run bundle review packet", first_stdout)
        self.assertIn(f"path: {bundle}", first_stdout)
        self.assertIn("claude_review_ready: true", first_stdout)
        self.assertIn("judge_ready: false", first_stdout)
        self.assertIn("required_review_files:", first_stdout)
        self.assertIn("  - codex: packet_file=packets/codex.json; packet_ready=true; result_present=false; result_file=results/codex.json", first_stdout)
        self.assertIn("reviewer_contract:", first_stdout)
        self.assertIn("provider/runtime/adapter execution: not triggered", first_stdout)

    def test_run_bundle_review_reports_result_evidence_without_reading_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            project_root = Path(tmpdir)
            self._write_bundle(project_root)
            expected_hashes = {}
            artifacts = []
            for actor in PACKET_ACTORS:
                content = f"{actor} result evidence"
                artifact = self._write_artifact(project_root, f"artifacts/{actor}.txt", content)
                expected_hashes[actor] = hashlib.sha256(content.encode("utf-8")).hexdigest()
                artifacts.append(artifact)
                exit_code, _stdout, stderr = run_cli(
                    [
                        "run-bundle",
                        "intake",
                        "--path",
                        ".ai/runs/P7-STATIC-RUN",
                        "--actor",
                        actor,
                        "--artifact",
                        str(artifact.relative_to(project_root)),
                        "--json",
                    ]
                )
                self.assertEqual(exit_code, 0, stderr)
            for artifact in artifacts:
                artifact.unlink()

            exit_code, stdout, stderr = run_cli(["run-bundle", "review", "--path", ".ai/runs/P7-STATIC-RUN", "--json"])

        self.assertEqual(exit_code, 0, stderr)
        payload = json.loads(stdout)
        self.assertTrue(payload["readiness"]["actor_results_complete"])
        self.assertTrue(payload["readiness"]["judge_ready"])
        for item in payload["actor_evidence"]:
            actor = item["actor"]
            self.assertTrue(item["result_present"])
            self.assertEqual(item["artifact"]["path"], f"artifacts/{actor}.txt")
            self.assertEqual(item["artifact"]["sha256"], expected_hashes[actor])

    def test_run_bundle_review_partial_intake_keeps_judge_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            project_root = Path(tmpdir)
            self._write_bundle(project_root)
            content = "codex partial result"
            artifact = self._write_artifact(project_root, "artifacts/codex.txt", content)
            expected_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            exit_code, _stdout, stderr = run_cli(
                [
                    "run-bundle",
                    "intake",
                    "--path",
                    ".ai/runs/P7-STATIC-RUN",
                    "--actor",
                    "codex",
                    "--artifact",
                    str(artifact.relative_to(project_root)),
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 0, stderr)
            artifact.unlink()

            review_code, review_stdout, review_stderr = run_cli(
                ["run-bundle", "review", "--path", ".ai/runs/P7-STATIC-RUN", "--json"]
            )

        self.assertEqual(review_code, 0, review_stderr)
        payload = json.loads(review_stdout)
        self.assertTrue(payload["readiness"]["claude_review_ready"])
        self.assertFalse(payload["readiness"]["actor_results_complete"])
        self.assertFalse(payload["readiness"]["judge_ready"])
        evidence = {item["actor"]: item for item in payload["actor_evidence"]}
        self.assertTrue(evidence["codex"]["result_present"])
        self.assertEqual(evidence["codex"]["artifact"]["path"], "artifacts/codex.txt")
        self.assertEqual(evidence["codex"]["artifact"]["sha256"], expected_hash)
        for actor in ("reviewer", "judge"):
            self.assertFalse(evidence[actor]["result_present"])
            self.assertIsNone(evidence[actor]["artifact"])

    def test_run_bundle_review_text_reports_intaked_artifact_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            project_root = Path(tmpdir)
            self._write_bundle(project_root)
            content = "codex text result"
            artifact = self._write_artifact(project_root, "artifacts/codex.txt", content)
            expected_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            exit_code, _stdout, stderr = run_cli(
                [
                    "run-bundle",
                    "intake",
                    "--path",
                    ".ai/runs/P7-STATIC-RUN",
                    "--actor",
                    "codex",
                    "--artifact",
                    str(artifact.relative_to(project_root)),
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 0, stderr)
            artifact.unlink()

            review_code, review_stdout, review_stderr = run_cli(
                ["run-bundle", "review", "--path", ".ai/runs/P7-STATIC-RUN"]
            )

        self.assertEqual(review_code, 0, review_stderr)
        self.assertIn(
            "  - codex: packet_file=packets/codex.json; packet_ready=true; result_present=true; result_file=results/codex.json",
            review_stdout,
        )
        self.assertIn("    artifact: path=artifacts/codex.txt;", review_stdout)
        self.assertIn(f"sha256={expected_hash}", review_stdout)
        self.assertIn(
            "  - reviewer: packet_file=packets/reviewer.json; packet_ready=true; result_present=false; result_file=results/reviewer.json",
            review_stdout,
        )
        self.assertIn("judge_ready: false", review_stdout)

    def test_run_bundle_review_rejects_symlink_bundle_path_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            project_root = Path(tmpdir)
            real_dir = self._write_bundle(project_root)
            link_dir = project_root / ".ai" / "runs" / "REVIEW-LINK"
            link_dir.symlink_to(real_dir, target_is_directory=True)

            stdout, stderr = self.assert_exit_two_without_traceback(
                ["run-bundle", "review", "--path", ".ai/runs/REVIEW-LINK", "--json"]
            )

        self.assertEqual(stdout, "")
        self.assertIn("Refusing symlink run bundle path", stderr)

    def test_run_bundle_review_rejects_missing_bundle_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            stdout, stderr = self.assert_exit_two_without_traceback(
                ["run-bundle", "review", "--path", ".ai/runs/MISSING", "--json"]
            )

        self.assertEqual(stdout, "")
        self.assertIn("Run bundle path is not a directory", stderr)

    def test_run_bundle_review_rejects_bad_bundle_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            bundle = self._write_bundle(Path(tmpdir))
            (bundle / "packets" / "judge.json").unlink()
            stdout, stderr = self.assert_exit_two_without_traceback(
                ["run-bundle", "review", "--path", ".ai/runs/P7-STATIC-RUN", "--json"]
            )

        self.assertEqual(stdout, "")
        self.assertIn("Missing run bundle file: packets/judge.json", stderr)

    def test_run_bundle_review_rejects_path_traversal_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            stdout, stderr = self.assert_exit_two_without_traceback(
                ["run-bundle", "review", "--path", "../outside-bundle", "--json"]
            )

        self.assertEqual(stdout, "")
        self.assertIn("Refusing to read run bundle outside project root", stderr)

    def test_run_bundle_handoff_text_rejects_missing_bundle_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            stdout, stderr = self.assert_exit_two_without_traceback(
                ["run-bundle", "handoff", "--path", ".ai/runs/MISSING"]
            )

        self.assertEqual(stdout, "")
        self.assertIn("Run bundle path is not a directory", stderr)

    def test_run_bundle_handoff_rejects_missing_bundle_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            stdout, stderr = self.assert_exit_two_without_traceback(
                ["run-bundle", "handoff", "--path", ".ai/runs/MISSING", "--json"]
            )

        self.assertEqual(stdout, "")
        self.assertIn("Run bundle path is not a directory", stderr)

    def test_run_bundle_handoff_rejects_bad_bundle_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            bundle = self._write_bundle(Path(tmpdir))
            (bundle / "packets" / "judge.json").unlink()
            stdout, stderr = self.assert_exit_two_without_traceback(
                ["run-bundle", "handoff", "--path", ".ai/runs/P7-STATIC-RUN", "--json"]
            )

        self.assertEqual(stdout, "")
        self.assertIn("Missing run bundle file: packets/judge.json", stderr)

    def test_run_bundle_handoff_rejects_path_traversal_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            stdout, stderr = self.assert_exit_two_without_traceback(
                ["run-bundle", "handoff", "--path", "../outside-bundle", "--json"]
            )

        self.assertEqual(stdout, "")
        self.assertIn("Refusing to read run bundle outside project root", stderr)

    def test_run_bundle_handoff_rejects_symlink_bundle_path_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            project_root = Path(tmpdir)
            real_dir = self._write_bundle(project_root)
            link_dir = project_root / ".ai" / "runs" / "LINK-BUNDLE"
            link_dir.symlink_to(real_dir, target_is_directory=True)

            stdout, stderr = self.assert_exit_two_without_traceback(
                ["run-bundle", "handoff", "--path", ".ai/runs/LINK-BUNDLE", "--json"]
            )

        self.assertEqual(stdout, "")
        self.assertIn("Refusing symlink run bundle path", stderr)

    def test_run_bundle_handoff_rejects_symlinked_required_file_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            project_root = Path(tmpdir)
            bundle = self._write_bundle(project_root)
            victim = self._write_artifact(project_root, "victim-run.json", "do not read")
            (bundle / "run.json").unlink()
            (bundle / "run.json").symlink_to(victim)

            stdout, stderr = self.assert_exit_two_without_traceback(
                ["run-bundle", "handoff", "--path", ".ai/runs/P7-STATIC-RUN", "--json"]
            )

        self.assertEqual(stdout, "")
        self.assertIn("Refusing unsafe bundle path: run.json", stderr)

    def test_run_bundle_intake_rejects_unknown_actor_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            project_root = Path(tmpdir)
            self._write_bundle(project_root)
            artifact = self._write_artifact(project_root, "artifacts/codex.txt")
            stdout, stderr = self.assert_exit_two_without_traceback(
                [
                    "run-bundle",
                    "intake",
                    "--path",
                    ".ai/runs/P7-STATIC-RUN",
                    "--actor",
                    "unknown",
                    "--artifact",
                    str(artifact.relative_to(project_root)),
                    "--json",
                ]
            )

        self.assertEqual(stdout, "")
        self.assertIn("run-bundle actor must be codex, reviewer, or judge", stderr)

    def test_run_bundle_intake_rejects_missing_artifact_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            self._write_bundle(Path(tmpdir))
            stdout, stderr = self.assert_exit_two_without_traceback(
                [
                    "run-bundle",
                    "intake",
                    "--path",
                    ".ai/runs/P7-STATIC-RUN",
                    "--actor",
                    "codex",
                    "--artifact",
                    "artifacts/missing.txt",
                    "--json",
                ]
            )

        self.assertEqual(stdout, "")
        self.assertIn("Missing artifact file", stderr)

    def test_run_bundle_intake_rejects_outside_project_artifact_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as outside, patch.object(
            cli, "PROJECT_ROOT", Path(tmpdir)
        ):
            self._write_bundle(Path(tmpdir))
            outside_artifact = Path(outside) / "artifact.txt"
            outside_artifact.write_text("outside", encoding="utf-8")
            stdout, stderr = self.assert_exit_two_without_traceback(
                [
                    "run-bundle",
                    "intake",
                    "--path",
                    ".ai/runs/P7-STATIC-RUN",
                    "--actor",
                    "codex",
                    "--artifact",
                    str(outside_artifact),
                    "--json",
                ]
            )

        self.assertEqual(stdout, "")
        self.assertIn("Refusing artifact outside project root", stderr)

    def test_run_bundle_intake_rejects_symlink_artifact_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            project_root = Path(tmpdir)
            self._write_bundle(project_root)
            target = self._write_artifact(project_root, "artifacts/target.txt")
            symlink = project_root / "artifacts" / "link.txt"
            symlink.symlink_to(target)
            stdout, stderr = self.assert_exit_two_without_traceback(
                [
                    "run-bundle",
                    "intake",
                    "--path",
                    ".ai/runs/P7-STATIC-RUN",
                    "--actor",
                    "codex",
                    "--artifact",
                    "artifacts/link.txt",
                    "--json",
                ]
            )

        self.assertEqual(stdout, "")
        self.assertIn("Refusing symlink artifact", stderr)

    def test_run_bundle_intake_rejects_directory_artifact_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            project_root = Path(tmpdir)
            self._write_bundle(project_root)
            (project_root / "artifacts" / "dir").mkdir(parents=True)
            stdout, stderr = self.assert_exit_two_without_traceback(
                [
                    "run-bundle",
                    "intake",
                    "--path",
                    ".ai/runs/P7-STATIC-RUN",
                    "--actor",
                    "codex",
                    "--artifact",
                    "artifacts/dir",
                    "--json",
                ]
            )

        self.assertEqual(stdout, "")
        self.assertIn("Artifact path is not a file", stderr)

    def test_run_bundle_intake_rejects_missing_bundle_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            artifact = self._write_artifact(Path(tmpdir), "artifacts/codex.txt")
            stdout, stderr = self.assert_exit_two_without_traceback(
                [
                    "run-bundle",
                    "intake",
                    "--path",
                    ".ai/runs/MISSING",
                    "--actor",
                    "codex",
                    "--artifact",
                    str(artifact.relative_to(Path(tmpdir))),
                    "--json",
                ]
            )

        self.assertEqual(stdout, "")
        self.assertIn("Run bundle path is not a directory", stderr)

    def test_run_bundle_results_rejects_missing_bundle_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            stdout, stderr = self.assert_exit_two_without_traceback(
                ["run-bundle", "results", "--path", ".ai/runs/MISSING", "--json"]
            )

        self.assertEqual(stdout, "")
        self.assertIn("Run bundle path is not a directory", stderr)

    def test_run_bundle_intake_rejects_bad_bundle_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            project_root = Path(tmpdir)
            bundle = self._write_bundle(project_root)
            (bundle / "packets" / "judge.json").unlink()
            artifact = self._write_artifact(project_root, "artifacts/codex.txt")
            stdout, stderr = self.assert_exit_two_without_traceback(
                [
                    "run-bundle",
                    "intake",
                    "--path",
                    ".ai/runs/P7-STATIC-RUN",
                    "--actor",
                    "codex",
                    "--artifact",
                    str(artifact.relative_to(project_root)),
                    "--json",
                ]
            )

            self.assertFalse((bundle / "results").exists())

        self.assertEqual(stdout, "")
        self.assertIn("Missing run bundle file: packets/judge.json", stderr)

    def test_run_bundle_intake_rejects_path_traversal_target_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            project_root = Path(tmpdir)
            artifact = self._write_artifact(project_root, "artifacts/codex.txt")
            stdout, stderr = self.assert_exit_two_without_traceback(
                [
                    "run-bundle",
                    "intake",
                    "--path",
                    "../outside-bundle",
                    "--actor",
                    "codex",
                    "--artifact",
                    str(artifact.relative_to(project_root)),
                    "--json",
                ]
            )

        self.assertEqual(stdout, "")
        self.assertIn("Refusing to read run bundle outside project root", stderr)

    def test_run_bundle_intake_rejects_symlinked_result_target_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            project_root = Path(tmpdir)
            bundle = self._write_bundle(project_root)
            artifact = self._write_artifact(project_root, "artifacts/codex.txt", "new metadata source")
            victim = self._write_artifact(project_root, "victim-result.json", "do not overwrite")
            results_dir = bundle / "results"
            results_dir.mkdir()
            result_link = results_dir / "codex.json"
            result_link.symlink_to(victim)

            stdout, stderr = self.assert_exit_two_without_traceback(
                [
                    "run-bundle",
                    "intake",
                    "--path",
                    ".ai/runs/P7-STATIC-RUN",
                    "--actor",
                    "codex",
                    "--artifact",
                    str(artifact.relative_to(project_root)),
                    "--json",
                ]
            )
            victim_text = victim.read_text(encoding="utf-8")

        self.assertEqual(stdout, "")
        self.assertIn("Refusing to overwrite symlink actor result", stderr)
        self.assertEqual(victim_text, "do not overwrite")

    def test_run_bundle_out_rejects_symlinked_bundle_file_target_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            project_root = Path(tmpdir)
            bundle = self._write_bundle(project_root)
            victim = self._write_artifact(project_root, "victim-run.json", "do not overwrite")
            (bundle / "run.json").unlink()
            (bundle / "run.json").symlink_to(victim)

            stdout, stderr = self.assert_exit_two_without_traceback(
                [
                    "run-bundle",
                    "--objective",
                    "P6-17",
                    "--profile",
                    "lowest-cost",
                    "--run-id",
                    "P7-STATIC-RUN",
                    "--out",
                    ".ai/runs/P7-STATIC-RUN",
                    "--json",
                ]
            )
            victim_text = victim.read_text(encoding="utf-8")

        self.assertEqual(stdout, "")
        self.assertIn("Refusing to overwrite symlink bundle file", stderr)
        self.assertEqual(victim_text, "do not overwrite")

    def test_run_bundle_rejects_symlinked_output_directory_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            project_root = Path(tmpdir)
            real_dir = project_root / ".ai" / "runs" / "REAL-BUNDLE"
            real_dir.mkdir(parents=True)
            link_dir = project_root / ".ai" / "runs" / "LINK-BUNDLE"
            link_dir.symlink_to(real_dir, target_is_directory=True)

            stdout, stderr = self.assert_exit_two_without_traceback(
                [
                    "run-bundle",
                    "--objective",
                    "P6-17",
                    "--profile",
                    "lowest-cost",
                    "--run-id",
                    "P7-LINK",
                    "--out",
                    ".ai/runs/LINK-BUNDLE",
                    "--json",
                ]
            )

        self.assertEqual(stdout, "")
        self.assertIn("Refusing to write run bundle to symlink path", stderr)

    def test_run_bundle_non_utf8_required_file_exits_two_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            project_root = Path(tmpdir)
            bundle = self._write_bundle(project_root)
            artifact = self._write_artifact(project_root, "artifacts/codex.txt")
            (bundle / "run.json").write_bytes(b"\xff\xfe")
            commands = [
                ["run-bundle", "inspect", "--path", ".ai/runs/P7-STATIC-RUN", "--json"],
                ["run-bundle", "validate", "--path", ".ai/runs/P7-STATIC-RUN", "--json"],
                ["run-bundle", "status", "--path", ".ai/runs/P7-STATIC-RUN", "--json"],
                ["run-bundle", "handoff", "--path", ".ai/runs/P7-STATIC-RUN", "--json"],
                ["run-bundle", "review", "--path", ".ai/runs/P7-STATIC-RUN", "--json"],
                ["run-bundle", "results", "--path", ".ai/runs/P7-STATIC-RUN", "--json"],
                [
                    "run-bundle",
                    "intake",
                    "--path",
                    ".ai/runs/P7-STATIC-RUN",
                    "--actor",
                    "codex",
                    "--artifact",
                    str(artifact.relative_to(project_root)),
                    "--json",
                ],
            ]

            for command in commands:
                stdout, stderr = self.assert_exit_two_without_traceback(command)
                self.assertIn("Invalid UTF-8 in run bundle file: run.json", stdout + stderr)

    def test_run_bundle_validate_missing_run_json_exits_two_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            bundle = self._write_bundle(Path(tmpdir))
            (bundle / "run.json").unlink()
            exit_code, stdout, stderr = run_cli(["run-bundle", "validate", "--path", ".ai/runs/P7-STATIC-RUN", "--json"])

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("Missing run bundle file: run.json", stderr)
        self.assertNotIn("Traceback", stderr)

    def test_run_bundle_validate_bad_json_exits_two_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            bundle = self._write_bundle(Path(tmpdir))
            (bundle / "run.json").write_text("{bad json", encoding="utf-8")
            exit_code, stdout, stderr = run_cli(["run-bundle", "validate", "--path", ".ai/runs/P7-STATIC-RUN", "--json"])

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("Invalid JSON in run bundle file: run.json", stderr)
        self.assertNotIn("Traceback", stderr)

    def test_run_bundle_validate_missing_judge_packet_exits_two_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            bundle = self._write_bundle(Path(tmpdir))
            (bundle / "packets" / "judge.json").unlink()
            exit_code, stdout, stderr = run_cli(["run-bundle", "validate", "--path", ".ai/runs/P7-STATIC-RUN", "--json"])

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("Missing run bundle file: packets/judge.json", stderr)
        self.assertNotIn("Traceback", stderr)

    def test_run_bundle_validate_execution_enabled_true_exits_two_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            bundle = self._write_bundle(Path(tmpdir))
            run = json.loads((bundle / "run.json").read_text(encoding="utf-8"))
            run["execution_enabled"] = True
            (bundle / "run.json").write_text(json.dumps(run), encoding="utf-8")
            exit_code, stdout, stderr = run_cli(["run-bundle", "validate", "--path", ".ai/runs/P7-STATIC-RUN", "--json"])

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("run.json execution_enabled must be false", stderr)
        self.assertNotIn("Traceback", stderr)

    def test_run_bundle_validate_provider_calls_non_empty_exits_two_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            bundle = self._write_bundle(Path(tmpdir))
            run = json.loads((bundle / "run.json").read_text(encoding="utf-8"))
            run["provider_calls"] = [{"role": "context", "call_enabled": True}]
            (bundle / "run.json").write_text(json.dumps(run), encoding="utf-8")
            exit_code, stdout, stderr = run_cli(["run-bundle", "validate", "--path", ".ai/runs/P7-STATIC-RUN", "--json"])

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("run.json provider_calls must be empty", stderr)
        self.assertNotIn("Traceback", stderr)

    def test_run_bundle_validate_missing_actor_exits_two_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(cli, "PROJECT_ROOT", Path(tmpdir)):
            bundle = self._write_bundle(Path(tmpdir))
            run = json.loads((bundle / "run.json").read_text(encoding="utf-8"))
            run["actors"] = ["codex", "reviewer"]
            (bundle / "run.json").write_text(json.dumps(run), encoding="utf-8")
            exit_code, stdout, stderr = run_cli(["run-bundle", "validate", "--path", ".ai/runs/P7-STATIC-RUN", "--json"])

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("run.json actors must be codex, reviewer, judge", stderr)
        self.assertNotIn("Traceback", stderr)

    def _bundle_file_snapshot(self, root: Path) -> list[tuple[str, int, str]]:
        snapshot = []
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            stat = path.stat()
            snapshot.append(
                (path.relative_to(root).as_posix(), stat.st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest())
            )
        return snapshot
