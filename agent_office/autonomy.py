from __future__ import annotations

from typing import Any

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


SCHEMA_VERSION = 1
PLAN_PACKET_TYPE = "agentoffice_autonomy_mission_plan"
PLAN_MARKER = "AGENTOFFICE_AUTONOMY_MISSION_PLAN"
LEDGER_PACKET_TYPE = "agentoffice_autonomy_run_ledger"
LEDGER_MARKER = "AGENTOFFICE_AUTONOMY_RUN_LEDGER"
ALLOWED_LEDGER_STATUSES = {"pending", "running", "passed", "failed", "skipped", "blocked"}
VALIDATION_SUITES = {"minimal", "release", "full"}


class AutonomyError(RuntimeError):
    pass


SAFETY_BOUNDARIES = [
    ".env is never read",
    "environment variables and token values are never printed",
    "provider, runtime, adapter, and model external behavior is not triggered",
    "GitHub tags and releases are not created, overwritten, or deleted",
    "phase6/mainline is not merged or mutated by autonomy commands",
    "validation uses local allowlisted commands only",
]

STOP_CONDITIONS = [
    "tracked worktree changes exist before a write-oriented milestone starts",
    "required baseline commit or release tag does not match the expected value",
    "a validation suite fails after one focused repair attempt",
    "a milestone requires credentials, tokens, or external provider access",
    "an output path targets .env, a symlink, or path traversal outside the project/output root",
]


def autonomy_plan_payload(goal: str) -> dict[str, Any]:
    normalized = goal.strip().lower()
    plans = _plans()
    if normalized not in plans:
        supported = ", ".join(sorted(plans))
        raise AutonomyError(f"unknown autonomy goal: {goal}. supported goals: {supported}.")
    plan = plans[normalized]
    return {
        "schema_version": SCHEMA_VERSION,
        "packet_type": PLAN_PACKET_TYPE,
        "goal": normalized,
        "status": "ready",
        "local_only": True,
        "network_required": False,
        "provider_runtime_adapter_external_behavior": False,
        "phases": plan["phases"],
        "validation_commands": plan["validation_commands"],
        "stop_conditions": STOP_CONDITIONS,
        "safety_boundaries": SAFETY_BOUNDARIES,
        "expected_artifacts": plan["expected_artifacts"],
        "review_handoff": plan["review_handoff"],
        "merge_gate_handoff": plan["merge_gate_handoff"],
    }


def format_autonomy_plan(payload: dict[str, Any]) -> str:
    lines = [
        PLAN_MARKER,
        f"goal: {payload['goal']}",
        f"status: {payload['status']}",
        f"local_only: {_bool_text(bool(payload['local_only']))}",
        f"network_required: {_bool_text(bool(payload['network_required']))}",
        "phases:",
    ]
    for phase in payload["phases"]:
        lines.append(f"  - {phase['id']}: {phase['name']}")
        lines.append(f"    objective: {phase['objective']}")
        lines.append("    tasks:")
        for task in phase["tasks"]:
            lines.append(f"      * {task}")
    lines.append("validation_commands:")
    for command in payload["validation_commands"]:
        lines.append(f"  - {command}")
    lines.append("stop_conditions:")
    for condition in payload["stop_conditions"]:
        lines.append(f"  - {condition}")
    lines.append("safety_boundaries:")
    for boundary in payload["safety_boundaries"]:
        lines.append(f"  - {boundary}")
    lines.append("expected_artifacts:")
    for artifact in payload["expected_artifacts"]:
        lines.append(f"  - {artifact}")
    lines.append("review_handoff:")
    for item in payload["review_handoff"]:
        lines.append(f"  - {item}")
    lines.append("merge_gate_handoff:")
    for item in payload["merge_gate_handoff"]:
        lines.append(f"  - {item}")
    return "\n".join(lines)


