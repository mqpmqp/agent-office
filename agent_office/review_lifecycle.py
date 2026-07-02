from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
ARTIFACT_BASED_CAVEAT = "This is an artifact-based review package. Reviewers must not claim they ran VPS validation unless they actually did."
REVIEWED_DELIVERY_EVIDENCE_MARKER = "REVIEWED_DELIVERY_EVIDENCE_BUNDLE_COMPLETE"
SAFETY_BOUNDARIES = (
    "do not read .env",
    "do not print env vars",
    "do not trigger real provider/model/runtime/adapter calls",
    "do not merge/push/tag unless an explicit merge gate authorizes it",
    "do not force push",
)
CODEX_ONLY_WORKFLOW = (
    "Codex implementation",
    "Codex self-review",
    "full validation",
    "Codex merge gate",
    "push mainline",
)
CODEX_ONLY_VALIDATION_CHECKLIST = (
    "python3 -m compileall agent_office tests",
    "python3 -m unittest tests.test_review_lifecycle_cli",
    "python3 -m unittest",
    "python3 -m unittest discover -s tests -p 'test_*.py'",
    "python3 -m agent_office doctor --adapters",
    "./scripts/verify.sh",
    "./scripts/smoke-test.sh P6-PROFILES",
    "python3 -m agent_office run-staged P6-PROFILES --dry-run --reset",
    "python3 -m agent_office review --help",
    "python3 -m agent_office review bundle --help",
    "python3 -m agent_office review attest --help",
    "python3 -m agent_office review merge-packet --help",
    "python3 -m agent_office review codex-gate --help",
    "python3 -m agent_office review reviewed-delivery --help",
    "python3 -m agent_office review codex-deliver --help",
    "git diff --check",
)
EXPECTED_REVIEW_FIELDS = (
    "verdict: pass / conditional pass / fail",
    "artifact-based caveat",
    "files reviewed",
    "validation artifacts reviewed",
    "blocker findings",
    "major findings",
    "minor findings",
    "nits",
    "missing tests",
    "contract risks",
    "safety risks",
    "regression risks",
    "report accuracy",
    "recommended minimal delta patch if needed",
    "final confidence",
)


@dataclass(frozen=True)
class CaptureCommand:
    name: str
    argv: tuple[str, ...]
    expected_exit: int = 0


DEFAULT_VALIDATION_COMMANDS = (
    CaptureCommand("compileall", ("python3", "-m", "compileall", "agent_office", "tests")),
    CaptureCommand("tests.test_review_lifecycle_cli", ("python3", "-m", "unittest", "tests.test_review_lifecycle_cli")),
    CaptureCommand("unittest", ("python3", "-m", "unittest")),
    CaptureCommand("unittest discovery", ("python3", "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py")),
    CaptureCommand("doctor --adapters", ("python3", "-m", "agent_office", "doctor", "--adapters")),
    CaptureCommand("verify.sh", ("./scripts/verify.sh",)),
    CaptureCommand("smoke-test.sh P6-PROFILES", ("./scripts/smoke-test.sh", "P6-PROFILES")),
    CaptureCommand("run-staged P6-PROFILES --dry-run --reset", ("python3", "-m", "agent_office", "run-staged", "P6-PROFILES", "--dry-run", "--reset")),
    CaptureCommand("review --help", ("python3", "-m", "agent_office", "review", "--help")),
    CaptureCommand("review bundle --help", ("python3", "-m", "agent_office", "review", "bundle", "--help")),
    CaptureCommand("review attest --help", ("python3", "-m", "agent_office", "review", "attest", "--help")),
    CaptureCommand("review merge-packet --help", ("python3", "-m", "agent_office", "review", "merge-packet", "--help")),
    CaptureCommand("review codex-gate --help", ("python3", "-m", "agent_office", "review", "codex-gate", "--help")),
    CaptureCommand("review reviewed-delivery --help", ("python3", "-m", "agent_office", "review", "reviewed-delivery", "--help")),
    CaptureCommand("review codex-deliver --help", ("python3", "-m", "agent_office", "review", "codex-deliver", "--help")),
    CaptureCommand("git diff --check", ("git", "diff", "--check")),
)


class ReviewLifecycleError(ValueError):
    def __init__(self, error_code: str, message: str, details: dict[str, Any] | None = None, exit_code: int = 2) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.details = details or {}
        self.exit_code = exit_code


def error_payload(command: str, exc: ReviewLifecycleError) -> dict[str, Any]:
    return {"ok": False, "command": command, "error_code": exc.error_code, "message": exc.message, "details": exc.details}


def format_error(payload: dict[str, Any]) -> str:
    lines = ["AgentOffice review lifecycle command failed", f"command: {payload['command']}", f"error_code: {payload['error_code']}", f"reason: {payload['message']}"]
    details = payload.get("details")
    if isinstance(details, dict) and details:
        lines.append("details:")
        for key in sorted(details):
            lines.append(f"  {key}: {details[key]}")
    return "\n".join(lines)


def review_bundle_payload(
    *,
    baseline: str,
    head: str,
    branch: str,
    report: str | Path,
    out: str | Path,
    prompt_out: str | Path,
    title: str,
    bundle_marker: str,
    review_marker: str,
    focus: str | None,
    project_root: Path,
    run_validation: bool = False,
    validation_fixture_dir: str | Path | None = None,
    allow_dirty: bool = False,
    mkdirs: bool = False,
) -> dict[str, Any]:
    command = "review bundle"
    root = project_root.resolve()
    baseline_commit = _resolve_commit(root, baseline, "baseline")
    head_commit = _resolve_commit(root, head, "head")
    _require_branch(root, branch)
    tracked_status = _tracked_status(root)
    if tracked_status and not allow_dirty:
        raise ReviewLifecycleError("review_bundle_dirty_tree", "tracked working tree is dirty; pass --allow-dirty to record dirty state", {"status": tracked_status})
    report_path = _require_input_file(report, "review_bundle_missing_report")
    report_text = _read_text(report_path, "review_bundle_unreadable_report")
    focus_text, focus_source = _focus_text(focus)
    out_path = _prepare_output_path(out, "review_bundle", mkdirs=mkdirs)
    prompt_path = _prepare_output_path(prompt_out, "review_prompt", mkdirs=mkdirs)
    diff_check = _git_capture(root, ("diff", "--check", baseline_commit, head_commit))
    git_evidence = _git_evidence(root, baseline_commit, head_commit, branch, tracked_status, diff_check)
    validation = _validation_evidence(root, run_validation=run_validation, fixture_dir=validation_fixture_dir)
    validation_success = all(item["exit_code"] == item["expected_exit"] for item in validation)
    incomplete = bool(run_validation or validation_fixture_dir) and not validation_success
    bundle_text = _bundle_markdown(
        title=title,
        bundle_marker=bundle_marker,
        review_marker=review_marker,
        root=root,
        branch=branch,
        baseline=baseline_commit,
        head=head_commit,
        report_path=report_path,
        report_text=report_text,
        focus_text=focus_text,
        focus_source=focus_source,
        git_evidence=git_evidence,
        validation=validation,
        validation_success=validation_success,
        output_bundle=out_path,
        output_prompt=prompt_path,
        incomplete=incomplete,
    )
    if incomplete:
        partial_path = Path(str(out_path) + ".partial")
        _prepare_output_path(partial_path, "review_bundle", mkdirs=mkdirs)
        _safe_write(partial_path, bundle_text)
        failed = [item for item in validation if item["exit_code"] != item["expected_exit"]]
        raise ReviewLifecycleError(
            "review_bundle_validation_failed",
            "validation command failed; incomplete bundle was written with .partial suffix",
            {"partial_bundle": str(partial_path), "failed_commands": [item["name"] for item in failed]},
            exit_code=1,
        )
    _safe_write(out_path, bundle_text)
    prompt_text = _prompt_markdown(
        baseline=baseline_commit,
        head=head_commit,
        branch=branch,
        report_path=report_path,
        bundle_path=out_path,
        review_marker=review_marker,
        title=title,
    )
    _safe_write(prompt_path, prompt_text)
    return _success_payload(
        command,
        branch=branch,
        baseline=baseline_commit,
        head=head_commit,
        outputs={"bundle": str(out_path), "prompt": str(prompt_path), "attestation": None, "merge_packet": None},
        extra={"marker": bundle_marker, "review_marker": review_marker, "validation_success": validation_success, "changed_files": git_evidence["changed_files"]},
    )


