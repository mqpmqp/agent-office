from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .adapters.base import AdapterError, AdapterInvocation, AdapterResult, mask_secrets
from .adapters.mock import MockAdapter
from .adapters.modes import adapter_for_role, load_adapter_mode_config, validate_adapter_mode
from .adapters.registry import get_adapter
from .doctor import (
    bool_text,
    collect_doctor,
    collect_profile_plan_audit,
    doctor_json,
    format_adapters,
    format_doctor,
    format_profile_plan_audit,
)
from .objectives import (
    ObjectiveSpecError,
    objective_detail_payload,
    objective_listing_payload,
    objective_registry_validation_payload,
    objective_spec_payload,
)
from .planner import PlanningError, execution_blueprint_payload
from .packets import (
    PacketError,
    execution_packet_payload,
    packet_contract_validation_payload,
)
from .profiles import (
    ALLOWED_ROLES,
    ProfileError,
    default_profile_name,
    get_profile,
    list_profiles,
    profile_plan_payload,
    profile_plan_contract_audit_payload,
    profile_plans_payload,
    profile_plans_contract_audit_payload,
)
from .run_bundle import (
    RunBundleError,
    format_run_bundle_catalog,
    format_run_bundle_inspection,
    format_run_bundle_preview,
    format_run_bundle_status,
    format_run_bundle_validation,
    inspect_run_bundle_payload,
    list_run_bundles_payload,
    run_bundle_preview_payload,
    status_run_bundle_payload,
    validate_run_bundle_payload,
    write_run_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASKS_ROOT = PROJECT_ROOT / ".ai" / "tasks"
FINAL_FOR_CLAUDE_LIMIT = 4000
MAX_REWORK_ROUNDS = 2
DRY_RUN_REAL_ADAPTERS = {"gemini", "codex", "grok", "claude"}
STAGED_REAL_ADAPTER_ROLES = {
    "gemini": "context",
    "codex": "implement",
    "grok": "redteam",
    "claude": "final",
}
STAGED_RUNTIME_DIR_NAMES = ("context", "codex", "grok", "claude", "finalize")
STAGED_ARTIFACT_DESTINATION_PARTS = (
    (".ai", "context", "gemini-context.md"),
    (".ai", "codex", "patch.diff"),
    (".ai", "codex", "codex-report.md"),
    (".ai", "grok", "redteam-report.md"),
    (".ai", "finalize", "final-for-claude.md"),
)

STATES = {
    "CREATED",
    "CONTEXT_READY",
    "IMPLEMENTED",
    "REVIEWED",
    "SUMMARIZED",
    "CLAUDE_DECIDED",
    "APPROVED",
    "REQUEST_CHANGES",
    "REJECTED",
}

TERMINAL_STATES = {"APPROVED", "REJECTED"}


class AgentOfficeError(RuntimeError):
    pass


@dataclass(frozen=True)
class TaskPaths:
    root: Path
    task_json: Path
    brief: Path
    gemini_context: Path
    codex_report: Path
    patch_diff: Path
    grok_review: Path
    final_for_claude: Path
    claude_decision: Path


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def task_paths(task_id: str) -> TaskPaths:
    root = TASKS_ROOT / task_id
    return TaskPaths(
        root=root,
        task_json=root / "task.json",
        brief=root / "brief.md",
        gemini_context=root / "gemini-context.md",
        codex_report=root / "codex-report.md",
        patch_diff=root / "patch.diff",
        grok_review=root / "grok-review.md",
        final_for_claude=root / "final-for-claude.md",
        claude_decision=root / "claude-decision.md",
    )


def validate_task_id(task_id: str) -> None:
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
    if not task_id or any(ch not in allowed for ch in task_id):
        raise AgentOfficeError("TASK_ID may only contain letters, numbers, dash, underscore, and dot.")
    if task_id in {".", ".."}:
        raise AgentOfficeError("TASK_ID is invalid.")


def reset_task(task_id: str) -> None:
    validate_task_id(task_id)
    paths = task_paths(task_id)
    resolved_root = paths.root.resolve()
    resolved_tasks_root = TASKS_ROOT.resolve()
    if resolved_tasks_root not in resolved_root.parents:
        raise AgentOfficeError(f"Refusing to reset task outside tasks root: {paths.root}")
    if paths.root.exists():
        shutil.rmtree(paths.root)


def clear_staged_runtime_dirs() -> None:
    ai_root = (PROJECT_ROOT / ".ai").resolve()
    for name in STAGED_RUNTIME_DIR_NAMES:
        path = PROJECT_ROOT / ".ai" / name
        resolved = path.resolve()
        expected = (PROJECT_ROOT / ".ai" / name).resolve()
        if resolved != expected or resolved.parent != ai_root:
            raise AgentOfficeError(f"Refusing to clear unsafe staged runtime path: {path}")
        if not path.exists():
            continue
        if path.is_symlink() or not path.is_dir():
            raise AgentOfficeError(f"Refusing to clear non-directory staged runtime path: {path}")
        shutil.rmtree(path)


def allowed_staged_artifact_destinations() -> set[Path]:
    return {(PROJECT_ROOT.joinpath(*parts)).resolve() for parts in STAGED_ARTIFACT_DESTINATION_PARTS}


def copy_task_artifact_if_exists(paths: TaskPaths, source: Path, destination: Path) -> bool:
    if source.is_symlink():
        raise AgentOfficeError(f"Refusing to stage symlink task artifact: {source}")
    if not source.exists():
        return False
    if not source.is_file():
        raise AgentOfficeError(f"Refusing to stage non-file task artifact: {source}")
    resolved_source = source.resolve()
    resolved_task_root = paths.root.resolve()
    if resolved_source != resolved_task_root and resolved_task_root not in resolved_source.parents:
        raise AgentOfficeError(f"Refusing to stage artifact outside current task root: {source}")
    resolved_destination = destination.resolve()
    if resolved_destination not in allowed_staged_artifact_destinations():
        raise AgentOfficeError(f"Refusing to stage artifact to unsupported destination: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    return True


def stage_current_task_artifacts(adapter_name: str, paths: TaskPaths) -> None:
    staged_context = PROJECT_ROOT / ".ai" / "context" / "gemini-context.md"
    staged_codex_patch = PROJECT_ROOT / ".ai" / "codex" / "patch.diff"
    staged_codex_report = PROJECT_ROOT / ".ai" / "codex" / "codex-report.md"
    staged_grok_report = PROJECT_ROOT / ".ai" / "grok" / "redteam-report.md"
    staged_final_packet = PROJECT_ROOT / ".ai" / "finalize" / "final-for-claude.md"

    if adapter_name in {"codex", "grok", "claude"}:
        copy_task_artifact_if_exists(paths, paths.gemini_context, staged_context)
    if adapter_name in {"grok", "claude"}:
        copy_task_artifact_if_exists(paths, paths.patch_diff, staged_codex_patch)
        copy_task_artifact_if_exists(paths, paths.codex_report, staged_codex_report)
    if adapter_name == "claude":
        copy_task_artifact_if_exists(paths, paths.grok_review, staged_grok_report)
        copy_task_artifact_if_exists(paths, paths.final_for_claude, staged_final_packet)


def load_task(paths: TaskPaths) -> dict[str, Any]:
    if not paths.task_json.exists():
        raise AgentOfficeError(f"Task does not exist: {paths.root}")
    return json.loads(paths.task_json.read_text(encoding="utf-8"))


def save_task(paths: TaskPaths, task: dict[str, Any]) -> None:
    task["updated_at"] = now_iso()
    tmp = paths.task_json.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(task, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(paths.task_json)


def append_history(task: dict[str, Any], event: str, detail: str) -> None:
    task.setdefault("history", []).append({"at": now_iso(), "event": event, "detail": detail})


def transition(paths: TaskPaths, task: dict[str, Any], new_state: str, detail: str) -> None:
    if new_state not in STATES:
        raise AgentOfficeError(f"Unknown state: {new_state}")
    old_state = task["state"]
    task["state"] = new_state
    append_history(task, f"{old_state}->{new_state}", detail)
    save_task(paths, task)


def require_state(task: dict[str, Any], allowed: set[str]) -> None:
    state = task["state"]
    if state not in allowed:
        raise AgentOfficeError(f"Invalid state {state}; expected one of: {', '.join(sorted(allowed))}")
    if state in TERMINAL_STATES:
        raise AgentOfficeError(f"Task is terminal: {state}")


def resolve_mode(args: argparse.Namespace, role: str) -> str:
    mock = bool(getattr(args, "mock", False))
    real = bool(getattr(args, "real", False))
    if mock and real:
        raise AgentOfficeError("Use only one of --mock or --real.")
    if real:
        return "real"
    if mock:
        return "mock"
    if role in {"context", "implement", "run-demo"}:
        env_mode = os.environ.get("AGENTOFFICE_AGENT_MODE", "mock").strip().lower()
        if env_mode == "real":
            return "real"
    return "mock"


def require_mock_mode(args: argparse.Namespace, role: str) -> None:
    if resolve_mode(args, role) == "real":
        raise AgentOfficeError(f"{role} real adapter is not implemented in this phase. Use --mock.")


def build_invocation(args: argparse.Namespace, paths: TaskPaths) -> AdapterInvocation:
    timeout = getattr(args, "timeout", None)
    if timeout is not None and timeout <= 0:
        raise AgentOfficeError("--timeout must be a positive integer.")
    return AdapterInvocation(
        task_id=args.task_id,
        project_root=PROJECT_ROOT,
        paths=paths,
        timeout_seconds=timeout,
        max_rework_rounds=MAX_REWORK_ROUNDS,
        final_for_claude_limit=FINAL_FOR_CLAUDE_LIMIT,
    )


def run_adapter(role: str, args: argparse.Namespace, paths: TaskPaths):
    mode = resolve_mode(args, role)
    adapter_name = getattr(args, "adapter", None)
    if mode == "real":
        return run_real_adapter(role, args, paths, adapter_name)
    try:
        adapter = get_adapter(role, mode, adapter_name)
        method = getattr(adapter, role)
        return method(build_invocation(args, paths))
    except AdapterError as exc:
        raise AgentOfficeError(str(exc)) from exc


def run_real_adapter(role: str, args: argparse.Namespace, paths: TaskPaths, adapter_name: str | None) -> AdapterResult:
    config_name = adapter_name if adapter_name not in {None, "mock"} else adapter_for_role(role)
    if not config_name:
        raise AgentOfficeError(f"No staged real adapter is registered for role `{role}`. Use --mock.")
    dry_run_var = f"AGENTOFFICE_{config_name.upper()}_DRY_RUN"
    previous_dry_run = os.environ.get(dry_run_var)
    if bool(getattr(args, "dry_run", False)):
        os.environ[dry_run_var] = "true"
    try:
        config = load_adapter_mode_config(config_name)
        if config.role != role:
            raise AgentOfficeError(f"Adapter `{config.name}` is registered for role `{config.role}`, not `{role}`.")
        if config.mode != "real":
            raise AgentOfficeError(
                f"{config.name} adapter mode is `{config.mode}`. Set AGENTOFFICE_{config.name.upper()}_MODE=real explicitly or use --mock."
            )

        validation = validate_adapter_mode(config)
        if validation.errors:
            reason = "; ".join(validation.errors)
            return maybe_fallback_to_mock(role, args, paths, config.name, config.fallback_to_mock, reason)

        if config.name not in DRY_RUN_REAL_ADAPTERS and config.dry_run:
            reason = f"{config.name} adapter dry_run=true; real command was not executed."
            return maybe_fallback_to_mock(role, args, paths, config.name, config.fallback_to_mock, reason)

        try:
            adapter = get_adapter(role, "real", config.name)
            method = getattr(adapter, role)
            return method(build_invocation(args, paths))
        except AdapterError as exc:
            return maybe_fallback_to_mock(role, args, paths, config.name, config.fallback_to_mock, str(exc))
    finally:
        if bool(getattr(args, "dry_run", False)):
            if previous_dry_run is None:
                os.environ.pop(dry_run_var, None)
            else:
                os.environ[dry_run_var] = previous_dry_run


def maybe_fallback_to_mock(
    role: str,
    args: argparse.Namespace,
    paths: TaskPaths,
    adapter_name: str,
    fallback_to_mock: bool,
    reason: str,
) -> AdapterResult:
    safe_reason = mask_secrets(reason)
    if not fallback_to_mock:
        raise AgentOfficeError(f"{adapter_name} real adapter failed safely: {safe_reason}")
    mock = MockAdapter()
    method = getattr(mock, role)
    result = method(build_invocation(args, paths))
    metadata = dict(result.metadata)
    metadata.update({"fallback_used": True, "real_adapter": adapter_name, "fallback_reason": safe_reason})
    return AdapterResult(
        detail=f"{result.detail} fallback_used=true; real_adapter={adapter_name}; reason={safe_reason}",
        decision=result.decision,
        stdout=result.stdout,
        stderr=result.stderr,
        metadata=metadata,
    )


def write_file(path: Path, content: str) -> None:
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def read_if_exists(path: Path, max_chars: int | None = None) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8")
    if max_chars is not None and len(text) > max_chars:
        return text[:max_chars] + "\n...[truncated]..."
    return text


def cmd_new(args: argparse.Namespace) -> int:
    validate_task_id(args.task_id)
    paths = task_paths(args.task_id)
    if paths.root.exists():
        raise AgentOfficeError(f"Task already exists: {paths.root}")
    paths.root.mkdir(parents=True)
    task = {
        "task_id": args.task_id,
        "state": "CREATED",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "rework_rounds": 0,
        "max_rework_rounds": MAX_REWORK_ROUNDS,
        "final_for_claude_limit": FINAL_FOR_CLAUDE_LIMIT,
        "agents": {
            "gemini": "context scan and compressed summary",
            "codex": "implementation, bug fixing, tests",
            "grok_build": "red-team review",
            "claude_code": "final decision only from final-for-claude.md",
            "orchestrator": "state machine, task queue, logs, artifacts",
        },
        "history": [{"at": now_iso(), "event": "CREATED", "detail": "Task workspace initialized."}],
    }
    save_task(paths, task)
    write_file(
        paths.brief,
        f"""# Task Brief

Task ID: `{args.task_id}`

## Goal

Describe the user request here before running real providers.

## Collaboration Rules

- Agents communicate through files in this directory.
- Gemini writes `gemini-context.md`.
- Codex writes `codex-report.md` and `patch.diff`.
- Grok Build writes `grok-review.md`.
- Orchestrator writes `final-for-claude.md`.
- Claude reads only `final-for-claude.md` and writes `claude-decision.md`.
""",
    )
    print(f"created {paths.root}")
    return 0


def cmd_context(args: argparse.Namespace) -> int:
    paths = task_paths(args.task_id)
    task = load_task(paths)
    require_state(task, {"CREATED", "REQUEST_CHANGES"})
    result = run_adapter("context", args, paths)
    transition(paths, task, "CONTEXT_READY", result.detail)
    print("state=CONTEXT_READY")
    return 0


def cmd_implement(args: argparse.Namespace) -> int:
    paths = task_paths(args.task_id)
    task = load_task(paths)
    require_state(task, {"CONTEXT_READY", "REQUEST_CHANGES"})
    if task["state"] == "REQUEST_CHANGES":
        if int(task.get("rework_rounds", 0)) >= MAX_REWORK_ROUNDS:
            raise AgentOfficeError("Max rework rounds reached.")
        task["rework_rounds"] = int(task.get("rework_rounds", 0)) + 1
    result = run_adapter("implement", args, paths)
    transition(paths, task, "IMPLEMENTED", result.detail)
    print("state=IMPLEMENTED")
    return 0


def cmd_redteam(args: argparse.Namespace) -> int:
    paths = task_paths(args.task_id)
    task = load_task(paths)
    require_state(task, {"IMPLEMENTED"})
    result = run_adapter("redteam", args, paths)
    transition(paths, task, "REVIEWED", result.detail)
    print("state=REVIEWED")
    return 0


def build_final_summary(paths: TaskPaths, task: dict[str, Any]) -> str:
    brief = read_if_exists(paths.brief, 800)
    gemini = read_if_exists(paths.gemini_context, 900)
    codex = read_if_exists(paths.codex_report, 900)
    review = read_if_exists(paths.grok_review, 900)
    patch_head = read_if_exists(paths.patch_diff, 800)
    summary = f"""# Final For Claude

Claude must read only this file for task `{task['task_id']}`.

## Current State

- State before Claude decision: {task['state']}
- Rework rounds used: {task.get('rework_rounds', 0)} / {task.get('max_rework_rounds', MAX_REWORK_ROUNDS)}
- Final summary limit: {task.get('final_for_claude_limit', FINAL_FOR_CLAUDE_LIMIT)} characters

## Task Brief Snapshot

{brief}

## Gemini Context Snapshot

{gemini}

## Codex Implementation Snapshot

{codex}

## Grok Build Review Snapshot

{review}

## Patch Preview Only

Claude receives only this preview, not the full repository or full logs.

```diff
{patch_head}
```

## Decision Options

- APPROVED
- REQUEST_CHANGES
- REJECTED
"""
    limit = int(task.get("final_for_claude_limit", FINAL_FOR_CLAUDE_LIMIT))
    if len(summary) > limit:
        suffix = "\n\n[TRUNCATED BY ORCHESTRATOR TO PROTECT CLAUDE TOKENS]\n"
        summary = summary[: max(0, limit - len(suffix))] + suffix
    return summary


def cmd_summarize(args: argparse.Namespace) -> int:
    require_mock_mode(args, "summarize")
    paths = task_paths(args.task_id)
    task = load_task(paths)
    require_state(task, {"REVIEWED"})
    write_file(paths.final_for_claude, build_final_summary(paths, task))
    transition(paths, task, "SUMMARIZED", "Orchestrator wrote Claude-only compressed summary.")
    print(f"state=SUMMARIZED final_chars={len(paths.final_for_claude.read_text(encoding='utf-8'))}")
    return 0


def cmd_final(args: argparse.Namespace) -> int:
    paths = task_paths(args.task_id)
    task = load_task(paths)
    require_state(task, {"SUMMARIZED"})
    result = run_adapter("final", args, paths)
    decision = result.decision
    if decision not in {"APPROVED", "REQUEST_CHANGES", "REJECTED"}:
        raise AgentOfficeError("Final adapter returned an invalid decision.")
    append_history(task, "SUMMARIZED->CLAUDE_DECIDED", "Claude final adapter read final-for-claude.md only.")
    transition(paths, task, decision, result.detail)
    print(f"state={decision}")
    return 0


def cmd_judge(args: argparse.Namespace) -> int:
    paths = task_paths(args.task_id)
    task = load_task(paths)
    require_state(task, {"REVIEWED", "SUMMARIZED"})
    if task["state"] == "REVIEWED":
        write_file(paths.final_for_claude, build_final_summary(paths, task))
        transition(paths, task, "SUMMARIZED", "Orchestrator wrote Claude-only compressed summary for judge.")
    return cmd_final(args)


def cmd_status(args: argparse.Namespace) -> int:
    paths = task_paths(args.task_id)
    task = load_task(paths)
    files = [
        paths.task_json,
        paths.brief,
        paths.gemini_context,
        paths.codex_report,
        paths.patch_diff,
        paths.grok_review,
        paths.final_for_claude,
        paths.claude_decision,
    ]
    print(json.dumps({
        "task_id": task["task_id"],
        "state": task["state"],
        "rework_rounds": task.get("rework_rounds", 0),
        "max_rework_rounds": task.get("max_rework_rounds", MAX_REWORK_ROUNDS),
        "files": {p.name: p.exists() for p in files},
    }, indent=2, ensure_ascii=False))
    return 0


def cmd_adapters(args: argparse.Namespace) -> int:
    print(format_adapters(PROJECT_ROOT))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    if bool(getattr(args, "profiles", False)):
        audit = collect_profile_plan_audit()
        if args.json:
            print(json.dumps(audit, indent=2, ensure_ascii=False))
        else:
            print(format_profile_plan_audit(audit))
        return 0

    report = collect_doctor(PROJECT_ROOT, adapter_filter=args.adapter)
    if args.adapters:
        if args.json:
            print(json.dumps(report["adapter_modes"]["rows"], indent=2, ensure_ascii=False))
        else:
            print(format_adapter_rows(report["adapter_modes"]["rows"]))
    elif args.json:
        print(doctor_json(report))
    else:
        print(format_doctor(report))
    return 0


def format_adapter_rows(rows: list[dict[str, object]]) -> str:
    lines = ["adapter | mode | dry_run | env_ok | fallback | status"]
    for row in rows:
        lines.append(
            " | ".join(
                [
                    str(row["adapter"]),
                    str(row["mode"]),
                    bool_text(bool(row["dry_run"])),
                    bool_text(bool(row["env_ok"])),
                    bool_text(bool(row["fallback"])),
                    str(row["status"]),
                ]
            )
        )
    return "\n".join(lines)


def profile_payload(name: str | None = None) -> dict[str, object]:
    profile_names = list_profiles()
    selected_names = (name,) if name else profile_names
    try:
        profiles = []
        for profile_name in selected_names:
            profile = get_profile(profile_name)
            profiles.append(
                {
                    "name": profile.name,
                    "roles": {role: profile.roles[role] for role in ALLOWED_ROLES},
                }
            )
    except ProfileError as exc:
        raise AgentOfficeError(str(exc)) from exc
    return {
        "default_profile": default_profile_name(),
        "available_profiles": list(profile_names),
        "profiles": profiles,
    }


def format_profiles(payload: dict[str, object]) -> str:
    lines = [
        "AgentOffice provider profiles",
        f"default: {payload['default_profile']}",
        f"available: {', '.join(str(name) for name in payload['available_profiles'])}",
    ]
    for profile in payload["profiles"]:
        if not isinstance(profile, dict):
            continue
        lines.append("")
        lines.append(str(profile["name"]))
        roles = profile["roles"]
        if not isinstance(roles, dict):
            continue
        for role in ALLOWED_ROLES:
            lines.append(f"  {role}: {roles[role]}")
    return "\n".join(lines)


def format_profile_plan(payload: dict[str, object]) -> str:
    lines = [
        "AgentOffice profile plan preview",
        f"selected_profile: {payload['selected_profile']}",
        f"default_profile: {payload['default_profile']}",
        f"is_default: {str(payload['is_default']).lower()}",
        f"execution_enabled: {str(payload['execution_enabled']).lower()}",
        f"provider_calls: {str(payload['provider_calls']).lower()}",
        f"artifact_writes: {str(payload['artifact_writes']).lower()}",
        "",
        "roles:",
    ]
    for role in payload["roles"]:
        if not isinstance(role, dict):
            continue
        lines.append(f"  {role['role']}: {role['provider']} ({role['execution_category']})")
    return "\n".join(lines)


def format_profile_plans(payload: dict[str, object]) -> str:
    lines = [
        "AgentOffice profile plan previews",
        f"default_profile: {payload['default_profile']}",
        f"available_profiles: {', '.join(str(name) for name in payload['available_profiles'])}",
        "",
    ]
    plans = payload["plans"]
    if not isinstance(plans, list):
        return "\n".join(lines).rstrip()
    for index, plan in enumerate(plans):
        if not isinstance(plan, dict):
            continue
        if index:
            lines.append("")
        lines.append(format_profile_plan(plan))
    return "\n".join(lines)


def format_profile_plan_contract_audit(payload: dict[str, object]) -> str:
    provider_calls = payload["provider_calls"]
    provider_calls_count = len(provider_calls) if isinstance(provider_calls, list) else int(bool(provider_calls))
    lines = [
        "Profile plan contract audit",
        f"selected_profile: {payload['selected_profile']}",
        f"default_profile: {payload['default_profile']}",
        f"is_default: {str(payload['is_default']).lower()}",
        f"execution_enabled: {str(payload['execution_enabled']).lower()}",
        f"provider_calls_count: {provider_calls_count}",
        f"contract_status: {payload['status']}",
        "checks:",
    ]
    checks = payload["checks"]
    if isinstance(checks, list):
        for check in checks:
            if isinstance(check, dict):
                lines.append(f"  {check['name']}: {check['status']}")
    lines.append("provider/runtime/adapter execution: not triggered")
    return "\n".join(lines)


def format_profile_plan_contract_audits(payload: dict[str, object]) -> str:
    lines = [
        "Profile plan contract audits",
        f"default_profile: {payload['default_profile']}",
        f"available_profiles: {', '.join(str(name) for name in payload['available_profiles'])}",
        f"contract_status: {payload['status']}",
        "",
    ]
    audits = payload["audits"]
    if isinstance(audits, list):
        for index, audit in enumerate(audits):
            if not isinstance(audit, dict):
                continue
            if index:
                lines.append("")
            lines.append(format_profile_plan_contract_audit(audit))
    return "\n".join(lines).rstrip()


def format_objective_spec(payload: dict[str, object]) -> str:
    lines = [
        "AgentOffice objective spec",
        f"phase: {payload['phase']}",
        f"title: {payload['title']}",
        f"status: {payload['status']}",
        f"objective: {payload['objective']}",
        f"source_phases: {', '.join(str(phase) for phase in payload['source_phases'])}",
        "cli_contract:",
    ]
    for command in payload["cli_contract"]:
        lines.append(f"  - {command}")
    contract = payload["json_contract"]
    if isinstance(contract, dict):
        lines.append("json_contract:")
        lines.append(f"  schema_version: {contract['schema_version']}")
        lines.append(f"  required_fields: {', '.join(str(field) for field in contract['required_fields'])}")
    for section in ("tests", "validation"):
        lines.append(f"{section}:")
        for item in payload[section]:
            lines.append(f"  - {item}")
    safety = payload["safety"]
    if isinstance(safety, dict):
        lines.append("safety:")
        for key in sorted(safety):
            lines.append(f"  {key}: {str(safety[key]).lower()}")
    return "\n".join(lines)


def format_objective_listing(payload: dict[str, object]) -> str:
    lines = [
        "AgentOffice objectives",
        f"default_phase: {payload['default_phase']}",
        "objectives:",
    ]
    objectives = payload["objectives"]
    if isinstance(objectives, list):
        for objective in objectives:
            if not isinstance(objective, dict):
                continue
            lines.append(f"  - phase: {objective['phase']}")
            lines.append(f"    title: {objective['title']}")
            lines.append(f"    status: {objective['status']}")
            lines.append(f"    objective: {objective['objective']}")
    return "\n".join(lines)


def format_objective_registry_validation(payload: dict[str, object]) -> str:
    lines = [
        "Objective registry validation",
        f"default_phase: {payload['default_phase']}",
        f"objectives_checked: {payload['objectives_checked']}",
        f"status: {payload['status']}",
        "checks:",
    ]
    checks = payload["checks"]
    if isinstance(checks, list):
        for check in checks:
            if isinstance(check, dict):
                lines.append(f"  {check['name']}: {check['status']}")
    errors = payload.get("errors", [])
    if isinstance(errors, list) and errors:
        lines.append("errors:")
        for error in errors:
            lines.append(f"  - {error}")
    lines.append("provider/runtime/adapter execution: not triggered")
    return "\n".join(lines)


def format_execution_blueprint(payload: dict[str, object]) -> str:
    lines = [
        "AgentOffice execution blueprint",
        f"objective_id: {payload['objective_id']}",
        f"objective_name: {payload['objective_name']}",
        f"objective_summary: {payload['objective_summary']}",
        f"selected_profile: {payload['selected_profile']}",
        f"default_profile: {payload['default_profile']}",
        f"is_default: {str(payload['is_default']).lower()}",
        f"execution_enabled: {str(payload['execution_enabled']).lower()}",
        "provider_calls:",
    ]
    provider_calls = payload["provider_calls"]
    if isinstance(provider_calls, list):
        for call in provider_calls:
            if isinstance(call, dict):
                lines.append(
                    f"  - {call['role']}: {call['provider']} ({call['execution_category']}); call_enabled={str(call['call_enabled']).lower()}"
                )
    lines.extend(
        [
            f"runtime_calls: {str(payload['runtime_calls']).lower()}",
            f"adapter_calls: {str(payload['adapter_calls']).lower()}",
            f"env_required: {str(payload['env_required']).lower()}",
            "safety_constraints:",
        ]
    )
    for constraint in payload["safety_constraints"]:
        lines.append(f"  - {constraint}")
    lines.append("validation_commands:")
    for command in payload["validation_commands"]:
        lines.append(f"  - {command}")
    lines.extend(
        [
            f"next_actor: {payload['next_actor']}",
            f"next_action_summary: {payload['next_action_summary']}",
        ]
    )
    return "\n".join(lines)


def format_execution_packet(payload: dict[str, object]) -> str:
    objective = payload["objective"]
    profile = payload["profile"]
    lines = [
        "AgentOffice execution packet",
        f"packet_version: {payload['packet_version']}",
        f"objective: {objective['id']} - {objective['name']}" if isinstance(objective, dict) else f"objective: {objective}",
        f"profile: {profile['selected']}" if isinstance(profile, dict) else f"profile: {profile}",
        f"actor: {payload['actor']}",
        f"execution_enabled: {str(payload['execution_enabled']).lower()}",
        f"env_required: {str(payload['env_required']).lower()}",
        f"runtime_calls: {str(payload['runtime_calls']).lower()}",
        f"adapter_calls: {str(payload['adapter_calls']).lower()}",
        "instructions:",
    ]
    for instruction in payload["instructions"]:
        lines.append(f"  - {instruction}")
    lines.append("safety_constraints:")
    for constraint in payload["safety_constraints"]:
        lines.append(f"  - {constraint}")
    lines.append("allowed_actions:")
    for action in payload["allowed_actions"]:
        lines.append(f"  - {action}")
    lines.append("forbidden_actions:")
    for action in payload["forbidden_actions"]:
        lines.append(f"  - {action}")
    lines.append("validation_commands:")
    for command in payload["validation_commands"]:
        lines.append(f"  - {command}")
    lines.append("success_criteria:")
    for criterion in payload["success_criteria"]:
        lines.append(f"  - {criterion}")
    lines.append("failure_criteria:")
    for criterion in payload["failure_criteria"]:
        lines.append(f"  - {criterion}")
    lines.append(f"handoff_summary: {payload['handoff_summary']}")
    return "\n".join(lines)


def format_packet_contract_validation(payload: dict[str, object]) -> str:
    status = "PASS" if payload["valid"] else "FAIL"
    lines = [
        "Packet contract validation",
        f"status: {status}",
        f"schema_version: {payload['schema_version']}",
        f"objective: {payload['objective']}",
        f"profile: {payload['profile']}",
        f"actor: {payload['actor']}",
        "checks:",
    ]
    checks = payload["checks"]
    if isinstance(checks, list):
        for check in checks:
            if isinstance(check, dict):
                lines.append(f"  - {check['name']}: {check['status']}")
    lines.append("external_behavior:")
    external_behavior = payload["external_behavior"]
    if isinstance(external_behavior, dict):
        for key in sorted(external_behavior):
            lines.append(f"  {key}: {str(external_behavior[key]).lower()}")
    lines.append("no real execution performed: true")
    return "\n".join(lines)


def cmd_objectives(args: argparse.Namespace) -> int:
    if bool(getattr(args, "list", False)):
        payload = objective_listing_payload()
        print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_objective_listing(payload))
        return 0
    if bool(getattr(args, "validate", False)):
        payload = objective_registry_validation_payload()
        print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_objective_registry_validation(payload))
        return 0 if payload["status"] == "pass" else 1
    try:
        if getattr(args, "show", None):
            payload = objective_detail_payload(args.show)
        else:
            payload = objective_spec_payload(getattr(args, "phase", None))
    except ObjectiveSpecError as exc:
        raise AgentOfficeError(str(exc)) from exc
    print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_objective_spec(payload))
    return 0


