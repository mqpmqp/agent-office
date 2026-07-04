from __future__ import annotations

import hashlib
import json
import re
import tarfile
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
RELEASE_COMMIT = "91a8e38cd8d3db540e8c5655304f0f1e4d8f8213"
RELEASE_TAG = "v1.0.0"
RELEASE_TITLE = "AgentOffice v1.0.0"
MAINLINE_BRANCH = "phase6/mainline"
POST_V1_BRANCH = "phase50/post-v1-release-ops-foundation"
ARCHIVE_ROOT = "V1_0_0_FINAL_DELIVERY_ARCHIVE"
ARCHIVE_PACKET_TYPE = "agentoffice_v1_release_archive_verification"
READBACK_PACKET_TYPE = "agentoffice_v1_github_release_readback_verification"
ROADMAP_PACKET_TYPE = "agentoffice_post_v1_roadmap"
ARCHIVE_VERIFY_PASS_MARKER = "AGENTOFFICE_V1_RELEASE_ARCHIVE_VERIFY_PASS"
ARCHIVE_VERIFY_FAIL_MARKER = "AGENTOFFICE_V1_RELEASE_ARCHIVE_VERIFY_FAIL"
READBACK_VERIFY_PASS_MARKER = "AGENTOFFICE_V1_GITHUB_RELEASE_READBACK_VERIFY_PASS"
READBACK_VERIFY_FAIL_MARKER = "AGENTOFFICE_V1_GITHUB_RELEASE_READBACK_VERIFY_FAIL"
ROADMAP_MARKER = "AGENTOFFICE_POST_V1_ROADMAP"

REQUIRED_ARCHIVE_MEMBERS = (
    f"{ARCHIVE_ROOT}/README_FOR_RELEASE_ARCHIVE.md",
    f"{ARCHIVE_ROOT}/SHA256SUMS",
)

REQUIRED_RELEASE_ASSETS = (
    "V1_0_0_TAG_VERIFICATION_READBACK.md",
    "agentoffice-v1.0.0-final-delivery-archive.tar.gz",
    "agentoffice-v1.0.0-final-delivery-archive.tar.gz.sha256",
    "V1_0_0_RELEASE_ARCHIVE_REPORT.md",
)

READBACK_STATUS_TO_PUBLISH_STATE = {
    "published": "published",
    "verified_existing": "verified_existing",
    "skipped_no_token": "skipped",
    "skipped_api_error": "skipped",
    "partial_remote_state": "partial_remote_state",
}


def verify_release_archive_payload(archive: str, sha256: str) -> dict[str, Any]:
    errors: list[str] = []
    archive_path = _safe_file_path(archive, "release_archive", errors)
    sha_path = _safe_file_path(sha256, "release_archive_sha256", errors)
    payload: dict[str, Any] = {
        "ok": False,
        "packet_type": ARCHIVE_PACKET_TYPE,
        "schema_version": SCHEMA_VERSION,
        "archive": str(archive),
        "sha256": str(sha256),
        "external_sha256": None,
        "expected_external_sha256": None,
        "external_sha256_match": False,
        "required_members_present": False,
        "internal_sha256_ok": False,
        "checked_files": 0,
        "errors": errors,
    }
    if errors or archive_path is None or sha_path is None:
        return payload

    expected = _read_expected_sha256(sha_path, errors)
    actual = _file_sha256(archive_path, errors)
    payload["expected_external_sha256"] = expected
    payload["external_sha256"] = actual
    if expected and actual:
        payload["external_sha256_match"] = expected == actual
        if expected != actual:
            errors.append("release_archive_sha256_mismatch")

    archive_result = _verify_archive_members(archive_path, errors)
    payload["required_members_present"] = archive_result["required_members_present"]
    payload["internal_sha256_ok"] = archive_result["internal_sha256_ok"]
    payload["checked_files"] = archive_result["checked_files"]
    payload["ok"] = not errors
    return payload


def format_release_archive_verify(payload: dict[str, Any]) -> str:
    marker = ARCHIVE_VERIFY_PASS_MARKER if payload["ok"] else ARCHIVE_VERIFY_FAIL_MARKER
    lines = [
        marker,
        f"ok: {_bool_text(bool(payload['ok']))}",
        f"archive: {payload['archive']}",
        f"sha256: {payload['sha256']}",
        f"external_sha256_match: {_bool_text(bool(payload['external_sha256_match']))}",
        f"required_members_present: {_bool_text(bool(payload['required_members_present']))}",
        f"internal_sha256_ok: {_bool_text(bool(payload['internal_sha256_ok']))}",
        f"checked_files: {payload['checked_files']}",
        "errors:",
    ]
    errors = payload["errors"]
    if errors:
        lines.extend(f"  - {error}" for error in errors)
    else:
        lines.append("  - none")
    return "\n".join(lines)