def _plans() -> dict[str, dict[str, Any]]:
    return {
        "release-ops": {
            "phases": [
                _phase("release-state", "Release State Inspection", "Summarize tokenless local release status without GitHub writes.", ["verify v1.0.0 archive and checksum if artifacts are present", "verify local GitHub release readback evidence", "classify skipped_no_token honestly as skipped, not published"]),
                _phase("handoff", "Operator Handoff", "Produce deterministic release handoff and dry-run publish guidance.", ["list required assets and exact manual release checks", "record commands that remain token-gated", "document no-write default behavior"]),
            ],
            "validation_commands": _common_validation() + [
                "python3 -m agent_office v1 verify-release-archive --archive /opt/agent-office/agentoffice-v1.0.0-final-delivery-archive.tar.gz --sha256 /opt/agent-office/agentoffice-v1.0.0-final-delivery-archive.tar.gz.sha256 --json",
                "python3 -m agent_office v1 verify-github-release-readback --dir /opt/agent-office/V1_0_0_GITHUB_RELEASE_API_LONGRUN_READBACK --json",
            ],
            "expected_artifacts": ["release-state JSON/text packet", "GitHub release handoff packet", "dry-run publish plan packet"],
            "review_handoff": ["review release-state honesty and no-token behavior", "confirm no GitHub write path runs without explicit operator action"],
            "merge_gate_handoff": ["require archive/readback verification output", "require no tag or release mutation in git/release logs"],
        },
        "post-v1": {
            "phases": [
                _phase("roadmap", "Post-V1 Roadmap", "Turn v1 release outputs into reviewable post-v1 operating lanes.", ["emit deterministic roadmap JSON/text", "separate hotfix, release-ops, and artifact-review lanes", "preserve mainline and release immutability boundaries"]),
                _phase("evidence", "Evidence Closure", "Collect local validation and review evidence for the next branch gate.", ["record validation commands and results", "generate review packet inputs", "generate merge gate inputs without merging"]),
            ],
            "validation_commands": _common_validation() + ["python3 -m agent_office v1 post-v1-roadmap --json"],
            "expected_artifacts": ["post-v1 roadmap packet", "review evidence bundle", "merge gate packet"],
            "review_handoff": ["review roadmap lane scope and safety non-goals", "check validation evidence before merge discussion"],
            "merge_gate_handoff": ["confirm source branch is pushed and target branch is unchanged", "run full local validation before any no-ff merge"],
        },
        "autonomous-delivery": {
            "phases": [
                _phase("plan", "Autonomous Mission Planner", "Create deterministic local mission plans for delivery goals.", ["emit stable JSON/text plans", "include phases, tasks, validation, stop conditions, and handoffs", "fail cleanly for unknown goals"]),
                _phase("ledger", "Run Ledger And Checkpoints", "Persist resumable local run state for long unattended delivery work.", ["initialize a run ledger under an operator-selected path", "record checkpoints, artifacts, and validation results", "reject traversal, symlink, malformed, and .env paths"]),
                _phase("validate", "Validation Recorder", "Run allowlisted local validation suites and save transcripts.", ["support minimal, release, and full validation suites", "record command, exit code, stdout/stderr paths, and duration", "avoid arbitrary shell command execution"]),
                _phase("review-packet", "Review Packet Generator", "Generate local review bundles without calling Claude or any provider.", ["include commit list, diff stat, name-status, full diff, and snapshots", "summarize validation and caveats", "reject unsafe output paths"]),
                _phase("merge-packet", "Merge Gate Packet Generator", "Generate merge instructions and stop conditions without executing a merge.", ["record source, target, heads, merge-base, and changed files", "emit exact validation and merge commands", "document rollback notes and required reports"]),
            ],
            "validation_commands": _common_validation() + ["python3 -m agent_office autonomy plan --goal autonomous-delivery --json", "python3 -m agent_office autonomy plan --goal autonomous-delivery"],
            "expected_artifacts": ["AUTONOMOUS_DELIVERY_PLATFORM_V1_REPORT.md", "AUTONOMOUS_DELIVERY_PLATFORM_V1_SELF_REVIEW.md", "AUTONOMOUS_DELIVERY_PLATFORM_V1_REVIEW_BUNDLE.md", "AUTONOMOUS_DELIVERY_PLATFORM_V1_REVIEW_BUNDLE.md.sha256"],
            "review_handoff": ["review each milestone as an independently shippable local-only feature", "verify ledger, validation, review, and merge packets do not read .env or call providers", "check tests cover positive, negative, and deterministic output paths"],
            "merge_gate_handoff": ["do not merge automatically", "require final full validation and pushed feature branch", "attach self-review, review bundle, and SHA256 sidecar"],
        },
    }


