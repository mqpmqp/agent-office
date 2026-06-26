from __future__ import annotations

import hashlib
import json
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .run_bundle import RunBundleError, validate_run_bundle_payload


class ReviewArtifactError(ValueError):
    pass


SCHEMA_VERSION = 1
REVIEW_ARTIFACT_SCHEMA_VERSION = 1
REVIEW_ARTIFACT_SECTIONS = (
    "Integrity guard",
    "Self-audit",
    "Review gate status",
    "Artifact-based review caveat",
    "Git state",
    "Diff evidence",
    "Changed file snapshots",
    "Validation outputs",
    "Smoke outputs",
    "Report snapshots",
    "README snapshot",
)
LEGACY_REVIEW_ARTIFACT_SECTIONS = tuple(section for section in REVIEW_ARTIFACT_SECTIONS if section != "Review gate status")
LEGACY_GATE_STATUS_MISSING = "legacy_gate_status_missing"
LEGACY_REVIEW_GATE_CAVEAT = (
    "Legacy artifact lacks Review gate status; cannot be treated as Claude PASS. "
    "Run Claude artifact review follow-up before relying on this artifact."
)
GATE_MODES = ("claude_pass", "codex_interim", "codex_self_check", "unknown")
CLAUDE_REVIEW_STATUSES = ("pass", "pending", "unavailable", "not_required", "unknown")
CODEX_SELF_CHECK_STATUSES = ("pass", "fail", "not_run", "unknown")
CLAUDE_ARTIFACT_REVIEW_FOLLOW_UP = "claude_artifact_review"
CODEX_INTERIM_GATE_CAVEAT = "Codex interim gate only; this is not a Claude review. Claude artifact review remains pending."
UNKNOWN_GATE_CAVEAT = "Review gate status was not asserted; do not treat this artifact as Claude review evidence."
CLOSURE_TITLE = "# AgentOffice Claude Pending Review Closure"
CLOSURE_ARTIFACT_SECTIONS = (
    "Integrity guard",
    "Closure summary",
    "Prior interim gate",
    "Claude review evidence",
    "Closed review gate status",
    "Interim artifact self-check summary",
    "Claude review report snapshot",
    "Caveats",
    "Artifact end",
)
CLOSURE_GATE_CAVEAT = "Claude reviewed artifact evidence, not direct VPS execution unless the report says otherwise."
REVIEW_COMPLETE_MARKER_RE = re.compile(r"\b[A-Z0-9][A-Z0-9_]*(?:ARTIFACT_REVIEW_COMPLETE|EVIDENCE_CLOSURE_REVIEW_COMPLETE)\b")
CONDITIONAL_PASS_RE = re.compile(r"\bconditional\s+pass\b", re.IGNORECASE)
FAIL_RE = re.compile(r"\b(?:fail|failed|failure)\b", re.IGNORECASE)
BLOCKER_UNRESOLVED_RE = re.compile(r"\b(?:blockers?\s+unresolved|unresolved\s+blockers?)\b", re.IGNORECASE)
PASS_RE = re.compile(r"\bpass\b", re.IGNORECASE)
ATTESTATION_TYPES = ("real", "fixture")
ALLOWED_ATTESTATION_REVIEWERS = ("claude",)


@dataclass(frozen=True)
class CaptureCommand:
    name: str
    argv: tuple[str, ...]
    expected_exit: int = 0


VALIDATION_COMMANDS = (
    CaptureCommand("compileall", ("python3", "-m", "compileall", "agent_office", "tests")),
    CaptureCommand("full unittest", ("python3", "-m", "unittest")),
    CaptureCommand("unittest discovery", ("python3", "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py")),
    CaptureCommand("focused tests.test_run_bundle_cli", ("python3", "-m", "unittest", "tests.test_run_bundle_cli")),
    CaptureCommand("doctor --adapters", ("python3", "-m", "agent_office", "doctor", "--adapters")),
    CaptureCommand("verify.sh", ("./scripts/verify.sh",)),
    CaptureCommand("smoke-test.sh P6-PROFILES", ("./scripts/smoke-test.sh", "P6-PROFILES")),
    CaptureCommand("run-staged P6-PROFILES --dry-run --reset", ("python3", "-m", "agent_office", "run-staged", "P6-PROFILES", "--dry-run", "--reset")),
)


def export_review_artifact_payload(
    *,
    base: str,
    review: str,
    branch: str,
    out: str | Path,
    title: str,
    project_root: Path,
    gate_mode: str = "unknown",
    claude_review_status: str = "unknown",
    codex_self_check_status: str = "not_run",
) -> dict[str, object]:
    root = project_root.resolve()
    out_path = _resolve_artifact_out_path(out, root)
    sha256_path = _resolve_artifact_sha256_path(out_path, root)
    base_commit = _resolve_commit(root, base, "base")
    review_commit = _resolve_commit(root, review, "review")

    git_state = _git_state(root, branch)
    repo = _repo_identity(root)
    diff_evidence = _diff_evidence(root, base_commit, review_commit)
    changed_files = _changed_file_snapshots(root, base_commit, review_commit)
    validation_results = [_capture_command(command, root) for command in VALIDATION_COMMANDS]
    smoke_commands, smoke_notes = build_smoke_commands(root, base_commit, review_commit, branch)
    smoke_results = [_capture_command(command, root) for command in smoke_commands]
    report_snapshots = _report_snapshots(root, branch, title)
    readme_snapshot = _read_text_snapshot(root / "README.md", "README_NOT_FOUND")

    validation_success = all(bool(item["success"]) for item in validation_results)
    smoke_success = all(bool(item["success"]) for item in smoke_results)
    command_failures = _command_failures(validation_results, smoke_results)
    evidence_consistency_warnings = _evidence_consistency_warnings(report_snapshots, smoke_results)
    warnings: list[str] = []
    if not validation_success:
        warnings.append("validation_success=false; see Validation outputs section")
    if not smoke_success:
        warnings.append("smoke_success=false; see Smoke outputs section")
    warnings.extend(evidence_consistency_warnings)

    verify = _verification_metadata(out_path, sha256_path)
    review_gate = _review_gate_status(
        gate_mode=gate_mode,
        claude_review_status=claude_review_status,
        codex_self_check_status=codex_self_check_status,
        out_path=out_path,
        sha256_path=sha256_path,
    )
    warnings.extend(str(item) for item in review_gate["warnings"])
    section_audit = _section_audit(
        out_path=out_path,
        sha256_path=sha256_path,
        verify=verify,
        validation_success=validation_success,
        smoke_success=smoke_success,
        command_failures=command_failures,
        changed_files=changed_files,
        report_snapshots=report_snapshots,
        readme_snapshot=readme_snapshot,
        evidence_consistency_warnings=evidence_consistency_warnings,
        missing_section_count=0,
        empty_section_count=0,
    )

    artifact_text = _artifact_markdown(
        title=title,
        repo=repo,
        branch=branch,
        base_commit=base_commit,
        review_commit=review_commit,
        git_state=git_state,
        diff_evidence=diff_evidence,
        changed_files=changed_files,
        validation_results=validation_results,
        validation_success=validation_success,
        smoke_results=smoke_results,
        smoke_notes=smoke_notes,
        smoke_success=smoke_success,
        report_snapshots=report_snapshots,
        readme_snapshot=readme_snapshot,
        section_audit=section_audit,
        review_gate=review_gate,
    )
    section_counts = _artifact_section_counts(artifact_text, REVIEW_ARTIFACT_SECTIONS)
    if section_counts["missing_section_count"] or section_counts["empty_section_count"]:
        section_audit = dict(section_audit)
        section_audit.update(section_counts)
        artifact_text = _artifact_markdown(
            title=title,
            repo=repo,
            branch=branch,
            base_commit=base_commit,
            review_commit=review_commit,
            git_state=git_state,
            diff_evidence=diff_evidence,
            changed_files=changed_files,
            validation_results=validation_results,
            validation_success=validation_success,
            smoke_results=smoke_results,
            smoke_notes=smoke_notes,
            smoke_success=smoke_success,
            report_snapshots=report_snapshots,
            readme_snapshot=readme_snapshot,
            section_audit=section_audit,
            review_gate=review_gate,
        )
    _write_text(out_path, artifact_text)
    sha256 = _sha256_file(out_path)
    _write_text(sha256_path, f"{sha256}  {out_path.name}\n")
    byte_count = _stat_size(out_path)
    return {
        "schema_version": SCHEMA_VERSION,
        "review_artifact_schema_version": REVIEW_ARTIFACT_SCHEMA_VERSION,
        "kind": "review_artifact_export",
        "valid": True,
        "repo": repo,
        "branch": branch,
        "base": base_commit,
        "review": review_commit,
        "head": git_state["head"],
        "out": str(out_path),
        "sha256_path": str(sha256_path),
        "artifact_dir": verify["artifact_dir"],
        "artifact_basename": verify["artifact_basename"],
        "sha256_basename": verify["sha256_basename"],
        "sha256_verify_command": verify["sha256_verify_command"],
        "sha256": sha256,
        "artifact_sha256": sha256,
        "byte_count": byte_count,
        "artifact_bytes": byte_count,
        "validation_success": validation_success,
        "smoke_success": smoke_success,
        "command_failures": command_failures,
        "sections": list(REVIEW_ARTIFACT_SECTIONS),
        "missing_file_markers": 0,
        "empty_section_markers": 0,
        "section_audit": section_audit,
        "review_gate": review_gate,
        "evidence_consistency_warnings": evidence_consistency_warnings,
        "warnings": warnings,
        "blocking_reasons": [],
    }