def verify_github_release_readback_payload(directory: str) -> dict[str, Any]:
    errors: list[str] = []
    readback_dir = _safe_dir_path(directory, "github_release_readback", errors)
    payload: dict[str, Any] = {
        "ok": False,
        "packet_type": READBACK_PACKET_TYPE,
        "schema_version": SCHEMA_VERSION,
        "dir": str(directory),
        "status": "unknown",
        "publish_state": "unknown",
        "release_url": None,
        "assets": [],
        "errors": errors,
    }
    if errors or readback_dir is None:
        return payload

    state_path = readback_dir / "state.json"
    state = _read_json_object(state_path, "github_release_readback_state", errors)
    if state is None:
        return payload

    status = _string_value(state.get("status")) or "unknown"
    publish_state = _string_value(state.get("publish_state")) or "unknown"
    release_url = _string_value(state.get("release_url"))
    assets = _asset_names(state)

    release_json_path = readback_dir / "release.json"
    if release_json_path.exists():
        release = _read_json_object(release_json_path, "github_release_readback_release", errors)
        if release is not None:
            release_url = release_url or _string_value(release.get("html_url"))
            assets = assets or _asset_names(release)

    expected_publish_state = READBACK_STATUS_TO_PUBLISH_STATE.get(status)
    if expected_publish_state is None:
        errors.append(f"github_release_readback_unknown_status:{status}")
    elif publish_state != expected_publish_state:
        errors.append(f"github_release_readback_publish_state_mismatch:{publish_state}:{expected_publish_state}")

    if status in {"published", "verified_existing"}:
        if not release_url:
            errors.append("github_release_readback_missing_release_url")
        elif not _valid_release_url(release_url):
            errors.append("github_release_readback_invalid_release_url")
        missing_assets = [name for name in REQUIRED_RELEASE_ASSETS if name not in assets]
        if missing_assets:
            errors.append("github_release_readback_missing_assets:" + ",".join(missing_assets))
    elif status in {"skipped_no_token", "skipped_api_error"}:
        if publish_state != "skipped":
            errors.append("github_release_readback_skipped_state_not_skipped")
    elif status == "partial_remote_state":
        errors.append("github_release_readback_partial_remote_state")

    if release_url and not _valid_release_url(release_url):
        if "github_release_readback_invalid_release_url" not in errors:
            errors.append("github_release_readback_invalid_release_url")

    payload.update(
        {
            "status": status,
            "publish_state": publish_state,
            "release_url": release_url,
            "assets": assets,
            "ok": not errors,
        }
    )
    return payload


def format_github_release_readback_verify(payload: dict[str, Any]) -> str:
    marker = READBACK_VERIFY_PASS_MARKER if payload["ok"] else READBACK_VERIFY_FAIL_MARKER
    lines = [
        marker,
        f"ok: {_bool_text(bool(payload['ok']))}",
        f"status: {payload['status']}",
        f"publish_state={payload['publish_state']}",
        f"release_url: {payload['release_url'] or 'n/a'}",
        "assets:",
    ]
    assets = payload["assets"]
    if assets:
        lines.extend(f"  - {asset}" for asset in assets)
    else:
        lines.append("  - none")
    lines.append("errors:")
    errors = payload["errors"]
    if errors:
        lines.extend(f"  - {error}" for error in errors)
    else:
        lines.append("  - none")
    return "\n".join(lines)


