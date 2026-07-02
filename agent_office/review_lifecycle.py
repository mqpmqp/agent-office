from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
ARTIFACT_BASED_CAVEAT = "This is an artifact-based review package. Reviewers must not claim they ran VPS validation unless they actually did."
SAFETY_BOUNDARIES = (
    "do not read .env",
    "do not print env vars",
    "do not trigger real provider/model/runtime/adapter calls",
    "do not merge/push/tag unless an explicit merge gate authorizes it",
    "do not force push",
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
    CaptureCommand("unittest", ("python3", "-m", "unittest")),
    CaptureCommand("unittest discovery", ("python3", "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py")),
    CaptureCommand("doctor --adapters", ("python3", "-m", "agent_office", "doctor", "--adapters")),
    CaptureCommand("verify.sh", ("./scripts/verify.sh",)),
    CaptureCommand("smoke-test.sh P6-PROFILES", ("./scripts/smoke-test.sh", "P6-PROFILES")),
    CaptureCommand("run-staged P6-PROFILES --dry-run --reset", ("python3", "-m", "agent_office", "run-staged", "P6-PROFILES", "--dry-run", "--reset")),
    CaptureCommand("orchestrate --help", ("python3", "-m", "agent_office", "orchestrate", "--help")),
    CaptureCommand("tests.test_orchestration_cli", ("python3", "-m", "unittest", "tests.test_orchestration_cli")),
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


def format_review_lifecycle_success(payload: dict[str, Any]) -> str:
    lines = ["AgentOffice review lifecycle command complete", f"command: {payload['command']}"]
    for key in ("marker", "review_marker", "merge_marker", "status"):
        if payload.get(key):
            lines.append(f"{key}: {payload[key]}")
    outputs = payload.get("outputs")
    if isinstance(outputs, dict):
        lines.append("outputs:")
        for key in ("bundle", "prompt", "attestation", "merge_packet"):
            if outputs.get(key):
                lines.append(f"  {key}: {outputs[key]}")
    lines.append("next_action: hand artifacts to Claude for artifact-based review or run the next explicit lifecycle step")
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
