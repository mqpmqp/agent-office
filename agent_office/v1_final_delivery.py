from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
PACKET_TYPE = "agentoffice_v1_final_delivery"
PHASE = "P49"
STATUS = "ready_for_v1_final_review"
TEXT_MARKER = "AGENTOFFICE_V1_FINAL_DELIVERY_PACKET"
VERIFY_PASS_MARKER = "AGENTOFFICE_V1_FINAL_DELIVERY_VERIFY_PASS"
VERIFY_FAIL_MARKER = "AGENTOFFICE_V1_FINAL_DELIVERY_VERIFY_FAIL"
SOURCE_BRANCH = "phase49/agentoffice-v1-final-delivery-batch"
TARGET_BRANCH = "phase6/mainline"
REVIEW_OUTPUT = "P49_CLAUDE_ARTIFACT_REVIEW_OUTPUT.md"

REQUIRED_TOP_LEVEL_KEYS = (
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
)

REQUIRED_SAFETY_KEYS = (
    "dotenv_read",
    "env_vars_printed",
    "provider_runtime_adapter_external_behavior",
    "real_model_provider_connection",
    "real_worker_or_job_started",
    "merge_performed",
    "tag_created",
    "force_push",
    "default_branch_mutation",
)

REQUIRED_VALIDATION_COMMANDS = (
    "python3 -m compileall agent_office tests",
    "python3 -m unittest",
    "python3 -m unittest discover -s tests -p 'test_*.py'",
    "python3 -m agent_office doctor --adapters",
    "./scripts/verify.sh",
    "./scripts/smoke-test.sh P6-PROFILES",
    "python3 -m agent_office run-staged P6-PROFILES --dry-run --reset",
    "python3 -m agent_office profiles --name lowest-cost --plan --json",
    "python3 -m agent_office v1 final-delivery --help",
    "python3 -m agent_office v1 final-delivery --json",
    "python3 -m agent_office v1 final-delivery",
    "python3 -m agent_office v1 final-delivery --out /tmp/agentoffice-v1-final-delivery.json --json",
    "python3 -m agent_office v1 verify-final-delivery --path /tmp/agentoffice-v1-final-delivery.json --json",
    "python3 -m agent_office v1 verify-final-delivery --path /tmp/agentoffice-v1-final-delivery.json",
    "python3 -m agent_office v1 verify-final-delivery --path /tmp/does-not-exist --json || true",
    "python3 -m agent_office v1 verify-final-delivery --path /tmp/agentoffice-v1-final-delivery-bad.json --json || true",
    "git diff --check",
)


class V1FinalDeliveryError(ValueError):
    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