def build_smoke_commands(project_root: Path, base: str | None = None, review: str | None = None, branch: str | None = None) -> tuple[list[CaptureCommand], list[str]]:
    commands = [
        CaptureCommand(
            "run-bundle export-review --help",
            ("python3", "-m", "agent_office", "run-bundle", "export-review", "--help"),
            0,
        )
    ]
    notes: list[str] = []
    sample, invalid_sample_count = _existing_run_bundle_sample(project_root)
    if sample is None:
        if invalid_sample_count:
            notes.append("NO_USABLE_EXISTING_RUN_DIRECTORY_FOUND")
        else:
            notes.append("NO_EXISTING_RUN_DIRECTORY_FOUND")
    else:
        positive_out = Path("/tmp/agentoffice-review-artifact-export-review-smoke.md")
        commands.extend(
            [
                CaptureCommand(
                    "positive run-bundle export-review smoke",
                    (
                        "python3",
                        "-m",
                        "agent_office",
                        "run-bundle",
                        "export-review",
                        "--path",
                        sample,
                        "--out",
                        str(positive_out),
                        "--json",
                    ),
                    0,
                ),
                CaptureCommand(
                    "positive run-bundle export-review sha256sum -c",
                    ("bash", "-lc", f"cd {shlex.quote(str(positive_out.parent))} && sha256sum -c {shlex.quote(positive_out.name + '.sha256')}"),
                    0,
                ),
            ]
        )
    commands.extend(
        [
            CaptureCommand(
                "negative run-bundle export-review missing path",
                (
                    "python3",
                    "-m",
                    "agent_office",
                    "run-bundle",
                    "export-review",
                    "--path",
                    ".ai/runs/MISSING",
                    "--out",
                    "/tmp/agentoffice-review-artifact-missing-negative.md",
                    "--json",
                ),
                2,
            ),
            CaptureCommand(
                "negative run-bundle export-review unsafe path",
                (
                    "python3",
                    "-m",
                    "agent_office",
                    "run-bundle",
                    "export-review",
                    "--path",
                    "../bad",
                    "--out",
                    "/tmp/agentoffice-review-artifact-unsafe-negative.md",
                    "--json",
                ),
                2,
            ),
        ]
    )
    if base and review and branch:
        notes.append("NOT_RUN_WITH_REASON: positive review-artifact export smoke is not run inside review-artifact export to avoid recursive exporter execution.")
        safe_base = shlex.quote(base)
        safe_review = shlex.quote(review)
        safe_branch = shlex.quote(branch)
        commands.extend(
            [
                CaptureCommand(
                    "negative review-artifact missing commit",
                    (
                        "python3",
                        "-m",
                        "agent_office",
                        "review-artifact",
                        "export",
                        "--base",
                        "missing-review-artifact-commit",
                        "--review",
                        review,
                        "--branch",
                        branch,
                        "--out",
                        "/tmp/agentoffice-review-artifact-missing-commit-negative.md",
                        "--title",
                        "Review artifact missing commit negative smoke",
                        "--json",
                    ),
                    2,
                ),
                CaptureCommand(
                    "negative review-artifact unsafe out",
                    (
                        "python3",
                        "-m",
                        "agent_office",
                        "review-artifact",
                        "export",
                        "--base",
                        base,
                        "--review",
                        review,
                        "--branch",
                        branch,
                        "--out",
                        "../agentoffice-review-artifact-unsafe-negative.md",
                        "--title",
                        "Review artifact unsafe out negative smoke",
                        "--json",
                    ),
                    2,
                ),
                CaptureCommand(
                    "negative review-artifact directory out",
                    (
                        "bash",
                        "-lc",
                        "rm -rf /tmp/agentoffice-review-artifact-directory-negative.md && "
                        "mkdir -p /tmp/agentoffice-review-artifact-directory-negative.md && "
                        f"python3 -m agent_office review-artifact export --base {safe_base} --review {safe_review} --branch {safe_branch} "
                        "--out /tmp/agentoffice-review-artifact-directory-negative.md --title 'Review artifact directory out negative smoke' --json",
                    ),
                    2,
                ),
                CaptureCommand(
                    "negative review-artifact parent missing",
                    (
                        "bash",
                        "-lc",
                        "rm -rf /tmp/agentoffice-review-artifact-parent-missing && "
                        f"python3 -m agent_office review-artifact export --base {safe_base} --review {safe_review} --branch {safe_branch} "
                        "--out /tmp/agentoffice-review-artifact-parent-missing/artifact.md --title 'Review artifact parent missing negative smoke' --json",
                    ),
                    2,
                ),
            ]
        )
    else:
        notes.append("NOT_RUN_WITH_REASON: review-artifact negative smokes require base/review/branch context.")
    return commands, notes


def review_artifact_error_payload(
    *,
    base: str | None,
    review: str | None,
    branch: str | None,
    out: str | Path | None,
    title: str | None,
    error: str,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "review_artifact_schema_version": REVIEW_ARTIFACT_SCHEMA_VERSION,
        "kind": "review_artifact_export",
        "valid": False,
        "repo": None,
        "branch": branch,
        "base": base,
        "review": review,
        "head": None,
        "out": str(out) if out is not None else None,
        "sha256_path": f"{out}.sha256" if out else None,
        "artifact_dir": None,
        "artifact_basename": Path(out).name if out else None,
        "sha256_basename": f"{Path(out).name}.sha256" if out else None,
        "sha256_verify_command": None,
        "sha256": None,
        "artifact_sha256": None,
        "byte_count": 0,
        "artifact_bytes": 0,
        "validation_success": False,
        "smoke_success": False,
        "command_failures": [],
        "sections": [],
        "missing_file_markers": 0,
        "empty_section_markers": 0,
        "section_audit": {},
        "review_gate": _review_gate_error_status(),
        "evidence_consistency_warnings": [],
        "warnings": [error],
        "blocking_reasons": [_error_reason(error)],
        "title": title,
    }


def close_pending_review_artifact_payload(
    *,
    artifact: str | Path,
    sha256_path: str | Path,
    claude_attestation: str | Path,
    out: str | Path,
    project_root: Path,
    allow_fixture_attestation: bool = False,
    source_review_report: str | Path | None = None,
) -> dict[str, object]:
    root = project_root.resolve()
    out_path = _resolve_artifact_out_path(out, root)
    out_sha256_path = _resolve_artifact_sha256_path(out_path, root)
    interim_self_check = self_check_review_artifact_payload(artifact=artifact, sha256_path=sha256_path, project_root=root)
    interim_failures = _interim_artifact_closure_failures(interim_self_check)
    attestation = _claude_attestation_evidence(claude_attestation, allow_fixture_attestation=allow_fixture_attestation)
    source_report = _source_review_report_evidence(source_review_report)
    failures = [*interim_failures, *attestation["failures"], *source_report["failures"]]
    if failures:
        raise ReviewArtifactError("closure failures: " + ",".join(str(item) for item in failures))

    interim_hash = str(interim_self_check.get("artifact_sha256") or "")
    prior_gate = interim_self_check.get("review_gate", {}) if isinstance(interim_self_check.get("review_gate"), dict) else {}
    review_gate = _closed_review_gate_status(
        prior_gate,
        out_path,
        out_sha256_path,
        attestation=attestation,
        source_report=source_report,
        allow_fixture_attestation=allow_fixture_attestation,
    )
    verify = _verification_metadata(out_path, out_sha256_path)
    artifact_text = _closure_artifact_markdown(
        out_path=out_path,
        sha256_path=out_sha256_path,
        verify=verify,
        interim_artifact=Path(artifact).resolve(strict=False),
        interim_sha256_path=Path(sha256_path).resolve(strict=False),
        interim_hash=interim_hash,
        interim_self_check=interim_self_check,
        attestation=attestation,
        source_report=source_report,
        review_gate=review_gate,
    )
    section_counts = _artifact_section_counts(artifact_text, CLOSURE_ARTIFACT_SECTIONS)
    if section_counts["missing_section_count"] or section_counts["empty_section_count"]:
        raise ReviewArtifactError("closure failures: closure_section_contract_failed")
    _write_text(out_path, artifact_text)
    artifact_sha256 = _sha256_file(out_path)
    _write_text(out_sha256_path, f"{artifact_sha256}  {out_path.name}\n")
    artifact_bytes = _stat_size(out_path)
    return {
        "schema_version": SCHEMA_VERSION,
        "review_artifact_schema_version": REVIEW_ARTIFACT_SCHEMA_VERSION,
        "kind": "review_artifact_close_pending",
        "valid": True,
        "closure_created": True,
        "artifact_path": str(out_path),
        "sha256_path": str(out_sha256_path),
        "artifact_sha256": artifact_sha256,
        "artifact_bytes": artifact_bytes,
        "byte_count": artifact_bytes,
        "artifact_dir": verify["artifact_dir"],
        "artifact_basename": verify["artifact_basename"],
        "sha256_basename": verify["sha256_basename"],
        "sha256_verify_command": verify["sha256_verify_command"],
        "interim_artifact": str(Path(artifact).resolve(strict=False)),
        "interim_sha256_path": str(Path(sha256_path).resolve(strict=False)),
        "interim_sha256": interim_hash,
        "claude_attestation": attestation["path"],
        "claude_attestation_sha256": attestation["sha256"],
        "claude_review_report": attestation["path"],
        "claude_review_sha256": attestation["sha256"],
        "source_review_report": source_report["path"],
        "source_review_report_sha256": source_report["sha256"],
        "attestation_type": attestation["attestation_type"],
        "fixture_only": attestation["attestation_type"] == "fixture",
        "fixture_attestation_allowed": allow_fixture_attestation,
        "reviewer": attestation["reviewer"],
        "detected_review_marker": attestation["review_marker"],
        "detected_review_markers": attestation["markers"],
        "detected_review_verdict": attestation["verdict"],
        "review_gate": review_gate,
        "warnings": ["fixture_only_closure"] if attestation["attestation_type"] == "fixture" else [],
        "failures": [],
        "blocking_reasons": [],
    }


