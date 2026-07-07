from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .workspace_store import (
    WorkspaceStoreError,
    inspect_workspace,
    read_json,
    validate_store_id,
    workspace_dir,
    write_json_atomic,
)


class TaskGraphError(ValueError):
    pass


def validate_graph_id(value: str, label: str) -> str:
    try:
        return validate_store_id(value, label)
    except WorkspaceStoreError as exc:
        raise TaskGraphError(str(exc)) from exc


def goal_dir(root: Path, workspace_id: str, goal_id: str) -> Path:
    return workspace_dir(root, workspace_id) / "goals" / validate_graph_id(goal_id, "goal_id")


def goal_payload(workspace_id: str, goal_id: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "agentoffice.goal",
        "workspace_id": workspace_id,
        "goal_id": goal_id,
        "status": "created",
        "task_graph_file": "task_graph.json",
    }


def default_tasks() -> list[dict[str, Any]]:
    return [
        {
            "task_id": "task-a",
            "title": "Task A",
            "status": "created",
            "depends_on": [],
            "role": "implementation_agent",
            "required_evidence": [],
        },
        {
            "task_id": "task-b",
            "title": "Task B",
            "status": "created",
            "depends_on": ["task-a"],
            "role": "review_agent",
            "required_evidence": [],
        },
    ]


def normalize_tasks(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for task in tasks:
        task_id = validate_graph_id(str(task.get("task_id", "")), "task_id")
        if task_id in seen:
            raise TaskGraphError(f"Duplicate task_id: {task_id}")
        seen.add(task_id)
        depends_on = task.get("depends_on", [])
        if not isinstance(depends_on, list):
            raise TaskGraphError(f"Task {task_id} depends_on must be a list")
        dependencies = [validate_graph_id(str(dep), "task_id") for dep in depends_on]
        required_evidence = task.get("required_evidence", [])
        if not isinstance(required_evidence, list):
            raise TaskGraphError(f"Task {task_id} required_evidence must be a list")
        normalized_task = {
            "task_id": task_id,
            "title": str(task.get("title", task_id)),
            "status": str(task.get("status", "created")),
            "depends_on": dependencies,
            "role": str(task.get("role", "implementation_agent")),
            "required_evidence": list(required_evidence),
        }
        if "priority" in task:
            try:
                normalized_task["priority"] = int(task["priority"])
            except (TypeError, ValueError) as exc:
                raise TaskGraphError(f"Task {task_id} priority must be an integer") from exc
        normalized.append(normalized_task)
    return normalized


def task_graph_payload(workspace_id: str, goal_id: str, tasks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "agentoffice.task_graph",
        "workspace_id": workspace_id,
        "goal_id": goal_id,
        "tasks": normalize_tasks(tasks),
    }


def create_goal_graph(
    root: Path,
    workspace_id: str,
    goal_id: str,
    tasks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    workspace_id = validate_graph_id(workspace_id, "workspace_id")
    goal_id = validate_graph_id(goal_id, "goal_id")
    try:
        inspect_workspace(root, workspace_id)
    except WorkspaceStoreError as exc:
        raise TaskGraphError(str(exc)) from exc

    target = goal_dir(root, workspace_id, goal_id)
    if target.exists():
        raise TaskGraphError(f"Goal already exists: {goal_id}")
    target.mkdir(parents=True, exist_ok=False)

    goal = goal_payload(workspace_id, goal_id)
    graph = task_graph_payload(workspace_id, goal_id, default_tasks() if tasks is None else tasks)
    write_json_atomic(target / "goal.json", goal)
    write_json_atomic(target / "task_graph.json", graph)
    return {
        "schema_version": 1,
        "kind": "agentoffice.task_graph_create",
        "workspace_id": workspace_id,
        "goal_id": goal_id,
        "goal": goal,
        "task_graph": graph,
    }


def load_task_graph(root: Path, workspace_id: str, goal_id: str) -> dict[str, Any]:
    workspace_id = validate_graph_id(workspace_id, "workspace_id")
    goal_id = validate_graph_id(goal_id, "goal_id")
    target = goal_dir(root, workspace_id, goal_id)
    graph_path = target / "task_graph.json"
    if not graph_path.exists():
        raise TaskGraphError(f"Task graph not found: {workspace_id}/{goal_id}")
    try:
        graph = read_json(graph_path)
    except WorkspaceStoreError as exc:
        raise TaskGraphError(str(exc)) from exc
    graph["tasks"] = normalize_tasks(graph.get("tasks", []))
    return graph


def compute_ready_tasks(graph: dict[str, Any]) -> dict[str, Any]:
    tasks = normalize_tasks(graph.get("tasks", []))
    by_id = {task["task_id"]: task for task in tasks}
    ready: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []

    for task in tasks:
        reasons: list[str] = []
        if task["status"] != "created":
            reasons.append(f"status:{task['status']}")
        for dependency in task["depends_on"]:
            dependency_task = by_id.get(dependency)
            if dependency_task is None:
                reasons.append(f"unknown_dependency:{dependency}")
            elif dependency_task["status"] != "accepted":
                reasons.append(f"dependency_not_accepted:{dependency}")
        if reasons:
            blocked.append({"task_id": task["task_id"], "reasons": reasons})
        else:
            ready.append(task)

    return {
        "schema_version": 1,
        "kind": "agentoffice.task_graph_ready",
        "workspace_id": graph["workspace_id"],
        "goal_id": graph["goal_id"],
        "ready_tasks": ready,
        "blocked_tasks": blocked,
    }


def ready_tasks_payload(root: Path, workspace_id: str, goal_id: str) -> dict[str, Any]:
    return compute_ready_tasks(load_task_graph(root, workspace_id, goal_id))


def format_task_graph_payload(payload: dict[str, Any]) -> str:
    if payload.get("kind") == "agentoffice.task_graph_create":
        return f"task graph {payload['workspace_id']}/{payload['goal_id']} tasks={len(payload['task_graph']['tasks'])}"
    if payload.get("kind") == "agentoffice.task_graph_ready":
        ready = ", ".join(task["task_id"] for task in payload["ready_tasks"]) or "none"
        blocked = ", ".join(item["task_id"] for item in payload["blocked_tasks"]) or "none"
        return f"ready={ready} blocked={blocked}"
    return json.dumps(payload, indent=2, ensure_ascii=False)