def _phase(identifier: str, name: str, objective: str, tasks: list[str]) -> dict[str, Any]:
    return {"id": identifier, "name": name, "objective": objective, "tasks": tasks}


def _common_validation() -> list[str]:
    return [
        "python3 -m compileall agent_office tests",
        "python3 -m unittest discover -s tests -p 'test_*.py'",
        "git diff --check",
    ]


def _bool_text(value: bool) -> str:
    return "true" if value else "false"



def autonomy_init_payload(path: str, goal: str, project_root: Path) -> dict[str, Any]:
    run_dir = _safe_run_dir(path, project_root, must_exist=False)
    normalized_goal = goal.strip().lower()
    if normalized_goal not in _plans():
        supported = ", ".join(sorted(_plans()))
        raise AutonomyError(f"unknown autonomy goal: {goal}. supported goals: {supported}.")
    run_dir.mkdir(parents=True, exist_ok=True)
    ledger = {
        "schema_version": SCHEMA_VERSION,
        "packet_type": LEDGER_PACKET_TYPE,
        "goal": normalized_goal,
        "status": "running",
        "path": str(run_dir),
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "checkpoints": [],
        "artifacts": [],
        "validation_records": [],
    }
    _write_ledger(run_dir, ledger)
    return _ledger_response("init", ledger)


def autonomy_status_payload(path: str, project_root: Path) -> dict[str, Any]:
    run_dir = _safe_run_dir(path, project_root, must_exist=True)
    ledger = _read_ledger(run_dir)
    return _ledger_response("status", ledger)


def autonomy_checkpoint_payload(path: str, name: str, status: str, project_root: Path) -> dict[str, Any]:
    if status not in ALLOWED_LEDGER_STATUSES:
        raise AutonomyError(f"invalid checkpoint status: {status}.")
    if not name.strip():
        raise AutonomyError("checkpoint name is required.")
    run_dir = _safe_run_dir(path, project_root, must_exist=True)
    ledger = _read_ledger(run_dir)
    checkpoint = {"name": name.strip(), "status": status, "recorded_at": _now_iso()}
    ledger["checkpoints"].append(checkpoint)
    ledger["status"] = status
    ledger["updated_at"] = checkpoint["recorded_at"]
    _write_ledger(run_dir, ledger)
    return _ledger_response("checkpoint", ledger, checkpoint=checkpoint)


def autonomy_report_payload(path: str, project_root: Path) -> dict[str, Any]:
    run_dir = _safe_run_dir(path, project_root, must_exist=True)
    ledger = _read_ledger(run_dir)
    summary = {
        "checkpoint_count": len(ledger["checkpoints"]),
        "artifact_count": len(ledger["artifacts"]),
        "validation_record_count": len(ledger["validation_records"]),
        "latest_checkpoint": ledger["checkpoints"][-1] if ledger["checkpoints"] else None,
    }
    return _ledger_response("report", ledger, summary=summary)