def review_prompt_payload(
    *,
    baseline: str,
    head: str,
    branch: str,
    report: str | Path,
    bundle: str | Path,
    out: str | Path,
    review_marker: str,
    title: str | None,
    project_root: Path,
    mkdirs: bool = False,
) -> dict[str, Any]:
    command = "review prompt"
    root = project_root.resolve()
    baseline_commit = _resolve_commit(root, baseline, "baseline")
    head_commit = _resolve_commit(root, head, "head")
    _require_branch(root, branch)
    report_path = _require_input_file(report, "review_prompt_missing_report")
    bundle_path = _require_input_file(bundle, "review_prompt_missing_bundle")
    out_path = _prepare_output_path(out, "review_prompt", mkdirs=mkdirs)
    text = _prompt_markdown(
        baseline=baseline_commit,
        head=head_commit,
        branch=branch,
        report_path=report_path,
        bundle_path=bundle_path,
        review_marker=review_marker,
        title=title or "AgentOffice Artifact Review",
    )
    _safe_write(out_path, text)
    return _success_payload(command, branch=branch, baseline=baseline_commit, head=head_commit, outputs={"bundle": str(bundle_path), "prompt": str(out_path), "attestation": None, "merge_packet": None}, extra={"review_marker": review_marker})


def review_attest_payload(
    *,
    review_report: str | Path,
    expected_marker: str,
    expected_verdict: str,
    out: str | Path,
    mkdirs: bool = False,
) -> dict[str, Any]:
    command = "review attest"
    out_path = _prepare_output_path(out, "review_attest", mkdirs=mkdirs)
    report_path = _require_input_file(review_report, "review_attest_missing_report")
    text = _read_text(report_path, "review_attest_unreadable_report")
    verdicts = _detect_verdicts(text)
    marker_present = expected_marker in text
    if not marker_present:
        raise ReviewLifecycleError("review_attest_marker_missing", "expected review marker is missing", {"expected_marker": expected_marker})
    if not verdicts:
        raise ReviewLifecycleError("review_attest_verdict_missing", "review verdict is missing", {})
    if len(set(verdicts)) > 1:
        raise ReviewLifecycleError("review_attest_ambiguous_verdict", "multiple conflicting verdicts were detected", {"verdicts": verdicts})
    detected = verdicts[0]
    expected = expected_verdict.strip().lower()
    if detected != expected:
        raise ReviewLifecycleError("review_attest_verdict_mismatch", "review verdict does not match expected verdict", {"detected_verdict": detected, "expected_verdict": expected})
    if detected != "pass":
        raise ReviewLifecycleError("review_attest_non_pass_verdict", "only verdict: pass is accepted by default", {"detected_verdict": detected})
    blocker_present = _finding_present(text, "blocker findings")
    major_present = _finding_present(text, "major findings")
    attestation = _attestation_markdown(report_path, expected_marker, expected, detected, marker_present, blocker_present, major_present, "pass")
    _safe_write(out_path, attestation)
    return _success_payload(command, branch=None, baseline=None, head=None, outputs={"bundle": None, "prompt": None, "attestation": str(out_path), "merge_packet": None}, extra={"status": "pass", "detected_verdict": detected, "marker_present": marker_present, "blocker_finding_present": blocker_present, "major_finding_present": major_present})


def review_merge_packet_payload(
    *,
    baseline: str,
    source_branch: str,
    source_commit: str,
    implementation_report: str | Path,
    review_bundle: str | Path,
    review_attestation: str | Path | None,
    out: str | Path,
    merge_marker: str,
    project_root: Path,
    mkdirs: bool = False,
) -> dict[str, Any]:
    command = "review merge-packet"
    root = project_root.resolve()
    baseline_commit = _resolve_commit(root, baseline, "baseline")
    source_commit_resolved = _resolve_commit(root, source_commit, "source")
    _require_branch(root, source_branch)
    report_path = _require_input_file(implementation_report, "review_merge_packet_missing_report")
    bundle_path = _require_input_file(review_bundle, "review_merge_packet_missing_bundle")
    attestation_path = _require_input_file(review_attestation, "review_merge_packet_missing_attestation") if review_attestation else None
    if attestation_path:
        attestation_text = _read_text(attestation_path, "review_merge_packet_unreadable_attestation")
        attestation_status = "pass" if re.search(r"(?im)^\s*status\s*:\s*pass\s*$", attestation_text) else "unverified"
        if attestation_status != "pass":
            raise ReviewLifecycleError("review_merge_packet_attestation_not_pass", "review attestation is not pass", {"attestation": str(attestation_path)})
    else:
        attestation_status = "pending"
    out_path = _prepare_output_path(out, "review_merge_packet", mkdirs=mkdirs)
    checksum_path = Path(str(bundle_path) + ".sha256")
    text = _merge_packet_markdown(
        baseline=baseline_commit,
        source_branch=source_branch,
        source_commit=source_commit_resolved,
        implementation_report=report_path,
        review_bundle=bundle_path,
        review_attestation=attestation_path,
        attestation_status=attestation_status,
        checksum_path=checksum_path if checksum_path.is_file() else None,
        merge_marker=merge_marker,
    )
    _safe_write(out_path, text)
    return _success_payload(command, branch=source_branch, baseline=baseline_commit, head=source_commit_resolved, outputs={"bundle": str(bundle_path), "prompt": None, "attestation": str(attestation_path) if attestation_path else None, "merge_packet": str(out_path)}, extra={"merge_marker": merge_marker, "attestation_status": attestation_status})


def review_codex_gate_payload(
    *,
    baseline: str,
    head: str,
    branch: str,
    out: str | Path,
    project_root: Path,
    allow_dirty: bool = False,
    mkdirs: bool = False,
) -> dict[str, Any]:
    command = "review codex-gate"
    root = project_root.resolve()
    baseline_commit = _resolve_commit(root, baseline, "baseline")
    head_commit = _resolve_commit(root, head, "head")
    _require_branch(root, branch)
    tracked_status = _tracked_status(root)
    if tracked_status and not allow_dirty:
        raise ReviewLifecycleError("review_codex_gate_dirty_tree", "tracked working tree is dirty; pass --allow-dirty to record dirty state", {"status": tracked_status})
    diff_check = _git_capture(root, ("diff", "--check", baseline_commit, head_commit))
    if diff_check["exit_code"] != 0:
        raise ReviewLifecycleError("review_codex_gate_diff_check_failed", "git diff --check failed for the reviewed range", {"stderr": diff_check["stderr"].strip(), "stdout": diff_check["stdout"].strip()}, exit_code=1)
    git_evidence = _git_evidence(root, baseline_commit, head_commit, branch, tracked_status, diff_check)
    out_path = _prepare_output_path(out, "review_codex_gate", mkdirs=mkdirs)
    text = _codex_gate_markdown(
        root=root,
        baseline=baseline_commit,
        head=head_commit,
        branch=branch,
        git_evidence=git_evidence,
    )
    _safe_write(out_path, text)
    return _success_payload(
        command,
        branch=branch,
        baseline=baseline_commit,
        head=head_commit,
        outputs={"bundle": None, "prompt": None, "attestation": None, "merge_packet": None, "codex_gate": str(out_path)},
        extra={
            "status": "ready",
            "marker": "CODEX_ONLY_DELIVERY_LANE_READY",
            "workflow": list(CODEX_ONLY_WORKFLOW),
            "validation_checklist": list(CODEX_ONLY_VALIDATION_CHECKLIST),
            "changed_files": git_evidence["changed_files"],
            "claude_path": "optional_legacy_lower_level",
        },
    )