def build_final_delivery_packet(project_root: Path) -> dict[str, Any]:
    branch = _git(project_root, "branch", "--show-current") or "detached"
    head = _git(project_root, "rev-parse", "HEAD")
    baseline = _git(project_root, "merge-base", "HEAD", f"origin/{TARGET_BRANCH}")
    if baseline == "unavailable":
        baseline = _git(project_root, "rev-parse", f"origin/{TARGET_BRANCH}")
    if baseline == "unavailable":
        baseline = head

    return {
        "schema_version": SCHEMA_VERSION,
        "packet_type": PACKET_TYPE,
        "phase": PHASE,
        "status": STATUS,
        "repo": {
            "name": "mqpmqp/agent-office",
            "target_branch": TARGET_BRANCH,
            "expected_source_branch": SOURCE_BRANCH,
            "current_branch": branch,
            "head": head,
            "baseline": baseline,
            "baseline_source": f"git merge-base HEAD origin/{TARGET_BRANCH}",
        },
        "delivery": {
            "version": "v1",
            "final_implementation_batch": PHASE,
            "review_ready": True,
            "implementation_report": "P49_AGENTOFFICE_V1_FINAL_DELIVERY_BATCH_REPORT.md",
        },
        "contracts": {
            "cli_surfaces": [
                "python3 -m agent_office v1 final-delivery --json",
                "python3 -m agent_office v1 final-delivery",
                "python3 -m agent_office v1 final-delivery --out /tmp/agentoffice-v1-final-delivery.json --json",
                "python3 -m agent_office v1 verify-final-delivery --path /tmp/agentoffice-v1-final-delivery.json --json",
                "python3 -m agent_office v1 verify-final-delivery --path /tmp/agentoffice-v1-final-delivery.json",
            ],
            "existing_static_surfaces": [
                "python3 -m agent_office review codex-deliver",
                "python3 -m agent_office review-artifact export",
                "python3 -m agent_office review-artifact verify",
                "python3 -m agent_office runtime worker-result final-readiness",
                "python3 -m agent_office runtime worker-result promotion-evidence",
                "python3 -m agent_office runtime worker-result dry-run-publish",
            ],
            "static_only": True,
            "deterministic_contract": "git metadata plus static v1 constants; no wall-clock timestamp",
        },
        "validation": {
            "release_blocking_commands": list(REQUIRED_VALIDATION_COMMANDS),
            "positive_smokes": [
                "v1 final-delivery --json",
                "v1 final-delivery text marker",
                "v1 final-delivery --out then verify JSON/text",
            ],
            "negative_smokes": [
                "verify missing path",
                "verify bad JSON",
                "verify wrong packet_type",
                "verify missing required key",
                "verify directory path",
                "verify symlink path",
                "verify non-UTF-8 input",
                "final-delivery .env output rejected",
                "final-delivery directory output rejected",
            ],
        },
        "artifacts": {
            "tracked_report": "P49_AGENTOFFICE_V1_FINAL_DELIVERY_BATCH_REPORT.md",
            "review_bundle": "P49_REVIEW_ARTIFACT_BUNDLE.md",
            "review_bundle_sha256": "P49_REVIEW_ARTIFACT_BUNDLE.md.sha256",
            "claude_artifact_review_output": REVIEW_OUTPUT,
            "review_fix_delta_output": "P49_CLAUDE_REVIEW_FIX_DELTA_REVIEW_OUTPUT.md",
            "merge_gate_review_output": "P49_CLAUDE_MERGE_GATE_REVIEW_OUTPUT.md",
            "merge_gate_packet": "P49_MERGE_GATE_PACKET.md",
            "archive_index": "P49_V1_FINAL_DELIVERY_ARCHIVE_INDEX.md",
        },
        "review": {
            "reviewer": "Claude",
            "mode": "artifact_based",
            "expected_output": REVIEW_OUTPUT,
            "required_marker": "P49_ARTIFACT_REVIEW_COMPLETE",
            "rules": [
                "review P49_REVIEW_ARTIFACT_BUNDLE.md and .sha256 as uploaded artifacts",
                "do not claim Claude personally executed VPS commands unless the source report proves it",
                "report blockers against CLI contract, deterministic schema, safety, tests, and README accuracy",
            ],
        },
        "merge_gate": {
            "target_branch": TARGET_BRANCH,
            "allowed_after": [
                "P49 source branch pushed",
                "P49 artifact-based review complete",
                "review-fix delta complete if required",
                "merge gate explicitly authorized",
            ],
            "forbidden_in_p49": [
                "merge phase6/mainline",
                "create tag",
                "force push",
                "mutate default branch",
                "trigger provider/runtime/adapter external behavior",
            ],
        },
        "safety": {
            "dotenv_read": False,
            "env_vars_printed": False,
            "provider_runtime_adapter_external_behavior": False,
            "real_model_provider_connection": False,
            "real_worker_or_job_started": False,
            "merge_performed": False,
            "tag_created": False,
            "force_push": False,
            "default_branch_mutation": False,
        },
        "non_goals": [
            "real provider integration",
            "real scheduler",
            "real worker marketplace",
            "real trading or execution",
            "mainline merge",
            "tag or release creation",
        ],
        "next_actions": [
            "P49 Claude artifact-based review",
            "P49 review-fix delta only if review requires changes",
            "P49 merge gate",
            "v1 tag/release declaration only after merge gate",
        ],
    }


