from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .autonomy import (
    AutonomyError,
    autonomy_init_payload,
    autonomy_merge_packet_payload,
    autonomy_review_packet_payload,
    autonomy_validate_payload,
)
from .v1_final_delivery import build_final_delivery_packet
from .v1_post_release_ops import github_release_plan_payload, release_state_payload

SCHEMA_VERSION = 1
QUEUE_PACKET_TYPE = "agentoffice_autonomy_goal_queue"
QUEUE_MARKER = "AGENTOFFICE_AUTONOMY_GOAL_QUEUE"
NEXT_MARKER = "AGENTOFFICE_AUTONOMY_QUEUE_NEXT"
RUNNER_MARKER = "AGENTOFFICE_AUTONOMY_GOAL_RUNNER"
TEMPLATE_MARKER = "AGENTOFFICE_AUTONOMY_GOAL_TEMPLATE"
REPORT_MARKER = "AGENTOFFICE_AUTONOMY_GOAL_REPORT"
CLASSIFY_MARKER = "AGENTOFFICE_AUTONOMY_FAILURE_CLASSIFICATION"

TASK_STATUSES = {"pending", "running", "passed", "failed", "skipped", "blocked"}
TASK_KINDS = {
    "checkpoint",
    "validate-suite",
    "review-packet",
    "merge-packet",
    "release-state",
    "github-release-plan",
    "final-delivery",
    "noop",
    "manual",
}
FAILURE_CLASSES = {
    "validation_failed",
    "command_failed",
    "invalid_queue",
    "unsafe_path",
    "symlink_refused",
    "dependency_failed",
    "dependency_cycle",
    "missing_dependency",
    "missing_artifact",
    "malformed_json",
    "partial_remote_state",
    "manual_block",
    "unknown",
}
NON_RETRYABLE = {
    "invalid_queue",
    "unsafe_path",
    "symlink_refused",
    "dependency_failed",
    "dependency_cycle",
    "missing_dependency",
    "missing_artifact",
    "malformed_json",
    "partial_remote_state",
    "manual_block",
    "unknown",
}


def queue_init_payload(path: str, goal: str | None, template: str | None, project_root: Path) -> dict[str, Any]:
    queue_dir = _safe_queue_dir(path, project_root, must_exist=False)
    queue_dir.mkdir(parents=True, exist_ok=True)
    tasks = []
    resolved_goal = (goal or template or "autonomous-executor").strip()
    if template:
        tasks = [_normalize_task(task) for task in goal_template_payload(template)["tasks"]]
    queue = {
        "schema_version": SCHEMA_VERSION,
        "packet_type": QUEUE_PACKET_TYPE,
        "goal": resolved_goal,
        "status": "pending",
        "path": str(queue_dir),
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "tasks": tasks,
        "ledger": [],
        "artifacts": [],
    }
    _write_queue(queue_dir, queue)
    return _queue_response("init", queue)


def queue_add_payload(
    path: str,
    task_id: str,
    kind: str,
    project_root: Path,
    *,
    suite: str | None = None,
    depends_on: list[str] | None = None,
    max_attempts: int = 1,
    base: str | None = None,
    head: str | None = None,
    source: str | None = None,
    target: str | None = None,
    out: str | None = None,
) -> dict[str, Any]:
    queue_dir = _safe_queue_dir(path, project_root, must_exist=True)
    queue = _read_queue(queue_dir)
    if any(task["id"] == task_id for task in queue["tasks"]):
        raise AutonomyError(f"queue task already exists: {task_id}.")
    task = _normalize_task(
        {
            "id": task_id,
            "kind": kind,
            "suite": suite,
            "depends_on": depends_on or [],
            "max_attempts": max_attempts,
            "base": base,
            "head": head,
            "source": source,
            "target": target,
            "out": out,
        }
    )
    queue["tasks"].append(task)
    queue["updated_at"] = _now_iso()
    _write_queue(queue_dir, queue)
    return _queue_response("add", queue, task=task)


def queue_status_payload(path: str, project_root: Path) -> dict[str, Any]:
    queue_dir = _safe_queue_dir(path, project_root, must_exist=True)
    queue = _read_queue(queue_dir)
    summary = _queue_summary(queue)
    return _queue_response("status", queue, summary=summary)


