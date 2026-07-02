from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
TASK_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
TASK_STATUSES = {"pending", "completed", "failed", "blocked"}
JOB_STATES = {"created", "running", "completed", "failed", "cancelled"}
WORKER_RESULT_STATUSES = {"completed", "failed", "skipped"}
WORKER_REFUSAL_REASON = "external worker prototype is contract-only; execution refused"
TERMINAL_WORKSPACE_STATUSES = {"completed", "failed", "blocked"}
WORKER_ADAPTERS = {
    "local-static": {
        "name": "local-static",
        "kind": "local_static_worker_adapter",
        "dry_run_supported": True,
        "execute_local_supported": True,
        "external_execution_enabled": False,
        "provider_calls": False,
        "model_calls": False,
        "shell_calls": False,
        "browser_calls": False,
        "reason": "deterministic local/static adapter",
    },
    "noop": {
        "name": "noop",
        "kind": "local_static_worker_adapter",
        "dry_run_supported": True,
        "execute_local_supported": True,
        "external_execution_enabled": False,
        "provider_calls": False,
        "model_calls": False,
        "shell_calls": False,
        "browser_calls": False,
        "reason": "deterministic noop/local adapter",
    },
    "external-prototype": {
        "name": "external-prototype",
        "kind": "external_worker_adapter_prototype",
        "dry_run_supported": True,
        "execute_local_supported": False,
        "external_execution_enabled": False,
        "provider_calls": False,
        "model_calls": False,
        "shell_calls": False,
        "browser_calls": False,
        "reason": WORKER_REFUSAL_REASON,
    },
}
ALLOWED_ADAPTERS = set(WORKER_ADAPTERS)
EXPLICIT_RUNTIME_BOUNDARY = [
    "local/static/deterministic runtime only",
    "not real multi-agent runtime",
]
SAFETY_BOUNDARIES = {
    "mode": "local_static",
    "provider_calls": [],
    "model_calls": [],
    "adapter_external_behavior": False,
    "dotenv_read": False,
    "env_vars_printed": False,
    "daemon": False,
    "concurrency": False,
    "database": False,
    "vector_store": False,
}
WORKER_SAFETY_BOUNDARIES = {
    "external_execution_default": "refused",
    "provider_calls": False,
    "model_calls": False,
    "browser_calls": False,
    "shell_calls": False,
    "real_worker_execution": "not_implemented",
    "dotenv_read": False,
    "env_vars_printed": False,
}


class RuntimeFoundationError(ValueError):
    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


def runtime_init_payload(*, workspace: str, goal: str, project_root: Path) -> dict[str, Any]:
    workspace_root = _workspace_path(workspace, project_root)
    if workspace_root.exists() and workspace_root.is_symlink():
        raise RuntimeFoundationError("runtime_workspace_symlink_refused", f"Refusing workspace symlink: {workspace}")
    if workspace_root.exists() and not workspace_root.is_dir():
        raise RuntimeFoundationError("runtime_workspace_not_directory", f"Workspace path is not a directory: {workspace}")
    workspace_root.mkdir(parents=True, exist_ok=True)

    paths = _workspace_files(workspace_root, project_root)
    _touch_jsonl(paths["memory"])
    _touch_jsonl(paths["events"])
    if not paths["task_graph"].exists():
        _write_json(paths["task_graph"], _empty_task_graph(workspace_root, project_root))
    manifest = _manifest_payload(workspace_root, goal, "initialized", paths, project_root)
    _write_json(paths["manifest"], manifest)
    return {
        "ok": True,
        "command": "runtime init",
        "schema_version": SCHEMA_VERSION,
        "workspace": _project_relative(workspace_root, project_root),
        "goal": goal,
        "status": manifest["status"],
        "manifest_path": _project_relative(paths["manifest"], project_root),
        "task_graph_path": _project_relative(paths["task_graph"], project_root),
        "memory_path": _project_relative(paths["memory"], project_root),
        "events_path": _project_relative(paths["events"], project_root),
        "external_behavior": dict(SAFETY_BOUNDARIES),
    }


def runtime_plan_payload(*, workspace: str, tasks: list[str], depends: list[str], project_root: Path) -> dict[str, Any]:
    workspace_root = _existing_workspace_path(workspace, project_root)
    paths = _workspace_files(workspace_root, project_root)
    manifest = _load_manifest(paths["manifest"])
    parsed_tasks = [_parse_task_spec(spec) for spec in tasks]
    if not parsed_tasks:
        raise RuntimeFoundationError("runtime_plan_tasks_required", "runtime plan requires at least one --task.")
    task_ids = [task["id"] for task in parsed_tasks]
    duplicates = sorted({task_id for task_id in task_ids if task_ids.count(task_id) > 1})
    if duplicates:
        raise RuntimeFoundationError("runtime_plan_duplicate_task_id", f"Duplicate task id: {duplicates[0]}")
    by_id = {task["id"]: task for task in parsed_tasks}
    for spec in depends:
        task_id, dependency_id = _parse_dependency_spec(spec)
        if task_id not in by_id:
            raise RuntimeFoundationError("runtime_plan_missing_dependency_task", f"Dependency references missing task: {task_id}")
        if dependency_id not in by_id:
            raise RuntimeFoundationError("runtime_plan_missing_dependency", f"Dependency references missing task: {dependency_id}")
        by_id[task_id]["dependencies"].append(dependency_id)
    for task in parsed_tasks:
        task["dependencies"] = sorted(set(task["dependencies"]))
    topological_order = _topological_order(parsed_tasks)
    graph = {
        "kind": "runtime_task_graph",
        "schema_version": SCHEMA_VERSION,
        "workspace": _project_relative(workspace_root, project_root),
        "tasks": parsed_tasks,
        "topological_order": topological_order,
    }
    _write_json(paths["task_graph"], graph)
    manifest["status"] = "planned"
    _write_json(paths["manifest"], manifest)
    return {
        "ok": True,
        "command": "runtime plan",
        "schema_version": SCHEMA_VERSION,
        "workspace": _project_relative(workspace_root, project_root),
        "status": manifest["status"],
        "task_count": len(parsed_tasks),
        "tasks": parsed_tasks,
        "topological_order": topological_order,
        "external_behavior": dict(SAFETY_BOUNDARIES),
    }


def runtime_run_payload(
    *,
    workspace: str,
    adapter: str,
    dry_run: bool,
    execute_local: bool,
    reset: bool,
    project_root: Path,
) -> dict[str, Any]:
    if adapter not in ALLOWED_ADAPTERS:
        raise RuntimeFoundationError("runtime_unsupported_adapter", f"Unsupported runtime adapter: {adapter}")
    if adapter == "external-prototype" and execute_local:
        raise RuntimeFoundationError("runtime_external_prototype_execute_refused", "external-prototype is a contract stub and cannot execute local or external work.")
    if dry_run == execute_local:
        raise RuntimeFoundationError("runtime_run_mode_required", "runtime run requires exactly one of --dry-run or --execute-local.")
    if dry_run and reset:
        raise RuntimeFoundationError("runtime_reset_requires_execute_local", "runtime run --reset requires --execute-local.")
    workspace_root = _existing_workspace_path(workspace, project_root)
    paths = _workspace_files(workspace_root, project_root)
    manifest = _load_manifest(paths["manifest"])
    graph = _load_task_graph(paths["task_graph"])
    tasks = _graph_tasks(graph)
    topological_order = _topological_order(tasks)
    task_by_id = {task["id"]: task for task in tasks}
    job = _load_job(paths["job"], required=False)
    if execute_local and job:
        _ensure_job_allows_run(job)
        job = _write_job_state(paths=paths, workspace_root=workspace_root, project_root=project_root, manifest=manifest, tasks=tasks, existing=job, state="running")
    if reset:
        for task in tasks:
            task["status"] = "pending"
            task.pop("result", None)
            task.pop("blocked_by", None)

    if dry_run:
        return {
            "ok": True,
            "command": "runtime run",
            "schema_version": SCHEMA_VERSION,
            "workspace": _project_relative(workspace_root, project_root),
            "adapter": adapter,
            "dry_run": True,
            "execute_local": False,
            "reset": False,
            "topological_order": topological_order,
            "would_execute_task_ids": _would_execute(tasks, topological_order),
            "executed_task_ids": [],
            "skipped_completed_task_ids": _ids_with_status(tasks, "completed"),
            "blocked_task_ids": _ids_with_status(tasks, "blocked"),
            "failed_task_ids": _ids_with_status(tasks, "failed"),
            "task_counts": _task_counts(tasks),
            "memory_entry_count": _jsonl_count(paths["memory"]),
            "job": _job_readback(job) if job else None,
            "worker_adapter": _worker_adapter_descriptor(adapter),
            "external_behavior": dict(SAFETY_BOUNDARIES),
        }

    executed: list[str] = []
    skipped_completed: list[str] = []
    newly_blocked: list[str] = []
    newly_failed: list[str] = []
    for task_id in topological_order:
        task = task_by_id[task_id]
        status = str(task.get("status", "pending"))
        if status == "completed":
            skipped_completed.append(task_id)
            continue
        if status == "failed":
            newly_failed.append(task_id)
            continue
        if status == "blocked":
            newly_blocked.append(task_id)
            continue
        blockers = [dependency for dependency in task["dependencies"] if task_by_id[dependency].get("status") in {"failed", "blocked"}]
        if blockers:
            task["status"] = "blocked"
            task["blocked_by"] = blockers
            newly_blocked.append(task_id)
            _append_event(paths["events"], "task_blocked", task, adapter, len(executed), {"blocked_by": blockers})
            continue
        incomplete = [dependency for dependency in task["dependencies"] if task_by_id[dependency].get("status") != "completed"]
        if incomplete:
            continue
        result = _static_worker_result(task, adapter)
        task["status"] = result["status"]
        task["result"] = result
        executed.append(task_id)
        if result["status"] == "failed":
            newly_failed.append(task_id)
        _append_memory(paths["memory"], task, adapter, len(executed), result)
        _append_event(paths["events"], "task_executed", task, adapter, len(executed), {"result": result})

    graph["tasks"] = tasks
    graph["topological_order"] = topological_order
    _write_json(paths["task_graph"], graph)
    manifest["status"] = _workspace_status(tasks)
    _write_json(paths["manifest"], manifest)
    if job:
        if manifest["status"] == "completed":
            job = _write_job_state(paths=paths, workspace_root=workspace_root, project_root=project_root, manifest=manifest, tasks=tasks, existing=job, state="completed", failure_reason=None)
        elif manifest["status"] in {"failed", "blocked"}:
            job = _write_job_state(paths=paths, workspace_root=workspace_root, project_root=project_root, manifest=manifest, tasks=tasks, existing=job, state="failed", failure_reason=f"workspace_status={manifest['status']}")
        else:
            job = _write_job_state(paths=paths, workspace_root=workspace_root, project_root=project_root, manifest=manifest, tasks=tasks, existing=job, state="running")
    return {
        "ok": True,
        "command": "runtime run",
        "schema_version": SCHEMA_VERSION,
        "workspace": _project_relative(workspace_root, project_root),
        "adapter": adapter,
        "dry_run": False,
        "execute_local": True,
        "reset": reset,
        "topological_order": topological_order,
        "would_execute_task_ids": [],
        "executed_task_ids": executed,
        "skipped_completed_task_ids": skipped_completed,
        "blocked_task_ids": _ids_with_status(tasks, "blocked"),
        "failed_task_ids": _ids_with_status(tasks, "failed"),
        "task_counts": _task_counts(tasks),
        "memory_entry_count": _jsonl_count(paths["memory"]),
        "job": _job_readback(job) if job else None,
        "worker_adapter": _worker_adapter_descriptor(adapter),
        "external_behavior": dict(SAFETY_BOUNDARIES),
    }


