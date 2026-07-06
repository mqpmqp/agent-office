from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from agent_office.runtime_kernel import executor as runtime_executor
from agent_office.runtime_kernel import kernel as runtime_kernel
from agent_office.runtime_kernel import scheduler as runtime_scheduler
from agent_office.runtime_kernel.event_log import EventLogError, append_event, ensure_event_log


SCHEMA_VERSION = 1
TASK_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
TASK_STATUSES = {"pending", "completed", "failed", "blocked"}
JOB_STATES = {"created", "running", "completed", "failed", "cancelled"}
WORKER_RESULT_STATUSES = {"completed", "failed", "skipped"}
REVIEWER_ATTESTATION_PACKET_MARKER = "AGENT_OFFICE_REVIEWER_ATTESTATION_PACKET"
CLOSURE_EVIDENCE_IMPORTED_MARKER = "AGENT_OFFICE_CLOSURE_EVIDENCE_IMPORTED"
MERGE_READINESS_PACKET_MARKER = "AGENT_OFFICE_MERGE_READINESS_PACKET"
DELIVERY_GATE_PACKET_MARKER = "AGENT_OFFICE_DELIVERY_GATE_PACKET"
REJECTION_RECOVERY_PACKET_MARKER = "AGENT_OFFICE_REJECTION_RECOVERY_PACKET"
AUDIT_PACKET_REPLAY_MARKER = "AGENT_OFFICE_AUDIT_PACKET_REPLAY"
PROVENANCE_MANIFEST_MARKER = "AGENT_OFFICE_ARTIFACT_CHAIN_PROVENANCE_MANIFEST"
PROVENANCE_VERIFY_MARKER = "AGENT_OFFICE_ARTIFACT_CHAIN_PROVENANCE_VERIFY"
PROVENANCE_REPLAY_MARKER = "AGENT_OFFICE_ARTIFACT_CHAIN_TAMPER_REPLAY"
RELEASE_CANDIDATE_PACKAGE_MARKER = "AGENT_OFFICE_RELEASE_CANDIDATE_PACKAGE"
EXTERNAL_REVIEW_HANDOFF_MARKER = "AGENT_OFFICE_EXTERNAL_REVIEW_HANDOFF"
EVIDENCE_ARCHIVE_INDEX_MARKER = "AGENT_OFFICE_EVIDENCE_ARCHIVE_INDEX"
EVIDENCE_ARCHIVE_VERIFY_MARKER = "AGENT_OFFICE_EVIDENCE_ARCHIVE_VERIFY"
EXTERNAL_REVIEW_ARCHIVE_IMPORT_MARKER = "AGENT_OFFICE_EXTERNAL_REVIEW_ARCHIVE_IMPORT"
RELEASE_CLOSURE_BUNDLE_MARKER = "AGENT_OFFICE_RELEASE_CLOSURE_BUNDLE"
ARCHIVE_REPLAY_VERIFICATION_MARKER = "AGENT_OFFICE_ARCHIVE_REPLAY_VERIFICATION"
FINAL_DELIVERY_READINESS_MARKER = "AGENT_OFFICE_FINAL_DELIVERY_READINESS"
FAILED_REVIEW_RECOVERY_MARKER = "AGENT_OFFICE_FAILED_REVIEW_RECOVERY_PACKET"
COMPACT_ARCHIVE_INDEX_MARKER = "AGENT_OFFICE_COMPACT_EVIDENCE_ARCHIVE_INDEX"
COMPACT_ARCHIVE_VERIFY_MARKER = "AGENT_OFFICE_COMPACT_EVIDENCE_ARCHIVE_VERIFY"
RC_PROMOTION_GATE_MARKER = "AGENT_OFFICE_RC_PROMOTION_GATE"
RELEASE_CANDIDATE_EXPORT_PACKET_MARKER = "AGENT_OFFICE_RELEASE_CANDIDATE_EXPORT_PACKET"
PROMOTION_EVIDENCE_PACKET_MARKER = "AGENT_OFFICE_PROMOTION_EVIDENCE_PACKET"
DRY_RUN_PUBLISH_PACKET_MARKER = "AGENT_OFFICE_DRY_RUN_PUBLISH_PACKET"
ARCHIVE_REQUIRED_ROLES = (
    "release_candidate",
    "provenance_manifest",
    "delivery_gate",
    "reviewer_attestation",
    "closure_evidence",
    "merge_readiness",
    "rejection_recovery",
    "audit_replay",
    "external_review_handoff",
)
COMPACT_ARCHIVE_REQUIRED_ROLES = ARCHIVE_REQUIRED_ROLES + (
    "external_reviewer_import",
    "release_closure",
    "archive_replay",
    "final_delivery_readiness",
)
PROVENANCE_REQUIRED_ROLE_ORDER = (
    "reviewer_attestation",
    "closure_evidence",
    "merge_readiness",
    "delivery_gate",
    "rejection_recovery",
    "audit_replay",
)
PROVENANCE_ROLE_KINDS = {
    "reviewer_attestation": "runtime_worker_reviewer_attestation_packet",
    "closure_evidence": "runtime_worker_closure_evidence",
    "merge_readiness": "runtime_worker_merge_readiness_packet",
    "delivery_gate": "runtime_worker_delivery_gate_summary",
    "rejection_recovery": "runtime_worker_rejection_recovery_packet",
    "audit_replay": "runtime_worker_audit_packet_replay",
}
PROVENANCE_PARENT_IDS = {
    "reviewer_attestation": (),
    "closure_evidence": ("reviewer_attestation",),
    "merge_readiness": ("reviewer_attestation", "closure_evidence"),
    "delivery_gate": ("merge_readiness",),
    "rejection_recovery": ("delivery_gate",),
    "audit_replay": ("rejection_recovery",),
}
REVIEWER_ARTIFACT_SAFETY_CAVEAT = "artifact-based static review only; no provider/model/browser/shell execution is implied"
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



def runtime_worker_reviewer_attestation_payload(*, reviewer_artifact: str, expected_marker: str, out: str, attestation_format: str, project_root: Path) -> dict[str, Any]:
    if attestation_format not in {"json", "text"}:
        raise RuntimeFoundationError("runtime_worker_reviewer_attestation_format_invalid", f"Unsupported reviewer attestation format: {attestation_format}")
    output_path = _safe_output_path(out, project_root, "runtime_worker_reviewer_attestation")
    artifact_path = _safe_input_path(reviewer_artifact, project_root, "runtime_worker_reviewer_artifact")
    parsed = _load_reviewer_artifact(artifact_path, expected_marker)
    artifact_source = _artifact_source(artifact_path, project_root)
    attestation = {
        "ok": True,
        "command": "runtime worker-result reviewer-attestation",
        "kind": "runtime_worker_reviewer_attestation_packet",
        "schema_version": SCHEMA_VERSION,
        "packet_marker": REVIEWER_ATTESTATION_PACKET_MARKER,
        "artifact_path": artifact_source["path"],
        "sha256": artifact_source["sha256"],
        "byte_count": artifact_source["bytes"],
        "reviewer_artifact_source": artifact_source,
        "verdict": parsed["verdict"],
        "marker": parsed["marker"],
        "review_type": parsed["review_type"],
        "review_caveat": parsed["review_caveat"],
        "findings_summary": parsed["findings_summary"],
        "reviewed_artifacts": parsed["reviewed_artifacts"],
        "reviewed_bundle_summary": parsed["reviewed_bundle_summary"],
        "safety_caveat": parsed["safety_caveat"],
        "reviewer_attestation_present": True,
        "invocation_allowed": False,
        "external_execution_refused": True,
        "external_execution_allowed": False,
        "external_execution_enabled": False,
        "provider_calls": False,
        "model_calls": False,
        "browser_calls": False,
        "shell_calls": False,
        "validation_commands": _worker_validation_commands(),
        "safety_boundaries": dict(WORKER_SAFETY_BOUNDARIES),
        "output_path": _project_relative(output_path, project_root),
        "attestation_format": attestation_format,
        "written": True,
    }
    if attestation_format == "json":
        _write_json(output_path, attestation)
    else:
        _write_text(output_path, _format_reviewer_attestation_text(attestation))
    return attestation


def runtime_worker_closure_evidence_payload(*, reviewer_attestation: str, out: str, evidence_format: str, project_root: Path) -> dict[str, Any]:
    if evidence_format not in {"json", "text"}:
        raise RuntimeFoundationError("runtime_worker_closure_evidence_format_invalid", f"Unsupported closure evidence format: {evidence_format}")
    output_path = _safe_output_path(out, project_root, "runtime_worker_closure_evidence")
    attestation_path = _safe_input_path(reviewer_attestation, project_root, "runtime_worker_closure_evidence_attestation")
    attestation = _load_input_json(attestation_path, "runtime_worker_closure_evidence_attestation")
    _validate_reviewer_attestation_packet(attestation, "runtime_worker_closure_evidence_attestation")
    evidence = {
        "ok": True,
        "command": "runtime worker-result closure-evidence",
        "kind": "runtime_worker_closure_evidence",
        "schema_version": SCHEMA_VERSION,
        "marker": CLOSURE_EVIDENCE_IMPORTED_MARKER,
        "closure_evidence_imported": True,
        "audit_replayable": True,
        "gate_readable": True,
        "reviewer_attestation_present": True,
        "reviewer_attestation_source": _artifact_source(attestation_path, project_root),
        "reviewer_artifact_source": attestation["reviewer_artifact_source"],
        "verdict": attestation["verdict"],
        "review_marker": attestation["marker"],
        "review_type": attestation["review_type"],
        "findings_summary": attestation["findings_summary"],
        "reviewed_artifacts": list(attestation["reviewed_artifacts"]),
        "reviewed_bundle_summary": attestation["reviewed_bundle_summary"],
        "safety_caveat": attestation["safety_caveat"],
        "invocation_allowed": False,
        "external_execution_refused": True,
        "external_execution_allowed": False,
        "external_execution_enabled": False,
        "provider_calls": False,
        "model_calls": False,
        "browser_calls": False,
        "shell_calls": False,
        "validation_commands": _worker_validation_commands(),
        "safety_boundaries": dict(WORKER_SAFETY_BOUNDARIES),
        "output_path": _project_relative(output_path, project_root),
        "evidence_format": evidence_format,
        "written": True,
    }
    if evidence_format == "json":
        _write_json(output_path, evidence)
    else:
        _write_text(output_path, _format_closure_evidence_text(evidence))
    return evidence


def runtime_worker_merge_readiness_payload(
    *,
    delivery_bundle: str,
    reviewer_attestation: str,
    closure_evidence: str,
    baseline: str,
    source_branch: str,
    source_head: str,
    target_branch: str,
    out: str,
    readiness_format: str,
    project_root: Path,
) -> dict[str, Any]:
    if readiness_format not in {"json", "text"}:
        raise RuntimeFoundationError("runtime_worker_merge_readiness_format_invalid", f"Unsupported merge readiness format: {readiness_format}")
    output_path = _safe_output_path(out, project_root, "runtime_worker_merge_readiness")
    delivery_path = _safe_input_path(delivery_bundle, project_root, "runtime_worker_merge_readiness_delivery_bundle")
    attestation_path = _safe_input_path(reviewer_attestation, project_root, "runtime_worker_merge_readiness_attestation")
    evidence_path = _safe_input_path(closure_evidence, project_root, "runtime_worker_merge_readiness_closure_evidence")
    delivery = _load_input_json(delivery_path, "runtime_worker_merge_readiness_delivery_bundle")
    attestation = _load_input_json(attestation_path, "runtime_worker_merge_readiness_attestation")
    evidence = _load_input_json(evidence_path, "runtime_worker_merge_readiness_closure_evidence")
    _validate_worker_delivery_bundle_for_merge(delivery)
    _validate_reviewer_attestation_packet(attestation, "runtime_worker_merge_readiness_attestation")
    _validate_closure_evidence_packet(evidence, attestation_path, project_root)

    replay_summary = delivery.get("replay_summary", {})
    audit_summary = delivery.get("audit_closure_summary", {})
    external_worker_replay_ready = bool(replay_summary.get("replay_ready"))
    audit_closure_ready = bool(audit_summary.get("governance_ready")) and bool(audit_summary.get("replay_ready"))
    delivery_bundle_ready = bool(delivery.get("delivery_ready")) and bool(delivery.get("reviewer_ready"))
    reviewer_attestation_present = bool(attestation.get("reviewer_attestation_present"))
    closure_evidence_imported = bool(evidence.get("closure_evidence_imported"))
    closure_evidence_gate_readable = bool(evidence.get("gate_readable"))
    closure_evidence_audit_replayable = bool(evidence.get("audit_replayable"))
    safety_false = all(
        item is False
        for item in (
            delivery.get("worker_gate_summary", {}).get("provider_calls"),
            delivery.get("worker_gate_summary", {}).get("model_calls"),
            delivery.get("worker_gate_summary", {}).get("browser_calls"),
            delivery.get("worker_gate_summary", {}).get("shell_calls"),
            attestation.get("provider_calls"),
            attestation.get("model_calls"),
            attestation.get("browser_calls"),
            attestation.get("shell_calls"),
            evidence.get("provider_calls"),
            evidence.get("model_calls"),
            evidence.get("browser_calls"),
            evidence.get("shell_calls"),
        )
    )
    blockers: list[str] = []
    if not external_worker_replay_ready:
        blockers.append("external_worker_replay_not_ready")
    if not audit_closure_ready:
        blockers.append("audit_closure_not_ready")
    if not reviewer_attestation_present:
        blockers.append("reviewer_attestation_missing")
    if str(attestation.get("verdict", "")).lower() != "pass":
        blockers.append("reviewer_verdict_not_pass")
    if not closure_evidence_imported:
        blockers.append("closure_evidence_not_imported")
    if not closure_evidence_gate_readable:
        blockers.append("closure_evidence_not_gate_readable")
    if not delivery_bundle_ready:
        blockers.append("delivery_bundle_not_ready")
    if delivery.get("invocation_packet_summary", {}).get("invocation_allowed") is not False:
        blockers.append("invocation_not_refused")
    if not safety_false:
        blockers.append("static_safety_calls_not_false")

    ready = not blockers
    packet = {
        "ok": True,
        "command": "runtime worker-result merge-readiness",
        "kind": "runtime_worker_merge_readiness_packet",
        "schema_version": SCHEMA_VERSION,
        "marker": MERGE_READINESS_PACKET_MARKER,
        "baseline": baseline,
        "source_branch": source_branch,
        "source_head": source_head,
        "target_branch": target_branch,
        "delivery_bundle_source": _artifact_source(delivery_path, project_root),
        "reviewer_attestation_source": _artifact_source(attestation_path, project_root),
        "closure_evidence_source": _artifact_source(evidence_path, project_root),
        "external_worker_replay_ready": external_worker_replay_ready,
        "audit_closure_ready": audit_closure_ready,
        "reviewer_attestation_present": reviewer_attestation_present,
        "closure_evidence_imported": closure_evidence_imported,
        "closure_evidence_gate_readable": closure_evidence_gate_readable,
        "closure_evidence_audit_replayable": closure_evidence_audit_replayable,
        "delivery_bundle_ready": delivery_bundle_ready,
        "merge_readiness_ready": ready,
        "readiness_blocking_reasons": blockers,
        "invocation_allowed": False,
        "external_execution_refused": True,
        "external_execution_allowed": False,
        "external_execution_enabled": False,
        "provider_calls": False,
        "model_calls": False,
        "browser_calls": False,
        "shell_calls": False,
        "validation_commands": _worker_validation_commands(),
        "next_action": "safe delivery" if ready else "stop",
        "safety_boundaries": dict(WORKER_SAFETY_BOUNDARIES),
        "output_path": _project_relative(output_path, project_root),
        "readiness_format": readiness_format,
        "written": True,
    }
    if readiness_format == "json":
        _write_json(output_path, packet)
    else:
        _write_text(output_path, _format_merge_readiness_text(packet))
    return packet




def runtime_worker_delivery_gate_payload(*, merge_readiness: str, out: str, gate_format: str, project_root: Path) -> dict[str, Any]:
    if gate_format not in {"json", "text"}:
        raise RuntimeFoundationError("runtime_worker_delivery_gate_format_invalid", f"Unsupported delivery gate format: {gate_format}")
    output_path = _safe_output_path(out, project_root, "runtime_worker_delivery_gate")
    readiness_path = _safe_input_path(merge_readiness, project_root, "runtime_worker_delivery_gate_merge_readiness")
    readiness = _load_input_json(readiness_path, "runtime_worker_delivery_gate_merge_readiness")
    _validate_merge_readiness_packet(readiness, "runtime_worker_delivery_gate_merge_readiness")
    reasons = _delivery_gate_rejection_reasons(readiness)
    gate_pass = not reasons
    packet = {
        "ok": True,
        "command": "runtime worker-result delivery-gate",
        "kind": "runtime_worker_delivery_gate_summary",
        "schema_version": SCHEMA_VERSION,
        "marker": DELIVERY_GATE_PACKET_MARKER,
        "merge_readiness_source": _artifact_source(readiness_path, project_root),
        "baseline": str(readiness.get("baseline", "")),
        "source_branch": str(readiness.get("source_branch", "")),
        "source_head": str(readiness.get("source_head", "")),
        "target_branch": str(readiness.get("target_branch", "")),
        "reviewer_attestation_present": bool(readiness.get("reviewer_attestation_present")),
        "closure_evidence_imported": bool(readiness.get("closure_evidence_imported")),
        "closure_evidence_gate_readable": bool(readiness.get("closure_evidence_gate_readable")),
        "external_worker_replay_ready": bool(readiness.get("external_worker_replay_ready")),
        "audit_closure_ready": bool(readiness.get("audit_closure_ready")),
        "delivery_bundle_ready": bool(readiness.get("delivery_bundle_ready")),
        "merge_readiness_ready": bool(readiness.get("merge_readiness_ready")),
        "invocation_allowed": bool(readiness.get("invocation_allowed")),
        "external_execution_refused": bool(readiness.get("external_execution_refused")),
        "provider_calls": bool(readiness.get("provider_calls")),
        "model_calls": bool(readiness.get("model_calls")),
        "browser_calls": bool(readiness.get("browser_calls")),
        "shell_calls": bool(readiness.get("shell_calls")),
        "delivery_gate_pass": gate_pass,
        "gate_status": "pass" if gate_pass else "rejected",
        "rejection_reasons": reasons,
        "next_required_evidence": _next_required_evidence(reasons),
        "recovery_guidance": _recovery_guidance(reasons),
        "next_action": "safe delivery" if gate_pass else "recover required evidence",
        "validation_commands": _worker_validation_commands(),
        "safety_boundaries": dict(WORKER_SAFETY_BOUNDARIES),
        "output_path": _project_relative(output_path, project_root),
        "gate_format": gate_format,
        "written": True,
    }
    if gate_format == "json":
        _write_json(output_path, packet)
    else:
        _write_text(output_path, _format_delivery_gate_text(packet))
    return packet


def runtime_worker_rejection_packet_payload(*, delivery_gate: str, out: str, rejection_format: str, project_root: Path) -> dict[str, Any]:
    if rejection_format not in {"json", "text"}:
        raise RuntimeFoundationError("runtime_worker_rejection_packet_format_invalid", f"Unsupported rejection packet format: {rejection_format}")
    output_path = _safe_output_path(out, project_root, "runtime_worker_rejection_packet")
    gate_path = _safe_input_path(delivery_gate, project_root, "runtime_worker_rejection_packet_delivery_gate")
    gate = _load_input_json(gate_path, "runtime_worker_rejection_packet_delivery_gate")
    _validate_delivery_gate_packet(gate, "runtime_worker_rejection_packet_delivery_gate")
    rejected = not bool(gate.get("delivery_gate_pass"))
    reasons = list(gate.get("rejection_reasons") or [])
    packet = {
        "ok": True,
        "command": "runtime worker-result rejection-packet",
        "kind": "runtime_worker_rejection_recovery_packet",
        "schema_version": SCHEMA_VERSION,
        "marker": REJECTION_RECOVERY_PACKET_MARKER,
        "delivery_gate_source": _artifact_source(gate_path, project_root),
        "original_readiness": bool(gate.get("delivery_gate_pass")),
        "rejected": rejected,
        "rejection_reasons": reasons,
        "next_required_evidence": _next_required_evidence(reasons),
        "recovery_guidance": _recovery_guidance(reasons),
        "recovery_status": "blocked_until_evidence_fixed" if rejected else "not_required",
        "rerun_command": "runtime worker-result delivery-gate after fixed closure evidence and merge-readiness are regenerated" if rejected else "none",
        "replay_ready": True,
        "governance_ready": not rejected,
        "invocation_allowed": False,
        "external_execution_refused": True,
        "provider_calls": False,
        "model_calls": False,
        "browser_calls": False,
        "shell_calls": False,
        "validation_commands": _worker_validation_commands(),
        "safety_boundaries": dict(WORKER_SAFETY_BOUNDARIES),
        "output_path": _project_relative(output_path, project_root),
        "rejection_format": rejection_format,
        "written": True,
    }
    if rejection_format == "json":
        _write_json(output_path, packet)
    else:
        _write_text(output_path, _format_rejection_packet_text(packet))
    return packet


def runtime_worker_audit_replay_payload(*, packet: str, out: str | None = None, replay_format: str = "json", project_root: Path) -> dict[str, Any]:
    if replay_format not in {"json", "text"}:
        raise RuntimeFoundationError("runtime_worker_audit_replay_format_invalid", f"Unsupported audit replay format: {replay_format}")
    packet_path = _safe_input_path(packet, project_root, "runtime_worker_audit_replay_packet")
    source = _load_input_json(packet_path, "runtime_worker_audit_replay_packet")
    summary = _audit_replay_summary(source)
    payload = {
        "ok": True,
        "command": "runtime worker-result audit-replay",
        "kind": "runtime_worker_audit_packet_replay",
        "schema_version": SCHEMA_VERSION,
        "marker": AUDIT_PACKET_REPLAY_MARKER,
        "packet_source": _artifact_source(packet_path, project_root),
        "packet_kind": str(source.get("kind", "")),
        "original_readiness": summary["original_readiness"],
        "rejection_reasons": summary["rejection_reasons"],
        "recovery_status": summary["recovery_status"],
        "replay_ready": summary["replay_ready"],
        "governance_ready": summary["governance_ready"],
        "invocation_allowed": False,
        "external_execution_refused": True,
        "provider_calls": False,
        "model_calls": False,
        "browser_calls": False,
        "shell_calls": False,
        "safety_boundaries": dict(WORKER_SAFETY_BOUNDARIES),
        "written": False,
    }
    if out:
        output_path = _safe_output_path(out, project_root, "runtime_worker_audit_replay")
        payload["output_path"] = _project_relative(output_path, project_root)
        payload["replay_format"] = replay_format
        payload["written"] = True
        if replay_format == "json":
            _write_json(output_path, payload)
        else:
            _write_text(output_path, format_runtime_payload(payload))
    return payload


def runtime_worker_provenance_manifest_payload(
    *,
    reviewer_attestation: str,
    closure_evidence: str,
    merge_readiness: str,
    delivery_gate: str,
    rejection_packet: str,
    audit_replay: str,
    out: str,
    manifest_format: str,
    project_root: Path,
) -> dict[str, Any]:
    if manifest_format not in {"json", "text"}:
        raise RuntimeFoundationError("runtime_worker_provenance_manifest_format_invalid", f"Unsupported provenance manifest format: {manifest_format}")
    output_path = _safe_output_path(out, project_root, "runtime_worker_provenance_manifest")
    inputs = {
        "reviewer_attestation": reviewer_attestation,
        "closure_evidence": closure_evidence,
        "merge_readiness": merge_readiness,
        "delivery_gate": delivery_gate,
        "rejection_recovery": rejection_packet,
        "audit_replay": audit_replay,
    }
    payloads: dict[str, dict[str, Any]] = {}
    artifacts: list[dict[str, Any]] = []
    for role in PROVENANCE_REQUIRED_ROLE_ORDER:
        source_path = _safe_input_path(inputs[role], project_root, f"runtime_worker_provenance_{role}")
        payload = _load_input_json(source_path, f"runtime_worker_provenance_{role}")
        _validate_provenance_payload_shape(role, payload, f"runtime_worker_provenance_{role}")
        payloads[role] = payload
        artifacts.append(_provenance_artifact_entry(role, source_path, payload, project_root))
    linkage_reasons = _provenance_source_linkage_reasons(payloads, artifacts)
    if linkage_reasons:
        raise RuntimeFoundationError("runtime_worker_provenance_manifest_parent_linkage_invalid", "; ".join(linkage_reasons))
    readiness_summary = _provenance_readiness_summary(payloads)
    manifest = {
        "ok": True,
        "command": "runtime worker-result provenance-manifest",
        "kind": "runtime_worker_provenance_manifest",
        "schema_version": SCHEMA_VERSION,
        "marker": PROVENANCE_MANIFEST_MARKER,
        "generated_at": "deterministic-static-v1",
        "chain_root": PROVENANCE_REQUIRED_ROLE_ORDER[0],
        "terminal_artifact": PROVENANCE_REQUIRED_ROLE_ORDER[-1],
        "terminal_readiness_required": True,
        "required_role_order": list(PROVENANCE_REQUIRED_ROLE_ORDER),
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "readiness_summary": readiness_summary,
        "invocation_allowed": False,
        "external_execution_refused": True,
        "provider_calls": False,
        "model_calls": False,
        "browser_calls": False,
        "shell_calls": False,
        "validation_commands": _worker_validation_commands(),
        "safety_boundaries": dict(WORKER_SAFETY_BOUNDARIES),
        "output_path": _project_relative(output_path, project_root),
        "manifest_format": manifest_format,
        "written": True,
    }
    if manifest_format == "json":
        _write_json(output_path, manifest)
    else:
        _write_text(output_path, _format_provenance_manifest_text(manifest))
    return manifest


def runtime_worker_provenance_verify_payload(*, manifest: str, project_root: Path) -> dict[str, Any]:
    manifest_path = _safe_input_path(manifest, project_root, "runtime_worker_provenance_manifest")
    manifest_payload = _load_input_json(manifest_path, "runtime_worker_provenance_manifest")
    return _verify_provenance_manifest(manifest_payload, manifest_path, project_root, command="runtime worker-result provenance-verify")


