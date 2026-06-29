from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any

from .review_artifact import self_check_review_artifact_payload
from .run_bundle import RunBundleError, validate_run_bundle_payload


SCHEMA_VERSION = 1
MAX_ARTIFACT_READ_BYTES = 1024 * 1024
DEFAULT_TMP_PATTERNS = ("agentoffice-*.md", "agentoffice-*.json", "agentoffice-*.sha256")
DEFAULT_KINDS = (
    "closure_artifact",
    "review_report",
    "sha256",
    "json",
    "markdown",
    "run_bundle",
    "unknown",
)

COMMAND_MAP = {
    "registry_help": "python3 -m agent_office review-artifact registry --help",
    "registry_list": "python3 -m agent_office review-artifact registry list --json",
    "registry_inspect": "python3 -m agent_office review-artifact registry inspect --path <artifact> --json",
    "registry_status": "python3 -m agent_office review-artifact registry status --json",
    "lifecycle_help": "python3 -m agent_office review-artifact lifecycle --help",
    "lifecycle_status": "python3 -m agent_office review-artifact lifecycle status --json",
    "lifecycle_verify": "python3 -m agent_office review-artifact lifecycle verify --json",
    "export_evidence_help": "python3 -m agent_office export-evidence --help",
    "export_evidence": "python3 -m agent_office export-evidence --out <dir> --json",
}

VALIDATION_COMMANDS = [
    "python3 -m compileall agent_office tests",
    "python3 -m unittest",
    "python3 -m unittest discover -s tests -p 'test_*.py'",
    "python3 -m agent_office doctor --adapters",
    "./scripts/verify.sh",
    "./scripts/smoke-test.sh P6-PROFILES",
    "python3 -m agent_office run-staged P6-PROFILES --dry-run --reset",
    "python3 -m agent_office review-artifact registry list --json",
    "python3 -m agent_office review-artifact lifecycle verify --json",
    "python3 -m agent_office export-evidence --out /tmp/agentoffice-p23-evidence --json",
]

SAFETY_BOUNDARIES = [
    "Static local filesystem scan only.",
    "Does not read .env files.",
    "Does not print environment variables.",
    "Does not call providers, adapters, runtimes, or models.",
    "Does not access the network.",
    "Does not follow symlinks.",
    "Does not read .git contents.",
    "Limits single-file content reads to 1 MiB.",
]

KNOWN_LIMITATIONS = [
    "Artifact kind detection is intentionally conservative and based on filenames plus lightweight local markers.",
    "Large files are recorded but not content-inspected or hash-verified by registry scans.",
    "Lifecycle verify only validates artifacts that match the existing review-artifact or run-bundle contracts.",
]

_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def registry_list_payload(*, project_root: Path, roots: list[str] | None = None) -> dict[str, Any]:
    root = project_root.resolve()
    warnings: list[str] = []
    errors: list[str] = []
    candidates, scanned_paths = _scan_candidates(root, roots or [], warnings)
    artifacts = [_artifact_entry(path, root) for path in candidates]
    counts = _registry_counts(artifacts)
    return {
        "schema_version": SCHEMA_VERSION,
        "valid": True,
        "command": _command_text("review-artifact registry list", roots),
        "artifacts": artifacts,
        "counts": counts,
        "warnings": _dedupe(warnings),
        "errors": errors,
        "scanned_paths": scanned_paths,
    }