def autonomy_validate_payload(path: str, suite: str, project_root: Path) -> dict[str, Any]:
    if suite not in VALIDATION_SUITES:
        supported = ", ".join(sorted(VALIDATION_SUITES))
        raise AutonomyError(f"unknown validation suite: {suite}. supported suites: {supported}.")
    run_dir = _safe_run_dir(path, project_root, must_exist=True)
    ledger = _read_ledger(run_dir)
    validation_dir = run_dir / "validation" / _validation_run_id(suite)
    validation_dir.mkdir(parents=True, exist_ok=False)
    commands = _validation_commands(suite)
    records = []
    for index, command in enumerate(commands, start=1):
        records.append(_run_validation_command(command, index, validation_dir, project_root))
    ok = all(record["exit_code"] == 0 for record in records)
    validation_record = {
        "suite": suite,
        "status": "passed" if ok else "failed",
        "recorded_at": _now_iso(),
        "commands": records,
    }
    ledger["validation_records"].append(validation_record)
    ledger["status"] = validation_record["status"]
    ledger["updated_at"] = validation_record["recorded_at"]
    _write_ledger(run_dir, ledger)
    return {"ok": ok, "action": "validate", "suite": suite, "ledger": ledger, "validation": validation_record}


def format_autonomy_validation(payload: dict[str, Any]) -> str:
    validation = payload["validation"]
    lines = [
        "AGENTOFFICE_AUTONOMY_VALIDATION",
        f"suite: {payload['suite']}",
        f"status: {validation['status']}",
        f"ok: {_bool_text(bool(payload['ok']))}",
        "commands:",
    ]
    for record in validation["commands"]:
        lines.append(f"  - {record['command']}: exit_code={record['exit_code']} duration_seconds={record['duration_seconds']}")
        lines.append(f"    stdout: {record['stdout_path']}")
        lines.append(f"    stderr: {record['stderr_path']}")
    return "\n".join(lines)


def autonomy_review_packet_payload(base: str, head: str, out: str, project_root: Path) -> dict[str, Any]:
    out_path = _safe_output_file(out, project_root)
    base_commit = _git_capture(["rev-parse", "--verify", base], project_root, "review_packet_base").strip()
    head_commit = _git_capture(["rev-parse", "--verify", head], project_root, "review_packet_head").strip()
    branch = _git_capture(["branch", "--show-current"], project_root, "review_packet_branch").strip() or "detached"
    commits = _git_capture(["log", "--oneline", f"{base_commit}..{head_commit}"], project_root, "review_packet_log").splitlines()
    diff_stat = _git_capture(["diff", "--stat", base_commit, head_commit], project_root, "review_packet_diff_stat")
    name_status = _git_capture(["diff", "--name-status", base_commit, head_commit], project_root, "review_packet_name_status")
    full_diff = _git_capture(["diff", "--no-ext-diff", base_commit, head_commit], project_root, "review_packet_full_diff")
    snapshots = _changed_file_snapshots(name_status, head_commit, project_root)
    bundle = _format_review_packet_markdown(
        base_commit=base_commit,
        head_commit=head_commit,
        branch=branch,
        commits=commits,
        diff_stat=diff_stat,
        name_status=name_status,
        full_diff=full_diff,
        snapshots=snapshots,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists() and out_path.is_symlink():
        raise AutonomyError("review packet output symlink refused.")
    out_path.write_text(bundle, encoding="utf-8")
    return {
        "ok": True,
        "action": "review-packet",
        "base": base_commit,
        "head": head_commit,
        "branch": branch,
        "out": str(out_path),
        "commit_count": len(commits),
        "snapshot_count": len(snapshots),
        "safety_boundaries": SAFETY_BOUNDARIES,
    }


def format_autonomy_review_packet(payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            "AGENTOFFICE_AUTONOMY_REVIEW_PACKET",
            f"ok: {_bool_text(bool(payload['ok']))}",
            f"branch: {payload['branch']}",
            f"base: {payload['base']}",
            f"head: {payload['head']}",
            f"out: {payload['out']}",
            f"commits: {payload['commit_count']}",
            f"snapshots: {payload['snapshot_count']}",
        ]
    )