def close_pending_review_artifact_error_payload(
    *,
    artifact: str | Path | None,
    sha256_path: str | Path | None,
    claude_attestation: str | Path | None,
    out: str | Path | None,
    error: str,
    source_review_report: str | Path | None = None,
    allow_fixture_attestation: bool = False,
) -> dict[str, object]:
    failures = _close_pending_error_failures(error)
    return {
        "schema_version": SCHEMA_VERSION,
        "review_artifact_schema_version": REVIEW_ARTIFACT_SCHEMA_VERSION,
        "kind": "review_artifact_close_pending",
        "valid": False,
        "closure_created": False,
        "artifact_path": str(out) if out is not None else None,
        "sha256_path": f"{out}.sha256" if out else None,
        "artifact_sha256": None,
        "artifact_bytes": 0,
        "byte_count": 0,
        "artifact_dir": None,
        "artifact_basename": Path(out).name if out else None,
        "sha256_basename": f"{Path(out).name}.sha256" if out else None,
        "sha256_verify_command": None,
        "interim_artifact": str(artifact) if artifact is not None else None,
        "interim_sha256_path": str(sha256_path) if sha256_path is not None else None,
        "interim_sha256": None,
        "claude_attestation": str(claude_attestation) if claude_attestation is not None else None,
        "claude_attestation_sha256": None,
        "claude_review_report": str(claude_attestation) if claude_attestation is not None else None,
        "claude_review_sha256": None,
        "source_review_report": str(source_review_report) if source_review_report is not None else None,
        "source_review_report_sha256": None,
        "attestation_type": None,
        "fixture_only": False,
        "fixture_attestation_allowed": allow_fixture_attestation,
        "reviewer": None,
        "detected_review_marker": None,
        "detected_review_markers": [],
        "detected_review_verdict": None,
        "review_gate": _review_gate_error_status(),
        "warnings": [error],
        "failures": failures,
        "blocking_reasons": failures,
    }


def format_review_artifact_close_pending(payload: dict[str, object]) -> str:
    return "\n".join(
        [
            "Review artifact pending Claude review closed",
            f"Closure artifact: {payload['artifact_path']}",
            f"SHA256 sidecar: {payload['sha256_path']}",
            f"Verification command: {payload['sha256_verify_command']}",
            "Gate transition: codex_interim to claude_pass",
            f"attestation_type: {payload.get('attestation_type')}",
            f"fixture_only: {str(payload.get('fixture_only')).lower()}",
            f"fixture_attestation_allowed: {str(payload.get('fixture_attestation_allowed')).lower()}",
            f"reviewer: {payload.get('reviewer')}",
            f"detected_review_marker: {payload['detected_review_marker']}",
            f"detected_review_verdict: {payload['detected_review_verdict']}",
            f"gate_mode: {payload.get('review_gate', {}).get('gate_mode')}",
            f"claude_review_status: {payload.get('review_gate', {}).get('claude_review_status')}",
            f"pending_closed: {str(payload.get('review_gate', {}).get('pending_closed')).lower()}",
            f"Claude caveat: {payload.get('review_gate', {}).get('gate_caveat')}",
        ]
    )


def format_review_artifact_export(payload: dict[str, object]) -> str:
    return "\n".join(
        [
            "Review artifact exported",
            f"Artifact: {payload['out']}",
            f"SHA256 sidecar: {payload['sha256_path']}",
            f"Verification command: {payload['sha256_verify_command']}",
            f"SHA256: {payload['sha256']}",
            f"Byte count: {payload['byte_count']}",
            f"validation_success: {str(payload['validation_success']).lower()}",
            f"smoke_success: {str(payload['smoke_success']).lower()}",
            f"command_failures: {len(payload.get('command_failures', []))}",
            f"gate_mode: {payload.get('review_gate', {}).get('gate_mode')}",
            f"claude_review_status: {payload.get('review_gate', {}).get('claude_review_status')}",
            f"codex_self_check_status: {payload.get('review_gate', {}).get('codex_self_check_status')}",
            f"gate_caveat: {payload.get('review_gate', {}).get('gate_caveat')}",
            "PowerShell download:",
            f"  scp -o BatchMode=yes agentoffice-vps:{payload['out']} $env:USERPROFILE\\Desktop\\",
            f"  scp -o BatchMode=yes agentoffice-vps:{payload['sha256_path']} $env:USERPROFILE\\Desktop\\",
            "PowerShell local check: compare Get-FileHash output with the first field in the .sha256 sidecar.",
        ]
    )


def _artifact_markdown(
    *,
    title: str,
    repo: str,
    branch: str,
    base_commit: str,
    review_commit: str,
    git_state: dict[str, str],
    diff_evidence: list[dict[str, object]],
    changed_files: list[dict[str, object]],
    validation_results: list[dict[str, object]],
    validation_success: bool,
    smoke_results: list[dict[str, object]],
    smoke_notes: list[str],
    smoke_success: bool,
    report_snapshots: list[dict[str, str]],
    readme_snapshot: dict[str, str],
    section_audit: dict[str, object],
    review_gate: dict[str, object],
) -> str:
    lines = [
        f"# {title}",
        "",
        "## Integrity guard",
        f"- repo: {repo}",
        f"- branch: {branch}",
        f"- base commit: {base_commit}",
        f"- review commit: {review_commit}",
        f"- current HEAD: {git_state['head']}",
        "- generated_from: python3 -m agent_office review-artifact export",
        "- artifact_kind: claude_review_artifact_exporter",
        "- MISSING_FILE_MARKERS: 0",
        "- EMPTY_SECTION_MARKERS: 0",
        f"- validation_success: {str(validation_success).lower()}",
        f"- smoke_success: {str(smoke_success).lower()}",
        "",
        "## Self-audit",
        f"- artifact_file: {section_audit['artifact_file']}",
        f"- sha256_sidecar: {section_audit['sha256_sidecar']}",
        f"- sha256_verify_command: {section_audit['sha256_verify_command']}",
        f"- validation_success: {str(section_audit['validation_success']).lower()}",
        f"- smoke_success: {str(section_audit['smoke_success']).lower()}",
        f"- missing_section_count: {section_audit['missing_section_count']}",
        f"- empty_section_count: {section_audit['empty_section_count']}",
        f"- changed_file_snapshot_count: {section_audit['changed_file_snapshot_count']}",
        f"- deleted_file_marker_count: {section_audit['deleted_file_marker_count']}",
        f"- binary_file_marker_count: {section_audit['binary_file_marker_count']}",
        f"- report_snapshot_count: {section_audit['report_snapshot_count']}",
        f"- README snapshot included: {section_audit['readme_snapshot_included']}",
        "### command_failures",
        _fence(json.dumps(section_audit["command_failures"], indent=2, ensure_ascii=False), "json"),
        "### evidence_consistency_warnings",
        _fence(json.dumps(section_audit["evidence_consistency_warnings"], indent=2, ensure_ascii=False), "json"),
        "",
        "## Review gate status",
        f"- gate_mode: {review_gate['gate_mode']}",
        f"- claude_review_status: {review_gate['claude_review_status']}",
        f"- codex_self_check_status: {review_gate['codex_self_check_status']}",
        f"- interim_merge: {str(review_gate['interim_merge']).lower()}",
        f"- gate_valid: {str(review_gate['gate_valid']).lower()}",
        f"- gate_caveat: {review_gate['gate_caveat']}",
        "### review_gate JSON",
        _fence(json.dumps(review_gate, indent=2, ensure_ascii=False), "json"),
        "",
        "## Artifact-based review caveat",
        "Claude should review this uploaded artifact as captured evidence. Claude should not claim it personally ran VPS validation unless it separately did so. Validation and smoke sections are VPS captured transcripts.",
        "",
        "## Git state",
        f"- current branch: {git_state['current_branch']}",
        f"- HEAD: {git_state['head']}",
        f"- origin branch HEAD if available: {git_state['origin_branch_head']}",
        "- tracked status:",
        _fence(git_state["tracked_status"]),
        "",
        "## Diff evidence",
    ]
    lines.extend(_command_blocks(diff_evidence))
    lines.extend(["", "## Changed file snapshots"])
    if changed_files:
        for item in changed_files:
            lines.extend(_changed_file_block(item))
    else:
        lines.append("NO_CHANGED_FILES")
    lines.extend(["", "## Validation outputs", f"validation_success: {str(validation_success).lower()}"])
    lines.extend(_command_blocks(validation_results))
    lines.extend(["", "## Smoke outputs", f"smoke_success: {str(smoke_success).lower()}"])
    if smoke_notes:
        lines.extend(["### Smoke notes", _fence("\n".join(smoke_notes))])
    lines.extend(_command_blocks(smoke_results))
    lines.extend(["", "## Report snapshots"])
    for snapshot in report_snapshots:
        lines.extend([f"### {snapshot['path']}", _fence(snapshot["content"], "markdown")])
    lines.extend(["", "## README snapshot", f"### {readme_snapshot['path']}", _fence(readme_snapshot["content"], "markdown")])
    lines.extend(["", "REVIEW_ARTIFACT_EXPORT_COMPLETE", ""])
    return "\n".join(lines)