def review_codex_deliver_payload(
    *,
    source: str,
    target: str,
    expected_source_head: str,
    expected_target_head: str,
    out: str | Path,
    project_root: Path,
    phase: str | None = None,
    run_id: str | None = None,
    merge_authorized: bool = False,
    push_authorized: bool = False,
    allow_dirty: bool = False,
    mkdirs: bool = False,
) -> dict[str, Any]:
    command = "review codex-deliver"
    root = project_root.resolve()
    _require_branch(root, source)
    _require_branch(root, target)
    expected_source = _resolve_commit(root, expected_source_head, "source")
    expected_target = _resolve_commit(root, expected_target_head, "target")
    source_head = _git(root, ("rev-parse", source)).stdout.strip()
    target_head = _git(root, ("rev-parse", target)).stdout.strip()
    origin_source_head = _git_optional(root, f"origin/{source}")
    origin_target_head = _git_optional(root, f"origin/{target}")
    tracked_status = _tracked_status(root)
    untracked_files = _untracked_files(root)
    diff_check = _git_capture(root, ("diff", "--check", expected_target, expected_source))
    changed_files = _git(root, ("diff", "--name-only", expected_target, expected_source)).stdout.splitlines()
    diff_stat = _git(root, ("diff", "--stat", expected_target, expected_source)).stdout
    name_status = _git(root, ("diff", "--name-status", expected_target, expected_source)).stdout

    readiness_blockers: list[str] = []
    if source_head != expected_source:
        readiness_blockers.append("source_head_mismatch")
    if target_head != expected_target:
        readiness_blockers.append("target_head_mismatch")
    if origin_source_head != "unavailable" and origin_source_head != expected_source:
        readiness_blockers.append("origin_source_head_mismatch")
    if origin_target_head != "unavailable" and origin_target_head != expected_target:
        readiness_blockers.append("origin_target_head_mismatch")
    if tracked_status and not allow_dirty:
        readiness_blockers.append("tracked_tree_dirty")
    if diff_check["exit_code"] != 0:
        readiness_blockers.append("diff_check_failed")

    merge_gate_blockers = list(readiness_blockers)
    if not merge_authorized:
        merge_gate_blockers.append("merge_authorization_missing")
    if not push_authorized:
        merge_gate_blockers.append("push_authorization_missing")

    merge_planned = merge_authorized and not readiness_blockers
    push_planned = push_authorized and not readiness_blockers
    execution_status = "safe_mode" if not merge_authorized and not push_authorized else "blocked"
    if not merge_gate_blockers:
        execution_status = "ready_to_execute"

    out_path = _prepare_output_path(out, "review_codex_deliver", mkdirs=mkdirs)
    payload: dict[str, Any] = {
        "ok": True,
        "command": command,
        "phase": phase or "unspecified",
        "run_id": run_id or f"{source}->{target}",
        "source_branch": source,
        "source_head": source_head,
        "expected_source_head": expected_source,
        "target_branch": target,
        "target_head": target_head,
        "target_expected_head": expected_target,
        "origin_source_head": origin_source_head,
        "origin_target_head": origin_target_head,
        "tracked_tree_clean": not bool(tracked_status),
        "tracked_status": tracked_status or "clean",
        "untracked_artifacts_allowed": True,
        "untracked_artifact_count": len(untracked_files),
        "changed_files": changed_files,
        "diff_stat": diff_stat,
        "name_status": name_status,
        "diff_check_status": "pass" if diff_check["exit_code"] == 0 else "fail",
        "diff_check_exit_code": diff_check["exit_code"],
        "validation_command_list": codex_only_validation_command_list(),
        "pre_merge_validation_status": "not_run_by_runner",
        "post_merge_validation_status": "not_executed",
        "merge_authorization_status": "authorized" if merge_authorized else "not_authorized",
        "push_authorization_status": "authorized" if push_authorized else "not_authorized",
        "merge_planned": merge_planned,
        "push_planned": push_planned,
        "merge_executed": False,
        "push_executed": False,
        "non_destructive": execution_status in {"safe_mode", "blocked"},
        "execution_status": execution_status,
        "execution_failed_step": "none",
        "execution_error": "",
        "final_target_head": target_head,
        "final_origin_target_status": origin_target_head,
        "safety_boundary_checklist": _codex_delivery_safety_checklist(),
        "claude_path": "optional_legacy_lower_level",
        "readiness": "ready" if not readiness_blockers else "blocked",
        "readiness_blocking_reasons": readiness_blockers,
        "merge_gate_ready": not merge_gate_blockers,
        "blocking_reasons": merge_gate_blockers,
        "outputs": {"codex_delivery_report": str(out_path)},
        "marker": "P34_CODEX_DELIVERY_RUNNER_COMPLETE",
    }

    def record_execution_failure(step: str, message: str, completed: subprocess.CompletedProcess[str] | None = None) -> None:
        error_text = message
        details: dict[str, Any] = {"step": step, "report": str(out_path)}
        if completed is not None:
            stdout = completed.stdout.strip()
            stderr = completed.stderr.strip()
            error_text = stderr or stdout or message
            details.update({"argv": completed.args, "stdout": stdout, "stderr": stderr})
        payload["execution_status"] = "failed"
        payload["non_destructive"] = not payload["merge_executed"] and not payload["push_executed"]
        payload["execution_failed_step"] = step
        payload["execution_error"] = error_text
        payload["final_target_head"] = _git_optional(root, target)
        payload["final_origin_target_status"] = _git_optional(root, f"origin/{target}")
        _safe_write(out_path, _codex_deliver_markdown(payload))
        raise ReviewLifecycleError(f"review_codex_deliver_{step}_failed", message, details, exit_code=1)

    if not merge_gate_blockers:
        checkout = _git(root, ("checkout", target), check=False)
        if checkout.returncode != 0:
            record_execution_failure("checkout", "git checkout target branch failed", checkout)
        checkout_target_head = _git(root, ("rev-parse", "HEAD")).stdout.strip()
        if checkout_target_head != expected_target:
            record_execution_failure("target_head_changed", "target branch changed before merge execution")

        merge = _git(root, ("merge", "--no-ff", source, "-m", f"Merge {source} into {target} via codex-deliver"), check=False)
        if merge.returncode != 0:
            _git(root, ("merge", "--abort"), check=False)
            record_execution_failure("merge", "git merge failed", merge)
        payload["merge_executed"] = True
        payload["final_target_head"] = _git(root, ("rev-parse", target)).stdout.strip()

        push = _git(root, ("push", "origin", target), check=False)
        if push.returncode != 0:
            record_execution_failure("push", "git push failed", push)
        payload["push_executed"] = True

        fetch = _git(root, ("fetch", "origin", target), check=False)
        if fetch.returncode != 0:
            record_execution_failure("post_push_fetch", "git fetch after push failed", fetch)
        payload["final_origin_target_status"] = _git_optional(root, f"origin/{target}")
        if payload["final_origin_target_status"] != payload["final_target_head"]:
            record_execution_failure("push_verify", "origin target did not match local target after push")
        payload["execution_status"] = "executed"
        payload["non_destructive"] = False

    _safe_write(out_path, _codex_deliver_markdown(payload))
    return payload