def registry_inspect_payload(*, path: str | Path, project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    artifact = _artifact_entry(_coerce_path(path, root), root)
    return {
        "schema_version": SCHEMA_VERSION,
        "valid": bool(artifact["exists"]) and not artifact["errors"],
        "command": f"python3 -m agent_office review-artifact registry inspect --path {path}",
        "artifact": artifact,
        "warnings": list(artifact["warnings"]),
        "errors": list(artifact["errors"]),
    }


def registry_status_payload(*, project_root: Path, roots: list[str] | None = None) -> dict[str, Any]:
    listing = registry_list_payload(project_root=project_root, roots=roots)
    artifacts = listing["artifacts"]
    closure_artifacts = [item for item in artifacts if item["kind"] == "closure_artifact"]
    report_artifacts = [item for item in artifacts if item["kind"] == "review_report"]
    sha256_files = [item for item in artifacts if item["kind"] == "sha256"]
    return {
        "schema_version": SCHEMA_VERSION,
        "valid": True,
        "command": _command_text("review-artifact registry status", roots),
        "artifacts": artifacts,
        "counts": listing["counts"],
        "closure_artifacts": closure_artifacts,
        "report_artifacts": report_artifacts,
        "sha256_files": sha256_files,
        "warnings": listing["warnings"],
        "errors": listing["errors"],
        "scanned_paths": listing["scanned_paths"],
    }


def lifecycle_status_payload(*, project_root: Path, roots: list[str] | None = None) -> dict[str, Any]:
    status = registry_status_payload(project_root=project_root, roots=roots)
    artifacts = sorted(status["artifacts"], key=lambda item: str(item["path"]))
    verified_artifacts = [item for item in artifacts if item.get("sha256_verified") is True]
    pending_like = [item for item in artifacts if _is_pending_like(item)]
    real_closure_count = sum(1 for item in artifacts if item.get("detected_fields", {}).get("real_closure") is True)
    fixture_only_count = sum(1 for item in artifacts if item.get("detected_fields", {}).get("fixture_only") is True)
    pending_closed_count = sum(1 for item in artifacts if item.get("detected_fields", {}).get("pending_closed") is True)
    counts = dict(status["counts"])
    counts.update(
        {
            "known_artifacts": len(artifacts),
            "verified_artifacts": len(verified_artifacts),
            "pending_like_artifacts": len(pending_like),
            "real_closure_count": real_closure_count,
            "fixture_only_count": fixture_only_count,
            "pending_closed_count": pending_closed_count,
        }
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "valid": True,
        "command": _command_text("review-artifact lifecycle status", roots),
        "counts": counts,
        "known_artifacts": artifacts,
        "closure_artifacts": status["closure_artifacts"],
        "report_artifacts": status["report_artifacts"],
        "sha256_files": status["sha256_files"],
        "verified_artifacts": verified_artifacts,
        "pending_like_artifacts": pending_like,
        "real_closure_count": real_closure_count,
        "fixture_only_count": fixture_only_count,
        "pending_closed_count": pending_closed_count,
        "warnings": status["warnings"],
        "errors": status["errors"],
        "scanned_paths": status["scanned_paths"],
    }


def lifecycle_verify_payload(*, project_root: Path, roots: list[str] | None = None) -> dict[str, Any]:
    listing = registry_list_payload(project_root=project_root, roots=roots)
    checked: list[dict[str, Any]] = []
    verified: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    warnings = list(listing["warnings"])
    errors = list(listing["errors"])
    for artifact in listing["artifacts"]:
        result = _verify_artifact_entry(artifact, project_root.resolve())
        bucket = result.pop("bucket")
        if bucket == "checked":
            checked.append(result)
            if result["valid"]:
                verified.append(result)
            else:
                invalid.append(result)
        else:
            skipped.append(result)
            reason = result.get("reason")
            if reason:
                warnings.append(f"skipped {result['path']}: {reason}")
    counts = dict(listing["counts"])
    counts.update(
        {
            "checked_count": len(checked),
            "verified_count": len(verified),
            "invalid_count": len(invalid),
            "skipped_count": len(skipped),
        }
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "valid": not invalid,
        "command": _command_text("review-artifact lifecycle verify", roots),
        "checked": checked,
        "verified": verified,
        "invalid": invalid,
        "skipped": skipped,
        "counts": counts,
        "warnings": _dedupe(warnings),
        "errors": errors,
        "scanned_paths": listing["scanned_paths"],
    }


def export_evidence_payload(*, out: str | Path, project_root: Path, roots: list[str] | None = None) -> dict[str, Any]:
    root = project_root.resolve()
    out_dir = _prepare_output_dir(out)
    registry = registry_status_payload(project_root=root, roots=roots)
    lifecycle = lifecycle_status_payload(project_root=root, roots=roots)
    verification = lifecycle_verify_payload(project_root=root, roots=roots)
    example_validation = _example_validation(verification)
    warnings = _dedupe([*registry["warnings"], *lifecycle["warnings"], *verification["warnings"]])
    errors = _dedupe([*registry["errors"], *lifecycle["errors"], *verification["errors"]])
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_by": "python3 -m agent_office export-evidence",
        "repo": _repo_metadata(root),
        "commit": _git_value(root, "rev-parse", "HEAD"),
        "branch": _git_value(root, "branch", "--show-current"),
        "command_map": COMMAND_MAP,
        "validation_commands": VALIDATION_COMMANDS,
        "safety_boundaries": SAFETY_BOUNDARIES,
        "known_limitations": KNOWN_LIMITATIONS,
        "registry_summary": _summary_from_registry(registry),
        "lifecycle_summary": _summary_from_lifecycle(lifecycle, verification),
        "example_artifact_validation": example_validation,
        "files": [
            {"path": "manifest.json", "kind": "manifest"},
            {"path": "README.md", "kind": "readme"},
        ],
        "warnings": warnings,
        "errors": errors,
    }
    readme = _evidence_readme(manifest)
    manifest_path = out_dir / "manifest.json"
    readme_path = out_dir / "README.md"
    _write_text(manifest_path, json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    _write_text(readme_path, readme)
    return {
        "schema_version": SCHEMA_VERSION,
        "valid": not errors,
        "command": _command_text("export-evidence", roots, out=out),
        "out": str(out_dir),
        "manifest_path": str(manifest_path),
        "readme_path": str(readme_path),
        "manifest": manifest,
        "warnings": warnings,
        "errors": errors,
    }


def format_registry_list(payload: dict[str, Any]) -> str:
    lines = [
        "AgentOffice artifact registry",
        f"artifacts: {payload['counts']['total']}",
        f"warnings: {len(payload.get('warnings', []))}",
        f"errors: {len(payload.get('errors', []))}",
    ]
    for item in payload["artifacts"]:
        verified = item.get("sha256_verified")
        verified_text = "unknown" if verified is None else str(verified).lower()
        lines.append(f"- {item['kind']}: {item['path']} (sha256_verified={verified_text})")
    for warning in payload.get("warnings", []):
        lines.append(f"warning: {warning}")
    return "\n".join(lines)


def format_registry_inspect(payload: dict[str, Any]) -> str:
    item = payload["artifact"]
    lines = [
        "AgentOffice artifact inspection",
        f"path: {item['path']}",
        f"kind: {item['kind']}",
        f"exists: {str(item['exists']).lower()}",
        f"size_bytes: {item['size_bytes']}",
        f"sha256_path: {item['sha256_path']}",
        f"sha256_verified: {item['sha256_verified']}",
        f"warnings: {len(item['warnings'])}",
        f"errors: {len(item['errors'])}",
    ]
    if item["detected_fields"]:
        lines.append("detected_fields:")
        for key in sorted(item["detected_fields"]):
            lines.append(f"  {key}: {item['detected_fields'][key]}")
    for warning in item["warnings"]:
        lines.append(f"warning: {warning}")
    for error in item["errors"]:
        lines.append(f"error: {error}")
    return "\n".join(lines)


def format_registry_status(payload: dict[str, Any]) -> str:
    counts = payload["counts"]
    return "\n".join(
        [
            "AgentOffice artifact registry status",
            f"artifacts: {counts['total']}",
            f"closure_artifacts: {counts['closure_artifacts']}",
            f"report_artifacts: {counts['review_reports']}",
            f"sha256_files: {counts['sha256_files']}",
            f"verified_artifacts: {counts['sha256_verified']}",
            f"warnings: {len(payload.get('warnings', []))}",
            f"errors: {len(payload.get('errors', []))}",
        ]
    )


def format_lifecycle_status(payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            "AgentOffice artifact lifecycle status",
            f"known_artifacts: {payload['counts']['known_artifacts']}",
            f"verified_artifacts: {payload['counts']['verified_artifacts']}",
            f"pending_like_artifacts: {payload['counts']['pending_like_artifacts']}",
            f"real_closure_count: {payload['real_closure_count']}",
            f"fixture_only_count: {payload['fixture_only_count']}",
            f"pending_closed_count: {payload['pending_closed_count']}",
            f"warnings: {len(payload.get('warnings', []))}",
            f"errors: {len(payload.get('errors', []))}",
        ]
    )