def format_autonomy_ledger(payload: dict[str, Any]) -> str:
    ledger = payload["ledger"]
    lines = [
        LEDGER_MARKER,
        f"action: {payload['action']}",
        f"goal: {ledger['goal']}",
        f"status: {ledger['status']}",
        f"path: {ledger['path']}",
        f"checkpoints: {len(ledger['checkpoints'])}",
        f"artifacts: {len(ledger['artifacts'])}",
        f"validation_records: {len(ledger['validation_records'])}",
    ]
    checkpoint = payload.get("checkpoint")
    if checkpoint:
        lines.append(f"latest_checkpoint: {checkpoint['name']} ({checkpoint['status']})")
    summary = payload.get("summary")
    if summary:
        lines.append("summary:")
        lines.append(f"  checkpoint_count: {summary['checkpoint_count']}")
        lines.append(f"  artifact_count: {summary['artifact_count']}")
        lines.append(f"  validation_record_count: {summary['validation_record_count']}")
        latest = summary.get("latest_checkpoint")
        lines.append(f"  latest_checkpoint: {latest['name'] + ' (' + latest['status'] + ')' if latest else 'none'}")
    return "\n".join(lines)


def _ledger_response(action: str, ledger: dict[str, Any], **extra: Any) -> dict[str, Any]:
    payload = {"ok": True, "action": action, "ledger": ledger}
    payload.update(extra)
    return payload



def _safe_output_file(path: str, project_root: Path) -> Path:
    if not str(path).strip():
        raise AutonomyError("output path is required.")
    candidate = Path(path)
    if any(part in {"..", ""} for part in candidate.parts) or any(part == ".env" for part in candidate.parts):
        raise AutonomyError("output path contains refused traversal or .env component.")
    if not candidate.is_absolute():
        candidate = project_root / candidate
    _reject_symlink_components(candidate if candidate.exists() else candidate.parent)
    candidate = candidate.resolve(strict=False)
    root = project_root.resolve(strict=False)
    tmp = Path(os.getenv("TMPDIR", "/tmp")).resolve(strict=False)
    if not _is_relative_to(candidate, root) and not _is_relative_to(candidate, tmp):
        raise AutonomyError("output path must stay under the project root or temp directory.")
    if candidate.exists() and candidate.is_dir():
        raise AutonomyError("output path is a directory.")
    return candidate


def _git_capture(args: list[str], project_root: Path, label: str) -> str:
    result = subprocess.run(["git", *args], cwd=project_root, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "git command failed").strip().splitlines()
        detail = message[0] if message else "git command failed"
        raise AutonomyError(f"{label} failed: {detail}")
    return result.stdout


def _changed_file_snapshots(name_status: str, head_commit: str, project_root: Path) -> list[dict[str, Any]]:
    snapshots = []
    for raw_line in name_status.splitlines():
        parts = raw_line.split("\t")
        if len(parts) < 2:
            continue
        status = parts[0]
        file_path = parts[-1]
        path_obj = Path(file_path)
        if status.startswith("D") or any(part == ".env" for part in path_obj.parts):
            snapshots.append({"path": file_path, "status": status, "skipped": True, "reason": "deleted_or_refused_path"})
            continue
        result = subprocess.run(["git", "show", f"{head_commit}:{file_path}"], cwd=project_root, text=True, capture_output=True, check=False)
        if result.returncode != 0:
            snapshots.append({"path": file_path, "status": status, "skipped": True, "reason": "snapshot_unavailable"})
            continue
        content = result.stdout
        truncated = len(content) > 20000
        snapshots.append({"path": file_path, "status": status, "skipped": False, "truncated": truncated, "content": content[:20000]})
    return snapshots