def runtime_status_payload(*, workspace: str, project_root: Path) -> dict[str, Any]:
    workspace_root = _existing_workspace_path(workspace, project_root)
    paths = _workspace_files(workspace_root, project_root)
    manifest = _load_manifest(paths["manifest"])
    graph = _load_task_graph(paths["task_graph"], allow_empty=True)
    tasks = _graph_tasks(graph, allow_empty=True)
    latest_event = _latest_jsonl(paths["events"])
    return {
        "ok": True,
        "command": "runtime status",
        "schema_version": SCHEMA_VERSION,
        "workspace": _project_relative(workspace_root, project_root),
        "workspace_status": manifest.get("status", "unknown"),
        "goal": manifest.get("goal", ""),
        "task_counts": _task_counts(tasks),
        "completed_task_ids": _ids_with_status(tasks, "completed"),
        "pending_task_ids": _ids_with_status(tasks, "pending"),
        "failed_task_ids": _ids_with_status(tasks, "failed"),
        "blocked_task_ids": _ids_with_status(tasks, "blocked"),
        "memory_entry_count": _jsonl_count(paths["memory"]),
        "latest_event_summary": _event_summary(latest_event),
        "job": _job_readback(_load_job(paths["job"], required=False)),
        "external_behavior": dict(SAFETY_BOUNDARIES),
    }


def runtime_packet_payload(*, workspace: str, project_root: Path) -> dict[str, Any]:
    snapshot = _workspace_snapshot(workspace, project_root, allow_empty=True)
    tasks = snapshot["tasks"]
    manifest = snapshot["manifest"]
    graph = snapshot["graph"]
    replay = _replay_contract(snapshot)
    return {
        "ok": True,
        "command": "runtime packet",
        "kind": "runtime_lifecycle_packet",
        "schema_version": SCHEMA_VERSION,
        "workspace": snapshot["workspace"],
        "lifecycle": {
            "workspace_status": manifest.get("status", "unknown"),
            "goal": manifest.get("goal", ""),
            "terminal": manifest.get("status") in TERMINAL_WORKSPACE_STATUSES,
            "task_counts": _task_counts(tasks),
            "completed_task_ids": _ids_with_status(tasks, "completed"),
            "pending_task_ids": _ids_with_status(tasks, "pending"),
            "failed_task_ids": _ids_with_status(tasks, "failed"),
            "blocked_task_ids": _ids_with_status(tasks, "blocked"),
        },
        "files": _runtime_file_statuses(snapshot["paths"], project_root),
        "task_graph": {
            "task_count": len(tasks),
            "topological_order": list(graph.get("topological_order", [])),
            "tasks": [_task_readback(task) for task in tasks],
        },
        "memory": {
            "entry_count": len(snapshot["memory_entries"]),
            "task_memory_ids": [entry.get("task_id") for entry in snapshot["memory_entries"] if entry.get("entry_type") == "task_memory"],
        },
        "events": {
            "entry_count": len(snapshot["event_entries"]),
            "latest_event_summary": _event_summary(snapshot["event_entries"][-1] if snapshot["event_entries"] else None),
        },
        "readback_contract": {
            "replay_valid": replay["replay_valid"],
            "graph_order_valid": replay["graph_order_valid"],
            "workspace_status_matches_tasks": replay["workspace_status_matches_tasks"],
            "mismatches": replay["mismatches"],
        },
        "external_behavior": dict(SAFETY_BOUNDARIES),
    }


def runtime_replay_payload(*, workspace: str, project_root: Path) -> dict[str, Any]:
    snapshot = _workspace_snapshot(workspace, project_root, allow_empty=True)
    replay = _replay_contract(snapshot)
    return {
        "ok": True,
        "command": "runtime replay",
        "kind": "runtime_replay_readback",
        "schema_version": SCHEMA_VERSION,
        "workspace": snapshot["workspace"],
        **replay,
        "external_behavior": dict(SAFETY_BOUNDARIES),
    }


def runtime_evidence_payload(*, workspace: str, out: str, evidence_format: str, project_root: Path) -> dict[str, Any]:
    if evidence_format not in {"json", "text"}:
        raise RuntimeFoundationError("runtime_evidence_format_invalid", f"Unsupported evidence format: {evidence_format}")
    output_path = _safe_output_path(out, project_root, "runtime_evidence")
    packet = runtime_packet_payload(workspace=workspace, project_root=project_root)
    replay = runtime_replay_payload(workspace=workspace, project_root=project_root)
    snapshot = _workspace_snapshot(workspace, project_root, allow_empty=True)
    evidence = {
        "ok": True,
        "command": "runtime evidence",
        "kind": "runtime_workspace_evidence",
        "schema_version": SCHEMA_VERSION,
        "workspace": snapshot["workspace"],
        "evidence_path": _project_relative(output_path, project_root),
        "evidence_format": evidence_format,
        "packet": packet,
        "replay": replay,
        "file_digests": _runtime_file_digests(snapshot["paths"], project_root),
        "safety_boundaries": dict(SAFETY_BOUNDARIES),
        "written": True,
    }
    if evidence_format == "json":
        _write_json(output_path, evidence)
    else:
        _write_text(output_path, _format_evidence_text(evidence))
    return evidence


def runtime_close_payload(*, workspace: str, out: str | None, project_root: Path) -> dict[str, Any]:
    packet = runtime_packet_payload(workspace=workspace, project_root=project_root)
    replay = runtime_replay_payload(workspace=workspace, project_root=project_root)
    workspace_status = packet["lifecycle"]["workspace_status"]
    terminal = workspace_status in TERMINAL_WORKSPACE_STATUSES
    blocking_reasons: list[str] = []
    if not replay["replay_valid"]:
        blocking_reasons.append("replay_readback_invalid")
    if not terminal:
        blocking_reasons.append("workspace_not_terminal")
    closure_packet_valid = replay["replay_valid"] and terminal
    closure_ready = closure_packet_valid and workspace_status == "completed"
    payload = {
        "ok": True,
        "command": "runtime close",
        "kind": "runtime_closure_packet",
        "schema_version": SCHEMA_VERSION,
        "workspace": packet["workspace"],
        "workspace_status": workspace_status,
        "closure_packet_valid": closure_packet_valid,
        "closure_ready": closure_ready,
        "readiness": "ready" if closure_ready else "not_ready",
        "blocking_reasons": blocking_reasons,
        "packet": packet,
        "replay": replay,
        "output_path": None,
        "written": False,
        "external_behavior": dict(SAFETY_BOUNDARIES),
    }
    if out:
        output_path = _safe_output_path(out, project_root, "runtime_close")
        payload["output_path"] = _project_relative(output_path, project_root)
        payload["written"] = True
        _write_json(output_path, payload)
    return payload


def runtime_governance_payload(*, workspace: str, closure_packet: str, evidence_out: str, evidence_format: str, project_root: Path) -> dict[str, Any]:
    if evidence_format not in {"json", "text"}:
        raise RuntimeFoundationError("runtime_governance_format_invalid", f"Unsupported governance evidence format: {evidence_format}")
    output_path = _safe_output_path(evidence_out, project_root, "runtime_governance")
    closure_path = _safe_input_path(closure_packet, project_root, "runtime_governance_closure_packet")
    closure = _load_input_json(closure_path, "runtime_governance_closure_packet")
    status = runtime_status_payload(workspace=workspace, project_root=project_root)
    replay = runtime_replay_payload(workspace=workspace, project_root=project_root)
    closure_lifecycle = closure.get("packet", {}).get("lifecycle", {}) if isinstance(closure.get("packet"), dict) else {}
    closure_replay = closure.get("replay", {}) if isinstance(closure.get("replay"), dict) else {}
    workspace_identity_match = closure.get("workspace") == status["workspace"] == replay["workspace"]
    task_counts_match = closure_lifecycle.get("task_counts") == status["task_counts"]
    replay_valid = bool(replay.get("replay_valid")) and bool(closure_replay.get("replay_valid"))
    closure_packet_valid = bool(closure.get("closure_packet_valid"))
    closure_ready = bool(closure.get("closure_ready"))
    blocking_reasons: list[str] = []
    if closure.get("kind") != "runtime_closure_packet":
        blocking_reasons.append("closure_packet_kind_invalid")
    if not workspace_identity_match:
        blocking_reasons.append("workspace_identity_mismatch")
    if not task_counts_match:
        blocking_reasons.append("task_counts_mismatch")
    if not replay_valid:
        blocking_reasons.append("replay_readback_invalid")
    if not closure_packet_valid:
        blocking_reasons.append("closure_packet_invalid")
    if not closure_ready:
        blocking_reasons.append("closure_not_ready")
    runtime_governance_ready = not blocking_reasons
    evidence = {
        "ok": True,
        "command": "runtime governance",
        "kind": "runtime_governance_evidence",
        "schema_version": SCHEMA_VERSION,
        "workspace": status["workspace"],
        "goal": status.get("goal", ""),
        "runtime_status": status["workspace_status"],
        "task_counts": status["task_counts"],
        "completed_task_ids": status["completed_task_ids"],
        "failed_task_ids": status["failed_task_ids"],
        "memory_entry_count": status["memory_entry_count"],
        "replay_valid": replay_valid,
        "closure_packet_valid": closure_packet_valid,
        "closure_ready": closure_ready,
        "runtime_governance_ready": runtime_governance_ready,
        "blocking_reasons": blocking_reasons,
        "closure_packet_path": _project_relative(closure_path, project_root),
        "closure_packet_hash": _sha256_file(closure_path),
        "evidence_path": _project_relative(output_path, project_root),
        "evidence_format": evidence_format,
        "safety_boundaries": dict(SAFETY_BOUNDARIES),
        "explicit_boundary": list(EXPLICIT_RUNTIME_BOUNDARY),
        "written": True,
    }
    if evidence_format == "json":
        _write_json(output_path, evidence)
    else:
        _write_text(output_path, _format_governance_text(evidence))
    return evidence