def format_lifecycle_verify(payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            "AgentOffice artifact lifecycle verify",
            f"checked: {payload['counts']['checked_count']}",
            f"verified: {payload['counts']['verified_count']}",
            f"invalid: {payload['counts']['invalid_count']}",
            f"skipped: {payload['counts']['skipped_count']}",
            f"warnings: {len(payload.get('warnings', []))}",
            f"errors: {len(payload.get('errors', []))}",
        ]
    )


def format_export_evidence(payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            "AgentOffice evidence package exported",
            f"out: {payload['out']}",
            f"manifest: {payload['manifest_path']}",
            f"README: {payload['readme_path']}",
            f"valid: {str(payload['valid']).lower()}",
            f"warnings: {len(payload.get('warnings', []))}",
            f"errors: {len(payload.get('errors', []))}",
        ]
    )


def _scan_candidates(project_root: Path, roots: list[str], warnings: list[str]) -> tuple[list[Path], list[str]]:
    paths: list[Path] = []
    scanned_paths: list[str] = []
    if roots:
        for raw_root in roots:
            scan_root = _coerce_path(raw_root, project_root)
            scanned_paths.append(str(scan_root))
            if _has_forbidden_part(scan_root):
                warnings.append(f"root_skipped_forbidden_path: {scan_root}")
                continue
            if scan_root.is_symlink():
                warnings.append(f"root_skipped_symlink: {scan_root}")
                continue
            if not scan_root.exists():
                warnings.append(f"root_missing: {scan_root}")
                continue
            before = len(paths)
            paths.extend(_walk_root(scan_root))
            if len(paths) == before:
                warnings.append(f"root_empty: {scan_root}")
        return _dedupe_paths(paths), scanned_paths

    tmp_root = Path("/tmp")
    for pattern in DEFAULT_TMP_PATTERNS:
        for path in sorted(tmp_root.glob(pattern), key=lambda item: str(item)):
            paths.append(path)
    for path in sorted(project_root.glob("*REPORT.md"), key=lambda item: str(item)):
        paths.append(path)
    runs_root = project_root / ".ai" / "runs"
    if runs_root.exists() and not runs_root.is_symlink():
        for path in sorted(runs_root.iterdir(), key=lambda item: str(item)):
            paths.append(path)
    scanned_paths = [str(path) for path in _dedupe_paths(paths)]
    return _dedupe_paths(paths), scanned_paths


