from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .packet_result import (
    PacketResultError,
    actor_result_payload,
    emit_packet,
    packet_id_for_task,
    packets_dir,
    read_actor_result,
    read_packet,
    result_id_for_task,
    results_dir,
)
from .runtime_events import RuntimeEventLogError, append_event, list_events
from .task_graph import TaskGraphError, compute_ready_tasks, goal_dir, load_task_graph
from .workspace_store import (
    WorkspaceStoreError,
    inspect_workspace,
    read_json,
    run_dir,
    validate_store_id,
    workspace_dir,
    write_json_atomic,
)


TERMINAL_TASK_STATUSES = {"accepted", "rejected", "skipped"}
JOB_STATUSES = {"pending", "running", "succeeded", "failed", "cancelled"}
TERMINAL_JOB_STATUSES = {"succeeded", "failed", "cancelled"}
WORKER_RESULT_STATUSES = {"succeeded", "failed"}
SCHEDULER_TASK_STATUSES = {
    "pending",
    "selected",
    "dispatched",
    "waiting_result",
    "completed",
    "failed",
    "paused",
    "blocked",
    "retry_scheduled",
}
TERMINAL_SCHEDULER_TASK_STATUSES = {"completed", "failed"}
LOCAL_WORKER_ADAPTER_ID = "local_worker_adapter_stub"
LOCAL_EXECUTOR_NAME = "local_executor_stub"
LOCAL_WORKER_NAME = "local_echo_worker"
REVIEW_STUB_NAME = "local_review_stub"
JUDGE_STUB_NAME = "local_judge_stub"
LOCAL_ORCHESTRATOR_NAME = "local_orchestrator_stub"
LOCAL_EXECUTION_LOOP_NAME = "local_execution_loop_stub"
LOCAL_EXECUTION_CAPABILITY_ID = "local.execution.dispatch"


class FrameworkRuntimeError(ValueError):
    pass


def runtime_contract_status() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "agentoffice.framework_runtime_contract",
        "status": "available",
        "runtime_loop": "local_deterministic_trunk",
        "worker_adapters": [LOCAL_WORKER_NAME],
        "review_stub": REVIEW_STUB_NAME,
        "judge_stub": JUDGE_STUB_NAME,
        "provider_calls_enabled": False,
        "env_reads_allowed": False,
        "network_calls_enabled": False,
        "external_adapters_enabled": False,
        "supports": [
            "dispatch",
            "worker_result",
            "actor_result_intake",
            "review_stub",
            "judge_stub",
            "status",
            "inspect",
            "resume",
            "replay",
            "evidence_export",
            "job_lifecycle",
            "local_executor_loop_v1",
            "worker_adapter_contract",
            "deterministic_worker_result_intake",
            "local_orchestration_contract_v1",
            "local_execution_loop_v1",
            "execution_policy_capability_boundary_v1",
        ],
    }



def capability_declarations() -> list[dict[str, Any]]:
    return [
        {
            "capability_id": LOCAL_EXECUTION_CAPABILITY_ID,
            "worker": LOCAL_EXECUTION_LOOP_NAME,
            "action": "dispatch",
            "status": "local-only",
            "allowed": True,
            "reason_code": "LOCAL_ONLY_ALLOWED",
            "description": "Allow deterministic local execution-loop dispatch only.",
            "provider_calls": False,
            "network_calls": False,
            "env_reads": False,
            "external_worker_calls": False,
        },
        {
            "capability_id": "local.worker_result.intake",
            "worker": LOCAL_WORKER_ADAPTER_ID,
            "action": "result-intake",
            "status": "local-only",
            "allowed": True,
            "reason_code": "LOCAL_ONLY_ALLOWED",
            "description": "Allow deterministic local worker-result intake only.",
            "provider_calls": False,
            "network_calls": False,
            "env_reads": False,
            "external_worker_calls": False,
        },
        {
            "capability_id": "external.provider.execute",
            "worker": "external_provider",
            "action": "execute",
            "status": "forbidden",
            "allowed": False,
            "reason_code": "FORBIDDEN_CAPABILITY",
            "description": "Deny real provider execution in framework-runtime local mode.",
            "provider_calls": True,
            "network_calls": True,
            "env_reads": False,
            "external_worker_calls": True,
        },
        {
            "capability_id": "real.codex.execute",
            "worker": "codex",
            "action": "execute",
            "status": "forbidden",
            "allowed": False,
            "reason_code": "FORBIDDEN_CAPABILITY",
            "description": "Deny real Codex worker execution in framework-runtime local mode.",
            "provider_calls": False,
            "network_calls": False,
            "env_reads": False,
            "external_worker_calls": True,
        },
        {
            "capability_id": "real.claude.execute",
            "worker": "claude",
            "action": "execute",
            "status": "forbidden",
            "allowed": False,
            "reason_code": "FORBIDDEN_CAPABILITY",
            "description": "Deny real Claude worker execution in framework-runtime local mode.",
            "provider_calls": False,
            "network_calls": False,
            "env_reads": False,
            "external_worker_calls": True,
        },
    ]


def capability_contract_payload() -> dict[str, Any]:
    capabilities = capability_declarations()
    return {
        "schema_version": 1,
        "kind": "agentoffice.framework_runtime_capability_contract",
        "contract_version": "execution_policy_capability_boundary_v1",
        "capabilities": capabilities,
        "allowed_capabilities": [item for item in capabilities if item["allowed"]],
        "forbidden_capabilities": [item for item in capabilities if not item["allowed"]],
        "local_static": True,
        "deterministic": True,
        "provider_calls": False,
        "network_calls": False,
        "env_reads": False,
        "external_worker_calls": False,
    }


def capability_by_id(capability_id: str) -> dict[str, Any] | None:
    for item in capability_declarations():
        if item["capability_id"] == capability_id:
            return item
    return None


def policy_decision_payload(capability_id: str, worker: str, action: str, subject: dict[str, str] | None = None) -> dict[str, Any]:
    capability_id = str(capability_id or "")
    worker = str(worker or "")
    action = str(action or "")
    declaration = capability_by_id(capability_id)
    if declaration is None:
        allowed = False
        status = "unknown"
        reason_code = "UNKNOWN_CAPABILITY"
        reason = f"Capability is not declared: {capability_id}"
    elif declaration["status"] == "forbidden" or not declaration["allowed"]:
        allowed = False
        status = str(declaration["status"])
        reason_code = str(declaration["reason_code"])
        reason = f"Capability is forbidden: {capability_id}"
    elif declaration["worker"] != worker or declaration["action"] != action:
        allowed = False
        status = str(declaration["status"])
        reason_code = "WORKER_ACTION_MISMATCH"
        reason = f"Capability {capability_id} does not allow worker/action {worker}/{action}"
    else:
        allowed = True
        status = str(declaration["status"])
        reason_code = str(declaration["reason_code"])
        reason = f"Capability allowed: {capability_id}"
    return {
        "schema_version": 1,
        "kind": "agentoffice.framework_runtime_policy_decision",
        "contract_version": "execution_policy_capability_boundary_v1",
        "capability_id": capability_id,
        "worker": worker,
        "action": action,
        "allowed": allowed,
        "status": status,
        "reason_code": reason_code,
        "reason": reason,
        "subject": dict(sorted((subject or {}).items())),
        "capability": declaration,
        "local_static": True,
        "deterministic": True,
        "provider_calls": False,
        "network_calls": False,
        "env_reads": False,
        "external_worker_calls": False,
        "codex_worker_connected": False,
        "claude_worker_connected": False,
    }


def policy_check_payload(capability_id: str, worker: str | None = None, action: str | None = None) -> dict[str, Any]:
    declaration = capability_by_id(str(capability_id or ""))
    decision = policy_decision_payload(
        capability_id,
        worker or str(declaration.get("worker", "")) if declaration else worker or "unknown",
        action or str(declaration.get("action", "")) if declaration else action or "unknown",
        None,
    )
    return {
        "schema_version": 1,
        "kind": "agentoffice.framework_runtime_policy_check",
        "decision": decision,
        "capability_contract": capability_contract_payload(),
        "local_static": True,
        "provider_calls": False,
        "network_calls": False,
        "env_reads": False,
        "external_worker_calls": False,
    }


def legacy_packet_worker_adapter() -> dict[str, Any]:
    return {
        "name": LOCAL_WORKER_NAME,
        "mode": "deterministic_local_stub",
        "input_kind": "agentoffice.packet",
        "output_kind": "agentoffice.actor_result",
        "reads_env": False,
        "prints_env": False,
        "network_calls": False,
        "provider_calls": False,
        "external_runtime_calls": False,
        "failure_contract": "structured_framework_runtime_error",
    }


def deterministic_job_worker_adapter() -> dict[str, Any]:
    return {
        "adapter_id": LOCAL_WORKER_ADAPTER_ID,
        "name": LOCAL_WORKER_ADAPTER_ID,
        "mode": "deterministic_local_stub",
        "input_kind": "agentoffice.framework_runtime_job",
        "output_kind": "agentoffice.framework_runtime_worker_result",
        "supported_result_statuses": sorted(WORKER_RESULT_STATUSES),
        "execution_enabled": False,
        "result_intake_enabled": True,
        "reads_env": False,
        "prints_env": False,
        "network_calls": False,
        "provider_calls": False,
        "codex_worker_connected": False,
        "claude_worker_connected": False,
        "external_runtime_calls": False,
        "failure_contract": "structured_framework_runtime_error",
    }


def worker_contract_payload() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "agentoffice.framework_runtime_worker_contract",
        "adapters": [legacy_packet_worker_adapter(), deterministic_job_worker_adapter()],
    }


def worker_adapter_contract_payload() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "agentoffice.framework_runtime_worker_adapter_contract",
        "adapters": [deterministic_job_worker_adapter()],
        "local_static": True,
        "provider_calls": False,
        "network_calls": False,
        "env_reads": False,
        "external_worker_calls": False,
    }


def validate_runtime_id(value: str, label: str) -> str:
    try:
        return validate_store_id(value, label)
    except WorkspaceStoreError as exc:
        raise FrameworkRuntimeError(str(exc)) from exc


def safe_root(root: Path) -> Path:
    path = Path(root)
    if any(part == ".." for part in path.parts):
        raise FrameworkRuntimeError("Invalid root: path traversal is not allowed.")
    if path.exists() and path.is_symlink():
        raise FrameworkRuntimeError(f"Invalid root: symlink roots are not allowed: {path}")
    return path


def ensure_runtime_run(root: Path, workspace_id: str, run_id: str) -> Path:
    root = safe_root(root)
    workspace_id = validate_runtime_id(workspace_id, "workspace_id")
    run_id = validate_runtime_id(run_id, "run_id")
    try:
        inspect_workspace(root, workspace_id)
        target = run_dir(root, workspace_id, run_id)
        metadata = target / "run.json"
        if not metadata.exists():
            raise FrameworkRuntimeError(f"Run not found: {run_id}")
        read_json(metadata)
    except WorkspaceStoreError as exc:
        raise FrameworkRuntimeError(str(exc)) from exc
    return target


def load_runtime_graph(root: Path, workspace_id: str, goal_id: str) -> dict[str, Any]:
    root = safe_root(root)
    try:
        return load_task_graph(root, workspace_id, goal_id)
    except TaskGraphError as exc:
        raise FrameworkRuntimeError(str(exc)) from exc


def save_runtime_graph(root: Path, workspace_id: str, goal_id: str, graph: dict[str, Any]) -> None:
    target = goal_dir(root, workspace_id, goal_id) / "task_graph.json"
    write_json_atomic(target, graph)


def set_task_status(root: Path, workspace_id: str, run_id: str, goal_id: str, task_id: str, status: str) -> dict[str, Any]:
    graph = load_runtime_graph(root, workspace_id, goal_id)
    task_id = validate_runtime_id(task_id, "task_id")
    for task in graph.get("tasks", []):
        if task.get("task_id") != task_id:
            continue
        old_status = str(task.get("status", "created"))
        if old_status in TERMINAL_TASK_STATUSES and old_status != status:
            return dict(task)
        if old_status != status:
            task["status"] = status
            save_runtime_graph(root, workspace_id, goal_id, graph)
            append_runtime_event(root, workspace_id, run_id, f"task.{status}", "runtime")
        return dict(task)
    raise FrameworkRuntimeError(f"Task not found in task graph: {task_id}")


def append_runtime_event(root: Path, workspace_id: str, run_id: str, event_type: str, actor: str) -> dict[str, Any]:
    try:
        return append_event(root, workspace_id, run_id, event_type, actor)
    except RuntimeEventLogError as exc:
        raise FrameworkRuntimeError(str(exc)) from exc


def runtime_packet(root: Path, workspace_id: str, run_id: str, goal_id: str, task: dict[str, Any]) -> dict[str, Any]:
    task_id = validate_runtime_id(str(task["task_id"]), "task_id")
    packet_id = packet_id_for_task(task_id)
    try:
        packet_path = packets_dir(root, workspace_id, run_id) / f"{packet_id}.json"
        if packet_path.exists():
            return read_packet(root, workspace_id, run_id, packet_id)
        return emit_packet(root, workspace_id, run_id, goal_id, task_id)
    except PacketResultError as exc:
        raise FrameworkRuntimeError(str(exc)) from exc


def local_worker_result(packet: dict[str, Any]) -> dict[str, Any]:
    summary = f"local stub worker completed {packet['task_id']}: {packet['objective']}"
    payload = actor_result_payload(packet, LOCAL_WORKER_NAME, "completed", summary)
    payload["worker"] = {
        "name": LOCAL_WORKER_NAME,
        "mode": "deterministic_local_stub",
        "provider_calls": False,
        "network_calls": False,
        "env_reads": False,
        "external_runtime_calls": False,
    }
    payload["outputs"] = {
        "echo_task_id": packet["task_id"],
        "echo_objective": packet["objective"],
    }
    return payload


def runtime_actor_result(root: Path, workspace_id: str, run_id: str, packet: dict[str, Any]) -> dict[str, Any]:
    result_id = result_id_for_task(str(packet["task_id"]))
    try:
        result_path = results_dir(root, workspace_id, run_id) / f"{result_id}.json"
        if result_path.exists():
            return read_actor_result(root, workspace_id, run_id, result_id)
        payload = local_worker_result(packet)
        write_json_atomic(result_path, payload)
        append_runtime_event(root, workspace_id, run_id, "actor_result.received", LOCAL_WORKER_NAME)
        return payload
    except PacketResultError as exc:
        raise FrameworkRuntimeError(str(exc)) from exc