def runtime_job_payload(*, action: str, workspace: str, job_id: str | None, reason: str | None, project_root: Path) -> dict[str, Any]:
    workspace_root = _existing_workspace_path(workspace, project_root)
    paths = _workspace_files(workspace_root, project_root)
    manifest = _load_manifest(paths["manifest"])
    graph = _load_task_graph(paths["task_graph"], allow_empty=True)
    tasks = _graph_tasks(graph, allow_empty=True)
    if action == "create":
        required_job_id = _require_job_id(job_id)
        if paths["job"].exists():
            raise RuntimeFoundationError("runtime_job_already_exists", "Runtime job already exists for this workspace.")
        payload = _write_job_state(paths=paths, workspace_root=workspace_root, project_root=project_root, manifest=manifest, tasks=tasks, existing=None, state="created", job_id=required_job_id)
        return {"ok": True, "command": "runtime job create", **_job_readback(payload), "external_behavior": dict(SAFETY_BOUNDARIES)}

    job = _load_job(paths["job"], required=True)
    if job_id is not None and job.get("job_id") != job_id:
        raise RuntimeFoundationError("runtime_job_id_mismatch", f"Runtime job id does not match: {job_id}")
    if action == "status":
        return {"ok": True, "command": "runtime job status", **_job_readback(job), "external_behavior": dict(SAFETY_BOUNDARIES)}
    if action == "cancel":
        if not _job_cancel_allowed(str(job.get("state", ""))):
            raise RuntimeFoundationError("runtime_job_cancel_not_allowed", f"Runtime job cannot be cancelled from state: {job.get('state')}")
        payload = _write_job_state(paths=paths, workspace_root=workspace_root, project_root=project_root, manifest=manifest, tasks=tasks, existing=job, state="cancelled")
        return {"ok": True, "command": "runtime job cancel", **_job_readback(payload), "external_behavior": dict(SAFETY_BOUNDARIES)}
    if action == "fail":
        if str(job.get("state")) in {"completed", "cancelled"}:
            raise RuntimeFoundationError("runtime_job_fail_not_allowed", f"Runtime job cannot be failed from state: {job.get('state')}")
        payload = _write_job_state(paths=paths, workspace_root=workspace_root, project_root=project_root, manifest=manifest, tasks=tasks, existing=job, state="failed", failure_reason=reason or "manual failure")
        return {"ok": True, "command": "runtime job fail", **_job_readback(payload), "external_behavior": dict(SAFETY_BOUNDARIES)}
    if action == "resume":
        if not _job_resume_allowed(str(job.get("state", ""))):
            raise RuntimeFoundationError("runtime_job_resume_not_allowed", f"Runtime job cannot be resumed from state: {job.get('state')}")
        payload = _write_job_state(paths=paths, workspace_root=workspace_root, project_root=project_root, manifest=manifest, tasks=tasks, existing=job, state="running", failure_reason=None)
        return {"ok": True, "command": "runtime job resume", **_job_readback(payload), "external_behavior": dict(SAFETY_BOUNDARIES)}
    raise RuntimeFoundationError("runtime_job_unknown_action", f"Unsupported runtime job action: {action}")


def runtime_worker_adapter_payload(*, list_adapters: bool, name: str | None, describe: bool) -> dict[str, Any]:
    if list_adapters and (name or describe):
        raise RuntimeFoundationError("runtime_worker_adapter_args_invalid", "Use --list by itself, or --name with --describe.")
    if list_adapters:
        return {
            "ok": True,
            "command": "runtime worker-adapter",
            "kind": "runtime_worker_adapter_registry",
            "schema_version": SCHEMA_VERSION,
            "adapters": [_worker_adapter_descriptor(adapter_name) for adapter_name in sorted(WORKER_ADAPTERS)],
            "external_behavior": dict(SAFETY_BOUNDARIES),
        }
    if describe and name:
        return {
            "ok": True,
            "command": "runtime worker-adapter",
            "kind": "runtime_worker_adapter_contract",
            "schema_version": SCHEMA_VERSION,
            "adapter": _worker_adapter_descriptor(name),
            "external_behavior": dict(SAFETY_BOUNDARIES),
        }
    raise RuntimeFoundationError("runtime_worker_adapter_args_required", "runtime worker-adapter requires --list or --name with --describe.")


def runtime_worker_gate_payload(*, workspace: str, adapter: str, project_root: Path) -> dict[str, Any]:
    snapshot = _workspace_snapshot(workspace, project_root, allow_empty=True)
    descriptor = _worker_adapter_descriptor(adapter)
    return _worker_gate_contract(snapshot=snapshot, adapter=adapter, descriptor=descriptor)


def runtime_worker_invocation_packet_payload(*, workspace: str, adapter: str, job_id: str, out: str, packet_format: str, project_root: Path) -> dict[str, Any]:
    if packet_format not in {"json", "text"}:
        raise RuntimeFoundationError("runtime_worker_packet_format_invalid", f"Unsupported worker packet format: {packet_format}")
    output_path = _safe_output_path(out, project_root, "runtime_worker_packet")
    snapshot = _workspace_snapshot(workspace, project_root, allow_empty=False)
    job = _load_job(snapshot["paths"]["job"], required=True)
    required_job_id = _require_job_id(job_id)
    if job and job.get("job_id") != required_job_id:
        raise RuntimeFoundationError("runtime_worker_packet_job_mismatch", f"Runtime job id does not match: {job_id}")
    descriptor = _worker_adapter_descriptor(adapter)
    gate = _worker_gate_contract(snapshot=snapshot, adapter=adapter, descriptor=descriptor)
    tasks = snapshot["tasks"]
    packet = {
        "ok": True,
        "command": "runtime worker-packet",
        "kind": "runtime_worker_invocation_packet",
        "schema_version": SCHEMA_VERSION,
        "packet_type": "worker_invocation",
        "workspace": snapshot["workspace"],
        "goal": str(snapshot["manifest"].get("goal", "")),
        "job_id": required_job_id,
        "adapter": adapter,
        "task_ids": [task["id"] for task in tasks],
        "pending_task_ids": _ids_with_status(tasks, "pending"),
        "completed_task_ids": _ids_with_status(tasks, "completed"),
        "failed_task_ids": _ids_with_status(tasks, "failed"),
        "requested_capabilities": _worker_requested_capabilities(descriptor),
        "external_execution_allowed": False,
        "external_execution_enabled": False,
        "provider_calls": False,
        "model_calls": False,
        "browser_calls": False,
        "shell_calls": False,
        "worker_gate_ready": bool(gate["worker_gate_ready"]),
        "invocation_ready": True,
        "invocation_allowed": False,
        "refusal_reason": WORKER_REFUSAL_REASON,
        "safety_boundaries": dict(WORKER_SAFETY_BOUNDARIES),
        "created_by": "agent_office.runtime",
        "output_path": _project_relative(output_path, project_root),
        "packet_format": packet_format,
        "written": True,
    }
    if packet_format == "json":
        _write_json(output_path, packet)
    else:
        _write_text(output_path, _format_worker_packet_text(packet))
    return packet


def runtime_worker_result_intake_payload(*, workspace: str, packet: str, result: str, project_root: Path) -> dict[str, Any]:
    snapshot = _workspace_snapshot(workspace, project_root, allow_empty=False)
    packet_path = _safe_input_path(packet, project_root, "runtime_worker_result_packet")
    result_path = _safe_input_path(result, project_root, "runtime_worker_result")
    packet_payload = _load_input_json(packet_path, "runtime_worker_result_packet")
    result_payload = _load_input_json(result_path, "runtime_worker_result")
    _validate_worker_packet_for_intake(packet_payload, snapshot)
    task_results = _validate_worker_result_for_intake(result_payload, packet_payload, snapshot)
    paths = snapshot["paths"]
    tasks = snapshot["tasks"]
    task_by_id = {task["id"]: task for task in tasks}
    updated_task_ids: list[str] = []
    for task_result in task_results:
        task = task_by_id[str(task_result["task_id"])]
        status = str(task_result["status"])
        if status != "skipped":
            task["status"] = status
            task["result"] = {
                "schema_version": SCHEMA_VERSION,
                "adapter": str(result_payload["adapter"]),
                "task_id": task["id"],
                "role": task["role"],
                "status": status,
                "summary": str(task_result.get("summary", "")),
                "external_behavior": False,
                "intake_marker": str(result_payload["marker"]),
            }
            updated_task_ids.append(task["id"])
            _append_memory(paths["memory"], task, str(result_payload["adapter"]), _jsonl_count(paths["memory"]) + 1, task["result"])
        _append_event(
            paths["events"],
            "worker_result_intake",
            task,
            str(result_payload["adapter"]),
            _jsonl_count(paths["events"]) + 1,
            {"result": task_result, "packet_path": _project_relative(packet_path, project_root), "result_path": _project_relative(result_path, project_root)},
        )
    graph = snapshot["graph"]
    graph["tasks"] = tasks
    graph["topological_order"] = _topological_order(tasks)
    _write_json(paths["task_graph"], graph)
    manifest = snapshot["manifest"]
    manifest["status"] = _workspace_status(tasks)
    _write_json(paths["manifest"], manifest)
    job = _load_job(paths["job"], required=False)
    if job:
        state = "completed" if manifest["status"] == "completed" else "failed" if manifest["status"] in {"failed", "blocked"} else str(job.get("state", "running"))
        job = _write_job_state(paths=paths, workspace_root=snapshot["workspace_root"], project_root=project_root, manifest=manifest, tasks=tasks, existing=job, state=state, failure_reason=None if state != "failed" else f"workspace_status={manifest['status']}")
    return {
        "ok": True,
        "command": "runtime worker-result intake",
        "kind": "runtime_worker_result_intake",
        "schema_version": SCHEMA_VERSION,
        "workspace": snapshot["workspace"],
        "job_id": str(result_payload["job_id"]),
        "adapter": str(result_payload["adapter"]),
        "packet_path": _project_relative(packet_path, project_root),
        "result_path": _project_relative(result_path, project_root),
        "intake_ready": True,
        "intake_accepted": True,
        "updated_task_ids": updated_task_ids,
        "task_counts": _task_counts(tasks),
        "memory_entry_count": _jsonl_count(paths["memory"]),
        "event_entry_count": _jsonl_count(paths["events"]),
        "job": _job_readback(job) if job else None,
        "external_execution": False,
        "provider_calls": False,
        "model_calls": False,
        "browser_calls": False,
        "shell_calls": False,
        "safety_boundaries": dict(WORKER_SAFETY_BOUNDARIES),
    }




def runtime_worker_result_replay_payload(*, workspace: str, packet: str, result: str, project_root: Path) -> dict[str, Any]:
    snapshot, packet_path, result_path, packet_payload, result_payload, task_results = _load_worker_result_static_inputs(
        workspace=workspace,
        packet=packet,
        result=result,
        project_root=project_root,
    )
    return _worker_result_replay_payload(
        snapshot=snapshot,
        packet_path=packet_path,
        result_path=result_path,
        packet_payload=packet_payload,
        result_payload=result_payload,
        task_results=task_results,
        project_root=project_root,
    )


def runtime_worker_audit_closure_payload(*, workspace: str, packet: str, result: str, out: str, closure_format: str, project_root: Path) -> dict[str, Any]:
    if closure_format not in {"json", "text"}:
        raise RuntimeFoundationError("runtime_worker_audit_closure_format_invalid", f"Unsupported worker audit closure format: {closure_format}")
    output_path = _safe_output_path(out, project_root, "runtime_worker_audit_closure")
    replay = runtime_worker_result_replay_payload(workspace=workspace, packet=packet, result=result, project_root=project_root)
    closure = {
        "ok": True,
        "command": "runtime worker-result audit-closure",
        "kind": "runtime_worker_audit_closure_packet",
        "schema_version": SCHEMA_VERSION,
        "workspace": replay["workspace"],
        "job_id": replay["job_id"],
        "adapter": replay["adapter"],
        "invocation_packet_source": replay["invocation_packet_source"],
        "result_artifact_source": replay["result_artifact_source"],
        "replay_summary": _worker_replay_summary_readback(replay),
        "invocation_allowed": False,
        "external_execution_refused": True,
        "external_execution_allowed": False,
        "external_execution_enabled": False,
        "provider_calls": False,
        "model_calls": False,
        "browser_calls": False,
        "shell_calls": False,
        "governance_ready": replay["governance_ready"],
        "replay_ready": replay["replay_ready"],
        "validation_commands": _worker_validation_commands(),
        "review_delivery_next_action": "review codex-deliver safe-mode, then authorized delivery only if ready",
        "safety_boundaries": dict(WORKER_SAFETY_BOUNDARIES),
        "output_path": _project_relative(output_path, project_root),
        "closure_format": closure_format,
        "written": True,
    }
    if closure_format == "json":
        _write_json(output_path, closure)
    else:
        _write_text(output_path, _format_worker_audit_closure_text(closure))
    return closure


