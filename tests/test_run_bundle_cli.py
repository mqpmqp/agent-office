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
                ["run-bundle", "results", "--path", ".ai/runs/P7-STATIC-RUN", "--json"],
            ]
            for command in commands:
                exit_code, _stdout, stderr = run_cli(command)
                self.assertEqual(exit_code, 0, stderr)

            self.assertFalse((bundle / "results").exists())

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