def runtime_worker_provenance_replay_payload(*, manifest: str, project_root: Path) -> dict[str, Any]:
    manifest_path = _safe_input_path(manifest, project_root, "runtime_worker_provenance_manifest")
    manifest_payload = _load_input_json(manifest_path, "runtime_worker_provenance_manifest")
    verification = _verify_provenance_manifest(manifest_payload, manifest_path, project_root, command="runtime worker-result provenance-verify")
    summary = verification["readiness_summary"]
    chain_ready = bool(verification["chain_valid"])
    return {
        "ok": True,
        "command": "runtime worker-result provenance-replay",
        "kind": "runtime_worker_provenance_replay",
        "schema_version": SCHEMA_VERSION,
        "marker": PROVENANCE_REPLAY_MARKER,
        "manifest_source": _artifact_source(manifest_path, project_root),
        "chain_replay_ready": chain_ready,
        "artifact_integrity_valid": bool(verification["artifact_integrity_valid"]),
        "parent_linkage_valid": bool(verification["parent_linkage_valid"]),
        "role_order_valid": bool(verification["role_order_valid"]),
        "readiness_predicates_valid": bool(verification["readiness_predicates_valid"]),
        "original_readiness": bool(summary.get("terminal_readiness")) if chain_ready else False,
        "delivery_gate_pass": bool(summary.get("delivery_gate_pass")),
        "rejection_reasons": list(summary.get("rejection_reasons") or verification["rejection_reasons"]),
        "recovery_status": str(summary.get("recovery_status", "unknown")) if chain_ready else "blocked_until_chain_fixed",
        "replay_ready": bool(summary.get("audit_replay_ready")) if chain_ready else False,
        "governance_ready": bool(summary.get("governance_ready")) if chain_ready else False,
        "chain_verification": {
            "chain_valid": verification["chain_valid"],
            "rejection_reasons": verification["rejection_reasons"],
            "recovery_guidance": verification["recovery_guidance"],
        },
        "recovery_guidance": verification["recovery_guidance"],
        "invocation_allowed": False,
        "external_execution_refused": True,
        "provider_calls": False,
        "model_calls": False,
        "browser_calls": False,
        "shell_calls": False,
        "safety_boundaries": dict(WORKER_SAFETY_BOUNDARIES),
    }



def runtime_worker_release_candidate_payload(*, provenance_manifest: str, out: str, package_format: str, review_target: str, project_root: Path) -> dict[str, Any]:
    if package_format not in {"json", "text"}:
        raise RuntimeFoundationError("runtime_worker_release_candidate_format_invalid", f"Unsupported release candidate format: {package_format}")
    output_path = _safe_output_path(out, project_root, "runtime_worker_release_candidate")
    manifest_path = _safe_input_path(provenance_manifest, project_root, "runtime_worker_release_candidate_provenance_manifest")
    manifest = _load_input_json(manifest_path, "runtime_worker_release_candidate_provenance_manifest")
    verification = _verify_provenance_manifest(manifest, manifest_path, project_root, command="runtime worker-result provenance-verify")
    if not verification["chain_valid"]:
        raise RuntimeFoundationError("runtime_worker_release_candidate_provenance_not_ready", "Provenance manifest is not release-candidate ready: " + ", ".join(verification["rejection_reasons"]))
    replay = runtime_worker_provenance_replay_payload(manifest=provenance_manifest, project_root=project_root)
    included_artifacts = _release_candidate_included_artifacts(manifest, manifest_path, project_root)
    package = {
        "ok": True,
        "command": "runtime worker-result release-candidate",
        "kind": "runtime_worker_release_candidate_package",
        "schema_version": SCHEMA_VERSION,
        "marker": RELEASE_CANDIDATE_PACKAGE_MARKER,
        "generated_at": "deterministic-static-v1",
        "review_target": str(review_target).strip() or "AgentOffice static release candidate",
        "chain_root": manifest["chain_root"],
        "terminal_artifact": manifest["terminal_artifact"],
        "provenance_manifest_source": _artifact_source(manifest_path, project_root),
        "included_artifacts": included_artifacts,
        "artifact_count": len(included_artifacts),
        "tamper_evident_replay_summary": _release_candidate_replay_summary(replay),
        "archive_ready": bool(replay["chain_replay_ready"]),
        "replay_ready": bool(replay["replay_ready"]),
        "governance_ready": bool(replay["governance_ready"]),
        "invocation_allowed": False,
        "external_execution_refused": True,
        "provider_calls": False,
        "model_calls": False,
        "browser_calls": False,
        "shell_calls": False,
        "validation_commands": _worker_validation_commands(),
        "safety_boundaries": dict(WORKER_SAFETY_BOUNDARIES),
        "output_path": _project_relative(output_path, project_root),
        "package_format": package_format,
        "written": True,
    }
    if package_format == "json":
        _write_json(output_path, package)
    else:
        _write_text(output_path, _format_release_candidate_text(package))
    return package


def runtime_worker_external_review_handoff_payload(
    *,
    release_candidate: str,
    out: str,
    handoff_format: str,
    review_target: str,
    expected_marker: str,
    attestation_import_path: str,
    project_root: Path,
) -> dict[str, Any]:
    if handoff_format not in {"json", "text"}:
        raise RuntimeFoundationError("runtime_worker_external_review_handoff_format_invalid", f"Unsupported external review handoff format: {handoff_format}")
    marker = str(expected_marker).strip()
    if not marker:
        raise RuntimeFoundationError("runtime_worker_external_review_handoff_marker_required", "Expected reviewer output marker is required.")
    output_path = _safe_output_path(out, project_root, "runtime_worker_external_review_handoff")
    attestation_path = _safe_output_path(attestation_import_path, project_root, "runtime_worker_external_review_handoff_attestation")
    package_path = _safe_input_path(release_candidate, project_root, "runtime_worker_external_review_handoff_release_candidate")
    package = _load_input_json(package_path, "runtime_worker_external_review_handoff_release_candidate")
    _validate_release_candidate_package(package, "runtime_worker_external_review_handoff_release_candidate")
    target = str(review_target).strip() or str(package.get("review_target", "AgentOffice static release candidate"))
    handoff = {
        "ok": True,
        "command": "runtime worker-result external-review-handoff",
        "kind": "runtime_worker_external_review_handoff",
        "schema_version": SCHEMA_VERSION,
        "marker": EXTERNAL_REVIEW_HANDOFF_MARKER,
        "generated_at": "deterministic-static-v1",
        "review_target": target,
        "release_candidate_source": _artifact_source(package_path, project_root),
        "artifact_chain_root": package["chain_root"],
        "terminal_artifact": package["terminal_artifact"],
        "included_evidence": list(package["included_artifacts"]),
        "integrity_verification_instructions": [
            f"Run: python3 -m agent_office runtime worker-result archive-verify --index <archive-index.json> --json",
            f"Run: python3 -m agent_office runtime worker-result provenance-verify --manifest {package['provenance_manifest_source']['path']} --json",
        ],
        "replay_instructions": [
            f"Run: python3 -m agent_office runtime worker-result provenance-replay --manifest {package['provenance_manifest_source']['path']} --json",
            "Do not claim VPS command execution unless you actually ran those commands.",
        ],
        "known_safety_caveat": "External reviewer handoff is artifact-only; reviewer must not claim VPS validation unless they actually executed it.",
        "expected_reviewer_output_marker": marker,
        "attestation_import_path": _project_relative(attestation_path, project_root),
        "archive_ready": bool(package["archive_ready"]),
        "replay_ready": bool(package["replay_ready"]),
        "invocation_allowed": False,
        "external_execution_refused": True,
        "provider_calls": False,
        "model_calls": False,
        "browser_calls": False,
        "shell_calls": False,
        "safety_boundaries": dict(WORKER_SAFETY_BOUNDARIES),
        "output_path": _project_relative(output_path, project_root),
        "handoff_format": handoff_format,
        "written": True,
    }
    if handoff_format == "json":
        _write_json(output_path, handoff)
    else:
        _write_text(output_path, _format_external_review_handoff_text(handoff))
    return handoff


def runtime_worker_archive_index_payload(*, release_candidate: str, external_review_handoff: str, out: str, index_format: str, project_root: Path) -> dict[str, Any]:
    if index_format not in {"json", "text"}:
        raise RuntimeFoundationError("runtime_worker_archive_index_format_invalid", f"Unsupported archive index format: {index_format}")
    output_path = _safe_output_path(out, project_root, "runtime_worker_archive_index")
    package_path = _safe_input_path(release_candidate, project_root, "runtime_worker_archive_index_release_candidate")
    handoff_path = _safe_input_path(external_review_handoff, project_root, "runtime_worker_archive_index_external_review_handoff")
    package = _load_input_json(package_path, "runtime_worker_archive_index_release_candidate")
    handoff = _load_input_json(handoff_path, "runtime_worker_archive_index_external_review_handoff")
    _validate_release_candidate_package(package, "runtime_worker_archive_index_release_candidate")
    _validate_external_review_handoff(handoff, package, "runtime_worker_archive_index_external_review_handoff")
    records = _archive_index_records(package_path, package, handoff_path, handoff, project_root)
    archive_ready = all(record["archive_ready"] for record in records)
    replay_ready = all(record["replay_ready"] for record in records)
    index = {
        "ok": True,
        "command": "runtime worker-result archive-index",
        "kind": "runtime_worker_evidence_archive_index",
        "schema_version": SCHEMA_VERSION,
        "marker": EVIDENCE_ARCHIVE_INDEX_MARKER,
        "generated_at": "deterministic-static-v1",
        "required_roles": list(ARCHIVE_REQUIRED_ROLES),
        "record_count": len(records),
        "records": records,
        "release_candidate_source": _artifact_source(package_path, project_root),
        "external_review_handoff_source": _artifact_source(handoff_path, project_root),
        "archive_ready": archive_ready,
        "replay_ready": replay_ready,
        "invocation_allowed": False,
        "external_execution_refused": True,
        "provider_calls": False,
        "model_calls": False,
        "browser_calls": False,
        "shell_calls": False,
        "safety_boundaries": dict(WORKER_SAFETY_BOUNDARIES),
        "output_path": _project_relative(output_path, project_root),
        "index_format": index_format,
        "written": True,
    }
    if index_format == "json":
        _write_json(output_path, index)
    else:
        _write_text(output_path, _format_archive_index_text(index))
    return index


def runtime_worker_archive_verify_payload(*, index: str, project_root: Path) -> dict[str, Any]:
    index_path = _safe_input_path(index, project_root, "runtime_worker_archive_index")
    index_payload = _load_input_json(index_path, "runtime_worker_archive_index")
    return _verify_archive_index(index_payload, index_path, project_root)


def runtime_worker_reviewer_archive_import_payload(
    *,
    reviewer_output: str,
    archive_index: str,
    expected_marker: str,
    out: str,
    import_format: str,
    project_root: Path,
) -> dict[str, Any]:
    if import_format not in {"json", "text"}:
        raise RuntimeFoundationError("runtime_worker_reviewer_archive_import_format_invalid", f"Unsupported reviewer import format: {import_format}")
    marker = str(expected_marker).strip()
    if not marker:
        raise RuntimeFoundationError("runtime_worker_reviewer_archive_import_marker_required", "Expected reviewer output marker is required.")
    output_path = _safe_output_path(out, project_root, "runtime_worker_reviewer_archive_import")
    reviewer_path = _safe_input_path(reviewer_output, project_root, "runtime_worker_reviewer_archive_import_reviewer_output")
    archive_path = _safe_input_path(archive_index, project_root, "runtime_worker_reviewer_archive_import_archive_index")
    archive_payload = _load_input_json(archive_path, "runtime_worker_reviewer_archive_import_archive_index")
    archive_verification = _verify_archive_index(archive_payload, archive_path, project_root)
    if not archive_verification["archive_valid"]:
        raise RuntimeFoundationError(
            "runtime_worker_reviewer_archive_import_archive_not_ready",
            "Evidence archive index is not ready for reviewer import: " + ", ".join(archive_verification["rejection_reasons"]),
        )
    parsed = _load_reviewer_artifact(reviewer_path, marker)
    reviewer_source = _artifact_source(reviewer_path, project_root)
    verdict = parsed["verdict"]
    review_passed = verdict == "pass"
    archive_record = _archive_record(
        record_id="external_reviewer_import",
        role="external_reviewer_import",
        path=reviewer_source["path"],
        sha256=reviewer_source["sha256"],
        byte_count=reviewer_source["bytes"],
        parents=["external_review_handoff"],
        source_marker=parsed["marker"],
        archive_ready=bool(archive_verification["archive_ready"]),
        replay_ready=bool(archive_verification["replay_ready"] and review_passed),
    )
    payload = {
        "ok": True,
        "command": "runtime worker-result reviewer-archive-import",
        "kind": "runtime_worker_external_reviewer_archive_import",
        "schema_version": SCHEMA_VERSION,
        "marker": EXTERNAL_REVIEW_ARCHIVE_IMPORT_MARKER,
        "generated_at": "deterministic-static-v1",
        "reviewer_output_source": reviewer_source,
        "archive_index_source": _artifact_source(archive_path, project_root),
        "review_verdict": verdict,
        "review_marker": parsed["marker"],
        "review_caveat": parsed["review_caveat"],
        "findings_summary": parsed["findings_summary"],
        "reviewed_artifact_chain": list(parsed["reviewed_artifacts"]),
        "reviewed_bundle_summary": parsed["reviewed_bundle_summary"],
        "safety_caveat": parsed["safety_caveat"],
        "archive_import_record": archive_record,
        "archive_verification_summary": _archive_verification_summary(archive_verification),
        "archive_ready": bool(archive_verification["archive_ready"]),
        "replay_ready": bool(archive_verification["replay_ready"] and review_passed),
        "terminal_status": "review_passed" if review_passed else f"review_{verdict or 'missing'}",
        "promotion_eligible": review_passed,
        "invocation_allowed": False,
        "external_execution_refused": True,
        "provider_calls": False,
        "model_calls": False,
        "browser_calls": False,
        "shell_calls": False,
        "safety_boundaries": dict(WORKER_SAFETY_BOUNDARIES),
        "output_path": _project_relative(output_path, project_root),
        "import_format": import_format,
        "written": True,
    }
    if import_format == "json":
        _write_json(output_path, payload)
    else:
        _write_text(output_path, _format_reviewer_archive_import_text(payload))
    return payload


def runtime_worker_release_closure_payload(
    *,
    release_candidate: str,
    external_review_handoff: str,
    archive_index: str,
    reviewer_import: str,
    provenance_manifest: str,
    out: str,
    closure_format: str,
    project_root: Path,
) -> dict[str, Any]:
    if closure_format not in {"json", "text"}:
        raise RuntimeFoundationError("runtime_worker_release_closure_format_invalid", f"Unsupported release closure format: {closure_format}")
    output_path = _safe_output_path(out, project_root, "runtime_worker_release_closure")
    package_path = _safe_input_path(release_candidate, project_root, "runtime_worker_release_closure_release_candidate")
    handoff_path = _safe_input_path(external_review_handoff, project_root, "runtime_worker_release_closure_external_review_handoff")
    archive_path = _safe_input_path(archive_index, project_root, "runtime_worker_release_closure_archive_index")
    import_path = _safe_input_path(reviewer_import, project_root, "runtime_worker_release_closure_reviewer_import")
    manifest_path = _safe_input_path(provenance_manifest, project_root, "runtime_worker_release_closure_provenance_manifest")
    package = _load_input_json(package_path, "runtime_worker_release_closure_release_candidate")
    handoff = _load_input_json(handoff_path, "runtime_worker_release_closure_external_review_handoff")
    archive_payload = _load_input_json(archive_path, "runtime_worker_release_closure_archive_index")
    import_payload = _load_input_json(import_path, "runtime_worker_release_closure_reviewer_import")
    manifest = _load_input_json(manifest_path, "runtime_worker_release_closure_provenance_manifest")
    _validate_release_candidate_package(package, "runtime_worker_release_closure_release_candidate")
    _validate_external_review_handoff(handoff, package, "runtime_worker_release_closure_external_review_handoff")
    _validate_external_reviewer_import(import_payload, "runtime_worker_release_closure_reviewer_import")
    archive_verification = _verify_archive_index(archive_payload, archive_path, project_root)
    provenance_verification = _verify_provenance_manifest(manifest, manifest_path, project_root, command="runtime worker-result provenance-verify")
    reasons = _release_closure_reasons(package, handoff, archive_verification, import_payload, provenance_verification)
    closure_ready = not reasons
    payload = {
        "ok": True,
        "command": "runtime worker-result release-closure",
        "kind": "runtime_worker_release_closure_bundle",
        "schema_version": SCHEMA_VERSION,
        "marker": RELEASE_CLOSURE_BUNDLE_MARKER,
        "generated_at": "deterministic-static-v1",
        "release_candidate_source": _artifact_source(package_path, project_root),
        "external_review_handoff_source": _artifact_source(handoff_path, project_root),
        "archive_index_source": _artifact_source(archive_path, project_root),
        "reviewer_import_source": _artifact_source(import_path, project_root),
        "provenance_manifest_source": _artifact_source(manifest_path, project_root),
        "closure_status": "closed" if closure_ready else "blocked",
        "review_verdict": import_payload["review_verdict"],
        "review_marker": import_payload["review_marker"],
        "expected_reviewer_output_marker": handoff["expected_reviewer_output_marker"],
        "findings_summary": import_payload["findings_summary"],
        "evidence_chain_status": {
            "archive_valid": bool(archive_verification["archive_valid"]),
            "archive_ready": bool(archive_verification["archive_ready"]),
            "provenance_chain_valid": bool(provenance_verification["chain_valid"]),
            "release_candidate_archive_ready": bool(package["archive_ready"]),
        },
        "replay_status": {
            "archive_replay_ready": bool(archive_verification["replay_ready"]),
            "provenance_replay_ready": bool(package["replay_ready"]),
            "reviewer_import_replay_ready": bool(import_payload["replay_ready"]),
        },
        "safety_predicates": _static_refusal_predicate_summary([package, handoff, archive_payload, import_payload]),
        "rejection_reasons": reasons,
        "required_evidence": _closure_required_evidence(reasons),
        "recovery_guidance": _release_closure_recovery_guidance(reasons),
        "archive_ready": closure_ready,
        "replay_ready": closure_ready,
        "delivery_ready": closure_ready,
        "promotion_ready": closure_ready,
        "next_action": "generate final delivery readiness" if closure_ready else "run failed review recovery loop",
        "invocation_allowed": False,
        "external_execution_refused": True,
        "provider_calls": False,
        "model_calls": False,
        "browser_calls": False,
        "shell_calls": False,
        "safety_boundaries": dict(WORKER_SAFETY_BOUNDARIES),
        "output_path": _project_relative(output_path, project_root),
        "closure_format": closure_format,
        "written": True,
    }
    if closure_format == "json":
        _write_json(output_path, payload)
    else:
        _write_text(output_path, _format_release_closure_text(payload))
    return payload


def runtime_worker_archive_replay_verification_payload(
    *,
    archive_index: str,
    release_candidate: str,
    closure_bundle: str,
    out: str,
    replay_format: str,
    project_root: Path,
) -> dict[str, Any]:
    if replay_format not in {"json", "text"}:
        raise RuntimeFoundationError("runtime_worker_archive_replay_format_invalid", f"Unsupported archive replay format: {replay_format}")
    output_path = _safe_output_path(out, project_root, "runtime_worker_archive_replay")
    archive_path = _safe_input_path(archive_index, project_root, "runtime_worker_archive_replay_archive_index")
    package_path = _safe_input_path(release_candidate, project_root, "runtime_worker_archive_replay_release_candidate")
    closure_path = _safe_input_path(closure_bundle, project_root, "runtime_worker_archive_replay_closure_bundle")
    archive_payload = _load_input_json(archive_path, "runtime_worker_archive_replay_archive_index")
    package = _load_input_json(package_path, "runtime_worker_archive_replay_release_candidate")
    closure = _load_input_json(closure_path, "runtime_worker_archive_replay_closure_bundle")
    archive_verification = _verify_archive_index(archive_payload, archive_path, project_root)
    reasons = list(archive_verification["rejection_reasons"])
    try:
        _validate_release_candidate_package(package, "runtime_worker_archive_replay_release_candidate")
    except RuntimeFoundationError as exc:
        reasons.append(exc.error_code)
    try:
        _validate_release_closure_bundle(closure, "runtime_worker_archive_replay_closure_bundle")
    except RuntimeFoundationError as exc:
        reasons.append(exc.error_code)
    package_source = _artifact_source(package_path, project_root)
    if archive_payload.get("release_candidate_source", {}).get("sha256") != package_source["sha256"]:
        reasons.append("release_candidate_source_mismatch")
    if closure.get("closure_status") != "closed":
        reasons.append("release_closure_not_closed")
    _append_static_refusal_reasons(package, "release_candidate", reasons)
    _append_static_refusal_reasons(closure, "release_closure", reasons)
    reasons = _dedupe_text(reasons)
    valid = not reasons
    payload = {
        "ok": True,
        "command": "runtime worker-result archive-replay",
        "kind": "runtime_worker_archive_replay_verification",
        "schema_version": SCHEMA_VERSION,
        "marker": ARCHIVE_REPLAY_VERIFICATION_MARKER,
        "generated_at": "deterministic-static-v1",
        "archive_index_source": _artifact_source(archive_path, project_root),
        "release_candidate_source": package_source,
        "release_closure_source": _artifact_source(closure_path, project_root),
        "archive_replay_valid": valid,
        "archive_ready": valid and bool(archive_verification["archive_ready"]) and bool(closure.get("archive_ready")),
        "replay_ready": valid and bool(archive_verification["replay_ready"]) and bool(closure.get("replay_ready")),
        "record_count": int(archive_verification["record_count"]),
        "closure_status": str(closure.get("closure_status", "unknown")),
        "review_verdict": str(closure.get("review_verdict", "unknown")),
        "rejection_reasons": reasons,
        "recovery_guidance": _archive_replay_recovery_guidance(reasons),
        "invocation_allowed": False,
        "external_execution_refused": True,
        "provider_calls": False,
        "model_calls": False,
        "browser_calls": False,
        "shell_calls": False,
        "safety_boundaries": dict(WORKER_SAFETY_BOUNDARIES),
        "output_path": _project_relative(output_path, project_root),
        "replay_format": replay_format,
        "written": True,
    }
    if replay_format == "json":
        _write_json(output_path, payload)
    else:
        _write_text(output_path, _format_archive_replay_text(payload))
    return payload


def runtime_worker_final_delivery_readiness_payload(*, closure_bundle: str, archive_replay: str, out: str, readiness_format: str, project_root: Path) -> dict[str, Any]:
    if readiness_format not in {"json", "text"}:
        raise RuntimeFoundationError("runtime_worker_final_delivery_readiness_format_invalid", f"Unsupported final delivery readiness format: {readiness_format}")
    output_path = _safe_output_path(out, project_root, "runtime_worker_final_delivery_readiness")
    closure_path = _safe_input_path(closure_bundle, project_root, "runtime_worker_final_delivery_readiness_closure_bundle")
    replay_path = _safe_input_path(archive_replay, project_root, "runtime_worker_final_delivery_readiness_archive_replay")
    closure = _load_input_json(closure_path, "runtime_worker_final_delivery_readiness_closure_bundle")
    replay = _load_input_json(replay_path, "runtime_worker_final_delivery_readiness_archive_replay")
    reasons: list[str] = []
    try:
        _validate_release_closure_bundle(closure, "runtime_worker_final_delivery_readiness_closure_bundle")
    except RuntimeFoundationError as exc:
        reasons.append(exc.error_code)
    try:
        _validate_archive_replay_verification(replay, "runtime_worker_final_delivery_readiness_archive_replay")
    except RuntimeFoundationError as exc:
        reasons.append(exc.error_code)
    if closure.get("closure_status") != "closed":
        reasons.append("release_closure_not_closed")
    if str(closure.get("review_verdict", "")).lower() != "pass":
        reasons.append(f"reviewer_verdict_not_pass:{closure.get('review_verdict', 'missing')}")
    if replay.get("archive_replay_valid") is not True:
        reasons.append("archive_replay_not_valid")
    if replay.get("archive_ready") is not True:
        reasons.append("archive_not_ready")
    if replay.get("replay_ready") is not True:
        reasons.append("archive_replay_not_ready")
    _append_static_refusal_reasons(closure, "release_closure", reasons)
    _append_static_refusal_reasons(replay, "archive_replay", reasons)
    reasons = _dedupe_text(reasons)
    ready = not reasons
    payload = {
        "ok": True,
        "command": "runtime worker-result final-readiness",
        "kind": "runtime_worker_final_delivery_readiness_packet",
        "schema_version": SCHEMA_VERSION,
        "marker": FINAL_DELIVERY_READINESS_MARKER,
        "generated_at": "deterministic-static-v1",
        "release_closure_source": _artifact_source(closure_path, project_root),
        "archive_replay_source": _artifact_source(replay_path, project_root),
        "delivery_ready": ready,
        "promotion_ready": ready,
        "review_verdict": str(closure.get("review_verdict", "unknown")),
        "closure_status": str(closure.get("closure_status", "unknown")),
        "rejection_reasons": reasons,
        "required_evidence": _final_readiness_required_evidence(reasons),
        "recovery_guidance": _final_readiness_recovery_guidance(reasons),
        "next_action": "run release candidate promotion gate" if ready else "recover failed review or evidence chain",
        "invocation_allowed": False,
        "external_execution_refused": True,
        "provider_calls": False,
        "model_calls": False,
        "browser_calls": False,
        "shell_calls": False,
        "safety_boundaries": dict(WORKER_SAFETY_BOUNDARIES),
        "output_path": _project_relative(output_path, project_root),
        "readiness_format": readiness_format,
        "written": True,
    }
    if readiness_format == "json":
        _write_json(output_path, payload)
    else:
        _write_text(output_path, _format_final_readiness_text(payload))
    return payload