def runtime_worker_delivery_bundle_payload(*, workspace: str, packet: str, result: str, audit_closure: str, out: str, bundle_format: str, project_root: Path) -> dict[str, Any]:
    if bundle_format not in {"json", "text"}:
        raise RuntimeFoundationError("runtime_worker_delivery_bundle_format_invalid", f"Unsupported worker delivery bundle format: {bundle_format}")
    output_path = _safe_output_path(out, project_root, "runtime_worker_delivery_bundle")
    closure_path = _safe_input_path(audit_closure, project_root, "runtime_worker_delivery_bundle_audit_closure")
    closure = _load_input_json(closure_path, "runtime_worker_delivery_bundle_audit_closure")
    replay = runtime_worker_result_replay_payload(workspace=workspace, packet=packet, result=result, project_root=project_root)
    _validate_worker_audit_closure_for_bundle(closure, replay)
    snapshot = _workspace_snapshot(workspace, project_root, allow_empty=True)
    gate = runtime_worker_gate_payload(workspace=workspace, adapter=replay["adapter"], project_root=project_root)
    bundle = {
        "ok": True,
        "command": "runtime worker-result delivery-bundle",
        "kind": "runtime_worker_delivery_bundle",
        "schema_version": SCHEMA_VERSION,
        "workspace": replay["workspace"],
        "job_id": replay["job_id"],
        "adapter": replay["adapter"],
        "worker_gate_summary": {
            "worker_gate_ready": gate["worker_gate_ready"],
            "external_execution_allowed": gate["external_execution_allowed"],
            "external_execution_enabled": gate["external_execution_enabled"],
            "provider_calls": gate["provider_calls"],
            "model_calls": gate["model_calls"],
            "browser_calls": gate["browser_calls"],
            "shell_calls": gate["shell_calls"],
            "reason": gate["reason"],
        },
        "invocation_packet_summary": {
            "source": replay["invocation_packet_source"],
            "invocation_ready": replay["invocation_ready"],
            "invocation_allowed": replay["invocation_allowed"],
            "task_ids": replay["task_ids"],
        },
        "result_intake_summary": {
            "source": replay["result_artifact_source"],
            "result_task_count": replay["result_task_count"],
            "result_completed_task_count": replay["result_completed_task_count"],
            "memory_update_summary": replay["memory_update_summary"],
            "events_update_summary": replay["events_update_summary"],
        },
        "replay_summary": _worker_replay_summary_readback(replay),
        "audit_closure_summary": {
            "source": _project_relative(closure_path, project_root),
            "governance_ready": bool(closure.get("governance_ready")),
            "replay_ready": bool(closure.get("replay_ready")),
            "external_execution_refused": bool(closure.get("external_execution_refused")),
            "review_delivery_next_action": str(closure.get("review_delivery_next_action", "")),
        },
        "reviewer_ready": replay["replay_ready"] and bool(closure.get("replay_ready")),
        "delivery_ready": replay["governance_ready"] and bool(closure.get("governance_ready")),
        "validation_commands": _worker_validation_commands(),
        "static_artifacts": _runtime_file_statuses(snapshot["paths"], project_root),
        "safety_boundaries": dict(WORKER_SAFETY_BOUNDARIES),
        "output_path": _project_relative(output_path, project_root),
        "bundle_format": bundle_format,
        "written": True,
    }
    if bundle_format == "json":
        _write_json(output_path, bundle)
    else:
        _write_text(output_path, _format_worker_delivery_bundle_text(bundle))
    return bundle


def runtime_error_payload(command: str, exc: RuntimeFoundationError) -> dict[str, Any]:
    return {
        "ok": False,
        "command": command,
        "schema_version": SCHEMA_VERSION,
        "error_code": exc.error_code,
        "error": str(exc),
        "external_behavior": dict(SAFETY_BOUNDARIES),
    }


def format_runtime_payload(payload: dict[str, Any]) -> str:
    command = str(payload.get("command", "runtime"))
    lines = ["AgentOffice runtime foundation", f"command: {command}"]
    if "workspace" in payload:
        lines.append(f"workspace: {payload['workspace']}")
    status = payload.get("workspace_status", payload.get("status"))
    if status is not None:
        lines.append(f"status: {status}")
    if "goal" in payload:
        lines.append(f"goal: {payload['goal']}")
    if "task_count" in payload:
        lines.append(f"task_count: {payload['task_count']}")
    if "topological_order" in payload:
        lines.append(f"topological_order: {', '.join(payload['topological_order'])}")
    if "executed_task_ids" in payload:
        lines.append(f"executed: {', '.join(payload['executed_task_ids']) or '-'}")
    if "would_execute_task_ids" in payload:
        lines.append(f"would_execute: {', '.join(payload['would_execute_task_ids']) or '-'}")
    counts = payload.get("task_counts")
    if isinstance(counts, dict):
        lines.append(
            "tasks: "
            f"total={counts.get('total', 0)} "
            f"pending={counts.get('pending', 0)} "
            f"completed={counts.get('completed', 0)} "
            f"failed={counts.get('failed', 0)} "
            f"blocked={counts.get('blocked', 0)}"
        )
    for key, label in (
        ("completed_task_ids", "completed"),
        ("pending_task_ids", "pending"),
        ("failed_task_ids", "failed"),
        ("blocked_task_ids", "blocked"),
    ):
        if key in payload:
            lines.append(f"{label}: {', '.join(payload[key]) or '-'}")
    if "memory_entry_count" in payload:
        lines.append(f"memory_entries: {payload['memory_entry_count']}")
    if "latest_event_summary" in payload:
        lines.append(f"latest_event: {payload['latest_event_summary'] or '-'}")
    if payload.get("kind") == "runtime_lifecycle_packet":
        lifecycle = payload["lifecycle"]
        lines.append(f"lifecycle_status: {lifecycle['workspace_status']}")
        lines.append(f"terminal: {str(lifecycle['terminal']).lower()}")
    if payload.get("kind") == "runtime_replay_readback":
        lines.append(f"replay_valid: {str(payload['replay_valid']).lower()}")
        lines.append(f"mismatches: {len(payload['mismatches'])}")
    if payload.get("kind") == "runtime_workspace_evidence":
        lines.append(f"evidence_path: {payload['evidence_path']}")
        lines.append(f"evidence_format: {payload['evidence_format']}")
    if payload.get("kind") == "runtime_closure_packet":
        lines.append(f"closure_packet_valid: {str(payload['closure_packet_valid']).lower()}")
        lines.append(f"closure_ready: {str(payload['closure_ready']).lower()}")
        lines.append(f"readiness: {payload['readiness']}")
        lines.append(f"blocking_reasons: {', '.join(payload['blocking_reasons']) or 'none'}")
    if payload.get("kind") == "runtime_governance_evidence":
        lines.append(f"runtime_governance_ready: {str(payload['runtime_governance_ready']).lower()}")
        lines.append(f"closure_ready: {str(payload['closure_ready']).lower()}")
        lines.append(f"replay_valid: {str(payload['replay_valid']).lower()}")
        lines.append(f"evidence_path: {payload['evidence_path']}")
        lines.append(f"blocking_reasons: {', '.join(payload['blocking_reasons']) or 'none'}")
    if payload.get("kind") == "runtime_job_state" or ("job_id" in payload and "state" in payload):
        lines.append(f"job_id: {payload['job_id']}")
        lines.append(f"job_state: {payload['state']}")
        lines.append(f"resume_allowed: {str(payload['resume_allowed']).lower()}")
        lines.append(f"cancel_allowed: {str(payload['cancel_allowed']).lower()}")
    if payload.get("kind") == "runtime_worker_adapter_registry":
        lines.append("adapters: " + ", ".join(adapter["name"] for adapter in payload["adapters"]))
    if payload.get("kind") == "runtime_worker_adapter_contract":
        adapter = payload["adapter"]
        lines.append(f"adapter: {adapter['name']}")
        lines.append(f"external_execution_enabled: {str(adapter['external_execution_enabled']).lower()}")
        lines.append(f"reason: {adapter['reason']}")
    if payload.get("kind") == "runtime_worker_safety_gate":
        lines.append(f"adapter: {payload['adapter']}")
        lines.append(f"worker_gate_ready: {str(payload['worker_gate_ready']).lower()}")
        lines.append(f"external_execution_allowed: {str(payload['external_execution_allowed']).lower()}")
        lines.append(f"external_execution_enabled: {str(payload['external_execution_enabled']).lower()}")
        lines.append(f"provider_calls: {str(payload['provider_calls']).lower()}")
        lines.append(f"model_calls: {str(payload['model_calls']).lower()}")
        lines.append(f"browser_calls: {str(payload['browser_calls']).lower()}")
        lines.append(f"shell_calls: {str(payload['shell_calls']).lower()}")
        lines.append(f"reason: {payload['reason']}")
    if payload.get("kind") == "runtime_worker_invocation_packet":
        lines.append(f"adapter: {payload['adapter']}")
        lines.append(f"job_id: {payload['job_id']}")
        lines.append(f"worker_gate_ready: {str(payload['worker_gate_ready']).lower()}")
        lines.append(f"invocation_ready: {str(payload['invocation_ready']).lower()}")
        lines.append(f"invocation_allowed: {str(payload['invocation_allowed']).lower()}")
        lines.append(f"output_path: {payload['output_path']}")
    if payload.get("kind") == "runtime_worker_result_intake":
        lines.append(f"adapter: {payload['adapter']}")
        lines.append(f"job_id: {payload['job_id']}")
        lines.append(f"intake_accepted: {str(payload['intake_accepted']).lower()}")
        lines.append(f"updated: {', '.join(payload['updated_task_ids']) or '-'}")
        lines.append(f"event_entries: {payload['event_entry_count']}")
    if payload.get("kind") == "runtime_worker_result_replay":
        lines.append(f"adapter: {payload['adapter']}")
        lines.append(f"job_id: {payload['job_id']}")
        lines.append(f"replay_ready: {str(payload['replay_ready']).lower()}")
        lines.append(f"governance_ready: {str(payload['governance_ready']).lower()}")
        lines.append(f"result_completed_task_count: {payload['result_completed_task_count']}")
        lines.append(f"memory_updates: {payload['memory_update_summary']['entry_count']}")
        lines.append(f"event_updates: {payload['events_update_summary']['entry_count']}")
        lines.append(f"external_execution_refused: {str(payload['external_execution_refused']).lower()}")
    if payload.get("kind") == "runtime_worker_audit_closure_packet":
        lines.append(f"adapter: {payload['adapter']}")
        lines.append(f"job_id: {payload['job_id']}")
        lines.append(f"replay_ready: {str(payload['replay_ready']).lower()}")
        lines.append(f"governance_ready: {str(payload['governance_ready']).lower()}")
        lines.append(f"external_execution_refused: {str(payload['external_execution_refused']).lower()}")
        lines.append(f"output_path: {payload['output_path']}")
    if payload.get("kind") == "runtime_worker_delivery_bundle":
        lines.append(f"adapter: {payload['adapter']}")
        lines.append(f"job_id: {payload['job_id']}")
        lines.append(f"reviewer_ready: {str(payload['reviewer_ready']).lower()}")
        lines.append(f"delivery_ready: {str(payload['delivery_ready']).lower()}")
        lines.append(f"output_path: {payload['output_path']}")
    lines.append("provider/runtime/adapter execution: not triggered")
    return "\n".join(lines)