def review_reviewed_delivery_payload(
    *,
    source: str,
    target: str,
    expected_source_head: str,
    expected_target_head: str,
    implementation_report: str | Path,
    review_bundle: str | Path,
    review_report: str | Path,
    expected_marker: str,
    out_dir: str | Path,
    project_root: Path,
    expected_verdict: str = "pass",
    merge_marker: str = "MERGE_GATE_PASS_MAINLINE_SYNCED",
    phase: str | None = None,
    run_id: str | None = None,
    merge_authorized: bool = False,
    push_authorized: bool = False,
    allow_dirty: bool = False,
    mkdirs: bool = False,
    evidence_bundle_out: str | Path | None = None,
    evidence_bundle_format: str = 'json',
) -> dict[str, Any]:
    command = "review reviewed-delivery"
    run_label = run_id or phase or f"{source}-to-{target}"
    prefix = _slug(run_label)
    output_root = Path(out_dir)
    attestation_out = output_root / f"{prefix}-attestation.md"
    merge_packet_out = output_root / f"{prefix}-merge-packet.md"
    delivery_out = output_root / f"{prefix}-codex-deliver.md"

    attestation_payload = review_attest_payload(
        review_report=review_report,
        expected_marker=expected_marker,
        expected_verdict=expected_verdict,
        out=attestation_out,
        mkdirs=mkdirs,
    )
    merge_packet_payload = review_merge_packet_payload(
        baseline=expected_target_head,
        source_branch=source,
        source_commit=expected_source_head,
        implementation_report=implementation_report,
        review_bundle=review_bundle,
        review_attestation=attestation_out,
        out=merge_packet_out,
        merge_marker=merge_marker,
        project_root=project_root,
        mkdirs=mkdirs,
    )
    delivery_payload = review_codex_deliver_payload(
        source=source,
        target=target,
        expected_source_head=expected_source_head,
        expected_target_head=expected_target_head,
        out=delivery_out,
        project_root=project_root,
        phase=phase,
        run_id=run_id,
        merge_authorized=merge_authorized,
        push_authorized=push_authorized,
        allow_dirty=allow_dirty,
        mkdirs=mkdirs,
    )

    if delivery_payload["merge_executed"] and delivery_payload["push_executed"]:
        status = "delivered"
    elif delivery_payload["execution_status"] == "safe_mode":
        status = "preview"
    else:
        status = "blocked"

    payload = _success_payload(
        command,
        branch=source,
        baseline=delivery_payload["target_expected_head"],
        head=delivery_payload["source_head"],
        outputs={
            "attestation": str(attestation_out),
            "merge_packet": str(merge_packet_out),
            "codex_delivery_report": str(delivery_out),
        },
        extra={
            "status": status,
            "phase": phase or "unspecified",
            "run_id": run_id or f"{source}->{target}",
            "source_branch": source,
            "target_branch": target,
            "expected_source_head": delivery_payload["expected_source_head"],
            "expected_target_head": delivery_payload["target_expected_head"],
            "attestation_status": attestation_payload["status"],
            "merge_packet_status": merge_packet_payload["attestation_status"],
            "delivery_readiness": delivery_payload["readiness"],
            "delivery_execution_status": delivery_payload["execution_status"],
            "merge_gate_ready": delivery_payload["merge_gate_ready"],
            "blocking_reasons": delivery_payload["blocking_reasons"],
            "readiness_blocking_reasons": delivery_payload["readiness_blocking_reasons"],
            "merge_authorization_status": delivery_payload["merge_authorization_status"],
            "push_authorization_status": delivery_payload["push_authorization_status"],
            "merge_executed": delivery_payload["merge_executed"],
            "push_executed": delivery_payload["push_executed"],
            "non_destructive": delivery_payload["non_destructive"],
            "final_target_head": delivery_payload["final_target_head"],
            "final_origin_target_status": delivery_payload["final_origin_target_status"],
            "marker": "REVIEWED_DELIVERY_WORKFLOW_COMPLETE",
        },
    )
    if evidence_bundle_out:
        evidence_path = _prepare_evidence_bundle_output_path(evidence_bundle_out, project_root, output_root, mkdirs=mkdirs)
        evidence_payload = _reviewed_delivery_evidence_payload(
            reviewed_delivery_payload=payload,
            delivery_payload=delivery_payload,
            source=source,
            target=target,
            implementation_report=implementation_report,
            review_bundle=review_bundle,
            review_report=review_report,
            expected_marker=expected_marker,
            expected_verdict=expected_verdict,
            attestation_path=attestation_out,
            merge_packet_path=merge_packet_out,
            delivery_report_path=delivery_out,
            evidence_path=evidence_path,
            project_root=project_root,
            authorized_requested=merge_authorized or push_authorized,
        )
        blockers = _reviewed_delivery_evidence_readiness_blockers(evidence_payload, authorized_requested=merge_authorized or push_authorized)
        evidence_payload["readiness"]["blocking_reasons"] = blockers
        evidence_payload["readiness"]["verdict"] = "ready" if not blockers else "failed"
        if blockers:
            raise ReviewLifecycleError(
                "reviewed_delivery_evidence_readiness_failed",
                "reviewed-delivery evidence bundle readiness checks failed",
                {"blocking_reasons": blockers, "evidence_bundle": str(evidence_path)},
                exit_code=2,
            )
        if evidence_bundle_format == "json":
            evidence_text = json.dumps(evidence_payload, indent=2, sort_keys=True)
        elif evidence_bundle_format == "text":
            evidence_text = _reviewed_delivery_evidence_text(evidence_payload)
        else:
            raise ReviewLifecycleError("reviewed_delivery_evidence_format_invalid", "evidence bundle format must be json or text", {"format": evidence_bundle_format})
        _safe_write(evidence_path, evidence_text)
        payload["outputs"]["evidence_bundle"] = str(evidence_path)
        payload["evidence_bundle_format"] = evidence_bundle_format
        payload["evidence_bundle_readiness"] = evidence_payload["readiness"]["verdict"]
        payload["evidence_bundle_marker"] = REVIEWED_DELIVERY_EVIDENCE_MARKER
    return payload


def _prepare_evidence_bundle_output_path(path: str | Path, project_root: Path, output_root: Path, *, mkdirs: bool) -> Path:
    root = project_root.resolve(strict=False)
    out_root = output_root if output_root.is_absolute() else root / output_root
    out_root = out_root.resolve(strict=False)
    p = Path(path)
    p = p if p.is_absolute() else root / p
    resolved = p.resolve(strict=False)
    allowed_roots = (root, out_root)
    if not any(resolved == base or base in resolved.parents for base in allowed_roots):
        raise ReviewLifecycleError(
            "reviewed_delivery_evidence_output_outside_allowed_roots",
            "evidence bundle output path must stay inside the repository root or reviewed-delivery output root",
            {"path": str(path), "project_root": str(root), "out_dir": str(out_root)},
        )
    return _prepare_output_path(resolved, "reviewed_delivery_evidence", mkdirs=mkdirs)


def _reviewed_delivery_evidence_payload(
    *,
    reviewed_delivery_payload: dict[str, Any],
    delivery_payload: dict[str, Any],
    source: str,
    target: str,
    implementation_report: str | Path,
    review_bundle: str | Path,
    review_report: str | Path,
    expected_marker: str,
    expected_verdict: str,
    attestation_path: Path,
    merge_packet_path: Path,
    delivery_report_path: Path,
    evidence_path: Path,
    project_root: Path,
    authorized_requested: bool,
) -> dict[str, Any]:
    root = project_root.resolve(strict=False)
    delivery_summary = _delivery_execution_summary(delivery_payload, delivery_report_path, root)
    mode = "authorized" if authorized_requested else "safe_mode"
    return {
        "schema_version": SCHEMA_VERSION,
        "marker": REVIEWED_DELIVERY_EVIDENCE_MARKER,
        "command": "review reviewed-delivery",
        "mode": mode,
        "phase": reviewed_delivery_payload["phase"],
        "run_id": reviewed_delivery_payload["run_id"],
        "evidence_bundle_path": _display_path(evidence_path, root),
        "source": {
            "branch": source,
            "head": delivery_payload["source_head"],
            "expected_head": delivery_payload["expected_source_head"],
            "origin_head": delivery_payload["origin_source_head"],
        },
        "target": {
            "branch": target,
            "before": delivery_payload["target_head"],
            "expected_before": delivery_payload["target_expected_head"],
            "origin_before": delivery_payload["origin_target_head"],
            "final_target": delivery_payload["final_target_head"],
            "final_origin": delivery_payload["final_origin_target_status"],
        },
        "review_output": {
            **_file_snapshot(review_report, root, "reviewed_delivery_evidence_missing_review_output"),
            "expected_marker": expected_marker,
            "expected_verdict": expected_verdict,
            "attestation_status": reviewed_delivery_payload["attestation_status"],
        },
        "implementation_report": _file_snapshot(implementation_report, root, "reviewed_delivery_evidence_missing_implementation_report"),
        "review_bundle": _file_snapshot(review_bundle, root, "reviewed_delivery_evidence_missing_review_bundle"),
        "attestation": {
            **_file_snapshot(attestation_path, root, "reviewed_delivery_evidence_missing_attestation"),
            "status": reviewed_delivery_payload["attestation_status"],
        },
        "merge_packet": {
            **_file_snapshot(merge_packet_path, root, "reviewed_delivery_evidence_missing_merge_packet"),
            "readiness": reviewed_delivery_payload["merge_packet_status"],
        },
        "delivery_reports": {
            "current": delivery_summary,
            "safe_mode_report": delivery_summary if mode == "safe_mode" else None,
            "authorized_report": delivery_summary if mode == "authorized" else None,
        },
        "execution": {
            "status": reviewed_delivery_payload["status"],
            "delivery_readiness": reviewed_delivery_payload["delivery_readiness"],
            "delivery_execution_status": reviewed_delivery_payload["delivery_execution_status"],
            "merge_gate_ready": reviewed_delivery_payload["merge_gate_ready"],
            "merge_authorization_status": reviewed_delivery_payload["merge_authorization_status"],
            "push_authorization_status": reviewed_delivery_payload["push_authorization_status"],
            "merge_executed": reviewed_delivery_payload["merge_executed"],
            "push_executed": reviewed_delivery_payload["push_executed"],
            "blocking_reasons": reviewed_delivery_payload["blocking_reasons"],
            "readiness_blocking_reasons": reviewed_delivery_payload["readiness_blocking_reasons"],
        },
        "post_validation_summary": {
            "pre_merge_validation_status": delivery_payload["pre_merge_validation_status"],
            "post_merge_validation_status": delivery_payload["post_merge_validation_status"],
            "validation_command_list": delivery_payload["validation_command_list"],
        },
        "safety_boundary_summary": {
            "review_lifecycle": list(SAFETY_BOUNDARIES),
            "codex_delivery": delivery_payload["safety_boundary_checklist"],
            "non_execution_statement": _codex_deliver_execution_statement(delivery_payload),
        },
        "readiness": {
            "verdict": "pending",
            "blocking_reasons": [],
        },
    }