def queue_validate_payload(path: str, project_root: Path) -> dict[str, Any]:
    queue_dir = _safe_queue_dir(path, project_root, must_exist=True)
    queue = _read_queue(queue_dir)
    resolver = _resolve_next(queue)
    ok = not resolver["errors"]
    return {"ok": ok, "action": "validate", "queue": queue, "validation": resolver}


def queue_next_payload(path: str, project_root: Path) -> dict[str, Any]:
    queue_dir = _safe_queue_dir(path, project_root, must_exist=True)
    queue = _read_queue(queue_dir)
    resolver = _resolve_next(queue)
    return {"ok": not resolver["errors"], "action": "next", "queue": queue, **resolver}


def classify_failure_payload(kind: str, attempts: int = 0, max_attempts: int = 1) -> dict[str, Any]:
    failure = kind if kind in FAILURE_CLASSES else "unknown"
    retryable = failure == "validation_failed" and attempts < max_attempts
    if failure in NON_RETRYABLE:
        retryable = False
    return {
        "ok": kind in FAILURE_CLASSES,
        "schema_version": SCHEMA_VERSION,
        "packet_type": "agentoffice_autonomy_failure_classification",
        "kind": failure,
        "retryable": retryable,
        "attempts": attempts,
        "max_attempts": max_attempts,
        "policy": "retry_allowed" if retryable else "do_not_retry",
    }


def run_goal_payload(path: str, max_steps: int, project_root: Path, *, retry_failed: bool = False) -> dict[str, Any]:
    queue_dir = _safe_queue_dir(path, project_root, must_exist=True)
    queue = _read_queue(queue_dir)
    _recover_running_tasks(queue)
    steps = []
    for _ in range(max(0, max_steps)):
        resolver = _resolve_next(queue)
        if resolver["errors"]:
            _append_ledger(queue, {"event": "resolver_error", "status": "blocked", "errors": resolver["errors"]})
            break
        ready = resolver["ready_tasks"]
        if retry_failed:
            ready = ready + _retryable_failed_tasks(queue)
        if not ready:
            break
        task = _task_by_id(queue, ready[0]["id"])
        if task["status"] == "passed":
            continue
        result = _execute_task(queue_dir, queue, task, project_root)
        steps.append(result)
        if result["status_after"] in {"failed", "blocked"}:
            break
    queue["updated_at"] = _now_iso()
    queue["status"] = _overall_status(queue)
    _write_queue(queue_dir, queue)
    return {"ok": queue["status"] not in {"failed", "blocked"}, "action": "run-goal", "queue": queue, "steps": steps, "next": _resolve_next(queue)}


def resume_payload(path: str, max_steps: int, project_root: Path, *, retry_failed: bool = False) -> dict[str, Any]:
    payload = run_goal_payload(path, max_steps, project_root, retry_failed=retry_failed)
    payload["action"] = "resume"
    return payload


def goal_template_payload(name: str) -> dict[str, Any]:
    templates = _goal_templates()
    if name not in templates:
        raise AutonomyError(f"unknown goal template: {name}.")
    return {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "packet_type": "agentoffice_autonomy_goal_template",
        "name": name,
        "tasks": [_normalize_task(task) for task in templates[name]],
    }


def goal_report_payload(path: str, out: str, project_root: Path) -> dict[str, Any]:
    queue_dir = _safe_queue_dir(path, project_root, must_exist=True)
    queue = _read_queue(queue_dir)
    out_path = _safe_output_file(out, project_root)
    resolver = _resolve_next(queue)
    markdown = _format_goal_report_markdown(queue, resolver)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists() and out_path.is_symlink():
        raise AutonomyError("goal report output symlink refused.")
    out_path.write_text(markdown, encoding="utf-8")
    return {"ok": True, "action": "goal-report", "out": str(out_path), "queue": queue, "next_action": resolver["next_action"]}