def _workspace_path(workspace: str, project_root: Path) -> Path:
    root = project_root.resolve(strict=True)
    raw = Path(workspace)
    if not str(workspace).strip():
        raise RuntimeFoundationError("runtime_workspace_required", "Workspace path is required.")
    if any(part == ".." for part in raw.parts):
        raise RuntimeFoundationError("runtime_workspace_path_traversal", f"Refusing workspace path traversal: {workspace}")
    if ".git" in raw.parts:
        raise RuntimeFoundationError("runtime_workspace_git_path_refused", f"Refusing workspace under .git: {workspace}")
    candidate = raw if raw.is_absolute() else root / raw
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise RuntimeFoundationError("runtime_workspace_outside_project", f"Workspace must stay inside project root: {workspace}") from exc
    _reject_symlink_escape(candidate, root, workspace)
    resolved = candidate.resolve(strict=False)
    if resolved != root and root in resolved.parents:
        return resolved
    raise RuntimeFoundationError("runtime_workspace_outside_project", f"Workspace must stay inside project root: {workspace}")


def _existing_workspace_path(workspace: str, project_root: Path) -> Path:
    workspace_root = _workspace_path(workspace, project_root)
    if not workspace_root.is_dir():
        raise RuntimeFoundationError("runtime_workspace_missing", f"Workspace does not exist: {workspace}")
    if workspace_root.is_symlink():
        raise RuntimeFoundationError("runtime_workspace_symlink_refused", f"Refusing workspace symlink: {workspace}")
    return workspace_root


def _reject_symlink_escape(candidate: Path, root: Path, original: str) -> None:
    current = root
    try:
        parts = candidate.relative_to(root).parts
    except ValueError:
        return
    for part in parts:
        current = current / part
        if current.exists() and current.is_symlink():
            target = current.resolve(strict=True)
            if target != root and root not in target.parents:
                raise RuntimeFoundationError("runtime_workspace_symlink_escape", f"Refusing symlink escape in workspace path: {original}")


def _workspace_files(workspace_root: Path, project_root: Path) -> dict[str, Path]:
    return {
        "manifest": _workspace_child(workspace_root, "manifest.json"),
        "task_graph": _workspace_child(workspace_root, "task_graph.json"),
        "memory": _workspace_child(workspace_root, "memory.jsonl"),
        "events": _workspace_child(workspace_root, "events.jsonl"),
        "job": _workspace_child(workspace_root, "runtime-job.json"),
    }


def _workspace_child(workspace_root: Path, relative: str) -> Path:
    if ".." in Path(relative).parts:
        raise RuntimeFoundationError("runtime_workspace_child_traversal", f"Refusing workspace child path traversal: {relative}")
    target = workspace_root / relative
    root = workspace_root.resolve(strict=True)
    resolved = target.resolve(strict=False)
    if resolved != root and root not in resolved.parents:
        raise RuntimeFoundationError("runtime_workspace_symlink_escape", f"Refusing workspace child symlink escape: {relative}")
    if target.exists() and target.is_symlink():
        raise RuntimeFoundationError("runtime_workspace_file_symlink_refused", f"Refusing workspace file symlink: {relative}")
    return resolved


def _worker_adapter_descriptor(name: str) -> dict[str, Any]:
    if name not in WORKER_ADAPTERS:
        raise RuntimeFoundationError("runtime_worker_adapter_unknown", f"Unsupported runtime worker adapter: {name}")
    return dict(WORKER_ADAPTERS[name])


def _require_job_id(job_id: str | None) -> str:
    if not job_id:
        raise RuntimeFoundationError("runtime_job_id_required", "Runtime job id is required.")
    if not TASK_ID_RE.match(job_id) or job_id in {".", ".."}:
        raise RuntimeFoundationError("runtime_job_id_invalid", f"Invalid runtime job id: {job_id}")
    return job_id


def _load_job(path: Path, *, required: bool) -> dict[str, Any] | None:
    if not path.exists():
        if required:
            raise RuntimeFoundationError("runtime_job_missing", "Runtime job state is missing. Run runtime job create first.")
        return None
    data = _load_json(path, "runtime_job_missing", "Runtime job state is missing.")
    if data.get("schema_version") != SCHEMA_VERSION or data.get("kind") != "runtime_job_state":
        raise RuntimeFoundationError("runtime_job_invalid", "Runtime job state schema is invalid.")
    state = str(data.get("state", ""))
    if state not in JOB_STATES:
        raise RuntimeFoundationError("runtime_job_invalid", f"Runtime job state is unsupported: {state}")
    return data


def _write_job_state(
    *,
    paths: dict[str, Path],
    workspace_root: Path,
    project_root: Path,
    manifest: dict[str, Any],
    tasks: list[dict[str, Any]],
    existing: dict[str, Any] | None,
    state: str,
    job_id: str | None = None,
    failure_reason: str | None = None,
) -> dict[str, Any]:
    if state not in JOB_STATES:
        raise RuntimeFoundationError("runtime_job_invalid", f"Runtime job state is unsupported: {state}")
    revision = int(existing.get("revision", 0)) + 1 if existing else 1
    created_timestamp = existing.get("created_at_or_static_timestamp") if existing else _logical_timestamp(1)
    current_reason = failure_reason if failure_reason is not None else (existing or {}).get("failure_reason")
    if state != "failed":
        current_reason = None
    payload = {
        "kind": "runtime_job_state",
        "schema_version": SCHEMA_VERSION,
        "job_id": _require_job_id(job_id or (str(existing.get("job_id")) if existing else None)),
        "workspace": _project_relative(workspace_root, project_root),
        "goal": str(manifest.get("goal", "")),
        "state": state,
        "created_at_or_static_timestamp": created_timestamp,
        "updated_at_or_static_timestamp": _logical_timestamp(revision),
        "revision": revision,
        "task_counts": _task_counts(tasks),
        "last_event_summary": _event_summary(_latest_jsonl(paths["events"])),
        "resume_allowed": _job_resume_allowed(state),
        "cancel_allowed": _job_cancel_allowed(state),
        "failure_reason": current_reason,
    }
    _write_json(paths["job"], payload)
    return payload


def _job_readback(job: dict[str, Any] | None) -> dict[str, Any] | None:
    if job is None:
        return None
    state = str(job.get("state", ""))
    return {
        "kind": "runtime_job_state",
        "schema_version": SCHEMA_VERSION,
        "job_id": str(job.get("job_id", "")),
        "workspace": str(job.get("workspace", "")),
        "goal": str(job.get("goal", "")),
        "state": state,
        "created_at_or_static_timestamp": str(job.get("created_at_or_static_timestamp", "")),
        "updated_at_or_static_timestamp": str(job.get("updated_at_or_static_timestamp", "")),
        "task_counts": dict(job.get("task_counts", {})),
        "last_event_summary": str(job.get("last_event_summary", "")),
        "resume_allowed": _job_resume_allowed(state),
        "cancel_allowed": _job_cancel_allowed(state),
        "failure_reason": job.get("failure_reason"),
    }


def _ensure_job_allows_run(job: dict[str, Any]) -> None:
    state = str(job.get("state", ""))
    if state == "cancelled":
        raise RuntimeFoundationError("runtime_job_cancelled", "Runtime job is cancelled and cannot execute.")
    if state == "failed":
        raise RuntimeFoundationError("runtime_job_failed", "Runtime job is failed; resume it before executing again.")


def _job_resume_allowed(state: str) -> bool:
    return state in {"created", "failed"}


def _job_cancel_allowed(state: str) -> bool:
    return state in {"created", "running", "failed"}


def _logical_timestamp(revision: int) -> str:
    return f"logical-{revision:06d}"


def _manifest_payload(workspace_root: Path, goal: str, status: str, paths: dict[str, Path], project_root: Path) -> dict[str, Any]:
    return {
        "kind": "runtime_workspace_manifest",
        "schema_version": SCHEMA_VERSION,
        "workspace": _project_relative(workspace_root, project_root),
        "goal": goal,
        "status": status,
        "task_graph_path": _project_relative(paths["task_graph"], project_root),
        "memory_path": _project_relative(paths["memory"], project_root),
        "events_path": _project_relative(paths["events"], project_root),
        "safety": dict(SAFETY_BOUNDARIES),
    }


def _empty_task_graph(workspace_root: Path, project_root: Path) -> dict[str, Any]:
    return {
        "kind": "runtime_task_graph",
        "schema_version": SCHEMA_VERSION,
        "workspace": _project_relative(workspace_root, project_root),
        "tasks": [],
        "topological_order": [],
    }


def _parse_task_spec(spec: str) -> dict[str, Any]:
    task_id, separator, title = spec.partition(":")
    if not separator or not task_id or not title:
        raise RuntimeFoundationError("runtime_plan_invalid_task", f"Task must use id:title format: {spec}")
    _validate_task_id(task_id)
    title = title.strip()
    if not title:
        raise RuntimeFoundationError("runtime_plan_invalid_task", f"Task title is required: {spec}")
    return {"id": task_id, "title": title, "role": _role_for_task(task_id, title), "status": "pending", "dependencies": []}


def _parse_dependency_spec(spec: str) -> tuple[str, str]:
    task_id, separator, dependency_id = spec.partition(":")
    if not separator or not task_id or not dependency_id:
        raise RuntimeFoundationError("runtime_plan_invalid_dependency", f"Dependency must use task:dependency format: {spec}")
    _validate_task_id(task_id)
    _validate_task_id(dependency_id)
    if task_id == dependency_id:
        raise RuntimeFoundationError("runtime_plan_cycle", f"Task cannot depend on itself: {task_id}")
    return task_id, dependency_id


def _validate_task_id(task_id: str) -> None:
    if not TASK_ID_RE.match(task_id) or task_id in {".", ".."}:
        raise RuntimeFoundationError("runtime_plan_invalid_task_id", f"Invalid task id: {task_id}")


def _role_for_task(task_id: str, title: str) -> str:
    text = f"{task_id} {title}".lower()
    if "review" in text or "verify" in text:
        return "reviewer"
    if "plan" in text or "inspect" in text:
        return "planner"
    return "worker"


def _topological_order(tasks: list[dict[str, Any]]) -> list[str]:
    by_id = {task["id"]: task for task in tasks}
    incoming = {task_id: set(task.get("dependencies", [])) for task_id, task in by_id.items()}
    for dependencies in incoming.values():
        missing = sorted(dependency for dependency in dependencies if dependency not in by_id)
        if missing:
            raise RuntimeFoundationError("runtime_plan_missing_dependency", f"Dependency references missing task: {missing[0]}")
    ready = sorted(task_id for task_id, dependencies in incoming.items() if not dependencies)
    ordered: list[str] = []
    while ready:
        task_id = ready.pop(0)
        ordered.append(task_id)
        for candidate in sorted(incoming):
            dependencies = incoming[candidate]
            if task_id in dependencies:
                dependencies.remove(task_id)
                if not dependencies and candidate not in ordered and candidate not in ready:
                    ready.append(candidate)
                    ready.sort()
    if len(ordered) != len(tasks):
        raise RuntimeFoundationError("runtime_plan_cycle", "Task graph contains a dependency cycle.")
    return ordered


def _static_worker_result(task: dict[str, Any], adapter: str) -> dict[str, Any]:
    failed = "[fail]" in str(task["title"]).lower()
    status = "failed" if failed else "completed"
    return {
        "schema_version": SCHEMA_VERSION,
        "adapter": adapter,
        "task_id": task["id"],
        "role": task["role"],
        "status": status,
        "summary": f"{adapter} deterministic {status} result for {task['id']}",
        "external_behavior": False,
    }


def _would_execute(tasks: list[dict[str, Any]], topological_order: list[str]) -> list[str]:
    by_id = {task["id"]: task for task in tasks}
    blocked = {task["id"] for task in tasks if task.get("status") in {"failed", "blocked"}}
    would: list[str] = []
    completed = {task["id"] for task in tasks if task.get("status") == "completed"}
    for task_id in topological_order:
        task = by_id[task_id]
        if task.get("status") == "completed":
            continue
        if any(dependency in blocked for dependency in task["dependencies"]):
            continue
        if all(dependency in completed or dependency in would for dependency in task["dependencies"]):
            would.append(task_id)
    return would


