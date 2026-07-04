from __future__ import annotations

import hashlib
import io
import json
import tarfile
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from agent_office import cli


REQUIRED_ASSETS = [
    "V1_0_0_TAG_VERIFICATION_READBACK.md",
    "agentoffice-v1.0.0-final-delivery-archive.tar.gz",
    "agentoffice-v1.0.0-final-delivery-archive.tar.gz.sha256",
    "V1_0_0_RELEASE_ARCHIVE_REPORT.md",
]


def run_cli(argv: list[str], project_root: Path) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with patch.object(cli, "PROJECT_ROOT", project_root), redirect_stdout(stdout), redirect_stderr(stderr):
        code = cli.main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


def write_archive(root: Path, *, missing_manifest: bool = False, bad_checksum: bool = False) -> tuple[Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    archive = root / "release.tar.gz"
    sha = root / "release.tar.gz.sha256"
    files = {
        "README_FOR_RELEASE_ARCHIVE.md": b"release archive\n",
        "reports/report.md": b"report\n",
    }
    if missing_manifest:
        files.pop("README_FOR_RELEASE_ARCHIVE.md")
    sums = []
    for rel_path, content in sorted(files.items()):
        digest = hashlib.sha256(content).hexdigest()
        if bad_checksum and rel_path == "reports/report.md":
            digest = "0" * 64
        sums.append(f"{digest}  ./{rel_path}\n".encode("utf-8"))
    with tarfile.open(archive, "w:gz") as tar:
        for rel_path, content in sorted(files.items()):
            info = tarfile.TarInfo(f"V1_0_0_FINAL_DELIVERY_ARCHIVE/{rel_path}")
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
        sums_content = b"".join(sums)
        sums_info = tarfile.TarInfo("V1_0_0_FINAL_DELIVERY_ARCHIVE/SHA256SUMS")
        sums_info.size = len(sums_content)
        tar.addfile(sums_info, io.BytesIO(sums_content))
    sha.write_text(f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive}\n", encoding="utf-8")
    return archive, sha


class V1PostReleaseOpsCliTests(unittest.TestCase):
    maxDiff = None

    def test_release_archive_verify_positive_json_and_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            archive, sha = write_archive(root)
            json_result = run_cli(["v1", "verify-release-archive", "--archive", str(archive), "--sha256", str(sha), "--json"], root)
            text_result = run_cli(["v1", "verify-release-archive", "--archive", str(archive), "--sha256", str(sha)], root)

        self.assertEqual(json_result[0], 0, json_result[1] + json_result[2])
        payload = json.loads(json_result[1])
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["packet_type"], "agentoffice_v1_release_archive_verification")
        self.assertTrue(payload["external_sha256_match"])
        self.assertTrue(payload["required_members_present"])
        self.assertTrue(payload["internal_sha256_ok"])
        self.assertEqual(payload["checked_files"], 2)
        self.assertEqual(payload["errors"], [])
        self.assertEqual(text_result[0], 0, text_result[2])
        self.assertIn("AGENTOFFICE_V1_RELEASE_ARCHIVE_VERIFY_PASS", text_result[1])
        self.assertNotIn("Traceback", json_result[1] + json_result[2] + text_result[1] + text_result[2])

    def test_release_archive_negative_inputs_are_clean_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            archive, sha = write_archive(root)
            missing_sha = root / "missing.sha256"
            mismatch_sha = root / "mismatch.sha256"
            mismatch_sha.write_text(f"{'1' * 64}  {archive}\n", encoding="utf-8")
            corrupt_tar = root / "corrupt.tar.gz"
            corrupt_tar.write_bytes(b"not a tar")
            corrupt_sha = root / "corrupt.tar.gz.sha256"
            corrupt_sha.write_text(f"{hashlib.sha256(corrupt_tar.read_bytes()).hexdigest()}  {corrupt_tar}\n", encoding="utf-8")
            missing_manifest, missing_manifest_sha = write_archive(root / "missing", missing_manifest=True)
            bad_internal, bad_internal_sha = write_archive(root / "bad", bad_checksum=True)
            cases = [
                (["--archive", str(root / "missing.tar.gz"), "--sha256", str(sha), "--json"], "release_archive_missing"),
                (["--archive", str(archive), "--sha256", str(missing_sha), "--json"], "release_archive_sha256_missing"),
                (["--archive", str(archive), "--sha256", str(mismatch_sha), "--json"], "release_archive_sha256_mismatch"),
                (["--archive", str(corrupt_tar), "--sha256", str(corrupt_sha), "--json"], "release_archive_corrupt_tar"),
                (["--archive", str(missing_manifest), "--sha256", str(missing_manifest_sha), "--json"], "release_archive_missing_internal_manifest"),
                (["--archive", str(bad_internal), "--sha256", str(bad_internal_sha), "--json"], "release_archive_bad_internal_checksum"),
            ]
            results = [(run_cli(["v1", "verify-release-archive", *argv], root), expected) for argv, expected in cases]
            text_failure = run_cli(["v1", "verify-release-archive", "--archive", str(archive), "--sha256", str(mismatch_sha)], root)

        for result, expected in results:
            with self.subTest(expected=expected):
                self.assertEqual(result[0], 2, result[1] + result[2])
                payload = json.loads(result[1])
                self.assertFalse(payload["ok"])
                self.assertTrue(any(expected in error for error in payload["errors"]), payload["errors"])
                self.assertNotIn("Traceback", result[1] + result[2])
        self.assertEqual(text_failure[0], 2)
        self.assertIn("AGENTOFFICE_V1_RELEASE_ARCHIVE_VERIFY_FAIL", text_failure[1])
        self.assertNotIn("Traceback", text_failure[1] + text_failure[2])

    def test_github_release_readback_published_positive(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            readback = root / "readback"
            readback.mkdir()
            (readback / "state.json").write_text(
                json.dumps(
                    {
                        "status": "published",
                        "publish_state": "published",
                        "release_url": "https://github.com/mqpmqp/agent-office/releases/tag/v1.0.0",
                        "release_published": True,
                        "assets_uploaded": REQUIRED_ASSETS,
                    }
                ),
                encoding="utf-8",
            )
            json_result = run_cli(["v1", "verify-github-release-readback", "--dir", str(readback), "--json"], root)
            text_result = run_cli(["v1", "verify-github-release-readback", "--dir", str(readback)], root)

        self.assertEqual(json_result[0], 0, json_result[1] + json_result[2])
        payload = json.loads(json_result[1])
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["packet_type"], "agentoffice_v1_github_release_readback_verification")
        self.assertEqual(payload["status"], "published")
        self.assertEqual(payload["publish_state"], "published")
        self.assertEqual(payload["assets"], REQUIRED_ASSETS)
        self.assertEqual(text_result[0], 0, text_result[2])
        self.assertIn("AGENTOFFICE_V1_GITHUB_RELEASE_READBACK_VERIFY_PASS", text_result[1])
        self.assertNotIn("Traceback", json_result[1] + json_result[2] + text_result[1] + text_result[2])

    def test_github_release_readback_verified_existing_positive(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            readback = root / "readback"
            readback.mkdir()
            (readback / "state.json").write_text(
                json.dumps(
                    {
                        "status": "verified_existing",
                        "publish_state": "verified_existing",
                        "release_url": "https://github.com/mqpmqp/agent-office/releases/tag/v1.0.0",
                        "release_published": True,
                    }
                ),
                encoding="utf-8",
            )
            (readback / "release.json").write_text(
                json.dumps({"html_url": "https://github.com/mqpmqp/agent-office/releases/tag/v1.0.0", "assets": [{"name": name} for name in REQUIRED_ASSETS]}),
                encoding="utf-8",
            )
            result = run_cli(["v1", "verify-github-release-readback", "--dir", str(readback), "--json"], root)

        self.assertEqual(result[0], 0, result[1] + result[2])
        payload = json.loads(result[1])
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "verified_existing")
        self.assertEqual(payload["publish_state"], "verified_existing")
        self.assertEqual(payload["assets"], REQUIRED_ASSETS)
        self.assertNotIn("Traceback", result[1] + result[2])

    def test_github_release_readback_skipped_no_token_positive(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            readback = root / "readback"
            readback.mkdir()
            (readback / "state.json").write_text(json.dumps({"status": "skipped_no_token", "publish_state": "skipped", "reason": "release_publish_skipped_token_missing"}), encoding="utf-8")
            json_result = run_cli(["v1", "verify-github-release-readback", "--dir", str(readback), "--json"], root)
            text_result = run_cli(["v1", "verify-github-release-readback", "--dir", str(readback)], root)

        self.assertEqual(json_result[0], 0, json_result[1] + json_result[2])
        payload = json.loads(json_result[1])
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "skipped_no_token")
        self.assertEqual(payload["publish_state"], "skipped")
        self.assertIn("publish_state=skipped", text_result[1])
        self.assertNotIn("Traceback", json_result[1] + json_result[2] + text_result[1] + text_result[2])

    def test_github_release_readback_negative_inputs_are_clean_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            partial = root / "partial"
            partial.mkdir()
            (partial / "state.json").write_text(json.dumps({"status": "partial_remote_state", "publish_state": "partial_remote_state", "assets_uploaded": [REQUIRED_ASSETS[0]]}), encoding="utf-8")
            malformed = root / "malformed"
            malformed.mkdir()
            (malformed / "state.json").write_text("{bad json", encoding="utf-8")
            cases = [
                (root / "missing", "github_release_readback_missing"),
                (partial, "github_release_readback_partial_remote_state"),
                (malformed, "github_release_readback_state_malformed_json"),
            ]
            results = [(run_cli(["v1", "verify-github-release-readback", "--dir", str(path), "--json"], root), expected) for path, expected in cases]
            text_failure = run_cli(["v1", "verify-github-release-readback", "--dir", str(partial)], root)

        for result, expected in results:
            with self.subTest(expected=expected):
                self.assertEqual(result[0], 2, result[1] + result[2])
                payload = json.loads(result[1])
                self.assertFalse(payload["ok"])
                self.assertTrue(any(expected in error for error in payload["errors"]), payload["errors"])
                self.assertNotIn("Traceback", result[1] + result[2])
        self.assertEqual(text_failure[0], 2)
        self.assertIn("AGENTOFFICE_V1_GITHUB_RELEASE_READBACK_VERIFY_FAIL", text_failure[1])
        self.assertNotIn("Traceback", text_failure[1] + text_failure[2])

    def test_post_v1_roadmap_json_and_text_are_stable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            first_json = run_cli(["v1", "post-v1-roadmap", "--json"], root)
            second_json = run_cli(["v1", "post-v1-roadmap", "--json"], root)
            text_result = run_cli(["v1", "post-v1-roadmap"], root)

        self.assertEqual(first_json[0], 0, first_json[2])
        self.assertEqual(second_json[0], 0, second_json[2])
        self.assertEqual(first_json[1], second_json[1])
        payload = json.loads(first_json[1])
        self.assertEqual(payload["packet_type"], "agentoffice_post_v1_roadmap")
        lane_labels = [lane["label"] for lane in payload["lanes"]]
        self.assertIn("v1.0.1 hotfix lane", lane_labels)
        self.assertIn("v1.1 release ops lane", lane_labels)
        self.assertIn("artifact review automation lane", lane_labels)
        self.assertIn("external worker adapter hardening lane", lane_labels)
        self.assertIn("provider/runtime safety lane", lane_labels)
        self.assertIn("validation_commands", payload)
        self.assertFalse(payload["safety"]["dotenv_read"])
        self.assertFalse(payload["safety"]["provider_runtime_adapter_external_behavior"])
        self.assertEqual(text_result[0], 0, text_result[2])
        self.assertIn("AGENTOFFICE_POST_V1_ROADMAP", text_result[1])
        self.assertIn("v1.0.1 hotfix lane", text_result[1])
        self.assertNotIn("Traceback", first_json[1] + first_json[2] + text_result[1] + text_result[2])
