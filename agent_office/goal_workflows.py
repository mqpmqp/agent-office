from __future__ import annotations

import re
import shlex
import subprocess
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
MAX_REVIEW_READ_BYTES = 1024 * 1024
READY_VERDICTS = {"pass", "conditional_pass"}
REVIEW_MARKER_RE = re.compile(r"\bP[0-9A-Z_]*_(?:ARTIFACT_CODE_REVIEW|ARTIFACT_REVIEW|CODE_REVIEW|REVIEW)_COMPLETE\b")

SAFETY_BOUNDARIES = [
    "Never read .env files.",
    "Never print environment variables.",
    "Never call real model, provider, runtime, or adapter external behavior.",
    "Never force push, tag, or change the default branch.",
    "Never clean historical untracked artifacts.",
    "Never merge implementation branches without an explicit merge gate instruction.",
]

AUTONOMY_RULES = [
    "Proceed through routine local implementation and validation without stopping for design questions.",
    "Choose the simplest CLI-first deterministic implementation that matches existing AgentOffice style.",
    "Stop only for unsafe baseline state, unresolvable merge conflicts, unrepairable validation failures, force-push requirements, or unavoidable architecture decisions.",
]

VALIDATION_CHECKLIST = [
    "python3 -m compileall agent_office tests",
    "python3 -m unittest",
    "python3 -m unittest discover -s tests -p 'test_*.py'",
    "python3 -m agent_office doctor --adapters",
    "./scripts/verify.sh",
    "./scripts/smoke-test.sh P6-PROFILES",
    "python3 -m agent_office run-staged P6-PROFILES --dry-run --reset",
    "git diff --check",
    "git status --short --untracked-files=no",
]


def review_gate_payload(*, path: str | Path, action: str) -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []
    text = _read_review_text(path, warnings, errors)
    verdict = "unknown"
    marker: str | None = None
    blocker_count = 0
    major_count = 0
    minor_count = 0
    if text is not None:
        marker = _find_marker(text)
        verdict = _detect_verdict(text)
        lines = text.splitlines()
        blocker_count = _count_named_findings(lines, {"blocker", "blockers", "blocker findings", "blocking findings"})
        major_count = _count_named_findings(lines, {"major", "majors", "major findings"})
        minor_count = _count_named_findings(lines, {"minor", "minors", "minor findings", "minor findings only"})
        if marker is None:
            warnings.append("completion_marker_missing")
        if verdict == "unknown":
            warnings.append("verdict_unknown")
    marker_present = marker is not None
    merge_ready = bool(marker_present and verdict in READY_VERDICTS and blocker_count == 0 and major_count == 0 and not errors)
    valid = bool(marker_present and verdict != "unknown" and not errors)
    return {
        "schema_version": SCHEMA_VERSION,
        "valid": valid,
        "command": _command_text("review-artifact review-gate", action=action, path=path),
        "path": str(path),
        "verdict": verdict,
        "marker": marker,
        "marker_present": marker_present,
        "blocker_count": blocker_count,
        "major_count": major_count,
        "minor_count": minor_count,
        "merge_ready": merge_ready,
        "warnings": _dedupe(warnings),
        "errors": _dedupe(errors),
    }


def merge_readiness_payload(
    *,
    source: str,
    target: str,
    review: str | Path,
    project_root: Path,
    ignore_dirty: bool = False,
    validation_artifacts: list[str] | None = None,
) -> dict[str, Any]:
    root = project_root.resolve()
    warnings: list[str] = []
    errors: list[str] = []
    source_head = _git_commit(root, source, errors, "source")
    target_head = _git_commit(root, target, errors, "target")
    diff_files: list[str] = []
    if source_head and target_head:
        code, stdout, stderr = _git(root, "diff", "--name-only", f"{target}..{source}", "--")
        if code == 0:
            diff_files = [line for line in stdout.splitlines() if line.strip()]
            if not diff_files:
                errors.append("source_has_no_delta_from_target")
        else:
            errors.append(f"git_diff_failed: {stderr or stdout}".strip())
    review_payload = review_gate_payload(path=review, action="status")
    if not review_payload["merge_ready"]:
        errors.append("review_gate_not_merge_ready")
    if not ignore_dirty:
        code, stdout, stderr = _git(root, "status", "--short", "--untracked-files=no")
        if code != 0:
            errors.append(f"git_status_failed: {stderr or stdout}".strip())
        elif stdout.strip():
            errors.append("tracked_worktree_dirty")
    artifacts = [_validation_artifact_entry(item, root) for item in validation_artifacts or []]
    for item in artifacts:
        errors.extend(item["errors"])
        warnings.extend(item["warnings"])
    errors = _dedupe(errors)
    merge_ready = bool(not errors and review_payload["merge_ready"] and diff_files)
    return {
        "schema_version": SCHEMA_VERSION,
        "valid": not errors,
        "command": _merge_readiness_command(source, target, review, ignore_dirty, validation_artifacts or []),
        "source": source,
        "target": target,
        "source_head": source_head,
        "target_head": target_head,
        "diff_files": diff_files,
        "review": review_payload,
        "validation_artifacts": artifacts,
        "merge_ready": merge_ready,
        "warnings": _dedupe(warnings),
        "errors": errors,
    }


