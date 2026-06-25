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
        "follow_up_required": [],
        "pending_review_artifact": None,
        "pending_review_sha256": None,
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

    has_gate_status_section = _artifact_has_section(text, "Review gate status")
    required_sections = REVIEW_ARTIFACT_SECTIONS if has_gate_status_section else LEGACY_REVIEW_ARTIFACT_SECTIONS
    required_section_contract = "current" if has_gate_status_section else "legacy_pre_p16"
    section_counts = _artifact_section_counts(text, required_sections)
    legacy_artifact = bool(text) and not has_gate_status_section and section_counts["missing_section_count"] == 0
    legacy_gate_status_missing = legacy_artifact

    if legacy_artifact:
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
        f"gate_mode: {payload.get('review_gate', {}).get('gate_mode')}",
        f"claude_review_status: {payload.get('review_gate', {}).get('claude_review_status')}",
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
    if (resolved == base or base in resolved.parents) and _exists(resolved):
        raise ReviewArtifactError(f"Refusing to overwrite existing project file with review artifact sha256: {sha256_path}")
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
    if "outside project" in lowered or ".ai/runs" in lowered:
        return "unsafe_path"
    if "parent directory" in lowered or "not a file" in lowered or "overwrite existing project file" in lowered:
        return "invalid_output"
    if "write" in lowered or "stat" in lowered or "read" in lowered:
        return "artifact_io_failure"
    if "git" in lowered:
        return "git_failure"
    return "invalid_request"