def cmd_profiles(args: argparse.Namespace) -> int:
    plan = bool(getattr(args, "plan", False))
    audit = bool(getattr(args, "audit", False))
    if audit and not plan:
        raise AgentOfficeError("profiles --audit requires --plan.")
    if plan:
        try:
            if audit:
                if args.name:
                    payload = profile_plan_contract_audit_payload(args.name)
                    print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_profile_plan_contract_audit(payload))
                else:
                    payload = profile_plans_contract_audit_payload()
                    print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_profile_plan_contract_audits(payload))
            elif args.name:
                payload = profile_plan_payload(args.name)
                print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_profile_plan(payload))
            else:
                payload = profile_plans_payload()
                print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_profile_plans(payload))
        except ProfileError as exc:
            raise AgentOfficeError(str(exc)) from exc
        return 0

    payload = profile_payload(args.name)
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(format_profiles(payload))
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    try:
        payload = execution_blueprint_payload(args.objective, args.profile)
    except PlanningError as exc:
        raise AgentOfficeError(str(exc)) from exc
    print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_execution_blueprint(payload))
    return 0


def cmd_packet(args: argparse.Namespace) -> int:
    validate = bool(getattr(args, "validate", False))
    try:
        if validate:
            payload = packet_contract_validation_payload(args.objective, args.profile, args.actor)
        else:
            payload = execution_packet_payload(args.objective, args.profile, args.actor)
    except PacketError as exc:
        raise AgentOfficeError(str(exc)) from exc
    if validate:
        print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_packet_contract_validation(payload))
        return 0 if payload["valid"] else 1
    print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_execution_packet(payload))
    return 0