def _walk_root(root: Path) -> list[Path]:
    if root.is_file() or root.is_symlink():
        return [root]
    if not root.is_dir():
        return []
    found: list[Path] = []
    for current, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        dirnames[:] = sorted(dirname for dirname in dirnames if dirname not in {".git", ".env"})
        filenames = sorted(filenames)
        if current_path != root and _looks_like_run_bundle(current_path):
            found.append(current_path)
        for filename in filenames:
            path = current_path / filename
            if _has_forbidden_part(path):
                continue
            found.append(path)
    return found


def _artifact_entry(path: Path, project_root: Path) -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []
    exists = path.exists() or path.is_symlink()
    size_bytes: int | None = None
    detected_fields: dict[str, Any] = {}
    sha256_path: str | None = None
    sha256_verified: bool | None = None

    if _has_forbidden_part(path):
        return _entry(path, "unknown", exists, None, None, None, {}, ["forbidden_path_skipped"], [])
    if path.is_symlink():
        return _entry(path, _kind_from_path(path, None), exists, None, None, None, {}, ["symlink_skipped"], [])
    if not exists:
        return _entry(path, "unknown", False, None, None, None, {}, [], ["missing_path"])
    try:
        size_bytes = path.stat().st_size if path.is_file() else 0
    except OSError as exc:
        errors.append(f"stat_error: {exc}")
    if path.is_dir():
        kind = "run_bundle" if _looks_like_run_bundle(path) else "unknown"
        if kind == "run_bundle":
            detected_fields.update(_run_bundle_detected_fields(path, project_root, warnings))
        return _entry(path, kind, True, size_bytes, None, None, detected_fields, warnings, errors)

    text = _read_limited_text(path, size_bytes, warnings)
    kind = _kind_from_path(path, text)
    detected_fields.update(_detected_fields(path, text, kind, warnings))
    if kind != "sha256":
        sidecar = Path(f"{path}.sha256")
        if sidecar.exists() or sidecar.is_symlink():
            sha256_path = str(sidecar)
            sha256_verified = _verify_sha256_sidecar(path, sidecar, size_bytes, warnings, errors)
    return _entry(path, kind, True, size_bytes, sha256_path, sha256_verified, detected_fields, warnings, errors)