def review_id_for_task(task_id: str) -> str:
    return validate_runtime_id(f"rev_{task_id}", "review_id")


def judge_id_for_task(task_id: str) -> str:
    return validate_runtime_id(f"jdg_{task_id}", "judge_id")


def reviews_dir(root: Path, workspace_id: str, run_id: str) -> Path:
    return ensure_runtime_run(root, workspace_id, run_id) / "reviews"


def judges_dir(root: Path, workspace_id: str, run_id: str) -> Path:
    return ensure_runtime_run(root, workspace_id, run_id) / "judges"


def read_review(root: Path, workspace_id: str, run_id: str, review_id: str) -> dict[str, Any]:
    review_id = validate_runtime_id(review_id, "review_id")
    path = reviews_dir(root, workspace_id, run_id) / f"{review_id}.json"
    if not path.exists():
        raise FrameworkRuntimeError(f"Review result not found: {review_id}")
    try:
        return read_json(path)
    except WorkspaceStoreError as exc:
        raise FrameworkRuntimeError(str(exc)) from exc


def read_judge(root: Path, workspace_id: str, run_id: str, judge_id: str) -> dict[str, Any]:
    judge_id = validate_runtime_id(judge_id, "judge_id")
    path = judges_dir(root, workspace_id, run_id) / f"{judge_id}.json"
    if not path.exists():
        raise FrameworkRuntimeError(f"Judge result not found: {judge_id}")
    try:
        return read_json(path)
    except WorkspaceStoreError as exc:
        raise FrameworkRuntimeError(str(exc)) from exc


def read_runtime_json_child(parent: Path, child: Path) -> dict[str, Any]:
    if child.is_symlink():
        raise FrameworkRuntimeError(f"Refusing to read symlink JSON file: {child}")
    if not child.is_file():
        raise FrameworkRuntimeError(f"Refusing to read non-file JSON path: {child}")
    try:
        parent_resolved = parent.resolve()
        child_resolved = child.resolve()
    except OSError as exc:
        raise FrameworkRuntimeError(f"Invalid JSON path: {child}: {exc}") from exc
    if child_resolved.parent != parent_resolved:
        raise FrameworkRuntimeError(f"Refusing to read JSON file outside runtime directory: {child}")
    try:
        return read_json(child)
    except WorkspaceStoreError as exc:
        raise FrameworkRuntimeError(str(exc)) from exc


def list_json_objects(path: Path) -> list[dict[str, Any]]:
    if path.is_symlink():
        raise FrameworkRuntimeError(f"Refusing to read symlink JSON directory: {path}")
    if not path.exists():
        return []
    if not path.is_dir():
        raise FrameworkRuntimeError(f"Refusing to read non-directory JSON path: {path}")
    items: list[dict[str, Any]] = []
    for child in sorted(path.glob("*.json")):
        items.append(read_runtime_json_child(path, child))
    return items


def jobs_dir(root: Path, workspace_id: str, run_id: str) -> Path:
    return ensure_runtime_run(root, workspace_id, run_id) / "jobs"


def job_path(root: Path, workspace_id: str, run_id: str, job_id: str) -> Path:
    job_id = validate_runtime_id(job_id, "job_id")
    return jobs_dir(root, workspace_id, run_id) / f"{job_id}.json"


def job_transition_stamp(sequence: int) -> str:
    return f"transition-{sequence:04d}"


def job_transition_entry(sequence: int, action: str, from_status: str | None, to_status: str, reason: str) -> dict[str, Any]:
    return {
        "sequence": sequence,
        "stamp": job_transition_stamp(sequence),
        "action": action,
        "from_status": from_status,
        "to_status": to_status,
        "reason": reason,
    }


def normalize_job_metadata(metadata: dict[str, str] | None) -> dict[str, str]:
    return dict(sorted((metadata or {}).items()))


def normalize_evidence_refs(evidence_refs: list[str] | None) -> list[str]:
    return sorted(dict.fromkeys(evidence_refs or []))


def create_job_payload(root: Path, workspace_id: str, run_id: str, job_id: str, objective: str, metadata: dict[str, str] | None = None, evidence_refs: list[str] | None = None) -> dict[str, Any]:
    root = safe_root(root)
    job_id = validate_runtime_id(job_id, "job_id")
    if not objective.strip():
        raise FrameworkRuntimeError("Job objective must not be empty.")
    target = job_path(root, workspace_id, run_id, job_id)
    if target.exists():
        raise FrameworkRuntimeError(f"Job already exists: {job_id}")
    transition = job_transition_entry(1, "create", None, "pending", "job created")
    payload = {
        "schema_version": 1,
        "kind": "agentoffice.framework_runtime_job",
        "workspace_id": validate_runtime_id(workspace_id, "workspace_id"),
        "run_id": validate_runtime_id(run_id, "run_id"),
        "job_id": job_id,
        "status": "pending",
        "created_at": transition["stamp"],
        "updated_at": transition["stamp"],
        "objective": objective,
        "metadata": normalize_job_metadata(metadata),
        "evidence_refs": normalize_evidence_refs(evidence_refs),
        "transition_log": [transition],
        "local_static": True,
        "provider_calls": False,
        "network_calls": False,
        "external_worker_calls": False,
        "executor": None,
    }
    write_json_atomic(target, payload)
    return payload


def read_job_payload(root: Path, workspace_id: str, run_id: str, job_id: str) -> dict[str, Any]:
    target = job_path(root, workspace_id, run_id, job_id)
    if not target.exists():
        raise FrameworkRuntimeError(f"Job not found: {job_id}")
    try:
        return read_json(target)
    except WorkspaceStoreError as exc:
        raise FrameworkRuntimeError(str(exc)) from exc


def list_jobs_payload(root: Path, workspace_id: str, run_id: str) -> dict[str, Any]:
    rows = list_json_objects(jobs_dir(root, workspace_id, run_id))
    rows.sort(key=lambda item: str(item.get("job_id", "")))
    return {
        "schema_version": 1,
        "kind": "agentoffice.framework_runtime_job_list",
        "workspace_id": validate_runtime_id(workspace_id, "workspace_id"),
        "run_id": validate_runtime_id(run_id, "run_id"),
        "jobs": rows,
        "job_count": len(rows),
        "local_static": True,
        "provider_calls": False,
    }


