from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .workspace_store import WorkspaceStoreError, read_json, run_dir, validate_store_id


class RuntimeEventLogError(ValueError):
    pass


def validate_event_value(value: str, label: str) -> str:
    try:
        return validate_store_id(value, label)
    except WorkspaceStoreError as exc:
        raise RuntimeEventLogError(str(exc)) from exc


def event_log_path(root: Path, workspace_id: str, run_id: str) -> Path:
    return run_dir(root, workspace_id, run_id) / "events.jsonl"


def ensure_run(root: Path, workspace_id: str, run_id: str) -> Path:
    try:
        target = run_dir(root, workspace_id, run_id)
        read_json(target.parent.parent / "workspace.json")
        run_metadata = target / "run.json"
        if not run_metadata.exists():
            raise RuntimeEventLogError(f"Run not found: {run_id}")
        read_json(run_metadata)
    except WorkspaceStoreError as exc:
        raise RuntimeEventLogError(str(exc)) from exc
    return target


def read_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise RuntimeEventLogError(f"Invalid event JSON at line {line_number}: {exc.msg}") from exc
                if not isinstance(payload, dict):
                    raise RuntimeEventLogError(f"Expected event object at line {line_number}")
                events.append(payload)
    except UnicodeDecodeError as exc:
        raise RuntimeEventLogError(f"Invalid UTF-8 in {path}: {exc.reason}") from exc
    return events


def build_event(
    workspace_id: str,
    run_id: str,
    event_id: str,
    event_type: str,
    actor: str,
    task_id: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "agentoffice.runtime_event",
        "event_id": event_id,
        "workspace_id": workspace_id,
        "run_id": run_id,
        "task_id": task_id,
        "event_type": event_type,
        "actor": actor,
        "payload": {},
        "evidence_refs": [],
    }


def append_event(root: Path, workspace_id: str, run_id: str, event_type: str, actor: str) -> dict[str, Any]:
    workspace_id = validate_event_value(workspace_id, "workspace_id")
    run_id = validate_event_value(run_id, "run_id")
    event_type = validate_event_value(event_type, "event_type")
    actor = validate_event_value(actor, "actor")
    ensure_run(root, workspace_id, run_id)

    path = event_log_path(root, workspace_id, run_id)
    events = read_events(path)
    event = build_event(workspace_id, run_id, f"evt_{len(events) + 1:06d}", event_type, actor)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False))
        handle.write("\n")
    return event


def list_events(root: Path, workspace_id: str, run_id: str) -> list[dict[str, Any]]:
    workspace_id = validate_event_value(workspace_id, "workspace_id")
    run_id = validate_event_value(run_id, "run_id")
    ensure_run(root, workspace_id, run_id)
    return read_events(event_log_path(root, workspace_id, run_id))


def list_events_payload(root: Path, workspace_id: str, run_id: str) -> dict[str, Any]:
    workspace_id = validate_event_value(workspace_id, "workspace_id")
    run_id = validate_event_value(run_id, "run_id")
    return {
        "schema_version": 1,
        "kind": "agentoffice.runtime_event_list",
        "workspace_id": workspace_id,
        "run_id": run_id,
        "events": list_events(root, workspace_id, run_id),
    }


def format_runtime_event_payload(payload: dict[str, Any]) -> str:
    if payload.get("kind") == "agentoffice.runtime_event":
        return f"event {payload['event_id']} type={payload['event_type']} actor={payload['actor']}"
    if payload.get("kind") == "agentoffice.runtime_event_list":
        events = payload.get("events", [])
        if not events:
            return f"events {payload['workspace_id']}/{payload['run_id']}: none"
        return "\n".join(f"event {event['event_id']} type={event['event_type']} actor={event['actor']}" for event in events)
    return json.dumps(payload, indent=2, ensure_ascii=False)