def write_final_delivery_packet(out: str, packet: dict[str, Any], project_root: Path) -> Path:
    output_path = _safe_output_path(out, project_root, "v1_final_delivery_output")
    tmp = output_path.with_name(f"{output_path.name}.tmp")
    if tmp.exists() and tmp.is_symlink():
        raise V1FinalDeliveryError("v1_final_delivery_output_temp_symlink", f"Refusing symlink temp output path: {tmp}")
    try:
        tmp.write_text(json.dumps(packet, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(output_path)
    except OSError as exc:
        raise V1FinalDeliveryError("v1_final_delivery_output_unwritable", f"Unable to write output path: {output_path}") from exc
    return output_path


def verify_final_delivery_packet(path: str, project_root: Path) -> dict[str, Any]:
    packet: dict[str, Any] | None = None
    errors: list[str] = []
    try:
        input_path = _safe_input_path(path, project_root, "v1_final_delivery_verify")
        try:
            text = input_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise V1FinalDeliveryError("v1_final_delivery_verify_non_utf8", f"Input must be UTF-8: {input_path}") from exc
        except OSError as exc:
            raise V1FinalDeliveryError("v1_final_delivery_verify_unreadable", f"Unable to read input path: {input_path}") from exc
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise V1FinalDeliveryError("v1_final_delivery_verify_bad_json", f"Input JSON is invalid: {input_path.name}") from exc
        if not isinstance(data, dict):
            raise V1FinalDeliveryError("v1_final_delivery_verify_not_object", "Final delivery packet must be a JSON object.")
        packet = data
        errors.extend(validate_final_delivery_packet(packet))
    except V1FinalDeliveryError as exc:
        errors.append(f"{exc.error_code}: {exc}")

    return {
        "ok": not errors,
        "packet_type": packet.get("packet_type") if packet else None,
        "schema_version": packet.get("schema_version") if packet else None,
        "phase": packet.get("phase") if packet else None,
        "status": packet.get("status") if packet else None,
        "errors": errors,
    }


def validate_final_delivery_packet(packet: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in REQUIRED_TOP_LEVEL_KEYS:
        if key not in packet:
            errors.append(f"missing_required_key:{key}")
    if packet.get("packet_type") != PACKET_TYPE:
        errors.append("wrong_packet_type")
    if packet.get("schema_version") != SCHEMA_VERSION:
        errors.append("wrong_schema_version")
    if packet.get("phase") != PHASE:
        errors.append("wrong_phase")
    if packet.get("status") != STATUS:
        errors.append("wrong_status")

    safety = packet.get("safety")
    if not isinstance(safety, dict):
        errors.append("missing_safety_object")
    else:
        for key in REQUIRED_SAFETY_KEYS:
            if key not in safety:
                errors.append(f"missing_safety_key:{key}")

    validation = packet.get("validation")
    commands = validation.get("release_blocking_commands") if isinstance(validation, dict) else None
    if not isinstance(commands, list):
        errors.append("missing_validation_commands")
    else:
        for command in REQUIRED_VALIDATION_COMMANDS:
            if command not in commands:
                errors.append(f"missing_validation_command:{command}")

    next_actions = packet.get("next_actions")
    if not isinstance(next_actions, list):
        errors.append("missing_next_actions")
    else:
        if any("P50" in str(action) for action in next_actions):
            errors.append("next_actions_must_not_reference_P50")
    return errors


def format_final_delivery_packet(packet: dict[str, Any]) -> str:
    repo = packet["repo"]
    validation = packet["validation"]
    artifacts = packet["artifacts"]
    merge_gate = packet["merge_gate"]
    lines = [
        TEXT_MARKER,
        f"phase: {packet['phase']}",
        f"status: {packet['status']}",
        f"current_branch: {repo['current_branch']}",
        f"head: {repo['head']}",
        f"baseline: {repo['baseline']}",
        "required_validation_commands:",
    ]
    for command in validation["release_blocking_commands"]:
        lines.append(f"  - {command}")
    lines.extend(
        [
            f"expected_review_output: {artifacts['claude_artifact_review_output']}",
            f"expected_merge_gate_next_step: {merge_gate['allowed_after'][-1]}",
            "safety_constraints:",
            "  - .env not read",
            "  - env vars not printed",
            "  - provider/runtime/adapter external behavior not triggered",
            "  - no merge, tag, force push, or default branch mutation in P49",
            "non_goals:",
        ]
    )
    for item in packet["non_goals"]:
        lines.append(f"  - {item}")
    lines.append("next_actions:")
    for item in packet["next_actions"]:
        lines.append(f"  - {item}")
    return "\n".join(lines)


def format_final_delivery_verify(payload: dict[str, Any]) -> str:
    marker = VERIFY_PASS_MARKER if payload["ok"] else VERIFY_FAIL_MARKER
    lines = [
        marker,
        f"ok: {str(payload['ok']).lower()}",
        f"packet_type: {payload['packet_type']}",
        f"schema_version: {payload['schema_version']}",
        f"phase: {payload['phase']}",
        f"status: {payload['status']}",
        "errors:",
    ]
    errors = payload["errors"]
    if errors:
        for error in errors:
            lines.append(f"  - {error}")
    else:
        lines.append("  - none")
    return "\n".join(lines)


def final_delivery_error_payload(command: str, exc: V1FinalDeliveryError) -> dict[str, Any]:
    return {
        "ok": False,
        "command": command,
        "packet_type": PACKET_TYPE,
        "schema_version": SCHEMA_VERSION,
        "phase": PHASE,
        "status": "error",
        "error_code": exc.error_code,
        "error": str(exc),
    }


def _git(project_root: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=project_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    except OSError:
        return "unavailable"
    if completed.returncode != 0:
        return "unavailable"
    return completed.stdout.strip() or "unavailable"


def _safe_input_path(path: str, project_root: Path, code_prefix: str) -> Path:
    candidate, resolved, allowed_root = _safe_candidate(path, project_root, code_prefix, kind="input")
    if not candidate.exists():
        raise V1FinalDeliveryError(f"{code_prefix}_missing", f"Input file does not exist: {candidate}")
    _reject_symlink_components(resolved, allowed_root, code_prefix)
    if candidate.is_symlink():
        raise V1FinalDeliveryError(f"{code_prefix}_symlink", f"Refusing symlink input path: {candidate}")
    if candidate.is_dir():
        raise V1FinalDeliveryError(f"{code_prefix}_directory", f"Input path is a directory: {candidate}")
    if not candidate.is_file():
        raise V1FinalDeliveryError(f"{code_prefix}_not_file", f"Input path is not a file: {candidate}")
    return resolved


def _safe_output_path(path: str, project_root: Path, code_prefix: str) -> Path:
    candidate, resolved, allowed_root = _safe_candidate(path, project_root, code_prefix, kind="output")
    _reject_symlink_components(candidate.parent.resolve(strict=False), allowed_root, code_prefix)
    if candidate.exists() and candidate.is_symlink():
        raise V1FinalDeliveryError(f"{code_prefix}_symlink", f"Refusing symlink output path: {candidate}")
    if candidate.exists() and candidate.is_dir():
        raise V1FinalDeliveryError(f"{code_prefix}_directory", f"Output path is a directory: {candidate}")
    try:
        candidate.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise V1FinalDeliveryError(f"{code_prefix}_parent_unwritable", f"Unable to create output parent: {candidate.parent}") from exc
    if candidate.parent.is_symlink():
        raise V1FinalDeliveryError(f"{code_prefix}_parent_symlink", f"Refusing symlink output parent: {candidate.parent}")
    if not candidate.parent.is_dir():
        raise V1FinalDeliveryError(f"{code_prefix}_parent_not_directory", f"Output parent is not a directory: {candidate.parent}")
    return resolved


def _safe_candidate(path: str, project_root: Path, code_prefix: str, *, kind: str) -> tuple[Path, Path, Path]:
    if not str(path).strip():
        raise V1FinalDeliveryError(f"{code_prefix}_required", f"{kind.title()} path is required.")
    raw = Path(path)
    if any(part == ".." for part in raw.parts):
        raise V1FinalDeliveryError(f"{code_prefix}_path_traversal", f"Refusing path traversal: {path}")
    if any(part == ".env" for part in raw.parts):
        raise V1FinalDeliveryError(f"{code_prefix}_dotenv_refused", f"Refusing .env path: {path}")
    root = project_root.resolve(strict=True)
    candidate = raw if raw.is_absolute() else root / raw
    resolved = candidate.resolve(strict=False)
    for allowed_root in _allowed_roots(root):
        if _is_relative_to(resolved, allowed_root):
            return candidate, resolved, allowed_root
    raise V1FinalDeliveryError(f"{code_prefix}_outside_allowed_roots", f"{kind.title()} path must stay inside the project root or temp directory: {path}")


def _allowed_roots(project_root: Path) -> tuple[Path, Path]:
    return (project_root, Path(tempfile.gettempdir()).resolve(strict=True))


def _reject_symlink_components(path: Path, allowed_root: Path, code_prefix: str) -> None:
    if not _is_relative_to(path, allowed_root):
        raise V1FinalDeliveryError(f"{code_prefix}_symlink_escape", f"Refusing path outside allowed root: {path}")
    current = allowed_root
    for part in path.relative_to(allowed_root).parts:
        current = current / part
        if current.exists() and current.is_symlink():
            raise V1FinalDeliveryError(f"{code_prefix}_symlink", f"Refusing symlink path component: {current}")


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