def _entry(
    path: Path,
    kind: str,
    exists: bool,
    size_bytes: int | None,
    sha256_path: str | None,
    sha256_verified: bool | None,
    detected_fields: dict[str, Any],
    warnings: list[str],
    errors: list[str],
) -> dict[str, Any]:
    return {
        "path": str(path),
        "kind": kind,
        "exists": exists,
        "size_bytes": size_bytes,
        "sha256_path": sha256_path,
        "sha256_verified": sha256_verified,
        "detected_fields": detected_fields,
        "warnings": _dedupe(warnings),
        "errors": _dedupe(errors),
    }


def _kind_from_path(path: Path, text: str | None) -> str:
    lower = path.name.lower()
    if lower.endswith(".sha256"):
        return "sha256"
    if lower.endswith("report.md"):
        return "review_report"
    if text and "# AgentOffice Claude Pending Review Closure" in text:
        return "closure_artifact"
    if lower.endswith(".json"):
        return "json"
    if lower.endswith(".md"):
        return "markdown"
    return "unknown"


def _detected_fields(path: Path, text: str | None, kind: str, warnings: list[str]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    if text is None:
        return fields
    if kind == "json":
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            warnings.append(f"bad_json: {exc.msg}")
            return fields
        if isinstance(value, dict):
            for key in ("schema_version", "kind", "valid"):
                if key in value:
                    fields[key] = value[key]
            gate = value.get("review_gate")
            if isinstance(gate, dict):
                fields.update(_review_gate_fields(gate))
        return fields
    gate = _extract_review_gate_fields(text)
    fields.update(gate)
    for key in ("gate_mode", "claude_review_status", "real_closure", "fixture_only", "pending_closed", "follow_up_required"):
        if key not in fields:
            value = _line_field(text, key)
            if value is not None:
                fields[key] = value
    if "P18_CLAUDE_PENDING_REVIEW_CLOSURE_ARTIFACT_COMPLETE" in text:
        fields["closure_marker"] = "P18_CLAUDE_PENDING_REVIEW_CLOSURE_ARTIFACT_COMPLETE"
    if "REVIEW_ARTIFACT_EXPORT_COMPLETE" in text:
        fields["review_artifact_marker"] = "REVIEW_ARTIFACT_EXPORT_COMPLETE"
    if path.name.lower().endswith("report.md"):
        fields.setdefault("report_artifact", True)
    return fields


def _extract_review_gate_fields(text: str) -> dict[str, Any]:
    marker = "### review_gate JSON"
    if marker not in text:
        return {}
    tail = text.split(marker, 1)[1]
    match = re.search(r"```json\s*(.*?)\s*```", tail, flags=re.DOTALL)
    if not match:
        return {}
    try:
        value = json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}
    if not isinstance(value, dict):
        return {}
    return _review_gate_fields(value)


def _review_gate_fields(value: dict[str, Any]) -> dict[str, Any]:
    keys = ("gate_mode", "claude_review_status", "real_closure", "fixture_only", "pending_closed", "follow_up_required")
    return {key: value[key] for key in keys if key in value}


def _line_field(text: str, key: str) -> Any:
    match = re.search(rf"^[- ]*{re.escape(key)}:\s*(.+)$", text, flags=re.MULTILINE)
    if not match:
        return None
    value = match.group(1).strip()
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if value == "[]":
        return []
    return value