def format_queue(payload: dict[str, Any]) -> str:
    queue = payload["queue"]
    lines = [QUEUE_MARKER, f"action: {payload['action']}", f"goal: {queue['goal']}", f"status: {queue['status']}", f"path: {queue['path']}", "tasks:"]
    for task in queue["tasks"]:
        lines.append(f"  - {task['id']} ({task['kind']}): {task['status']}")
    if "summary" in payload:
        lines.append("summary:")
        for key, value in payload["summary"].items():
            lines.append(f"  {key}: {value}")
    if "validation" in payload:
        lines.append("errors:")
        errors = payload["validation"].get("errors", [])
        lines.extend(f"  - {error}" for error in errors or ["none"])
    return "\n".join(lines)


def format_next(payload: dict[str, Any]) -> str:
    lines = [NEXT_MARKER, f"ok: {_bool_text(bool(payload['ok']))}", f"next_action: {payload['next_action']}"]
    next_task = payload.get("next_task")
    lines.append(f"next_task: {next_task['id'] if next_task else 'none'}")
    lines.append("ready_tasks:")
    lines.extend(f"  - {task['id']}" for task in payload.get("ready_tasks", []) or ["none"])
    lines.append("blocked_tasks:")
    lines.extend(f"  - {task['id']}: {task.get('reason', 'blocked')}" for task in payload.get("blocked_tasks", []) or [{"id": "none", "reason": "none"}])
    lines.append("errors:")
    lines.extend(f"  - {error}" for error in payload.get("errors", []) or ["none"])
    return "\n".join(lines)


def format_runner(payload: dict[str, Any]) -> str:
    lines = [RUNNER_MARKER, f"action: {payload['action']}", f"ok: {_bool_text(bool(payload['ok']))}", f"queue_status: {payload['queue']['status']}", "steps:"]
    lines.extend(f"  - {step['task_id']}: {step['status_before']} -> {step['status_after']}" for step in payload["steps"] or [{"task_id": "none", "status_before": "none", "status_after": "none"}])
    lines.append(f"next_action: {payload['next']['next_action']}")
    return "\n".join(lines)


def format_classification(payload: dict[str, Any]) -> str:
    return "\n".join([CLASSIFY_MARKER, f"kind: {payload['kind']}", f"retryable: {_bool_text(bool(payload['retryable']))}", f"policy: {payload['policy']}"])


def format_goal_template(payload: dict[str, Any]) -> str:
    lines = [TEMPLATE_MARKER, f"name: {payload['name']}", "tasks:"]
    lines.extend(f"  - {task['id']} ({task['kind']})" for task in payload["tasks"])
    return "\n".join(lines)


def format_goal_report(payload: dict[str, Any]) -> str:
    return "\n".join([REPORT_MARKER, f"ok: {_bool_text(bool(payload['ok']))}", f"out: {payload['out']}", f"next_action: {payload['next_action']}"])


def _normalize_task(raw: dict[str, Any]) -> dict[str, Any]:
    task_id = _safe_id(str(raw.get("id") or ""), "task id")
    kind = str(raw.get("kind") or "").strip()
    if kind not in TASK_KINDS:
        raise AutonomyError(f"unknown queue task kind: {kind}.")
    depends = raw.get("depends_on") or raw.get("depends") or []
    if isinstance(depends, str):
        depends = [depends]
    if not isinstance(depends, list) or not all(isinstance(item, str) and item for item in depends):
        raise AutonomyError("task depends_on must be a list of task ids.")
    status = str(raw.get("status") or "pending")
    if status not in TASK_STATUSES:
        raise AutonomyError(f"invalid task status: {status}.")
    max_attempts = int(raw.get("max_attempts") or 1)
    task = {
        "id": task_id,
        "kind": kind,
        "status": status,
        "depends_on": depends,
        "attempts": int(raw.get("attempts") or 0),
        "max_attempts": max(1, max_attempts),
        "created_at": raw.get("created_at"),
        "updated_at": raw.get("updated_at"),
        "artifacts": list(raw.get("artifacts") or []),
        "last_error": raw.get("last_error"),
    }
    for key in ("suite", "base", "head", "source", "target", "out"):
        if raw.get(key) is not None:
            task[key] = raw.get(key)
    return task


