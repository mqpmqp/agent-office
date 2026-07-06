from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .runtime_events import RuntimeEventLogError, append_event, event_log_path
from .task_graph import TaskGraphError, load_task_graph
from .workspace_store import WorkspaceStoreError, inspect_workspace, read_json, run_dir, validate_store_id, write_json_atomic


FORBIDDEN_ACTIONS = [
    "read .env",
    "print env vars",
    "call provider/model/network",
    "touch trading-bot repositories",
]


class PacketResultError(ValueError):
    pass


def validate_packet_result_id(value: str, label: str) -> str:
    try:
        return validate_store_id(value, label)
    except WorkspaceStoreError as exc:
        raise PacketResultError(str(exc)) from exc


def ensure_run(root: Path, workspace_id: str, run_id: str) -> Path:
    workspace_id = validate_packet_result_id(workspace_id, "workspace_id")
    run_id = validate_packet_result_id(run_id, "run_id")
    target = run_dir(root, workspace_id, run_id)
    try:
        inspect_workspace(root, workspace_id)
    except WorkspaceStoreError as exc:
        raise PacketResultError(str(exc)) from exc
    run_metadata = target / "run.json"
    if not run_metadata.exists():
        raise PacketResultError(f"Run not found: {run_id}")
    try:
        read_json(run_metadata)
    except WorkspaceStoreError as exc:
        raise PacketResultError(str(exc)) from exc
    return target


def packets_dir(root: Path, workspace_id: str, run_id: str) -> Path:
    return ensure_run(root, workspace_id, run_id) / "packets"


def results_dir(root: Path, workspace_id: str, run_id: str) -> Path:
    return ensure_run(root, workspace_id, run_id) / "results"


def packet_id_for_task(task_id: str) -> str:
    return validate_packet_result_id(f"pkt_{task_id}", "packet_id")


def result_id_for_task(task_id: str) -> str:
    return validate_packet_result_id(f"res_{task_id}", "result_id")


def find_task(root: Path, workspace_id: str, goal_id: str, task_id: str) -> dict[str, Any]:
    task_id = validate_packet_result_id(task_id, "task_id")
    try:
        graph = load_task_graph(root, workspace_id, goal_id)
    except TaskGraphError as exc:
        raise PacketResultError(str(exc)) from exc
    for task in graph.get("tasks", []):
        if task.get("task_id") == task_id:
            return task
    raise PacketResultError(f"Task not found in task graph: {task_id}")


def packet_payload(workspace_id: str, run_id: str, goal_id: str, task: dict[str, Any]) -> dict[str, Any]:
    task_id = validate_packet_result_id(str(task["task_id"]), "task_id")
    return {
        "schema_version": 1,
        "kind": "agentoffice.packet",
        "packet_id": packet_id_for_task(task_id),
        "workspace_id": workspace_id,
        "run_id": run_id,
        "goal_id": goal_id,
        "task_id": task_id,
        "role": str(task["role"]),
        "objective": str(task["title"]),
        "allowed_files": [],
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
        "validation_commands": [],
        "expected_outputs": [],
        "evidence_requirements": [],
        "status": "emitted",
    }


def maybe_append_runtime_event(root: Path, workspace_id: str, run_id: str, event_type: str) -> None:
    if not event_log_path(root, workspace_id, run_id).exists():
        return
    try:
        append_event(root, workspace_id, run_id, event_type, "runtime")
    except RuntimeEventLogError as exc:
        raise PacketResultError(str(exc)) from exc