def _format_review_packet_markdown(*, base_commit: str, head_commit: str, branch: str, commits: list[str], diff_stat: str, name_status: str, full_diff: str, snapshots: list[dict[str, Any]]) -> str:
    lines = [
        "# AgentOffice Autonomy Review Packet",
        "",
        "Marker: AGENTOFFICE_AUTONOMY_REVIEW_PACKET",
        "",
        "## Scope",
        "",
        f"- branch: `{branch}`",
        f"- base: `{base_commit}`",
        f"- head: `{head_commit}`",
        "",
        "## Safety Boundaries",
        "",
    ]
    lines.extend(f"- {boundary}" for boundary in SAFETY_BOUNDARIES)
    lines.extend(["", "## Commit List", "", "```text"])
    lines.extend(commits or ["none"])
    lines.extend(["```", "", "## Diff Stat", "", "```text", diff_stat.rstrip() or "none", "```", "", "## Name Status", "", "```text", name_status.rstrip() or "none", "```", "", "## Full Diff", "", "```diff", full_diff.rstrip() or "none", "```", "", "## Changed File Snapshots", ""])
    for snapshot in snapshots:
        lines.append(f"### {snapshot['path']}")
        lines.append("")
        lines.append(f"- status: `{snapshot['status']}`")
        if snapshot.get("skipped"):
            lines.append(f"- skipped: `{snapshot['reason']}`")
            lines.append("")
            continue
        lines.append(f"- truncated: `{_bool_text(bool(snapshot['truncated']))}`")
        lines.append("")
        lines.append("```text")
        lines.append(str(snapshot["content"]).rstrip())
        lines.append("```")
        lines.append("")
    lines.extend(["## Validation Summary", "", "Validation is supplied by the active autonomy ledger or external gate report.", "", "## Requested Review Focus", "", "- correctness of changed behavior", "- safety boundary preservation", "- deterministic output contracts", "- missing tests or operator caveats", "", "## Known Caveats", "", "- This packet is generated locally and does not call external reviewers or providers.", ""])
    return "\n".join(lines)

def _safe_run_dir(path: str, project_root: Path, *, must_exist: bool) -> Path:
    if not str(path).strip():
        raise AutonomyError("run path is required.")
    candidate = Path(path)
    if any(part in {"..", ""} for part in candidate.parts) or any(part == ".env" for part in candidate.parts):
        raise AutonomyError("run path contains refused traversal or .env component.")
    if not candidate.is_absolute():
        candidate = project_root / candidate
    _reject_symlink_components(candidate)
    candidate = candidate.resolve(strict=False)
    root = project_root.resolve(strict=False)
    tmp = Path(os.getenv("TMPDIR", "/tmp")).resolve(strict=False)
    if not _is_relative_to(candidate, root) and not _is_relative_to(candidate, tmp):
        raise AutonomyError("run path must stay under the project root or temp directory.")
    current = candidate if candidate.exists() else candidate.parent
    while current != current.parent:
        if current.exists() and current.is_symlink():
            raise AutonomyError("run path symlink refused.")
        if current == root or current == tmp:
            break
        current = current.parent
    if must_exist and not candidate.exists():
        raise AutonomyError("run ledger path is missing.")
    if candidate.exists() and not candidate.is_dir():
        raise AutonomyError("run ledger path is not a directory.")
    return candidate


def _reject_symlink_components(path: Path) -> None:
    current = path
    candidates = []
    while current != current.parent:
        candidates.append(current)
        current = current.parent
    for candidate in candidates:
        if candidate.exists() and candidate.is_symlink():
            raise AutonomyError("run path symlink refused.")


def _ledger_path(run_dir: Path) -> Path:
    return run_dir / "ledger.json"