def _read_limited_text(path: Path, size_bytes: int | None, warnings: list[str]) -> str | None:
    if size_bytes is not None and size_bytes > MAX_ARTIFACT_READ_BYTES:
        warnings.append(f"file_too_large_skipped_content_read: {size_bytes}")
        return None
    try:
        data = path.read_bytes()
    except OSError as exc:
        warnings.append(f"read_error: {exc}")
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        warnings.append("non_utf8_content")
        return data.decode("utf-8", errors="replace")


def _verify_sha256_sidecar(path: Path, sidecar: Path, size_bytes: int | None, warnings: list[str], errors: list[str]) -> bool | None:
    if sidecar.is_symlink():
        warnings.append("sha256_sidecar_symlink_skipped")
        return None
    try:
        sidecar_size = sidecar.stat().st_size
    except OSError as exc:
        warnings.append(f"sha256_stat_error: {exc}")
        return None
    if sidecar_size > MAX_ARTIFACT_READ_BYTES:
        warnings.append(f"sha256_sidecar_too_large: {sidecar_size}")
        return None
    if size_bytes is not None and size_bytes > MAX_ARTIFACT_READ_BYTES:
        warnings.append("sha256_verification_skipped_large_artifact")
        return None
    text = _read_limited_text(sidecar, sidecar_size, warnings)
    parsed = _parse_sha256_sidecar(text or "")
    if parsed is None:
        warnings.append("bad_sha256_sidecar")
        return False
    expected_hash, expected_name = parsed
    if expected_name and expected_name != path.name:
        warnings.append("sha256_sidecar_name_mismatch")
    try:
        actual = _sha256_file(path)
    except OSError as exc:
        errors.append(f"sha256_artifact_read_error: {exc}")
        return False
    if actual.lower() != expected_hash.lower():
        errors.append("sha256_mismatch")
        return False
    return True


def _parse_sha256_sidecar(text: str) -> tuple[str, str | None] | None:
    lines = text.strip().splitlines()
    first = lines[0] if lines else ""
    parts = first.split()
    if not parts or not _SHA256_RE.fullmatch(parts[0]):
        return None
    return parts[0].lower(), parts[1] if len(parts) > 1 else None


def _verify_artifact_entry(artifact: dict[str, Any], project_root: Path) -> dict[str, Any]:
    path = Path(str(artifact["path"]))
    if not artifact["exists"]:
        return {"bucket": "skipped", "path": str(path), "kind": artifact["kind"], "reason": "missing_path"}
    if artifact["kind"] == "run_bundle":
        try:
            payload = validate_run_bundle_payload(path, project_root)
            valid = bool(payload.get("valid"))
            return {
                "bucket": "checked",
                "path": str(path),
                "kind": "run_bundle",
                "valid": valid,
                "extracted_fields": {"kind": payload.get("kind"), "valid": valid},
                "warnings": [],
                "errors": [] if valid else list(payload.get("errors", [])),
            }
        except (OSError, RunBundleError, ValueError, json.JSONDecodeError) as exc:
            return {
                "bucket": "checked",
                "path": str(path),
                "kind": "run_bundle",
                "valid": False,
                "extracted_fields": {},
                "warnings": [],
                "errors": [f"run_bundle_validation_error: {exc}"],
            }
    if artifact["kind"] not in {"closure_artifact", "markdown", "review_report"}:
        return {"bucket": "skipped", "path": str(path), "kind": artifact["kind"], "reason": "unsupported_kind"}
    sha256_path = artifact.get("sha256_path")
    if not sha256_path:
        return {"bucket": "skipped", "path": str(path), "kind": artifact["kind"], "reason": "missing_sha256_sidecar"}
    try:
        payload = self_check_review_artifact_payload(artifact=path, sha256_path=sha256_path, project_root=project_root)
    except Exception as exc:  # defensive: lifecycle verify must not traceback on one artifact
        return {
            "bucket": "checked",
            "path": str(path),
            "kind": artifact["kind"],
            "valid": False,
            "extracted_fields": {},
            "warnings": [],
            "errors": [f"review_artifact_validation_error: {exc}"],
        }
    gate = payload.get("review_gate", {}) if isinstance(payload.get("review_gate"), dict) else {}
    extracted = _review_gate_fields(gate)
    extracted.update(
        {
            "gate_mode": gate.get("gate_mode"),
            "claude_review_status": gate.get("claude_review_status"),
            "real_closure": bool(gate.get("real_closure")),
            "fixture_only": bool(gate.get("fixture_only")),
            "pending_closed": bool(gate.get("pending_closed")),
            "follow_up_required": payload.get("follow_up_required", []),
        }
    )
    return {
        "bucket": "checked",
        "path": str(path),
        "kind": artifact["kind"],
        "valid": bool(payload.get("valid")),
        "extracted_fields": extracted,
        "warnings": list(payload.get("warnings", [])),
        "errors": list(payload.get("failures", [])),
    }