def _review_gate_status(
    *,
    gate_mode: str,
    claude_review_status: str,
    codex_self_check_status: str,
    out_path: Path,
    sha256_path: Path,
) -> dict[str, object]:
    gate_mode = gate_mode if gate_mode in GATE_MODES else "unknown"
    claude_review_status = claude_review_status if claude_review_status in CLAUDE_REVIEW_STATUSES else "unknown"
    codex_self_check_status = codex_self_check_status if codex_self_check_status in CODEX_SELF_CHECK_STATUSES else "unknown"
    follow_up_required: list[str] = []
    warnings: list[str] = []
    gate_valid = True
    interim_merge = gate_mode == "codex_interim"
    pending_artifact: str | None = None
    pending_sha256: str | None = None
    caveat = UNKNOWN_GATE_CAVEAT

    if gate_mode == "codex_interim":
        caveat = CODEX_INTERIM_GATE_CAVEAT
        pending_artifact = str(out_path)
        pending_sha256 = str(sha256_path)
        if claude_review_status in {"pending", "unavailable", "unknown"}:
            follow_up_required.append(CLAUDE_ARTIFACT_REVIEW_FOLLOW_UP)
        if claude_review_status == "pass":
            warnings.append("codex_interim_with_claude_pass_status")
    elif gate_mode == "claude_pass":
        caveat = "Claude artifact review is marked pass. Verify reviewer evidence before relying on this gate."
        if claude_review_status != "pass":
            gate_valid = False
            warnings.append("claude_pass_gate_requires_claude_review_status_pass")
    elif gate_mode == "codex_self_check":
        caveat = "Codex self-check gate only; this is not a Claude review."
        if claude_review_status in {"pending", "unavailable"}:
            follow_up_required.append(CLAUDE_ARTIFACT_REVIEW_FOLLOW_UP)
    elif gate_mode == "unknown" and claude_review_status in {"pending", "unavailable"}:
        follow_up_required.append(CLAUDE_ARTIFACT_REVIEW_FOLLOW_UP)

    return {
        "gate_mode": gate_mode,
        "claude_review_status": claude_review_status,
        "codex_self_check_status": codex_self_check_status,
        "interim_merge": interim_merge,
        "follow_up_required": follow_up_required,
        "pending_review_artifact": pending_artifact,
        "pending_review_sha256": pending_sha256,
        "gate_caveat": caveat,
        "gate_valid": gate_valid,
        "warnings": warnings,
    }


def _review_gate_error_status() -> dict[str, object]:
    return {
        "gate_mode": "unknown",
        "claude_review_status": "unknown",
        "codex_self_check_status": "unknown",
        "interim_merge": False,
        "pending_closed": False,
        "follow_up_required": [],
        "pending_review_artifact": None,
        "pending_review_sha256": None,
        "closure_source": None,
        "attestation_type": None,
        "fixture_only": False,
        "fixture_attestation_allowed": False,
        "reviewer": None,
        "review_marker": None,
        "attestation_path": None,
        "attestation_sha256": None,
        "source_review_report": None,
        "source_review_report_sha256": None,
        "gate_caveat": UNKNOWN_GATE_CAVEAT,
        "gate_valid": False,
        "warnings": [],
    }


def _legacy_review_gate_status() -> dict[str, object]:
    status = _review_gate_error_status()
    status.update(
        {
            "follow_up_required": [CLAUDE_ARTIFACT_REVIEW_FOLLOW_UP],
            "gate_caveat": LEGACY_REVIEW_GATE_CAVEAT,
            "gate_valid": True,
            "warnings": [LEGACY_GATE_STATUS_MISSING],
            "legacy_artifact": True,
            "legacy_gate_status_missing": True,
        }
    )
    return status




def _closed_review_gate_status(
    prior_gate: dict[str, object],
    out_path: Path,
    sha256_path: Path,
    *,
    attestation: dict[str, object],
    source_report: dict[str, object],
    allow_fixture_attestation: bool,
) -> dict[str, object]:
    codex_status = str(prior_gate.get("codex_self_check_status") or "pass")
    if codex_status not in CODEX_SELF_CHECK_STATUSES:
        codex_status = "unknown"
    fixture_only = attestation.get("attestation_type") == "fixture"
    warnings = ["fixture_only_closure"] if fixture_only else []
    return {
        "gate_mode": "claude_pass",
        "claude_review_status": "pass",
        "codex_self_check_status": codex_status,
        "interim_merge": bool(prior_gate.get("interim_merge", prior_gate.get("gate_mode") == "codex_interim")),
        "pending_closed": True,
        "follow_up_required": [],
        "pending_review_artifact": None,
        "pending_review_sha256": None,
        "closure_source": "claude_attestation",
        "closure_artifact": str(out_path),
        "closure_sha256": str(sha256_path),
        "attestation_path": attestation.get("path"),
        "attestation_sha256": attestation.get("sha256"),
        "attestation_type": attestation.get("attestation_type"),
        "fixture_only": fixture_only,
        "fixture_attestation_allowed": allow_fixture_attestation,
        "reviewer": attestation.get("reviewer"),
        "review_marker": attestation.get("review_marker"),
        "source_review_report": source_report.get("path"),
        "source_review_report_sha256": source_report.get("sha256"),
        "gate_caveat": CLOSURE_GATE_CAVEAT,
        "gate_valid": True,
        "warnings": warnings,
    }


def _interim_artifact_closure_failures(payload: dict[str, object]) -> list[str]:
    failures: list[str] = []
    if not bool(payload.get("valid")):
        failures.append("artifact_self_check_failed")
    if payload.get("missing_file_markers") != 0:
        failures.append("missing_file_markers_nonzero")
    if payload.get("empty_section_markers") != 0:
        failures.append("empty_section_markers_nonzero")
    review_gate = payload.get("review_gate", {}) if isinstance(payload.get("review_gate"), dict) else {}
    follow_up = review_gate.get("follow_up_required", [])
    if not isinstance(follow_up, list):
        follow_up = []
    gate_mode = review_gate.get("gate_mode")
    claude_status = review_gate.get("claude_review_status")
    caveat = str(payload.get("gate_caveat") or review_gate.get("gate_caveat") or "").lower()
    caveat_counts_as_pending = bool(payload.get("legacy_artifact")) or gate_mode in {"codex_interim", "unknown"}
    has_follow_up = CLAUDE_ARTIFACT_REVIEW_FOLLOW_UP in follow_up or (caveat_counts_as_pending and "claude artifact review" in caveat)
    if not has_follow_up:
        failures.append("artifact_has_no_pending_claude_follow_up")
    if bool(payload.get("legacy_artifact")):
        return _dedupe(failures)
    if gate_mode != "codex_interim":
        failures.append("artifact_gate_not_codex_interim_or_legacy")
    if claude_status not in {"pending", "unknown", "unavailable"}:
        failures.append("artifact_claude_status_not_pending")
    return _dedupe(failures)