def cmd_run_bundle(args: argparse.Namespace) -> int:
    action = getattr(args, "bundle_action", None)
    try:
        if action == "list":
            if not args.root:
                raise RunBundleError("run-bundle list requires --root.")
            payload = list_run_bundles_payload(args.root, PROJECT_ROOT)
            print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_run_bundle_catalog(payload))
            return 0
        if action == "inspect":
            if not args.path:
                raise RunBundleError("run-bundle inspect requires --path.")
            payload = inspect_run_bundle_payload(args.path, PROJECT_ROOT)
            print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_run_bundle_inspection(payload))
            return 0
        if action == "validate":
            if not args.path:
                raise RunBundleError("run-bundle validate requires --path.")
            payload = validate_run_bundle_payload(args.path, PROJECT_ROOT)
            print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_run_bundle_validation(payload))
            return 0
        if action == "status":
            if not args.path:
                raise RunBundleError("run-bundle status requires --path.")
            payload = status_run_bundle_payload(args.path, PROJECT_ROOT)
            print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_run_bundle_status(payload))
            return 0 if payload["status"] == "ready" else 2
        if not args.objective or not args.profile or not args.run_id:
            raise RunBundleError("run-bundle requires --objective, --profile, and --run-id.")
        payload = run_bundle_preview_payload(args.objective, args.profile, args.run_id)
        if args.out:
            payload = dict(payload)
            payload["write_result"] = write_run_bundle(payload, args.out, PROJECT_ROOT)
            payload["artifact_writes"] = True
    except RunBundleError as exc:
        raise AgentOfficeError(str(exc)) from exc
    print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_run_bundle_preview(payload))
    return 0