def runtime_worker_failed_review_recovery_payload(*, closure_bundle: str, out: str, recovery_format: str, project_root: Path) -> dict[str, Any]:
    if recovery_format not in {"json", "text"}:
        raise RuntimeFoundationError("runtime_worker_failed_review_recovery_format_invalid", f"Unsupported review recovery format: {recovery_format}")
    output_path = _safe_output_path(out, project_root, "runtime_worker_failed_review_recovery")
    closure_path = _safe_input_path(closure_bundle, project_root, "runtime_worker_failed_review_recovery_closure_bundle")
    closure = _load_input_json(closure_path, "runtime_worker_failed_review_recovery_closure_bundle")
    try:
        _validate_release_closure_bundle(closure, "runtime_worker_failed_review_recovery_closure_bundle")
        reasons = list(closure.get("rejection_reasons", []))
    except RuntimeFoundationError as exc:
        reasons = [exc.error_code]
    recovery_required = bool(reasons) or closure.get("closure_status") != "closed"
    payload = {
        "ok": True,
        "command": "runtime worker-result review-recovery",
        "kind": "runtime_worker_failed_review_recovery_packet",
        "schema_version": SCHEMA_VERSION,
        "marker": FAILED_REVIEW_RECOVERY_MARKER,
        "generated_at": "deterministic-static-v1",
        "release_closure_source": _artifact_source(closure_path, project_root),
        "original_closure_status": str(closure.get("closure_status", "unknown")),
        "original_review_verdict": str(closure.get("review_verdict", "unknown")),
        "recovery_required": recovery_required,
        "recovery_status": "blocked_until_review_or_evidence_fixed" if recovery_required else "not_required",
        "rejection_reasons": _dedupe_text(reasons),
        "required_evidence": _closure_required_evidence(reasons),
        "recovery_path": [
            "Import fixed external reviewer output with the expected marker and verdict PASS.",
            "Regenerate release-closure from the fixed reviewer import and current evidence archive.",
            "Rerun archive-replay and final-readiness.",
            "Run compact-archive, compact-verify, and rc-promotion-gate after readiness passes.",
        ] if recovery_required else ["No recovery required; release closure is already closed."],
        "invocation_allowed": False,
        "external_execution_refused": True,
        "provider_calls": False,
        "model_calls": False,
        "browser_calls": False,
        "shell_calls": False,
        "safety_boundaries": dict(WORKER_SAFETY_BOUNDARIES),
        "output_path": _project_relative(output_path, project_root),
        "recovery_format": recovery_format,
        "written": True,
    }
    if recovery_format == "json":
        _write_json(output_path, payload)
    else:
        _write_text(output_path, _format_review_recovery_text(payload))
    return payload


def runtime_worker_compact_archive_payload(
    *,
    archive_index: str,
    release_closure: str,
    archive_replay: str,
    final_readiness: str,
    out: str,
    compact_format: str,
    project_root: Path,
) -> dict[str, Any]:
    if compact_format not in {"json", "text"}:
        raise RuntimeFoundationError("runtime_worker_compact_archive_format_invalid", f"Unsupported compact archive format: {compact_format}")
    output_path = _safe_output_path(out, project_root, "runtime_worker_compact_archive")
    archive_path = _safe_input_path(archive_index, project_root, "runtime_worker_compact_archive_archive_index")
    closure_path = _safe_input_path(release_closure, project_root, "runtime_worker_compact_archive_release_closure")
    replay_path = _safe_input_path(archive_replay, project_root, "runtime_worker_compact_archive_archive_replay")
    readiness_path = _safe_input_path(final_readiness, project_root, "runtime_worker_compact_archive_final_readiness")
    archive_payload = _load_input_json(archive_path, "runtime_worker_compact_archive_archive_index")
    closure = _load_input_json(closure_path, "runtime_worker_compact_archive_release_closure")
    replay = _load_input_json(replay_path, "runtime_worker_compact_archive_archive_replay")
    readiness = _load_input_json(readiness_path, "runtime_worker_compact_archive_final_readiness")
    _validate_release_closure_bundle(closure, "runtime_worker_compact_archive_release_closure")
    _validate_archive_replay_verification(replay, "runtime_worker_compact_archive_archive_replay")
    _validate_final_delivery_readiness(readiness, "runtime_worker_compact_archive_final_readiness")
    records = _compact_archive_records(archive_payload, closure, closure_path, replay, replay_path, readiness, readiness_path, project_root)
    archive_ready = all(record["archive_ready"] is True for record in records)
    replay_ready = all(record["replay_ready"] is True for record in records)
    payload = {
        "ok": True,
        "command": "runtime worker-result compact-archive",
        "kind": "runtime_worker_compact_evidence_archive_index",
        "schema_version": SCHEMA_VERSION,
        "marker": COMPACT_ARCHIVE_INDEX_MARKER,
        "generated_at": "deterministic-static-v1",
        "required_roles": list(COMPACT_ARCHIVE_REQUIRED_ROLES),
        "record_count": len(records),
        "records": records,
        "archive_index_source": _artifact_source(archive_path, project_root),
        "release_closure_source": _artifact_source(closure_path, project_root),
        "archive_replay_source": _artifact_source(replay_path, project_root),
        "final_readiness_source": _artifact_source(readiness_path, project_root),
        "archive_ready": archive_ready,
        "replay_ready": replay_ready,
        "terminal_status": "ready" if archive_ready and replay_ready and readiness.get("delivery_ready") is True else "blocked",
        "invocation_allowed": False,
        "external_execution_refused": True,
        "provider_calls": False,
        "model_calls": False,
        "browser_calls": False,
        "shell_calls": False,
        "safety_boundaries": dict(WORKER_SAFETY_BOUNDARIES),
        "output_path": _project_relative(output_path, project_root),
        "compact_format": compact_format,
        "written": True,
    }
    if compact_format == "json":
        _write_json(output_path, payload)
    else:
        _write_text(output_path, _format_compact_archive_text(payload))
    return payload


def runtime_worker_compact_archive_verify_payload(*, compact_index: str, project_root: Path) -> dict[str, Any]:
    compact_path = _safe_input_path(compact_index, project_root, "runtime_worker_compact_archive_index")
    compact_payload = _load_input_json(compact_path, "runtime_worker_compact_archive_index")
    return _verify_compact_archive_index(compact_payload, compact_path, project_root)


def runtime_worker_rc_promotion_gate_payload(*, final_readiness: str, compact_index: str, release_closure: str, out: str, gate_format: str, project_root: Path) -> dict[str, Any]:
    if gate_format not in {"json", "text"}:
        raise RuntimeFoundationError("runtime_worker_rc_promotion_gate_format_invalid", f"Unsupported promotion gate format: {gate_format}")
    output_path = _safe_output_path(out, project_root, "runtime_worker_rc_promotion_gate")
    readiness_path = _safe_input_path(final_readiness, project_root, "runtime_worker_rc_promotion_gate_final_readiness")
    compact_path = _safe_input_path(compact_index, project_root, "runtime_worker_rc_promotion_gate_compact_index")
    closure_path = _safe_input_path(release_closure, project_root, "runtime_worker_rc_promotion_gate_release_closure")
    readiness = _load_input_json(readiness_path, "runtime_worker_rc_promotion_gate_final_readiness")
    compact = _load_input_json(compact_path, "runtime_worker_rc_promotion_gate_compact_index")
    closure = _load_input_json(closure_path, "runtime_worker_rc_promotion_gate_release_closure")
    compact_verification = _verify_compact_archive_index(compact, compact_path, project_root)
    reasons = list(compact_verification["rejection_reasons"])
    try:
        _validate_final_delivery_readiness(readiness, "runtime_worker_rc_promotion_gate_final_readiness")
    except RuntimeFoundationError as exc:
        reasons.append(exc.error_code)
    try:
        _validate_release_closure_bundle(closure, "runtime_worker_rc_promotion_gate_release_closure")
    except RuntimeFoundationError as exc:
        reasons.append(exc.error_code)
    if readiness.get("delivery_ready") is not True:
        reasons.append("final_delivery_not_ready")
    if readiness.get("promotion_ready") is not True:
        reasons.append("final_promotion_not_ready")
    if compact_verification.get("compact_valid") is not True:
        reasons.append("compact_archive_not_valid")
    if compact_verification.get("archive_ready") is not True:
        reasons.append("compact_archive_not_ready")
    if compact_verification.get("replay_ready") is not True:
        reasons.append("compact_replay_not_ready")
    if closure.get("closure_status") != "closed":
        reasons.append("release_closure_not_closed")
    _append_static_refusal_reasons(readiness, "final_readiness", reasons)
    _append_static_refusal_reasons(compact, "compact_archive", reasons)
    _append_static_refusal_reasons(closure, "release_closure", reasons)
    reasons = _dedupe_text(reasons)
    promotion_ready = not reasons
    payload = {
        "ok": True,
        "command": "runtime worker-result rc-promotion-gate",
        "kind": "runtime_worker_release_candidate_promotion_gate",
        "schema_version": SCHEMA_VERSION,
        "marker": RC_PROMOTION_GATE_MARKER,
        "generated_at": "deterministic-static-v1",
        "final_readiness_source": _artifact_source(readiness_path, project_root),
        "compact_archive_source": _artifact_source(compact_path, project_root),
        "release_closure_source": _artifact_source(closure_path, project_root),
        "promotion_ready": promotion_ready,
        "delivery_ready": promotion_ready,
        "rejection_reasons": reasons,
        "recovery_guidance": _promotion_recovery_guidance(reasons),
        "next_action": "static promotion packet ready; no release, tag, or default branch change executed" if promotion_ready else "recover final readiness and compact archive evidence",
        "real_release_executed": False,
        "tag_created": False,
        "default_branch_changed": False,
        "invocation_allowed": False,
        "external_execution_refused": True,
        "provider_calls": False,
        "model_calls": False,
        "browser_calls": False,
        "shell_calls": False,
        "safety_boundaries": dict(WORKER_SAFETY_BOUNDARIES),
        "output_path": _project_relative(output_path, project_root),
        "gate_format": gate_format,
        "written": True,
    }
    if gate_format == "json":
        _write_json(output_path, payload)
    else:
        _write_text(output_path, _format_promotion_gate_text(payload))
    return payload


def runtime_worker_release_candidate_export_payload(*, release_candidate: str, archive_index: str, out: str, export_format: str, project_root: Path) -> dict[str, Any]:
    if export_format not in {"json", "text"}:
        raise RuntimeFoundationError("runtime_worker_release_candidate_export_format_invalid", f"Unsupported release candidate export format: {export_format}")
    output_path = _safe_output_path(out, project_root, "runtime_worker_release_candidate_export")
    package_path = _safe_input_path(release_candidate, project_root, "runtime_worker_release_candidate_export_release_candidate")
    archive_path = _safe_input_path(archive_index, project_root, "runtime_worker_release_candidate_export_archive_index")
    package = _load_input_json(package_path, "runtime_worker_release_candidate_export_release_candidate")
    archive_payload = _load_input_json(archive_path, "runtime_worker_release_candidate_export_archive_index")
    _validate_release_candidate_package(package, "runtime_worker_release_candidate_export_release_candidate")
    archive_verification = _verify_archive_index(archive_payload, archive_path, project_root)
    if not archive_verification["archive_valid"]:
        raise RuntimeFoundationError(
            "runtime_worker_release_candidate_export_archive_not_ready",
            "Evidence archive index is not export-ready: " + ", ".join(archive_verification["rejection_reasons"]),
        )
    manifest = {
        "release_candidate_source": _artifact_source(package_path, project_root),
        "archive_index_source": _artifact_source(archive_path, project_root),
        "expected_roles": list(ARCHIVE_REQUIRED_ROLES),
        "record_count": int(archive_verification["record_count"]),
        "records": _release_candidate_export_records(archive_payload),
    }
    digest = _stable_payload_digest(manifest)
    readiness_summary = {
        "release_candidate_archive_ready": bool(package["archive_ready"]),
        "release_candidate_replay_ready": bool(package["replay_ready"]),
        "archive_valid": bool(archive_verification["archive_valid"]),
        "archive_ready": bool(archive_verification["archive_ready"]),
        "replay_ready": bool(archive_verification["replay_ready"]),
        "export_ready": bool(package["archive_ready"] and package["replay_ready"] and archive_verification["archive_ready"] and archive_verification["replay_ready"]),
    }
    payload = {
        "ok": True,
        "command": "runtime worker-result release-candidate-export",
        "kind": "runtime_worker_release_candidate_export_packet",
        "schema_version": SCHEMA_VERSION,
        "marker": RELEASE_CANDIDATE_EXPORT_PACKET_MARKER,
        "generated_at": "deterministic-static-v1",
        "manifest": manifest,
        "manifest_digest": digest,
        "digest": digest,
        "record_count": manifest["record_count"],
        "expected_roles": list(ARCHIVE_REQUIRED_ROLES),
        "readiness_summary": readiness_summary,
        "export_ready": readiness_summary["export_ready"],
        "invocation_allowed": False,
        "external_execution_refused": True,
        "provider_calls": False,
        "model_calls": False,
        "browser_calls": False,
        "shell_calls": False,
        "safety_boundaries": dict(WORKER_SAFETY_BOUNDARIES),
        "output_path": _project_relative(output_path, project_root),
        "export_format": export_format,
        "written": True,
    }
    if export_format == "json":
        _write_json(output_path, payload)
    else:
        _write_text(output_path, _format_release_candidate_export_text(payload))
    return payload


def runtime_worker_promotion_evidence_payload(
    *,
    release_candidate: str,
    archive_index: str,
    release_closure: str,
    archive_replay: str,
    final_readiness: str,
    compact_index: str,
    promotion_gate: str,
    out: str,
    evidence_format: str,
    final_mainline: str,
    project_root: Path,
) -> dict[str, Any]:
    if evidence_format not in {"json", "text"}:
        raise RuntimeFoundationError("runtime_worker_promotion_evidence_format_invalid", f"Unsupported promotion evidence format: {evidence_format}")
    output_path = _safe_output_path(out, project_root, "runtime_worker_promotion_evidence")
    package_path = _safe_input_path(release_candidate, project_root, "runtime_worker_promotion_evidence_release_candidate")
    archive_path = _safe_input_path(archive_index, project_root, "runtime_worker_promotion_evidence_archive_index")
    closure_path = _safe_input_path(release_closure, project_root, "runtime_worker_promotion_evidence_release_closure")
    replay_path = _safe_input_path(archive_replay, project_root, "runtime_worker_promotion_evidence_archive_replay")
    readiness_path = _safe_input_path(final_readiness, project_root, "runtime_worker_promotion_evidence_final_readiness")
    compact_path = _safe_input_path(compact_index, project_root, "runtime_worker_promotion_evidence_compact_index")
    gate_path = _safe_input_path(promotion_gate, project_root, "runtime_worker_promotion_evidence_promotion_gate")
    package = _load_input_json(package_path, "runtime_worker_promotion_evidence_release_candidate")
    archive_payload = _load_input_json(archive_path, "runtime_worker_promotion_evidence_archive_index")
    closure = _load_input_json(closure_path, "runtime_worker_promotion_evidence_release_closure")
    replay = _load_input_json(replay_path, "runtime_worker_promotion_evidence_archive_replay")
    readiness = _load_input_json(readiness_path, "runtime_worker_promotion_evidence_final_readiness")
    compact = _load_input_json(compact_path, "runtime_worker_promotion_evidence_compact_index")
    gate = _load_input_json(gate_path, "runtime_worker_promotion_evidence_promotion_gate")
    _validate_release_candidate_package(package, "runtime_worker_promotion_evidence_release_candidate")
    _validate_release_closure_bundle(closure, "runtime_worker_promotion_evidence_release_closure")
    _validate_archive_replay_verification(replay, "runtime_worker_promotion_evidence_archive_replay")
    _validate_final_delivery_readiness(readiness, "runtime_worker_promotion_evidence_final_readiness")
    _validate_rc_promotion_gate(gate, "runtime_worker_promotion_evidence_promotion_gate")
    archive_verification = _verify_archive_index(archive_payload, archive_path, project_root)
    compact_verification = _verify_compact_archive_index(compact, compact_path, project_root)
    if not archive_verification["archive_valid"]:
        raise RuntimeFoundationError(
            "runtime_worker_promotion_evidence_archive_not_ready",
            "Evidence archive index is not evidence-ready: " + ", ".join(archive_verification["rejection_reasons"]),
        )
    if not compact_verification["compact_valid"]:
        raise RuntimeFoundationError(
            "runtime_worker_promotion_evidence_compact_not_ready",
            "Compact archive index is not evidence-ready: " + ", ".join(compact_verification["rejection_reasons"]),
        )
    merge_readiness = _archive_payload_by_role(compact, "merge_readiness", project_root, "runtime_worker_promotion_evidence")
    reviewed_refs = {
        "source_branch": str(merge_readiness.get("source_branch", "")),
        "source_head": str(merge_readiness.get("source_head", "")),
        "target_branch": str(merge_readiness.get("target_branch", "")),
        "target_before": str(merge_readiness.get("baseline", "")),
        "final_mainline": str(final_mainline).strip() or "not_recorded_static_pre_release",
    }
    evidence_ready = bool(
        closure.get("delivery_ready") is True
        and closure.get("promotion_ready") is True
        and replay.get("archive_replay_valid") is True
        and readiness.get("delivery_ready") is True
        and readiness.get("promotion_ready") is True
        and compact_verification.get("compact_valid") is True
        and gate.get("promotion_ready") is True
    )
    payload = {
        "ok": True,
        "command": "runtime worker-result promotion-evidence",
        "kind": "runtime_worker_promotion_evidence_packet",
        "schema_version": SCHEMA_VERSION,
        "marker": PROMOTION_EVIDENCE_PACKET_MARKER,
        "generated_at": "deterministic-static-v1",
        "reviewed_refs": reviewed_refs,
        "release_candidate_source": _artifact_source(package_path, project_root),
        "archive_index_source": _artifact_source(archive_path, project_root),
        "release_closure_source": _artifact_source(closure_path, project_root),
        "archive_replay_source": _artifact_source(replay_path, project_root),
        "final_readiness_source": _artifact_source(readiness_path, project_root),
        "compact_archive_source": _artifact_source(compact_path, project_root),
        "promotion_gate_source": _artifact_source(gate_path, project_root),
        "release_closure_status": {
            "closure_status": str(closure.get("closure_status", "unknown")),
            "review_verdict": str(closure.get("review_verdict", "unknown")),
            "delivery_ready": bool(closure.get("delivery_ready")),
            "promotion_ready": bool(closure.get("promotion_ready")),
        },
        "archive_replay_status": {
            "archive_replay_valid": bool(replay.get("archive_replay_valid")),
            "archive_ready": bool(replay.get("archive_ready")),
            "replay_ready": bool(replay.get("replay_ready")),
        },
        "compact_archive_terminal_status": {
            "compact_valid": bool(compact_verification.get("compact_valid")),
            "archive_ready": bool(compact_verification.get("archive_ready")),
            "replay_ready": bool(compact_verification.get("replay_ready")),
            "terminal_status": str(compact.get("terminal_status", "unknown")),
            "record_count": int(compact_verification.get("record_count", 0)),
        },
        "promotion_gate_result": {
            "promotion_ready": bool(gate.get("promotion_ready")),
            "delivery_ready": bool(gate.get("delivery_ready")),
            "rejection_reasons": list(gate.get("rejection_reasons", [])),
        },
        "delivery_promotion_readiness": {
            "delivery_ready": evidence_ready,
            "promotion_ready": evidence_ready,
            "evidence_ready": evidence_ready,
        },
        "validation_evidence_references": _worker_validation_commands(),
        "negative_recovery_coverage_references": [
            "review-recovery supports fail -> fixed import -> replay -> readiness pass",
            "archive-verify and compact-verify reject duplicate, missing, malformed, and traversal evidence cleanly",
            "dry-run-publish refuses publish-ready status when promotion evidence is blocked",
        ],
        "safety_boundary_declarations": dict(WORKER_SAFETY_BOUNDARIES),
        "no_real_promotion_proof": _no_real_promotion_proof(),
        "evidence_ready": evidence_ready,
        "promotion_ready": evidence_ready,
        "invocation_allowed": False,
        "external_execution_refused": True,
        "provider_calls": False,
        "model_calls": False,
        "browser_calls": False,
        "shell_calls": False,
        "safety_boundaries": dict(WORKER_SAFETY_BOUNDARIES),
        "output_path": _project_relative(output_path, project_root),
        "evidence_format": evidence_format,
        "written": True,
    }
    if evidence_format == "json":
        _write_json(output_path, payload)
    else:
        _write_text(output_path, _format_promotion_evidence_text(payload))
    return payload


def runtime_worker_dry_run_publish_payload(
    *,
    promotion_evidence: str,
    release_candidate_export: str,
    promotion_gate: str,
    out: str,
    publish_format: str,
    candidate_name: str,
    target_branch: str,
    target_commit: str,
    project_root: Path,
) -> dict[str, Any]:
    if publish_format not in {"json", "text"}:
        raise RuntimeFoundationError("runtime_worker_dry_run_publish_format_invalid", f"Unsupported dry-run publish format: {publish_format}")
    if not str(candidate_name).strip():
        raise RuntimeFoundationError("runtime_worker_dry_run_publish_candidate_name_required", "Candidate release name is required.")
    if not str(target_branch).strip() or not str(target_commit).strip():
        raise RuntimeFoundationError("runtime_worker_dry_run_publish_target_required", "Target branch and target commit are required.")
    output_path = _safe_output_path(out, project_root, "runtime_worker_dry_run_publish")
    evidence_path = _safe_input_path(promotion_evidence, project_root, "runtime_worker_dry_run_publish_promotion_evidence")
    export_path = _safe_input_path(release_candidate_export, project_root, "runtime_worker_dry_run_publish_release_candidate_export")
    gate_path = _safe_input_path(promotion_gate, project_root, "runtime_worker_dry_run_publish_promotion_gate")
    evidence = _load_input_json(evidence_path, "runtime_worker_dry_run_publish_promotion_evidence")
    export = _load_input_json(export_path, "runtime_worker_dry_run_publish_release_candidate_export")
    gate = _load_input_json(gate_path, "runtime_worker_dry_run_publish_promotion_gate")
    _validate_promotion_evidence_packet(evidence, "runtime_worker_dry_run_publish_promotion_evidence")
    _validate_release_candidate_export_packet(export, "runtime_worker_dry_run_publish_release_candidate_export")
    _validate_rc_promotion_gate(gate, "runtime_worker_dry_run_publish_promotion_gate")
    reasons: list[str] = []
    if evidence.get("evidence_ready") is not True:
        reasons.append("promotion_evidence_not_ready")
    if export.get("export_ready") is not True:
        reasons.append("release_candidate_export_not_ready")
    if gate.get("promotion_ready") is not True:
        reasons.append("promotion_gate_not_ready")
    publish_ready = not reasons
    payload = {
        "ok": True,
        "command": "runtime worker-result dry-run-publish",
        "kind": "runtime_worker_dry_run_publish_packet",
        "schema_version": SCHEMA_VERSION,
        "marker": DRY_RUN_PUBLISH_PACKET_MARKER,
        "generated_at": "deterministic-static-v1",
        "target_branch": str(target_branch).strip(),
        "target_commit": str(target_commit).strip(),
        "candidate_release_id": _candidate_release_id(candidate_name, target_commit),
        "candidate_release_name": str(candidate_name).strip(),
        "source_evidence_references": {
            "promotion_evidence": _artifact_source(evidence_path, project_root),
            "release_candidate_export": _artifact_source(export_path, project_root),
            "promotion_gate": _artifact_source(gate_path, project_root),
        },
        "promotion_gate_status": {
            "promotion_ready": bool(gate.get("promotion_ready")),
            "delivery_ready": bool(gate.get("delivery_ready")),
            "rejection_reasons": list(gate.get("rejection_reasons", [])),
        },
        "publish_ready": publish_ready,
        "dry_run_only": True,
        "would_create_tag": False,
        "would_create_release": False,
        "would_push": False,
        "would_change_default_branch": False,
        "required_human_approval_checklist": [
            "Confirm independent review remains PASS for the exact target commit.",
            "Confirm release notes and rollback plan are ready.",
            "Authorize a separate real release/tag/default-branch gate explicitly.",
        ],
        "required_artifacts_before_real_promotion": [
            "promotion evidence packet",
            "release candidate export packet",
            "RC promotion gate packet",
            "operator approval outside this dry-run command",
        ],
        "dry_run_proof": {
            "status": "dry_run_only",
            "exact_command": "python3 -m agent_office runtime worker-result dry-run-publish",
            "real_tag_created": False,
            "real_release_created": False,
            "real_push_executed": False,
            "default_branch_changed": False,
        },
        "rejection_reasons": reasons,
        "invocation_allowed": False,
        "external_execution_refused": True,
        "provider_calls": False,
        "model_calls": False,
        "browser_calls": False,
        "shell_calls": False,
        "safety_boundaries": dict(WORKER_SAFETY_BOUNDARIES),
        "output_path": _project_relative(output_path, project_root),
        "publish_format": publish_format,
        "written": True,
    }
    if publish_format == "json":
        _write_json(output_path, payload)
    else:
        _write_text(output_path, _format_dry_run_publish_text(payload))
    return payload


LOCAL_RUNTIME_MARKER = "AGENTOFFICE_LOCAL_MULTI_AGENT_RUNTIME_V1"
LOCAL_RUNTIME_PACKET_TYPE = "agentoffice_local_multi_agent_runtime_v1"
LOCAL_RUNTIME_CREATED_AT = "deterministic-static-v1"
LOCAL_GOAL_STATUSES = {"pending", "running", "completed", "failed", "skipped", "blocked"}
LOCAL_AGENT_ROLES = {"planner", "scheduler", "executor", "reviewer", "operator"}