def emit_packet(root: Path, workspace_id: str, run_id: str, goal_id: str, task_id: str) -> dict[str, Any]:
    workspace_id = validate_packet_result_id(workspace_id, "workspace_id")
    run_id = validate_packet_result_id(run_id, "run_id")
    goal_id = validate_packet_result_id(goal_id, "goal_id")
    target_dir = ensure_run(root, workspace_id, run_id) / "packets"
    task = find_task(root, workspace_id, goal_id, task_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    payload = packet_payload(workspace_id, run_id, goal_id, task)
    target = target_dir / f"{payload['packet_id']}.json"
    if target.exists():
        raise PacketResultError(f"Packet already exists: {payload['packet_id']}")
    write_json_atomic(target, payload)
    maybe_append_runtime_event(root, workspace_id, run_id, "packet.emitted")
    return payload


def read_packet(root: Path, workspace_id: str, run_id: str, packet_id: str) -> dict[str, Any]:
    workspace_id = validate_packet_result_id(workspace_id, "workspace_id")
    run_id = validate_packet_result_id(run_id, "run_id")
    packet_id = validate_packet_result_id(packet_id, "packet_id")
    path = packets_dir(root, workspace_id, run_id) / f"{packet_id}.json"
    if not path.exists():
        raise PacketResultError(f"Packet not found: {packet_id}")
    try:
        return read_json(path)
    except WorkspaceStoreError as exc:
        raise PacketResultError(str(exc)) from exc


def list_packets(root: Path, workspace_id: str, run_id: str) -> list[dict[str, Any]]:
    target = packets_dir(root, workspace_id, run_id)
    target.mkdir(parents=True, exist_ok=True)
    packets: list[dict[str, Any]] = []
    for path in sorted(target.glob("*.json")):
        try:
            packets.append(read_json(path))
        except WorkspaceStoreError as exc:
            raise PacketResultError(str(exc)) from exc
    return packets


def list_packets_payload(root: Path, workspace_id: str, run_id: str) -> dict[str, Any]:
    workspace_id = validate_packet_result_id(workspace_id, "workspace_id")
    run_id = validate_packet_result_id(run_id, "run_id")
    return {
        "schema_version": 1,
        "kind": "agentoffice.packet_list",
        "workspace_id": workspace_id,
        "run_id": run_id,
        "packets": list_packets(root, workspace_id, run_id),
    }


def actor_result_payload(packet: dict[str, Any], actor: str, status: str, summary: str) -> dict[str, Any]:
    actor = validate_packet_result_id(actor, "actor")
    status = validate_packet_result_id(status, "status")
    task_id = validate_packet_result_id(str(packet["task_id"]), "task_id")
    return {
        "schema_version": 1,
        "kind": "agentoffice.actor_result",
        "result_id": result_id_for_task(task_id),
        "packet_id": str(packet["packet_id"]),
        "workspace_id": str(packet["workspace_id"]),
        "run_id": str(packet["run_id"]),
        "goal_id": str(packet["goal_id"]),
        "task_id": task_id,
        "actor": actor,
        "status": status,
        "changed_files": [],
        "validation_commands": [],
        "validation_results": [],
        "evidence_refs": [],
        "summary": summary,
        "blockers": [],
    }


def intake_actor_result(
    root: Path,
    workspace_id: str,
    run_id: str,
    packet_id: str,
    actor: str,
    status: str,
    summary: str,
) -> dict[str, Any]:
    packet = read_packet(root, workspace_id, run_id, packet_id)
    target_dir = results_dir(root, workspace_id, run_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    payload = actor_result_payload(packet, actor, status, summary)
    target = target_dir / f"{payload['result_id']}.json"
    if target.exists():
        raise PacketResultError(f"Actor result already exists: {payload['result_id']}")
    write_json_atomic(target, payload)
    maybe_append_runtime_event(root, workspace_id, run_id, "actor_result.received")
    return payload


def read_actor_result(root: Path, workspace_id: str, run_id: str, result_id: str) -> dict[str, Any]:
    workspace_id = validate_packet_result_id(workspace_id, "workspace_id")
    run_id = validate_packet_result_id(run_id, "run_id")
    result_id = validate_packet_result_id(result_id, "result_id")
    path = results_dir(root, workspace_id, run_id) / f"{result_id}.json"
    if not path.exists():
        raise PacketResultError(f"Actor result not found: {result_id}")
    try:
        return read_json(path)
    except WorkspaceStoreError as exc:
        raise PacketResultError(str(exc)) from exc


def list_actor_results(root: Path, workspace_id: str, run_id: str) -> list[dict[str, Any]]:
    target = results_dir(root, workspace_id, run_id)
    target.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    for path in sorted(target.glob("*.json")):
        try:
            results.append(read_json(path))
        except WorkspaceStoreError as exc:
            raise PacketResultError(str(exc)) from exc
    return results


def list_actor_results_payload(root: Path, workspace_id: str, run_id: str) -> dict[str, Any]:
    workspace_id = validate_packet_result_id(workspace_id, "workspace_id")
    run_id = validate_packet_result_id(run_id, "run_id")
    return {
        "schema_version": 1,
        "kind": "agentoffice.actor_result_list",
        "workspace_id": workspace_id,
        "run_id": run_id,
        "results": list_actor_results(root, workspace_id, run_id),
    }


def format_packet_result_payload(payload: dict[str, Any]) -> str:
    if payload.get("kind") == "agentoffice.packet":
        return f"packet {payload['packet_id']} task={payload['task_id']} status={payload['status']}"
    if payload.get("kind") == "agentoffice.packet_list":
        packets = payload.get("packets", [])
        if not packets:
            return f"packets {payload['workspace_id']}/{payload['run_id']}: none"
        return "\n".join(f"packet {packet['packet_id']} task={packet['task_id']} status={packet['status']}" for packet in packets)
    return json.dumps(payload, indent=2, ensure_ascii=False)


def format_actor_result_payload(payload: dict[str, Any]) -> str:
    if payload.get("kind") == "agentoffice.actor_result":
        return f"actor result {payload['result_id']} packet={payload['packet_id']} status={payload['status']}"
    if payload.get("kind") == "agentoffice.actor_result_list":
        results = payload.get("results", [])
        if not results:
            return f"actor results {payload['workspace_id']}/{payload['run_id']}: none"
        return "\n".join(
            f"actor result {result['result_id']} packet={result['packet_id']} status={result['status']}"
            for result in results
        )
    return json.dumps(payload, indent=2, ensure_ascii=False)