def _workspace_status(tasks: list[dict[str, Any]]) -> str:
    if not tasks:
        return "planned"
    if any(task.get("status") == "failed" for task in tasks):
        return "failed"
    if any(task.get("status") == "blocked" for task in tasks):
        return "blocked"
    if all(task.get("status") == "completed" for task in tasks):
        return "completed"
    return "planned"


def _task_counts(tasks: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"total": len(tasks), "pending": 0, "completed": 0, "failed": 0, "blocked": 0}
    for task in tasks:
        status = str(task.get("status", "pending"))
        if status in counts:
            counts[status] += 1
    return counts


def _ids_with_status(tasks: list[dict[str, Any]], status: str) -> list[str]:
    return [task["id"] for task in tasks if task.get("status") == status]


def _graph_tasks(graph: dict[str, Any], *, allow_empty: bool = False) -> list[dict[str, Any]]:
    tasks = graph.get("tasks")
    if not isinstance(tasks, list):
        raise RuntimeFoundationError("runtime_task_graph_invalid", "Task graph has no task list.")
    if not tasks and not allow_empty:
        raise RuntimeFoundationError("runtime_task_graph_empty", "Task graph has no tasks. Run runtime plan first.")
    normalized: list[dict[str, Any]] = []
    for task in tasks:
        if not isinstance(task, dict):
            raise RuntimeFoundationError("runtime_task_graph_invalid", "Task graph contains a malformed task.")
        task_id = str(task.get("id", ""))
        _validate_task_id(task_id)
        dependencies = task.get("dependencies", [])
        if not isinstance(dependencies, list):
            raise RuntimeFoundationError("runtime_task_graph_invalid", f"Task dependencies must be a list: {task_id}")
        status = str(task.get("status", "pending"))
        if status not in TASK_STATUSES:
            raise RuntimeFoundationError("runtime_task_graph_invalid", f"Unsupported task status: {status}")
        copied = dict(task)
        copied["id"] = task_id
        copied["title"] = str(task.get("title", ""))
        copied["role"] = str(task.get("role", _role_for_task(task_id, copied["title"])))
        copied["status"] = status
        copied["dependencies"] = [str(dependency) for dependency in dependencies]
        normalized.append(copied)
    return normalized


def _load_manifest(path: Path) -> dict[str, Any]:
    data = _load_json(path, "runtime_manifest_missing", "Runtime manifest is missing.")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise RuntimeFoundationError("runtime_manifest_invalid", "Runtime manifest schema version is unsupported.")
    return data


def _load_task_graph(path: Path, *, allow_empty: bool = False) -> dict[str, Any]:
    data = _load_json(path, "runtime_task_graph_missing", "Runtime task graph is missing.")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise RuntimeFoundationError("runtime_task_graph_invalid", "Runtime task graph schema version is unsupported.")
    if not allow_empty:
        _graph_tasks(data)
    return data