def goal_packet_export_payload(*, name: str, baseline: str, out: str | Path, project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    warnings: list[str] = []
    errors: list[str] = []
    branch = _git_value(root, "branch", "--show-current")
    head = _git_value(root, "rev-parse", "HEAD")
    baseline_head = _git_commit(root, baseline, errors, "baseline") if baseline else None
    if not name.strip():
        errors.append("objective_name_required")
    out_path = _coerce_output_path(out, root)
    errors.extend(_output_path_errors(out_path))
    if not errors:
        markdown = _goal_packet_markdown(name=name, baseline=baseline, baseline_head=baseline_head, branch=branch, head=head)
        try:
            out_path.write_text(markdown, encoding="utf-8")
        except OSError as exc:
            errors.append(f"write_failed: {exc}")
    return {
        "schema_version": SCHEMA_VERSION,
        "valid": not errors,
        "command": _goal_packet_command(name, baseline, out),
        "out": str(out_path),
        "objective": name,
        "baseline": baseline,
        "baseline_head": baseline_head,
        "branch": branch,
        "head": head,
        "warnings": _dedupe(warnings),
        "errors": _dedupe(errors),
    }


def format_review_gate_status(payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            "AgentOffice review gate status",
            f"path: {payload['path']}",
            f"valid: {str(payload['valid']).lower()}",
            f"verdict: {payload['verdict']}",
            f"marker: {payload['marker']}",
            f"marker_present: {str(payload['marker_present']).lower()}",
            f"blocker_count: {payload['blocker_count']}",
            f"major_count: {payload['major_count']}",
            f"minor_count: {payload['minor_count']}",
            f"merge_ready: {str(payload['merge_ready']).lower()}",
            f"warnings: {len(payload.get('warnings', []))}",
            f"errors: {len(payload.get('errors', []))}",
        ]
    )


def format_merge_readiness(payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            "AgentOffice merge readiness",
            f"source: {payload['source']}",
            f"target: {payload['target']}",
            f"source_head: {payload['source_head']}",
            f"target_head: {payload['target_head']}",
            f"diff_files: {len(payload['diff_files'])}",
            f"review_merge_ready: {str(payload['review']['merge_ready']).lower()}",
            f"merge_ready: {str(payload['merge_ready']).lower()}",
            f"warnings: {len(payload.get('warnings', []))}",
            f"errors: {len(payload.get('errors', []))}",
        ]
    )


def format_goal_packet_export(payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            "AgentOffice Goal-mode packet export",
            f"out: {payload['out']}",
            f"objective: {payload['objective']}",
            f"baseline: {payload['baseline']}",
            f"branch: {payload['branch']}",
            f"head: {payload['head']}",
            f"valid: {str(payload['valid']).lower()}",
            f"warnings: {len(payload.get('warnings', []))}",
            f"errors: {len(payload.get('errors', []))}",
        ]
    )


def _read_review_text(path: str | Path, warnings: list[str], errors: list[str]) -> str | None:
    review_path = Path(path)
    if review_path.is_symlink():
        errors.append("review_path_symlink_refused")
        return None
    if not review_path.exists():
        errors.append("missing_path")
        return None
    if not review_path.is_file():
        errors.append("review_path_not_file")
        return None
    try:
        with review_path.open("rb") as handle:
            data = handle.read(MAX_REVIEW_READ_BYTES + 1)
    except OSError as exc:
        errors.append(f"read_error: {exc}")
        return None
    if len(data) > MAX_REVIEW_READ_BYTES:
        warnings.append(f"file_too_large_truncated: {len(data)}")
        data = data[:MAX_REVIEW_READ_BYTES]
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        warnings.append("non_utf8_content")
        return data.decode("utf-8", errors="replace")