def post_v1_roadmap_payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "packet_type": ROADMAP_PACKET_TYPE,
        "status": "ready_for_review",
        "baseline": {
            "tag": RELEASE_TAG,
            "release_title": RELEASE_TITLE,
            "release_commit": RELEASE_COMMIT,
            "mainline_branch": MAINLINE_BRANCH,
            "post_v1_branch": POST_V1_BRANCH,
        },
        "lanes": [
            {
                "id": "v1.0.1-hotfix",
                "label": "v1.0.1 hotfix lane",
                "focus": [
                    "small correctness fixes found by v1 release review",
                    "documentation clarifications with no runtime behavior change",
                    "targeted verifier fixes with regression tests",
                ],
            },
            {
                "id": "v1.1-release-ops",
                "label": "v1.1 release ops lane",
                "focus": [
                    "idempotent release readback and archive verification surfaces",
                    "review bundle lifecycle evidence",
                    "operator handoff packets before any remote release write",
                ],
            },
            {
                "id": "artifact-review-automation",
                "label": "artifact review automation lane",
                "focus": [
                    "single-file reviewer bundles with checksums",
                    "local self-checks for exported review artifacts",
                    "clear PASS marker import requirements",
                ],
            },
            {
                "id": "external-worker-adapter-hardening",
                "label": "external worker adapter hardening lane",
                "focus": [
                    "dry-run first worker handoffs",
                    "explicit boundaries for real provider calls",
                    "failure readbacks that avoid secrets and environment dumps",
                ],
            },
            {
                "id": "provider-runtime-safety",
                "label": "provider/runtime safety lane",
                "focus": [
                    "static doctor and profile checks before real execution",
                    "no .env reads in release verification surfaces",
                    "no provider, runtime, model, or adapter execution in roadmap commands",
                ],
            },
        ],
        "non_goals": [
            "automatic merge to phase6/mainline",
            "tag creation or mutation",
            "GitHub release deletion or asset overwrite",
            "real provider/model/runtime/adapter execution",
            "reading .env or printing environment variables",
        ],
        "validation_commands": [
            "python3 -m compileall agent_office tests",
            "python3 -m unittest discover -s tests -p 'test_*.py'",
            "python3 -m agent_office v1 verify-release-archive --archive /opt/agent-office/agentoffice-v1.0.0-final-delivery-archive.tar.gz --sha256 /opt/agent-office/agentoffice-v1.0.0-final-delivery-archive.tar.gz.sha256 --json",
            "python3 -m agent_office v1 verify-github-release-readback --dir /opt/agent-office/V1_0_0_GITHUB_RELEASE_API_LONGRUN_READBACK --json",
            "python3 -m agent_office v1 post-v1-roadmap --json",
            "git diff --check",
        ],
        "review_handoff_guidance": [
            "Attach POST_V1_LONGRUN_REVIEW_ARTIFACT_BUNDLE.md and its SHA256 sidecar.",
            "Ask Claude artifact review to inspect the full diff and validation outputs without executing commands.",
            "Require marker POST_V1_LONGRUN_ARTIFACT_REVIEW_COMPLETE before any merge discussion.",
        ],
        "safety": {
            "dotenv_read": False,
            "env_vars_printed": False,
            "provider_runtime_adapter_external_behavior": False,
            "real_model_provider_connection": False,
            "merge_performed": False,
            "tag_created": False,
            "force_push": False,
            "default_branch_mutation": False,
        },
    }


def format_post_v1_roadmap(payload: dict[str, Any]) -> str:
    baseline = payload["baseline"]
    lines = [
        ROADMAP_MARKER,
        f"status: {payload['status']}",
        f"release_tag: {baseline['tag']}",
        f"release_commit: {baseline['release_commit']}",
        f"post_v1_branch: {baseline['post_v1_branch']}",
        "lanes:",
    ]
    for lane in payload["lanes"]:
        lines.append(f"  - {lane['label']} ({lane['id']})")
        for item in lane["focus"]:
            lines.append(f"    * {item}")
    lines.append("non_goals:")
    for item in payload["non_goals"]:
        lines.append(f"  - {item}")
    lines.append("validation_commands:")
    for command in payload["validation_commands"]:
        lines.append(f"  - {command}")
    lines.append("review_handoff_guidance:")
    for item in payload["review_handoff_guidance"]:
        lines.append(f"  - {item}")
    return "\n".join(lines)



def release_state_payload() -> dict[str, Any]:
    archive = Path("/opt/agent-office/agentoffice-v1.0.0-final-delivery-archive.tar.gz")
    sha256 = Path("/opt/agent-office/agentoffice-v1.0.0-final-delivery-archive.tar.gz.sha256")
    readback = Path("/opt/agent-office/V1_0_0_GITHUB_RELEASE_API_LONGRUN_READBACK")
    return {
        "schema_version": SCHEMA_VERSION,
        "packet_type": "agentoffice_v1_release_state",
        "release_tag": RELEASE_TAG,
        "release_commit": RELEASE_COMMIT,
        "mainline_branch": MAINLINE_BRANCH,
        "archive_present": archive.exists() and archive.is_file() and not archive.is_symlink(),
        "sha256_present": sha256.exists() and sha256.is_file() and not sha256.is_symlink(),
        "github_release_status": "skipped_no_token",
        "publish_state": "skipped",
        "release_url": None,
        "readback_dir_present": readback.exists() and readback.is_dir() and not readback.is_symlink(),
        "github_write_performed": False,
        "network_required": False,
        "token_required_for_publish": True,
        "safety": _release_ops_safety(),
    }


