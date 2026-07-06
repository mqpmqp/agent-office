from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")


class WorkspaceStoreError(ValueError):
    pass


def validate_store_id(value: str, label: str) -> str:
    if not ID_PATTERN.fullmatch(value):
        raise WorkspaceStoreError(
            f"Invalid {label}: use [a-zA-Z0-9][a-zA-Z0-9._-]{{0,63}} without path separators."
        )
    return value


def workspace_store_root(root: Path) -> Path:
    return root / ".ai" / "workspaces"


def workspace_dir(root: Path, workspace_id: str) -> Path:
    return workspace_store_root(root) / validate_store_id(workspace_id, "workspace_id")


def run_dir(root: Path, workspace_id: str, run_id: str) -> Path:
    return workspace_dir(root, workspace_id) / "runs" / validate_store_id(run_id, "run_id")


def workspace_payload(workspace_id: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "agentoffice.workspace",
        "workspace_id": workspace_id,
        "status": "active",
        "runs_dir": "runs",
    }


def run_payload(workspace_id: str, run_id: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "agentoffice.run",
        "workspace_id": workspace_id,
        "run_id": run_id,
        "status": "created",
        "packets_dir": "packets",
        "results_dir": "results",
        "evidence_dir": "evidence",
    }


def read_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except FileNotFoundError as exc:
        raise WorkspaceStoreError(f"Missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise WorkspaceStoreError(f"Invalid JSON in {path}: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise WorkspaceStoreError(f"Expected JSON object in {path}")
    return payload


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    temp_path.replace(path)


def init_workspace(root: Path, workspace_id: str) -> dict[str, Any]:
    workspace_id = validate_store_id(workspace_id, "workspace_id")
    target = workspace_dir(root, workspace_id)
    metadata = target / "workspace.json"
    if target.exists() or metadata.exists():
        raise WorkspaceStoreError(f"Workspace already exists: {workspace_id}")

    (target / "runs").mkdir(parents=True, exist_ok=False)
    payload = workspace_payload(workspace_id)
    write_json_atomic(metadata, payload)
    return payload


def inspect_workspace(root: Path, workspace_id: str) -> dict[str, Any]:
    workspace_id = validate_store_id(workspace_id, "workspace_id")
    metadata = workspace_dir(root, workspace_id) / "workspace.json"
    if not metadata.exists():
        raise WorkspaceStoreError(f"Workspace not found: {workspace_id}")
    return read_json(metadata)


def create_run(root: Path, workspace_id: str, run_id: str) -> dict[str, Any]:
    workspace_id = validate_store_id(workspace_id, "workspace_id")
    run_id = validate_store_id(run_id, "run_id")
    inspect_workspace(root, workspace_id)

    target = run_dir(root, workspace_id, run_id)
    metadata = target / "run.json"
    if target.exists() or metadata.exists():
        raise WorkspaceStoreError(f"Run already exists: {run_id}")

    for child in ("packets", "results", "evidence"):
        (target / child).mkdir(parents=True, exist_ok=False)
    payload = run_payload(workspace_id, run_id)
    write_json_atomic(metadata, payload)
    return payload


def format_workspace_payload(payload: dict[str, Any]) -> str:
    if payload.get("kind") == "agentoffice.workspace":
        return f"workspace {payload['workspace_id']} status={payload['status']}"
    if payload.get("kind") == "agentoffice.run":
        return f"run {payload['workspace_id']}/{payload['run_id']} status={payload['status']}"
    return json.dumps(payload, indent=2, ensure_ascii=False)