def _find_marker(text: str) -> str | None:
    match = REVIEW_MARKER_RE.search(text)
    return match.group(0) if match else None


def _detect_verdict(text: str) -> str:
    for pattern in (
        r"(?im)^\s*(?:[-*]\s*)?(?:verdict|review verdict|review result|claude artifact/code review result|claude artifact review result|claude code review result)\s*[:|-]\s*(.+)$",
        r"(?im)^\s*(?:[-*]\s*)?result\s*[:|-]\s*(.+)$",
    ):
        match = re.search(pattern, text)
        if match:
            verdict = _normalize_verdict(match.group(1))
            if verdict != "unknown":
                return verdict
    if re.search(r"(?i)\bconditional\s+pass\b", text):
        return "conditional_pass"
    if re.search(r"(?i)\bpass\b", text):
        return "pass"
    if re.search(r"(?i)\b(fail|failed|request changes|rejected)\b", text):
        return "fail"
    return "unknown"


def _normalize_verdict(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z ]+", " ", value).strip().lower()
    if "conditional" in normalized and "pass" in normalized:
        return "conditional_pass"
    if normalized.startswith("pass") or normalized == "approved":
        return "pass"
    if any(word in normalized for word in ("fail", "failed", "rejected", "request changes", "block")):
        return "fail"
    return "unknown"


def _count_named_findings(lines: list[str], labels: set[str]) -> int:
    count = 0
    matched = False
    for index, line in enumerate(lines):
        value = _label_value(line, labels)
        if value is None:
            continue
        matched = True
        inline_count = _count_inline_findings(value)
        if inline_count is not None:
            count += inline_count
            continue
        count += _count_following_findings(lines[index + 1 :])
    return count if matched else 0


def _label_value(line: str, labels: set[str]) -> str | None:
    stripped = _plain_line(line)
    lower = stripped.lower()
    if not stripped:
        return None
    if ":" in stripped:
        label, value = stripped.split(":", 1)
        if label.strip().lower() in labels:
            return value.strip()
    for label in labels:
        if lower == label:
            return ""
        if lower.startswith(label + " "):
            return stripped[len(label) :].strip(" -:")
    return None


def _plain_line(line: str) -> str:
    stripped = line.strip()
    stripped = stripped.lstrip("#").strip()
    stripped = re.sub(r"^[-*]\s+", "", stripped)
    return stripped


def _count_inline_findings(value: str) -> int | None:
    if not value:
        return None
    if _is_none_text(value):
        return 0
    if value.lower().strip() in {"only"}:
        return None
    return 1


def _count_following_findings(lines: list[str]) -> int:
    count = 0
    saw_none = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        plain = _plain_line(line)
        if stripped.startswith("#") or _looks_like_any_finding_label(plain):
            break
        if _is_none_text(plain):
            saw_none = True
            continue
        if re.match(r"^[-*]\s+", stripped):
            count += 1
            continue
        if count == 0:
            count = 1
        break
    return 0 if saw_none and count == 0 else count


def _looks_like_any_finding_label(value: str) -> bool:
    lower = value.lower()
    labels = {
        "blocker",
        "blockers",
        "blocker findings",
        "blocking findings",
        "major",
        "majors",
        "major findings",
        "minor",
        "minors",
        "minor findings",
        "minor findings only",
    }
    return any(lower == label or lower.startswith(label + ":") for label in labels)


def _is_none_text(value: str) -> bool:
    lower = value.strip().lower().strip(".:")
    return lower in {"none", "no", "no findings", "no blockers", "no blocker findings", "no major findings", "n/a", "na"}


def _git_commit(project_root: Path, revision: str, errors: list[str], label: str) -> str | None:
    if not _safe_revision(revision):
        errors.append(f"bad_{label}_revision")
        return None
    code, stdout, _stderr = _git(project_root, "rev-parse", "--verify", f"{revision}^{{commit}}")
    if code != 0:
        errors.append(f"{label}_commit_not_found: {revision}")
        return None
    return stdout.strip()


def _git_value(project_root: Path, *args: str) -> str | None:
    code, stdout, _stderr = _git(project_root, *args)
    if code != 0:
        return None
    return stdout.strip() or None