def _run_bundle_detected_fields(path: Path, project_root: Path, warnings: list[str]) -> dict[str, Any]:
    try:
        payload = validate_run_bundle_payload(path, project_root)
    except (OSError, RunBundleError, ValueError, json.JSONDecodeError) as exc:
        warnings.append(f"run_bundle_probe_warning: {exc}")
        return {"run_bundle_valid": False}
    return {"run_bundle_valid": bool(payload.get("valid")), "kind": payload.get("kind")}


def _registry_counts(artifacts: list[dict[str, Any]]) -> dict[str, int]:
    counts = {kind: 0 for kind in DEFAULT_KINDS}
    for item in artifacts:
        counts[str(item["kind"])] = counts.get(str(item["kind"]), 0) + 1
    return {
        "total": len(artifacts),
        "exists": sum(1 for item in artifacts if item["exists"]),
        "missing": sum(1 for item in artifacts if not item["exists"]),
        "closure_artifacts": counts.get("closure_artifact", 0),
        "review_reports": counts.get("review_report", 0),
        "sha256_files": counts.get("sha256", 0),
        "json_files": counts.get("json", 0),
        "markdown_files": counts.get("markdown", 0),
        "run_bundles": counts.get("run_bundle", 0),
        "unknown": counts.get("unknown", 0),
        "sha256_verified": sum(1 for item in artifacts if item.get("sha256_verified") is True),
        "warnings": sum(len(item.get("warnings", [])) for item in artifacts),
        "errors": sum(len(item.get("errors", [])) for item in artifacts),
    }


def _is_pending_like(item: dict[str, Any]) -> bool:
    fields = item.get("detected_fields", {})
    path = str(item.get("path", "")).lower()
    return bool(fields.get("follow_up_required")) or fields.get("gate_mode") == "codex_interim" or fields.get("claude_review_status") in {
        "pending",
        "unavailable",
    } or "pending" in path


def _summary_from_registry(registry: dict[str, Any]) -> dict[str, Any]:
    return {
        "counts": registry["counts"],
        "scanned_paths": registry["scanned_paths"],
        "warnings": registry["warnings"],
        "errors": registry["errors"],
    }


def _summary_from_lifecycle(lifecycle: dict[str, Any], verification: dict[str, Any]) -> dict[str, Any]:
    return {
        "counts": lifecycle["counts"],
        "real_closure_count": lifecycle["real_closure_count"],
        "fixture_only_count": lifecycle["fixture_only_count"],
        "pending_closed_count": lifecycle["pending_closed_count"],
        "checked_count": verification["counts"]["checked_count"],
        "verified_count": verification["counts"]["verified_count"],
        "invalid_count": verification["counts"]["invalid_count"],
        "skipped_count": verification["counts"]["skipped_count"],
    }


def _example_validation(verification: dict[str, Any]) -> dict[str, Any]:
    for key in ("verified", "invalid", "skipped"):
        values = verification.get(key, [])
        if values:
            return {"source": key, "result": values[0]}
    return {"source": "none", "result": None}


