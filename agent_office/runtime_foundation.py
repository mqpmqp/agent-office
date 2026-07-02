from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
ALLOWED_ADAPTERS = {"local-static", "noop"}
TASK_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
TASK_STATUSES = {"pending", "completed", "failed", "blocked"}
TERMINAL_WORKSPACE_STATUSES = {"completed", "failed", "blocked"}
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


def _event_summary(event: dict[str, Any] | None) -> str:
    if not event:
        return ""
    return f"{event.get('entry_type')}:{event.get('task_id')}:{event.get('status')}"


def _project_relative(path: Path, project_root: Path) -> str:
    root = project_root.resolve(strict=True)
    return path.resolve(strict=False).relative_to(root).as_posix()