def runtime_workspace_payload(*, action: str, workspace: str, run_id: str | None = None, out: str | None = None, project_root: Path) -> dict[str, Any]:
    if action == "init":
        required_run_id = _local_required_id(run_id, "runtime_workspace_run_id_required", "runtime workspace init requires --run-id.")
        workspace_root = _local_workspace_path(workspace, project_root, must_exist=False)
        if workspace_root.exists() and workspace_root.is_symlink():
            raise RuntimeFoundationError("runtime_workspace_symlink_refused", f"Refusing workspace symlink: {workspace}")
        if workspace_root.exists() and not workspace_root.is_dir():
            raise RuntimeFoundationError("runtime_workspace_not_directory", f"Workspace path is not a directory: {workspace}")
        workspace_root.mkdir(parents=True, exist_ok=True)
        paths = _local_workspace_files(workspace_root)
        paths["agent_outputs"].mkdir(parents=True, exist_ok=True)
        paths["reports"].mkdir(parents=True, exist_ok=True)
        _touch_jsonl(paths["memory"])
        ensure_event_log(paths["event_log"])
        if not paths["goal_queue"].exists():
            _write_json(paths["goal_queue"], _local_empty_goal_queue(required_run_id))
        if not paths["scheduler_ledger"].exists():
            _write_json(paths["scheduler_ledger"], _local_empty_ledger("scheduler"))
        if not paths["executor_ledger"].exists():
            _write_json(paths["executor_ledger"], _local_empty_ledger("executor"))
        if not paths["failure_ledger"].exists():
            _write_json(paths["failure_ledger"], {"schema_version": SCHEMA_VERSION, "packet_type": "agentoffice_local_executor_failure_ledger", "failures": []})
        schema = _local_workspace_schema(workspace_root, required_run_id, project_root)
        _write_json(paths["workspace"], schema)
        if not _local_kernel_events(paths, required_run_id):
            append_event(paths["event_log"], run_id=required_run_id, event_type="RUN_CREATED", payload={"workspace": schema["workspace"], "objective": "", "artifact_root": schema["run_root"]})
        return _local_base_payload("runtime workspace init", schema=schema, status="initialized")

    schema, workspace_root, paths = _load_local_workspace(workspace, project_root)
    if action == "inspect":
        return _local_base_payload("runtime workspace inspect", schema=schema, status=_local_status_from_kernel(paths, str(schema["run_id"])))
    if action == "status":
        scheduler = _local_kernel_scheduler(paths, str(schema["run_id"]))
        payload = _local_base_payload("runtime workspace status", schema=schema, status=_local_status_from_scheduler(scheduler))
        payload.update(
            {
                "goal_counts": scheduler["counts"],
                "ready_goal_ids": [goal["goal_id"] for goal in scheduler["ready"]],
                "blocked_goal_ids": [goal["goal_id"] for goal in scheduler["blocked"]],
                "running_goal_ids": [goal["goal_id"] for goal in scheduler["running"]],
                "completed_goal_ids": [goal["goal_id"] for goal in scheduler["completed"]],
                "failed_goal_ids": [goal["goal_id"] for goal in scheduler["failed"]],
                "skipped_goal_ids": [goal["goal_id"] for goal in scheduler["skipped"]],
                "memory_count": len(_local_memory_projection(paths, str(schema["run_id"]))),
                "next_action": scheduler["next_action"],
            }
        )
        return payload
    if action == "report":
        payload = runtime_workspace_payload(action="status", workspace=workspace, project_root=project_root)
        output_path = _local_output_or_default(out, paths["reports"] / "workspace-report.md", project_root, "runtime_workspace_report")
        _write_text(output_path, _local_workspace_report_text(payload))
        payload = dict(payload)
        payload["command"] = "runtime workspace report"
        payload["output_path"] = _project_relative(output_path, project_root)
        payload["written"] = True
        return payload
    if action == "packet":
        payload = runtime_workspace_payload(action="status", workspace=workspace, project_root=project_root)
        output_path = _local_output_or_default(out, paths["handoff_packet"], project_root, "runtime_workspace_packet")
        packet = {
            "ok": True,
            "schema_version": SCHEMA_VERSION,
            "packet_type": "agentoffice_local_runtime_handoff_packet",
            "marker": LOCAL_RUNTIME_MARKER,
            "workspace": payload["workspace"],
            "run_id": payload["run_id"],
            "status": payload["status"],
            "goal_counts": payload["goal_counts"],
            "next_action": payload["next_action"],
            "operator_summary": _local_operator_summary(payload),
            "safety": _local_runtime_safety(),
            "created_at": LOCAL_RUNTIME_CREATED_AT,
        }
        _write_json(output_path, packet)
        packet["command"] = "runtime workspace packet"
        packet["output_path"] = _project_relative(output_path, project_root)
        packet["written"] = True
        return packet
    raise RuntimeFoundationError("runtime_workspace_unknown_action", f"Unsupported runtime workspace action: {action}")


def runtime_memory_payload(
    *,
    action: str,
    workspace: str,
    project_root: Path,
    memory_id: str | None = None,
    goal_id: str | None = None,
    agent_role: str | None = None,
    kind: str | None = None,
    content: str | None = None,
    summary: str | None = None,
    source_command: str | None = None,
    source_artifact: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    schema, _, paths = _load_local_workspace(workspace, project_root)
    records = _local_memory_projection(paths, str(schema["run_id"]))
    if action == "write":
        required_goal_id = _local_required_id(goal_id, "runtime_memory_goal_id_required", "memory write requires --goal-id.")
        required_role = _local_agent_role(agent_role)
        required_kind = _local_required_id(kind, "runtime_memory_kind_required", "memory write requires --kind.")
        required_content = _local_required_text(content, "runtime_memory_content_required", "memory write requires --content.")
        record = {
            "schema_version": SCHEMA_VERSION,
            "memory_id": f"mem-{len(records) + 1:04d}",
            "run_id": str(schema["run_id"]),
            "goal_id": required_goal_id,
            "agent_role": required_role,
            "kind": required_kind,
            "content": required_content,
            "summary": summary.strip() if summary and summary.strip() else _local_summarize_text(required_content),
            "created_at": LOCAL_RUNTIME_CREATED_AT,
            "source": {
                "command": source_command or "runtime memory write",
                "artifact": source_artifact or "",
            },
        }
        append_event(paths["event_log"], run_id=str(schema["run_id"]), event_type="MEMORY_RECORDED", payload=record)
        _write_memory_projection(paths, str(schema["run_id"]))
        payload = _local_base_payload("runtime memory write", schema=schema, status=_local_status_from_kernel(paths, str(schema["run_id"])))
        payload.update({"record": record, "record_count": len(records) + 1})
        return payload
    filtered = _filter_local_memory(records, run_id=run_id, goal_id=goal_id, agent_role=agent_role)
    if action == "list":
        payload = _local_base_payload("runtime memory list", schema=schema, status=_local_status_from_kernel(paths, str(schema["run_id"])))
        payload.update({"records": filtered, "record_count": len(filtered), "filters": {"run_id": run_id, "goal_id": goal_id, "agent_role": agent_role}})
        return payload
    if action == "inspect":
        required_memory_id = _local_required_id(memory_id, "runtime_memory_id_required", "memory inspect requires --memory-id.")
        for record in records:
            if record.get("memory_id") == required_memory_id:
                payload = _local_base_payload("runtime memory inspect", schema=schema, status=_local_status_from_kernel(paths, str(schema["run_id"])))
                payload.update({"record": record})
                return payload
        raise RuntimeFoundationError("runtime_memory_missing", f"Memory record not found: {required_memory_id}")
    if action == "summarize":
        payload = _local_base_payload("runtime memory summarize", schema=schema, status=_local_status_from_kernel(paths, str(schema["run_id"])))
        payload.update({"summary": _local_memory_summary(filtered), "record_count": len(filtered), "filters": {"run_id": run_id, "goal_id": goal_id, "agent_role": agent_role}})
        return payload
    raise RuntimeFoundationError("runtime_memory_unknown_action", f"Unsupported runtime memory action: {action}")


def runtime_planner_payload(*, workspace: str, objective: str | None, explain: bool, project_root: Path) -> dict[str, Any]:
    schema, _, paths = _load_local_workspace(workspace, project_root)
    objective_text = _local_required_text(objective, "runtime_planner_objective_required", "runtime planner requires --objective.")
    memory_records = _local_memory_projection(paths, str(schema["run_id"]))
    existing = list(_local_kernel_state(paths, str(schema["run_id"])).get("tasks", {}).values())
    goals = _local_plan_goals(objective_text)
    graph = {
        "schema_version": SCHEMA_VERSION,
        "packet_type": "agentoffice_local_plan_graph",
        "run_id": str(schema["run_id"]),
        "objective": objective_text,
        "goals": goals,
        "dependency_edges": _local_dependency_edges(goals),
        "generated_at": LOCAL_RUNTIME_CREATED_AT,
    }
    _write_json(paths["goal_queue"], graph)
    append_event(paths["event_log"], run_id=str(schema["run_id"]), event_type="RUN_CREATED", payload={"workspace": schema["workspace"], "objective": objective_text, "artifact_root": schema["run_root"]})
    for goal in goals:
        append_event(paths["event_log"], run_id=str(schema["run_id"]), event_type="TASK_DEFINED", payload=goal)
    payload = _local_base_payload("runtime planner", schema=schema, status="planned")
    payload.update(
        {
            "objective": objective_text,
            "plan_graph": graph,
            "goal_proposals": goals,
            "dependency_edges": graph["dependency_edges"],
            "existing_goal_count": len(existing),
            "memory_record_count": len(memory_records),
            "explain": explain,
            "rationale": "static deterministic decomposition from objective into planner, scheduler, executor, and reviewer goals",
            "safety_classification": "local_static_dry_run_only",
            "reviewer_hints": [
                "verify goal graph before executor dry-run",
                "inspect scheduler/executor ledgers before handoff",
                "do not treat dry-run executor output as real agent work",
            ],
            "next_action": runtime_kernel.get_next_actions(_local_kernel_state(paths, str(schema["run_id"])))["next_action"],
        }
    )
    return payload


def runtime_scheduler_payload(*, workspace: str, project_root: Path, dry_run: bool = True) -> dict[str, Any]:
    schema, _, paths = _load_local_workspace(workspace, project_root)
    scheduler = _local_kernel_scheduler(paths, str(schema["run_id"]))
    payload = _local_base_payload("runtime scheduler", schema=schema, status=_local_status_from_scheduler(scheduler), ok=not scheduler["errors"])
    payload.update({"dry_run": dry_run, "writes_ledger": False, "projection_cache_path": schema["scheduler_ledger_path"], **scheduler})
    _write_json(paths["scheduler_ledger"], {"schema_version": SCHEMA_VERSION, "packet_type": "agentoffice_local_scheduler_projection_cache", "canonical_source": "events.jsonl", "entries": [payload]})
    return payload


def runtime_parallel_payload(*, workspace: str, max_workers: int, project_root: Path, dry_run: bool = True, fail_goal: list[str] | None = None) -> dict[str, Any]:
    if max_workers < 1:
        raise RuntimeFoundationError("runtime_parallel_workers_invalid", "runtime parallel requires --max-workers >= 1.")
    schema, _, paths = _load_local_workspace(workspace, project_root)
    scheduler = runtime_scheduler_payload(workspace=workspace, project_root=project_root, dry_run=True)
    failures_requested = set(fail_goal or [])
    runnable = list(scheduler.get("ready", []))[:max_workers]
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for index, goal in enumerate(runnable, start=1):
        goal_id = str(goal["goal_id"])
        failed = goal_id in failures_requested or str(goal.get("simulate_result", "")) == "failed"
        runtime_executor.execute(paths["event_log"], run_id=str(schema["run_id"]), task=goal, worker_slot=index, fail=failed)
        result = {
            "goal_id": goal_id,
            "agent_role": goal["agent_role"],
            "worker_slot": index,
            "status": "failed" if failed else "dry_run_completed",
            "classification": "simulated_failure" if failed else "safe_local_simulation",
            "shell_executed": False,
            "provider_calls": False,
            "model_calls": False,
        }
        results.append(result)
        if failed:
            failures.append({"goal_id": goal_id, "failure_class": "simulated_failure", "next_action": "inspect_goal_before_retry"})
    payload = _local_base_payload("runtime parallel", schema=schema, status="failed" if failures else _local_status_from_scheduler(scheduler), ok=not scheduler.get("errors"))
    payload.update(
        {
            "dry_run": dry_run,
            "max_workers": max_workers,
            "bounded_worker_count": min(max_workers, len(runnable)),
            "ready_goal_count": len(scheduler.get("ready", [])),
            "results": results,
            "failure_ledger": failures,
            "execution_ledger_path": schema["executor_ledger_path"],
            "failure_ledger_path": _project_relative(paths["failure_ledger"], project_root),
            "next_action": "runtime orchestrate --resume" if failures else runtime_kernel.get_next_actions(_local_kernel_state(paths, str(schema["run_id"])))["next_action"],
        }
    )
    _write_json(paths["executor_ledger"], {"schema_version": SCHEMA_VERSION, "packet_type": "agentoffice_local_executor_projection_cache", "canonical_source": "events.jsonl", "entries": [payload]})
    _write_json(paths["failure_ledger"], {"schema_version": SCHEMA_VERSION, "packet_type": "agentoffice_local_executor_failure_projection_cache", "canonical_source": "events.jsonl", "failures": failures})
    return payload


def runtime_orchestrate_payload(
    *,
    workspace: str,
    objective: str | None,
    run_id: str | None,
    max_workers: int,
    dry_run: bool,
    resume: bool,
    project_root: Path,
) -> dict[str, Any]:
    if resume:
        schema, _, paths = _load_local_workspace(workspace, project_root)
        scheduler = _load_optional_json(paths["scheduler_ledger"], "runtime_orchestrate_scheduler_ledger")
        executor = _load_optional_json(paths["executor_ledger"], "runtime_orchestrate_executor_ledger")
        failures = _load_optional_json(paths["failure_ledger"], "runtime_orchestrate_failure_ledger")
        summary = {
            "scheduler_entries": len(scheduler.get("entries", [])),
            "executor_entries": len(executor.get("entries", [])),
            "failure_count": len(failures.get("failures", [])),
            "next_action": runtime_kernel.get_next_actions(_local_kernel_state(paths, str(schema["run_id"])))["next_action"],
        }
        payload = _local_base_payload("runtime orchestrate", schema=schema, status="resume_inspection")
        payload.update({"resume": True, "dry_run": True, "recovery_summary": summary, "operator_summary": _local_operator_summary(summary), "final_report_path": None, "handoff_packet_path": schema["handoff_packet_path"]})
        return payload

    objective_text = _local_required_text(objective, "runtime_orchestrate_objective_required", "runtime orchestrate requires --objective unless --resume is used.")
    try:
        schema, _, paths = _load_local_workspace(workspace, project_root)
    except RuntimeFoundationError as exc:
        if exc.error_code != "runtime_workspace_missing" or not run_id:
            raise
        runtime_workspace_payload(action="init", workspace=workspace, run_id=run_id, project_root=project_root)
        schema, _, paths = _load_local_workspace(workspace, project_root)
    planner = runtime_planner_payload(workspace=workspace, objective=objective_text, explain=False, project_root=project_root)
    scheduler = runtime_scheduler_payload(workspace=workspace, project_root=project_root, dry_run=True)
    executor = runtime_parallel_payload(workspace=workspace, max_workers=max_workers, project_root=project_root, dry_run=True)
    report = {
        "schema_version": SCHEMA_VERSION,
        "packet_type": "agentoffice_local_runtime_final_report",
        "marker": LOCAL_RUNTIME_MARKER,
        "workspace": schema["workspace"],
        "run_id": schema["run_id"],
        "objective": objective_text,
        "dry_run": dry_run,
        "planner_goal_count": len(planner["goal_proposals"]),
        "scheduler_next_action": scheduler["next_action"],
        "executor_result_count": len(executor["results"]),
        "failure_count": len(executor["failure_ledger"]),
        "operator_ready_summary": "ready_for_review" if not executor["failure_ledger"] else "needs_recovery",
        "safety": _local_runtime_safety(),
        "created_at": LOCAL_RUNTIME_CREATED_AT,
    }
    final_report_path = paths["reports"] / "final-runtime-report.json"
    _write_json(final_report_path, report)
    handoff = {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "packet_type": "agentoffice_local_runtime_orchestrator_handoff",
        "marker": LOCAL_RUNTIME_MARKER,
        "workspace": schema["workspace"],
        "run_id": schema["run_id"],
        "objective": objective_text,
        "operator_summary": report["operator_ready_summary"],
        "reviewer_packet": {
            "planner": planner["plan_graph"]["packet_type"],
            "scheduler_next_action": scheduler["next_action"],
            "executor_results": executor["results"],
            "final_report_path": _project_relative(final_report_path, project_root),
        },
        "recovery_summary": {"failure_count": report["failure_count"], "next_action": executor["next_action"]},
        "safety": _local_runtime_safety(),
        "created_at": LOCAL_RUNTIME_CREATED_AT,
    }
    _write_json(paths["handoff_packet"], handoff)
    payload = _local_base_payload("runtime orchestrate", schema=schema, status="dry_run_complete" if not executor["failure_ledger"] else "needs_recovery", ok=not scheduler.get("errors"))
    payload.update(
        {
            "objective": objective_text,
            "dry_run": True,
            "resume": False,
            "planner": planner,
            "scheduler": scheduler,
            "executor": executor,
            "reviewer_packet": handoff,
            "recovery_summary": handoff["recovery_summary"],
            "operator_ready_summary": report["operator_ready_summary"],
            "final_report_path": _project_relative(final_report_path, project_root),
            "handoff_packet_path": schema["handoff_packet_path"],
        }
    )
    return payload


def _local_base_payload(command: str, *, schema: dict[str, Any], status: str, ok: bool = True) -> dict[str, Any]:
    return {
        "ok": ok,
        "command": command,
        "kind": "local_multi_agent_runtime_v1",
        "schema_version": SCHEMA_VERSION,
        "packet_type": LOCAL_RUNTIME_PACKET_TYPE,
        "marker": LOCAL_RUNTIME_MARKER,
        "workspace": schema["workspace"],
        "run_root": schema["run_root"],
        "run_id": schema["run_id"],
        "status": status,
        "paths": {key: schema[key] for key in _local_schema_path_keys()},
        "safety": _local_runtime_safety(),
        "created_at": LOCAL_RUNTIME_CREATED_AT,
    }


def _local_workspace_path(workspace: str, project_root: Path, *, must_exist: bool) -> Path:
    raw = Path(workspace)
    if ".env" in raw.parts:
        raise RuntimeFoundationError("runtime_workspace_dotenv_refused", f"Refusing workspace under .env: {workspace}")
    root = project_root.resolve(strict=True)
    candidate = raw if raw.is_absolute() else root / raw
    if candidate.exists() and candidate.is_symlink():
        raise RuntimeFoundationError("runtime_workspace_symlink_refused", f"Refusing workspace symlink: {workspace}")
    workspace_root = _workspace_path(workspace, project_root)
    if must_exist and not workspace_root.is_dir():
        raise RuntimeFoundationError("runtime_workspace_missing", f"Workspace does not exist: {workspace}")
    if workspace_root.exists() and workspace_root.is_symlink():
        raise RuntimeFoundationError("runtime_workspace_symlink_refused", f"Refusing workspace symlink: {workspace}")
    return workspace_root


def _local_workspace_files(workspace_root: Path) -> dict[str, Path]:
    return {
        "workspace": workspace_root / "workspace.json",
        "goal_queue": workspace_root / "goal-queue.json",
        "agent_outputs": workspace_root / "agent-outputs",
        "memory": workspace_root / "memory.jsonl",
        "event_log": workspace_root / "events.jsonl",
        "scheduler_ledger": workspace_root / "scheduler-ledger.json",
        "executor_ledger": workspace_root / "executor-ledger.json",
        "failure_ledger": workspace_root / "executor-failures.json",
        "reports": workspace_root / "reports",
        "handoff_packet": workspace_root / "handoff-packet.json",
    }


def _load_local_workspace(workspace: str, project_root: Path) -> tuple[dict[str, Any], Path, dict[str, Path]]:
    workspace_root = _local_workspace_path(workspace, project_root, must_exist=True)
    paths = _local_workspace_files(workspace_root)
    schema = _load_json(paths["workspace"], "runtime_workspace_manifest_missing", "Local runtime workspace manifest is missing.")
    if schema.get("packet_type") != LOCAL_RUNTIME_PACKET_TYPE:
        raise RuntimeFoundationError("runtime_workspace_manifest_invalid", "Local runtime workspace manifest is invalid.")
    return schema, workspace_root, paths


def _local_workspace_schema(workspace_root: Path, run_id: str, project_root: Path) -> dict[str, Any]:
    paths = _local_workspace_files(workspace_root)
    schema = {
        "schema_version": SCHEMA_VERSION,
        "packet_type": LOCAL_RUNTIME_PACKET_TYPE,
        "marker": LOCAL_RUNTIME_MARKER,
        "workspace": _project_relative(workspace_root, project_root),
        "run_root": _project_relative(workspace_root, project_root),
        "run_id": run_id,
        "created_at": LOCAL_RUNTIME_CREATED_AT,
        "status": "initialized",
    }
    for key in _local_schema_path_keys():
        schema[key] = _project_relative(paths[_local_file_key_for_schema(key)], project_root)
    return schema


def _local_schema_path_keys() -> tuple[str, ...]:
    return (
        "goal_queue_path",
        "agent_outputs_path",
        "memory_path",
        "event_log_path",
        "scheduler_ledger_path",
        "executor_ledger_path",
        "reports_path",
        "handoff_packet_path",
    )


def _local_file_key_for_schema(schema_key: str) -> str:
    return {
        "goal_queue_path": "goal_queue",
        "agent_outputs_path": "agent_outputs",
        "memory_path": "memory",
        "event_log_path": "event_log",
        "scheduler_ledger_path": "scheduler_ledger",
        "executor_ledger_path": "executor_ledger",
        "reports_path": "reports",
        "handoff_packet_path": "handoff_packet",
    }[schema_key]


def _local_empty_goal_queue(run_id: str) -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "packet_type": "agentoffice_local_plan_graph", "run_id": run_id, "objective": "", "goals": [], "dependency_edges": [], "generated_at": LOCAL_RUNTIME_CREATED_AT}


def _local_empty_ledger(name: str) -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "packet_type": f"agentoffice_local_{name}_ledger", "entries": []}


def _local_runtime_safety() -> dict[str, Any]:
    return {
        "local_only": True,
        "deterministic": True,
        "dry_run_default": True,
        "provider_calls": False,
        "model_calls": False,
        "network_calls": False,
        "adapter_external_behavior": False,
        "dotenv_read": False,
        "env_vars_printed": False,
        "daemon": False,
        "vector_store": False,
        "shell_mutation": False,
    }


def _load_local_goal_queue(path: Path, *, required: bool) -> dict[str, Any]:
    if not path.exists():
        if required:
            raise RuntimeFoundationError("runtime_goal_queue_missing", "Local runtime goal queue is missing.")
        return _local_empty_goal_queue("")
    data = _load_json(path, "runtime_goal_queue_missing", "Local runtime goal queue is missing.")
    goals = data.get("goals")
    if not isinstance(goals, list):
        raise RuntimeFoundationError("runtime_goal_queue_invalid", "Local runtime goal queue must include a goals list.")
    return data


def _local_plan_goals(objective: str) -> list[dict[str, Any]]:
    specs = [
        ("plan-objective", "planner", [], "Convert objective into a deterministic goal graph."),
        ("inspect-workspace", "scheduler", ["plan-objective"], "Classify runnable, blocked, and terminal goals."),
        ("simulate-execution", "executor", ["inspect-workspace"], "Run bounded local dry-run simulation for ready goals."),
        ("review-handoff", "reviewer", ["simulate-execution"], "Create reviewer/operator handoff packet from local evidence."),
    ]
    return [
        {
            "goal_id": goal_id,
            "objective": objective,
            "agent_role": role,
            "status": "pending",
            "depends_on": depends,
            "rationale": rationale,
            "safety_classification": "local_static_dry_run_only",
            "reviewer_hint": f"Review {goal_id} evidence before treating it as complete.",
        }
        for goal_id, role, depends, rationale in specs
    ]


def _local_dependency_edges(goals: list[dict[str, Any]]) -> list[dict[str, str]]:
    edges: list[dict[str, str]] = []
    for goal in goals:
        for dependency in goal.get("depends_on", []):
            edges.append({"from": str(dependency), "to": str(goal["goal_id"])})
    return edges


def _local_scheduler_snapshot(queue: dict[str, Any]) -> dict[str, Any]:
    goals = [_normalize_local_goal(goal) for goal in queue.get("goals", [])]
    by_id = {goal["goal_id"]: goal for goal in goals}
    errors = _local_goal_graph_errors(goals, by_id)
    ready: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    running: list[dict[str, Any]] = []
    completed: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for goal in goals:
        status = str(goal["status"])
        if status == "completed":
            completed.append(goal)
        elif status == "failed":
            failed.append(goal)
        elif status == "skipped":
            skipped.append(goal)
        elif status == "running":
            running.append(goal)
        elif status == "blocked":
            blocked.append({**goal, "reason": "explicitly_blocked"})
        else:
            deps = [by_id.get(dep) for dep in goal["depends_on"]]
            if any(dep is None for dep in deps):
                blocked.append({**goal, "reason": "missing_dependency"})
            elif any(dep and dep["status"] == "failed" for dep in deps):
                blocked.append({**goal, "reason": "dependency_failed"})
            elif any(dep and dep["status"] in {"blocked", "skipped"} for dep in deps):
                blocked.append({**goal, "reason": "dependency_blocked"})
            elif all(dep and dep["status"] == "completed" for dep in deps):
                ready.append({**goal, "reason": "dependencies_satisfied"})
            else:
                blocked.append({**goal, "reason": "waiting_dependency"})
    counts = {status: 0 for status in ("ready", "blocked", "running", "completed", "failed", "skipped")}
    counts.update({"ready": len(ready), "blocked": len(blocked), "running": len(running), "completed": len(completed), "failed": len(failed), "skipped": len(skipped), "total": len(goals)})
    next_action = "repair_goal_graph" if errors else "run_ready_goals" if ready else "inspect_failed" if failed else "inspect_blocked" if blocked else "inspect_running" if running else "complete"
    return {
        "goal_queue": queue,
        "ready": ready,
        "blocked": blocked,
        "running": running,
        "completed": completed,
        "failed": failed,
        "skipped": skipped,
        "counts": counts,
        "errors": errors,
        "next_action": next_action,
        "recovery_next_action": "repair graph and rerun scheduler" if errors else "retry failed dry-run goals" if failed else "run executor dry-run" if ready else "no runnable goals",
    }


def _normalize_local_goal(goal: Any) -> dict[str, Any]:
    if not isinstance(goal, dict):
        raise RuntimeFoundationError("runtime_goal_invalid", "Each local runtime goal must be an object.")
    goal_id = _local_required_id(str(goal.get("goal_id", "")), "runtime_goal_id_required", "Local runtime goal requires goal_id.")
    status = str(goal.get("status", "pending"))
    if status not in LOCAL_GOAL_STATUSES:
        raise RuntimeFoundationError("runtime_goal_status_invalid", f"Unsupported local runtime goal status: {status}")
    role = _local_agent_role(str(goal.get("agent_role", "executor")))
    depends_on = goal.get("depends_on", [])
    if not isinstance(depends_on, list) or not all(isinstance(item, str) and item.strip() for item in depends_on):
        raise RuntimeFoundationError("runtime_goal_dependencies_invalid", "Goal depends_on must be a list of ids.")
    return {**goal, "goal_id": goal_id, "status": status, "agent_role": role, "depends_on": sorted(set(depends_on))}


