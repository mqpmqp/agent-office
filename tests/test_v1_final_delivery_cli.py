from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from agent_office import cli


REQUIRED_KEYS = {
    "schema_version",
    "packet_type",
    "phase",
    "status",
    "repo",
    "delivery",
    "contracts",
    "validation",
    "artifacts",
    "review",
    "merge_gate",
    "safety",
    "non_goals",
    "next_actions",
}


def run_cli(argv: list[str], project_root: Path) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with patch.object(cli, "PROJECT_ROOT", project_root), redirect_stdout(stdout), redirect_stderr(stderr):
        code = cli.main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


class V1FinalDeliveryCliTests(unittest.TestCase):
    maxDiff = None

    def _packet(self, root: Path) -> dict[str, object]:
        code, stdout, stderr = run_cli(["v1", "final-delivery", "--json"], root)
        self.assertEqual(code, 0, stderr)
        self.assertNotIn("Traceback", stdout + stderr)
        return json.loads(stdout)

    def test_final_delivery_json_and_text_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            packet = self._packet(root)
            text_code, text_stdout, text_stderr = run_cli(["v1", "final-delivery"], root)

        self.assertTrue(REQUIRED_KEYS.issubset(packet))
        self.assertEqual(packet["packet_type"], "agentoffice_v1_final_delivery")
        self.assertEqual(packet["schema_version"], 1)
        self.assertEqual(packet["phase"], "P49")
        self.assertEqual(packet["status"], "ready_for_v1_final_review")
        self.assertEqual(packet["delivery"]["version"], "v1")
        self.assertEqual(packet["delivery"]["final_implementation_batch"], "P49")
        self.assertTrue(packet["contracts"]["static_only"])
        self.assertFalse(packet["safety"]["dotenv_read"])
        self.assertFalse(packet["safety"]["env_vars_printed"])
        self.assertFalse(packet["safety"]["provider_runtime_adapter_external_behavior"])
        self.assertTrue(all("P50" not in str(action) for action in packet["next_actions"]))
        self.assertIn("python3 -m agent_office v1 final-delivery --json", packet["validation"]["release_blocking_commands"])
        self.assertEqual(text_code, 0, text_stderr)
        self.assertIn("AGENTOFFICE_V1_FINAL_DELIVERY_PACKET", text_stdout)
        self.assertIn("phase: P49", text_stdout)
        self.assertIn("expected_review_output: P49_CLAUDE_ARTIFACT_REVIEW_OUTPUT.md", text_stdout)
        self.assertNotIn("P50", text_stdout)
        self.assertNotIn("Traceback", text_stdout + text_stderr)

    def test_out_writes_json_and_verify_passes_json_and_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            out = root / "nested" / "packet.json"
            code, stdout, stderr = run_cli(["v1", "final-delivery", "--out", str(out), "--json"], root)
            self.assertEqual(code, 0, stderr)
            written = json.loads(out.read_text(encoding="utf-8"))
            printed = json.loads(stdout)
            verify_json = run_cli(["v1", "verify-final-delivery", "--path", str(out), "--json"], root)
            verify_text = run_cli(["v1", "verify-final-delivery", "--path", str(out)], root)

        self.assertEqual(written, printed)
        self.assertEqual(verify_json[0], 0, verify_json[2])
        payload = json.loads(verify_json[1])
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["packet_type"], "agentoffice_v1_final_delivery")
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["phase"], "P49")
        self.assertEqual(payload["status"], "ready_for_v1_final_review")
        self.assertEqual(payload["errors"], [])
        self.assertEqual(verify_text[0], 0, verify_text[2])
        self.assertIn("AGENTOFFICE_V1_FINAL_DELIVERY_VERIFY_PASS", verify_text[1])
        self.assertNotIn("Traceback", verify_json[1] + verify_json[2] + verify_text[1] + verify_text[2])

    def test_verify_negative_inputs_are_clean_json_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            packet = self._packet(root)
            bad_json = root / "bad.json"
            bad_json.write_text("{bad json\n", encoding="utf-8")
            wrong_type = root / "wrong-type.json"
            wrong_packet = dict(packet)
            wrong_packet["packet_type"] = "wrong"
            wrong_type.write_text(json.dumps(wrong_packet), encoding="utf-8")
            missing_key = root / "missing-key.json"
            missing_packet = dict(packet)
            missing_packet.pop("safety")
            missing_key.write_text(json.dumps(missing_packet), encoding="utf-8")
            non_utf8 = root / "non-utf8.json"
            non_utf8.write_bytes(b"\xff\xfe")
            directory = root / "packet-dir"
            directory.mkdir()
            cases = [
                (root / "missing.json", "v1_final_delivery_verify_missing"),
                (bad_json, "v1_final_delivery_verify_bad_json"),
                (wrong_type, "wrong_packet_type"),
                (missing_key, "missing_required_key:safety"),
                (directory, "v1_final_delivery_verify_directory"),
                (non_utf8, "v1_final_delivery_verify_non_utf8"),
            ]
            target = root / "target.json"
            target.write_text(json.dumps(packet), encoding="utf-8")
            try:
                link = root / "link.json"
                link.symlink_to(target)
                cases.append((link, "v1_final_delivery_verify_symlink"))
            except OSError as exc:
                link = None
                symlink_error = exc

            results = []
            for path, expected in cases:
                result = run_cli(["v1", "verify-final-delivery", "--path", str(path), "--json"], root)
                results.append((result, expected))
            fail_text = run_cli(["v1", "verify-final-delivery", "--path", str(bad_json)], root)

        if link is None:
            self.assertIsInstance(symlink_error, OSError)
        for result, expected in results:
            with self.subTest(expected=expected):
                self.assertEqual(result[0], 2, result[1] + result[2])
                payload = json.loads(result[1])
                self.assertFalse(payload["ok"])
                self.assertTrue(any(expected in error for error in payload["errors"]))
                self.assertNotIn("Traceback", result[1] + result[2])
        self.assertEqual(fail_text[0], 2)
        self.assertIn("AGENTOFFICE_V1_FINAL_DELIVERY_VERIFY_FAIL", fail_text[1])
        self.assertNotIn("Traceback", fail_text[1] + fail_text[2])

    def test_final_delivery_output_path_errors_are_clean_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            out_dir = root / "out-dir"
            out_dir.mkdir()
            cases = [
                (root / ".env", "v1_final_delivery_output_dotenv_refused"),
                (out_dir, "v1_final_delivery_output_directory"),
            ]
            target = root / "target.json"
            target.write_text("keep\n", encoding="utf-8")
            try:
                link = root / "out-link.json"
                link.symlink_to(target)
                cases.append((link, "v1_final_delivery_output_symlink"))
            except OSError as exc:
                link = None
                symlink_error = exc

            results = []
            for path, expected in cases:
                result = run_cli(["v1", "final-delivery", "--out", str(path), "--json"], root)
                results.append((result, expected))

        if link is None:
            self.assertIsInstance(symlink_error, OSError)
        for result, expected in results:
            with self.subTest(expected=expected):
                self.assertEqual(result[0], 2, result[1] + result[2])
                payload = json.loads(result[1])
                self.assertEqual(payload["error_code"], expected)
                self.assertNotIn("Traceback", result[1] + result[2])