def cmd_run_demo(args: argparse.Namespace) -> int:
    demo_mode = resolve_mode(args, "run-demo")
    validate_task_id(args.task_id)
    if args.reset:
        reset_task(args.task_id)
        print(f"reset task: {args.task_id}")
    demo_steps: list[tuple[str, Callable[[argparse.Namespace], int]]] = [
        ("new", cmd_new),
        ("context", cmd_context),
        ("implement", cmd_implement),
        ("redteam", cmd_redteam),
        ("summarize", cmd_summarize),
        ("final", cmd_final),
        ("status", cmd_status),
    ]
    for name, fn in demo_steps:
        real_step = demo_mode == "real" and name == "implement"
        step_args = argparse.Namespace(
            task_id=args.task_id,
            mock=not real_step,
            real=real_step,
            adapter=getattr(args, "adapter", None),
            timeout=getattr(args, "timeout", None),
            reset=False,
            dry_run=False,
        )
        if name == "new" and task_paths(args.task_id).root.exists():
            print(f"skip new: task already exists ({args.task_id})")
            continue
        print(f"\n== {name} ==")
        fn(step_args)
    return 0


def staged_real_selection(args: argparse.Namespace) -> tuple[str | None, str | None]:
    if not bool(getattr(args, "dry_run", False)):
        raise AgentOfficeError("run-staged requires --dry-run.")
    real = bool(getattr(args, "real", False))
    adapter_name = getattr(args, "adapter", None)
    if adapter_name == "mock":
        adapter_name = None
    if not real and adapter_name:
        raise AgentOfficeError("run-staged accepts --adapter only with --real.")
    if not real:
        return None, None
    if not adapter_name:
        raise AgentOfficeError("run-staged --real requires one explicit --adapter. Enabling all real adapters is refused.")
    role = STAGED_REAL_ADAPTER_ROLES.get(adapter_name)
    if role is None:
        raise AgentOfficeError(f"Unsupported run-staged real adapter: {adapter_name}")
    return role, adapter_name