def github_release_handoff_payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "packet_type": "agentoffice_v1_github_release_handoff",
        "release_tag": RELEASE_TAG,
        "release_title": RELEASE_TITLE,
        "status": "tokenless_handoff_ready",
        "github_write_performed": False,
        "network_required": False,
        "operator_steps": [
            "Confirm v1.0.0 tag points at the recorded release commit.",
            "Verify release archive and SHA256 sidecar locally.",
            "Create or verify the GitHub Release only from an authenticated operator session.",
            "Upload required assets without deleting or overwriting existing release assets unless explicitly approved.",
            "Save readback evidence and run verify-github-release-readback.",
        ],
        "required_assets": list(REQUIRED_RELEASE_ASSETS),
        "safety": _release_ops_safety(),
    }


def github_release_plan_payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "packet_type": "agentoffice_v1_github_release_plan",
        "release_tag": RELEASE_TAG,
        "release_title": RELEASE_TITLE,
        "plan_type": "dry_run_only",
        "github_write_performed": False,
        "network_required": False,
        "preflight": [
            "verify tag commit matches release commit",
            "verify archive checksum and internal SHA256SUMS",
            "verify required release notes and reports are present",
            "confirm token scope and operator approval before any remote write",
        ],
        "write_steps_when_authorized": [
            "create draft release if it does not exist",
            "upload required assets exactly once",
            "read back release JSON and asset list",
            "run local readback verifier",
        ],
        "stop_conditions": [
            "missing token or explicit operator approval",
            "existing release has conflicting assets",
            "tag commit mismatch",
            "partial remote state",
        ],
        "safety": _release_ops_safety(),
    }


def release_candidate_payload(version: str) -> dict[str, Any]:
    if not re.fullmatch(r"v\d+\.\d+\.\d+", version):
        return {
            "ok": False,
            "schema_version": SCHEMA_VERSION,
            "packet_type": "agentoffice_v1_release_candidate",
            "version": version,
            "errors": ["release_candidate_invalid_version"],
        }
    return {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "packet_type": "agentoffice_v1_release_candidate",
        "version": version,
        "base_release": RELEASE_TAG,
        "base_commit": RELEASE_COMMIT,
        "status": "candidate_plan_ready",
        "github_write_performed": False,
        "tag_created": False,
        "network_required": False,
        "required_validations": [
            "python3 -m compileall agent_office tests",
            "python3 -m unittest",
            "python3 -m unittest discover -s tests -p 'test_*.py'",
            "python3 -m agent_office doctor --adapters",
            "./scripts/verify.sh",
            "git diff --check",
        ],
        "required_packets": [
            "release-state",
            "github-release-handoff",
            "github-release-plan",
            "merge gate packet",
            "review bundle",
        ],
        "safety": _release_ops_safety(),
        "errors": [],
    }


def format_release_state(payload: dict[str, Any]) -> str:
    return "\n".join([
        "AGENTOFFICE_V1_RELEASE_STATE",
        f"release_tag: {payload['release_tag']}",
        f"release_commit: {payload['release_commit']}",
        f"archive_present: {_bool_text(bool(payload['archive_present']))}",
        f"sha256_present: {_bool_text(bool(payload['sha256_present']))}",
        f"github_release_status: {payload['github_release_status']}",
        f"publish_state: {payload['publish_state']}",
        "github_write_performed: false",
        "network_required: false",
    ])


def format_github_release_handoff(payload: dict[str, Any]) -> str:
    lines = ["AGENTOFFICE_V1_GITHUB_RELEASE_HANDOFF", f"status: {payload['status']}", "github_write_performed: false", "operator_steps:"]
    lines.extend(f"  - {step}" for step in payload["operator_steps"])
    lines.append("required_assets:")
    lines.extend(f"  - {asset}" for asset in payload["required_assets"])
    return "\n".join(lines)