def write_job_payload(root: Path, workspace_id: str, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    write_json_atomic(job_path(root, workspace_id, run_id, str(payload["job_id"])), payload)
    return payload


def append_job_transition(payload: dict[str, Any], action: str, new_status: str, reason: str) -> dict[str, Any]:
    old_status = str(payload.get("status", ""))
    log = list(payload.get("transition_log", []))
    sequence = len(log) + 1
    transition = job_transition_entry(sequence, action, old_status, new_status, reason)
    log.append(transition)
    payload["status"] = new_status
    payload["updated_at"] = transition["stamp"]
    payload["transition_log"] = log
    return payload


def transition_job_payload(root: Path, workspace_id: str, run_id: str, job_id: str, action: str, reason: str) -> dict[str, Any]:
    if action not in {"cancel", "fail"}:
        raise FrameworkRuntimeError(f"Unsupported job transition: {action}")
    payload = read_job_payload(root, workspace_id, run_id, job_id)
    old_status = str(payload.get("status", ""))
    if old_status in TERMINAL_JOB_STATUSES:
        raise FrameworkRuntimeError(f"Job {job_id} is terminal and cannot be {action}ed: {old_status}")
    if old_status not in {"pending", "running"}:
        raise FrameworkRuntimeError(f"Job {job_id} cannot be {action}ed from status: {old_status}")
    new_status = "cancelled" if action == "cancel" else "failed"
    append_job_transition(payload, action, new_status, reason or f"job {action}ed")
    write_job_payload(root, workspace_id, run_id, payload)
    return payload


def executor_results_dir(root: Path, workspace_id: str, run_id: str) -> Path:
    return ensure_runtime_run(root, workspace_id, run_id) / "executor_results"


def executor_result_path(root: Path, workspace_id: str, run_id: str, job_id: str) -> Path:
    job_id = validate_runtime_id(job_id, "job_id")
    return executor_results_dir(root, workspace_id, run_id) / f"{job_id}.json"


def executor_result_ref(workspace_id: str, run_id: str, job_id: str) -> str:
    return f".ai/workspaces/{workspace_id}/runs/{run_id}/executor_results/{job_id}.json"


def executor_event_log_ref(workspace_id: str, run_id: str) -> str:
    return f".ai/workspaces/{workspace_id}/runs/{run_id}/events.jsonl"


def selected_executor_job(root: Path, workspace_id: str, run_id: str, job_id: str | None) -> dict[str, Any] | None:
    if job_id is not None:
        job = read_job_payload(root, workspace_id, run_id, job_id)
        if str(job.get("status")) in TERMINAL_JOB_STATUSES:
            return None
        return job
    for status in ("running", "pending"):
        for job in list_jobs_payload(root, workspace_id, run_id)["jobs"]:
            if str(job.get("status")) == status:
                return job
    return None


def executor_job_outcome(job: dict[str, Any]) -> str:
    metadata = job.get("metadata", {})
    if isinstance(metadata, dict) and str(metadata.get("executor_outcome", "succeeded")) == "failed":
        return "failed"
    return "succeeded"


def executor_result_payload(workspace_id: str, run_id: str, job: dict[str, Any], outcome: str) -> dict[str, Any]:
    job_id = str(job["job_id"])
    return {
        "schema_version": 1,
        "kind": "agentoffice.framework_runtime_executor_result",
        "workspace_id": workspace_id,
        "run_id": run_id,
        "job_id": job_id,
        "executor": LOCAL_EXECUTOR_NAME,
        "mode": "deterministic_local_stub",
        "status": outcome,
        "summary": f"local executor stub {outcome} job {job_id}: {job['objective']}",
        "outputs": {
            "echo_job_id": job_id,
            "echo_objective": job["objective"],
        },
        "local_stub": True,
        "provider_calls": False,
        "network_calls": False,
        "env_reads": False,
        "external_worker_calls": False,
    }


def executor_run_once_payload(root: Path, workspace_id: str, run_id: str, job_id: str | None = None) -> dict[str, Any]:
    root = safe_root(root)
    ensure_runtime_run(root, workspace_id, run_id)
    job = selected_executor_job(root, workspace_id, run_id, job_id)
    if job is None:
        return {
            "schema_version": 1,
            "kind": "agentoffice.framework_runtime_executor_run_once",
            "workspace_id": workspace_id,
            "run_id": run_id,
            "job": None,
            "progressed": False,
            "reason": "no runnable job",
            "local_stub": True,
            "provider_calls": False,
            "network_calls": False,
            "env_reads": False,
        }

    job_id = str(job["job_id"])
    if str(job.get("status")) == "pending":
        append_job_transition(job, "executor_start", "running", "local executor stub started")
        append_runtime_event(root, workspace_id, run_id, "executor.job_started", LOCAL_EXECUTOR_NAME)
        write_job_payload(root, workspace_id, run_id, job)

    outcome = executor_job_outcome(job)
    result = executor_result_payload(workspace_id, run_id, job, outcome)
    result_path = executor_result_path(root, workspace_id, run_id, job_id)
    write_json_atomic(result_path, result)
    event_type = "executor.job_succeeded" if outcome == "succeeded" else "executor.job_failed"
    append_runtime_event(root, workspace_id, run_id, event_type, LOCAL_EXECUTOR_NAME)
    reason = f"local executor stub {outcome}"
    append_job_transition(job, f"executor_{outcome}", outcome, reason)
    refs = normalize_evidence_refs(list(job.get("evidence_refs", [])) + [executor_result_ref(workspace_id, run_id, job_id), executor_event_log_ref(workspace_id, run_id)])
    job["evidence_refs"] = refs
    job["executor"] = {
        "name": LOCAL_EXECUTOR_NAME,
        "mode": "deterministic_local_stub",
        "result_ref": executor_result_ref(workspace_id, run_id, job_id),
        "provider_calls": False,
        "network_calls": False,
        "env_reads": False,
        "external_worker_calls": False,
    }
    write_job_payload(root, workspace_id, run_id, job)
    return {
        "schema_version": 1,
        "kind": "agentoffice.framework_runtime_executor_run_once",
        "workspace_id": workspace_id,
        "run_id": run_id,
        "job": job,
        "executor_result": result,
        "progressed": True,
        "local_stub": True,
        "provider_calls": False,
        "network_calls": False,
        "env_reads": False,
    }


def executor_loop_payload(root: Path, workspace_id: str, run_id: str, max_iterations: int = 100) -> dict[str, Any]:
    if max_iterations < 1:
        raise FrameworkRuntimeError("Executor loop max iterations must be at least 1.")
    actions: list[dict[str, Any]] = []
    for _ in range(max_iterations):
        action = executor_run_once_payload(root, workspace_id, run_id)
        if not action["progressed"]:
            break
        actions.append(action)
    status = executor_status_payload(root, workspace_id, run_id)
    return {
        "schema_version": 1,
        "kind": "agentoffice.framework_runtime_executor_loop",
        "workspace_id": workspace_id,
        "run_id": run_id,
        "actions": actions,
        "action_count": len(actions),
        "complete": status["pending_count"] == 0 and status["running_count"] == 0,
        "status": status,
        "local_stub": True,
        "provider_calls": False,
        "network_calls": False,
        "env_reads": False,
    }


def executor_status_payload(root: Path, workspace_id: str, run_id: str) -> dict[str, Any]:
    root = safe_root(root)
    ensure_runtime_run(root, workspace_id, run_id)
    jobs = list_jobs_payload(root, workspace_id, run_id)["jobs"]
    results = list_json_objects(executor_results_dir(root, workspace_id, run_id))
    return {
        "schema_version": 1,
        "kind": "agentoffice.framework_runtime_executor_status",
        "workspace_id": workspace_id,
        "run_id": run_id,
        "executor": LOCAL_EXECUTOR_NAME,
        "mode": "deterministic_local_stub",
        "jobs": jobs,
        "executor_results": results,
        "job_count": len(jobs),
        "pending_count": sum(1 for job in jobs if job.get("status") == "pending"),
        "running_count": sum(1 for job in jobs if job.get("status") == "running"),
        "succeeded_count": sum(1 for job in jobs if job.get("status") == "succeeded"),
        "failed_count": sum(1 for job in jobs if job.get("status") == "failed"),
        "cancelled_count": sum(1 for job in jobs if job.get("status") == "cancelled"),
        "local_stub": True,
        "provider_calls": False,
        "network_calls": False,
        "env_reads": False,
        "external_worker_calls": False,
    }


def worker_results_dir(root: Path, workspace_id: str, run_id: str) -> Path:
    return ensure_runtime_run(root, workspace_id, run_id) / "worker_results"


def worker_result_path(root: Path, workspace_id: str, run_id: str, job_id: str) -> Path:
    job_id = validate_runtime_id(job_id, "job_id")
    return worker_results_dir(root, workspace_id, run_id) / f"{job_id}.json"


def worker_result_ref(workspace_id: str, run_id: str, job_id: str) -> str:
    return f".ai/workspaces/{workspace_id}/runs/{run_id}/worker_results/{job_id}.json"


def read_worker_result_payload(root: Path, workspace_id: str, run_id: str, job_id: str) -> dict[str, Any]:
    path = worker_result_path(root, workspace_id, run_id, job_id)
    if not path.exists():
        raise FrameworkRuntimeError(f"Worker result not found for job: {job_id}")
    try:
        return read_json(path)
    except WorkspaceStoreError as exc:
        raise FrameworkRuntimeError(str(exc)) from exc


def worker_result_payload(workspace_id: str, run_id: str, job: dict[str, Any], adapter_id: str, status: str, summary: str, evidence_refs: list[str] | None = None) -> dict[str, Any]:
    job_id = str(job["job_id"])
    return {
        "schema_version": 1,
        "kind": "agentoffice.framework_runtime_worker_result",
        "workspace_id": workspace_id,
        "run_id": run_id,
        "job_id": job_id,
        "adapter_id": adapter_id,
        "status": status,
        "summary": summary,
        "evidence_refs": normalize_evidence_refs(evidence_refs),
        "local_static": True,
        "deterministic_intake": True,
        "provider_calls": False,
        "network_calls": False,
        "env_reads": False,
        "external_worker_calls": False,
        "codex_worker_connected": False,
        "claude_worker_connected": False,
    }


def intake_worker_result_payload(root: Path, workspace_id: str, run_id: str, job_id: str, adapter_id: str, status: str, summary: str, evidence_refs: list[str] | None = None) -> dict[str, Any]:
    root = safe_root(root)
    adapter_id = validate_runtime_id(adapter_id, "adapter_id")
    if adapter_id != LOCAL_WORKER_ADAPTER_ID:
        raise FrameworkRuntimeError(f"Unsupported worker adapter: {adapter_id}")
    if status not in WORKER_RESULT_STATUSES:
        raise FrameworkRuntimeError(f"Unsupported worker result status: {status}")
    if not summary.strip():
        raise FrameworkRuntimeError("Worker result summary must not be empty.")
    job = read_job_payload(root, workspace_id, run_id, job_id)
    old_status = str(job.get("status", ""))
    if old_status in TERMINAL_JOB_STATUSES:
        raise FrameworkRuntimeError(f"Job {job_id} is terminal and cannot accept worker result: {old_status}")
    if old_status not in {"pending", "running"}:
        raise FrameworkRuntimeError(f"Job {job_id} cannot accept worker result from status: {old_status}")
    target = worker_result_path(root, workspace_id, run_id, job_id)
    if target.exists():
        raise FrameworkRuntimeError(f"Worker result already exists for job: {job_id}")

    result = worker_result_payload(workspace_id, run_id, job, adapter_id, status, summary, evidence_refs)
    write_json_atomic(target, result)
    append_runtime_event(root, workspace_id, run_id, "worker_result.received", adapter_id)
    append_runtime_event(root, workspace_id, run_id, f"worker_result.{status}", adapter_id)
    append_job_transition(job, f"worker_result_{status}", status, f"deterministic worker result {status}")
    refs = normalize_evidence_refs(
        list(job.get("evidence_refs", []))
        + list(result.get("evidence_refs", []))
        + [worker_result_ref(workspace_id, run_id, job_id), executor_event_log_ref(workspace_id, run_id)]
    )
    job["evidence_refs"] = refs
    job["worker_result"] = {
        "adapter_id": adapter_id,
        "result_ref": worker_result_ref(workspace_id, run_id, job_id),
        "status": status,
        "provider_calls": False,
        "network_calls": False,
        "env_reads": False,
        "external_worker_calls": False,
    }
    write_job_payload(root, workspace_id, run_id, job)
    return {
        "schema_version": 1,
        "kind": "agentoffice.framework_runtime_worker_result_intake",
        "workspace_id": workspace_id,
        "run_id": run_id,
        "job": job,
        "worker_result": result,
        "local_static": True,
        "provider_calls": False,
        "network_calls": False,
        "env_reads": False,
        "external_worker_calls": False,
    }



def orchestration_id_for_goal(goal_id: str) -> str:
    return validate_runtime_id(goal_id, "orchestration_id")


def orchestrations_dir(root: Path, workspace_id: str, run_id: str) -> Path:
    return ensure_runtime_run(root, workspace_id, run_id) / "orchestrations"


def orchestration_state_path(root: Path, workspace_id: str, run_id: str, goal_id: str) -> Path:
    orchestration_id = orchestration_id_for_goal(goal_id)
    return orchestrations_dir(root, workspace_id, run_id) / f"{orchestration_id}.json"


def orchestration_state_ref(workspace_id: str, run_id: str, goal_id: str) -> str:
    orchestration_id = orchestration_id_for_goal(goal_id)
    return f".ai/workspaces/{workspace_id}/runs/{run_id}/orchestrations/{orchestration_id}.json"


def task_graph_ref(workspace_id: str, goal_id: str) -> str:
    return f".ai/workspaces/{workspace_id}/goals/{goal_id}/task_graph.json"


def orchestration_job_ref(workspace_id: str, run_id: str, job_id: str) -> str:
    return f".ai/workspaces/{workspace_id}/runs/{run_id}/jobs/{job_id}.json"


def orchestration_transition_entry(sequence: int, action: str, from_status: str | None, to_status: str, reason: str) -> dict[str, Any]:
    return {
        "sequence": sequence,
        "stamp": f"orchestration-transition-{sequence:04d}",
        "action": action,
        "from_status": from_status,
        "to_status": to_status,
        "reason": reason,
    }


def append_orchestration_transition(payload: dict[str, Any], action: str, new_status: str, reason: str) -> dict[str, Any]:
    old_status = str(payload.get("status", "")) or None
    log = list(payload.get("transition_log", []))
    transition = orchestration_transition_entry(len(log) + 1, action, old_status, new_status, reason)
    log.append(transition)
    payload["status"] = new_status
    payload["updated_at"] = transition["stamp"]
    payload["transition_log"] = log
    return payload


def orchestration_ordered_tasks(graph: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    tasks = list(graph.get("tasks", []))
    by_id = {str(task["task_id"]): task for task in tasks}
    accepted = {str(task["task_id"]) for task in tasks if str(task.get("status", "created")) == "accepted"}
    remaining = {str(task["task_id"]) for task in tasks if str(task.get("status", "created")) == "created"}
    blocked: list[dict[str, Any]] = []
    for task in tasks:
        status = str(task.get("status", "created"))
        if status not in {"created", "accepted"}:
            blocked.append({"task_id": str(task["task_id"]), "reasons": [f"status:{status}"]})

    ordered: list[dict[str, Any]] = []
    while remaining:
        ready_batch: list[dict[str, Any]] = []
        for task in tasks:
            task_id = str(task["task_id"])
            if task_id not in remaining:
                continue
            if all(str(dependency) in accepted for dependency in task.get("depends_on", [])):
                ready_batch.append(task)
        if not ready_batch:
            for task in tasks:
                task_id = str(task["task_id"])
                if task_id not in remaining:
                    continue
                reasons: list[str] = []
                for dependency in task.get("depends_on", []):
                    dependency_id = str(dependency)
                    if dependency_id not in by_id:
                        reasons.append(f"unknown_dependency:{dependency_id}")
                    elif dependency_id not in accepted:
                        reasons.append(f"dependency_not_accepted:{dependency_id}")
                blocked.append({"task_id": task_id, "reasons": reasons or ["not_ready"]})
            break
        for task in ready_batch:
            task_id = str(task["task_id"])
            ordered.append(dict(task))
            accepted.add(task_id)
            remaining.remove(task_id)
    return ordered, blocked


def orchestration_dispatch_for_task(workspace_id: str, run_id: str, goal_id: str, task: dict[str, Any], sequence: int) -> dict[str, Any]:
    task_id = validate_runtime_id(str(task["task_id"]), "task_id")
    job_id = task_id
    return {
        "schema_version": 1,
        "kind": "agentoffice.framework_runtime_local_task_dispatch",
        "sequence": sequence,
        "workspace_id": workspace_id,
        "run_id": run_id,
        "goal_id": goal_id,
        "task_id": task_id,
        "job_id": job_id,
        "title": str(task.get("title", task_id)),
        "role": str(task.get("role", "implementation_agent")),
        "depends_on": list(task.get("depends_on", [])),
        "required_evidence": list(task.get("required_evidence", [])),
        "worker_adapter": LOCAL_WORKER_ADAPTER_ID,
        "job_ref": orchestration_job_ref(workspace_id, run_id, job_id),
        "worker_result_ref": worker_result_ref(workspace_id, run_id, job_id),
        "local_static": True,
        "provider_calls": False,
        "network_calls": False,
        "env_reads": False,
        "external_worker_calls": False,
        "codex_worker_connected": False,
        "claude_worker_connected": False,
    }


def orchestration_plan_payload(root: Path, workspace_id: str, run_id: str, goal_id: str) -> dict[str, Any]:
    root = safe_root(root)
    ensure_runtime_run(root, workspace_id, run_id)
    graph = load_runtime_graph(root, workspace_id, goal_id)
    ordered, blocked = orchestration_ordered_tasks(graph)
    dispatches = [
        orchestration_dispatch_for_task(workspace_id, run_id, goal_id, task, index)
        for index, task in enumerate(ordered, start=1)
    ]
    return {
        "schema_version": 1,
        "kind": "agentoffice.framework_runtime_orchestration_plan",
        "contract_version": "local_orchestration_contract_v1",
        "workspace_id": validate_runtime_id(workspace_id, "workspace_id"),
        "run_id": validate_runtime_id(run_id, "run_id"),
        "goal_id": validate_runtime_id(goal_id, "goal_id"),
        "orchestration_id": orchestration_id_for_goal(goal_id),
        "request": {
            "kind": "agentoffice.framework_runtime_orchestration_request",
            "workspace_id": workspace_id,
            "run_id": run_id,
            "goal_id": goal_id,
            "task_graph_ref": task_graph_ref(workspace_id, goal_id),
            "mode": "local_static",
        },
        "dispatch_plan": dispatches,
        "blocked_tasks": blocked,
        "valid": not blocked,
        "status_model": ["planned", "running", "succeeded", "blocked", "failed"],
        "ordering_contract": "task graph order; dependencies must be accepted before dependent dispatch",
        "local_static": True,
        "deterministic": True,
        "provider_calls": False,
        "network_calls": False,
        "env_reads": False,
        "external_worker_calls": False,
        "codex_worker_connected": False,
        "claude_worker_connected": False,
    }


def read_orchestration_state_payload(root: Path, workspace_id: str, run_id: str, goal_id: str) -> dict[str, Any]:
    path = orchestration_state_path(root, workspace_id, run_id, goal_id)
    if not path.exists():
        raise FrameworkRuntimeError(f"Orchestration state not found: {goal_id}")
    return read_runtime_json_child(path.parent, path)


def orchestration_show_payload(root: Path, workspace_id: str, run_id: str, goal_id: str) -> dict[str, Any]:
    root = safe_root(root)
    path = orchestration_state_path(root, workspace_id, run_id, goal_id)
    if path.exists():
        state = read_runtime_json_child(path.parent, path)
        persisted = True
    else:
        state = orchestration_plan_payload(root, workspace_id, run_id, goal_id)
        persisted = False
    return {
        "schema_version": 1,
        "kind": "agentoffice.framework_runtime_orchestration_show",
        "workspace_id": workspace_id,
        "run_id": run_id,
        "goal_id": goal_id,
        "persisted": persisted,
        "orchestration": state,
        "local_static": True,
        "provider_calls": False,
        "network_calls": False,
        "env_reads": False,
    }


def orchestration_validate_payload(root: Path, workspace_id: str, run_id: str, goal_id: str) -> dict[str, Any]:
    plan = orchestration_plan_payload(root, workspace_id, run_id, goal_id)
    errors = [
        f"{item['task_id']}:{','.join(item['reasons'])}"
        for item in plan["blocked_tasks"]
    ]
    return {
        "schema_version": 1,
        "kind": "agentoffice.framework_runtime_orchestration_validation",
        "workspace_id": workspace_id,
        "run_id": run_id,
        "goal_id": goal_id,
        "valid": not errors,
        "errors": errors,
        "dispatch_count": len(plan["dispatch_plan"]),
        "plan": plan,
        "local_static": True,
        "provider_calls": False,
        "network_calls": False,
        "env_reads": False,
        "external_worker_calls": False,
    }


def initial_orchestration_state(plan: dict[str, Any]) -> dict[str, Any]:
    transition = orchestration_transition_entry(1, "plan", None, "planned", "deterministic orchestration plan prepared")
    return {
        "schema_version": 1,
        "kind": "agentoffice.framework_runtime_orchestration_state",
        "contract_version": "local_orchestration_contract_v1",
        "workspace_id": plan["workspace_id"],
        "run_id": plan["run_id"],
        "goal_id": plan["goal_id"],
        "orchestration_id": plan["orchestration_id"],
        "status": "planned",
        "created_at": transition["stamp"],
        "updated_at": transition["stamp"],
        "request": plan["request"],
        "plan": plan,
        "tasks": [],
        "evidence_refs": [
            task_graph_ref(plan["workspace_id"], plan["goal_id"]),
            orchestration_state_ref(plan["workspace_id"], plan["run_id"], plan["goal_id"]),
        ],
        "transition_log": [transition],
        "local_static": True,
        "deterministic": True,
        "provider_calls": False,
        "network_calls": False,
        "env_reads": False,
        "external_worker_calls": False,
        "codex_worker_connected": False,
        "claude_worker_connected": False,
        "daemon_started": False,
        "background_worker_started": False,
    }


def orchestration_run_local_payload(root: Path, workspace_id: str, run_id: str, goal_id: str) -> dict[str, Any]:
    root = safe_root(root)
    state_path = orchestration_state_path(root, workspace_id, run_id, goal_id)
    if state_path.exists():
        state = read_runtime_json_child(state_path.parent, state_path)
        if state.get("status") in {"succeeded", "blocked", "failed"}:
            return {
                "schema_version": 1,
                "kind": "agentoffice.framework_runtime_orchestration_run_local",
                "workspace_id": workspace_id,
                "run_id": run_id,
                "goal_id": goal_id,
                "progressed": False,
                "reason": f"orchestration already {state.get('status')}",
                "orchestration": state,
                "local_static": True,
                "provider_calls": False,
                "network_calls": False,
                "env_reads": False,
            }
        raise FrameworkRuntimeError(f"Orchestration state is not terminal: {state.get('status')}")

    plan = orchestration_plan_payload(root, workspace_id, run_id, goal_id)
    state = initial_orchestration_state(plan)
    append_runtime_event(root, workspace_id, run_id, "orchestration.planned", LOCAL_ORCHESTRATOR_NAME)
    if not plan["valid"]:
        append_orchestration_transition(state, "block", "blocked", "orchestration plan has blocked tasks")
        write_json_atomic(state_path, state)
        append_runtime_event(root, workspace_id, run_id, "orchestration.blocked", LOCAL_ORCHESTRATOR_NAME)
        return {
            "schema_version": 1,
            "kind": "agentoffice.framework_runtime_orchestration_run_local",
            "workspace_id": workspace_id,
            "run_id": run_id,
            "goal_id": goal_id,
            "progressed": False,
            "reason": "orchestration plan blocked",
            "orchestration": state,
            "local_static": True,
            "provider_calls": False,
            "network_calls": False,
            "env_reads": False,
        }

    append_orchestration_transition(state, "start", "running", "local orchestration run started")
    write_json_atomic(state_path, state)
    append_runtime_event(root, workspace_id, run_id, "orchestration.started", LOCAL_ORCHESTRATOR_NAME)
    for dispatch in plan["dispatch_plan"]:
        task_id = str(dispatch["task_id"])
        job_id = str(dispatch["job_id"])
        job = create_job_payload(
            root,
            workspace_id,
            run_id,
            job_id,
            f"orchestration task {task_id}: {dispatch['title']}",
            {
                "dispatch_sequence": str(dispatch["sequence"]),
                "goal_id": goal_id,
                "orchestration_id": plan["orchestration_id"],
                "task_id": task_id,
            },
            [task_graph_ref(workspace_id, goal_id), orchestration_state_ref(workspace_id, run_id, goal_id)],
        )
        append_runtime_event(root, workspace_id, run_id, "orchestration.task_dispatched", LOCAL_ORCHESTRATOR_NAME)
        intake = intake_worker_result_payload(
            root,
            workspace_id,
            run_id,
            job_id,
            LOCAL_WORKER_ADAPTER_ID,
            "succeeded",
            f"local orchestration completed task {task_id}: {dispatch['title']}",
            [orchestration_state_ref(workspace_id, run_id, goal_id)],
        )
        task = set_task_status(root, workspace_id, run_id, goal_id, task_id, "accepted")
        append_runtime_event(root, workspace_id, run_id, "orchestration.task_succeeded", LOCAL_ORCHESTRATOR_NAME)
        state["tasks"].append(
            {
                "sequence": dispatch["sequence"],
                "task_id": task_id,
                "job_id": job_id,
                "status": "succeeded",
                "task_status": task["status"],
                "job_ref": orchestration_job_ref(workspace_id, run_id, job_id),
                "worker_result_ref": worker_result_ref(workspace_id, run_id, job_id),
                "transition_count": len(intake["job"]["transition_log"]),
            }
        )
        state["evidence_refs"] = normalize_evidence_refs(
            list(state["evidence_refs"])
            + [orchestration_job_ref(workspace_id, run_id, job_id), worker_result_ref(workspace_id, run_id, job_id), executor_event_log_ref(workspace_id, run_id)]
            + list(job.get("evidence_refs", []))
            + list(intake["worker_result"].get("evidence_refs", []))
        )
        write_json_atomic(state_path, state)

    append_orchestration_transition(state, "succeed", "succeeded", "local orchestration run completed")
    write_json_atomic(state_path, state)
    append_runtime_event(root, workspace_id, run_id, "orchestration.succeeded", LOCAL_ORCHESTRATOR_NAME)
    return {
        "schema_version": 1,
        "kind": "agentoffice.framework_runtime_orchestration_run_local",
        "workspace_id": workspace_id,
        "run_id": run_id,
        "goal_id": goal_id,
        "progressed": True,
        "reason": "local orchestration completed",
        "orchestration": state,
        "local_static": True,
        "provider_calls": False,
        "network_calls": False,
        "env_reads": False,
        "external_worker_calls": False,
    }



def execution_loops_dir(root: Path, workspace_id: str, run_id: str) -> Path:
    return ensure_runtime_run(root, workspace_id, run_id) / "execution_loops"


def execution_loop_state_path(root: Path, workspace_id: str, run_id: str, goal_id: str) -> Path:
    execution_id = orchestration_id_for_goal(goal_id)
    return execution_loops_dir(root, workspace_id, run_id) / f"{execution_id}.json"


def execution_loop_state_ref(workspace_id: str, run_id: str, goal_id: str) -> str:
    execution_id = orchestration_id_for_goal(goal_id)
    return f".ai/workspaces/{workspace_id}/runs/{run_id}/execution_loops/{execution_id}.json"



def policy_decisions_dir(root: Path, workspace_id: str, run_id: str) -> Path:
    return ensure_runtime_run(root, workspace_id, run_id) / "policy_decisions"


def policy_decision_path(root: Path, workspace_id: str, run_id: str, job_id: str) -> Path:
    job_id = validate_runtime_id(job_id, "job_id")
    return policy_decisions_dir(root, workspace_id, run_id) / f"{job_id}.json"


def policy_decision_ref(workspace_id: str, run_id: str, job_id: str) -> str:
    job_id = validate_runtime_id(job_id, "job_id")
    return f".ai/workspaces/{workspace_id}/runs/{run_id}/policy_decisions/{job_id}.json"


def write_policy_decision(root: Path, workspace_id: str, run_id: str, job_id: str, decision: dict[str, Any]) -> dict[str, Any]:
    payload = dict(decision)
    payload["job_id"] = validate_runtime_id(job_id, "job_id")
    payload["decision_ref"] = policy_decision_ref(workspace_id, run_id, job_id)
    write_json_atomic(policy_decision_path(root, workspace_id, run_id, job_id), payload)
    return payload


def fail_job_for_policy_denial(root: Path, workspace_id: str, run_id: str, goal_id: str, job_id: str, task_id: str, title: str, state: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    target = job_path(root, workspace_id, run_id, job_id)
    decision_ref = policy_decision_ref(workspace_id, run_id, job_id)
    if target.exists():
        job = read_job_payload(root, workspace_id, run_id, job_id)
    else:
        job = create_job_payload(
            root,
            workspace_id,
            run_id,
            job_id,
            f"policy denied execution loop task {task_id}: {title}",
            {
                "dispatch_sequence": str(state.get("cursor", 0) + 1),
                "execution_id": str(state["execution_id"]),
                "goal_id": goal_id,
                "task_id": task_id,
                "policy_decision": "denied",
                "policy_reason_code": str(decision["reason_code"]),
                "capability_id": str(decision["capability_id"]),
            },
            [task_graph_ref(workspace_id, goal_id), execution_loop_state_ref(workspace_id, run_id, goal_id), decision_ref],
        )
    metadata = normalize_job_metadata(
        dict(job.get("metadata", {}))
        | {
            "policy_decision": "denied",
            "policy_reason_code": str(decision["reason_code"]),
            "capability_id": str(decision["capability_id"]),
        }
    )
    job["metadata"] = metadata
    job["policy_decision"] = decision
    job["evidence_refs"] = normalize_evidence_refs(list(job.get("evidence_refs", [])) + [decision_ref, executor_event_log_ref(workspace_id, run_id)])
    if str(job.get("status")) not in TERMINAL_JOB_STATUSES:
        append_job_transition(job, "policy_denied", "failed", str(decision["reason"]))
    write_job_payload(root, workspace_id, run_id, job)
    return job


def execution_loop_transition_entry(sequence: int, action: str, from_status: str | None, to_status: str, reason: str) -> dict[str, Any]:
    return {
        "sequence": sequence,
        "stamp": f"execution-loop-transition-{sequence:04d}",
        "action": action,
        "from_status": from_status,
        "to_status": to_status,
        "reason": reason,
    }


def append_execution_loop_transition(payload: dict[str, Any], action: str, new_status: str, reason: str) -> dict[str, Any]:
    old_status = str(payload.get("status", "")) or None
    log = list(payload.get("transition_log", []))
    transition = execution_loop_transition_entry(len(log) + 1, action, old_status, new_status, reason)
    log.append(transition)
    payload["status"] = new_status
    payload["updated_at"] = transition["stamp"]
    payload["transition_log"] = log
    return payload


def initial_execution_loop_state(plan: dict[str, Any]) -> dict[str, Any]:
    transition = execution_loop_transition_entry(1, "plan", None, "planned", "deterministic execution loop planned")
    dispatches = [
        {
            "sequence": dispatch["sequence"],
            "task_id": dispatch["task_id"],
            "job_id": dispatch["job_id"],
            "status": "pending",
            "job_ref": dispatch["job_ref"],
            "worker_result_ref": dispatch["worker_result_ref"],
        }
        for dispatch in plan["dispatch_plan"]
    ]
    return {
        "schema_version": 1,
        "kind": "agentoffice.framework_runtime_execution_loop_state",
        "contract_version": "local_execution_loop_v1",
        "workspace_id": plan["workspace_id"],
        "run_id": plan["run_id"],
        "goal_id": plan["goal_id"],
        "execution_id": plan["orchestration_id"],
        "orchestration_id": plan["orchestration_id"],
        "status": "planned",
        "created_at": transition["stamp"],
        "updated_at": transition["stamp"],
        "cursor": 0,
        "dispatch_count": len(dispatches),
        "completed_count": 0,
        "plan": plan,
        "dispatches": dispatches,
        "evidence_refs": [
            task_graph_ref(plan["workspace_id"], plan["goal_id"]),
            execution_loop_state_ref(plan["workspace_id"], plan["run_id"], plan["goal_id"]),
        ],
        "transition_log": [transition],
        "local_static": True,
        "deterministic": True,
        "provider_calls": False,
        "network_calls": False,
        "env_reads": False,
        "external_worker_calls": False,
        "codex_worker_connected": False,
        "claude_worker_connected": False,
        "daemon_started": False,
        "background_worker_started": False,
    }


def read_execution_loop_state_payload(root: Path, workspace_id: str, run_id: str, goal_id: str) -> dict[str, Any]:
    path = execution_loop_state_path(root, workspace_id, run_id, goal_id)
    if not path.exists():
        raise FrameworkRuntimeError(f"Execution loop state not found: {goal_id}")
    return read_runtime_json_child(path.parent, path)


def write_execution_loop_state(root: Path, workspace_id: str, run_id: str, goal_id: str, state: dict[str, Any]) -> dict[str, Any]:
    write_json_atomic(execution_loop_state_path(root, workspace_id, run_id, goal_id), state)
    return state


def load_or_create_execution_loop_state(root: Path, workspace_id: str, run_id: str, goal_id: str) -> tuple[dict[str, Any], bool]:
    path = execution_loop_state_path(root, workspace_id, run_id, goal_id)
    if path.exists():
        return read_runtime_json_child(path.parent, path), False
    plan = orchestration_plan_payload(root, workspace_id, run_id, goal_id)
    state = initial_execution_loop_state(plan)
    append_runtime_event(root, workspace_id, run_id, "execution_loop.planned", LOCAL_EXECUTION_LOOP_NAME)
    if not plan["valid"]:
        append_execution_loop_transition(state, "block", "blocked", "execution loop plan has blocked tasks")
        write_execution_loop_state(root, workspace_id, run_id, goal_id, state)
        append_runtime_event(root, workspace_id, run_id, "execution_loop.blocked", LOCAL_EXECUTION_LOOP_NAME)
        return state, True
    write_execution_loop_state(root, workspace_id, run_id, goal_id, state)
    return state, True


def execution_loop_status_payload(root: Path, workspace_id: str, run_id: str, goal_id: str) -> dict[str, Any]:
    root = safe_root(root)
    path = execution_loop_state_path(root, workspace_id, run_id, goal_id)
    if path.exists():
        state = read_runtime_json_child(path.parent, path)
        persisted = True
    else:
        plan = orchestration_plan_payload(root, workspace_id, run_id, goal_id)
        state = initial_execution_loop_state(plan)
        if not plan["valid"]:
            append_execution_loop_transition(state, "block", "blocked", "execution loop plan has blocked tasks")
        persisted = False
    return {
        "schema_version": 1,
        "kind": "agentoffice.framework_runtime_execution_loop_status",
        "workspace_id": workspace_id,
        "run_id": run_id,
        "goal_id": goal_id,
        "persisted": persisted,
        "execution_loop": state,
        "complete": state.get("status") == "succeeded",
        "local_static": True,
        "provider_calls": False,
        "network_calls": False,
        "env_reads": False,
        "external_worker_calls": False,
    }


def execution_loop_next_dispatch(state: dict[str, Any]) -> dict[str, Any] | None:
    for dispatch in state.get("dispatches", []):
        if dispatch.get("status") == "pending":
            return dispatch
    return None


def execution_loop_dispatch_plan_item(state: dict[str, Any], task_id: str) -> dict[str, Any]:
    for dispatch in state["plan"]["dispatch_plan"]:
        if str(dispatch["task_id"]) == task_id:
            return dispatch
    raise FrameworkRuntimeError(f"Execution loop dispatch not found for task: {task_id}")


def execution_loop_run_once_payload(root: Path, workspace_id: str, run_id: str, goal_id: str, capability_id: str = LOCAL_EXECUTION_CAPABILITY_ID) -> dict[str, Any]:
    root = safe_root(root)
    state, created = load_or_create_execution_loop_state(root, workspace_id, run_id, goal_id)
    if state.get("status") in {"succeeded", "blocked", "failed"}:
        return {
            "schema_version": 1,
            "kind": "agentoffice.framework_runtime_execution_loop_run_once",
            "workspace_id": workspace_id,
            "run_id": run_id,
            "goal_id": goal_id,
            "progressed": False,
            "created": created,
            "reason": f"execution loop already {state.get('status')}",
            "execution_loop": state,
            "dispatch": None,
            "local_static": True,
            "provider_calls": False,
            "network_calls": False,
            "env_reads": False,
        }
    if state.get("status") == "planned":
        append_execution_loop_transition(state, "start", "running", "local execution loop started")
        write_execution_loop_state(root, workspace_id, run_id, goal_id, state)
        append_runtime_event(root, workspace_id, run_id, "execution_loop.started", LOCAL_EXECUTION_LOOP_NAME)
    if state.get("status") != "running":
        raise FrameworkRuntimeError(f"Execution loop state is not runnable: {state.get('status')}")

    dispatch = execution_loop_next_dispatch(state)
    if dispatch is None:
        append_execution_loop_transition(state, "succeed", "succeeded", "local execution loop completed")
        write_execution_loop_state(root, workspace_id, run_id, goal_id, state)
        append_runtime_event(root, workspace_id, run_id, "execution_loop.succeeded", LOCAL_EXECUTION_LOOP_NAME)
        return {
            "schema_version": 1,
            "kind": "agentoffice.framework_runtime_execution_loop_run_once",
            "workspace_id": workspace_id,
            "run_id": run_id,
            "goal_id": goal_id,
            "progressed": False,
            "created": created,
            "reason": "execution loop completed",
            "execution_loop": state,
            "dispatch": None,
            "local_static": True,
            "provider_calls": False,
            "network_calls": False,
            "env_reads": False,
        }

    task_id = str(dispatch["task_id"])
    job_id = str(dispatch["job_id"])
    plan_item = execution_loop_dispatch_plan_item(state, task_id)
    decision = write_policy_decision(
        root,
        workspace_id,
        run_id,
        job_id,
        policy_decision_payload(
            capability_id,
            LOCAL_EXECUTION_LOOP_NAME,
            "dispatch",
            {"workspace_id": workspace_id, "run_id": run_id, "goal_id": goal_id, "task_id": task_id, "job_id": job_id},
        ),
    )
    dispatch["policy_decision"] = {
        "allowed": decision["allowed"],
        "reason_code": decision["reason_code"],
        "capability_id": decision["capability_id"],
        "decision_ref": decision["decision_ref"],
    }
    if not decision["allowed"]:
        append_runtime_event(root, workspace_id, run_id, "policy.denied", LOCAL_EXECUTION_LOOP_NAME)
        job = fail_job_for_policy_denial(root, workspace_id, run_id, goal_id, job_id, task_id, str(plan_item["title"]), state, decision)
        task = set_task_status(root, workspace_id, run_id, goal_id, task_id, "rejected")
        dispatch["status"] = "policy_denied"
        dispatch["task_status"] = task["status"]
        dispatch["job_status"] = job["status"]
        state["cursor"] = int(dispatch["sequence"])
        state["evidence_refs"] = normalize_evidence_refs(
            list(state["evidence_refs"])
            + [policy_decision_ref(workspace_id, run_id, job_id), orchestration_job_ref(workspace_id, run_id, job_id), executor_event_log_ref(workspace_id, run_id)]
            + list(job.get("evidence_refs", []))
        )
        append_execution_loop_transition(state, "policy_denied", "blocked", str(decision["reason"]))
        write_execution_loop_state(root, workspace_id, run_id, goal_id, state)
        append_runtime_event(root, workspace_id, run_id, "execution_loop.policy_denied", LOCAL_EXECUTION_LOOP_NAME)
        return {
            "schema_version": 1,
            "kind": "agentoffice.framework_runtime_execution_loop_run_once",
            "workspace_id": workspace_id,
            "run_id": run_id,
            "goal_id": goal_id,
            "progressed": False,
            "created": created,
            "reason": str(decision["reason"]),
            "execution_loop": state,
            "dispatch": dispatch,
            "job": job,
            "worker_result": None,
            "policy_decision": decision,
            "local_static": True,
            "provider_calls": False,
            "network_calls": False,
            "env_reads": False,
            "external_worker_calls": False,
        }
    append_runtime_event(root, workspace_id, run_id, "policy.allowed", LOCAL_EXECUTION_LOOP_NAME)
    job_path_target = job_path(root, workspace_id, run_id, job_id)
    if job_path_target.exists():
        job = read_job_payload(root, workspace_id, run_id, job_id)
    else:
        job = create_job_payload(
            root,
            workspace_id,
            run_id,
            job_id,
            f"execution loop task {task_id}: {plan_item['title']}",
            {
                "dispatch_sequence": str(dispatch["sequence"]),
                "execution_id": str(state["execution_id"]),
                "goal_id": goal_id,
                "task_id": task_id,
            },
            [task_graph_ref(workspace_id, goal_id), execution_loop_state_ref(workspace_id, run_id, goal_id), policy_decision_ref(workspace_id, run_id, job_id)],
        )
    append_runtime_event(root, workspace_id, run_id, "execution_loop.task_dispatched", LOCAL_EXECUTION_LOOP_NAME)
    if worker_result_path(root, workspace_id, run_id, job_id).exists():
        worker_result = read_worker_result_payload(root, workspace_id, run_id, job_id)
    else:
        intake = intake_worker_result_payload(
            root,
            workspace_id,
            run_id,
            job_id,
            LOCAL_WORKER_ADAPTER_ID,
            "succeeded",
            f"local execution loop completed task {task_id}: {plan_item['title']}",
            [execution_loop_state_ref(workspace_id, run_id, goal_id)],
        )
        job = intake["job"]
        worker_result = intake["worker_result"]
    task = set_task_status(root, workspace_id, run_id, goal_id, task_id, "accepted")
    append_runtime_event(root, workspace_id, run_id, "execution_loop.task_succeeded", LOCAL_EXECUTION_LOOP_NAME)
    dispatch["status"] = "succeeded"
    dispatch["task_status"] = task["status"]
    dispatch["job_status"] = job["status"]
    dispatch["worker_result_status"] = worker_result["status"]
    dispatch["policy_decision"]["allowed"] = True
    state["cursor"] = int(dispatch["sequence"])
    state["completed_count"] = sum(1 for item in state["dispatches"] if item.get("status") == "succeeded")
    state["evidence_refs"] = normalize_evidence_refs(
        list(state["evidence_refs"])
        + [policy_decision_ref(workspace_id, run_id, job_id), orchestration_job_ref(workspace_id, run_id, job_id), worker_result_ref(workspace_id, run_id, job_id), executor_event_log_ref(workspace_id, run_id)]
        + list(job.get("evidence_refs", []))
        + list(worker_result.get("evidence_refs", []))
    )
    if state["completed_count"] == state["dispatch_count"]:
        append_execution_loop_transition(state, "succeed", "succeeded", "local execution loop completed")
        append_runtime_event(root, workspace_id, run_id, "execution_loop.succeeded", LOCAL_EXECUTION_LOOP_NAME)
    write_execution_loop_state(root, workspace_id, run_id, goal_id, state)
    return {
        "schema_version": 1,
        "kind": "agentoffice.framework_runtime_execution_loop_run_once",
        "workspace_id": workspace_id,
        "run_id": run_id,
        "goal_id": goal_id,
        "progressed": True,
        "created": created,
        "reason": "local execution loop progressed one dispatch",
        "execution_loop": state,
        "dispatch": dispatch,
        "job": job,
        "worker_result": worker_result,
        "policy_decision": decision,
        "local_static": True,
        "provider_calls": False,
        "network_calls": False,
        "env_reads": False,
        "external_worker_calls": False,
    }


def execution_loop_payload(root: Path, workspace_id: str, run_id: str, goal_id: str, max_iterations: int = 100, capability_id: str = LOCAL_EXECUTION_CAPABILITY_ID) -> dict[str, Any]:
    if max_iterations < 1:
        raise FrameworkRuntimeError("Execution loop max iterations must be at least 1.")
    actions: list[dict[str, Any]] = []
    for _ in range(max_iterations):
        action = execution_loop_run_once_payload(root, workspace_id, run_id, goal_id, capability_id)
        if not action["progressed"]:
            break
        actions.append(action)
        if action["execution_loop"].get("status") in {"succeeded", "blocked", "failed"}:
            break
    status = execution_loop_status_payload(root, workspace_id, run_id, goal_id)
    return {
        "schema_version": 1,
        "kind": "agentoffice.framework_runtime_execution_loop",
        "workspace_id": workspace_id,
        "run_id": run_id,
        "goal_id": goal_id,
        "actions": actions,
        "action_count": len(actions),
        "complete": status["complete"],
        "status": status,
        "local_static": True,
        "provider_calls": False,
        "network_calls": False,
        "env_reads": False,
        "external_worker_calls": False,
    }




def scheduler_states_dir(root: Path, workspace_id: str, run_id: str) -> Path:
    return ensure_runtime_run(root, workspace_id, run_id) / "scheduler_states"


def scheduler_state_path(root: Path, workspace_id: str, run_id: str, goal_id: str) -> Path:
    return scheduler_states_dir(root, workspace_id, run_id) / f"{orchestration_id_for_goal(goal_id)}.json"


def scheduler_state_ref(workspace_id: str, run_id: str, goal_id: str) -> str:
    return f".ai/workspaces/{workspace_id}/runs/{run_id}/scheduler_states/{orchestration_id_for_goal(goal_id)}.json"


def scheduler_transition_entry(sequence: int, action: str, from_status: str | None, to_status: str, reason: str) -> dict[str, Any]:
    return {
        "sequence": sequence,
        "stamp": f"scheduler-transition-{sequence:04d}",
        "action": action,
        "from_status": from_status,
        "to_status": to_status,
        "reason": reason,
    }


def append_scheduler_transition(payload: dict[str, Any], action: str, new_status: str, reason: str) -> dict[str, Any]:
    old_status = str(payload.get("status", "")) or None
    log = list(payload.get("transition_log", []))
    transition = scheduler_transition_entry(len(log) + 1, action, old_status, new_status, reason)
    log.append(transition)
    payload["status"] = new_status
    payload["updated_at"] = transition["stamp"]
    payload["transition_log"] = log
    return payload


def scheduler_task_transition_entry(sequence: int, action: str, from_status: str | None, to_status: str, reason: str) -> dict[str, Any]:
    return {
        "sequence": sequence,
        "stamp": f"scheduler-task-transition-{sequence:04d}",
        "action": action,
        "from_status": from_status,
        "to_status": to_status,
        "reason": reason,
    }


def append_scheduler_task_transition(task: dict[str, Any], action: str, new_status: str, reason: str) -> dict[str, Any]:
    if new_status not in SCHEDULER_TASK_STATUSES:
        raise FrameworkRuntimeError(f"Unsupported scheduler task status: {new_status}")
    old_status = str(task.get("status", "")) or None
    log = list(task.get("transition_log", []))
    transition = scheduler_task_transition_entry(len(log) + 1, action, old_status, new_status, reason)
    log.append(transition)
    task["status"] = new_status
    task["updated_at"] = transition["stamp"]
    task["transition_log"] = log
    return task


def scheduler_priority(task: dict[str, Any]) -> int:
    raw = task.get("priority", task.get("metadata", {}).get("priority", 0) if isinstance(task.get("metadata"), dict) else 0)
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise FrameworkRuntimeError(f"Task priority must be an integer for task {task.get('task_id')}: {raw}") from exc


def scheduler_dependency_reasons(task: dict[str, Any], by_task_id: dict[str, dict[str, Any]]) -> list[str]:
    reasons: list[str] = []
    for dependency in task.get("depends_on", []):
        dependency_task = by_task_id.get(str(dependency))
        if dependency_task is None:
            reasons.append(f"unknown_dependency:{dependency}")
        elif dependency_task.get("status") != "accepted":
            reasons.append(f"dependency_not_accepted:{dependency}")
    return reasons


def initial_scheduler_state(root: Path, workspace_id: str, run_id: str, goal_id: str, trigger: str, max_retries: int) -> dict[str, Any]:
    if max_retries < 0:
        raise FrameworkRuntimeError("Scheduler max retries must be zero or greater.")
    graph = load_runtime_graph(root, workspace_id, goal_id)
    tasks = graph["tasks"]
    by_task_id = {task["task_id"]: task for task in tasks}
    scheduler_tasks: list[dict[str, Any]] = []
    for index, task in enumerate(tasks, start=1):
        task_status = str(task.get("status", "created"))
        reasons: list[str] = []
        if task_status in TERMINAL_TASK_STATUSES:
            initial_status = "completed" if task_status == "accepted" else "failed"
            reasons.append(f"task_terminal:{task_status}")
        elif task_status != "created":
            initial_status = "blocked"
            reasons.append(f"task_status:{task_status}")
        else:
            reasons = scheduler_dependency_reasons(task, by_task_id)
            initial_status = "blocked" if reasons else "pending"
        transition = scheduler_task_transition_entry(1, "request", None, initial_status, ";".join(reasons) or f"scheduler request trigger={trigger}")
        scheduler_tasks.append(
            {
                "sequence": index,
                "task_id": task["task_id"],
                "title": task["title"],
                "priority": scheduler_priority(task),
                "depends_on": list(task.get("depends_on", [])),
                "status": initial_status,
                "blocked_reasons": reasons,
                "retry_count": 0,
                "max_retries": max_retries,
                "job_id": None,
                "job_ref": None,
                "worker_assignment": None,
                "worker_result_ref": None,
                "updated_at": transition["stamp"],
                "transition_log": [transition],
            }
        )
    transition = scheduler_transition_entry(1, "request", None, "pending", f"scheduler request trigger={trigger}")
    return {
        "schema_version": 1,
        "kind": "agentoffice.framework_runtime_scheduler_state",
        "contract_version": "framework_runtime_wp8_scheduler_kernel_v1",
        "workspace_id": validate_runtime_id(workspace_id, "workspace_id"),
        "run_id": validate_runtime_id(run_id, "run_id"),
        "goal_id": validate_runtime_id(goal_id, "goal_id"),
        "scheduler_id": orchestration_id_for_goal(goal_id),
        "status": "pending",
        "trigger": trigger,
        "created_at": transition["stamp"],
        "updated_at": transition["stamp"],
        "tasks": scheduler_tasks,
        "task_count": len(scheduler_tasks),
        "selected_task_id": None,
        "completed_count": sum(1 for item in scheduler_tasks if item["status"] == "completed"),
        "failed_count": sum(1 for item in scheduler_tasks if item["status"] == "failed"),
        "blocked_count": sum(1 for item in scheduler_tasks if item["status"] == "blocked"),
        "evidence_refs": [task_graph_ref(workspace_id, goal_id), scheduler_state_ref(workspace_id, run_id, goal_id)],
        "transition_log": [transition],
        "local_static": True,
        "deterministic": True,
        "provider_calls": False,
        "network_calls": False,
        "env_reads": False,
        "external_worker_calls": False,
        "daemon_started": False,
        "background_worker_started": False,
        "legacy_runtime_backend": False,
    }


def refresh_scheduler_counts(state: dict[str, Any], append_transitions: bool = True) -> dict[str, Any]:
    tasks = list(state.get("tasks", []))
    state["task_count"] = len(tasks)
    state["completed_count"] = sum(1 for item in tasks if item.get("status") == "completed")
    state["failed_count"] = sum(1 for item in tasks if item.get("status") == "failed")
    state["blocked_count"] = sum(1 for item in tasks if item.get("status") == "blocked")
    if append_transitions and tasks and all(item.get("status") in TERMINAL_SCHEDULER_TASK_STATUSES for item in tasks):
        if state["failed_count"] and state.get("status") != "failed":
            append_scheduler_transition(state, "fail", "failed", "one or more scheduler tasks failed")
        elif not state["failed_count"] and state.get("status") != "completed":
            append_scheduler_transition(state, "complete", "completed", "all scheduler tasks completed")
    return state


def write_scheduler_state(root: Path, workspace_id: str, run_id: str, goal_id: str, state: dict[str, Any]) -> dict[str, Any]:
    refresh_scheduler_counts(state)
    write_json_atomic(scheduler_state_path(root, workspace_id, run_id, goal_id), state)
    return state


def read_scheduler_state(root: Path, workspace_id: str, run_id: str, goal_id: str) -> dict[str, Any]:
    path = scheduler_state_path(root, workspace_id, run_id, goal_id)
    if not path.exists():
        raise FrameworkRuntimeError(f"Scheduler state not found: {goal_id}")
    return read_runtime_json_child(path.parent, path)


def scheduler_task_by_id(state: dict[str, Any], task_id: str) -> dict[str, Any]:
    for task in state.get("tasks", []):
        if str(task.get("task_id")) == task_id:
            return task
    raise FrameworkRuntimeError(f"Scheduler task not found: {task_id}")


def scheduler_request_payload(root: Path, workspace_id: str, run_id: str, goal_id: str, trigger: str = "manual", max_retries: int = 1, reset: bool = False) -> dict[str, Any]:
    root = safe_root(root)
    if trigger not in {"manual", "dependency-ready", "retry", "resume"}:
        raise FrameworkRuntimeError(f"Unsupported scheduler trigger: {trigger}")
    path = scheduler_state_path(root, workspace_id, run_id, goal_id)
    if path.exists() and not reset:
        state = read_runtime_json_child(path.parent, path)
        created = False
    else:
        state = initial_scheduler_state(root, workspace_id, run_id, goal_id, trigger, max_retries)
        write_scheduler_state(root, workspace_id, run_id, goal_id, state)
        append_runtime_event(root, workspace_id, run_id, "scheduler.requested", LOCAL_EXECUTION_LOOP_NAME)
        created = True
    return {
        "schema_version": 1,
        "kind": "agentoffice.framework_runtime_scheduler_request",
        "workspace_id": workspace_id,
        "run_id": run_id,
        "goal_id": goal_id,
        "created": created,
        "scheduler": state,
        "local_static": True,
        "provider_calls": False,
        "network_calls": False,
        "env_reads": False,
        "external_worker_calls": False,
    }


def scheduler_status_payload(root: Path, workspace_id: str, run_id: str, goal_id: str) -> dict[str, Any]:
    root = safe_root(root)
    path = scheduler_state_path(root, workspace_id, run_id, goal_id)
    if path.exists():
        state = read_runtime_json_child(path.parent, path)
        persisted = True
    else:
        state = initial_scheduler_state(root, workspace_id, run_id, goal_id, "manual", 1)
        persisted = False
    refresh_scheduler_counts(state, append_transitions=persisted)
    return {
        "schema_version": 1,
        "kind": "agentoffice.framework_runtime_scheduler_status",
        "workspace_id": workspace_id,
        "run_id": run_id,
        "goal_id": goal_id,
        "persisted": persisted,
        "scheduler": state,
        "local_static": True,
        "provider_calls": False,
        "network_calls": False,
        "env_reads": False,
        "external_worker_calls": False,
    }


def scheduler_dependency_ready(task: dict[str, Any], state: dict[str, Any]) -> tuple[bool, list[str]]:
    by_task_id = {item["task_id"]: item for item in state.get("tasks", [])}
    reasons: list[str] = []
    for dependency in task.get("depends_on", []):
        dependency_task = by_task_id.get(str(dependency))
        if dependency_task is None:
            reasons.append(f"unknown_dependency:{dependency}")
        elif dependency_task.get("status") != "completed":
            reasons.append(f"dependency_not_completed:{dependency}")
    return not reasons, reasons


def has_scheduler_task_status_block(task: dict[str, Any]) -> bool:
    return any(str(reason).startswith(("task_status:", "task_terminal:")) for reason in task.get("blocked_reasons", []))


def refresh_scheduler_eligibility(state: dict[str, Any]) -> None:
    for task in state.get("tasks", []):
        status = str(task.get("status", ""))
        if status in {"paused", "waiting_result", "selected", "dispatched"} | TERMINAL_SCHEDULER_TASK_STATUSES:
            continue
        if has_scheduler_task_status_block(task):
            if status != "blocked":
                append_scheduler_task_transition(task, "block", "blocked", ";".join(str(reason) for reason in task.get("blocked_reasons", [])))
            continue
        ready, reasons = scheduler_dependency_ready(task, state)
        if ready and status == "blocked":
            task["blocked_reasons"] = []
            append_scheduler_task_transition(task, "dependency-ready", "pending", "scheduler dependencies satisfied")
        elif not ready and status in {"pending", "retry_scheduled", "blocked"}:
            task["blocked_reasons"] = reasons
            if status != "blocked":
                append_scheduler_task_transition(task, "block", "blocked", ";".join(reasons))


def scheduler_next_task(state: dict[str, Any]) -> dict[str, Any] | None:
    refresh_scheduler_eligibility(state)
    candidates = [
        task for task in state.get("tasks", [])
        if task.get("status") in {"pending", "retry_scheduled"} and not task.get("blocked_reasons")
    ]
    candidates.sort(key=lambda item: (-int(item.get("priority", 0)), int(item.get("sequence", 0)), str(item.get("task_id", ""))))
    return candidates[0] if candidates else None


def scheduler_run_payload(root: Path, workspace_id: str, run_id: str, goal_id: str, capability_id: str = LOCAL_EXECUTION_CAPABILITY_ID) -> dict[str, Any]:
    root = safe_root(root)
    state = read_scheduler_state(root, workspace_id, run_id, goal_id)
    if state.get("status") in {"completed", "failed", "paused"}:
        return {
            "schema_version": 1,
            "kind": "agentoffice.framework_runtime_scheduler_run",
            "workspace_id": workspace_id,
            "run_id": run_id,
            "goal_id": goal_id,
            "progressed": False,
            "reason": f"scheduler already {state.get('status')}",
            "scheduler": state,
            "dispatch": None,
            "local_static": True,
            "provider_calls": False,
            "network_calls": False,
            "env_reads": False,
            "external_worker_calls": False,
        }
    task = scheduler_next_task(state)
    if task is None:
        write_scheduler_state(root, workspace_id, run_id, goal_id, state)
        return {
            "schema_version": 1,
            "kind": "agentoffice.framework_runtime_scheduler_run",
            "workspace_id": workspace_id,
            "run_id": run_id,
            "goal_id": goal_id,
            "progressed": False,
            "reason": "no eligible scheduler task",
            "scheduler": state,
            "dispatch": None,
            "local_static": True,
            "provider_calls": False,
            "network_calls": False,
            "env_reads": False,
            "external_worker_calls": False,
        }
    if state.get("status") == "pending":
        append_scheduler_transition(state, "start", "selected", "scheduler selected first task")
    task_id = str(task["task_id"])
    retry_suffix = f"-r{int(task.get('retry_count', 0))}" if int(task.get("retry_count", 0)) else ""
    job_id = f"sched-{goal_id}-{task_id}{retry_suffix}"
    append_scheduler_task_transition(task, "select", "selected", "scheduler selected task by priority")
    decision = write_policy_decision(
        root,
        workspace_id,
        run_id,
        job_id,
        policy_decision_payload(
            capability_id,
            LOCAL_EXECUTION_LOOP_NAME,
            "dispatch",
            {"workspace_id": workspace_id, "run_id": run_id, "goal_id": goal_id, "task_id": task_id, "job_id": job_id, "scheduler_id": str(state["scheduler_id"])},
        ),
    )
    if not decision["allowed"]:
        job = fail_job_for_policy_denial(root, workspace_id, run_id, goal_id, job_id, task_id, str(task["title"]), {"execution_id": state["scheduler_id"], "cursor": task["sequence"]}, decision)
        append_scheduler_task_transition(task, "policy_denied", "failed", str(decision["reason"]))
        append_scheduler_transition(state, "policy_denied", "blocked", str(decision["reason"]))
        write_scheduler_state(root, workspace_id, run_id, goal_id, state)
        append_runtime_event(root, workspace_id, run_id, "scheduler.policy_denied", LOCAL_EXECUTION_LOOP_NAME)
        return {
            "schema_version": 1,
            "kind": "agentoffice.framework_runtime_scheduler_run",
            "workspace_id": workspace_id,
            "run_id": run_id,
            "goal_id": goal_id,
            "progressed": False,
            "reason": str(decision["reason"]),
            "scheduler": state,
            "dispatch": task,
            "job": job,
            "policy_decision": decision,
            "worker_assignment": None,
            "local_static": True,
            "provider_calls": False,
            "network_calls": False,
            "env_reads": False,
            "external_worker_calls": False,
        }
    if job_path(root, workspace_id, run_id, job_id).exists():
        job = read_job_payload(root, workspace_id, run_id, job_id)
        metadata = job.get("metadata", {}) if isinstance(job.get("metadata"), dict) else {}
        if str(metadata.get("goal_id", "")) != goal_id or str(metadata.get("task_id", "")) != task_id:
            raise FrameworkRuntimeError(f"Scheduler job id collision for goal/task: {job_id}")
    else:
        job = create_job_payload(
            root,
            workspace_id,
            run_id,
            job_id,
            f"scheduler task {task_id}: {task['title']}",
            {
                "scheduler_id": str(state["scheduler_id"]),
                "goal_id": goal_id,
                "task_id": task_id,
                "priority": str(task["priority"]),
                "retry_count": str(task.get("retry_count", 0)),
                "capability_id": str(decision["capability_id"]),
            },
            [task_graph_ref(workspace_id, goal_id), scheduler_state_ref(workspace_id, run_id, goal_id), policy_decision_ref(workspace_id, run_id, job_id)],
        )
    worker_assignment = {
        "worker": LOCAL_EXECUTION_LOOP_NAME,
        "adapter_id": LOCAL_WORKER_ADAPTER_ID,
        "capability_id": str(decision["capability_id"]),
        "capability_allowed": True,
        "assignment_mode": "local_static_capability_boundary",
        "provider_calls": False,
        "network_calls": False,
        "external_worker_calls": False,
    }
    task["job_id"] = job_id
    task["job_ref"] = orchestration_job_ref(workspace_id, run_id, job_id)
    task["worker_assignment"] = worker_assignment
    append_scheduler_task_transition(task, "dispatch", "dispatched", "scheduler created local framework-runtime job")
    append_scheduler_task_transition(task, "wait", "waiting_result", "scheduler waiting for deterministic worker result intake")
    state["selected_task_id"] = task_id
    state["evidence_refs"] = normalize_evidence_refs(list(state.get("evidence_refs", [])) + [orchestration_job_ref(workspace_id, run_id, job_id), policy_decision_ref(workspace_id, run_id, job_id)])
    append_scheduler_transition(state, "dispatch", "waiting_result", f"scheduler dispatched task {task_id}")
    write_scheduler_state(root, workspace_id, run_id, goal_id, state)
    append_runtime_event(root, workspace_id, run_id, "scheduler.task_dispatched", LOCAL_EXECUTION_LOOP_NAME)
    return {
        "schema_version": 1,
        "kind": "agentoffice.framework_runtime_scheduler_run",
        "workspace_id": workspace_id,
        "run_id": run_id,
        "goal_id": goal_id,
        "progressed": True,
        "reason": "scheduler dispatched one task",
        "scheduler": state,
        "dispatch": task,
        "job": job,
        "policy_decision": decision,
        "worker_assignment": worker_assignment,
        "local_static": True,
        "provider_calls": False,
        "network_calls": False,
        "env_reads": False,
        "external_worker_calls": False,
    }


def scheduler_pause_payload(root: Path, workspace_id: str, run_id: str, goal_id: str, task_id: str | None = None) -> dict[str, Any]:
    root = safe_root(root)
    state = read_scheduler_state(root, workspace_id, run_id, goal_id)
    targets = [scheduler_task_by_id(state, task_id)] if task_id else [task for task in state.get("tasks", []) if task.get("status") not in TERMINAL_SCHEDULER_TASK_STATUSES]
    for task in targets:
        if task.get("status") != "paused":
            task["previous_status"] = task.get("status")
            append_scheduler_task_transition(task, "pause", "paused", "operator paused scheduler task")
    if task_id:
        append_scheduler_transition(state, "pause-task", "pending", f"operator paused scheduler task {task_id}")
    else:
        append_scheduler_transition(state, "pause", "paused", "operator paused scheduler")
    write_scheduler_state(root, workspace_id, run_id, goal_id, state)
    append_runtime_event(root, workspace_id, run_id, "scheduler.paused", LOCAL_EXECUTION_LOOP_NAME)
    return {"schema_version": 1, "kind": "agentoffice.framework_runtime_scheduler_pause", "workspace_id": workspace_id, "run_id": run_id, "goal_id": goal_id, "scheduler": state, "local_static": True, "provider_calls": False, "network_calls": False, "env_reads": False, "external_worker_calls": False}


def scheduler_resume_payload(root: Path, workspace_id: str, run_id: str, goal_id: str, task_id: str | None = None) -> dict[str, Any]:
    root = safe_root(root)
    state = read_scheduler_state(root, workspace_id, run_id, goal_id)
    targets = [scheduler_task_by_id(state, task_id)] if task_id else [task for task in state.get("tasks", []) if task.get("status") == "paused"]
    for task in targets:
        if task.get("status") == "paused":
            task.pop("previous_status", None)
            append_scheduler_task_transition(task, "resume", "pending", "operator resumed scheduler task")
    append_scheduler_transition(state, "resume", "pending", "operator resumed scheduler")
    refresh_scheduler_eligibility(state)
    write_scheduler_state(root, workspace_id, run_id, goal_id, state)
    append_runtime_event(root, workspace_id, run_id, "scheduler.resumed", LOCAL_EXECUTION_LOOP_NAME)
    return {"schema_version": 1, "kind": "agentoffice.framework_runtime_scheduler_resume", "workspace_id": workspace_id, "run_id": run_id, "goal_id": goal_id, "scheduler": state, "local_static": True, "provider_calls": False, "network_calls": False, "env_reads": False, "external_worker_calls": False}


def scheduler_retry_payload(root: Path, workspace_id: str, run_id: str, goal_id: str, task_id: str) -> dict[str, Any]:
    root = safe_root(root)
    state = read_scheduler_state(root, workspace_id, run_id, goal_id)
    task = scheduler_task_by_id(state, task_id)
    retry_count = int(task.get("retry_count", 0))
    max_retries = int(task.get("max_retries", 0))
    if task.get("status") != "failed":
        raise FrameworkRuntimeError(f"Scheduler task is not failed and cannot be retried: {task_id}")
    if retry_count >= max_retries:
        refresh_scheduler_counts(state)
        return {"schema_version": 1, "kind": "agentoffice.framework_runtime_scheduler_retry", "workspace_id": workspace_id, "run_id": run_id, "goal_id": goal_id, "task": task, "scheduler": state, "local_static": True, "provider_calls": False, "network_calls": False, "env_reads": False, "external_worker_calls": False}
    task["retry_count"] = retry_count + 1
    task["job_id"] = None
    task["job_ref"] = None
    task["worker_assignment"] = None
    task["worker_result_ref"] = None
    append_scheduler_task_transition(task, "retry", "retry_scheduled", "scheduler retry scheduled")
    append_scheduler_transition(state, "retry", "retry_scheduled", f"scheduler retry scheduled for task {task_id}")
    write_scheduler_state(root, workspace_id, run_id, goal_id, state)
    append_runtime_event(root, workspace_id, run_id, "scheduler.retry", LOCAL_EXECUTION_LOOP_NAME)
    return {"schema_version": 1, "kind": "agentoffice.framework_runtime_scheduler_retry", "workspace_id": workspace_id, "run_id": run_id, "goal_id": goal_id, "task": task, "scheduler": state, "local_static": True, "provider_calls": False, "network_calls": False, "env_reads": False, "external_worker_calls": False}


def scheduler_result_intake_payload(root: Path, workspace_id: str, run_id: str, goal_id: str, task_id: str, status: str, summary: str) -> dict[str, Any]:
    root = safe_root(root)
    state = read_scheduler_state(root, workspace_id, run_id, goal_id)
    task = scheduler_task_by_id(state, task_id)
    if task.get("status") != "waiting_result":
        raise FrameworkRuntimeError(f"Scheduler task is not waiting for result: {task_id}")
    job_id = str(task.get("job_id") or "")
    if not job_id:
        raise FrameworkRuntimeError(f"Scheduler task has no job: {task_id}")
    intake = intake_worker_result_payload(root, workspace_id, run_id, job_id, LOCAL_WORKER_ADAPTER_ID, status, summary, [scheduler_state_ref(workspace_id, run_id, goal_id)])
    if status == "succeeded":
        set_task_status(root, workspace_id, run_id, goal_id, task_id, "accepted")
        append_scheduler_task_transition(task, "result-intake", "completed", "scheduler result succeeded")
        append_runtime_event(root, workspace_id, run_id, "scheduler.task_completed", LOCAL_EXECUTION_LOOP_NAME)
    else:
        append_scheduler_task_transition(task, "result-intake", "failed", "scheduler result failed")
        append_runtime_event(root, workspace_id, run_id, "scheduler.task_failed", LOCAL_EXECUTION_LOOP_NAME)
    task["worker_result_ref"] = worker_result_ref(workspace_id, run_id, job_id)
    state["evidence_refs"] = normalize_evidence_refs(list(state.get("evidence_refs", [])) + [worker_result_ref(workspace_id, run_id, job_id), executor_event_log_ref(workspace_id, run_id)])
    append_scheduler_transition(state, "result-intake", "pending", f"scheduler intook result for task {task_id}")
    refresh_scheduler_eligibility(state)
    write_scheduler_state(root, workspace_id, run_id, goal_id, state)
    return {"schema_version": 1, "kind": "agentoffice.framework_runtime_scheduler_result_intake", "workspace_id": workspace_id, "run_id": run_id, "goal_id": goal_id, "task": task, "scheduler": state, "job": intake["job"], "worker_result": intake["worker_result"], "local_static": True, "provider_calls": False, "network_calls": False, "env_reads": False, "external_worker_calls": False}

def job_error_payload(message: str, action: str | None = None) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "agentoffice.framework_runtime_job_error",
        "action": action,
        "error": message,
        "local_static": True,
        "provider_calls": False,
    }


def dispatch_payload(root: Path, workspace_id: str, run_id: str, goal_id: str, task_id: str | None = None) -> dict[str, Any]:
    root = safe_root(root)
    ensure_runtime_run(root, workspace_id, run_id)
    graph = load_runtime_graph(root, workspace_id, goal_id)
    ready = compute_ready_tasks(graph)["ready_tasks"]
    if task_id is not None:
        task_id = validate_runtime_id(task_id, "task_id")
        selected = next((task for task in ready if task["task_id"] == task_id), None)
        if selected is None:
            raise FrameworkRuntimeError(f"Task is not ready for dispatch: {task_id}")
    else:
        selected = ready[0] if ready else None
    if selected is None:
        raise FrameworkRuntimeError(f"No ready task for run: {workspace_id}/{run_id}/{goal_id}")

    append_runtime_event(root, workspace_id, run_id, "runtime.dispatch_started", "runtime")
    packet = runtime_packet(root, workspace_id, run_id, goal_id, selected)
    result = runtime_actor_result(root, workspace_id, run_id, packet)
    task = set_task_status(root, workspace_id, run_id, goal_id, str(selected["task_id"]), "result_received")
    append_runtime_event(root, workspace_id, run_id, "runtime.dispatch_completed", "runtime")
    return {
        "schema_version": 1,
        "kind": "agentoffice.framework_runtime_dispatch",
        "workspace_id": workspace_id,
        "run_id": run_id,
        "goal_id": goal_id,
        "task_id": selected["task_id"],
        "packet": packet,
        "actor_result": result,
        "task": task,
        "worker_adapter": LOCAL_WORKER_NAME,
        "local_stub": True,
        "provider_calls": False,
        "network_calls": False,
        "env_reads": False,
    }


def review_payload(root: Path, workspace_id: str, run_id: str, goal_id: str, result_id: str) -> dict[str, Any]:
    root = safe_root(root)
    result_id = validate_runtime_id(result_id, "result_id")
    try:
        result = read_actor_result(root, workspace_id, run_id, result_id)
    except PacketResultError as exc:
        raise FrameworkRuntimeError(str(exc)) from exc
    task_id = validate_runtime_id(str(result["task_id"]), "task_id")
    review_id = review_id_for_task(task_id)
    target = reviews_dir(root, workspace_id, run_id) / f"{review_id}.json"
    if target.exists():
        review = read_review(root, workspace_id, run_id, review_id)
    else:
        verdict = "pass" if result.get("status") == "completed" else "fail"
        review = {
            "schema_version": 1,
            "kind": "agentoffice.framework_runtime_review",
            "review_id": review_id,
            "workspace_id": workspace_id,
            "run_id": run_id,
            "goal_id": goal_id,
            "task_id": task_id,
            "result_id": result_id,
            "reviewer": REVIEW_STUB_NAME,
            "verdict": verdict,
            "summary": f"local stub review {verdict} for {result_id}",
            "local_stub": True,
            "provider_calls": False,
            "network_calls": False,
            "env_reads": False,
        }
        write_json_atomic(target, review)
        append_runtime_event(root, workspace_id, run_id, "review.stub_completed", REVIEW_STUB_NAME)
    task = set_task_status(root, workspace_id, run_id, goal_id, task_id, "reviewed")
    return {
        "schema_version": 1,
        "kind": "agentoffice.framework_runtime_review_intake",
        "workspace_id": workspace_id,
        "run_id": run_id,
        "goal_id": goal_id,
        "task_id": task_id,
        "review": review,
        "task": task,
        "local_stub": True,
        "provider_calls": False,
    }


def judge_payload(root: Path, workspace_id: str, run_id: str, goal_id: str, review_id: str) -> dict[str, Any]:
    root = safe_root(root)
    review = read_review(root, workspace_id, run_id, review_id)
    task_id = validate_runtime_id(str(review["task_id"]), "task_id")
    judge_id = judge_id_for_task(task_id)
    target = judges_dir(root, workspace_id, run_id) / f"{judge_id}.json"
    if target.exists():
        judge = read_judge(root, workspace_id, run_id, judge_id)
    else:
        decision = "accepted" if review.get("verdict") == "pass" else "rejected"
        judge = {
            "schema_version": 1,
            "kind": "agentoffice.framework_runtime_judge",
            "judge_id": judge_id,
            "workspace_id": workspace_id,
            "run_id": run_id,
            "goal_id": goal_id,
            "task_id": task_id,
            "review_id": review_id,
            "judge": JUDGE_STUB_NAME,
            "decision": decision,
            "summary": f"local stub judge {decision} for {review_id}",
            "local_stub": True,
            "provider_calls": False,
            "network_calls": False,
            "env_reads": False,
        }
        write_json_atomic(target, judge)
        append_runtime_event(root, workspace_id, run_id, "judge.stub_completed", JUDGE_STUB_NAME)
    task = set_task_status(root, workspace_id, run_id, goal_id, task_id, str(judge["decision"]))
    return {
        "schema_version": 1,
        "kind": "agentoffice.framework_runtime_judge_intake",
        "workspace_id": workspace_id,
        "run_id": run_id,
        "goal_id": goal_id,
        "task_id": task_id,
        "judge": judge,
        "task": task,
        "local_stub": True,
        "provider_calls": False,
    }


def run_status_payload(root: Path, workspace_id: str, run_id: str, goal_id: str) -> dict[str, Any]:
    root = safe_root(root)
    ensure_runtime_run(root, workspace_id, run_id)
    graph = load_runtime_graph(root, workspace_id, goal_id)
    run_root = run_dir(root, workspace_id, run_id)
    try:
        events = list_events(root, workspace_id, run_id)
    except RuntimeEventLogError as exc:
        raise FrameworkRuntimeError(str(exc)) from exc
    tasks = list(graph.get("tasks", []))
    incomplete = [task for task in tasks if task.get("status") not in TERMINAL_TASK_STATUSES]
    return {
        "schema_version": 1,
        "kind": "agentoffice.framework_runtime_status",
        "workspace_id": workspace_id,
        "run_id": run_id,
        "goal_id": goal_id,
        "local_stub": True,
        "provider_calls": False,
        "network_calls": False,
        "env_reads": False,
        "tasks": tasks,
        "incomplete_tasks": incomplete,
        "packets": list_json_objects(run_root / "packets"),
        "actor_results": list_json_objects(run_root / "results"),
        "reviews": list_json_objects(run_root / "reviews"),
        "judges": list_json_objects(run_root / "judges"),
        "jobs": list_json_objects(run_root / "jobs"),
        "executor_results": list_json_objects(run_root / "executor_results"),
        "worker_results": list_json_objects(run_root / "worker_results"),
        "orchestrations": list_json_objects(run_root / "orchestrations"),
        "execution_loops": list_json_objects(run_root / "execution_loops"),
        "policy_decisions": list_json_objects(run_root / "policy_decisions"),
        "events": events,
        "complete": not incomplete,
    }


def list_runs_payload(root: Path, workspace_id: str) -> dict[str, Any]:
    root = safe_root(root)
    workspace_id = validate_runtime_id(workspace_id, "workspace_id")
    try:
        inspect_workspace(root, workspace_id)
    except WorkspaceStoreError as exc:
        raise FrameworkRuntimeError(str(exc)) from exc
    workspace_root = workspace_dir(root, workspace_id)
    runs_root = workspace_root / "runs"
    goals_root = workspace_root / "goals"
    rows: list[dict[str, Any]] = []
    for run_path in sorted(runs_root.glob("*")) if runs_root.exists() else []:
        if not run_path.is_dir():
            continue
        run_id = validate_runtime_id(run_path.name, "run_id")
        if not (run_path / "run.json").exists():
            continue
        for graph_path in sorted(goals_root.glob("*/task_graph.json")) if goals_root.exists() else []:
            goal_id = validate_runtime_id(graph_path.parent.name, "goal_id")
            status = run_status_payload(root, workspace_id, run_id, goal_id)
            rows.append(
                {
                    "workspace_id": workspace_id,
                    "run_id": run_id,
                    "goal_id": goal_id,
                    "complete": status["complete"],
                    "incomplete_task_ids": [task["task_id"] for task in status["incomplete_tasks"]],
                    "event_count": len(status["events"]),
                }
            )
    return {
        "schema_version": 1,
        "kind": "agentoffice.framework_runtime_run_list",
        "workspace_id": workspace_id,
        "runs": rows,
        "incomplete_runs": [row for row in rows if not row["complete"]],
    }


def inspect_payload(root: Path, workspace_id: str, run_id: str, goal_id: str, task_id: str | None = None) -> dict[str, Any]:
    status = run_status_payload(root, workspace_id, run_id, goal_id)
    if task_id is None:
        return {
            "schema_version": 1,
            "kind": "agentoffice.framework_runtime_inspect",
            "workspace_id": workspace_id,
            "run_id": run_id,
            "goal_id": goal_id,
            "status": status,
        }
    task_id = validate_runtime_id(task_id, "task_id")
    task = next((item for item in status["tasks"] if item["task_id"] == task_id), None)
    if task is None:
        raise FrameworkRuntimeError(f"Task not found in task graph: {task_id}")
    packet_id = packet_id_for_task(task_id)
    result_id = result_id_for_task(task_id)
    review_id = review_id_for_task(task_id)
    judge_id = judge_id_for_task(task_id)
    return {
        "schema_version": 1,
        "kind": "agentoffice.framework_runtime_inspect",
        "workspace_id": workspace_id,
        "run_id": run_id,
        "goal_id": goal_id,
        "task_id": task_id,
        "task": task,
        "packet": next((item for item in status["packets"] if item.get("packet_id") == packet_id), None),
        "actor_result": next((item for item in status["actor_results"] if item.get("result_id") == result_id), None),
        "review": next((item for item in status["reviews"] if item.get("review_id") == review_id), None),
        "judge": next((item for item in status["judges"] if item.get("judge_id") == judge_id), None),
    }


def resume_payload(root: Path, workspace_id: str, run_id: str, goal_id: str) -> dict[str, Any]:
    root = safe_root(root)
    actions: list[dict[str, Any]] = []
    for _ in range(100):
        status = run_status_payload(root, workspace_id, run_id, goal_id)
        if status["complete"]:
            break
        progressed = False
        for task in status["tasks"]:
            task_id = str(task["task_id"])
            task_status = str(task.get("status", "created"))
            if task_status == "result_received":
                actions.append(review_payload(root, workspace_id, run_id, goal_id, result_id_for_task(task_id)))
                progressed = True
                break
            if task_status == "reviewed":
                actions.append(judge_payload(root, workspace_id, run_id, goal_id, review_id_for_task(task_id)))
                progressed = True
                break
        if progressed:
            continue
        ready = compute_ready_tasks(load_runtime_graph(root, workspace_id, goal_id))["ready_tasks"]
        if ready:
            actions.append(dispatch_payload(root, workspace_id, run_id, goal_id, str(ready[0]["task_id"])))
            continue
        break
    final_status = run_status_payload(root, workspace_id, run_id, goal_id)
    return {
        "schema_version": 1,
        "kind": "agentoffice.framework_runtime_resume",
        "workspace_id": workspace_id,
        "run_id": run_id,
        "goal_id": goal_id,
        "actions": actions,
        "action_count": len(actions),
        "complete": final_status["complete"],
        "incomplete_tasks": final_status["incomplete_tasks"],
        "local_stub": True,
        "provider_calls": False,
    }


def replay_payload(root: Path, workspace_id: str, run_id: str) -> dict[str, Any]:
    root = safe_root(root)
    ensure_runtime_run(root, workspace_id, run_id)
    try:
        events = list_events(root, workspace_id, run_id)
    except RuntimeEventLogError as exc:
        raise FrameworkRuntimeError(str(exc)) from exc
    return {
        "schema_version": 1,
        "kind": "agentoffice.framework_runtime_replay",
        "workspace_id": workspace_id,
        "run_id": run_id,
        "event_count": len(events),
        "events": events,
        "replay_view": [
            {
                "event_id": event["event_id"],
                "event_type": event["event_type"],
                "actor": event["actor"],
                "task_id": event.get("task_id"),
            }
            for event in events
        ],
        "read_only": True,
    }


def evidence_payload(root: Path, workspace_id: str, run_id: str, goal_id: str, output_format: str = "json") -> dict[str, Any]:
    if output_format not in {"json", "text"}:
        raise FrameworkRuntimeError("Evidence format must be json or text.")
    status = run_status_payload(root, workspace_id, run_id, goal_id)
    replay = replay_payload(root, workspace_id, run_id)
    bundle = {
        "schema_version": 1,
        "kind": "agentoffice.framework_runtime_evidence_bundle",
        "workspace_id": workspace_id,
        "run_id": run_id,
        "goal_id": goal_id,
        "status": status,
        "replay": replay,
        "worker_contract": worker_contract_payload(),
        "capability_contract": capability_contract_payload(),
        "safety": {
            "local_stub": True,
            "provider_calls": False,
            "network_calls": False,
            "env_reads": False,
            "external_adapters": False,
        },
    }
    evidence_root = ensure_runtime_run(root, workspace_id, run_id) / "evidence"
    artifact_path = evidence_root / f"framework_runtime_evidence.{output_format}"
    if output_format == "json":
        write_json_atomic(artifact_path, bundle)
    else:
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(format_evidence_bundle_text(bundle) + "\n", encoding="utf-8")
    return {
        "schema_version": 1,
        "kind": "agentoffice.framework_runtime_evidence_export",
        "workspace_id": workspace_id,
        "run_id": run_id,
        "goal_id": goal_id,
        "format": output_format,
        "artifact_path": str(artifact_path),
        "bundle": bundle,
        "local_stub": True,
        "provider_calls": False,
    }


def format_evidence_bundle_text(bundle: dict[str, Any]) -> str:
    status = bundle["status"]
    replay = bundle["replay"]
    lines = [
        "AgentOffice Framework Runtime Evidence",
        f"workspace: {bundle['workspace_id']}",
        f"run: {bundle['run_id']}",
        f"goal: {bundle['goal_id']}",
        f"complete: {str(status['complete']).lower()}",
        f"tasks: {len(status['tasks'])}",
        f"packets: {len(status['packets'])}",
        f"actor_results: {len(status['actor_results'])}",
        f"reviews: {len(status['reviews'])}",
        f"judges: {len(status['judges'])}",
        f"jobs: {len(status['jobs'])}",
        f"executor_results: {len(status['executor_results'])}",
        f"worker_results: {len(status['worker_results'])}",
        f"orchestrations: {len(status['orchestrations'])}",
        f"execution_loops: {len(status['execution_loops'])}",
        f"policy_decisions: {len(status['policy_decisions'])}",
        f"events: {replay['event_count']}",
        "local stub / no external provider: true",
    ]
    return "\n".join(lines)


def format_framework_runtime_payload(payload: dict[str, Any]) -> str:
    kind = payload.get("kind")
    if kind == "agentoffice.framework_runtime_capability_contract":
        return "\n".join(
            f"capability {item['capability_id']} worker={item['worker']} action={item['action']} status={item['status']} allowed={str(item['allowed']).lower()}"
            for item in payload["capabilities"]
        )
    if kind == "agentoffice.framework_runtime_policy_check":
        decision = payload["decision"]
        return f"policy check capability={decision['capability_id']} allowed={str(decision['allowed']).lower()} code={decision['reason_code']} local_static=true"
    if kind == "agentoffice.framework_runtime_worker_contract":
        return "\n".join(
            f"worker {adapter['name']} mode={adapter['mode']} provider_calls={adapter['provider_calls']} network_calls={adapter['network_calls']}"
            for adapter in payload["adapters"]
        )
    if kind == "agentoffice.framework_runtime_dispatch":
        return (
            f"dispatch {payload['workspace_id']}/{payload['run_id']}/{payload['goal_id']} "
            f"task={payload['task_id']} worker={payload['worker_adapter']} local_stub=true no_external_provider=true"
        )
    if kind == "agentoffice.framework_runtime_review_intake":
        review = payload["review"]
        return f"review {review['review_id']} task={payload['task_id']} verdict={review['verdict']} local_stub=true no_external_provider=true"
    if kind == "agentoffice.framework_runtime_judge_intake":
        judge = payload["judge"]
        return f"judge {judge['judge_id']} task={payload['task_id']} decision={judge['decision']} local_stub=true no_external_provider=true"
    if kind == "agentoffice.framework_runtime_status":
        return (
            f"runtime {payload['workspace_id']}/{payload['run_id']}/{payload['goal_id']} "
            f"complete={str(payload['complete']).lower()} tasks={len(payload['tasks'])} "
            f"incomplete={len(payload['incomplete_tasks'])} events={len(payload['events'])} local_stub=true"
        )
    if kind == "agentoffice.framework_runtime_run_list":
        if not payload["runs"]:
            return f"runtime runs {payload['workspace_id']}: none"
        return "\n".join(
            f"runtime run {row['workspace_id']}/{row['run_id']}/{row['goal_id']} complete={str(row['complete']).lower()} incomplete={','.join(row['incomplete_task_ids']) or 'none'}"
            for row in payload["runs"]
        )
    if kind == "agentoffice.framework_runtime_inspect":
        if "task_id" in payload:
            task = payload["task"]
            return f"inspect task={payload['task_id']} status={task['status']} packet={payload['packet'] is not None} result={payload['actor_result'] is not None} review={payload['review'] is not None} judge={payload['judge'] is not None}"
        status = payload["status"]
        return f"inspect {payload['workspace_id']}/{payload['run_id']}/{payload['goal_id']} tasks={len(status['tasks'])} complete={str(status['complete']).lower()}"
    if kind == "agentoffice.framework_runtime_resume":
        return f"resume {payload['workspace_id']}/{payload['run_id']}/{payload['goal_id']} actions={payload['action_count']} complete={str(payload['complete']).lower()} local_stub=true"
    if kind == "agentoffice.framework_runtime_replay":
        return f"replay {payload['workspace_id']}/{payload['run_id']} events={payload['event_count']} read_only=true"
    if kind == "agentoffice.framework_runtime_evidence_export":
        return f"evidence {payload['workspace_id']}/{payload['run_id']}/{payload['goal_id']} format={payload['format']} path={payload['artifact_path']} local_stub=true"
    if kind == "agentoffice.framework_runtime_executor_run_once":
        if not payload["progressed"]:
            return f"executor run-once {payload['workspace_id']}/{payload['run_id']} progressed=false reason={payload['reason']} local_stub=true"
        job = payload["job"]
        return f"executor run-once {payload['workspace_id']}/{payload['run_id']} job={job['job_id']} status={job['status']} local_stub=true"
    if kind == "agentoffice.framework_runtime_executor_loop":
        return f"executor loop {payload['workspace_id']}/{payload['run_id']} actions={payload['action_count']} complete={str(payload['complete']).lower()} local_stub=true"
    if kind == "agentoffice.framework_runtime_executor_status":
        return f"executor status {payload['workspace_id']}/{payload['run_id']} jobs={payload['job_count']} pending={payload['pending_count']} running={payload['running_count']} succeeded={payload['succeeded_count']} failed={payload['failed_count']} cancelled={payload['cancelled_count']} local_stub=true"
    if kind == "agentoffice.framework_runtime_orchestration_plan":
        return f"orchestration plan {payload['workspace_id']}/{payload['run_id']}/{payload['goal_id']} dispatches={len(payload['dispatch_plan'])} valid={str(payload['valid']).lower()} local_static=true"
    if kind == "agentoffice.framework_runtime_orchestration_show":
        orchestration = payload["orchestration"]
        status = orchestration.get("status", "planned")
        return f"orchestration show {payload['workspace_id']}/{payload['run_id']}/{payload['goal_id']} persisted={str(payload['persisted']).lower()} status={status} local_static=true"
    if kind == "agentoffice.framework_runtime_orchestration_validation":
        return f"orchestration validate {payload['workspace_id']}/{payload['run_id']}/{payload['goal_id']} valid={str(payload['valid']).lower()} errors={len(payload['errors'])} dispatches={payload['dispatch_count']} local_static=true"
    if kind == "agentoffice.framework_runtime_orchestration_run_local":
        orchestration = payload["orchestration"]
        return f"orchestration run-local {payload['workspace_id']}/{payload['run_id']}/{payload['goal_id']} progressed={str(payload['progressed']).lower()} status={orchestration['status']} tasks={len(orchestration.get('tasks', []))} local_static=true"
    if kind == "agentoffice.framework_runtime_execution_loop_run_once":
        if not payload["progressed"]:
            return f"execution run-once {payload['workspace_id']}/{payload['run_id']}/{payload['goal_id']} progressed=false reason={payload['reason']} local_static=true"
        dispatch = payload["dispatch"]
        state = payload["execution_loop"]
        return f"execution run-once {payload['workspace_id']}/{payload['run_id']}/{payload['goal_id']} task={dispatch['task_id']} status={state['status']} completed={state['completed_count']}/{state['dispatch_count']} local_static=true"
    if kind == "agentoffice.framework_runtime_execution_loop":
        state = payload["status"]["execution_loop"]
        return f"execution loop {payload['workspace_id']}/{payload['run_id']}/{payload['goal_id']} actions={payload['action_count']} status={state['status']} complete={str(payload['complete']).lower()} local_static=true"
    if kind == "agentoffice.framework_runtime_execution_loop_status":
        state = payload["execution_loop"]
        return f"execution status {payload['workspace_id']}/{payload['run_id']}/{payload['goal_id']} persisted={str(payload['persisted']).lower()} status={state['status']} completed={state['completed_count']}/{state['dispatch_count']} local_static=true"
    if kind in {"agentoffice.framework_runtime_scheduler_request", "agentoffice.framework_runtime_scheduler_status", "agentoffice.framework_runtime_scheduler_pause", "agentoffice.framework_runtime_scheduler_resume"}:
        scheduler = payload["scheduler"]
        return f"scheduler {payload['workspace_id']}/{payload['run_id']}/{payload['goal_id']} status={scheduler['status']} tasks={scheduler['task_count']} completed={scheduler['completed_count']} failed={scheduler['failed_count']} blocked={scheduler['blocked_count']} local_static=true"
    if kind == "agentoffice.framework_runtime_scheduler_run":
        dispatch = payload.get("dispatch")
        task = dispatch.get("task_id") if dispatch else "none"
        return f"scheduler run {payload['workspace_id']}/{payload['run_id']}/{payload['goal_id']} progressed={str(payload['progressed']).lower()} task={task} reason={payload['reason']} local_static=true"
    if kind == "agentoffice.framework_runtime_scheduler_retry":
        task = payload["task"]
        return f"scheduler retry {payload['workspace_id']}/{payload['run_id']}/{payload['goal_id']} task={task['task_id']} status={task['status']} retry={task['retry_count']}/{task['max_retries']} local_static=true"
    if kind == "agentoffice.framework_runtime_scheduler_result_intake":
        task = payload["task"]
        return f"scheduler result-intake {payload['workspace_id']}/{payload['run_id']}/{payload['goal_id']} task={task['task_id']} status={task['status']} job={task['job_id']} local_static=true"
    if kind == "agentoffice.framework_runtime_worker_result_intake":
        result = payload["worker_result"]
        return f"worker result-intake {payload['workspace_id']}/{payload['run_id']} job={result['job_id']} status={result['status']} adapter={result['adapter_id']} local_static=true"
    if kind == "agentoffice.framework_runtime_worker_result":
        return f"worker result {payload['workspace_id']}/{payload['run_id']} job={payload['job_id']} status={payload['status']} adapter={payload['adapter_id']} local_static=true"
    if kind == "agentoffice.framework_runtime_job":
        return f"job {payload['workspace_id']}/{payload['run_id']}/{payload['job_id']} status={payload['status']} evidence_refs={len(payload['evidence_refs'])} local_static=true"
    if kind == "agentoffice.framework_runtime_job_list":
        if not payload["jobs"]:
            return f"jobs {payload['workspace_id']}/{payload['run_id']}: none"
        return "\n".join(
            f"job {job['workspace_id']}/{job['run_id']}/{job['job_id']} status={job['status']} evidence_refs={len(job['evidence_refs'])}"
            for job in payload["jobs"]
        )
    if kind == "agentoffice.framework_runtime_job_error":
        return f"job error action={payload.get('action') or 'unknown'} error={payload['error']}"
    return json.dumps(payload, indent=2, ensure_ascii=False)