def _resolve_next(queue: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    tasks = queue["tasks"]
    by_id = {task["id"]: task for task in tasks}
    if len(by_id) != len(tasks):
        errors.append("invalid_queue:duplicate_task_id")
    for task in tasks:
        for dep in task["depends_on"]:
            if dep not in by_id:
                errors.append(f"missing_dependency:{task['id']}:{dep}")
    cycle_nodes = _cycle_nodes(tasks)
    for node in cycle_nodes:
        errors.append(f"dependency_cycle:{node}")
    ready = []
    blocked = []
    for task in tasks:
        if task["status"] == "pending":
            deps = [by_id.get(dep) for dep in task["depends_on"]]
            if any(dep is None for dep in deps):
                blocked.append({"id": task["id"], "reason": "missing_dependency"})
            elif any(dep["status"] == "failed" for dep in deps if dep):
                task["status"] = "blocked"
                task["last_error"] = {"class": "dependency_failed", "message": "upstream dependency failed"}
                blocked.append({"id": task["id"], "reason": "dependency_failed"})
            elif any(dep["status"] in {"pending", "running", "blocked"} for dep in deps if dep):
                blocked.append({"id": task["id"], "reason": "waiting_for_dependency"})
            else:
                ready.append(task)
        elif task["status"] == "blocked":
            error = task.get("last_error") if isinstance(task.get("last_error"), dict) else {}
            if error.get("class") == "manual_block":
                blocked.append({"id": task["id"], "reason": "manual_block"})
                continue
            deps = [by_id.get(dep) for dep in task["depends_on"]]
            if deps and all(dep and dep["status"] == "passed" for dep in deps):
                task["status"] = "pending"
                task["last_error"] = None
                ready.append(task)
            else:
                blocked.append({"id": task["id"], "reason": "blocked"})
    ready = sorted(ready, key=lambda item: item["id"])
    next_task = ready[0] if ready and not errors else None
    if errors:
        next_action = "fix_queue"
    elif next_task:
        next_action = f"run:{next_task['id']}"
    elif blocked:
        next_action = "blocked"
    else:
        next_action = "complete"
    return {"next_task": next_task, "blocked_tasks": blocked, "ready_tasks": ready, "errors": errors, "warnings": warnings, "next_action": next_action}


def _execute_task(queue_dir: Path, queue: dict[str, Any], task: dict[str, Any], project_root: Path) -> dict[str, Any]:
    before = task["status"]
    task["status"] = "running"
    task["attempts"] += 1
    started = _now_iso()
    record = {"task_id": task["id"], "kind": task["kind"], "status_before": before, "started_at": started, "artifacts": []}
    try:
        artifacts = _run_task_action(queue_dir, queue, task, project_root)
        if task["kind"] == "manual":
            task["status"] = "blocked"
            task["last_error"] = {"class": "manual_block", "message": "manual task requires operator action"}
            record.update({"status_after": "blocked", "exit_code": 2, "failure_class": "manual_block", "artifacts": artifacts})
        else:
            task["status"] = "passed"
            task["last_error"] = None
            record.update({"status_after": "passed", "exit_code": 0, "failure_class": None, "artifacts": artifacts})
    except AutonomyError as exc:
        failure = _classify_exception(str(exc))
        retry = classify_failure_payload(failure, task["attempts"], task["max_attempts"])["retryable"]
        task["status"] = "pending" if retry else "failed"
        task["last_error"] = {"class": failure, "message": str(exc)}
        record.update({"status_after": task["status"], "exit_code": 2, "failure_class": failure, "artifacts": []})
    record["ended_at"] = _now_iso()
    task["updated_at"] = record["ended_at"]
    task["artifacts"].extend(record["artifacts"])
    queue["artifacts"].extend(record["artifacts"])
    _append_ledger(queue, record)
    return record


def _run_task_action(queue_dir: Path, queue: dict[str, Any], task: dict[str, Any], project_root: Path) -> list[dict[str, Any]]:
    artifacts_dir = queue_dir / "artifacts" / task["id"]
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    kind = task["kind"]
    if kind in {"checkpoint", "noop"}:
        path = artifacts_dir / "result.json"
        path.write_text(json.dumps({"ok": True, "kind": kind, "task_id": task["id"]}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return [_artifact(path, kind)]
    if kind == "manual":
        path = artifacts_dir / "manual.json"
        path.write_text(json.dumps({"ok": False, "next_action": "operator_action_required"}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return [_artifact(path, kind)]
    if kind == "validate-suite":
        suite = str(task.get("suite") or "minimal")
        ledger_dir = queue_dir / "validation-ledgers" / task["id"]
        if not (ledger_dir / "ledger.json").exists():
            autonomy_init_payload(str(ledger_dir), "autonomous-delivery", project_root)
        payload = autonomy_validate_payload(str(ledger_dir), suite, project_root)
        if not payload["ok"]:
            raise AutonomyError("validation_failed")
        artifacts = [_artifact(ledger_dir / "ledger.json", "validation_ledger")]
        for record in payload["validation"]["commands"]:
            artifacts.append(_artifact(Path(record["stdout_path"]), "validation_stdout"))
            artifacts.append(_artifact(Path(record["stderr_path"]), "validation_stderr"))
        return artifacts
    if kind == "review-packet":
        out = task.get("out") or str(artifacts_dir / "review-packet.md")
        payload = autonomy_review_packet_payload(str(task.get("base") or "HEAD~1"), str(task.get("head") or "HEAD"), str(out), project_root)
        return [_artifact(Path(payload["out"]), "review-packet")]
    if kind == "merge-packet":
        payload = autonomy_merge_packet_payload(str(task.get("source") or "HEAD"), str(task.get("target") or "HEAD"), project_root)
        out = artifacts_dir / "merge-packet.json"
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        return [_artifact(out, "merge-packet")]
    if kind == "release-state":
        out = artifacts_dir / "release-state.json"
        out.write_text(json.dumps(release_state_payload(), indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        return [_artifact(out, "release-state")]
    if kind == "github-release-plan":
        out = artifacts_dir / "github-release-plan.json"
        out.write_text(json.dumps(github_release_plan_payload(), indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        return [_artifact(out, "github-release-plan")]
    if kind == "final-delivery":
        out = artifacts_dir / "final-delivery.json"
        out.write_text(json.dumps(build_final_delivery_packet(project_root), indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        return [_artifact(out, "final-delivery")]
    raise AutonomyError(f"unknown queue task kind: {kind}.")


def _goal_templates() -> dict[str, list[dict[str, Any]]]:
    return {
        "release-cycle": [
            {"id": "release-state", "kind": "release-state"},
            {"id": "github-release-plan", "kind": "github-release-plan", "depends_on": ["release-state"]},
            {"id": "verify-release-archive", "kind": "manual", "depends_on": ["github-release-plan"]},
            {"id": "review-packet", "kind": "review-packet", "depends_on": ["verify-release-archive"]},
            {"id": "merge-packet", "kind": "merge-packet", "depends_on": ["review-packet"]},
        ],
        "feature-merge": [
            {"id": "checkpoint", "kind": "checkpoint"},
            {"id": "validate-minimal", "kind": "validate-suite", "suite": "minimal", "depends_on": ["checkpoint"]},
            {"id": "validate-full", "kind": "validate-suite", "suite": "full", "depends_on": ["validate-minimal"]},
            {"id": "review-packet", "kind": "review-packet", "depends_on": ["validate-full"]},
            {"id": "merge-packet", "kind": "merge-packet", "depends_on": ["review-packet"]},
        ],
        "longrun-development": [
            {"id": "checkpoint", "kind": "checkpoint"},
            {"id": "validate-minimal", "kind": "validate-suite", "suite": "minimal", "depends_on": ["checkpoint"]},
            {"id": "review-packet", "kind": "review-packet", "depends_on": ["validate-minimal"]},
            {"id": "merge-packet", "kind": "merge-packet", "depends_on": ["review-packet"]},
            {"id": "final-report", "kind": "manual", "depends_on": ["merge-packet"]},
        ],
    }


def _format_goal_report_markdown(queue: dict[str, Any], resolver: dict[str, Any]) -> str:
    lines = ["# AgentOffice Autonomy Goal Report", "", f"Marker: {REPORT_MARKER}", "", "## Goal", "", f"- goal: `{queue['goal']}`", f"- queue path: `{queue['path']}`", f"- status: `{queue['status']}`", "", "## Task Table", "", "| id | kind | status | attempts | failure |", "| --- | --- | --- | --- | --- |"]
    for task in queue["tasks"]:
        failure = (task.get("last_error") or {}).get("class") if isinstance(task.get("last_error"), dict) else ""
        lines.append(f"| {task['id']} | {task['kind']} | {task['status']} | {task['attempts']}/{task['max_attempts']} | {failure or ''} |")
    lines.extend(["", "## Dependency Graph Summary", "", f"- next_action: `{resolver['next_action']}`", f"- ready_tasks: `{', '.join(task['id'] for task in resolver['ready_tasks']) or 'none'}`", f"- blocked_tasks: `{', '.join(task['id'] for task in resolver['blocked_tasks']) or 'none'}`", "", "## Artifacts", ""])
    if queue["artifacts"]:
        lines.extend(f"- `{artifact['path']}` ({artifact['type']})" for artifact in queue["artifacts"])
    else:
        lines.append("- none")
    lines.extend(["", "## Validation Outputs", "", "Validation output artifacts are recorded per validate-suite task.", "", "## Merge/Readback Guidance", "", "Use review-packet and merge-packet artifacts for review. Do not merge without explicit operator authorization.", ""])
    return "\n".join(lines)


def _safe_queue_dir(path: str, project_root: Path, *, must_exist: bool) -> Path:
    if not str(path).strip():
        raise AutonomyError("queue path is required.")
    candidate = Path(path)
    if any(part in {"..", ""} for part in candidate.parts) or any(part == ".env" for part in candidate.parts):
        raise AutonomyError("unsafe_path: queue path contains refused traversal or .env component.")
    if not candidate.is_absolute():
        candidate = project_root / candidate
    _reject_symlink_components(candidate if candidate.exists() else candidate.parent)
    candidate = candidate.resolve(strict=False)
    root = project_root.resolve(strict=False)
    tmp = Path(os.getenv("TMPDIR", "/tmp")).resolve(strict=False)
    if not _is_relative_to(candidate, root) and not _is_relative_to(candidate, tmp):
        raise AutonomyError("unsafe_path: queue path must stay under project root or temp directory.")
    if must_exist and not candidate.exists():
        raise AutonomyError("invalid_queue: queue path is missing.")
    if candidate.exists() and not candidate.is_dir():
        raise AutonomyError("invalid_queue: queue path is not a directory.")
    return candidate


def _safe_output_file(path: str, project_root: Path) -> Path:
    candidate = Path(path)
    if any(part in {"..", ""} for part in candidate.parts) or any(part == ".env" for part in candidate.parts):
        raise AutonomyError("unsafe_path: output path contains refused traversal or .env component.")
    if not candidate.is_absolute():
        candidate = project_root / candidate
    _reject_symlink_components(candidate if candidate.exists() else candidate.parent)
    candidate = candidate.resolve(strict=False)
    root = project_root.resolve(strict=False)
    tmp = Path(os.getenv("TMPDIR", "/tmp")).resolve(strict=False)
    if not _is_relative_to(candidate, root) and not _is_relative_to(candidate, tmp):
        raise AutonomyError("unsafe_path: output path must stay under project root or temp directory.")
    if candidate.exists() and candidate.is_dir():
        raise AutonomyError("unsafe_path: output path is a directory.")
    return candidate


def _queue_file(queue_dir: Path) -> Path:
    return queue_dir / "queue.json"


def _read_queue(queue_dir: Path) -> dict[str, Any]:
    path = _queue_file(queue_dir)
    if path.is_symlink():
        raise AutonomyError("symlink_refused: queue file symlink refused.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AutonomyError("invalid_queue: queue file is missing.") from exc
    except json.JSONDecodeError as exc:
        raise AutonomyError("malformed_json: queue file is malformed JSON.") from exc
    except OSError as exc:
        raise AutonomyError("invalid_queue: queue file is unreadable.") from exc
    if not isinstance(data, dict) or data.get("packet_type") != QUEUE_PACKET_TYPE:
        raise AutonomyError("invalid_queue: invalid queue packet.")
    if not isinstance(data.get("tasks"), list):
        raise AutonomyError("invalid_queue: tasks must be a list.")
    data["tasks"] = [_normalize_task(task) for task in data["tasks"]]
    data.setdefault("ledger", [])
    data.setdefault("artifacts", [])
    data.setdefault("status", "pending")
    return data


def _write_queue(queue_dir: Path, queue: dict[str, Any]) -> None:
    path = _queue_file(queue_dir)
    if path.exists() and path.is_symlink():
        raise AutonomyError("symlink_refused: queue file symlink refused.")
    tmp = queue_dir / "queue.json.tmp"
    tmp.write_text(json.dumps(queue, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _queue_response(action: str, queue: dict[str, Any], **extra: Any) -> dict[str, Any]:
    payload = {"ok": True, "action": action, "queue": queue}
    payload.update(extra)
    return payload


def _queue_summary(queue: dict[str, Any]) -> dict[str, int]:
    return {status: sum(1 for task in queue["tasks"] if task["status"] == status) for status in sorted(TASK_STATUSES)}


def _task_by_id(queue: dict[str, Any], task_id: str) -> dict[str, Any]:
    for task in queue["tasks"]:
        if task["id"] == task_id:
            return task
    raise AutonomyError(f"missing_dependency: task not found: {task_id}.")


def _retryable_failed_tasks(queue: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for task in queue["tasks"]:
        error = task.get("last_error") or {}
        failure = error.get("class") if isinstance(error, dict) else "unknown"
        if task["status"] == "failed" and classify_failure_payload(failure, task["attempts"], task["max_attempts"])["retryable"]:
            task["status"] = "pending"
            result.append(task)
    return result


def _recover_running_tasks(queue: dict[str, Any]) -> None:
    for task in queue["tasks"]:
        if task["status"] == "running":
            task["status"] = "failed"
            task["last_error"] = {"class": "command_failed", "message": "interrupted running task recovered as failed"}


def _overall_status(queue: dict[str, Any]) -> str:
    statuses = {task["status"] for task in queue["tasks"]}
    if "failed" in statuses:
        return "failed"
    if "blocked" in statuses:
        return "blocked"
    if statuses and statuses <= {"passed", "skipped"}:
        return "passed"
    if "running" in statuses:
        return "running"
    return "pending"


def _append_ledger(queue: dict[str, Any], record: dict[str, Any]) -> None:
    queue.setdefault("ledger", []).append(record)


def _artifact(path: Path, artifact_type: str) -> dict[str, Any]:
    return {"type": artifact_type, "path": str(path)}


def _classify_exception(message: str) -> str:
    for failure in FAILURE_CLASSES:
        if failure in message:
            return failure
    return "command_failed"


def _cycle_nodes(tasks: list[dict[str, Any]]) -> list[str]:
    graph = {task["id"]: list(task["depends_on"]) for task in tasks}
    visiting: set[str] = set()
    visited: set[str] = set()
    cycle: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            cycle.add(node)
            return
        if node in visited:
            return
        visiting.add(node)
        for dep in graph.get(node, []):
            if dep in graph:
                visit(dep)
        visiting.remove(node)
        visited.add(node)

    for node in sorted(graph):
        visit(node)
    return sorted(cycle)


def _safe_id(value: str, label: str) -> str:
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
    if not value or any(ch not in allowed for ch in value) or value in {".", ".."}:
        raise AutonomyError(f"invalid_queue: invalid {label}.")
    return value


def _reject_symlink_components(path: Path) -> None:
    current = path
    candidates = []
    while current != current.parent:
        candidates.append(current)
        current = current.parent
    for candidate in candidates:
        if candidate.exists() and candidate.is_symlink():
            raise AutonomyError("symlink_refused: path symlink refused.")


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _bool_text(value: bool) -> str:
    return "true" if value else "false"