def format_github_release_plan(payload: dict[str, Any]) -> str:
    lines = ["AGENTOFFICE_V1_GITHUB_RELEASE_PLAN", f"plan_type: {payload['plan_type']}", "github_write_performed: false", "preflight:"]
    lines.extend(f"  - {step}" for step in payload["preflight"])
    lines.append("stop_conditions:")
    lines.extend(f"  - {condition}" for condition in payload["stop_conditions"])
    return "\n".join(lines)


def format_release_candidate(payload: dict[str, Any]) -> str:
    marker = "AGENTOFFICE_V1_RELEASE_CANDIDATE" if payload["ok"] else "AGENTOFFICE_V1_RELEASE_CANDIDATE_FAIL"
    lines = [marker, f"ok: {_bool_text(bool(payload['ok']))}", f"version: {payload['version']}"]
    if payload["ok"]:
        lines.extend([f"base_release: {payload['base_release']}", "github_write_performed: false", "tag_created: false", "required_validations:"])
        lines.extend(f"  - {command}" for command in payload["required_validations"])
    else:
        lines.append("errors:")
        lines.extend(f"  - {error}" for error in payload["errors"])
    return "\n".join(lines)


def _release_ops_safety() -> dict[str, bool]:
    return {
        "dotenv_read": False,
        "env_vars_printed": False,
        "token_printed": False,
        "github_write_performed": False,
        "tag_created": False,
        "tag_deleted": False,
        "release_deleted": False,
        "release_asset_deleted": False,
        "network_required": False,
        "provider_runtime_adapter_external_behavior": False,
    }

def _safe_file_path(path: str, code_prefix: str, errors: list[str]) -> Path | None:
    if not str(path).strip():
        errors.append(f"{code_prefix}_missing_path")
        return None
    candidate = Path(path)
    if _has_dotenv_component(candidate):
        errors.append(f"{code_prefix}_dotenv_refused")
        return None
    if not candidate.exists():
        errors.append(f"{code_prefix}_missing")
        return None
    if candidate.is_symlink():
        errors.append(f"{code_prefix}_symlink")
        return None
    if candidate.is_dir():
        errors.append(f"{code_prefix}_directory")
        return None
    if not candidate.is_file():
        errors.append(f"{code_prefix}_not_file")
        return None
    return candidate.resolve()


def _safe_dir_path(path: str, code_prefix: str, errors: list[str]) -> Path | None:
    if not str(path).strip():
        errors.append(f"{code_prefix}_missing_path")
        return None
    candidate = Path(path)
    if _has_dotenv_component(candidate):
        errors.append(f"{code_prefix}_dotenv_refused")
        return None
    if not candidate.exists():
        errors.append(f"{code_prefix}_missing")
        return None
    if candidate.is_symlink():
        errors.append(f"{code_prefix}_symlink")
        return None
    if not candidate.is_dir():
        errors.append(f"{code_prefix}_not_directory")
        return None
    return candidate.resolve()


def _read_expected_sha256(path: Path, errors: list[str]) -> str | None:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        errors.append("release_archive_sha256_non_utf8")
        return None
    except OSError:
        errors.append("release_archive_sha256_unreadable")
        return None
    for token in text.replace("\n", " ").split():
        if re.fullmatch(r"[0-9a-fA-F]{64}", token):
            return token.lower()
    errors.append("release_archive_sha256_missing_digest")
    return None


def _file_sha256(path: Path, errors: list[str]) -> str | None:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        errors.append("release_archive_unreadable")
        return None
    return digest.hexdigest()


