from __future__ import annotations

import hashlib
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
    "Artifact-based review caveat",
    "Git state",
    "Diff evidence",
    "Changed file snapshots",
    "Validation outputs",
    "Smoke outputs",
    "Report snapshots",
    "README snapshot",
)


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
    smoke_commands, smoke_notes = build_smoke_commands(root)
    smoke_results = [_capture_command(command, root) for command in smoke_commands]
    report_snapshots = _report_snapshots(root, branch, title)
    readme_snapshot = _read_text_snapshot(root / "README.md", "README_NOT_FOUND")

    validation_success = all(bool(item["success"]) for item in validation_results)
    smoke_success = all(bool(item["success"]) for item in smoke_results)
    warnings: list[str] = []
    if not validation_success:
        warnings.append("validation_success=false; see Validation outputs section")
    if not smoke_success:
        warnings.append("smoke_success=false; see Smoke outputs section")

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
    )
    _write_text(out_path, artifact_text)
    sha256 = _sha256_file(out_path)
    _write_text(sha256_path, f"{sha256}  {out_path.name}\n")
    byte_count = _stat_size(out_path)
    verify = _verification_metadata(out_path, sha256_path)
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
        "byte_count": byte_count,
        "validation_success": validation_success,
        "smoke_success": smoke_success,
        "sections": list(REVIEW_ARTIFACT_SECTIONS),
        "missing_file_markers": 0,
        "empty_section_markers": 0,
        "warnings": warnings,
        "blocking_reasons": [],
    }


def build_smoke_commands(project_root: Path) -> tuple[list[CaptureCommand], list[str]]:
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
        "byte_count": 0,
        "validation_success": False,
        "smoke_success": False,
        "sections": [],
        "missing_file_markers": 0,
        "empty_section_markers": 0,
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