def _claude_attestation_evidence(path: str | Path, *, allow_fixture_attestation: bool) -> dict[str, object]:
    attestation_path = Path(path).resolve(strict=False)
    failures: list[str] = []
    text = ""
    if _is_symlink(attestation_path):
        failures.append("claude_attestation_is_symlink")
    try:
        if not attestation_path.is_file():
            failures.append("claude_attestation_missing")
        else:
            text = attestation_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        failures.append("claude_attestation_read_error")
    fields = _parse_attestation_fields(text)
    verdict = fields.get("verdict")
    reviewer = fields.get("reviewer")
    attestation_type = fields.get("attestation_type")
    field_marker = fields.get("review_marker") or fields.get("marker")
    markers = _dedupe(REVIEW_COMPLETE_MARKER_RE.findall(text))
    review_marker = field_marker or (markers[0] if markers else None)

    if not fields:
        failures.append("claude_attestation_malformed")
    if attestation_type is None:
        failures.append("attestation_type_missing")
    elif attestation_type not in ATTESTATION_TYPES:
        failures.append("attestation_type_unknown")
    elif attestation_type == "fixture" and not allow_fixture_attestation:
        failures.append("fixture_attestation_requires_allow_flag")
    if reviewer not in ALLOWED_ATTESTATION_REVIEWERS:
        failures.append("attestation_reviewer_not_claude")
    if verdict != "PASS":
        if verdict and "conditional" in verdict.lower() and "pass" in verdict.lower():
            failures.append("attestation_verdict_conditional_pass")
        elif verdict and "fail" in verdict.lower():
            failures.append("attestation_verdict_fail")
        else:
            failures.append("attestation_verdict_not_pass")
    if not review_marker or not REVIEW_COMPLETE_MARKER_RE.fullmatch(review_marker):
        failures.append("attestation_review_marker_missing")
    if field_marker and markers and field_marker not in markers:
        failures.append("attestation_review_marker_mismatch")
    sha256 = _sha256_file(attestation_path) if attestation_path.is_file() and not attestation_path.is_symlink() else None
    return {
        "path": str(attestation_path),
        "sha256": sha256,
        "text": text,
        "fields": fields,
        "attestation_type": attestation_type,
        "reviewer": reviewer,
        "review_marker": review_marker,
        "markers": markers,
        "verdict": verdict.lower() if verdict == "PASS" else verdict,
        "failures": _dedupe(failures),
    }


def _source_review_report_evidence(path: str | Path | None) -> dict[str, object]:
    if path is None:
        return {"path": None, "sha256": None, "text": "", "failures": []}
    report_path = Path(path).resolve(strict=False)
    failures: list[str] = []
    text = ""
    if _is_symlink(report_path):
        failures.append("source_review_report_is_symlink")
    try:
        if not report_path.is_file():
            failures.append("source_review_report_missing")
        else:
            text = report_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        failures.append("source_review_report_read_error")
    sha256 = _sha256_file(report_path) if report_path.is_file() and not report_path.is_symlink() else None
    return {"path": str(report_path), "sha256": sha256, "text": text, "failures": _dedupe(failures)}