def _load_json(path: Path, missing_code: str, missing_message: str) -> dict[str, Any]:
    if not path.exists():
        raise RuntimeFoundationError(missing_code, missing_message)
    if path.is_symlink():
        raise RuntimeFoundationError("runtime_workspace_file_symlink_refused", f"Refusing symlink file: {path.name}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeFoundationError("runtime_json_unreadable", f"Unable to read runtime JSON: {path.name}") from exc
    if not isinstance(data, dict):
        raise RuntimeFoundationError("runtime_json_invalid", f"Runtime JSON must be an object: {path.name}")
    return data


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    if path.exists() and path.is_symlink():
        raise RuntimeFoundationError("runtime_workspace_file_symlink_refused", f"Refusing symlink file: {path.name}")
    tmp = path.with_name(f"{path.name}.tmp")
    if tmp.exists() and tmp.is_symlink():
        raise RuntimeFoundationError("runtime_workspace_file_symlink_refused", f"Refusing symlink temp file: {tmp.name}")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def _write_text(path: Path, text: str) -> None:
    if path.exists() and path.is_symlink():
        raise RuntimeFoundationError("runtime_workspace_file_symlink_refused", f"Refusing symlink file: {path.name}")
    tmp = path.with_name(f"{path.name}.tmp")
    if tmp.exists() and tmp.is_symlink():
        raise RuntimeFoundationError("runtime_workspace_file_symlink_refused", f"Refusing symlink temp file: {tmp.name}")
    tmp.write_text(text.rstrip() + "\n", encoding="utf-8")
    tmp.replace(path)


def _touch_jsonl(path: Path) -> None:
    if path.exists() and path.is_symlink():
        raise RuntimeFoundationError("runtime_workspace_file_symlink_refused", f"Refusing symlink file: {path.name}")
    if not path.exists():
        path.write_text("", encoding="utf-8")


def _append_memory(path: Path, task: dict[str, Any], adapter: str, sequence: int, result: dict[str, Any]) -> None:
    entry = {
        "schema_version": SCHEMA_VERSION,
        "entry_type": "task_memory",
        "sequence": sequence,
        "task_id": task["id"],
        "role": task["role"],
        "adapter": adapter,
        "status": result["status"],
        "summary": result["summary"],
    }
    _append_jsonl(path, entry)


def _append_event(path: Path, event_type: str, task: dict[str, Any], adapter: str, sequence: int, detail: dict[str, Any]) -> None:
    entry = {
        "schema_version": SCHEMA_VERSION,
        "entry_type": event_type,
        "sequence": sequence,
        "task_id": task["id"],
        "role": task["role"],
        "adapter": adapter,
        "status": task["status"],
        "detail": detail,
    }
    _append_jsonl(path, entry)


def _append_jsonl(path: Path, entry: dict[str, Any]) -> None:
    if path.exists() and path.is_symlink():
        raise RuntimeFoundationError("runtime_workspace_file_symlink_refused", f"Refusing symlink file: {path.name}")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def _jsonl_count(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_symlink():
        raise RuntimeFoundationError("runtime_workspace_file_symlink_refused", f"Refusing symlink file: {path.name}")
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _latest_jsonl(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    if path.is_symlink():
        raise RuntimeFoundationError("runtime_workspace_file_symlink_refused", f"Refusing symlink file: {path.name}")
    latest: dict[str, Any] | None = None
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in lines:
            if not line.strip():
                continue
            data = json.loads(line)
            if isinstance(data, dict):
                latest = data
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeFoundationError("runtime_jsonl_unreadable", f"Unable to read runtime JSONL: {path.name}") from exc
    return latest


def _workspace_snapshot(workspace: str, project_root: Path, *, allow_empty: bool) -> dict[str, Any]:
    workspace_root = _existing_workspace_path(workspace, project_root)
    paths = _workspace_files(workspace_root, project_root)
    manifest = _load_manifest(paths["manifest"])
    graph = _load_task_graph(paths["task_graph"], allow_empty=allow_empty)
    tasks = _graph_tasks(graph, allow_empty=allow_empty)
    return {
        "workspace_root": workspace_root,
        "workspace": _project_relative(workspace_root, project_root),
        "paths": paths,
        "manifest": manifest,
        "graph": graph,
        "tasks": tasks,
        "memory_entries": _load_jsonl(paths["memory"]),
        "event_entries": _load_jsonl(paths["events"]),
    }


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if path.is_symlink():
        raise RuntimeFoundationError("runtime_workspace_file_symlink_refused", f"Refusing symlink file: {path.name}")
    entries: list[dict[str, Any]] = []
    try:
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            data = json.loads(line)
            if not isinstance(data, dict):
                raise RuntimeFoundationError("runtime_jsonl_invalid", f"Runtime JSONL entry must be an object: {path.name}:{index}")
            entry = dict(data)
            entry["_line"] = index
            entries.append(entry)
    except json.JSONDecodeError as exc:
        raise RuntimeFoundationError("runtime_jsonl_unreadable", f"Unable to read runtime JSONL: {path.name}") from exc
    return entries


def _replay_contract(snapshot: dict[str, Any]) -> dict[str, Any]:
    tasks = snapshot["tasks"]
    graph = snapshot["graph"]
    topological_order = _topological_order(tasks) if tasks else []
    graph_order = list(graph.get("topological_order", []))
    graph_order_valid = graph_order == topological_order
    manifest_status = snapshot["manifest"].get("status")
    expected_workspace_status = "initialized" if not tasks else _workspace_status(tasks)
    workspace_status_matches_tasks = manifest_status == expected_workspace_status
    event_status_by_task: dict[str, str] = {}
    for entry in snapshot["event_entries"]:
        task_id = entry.get("task_id")
        status = entry.get("status")
        if isinstance(task_id, str) and isinstance(status, str):
            event_status_by_task[task_id] = status
    memory_status_by_task: dict[str, str] = {}
    for entry in snapshot["memory_entries"]:
        task_id = entry.get("task_id")
        status = entry.get("status")
        if entry.get("entry_type") == "task_memory" and isinstance(task_id, str) and isinstance(status, str):
            memory_status_by_task[task_id] = status

    mismatches: list[dict[str, Any]] = []
    if not graph_order_valid:
        mismatches.append({"kind": "topological_order", "graph": graph_order, "expected": topological_order})
    if not workspace_status_matches_tasks:
        mismatches.append({"kind": "workspace_status", "manifest": manifest_status, "expected": expected_workspace_status})
    for task in tasks:
        task_id = task["id"]
        graph_status = task["status"]
        event_status = event_status_by_task.get(task_id)
        memory_status = memory_status_by_task.get(task_id)
        if graph_status == "pending":
            if event_status is not None:
                mismatches.append({"kind": "pending_task_has_event", "task_id": task_id, "event_status": event_status})
            if memory_status is not None:
                mismatches.append({"kind": "pending_task_has_memory", "task_id": task_id, "memory_status": memory_status})
        elif graph_status in {"completed", "failed", "blocked"}:
            if event_status != graph_status:
                mismatches.append({"kind": "event_status", "task_id": task_id, "graph_status": graph_status, "event_status": event_status})
            if graph_status in {"completed", "failed"} and memory_status != graph_status:
                mismatches.append({"kind": "memory_status", "task_id": task_id, "graph_status": graph_status, "memory_status": memory_status})
            if graph_status == "blocked" and memory_status is not None:
                mismatches.append({"kind": "blocked_task_has_memory", "task_id": task_id, "memory_status": memory_status})

    task_statuses = [
        {
            "task_id": task["id"],
            "graph_status": task["status"],
            "event_status": event_status_by_task.get(task["id"]),
            "memory_status": memory_status_by_task.get(task["id"]),
        }
        for task in tasks
    ]
    return {
        "replay_valid": not mismatches,
        "graph_order_valid": graph_order_valid,
        "workspace_status_matches_tasks": workspace_status_matches_tasks,
        "workspace_status": manifest_status,
        "expected_workspace_status": expected_workspace_status,
        "topological_order": topological_order,
        "memory_entry_count": len(snapshot["memory_entries"]),
        "event_entry_count": len(snapshot["event_entries"]),
        "task_statuses": task_statuses,
        "mismatches": mismatches,
    }


def _task_readback(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": task["id"],
        "title": task["title"],
        "role": task["role"],
        "status": task["status"],
        "dependencies": list(task["dependencies"]),
        "result_status": task.get("result", {}).get("status") if isinstance(task.get("result"), dict) else None,
    }


def _runtime_file_statuses(paths: dict[str, Path], project_root: Path) -> dict[str, dict[str, Any]]:
    return {
        name: {
            "path": _project_relative(path, project_root),
            "exists": path.exists(),
            "is_file": path.is_file(),
            "is_symlink": path.is_symlink(),
        }
        for name, path in paths.items()
    }


def _runtime_file_digests(paths: dict[str, Path], project_root: Path) -> dict[str, dict[str, Any]]:
    digests: dict[str, dict[str, Any]] = {}
    for name, path in paths.items():
        if path.exists() and path.is_symlink():
            raise RuntimeFoundationError("runtime_workspace_file_symlink_refused", f"Refusing symlink file: {path.name}")
        data = path.read_bytes() if path.exists() else b""
        digests[name] = {
            "path": _project_relative(path, project_root),
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
            "lines": len(data.decode("utf-8").splitlines()) if data else 0,
        }
    return digests


def _safe_input_path(path: str, project_root: Path, code_prefix: str) -> Path:
    if not str(path).strip():
        raise RuntimeFoundationError(f"{code_prefix}_required", "Input path is required.")
    raw = Path(path)
    if any(part == ".." for part in raw.parts):
        raise RuntimeFoundationError(f"{code_prefix}_path_traversal", f"Refusing input path traversal: {path}")
    if any(part == ".env" for part in raw.parts):
        raise RuntimeFoundationError(f"{code_prefix}_dotenv_refused", f"Refusing .env input path: {path}")
    root = project_root.resolve(strict=True)
    candidate = raw if raw.is_absolute() else root / raw
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise RuntimeFoundationError(f"{code_prefix}_outside_project", f"Input path must stay inside project root: {path}") from exc
    parent = candidate.parent.resolve(strict=False)
    if parent != root and root not in parent.parents:
        raise RuntimeFoundationError(f"{code_prefix}_outside_project", f"Input path must stay inside project root: {path}")
    if candidate.parent.exists() and candidate.parent.is_symlink():
        raise RuntimeFoundationError(f"{code_prefix}_parent_symlink", f"Refusing symlink input parent: {candidate.parent}")
    if not candidate.exists():
        raise RuntimeFoundationError(f"{code_prefix}_missing", f"Input file does not exist: {candidate}")
    if candidate.is_symlink():
        raise RuntimeFoundationError(f"{code_prefix}_symlink", f"Refusing symlink input path: {candidate}")
    if not candidate.is_file():
        raise RuntimeFoundationError(f"{code_prefix}_not_file", f"Input path is not a file: {candidate}")
    return candidate.resolve(strict=False)


def _load_input_json(path: Path, code_prefix: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeFoundationError(f"{code_prefix}_invalid", f"Input JSON is invalid: {path.name}") from exc
    if not isinstance(data, dict):
        raise RuntimeFoundationError(f"{code_prefix}_invalid", f"Input JSON must be an object: {path.name}")
    return data


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_output_path(path: str, project_root: Path, code_prefix: str) -> Path:
    if not str(path).strip():
        raise RuntimeFoundationError(f"{code_prefix}_output_required", "Output path is required.")
    raw = Path(path)
    if any(part == ".." for part in raw.parts):
        raise RuntimeFoundationError(f"{code_prefix}_path_traversal", f"Refusing output path traversal: {path}")
    if any(part == ".env" for part in raw.parts):
        raise RuntimeFoundationError(f"{code_prefix}_dotenv_refused", f"Refusing .env output path: {path}")
    root = project_root.resolve(strict=True)
    candidate = raw if raw.is_absolute() else root / raw
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise RuntimeFoundationError(f"{code_prefix}_outside_project", f"Output path must stay inside project root: {path}") from exc
    parent = candidate.parent.resolve(strict=False)
    if parent != root and root not in parent.parents:
        raise RuntimeFoundationError(f"{code_prefix}_outside_project", f"Output path must stay inside project root: {path}")
    if not candidate.parent.exists():
        raise RuntimeFoundationError(f"{code_prefix}_parent_missing", f"Output parent does not exist: {candidate.parent}")
    if candidate.parent.is_symlink():
        raise RuntimeFoundationError(f"{code_prefix}_parent_symlink", f"Refusing symlink output parent: {candidate.parent}")
    if candidate.exists() and candidate.is_symlink():
        raise RuntimeFoundationError(f"{code_prefix}_output_symlink", f"Refusing symlink output path: {candidate}")
    if candidate.exists() and candidate.is_dir():
        raise RuntimeFoundationError(f"{code_prefix}_output_directory", f"Output path is a directory: {candidate}")
    return candidate.resolve(strict=False)


def _format_evidence_text(payload: dict[str, Any]) -> str:
    packet = payload["packet"]
    replay = payload["replay"]
    lifecycle = packet["lifecycle"]
    lines = [
        "# AgentOffice Runtime Workspace Evidence",
        "",
        f"schema_version: {payload['schema_version']}",
        f"workspace: {payload['workspace']}",
        f"workspace_status: {lifecycle['workspace_status']}",
        f"terminal: {str(lifecycle['terminal']).lower()}",
        f"replay_valid: {str(replay['replay_valid']).lower()}",
        f"memory_entry_count: {replay['memory_entry_count']}",
        f"event_entry_count: {replay['event_entry_count']}",
        "",
        "## Completed Tasks",
        "",
    ]
    completed = lifecycle["completed_task_ids"]
    lines.extend(f"- {task_id}" for task_id in completed)
    if not completed:
        lines.append("- none")
    lines.extend(["", "## File Digests", ""])
    for name, digest in payload["file_digests"].items():
        lines.append(f"- {name}: {digest['sha256']} ({digest['bytes']} bytes)")
    lines.extend(["", "provider/runtime/adapter execution: not triggered"])
    return "\n".join(lines)


def _format_governance_text(payload: dict[str, Any]) -> str:
    lines = [
        "# AgentOffice Runtime Governance Evidence",
        "",
        f"schema_version: {payload['schema_version']}",
        f"workspace: {payload['workspace']}",
        f"goal: {payload['goal']}",
        f"runtime_status: {payload['runtime_status']}",
        f"runtime_governance_ready: {str(payload['runtime_governance_ready']).lower()}",
        f"closure_packet_valid: {str(payload['closure_packet_valid']).lower()}",
        f"closure_ready: {str(payload['closure_ready']).lower()}",
        f"replay_valid: {str(payload['replay_valid']).lower()}",
        f"memory_entry_count: {payload['memory_entry_count']}",
        f"closure_packet_path: {payload['closure_packet_path']}",
        f"closure_packet_hash: {payload['closure_packet_hash']}",
        f"blocking_reasons: {', '.join(payload['blocking_reasons']) if payload['blocking_reasons'] else 'none'}",
        "",
        "## Explicit Boundary",
        "",
    ]
    lines.extend(f"- {item}" for item in payload["explicit_boundary"])
    lines.extend(["", "provider/runtime/adapter execution: not triggered"])
    return "\n".join(lines)


def _worker_gate_contract(*, snapshot: dict[str, Any], adapter: str, descriptor: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "command": "runtime worker-gate",
        "kind": "runtime_worker_safety_gate",
        "schema_version": SCHEMA_VERSION,
        "workspace": snapshot["workspace"],
        "adapter": adapter,
        "worker_gate_ready": True,
        "external_execution_allowed": False,
        "external_execution_enabled": bool(descriptor.get("external_execution_enabled", False)),
        "provider_calls": False,
        "model_calls": False,
        "browser_calls": False,
        "shell_calls": False,
        "requires_explicit_future_authorization": True,
        "reason": WORKER_REFUSAL_REASON if adapter == "external-prototype" else str(descriptor.get("reason", "local/static adapter")),
        "safety_boundaries": dict(WORKER_SAFETY_BOUNDARIES),
        "external_behavior": dict(SAFETY_BOUNDARIES),
    }


def _worker_requested_capabilities(descriptor: dict[str, Any]) -> dict[str, bool]:
    return {
        "dry_run": bool(descriptor.get("dry_run_supported", False)),
        "execute_local": bool(descriptor.get("execute_local_supported", False)),
        "external_execution": False,
        "provider_calls": False,
        "model_calls": False,
        "browser_calls": False,
        "shell_calls": False,
    }


def _validate_worker_packet_for_intake(packet: dict[str, Any], snapshot: dict[str, Any]) -> None:
    if packet.get("schema_version") != SCHEMA_VERSION or packet.get("packet_type") != "worker_invocation":
        raise RuntimeFoundationError("runtime_worker_result_packet_invalid", "Worker invocation packet schema is invalid.")
    if packet.get("workspace") != snapshot["workspace"]:
        raise RuntimeFoundationError("runtime_worker_result_workspace_mismatch", "Worker packet workspace does not match runtime workspace.")
    if packet.get("external_execution_allowed") is not False or packet.get("invocation_allowed") is not False:
        raise RuntimeFoundationError("runtime_worker_result_packet_invalid", "Worker packet must refuse external invocation.")
    for key in ("provider_calls", "model_calls", "browser_calls", "shell_calls"):
        if packet.get(key) is not False:
            raise RuntimeFoundationError("runtime_worker_result_packet_invalid", f"Worker packet must report {key}=false.")
    _require_job_id(str(packet.get("job_id", "")))
    _worker_adapter_descriptor(str(packet.get("adapter", "")))


def _validate_worker_result_for_intake(result: dict[str, Any], packet: dict[str, Any], snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    if result.get("schema_version") != SCHEMA_VERSION or result.get("artifact_type") != "worker_result":
        raise RuntimeFoundationError("runtime_worker_result_invalid", "Worker result schema is invalid.")
    if result.get("marker") != "AGENT_OFFICE_WORKER_RESULT":
        raise RuntimeFoundationError("runtime_worker_result_marker_missing", "Worker result marker is missing.")
    for key in ("external_execution", "provider_calls", "model_calls", "browser_calls", "shell_calls"):
        if result.get(key) is not False:
            raise RuntimeFoundationError(f"runtime_worker_result_{key}_refused", f"Worker result must report {key}=false.")
    if result.get("workspace") != snapshot["workspace"] or result.get("workspace") != packet.get("workspace"):
        raise RuntimeFoundationError("runtime_worker_result_workspace_mismatch", "Worker result workspace does not match packet/workspace.")
    if result.get("job_id") != packet.get("job_id"):
        raise RuntimeFoundationError("runtime_worker_result_job_mismatch", "Worker result job id does not match packet.")
    if result.get("adapter") != packet.get("adapter"):
        raise RuntimeFoundationError("runtime_worker_result_adapter_mismatch", "Worker result adapter does not match packet.")
    task_results = result.get("task_results")
    if not isinstance(task_results, list) or not task_results:
        raise RuntimeFoundationError("runtime_worker_result_task_results_missing", "Worker result task_results must be a non-empty list.")
    known_task_ids = {task["id"] for task in snapshot["tasks"]}
    normalized: list[dict[str, Any]] = []
    for entry in task_results:
        if not isinstance(entry, dict):
            raise RuntimeFoundationError("runtime_worker_result_task_invalid", "Worker result task entry must be an object.")
        task_id = str(entry.get("task_id", ""))
        _validate_task_id(task_id)
        if task_id not in known_task_ids:
            raise RuntimeFoundationError("runtime_worker_result_task_unknown", f"Worker result task does not exist: {task_id}")
        status = str(entry.get("status", ""))
        if status not in WORKER_RESULT_STATUSES:
            raise RuntimeFoundationError("runtime_worker_result_status_invalid", f"Unsupported worker result status: {status}")
        normalized.append({"task_id": task_id, "status": status, "summary": str(entry.get("summary", ""))})
    return normalized


def _format_worker_packet_text(payload: dict[str, Any]) -> str:
    lines = [
        "# AgentOffice Worker Invocation Packet",
        "",
        f"schema_version: {payload['schema_version']}",
        f"workspace: {payload['workspace']}",
        f"job_id: {payload['job_id']}",
        f"adapter: {payload['adapter']}",
        f"worker_gate_ready: {str(payload['worker_gate_ready']).lower()}",
        f"invocation_ready: {str(payload['invocation_ready']).lower()}",
        f"invocation_allowed: {str(payload['invocation_allowed']).lower()}",
        f"external_execution_enabled: {str(payload['external_execution_enabled']).lower()}",
        f"refusal_reason: {payload['refusal_reason']}",
        "",
        "## Tasks",
    ]
    lines.extend(f"- {task_id}" for task_id in payload["task_ids"])
    lines.append("")
    lines.append("provider/runtime/adapter execution: not triggered")
    return "\n".join(lines)




def _load_worker_result_static_inputs(*, workspace: str, packet: str, result: str, project_root: Path) -> tuple[dict[str, Any], Path, Path, dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    snapshot = _workspace_snapshot(workspace, project_root, allow_empty=False)
    packet_path = _safe_input_path(packet, project_root, "runtime_worker_result_packet")
    result_path = _safe_input_path(result, project_root, "runtime_worker_result")
    packet_payload = _load_input_json(packet_path, "runtime_worker_result_packet")
    result_payload = _load_input_json(result_path, "runtime_worker_result")
    _validate_worker_packet_for_intake(packet_payload, snapshot)
    task_results = _validate_worker_result_for_intake(result_payload, packet_payload, snapshot)
    return snapshot, packet_path, result_path, packet_payload, result_payload, task_results


def _worker_result_replay_payload(
    *,
    snapshot: dict[str, Any],
    packet_path: Path,
    result_path: Path,
    packet_payload: dict[str, Any],
    result_payload: dict[str, Any],
    task_results: list[dict[str, Any]],
    project_root: Path,
) -> dict[str, Any]:
    replay = _replay_contract(snapshot)
    result_status_counts = _worker_result_status_counts(task_results)
    replay_ready = bool(replay["replay_valid"])
    governance_ready = replay_ready and replay.get("workspace_status") == "completed"
    return {
        "ok": True,
        "command": "runtime worker-result replay",
        "kind": "runtime_worker_result_replay",
        "schema_version": SCHEMA_VERSION,
        "workspace": snapshot["workspace"],
        "job_id": str(result_payload["job_id"]),
        "adapter": str(result_payload["adapter"]),
        "invocation_packet_source": _artifact_source(packet_path, project_root),
        "result_artifact_source": _artifact_source(result_path, project_root),
        "task_ids": [task["id"] for task in snapshot["tasks"]],
        "result_task_ids": [str(task_result["task_id"]) for task_result in task_results],
        "result_task_count": len(task_results),
        "result_completed_task_count": result_status_counts["completed"],
        "result_failed_task_count": result_status_counts["failed"],
        "result_skipped_task_count": result_status_counts["skipped"],
        "runtime_completed_task_count": _task_counts(snapshot["tasks"])["completed"],
        "memory_update_summary": {
            "entry_count": len(snapshot["memory_entries"]),
            "task_memory_ids": [entry.get("task_id") for entry in snapshot["memory_entries"] if entry.get("entry_type") == "task_memory"],
        },
        "events_update_summary": {
            "entry_count": len(snapshot["event_entries"]),
            "latest_event_summary": _event_summary(snapshot["event_entries"][-1] if snapshot["event_entries"] else None),
            "worker_result_intake_event_count": sum(1 for entry in snapshot["event_entries"] if entry.get("entry_type") == "worker_result_intake"),
        },
        "runtime_replay": replay,
        "replay_ready": replay_ready,
        "governance_ready": governance_ready,
        "worker_result_replay_valid": True,
        "invocation_ready": bool(packet_payload.get("invocation_ready")),
        "invocation_allowed": False,
        "external_execution_refused": True,
        "external_execution_allowed": False,
        "external_execution_enabled": False,
        "provider_calls": False,
        "model_calls": False,
        "browser_calls": False,
        "shell_calls": False,
        "safety_boundaries": dict(WORKER_SAFETY_BOUNDARIES),
        "external_behavior": dict(SAFETY_BOUNDARIES),
    }


def _worker_result_status_counts(task_results: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"completed": 0, "failed": 0, "skipped": 0}
    for task_result in task_results:
        counts[str(task_result["status"])] += 1
    return counts


def _artifact_source(path: Path, project_root: Path) -> dict[str, Any]:
    return {
        "path": _project_relative(path, project_root),
        "sha256": _sha256_file(path),
        "bytes": path.stat().st_size,
    }


def _worker_replay_summary_readback(replay: dict[str, Any]) -> dict[str, Any]:
    return {
        "workspace": replay["workspace"],
        "job_id": replay["job_id"],
        "adapter": replay["adapter"],
        "result_completed_task_count": replay["result_completed_task_count"],
        "runtime_completed_task_count": replay["runtime_completed_task_count"],
        "memory_update_summary": replay["memory_update_summary"],
        "events_update_summary": replay["events_update_summary"],
        "replay_ready": replay["replay_ready"],
        "governance_ready": replay["governance_ready"],
        "external_execution_refused": replay["external_execution_refused"],
        "provider_calls": replay["provider_calls"],
        "model_calls": replay["model_calls"],
        "browser_calls": replay["browser_calls"],
        "shell_calls": replay["shell_calls"],
    }


def _worker_validation_commands() -> list[str]:
    return [
        "python3 -m compileall agent_office tests",
        "python3 -m unittest tests.test_runtime_foundation_cli",
        "python3 -m unittest tests.test_review_lifecycle_cli",
        "python3 -m unittest",
        "python3 -m unittest discover -s tests -p 'test_*.py'",
        "python3 -m agent_office doctor --adapters",
        "./scripts/verify.sh",
        "./scripts/smoke-test.sh P6-PROFILES",
        "python3 -m agent_office run-staged P6-PROFILES --dry-run --reset",
        "git diff --check",
    ]


def _validate_worker_audit_closure_for_bundle(closure: dict[str, Any], replay: dict[str, Any]) -> None:
    if closure.get("schema_version") != SCHEMA_VERSION or closure.get("kind") != "runtime_worker_audit_closure_packet":
        raise RuntimeFoundationError("runtime_worker_delivery_bundle_audit_closure_invalid", "Worker audit closure packet schema is invalid.")
    if closure.get("workspace") != replay["workspace"]:
        raise RuntimeFoundationError("runtime_worker_delivery_bundle_workspace_mismatch", "Worker audit closure workspace does not match replay.")
    if closure.get("job_id") != replay["job_id"]:
        raise RuntimeFoundationError("runtime_worker_delivery_bundle_job_mismatch", "Worker audit closure job id does not match replay.")
    if closure.get("adapter") != replay["adapter"]:
        raise RuntimeFoundationError("runtime_worker_delivery_bundle_adapter_mismatch", "Worker audit closure adapter does not match replay.")
    if closure.get("external_execution_refused") is not True or closure.get("invocation_allowed") is not False:
        raise RuntimeFoundationError("runtime_worker_delivery_bundle_audit_closure_invalid", "Worker audit closure must refuse external execution.")
    for key in ("provider_calls", "model_calls", "browser_calls", "shell_calls"):
        if closure.get(key) is not False:
            raise RuntimeFoundationError("runtime_worker_delivery_bundle_audit_closure_invalid", f"Worker audit closure must report {key}=false.")


def _format_worker_result_replay_text(payload: dict[str, Any]) -> str:
    lines = [
        "# AgentOffice Worker Result Replay",
        "",
        f"schema_version: {payload['schema_version']}",
        f"workspace: {payload['workspace']}",
        f"job_id: {payload['job_id']}",
        f"adapter: {payload['adapter']}",
        f"result_completed_task_count: {payload['result_completed_task_count']}",
        f"runtime_completed_task_count: {payload['runtime_completed_task_count']}",
        f"memory_entries: {payload['memory_update_summary']['entry_count']}",
        f"event_entries: {payload['events_update_summary']['entry_count']}",
        f"replay_ready: {str(payload['replay_ready']).lower()}",
        f"governance_ready: {str(payload['governance_ready']).lower()}",
        f"external_execution_refused: {str(payload['external_execution_refused']).lower()}",
        f"provider_calls: {str(payload['provider_calls']).lower()}",
        f"model_calls: {str(payload['model_calls']).lower()}",
        f"browser_calls: {str(payload['browser_calls']).lower()}",
        f"shell_calls: {str(payload['shell_calls']).lower()}",
        "",
        "provider/runtime/adapter execution: not triggered",
    ]
    return "\n".join(lines)


def _format_worker_audit_closure_text(payload: dict[str, Any]) -> str:
    summary = payload["replay_summary"]
    lines = [
        "# AgentOffice Worker Audit Closure Packet",
        "",
        f"schema_version: {payload['schema_version']}",
        f"workspace: {payload['workspace']}",
        f"job_id: {payload['job_id']}",
        f"adapter: {payload['adapter']}",
        f"invocation_packet: {payload['invocation_packet_source']['path']}",
        f"result_artifact: {payload['result_artifact_source']['path']}",
        f"result_completed_task_count: {summary['result_completed_task_count']}",
        f"memory_entries: {summary['memory_update_summary']['entry_count']}",
        f"event_entries: {summary['events_update_summary']['entry_count']}",
        f"replay_ready: {str(payload['replay_ready']).lower()}",
        f"governance_ready: {str(payload['governance_ready']).lower()}",
        f"invocation_allowed: {str(payload['invocation_allowed']).lower()}",
        f"external_execution_refused: {str(payload['external_execution_refused']).lower()}",
        f"provider_calls: {str(payload['provider_calls']).lower()}",
        f"model_calls: {str(payload['model_calls']).lower()}",
        f"browser_calls: {str(payload['browser_calls']).lower()}",
        f"shell_calls: {str(payload['shell_calls']).lower()}",
        "",
        "## Validation Commands",
    ]
    lines.extend(f"- {command}" for command in payload["validation_commands"])
    lines.extend(["", f"review_delivery_next_action: {payload['review_delivery_next_action']}"])
    return "\n".join(lines)


def _format_worker_delivery_bundle_text(payload: dict[str, Any]) -> str:
    lines = [
        "# AgentOffice Worker Delivery Bundle",
        "",
        f"schema_version: {payload['schema_version']}",
        f"workspace: {payload['workspace']}",
        f"job_id: {payload['job_id']}",
        f"adapter: {payload['adapter']}",
        f"reviewer_ready: {str(payload['reviewer_ready']).lower()}",
        f"delivery_ready: {str(payload['delivery_ready']).lower()}",
        f"worker_gate_ready: {str(payload['worker_gate_summary']['worker_gate_ready']).lower()}",
        f"invocation_allowed: {str(payload['invocation_packet_summary']['invocation_allowed']).lower()}",
        f"result_completed_task_count: {payload['replay_summary']['result_completed_task_count']}",
        f"audit_closure: {payload['audit_closure_summary']['source']}",
        "",
        "provider/runtime/adapter execution: not triggered",
    ]
    return "\n".join(lines)


def _event_summary(event: dict[str, Any] | None) -> str:
    if not event:
        return ""
    return f"{event.get('entry_type')}:{event.get('task_id')}:{event.get('status')}"


def _project_relative(path: Path, project_root: Path) -> str:
    root = project_root.resolve(strict=True)
    return path.resolve(strict=False).relative_to(root).as_posix()
