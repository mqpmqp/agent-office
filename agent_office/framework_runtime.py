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
LOCAL_WORKER_NAME = "local_echo_worker"
REVIEW_STUB_NAME = "local_review_stub"
JUDGE_STUB_NAME = "local_judge_stub"


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
        ],
    }


def worker_contract_payload() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "agentoffice.framework_runtime_worker_contract",
        "adapters": [
            {
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
        ],
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


def list_json_objects(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    items: list[dict[str, Any]] = []
    for child in sorted(path.glob("*.json")):
        try:
            items.append(read_json(child))
        except WorkspaceStoreError as exc:
            raise FrameworkRuntimeError(str(exc)) from exc
    return items


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
        f"events: {replay['event_count']}",
        "local stub / no external provider: true",
    ]
    return "\n".join(lines)


def format_framework_runtime_payload(payload: dict[str, Any]) -> str:
    kind = payload.get("kind")
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
    return json.dumps(payload, indent=2, ensure_ascii=False)