def _parse_attestation_fields(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower().replace("-", "_")
        value = value.strip()
        if not key or not value:
            continue
        fields[key] = value
    if "verdict" in fields:
        fields["verdict"] = fields["verdict"].strip()
    if "reviewer" in fields:
        fields["reviewer"] = fields["reviewer"].strip().lower()
    if "attestation_type" in fields:
        fields["attestation_type"] = fields["attestation_type"].strip().lower()
    return fields


def _closure_artifact_markdown(
    *,
    out_path: Path,
    sha256_path: Path,
    verify: dict[str, str],
    interim_artifact: Path,
    interim_sha256_path: Path,
    interim_hash: str,
    interim_self_check: dict[str, object],
    attestation: dict[str, object],
    source_report: dict[str, object],
    review_gate: dict[str, object],
) -> str:
    prior_gate = interim_self_check.get("review_gate", {})
    fixture_only = attestation.get("attestation_type") == "fixture"
    source_lines = [
        f"- source_review_report: {source_report.get('path')}",
        f"- source_review_report_sha256: {source_report.get('sha256')}",
    ]
    if source_report.get("text"):
        source_lines.extend(["### source_review_report snapshot", _fence(str(source_report.get("text")), "markdown")])
    else:
        source_lines.append("- source_review_report_snapshot: not_provided")
    lines = [
        CLOSURE_TITLE,
        "",
        "## Integrity guard",
        f"- artifact_file: {out_path}",
        f"- sha256_sidecar: {sha256_path}",
        f"- sha256_verify_command: {verify['sha256_verify_command']}",
        "- generated_from: python3 -m agent_office review-artifact close-pending",
        "- artifact_kind: claude_pending_review_closure",
        "- deterministic_timestamp: omitted",
        "- MISSING_FILE_MARKERS: 0",
        "- EMPTY_SECTION_MARKERS: 0",
        "",
        "## Closure summary",
        "- closure_created: true",
        "- pending_closed: true",
        "- closure_source: claude_attestation",
        "- gate_transition: codex_interim -> claude_pass",
        f"- fixture_only: {str(fixture_only).lower()}",
        f"- fixture_attestation_allowed: {str(review_gate['fixture_attestation_allowed']).lower()}",
        "- writes: --out and --out.sha256 only",
        "",
        "## Prior interim gate",
        f"- interim_artifact: {interim_artifact}",
        f"- interim_artifact_sha256: {interim_hash}",
        f"- interim_artifact_sidecar: {interim_sha256_path}",
        f"- prior_gate_mode: {prior_gate.get('gate_mode')}",
        f"- prior_claude_review_status: {prior_gate.get('claude_review_status')}",
        f"- prior_follow_up_required: {prior_gate.get('follow_up_required')}",
        f"- legacy_artifact: {str(interim_self_check.get('legacy_artifact', False)).lower()}",
        "",
        "## Claude review evidence",
        f"- claude_attestation: {attestation['path']}",
        f"- claude_attestation_sha256: {attestation['sha256']}",
        f"- attestation_type: {attestation['attestation_type']}",
        f"- fixture_only: {str(fixture_only).lower()}",
        f"- reviewer: {attestation['reviewer']}",
        f"- verdict: {attestation['verdict']}",
        f"- detected_review_marker: {attestation['review_marker']}",
        f"- detected_review_markers: {attestation['markers']}",
        *source_lines,
        "",
        "## Closed review gate status",
        "- gate_mode: claude_pass",
        "- claude_review_status: pass",
        f"- codex_self_check_status: {review_gate['codex_self_check_status']}",
        f"- interim_merge: {str(review_gate['interim_merge']).lower()}",
        "- pending_closed: true",
        "- follow_up_required: []",
        "- closure_source: claude_attestation",
        f"- attestation_type: {attestation['attestation_type']}",
        f"- fixture_only: {str(fixture_only).lower()}",
        f"- gate_caveat: {review_gate['gate_caveat']}",
        "### review_gate JSON",
        _fence(json.dumps(review_gate, indent=2, ensure_ascii=False), "json"),
        "",
        "## Interim artifact self-check summary",
        _fence(json.dumps(interim_self_check, indent=2, ensure_ascii=False), "json"),
        "",
        "## Claude review report snapshot",
        "This section contains the short Claude PASS attestation used for machine validation, not a verbose full review report. Optional full report evidence is recorded above when --source-review-report is provided.",
        _fence(str(attestation["text"]), "markdown"),
        "",
        "## Caveats",
        f"- {CLOSURE_GATE_CAVEAT}",
        "- Claude PASS evidence closes the pending artifact-review follow-up; it does not prove Claude independently executed VPS commands unless the attestation or source report says so.",
    ]
    if fixture_only:
        lines.extend(
            [
                "- fixture_only: true",
                "- not valid for real production closure",
                "- generated only to test CLI workflow",
            ]
        )
    lines.extend(
        [
            "",
            "## Artifact end",
            "P18_CLAUDE_PENDING_REVIEW_CLOSURE_ARTIFACT_COMPLETE",
            "",
        ]
    )
    return "\n".join(lines)


def _is_closure_artifact(text: str) -> bool:
    return CLOSURE_TITLE in text and _artifact_has_section(text, "Closed review gate status")


def _closure_self_check_failures(text: str, review_gate: dict[str, object]) -> list[str]:
    failures: list[str] = []
    if review_gate.get("gate_mode") != "claude_pass":
        failures.append("closure_gate_mode_not_claude_pass")
    if review_gate.get("claude_review_status") != "pass":
        failures.append("closure_claude_review_status_not_pass")
    if review_gate.get("pending_closed") is not True:
        failures.append("closure_pending_not_closed")
    if review_gate.get("follow_up_required"):
        failures.append("closure_follow_up_required_not_empty")
    if review_gate.get("closure_source") not in {CLAUDE_ARTIFACT_REVIEW_FOLLOW_UP, "claude_attestation"}:
        failures.append("closure_source_not_claude_attestation")
    marker_match = re.search(r"^- detected_review_marker:\s*(.+)$", text, flags=re.MULTILINE)
    verdict_match = re.search(r"^- verdict:\s*(.+)$", text, flags=re.MULTILINE) or re.search(r"^- detected_review_verdict:\s*(.+)$", text, flags=re.MULTILINE)
    if not marker_match or not REVIEW_COMPLETE_MARKER_RE.fullmatch(marker_match.group(1).strip()):
        failures.append("closure_review_marker_missing")
    if not verdict_match or verdict_match.group(1).strip().lower() != "pass":
        failures.append("closure_review_verdict_missing")
    attestation_type = review_gate.get("attestation_type")
    fixture_only = bool(review_gate.get("fixture_only"))
    if attestation_type == "fixture":
        if not fixture_only:
            failures.append("closure_fixture_attestation_not_flagged")
        if "not valid for real production closure" not in text:
            failures.append("closure_fixture_caveat_missing")
    elif attestation_type == "real":
        if fixture_only:
            failures.append("closure_real_attestation_marked_fixture")
    elif attestation_type is not None:
        failures.append("closure_attestation_type_unknown")
    evidence_section = _section_text(text, "Claude review evidence")
    report_section = _section_text(text, "Claude review report snapshot")
    if not PASS_RE.search(evidence_section + "\n" + report_section):
        failures.append("closure_claude_pass_evidence_missing")
    return _dedupe(failures)


def _section_text(text: str, section: str) -> str:
    lines = text.splitlines()
    header = f"## {section}"
    try:
        start = lines.index(header) + 1
    except ValueError:
        return ""
    end = len(lines)
    for index in range(start, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    return "\n".join(lines[start:end])


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _close_pending_error_failures(error: str) -> list[str]:
    prefix = "closure failures: "
    if error.startswith(prefix):
        return [item for item in error[len(prefix) :].split(",") if item]
    return [_error_reason(error)]


def _section_audit(
    *,
    out_path: Path,
    sha256_path: Path,
    verify: dict[str, str],
    validation_success: bool,
    smoke_success: bool,
    command_failures: list[dict[str, object]],
    changed_files: list[dict[str, object]],
    report_snapshots: list[dict[str, str]],
    readme_snapshot: dict[str, str],
    evidence_consistency_warnings: list[str],
    missing_section_count: int,
    empty_section_count: int,
) -> dict[str, object]:
    return {
        "artifact_file": str(out_path),
        "sha256_sidecar": str(sha256_path),
        "sha256_verify_command": verify["sha256_verify_command"],
        "validation_success": validation_success,
        "smoke_success": smoke_success,
        "command_failures": command_failures,
        "missing_section_count": missing_section_count,
        "empty_section_count": empty_section_count,
        "changed_file_snapshot_count": len(changed_files),
        "deleted_file_marker_count": sum(1 for item in changed_files if item.get("snapshot_state") == "deleted"),
        "binary_file_marker_count": sum(1 for item in changed_files if item.get("snapshot_state") == "binary_skipped"),
        "report_snapshot_count": sum(1 for item in report_snapshots if not str(item.get("content", "")).startswith(("REPORT_NOT_FOUND", "REPORT_READ_ERROR"))),
        "readme_snapshot_included": "yes" if not str(readme_snapshot.get("content", "")).startswith("README_NOT_FOUND") else "no",
        "evidence_consistency_warnings": evidence_consistency_warnings,
    }


def _command_failures(validation_results: list[dict[str, object]], smoke_results: list[dict[str, object]]) -> list[dict[str, object]]:
    failures: list[dict[str, object]] = []
    for kind, results in (("validation", validation_results), ("smoke", smoke_results)):
        for item in results:
            if bool(item.get("success")):
                continue
            failures.append(
                {
                    "kind": kind,
                    "name": item.get("name"),
                    "command": item.get("command"),
                    "expected_exit": item.get("expected_exit", 0),
                    "exit_code": item.get("exit_code"),
                }
            )
    return failures


_SHA256_RE = re.compile(r"\b[0-9a-fA-F]{64}\b")
_BYTE_CLAIM_RE = re.compile(r"(?i)\b(?:artifact_bytes|byte_count|byte count|bytes)\D{0,24}([0-9]{2,})\b")


def _evidence_consistency_warnings(report_snapshots: list[dict[str, str]], smoke_results: list[dict[str, object]]) -> list[str]:
    report_text = "\n".join(
        snapshot["content"]
        for snapshot in report_snapshots
        if not snapshot["content"].startswith(("REPORT_NOT_FOUND", "REPORT_READ_ERROR"))
    )
    if not report_text:
        return []
    smoke_context = "\n".join(
        "\n".join(str(item.get(key, "")) for key in ("name", "command", "stdout", "stderr"))
        for item in smoke_results
    )
    warnings: list[str] = []
    smoke_lower = smoke_context.lower()
    if any(digest.lower() not in smoke_lower for digest in set(_SHA256_RE.findall(report_text))):
        warnings.append("possible_report_hash_mismatch")
    if any(claim not in smoke_context for claim in set(_BYTE_CLAIM_RE.findall(report_text))):
        warnings.append("possible_report_size_mismatch")
    return warnings


def _artifact_has_section(text: str, section: str) -> bool:
    return f"## {section}" in text.splitlines()


def _artifact_section_counts(text: str, sections: tuple[str, ...]) -> dict[str, int]:
    missing = 0
    empty = 0
    lines = text.splitlines()
    for section in sections:
        header = f"## {section}"
        try:
            index = lines.index(header)
        except ValueError:
            missing += 1
            continue
        content: list[str] = []
        for line in lines[index + 1 :]:
            if line.startswith("## "):
                break
            content.append(line)
        if not any(line.strip() for line in content):
            empty += 1
    return {"missing_section_count": missing, "empty_section_count": empty}


def self_check_review_artifact_payload(*, artifact: str | Path, sha256_path: str | Path, project_root: Path) -> dict[str, object]:
    del project_root
    artifact_path = Path(artifact).resolve(strict=False)
    sidecar_path = Path(sha256_path).resolve(strict=False)
    failures: list[str] = []
    warnings: list[str] = []
    sidecar_hash: str | None = None
    sidecar_name: str | None = None
    sidecar_bytes: int | None = None
    artifact_bytes = 0
    artifact_hash: str | None = None
    text = ""

    if artifact_path.is_symlink():
        failures.append("artifact_is_symlink")
    if sidecar_path.is_symlink():
        failures.append("sha256_is_symlink")
    try:
        sidecar_text = sidecar_path.read_text(encoding="utf-8")
    except OSError as exc:
        sidecar_text = ""
        failures.append(f"sha256_read_error: {exc}")
    parsed = _parse_sha256_sidecar(sidecar_text)
    if parsed is None:
        failures.append("sha256_sidecar_invalid")
    else:
        sidecar_hash, sidecar_name, sidecar_bytes = parsed
        expected_artifact = (sidecar_path.parent / sidecar_name).resolve(strict=False)
        if expected_artifact != artifact_path:
            failures.append("sha256_sidecar_directory_mismatch")

    try:
        artifact_data = artifact_path.read_bytes()
        artifact_bytes = len(artifact_data)
        artifact_hash = hashlib.sha256(artifact_data).hexdigest()
        text = artifact_data.decode("utf-8", errors="replace")
    except OSError as exc:
        failures.append(f"artifact_read_error: {exc}")

    if sidecar_hash and artifact_hash and sidecar_hash.lower() != artifact_hash.lower():
        failures.append("sha256_mismatch")
    if sidecar_bytes is not None and artifact_bytes != sidecar_bytes:
        failures.append("artifact_bytes_mismatch")

    missing_file_markers = _marker_value(text, "MISSING_FILE_MARKERS")
    empty_section_markers = _marker_value(text, "EMPTY_SECTION_MARKERS")
    if missing_file_markers is None:
        failures.append("missing_file_marker_absent")
    elif missing_file_markers != 0:
        failures.append("missing_file_markers_nonzero")
    if empty_section_markers is None:
        failures.append("empty_section_marker_absent")
    elif empty_section_markers != 0:
        failures.append("empty_section_markers_nonzero")

    is_closure_artifact = _is_closure_artifact(text)
    has_gate_status_section = _artifact_has_section(text, "Review gate status")
    if is_closure_artifact:
        required_sections = CLOSURE_ARTIFACT_SECTIONS
        required_section_contract = "closure"
    else:
        required_sections = REVIEW_ARTIFACT_SECTIONS if has_gate_status_section else LEGACY_REVIEW_ARTIFACT_SECTIONS
        required_section_contract = "current" if has_gate_status_section else "legacy_pre_p16"
    section_counts = _artifact_section_counts(text, required_sections)
    legacy_artifact = bool(text) and not is_closure_artifact and not has_gate_status_section and section_counts["missing_section_count"] == 0
    legacy_gate_status_missing = legacy_artifact

    if is_closure_artifact:
        review_gate = _extract_review_gate(text)
        if bool(review_gate.get("fixture_only")):
            warnings.append("fixture_only_closure")
        if not bool(review_gate.get("gate_valid", False)):
            failures.append("review_gate_invalid")
        failures.extend(_closure_self_check_failures(text, review_gate))
    elif legacy_artifact:
        warnings.append(LEGACY_GATE_STATUS_MISSING)
        review_gate = _legacy_review_gate_status()
    else:
        review_gate = _extract_review_gate(text)
        if not bool(review_gate.get("gate_valid", False)):
            failures.append("review_gate_invalid")
        if review_gate.get("gate_mode") == "codex_interim" and review_gate.get("claude_review_status") == "pending":
            if CLAUDE_ARTIFACT_REVIEW_FOLLOW_UP not in review_gate.get("follow_up_required", []):
                failures.append("missing_claude_artifact_review_follow_up")
    if section_counts["missing_section_count"]:
        failures.append("missing_required_sections")
    if section_counts["empty_section_count"]:
        failures.append("empty_required_sections")

    verify = _verification_metadata(artifact_path, sidecar_path)
    return {
        "schema_version": SCHEMA_VERSION,
        "review_artifact_schema_version": REVIEW_ARTIFACT_SCHEMA_VERSION,
        "kind": "review_artifact_self_check",
        "valid": not failures,
        "artifact": str(artifact_path),
        "sha256_path": str(sidecar_path),
        "sha256_verify_command": verify["sha256_verify_command"],
        "artifact_sha256": artifact_hash,
        "artifact_bytes": artifact_bytes,
        "expected_sha256": sidecar_hash,
        "expected_artifact_basename": sidecar_name,
        "expected_artifact_bytes": sidecar_bytes,
        "missing_file_markers": missing_file_markers,
        "empty_section_markers": empty_section_markers,
        "required_sections": list(required_sections),
        "section_audit": {
            **section_counts,
            "required_section_contract": required_section_contract,
            "review_gate_status_section_present": has_gate_status_section,
            "closure_artifact": is_closure_artifact,
        },
        "legacy_artifact": legacy_artifact,
        "legacy_gate_status_missing": legacy_gate_status_missing,
        "review_gate": review_gate,
        "follow_up_required": review_gate.get("follow_up_required", []),
        "gate_caveat": review_gate.get("gate_caveat"),
        "failures": failures,
        "warnings": warnings,
    }


def format_review_artifact_self_check(payload: dict[str, object]) -> str:
    lines = [
        "Review artifact self-check",
        f"Artifact: {payload['artifact']}",
        f"SHA256 sidecar: {payload['sha256_path']}",
        f"Verification command: {payload['sha256_verify_command']}",
        f"valid: {str(payload['valid']).lower()}",
        f"failures: {len(payload.get('failures', []))}",
        f"legacy_artifact: {str(payload.get('legacy_artifact', False)).lower()}",
        f"closure_artifact: {str(payload.get('section_audit', {}).get('closure_artifact', False)).lower()}",
        f"gate_mode: {payload.get('review_gate', {}).get('gate_mode')}",
        f"claude_review_status: {payload.get('review_gate', {}).get('claude_review_status')}",
        f"pending_closed: {str(payload.get('review_gate', {}).get('pending_closed', False)).lower()}",
        f"follow_up_required: {payload.get('follow_up_required', [])}",
        f"gate_caveat: {payload.get('gate_caveat')}",
    ]
    for failure in payload.get("failures", []):
        lines.append(f"- {failure}")
    return "\n".join(lines)



def _extract_review_gate(text: str) -> dict[str, object]:
    marker = "### review_gate JSON"
    if marker not in text:
        return _review_gate_error_status()
    tail = text.split(marker, 1)[1]
    match = re.search(r"```json\s*(.*?)\s*```", tail, flags=re.DOTALL)
    if not match:
        return _review_gate_error_status()
    try:
        value = json.loads(match.group(1))
    except json.JSONDecodeError:
        return _review_gate_error_status()
    if not isinstance(value, dict):
        return _review_gate_error_status()
    status = _review_gate_error_status()
    status.update({key: value.get(key, status[key]) for key in status})
    status["gate_mode"] = status["gate_mode"] if status["gate_mode"] in GATE_MODES else "unknown"
    status["claude_review_status"] = status["claude_review_status"] if status["claude_review_status"] in CLAUDE_REVIEW_STATUSES else "unknown"
    status["codex_self_check_status"] = status["codex_self_check_status"] if status["codex_self_check_status"] in CODEX_SELF_CHECK_STATUSES else "unknown"
    follow_up = status.get("follow_up_required", [])
    if not isinstance(follow_up, list):
        status["follow_up_required"] = []
    status["interim_merge"] = bool(status.get("interim_merge"))
    status["pending_closed"] = bool(status.get("pending_closed"))
    status["gate_valid"] = bool(status.get("gate_valid"))
    if status["gate_mode"] == "claude_pass" and status["claude_review_status"] != "pass":
        status["gate_valid"] = False
    if status["gate_mode"] == "codex_interim" and status["claude_review_status"] == "pending":
        if CLAUDE_ARTIFACT_REVIEW_FOLLOW_UP not in status["follow_up_required"]:
            status["gate_valid"] = False
    return status

def _parse_sha256_sidecar(text: str) -> tuple[str, str, int | None] | None:
    line = next((item.strip() for item in text.splitlines() if item.strip()), "")
    parts = line.split()
    if len(parts) < 2 or not re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
        return None
    byte_count: int | None = None
    for token in parts[2:]:
        if token.isdigit():
            byte_count = int(token)
            continue
        match = re.fullmatch(r"(?:artifact_bytes|byte_count|bytes)=([0-9]+)", token)
        if match:
            byte_count = int(match.group(1))
    return parts[0], parts[1], byte_count


def _marker_value(text: str, name: str) -> int | None:
    match = re.search(rf"{re.escape(name)}:\s*([0-9]+)", text)
    return int(match.group(1)) if match else None


def _command_blocks(items: list[dict[str, object]]) -> list[str]:
    lines: list[str] = []
    for item in items:
        lines.extend(
            [
                f"### {item['name']}",
                f"- command: `{item['command']}`",
                f"- expected_exit: {item.get('expected_exit', 0)}",
                f"- exit_code: {item['exit_code']}",
                f"- success: {str(item['success']).lower()}",
                "#### stdout",
                _fence(str(item.get("stdout", ""))),
                "#### stderr",
                _fence(str(item.get("stderr", ""))),
            ]
        )
    return lines


def _changed_file_block(item: dict[str, object]) -> list[str]:
    lines = [
        f"### {item['path']}",
        f"- status: {item['status']}",
        f"- snapshot_state: {item['snapshot_state']}",
    ]
    old_path = item.get("old_path")
    if old_path:
        lines.append(f"- old_path: {old_path}")
    content = item.get("content")
    if isinstance(content, str):
        lines.extend(["#### review commit content", _fence(content)])
    else:
        lines.append(str(item.get("note", "no content copied")))
    return lines

def _diff_evidence(project_root: Path, base: str, review: str) -> list[dict[str, object]]:
    specs = [
        ("git diff --stat base..review", ("git", "diff", "--stat", f"{base}..{review}")),
        ("git diff --name-status base..review", ("git", "diff", "--name-status", f"{base}..{review}")),
        ("git diff --check base..review", ("git", "diff", "--check", f"{base}..{review}")),
        ("full diff base..review", ("git", "diff", f"{base}..{review}")),
    ]
    return [_capture_command(CaptureCommand(name, argv), project_root) for name, argv in specs]


def _changed_file_snapshots(project_root: Path, base: str, review: str) -> list[dict[str, object]]:
    result = _run(("git", "diff", "--name-status", f"{base}..{review}"), project_root)
    if result["exit_code"] != 0:
        raise ReviewArtifactError(f"git diff --name-status failed: {result['stderr'] or result['stdout']}")
    items: list[dict[str, object]] = []
    for line in str(result["stdout"]).splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0]
        if status.startswith(("R", "C")) and len(parts) >= 3:
            old_path = parts[1]
            path = parts[2]
        elif len(parts) >= 2:
            old_path = None
            path = parts[1]
        else:
            old_path = None
            path = line.strip()
        item: dict[str, object] = {"path": path, "status": status, "old_path": old_path}
        if status == "D":
            item.update({"snapshot_state": "deleted", "note": "deleted in review commit"})
        else:
            item.update(_review_file_snapshot(project_root, review, path))
        items.append(item)
    return items


def _review_file_snapshot(project_root: Path, review: str, path: str) -> dict[str, object]:
    result = _run_bytes(("git", "show", f"{review}:{path}"), project_root)
    if int(result["exit_code"]) != 0:
        return {
            "snapshot_state": "unavailable",
            "note": f"FILE_READ_ERROR: {result['stderr_bytes'] or result['stdout_bytes']}",
        }
    data = result["stdout_bytes"]
    if not isinstance(data, bytes):
        return {"snapshot_state": "unavailable", "note": "FILE_READ_ERROR: unexpected non-byte git show output"}
    if b"\0" in data:
        return {"snapshot_state": "binary_skipped", "note": "binary file skipped"}
    return {"snapshot_state": "text", "content": _decode(data)}


def _git_state(project_root: Path, branch: str) -> dict[str, str]:
    current_branch = _git_text(project_root, ("branch", "--show-current"), "current branch") or "DETACHED_HEAD"
    head = _git_text(project_root, ("rev-parse", "HEAD"), "HEAD")
    origin = _run(("git", "rev-parse", f"origin/{branch}"), project_root)
    origin_head = str(origin["stdout"]).strip() if origin["exit_code"] == 0 else "not_available"
    status = _git_text(project_root, ("status", "--short", "--untracked-files=no"), "tracked status")
    if not status:
        status = "clean"
    return {"current_branch": current_branch, "head": head, "origin_branch_head": origin_head, "tracked_status": status}


def _repo_identity(project_root: Path) -> str:
    result = _run(("git", "config", "--get", "remote.origin.url"), project_root)
    text = str(result["stdout"]).strip()
    return text if result["exit_code"] == 0 and text else project_root.name


def _resolve_commit(project_root: Path, value: str, label: str) -> str:
    if not value:
        raise ReviewArtifactError(f"missing {label} commit")
    result = _run(("git", "rev-parse", "--verify", f"{value}^{{commit}}"), project_root)
    if result["exit_code"] != 0:
        raise ReviewArtifactError(f"missing or invalid {label} commit: {value}")
    return str(result["stdout"]).strip()


def _git_text(project_root: Path, args: tuple[str, ...], label: str) -> str:
    result = _run(("git", *args), project_root)
    if result["exit_code"] != 0:
        raise ReviewArtifactError(f"git {label} failed: {result['stderr'] or result['stdout']}")
    return str(result["stdout"]).strip()


def _capture_command(command: CaptureCommand, cwd: Path) -> dict[str, object]:
    result = _run(command.argv, cwd)
    exit_code = int(result["exit_code"])
    return {
        "name": command.name,
        "command": shlex.join(command.argv),
        "expected_exit": command.expected_exit,
        "exit_code": exit_code,
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "success": exit_code == command.expected_exit,
    }


def _run(argv: tuple[str, ...], cwd: Path) -> dict[str, object]:
    result = _run_bytes(argv, cwd)
    return {
        "exit_code": result["exit_code"],
        "stdout": _decode(result["stdout_bytes"]),
        "stderr": _decode(result["stderr_bytes"]),
    }


def _run_bytes(argv: tuple[str, ...], cwd: Path) -> dict[str, object]:
    try:
        completed = subprocess.run(argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    except OSError as exc:
        return {"exit_code": 127, "stdout_bytes": b"", "stderr_bytes": str(exc).encode("utf-8", errors="replace")}
    return {"exit_code": completed.returncode, "stdout_bytes": completed.stdout, "stderr_bytes": completed.stderr}


def _decode(data: object) -> str:
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return str(data)


def _existing_run_bundle_sample(project_root: Path) -> tuple[str | None, int]:
    root = project_root / ".ai" / "runs"
    invalid_count = 0
    try:
        if root.is_symlink() or not root.is_dir():
            return None, invalid_count
        for child in sorted(root.iterdir()):
            if not child.is_dir() or child.is_symlink() or not (child / "run.json").is_file():
                continue
            relative = child.relative_to(project_root).as_posix()
            try:
                validate_run_bundle_payload(relative, project_root)
            except RunBundleError:
                invalid_count += 1
                continue
            return relative, invalid_count
    except OSError:
        return None, invalid_count
    return None, invalid_count


def _report_snapshots(project_root: Path, branch: str, title: str) -> list[dict[str, str]]:
    phase = _phase_token(branch) or _phase_token(title) or "P14"
    pattern = f"{phase}_*_REPORT.md"
    try:
        paths = sorted(path for path in project_root.glob(pattern) if path.is_file() and not path.is_symlink())
    except OSError as exc:
        return [{"path": pattern, "content": f"REPORT_READ_ERROR: {exc}"}]
    if not paths:
        return [{"path": pattern, "content": "REPORT_NOT_FOUND"}]
    return [_read_text_snapshot(path, "REPORT_READ_ERROR") for path in paths]


def _phase_token(value: str) -> str | None:
    upper = value.upper()
    for index, char in enumerate(upper):
        if char != "P":
            continue
        digits = []
        for next_char in upper[index + 1 :]:
            if next_char.isdigit():
                digits.append(next_char)
            else:
                break
        if digits:
            return f"P{''.join(digits)}"
    if "PHASE" in upper:
        suffix = upper.split("PHASE", 1)[1]
        digits = []
        for next_char in suffix:
            if next_char.isdigit():
                digits.append(next_char)
            elif digits:
                break
        if digits:
            return f"P{''.join(digits)}"
    return None


def _read_text_snapshot(path: Path, missing_text: str) -> dict[str, str]:
    try:
        if path.is_symlink() or not path.is_file():
            return {"path": path.name, "content": missing_text}
        return {"path": path.name, "content": path.read_text(encoding="utf-8", errors="replace")}
    except OSError as exc:
        return {"path": path.name, "content": f"{missing_text}: {exc}"}


def _resolve_artifact_out_path(out: str | Path, project_root: Path) -> Path:
    requested = Path(out)
    relative_request = not requested.is_absolute()
    if relative_request:
        requested = project_root / requested
    if _is_symlink(requested):
        raise ReviewArtifactError(f"Refusing symlink review artifact output path: {out}")
    try:
        resolved = requested.resolve(strict=False)
    except OSError as exc:
        raise ReviewArtifactError(f"Unable to resolve review artifact output path: {out}") from exc
    base = project_root.resolve()
    if relative_request and resolved != base and base not in resolved.parents:
        raise ReviewArtifactError(f"Refusing relative review artifact output outside project root: {out}")
    runs_root = (project_root / ".ai" / "runs").resolve()
    if resolved == runs_root or runs_root in resolved.parents:
        raise ReviewArtifactError(f"Refusing to write review artifact inside .ai/runs: {out}")
    if resolved == base or base in resolved.parents:
        raise ReviewArtifactError(f"Refusing to write review artifact inside project root: {out}")
    parent = resolved.parent
    if not _exists(parent):
        raise ReviewArtifactError(f"Review artifact parent directory does not exist: {parent}")
    if _is_symlink(parent) or not parent.is_dir():
        raise ReviewArtifactError(f"Review artifact parent is not a directory: {parent}")
    if _exists(resolved) and not resolved.is_file():
        raise ReviewArtifactError(f"Review artifact output path is not a file: {out}")
    if (resolved == base or base in resolved.parents) and _exists(resolved):
        raise ReviewArtifactError(f"Refusing to overwrite existing project file with review artifact: {out}")
    return resolved


def _resolve_artifact_sha256_path(out_path: Path, project_root: Path) -> Path:
    sha256_path = Path(f"{out_path}.sha256")
    if _is_symlink(sha256_path):
        raise ReviewArtifactError(f"Refusing symlink review artifact sha256 path: {sha256_path}")
    try:
        resolved = sha256_path.resolve(strict=False)
    except OSError as exc:
        raise ReviewArtifactError(f"Unable to resolve review artifact sha256 path: {sha256_path}") from exc
    runs_root = (project_root / ".ai" / "runs").resolve()
    if resolved == runs_root or runs_root in resolved.parents:
        raise ReviewArtifactError(f"Refusing to write review artifact sha256 inside .ai/runs: {sha256_path}")
    base = project_root.resolve()
    if resolved == base or base in resolved.parents:
        raise ReviewArtifactError(f"Refusing to write review artifact sha256 inside project root: {sha256_path}")
    parent = resolved.parent
    if not _exists(parent):
        raise ReviewArtifactError(f"Review artifact sha256 parent directory does not exist: {parent}")
    if _is_symlink(parent) or not parent.is_dir():
        raise ReviewArtifactError(f"Review artifact sha256 parent is not a directory: {parent}")
    if _exists(resolved) and not resolved.is_file():
        raise ReviewArtifactError(f"Review artifact sha256 path is not a file: {sha256_path}")
    return resolved


def _write_text(path: Path, value: str) -> None:
    tmp = path.with_name(f"{path.name}.tmp")
    if _is_symlink(tmp):
        raise ReviewArtifactError(f"Refusing to write temporary symlink: {tmp}")
    try:
        tmp.write_text(value, encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        raise ReviewArtifactError(f"Unable to write review artifact file: {path}") from exc


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ReviewArtifactError(f"Unable to read review artifact file: {path}") from exc
    return digest.hexdigest()


def _stat_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError as exc:
        raise ReviewArtifactError(f"Unable to stat review artifact file: {path}") from exc


def _verification_metadata(out_path: Path, sha256_path: Path) -> dict[str, str]:
    artifact_dir = str(out_path.parent)
    sha256_basename = sha256_path.name
    return {
        "artifact_dir": artifact_dir,
        "artifact_basename": out_path.name,
        "sha256_basename": sha256_basename,
        "sha256_verify_command": f"cd {shlex.quote(artifact_dir)} && sha256sum -c {shlex.quote(sha256_basename)}",
    }


def _exists(path: Path) -> bool:
    try:
        return path.exists()
    except OSError as exc:
        raise ReviewArtifactError(f"Unable to access path: {path}") from exc


def _is_symlink(path: Path) -> bool:
    try:
        return path.is_symlink()
    except OSError as exc:
        raise ReviewArtifactError(f"Unable to access path: {path}") from exc


def _fence(value: str, info: str = "text") -> str:
    text = value if value else "(empty output)"
    return f"```{info}\n{text.rstrip()}\n```"


def _error_reason(error: str) -> str:
    lowered = error.lower()
    if "commit" in lowered:
        return "invalid_commit"
    if "symlink" in lowered:
        return "unsafe_path"
    if "outside project" in lowered or ".ai/runs" in lowered or "inside project root" in lowered:
        return "unsafe_path"
    if "parent directory" in lowered or "not a file" in lowered or "overwrite existing project file" in lowered:
        return "invalid_output"
    if "write" in lowered or "stat" in lowered or "read" in lowered:
        return "artifact_io_failure"
    if "git" in lowered:
        return "git_failure"
    return "invalid_request"