def cmd_run_staged(args: argparse.Namespace) -> int:
    validate_task_id(args.task_id)
    real_role, real_adapter = staged_real_selection(args)
    clear_staged_runtime_dirs()
    if args.reset:
        reset_task(args.task_id)
        print(f"reset task: {args.task_id}")

    paths = task_paths(args.task_id)
    staged_steps: list[tuple[str, str | None, Callable[[argparse.Namespace], int]]] = [
        ("new", None, cmd_new),
        ("context", "context", cmd_context),
        ("implement", "implement", cmd_implement),
        ("redteam", "redteam", cmd_redteam),
        ("summarize", None, cmd_summarize),
        ("judge", "final", cmd_judge),
        ("status", None, cmd_status),
    ]
    for name, role, fn in staged_steps:
        if name == "new" and paths.root.exists():
            print(f"skip new: task already exists ({args.task_id})")
            continue
        real_step = bool(real_adapter and role == real_role)
        step_args = argparse.Namespace(
            task_id=args.task_id,
            mock=not real_step,
            real=real_step,
            adapter=real_adapter if real_step else None,
            timeout=getattr(args, "timeout", None),
            reset=False,
            dry_run=real_step,
        )
        if real_step:
            stage_current_task_artifacts(real_adapter, paths)
        print(f"\n== {name} ==")
        fn(step_args)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-office")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("new", help="Create a task workspace.")
    p.add_argument("task_id")
    p.set_defaults(func=cmd_new)

    for name, help_text, func in [
        ("context", "Generate Gemini context artifact.", cmd_context),
        ("implement", "Generate Codex implementation artifacts.", cmd_implement),
        ("redteam", "Generate Grok Build red-team artifact.", cmd_redteam),
        ("summarize", "Generate Claude-only final summary.", cmd_summarize),
        ("final", "Generate Claude final decision.", cmd_final),
        ("judge", "Generate Claude final judge decision.", cmd_judge),
        ("run-demo", "Run the full mock workflow.", cmd_run_demo),
    ]:
        step = sub.add_parser(name, help=help_text)
        step.add_argument("task_id")
        step.add_argument("--mock", action="store_true", help="Use deterministic mock provider output.")
        step.add_argument("--real", action="store_true", help="Use the configured real adapter where supported.")
        step.add_argument(
            "--adapter",
            choices=["mock", "codex", "gemini", "grok", "claude"],
            help="Adapter name. Real mode supports gemini for context, codex for implement, grok for redteam, and claude for final.",
        )
        step.add_argument("--timeout", type=int, help="Adapter timeout in seconds.")
        step.add_argument("--dry-run", action="store_true", help="Force staged real adapter dry-run mode for this command.")
        if name == "run-demo":
            step.add_argument("--reset", action="store_true", help="Delete an existing task with this ID before running.")
        step.set_defaults(func=func)

    p = sub.add_parser("run-staged", help="Run the staged full workflow in dry-run orchestration mode.")
    p.add_argument("task_id")
    p.add_argument("--dry-run", action="store_true", help="Required. Keep orchestration in staged dry-run mode.")
    p.add_argument("--reset", action="store_true", help="Delete an existing task with this ID before running.")
    p.add_argument("--real", action="store_true", help="Enable one explicitly configured real adapter for its stage.")
    p.add_argument(
        "--adapter",
        choices=["mock", "codex", "gemini", "grok", "claude"],
        help="Single real adapter to exercise. All other stages remain mock.",
    )
    p.add_argument("--timeout", type=int, help="Adapter timeout in seconds for the selected real stage.")
    p.set_defaults(func=cmd_run_staged)

    p = sub.add_parser("status", help="Print task state and artifact presence.")
    p.add_argument("task_id")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("adapters", help="List supported adapters without executing them.")
    p.set_defaults(func=cmd_adapters)

    p = sub.add_parser("profiles", help="List provider profiles without executing providers.")
    p.add_argument("--name", help="Show one provider profile by name.")
    p.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    p.add_argument("--plan", action="store_true", help="Preview a selected profile's static execution plan.")
    p.add_argument("--audit", action="store_true", help="Audit the static profile plan contract.")
    p.set_defaults(func=cmd_profiles)

    p = sub.add_parser("objectives", help="Print static phase objective specs without executing providers.")
    p.add_argument("--phase", help="Show one objective phase. Default: P6-10.")
    p.add_argument("--show", help="Show one objective by id.")
    p.add_argument("--list", action="store_true", help="List defined objective phases.")
    p.add_argument("--validate", action="store_true", help="Validate the static objective registry.")
    p.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    p.set_defaults(func=cmd_objectives)

    p = sub.add_parser("plan", help="Build a static execution blueprint without executing providers.")
    p.add_argument("--objective", required=True, help="Objective id to plan, for example P6-10.")
    p.add_argument("--profile", required=True, help="Provider profile name to use for the static plan.")
    p.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    p.set_defaults(func=cmd_plan)


    p = sub.add_parser("packet", help="Build a static execution packet for an actor without executing providers.")
    p.add_argument("--objective", required=True, help="Objective id to package, for example P6-10.")
    p.add_argument("--profile", required=True, help="Provider profile name to use for the static packet.")
    p.add_argument("--actor", required=True, help="Packet actor: codex, reviewer, or judge.")
    p.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    p.add_argument("--validate", action="store_true", help="Validate the static packet contract without executing it.")
    p.set_defaults(func=cmd_packet)

    p = sub.add_parser("run-bundle", help="Build, inspect, validate, list, or check static local run bundles without executing providers.")
    p.add_argument("bundle_action", nargs="?", choices=["inspect", "validate", "list", "status"], help="Read-only bundle action.")
    p.add_argument("--objective", help="Objective id to bundle, for example P6-17.")
    p.add_argument("--profile", help="Provider profile name to use for the static bundle.")
    p.add_argument("--run-id", help="Static run bundle id.")
    p.add_argument("--out", help="Explicit output directory for writing the local bundle.")
    p.add_argument("--path", help="Static run bundle directory for inspect, validate, or status.")
    p.add_argument("--root", help="Static run bundle catalog root for list.")
    p.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    p.set_defaults(func=cmd_run_bundle)

    p = sub.add_parser("doctor", help="Check AgentOffice adapter configuration without executing real adapters.")
    p.add_argument("--adapter", choices=["mock", "codex", "gemini", "grok", "claude"], help="Limit adapter diagnostics to one adapter.")
    view = p.add_mutually_exclusive_group()
    view.add_argument("--adapters", action="store_true", help="Print staged adapter mode table only.")
    view.add_argument("--profiles", action="store_true", help="Print static profile plan audit only.")
    p.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    p.set_defaults(func=cmd_doctor)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except AgentOfficeError as exc:
        print(f"agent-office: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