def _delivery_execution_summary(delivery_payload: dict[str, Any], report_path: Path, root: Path) -> dict[str, Any]:
    return {
        **_file_snapshot(report_path, root, "reviewed_delivery_evidence_missing_delivery_report"),
        "readiness": delivery_payload["readiness"],
        "execution_status": delivery_payload["execution_status"],
        "merge_gate_ready": delivery_payload["merge_gate_ready"],
        "merge_executed": delivery_payload["merge_executed"],
        "push_executed": delivery_payload["push_executed"],
        "final_target_head": delivery_payload["final_target_head"],
        "final_origin_target_status": delivery_payload["final_origin_target_status"],
    }


def _file_snapshot(path: str | Path, root: Path, missing_code: str) -> dict[str, Any]:
    file_path = _require_input_file(path, missing_code)
    return {
        "path": _display_path(file_path, root),
        "sha256": _sha256_file(file_path),
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _reviewed_delivery_evidence_readiness_blockers(evidence: dict[str, Any], *, authorized_requested: bool) -> list[str]:
    blockers: list[str] = []
    execution = evidence["execution"]
    target = evidence["target"]
    if evidence["attestation"]["status"] != "pass":
        blockers.append("attestation_not_pass")
    if evidence["merge_packet"]["readiness"] != "pass":
        blockers.append("merge_packet_not_ready")
    if execution["delivery_readiness"] != "ready":
        blockers.append("delivery_readiness_not_ready")
    if execution["status"] not in {"preview", "delivered"}:
        blockers.append("reviewed_delivery_status_not_ready")
    if target["final_origin"] == "unavailable":
        blockers.append("final_origin_unavailable")
    elif target["final_target"] != target["final_origin"]:
        blockers.append("final_target_origin_mismatch")
    if authorized_requested:
        if execution["delivery_execution_status"] != "executed":
            blockers.append("authorized_delivery_not_executed")
        if not execution["merge_gate_ready"]:
            blockers.append("authorized_merge_gate_not_ready")
        if not execution["merge_executed"]:
            blockers.append("authorized_merge_not_executed")
        if not execution["push_executed"]:
            blockers.append("authorized_push_not_executed")
    else:
        if execution["delivery_execution_status"] != "safe_mode":
            blockers.append("safe_mode_report_not_safe_mode")
        if execution["merge_executed"]:
            blockers.append("safe_mode_merge_executed")
        if execution["push_executed"]:
            blockers.append("safe_mode_push_executed")
    return blockers


def _reviewed_delivery_evidence_text(evidence: dict[str, Any]) -> str:
    current = evidence["delivery_reports"]["current"]
    execution = evidence["execution"]
    target = evidence["target"]
    lines = [
        "# AgentOffice Reviewed Delivery Evidence Bundle",
        "",
        f"Marker: {evidence['marker']}",
        f"readiness_verdict: {evidence['readiness']['verdict']}",
        f"mode: {evidence['mode']}",
        f"source_branch: {evidence['source']['branch']}",
        f"source_head: {evidence['source']['head']}",
        f"target_before: {target['before']}",
        f"final_target: {target['final_target']}",
        f"final_origin: {target['final_origin']}",
        f"merge_executed: {str(execution['merge_executed']).lower()}",
        f"push_executed: {str(execution['push_executed']).lower()}",
        "",
        "## Review Evidence",
        "",
        f"- review_output: {evidence['review_output']['path']} sha256={evidence['review_output']['sha256']}",
        f"- attestation: {evidence['attestation']['path']} status={evidence['attestation']['status']} sha256={evidence['attestation']['sha256']}",
        f"- merge_packet: {evidence['merge_packet']['path']} readiness={evidence['merge_packet']['readiness']} sha256={evidence['merge_packet']['sha256']}",
        "",
        "## Delivery Report",
        "",
        f"- path: {current['path']}",
        f"- sha256: {current['sha256']}",
        f"- readiness: {current['readiness']}",
        f"- execution_status: {current['execution_status']}",
        "",
        "## Post-Validation Summary",
        "",
        f"- pre_merge_validation_status: {evidence['post_validation_summary']['pre_merge_validation_status']}",
        f"- post_merge_validation_status: {evidence['post_validation_summary']['post_merge_validation_status']}",
        "",
        "## Safety Boundary Summary",
        "",
        _bullet_list(evidence["safety_boundary_summary"]["review_lifecycle"]),
        "",
        "## Final Readiness",
        "",
        f"final_readiness_verdict: {evidence['readiness']['verdict']}",
        f"blocking_reasons: {', '.join(evidence['readiness']['blocking_reasons']) if evidence['readiness']['blocking_reasons'] else 'none'}",
    ]
    return "\n".join(lines)


def format_review_lifecycle_success(payload: dict[str, Any]) -> str:
    if payload.get("command") == "review reviewed-delivery":
        return _format_reviewed_delivery_success(payload)
    lines = ["AgentOffice review lifecycle command complete", f"command: {payload['command']}"]
    for key in ("marker", "review_marker", "merge_marker", "status"):
        if payload.get(key):
            lines.append(f"{key}: {payload[key]}")
    outputs = payload.get("outputs")
    if isinstance(outputs, dict):
        lines.append("outputs:")
        for key in ("bundle", "prompt", "attestation", "merge_packet", "codex_gate", "codex_delivery_report"):
            if outputs.get(key):
                lines.append(f"  {key}: {outputs[key]}")
    if payload.get("command") in {"review codex-gate", "review codex-deliver"}:
        lines.append("next_action: run full validation, then use a separately authorized Codex merge gate")
    else:
        lines.append("next_action: hand artifacts to Claude for artifact-based review or run the next explicit lifecycle step")
    return "\n".join(lines)


def _format_reviewed_delivery_success(payload: dict[str, Any]) -> str:
    lines = [
        "AgentOffice reviewed delivery workflow complete",
        f"status: {payload['status']}",
        f"source_branch: {payload['source_branch']}",
        f"target_branch: {payload['target_branch']}",
        f"expected_source_head: {payload['expected_source_head']}",
        f"expected_target_head: {payload['expected_target_head']}",
        f"attestation_status: {payload['attestation_status']}",
        f"merge_packet_status: {payload['merge_packet_status']}",
        f"delivery_readiness: {payload['delivery_readiness']}",
        f"delivery_execution_status: {payload['delivery_execution_status']}",
        f"merge_gate_ready: {str(payload['merge_gate_ready']).lower()}",
        f"merge_executed: {str(payload['merge_executed']).lower()}",
        f"push_executed: {str(payload['push_executed']).lower()}",
        f"final_target_head: {payload['final_target_head']}",
        f"final_origin_target_status: {payload['final_origin_target_status']}",
        "outputs:",
    ]
    outputs = payload.get("outputs") or {}
    for key in ("attestation", "merge_packet", "codex_delivery_report", "evidence_bundle"):
        if outputs.get(key):
            lines.append(f"  {key}: {outputs[key]}")
    blockers = payload.get("blocking_reasons") or []
    readiness_blockers = payload.get("readiness_blocking_reasons") or []
    lines.append(f"blocking_reasons: {', '.join(blockers) if blockers else 'none'}")
    lines.append(f"readiness_blocking_reasons: {', '.join(readiness_blockers) if readiness_blockers else 'none'}")
    lines.append(f"marker: {payload['marker']}")
    return "\n".join(lines)


def _success_payload(command: str, *, branch: str | None, baseline: str | None, head: str | None, outputs: dict[str, str | None], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": True, "command": command, "branch": branch, "baseline": baseline, "head": head, "outputs": outputs}
    if extra:
        payload.update(extra)
    return payload


def _git(root: Path, args: tuple[str, ...], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(["git", *args], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    if check and completed.returncode != 0:
        raise ReviewLifecycleError("review_git_command_failed", "git command failed", {"argv": ["git", *args], "stderr": completed.stderr.strip()})
    return completed


def _git_capture(root: Path, args: tuple[str, ...]) -> dict[str, Any]:
    completed = _git(root, args, check=False)
    return {"argv": ["git", *args], "exit_code": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}


def _resolve_commit(root: Path, ref: str, label: str) -> str:
    if not ref or ref.strip() != ref:
        raise ReviewLifecycleError(f"review_invalid_{label}_commit", f"{label} commit is invalid", {"ref": ref})
    completed = _git(root, ("rev-parse", "--verify", f"{ref}^{{commit}}"), check=False)
    if completed.returncode != 0:
        raise ReviewLifecycleError(f"review_invalid_{label}_commit", f"{label} commit does not exist", {"ref": ref})
    return completed.stdout.strip()


def _require_branch(root: Path, branch: str) -> None:
    if not branch or branch.strip() != branch:
        raise ReviewLifecycleError("review_invalid_branch", "branch is invalid", {"branch": branch})
    completed = _git(root, ("rev-parse", "--verify", f"{branch}^{{commit}}"), check=False)
    if completed.returncode != 0:
        raise ReviewLifecycleError("review_invalid_branch", "branch does not exist", {"branch": branch})


def _tracked_status(root: Path) -> str:
    return _git(root, ("status", "--short", "-uno")).stdout.strip()


def _prepare_output_path(path: str | Path, code_prefix: str, *, mkdirs: bool) -> Path:
    p = Path(path)
    _reject_dotenv(p, f"{code_prefix}_dotenv_refused")
    if p.exists() and p.is_symlink():
        raise ReviewLifecycleError(f"{code_prefix}_output_symlink", "refusing to write through symlink output path", {"path": str(p)})
    if p.exists() and p.is_dir():
        raise ReviewLifecycleError(f"{code_prefix}_output_is_directory", "output path is a directory", {"path": str(p)})
    parent = p.parent if str(p.parent) else Path(".")
    if not parent.exists():
        if mkdirs:
            parent.mkdir(parents=True, exist_ok=True)
        else:
            raise ReviewLifecycleError(f"{code_prefix}_parent_missing", "output parent does not exist", {"parent": str(parent)})
    if parent.is_symlink():
        raise ReviewLifecycleError(f"{code_prefix}_parent_symlink", "refusing symlink output parent", {"parent": str(parent)})
    if not parent.is_dir():
        raise ReviewLifecycleError(f"{code_prefix}_parent_not_directory", "output parent is not a directory", {"parent": str(parent)})
    if not os.access(parent, os.W_OK):
        raise ReviewLifecycleError(f"{code_prefix}_parent_not_writable", "output parent is not writable", {"parent": str(parent)})
    return p


def _safe_write(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    if tmp.exists() and tmp.is_symlink():
        raise ReviewLifecycleError("review_output_tmp_symlink", "refusing symlink temporary output path", {"path": str(tmp)})
    tmp.write_text(text.rstrip() + "\n", encoding="utf-8")
    tmp.replace(path)


def _reject_dotenv(path: Path, code: str) -> None:
    if any(part == ".env" for part in path.parts):
        raise ReviewLifecycleError(code, "refusing to read or write .env path", {"path": str(path)})


def _require_input_file(path: str | Path | None, code: str) -> Path:
    if path is None:
        raise ReviewLifecycleError(code, "required input path is missing", {})
    p = Path(path)
    _reject_dotenv(p, code.replace("missing", "dotenv"))
    if not p.exists():
        raise ReviewLifecycleError(code, "required input file does not exist", {"path": str(p)})
    if not p.is_file():
        raise ReviewLifecycleError(code.replace("missing", "not_file"), "required input path is not a file", {"path": str(p)})
    return p


def _read_text(path: Path, code: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ReviewLifecycleError(code, "input is not valid UTF-8", {"path": str(path)}) from exc
    except OSError as exc:
        raise ReviewLifecycleError(code, "input could not be read", {"path": str(path), "error": str(exc)}) from exc


def _focus_text(focus: str | None) -> tuple[str, str]:
    if not focus:
        return "No additional focus supplied.", "inline"
    possible_path = Path(focus)
    if possible_path.name == ".env" or any(part == ".env" for part in possible_path.parts):
        raise ReviewLifecycleError("review_focus_dotenv_refused", "refusing to read .env focus path", {"path": focus})
    if possible_path.exists():
        return _read_text(possible_path, "review_focus_unreadable"), str(possible_path)
    return focus, "inline"


def _display_path(path: Path, root: Path | None = None) -> str:
    if root is not None:
        try:
            return path.resolve(strict=False).relative_to(root.resolve(strict=False)).as_posix()
        except ValueError:
            pass
    return str(path)


def _git_optional(root: Path, ref: str) -> str:
    completed = _git(root, ("rev-parse", "--verify", f"{ref}^{{commit}}"), check=False)
    return completed.stdout.strip() if completed.returncode == 0 else "unavailable"


def _git_evidence(root: Path, baseline: str, head: str, branch: str, tracked_status: str, diff_check: dict[str, Any]) -> dict[str, Any]:
    source_state = {
        "repo_root": str(root),
        "branch": branch,
        "head": _git(root, ("rev-parse", "HEAD")).stdout.strip(),
        "branch_commit": _git_optional(root, branch),
        "origin_branch_commit": _git_optional(root, f"origin/{branch}"),
        "local_mainline_commit": _git_optional(root, "phase6/mainline"),
        "origin_mainline_commit": _git_optional(root, "origin/phase6/mainline"),
        "tracked_status": tracked_status or "clean",
        "state": "dirty" if tracked_status else "clean",
    }
    changed_files = _git(root, ("diff", "--name-only", baseline, head)).stdout.splitlines()
    return {
        "source_state": source_state,
        "changed_files": changed_files,
        "diff_stat": _git(root, ("diff", "--stat", baseline, head)).stdout,
        "name_status": _git(root, ("diff", "--name-status", baseline, head)).stdout,
        "full_diff": _git(root, ("diff", "--no-ext-diff", baseline, head)).stdout,
        "diff_check": diff_check,
    }


def _validation_evidence(root: Path, *, run_validation: bool, fixture_dir: str | Path | None) -> list[dict[str, Any]]:
    if fixture_dir:
        return [_fixture_result(Path(fixture_dir), command) for command in DEFAULT_VALIDATION_COMMANDS]
    if not run_validation:
        return []
    results: list[dict[str, Any]] = []
    for command in DEFAULT_VALIDATION_COMMANDS:
        completed = subprocess.run(list(command.argv), cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        results.append({"name": command.name, "argv": list(command.argv), "expected_exit": command.expected_exit, "exit_code": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr})
    return results


def _fixture_result(root: Path, command: CaptureCommand) -> dict[str, Any]:
    stem = _slug(command.name)
    exit_path = root / f"{stem}.exit"
    if not exit_path.is_file():
        raise ReviewLifecycleError("review_bundle_validation_fixture_missing", "validation fixture exit file is missing", {"path": str(exit_path)})
    try:
        exit_code = int(exit_path.read_text(encoding="utf-8").strip())
    except ValueError as exc:
        raise ReviewLifecycleError("review_bundle_validation_fixture_invalid", "validation fixture exit file is invalid", {"path": str(exit_path)}) from exc
    return {
        "name": command.name,
        "argv": list(command.argv),
        "expected_exit": command.expected_exit,
        "exit_code": exit_code,
        "stdout": _read_optional(root / f"{stem}.stdout"),
        "stderr": _read_optional(root / f"{stem}.stderr"),
    }


def _read_optional(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "command"


def _bundle_markdown(**data: Any) -> str:
    root: Path = data["root"]
    git_evidence = data["git_evidence"]
    validation = data["validation"]
    validation_status = "pass" if data["validation_success"] else ("failed" if validation else "not_run")
    lines = [
        f"# {data['title']}",
        "",
        data["bundle_marker"],
        "",
        "## Bundle Metadata",
        "",
        f"bundle_schema_version: {SCHEMA_VERSION}",
        f"status: {'incomplete_failed_validation' if data['incomplete'] else 'complete'}",
        f"repo_root: {root}",
        f"branch: {data['branch']}",
        f"baseline_commit: {data['baseline']}",
        f"head_commit: {data['head']}",
        f"expected_review_marker: {data['review_marker']}",
        "",
        "## Source State And Provenance",
        "",
        _json_block(git_evidence["source_state"]),
        "",
        "## Implementation Report",
        "",
        f"path: {_display_path(data['report_path'], root)}",
        "",
        _fence(data["report_text"], "markdown"),
        "",
        "## Changed Files",
        "",
        _bullet_list(git_evidence["changed_files"]),
        "",
        "## Diff Stat",
        "",
        _fence(git_evidence["diff_stat"]),
        "",
        "## Name Status",
        "",
        _fence(git_evidence["name_status"]),
        "",
        "## Diff Check Output",
        "",
        f"exit_code: {git_evidence['diff_check']['exit_code']}",
        _fence(_combined_output(git_evidence["diff_check"])),
        "",
        "## Full Diff",
        "",
        _fence(git_evidence["full_diff"], "diff"),
        "",
        "## Validation Command List",
        "",
        _bullet_list([" ".join(command.argv) for command in DEFAULT_VALIDATION_COMMANDS]),
        "",
        "## Validation Captured Output Sections",
        "",
        f"validation_status: {validation_status}",
    ]
    if validation:
        for item in validation:
            lines.extend(["", f"### {item['name']}", "", f"argv: {' '.join(item['argv'])}", f"expected_exit: {item['expected_exit']}", f"exit_code: {item['exit_code']}", "", "stdout:", _fence(item["stdout"]), "", "stderr:", _fence(item["stderr"])])
    else:
        lines.extend(["", "Validation was not executed for this bundle."])
    lines.extend([
        "",
        "## Generated File Paths",
        "",
        f"bundle: {data['output_bundle'].name}",
        f"prompt: {data['output_prompt'].name}",
        f"implementation_report: {_display_path(data['report_path'], root)}",
        "",
        "## SHA Checksum Guidance",
        "",
        f"Run: sha256sum {data['output_bundle'].name} > {data['output_bundle'].name}.sha256",
        f"Verify: sha256sum -c {data['output_bundle'].name}.sha256",
        "",
        "## Safety Boundary Summary",
        "",
        _bullet_list(SAFETY_BOUNDARIES),
        "",
        "## Artifact-Based Review Caveat",
        "",
        ARTIFACT_BASED_CAVEAT,
        "",
        "## Required Review Focus",
        "",
        f"source: {data['focus_source']}",
        "",
        _fence(data["focus_text"], "text"),
        "",
        "## Expected Claude Review Output Shape",
        "",
        _bullet_list(EXPECTED_REVIEW_FIELDS),
        "",
        "## Expected Review Marker",
        "",
        data["review_marker"],
    ])
    return "\n".join(lines)


def _prompt_markdown(*, baseline: str, head: str, branch: str, report_path: Path, bundle_path: Path, review_marker: str, title: str) -> str:
    lines = [
        f"# Claude Artifact Review Prompt: {title}",
        "",
        "You are performing an artifact-based review. Do not claim you ran tests, VPS commands, provider calls, or validation unless you actually ran them yourself.",
        "",
        "## Review Object",
        "",
        "- repo: mqpmqp/agent-office",
        f"- baseline: {baseline}",
        f"- branch: {branch}",
        f"- reviewed commit: {head}",
        f"- implementation report: {report_path}",
        f"- review bundle: {bundle_path}",
        "",
        "## Must Review",
        "",
        _bullet_list([
            "contract correctness",
            "CLI/API schema stability",
            "JSON/text output stability",
            "validation evidence",
            "tests",
            "docs/report accuracy",
            "safety",
            "regression risk",
            "missing tests",
            "minimal delta patch",
        ]),
        "",
        "## Output Format",
        "",
        _bullet_list(EXPECTED_REVIEW_FIELDS),
        "",
        "If the review passes, end with this marker on its own line:",
        "",
        review_marker,
    ]
    return "\n".join(lines)


def codex_only_validation_command_list() -> list[str]:
    return list(CODEX_ONLY_VALIDATION_CHECKLIST)


def _codex_delivery_safety_checklist() -> list[str]:
    return [
        ".env not read",
        "env vars not printed",
        "provider/model/runtime/adapter external behavior not triggered",
        "no force push",
        "no tag",
        "no Claude output generated",
        "no Claude attestation generated",
        "no Claude merge packet generated",
    ]


def _untracked_files(root: Path) -> list[str]:
    return [line[3:] for line in _git(root, ("status", "--short", "--untracked-files=all")).stdout.splitlines() if line.startswith("?? ")]


def _codex_deliver_markdown(payload: dict[str, Any]) -> str:
    execution_error = []
    if payload.get("execution_error"):
        execution_error = ["", "### Execution Error", "", _fence(str(payload["execution_error"]))]
    return "\n".join([
        "# AgentOffice Codex Delivery Runner Report",
        "",
        "Marker: P34_CODEX_DELIVERY_RUNNER_COMPLETE",
        "",
        "## Identity",
        "",
        f"- phase: {payload['phase']}",
        f"- run_id: {payload['run_id']}",
        f"- command: {payload['command']}",
        "",
        "## Source And Target",
        "",
        f"- source_branch: {payload['source_branch']}",
        f"- source_head: {payload['source_head']}",
        f"- expected_source_head: {payload['expected_source_head']}",
        f"- origin_source_head: {payload['origin_source_head']}",
        f"- target_branch: {payload['target_branch']}",
        f"- target_head: {payload['target_head']}",
        f"- target_expected_head: {payload['target_expected_head']}",
        f"- origin_target_head: {payload['origin_target_head']}",
        "",
        "## Readiness",
        "",
        f"- readiness: {payload['readiness']}",
        f"- merge_gate_ready: {str(payload['merge_gate_ready']).lower()}",
        f"- blocking_reasons: {', '.join(payload['blocking_reasons']) if payload['blocking_reasons'] else 'none'}",
        f"- readiness_blocking_reasons: {', '.join(payload['readiness_blocking_reasons']) if payload['readiness_blocking_reasons'] else 'none'}",
        "",
        "## Working Tree",
        "",
        f"- tracked_tree_clean: {str(payload['tracked_tree_clean']).lower()}",
        f"- tracked_status: {payload['tracked_status']}",
        f"- untracked_artifacts_allowed: {str(payload['untracked_artifacts_allowed']).lower()}",
        f"- untracked_artifact_count: {payload['untracked_artifact_count']}",
        "",
        "## Diff",
        "",
        "### Changed Files",
        "",
        _bullet_list(payload["changed_files"]),
        "",
        "### Name Status",
        "",
        _fence(payload["name_status"]),
        "",
        "### Diff Stat",
        "",
        _fence(payload["diff_stat"]),
        "",
        f"diff_check_status: {payload['diff_check_status']}",
        f"diff_check_exit_code: {payload['diff_check_exit_code']}",
        "",
        "## Validation",
        "",
        f"- pre_merge_validation_status: {payload['pre_merge_validation_status']}",
        f"- post_merge_validation_status: {payload['post_merge_validation_status']}",
        "",
        _bullet_list(payload["validation_command_list"]),
        "",
        "## Authorization",
        "",
        f"- merge_authorization_status: {payload['merge_authorization_status']}",
        f"- push_authorization_status: {payload['push_authorization_status']}",
        f"- merge_planned: {str(payload['merge_planned']).lower()}",
        f"- push_planned: {str(payload['push_planned']).lower()}",
        f"- merge_executed: {str(payload['merge_executed']).lower()}",
        f"- push_executed: {str(payload['push_executed']).lower()}",
        f"- non_destructive: {str(payload['non_destructive']).lower()}",
        f"- execution_status: {payload['execution_status']}",
        f"- execution_failed_step: {payload['execution_failed_step']}",
        f"- final_target_head: {payload['final_target_head']}",
        f"- final_origin_target_status: {payload['final_origin_target_status']}",
        *execution_error,
        "",
        "## Safety Boundary Checklist",
        "",
        _bullet_list(payload["safety_boundary_checklist"]),
        "",
        "## Claude Path",
        "",
        "Claude review, attestation, and merge-packet remain optional/legacy/lower-level only, not mandatory.",
        "",
        "## Non-Execution Statement",
        "",
        _codex_deliver_execution_statement(payload),
    ])


def _codex_deliver_execution_statement(payload: dict[str, Any]) -> str:
    status = payload.get("execution_status")
    if status == "executed":
        return "Authorized mode executed merge and push. It did not execute tag, provider calls, runtimes, models, adapters, Claude output generation, Claude attestation generation, or Claude merge-packet generation."
    if status == "failed":
        return "Authorized mode attempted delivery and failed. It did not execute tag, provider calls, runtimes, models, adapters, Claude output generation, Claude attestation generation, or Claude merge-packet generation."
    if status == "safe_mode":
        return "Safe mode generated this report only. It did not execute merge, push, tag, provider calls, runtimes, models, adapters, Claude output generation, Claude attestation generation, or Claude merge-packet generation."
    return "Blocked delivery generated this report only. It did not execute merge, push, tag, provider calls, runtimes, models, adapters, Claude output generation, Claude attestation generation, or Claude merge-packet generation."


def _codex_gate_markdown(**data: Any) -> str:
    git_evidence = data["git_evidence"]
    return "\n".join([
        "# AgentOffice Codex-Only Delivery Lane Readiness",
        "",
        "Marker: CODEX_ONLY_DELIVERY_LANE_READY",
        "",
        "## Workflow",
        "",
        " -> ".join(CODEX_ONLY_WORKFLOW),
        "",
        "## Scope",
        "",
        "Codex-only is the default delivery lane. Claude artifact review, review attestation, and review merge-packet remain optional/legacy/lower-level paths, not mandatory gates.",
        "",
        "Merge gate still requires separate authorization; this report does not execute merge, push, tag, provider calls, runtimes, models, or adapters.",
        "",
        "## Source",
        "",
        f"- repo_root: {data['root']}",
        f"- branch: {data['branch']}",
        f"- baseline_commit: {data['baseline']}",
        f"- head_commit: {data['head']}",
        "",
        "## Changed Files",
        "",
        _bullet_list(git_evidence["changed_files"]),
        "",
        "## Name Status",
        "",
        _fence(git_evidence["name_status"]),
        "",
        "## Diff Stat",
        "",
        _fence(git_evidence["diff_stat"]),
        "",
        "## Diff Check",
        "",
        f"exit_code: {git_evidence['diff_check']['exit_code']}",
        _fence(_combined_output(git_evidence["diff_check"])),
        "",
        "## Required Validation Checklist",
        "",
        _bullet_list(CODEX_ONLY_VALIDATION_CHECKLIST),
        "",
        "## Safety Boundaries",
        "",
        _bullet_list(SAFETY_BOUNDARIES),
        "",
        "## Non-Execution Statement",
        "",
        "This command generated a readiness report only. It did not execute merge, push, tag, provider calls, runtimes, models, adapters, Claude output generation, Claude attestation generation, or Claude merge-packet generation.",
    ])


def _attestation_markdown(report_path: Path, marker: str, expected: str, detected: str, marker_present: bool, blocker_present: bool, major_present: bool, status: str) -> str:
    return "\n".join([
        "# AgentOffice Claude Review Attestation",
        "",
        f"status: {status}",
        f"source_review_report: {report_path}",
        f"expected_verdict: {expected}",
        f"detected_verdict: {detected}",
        f"expected_marker: {marker}",
        f"marker_present: {str(marker_present).lower()}",
        f"blocker_finding_present: {str(blocker_present).lower()}",
        f"major_finding_present: {str(major_present).lower()}",
        f"artifact_based_caveat: {ARTIFACT_BASED_CAVEAT}",
    ])


def _merge_packet_markdown(**data: Any) -> str:
    pre_post = [" ".join(command.argv) for command in DEFAULT_VALIDATION_COMMANDS]
    attestation = data["review_attestation"] or "PENDING_CLAUDE_REVIEW_ATTESTATION"
    checksum = data["checksum_path"] or "No checksum sidecar detected next to review bundle."
    return "\n".join([
        "# AgentOffice Merge Gate Packet",
        "",
        f"Marker suggestion: {data['merge_marker']}",
        "",
        "## Merge Target",
        "",
        "- target branch: phase6/mainline",
        f"- mainline baseline before merge: {data['baseline']}",
        f"- source branch: {data['source_branch']}",
        f"- source commit: {data['source_commit']}",
        "",
        "## Review Evidence",
        "",
        f"- implementation report: {data['implementation_report']}",
        f"- review bundle: {data['review_bundle']}",
        f"- review attestation: {attestation}",
        f"- review attestation status: {data['attestation_status']}",
        f"- artifact checksum path: {checksum}",
        "",
        "## Expected Pre-Merge Validation List",
        "",
        _bullet_list(pre_post),
        "",
        "## Expected Post-Merge Validation List",
        "",
        _bullet_list(pre_post),
        "",
        "## Safety Constraints",
        "",
        _bullet_list([*SAFETY_BOUNDARIES, "do not execute this packet generator as a merge", "do not merge P31 until Claude artifact review is complete"]),
        "",
        "## Exact Merge Command Suggestion",
        "",
        _fence(f"git checkout phase6/mainline\ngit merge --no-ff {data['source_branch']} -m \"Merge P31 phase lifecycle review system\""),
        "",
        "## Exact Push Command Suggestion",
        "",
        _fence("git push origin phase6/mainline"),
        "",
        "## Failure Stop Policy",
        "",
        "Stop on failed preflight, failed validation, merge conflict, safety boundary risk, or any need for force/overwrite/delete.",
        "",
        "## Final Report Template",
        "",
        _fence(f"Marker: {data['merge_marker']}\nmerge_commit: <sha>\norigin/phase6/mainline: <sha>\nvalidation: pass\nsafety: pass", "text"),
        "",
        "## Non-Execution Statement",
        "",
        "This command generated a merge-gate packet only. It did not execute merge, push, tag, or default-branch mutation.",
    ])


def _detect_verdicts(text: str) -> list[str]:
    verdicts: list[str] = []
    for match in re.finditer(r"(?im)^\s*verdict\s*:\s*(conditional\s+pass|pass|fail)\b", text):
        verdicts.append(" ".join(match.group(1).lower().split()))
    return verdicts


def _finding_present(text: str, label: str) -> bool:
    match = re.search(rf"(?im)^\s*{re.escape(label)}\s*:\s*(.+)$", text)
    return bool(match and match.group(1).strip().lower() not in {"none", "n/a", "no", "none found"})


def _json_block(value: Any) -> str:
    return _fence(json.dumps(value, indent=2, sort_keys=True), "json")


def _fence(text: str, language: str = "") -> str:
    content = text if text else "<no output>"
    return f"```{language}\n{content.rstrip()}\n```"


def _bullet_list(items: Any) -> str:
    values = list(items)
    if not values:
        return "- none"
    return "\n".join(f"- {item}" for item in values)


def _combined_output(result: dict[str, Any]) -> str:
    stdout = result.get("stdout") or ""
    stderr = result.get("stderr") or ""
    if stdout and stderr:
        return f"stdout:\n{stdout}\nstderr:\n{stderr}"
    return stdout or stderr or "<no output>"