def _local_goal_graph_errors(goals: list[dict[str, Any]], by_id: dict[str, dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for goal in goals:
        for dependency in goal["depends_on"]:
            if dependency not in by_id:
                errors.append(f"missing_dependency:{goal['goal_id']}->{dependency}")
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(goal_id: str, path: list[str]) -> None:
        if goal_id in visiting:
            errors.append("circular_dependency:" + "->".join([*path, goal_id]))
            return
        if goal_id in visited or goal_id not in by_id:
            return
        visiting.add(goal_id)
        for dependency in by_id[goal_id]["depends_on"]:
            visit(dependency, [*path, goal_id])
        visiting.remove(goal_id)
        visited.add(goal_id)

    for goal in goals:
        visit(goal["goal_id"], [])
    return sorted(set(errors))


def _local_status_from_goals(paths: dict[str, Path]) -> str:
    try:
        queue = _load_local_goal_queue(paths["goal_queue"], required=False)
    except RuntimeFoundationError:
        return "invalid"
    return _local_status_from_scheduler(_local_scheduler_snapshot(queue))


def _local_status_from_kernel(paths: dict[str, Path], run_id: str) -> str:
    try:
        return _local_status_from_scheduler(_local_kernel_scheduler(paths, run_id))
    except (RuntimeFoundationError, EventLogError):
        return "invalid"


def _local_kernel_events(paths: dict[str, Path], run_id: str) -> list[dict[str, Any]]:
    from agent_office.runtime_kernel.event_log import read_events_by_run_id
    try:
        return read_events_by_run_id(paths["event_log"], run_id)
    except EventLogError as exc:
        raise RuntimeFoundationError(exc.error_code, str(exc)) from exc


def _local_kernel_state(paths: dict[str, Path], run_id: str) -> dict[str, Any]:
    try:
        return runtime_kernel.get_state(paths["event_log"], run_id)
    except EventLogError as exc:
        raise RuntimeFoundationError(exc.error_code, str(exc)) from exc


def _local_kernel_scheduler(paths: dict[str, Path], run_id: str) -> dict[str, Any]:
    return runtime_scheduler.view(_local_kernel_state(paths, run_id))


def _local_memory_projection(paths: dict[str, Path], run_id: str) -> list[dict[str, Any]]:
    state = _local_kernel_state(paths, run_id)
    return list(state.get("memory", []))


def _write_memory_projection(paths: dict[str, Path], run_id: str) -> None:
    records = _local_memory_projection(paths, run_id)
    paths["memory"].write_text("".join(json.dumps(record, sort_keys=True) + "\n" for record in records), encoding="utf-8")


def _local_status_from_scheduler(scheduler: dict[str, Any]) -> str:
    if scheduler["errors"]:
        return "invalid"
    counts = scheduler["counts"]
    if counts["ready"]:
        return "ready"
    if counts["failed"]:
        return "failed"
    if counts["blocked"]:
        return "blocked"
    if counts["running"]:
        return "running"
    if counts["completed"] and counts["completed"] == counts["total"]:
        return "completed"
    return "empty" if counts["total"] == 0 else "pending"


def _load_local_memory_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise RuntimeFoundationError("runtime_memory_missing", "Local runtime memory file is missing.")
    if path.is_symlink():
        raise RuntimeFoundationError("runtime_workspace_file_symlink_refused", f"Refusing symlink file: {path.name}")
    records: list[dict[str, Any]] = []
    try:
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            data = json.loads(line)
            if not isinstance(data, dict):
                raise RuntimeFoundationError("runtime_memory_jsonl_invalid", f"Memory record {index} must be an object.")
            records.append(data)
    except json.JSONDecodeError as exc:
        raise RuntimeFoundationError("runtime_memory_jsonl_unreadable", f"Unable to read local runtime memory JSONL at line {index}.") from exc
    return records


def _filter_local_memory(records: list[dict[str, Any]], *, run_id: str | None, goal_id: str | None, agent_role: str | None) -> list[dict[str, Any]]:
    role = _local_agent_role(agent_role) if agent_role else None
    return [
        record
        for record in records
        if (run_id is None or record.get("run_id") == run_id)
        and (goal_id is None or record.get("goal_id") == goal_id)
        and (role is None or record.get("agent_role") == role)
    ]


def _local_memory_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_role: dict[str, int] = {}
    by_goal: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    for record in records:
        by_role[str(record.get("agent_role", "unknown"))] = by_role.get(str(record.get("agent_role", "unknown")), 0) + 1
        by_goal[str(record.get("goal_id", "unknown"))] = by_goal.get(str(record.get("goal_id", "unknown")), 0) + 1
        by_kind[str(record.get("kind", "unknown"))] = by_kind.get(str(record.get("kind", "unknown")), 0) + 1
    return {"by_role": dict(sorted(by_role.items())), "by_goal": dict(sorted(by_goal.items())), "by_kind": dict(sorted(by_kind.items())), "latest_memory_id": records[-1]["memory_id"] if records else None}


def _local_workspace_report_text(payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Local Multi-Agent Runtime Workspace Report",
            LOCAL_RUNTIME_MARKER,
            f"workspace: {payload['workspace']}",
            f"run_id: {payload['run_id']}",
            f"status: {payload['status']}",
            f"next_action: {payload.get('next_action', 'none')}",
            "paths:",
            *[f"- {key}: {value}" for key, value in payload["paths"].items()],
            "safety:",
            *[f"- {key}: {str(value).lower()}" for key, value in sorted(payload["safety"].items())],
        ]
    )


def _local_operator_summary(payload: dict[str, Any]) -> str:
    if "next_action" in payload:
        return f"status={payload.get('status', 'unknown')}; next_action={payload['next_action']}"
    return f"next_action={payload.get('next_action', 'inspect')}"


def _local_output_or_default(out: str | None, default_path: Path, project_root: Path, code_prefix: str) -> Path:
    if out:
        return _safe_output_path(out, project_root, code_prefix)
    if default_path.parent.exists() and default_path.parent.is_symlink():
        raise RuntimeFoundationError(f"{code_prefix}_parent_symlink", f"Refusing symlink output parent: {default_path.parent}")
    default_path.parent.mkdir(parents=True, exist_ok=True)
    return default_path


def _load_optional_json(path: Path, code_prefix: str) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "packet_type": code_prefix, "entries": [], "failures": []}
    return _load_json(path, f"{code_prefix}_missing", f"Missing optional local runtime JSON: {path.name}")


def _local_required_id(value: str | None, code: str, message: str) -> str:
    if not value or not str(value).strip():
        raise RuntimeFoundationError(code, message)
    text = str(value).strip()
    if any(part in {".", ".."} for part in Path(text).parts):
        raise RuntimeFoundationError(code.replace("required", "invalid"), f"Unsafe id: {text}")
    return text


def _local_required_text(value: str | None, code: str, message: str) -> str:
    if not value or not str(value).strip():
        raise RuntimeFoundationError(code, message)
    return str(value).strip()


def _local_agent_role(agent_role: str | None) -> str:
    role = _local_required_id(agent_role, "runtime_agent_role_required", "agent role is required.")
    if role not in LOCAL_AGENT_ROLES:
        raise RuntimeFoundationError("runtime_agent_role_invalid", f"Unsupported local agent role: {role}")
    return role


def _local_summarize_text(text: str) -> str:
    compact = " ".join(text.split())
    return compact[:120]


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
    if payload.get("marker") == LOCAL_RUNTIME_MARKER:
        lines[0] = LOCAL_RUNTIME_MARKER
        if "run_id" in payload:
            lines.append(f"run_id: {payload['run_id']}")
        if "packet_type" in payload:
            lines.append(f"packet_type: {payload['packet_type']}")
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
    if payload.get("marker") == LOCAL_RUNTIME_MARKER:
        if "next_action" in payload:
            lines.append(f"next_action: {payload['next_action']}")
        if "dry_run" in payload:
            lines.append(f"dry_run: {str(payload['dry_run']).lower()}")
        if "memory_count" in payload:
            lines.append(f"memory_count: {payload['memory_count']}")
        if "record_count" in payload:
            lines.append(f"record_count: {payload['record_count']}")
        if "goal_counts" in payload:
            counts = payload["goal_counts"]
            lines.append("goals: " + " ".join(f"{key}={counts.get(key, 0)}" for key in ("total", "ready", "blocked", "running", "completed", "failed", "skipped")))
        if "output_path" in payload:
            lines.append(f"output_path: {payload['output_path']}")
        if "operator_ready_summary" in payload:
            lines.append(f"operator_ready_summary: {payload['operator_ready_summary']}")
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
    if payload.get("kind") == "runtime_worker_reviewer_attestation_packet":
        lines.append(f"reviewer_artifact: {payload['artifact_path']}")
        lines.append(f"verdict: {payload['verdict']}")
        lines.append(f"marker: {payload['marker']}")
        lines.append(f"review_type: {payload['review_type']}")
        lines.append(f"reviewer_attestation_present: {str(payload['reviewer_attestation_present']).lower()}")
        lines.append(f"external_execution_refused: {str(payload['external_execution_refused']).lower()}")
        lines.append(f"output_path: {payload['output_path']}")
    if payload.get("kind") == "runtime_worker_closure_evidence":
        lines.append(f"closure_evidence_imported: {str(payload['closure_evidence_imported']).lower()}")
        lines.append(f"reviewer_attestation_present: {str(payload['reviewer_attestation_present']).lower()}")
        lines.append(f"verdict: {payload['verdict']}")
        lines.append(f"external_execution_refused: {str(payload['external_execution_refused']).lower()}")
        lines.append(f"output_path: {payload['output_path']}")
    if payload.get("kind") == "runtime_worker_merge_readiness_packet":
        lines.append(f"source_branch: {payload['source_branch']}")
        lines.append(f"source_head: {payload['source_head']}")
        lines.append(f"target_branch: {payload['target_branch']}")
        lines.append(f"external_worker_replay_ready: {str(payload['external_worker_replay_ready']).lower()}")
        lines.append(f"audit_closure_ready: {str(payload['audit_closure_ready']).lower()}")
        lines.append(f"reviewer_attestation_present: {str(payload['reviewer_attestation_present']).lower()}")
        lines.append(f"closure_evidence_imported: {str(payload['closure_evidence_imported']).lower()}")
        lines.append(f"delivery_bundle_ready: {str(payload['delivery_bundle_ready']).lower()}")
        lines.append(f"merge_readiness_ready: {str(payload['merge_readiness_ready']).lower()}")
        lines.append(f"next_action: {payload['next_action']}")
        lines.append(f"output_path: {payload['output_path']}")
    if payload.get("kind") == "runtime_worker_delivery_gate_summary":
        lines.append(f"source_branch: {payload['source_branch']}")
        lines.append(f"source_head: {payload['source_head']}")
        lines.append(f"target_branch: {payload['target_branch']}")
        lines.append(f"delivery_gate_pass: {str(payload['delivery_gate_pass']).lower()}")
        lines.append(f"gate_status: {payload['gate_status']}")
        lines.append(f"rejection_reasons: {', '.join(payload['rejection_reasons']) or 'none'}")
        lines.append(f"next_action: {payload['next_action']}")
        lines.append(f"output_path: {payload['output_path']}")
    if payload.get("kind") == "runtime_worker_rejection_recovery_packet":
        lines.append(f"rejected: {str(payload['rejected']).lower()}")
        lines.append(f"original_readiness: {str(payload['original_readiness']).lower()}")
        lines.append(f"rejection_reasons: {', '.join(payload['rejection_reasons']) or 'none'}")
        lines.append(f"recovery_status: {payload['recovery_status']}")
        lines.append(f"output_path: {payload['output_path']}")
    if payload.get("kind") == "runtime_worker_audit_packet_replay":
        lines.append(f"packet_kind: {payload['packet_kind']}")
        lines.append(f"original_readiness: {str(payload['original_readiness']).lower()}")
        lines.append(f"rejection_reasons: {', '.join(payload['rejection_reasons']) or 'none'}")
        lines.append(f"recovery_status: {payload['recovery_status']}")
        lines.append(f"replay_ready: {str(payload['replay_ready']).lower()}")
        lines.append(f"governance_ready: {str(payload['governance_ready']).lower()}")
        if payload.get("output_path"):
            lines.append(f"output_path: {payload['output_path']}")
    if payload.get("kind") == "runtime_worker_provenance_manifest":
        lines.append(f"chain_root: {payload['chain_root']}")
        lines.append(f"terminal_artifact: {payload['terminal_artifact']}")
        lines.append(f"artifact_count: {payload['artifact_count']}")
        lines.append(f"terminal_readiness: {str(payload['readiness_summary']['terminal_readiness']).lower()}")
        lines.append(f"output_path: {payload['output_path']}")
    if payload.get("kind") == "runtime_worker_provenance_verification":
        lines.append(f"chain_valid: {str(payload['chain_valid']).lower()}")
        lines.append(f"artifact_integrity_valid: {str(payload['artifact_integrity_valid']).lower()}")
        lines.append(f"parent_linkage_valid: {str(payload['parent_linkage_valid']).lower()}")
        lines.append(f"role_order_valid: {str(payload['role_order_valid']).lower()}")
        lines.append(f"readiness_predicates_valid: {str(payload['readiness_predicates_valid']).lower()}")
        lines.append(f"rejection_reasons: {', '.join(payload['rejection_reasons']) or 'none'}")
        lines.append(f"next_action: {payload['next_action']}")
        lines.append("recovery_guidance:")
        lines.extend(f"  - {item}" for item in payload["recovery_guidance"])
    if payload.get("kind") == "runtime_worker_provenance_replay":
        lines.append(f"chain_replay_ready: {str(payload['chain_replay_ready']).lower()}")
        lines.append(f"artifact_integrity_valid: {str(payload['artifact_integrity_valid']).lower()}")
        lines.append(f"original_readiness: {str(payload['original_readiness']).lower()}")
        lines.append(f"delivery_gate_pass: {str(payload['delivery_gate_pass']).lower()}")
        lines.append(f"recovery_status: {payload['recovery_status']}")
        lines.append(f"rejection_reasons: {', '.join(payload['rejection_reasons']) or 'none'}")
    if payload.get("kind") == "runtime_worker_release_candidate_package":
        lines.append(f"review_target: {payload['review_target']}")
        lines.append(f"chain_root: {payload['chain_root']}")
        lines.append(f"terminal_artifact: {payload['terminal_artifact']}")
        lines.append(f"artifact_count: {payload['artifact_count']}")
        lines.append(f"archive_ready: {str(payload['archive_ready']).lower()}")
        lines.append(f"replay_ready: {str(payload['replay_ready']).lower()}")
        lines.append(f"output_path: {payload['output_path']}")
    if payload.get("kind") == "runtime_worker_external_review_handoff":
        lines.append(f"review_target: {payload['review_target']}")
        lines.append(f"artifact_chain_root: {payload['artifact_chain_root']}")
        lines.append(f"terminal_artifact: {payload['terminal_artifact']}")
        lines.append(f"expected_reviewer_output_marker: {payload['expected_reviewer_output_marker']}")
        lines.append(f"attestation_import_path: {payload['attestation_import_path']}")
        lines.append(f"output_path: {payload['output_path']}")
    if payload.get("kind") == "runtime_worker_evidence_archive_index":
        lines.append(f"record_count: {payload['record_count']}")
        lines.append(f"archive_ready: {str(payload['archive_ready']).lower()}")
        lines.append(f"replay_ready: {str(payload['replay_ready']).lower()}")
        lines.append(f"output_path: {payload['output_path']}")
    if payload.get("kind") == "runtime_worker_evidence_archive_verification":
        lines.append(f"archive_valid: {str(payload['archive_valid']).lower()}")
        lines.append(f"archive_ready: {str(payload['archive_ready']).lower()}")
        lines.append(f"replay_ready: {str(payload['replay_ready']).lower()}")
        lines.append(f"rejection_reasons: {', '.join(payload['rejection_reasons']) or 'none'}")
        lines.append("recovery_guidance:")
        lines.extend(f"  - {item}" for item in payload["recovery_guidance"])
    if payload.get("kind") == "runtime_worker_external_reviewer_archive_import":
        lines.append(f"review_verdict: {payload['review_verdict']}")
        lines.append(f"review_marker: {payload['review_marker']}")
        lines.append(f"archive_ready: {str(payload['archive_ready']).lower()}")
        lines.append(f"replay_ready: {str(payload['replay_ready']).lower()}")
        lines.append(f"terminal_status: {payload['terminal_status']}")
        lines.append(f"output_path: {payload['output_path']}")
    if payload.get("kind") == "runtime_worker_release_closure_bundle":
        lines.append(f"closure_status: {payload['closure_status']}")
        lines.append(f"review_verdict: {payload['review_verdict']}")
        lines.append(f"delivery_ready: {str(payload['delivery_ready']).lower()}")
        lines.append(f"promotion_ready: {str(payload['promotion_ready']).lower()}")
        lines.append(f"rejection_reasons: {', '.join(payload['rejection_reasons']) or 'none'}")
        lines.append(f"next_action: {payload['next_action']}")
        lines.append(f"output_path: {payload['output_path']}")
    if payload.get("kind") == "runtime_worker_archive_replay_verification":
        lines.append(f"archive_replay_valid: {str(payload['archive_replay_valid']).lower()}")
        lines.append(f"archive_ready: {str(payload['archive_ready']).lower()}")
        lines.append(f"replay_ready: {str(payload['replay_ready']).lower()}")
        lines.append(f"rejection_reasons: {', '.join(payload['rejection_reasons']) or 'none'}")
        lines.append(f"output_path: {payload['output_path']}")
    if payload.get("kind") == "runtime_worker_final_delivery_readiness_packet":
        lines.append(f"delivery_ready: {str(payload['delivery_ready']).lower()}")
        lines.append(f"promotion_ready: {str(payload['promotion_ready']).lower()}")
        lines.append(f"rejection_reasons: {', '.join(payload['rejection_reasons']) or 'none'}")
        lines.append(f"next_action: {payload['next_action']}")
        lines.append(f"output_path: {payload['output_path']}")
    if payload.get("kind") == "runtime_worker_failed_review_recovery_packet":
        lines.append(f"recovery_required: {str(payload['recovery_required']).lower()}")
        lines.append(f"recovery_status: {payload['recovery_status']}")
        lines.append(f"rejection_reasons: {', '.join(payload['rejection_reasons']) or 'none'}")
        lines.append(f"output_path: {payload['output_path']}")
    if payload.get("kind") == "runtime_worker_compact_evidence_archive_index":
        lines.append(f"record_count: {payload['record_count']}")
        lines.append(f"archive_ready: {str(payload['archive_ready']).lower()}")
        lines.append(f"replay_ready: {str(payload['replay_ready']).lower()}")
        lines.append(f"terminal_status: {payload['terminal_status']}")
        lines.append(f"output_path: {payload['output_path']}")
    if payload.get("kind") == "runtime_worker_compact_evidence_archive_verification":
        lines.append(f"compact_valid: {str(payload['compact_valid']).lower()}")
        lines.append(f"archive_ready: {str(payload['archive_ready']).lower()}")
        lines.append(f"replay_ready: {str(payload['replay_ready']).lower()}")
        lines.append(f"rejection_reasons: {', '.join(payload['rejection_reasons']) or 'none'}")
        lines.append("recovery_guidance:")
        lines.extend(f"  - {item}" for item in payload["recovery_guidance"])
    if payload.get("kind") == "runtime_worker_release_candidate_promotion_gate":
        lines.append(f"promotion_ready: {str(payload['promotion_ready']).lower()}")
        lines.append(f"delivery_ready: {str(payload['delivery_ready']).lower()}")
        lines.append(f"rejection_reasons: {', '.join(payload['rejection_reasons']) or 'none'}")
        lines.append(f"next_action: {payload['next_action']}")
        lines.append(f"output_path: {payload['output_path']}")
    if payload.get("kind") == "runtime_worker_release_candidate_export_packet":
        lines.append(f"record_count: {payload['record_count']}")
        lines.append(f"manifest_digest: {payload['manifest_digest']}")
        lines.append(f"export_ready: {str(payload['export_ready']).lower()}")
        lines.append(f"output_path: {payload['output_path']}")
    if payload.get("kind") == "runtime_worker_promotion_evidence_packet":
        lines.append(f"source_branch: {payload['reviewed_refs']['source_branch']}")
        lines.append(f"source_head: {payload['reviewed_refs']['source_head']}")
        lines.append(f"target_branch: {payload['reviewed_refs']['target_branch']}")
        lines.append(f"evidence_ready: {str(payload['evidence_ready']).lower()}")
        lines.append(f"promotion_ready: {str(payload['promotion_ready']).lower()}")
        lines.append(f"output_path: {payload['output_path']}")
    if payload.get("kind") == "runtime_worker_dry_run_publish_packet":
        lines.append(f"candidate_release_id: {payload['candidate_release_id']}")
        lines.append(f"target_branch: {payload['target_branch']}")
        lines.append(f"target_commit: {payload['target_commit']}")
        lines.append(f"publish_ready: {str(payload['publish_ready']).lower()}")
        lines.append(f"would_create_tag: {str(payload['would_create_tag']).lower()}")
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



def _read_input_text(path: Path, code_prefix: str) -> str:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise RuntimeFoundationError(f"{code_prefix}_invalid", f"Input text is unreadable: {path.name}") from exc
    if not data:
        raise RuntimeFoundationError(f"{code_prefix}_empty", f"Input text is empty: {path.name}")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeFoundationError(f"{code_prefix}_non_utf8", f"Input text must be UTF-8: {path.name}") from exc
    if not text.strip():
        raise RuntimeFoundationError(f"{code_prefix}_empty", f"Input text is empty: {path.name}")
    return text


def _load_reviewer_artifact(path: Path, expected_marker: str) -> dict[str, Any]:
    marker = str(expected_marker).strip()
    if not marker:
        raise RuntimeFoundationError("runtime_worker_reviewer_artifact_marker_required", "Expected review marker is required.")
    text = _read_input_text(path, "runtime_worker_reviewer_artifact")
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeFoundationError("runtime_worker_reviewer_artifact_invalid_json", "Reviewer JSON artifact is invalid.") from exc
        if not isinstance(data, dict):
            raise RuntimeFoundationError("runtime_worker_reviewer_artifact_invalid_json", "Reviewer JSON artifact must be an object.")
        parsed = _parse_reviewer_json(data, marker)
    else:
        if marker not in text:
            raise RuntimeFoundationError("runtime_worker_reviewer_artifact_marker_missing", "Expected review marker is missing.")
        parsed = _parse_reviewer_text(text, marker)
    if parsed["marker"] != marker:
        raise RuntimeFoundationError("runtime_worker_reviewer_artifact_marker_mismatch", "Reviewer artifact marker does not match expected marker.")
    if not parsed["verdict"]:
        raise RuntimeFoundationError("runtime_worker_reviewer_artifact_verdict_missing", "Reviewer artifact verdict is missing.")
    return parsed


def _parse_reviewer_json(data: dict[str, Any], expected_marker: str) -> dict[str, Any]:
    verdict = _normalise_verdict(_reviewer_json_value(data, "verdict", "review_verdict"))
    marker = str(_reviewer_json_value(data, "marker", "review_marker") or expected_marker).strip()
    return {
        "verdict": verdict,
        "marker": marker,
        "review_type": str(_reviewer_json_value(data, "review_type", "type") or "artifact").strip(),
        "review_caveat": str(_reviewer_json_value(data, "review_caveat", "caveat") or REVIEWER_ARTIFACT_SAFETY_CAVEAT).strip(),
        "findings_summary": str(_reviewer_json_value(data, "findings_summary", "findings") or "not provided").strip(),
        "reviewed_artifacts": _reviewed_artifacts_from_value(_reviewer_json_value(data, "reviewed_artifacts", "artifacts")),
        "reviewed_bundle_summary": str(_reviewer_json_value(data, "reviewed_bundle_summary", "bundle_summary") or "not provided").strip(),
        "safety_caveat": str(_reviewer_json_value(data, "safety_caveat", "safety") or REVIEWER_ARTIFACT_SAFETY_CAVEAT).strip(),
    }


def _parse_reviewer_text(text: str, expected_marker: str) -> dict[str, Any]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        match = re.match(r"^\s*[-*]?\s*([A-Za-z][A-Za-z0-9 _-]{1,64})\s*:\s*(.*?)\s*$", line)
        if match:
            values[_normalise_reviewer_key(match.group(1))] = match.group(2).strip()
    reviewed_artifacts = _reviewed_artifacts_from_value(values.get("reviewed_artifacts"))
    if not reviewed_artifacts:
        reviewed_artifacts = _reviewed_artifacts_from_text(text)
    return {
        "verdict": _normalise_verdict(values.get("verdict") or values.get("review_verdict")),
        "marker": values.get("marker") or values.get("review_marker") or expected_marker,
        "review_type": values.get("review_type") or "artifact",
        "review_caveat": values.get("review_caveat") or values.get("caveat") or REVIEWER_ARTIFACT_SAFETY_CAVEAT,
        "findings_summary": values.get("findings_summary") or values.get("findings") or "not provided",
        "reviewed_artifacts": reviewed_artifacts,
        "reviewed_bundle_summary": values.get("reviewed_bundle_summary") or values.get("bundle_summary") or "not provided",
        "safety_caveat": values.get("safety_caveat") or values.get("safety") or REVIEWER_ARTIFACT_SAFETY_CAVEAT,
    }


def _reviewer_json_value(data: dict[str, Any], *keys: str) -> Any:
    candidates = [data]
    for nested_key in ("review", "reviewer", "summary"):
        nested = data.get(nested_key)
        if isinstance(nested, dict):
            candidates.append(nested)
    wanted = {_normalise_reviewer_key(key) for key in keys}
    for candidate in candidates:
        normalised = {_normalise_reviewer_key(str(key)): value for key, value in candidate.items()}
        for key in wanted:
            if key in normalised:
                return normalised[key]
    return None


def _normalise_reviewer_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", key.strip().lower()).strip("_")


def _normalise_verdict(value: Any) -> str:
    verdict = str(value or "").strip().lower()
    return {"approved": "pass", "passed": "pass", "changes requested": "fail"}.get(verdict, verdict)