def _evidence_readme(manifest: dict[str, Any]) -> str:
    registry = manifest["registry_summary"]
    lifecycle = manifest["lifecycle_summary"]
    repo = manifest["repo"]
    command_map = manifest["command_map"]
    lines = [
        "# AgentOffice Evidence Release Package",
        "",
        "## System overview",
        "AgentOffice coordinates static local planning, run-bundle, review-artifact, lifecycle, and evidence-export workflows without invoking providers for this package.",
        "",
        "## Current CLI command map",
    ]
    for key in sorted(command_map):
        lines.append(f"- {key}: `{command_map[key]}`")
    lines.extend(
        [
            "",
            "## Current mainline/branch commit metadata",
            f"- repo_path: {repo['path']}",
            f"- repo_remote: {repo.get('remote') or 'unknown'}",
            f"- branch: {manifest['branch']}",
            f"- commit: {manifest['commit']}",
            "",
            "## Validation command list",
        ]
    )
    for command in manifest["validation_commands"]:
        lines.append(f"- `{command}`")
    lines.extend(["", "## Safety boundaries"])
    for boundary in manifest["safety_boundaries"]:
        lines.append(f"- {boundary}")
    lines.extend(["", "## Known limitations"])
    for limitation in manifest["known_limitations"]:
        lines.append(f"- {limitation}")
    lines.extend(
        [
            "",
            "## Artifact registry summary",
            f"- total: {registry['counts']['total']}",
            f"- closure_artifacts: {registry['counts']['closure_artifacts']}",
            f"- report_artifacts: {registry['counts']['review_reports']}",
            f"- sha256_files: {registry['counts']['sha256_files']}",
            f"- warnings: {len(registry['warnings'])}",
            f"- errors: {len(registry['errors'])}",
            "",
            "## Lifecycle status summary",
            f"- verified_count: {lifecycle['verified_count']}",
            f"- invalid_count: {lifecycle['invalid_count']}",
            f"- skipped_count: {lifecycle['skipped_count']}",
            f"- real_closure_count: {lifecycle['real_closure_count']}",
            f"- fixture_only_count: {lifecycle['fixture_only_count']}",
            f"- pending_closed_count: {lifecycle['pending_closed_count']}",
            "",
            "## Example review/closure artifact validation summary",
            "```json",
            json.dumps(manifest["example_artifact_validation"], indent=2, ensure_ascii=False),
            "```",
            "",
            "## Reviewer instructions",
            "1. Inspect `manifest.json` first for machine-readable command, safety, registry, and lifecycle summaries.",
            "2. Run the validation commands listed above from the AgentOffice repository root.",
            "3. Use registry and lifecycle commands with `--root` for repeatable fixture-based review.",
            "4. Treat warnings as review inputs; missing optional artifacts are not fatal by design.",
            "",
        ]
    )
    return "\n".join(lines)


def _repo_metadata(project_root: Path) -> dict[str, Any]:
    return {"path": str(project_root), "remote": _git_value(project_root, "config", "--get", "remote.origin.url")}


def _git_value(project_root: Path, *args: str) -> str | None:
    completed = subprocess.run(["git", *args], cwd=project_root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def _prepare_output_dir(out: str | Path) -> Path:
    path = Path(out).resolve(strict=False)
    if path.is_symlink():
        raise ValueError(f"Refusing symlink evidence output directory: {out}")
    if path.exists() and not path.is_dir():
        raise ValueError(f"Evidence output path is not a directory: {out}")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_text(path: Path, value: str) -> None:
    tmp = path.with_name(f"{path.name}.tmp")
    if tmp.is_symlink():
        raise ValueError(f"Refusing symlink temporary output path: {tmp}")
    tmp.write_text(value, encoding="utf-8")
    tmp.replace(path)


def _looks_like_run_bundle(path: Path) -> bool:
    return path.is_dir() and all((path / name).is_file() for name in ("run.json", "validation.json", "plan.json", "README.md"))


def _coerce_path(path: str | Path, project_root: Path) -> Path:
    value = Path(path)
    if not value.is_absolute():
        value = project_root / value
    return value


def _has_forbidden_part(path: Path) -> bool:
    return any(part in {".git", ".env"} for part in path.parts)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in sorted(paths, key=lambda item: str(item)):
        key = str(path)
        if key not in seen:
            seen.add(key)
            result.append(path)
    return result


def _command_text(base: str, roots: list[str] | None, *, out: str | Path | None = None) -> str:
    command = ["python3", "-m", "agent_office", *base.split()]
    if out is not None:
        command.extend(["--out", str(out)])
    for root in roots or []:
        command.extend(["--root", root])
    command.append("--json")
    return " ".join(shlex.quote(part) for part in command)