def _read_ledger(run_dir: Path) -> dict[str, Any]:
    path = _ledger_path(run_dir)
    if path.is_symlink():
        raise AutonomyError("run ledger symlink refused.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AutonomyError("run ledger file is missing.") from exc
    except json.JSONDecodeError as exc:
        raise AutonomyError("run ledger file is malformed JSON.") from exc
    except OSError as exc:
        raise AutonomyError("run ledger file is unreadable.") from exc
    if not isinstance(data, dict):
        raise AutonomyError("run ledger file must contain a JSON object.")
    for key in ("schema_version", "packet_type", "goal", "status", "path", "created_at", "updated_at", "checkpoints", "artifacts", "validation_records"):
        if key not in data:
            raise AutonomyError(f"run ledger missing required key: {key}.")
    if data["packet_type"] != LEDGER_PACKET_TYPE:
        raise AutonomyError("run ledger packet type is invalid.")
    if data["status"] not in ALLOWED_LEDGER_STATUSES:
        raise AutonomyError("run ledger status is invalid.")
    for key in ("checkpoints", "artifacts", "validation_records"):
        if not isinstance(data[key], list):
            raise AutonomyError(f"run ledger {key} must be a list.")
    return data


def _write_ledger(run_dir: Path, ledger: dict[str, Any]) -> None:
    path = _ledger_path(run_dir)
    if path.exists() and path.is_symlink():
        raise AutonomyError("run ledger symlink refused.")
    tmp_path = run_dir / "ledger.json.tmp"
    tmp_path.write_text(json.dumps(ledger, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    tmp_path.replace(path)



def _validation_commands(suite: str) -> list[list[str]]:
    minimal = [
        ["python3", "-m", "compileall", "agent_office", "tests"],
        ["python3", "-m", "unittest", "tests.test_autonomy_plan_cli"],
        ["git", "diff", "--check"],
    ]
    release = [
        ["python3", "-m", "agent_office", "v1", "final-delivery", "--json"],
        ["python3", "-m", "agent_office", "v1", "verify-release-archive", "--archive", "/opt/agent-office/agentoffice-v1.0.0-final-delivery-archive.tar.gz", "--sha256", "/opt/agent-office/agentoffice-v1.0.0-final-delivery-archive.tar.gz.sha256", "--json"],
        ["python3", "-m", "agent_office", "v1", "verify-github-release-readback", "--dir", "/opt/agent-office/V1_0_0_GITHUB_RELEASE_API_LONGRUN_READBACK", "--json"],
    ]
    full = [
        ["python3", "-m", "compileall", "agent_office", "tests"],
        ["python3", "-m", "unittest"],
        ["python3", "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"],
        ["python3", "-m", "agent_office", "doctor", "--adapters"],
        ["./scripts/verify.sh"],
        ["./scripts/smoke-test.sh", "P6-PROFILES"],
        ["python3", "-m", "agent_office", "run-staged", "P6-PROFILES", "--dry-run", "--reset"],
        ["python3", "-m", "agent_office", "profiles", "--name", "lowest-cost", "--plan", "--json"],
        ["git", "diff", "--check"],
    ]
    if suite == "minimal":
        return minimal
    if suite == "release":
        return release
    if suite == "full":
        return full
    raise AutonomyError(f"unknown validation suite: {suite}.")


def _run_validation_command(command: list[str], index: int, validation_dir: Path, project_root: Path) -> dict[str, Any]:
    started = time.monotonic()
    result = subprocess.run(command, cwd=project_root, text=True, capture_output=True, check=False)
    duration = round(time.monotonic() - started, 3)
    stdout_path = validation_dir / f"{index:02d}-stdout.txt"
    stderr_path = validation_dir / f"{index:02d}-stderr.txt"
    stdout_path.write_text(result.stdout or "", encoding="utf-8")
    stderr_path.write_text(result.stderr or "", encoding="utf-8")
    return {
        "command": _command_text(command),
        "argv": command,
        "exit_code": int(result.returncode),
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "duration_seconds": duration,
    }


def _command_text(command: list[str]) -> str:
    return " ".join(command)


def _validation_run_id(suite: str) -> str:
    safe_time = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{safe_time}-{suite}"

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