def _reviewed_artifacts_from_value(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        artifacts: list[str] = []
        for item in value:
            if isinstance(item, dict):
                artifacts.append(str(item.get("path") or item.get("artifact") or json.dumps(item, sort_keys=True)))
            else:
                artifacts.append(str(item))
        return [artifact.strip() for artifact in artifacts if artifact.strip()]
    text = str(value)
    parts = re.split(r"[,\n]", text)
    return [part.strip() for part in parts if part.strip()]


def _reviewed_artifacts_from_text(text: str) -> list[str]:
    artifacts: list[str] = []
    in_block = False
    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r"^#{1,6}\s+reviewed artifacts\b", stripped, re.IGNORECASE) or _normalise_reviewer_key(stripped.rstrip(":")) == "reviewed_artifacts":
            in_block = True
            continue
        if not in_block:
            continue
        if not stripped:
            continue
        if stripped.startswith("#"):
            break
        if stripped.startswith(("-", "*")):
            artifacts.append(stripped.lstrip("-* ").strip())
        elif artifacts:
            break
    return artifacts



def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_payload_digest(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


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





def _release_candidate_included_artifacts(manifest: dict[str, Any], manifest_path: Path, project_root: Path) -> list[dict[str, Any]]:
    included: list[dict[str, Any]] = []
    manifest_source = _artifact_source(manifest_path, project_root)
    included.append({
        "artifact_id": "provenance_manifest",
        "role": "provenance_manifest",
        "path": manifest_source["path"],
        "sha256": manifest_source["sha256"],
        "byte_count": manifest_source["bytes"],
        "parent_artifact_ids": [],
        "source_marker": PROVENANCE_MANIFEST_MARKER,
        "archive_ready": True,
        "replay_ready": True,
    })
    for artifact in manifest["artifacts"]:
        artifact_path, reasons = _provenance_entry_path(artifact, project_root)
        if artifact_path is None:
            raise RuntimeFoundationError("runtime_worker_release_candidate_artifact_invalid", ", ".join(reasons))
        payload = _load_input_json(artifact_path, f"runtime_worker_release_candidate_{artifact['role']}")
        included.append({
            "artifact_id": artifact["artifact_id"],
            "role": artifact["role"],
            "path": artifact["path"],
            "sha256": artifact["sha256"],
            "byte_count": artifact["byte_count"],
            "parent_artifact_ids": list(artifact["parent_artifact_ids"]),
            "source_marker": _payload_marker(payload),
            "archive_ready": True,
            "replay_ready": bool(artifact["replay_status"]),
        })
    return included


def _release_candidate_replay_summary(replay: dict[str, Any]) -> dict[str, Any]:
    return {
        "chain_replay_ready": bool(replay["chain_replay_ready"]),
        "artifact_integrity_valid": bool(replay["artifact_integrity_valid"]),
        "original_readiness": bool(replay["original_readiness"]),
        "delivery_gate_pass": bool(replay["delivery_gate_pass"]),
        "recovery_status": str(replay["recovery_status"]),
        "rejection_reasons": list(replay["rejection_reasons"]),
        "replay_ready": bool(replay["replay_ready"]),
        "governance_ready": bool(replay["governance_ready"]),
    }


def _validate_release_candidate_package(payload: dict[str, Any], code_prefix: str) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION or payload.get("kind") != "runtime_worker_release_candidate_package":
        raise RuntimeFoundationError(f"{code_prefix}_invalid", "Release candidate package schema is invalid.")
    if payload.get("marker") != RELEASE_CANDIDATE_PACKAGE_MARKER:
        raise RuntimeFoundationError(f"{code_prefix}_marker_missing", "Release candidate package marker is missing.")
    if payload.get("archive_ready") is not True or payload.get("replay_ready") is not True:
        raise RuntimeFoundationError(f"{code_prefix}_not_ready", "Release candidate package is not archive/replay ready.")
    _validate_static_refusal_predicates(payload, f"{code_prefix}")
    if not isinstance(payload.get("included_artifacts"), list) or not payload["included_artifacts"]:
        raise RuntimeFoundationError(f"{code_prefix}_artifacts_missing", "Release candidate package included artifacts are missing.")


def _validate_external_review_handoff(payload: dict[str, Any], package: dict[str, Any], code_prefix: str) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION or payload.get("kind") != "runtime_worker_external_review_handoff":
        raise RuntimeFoundationError(f"{code_prefix}_invalid", "External review handoff schema is invalid.")
    if payload.get("marker") != EXTERNAL_REVIEW_HANDOFF_MARKER:
        raise RuntimeFoundationError(f"{code_prefix}_marker_missing", "External review handoff marker is missing.")
    if payload.get("artifact_chain_root") != package.get("chain_root") or payload.get("terminal_artifact") != package.get("terminal_artifact"):
        raise RuntimeFoundationError(f"{code_prefix}_chain_mismatch", "External review handoff does not match release candidate chain.")
    if payload.get("archive_ready") is not True or payload.get("replay_ready") is not True:
        raise RuntimeFoundationError(f"{code_prefix}_not_ready", "External review handoff is not archive/replay ready.")
    _validate_static_refusal_predicates(payload, f"{code_prefix}")


def _archive_index_records(package_path: Path, package: dict[str, Any], handoff_path: Path, handoff: dict[str, Any], project_root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for artifact in package["included_artifacts"]:
        if artifact["role"] == "provenance_manifest":
            parents: list[str] = []
        else:
            parents = list(artifact.get("parent_artifact_ids", []))
        records.append(_archive_record(
            record_id=str(artifact["artifact_id"]),
            role=str(artifact["role"]),
            path=str(artifact["path"]),
            sha256=str(artifact["sha256"]),
            byte_count=int(artifact["byte_count"]),
            parents=parents,
            source_marker=str(artifact["source_marker"]),
            archive_ready=bool(artifact["archive_ready"]),
            replay_ready=bool(artifact["replay_ready"]),
        ))
    package_source = _artifact_source(package_path, project_root)
    records.append(_archive_record(
        record_id="release_candidate",
        role="release_candidate",
        path=package_source["path"],
        sha256=package_source["sha256"],
        byte_count=package_source["bytes"],
        parents=["provenance_manifest", str(package["terminal_artifact"])],
        source_marker=RELEASE_CANDIDATE_PACKAGE_MARKER,
        archive_ready=bool(package["archive_ready"]),
        replay_ready=bool(package["replay_ready"]),
    ))
    handoff_source = _artifact_source(handoff_path, project_root)
    records.append(_archive_record(
        record_id="external_review_handoff",
        role="external_review_handoff",
        path=handoff_source["path"],
        sha256=handoff_source["sha256"],
        byte_count=handoff_source["bytes"],
        parents=["release_candidate"],
        source_marker=EXTERNAL_REVIEW_HANDOFF_MARKER,
        archive_ready=bool(handoff["archive_ready"]),
        replay_ready=bool(handoff["replay_ready"]),
    ))
    return records


def _archive_record(*, record_id: str, role: str, path: str, sha256: str, byte_count: int, parents: list[str], source_marker: str, archive_ready: bool, replay_ready: bool) -> dict[str, Any]:
    return {
        "record_id": record_id,
        "role": role,
        "path": path,
        "sha256": sha256,
        "byte_count": byte_count,
        "parents": parents,
        "source_marker": source_marker,
        "archive_ready": archive_ready,
        "replay_ready": replay_ready,
    }


def _verify_archive_index(index: dict[str, Any], index_path: Path, project_root: Path) -> dict[str, Any]:
    reasons: list[str] = []
    if index.get("schema_version") != SCHEMA_VERSION or index.get("kind") != "runtime_worker_evidence_archive_index":
        reasons.append("archive_index_schema_invalid")
    if index.get("marker") != EVIDENCE_ARCHIVE_INDEX_MARKER:
        reasons.append("archive_index_marker_missing")
    _append_static_refusal_reasons(index, "archive_index", reasons)
    records = index.get("records")
    if not isinstance(records, list) or not records:
        records = []
        reasons.append("archive_index_empty")
    entries = [record for record in records if isinstance(record, dict)]
    if len(entries) != len(records):
        reasons.append("archive_record_invalid")
    if index.get("record_count") != len(entries):
        reasons.append("archive_record_count_mismatch")
    record_ids = [str(record.get("record_id", "")) for record in entries]
    roles = [str(record.get("role", "")) for record in entries]
    for record_id in sorted({record_id for record_id in record_ids if record_ids.count(record_id) > 1}):
        reasons.append(f"duplicate_record_id:{record_id}")
    for role in ARCHIVE_REQUIRED_ROLES:
        if role not in roles:
            reasons.append(f"required_role_missing:{role}")
    for role in sorted({role for role in roles if roles.count(role) > 1}):
        reasons.append(f"duplicate_role:{role}")
    by_id = {str(record.get("record_id", "")): record for record in entries}
    payloads: dict[str, dict[str, Any]] = {}
    for record in entries:
        record_id = str(record.get("record_id", ""))
        role = str(record.get("role", "unknown"))
        parents = record.get("parents")
        if not isinstance(parents, list):
            reasons.append(f"parents_invalid:{record_id or role}")
            parents = []
        for parent in parents:
            if str(parent) not in by_id:
                reasons.append(f"parent_missing:{record_id or role}:{parent}")
        if record.get("archive_ready") is not True:
            reasons.append(f"archive_ready_false:{record_id or role}")
        if record.get("replay_ready") is not True:
            reasons.append(f"replay_ready_false:{record_id or role}")
        artifact_path, path_reasons = _archive_record_path(record, project_root)
        reasons.extend(path_reasons)
        if artifact_path is None:
            continue
        current = _artifact_source(artifact_path, project_root)
        if record.get("sha256") != current["sha256"]:
            reasons.append(f"sha256_mismatch:{record_id or role}")
        if record.get("byte_count") != current["bytes"]:
            reasons.append(f"byte_count_mismatch:{record_id or role}")
        try:
            payload = _load_input_json(artifact_path, f"runtime_worker_archive_{role}")
        except RuntimeFoundationError:
            reasons.append(f"artifact_json_invalid:{record_id or role}")
            continue
        payloads[record_id] = payload
        if record.get("source_marker") != _payload_marker(payload):
            reasons.append(f"source_marker_mismatch:{record_id or role}")
        _append_static_refusal_reasons(payload, record_id or role, reasons)

    package = payloads.get("release_candidate")
    handoff = payloads.get("external_review_handoff")
    if package:
        _append_stale_package_reasons(package, by_id, project_root, reasons)
    if package and handoff:
        try:
            _validate_release_candidate_package(package, "runtime_worker_archive_release_candidate")
            _validate_external_review_handoff(handoff, package, "runtime_worker_archive_external_review_handoff")
        except RuntimeFoundationError as exc:
            reasons.append(exc.error_code)

    unique_reasons = _dedupe_text(reasons)
    archive_valid = not unique_reasons
    archive_ready = archive_valid and bool(index.get("archive_ready")) and all(record.get("archive_ready") is True for record in entries)
    replay_ready = archive_valid and bool(index.get("replay_ready")) and all(record.get("replay_ready") is True for record in entries)
    return {
        "ok": True,
        "command": "runtime worker-result archive-verify",
        "kind": "runtime_worker_evidence_archive_verification",
        "schema_version": SCHEMA_VERSION,
        "marker": EVIDENCE_ARCHIVE_VERIFY_MARKER,
        "index_source": _artifact_source(index_path, project_root),
        "archive_valid": archive_valid,
        "archive_ready": archive_ready,
        "replay_ready": replay_ready,
        "record_count": len(entries),
        "rejection_reasons": unique_reasons,
        "recovery_guidance": _archive_recovery_guidance(unique_reasons),
        "invocation_allowed": False,
        "external_execution_refused": True,
        "provider_calls": False,
        "model_calls": False,
        "browser_calls": False,
        "shell_calls": False,
        "safety_boundaries": dict(WORKER_SAFETY_BOUNDARIES),
    }


def _archive_record_path(record: dict[str, Any], project_root: Path) -> tuple[Path | None, list[str]]:
    role = str(record.get("record_id") or record.get("role") or "unknown")
    raw_path = str(record.get("path", ""))
    if not raw_path.strip():
        return None, [f"artifact_path_missing:{role}"]
    raw = Path(raw_path)
    if any(part == ".." for part in raw.parts):
        return None, [f"artifact_path_traversal:{role}"]
    if any(part == ".env" for part in raw.parts):
        return None, [f"artifact_dotenv_refused:{role}"]
    root = project_root.resolve(strict=True)
    candidate = raw if raw.is_absolute() else root / raw
    try:
        candidate.relative_to(root)
    except ValueError:
        return None, [f"artifact_outside_project:{role}"]
    parent = candidate.parent.resolve(strict=False)
    if parent != root and root not in parent.parents:
        return None, [f"artifact_outside_project:{role}"]
    if candidate.parent.exists() and candidate.parent.is_symlink():
        return None, [f"artifact_parent_symlink:{role}"]
    if not candidate.exists():
        return None, [f"artifact_missing:{role}"]
    if candidate.is_symlink():
        return None, [f"artifact_symlink:{role}"]
    if not candidate.is_file():
        return None, [f"artifact_not_file:{role}"]
    return candidate.resolve(strict=False), []


def _append_stale_package_reasons(package: dict[str, Any], records_by_id: dict[str, dict[str, Any]], project_root: Path, reasons: list[str]) -> None:
    for artifact in package.get("included_artifacts", []):
        if not isinstance(artifact, dict):
            reasons.append("stale_package:artifact_entry_invalid")
            continue
        record_id = str(artifact.get("artifact_id", ""))
        record = records_by_id.get(record_id)
        if not record:
            reasons.append(f"stale_package:record_missing:{record_id}")
            continue
        artifact_path, path_reasons = _archive_record_path(record, project_root)
        if artifact_path is None:
            continue
        current = _artifact_source(artifact_path, project_root)
        if artifact.get("sha256") != current["sha256"] or artifact.get("byte_count") != current["bytes"]:
            reasons.append(f"stale_package:{record_id}")


def _payload_marker(payload: dict[str, Any]) -> str:
    marker = payload.get("marker", payload.get("packet_marker", ""))
    return str(marker)


def _validate_static_refusal_predicates(payload: dict[str, Any], code_prefix: str) -> None:
    if payload.get("invocation_allowed") is not False or payload.get("external_execution_refused") is not True:
        raise RuntimeFoundationError(f"{code_prefix}_static_refusal_invalid", "Static refusal predicates are invalid.")
    for key in ("provider_calls", "model_calls", "browser_calls", "shell_calls"):
        if payload.get(key) is not False:
            raise RuntimeFoundationError(f"{code_prefix}_{key}_not_false", f"{key} must be false.")


def _append_static_refusal_reasons(payload: dict[str, Any], label: str, reasons: list[str]) -> None:
    if payload.get("invocation_allowed") is not False:
        reasons.append(f"invocation_not_refused:{label}")
    if payload.get("external_execution_refused") is not True:
        reasons.append(f"external_execution_not_refused:{label}")
    for key in ("provider_calls", "model_calls", "browser_calls", "shell_calls"):
        if payload.get(key) is not False:
            reasons.append(f"{key}_not_false:{label}")


def _archive_recovery_guidance(reasons: list[str]) -> list[str]:
    if not reasons:
        return ["No recovery required; evidence archive index is intact and replay-ready."]
    guidance: list[str] = []
    if any("missing" in reason for reason in reasons):
        guidance.append("Restore or regenerate the missing package, handoff, or chain artifact, then regenerate the archive index.")
    if any(reason.startswith(("sha256_mismatch:", "byte_count_mismatch:", "stale_package:")) for reason in reasons):
        guidance.append("Regenerate the release candidate package and archive index from the current provenance manifest artifacts.")
    if any(reason.startswith(("duplicate_record_id:", "parent_missing:", "required_role_missing:", "parents_invalid:")) for reason in reasons):
        guidance.append("Regenerate the archive index with canonical record ids, required roles, and parent links.")
    if any(reason.startswith(("archive_ready_false:", "replay_ready_false:", "invocation_not_refused:", "external_execution_not_refused:", "provider_calls_not_false:", "model_calls_not_false:", "browser_calls_not_false:", "shell_calls_not_false:")) for reason in reasons):
        guidance.append("Restore archive/replay readiness and static refusal predicates before re-indexing.")
    if not guidance:
        guidance.append("Regenerate the archive index from verified release candidate and handoff artifacts.")
    guidance.append("Rerun runtime worker-result archive-verify after recovery.")
    return _dedupe_text(guidance)


def _format_release_candidate_text(payload: dict[str, Any]) -> str:
    lines = [
        "# AgentOffice Release Candidate Package",
        "",
        f"schema_version: {payload['schema_version']}",
        f"marker: {payload['marker']}",
        f"generated_at: {payload['generated_at']}",
        f"review_target: {payload['review_target']}",
        f"chain_root: {payload['chain_root']}",
        f"terminal_artifact: {payload['terminal_artifact']}",
        f"archive_ready: {str(payload['archive_ready']).lower()}",
        f"replay_ready: {str(payload['replay_ready']).lower()}",
        "",
        "## Included Artifacts",
    ]
    lines.extend(f"- {artifact['role']}: {artifact['path']} sha256={artifact['sha256']} bytes={artifact['byte_count']}" for artifact in payload["included_artifacts"])
    return "\n".join(lines)


def _format_external_review_handoff_text(payload: dict[str, Any]) -> str:
    lines = [
        "# AgentOffice External Review Handoff",
        "",
        f"schema_version: {payload['schema_version']}",
        f"marker: {payload['marker']}",
        f"review_target: {payload['review_target']}",
        f"artifact_chain_root: {payload['artifact_chain_root']}",
        f"terminal_artifact: {payload['terminal_artifact']}",
        f"expected_reviewer_output_marker: {payload['expected_reviewer_output_marker']}",
        f"attestation_import_path: {payload['attestation_import_path']}",
        "",
        "## Integrity Verification Instructions",
    ]
    lines.extend(f"- {item}" for item in payload["integrity_verification_instructions"])
    lines.extend(["", "## Replay Instructions"])
    lines.extend(f"- {item}" for item in payload["replay_instructions"])
    lines.extend(["", f"known_safety_caveat: {payload['known_safety_caveat']}"])
    return "\n".join(lines)


def _format_archive_index_text(payload: dict[str, Any]) -> str:
    lines = [
        "# AgentOffice Evidence Archive Index",
        "",
        f"schema_version: {payload['schema_version']}",
        f"marker: {payload['marker']}",
        f"record_count: {payload['record_count']}",
        f"archive_ready: {str(payload['archive_ready']).lower()}",
        f"replay_ready: {str(payload['replay_ready']).lower()}",
        "",
        "## Records",
    ]
    lines.extend(f"- {record['record_id']} ({record['role']}): {record['path']} sha256={record['sha256']} bytes={record['byte_count']} parents={','.join(record['parents']) or '-'}" for record in payload["records"])
    return "\n".join(lines)


def _format_reviewer_archive_import_text(payload: dict[str, Any]) -> str:
    return _format_release_loop_text(
        "AgentOffice External Reviewer Archive Import",
        payload,
        ["marker", "review_verdict", "review_marker", "archive_ready", "replay_ready", "terminal_status", "output_path"],
    )


def _format_release_closure_text(payload: dict[str, Any]) -> str:
    return _format_release_loop_text(
        "AgentOffice Release Closure Bundle",
        payload,
        ["marker", "closure_status", "review_verdict", "delivery_ready", "promotion_ready", "next_action", "output_path"],
    )


def _format_archive_replay_text(payload: dict[str, Any]) -> str:
    return _format_release_loop_text(
        "AgentOffice Archive Replay Verification",
        payload,
        ["marker", "archive_replay_valid", "archive_ready", "replay_ready", "closure_status", "review_verdict", "output_path"],
    )


def _format_final_readiness_text(payload: dict[str, Any]) -> str:
    return _format_release_loop_text(
        "AgentOffice Final Delivery Readiness",
        payload,
        ["marker", "delivery_ready", "promotion_ready", "review_verdict", "closure_status", "next_action", "output_path"],
    )


def _format_review_recovery_text(payload: dict[str, Any]) -> str:
    return _format_release_loop_text(
        "AgentOffice Failed Review Recovery",
        payload,
        ["marker", "recovery_required", "recovery_status", "original_review_verdict", "original_closure_status", "output_path"],
    )


def _format_compact_archive_text(payload: dict[str, Any]) -> str:
    lines = _format_release_loop_lines(
        "AgentOffice Compact Evidence Archive Index",
        payload,
        ["marker", "record_count", "archive_ready", "replay_ready", "terminal_status", "output_path"],
    )
    lines.extend(["", "## Records"])
    lines.extend(f"- {record['record_id']} ({record['role']}): {record['path']} sha256={record['sha256']} bytes={record['byte_count']} parents={','.join(record['parents']) or '-'} terminal_status={record['terminal_status']}" for record in payload["records"])
    return "\n".join(lines)


def _format_promotion_gate_text(payload: dict[str, Any]) -> str:
    return _format_release_loop_text(
        "AgentOffice Release Candidate Promotion Gate",
        payload,
        ["marker", "promotion_ready", "delivery_ready", "next_action", "real_release_executed", "tag_created", "default_branch_changed", "output_path"],
    )



def _format_release_candidate_export_text(payload: dict[str, Any]) -> str:
    lines = _format_release_loop_lines(
        "AgentOffice Release Candidate Export Packet",
        payload,
        ["marker", "record_count", "manifest_digest", "export_ready", "output_path"],
    )
    lines.extend(["", "## Records"])
    lines.extend(f"- {record['record_id']} ({record['role']}): {record['path']} sha256={record['sha256']}" for record in payload["manifest"]["records"])
    return "\n".join(lines)


def _format_promotion_evidence_text(payload: dict[str, Any]) -> str:
    lines = _format_release_loop_lines(
        "AgentOffice Promotion Evidence Packet",
        payload,
        ["marker", "evidence_ready", "promotion_ready", "output_path"],
    )
    refs = payload["reviewed_refs"]
    lines.extend([
        "",
        "## Reviewed Refs",
        f"source_branch: {refs['source_branch']}",
        f"source_head: {refs['source_head']}",
        f"target_branch: {refs['target_branch']}",
        f"target_before: {refs['target_before']}",
        f"final_mainline: {refs['final_mainline']}",
    ])
    lines.extend(["", "## No Real Promotion Proof"])
    lines.extend(f"{key}: {str(value).lower() if isinstance(value, bool) else value}" for key, value in payload["no_real_promotion_proof"].items())
    return "\n".join(lines)


def _format_dry_run_publish_text(payload: dict[str, Any]) -> str:
    return _format_release_loop_text(
        "AgentOffice Dry-run Publish Packet",
        payload,
        ["marker", "candidate_release_id", "target_branch", "target_commit", "publish_ready", "would_create_tag", "would_create_release", "would_push", "would_change_default_branch", "output_path"],
    )


def _format_release_loop_text(title: str, payload: dict[str, Any], keys: list[str]) -> str:
    return "\n".join(_format_release_loop_lines(title, payload, keys))


def _format_release_loop_lines(title: str, payload: dict[str, Any], keys: list[str]) -> list[str]:
    lines = [f"# {title}", "", f"schema_version: {payload['schema_version']}"]
    for key in keys:
        value = payload.get(key)
        if isinstance(value, bool):
            value = str(value).lower()
        lines.append(f"{key}: {value}")
    if "rejection_reasons" in payload:
        lines.append(f"rejection_reasons: {', '.join(payload['rejection_reasons']) or 'none'}")
    if "recovery_guidance" in payload:
        lines.append("recovery_guidance:")
        lines.extend(f"- {item}" for item in payload["recovery_guidance"])
    return lines


def _validate_external_reviewer_import(payload: dict[str, Any], code_prefix: str) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION or payload.get("kind") != "runtime_worker_external_reviewer_archive_import":
        raise RuntimeFoundationError(f"{code_prefix}_invalid", "External reviewer archive import schema is invalid.")
    if payload.get("marker") != EXTERNAL_REVIEW_ARCHIVE_IMPORT_MARKER:
        raise RuntimeFoundationError(f"{code_prefix}_marker_missing", "External reviewer archive import marker is missing.")
    if not str(payload.get("review_verdict", "")).strip():
        raise RuntimeFoundationError(f"{code_prefix}_verdict_missing", "External reviewer import verdict is missing.")
    if not isinstance(payload.get("archive_import_record"), dict):
        raise RuntimeFoundationError(f"{code_prefix}_record_missing", "External reviewer import record is missing.")
    _validate_static_refusal_predicates(payload, code_prefix)


def _validate_release_closure_bundle(payload: dict[str, Any], code_prefix: str) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION or payload.get("kind") != "runtime_worker_release_closure_bundle":
        raise RuntimeFoundationError(f"{code_prefix}_invalid", "Release closure bundle schema is invalid.")
    if payload.get("marker") != RELEASE_CLOSURE_BUNDLE_MARKER:
        raise RuntimeFoundationError(f"{code_prefix}_marker_missing", "Release closure bundle marker is missing.")
    _validate_static_refusal_predicates(payload, code_prefix)


def _validate_archive_replay_verification(payload: dict[str, Any], code_prefix: str) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION or payload.get("kind") != "runtime_worker_archive_replay_verification":
        raise RuntimeFoundationError(f"{code_prefix}_invalid", "Archive replay verification schema is invalid.")
    if payload.get("marker") != ARCHIVE_REPLAY_VERIFICATION_MARKER:
        raise RuntimeFoundationError(f"{code_prefix}_marker_missing", "Archive replay verification marker is missing.")
    _validate_static_refusal_predicates(payload, code_prefix)


def _validate_final_delivery_readiness(payload: dict[str, Any], code_prefix: str) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION or payload.get("kind") != "runtime_worker_final_delivery_readiness_packet":
        raise RuntimeFoundationError(f"{code_prefix}_invalid", "Final delivery readiness schema is invalid.")
    if payload.get("marker") != FINAL_DELIVERY_READINESS_MARKER:
        raise RuntimeFoundationError(f"{code_prefix}_marker_missing", "Final delivery readiness marker is missing.")
    _validate_static_refusal_predicates(payload, code_prefix)


def _archive_verification_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "archive_valid": bool(payload["archive_valid"]),
        "archive_ready": bool(payload["archive_ready"]),
        "replay_ready": bool(payload["replay_ready"]),
        "record_count": int(payload["record_count"]),
        "rejection_reasons": list(payload["rejection_reasons"]),
    }


def _release_closure_reasons(package: dict[str, Any], handoff: dict[str, Any], archive_verification: dict[str, Any], reviewer_import: dict[str, Any], provenance_verification: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    verdict = str(reviewer_import.get("review_verdict", "")).lower()
    if verdict != "pass":
        reasons.append(f"reviewer_verdict_not_pass:{verdict or 'missing'}")
    if reviewer_import.get("review_marker") != handoff.get("expected_reviewer_output_marker"):
        reasons.append("reviewer_marker_mismatch")
    if archive_verification.get("archive_valid") is not True:
        reasons.append("archive_index_not_valid")
    if archive_verification.get("archive_ready") is not True:
        reasons.append("archive_not_ready")
    if archive_verification.get("replay_ready") is not True:
        reasons.append("archive_replay_not_ready")
    if provenance_verification.get("chain_valid") is not True:
        reasons.append("provenance_chain_not_valid")
    if package.get("archive_ready") is not True or package.get("replay_ready") is not True:
        reasons.append("release_candidate_not_ready")
    if reviewer_import.get("archive_ready") is not True:
        reasons.append("reviewer_import_archive_not_ready")
    if reviewer_import.get("replay_ready") is not True:
        reasons.append("reviewer_import_replay_not_ready")
    for label, payload in (("release_candidate", package), ("external_review_handoff", handoff), ("reviewer_import", reviewer_import)):
        _append_static_refusal_reasons(payload, label, reasons)
    return _dedupe_text(reasons)


def _static_refusal_predicate_summary(payloads: list[dict[str, Any]]) -> dict[str, bool]:
    return {
        "invocation_allowed_false": all(payload.get("invocation_allowed") is False for payload in payloads),
        "external_execution_refused_true": all(payload.get("external_execution_refused") is True for payload in payloads),
        "provider_calls_false": all(payload.get("provider_calls") is False for payload in payloads),
        "model_calls_false": all(payload.get("model_calls") is False for payload in payloads),
        "browser_calls_false": all(payload.get("browser_calls") is False for payload in payloads),
        "shell_calls_false": all(payload.get("shell_calls") is False for payload in payloads),
    }


def _closure_required_evidence(reasons: list[str]) -> list[str]:
    if not reasons:
        return ["No additional evidence required."]
    evidence: list[str] = []
    if any(reason.startswith("reviewer_") for reason in reasons):
        evidence.append("Fixed external reviewer output with expected marker, verdict PASS, caveat, findings summary, and reviewed artifact chain.")
    if any("archive" in reason or "stale" in reason for reason in reasons):
        evidence.append("Regenerated release candidate package, handoff, and archive index from current artifacts.")
    if any("provenance" in reason for reason in reasons):
        evidence.append("Verified provenance manifest and replay-ready artifact chain.")
    if any("not_false" in reason or "not_refused" in reason for reason in reasons):
        evidence.append("Restored static refusal predicates: invocation_allowed=false, external_execution_refused=true, and provider/model/browser/shell calls false.")
    return _dedupe_text(evidence or ["Regenerated release closure evidence from current verified artifacts."])


def _release_closure_recovery_guidance(reasons: list[str]) -> list[str]:
    if not reasons:
        return ["No recovery required; release closure is reviewer-ready and archive-ready."]
    guidance = _closure_required_evidence(reasons)
    guidance.append("Rerun reviewer-archive-import, release-closure, archive-replay, and final-readiness after recovery.")
    return _dedupe_text(guidance)


def _archive_replay_recovery_guidance(reasons: list[str]) -> list[str]:
    if not reasons:
        return ["No recovery required; archive replay verification passed."]
    guidance = _archive_recovery_guidance(reasons)
    guidance.append("Regenerate release-closure before rerunning archive-replay when reviewer evidence changed.")
    return _dedupe_text(guidance)


def _final_readiness_required_evidence(reasons: list[str]) -> list[str]:
    if not reasons:
        return ["No additional evidence required."]
    evidence = _closure_required_evidence(reasons)
    if any("archive_replay" in reason for reason in reasons):
        evidence.append("Passing archive replay verification packet.")
    return _dedupe_text(evidence)


def _final_readiness_recovery_guidance(reasons: list[str]) -> list[str]:
    if not reasons:
        return ["No recovery required; final delivery readiness passed."]
    guidance = _final_readiness_required_evidence(reasons)
    guidance.append("Rerun final-readiness after release closure and archive replay pass.")
    return _dedupe_text(guidance)


def _compact_archive_records(archive_payload: dict[str, Any], closure: dict[str, Any], closure_path: Path, replay: dict[str, Any], replay_path: Path, readiness: dict[str, Any], readiness_path: Path, project_root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for record in archive_payload.get("records", []):
        if not isinstance(record, dict):
            continue
        compact = dict(record)
        compact["terminal_status"] = "ready" if record.get("archive_ready") is True and record.get("replay_ready") is True else "blocked"
        records.append(compact)
    import_source = closure["reviewer_import_source"]
    records.append(_compact_record_from_source(
        record_id="external_reviewer_import",
        role="external_reviewer_import",
        source=import_source,
        parents=["external_review_handoff"],
        source_marker=EXTERNAL_REVIEW_ARCHIVE_IMPORT_MARKER,
        archive_ready=closure.get("review_verdict") == "pass",
        replay_ready=closure.get("review_verdict") == "pass",
        terminal_status="ready" if closure.get("review_verdict") == "pass" else "blocked",
    ))
    closure_source = _artifact_source(closure_path, project_root)
    records.append(_compact_record_from_source(
        record_id="release_closure",
        role="release_closure",
        source=closure_source,
        parents=["release_candidate", "external_reviewer_import"],
        source_marker=RELEASE_CLOSURE_BUNDLE_MARKER,
        archive_ready=bool(closure.get("archive_ready")),
        replay_ready=bool(closure.get("replay_ready")),
        terminal_status=str(closure.get("closure_status", "unknown")),
    ))
    replay_source = _artifact_source(replay_path, project_root)
    records.append(_compact_record_from_source(
        record_id="archive_replay",
        role="archive_replay",
        source=replay_source,
        parents=["release_closure", "release_candidate"],
        source_marker=ARCHIVE_REPLAY_VERIFICATION_MARKER,
        archive_ready=bool(replay.get("archive_ready")),
        replay_ready=bool(replay.get("replay_ready")),
        terminal_status="ready" if replay.get("archive_replay_valid") is True else "blocked",
    ))
    readiness_source = _artifact_source(readiness_path, project_root)
    records.append(_compact_record_from_source(
        record_id="final_delivery_readiness",
        role="final_delivery_readiness",
        source=readiness_source,
        parents=["archive_replay", "release_closure"],
        source_marker=FINAL_DELIVERY_READINESS_MARKER,
        archive_ready=bool(readiness.get("delivery_ready")),
        replay_ready=bool(readiness.get("promotion_ready")),
        terminal_status="ready" if readiness.get("delivery_ready") is True and readiness.get("promotion_ready") is True else "blocked",
    ))
    return records


def _compact_record_from_source(*, record_id: str, role: str, source: dict[str, Any], parents: list[str], source_marker: str, archive_ready: bool, replay_ready: bool, terminal_status: str) -> dict[str, Any]:
    record = _archive_record(
        record_id=record_id,
        role=role,
        path=str(source["path"]),
        sha256=str(source["sha256"]),
        byte_count=int(source["bytes"]),
        parents=parents,
        source_marker=source_marker,
        archive_ready=archive_ready,
        replay_ready=replay_ready,
    )
    record["terminal_status"] = terminal_status
    return record


def _verify_compact_archive_index(index: dict[str, Any], index_path: Path, project_root: Path) -> dict[str, Any]:
    reasons: list[str] = []
    if index.get("schema_version") != SCHEMA_VERSION or index.get("kind") != "runtime_worker_compact_evidence_archive_index":
        reasons.append("compact_index_schema_invalid")
    if index.get("marker") != COMPACT_ARCHIVE_INDEX_MARKER:
        reasons.append("compact_index_marker_missing")
    _append_static_refusal_reasons(index, "compact_archive", reasons)
    records = index.get("records")
    if not isinstance(records, list) or not records:
        records = []
        reasons.append("compact_index_empty")
    entries = [record for record in records if isinstance(record, dict)]
    if len(entries) != len(records):
        reasons.append("compact_record_invalid")
    if index.get("record_count") != len(entries):
        reasons.append("compact_record_count_mismatch")
    record_ids = [str(record.get("record_id", "")) for record in entries]
    roles = [str(record.get("role", "")) for record in entries]
    for record_id in sorted({record_id for record_id in record_ids if record_ids.count(record_id) > 1}):
        reasons.append(f"duplicate_record_id:{record_id}")
    for role in COMPACT_ARCHIVE_REQUIRED_ROLES:
        if role not in roles:
            reasons.append(f"required_role_missing:{role}")
    for role in sorted({role for role in roles if roles.count(role) > 1}):
        reasons.append(f"duplicate_role:{role}")
    by_id = {str(record.get("record_id", "")): record for record in entries}
    payloads: dict[str, dict[str, Any]] = {}
    for record in entries:
        record_id = str(record.get("record_id", ""))
        role = str(record.get("role", "unknown"))
        parents = record.get("parents")
        if not isinstance(parents, list):
            reasons.append(f"parents_invalid:{record_id or role}")
            parents = []
        for parent in parents:
            if str(parent) not in by_id:
                reasons.append(f"parent_missing:{record_id or role}:{parent}")
        if record.get("archive_ready") is not True:
            reasons.append(f"archive_ready_false:{record_id or role}")
        if record.get("replay_ready") is not True:
            reasons.append(f"replay_ready_false:{record_id or role}")
        if not str(record.get("terminal_status", "")).strip():
            reasons.append(f"terminal_status_missing:{record_id or role}")
        artifact_path, path_reasons = _archive_record_path(record, project_root)
        reasons.extend(path_reasons)
        if artifact_path is None:
            continue
        current = _artifact_source(artifact_path, project_root)
        if record.get("sha256") != current["sha256"]:
            reasons.append(f"sha256_mismatch:{record_id or role}")
        if record.get("byte_count") != current["bytes"]:
            reasons.append(f"byte_count_mismatch:{record_id or role}")
        try:
            payload = _load_input_json(artifact_path, f"runtime_worker_compact_archive_{role}")
        except RuntimeFoundationError:
            reasons.append(f"artifact_json_invalid:{record_id or role}")
            continue
        payloads[record_id] = payload
        if record.get("source_marker") != _payload_marker(payload):
            reasons.append(f"source_marker_mismatch:{record_id or role}")
        _append_static_refusal_reasons(payload, record_id or role, reasons)
    final_readiness = payloads.get("final_delivery_readiness")
    if final_readiness and (final_readiness.get("delivery_ready") is not True or final_readiness.get("promotion_ready") is not True):
        reasons.append("final_delivery_not_ready")
    release_closure = payloads.get("release_closure")
    if release_closure and release_closure.get("closure_status") != "closed":
        reasons.append("release_closure_not_closed")
    unique_reasons = _dedupe_text(reasons)
    compact_valid = not unique_reasons
    return {
        "ok": True,
        "command": "runtime worker-result compact-verify",
        "kind": "runtime_worker_compact_evidence_archive_verification",
        "schema_version": SCHEMA_VERSION,
        "marker": COMPACT_ARCHIVE_VERIFY_MARKER,
        "compact_index_source": _artifact_source(index_path, project_root),
        "compact_valid": compact_valid,
        "archive_ready": compact_valid and bool(index.get("archive_ready")) and all(record.get("archive_ready") is True for record in entries),
        "replay_ready": compact_valid and bool(index.get("replay_ready")) and all(record.get("replay_ready") is True for record in entries),
        "record_count": len(entries),
        "rejection_reasons": unique_reasons,
        "recovery_guidance": _compact_archive_recovery_guidance(unique_reasons),
        "invocation_allowed": False,
        "external_execution_refused": True,
        "provider_calls": False,
        "model_calls": False,
        "browser_calls": False,
        "shell_calls": False,
        "safety_boundaries": dict(WORKER_SAFETY_BOUNDARIES),
    }



def _validate_rc_promotion_gate(payload: dict[str, Any], code_prefix: str) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION or payload.get("kind") != "runtime_worker_release_candidate_promotion_gate":
        raise RuntimeFoundationError(f"{code_prefix}_invalid", "RC promotion gate schema is invalid.")
    if payload.get("marker") != RC_PROMOTION_GATE_MARKER:
        raise RuntimeFoundationError(f"{code_prefix}_marker_missing", "RC promotion gate marker is missing.")
    if payload.get("real_release_executed") is not False or payload.get("tag_created") is not False or payload.get("default_branch_changed") is not False:
        raise RuntimeFoundationError(f"{code_prefix}_real_promotion_predicate_invalid", "RC promotion gate must prove no release, tag, or default branch mutation occurred.")
    _validate_static_refusal_predicates(payload, code_prefix)


def _validate_release_candidate_export_packet(payload: dict[str, Any], code_prefix: str) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION or payload.get("kind") != "runtime_worker_release_candidate_export_packet":
        raise RuntimeFoundationError(f"{code_prefix}_invalid", "Release candidate export packet schema is invalid.")
    if payload.get("marker") != RELEASE_CANDIDATE_EXPORT_PACKET_MARKER:
        raise RuntimeFoundationError(f"{code_prefix}_marker_missing", "Release candidate export packet marker is missing.")
    manifest = payload.get("manifest")
    if not isinstance(manifest, dict) or not isinstance(manifest.get("records"), list):
        raise RuntimeFoundationError(f"{code_prefix}_manifest_invalid", "Release candidate export manifest is invalid.")
    digest = str(payload.get("manifest_digest", ""))
    if not digest or digest != _stable_payload_digest(manifest):
        raise RuntimeFoundationError(f"{code_prefix}_digest_mismatch", "Release candidate export digest does not match manifest.")
    _validate_static_refusal_predicates(payload, code_prefix)


def _validate_promotion_evidence_packet(payload: dict[str, Any], code_prefix: str) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION or payload.get("kind") != "runtime_worker_promotion_evidence_packet":
        raise RuntimeFoundationError(f"{code_prefix}_invalid", "Promotion evidence packet schema is invalid.")
    if payload.get("marker") != PROMOTION_EVIDENCE_PACKET_MARKER:
        raise RuntimeFoundationError(f"{code_prefix}_marker_missing", "Promotion evidence packet marker is missing.")
    refs = payload.get("reviewed_refs")
    if not isinstance(refs, dict) or not refs.get("source_head") or not refs.get("target_branch"):
        raise RuntimeFoundationError(f"{code_prefix}_refs_invalid", "Promotion evidence reviewed refs are invalid.")
    proof = payload.get("no_real_promotion_proof")
    if not isinstance(proof, dict) or any(proof.get(key) is not False for key in ("real_release_executed", "tag_created", "github_release_created", "default_branch_changed", "force_push_executed")):
        raise RuntimeFoundationError(f"{code_prefix}_real_promotion_proof_invalid", "Promotion evidence must prove no real release, tag, force push, or default branch mutation occurred.")
    _validate_static_refusal_predicates(payload, code_prefix)


def _release_candidate_export_records(index: dict[str, Any]) -> list[dict[str, Any]]:
    records = [record for record in index.get("records", []) if isinstance(record, dict)]
    ordered = sorted(records, key=lambda record: (str(record.get("role", "")), str(record.get("record_id", ""))))
    return [
        {
            "record_id": str(record.get("record_id", "")),
            "role": str(record.get("role", "")),
            "path": str(record.get("path", "")),
            "sha256": str(record.get("sha256", "")),
            "byte_count": int(record.get("byte_count", 0)),
            "parents": [str(parent) for parent in record.get("parents", [])],
            "source_marker": str(record.get("source_marker", "")),
        }
        for record in ordered
    ]


def _archive_payload_by_role(index: dict[str, Any], role: str, project_root: Path, code_prefix: str) -> dict[str, Any]:
    records = index.get("records")
    if not isinstance(records, list):
        raise RuntimeFoundationError(f"{code_prefix}_records_invalid", "Archive records are invalid.")
    matches = [record for record in records if isinstance(record, dict) and record.get("role") == role]
    if len(matches) != 1:
        raise RuntimeFoundationError(f"{code_prefix}_{role}_record_invalid", f"Expected exactly one archive record for role: {role}")
    artifact_path, reasons = _archive_record_path(matches[0], project_root)
    if artifact_path is None:
        raise RuntimeFoundationError(f"{code_prefix}_{role}_path_invalid", ", ".join(reasons))
    return _load_input_json(artifact_path, f"{code_prefix}_{role}")


def _no_real_promotion_proof() -> dict[str, bool]:
    return {
        "real_release_executed": False,
        "tag_created": False,
        "github_release_created": False,
        "default_branch_changed": False,
        "force_push_executed": False,
    }


def _candidate_release_id(candidate_name: str, target_commit: str) -> str:
    name = str(candidate_name).strip().lower().replace(" ", "-") or "agentoffice-release-candidate"
    commit = str(target_commit).strip()[:12] or "unknown"
    return f"{name}-{commit}"


def _compact_archive_recovery_guidance(reasons: list[str]) -> list[str]:
    if not reasons:
        return ["No recovery required; compact archive index is intact and replay-ready."]
    guidance = _archive_recovery_guidance(reasons)
    if any(reason.startswith(("terminal_status_missing:", "final_delivery_not_ready", "release_closure_not_closed")) for reason in reasons):
        guidance.append("Regenerate release closure, archive replay, final readiness, and compact archive after fixing terminal status evidence.")
    guidance.append("Rerun runtime worker-result compact-verify after recovery.")
    return _dedupe_text(guidance)


def _promotion_recovery_guidance(reasons: list[str]) -> list[str]:
    if not reasons:
        return ["No recovery required; static RC promotion packet is ready. No release, tag, or default branch change was executed."]
    guidance = _compact_archive_recovery_guidance(reasons)
    guidance.append("Rerun rc-promotion-gate only after final-readiness and compact-verify pass.")
    return _dedupe_text(guidance)


def _provenance_artifact_entry(role: str, path: Path, payload: dict[str, Any], project_root: Path) -> dict[str, Any]:
    source = _artifact_source(path, project_root)
    return {
        "artifact_id": role,
        "role": role,
        "path": source["path"],
        "sha256": source["sha256"],
        "byte_count": source["bytes"],
        "parent_artifact_ids": list(PROVENANCE_PARENT_IDS[role]),
        "replay_status": _provenance_role_replay_status(role, payload),
        "readiness": _provenance_role_readiness(role, payload),
    }


def _validate_provenance_payload_shape(role: str, payload: dict[str, Any], code_prefix: str) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION or payload.get("kind") != PROVENANCE_ROLE_KINDS[role]:
        raise RuntimeFoundationError(f"{code_prefix}_invalid", f"Provenance artifact schema is invalid for role: {role}")
    marker_expectations = {
        "reviewer_attestation": REVIEWER_ATTESTATION_PACKET_MARKER,
        "closure_evidence": CLOSURE_EVIDENCE_IMPORTED_MARKER,
        "merge_readiness": MERGE_READINESS_PACKET_MARKER,
        "delivery_gate": DELIVERY_GATE_PACKET_MARKER,
        "rejection_recovery": REJECTION_RECOVERY_PACKET_MARKER,
        "audit_replay": AUDIT_PACKET_REPLAY_MARKER,
    }
    marker_key = "packet_marker" if role == "reviewer_attestation" else "marker"
    if payload.get(marker_key) != marker_expectations[role]:
        raise RuntimeFoundationError(f"{code_prefix}_marker_missing", f"Provenance artifact marker is missing for role: {role}")


def _provenance_role_replay_status(role: str, payload: dict[str, Any]) -> bool:
    readiness = _provenance_role_readiness(role, payload)
    return all(value is True for value in readiness.values() if isinstance(value, bool))


def _provenance_role_readiness(role: str, payload: dict[str, Any]) -> dict[str, Any]:
    if role == "reviewer_attestation":
        return {
            "reviewer_attestation_present": payload.get("reviewer_attestation_present") is True,
            "reviewer_verdict_pass": str(payload.get("verdict", "")).lower() == "pass",
        }
    if role == "closure_evidence":
        return {
            "closure_evidence_imported": payload.get("closure_evidence_imported") is True,
            "gate_readable": payload.get("gate_readable") is True,
            "audit_replayable": payload.get("audit_replayable") is True,
            "reviewer_attestation_present": payload.get("reviewer_attestation_present") is True,
        }
    if role == "merge_readiness":
        return {
            "merge_readiness_ready": payload.get("merge_readiness_ready") is True,
            "external_worker_replay_ready": payload.get("external_worker_replay_ready") is True,
            "audit_closure_ready": payload.get("audit_closure_ready") is True,
            "delivery_bundle_ready": payload.get("delivery_bundle_ready") is True,
        }
    if role == "delivery_gate":
        return {"delivery_gate_pass": payload.get("delivery_gate_pass") is True}
    if role == "rejection_recovery":
        return {
            "replay_ready": payload.get("replay_ready") is True,
            "governance_ready": payload.get("governance_ready") is True,
            "recovery_not_required": str(payload.get("recovery_status", "")) == "not_required",
        }
    if role == "audit_replay":
        return {
            "audit_replay_ready": payload.get("replay_ready") is True,
            "governance_ready": payload.get("governance_ready") is True,
            "original_readiness": payload.get("original_readiness") is True,
        }
    return {"unknown_role": False}


def _provenance_readiness_summary(payloads: dict[str, dict[str, Any]]) -> dict[str, Any]:
    delivery_gate = payloads.get("delivery_gate", {})
    rejection = payloads.get("rejection_recovery", {})
    audit = payloads.get("audit_replay", {})
    role_statuses = {role: _provenance_role_replay_status(role, payloads[role]) for role in PROVENANCE_REQUIRED_ROLE_ORDER if role in payloads}
    terminal_readiness = all(role_statuses.get(role) is True for role in PROVENANCE_REQUIRED_ROLE_ORDER)
    return {
        "terminal_readiness": terminal_readiness,
        "role_replay_statuses": role_statuses,
        "delivery_gate_pass": delivery_gate.get("delivery_gate_pass") is True,
        "rejection_reasons": list(delivery_gate.get("rejection_reasons") or rejection.get("rejection_reasons") or audit.get("rejection_reasons") or []),
        "recovery_status": str(rejection.get("recovery_status", audit.get("recovery_status", "unknown"))),
        "audit_replay_ready": audit.get("replay_ready") is True,
        "governance_ready": audit.get("governance_ready") is True,
    }


def _verify_provenance_manifest(manifest: dict[str, Any], manifest_path: Path, project_root: Path, *, command: str) -> dict[str, Any]:
    reasons: list[str] = []
    if manifest.get("schema_version") != SCHEMA_VERSION or manifest.get("kind") != "runtime_worker_provenance_manifest":
        reasons.append("manifest_schema_invalid")
    if manifest.get("marker") != PROVENANCE_MANIFEST_MARKER:
        reasons.append("manifest_marker_missing")
    if manifest.get("chain_root") != PROVENANCE_REQUIRED_ROLE_ORDER[0]:
        reasons.append("chain_root_invalid")
    if manifest.get("terminal_artifact") != PROVENANCE_REQUIRED_ROLE_ORDER[-1]:
        reasons.append("terminal_artifact_invalid")
    if manifest.get("required_role_order") != list(PROVENANCE_REQUIRED_ROLE_ORDER):
        reasons.append("required_role_order_invalid")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        artifacts = []
        reasons.append("manifest_empty")

    entries: list[dict[str, Any]] = [entry for entry in artifacts if isinstance(entry, dict)]
    if manifest.get("artifact_count") != len(entries):
        reasons.append("artifact_count_mismatch")
    if len(entries) != len(artifacts):
        reasons.append("artifact_entry_invalid")
    artifact_ids = [str(entry.get("artifact_id", "")) for entry in entries]
    roles = [str(entry.get("role", "")) for entry in entries]
    for artifact_id in sorted({artifact_id for artifact_id in artifact_ids if artifact_ids.count(artifact_id) > 1}):
        reasons.append(f"duplicate_artifact_id:{artifact_id}")
    for role in sorted({role for role in roles if roles.count(role) > 1}):
        reasons.append(f"duplicate_role:{role}")
    for role in PROVENANCE_REQUIRED_ROLE_ORDER:
        if role not in roles:
            reasons.append(f"required_role_missing:{role}")
    if roles != list(PROVENANCE_REQUIRED_ROLE_ORDER):
        reasons.append("role_order_invalid")

    by_id = {str(entry.get("artifact_id", "")): entry for entry in entries}
    for entry in entries:
        role = str(entry.get("role", ""))
        artifact_id = str(entry.get("artifact_id", ""))
        if role not in PROVENANCE_ROLE_KINDS:
            reasons.append(f"unknown_role:{role or artifact_id}")
            continue
        expected_parents = list(PROVENANCE_PARENT_IDS[role])
        parents = entry.get("parent_artifact_ids")
        if parents != expected_parents:
            reasons.append(f"parent_linkage_invalid:{role}")
        if not isinstance(parents, list):
            parents = []
        for parent_id in parents:
            parent_key = str(parent_id)
            if parent_key not in by_id:
                reasons.append(f"parent_missing:{role}:{parent_key}")
                continue
            if artifact_id in artifact_ids and artifact_ids.index(parent_key) >= artifact_ids.index(artifact_id):
                reasons.append(f"parent_order_invalid:{role}:{parent_key}")
    graph = {
        str(entry.get("artifact_id", "")): [str(parent) for parent in entry.get("parent_artifact_ids", [])]
        for entry in entries
        if isinstance(entry.get("parent_artifact_ids", []), list)
    }
    if _provenance_has_cycle(graph):
        reasons.append("parent_cycle_detected")

    payloads: dict[str, dict[str, Any]] = {}
    loaded_entries: dict[str, dict[str, Any]] = {}
    for entry in entries:
        role = str(entry.get("role", ""))
        if role not in PROVENANCE_ROLE_KINDS:
            continue
        artifact_path, path_reasons = _provenance_entry_path(entry, project_root)
        reasons.extend(path_reasons)
        if artifact_path is None:
            continue
        current = _artifact_source(artifact_path, project_root)
        if entry.get("sha256") != current["sha256"]:
            reasons.append(f"sha256_mismatch:{role}")
        if entry.get("byte_count") != current["bytes"]:
            reasons.append(f"byte_count_mismatch:{role}")
        try:
            payload = _load_input_json(artifact_path, f"runtime_worker_provenance_{role}")
        except RuntimeFoundationError:
            reasons.append(f"artifact_json_invalid:{role}")
            continue
        payloads[role] = payload
        loaded_entries[role] = entry
        try:
            _validate_provenance_payload_shape(role, payload, f"runtime_worker_provenance_{role}")
        except RuntimeFoundationError:
            reasons.append(f"artifact_schema_invalid:{role}")
        reasons.extend(_provenance_payload_predicate_reasons(role, payload))

    if all(role in payloads and role in loaded_entries for role in PROVENANCE_REQUIRED_ROLE_ORDER):
        reasons.extend(_provenance_source_linkage_reasons(payloads, [loaded_entries[role] for role in PROVENANCE_REQUIRED_ROLE_ORDER]))
    readiness_summary = _provenance_readiness_summary(payloads) if payloads else {"terminal_readiness": False, "role_replay_statuses": {}, "rejection_reasons": [], "recovery_status": "unknown", "delivery_gate_pass": False, "audit_replay_ready": False, "governance_ready": False}
    if manifest.get("terminal_readiness_required") is not True:
        reasons.append("terminal_readiness_required_missing")
    if not readiness_summary.get("terminal_readiness"):
        for role, ready in readiness_summary.get("role_replay_statuses", {}).items():
            if ready is not True:
                reasons.append(f"replay_status_not_ready:{role}")
        reasons.append("terminal_readiness_not_ready")

    unique_reasons = _dedupe_text(reasons)
    artifact_integrity_valid = not any(reason.startswith(("artifact_missing:", "artifact_path_", "artifact_symlink:", "artifact_not_file:", "sha256_mismatch:", "byte_count_mismatch:", "artifact_json_invalid:")) for reason in unique_reasons)
    parent_linkage_valid = not any(reason.startswith(("parent_", "duplicate_artifact_id", "duplicate_role", "parent_cycle")) for reason in unique_reasons)
    role_order_valid = "role_order_invalid" not in unique_reasons
    required_roles_present = not any(reason.startswith("required_role_missing:") for reason in unique_reasons)
    readiness_predicates_valid = not any(reason.startswith(("invocation_not_refused:", "external_execution_not_refused:", "provider_calls_not_false:", "model_calls_not_false:", "browser_calls_not_false:", "shell_calls_not_false:", "readiness_predicate_not_ready:", "replay_status_not_ready:", "terminal_readiness_not_ready")) for reason in unique_reasons)
    chain_valid = not unique_reasons
    return {
        "ok": True,
        "command": command,
        "kind": "runtime_worker_provenance_verification",
        "schema_version": SCHEMA_VERSION,
        "marker": PROVENANCE_VERIFY_MARKER,
        "manifest_source": _artifact_source(manifest_path, project_root),
        "chain_valid": chain_valid,
        "artifact_integrity_valid": artifact_integrity_valid,
        "parent_linkage_valid": parent_linkage_valid,
        "role_order_valid": role_order_valid,
        "required_roles_present": required_roles_present,
        "readiness_predicates_valid": readiness_predicates_valid,
        "readiness_summary": readiness_summary,
        "rejection_reasons": unique_reasons,
        "recovery_guidance": _provenance_recovery_guidance(unique_reasons),
        "next_action": "tamper-evident replay allowed" if chain_valid else "recover required evidence",
        "invocation_allowed": False,
        "external_execution_refused": True,
        "provider_calls": False,
        "model_calls": False,
        "browser_calls": False,
        "shell_calls": False,
        "safety_boundaries": dict(WORKER_SAFETY_BOUNDARIES),
    }


def _provenance_entry_path(entry: dict[str, Any], project_root: Path) -> tuple[Path | None, list[str]]:
    role = str(entry.get("role", "unknown"))
    raw_path = str(entry.get("path", ""))
    if not raw_path.strip():
        return None, [f"artifact_path_missing:{role}"]
    raw = Path(raw_path)
    if any(part == ".." for part in raw.parts):
        return None, [f"artifact_path_traversal:{role}"]
    if any(part == ".env" for part in raw.parts):
        return None, [f"artifact_dotenv_refused:{role}"]
    root = project_root.resolve(strict=True)
    candidate = raw if raw.is_absolute() else root / raw
    try:
        candidate.relative_to(root)
    except ValueError:
        return None, [f"artifact_outside_project:{role}"]
    parent = candidate.parent.resolve(strict=False)
    if parent != root and root not in parent.parents:
        return None, [f"artifact_outside_project:{role}"]
    if candidate.parent.exists() and candidate.parent.is_symlink():
        return None, [f"artifact_parent_symlink:{role}"]
    if not candidate.exists():
        return None, [f"artifact_missing:{role}"]
    if candidate.is_symlink():
        return None, [f"artifact_symlink:{role}"]
    if not candidate.is_file():
        return None, [f"artifact_not_file:{role}"]
    return candidate.resolve(strict=False), []


def _provenance_payload_predicate_reasons(role: str, payload: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if payload.get("invocation_allowed") is not False:
        reasons.append(f"invocation_not_refused:{role}")
    if payload.get("external_execution_refused") is not True:
        reasons.append(f"external_execution_not_refused:{role}")
    for key in ("provider_calls", "model_calls", "browser_calls", "shell_calls"):
        if payload.get(key) is not False:
            reasons.append(f"{key}_not_false:{role}")
    for name, ready in _provenance_role_readiness(role, payload).items():
        if ready is not True:
            reasons.append(f"readiness_predicate_not_ready:{role}:{name}")
    return reasons


def _provenance_source_linkage_reasons(payloads: dict[str, dict[str, Any]], artifacts: list[dict[str, Any]]) -> list[str]:
    by_role = {artifact["role"]: artifact for artifact in artifacts}
    checks = (
        ("closure_evidence", "reviewer_attestation", "reviewer_attestation_source"),
        ("merge_readiness", "reviewer_attestation", "reviewer_attestation_source"),
        ("merge_readiness", "closure_evidence", "closure_evidence_source"),
        ("delivery_gate", "merge_readiness", "merge_readiness_source"),
        ("rejection_recovery", "delivery_gate", "delivery_gate_source"),
        ("audit_replay", "rejection_recovery", "packet_source"),
    )
    reasons: list[str] = []
    for role, parent_role, source_key in checks:
        source = payloads.get(role, {}).get(source_key)
        parent = by_role.get(parent_role)
        if not isinstance(source, dict) or parent is None:
            reasons.append(f"parent_source_missing:{role}:{parent_role}")
            continue
        if not _provenance_source_matches(source, parent):
            reasons.append(f"parent_source_mismatch:{role}:{parent_role}")
    return reasons


def _provenance_source_matches(source: dict[str, Any], parent: dict[str, Any]) -> bool:
    return source.get("path") == parent.get("path") and source.get("sha256") == parent.get("sha256") and source.get("bytes") == parent.get("byte_count")


def _provenance_has_cycle(graph: dict[str, list[str]]) -> bool:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        for parent in graph.get(node, []):
            if parent in graph and visit(parent):
                return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node) for node in graph)


def _dedupe_text(items: list[str]) -> list[str]:
    deduped: list[str] = []
    for item in items:
        if item and item not in deduped:
            deduped.append(item)
    return deduped


def _provenance_recovery_guidance(reasons: list[str]) -> list[str]:
    if not reasons:
        return ["No recovery required; provenance chain is intact and replay-ready."]
    guidance: list[str] = []
    if any("missing" in reason for reason in reasons):
        guidance.append("Regenerate or restore the missing static artifact, then regenerate the provenance manifest.")
    if any(reason.startswith(("sha256_mismatch:", "byte_count_mismatch:")) for reason in reasons):
        guidance.append("Restore the artifact bytes recorded by the manifest or regenerate the manifest from the current artifacts.")
    if any(reason.startswith(("parent_", "role_order_invalid", "duplicate_artifact_id", "duplicate_role", "parent_cycle")) for reason in reasons):
        guidance.append("Regenerate the manifest with the canonical role order and parent links.")
    if any(reason.startswith(("invocation_not_refused:", "external_execution_not_refused:", "provider_calls_not_false:", "model_calls_not_false:", "browser_calls_not_false:", "shell_calls_not_false:")) for reason in reasons):
        guidance.append("Restore static refusal predicates before regenerating downstream artifacts.")
    if any(reason.startswith(("readiness_predicate_not_ready:", "replay_status_not_ready:", "terminal_readiness_not_ready")) for reason in reasons):
        guidance.append("Regenerate readiness, delivery gate, rejection recovery, and audit replay from fixed evidence.")
    if not guidance:
        guidance.append("Regenerate the provenance manifest from verified static artifacts.")
    guidance.append("Rerun runtime worker-result provenance-verify and provenance-replay after recovery.")
    return _dedupe_text(guidance)


def _format_provenance_manifest_text(payload: dict[str, Any]) -> str:
    lines = [
        "# AgentOffice Artifact Chain Provenance Manifest",
        "",
        f"schema_version: {payload['schema_version']}",
        f"marker: {payload['marker']}",
        f"generated_at: {payload['generated_at']}",
        f"chain_root: {payload['chain_root']}",
        f"terminal_artifact: {payload['terminal_artifact']}",
        f"terminal_readiness: {str(payload['readiness_summary']['terminal_readiness']).lower()}",
        f"artifact_count: {payload['artifact_count']}",
        "",
        "## Artifacts",
    ]
    for artifact in payload["artifacts"]:
        lines.append(f"- {artifact['artifact_id']} ({artifact['role']}): {artifact['path']} sha256={artifact['sha256']} bytes={artifact['byte_count']} replay_status={str(artifact['replay_status']).lower()}")
    lines.extend([
        "",
        "## Safety",
        f"invocation_allowed: {str(payload['invocation_allowed']).lower()}",
        f"external_execution_refused: {str(payload['external_execution_refused']).lower()}",
        f"provider_calls: {str(payload['provider_calls']).lower()}",
        f"model_calls: {str(payload['model_calls']).lower()}",
        f"browser_calls: {str(payload['browser_calls']).lower()}",
        f"shell_calls: {str(payload['shell_calls']).lower()}",
    ])
    return "\n".join(lines)


def _validate_reviewer_attestation_packet(payload: dict[str, Any], code_prefix: str) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION or payload.get("kind") != "runtime_worker_reviewer_attestation_packet":
        raise RuntimeFoundationError(f"{code_prefix}_invalid", "Reviewer attestation packet schema is invalid.")
    if payload.get("reviewer_attestation_present") is not True:
        raise RuntimeFoundationError(f"{code_prefix}_invalid", "Reviewer attestation must be present.")
    if payload.get("external_execution_refused") is not True or payload.get("invocation_allowed") is not False:
        raise RuntimeFoundationError(f"{code_prefix}_invalid", "Reviewer attestation must refuse external execution.")
    for key in ("provider_calls", "model_calls", "browser_calls", "shell_calls"):
        if payload.get(key) is not False:
            raise RuntimeFoundationError(f"{code_prefix}_invalid", f"Reviewer attestation must report {key}=false.")
    for key in ("artifact_path", "sha256", "byte_count", "verdict", "marker", "review_type", "reviewed_bundle_summary", "safety_caveat"):
        if payload.get(key) in (None, ""):
            raise RuntimeFoundationError(f"{code_prefix}_invalid", f"Reviewer attestation missing {key}.")


def _validate_closure_evidence_packet(payload: dict[str, Any], attestation_path: Path, project_root: Path) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION or payload.get("kind") != "runtime_worker_closure_evidence":
        raise RuntimeFoundationError("runtime_worker_merge_readiness_closure_evidence_invalid", "Closure evidence packet schema is invalid.")
    if payload.get("closure_evidence_imported") is not True or payload.get("reviewer_attestation_present") is not True:
        raise RuntimeFoundationError("runtime_worker_merge_readiness_closure_evidence_invalid", "Closure evidence import is incomplete.")
    current = _artifact_source(attestation_path, project_root)
    recorded = payload.get("reviewer_attestation_source", {})
    if recorded.get("sha256") != current["sha256"]:
        raise RuntimeFoundationError("runtime_worker_merge_readiness_closure_evidence_mismatch", "Closure evidence does not match reviewer attestation.")
    if payload.get("external_execution_refused") is not True or payload.get("invocation_allowed") is not False:
        raise RuntimeFoundationError("runtime_worker_merge_readiness_closure_evidence_invalid", "Closure evidence must refuse external execution.")
    for key in ("provider_calls", "model_calls", "browser_calls", "shell_calls"):
        if payload.get(key) is not False:
            raise RuntimeFoundationError("runtime_worker_merge_readiness_closure_evidence_invalid", f"Closure evidence must report {key}=false.")


def _validate_worker_delivery_bundle_for_merge(payload: dict[str, Any]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION or payload.get("kind") != "runtime_worker_delivery_bundle":
        raise RuntimeFoundationError("runtime_worker_merge_readiness_delivery_bundle_invalid", "Worker delivery bundle schema is invalid.")
    for key in ("worker_gate_summary", "invocation_packet_summary", "replay_summary", "audit_closure_summary"):
        if not isinstance(payload.get(key), dict):
            raise RuntimeFoundationError("runtime_worker_merge_readiness_delivery_bundle_invalid", f"Worker delivery bundle missing {key}.")



def _validate_merge_readiness_packet(payload: dict[str, Any], code_prefix: str) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION or payload.get("kind") != "runtime_worker_merge_readiness_packet":
        raise RuntimeFoundationError(f"{code_prefix}_invalid", "Merge-readiness packet schema is invalid.")
    if payload.get("marker") != MERGE_READINESS_PACKET_MARKER:
        raise RuntimeFoundationError(f"{code_prefix}_marker_missing", "Merge-readiness packet marker is missing.")


def _validate_delivery_gate_packet(payload: dict[str, Any], code_prefix: str) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION or payload.get("kind") != "runtime_worker_delivery_gate_summary":
        raise RuntimeFoundationError(f"{code_prefix}_invalid", "Delivery gate packet schema is invalid.")
    if payload.get("marker") != DELIVERY_GATE_PACKET_MARKER:
        raise RuntimeFoundationError(f"{code_prefix}_marker_missing", "Delivery gate packet marker is missing.")


def _delivery_gate_rejection_reasons(readiness: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if not bool(readiness.get("reviewer_attestation_present")):
        reasons.append("reviewer_attestation_missing")
    if not bool(readiness.get("closure_evidence_imported")):
        reasons.append("closure_evidence_not_imported")
    if not bool(readiness.get("closure_evidence_gate_readable")):
        reasons.append("closure_evidence_not_gate_readable")
    if not bool(readiness.get("external_worker_replay_ready")):
        reasons.append("external_worker_replay_not_ready")
    if not bool(readiness.get("audit_closure_ready")):
        reasons.append("audit_closure_not_ready")
    if not bool(readiness.get("delivery_bundle_ready")):
        reasons.append("delivery_bundle_not_ready")
    if not bool(readiness.get("merge_readiness_ready")):
        reasons.append("merge_readiness_not_ready")
    if readiness.get("invocation_allowed") is not False:
        reasons.append("invocation_not_refused")
    if readiness.get("external_execution_refused") is not True:
        reasons.append("external_execution_not_refused")
    for key in ("provider_calls", "model_calls", "browser_calls", "shell_calls"):
        if readiness.get(key) is not False:
            reasons.append(f"{key}_not_false")
    for reason in readiness.get("readiness_blocking_reasons") or []:
        text = str(reason)
        if text and text not in reasons:
            reasons.append(text)
    return reasons


def _next_required_evidence(reasons: list[str]) -> list[str]:
    evidence: list[str] = []
    mapping = {
        "reviewer_attestation_missing": "valid reviewer attestation packet",
        "closure_evidence_not_imported": "fixed closure evidence import",
        "closure_evidence_not_gate_readable": "gate-readable closure evidence",
        "external_worker_replay_not_ready": "worker-result replay evidence",
        "audit_closure_not_ready": "worker audit closure packet",
        "delivery_bundle_not_ready": "worker delivery bundle",
        "merge_readiness_not_ready": "regenerated merge-readiness packet",
        "invocation_not_refused": "merge-readiness with invocation_allowed=false",
        "external_execution_not_refused": "merge-readiness with external_execution_refused=true",
        "provider_calls_not_false": "merge-readiness with provider_calls=false",
        "model_calls_not_false": "merge-readiness with model_calls=false",
        "browser_calls_not_false": "merge-readiness with browser_calls=false",
        "shell_calls_not_false": "merge-readiness with shell_calls=false",
    }
    for reason in reasons:
        item = mapping.get(reason, f"evidence resolving {reason}")
        if item not in evidence:
            evidence.append(item)
    return evidence


def _recovery_guidance(reasons: list[str]) -> list[str]:
    if not reasons:
        return ["No recovery required; proceed to safe delivery."]
    guidance = [
        "Inspect rejection_reasons.",
        "Regenerate or re-import the required static evidence only.",
        "Regenerate merge-readiness from the fixed artifacts.",
        "Rerun runtime worker-result delivery-gate.",
    ]
    if any(reason.startswith(("provider_", "model_", "browser_", "shell_")) for reason in reasons):
        guidance.insert(1, "Remove any call-flag true claim from the static packet before rerun.")
    if "invocation_not_refused" in reasons or "external_execution_not_refused" in reasons:
        guidance.insert(1, "Restore explicit external execution refusal predicates before rerun.")
    return guidance


def _audit_replay_summary(payload: dict[str, Any]) -> dict[str, Any]:
    kind = str(payload.get("kind", ""))
    if kind == "runtime_worker_audit_closure_packet":
        return {
            "original_readiness": bool(payload.get("replay_ready")) and bool(payload.get("governance_ready")),
            "rejection_reasons": [],
            "recovery_status": "not_applicable",
            "replay_ready": bool(payload.get("replay_ready")),
            "governance_ready": bool(payload.get("governance_ready")),
        }
    if kind == "runtime_worker_merge_readiness_packet":
        if payload.get("marker") != MERGE_READINESS_PACKET_MARKER:
            raise RuntimeFoundationError("runtime_worker_audit_replay_packet_marker_missing", "Merge-readiness packet marker is missing.")
        reasons = list(payload.get("readiness_blocking_reasons") or [])
        ready = bool(payload.get("merge_readiness_ready"))
        return {
            "original_readiness": ready,
            "rejection_reasons": reasons,
            "recovery_status": "not_required" if ready else "needs_fixed_evidence",
            "replay_ready": bool(payload.get("external_worker_replay_ready")),
            "governance_ready": bool(payload.get("audit_closure_ready")) and bool(payload.get("delivery_bundle_ready")),
        }
    if kind == "runtime_worker_delivery_gate_summary":
        if payload.get("marker") != DELIVERY_GATE_PACKET_MARKER:
            raise RuntimeFoundationError("runtime_worker_audit_replay_packet_marker_missing", "Delivery gate packet marker is missing.")
        ready = bool(payload.get("delivery_gate_pass"))
        return {
            "original_readiness": ready,
            "rejection_reasons": list(payload.get("rejection_reasons") or []),
            "recovery_status": "not_required" if ready else "recovery_required",
            "replay_ready": True,
            "governance_ready": ready,
        }
    if kind == "runtime_worker_rejection_recovery_packet":
        if payload.get("marker") != REJECTION_RECOVERY_PACKET_MARKER:
            raise RuntimeFoundationError("runtime_worker_audit_replay_packet_marker_missing", "Rejection recovery packet marker is missing.")
        return {
            "original_readiness": bool(payload.get("original_readiness")),
            "rejection_reasons": list(payload.get("rejection_reasons") or []),
            "recovery_status": str(payload.get("recovery_status", "")),
            "replay_ready": bool(payload.get("replay_ready")),
            "governance_ready": bool(payload.get("governance_ready")),
        }
    raise RuntimeFoundationError("runtime_worker_audit_replay_packet_invalid", "Unsupported audit replay packet kind.")


def _format_delivery_gate_text(payload: dict[str, Any]) -> str:
    lines = [
        "# AgentOffice Delivery Gate Summary",
        "",
        f"schema_version: {payload['schema_version']}",
        f"marker: {payload['marker']}",
        f"source_branch: {payload['source_branch']}",
        f"source_head: {payload['source_head']}",
        f"target_branch: {payload['target_branch']}",
        f"delivery_gate_pass: {str(payload['delivery_gate_pass']).lower()}",
        f"gate_status: {payload['gate_status']}",
        f"reviewer_attestation_present: {str(payload['reviewer_attestation_present']).lower()}",
        f"closure_evidence_imported: {str(payload['closure_evidence_imported']).lower()}",
        f"closure_evidence_gate_readable: {str(payload['closure_evidence_gate_readable']).lower()}",
        f"external_worker_replay_ready: {str(payload['external_worker_replay_ready']).lower()}",
        f"audit_closure_ready: {str(payload['audit_closure_ready']).lower()}",
        f"delivery_bundle_ready: {str(payload['delivery_bundle_ready']).lower()}",
        f"invocation_allowed: {str(payload['invocation_allowed']).lower()}",
        f"external_execution_refused: {str(payload['external_execution_refused']).lower()}",
        f"provider_calls: {str(payload['provider_calls']).lower()}",
        f"model_calls: {str(payload['model_calls']).lower()}",
        f"browser_calls: {str(payload['browser_calls']).lower()}",
        f"shell_calls: {str(payload['shell_calls']).lower()}",
        f"next_action: {payload['next_action']}",
        f"rejection_reasons: {', '.join(payload['rejection_reasons']) or 'none'}",
        "",
        "## Recovery Guidance",
    ]
    lines.extend(f"- {item}" for item in payload["recovery_guidance"])
    return "\n".join(lines)


def _format_rejection_packet_text(payload: dict[str, Any]) -> str:
    lines = [
        "# AgentOffice Rejection Recovery Packet",
        "",
        f"schema_version: {payload['schema_version']}",
        f"marker: {payload['marker']}",
        f"rejected: {str(payload['rejected']).lower()}",
        f"original_readiness: {str(payload['original_readiness']).lower()}",
        f"recovery_status: {payload['recovery_status']}",
        f"replay_ready: {str(payload['replay_ready']).lower()}",
        f"governance_ready: {str(payload['governance_ready']).lower()}",
        f"rejection_reasons: {', '.join(payload['rejection_reasons']) or 'none'}",
        "",
        "## Next Required Evidence",
    ]
    lines.extend(f"- {item}" for item in payload["next_required_evidence"] or ["none"])
    lines.extend(["", "## Recovery Guidance"])
    lines.extend(f"- {item}" for item in payload["recovery_guidance"])
    return "\n".join(lines)



def _format_reviewer_attestation_text(payload: dict[str, Any]) -> str:
    lines = [
        "# AgentOffice Reviewer Attestation Packet",
        "",
        f"schema_version: {payload['schema_version']}",
        f"packet_marker: {payload['packet_marker']}",
        f"artifact_path: {payload['artifact_path']}",
        f"sha256: {payload['sha256']}",
        f"byte_count: {payload['byte_count']}",
        f"verdict: {payload['verdict']}",
        f"marker: {payload['marker']}",
        f"review_type: {payload['review_type']}",
        f"review_caveat: {payload['review_caveat']}",
        f"findings_summary: {payload['findings_summary']}",
        f"reviewed_bundle_summary: {payload['reviewed_bundle_summary']}",
        f"safety_caveat: {payload['safety_caveat']}",
        f"invocation_allowed: {str(payload['invocation_allowed']).lower()}",
        f"external_execution_refused: {str(payload['external_execution_refused']).lower()}",
        f"provider_calls: {str(payload['provider_calls']).lower()}",
        f"model_calls: {str(payload['model_calls']).lower()}",
        f"browser_calls: {str(payload['browser_calls']).lower()}",
        f"shell_calls: {str(payload['shell_calls']).lower()}",
        "",
        "## Reviewed Artifacts",
    ]
    lines.extend(f"- {artifact}" for artifact in payload["reviewed_artifacts"])
    return "\n".join(lines)


def _format_closure_evidence_text(payload: dict[str, Any]) -> str:
    lines = [
        "# AgentOffice Closure Evidence Import",
        "",
        f"schema_version: {payload['schema_version']}",
        f"marker: {payload['marker']}",
        f"closure_evidence_imported: {str(payload['closure_evidence_imported']).lower()}",
        f"gate_readable: {str(payload['gate_readable']).lower()}",
        f"audit_replayable: {str(payload['audit_replayable']).lower()}",
        f"reviewer_attestation: {payload['reviewer_attestation_source']['path']}",
        f"verdict: {payload['verdict']}",
        f"review_marker: {payload['review_marker']}",
        f"external_execution_refused: {str(payload['external_execution_refused']).lower()}",
        f"provider_calls: {str(payload['provider_calls']).lower()}",
        f"model_calls: {str(payload['model_calls']).lower()}",
        f"browser_calls: {str(payload['browser_calls']).lower()}",
        f"shell_calls: {str(payload['shell_calls']).lower()}",
        "",
        "provider/runtime/adapter execution: not triggered",
    ]
    return "\n".join(lines)


def _format_merge_readiness_text(payload: dict[str, Any]) -> str:
    lines = [
        "# AgentOffice Merge Readiness Packet",
        "",
        f"schema_version: {payload['schema_version']}",
        f"marker: {payload['marker']}",
        f"baseline: {payload['baseline']}",
        f"source_branch: {payload['source_branch']}",
        f"source_head: {payload['source_head']}",
        f"target_branch: {payload['target_branch']}",
        f"external_worker_replay_ready: {str(payload['external_worker_replay_ready']).lower()}",
        f"audit_closure_ready: {str(payload['audit_closure_ready']).lower()}",
        f"reviewer_attestation_present: {str(payload['reviewer_attestation_present']).lower()}",
        f"closure_evidence_imported: {str(payload['closure_evidence_imported']).lower()}",
        f"delivery_bundle_ready: {str(payload['delivery_bundle_ready']).lower()}",
        f"merge_readiness_ready: {str(payload['merge_readiness_ready']).lower()}",
        f"invocation_allowed: {str(payload['invocation_allowed']).lower()}",
        f"external_execution_refused: {str(payload['external_execution_refused']).lower()}",
        f"provider_calls: {str(payload['provider_calls']).lower()}",
        f"model_calls: {str(payload['model_calls']).lower()}",
        f"browser_calls: {str(payload['browser_calls']).lower()}",
        f"shell_calls: {str(payload['shell_calls']).lower()}",
        f"next_action: {payload['next_action']}",
        f"blocking_reasons: {', '.join(payload['readiness_blocking_reasons']) or 'none'}",
        "",
        "## Validation Commands",
    ]
    lines.extend(f"- {command}" for command in payload["validation_commands"])
    return "\n".join(lines)



def _event_summary(event: dict[str, Any] | None) -> str:
    if not event:
        return ""
    return f"{event.get('entry_type')}:{event.get('task_id')}:{event.get('status')}"


def _project_relative(path: Path, project_root: Path) -> str:
    root = project_root.resolve(strict=True)
    return path.resolve(strict=False).relative_to(root).as_posix()