def _git(project_root: Path, *args: str) -> tuple[int, str, str]:
    completed = subprocess.run(["git", *args], cwd=project_root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def _safe_revision(value: str | None) -> bool:
    if not value or value.startswith("-"):
        return False
    return not any(ch in value for ch in "\r\n\0")


def _validation_artifact_entry(raw_path: str, project_root: Path) -> dict[str, Any]:
    path = _coerce_output_path(raw_path, project_root)
    warnings: list[str] = []
    errors: list[str] = []
    if path.is_symlink():
        errors.append(f"validation_artifact_symlink_refused: {raw_path}")
    elif not path.exists():
        errors.append(f"validation_artifact_missing: {raw_path}")
    elif not path.is_file():
        errors.append(f"validation_artifact_not_file: {raw_path}")
    else:
        try:
            if path.stat().st_size == 0:
                warnings.append(f"validation_artifact_empty: {raw_path}")
        except OSError as exc:
            errors.append(f"validation_artifact_stat_error: {raw_path}: {exc}")
    return {"path": str(path), "warnings": warnings, "errors": errors}


def _coerce_output_path(path: str | Path, project_root: Path) -> Path:
    value = Path(path)
    if not value.is_absolute():
        value = project_root / value
    return value


def _output_path_errors(path: Path) -> list[str]:
    errors: list[str] = []
    if path.is_symlink():
        errors.append("output_path_symlink_refused")
    if path.exists() and path.is_dir():
        errors.append("output_path_is_directory")
    parent = path.parent
    if parent.is_symlink():
        errors.append("output_parent_symlink_refused")
    elif not parent.exists():
        errors.append("output_parent_missing")
    elif not parent.is_dir():
        errors.append("output_parent_not_directory")
    return errors


def _goal_packet_markdown(*, name: str, baseline: str, baseline_head: str | None, branch: str | None, head: str | None) -> str:
    lines = [
        f"# AgentOffice Goal Mode Packet: {name}",
        "",
        "You are running in Codex Goal Mode for AgentOffice.",
        "",
        "## Repo",
        "",
        "Use Windows PowerShell to SSH into the VPS:",
        "",
        "```bash",
        "ssh -o BatchMode=yes agentoffice-vps",
        "cd /opt/agent-office",
        "```",
        "",
        "## Baseline",
        "",
        f"- objective: {name}",
        f"- baseline: {baseline}",
        f"- baseline_head: {baseline_head or 'unknown'}",
        f"- current_branch: {branch or 'unknown'}",
        f"- current_head: {head or 'unknown'}",
        "",
        "## Safety Boundaries",
    ]
    lines.extend(f"- {item}" for item in SAFETY_BOUNDARIES)
    lines.extend(["", "## Autonomy Rules"])
    lines.extend(f"- {item}" for item in AUTONOMY_RULES)
    lines.extend(["", "## Validation Checklist"])
    lines.extend(f"- `{item}`" for item in VALIDATION_CHECKLIST)
    lines.extend(
        [
            "",
            "## Done Definition",
            "",
            "- Implementation is committed on a feature branch created from the stated baseline.",
            "- Focused tests cover the new behavior and regression commands still pass.",
            "- Full validation has been run and recorded.",
            "- The feature branch is pushed for review.",
            "- No implementation branch is merged without a later explicit merge gate instruction.",
            "",
            "## Report Requirements",
            "",
            "- Record start baseline head, feature branch, final commit, changed files, validations, known limitations, and safety constraints observed.",
            "- Include a clear completion marker for the batch.",
            "- State that .env was not read, environment variables were not printed, and providers/runtimes/adapters were not externally invoked.",
            "",
            "## Human Gate Reminders",
            "",
            "- Review outputs determine merge readiness only; they do not execute a merge.",
            "- A human or later explicit merge gate instruction is required before merging review batches into mainline.",
            "- Push rejection that requires force push is a stop condition.",
            "",
        ]
    )
    return "\n".join(lines)


def _command_text(base: str, *, action: str, path: str | Path) -> str:
    return " ".join(shlex.quote(part) for part in ["python3", "-m", "agent_office", *base.split(), action, "--path", str(path), "--json"])


def _merge_readiness_command(source: str, target: str, review: str | Path, ignore_dirty: bool, artifacts: list[str]) -> str:
    command = ["python3", "-m", "agent_office", "merge-readiness", "--source", source, "--target", target, "--review", str(review)]
    for artifact in artifacts:
        command.extend(["--validation-artifact", artifact])
    if ignore_dirty:
        command.append("--ignore-dirty")
    command.append("--json")
    return " ".join(shlex.quote(part) for part in command)


def _goal_packet_command(name: str, baseline: str, out: str | Path) -> str:
    command = ["python3", "-m", "agent_office", "goal-packet", "export", "--name", name, "--baseline", baseline, "--out", str(out), "--json"]
    return " ".join(shlex.quote(part) for part in command)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