def _verify_archive_members(path: Path, errors: list[str]) -> dict[str, Any]:
    result = {"required_members_present": False, "internal_sha256_ok": False, "checked_files": 0}
    try:
        with tarfile.open(path, "r:gz") as tar:
            members = tar.getmembers()
            member_by_name = {member.name: member for member in members}
            for member in members:
                if _unsafe_archive_name(member.name):
                    errors.append(f"release_archive_unsafe_member:{member.name}")
            missing_required = [name for name in REQUIRED_ARCHIVE_MEMBERS if name not in member_by_name]
            if missing_required:
                for name in missing_required:
                    if name.endswith("README_FOR_RELEASE_ARCHIVE.md"):
                        errors.append("release_archive_missing_internal_manifest")
                    elif name.endswith("SHA256SUMS"):
                        errors.append("release_archive_missing_internal_sha256sums")
                    else:
                        errors.append(f"release_archive_missing_required_member:{name}")
                return result
            result["required_members_present"] = True
            sums_member = member_by_name[f"{ARCHIVE_ROOT}/SHA256SUMS"]
            sums_file = tar.extractfile(sums_member)
            if sums_file is None:
                errors.append("release_archive_internal_sha256sums_unreadable")
                return result
            try:
                sums_text = sums_file.read().decode("utf-8")
            except UnicodeDecodeError:
                errors.append("release_archive_internal_sha256sums_non_utf8")
                return result
            entries = _parse_internal_sha256sums(sums_text, errors)
            for member in members:
                if member.isfile() and member.name != f"{ARCHIVE_ROOT}/SHA256SUMS" and member.name not in entries:
                    errors.append(f"release_archive_internal_sha256_missing_entry:{member.name}")
            for member_name, expected in entries.items():
                member = member_by_name.get(member_name)
                if member is None:
                    errors.append(f"release_archive_internal_sha256_missing_member:{member_name}")
                    continue
                if not member.isfile():
                    errors.append(f"release_archive_internal_sha256_not_regular_file:{member_name}")
                    continue
                extracted = tar.extractfile(member)
                if extracted is None:
                    errors.append(f"release_archive_internal_sha256_unreadable:{member_name}")
                    continue
                actual = hashlib.sha256(extracted.read()).hexdigest()
                result["checked_files"] += 1
                if actual != expected:
                    errors.append(f"release_archive_bad_internal_checksum:{member_name}")
            result["internal_sha256_ok"] = not any(
                error.startswith("release_archive_internal_sha256") or error.startswith("release_archive_bad_internal_checksum")
                for error in errors
            )
            return result
    except (tarfile.TarError, OSError, EOFError):
        errors.append("release_archive_corrupt_tar")
        return result


def _parse_internal_sha256sums(text: str, errors: list[str]) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
            errors.append(f"release_archive_internal_sha256sums_malformed:{line_number}")
            continue
        rel_path = parts[1].strip()
        if rel_path.startswith("*"):
            rel_path = rel_path[1:].strip()
        while rel_path.startswith("./"):
            rel_path = rel_path[2:]
        if not rel_path or _unsafe_archive_name(rel_path):
            errors.append(f"release_archive_internal_sha256sums_unsafe_path:{line_number}")
            continue
        member_name = rel_path if rel_path.startswith(f"{ARCHIVE_ROOT}/") else f"{ARCHIVE_ROOT}/{rel_path}"
        entries[member_name] = parts[0].lower()
    if not entries:
        errors.append("release_archive_internal_sha256sums_empty")
    return entries


def _read_json_object(path: Path, code_prefix: str, errors: list[str]) -> dict[str, Any] | None:
    if _has_dotenv_component(path):
        errors.append(f"{code_prefix}_dotenv_refused")
        return None
    if not path.exists():
        errors.append(f"{code_prefix}_missing")
        return None
    if path.is_symlink():
        errors.append(f"{code_prefix}_symlink")
        return None
    if path.is_dir():
        errors.append(f"{code_prefix}_directory")
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        errors.append(f"{code_prefix}_non_utf8")
        return None
    except OSError:
        errors.append(f"{code_prefix}_unreadable")
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        errors.append(f"{code_prefix}_malformed_json")
        return None
    if not isinstance(data, dict):
        errors.append(f"{code_prefix}_not_object")
        return None
    return data


def _asset_names(data: dict[str, Any]) -> list[str]:
    raw_assets = data.get("assets_uploaded")
    if raw_assets is None:
        raw_assets = data.get("assets")
    if not isinstance(raw_assets, list):
        return []
    names: list[str] = []
    for asset in raw_assets:
        if isinstance(asset, str):
            names.append(asset)
        elif isinstance(asset, dict) and isinstance(asset.get("name"), str):
            names.append(asset["name"])
    return names


def _string_value(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _valid_release_url(url: str) -> bool:
    return url.startswith("https://github.com/mqpmqp/agent-office/releases")


def _has_dotenv_component(path: Path) -> bool:
    return any(part == ".env" for part in path.parts)


def _unsafe_archive_name(name: str) -> bool:
    normalized = name.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part and part != "."]
    return normalized.startswith("/") or any(part == ".." for part in parts)


def _bool_text(value: bool) -> str:
    return "true" if value else "false"
