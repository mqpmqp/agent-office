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
from .framework_status import render_framework_status_json, render_framework_status_text
from .workspace_store import (
    WorkspaceStoreError,
    create_run,
    format_workspace_payload,
    init_workspace,
    inspect_workspace,
)
from .runtime_events import (
    RuntimeEventLogError,
    append_event,
    format_runtime_event_payload,
    list_events_payload,
)
from .task_graph import (
    TaskGraphError,
    create_goal_graph,
    format_task_graph_payload,
    ready_tasks_payload,
)
from .doctor import (
    bool_text,
    collect_doctor,
    collect_profile_plan_audit,
    doctor_json,
    format_adapters,
    format_doctor,
    format_profile_plan_audit,
)
from .artifact_registry import (
    export_evidence_payload,
    format_export_evidence,
    format_lifecycle_status,
    format_lifecycle_verify,
    format_registry_inspect,
    format_registry_list,
    format_registry_status,
    lifecycle_status_payload,
    lifecycle_verify_payload,
    registry_inspect_payload,
    registry_list_payload,
    registry_status_payload,
)
from .orchestration import (
    format_orchestrate_inspect,
    format_orchestrate_run,
    format_orchestrate_validate,
    orchestrate_inspect_payload,
    orchestrate_run_payload,
    orchestrate_validate_payload,
)
from .runtime_foundation import (
    RuntimeFoundationError,
    format_runtime_payload,
    runtime_close_payload,
    runtime_evidence_payload,
    runtime_error_payload,
    runtime_governance_payload,
    runtime_memory_payload,
    runtime_orchestrate_payload,
    runtime_parallel_payload,
    runtime_planner_payload,
    runtime_scheduler_payload,
    runtime_workspace_payload,
    runtime_init_payload,
    runtime_job_payload,
    runtime_packet_payload,
    runtime_plan_payload,
    runtime_replay_payload,
    runtime_run_payload,
    runtime_status_payload,
    runtime_worker_adapter_payload,
    runtime_worker_audit_closure_payload,
    runtime_worker_archive_index_payload,
    runtime_worker_archive_replay_verification_payload,
    runtime_worker_archive_verify_payload,
    runtime_worker_audit_replay_payload,
    runtime_worker_compact_archive_payload,
    runtime_worker_compact_archive_verify_payload,
    runtime_worker_closure_evidence_payload,
    runtime_worker_external_review_handoff_payload,
    runtime_worker_delivery_bundle_payload,
    runtime_worker_failed_review_recovery_payload,
    runtime_worker_final_delivery_readiness_payload,
    runtime_worker_delivery_gate_payload,
    runtime_worker_gate_payload,
    runtime_worker_invocation_packet_payload,
    runtime_worker_merge_readiness_payload,
    runtime_worker_provenance_manifest_payload,
    runtime_worker_provenance_replay_payload,
    runtime_worker_provenance_verify_payload,
    runtime_worker_rc_promotion_gate_payload,
    runtime_worker_release_candidate_export_payload,
    runtime_worker_promotion_evidence_payload,
    runtime_worker_dry_run_publish_payload,
    runtime_worker_rejection_packet_payload,
    runtime_worker_release_candidate_payload,
    runtime_worker_release_closure_payload,
    runtime_worker_result_intake_payload,
    runtime_worker_reviewer_archive_import_payload,
    runtime_worker_result_replay_payload,
    runtime_worker_reviewer_attestation_payload,
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
from .packet_result import (
    PacketResultError,
    emit_packet,
    format_actor_result_payload,
    format_packet_result_payload,
    intake_actor_result,
    list_actor_results_payload,
    list_packets_payload,
)
from .framework_runtime import (
    FrameworkRuntimeError,
    create_job_payload as framework_runtime_create_job_payload,
    dispatch_payload,
    evidence_payload as framework_runtime_evidence_payload,
    executor_loop_payload as framework_runtime_executor_loop_payload,
    executor_run_once_payload as framework_runtime_executor_run_once_payload,
    executor_status_payload as framework_runtime_executor_status_payload,
    format_framework_runtime_payload,
    inspect_payload as framework_runtime_inspect_payload,
    job_error_payload as framework_runtime_job_error_payload,
    judge_payload as framework_runtime_judge_payload,
    list_jobs_payload as framework_runtime_list_jobs_payload,
    list_runs_payload as framework_runtime_list_runs_payload,
    read_job_payload as framework_runtime_read_job_payload,
    replay_payload as framework_runtime_replay_payload,
    resume_payload as framework_runtime_resume_payload,
    review_payload as framework_runtime_review_payload,
    review_id_for_task,
    result_id_for_task,
    run_status_payload as framework_runtime_status_payload,
    transition_job_payload as framework_runtime_transition_job_payload,
    worker_contract_payload,
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
from .review_artifact import (
    ReviewArtifactError,
    close_pending_review_artifact_error_payload,
    close_pending_review_artifact_payload,
    export_review_artifact_payload,
    format_review_artifact_close_pending,
    format_review_artifact_export,
    format_review_artifact_self_check,
    review_artifact_error_payload,
    self_check_review_artifact_payload,
)
from . import review_lifecycle
from .run_bundle import (
    RunBundleError,
    export_review_error_payload,
    export_review_run_bundle_payload,
    format_actor_result_intake,
    format_run_bundle_catalog,
    format_run_bundle_gate,
    format_run_bundle_handoff,
    format_run_bundle_inspection,
    format_run_bundle_preview,
    format_run_bundle_review,
    format_run_bundle_results,
    format_run_bundle_status,
    format_run_bundle_validation,
    format_run_bundle_workflow,
    format_run_bundle_export_review,
    gate_run_bundle_payload,
    handoff_run_bundle_payload,
    inspect_run_bundle_payload,
    intake_actor_result_payload,
    list_run_bundles_payload,
    results_run_bundle_payload,
    review_run_bundle_payload,
    run_bundle_preview_payload,
    status_run_bundle_payload,
    validate_run_bundle_payload,
    workflow_run_bundle_payload,
    write_run_bundle,
)

from .v1_final_delivery import (
    V1FinalDeliveryError,
    build_final_delivery_packet,
    final_delivery_error_payload,
    format_final_delivery_packet,
    format_final_delivery_verify,
    verify_final_delivery_packet,
    write_final_delivery_packet,
)
from .v1_post_release_ops import (
    format_github_release_handoff,
    format_github_release_plan,
    format_github_release_readback_verify,
    format_post_v1_roadmap,
    format_release_archive_verify,
    format_release_candidate,
    format_release_state,
    github_release_handoff_payload,
    github_release_plan_payload,
    post_v1_roadmap_payload,
    release_candidate_payload,
    release_state_payload,
    verify_github_release_readback_payload,
    verify_release_archive_payload,
)
from .autonomy_executor import (
    classify_failure_payload,
    format_classification,
    format_goal_handoff,
    format_goal_report,
    format_goal_template,
    format_next,
    format_queue,
    format_queue_inspect,
    format_recovery_plan,
    format_runner,
    goal_handoff_payload,
    goal_report_payload,
    goal_template_payload,
    queue_add_payload,
    queue_init_payload,
    queue_inspect_payload,
    queue_next_payload,
    queue_status_payload,
    queue_validate_payload,
    recovery_plan_payload,
    resume_payload,
    run_goal_payload,
)
from .autonomy import (
    AutonomyError,
    autonomy_checkpoint_payload,
    autonomy_init_payload,
    autonomy_merge_packet_payload,
    autonomy_plan_payload,
    autonomy_report_payload,
    autonomy_review_packet_payload,
    autonomy_status_payload,
    autonomy_validate_payload,
    format_autonomy_ledger,
    format_autonomy_merge_packet,
    format_autonomy_plan,
    format_autonomy_review_packet,
    format_autonomy_validation,
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


def cmd_framework_status(args: argparse.Namespace) -> int:
    if args.json:
        print(render_framework_status_json())
    else:
        print(render_framework_status_text())
    return 0


def cmd_workspace(args: argparse.Namespace) -> int:
    root = Path(args.root)
    try:
        if args.workspace_action == "init":
            payload = init_workspace(root, args.workspace_id)
        elif args.workspace_action == "inspect":
            payload = inspect_workspace(root, args.workspace_id)
        elif args.workspace_action == "run-create":
            payload = create_run(root, args.workspace_id, args.run_id)
        else:
            raise AgentOfficeError("workspace requires init, inspect, or run-create.")
    except WorkspaceStoreError as exc:
        raise AgentOfficeError(str(exc)) from exc

    print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_workspace_payload(payload))
    return 0


def cmd_runtime_event(args: argparse.Namespace) -> int:
    root = Path(args.root)
    try:
        if args.runtime_event_action == "append":
            payload = append_event(root, args.workspace_id, args.run_id, args.event_type, args.actor)
        elif args.runtime_event_action == "list":
            payload = list_events_payload(root, args.workspace_id, args.run_id)
        else:
            raise AgentOfficeError("runtime-event requires append or list.")
    except RuntimeEventLogError as exc:
        raise AgentOfficeError(str(exc)) from exc

    print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_runtime_event_payload(payload))
    return 0


def cmd_task_graph(args: argparse.Namespace) -> int:
    root = Path(args.root)
    try:
        if args.task_graph_action == "create":
            payload = create_goal_graph(root, args.workspace_id, args.goal_id)
        elif args.task_graph_action == "ready":
            payload = ready_tasks_payload(root, args.workspace_id, args.goal_id)
        else:
            raise AgentOfficeError("task-graph requires create or ready.")
    except TaskGraphError as exc:
        raise AgentOfficeError(str(exc)) from exc

    print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_task_graph_payload(payload))
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
    action = getattr(args, "packet_action", None)
    if action:
        root = Path(args.root)
        try:
            if action == "emit":
                payload = emit_packet(root, args.workspace_id, args.run_id, args.goal_id, args.task_id)
            elif action == "list":
                payload = list_packets_payload(root, args.workspace_id, args.run_id)
            else:
                raise AgentOfficeError("packet requires emit, list, or legacy packet options.")
        except PacketResultError as exc:
            raise AgentOfficeError(str(exc)) from exc
        print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_packet_result_payload(payload))
        return 0

    for field in ("objective", "profile", "actor"):
        if getattr(args, field, None) is None:
            raise AgentOfficeError(f"packet legacy mode requires --{field.replace('_', '-')}. Use `packet emit` for framework packets.")

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


def cmd_actor_result(args: argparse.Namespace) -> int:
    root = Path(args.root)
    try:
        if args.actor_result_action == "intake":
            payload = intake_actor_result(root, args.workspace_id, args.run_id, args.packet_id, args.actor, args.status, args.summary)
        elif args.actor_result_action == "list":
            payload = list_actor_results_payload(root, args.workspace_id, args.run_id)
        else:
            raise AgentOfficeError("actor-result requires intake or list.")
    except PacketResultError as exc:
        raise AgentOfficeError(str(exc)) from exc

    print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_actor_result_payload(payload))
    return 0


def parse_key_value_metadata(items: list[str] | None) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for item in items or []:
        if "=" not in item:
            raise FrameworkRuntimeError("Job metadata must use KEY=VALUE entries.")
        key, value = item.split("=", 1)
        if not key:
            raise FrameworkRuntimeError("Job metadata key must not be empty.")
        metadata[key] = value
    return metadata


def cmd_framework_runtime(args: argparse.Namespace) -> int:
    action = args.framework_runtime_action
    job_action = getattr(args, "framework_runtime_job_action", None)
    executor_action = getattr(args, "framework_runtime_executor_action", None)
    try:
        if action == "workers":
            payload = worker_contract_payload()
        elif action == "dispatch":
            payload = dispatch_payload(Path(args.root), args.workspace_id, args.run_id, args.goal_id, args.task_id)
        elif action == "review":
            result_id = args.result_id or result_id_for_task(args.task_id)
            payload = framework_runtime_review_payload(Path(args.root), args.workspace_id, args.run_id, args.goal_id, result_id)
        elif action == "judge":
            review_id = args.review_id or review_id_for_task(args.task_id)
            payload = framework_runtime_judge_payload(Path(args.root), args.workspace_id, args.run_id, args.goal_id, review_id)
        elif action == "status":
            payload = framework_runtime_status_payload(Path(args.root), args.workspace_id, args.run_id, args.goal_id)
        elif action == "list":
            payload = framework_runtime_list_runs_payload(Path(args.root), args.workspace_id)
        elif action == "inspect":
            payload = framework_runtime_inspect_payload(Path(args.root), args.workspace_id, args.run_id, args.goal_id, args.task_id)
        elif action == "resume":
            payload = framework_runtime_resume_payload(Path(args.root), args.workspace_id, args.run_id, args.goal_id)
        elif action == "replay":
            payload = framework_runtime_replay_payload(Path(args.root), args.workspace_id, args.run_id)
        elif action == "evidence":
            payload = framework_runtime_evidence_payload(Path(args.root), args.workspace_id, args.run_id, args.goal_id, args.format)
        elif action == "executor":
            if executor_action == "run-once":
                payload = framework_runtime_executor_run_once_payload(Path(args.root), args.workspace_id, args.run_id, args.job_id)
            elif executor_action == "loop":
                payload = framework_runtime_executor_loop_payload(Path(args.root), args.workspace_id, args.run_id, args.max_iterations)
            elif executor_action == "status":
                payload = framework_runtime_executor_status_payload(Path(args.root), args.workspace_id, args.run_id)
            else:
                raise AgentOfficeError("framework-runtime executor requires a supported action.")
        elif action == "job":
            if job_action == "create":
                payload = framework_runtime_create_job_payload(
                    Path(args.root),
                    args.workspace_id,
                    args.run_id,
                    args.job_id,
                    args.objective,
                    parse_key_value_metadata(args.metadata),
                    args.evidence_ref,
                )
            elif job_action == "list":
                payload = framework_runtime_list_jobs_payload(Path(args.root), args.workspace_id, args.run_id)
            elif job_action == "show":
                payload = framework_runtime_read_job_payload(Path(args.root), args.workspace_id, args.run_id, args.job_id)
            elif job_action in {"cancel", "fail"}:
                payload = framework_runtime_transition_job_payload(Path(args.root), args.workspace_id, args.run_id, args.job_id, job_action, args.reason)
            else:
                raise AgentOfficeError("framework-runtime job requires a supported action.")
        else:
            raise AgentOfficeError("framework-runtime requires a supported action.")
    except FrameworkRuntimeError as exc:
        if action in {"job", "executor"} and getattr(args, "json", False):
            error_action = job_action if action == "job" else executor_action
            print(json.dumps(framework_runtime_job_error_payload(str(exc), error_action), indent=2, ensure_ascii=False))
            return 2
        raise AgentOfficeError(str(exc)) from exc

    print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_framework_runtime_payload(payload))
    return 0


def cmd_run_bundle(args: argparse.Namespace) -> int:
    action = getattr(args, "bundle_action", None)
    try:
        if action == "export-review":
            if not args.path or not args.out:
                error = "run-bundle export-review requires --path and --out."
                if args.json:
                    print(json.dumps(export_review_error_payload(args.path, args.out, error), indent=2, ensure_ascii=False))
                    return 2
                raise RunBundleError(error)
            try:
                payload = export_review_run_bundle_payload(args.path, args.out, PROJECT_ROOT)
            except RunBundleError as exc:
                if args.json:
                    print(json.dumps(export_review_error_payload(args.path, args.out, str(exc)), indent=2, ensure_ascii=False))
                    return 2
                raise
            print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_run_bundle_export_review(payload))
            return 0
        if action == "list":
            if not args.root:
                raise RunBundleError("run-bundle list requires --root.")
            payload = list_run_bundles_payload(args.root, PROJECT_ROOT)
            print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_run_bundle_catalog(payload))
            return 0
        if action == "handoff":
            if not args.path:
                raise RunBundleError("run-bundle handoff requires --path.")
            payload = handoff_run_bundle_payload(args.path, PROJECT_ROOT)
            print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_run_bundle_handoff(payload))
            return 0
        if action == "workflow":
            if not args.path:
                raise RunBundleError("run-bundle workflow requires --path.")
            payload = workflow_run_bundle_payload(args.path, PROJECT_ROOT)
            print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_run_bundle_workflow(payload))
            return 0 if payload["valid_bundle"] else 2
        if action == "gate":
            if not args.path:
                raise RunBundleError("run-bundle gate requires --path.")
            payload = gate_run_bundle_payload(args.path, PROJECT_ROOT)
            print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_run_bundle_gate(payload))
            return 0 if payload["valid_bundle"] else 2
        if action == "review":
            if not args.path:
                raise RunBundleError("run-bundle review requires --path.")
            payload = review_run_bundle_payload(args.path, PROJECT_ROOT)
            print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_run_bundle_review(payload))
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
        if action == "intake":
            if not args.path or not args.actor or not args.artifact:
                raise RunBundleError("run-bundle intake requires --path, --actor, and --artifact.")
            payload = intake_actor_result_payload(args.path, args.actor, args.artifact, PROJECT_ROOT)
            print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_actor_result_intake(payload))
            return 0
        if action == "results":
            if not args.path:
                raise RunBundleError("run-bundle results requires --path.")
            payload = results_run_bundle_payload(args.path, PROJECT_ROOT)
            print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_run_bundle_results(payload))
            return 0
        if action == "preview":
            if not args.objective or not args.profile:
                raise RunBundleError("run-bundle preview requires --objective and --profile.")
            run_id = args.run_id or args.objective
            allow_alias = True
        else:
            if not args.objective or not args.profile or not args.run_id:
                raise RunBundleError("run-bundle requires --objective, --profile, and --run-id.")
            run_id = args.run_id
            allow_alias = False
        payload = run_bundle_preview_payload(args.objective, args.profile, run_id, allow_alias=allow_alias)
        if args.out:
            payload = dict(payload)
            payload["write_result"] = write_run_bundle(payload, args.out, PROJECT_ROOT)
            payload["artifact_writes"] = True
    except RunBundleError as exc:
        raise AgentOfficeError(str(exc)) from exc
    print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_run_bundle_preview(payload))
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    action = args.review_action
    command = f"review {action}"
    try:
        if action == "preflight-status":
            payload = review_lifecycle.review_preflight_status_payload(project_root=PROJECT_ROOT)
        elif action == "bundle":
            payload = review_lifecycle.review_bundle_payload(
                baseline=args.baseline,
                head=args.head,
                branch=args.branch,
                report=args.report,
                out=args.out,
                prompt_out=args.prompt_out,
                title=args.title,
                bundle_marker=args.bundle_marker,
                review_marker=args.review_marker,
                focus=args.focus,
                project_root=PROJECT_ROOT,
                run_validation=args.run_validation,
                validation_fixture_dir=args.validation_fixture_dir,
                allow_dirty=args.allow_dirty,
                mkdirs=args.mkdirs,
            )
        elif action == "prompt":
            payload = review_lifecycle.review_prompt_payload(
                baseline=args.baseline,
                head=args.head,
                branch=args.branch,
                report=args.report,
                bundle=args.bundle,
                out=args.out,
                review_marker=args.review_marker,
                title=args.title,
                project_root=PROJECT_ROOT,
                mkdirs=args.mkdirs,
            )
        elif action == "attest":
            payload = review_lifecycle.review_attest_payload(
                review_report=args.review_report,
                expected_marker=args.expected_marker,
                expected_verdict=args.expected_verdict,
                out=args.out,
                mkdirs=args.mkdirs,
            )
        elif action == "merge-packet":
            payload = review_lifecycle.review_merge_packet_payload(
                baseline=args.baseline,
                source_branch=args.source_branch,
                source_commit=args.source_commit,
                implementation_report=args.implementation_report,
                review_bundle=args.review_bundle,
                review_attestation=args.review_attestation,
                out=args.out,
                merge_marker=args.merge_marker,
                project_root=PROJECT_ROOT,
                mkdirs=args.mkdirs,
            )
        elif action == "codex-gate":
            payload = review_lifecycle.review_codex_gate_payload(
                baseline=args.baseline,
                head=args.head,
                branch=args.branch,
                out=args.out,
                project_root=PROJECT_ROOT,
                allow_dirty=args.allow_dirty,
                mkdirs=args.mkdirs,
            )
        elif action == "reviewed-delivery":
            payload = review_lifecycle.review_reviewed_delivery_payload(
                source=args.source,
                target=args.target,
                expected_source_head=args.expected_source_head,
                expected_target_head=args.expected_target_head,
                implementation_report=args.implementation_report,
                review_bundle=args.review_bundle,
                review_report=args.review_report,
                expected_marker=args.expected_marker,
                expected_verdict=args.expected_verdict,
                out_dir=args.out_dir,
                project_root=PROJECT_ROOT,
                merge_marker=args.merge_marker,
                phase=args.phase,
                run_id=args.run_id,
                merge_authorized=args.merge_authorized,
                push_authorized=args.push_authorized,
                allow_dirty=args.allow_dirty,
                mkdirs=args.mkdirs,
                evidence_bundle_out=args.evidence_bundle_out,
                evidence_bundle_format=args.evidence_bundle_format,
            )
        elif action == "codex-deliver":
            payload = review_lifecycle.review_codex_deliver_payload(
                source=args.source,
                target=args.target,
                expected_source_head=args.expected_source_head,
                expected_target_head=args.expected_target_head,
                out=args.out,
                project_root=PROJECT_ROOT,
                phase=args.phase,
                run_id=args.run_id,
                merge_authorized=args.merge_authorized,
                push_authorized=args.push_authorized,
                allow_dirty=args.allow_dirty,
                mkdirs=args.mkdirs,
            )
        else:
            raise review_lifecycle.ReviewLifecycleError("review_unknown_action", "unknown review action", {"action": action})
    except review_lifecycle.ReviewLifecycleError as exc:
        payload = review_lifecycle.error_payload(command, exc)
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(review_lifecycle.format_error(payload), file=sys.stderr)
        return exc.exit_code
    except Exception as exc:
        safe = review_lifecycle.ReviewLifecycleError("review_unexpected_error", "unexpected review lifecycle error", {"type": type(exc).__name__})
        payload = review_lifecycle.error_payload(command, safe)
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(review_lifecycle.format_error(payload), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(review_lifecycle.format_merge_gate_preflight_status(payload) if action == "preflight-status" else review_lifecycle.format_review_lifecycle_success(payload))
    return 0


def cmd_review_artifact(args: argparse.Namespace) -> int:
    if args.review_artifact_action == "registry":
        action = args.registry_action
        roots = list(getattr(args, "root", []) or [])
        if action == "list":
            payload = registry_list_payload(project_root=PROJECT_ROOT, roots=roots)
            print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_registry_list(payload))
            return 0
        if action == "inspect":
            payload = registry_inspect_payload(path=args.path, project_root=PROJECT_ROOT)
            print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_registry_inspect(payload))
            return 0
        if action == "status":
            payload = registry_status_payload(project_root=PROJECT_ROOT, roots=roots)
            print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_registry_status(payload))
            return 0
        raise AgentOfficeError("review-artifact registry requires list, inspect, or status.")
    if args.review_artifact_action == "lifecycle":
        action = args.lifecycle_action
        roots = list(getattr(args, "root", []) or [])
        if action == "status":
            payload = lifecycle_status_payload(project_root=PROJECT_ROOT, roots=roots)
            print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_lifecycle_status(payload))
            return 0
        if action == "verify":
            payload = lifecycle_verify_payload(project_root=PROJECT_ROOT, roots=roots)
            print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_lifecycle_verify(payload))
            return 0
        raise AgentOfficeError("review-artifact lifecycle requires status or verify.")
    if args.review_artifact_action in {"self-check", "verify"}:
        payload = self_check_review_artifact_payload(artifact=args.artifact, sha256_path=args.sha256, project_root=PROJECT_ROOT)
        print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_review_artifact_self_check(payload))
        return 0 if payload["valid"] else 2
    if args.review_artifact_action == "close-pending":
        try:
            claude_attestation = args.claude_attestation or args.claude_review
            if not claude_attestation:
                raise ReviewArtifactError("missing Claude attestation: pass --claude-attestation")
            payload = close_pending_review_artifact_payload(
                artifact=args.artifact,
                sha256_path=args.sha256,
                claude_attestation=claude_attestation,
                out=args.out,
                project_root=PROJECT_ROOT,
                allow_fixture_attestation=args.allow_fixture_attestation,
                source_review_report=args.source_review_report,
            )
        except ReviewArtifactError as exc:
            if args.json:
                print(
                    json.dumps(
                        close_pending_review_artifact_error_payload(
                            artifact=args.artifact,
                            sha256_path=args.sha256,
                            claude_attestation=args.claude_attestation or args.claude_review,
                            out=args.out,
                            error=str(exc),
                            source_review_report=args.source_review_report,
                            allow_fixture_attestation=args.allow_fixture_attestation,
                        ),
                        indent=2,
                        ensure_ascii=False,
                    )
                )
                return 2
            raise AgentOfficeError(str(exc)) from exc
        print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_review_artifact_close_pending(payload))
        return 0
    if args.review_artifact_action != "export":
        raise AgentOfficeError("review-artifact requires the export, self-check, verify, or close-pending action.")
    try:
        payload = export_review_artifact_payload(
            base=args.base,
            review=args.review,
            branch=args.branch,
            out=args.out,
            title=args.title,
            project_root=PROJECT_ROOT,
            gate_mode=args.gate_mode,
            claude_review_status=args.claude_status,
            codex_self_check_status=args.codex_self_check_status,
        )
    except ReviewArtifactError as exc:
        if args.json:
            print(
                json.dumps(
                    review_artifact_error_payload(base=args.base, review=args.review, branch=args.branch, out=args.out, title=args.title, error=str(exc)),
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 2
        raise AgentOfficeError(str(exc)) from exc
    print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_review_artifact_export(payload))
    return 0


def cmd_export_evidence(args: argparse.Namespace) -> int:
    try:
        payload = export_evidence_payload(out=args.out, project_root=PROJECT_ROOT, roots=list(args.root or []))
    except ValueError as exc:
        if args.json:
            print(json.dumps({"valid": False, "command": "export-evidence", "warnings": [], "errors": [str(exc)]}, indent=2, ensure_ascii=False))
            return 2
        raise AgentOfficeError(str(exc)) from exc
    print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_export_evidence(payload))
    return 0 if payload["valid"] else 1


def cmd_orchestrate(args: argparse.Namespace) -> int:
    action = args.orchestrate_action
    if action == "run":
        payload = orchestrate_run_payload(task=args.task, mode=args.mode, out=args.out)
        print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_orchestrate_run(payload))
        return 0 if payload["valid"] else 2
    if action == "inspect":
        payload = orchestrate_inspect_payload(path=args.path)
        print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_orchestrate_inspect(payload))
        return 0 if payload["valid"] else 2
    if action == "validate":
        payload = orchestrate_validate_payload(path=args.path)
        print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_orchestrate_validate(payload))
        return 0 if payload["valid"] else 2
    raise AgentOfficeError("orchestrate requires run, inspect, or validate.")


def cmd_runtime(args: argparse.Namespace) -> int:
    action = args.runtime_action
    command = f"runtime {action}"
    if action == "job" and getattr(args, "job_action", None):
        command = f"runtime job {args.job_action}"
    if action == "worker-result" and getattr(args, "worker_result_action", None):
        command = f"runtime worker-result {args.worker_result_action}"
    if action == "workspace" and getattr(args, "workspace_action", None):
        command = f"runtime workspace {args.workspace_action}"
    if action == "memory" and getattr(args, "memory_action", None):
        command = f"runtime memory {args.memory_action}"
    try:
        if action == "init":
            payload = runtime_init_payload(workspace=args.workspace, goal=args.goal, project_root=PROJECT_ROOT)
        elif action == "plan":
            payload = runtime_plan_payload(workspace=args.workspace, tasks=list(args.task or []), depends=list(args.depends or []), project_root=PROJECT_ROOT)
        elif action == "run":
            payload = runtime_run_payload(
                workspace=args.workspace,
                adapter=args.adapter,
                dry_run=bool(args.dry_run),
                execute_local=bool(args.execute_local),
                reset=bool(args.reset),
                project_root=PROJECT_ROOT,
            )
        elif action == "status":
            payload = runtime_status_payload(workspace=args.workspace, project_root=PROJECT_ROOT)
        elif action == "packet":
            payload = runtime_packet_payload(workspace=args.workspace, project_root=PROJECT_ROOT)
        elif action == "replay":
            payload = runtime_replay_payload(workspace=args.workspace, project_root=PROJECT_ROOT)
        elif action == "evidence":
            payload = runtime_evidence_payload(workspace=args.workspace, out=args.out, evidence_format=args.format, project_root=PROJECT_ROOT)
        elif action in {"close", "closure-packet"}:
            payload = runtime_close_payload(workspace=args.workspace, out=args.out, project_root=PROJECT_ROOT)
        elif action == "governance":
            payload = runtime_governance_payload(workspace=args.workspace, closure_packet=args.closure_packet, evidence_out=args.evidence_out, evidence_format=args.format, project_root=PROJECT_ROOT)
        elif action == "workspace":
            payload = runtime_workspace_payload(action=args.workspace_action, workspace=args.workspace, run_id=getattr(args, "run_id", None), out=getattr(args, "out", None), project_root=PROJECT_ROOT)
        elif action == "memory":
            payload = runtime_memory_payload(
                action=args.memory_action,
                workspace=args.workspace,
                project_root=PROJECT_ROOT,
                memory_id=getattr(args, "memory_id", None),
                goal_id=getattr(args, "goal_id", None),
                agent_role=getattr(args, "agent_role", None),
                kind=getattr(args, "kind", None),
                content=getattr(args, "content", None),
                summary=getattr(args, "summary", None),
                source_command=getattr(args, "source_command", None),
                source_artifact=getattr(args, "source_artifact", None),
                run_id=getattr(args, "run_id", None),
            )
        elif action == "scheduler":
            payload = runtime_scheduler_payload(workspace=args.workspace, project_root=PROJECT_ROOT, dry_run=True)
        elif action == "planner":
            payload = runtime_planner_payload(workspace=args.workspace, objective=args.objective, explain=bool(args.explain), project_root=PROJECT_ROOT)
        elif action == "parallel":
            payload = runtime_parallel_payload(workspace=args.workspace, max_workers=args.max_workers, project_root=PROJECT_ROOT, dry_run=True, fail_goal=list(args.fail_goal or []))
        elif action == "orchestrate":
            payload = runtime_orchestrate_payload(workspace=args.workspace, objective=getattr(args, "objective", None), run_id=getattr(args, "run_id", None), max_workers=args.max_workers, dry_run=True, resume=bool(args.resume), project_root=PROJECT_ROOT)
        elif action == "job":
            payload = runtime_job_payload(action=args.job_action, workspace=args.workspace, job_id=getattr(args, "job_id", None), reason=getattr(args, "reason", None), project_root=PROJECT_ROOT)
        elif action == "worker-adapter":
            payload = runtime_worker_adapter_payload(list_adapters=bool(args.list_adapters), name=args.name, describe=bool(args.describe))
        elif action == "worker-gate":
            payload = runtime_worker_gate_payload(workspace=args.workspace, adapter=args.adapter, project_root=PROJECT_ROOT)
        elif action == "worker-packet":
            payload = runtime_worker_invocation_packet_payload(workspace=args.workspace, adapter=args.adapter, job_id=args.job_id, out=args.out, packet_format=args.format, project_root=PROJECT_ROOT)
        elif action == "worker-result" and args.worker_result_action == "intake":
            payload = runtime_worker_result_intake_payload(workspace=args.workspace, packet=args.packet, result=args.result, project_root=PROJECT_ROOT)
        elif action == "worker-result" and args.worker_result_action == "replay":
            payload = runtime_worker_result_replay_payload(workspace=args.workspace, packet=args.packet, result=args.result, project_root=PROJECT_ROOT)
        elif action == "worker-result" and args.worker_result_action == "audit-closure":
            payload = runtime_worker_audit_closure_payload(workspace=args.workspace, packet=args.packet, result=args.result, out=args.out, closure_format=args.format, project_root=PROJECT_ROOT)
        elif action == "worker-result" and args.worker_result_action == "delivery-bundle":
            payload = runtime_worker_delivery_bundle_payload(workspace=args.workspace, packet=args.packet, result=args.result, audit_closure=args.audit_closure, out=args.out, bundle_format=args.format, project_root=PROJECT_ROOT)
        elif action == "worker-result" and args.worker_result_action == "reviewer-attestation":
            payload = runtime_worker_reviewer_attestation_payload(reviewer_artifact=args.reviewer_artifact, expected_marker=args.marker, out=args.out, attestation_format=args.format, project_root=PROJECT_ROOT)
        elif action == "worker-result" and args.worker_result_action == "closure-evidence":
            payload = runtime_worker_closure_evidence_payload(reviewer_attestation=args.reviewer_attestation, out=args.out, evidence_format=args.format, project_root=PROJECT_ROOT)
        elif action == "worker-result" and args.worker_result_action == "merge-readiness":
            payload = runtime_worker_merge_readiness_payload(
                delivery_bundle=args.delivery_bundle,
                reviewer_attestation=args.reviewer_attestation,
                closure_evidence=args.closure_evidence,
                baseline=args.baseline,
                source_branch=args.source_branch,
                source_head=args.source_head,
                target_branch=args.target_branch,
                out=args.out,
                readiness_format=args.format,
                project_root=PROJECT_ROOT,
            )
        elif action == "worker-result" and args.worker_result_action == "delivery-gate":
            payload = runtime_worker_delivery_gate_payload(merge_readiness=args.merge_readiness, out=args.out, gate_format=args.format, project_root=PROJECT_ROOT)
        elif action == "worker-result" and args.worker_result_action == "rejection-packet":
            payload = runtime_worker_rejection_packet_payload(delivery_gate=args.delivery_gate, out=args.out, rejection_format=args.format, project_root=PROJECT_ROOT)
        elif action == "worker-result" and args.worker_result_action == "audit-replay":
            payload = runtime_worker_audit_replay_payload(packet=args.packet, out=args.out, replay_format=args.format, project_root=PROJECT_ROOT)
        elif action == "worker-result" and args.worker_result_action == "provenance-manifest":
            payload = runtime_worker_provenance_manifest_payload(
                reviewer_attestation=args.reviewer_attestation,
                closure_evidence=args.closure_evidence,
                merge_readiness=args.merge_readiness,
                delivery_gate=args.delivery_gate,
                rejection_packet=args.rejection_packet,
                audit_replay=args.audit_replay,
                out=args.out,
                manifest_format=args.format,
                project_root=PROJECT_ROOT,
            )
        elif action == "worker-result" and args.worker_result_action == "provenance-verify":
            payload = runtime_worker_provenance_verify_payload(manifest=args.manifest, project_root=PROJECT_ROOT)
        elif action == "worker-result" and args.worker_result_action == "provenance-replay":
            payload = runtime_worker_provenance_replay_payload(manifest=args.manifest, project_root=PROJECT_ROOT)
        elif action == "worker-result" and args.worker_result_action == "release-candidate":
            payload = runtime_worker_release_candidate_payload(provenance_manifest=args.provenance_manifest, out=args.out, package_format=args.format, review_target=args.review_target, project_root=PROJECT_ROOT)
        elif action == "worker-result" and args.worker_result_action == "external-review-handoff":
            payload = runtime_worker_external_review_handoff_payload(
                release_candidate=args.release_candidate,
                out=args.out,
                handoff_format=args.format,
                review_target=args.review_target,
                expected_marker=args.expected_marker,
                attestation_import_path=args.attestation_import_path,
                project_root=PROJECT_ROOT,
            )
        elif action == "worker-result" and args.worker_result_action == "archive-index":
            payload = runtime_worker_archive_index_payload(release_candidate=args.release_candidate, external_review_handoff=args.external_review_handoff, out=args.out, index_format=args.format, project_root=PROJECT_ROOT)
        elif action == "worker-result" and args.worker_result_action == "archive-verify":
            payload = runtime_worker_archive_verify_payload(index=args.index, project_root=PROJECT_ROOT)
        elif action == "worker-result" and args.worker_result_action == "reviewer-archive-import":
            payload = runtime_worker_reviewer_archive_import_payload(reviewer_output=args.reviewer_output, archive_index=args.archive_index, expected_marker=args.expected_marker, out=args.out, import_format=args.format, project_root=PROJECT_ROOT)
        elif action == "worker-result" and args.worker_result_action == "release-closure":
            payload = runtime_worker_release_closure_payload(release_candidate=args.release_candidate, external_review_handoff=args.external_review_handoff, archive_index=args.archive_index, reviewer_import=args.reviewer_import, provenance_manifest=args.provenance_manifest, out=args.out, closure_format=args.format, project_root=PROJECT_ROOT)
        elif action == "worker-result" and args.worker_result_action == "archive-replay":
            payload = runtime_worker_archive_replay_verification_payload(archive_index=args.archive_index, release_candidate=args.release_candidate, closure_bundle=args.release_closure, out=args.out, replay_format=args.format, project_root=PROJECT_ROOT)
        elif action == "worker-result" and args.worker_result_action == "final-readiness":
            payload = runtime_worker_final_delivery_readiness_payload(closure_bundle=args.release_closure, archive_replay=args.archive_replay, out=args.out, readiness_format=args.format, project_root=PROJECT_ROOT)
        elif action == "worker-result" and args.worker_result_action == "review-recovery":
            payload = runtime_worker_failed_review_recovery_payload(closure_bundle=args.release_closure, out=args.out, recovery_format=args.format, project_root=PROJECT_ROOT)
        elif action == "worker-result" and args.worker_result_action == "compact-archive":
            payload = runtime_worker_compact_archive_payload(archive_index=args.archive_index, release_closure=args.release_closure, archive_replay=args.archive_replay, final_readiness=args.final_readiness, out=args.out, compact_format=args.format, project_root=PROJECT_ROOT)
        elif action == "worker-result" and args.worker_result_action == "compact-verify":
            payload = runtime_worker_compact_archive_verify_payload(compact_index=args.index, project_root=PROJECT_ROOT)
        elif action == "worker-result" and args.worker_result_action == "rc-promotion-gate":
            payload = runtime_worker_rc_promotion_gate_payload(final_readiness=args.final_readiness, compact_index=args.compact_index, release_closure=args.release_closure, out=args.out, gate_format=args.format, project_root=PROJECT_ROOT)
        elif action == "worker-result" and args.worker_result_action == "release-candidate-export":
            payload = runtime_worker_release_candidate_export_payload(release_candidate=args.release_candidate, archive_index=args.archive_index, out=args.out, export_format=args.format, project_root=PROJECT_ROOT)
        elif action == "worker-result" and args.worker_result_action == "promotion-evidence":
            payload = runtime_worker_promotion_evidence_payload(
                release_candidate=args.release_candidate,
                archive_index=args.archive_index,
                release_closure=args.release_closure,
                archive_replay=args.archive_replay,
                final_readiness=args.final_readiness,
                compact_index=args.compact_index,
                promotion_gate=args.promotion_gate,
                out=args.out,
                evidence_format=args.format,
                final_mainline=args.final_mainline,
                project_root=PROJECT_ROOT,
            )
        elif action == "worker-result" and args.worker_result_action == "dry-run-publish":
            payload = runtime_worker_dry_run_publish_payload(
                promotion_evidence=args.promotion_evidence,
                release_candidate_export=args.release_candidate_export,
                promotion_gate=args.promotion_gate,
                out=args.out,
                publish_format=args.format,
                candidate_name=args.candidate_name,
                target_branch=args.target_branch,
                target_commit=args.target_commit,
                project_root=PROJECT_ROOT,
            )
        else:
            raise RuntimeFoundationError("runtime_unknown_action", "unknown runtime action")
    except RuntimeFoundationError as exc:
        payload = runtime_error_payload(command, exc)
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            raise AgentOfficeError(str(exc)) from exc
        return 2
    print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_runtime_payload(payload))
    if action == "replay":
        return 0 if payload["replay_valid"] else 2
    if action in {"close", "closure-packet"}:
        return 0 if payload["closure_packet_valid"] else 2
    if action == "governance":
        return 0 if payload["runtime_governance_ready"] else 2
    if action == "worker-result" and getattr(args, "worker_result_action", None) == "provenance-verify":
        return 0 if payload["chain_valid"] else 2
    if action == "worker-result" and getattr(args, "worker_result_action", None) == "provenance-replay":
        return 0 if payload["chain_replay_ready"] else 2
    if action == "worker-result" and getattr(args, "worker_result_action", None) == "archive-verify":
        return 0 if payload["archive_valid"] else 2
    if action == "worker-result" and getattr(args, "worker_result_action", None) == "release-closure":
        return 0 if payload["delivery_ready"] else 2
    if action == "worker-result" and getattr(args, "worker_result_action", None) == "archive-replay":
        return 0 if payload["archive_replay_valid"] else 2
    if action == "worker-result" and getattr(args, "worker_result_action", None) == "final-readiness":
        return 0 if payload["delivery_ready"] else 2
    if action == "worker-result" and getattr(args, "worker_result_action", None) == "compact-verify":
        return 0 if payload["compact_valid"] else 2
    if action == "worker-result" and getattr(args, "worker_result_action", None) == "rc-promotion-gate":
        return 0 if payload["promotion_ready"] else 2
    if action == "worker-result" and getattr(args, "worker_result_action", None) == "release-candidate-export":
        return 0 if payload["export_ready"] else 2
    if action == "worker-result" and getattr(args, "worker_result_action", None) == "promotion-evidence":
        return 0 if payload["evidence_ready"] else 2
    if action == "worker-result" and getattr(args, "worker_result_action", None) == "dry-run-publish":
        return 0 if payload["publish_ready"] else 2
    if action in {"workspace", "memory", "scheduler", "planner", "parallel", "orchestrate"}:
        return 0 if payload.get("ok", False) else 2
    return 0


def cmd_autonomy(args: argparse.Namespace) -> int:
    action = args.autonomy_action
    try:
        if action == "plan":
            payload = autonomy_plan_payload(args.goal)
            print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_autonomy_plan(payload))
            return 0
        if action == "init":
            payload = autonomy_init_payload(args.path, args.goal, PROJECT_ROOT)
            print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_autonomy_ledger(payload))
            return 0
        if action == "status":
            payload = autonomy_status_payload(args.path, PROJECT_ROOT)
            print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_autonomy_ledger(payload))
            return 0
        if action == "checkpoint":
            payload = autonomy_checkpoint_payload(args.path, args.name, args.status, PROJECT_ROOT)
            print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_autonomy_ledger(payload))
            return 0
        if action == "report":
            payload = autonomy_report_payload(args.path, PROJECT_ROOT)
            print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_autonomy_ledger(payload))
            return 0
        if action == "validate":
            payload = autonomy_validate_payload(args.path, args.suite, PROJECT_ROOT)
            print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_autonomy_validation(payload))
            return 0 if payload["ok"] else 2
        if action == "review-packet":
            payload = autonomy_review_packet_payload(args.base, args.head, args.out, PROJECT_ROOT)
            print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_autonomy_review_packet(payload))
            return 0
        if action == "merge-packet":
            payload = autonomy_merge_packet_payload(args.source, args.target, PROJECT_ROOT)
            print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_autonomy_merge_packet(payload))
            return 0
        if action == "queue":
            queue_action = args.queue_action
            if queue_action == "init":
                payload = queue_init_payload(args.path, args.goal, args.template, PROJECT_ROOT)
                print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_queue(payload))
                return 0
            if queue_action == "add":
                payload = queue_add_payload(
                    args.path,
                    args.id,
                    args.kind,
                    PROJECT_ROOT,
                    suite=args.suite,
                    depends_on=args.depends_on or [],
                    max_attempts=args.max_attempts,
                    base=args.base,
                    head=args.head,
                    source=args.source,
                    target=args.target,
                    out=args.out,
                )
                print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_queue(payload))
                return 0
            if queue_action == "status":
                payload = queue_status_payload(args.path, PROJECT_ROOT)
                print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_queue(payload))
                return 0
            if queue_action == "validate":
                payload = queue_validate_payload(args.path, PROJECT_ROOT)
                print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_queue(payload))
                return 0 if payload["ok"] else 2
            if queue_action == "next":
                payload = queue_next_payload(args.path, PROJECT_ROOT)
                print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_next(payload))
                return 0 if payload["ok"] else 2
            if queue_action == "inspect":
                payload = queue_inspect_payload(args.path, PROJECT_ROOT, ledger_limit=args.ledger_limit)
                print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_queue_inspect(payload))
                return 0 if payload["ok"] else 2
        if action == "run-goal":
            payload = run_goal_payload(args.path, args.max_steps, PROJECT_ROOT)
            print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_runner(payload))
            return 0 if payload["ok"] else 2
        if action == "resume":
            payload = resume_payload(args.path, args.max_steps, PROJECT_ROOT, retry_failed=args.retry_failed)
            print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_runner(payload))
            return 0 if payload["ok"] else 2
        if action == "recover-plan":
            payload = recovery_plan_payload(args.path, args.max_steps, PROJECT_ROOT, retry_failed=args.retry_failed, ledger_limit=args.ledger_limit)
            print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_recovery_plan(payload))
            return 0 if payload["ok"] else 2
        if action == "classify":
            payload = classify_failure_payload(args.kind, args.attempts, args.max_attempts)
            print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_classification(payload))
            return 0 if payload["ok"] else 2
        if action == "goal-template":
            payload = goal_template_payload(args.name)
            print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_goal_template(payload))
            return 0
        if action == "goal-report":
            payload = goal_report_payload(args.path, args.out, PROJECT_ROOT)
            print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_goal_report(payload))
            return 0
        if action == "goal-handoff":
            payload = goal_handoff_payload(args.path, args.out, PROJECT_ROOT, ledger_limit=args.ledger_limit)
            print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_goal_handoff(payload))
            return 0 if payload["ok"] else 2
    except AutonomyError as exc:
        raise AgentOfficeError(str(exc)) from exc
    raise AgentOfficeError("autonomy requires plan, init, status, checkpoint, report, validate, review-packet, merge-packet, queue, run-goal, resume, recover-plan, classify, goal-template, goal-report, or goal-handoff.")


def cmd_v1(args: argparse.Namespace) -> int:
    action = args.v1_action
    if action == "final-delivery":
        try:
            packet = build_final_delivery_packet(PROJECT_ROOT)
            if args.out:
                write_final_delivery_packet(args.out, packet, PROJECT_ROOT)
        except V1FinalDeliveryError as exc:
            if args.json:
                print(json.dumps(final_delivery_error_payload("v1 final-delivery", exc), indent=2, ensure_ascii=False))
                return 2
            raise AgentOfficeError(str(exc)) from exc
        print(json.dumps(packet, indent=2, ensure_ascii=False) if args.json else format_final_delivery_packet(packet))
        return 0
    if action == "verify-final-delivery":
        payload = verify_final_delivery_packet(args.path, PROJECT_ROOT)
        print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_final_delivery_verify(payload))
        return 0 if payload["ok"] else 2
    if action == "verify-release-archive":
        payload = verify_release_archive_payload(args.archive, args.sha256)
        print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_release_archive_verify(payload))
        return 0 if payload["ok"] else 2
    if action == "verify-github-release-readback":
        payload = verify_github_release_readback_payload(args.dir)
        print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_github_release_readback_verify(payload))
        return 0 if payload["ok"] else 2
    if action == "post-v1-roadmap":
        payload = post_v1_roadmap_payload()
        print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_post_v1_roadmap(payload))
        return 0
    if action == "release-state":
        payload = release_state_payload()
        print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_release_state(payload))
        return 0
    if action == "github-release-handoff":
        payload = github_release_handoff_payload()
        print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_github_release_handoff(payload))
        return 0
    if action == "github-release-plan":
        payload = github_release_plan_payload()
        print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_github_release_plan(payload))
        return 0
    if action == "release-candidate":
        payload = release_candidate_payload(args.version)
        print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_release_candidate(payload))
        return 0 if payload["ok"] else 2
    raise AgentOfficeError("v1 requires final-delivery, verify-final-delivery, verify-release-archive, verify-github-release-readback, post-v1-roadmap, release-state, github-release-handoff, github-release-plan, or release-candidate.")


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


def _add_review_artifact_check_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--artifact", required=True, help="Markdown artifact path to verify.")
    parser.add_argument("--sha256", required=True, help="SHA256 sidecar path to verify from its own directory.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")


def _add_repeatable_root_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", action="append", default=[], help="Repeatable artifact scan root. When set, default locations are not scanned.")


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

    p = sub.add_parser("framework-status", help="Print the FUGU-like framework reset contract without provider calls or env reads.")
    p.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    p.set_defaults(func=cmd_framework_status)

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


    p = sub.add_parser("packet", help="Build legacy static packets or framework task packets without executing providers.")
    p.add_argument("--objective", help="Legacy packet objective id, for example P6-10.")
    p.add_argument("--profile", help="Legacy provider profile name to use for the static packet.")
    p.add_argument("--actor", help="Legacy packet actor: codex, reviewer, or judge.")
    p.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    p.add_argument("--validate", action="store_true", help="Validate the legacy static packet contract without executing it.")
    packet_sub = p.add_subparsers(dest="packet_action")
    packet_emit = packet_sub.add_parser("emit", help="Emit one framework task packet from an existing task graph.")
    packet_emit.add_argument("--workspace-id", required=True, help="Stable workspace id.")
    packet_emit.add_argument("--run-id", required=True, help="Stable run id.")
    packet_emit.add_argument("--goal-id", required=True, help="Stable goal id.")
    packet_emit.add_argument("--task-id", required=True, help="Stable task id from the task graph.")
    packet_emit.add_argument("--root", required=True, help="Root directory that contains the .ai/workspaces store.")
    packet_emit.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    packet_emit.set_defaults(func=cmd_packet)
    packet_list = packet_sub.add_parser("list", help="List framework task packets stored under a run.")
    packet_list.add_argument("--workspace-id", required=True, help="Stable workspace id.")
    packet_list.add_argument("--run-id", required=True, help="Stable run id.")
    packet_list.add_argument("--root", required=True, help="Root directory that contains the .ai/workspaces store.")
    packet_list.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    packet_list.set_defaults(func=cmd_packet)
    p.set_defaults(func=cmd_packet)

    p = sub.add_parser("actor-result", help="Intake and list framework actor results without provider execution.")
    actor_result_sub = p.add_subparsers(dest="actor_result_action", required=True)
    actor_result_intake = actor_result_sub.add_parser("intake", help="Store one actor result for an emitted framework packet.")
    actor_result_intake.add_argument("--workspace-id", required=True, help="Stable workspace id.")
    actor_result_intake.add_argument("--run-id", required=True, help="Stable run id.")
    actor_result_intake.add_argument("--packet-id", required=True, help="Stable packet id to attach the result to.")
    actor_result_intake.add_argument("--actor", required=True, help="Stable actor name, for example manual.")
    actor_result_intake.add_argument("--status", required=True, help="Stable result status, for example completed.")
    actor_result_intake.add_argument("--summary", required=True, help="Short result summary.")
    actor_result_intake.add_argument("--root", required=True, help="Root directory that contains the .ai/workspaces store.")
    actor_result_intake.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    actor_result_intake.set_defaults(func=cmd_actor_result)
    actor_result_list = actor_result_sub.add_parser("list", help="List actor results stored under a run.")
    actor_result_list.add_argument("--workspace-id", required=True, help="Stable workspace id.")
    actor_result_list.add_argument("--run-id", required=True, help="Stable run id.")
    actor_result_list.add_argument("--root", required=True, help="Root directory that contains the .ai/workspaces store.")
    actor_result_list.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    actor_result_list.set_defaults(func=cmd_actor_result)

    p = sub.add_parser("framework-runtime", help="Run the deterministic framework runtime trunk without providers or external adapters.")
    framework_runtime_sub = p.add_subparsers(dest="framework_runtime_action", required=True)
    framework_runtime_workers = framework_runtime_sub.add_parser("workers", help="List local framework runtime worker adapter contracts.")
    framework_runtime_workers.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    framework_runtime_workers.set_defaults(func=cmd_framework_runtime)

    def add_framework_runtime_run_args(parser: argparse.ArgumentParser, *, goal: bool = True) -> None:
        parser.add_argument("--workspace-id", required=True, help="Stable workspace id.")
        parser.add_argument("--run-id", required=True, help="Stable run id.")
        if goal:
            parser.add_argument("--goal-id", required=True, help="Stable goal id.")
        parser.add_argument("--root", required=True, help="Root directory that contains the .ai/workspaces store.")
        parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    framework_runtime_dispatch = framework_runtime_sub.add_parser("dispatch", help="Dispatch one ready task to the local deterministic worker.")
    add_framework_runtime_run_args(framework_runtime_dispatch)
    framework_runtime_dispatch.add_argument("--task-id", help="Ready task id to dispatch. Defaults to the first ready task.")
    framework_runtime_dispatch.set_defaults(func=cmd_framework_runtime)

    framework_runtime_review = framework_runtime_sub.add_parser("review", help="Intake a deterministic local review stub for an actor result.")
    add_framework_runtime_run_args(framework_runtime_review)
    review_selector = framework_runtime_review.add_mutually_exclusive_group(required=True)
    review_selector.add_argument("--result-id", help="Actor result id to review.")
    review_selector.add_argument("--task-id", help="Task id whose actor result should be reviewed.")
    framework_runtime_review.set_defaults(func=cmd_framework_runtime)

    framework_runtime_judge = framework_runtime_sub.add_parser("judge", help="Intake a deterministic local judge stub for a review result.")
    add_framework_runtime_run_args(framework_runtime_judge)
    judge_selector = framework_runtime_judge.add_mutually_exclusive_group(required=True)
    judge_selector.add_argument("--review-id", help="Review id to judge.")
    judge_selector.add_argument("--task-id", help="Task id whose review should be judged.")
    framework_runtime_judge.set_defaults(func=cmd_framework_runtime)

    for runtime_action in ("status", "resume"):
        runtime_parser = framework_runtime_sub.add_parser(runtime_action, help=f"Framework runtime {runtime_action} for one run/goal.")
        add_framework_runtime_run_args(runtime_parser)
        runtime_parser.set_defaults(func=cmd_framework_runtime)

    framework_runtime_inspect = framework_runtime_sub.add_parser("inspect", help="Inspect one framework runtime run or task.")
    add_framework_runtime_run_args(framework_runtime_inspect)
    framework_runtime_inspect.add_argument("--task-id", help="Optional task id to inspect.")
    framework_runtime_inspect.set_defaults(func=cmd_framework_runtime)

    framework_runtime_list = framework_runtime_sub.add_parser("list", help="List framework runtime run/goal completeness for a workspace.")
    framework_runtime_list.add_argument("--workspace-id", required=True, help="Stable workspace id.")
    framework_runtime_list.add_argument("--root", required=True, help="Root directory that contains the .ai/workspaces store.")
    framework_runtime_list.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    framework_runtime_list.set_defaults(func=cmd_framework_runtime)

    framework_runtime_replay = framework_runtime_sub.add_parser("replay", help="Replay-read the framework runtime event log for one run.")
    add_framework_runtime_run_args(framework_runtime_replay, goal=False)
    framework_runtime_replay.set_defaults(func=cmd_framework_runtime)

    framework_runtime_evidence = framework_runtime_sub.add_parser("evidence", help="Export framework runtime run/task/packet/result/review/judge evidence.")
    add_framework_runtime_run_args(framework_runtime_evidence)
    framework_runtime_evidence.add_argument("--format", choices=["json", "text"], default="json", help="Evidence artifact format. Default: json.")
    framework_runtime_evidence.set_defaults(func=cmd_framework_runtime)

    framework_runtime_executor = framework_runtime_sub.add_parser("executor", help="Run the local deterministic framework runtime executor loop.")
    framework_runtime_executor_sub = framework_runtime_executor.add_subparsers(dest="framework_runtime_executor_action", required=True)

    def add_framework_runtime_executor_run_args(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--workspace-id", required=True, help="Stable workspace id.")
        parser.add_argument("--run-id", required=True, help="Stable run id.")
        parser.add_argument("--root", required=True, help="Root directory that contains the .ai/workspaces store.")
        parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    framework_runtime_executor_run_once = framework_runtime_executor_sub.add_parser("run-once", help="Run one pending local job through the deterministic stub executor.")
    add_framework_runtime_executor_run_args(framework_runtime_executor_run_once)
    framework_runtime_executor_run_once.add_argument("--job-id", help="Optional job id to run. Defaults to the first pending job.")
    framework_runtime_executor_run_once.set_defaults(func=cmd_framework_runtime)

    framework_runtime_executor_loop = framework_runtime_executor_sub.add_parser("loop", help="Run pending local jobs until drained or max iterations is reached.")
    add_framework_runtime_executor_run_args(framework_runtime_executor_loop)
    framework_runtime_executor_loop.add_argument("--max-iterations", type=int, default=100, help="Maximum run-once iterations. Default: 100.")
    framework_runtime_executor_loop.set_defaults(func=cmd_framework_runtime)

    framework_runtime_executor_status = framework_runtime_executor_sub.add_parser("status", help="Show local executor job and result status for a run.")
    add_framework_runtime_executor_run_args(framework_runtime_executor_status)
    framework_runtime_executor_status.set_defaults(func=cmd_framework_runtime)

    framework_runtime_job = framework_runtime_sub.add_parser("job", help="Manage local static framework runtime jobs.")
    framework_runtime_job_sub = framework_runtime_job.add_subparsers(dest="framework_runtime_job_action", required=True)

    def add_framework_runtime_job_run_args(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--workspace-id", required=True, help="Stable workspace id.")
        parser.add_argument("--run-id", required=True, help="Stable run id.")
        parser.add_argument("--root", required=True, help="Root directory that contains the .ai/workspaces store.")
        parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    framework_runtime_job_create = framework_runtime_job_sub.add_parser("create", help="Create a local static framework runtime job.")
    add_framework_runtime_job_run_args(framework_runtime_job_create)
    framework_runtime_job_create.add_argument("--job-id", required=True, help="Stable job id.")
    framework_runtime_job_create.add_argument("--objective", required=True, help="Local static job objective.")
    framework_runtime_job_create.add_argument("--metadata", action="append", help="Optional KEY=VALUE metadata entry. Repeatable.")
    framework_runtime_job_create.add_argument("--evidence-ref", action="append", help="Optional local evidence reference. Repeatable.")
    framework_runtime_job_create.set_defaults(func=cmd_framework_runtime)

    framework_runtime_job_list = framework_runtime_job_sub.add_parser("list", help="List local static framework runtime jobs for a run.")
    add_framework_runtime_job_run_args(framework_runtime_job_list)
    framework_runtime_job_list.set_defaults(func=cmd_framework_runtime)

    for job_action in ("show", "cancel", "fail"):
        job_parser = framework_runtime_job_sub.add_parser(job_action, help=f"{job_action.capitalize()} a local static framework runtime job.")
        add_framework_runtime_job_run_args(job_parser)
        job_parser.add_argument("--job-id", required=True, help="Stable job id.")
        if job_action in {"cancel", "fail"}:
            job_parser.add_argument("--reason", default=f"job {job_action}ed", help="Deterministic transition reason.")
        job_parser.set_defaults(func=cmd_framework_runtime)

    p = sub.add_parser("orchestrate", help="Create and inspect static auditable multi-agent orchestration artifacts.")
    orch_sub = p.add_subparsers(dest="orchestrate_action", required=True)
    run = orch_sub.add_parser("run", help="Generate a static orchestration artifact directory without provider calls.")
    run.add_argument("--task", required=True, help="High-level user task to orchestrate.")
    run.add_argument("--mode", choices=["static"], default="static", help="Orchestration mode. Current implementation supports static only.")
    run.add_argument("--out", required=True, help="Output directory for orchestration artifacts.")
    run.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    run.set_defaults(func=cmd_orchestrate)
    inspect = orch_sub.add_parser("inspect", help="Summarize an orchestration artifact directory.")
    inspect.add_argument("--path", required=True, help="Orchestration artifact directory.")
    inspect.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    inspect.set_defaults(func=cmd_orchestrate)
    validate = orch_sub.add_parser("validate", help="Validate an orchestration artifact directory.")
    validate.add_argument("--path", required=True, help="Orchestration artifact directory.")
    validate.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    validate.set_defaults(func=cmd_orchestrate)

    p = sub.add_parser("runtime", help="Manage a local deterministic runtime foundation workspace.")
    runtime_sub = p.add_subparsers(dest="runtime_action", required=True)
    runtime_init = runtime_sub.add_parser("init", help="Create a local runtime workspace manifest.")
    runtime_init.add_argument("--workspace", required=True, help="Project-local runtime workspace path.")
    runtime_init.add_argument("--goal", required=True, help="Runtime workspace goal.")
    runtime_init.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_init.set_defaults(func=cmd_runtime)
    runtime_plan = runtime_sub.add_parser("plan", help="Write a static deterministic runtime task graph.")
    runtime_plan.add_argument("--workspace", required=True, help="Project-local runtime workspace path.")
    runtime_plan.add_argument("--task", action="append", default=[], required=True, help="Task in id:title format. Repeatable.")
    runtime_plan.add_argument("--depends", action="append", default=[], help="Dependency in task:dependency format. Repeatable.")
    runtime_plan.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_plan.set_defaults(func=cmd_runtime)
    runtime_run = runtime_sub.add_parser("run", help="Run or preview the local deterministic runtime loop.")
    runtime_run.add_argument("--workspace", required=True, help="Project-local runtime workspace path.")
    runtime_run.add_argument("--adapter", required=True, help="Runtime adapter name. Supported: local-static, noop, external-prototype.")
    runtime_run.add_argument("--dry-run", action="store_true", help="Preview ready tasks without mutating task state.")
    runtime_run.add_argument("--execute-local", action="store_true", help="Execute deterministic local/static task results.")
    runtime_run.add_argument("--reset", action="store_true", help="Reset task statuses before --execute-local.")
    runtime_run.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_run.set_defaults(func=cmd_runtime)
    runtime_status = runtime_sub.add_parser("status", help="Read back runtime workspace status and memory counts.")
    runtime_status.add_argument("--workspace", required=True, help="Project-local runtime workspace path.")
    runtime_status.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_status.set_defaults(func=cmd_runtime)
    runtime_packet = runtime_sub.add_parser("packet", help="Build a static runtime lifecycle packet.")
    runtime_packet.add_argument("--workspace", required=True, help="Project-local runtime workspace path.")
    runtime_packet.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_packet.set_defaults(func=cmd_runtime)
    runtime_replay = runtime_sub.add_parser("replay", help="Replay-read runtime graph, memory, and event logs.")
    runtime_replay.add_argument("--workspace", required=True, help="Project-local runtime workspace path.")
    runtime_replay.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_replay.set_defaults(func=cmd_runtime)
    runtime_evidence = runtime_sub.add_parser("evidence", help="Write a local runtime workspace evidence bundle.")
    runtime_evidence.add_argument("--workspace", required=True, help="Project-local runtime workspace path.")
    runtime_evidence.add_argument("--out", required=True, help="Project-local evidence output path.")
    runtime_evidence.add_argument("--format", choices=["json", "text"], default="json", help="Evidence output format. Default: json.")
    runtime_evidence.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_evidence.set_defaults(func=cmd_runtime)
    runtime_close = runtime_sub.add_parser("close", help="Build a runtime closure packet from local readback evidence.")
    runtime_close.add_argument("--workspace", required=True, help="Project-local runtime workspace path.")
    runtime_close.add_argument("--out", help="Optional project-local closure packet JSON output path.")
    runtime_close.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_close.set_defaults(func=cmd_runtime)
    runtime_closure_packet = runtime_sub.add_parser("closure-packet", help="Alias for runtime close; writes a runtime closure packet.")
    runtime_closure_packet.add_argument("--workspace", required=True, help="Project-local runtime workspace path.")
    runtime_closure_packet.add_argument("--out", help="Optional project-local closure packet JSON output path.")
    runtime_closure_packet.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_closure_packet.set_defaults(func=cmd_runtime)
    runtime_governance = runtime_sub.add_parser("governance", help="Write runtime governance evidence from closure/readback artifacts.")
    runtime_governance.add_argument("--workspace", required=True, help="Project-local runtime workspace path.")
    runtime_governance.add_argument("--closure-packet", required=True, help="Project-local runtime closure packet JSON path.")
    runtime_governance.add_argument("--evidence-out", required=True, help="Project-local governance evidence output path.")
    runtime_governance.add_argument("--format", choices=["json", "text"], default="json", help="Governance evidence output format. Default: json.")
    runtime_governance.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_governance.set_defaults(func=cmd_runtime)
    runtime_workspace = runtime_sub.add_parser("workspace", help="Manage a local-only multi-agent runtime workspace.")
    runtime_workspace_sub = runtime_workspace.add_subparsers(dest="workspace_action", required=True)
    runtime_workspace_init = runtime_workspace_sub.add_parser("init", help="Initialize local multi-agent runtime workspace schema.")
    runtime_workspace_init.add_argument("--workspace", required=True, help="Project-local runtime workspace path.")
    runtime_workspace_init.add_argument("--run-id", required=True, help="Stable local runtime run id.")
    runtime_workspace_init.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_workspace_init.set_defaults(func=cmd_runtime)
    for workspace_action in ("inspect", "status"):
        workspace_parser = runtime_workspace_sub.add_parser(workspace_action, help=f"Runtime workspace {workspace_action}.")
        workspace_parser.add_argument("--workspace", required=True, help="Project-local runtime workspace path.")
        workspace_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
        workspace_parser.set_defaults(func=cmd_runtime)
    for workspace_action in ("report", "packet"):
        workspace_parser = runtime_workspace_sub.add_parser(workspace_action, help=f"Write runtime workspace {workspace_action} output.")
        workspace_parser.add_argument("--workspace", required=True, help="Project-local runtime workspace path.")
        workspace_parser.add_argument("--out", help="Optional project-local output path.")
        workspace_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
        workspace_parser.set_defaults(func=cmd_runtime)

    runtime_memory = runtime_sub.add_parser("memory", help="Read and write local-only persistent agent memory.")
    runtime_memory_sub = runtime_memory.add_subparsers(dest="memory_action", required=True)
    runtime_memory_write = runtime_memory_sub.add_parser("write", help="Append one deterministic local memory record.")
    runtime_memory_write.add_argument("--workspace", required=True, help="Project-local runtime workspace path.")
    runtime_memory_write.add_argument("--goal-id", required=True, help="Goal id associated with this memory.")
    runtime_memory_write.add_argument("--agent-role", required=True, help="Agent role: planner, scheduler, executor, reviewer, or operator.")
    runtime_memory_write.add_argument("--kind", required=True, help="Memory kind.")
    runtime_memory_write.add_argument("--content", required=True, help="Memory content to store locally.")
    runtime_memory_write.add_argument("--summary", help="Optional deterministic summary. Defaults to compacted content prefix.")
    runtime_memory_write.add_argument("--source-command", help="Source command string recorded as provenance.")
    runtime_memory_write.add_argument("--source-artifact", help="Source artifact path recorded as provenance.")
    runtime_memory_write.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_memory_write.set_defaults(func=cmd_runtime)
    runtime_memory_list = runtime_memory_sub.add_parser("list", help="List local memory records with optional filters.")
    runtime_memory_list.add_argument("--workspace", required=True, help="Project-local runtime workspace path.")
    runtime_memory_list.add_argument("--run-id", help="Filter by run id.")
    runtime_memory_list.add_argument("--goal-id", help="Filter by goal id.")
    runtime_memory_list.add_argument("--agent-role", help="Filter by agent role.")
    runtime_memory_list.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_memory_list.set_defaults(func=cmd_runtime)
    runtime_memory_inspect = runtime_memory_sub.add_parser("inspect", help="Inspect one local memory record.")
    runtime_memory_inspect.add_argument("--workspace", required=True, help="Project-local runtime workspace path.")
    runtime_memory_inspect.add_argument("--memory-id", required=True, help="Memory id to inspect.")
    runtime_memory_inspect.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_memory_inspect.set_defaults(func=cmd_runtime)
    runtime_memory_summarize = runtime_memory_sub.add_parser("summarize", help="Summarize local memory records by role, goal, and kind.")
    runtime_memory_summarize.add_argument("--workspace", required=True, help="Project-local runtime workspace path.")
    runtime_memory_summarize.add_argument("--run-id", help="Filter by run id.")
    runtime_memory_summarize.add_argument("--goal-id", help="Filter by goal id.")
    runtime_memory_summarize.add_argument("--agent-role", help="Filter by agent role.")
    runtime_memory_summarize.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_memory_summarize.set_defaults(func=cmd_runtime)

    runtime_scheduler = runtime_sub.add_parser("scheduler", help="Classify local goal dependency graph readiness without starting workers.")
    runtime_scheduler.add_argument("--workspace", required=True, help="Project-local runtime workspace path.")
    runtime_scheduler.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_scheduler.set_defaults(func=cmd_runtime)

    runtime_planner = runtime_sub.add_parser("planner", help="Generate a static deterministic local plan graph from an objective.")
    runtime_planner.add_argument("--workspace", required=True, help="Project-local runtime workspace path.")
    runtime_planner.add_argument("--objective", required=True, help="Objective to decompose into local goals.")
    runtime_planner.add_argument("--explain", action="store_true", help="Include explanation fields in output.")
    runtime_planner.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_planner.set_defaults(func=cmd_runtime)

    runtime_parallel = runtime_sub.add_parser("parallel", help="Run bounded local dry-run executor simulation for ready goals.")
    runtime_parallel.add_argument("--workspace", required=True, help="Project-local runtime workspace path.")
    runtime_parallel.add_argument("--max-workers", type=int, default=2, help="Maximum simulated workers. Default: 2.")
    runtime_parallel.add_argument("--fail-goal", action="append", help="Goal id to classify as simulated failure. Repeatable.")
    runtime_parallel.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_parallel.set_defaults(func=cmd_runtime)

    runtime_orchestrate = runtime_sub.add_parser("orchestrate", help="Run local planner -> scheduler -> executor -> reviewer packet -> report dry-run.")
    runtime_orchestrate.add_argument("--workspace", required=True, help="Project-local runtime workspace path.")
    runtime_orchestrate.add_argument("--objective", help="Objective to orchestrate. Required unless --resume is used.")
    runtime_orchestrate.add_argument("--run-id", help="Run id to use if the workspace must be initialized.")
    runtime_orchestrate.add_argument("--max-workers", type=int, default=2, help="Maximum simulated workers. Default: 2.")
    runtime_orchestrate.add_argument("--dry-run", action="store_true", default=True, help="Dry-run mode is the only supported mode.")
    runtime_orchestrate.add_argument("--resume", action="store_true", help="Inspect existing ledgers and recovery state instead of planning new goals.")
    runtime_orchestrate.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_orchestrate.set_defaults(func=cmd_runtime)

    runtime_job = runtime_sub.add_parser("job", help="Create and read local deterministic runtime job state.")
    runtime_job_sub = runtime_job.add_subparsers(dest="job_action", required=True)
    runtime_job_create = runtime_job_sub.add_parser("create", help="Create a local runtime job state file.")
    runtime_job_create.add_argument("--workspace", required=True, help="Project-local runtime workspace path.")
    runtime_job_create.add_argument("--job-id", required=True, help="Stable runtime job id.")
    runtime_job_create.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_job_create.set_defaults(func=cmd_runtime)
    runtime_job_status = runtime_job_sub.add_parser("status", help="Read local runtime job state.")
    runtime_job_status.add_argument("--workspace", required=True, help="Project-local runtime workspace path.")
    runtime_job_status.add_argument("--job-id", required=True, help="Stable runtime job id.")
    runtime_job_status.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_job_status.set_defaults(func=cmd_runtime)
    runtime_job_cancel = runtime_job_sub.add_parser("cancel", help="Cancel a local runtime job state.")
    runtime_job_cancel.add_argument("--workspace", required=True, help="Project-local runtime workspace path.")
    runtime_job_cancel.add_argument("--job-id", required=True, help="Stable runtime job id.")
    runtime_job_cancel.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_job_cancel.set_defaults(func=cmd_runtime)
    runtime_job_fail = runtime_job_sub.add_parser("fail", help="Mark a local runtime job state failed.")
    runtime_job_fail.add_argument("--workspace", required=True, help="Project-local runtime workspace path.")
    runtime_job_fail.add_argument("--job-id", required=True, help="Stable runtime job id.")
    runtime_job_fail.add_argument("--reason", required=True, help="Deterministic failure reason.")
    runtime_job_fail.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_job_fail.set_defaults(func=cmd_runtime)
    runtime_job_resume = runtime_job_sub.add_parser("resume", help="Resume an allowed local runtime job state.")
    runtime_job_resume.add_argument("--workspace", required=True, help="Project-local runtime workspace path.")
    runtime_job_resume.add_argument("--job-id", required=True, help="Stable runtime job id.")
    runtime_job_resume.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_job_resume.set_defaults(func=cmd_runtime)
    runtime_worker_adapter = runtime_sub.add_parser("worker-adapter", help="List or describe runtime worker adapter contracts.")
    runtime_worker_adapter.add_argument("--list", dest="list_adapters", action="store_true", help="List runtime worker adapters.")
    runtime_worker_adapter.add_argument("--name", help="Runtime worker adapter name to describe.")
    runtime_worker_adapter.add_argument("--describe", action="store_true", help="Describe one runtime worker adapter contract.")
    runtime_worker_adapter.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_worker_adapter.set_defaults(func=cmd_runtime)

    runtime_worker_gate = runtime_sub.add_parser("worker-gate", help="Read external worker safety gate readiness without executing workers.")
    runtime_worker_gate.add_argument("--workspace", required=True, help="Project-local runtime workspace path.")
    runtime_worker_gate.add_argument("--adapter", required=True, help="Runtime worker adapter name.")
    runtime_worker_gate.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_worker_gate.set_defaults(func=cmd_runtime)
    runtime_worker_packet = runtime_sub.add_parser("worker-packet", help="Write a static worker invocation packet without executing workers.")
    runtime_worker_packet.add_argument("--workspace", required=True, help="Project-local runtime workspace path.")
    runtime_worker_packet.add_argument("--adapter", required=True, help="Runtime worker adapter name.")
    runtime_worker_packet.add_argument("--job-id", required=True, help="Stable runtime job id.")
    runtime_worker_packet.add_argument("--out", required=True, help="Project-local worker invocation packet output path.")
    runtime_worker_packet.add_argument("--format", choices=["json", "text"], default="json", help="Packet output format. Default: json.")
    runtime_worker_packet.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_worker_packet.set_defaults(func=cmd_runtime)
    runtime_worker_result = runtime_sub.add_parser("worker-result", help="Intake saved static worker result artifacts.")
    runtime_worker_result_sub = runtime_worker_result.add_subparsers(dest="worker_result_action", required=True)
    runtime_worker_result_intake = runtime_worker_result_sub.add_parser("intake", help="Intake a saved worker result artifact without executing workers.")
    runtime_worker_result_intake.add_argument("--workspace", required=True, help="Project-local runtime workspace path.")
    runtime_worker_result_intake.add_argument("--packet", required=True, help="Project-local worker invocation packet JSON path.")
    runtime_worker_result_intake.add_argument("--result", required=True, help="Project-local saved worker result JSON path.")
    runtime_worker_result_intake.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_worker_result_intake.set_defaults(func=cmd_runtime)
    runtime_worker_result_replay = runtime_worker_result_sub.add_parser("replay", help="Replay saved worker packet/result artifacts without executing workers.")
    runtime_worker_result_replay.add_argument("--workspace", required=True, help="Project-local runtime workspace path.")
    runtime_worker_result_replay.add_argument("--packet", required=True, help="Project-local worker invocation packet JSON path.")
    runtime_worker_result_replay.add_argument("--result", required=True, help="Project-local saved worker result JSON path.")
    runtime_worker_result_replay.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_worker_result_replay.set_defaults(func=cmd_runtime)
    runtime_worker_audit_closure = runtime_worker_result_sub.add_parser("audit-closure", help="Write a deterministic worker audit closure packet.")
    runtime_worker_audit_closure.add_argument("--workspace", required=True, help="Project-local runtime workspace path.")
    runtime_worker_audit_closure.add_argument("--packet", required=True, help="Project-local worker invocation packet JSON path.")
    runtime_worker_audit_closure.add_argument("--result", required=True, help="Project-local saved worker result JSON path.")
    runtime_worker_audit_closure.add_argument("--out", required=True, help="Project-local worker audit closure output path.")
    runtime_worker_audit_closure.add_argument("--format", choices=["json", "text"], default="json", help="Audit closure output format. Default: json.")
    runtime_worker_audit_closure.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_worker_audit_closure.set_defaults(func=cmd_runtime)
    runtime_worker_delivery_bundle = runtime_worker_result_sub.add_parser("delivery-bundle", help="Write a static reviewer-ready worker delivery bundle.")
    runtime_worker_delivery_bundle.add_argument("--workspace", required=True, help="Project-local runtime workspace path.")
    runtime_worker_delivery_bundle.add_argument("--packet", required=True, help="Project-local worker invocation packet JSON path.")
    runtime_worker_delivery_bundle.add_argument("--result", required=True, help="Project-local saved worker result JSON path.")
    runtime_worker_delivery_bundle.add_argument("--audit-closure", required=True, help="Project-local worker audit closure packet JSON path.")
    runtime_worker_delivery_bundle.add_argument("--out", required=True, help="Project-local worker delivery bundle output path.")
    runtime_worker_delivery_bundle.add_argument("--format", choices=["json", "text"], default="json", help="Delivery bundle output format. Default: json.")
    runtime_worker_delivery_bundle.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_worker_delivery_bundle.set_defaults(func=cmd_runtime)
    runtime_worker_reviewer_attestation = runtime_worker_result_sub.add_parser("reviewer-attestation", help="Write a deterministic reviewer attestation packet from a saved reviewer artifact.")
    runtime_worker_reviewer_attestation.add_argument("--reviewer-artifact", required=True, help="Project-local reviewer output artifact path, Markdown or JSON.")
    runtime_worker_reviewer_attestation.add_argument("--marker", required=True, help="Expected review marker that must appear in the reviewer artifact.")
    runtime_worker_reviewer_attestation.add_argument("--out", required=True, help="Project-local reviewer attestation output path.")
    runtime_worker_reviewer_attestation.add_argument("--format", choices=["json", "text"], default="json", help="Reviewer attestation output format. Default: json.")
    runtime_worker_reviewer_attestation.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_worker_reviewer_attestation.set_defaults(func=cmd_runtime)
    runtime_worker_closure_evidence = runtime_worker_result_sub.add_parser("closure-evidence", help="Import reviewer attestation as static closure evidence.")
    runtime_worker_closure_evidence.add_argument("--reviewer-attestation", required=True, help="Project-local reviewer attestation JSON path.")
    runtime_worker_closure_evidence.add_argument("--out", required=True, help="Project-local closure evidence output path.")
    runtime_worker_closure_evidence.add_argument("--format", choices=["json", "text"], default="json", help="Closure evidence output format. Default: json.")
    runtime_worker_closure_evidence.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_worker_closure_evidence.set_defaults(func=cmd_runtime)
    runtime_worker_merge_readiness = runtime_worker_result_sub.add_parser("merge-readiness", help="Write a static merge-readiness packet from delivery bundle, reviewer attestation, and closure evidence.")
    runtime_worker_merge_readiness.add_argument("--delivery-bundle", required=True, help="Project-local worker delivery bundle JSON path.")
    runtime_worker_merge_readiness.add_argument("--reviewer-attestation", required=True, help="Project-local reviewer attestation JSON path.")
    runtime_worker_merge_readiness.add_argument("--closure-evidence", required=True, help="Project-local closure evidence JSON path.")
    runtime_worker_merge_readiness.add_argument("--baseline", required=True, help="Target baseline commit for the readiness packet.")
    runtime_worker_merge_readiness.add_argument("--source-branch", required=True, help="Source branch name for delivery.")
    runtime_worker_merge_readiness.add_argument("--source-head", required=True, help="Source branch head commit for delivery.")
    runtime_worker_merge_readiness.add_argument("--target-branch", required=True, help="Target branch name for delivery.")
    runtime_worker_merge_readiness.add_argument("--out", required=True, help="Project-local merge-readiness output path.")
    runtime_worker_merge_readiness.add_argument("--format", choices=["json", "text"], default="json", help="Merge-readiness output format. Default: json.")
    runtime_worker_merge_readiness.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_worker_merge_readiness.set_defaults(func=cmd_runtime)
    runtime_worker_delivery_gate = runtime_worker_result_sub.add_parser("delivery-gate", help="Run the static end-to-end delivery gate from a merge-readiness packet.")
    runtime_worker_delivery_gate.add_argument("--merge-readiness", required=True, help="Project-local merge-readiness packet JSON path.")
    runtime_worker_delivery_gate.add_argument("--out", required=True, help="Project-local delivery gate output path.")
    runtime_worker_delivery_gate.add_argument("--format", choices=["json", "text"], default="json", help="Delivery gate output format. Default: json.")
    runtime_worker_delivery_gate.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_worker_delivery_gate.set_defaults(func=cmd_runtime)
    runtime_worker_rejection_packet = runtime_worker_result_sub.add_parser("rejection-packet", help="Write a deterministic rejection recovery packet from a failed delivery gate.")
    runtime_worker_rejection_packet.add_argument("--delivery-gate", required=True, help="Project-local delivery gate JSON path.")
    runtime_worker_rejection_packet.add_argument("--out", required=True, help="Project-local rejection recovery output path.")
    runtime_worker_rejection_packet.add_argument("--format", choices=["json", "text"], default="json", help="Rejection packet output format. Default: json.")
    runtime_worker_rejection_packet.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_worker_rejection_packet.set_defaults(func=cmd_runtime)
    runtime_worker_audit_replay = runtime_worker_result_sub.add_parser("audit-replay", help="Replay static audit, merge-readiness, delivery-gate, or rejection packets.")
    runtime_worker_audit_replay.add_argument("--packet", required=True, help="Project-local audit packet JSON path.")
    runtime_worker_audit_replay.add_argument("--out", help="Optional project-local audit replay artifact output path.")
    runtime_worker_audit_replay.add_argument("--format", choices=["json", "text"], default="json", help="Audit replay artifact output format when --out is used. Default: json.")
    runtime_worker_audit_replay.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_worker_audit_replay.set_defaults(func=cmd_runtime)
    runtime_worker_provenance_manifest = runtime_worker_result_sub.add_parser("provenance-manifest", help="Write a deterministic artifact-chain provenance manifest.")
    runtime_worker_provenance_manifest.add_argument("--reviewer-attestation", required=True, help="Project-local reviewer attestation JSON path.")
    runtime_worker_provenance_manifest.add_argument("--closure-evidence", required=True, help="Project-local closure evidence JSON path.")
    runtime_worker_provenance_manifest.add_argument("--merge-readiness", required=True, help="Project-local merge-readiness JSON path.")
    runtime_worker_provenance_manifest.add_argument("--delivery-gate", required=True, help="Project-local delivery gate JSON path.")
    runtime_worker_provenance_manifest.add_argument("--rejection-packet", required=True, help="Project-local rejection recovery JSON path.")
    runtime_worker_provenance_manifest.add_argument("--audit-replay", required=True, help="Project-local audit replay JSON path.")
    runtime_worker_provenance_manifest.add_argument("--out", required=True, help="Project-local provenance manifest output path.")
    runtime_worker_provenance_manifest.add_argument("--format", choices=["json", "text"], default="json", help="Provenance manifest output format. Default: json.")
    runtime_worker_provenance_manifest.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_worker_provenance_manifest.set_defaults(func=cmd_runtime)
    runtime_worker_provenance_verify = runtime_worker_result_sub.add_parser("provenance-verify", help="Verify provenance manifest integrity, parent links, role order, and static predicates.")
    runtime_worker_provenance_verify.add_argument("--manifest", required=True, help="Project-local provenance manifest JSON path.")
    runtime_worker_provenance_verify.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_worker_provenance_verify.set_defaults(func=cmd_runtime)
    runtime_worker_provenance_replay = runtime_worker_result_sub.add_parser("provenance-replay", help="Replay a tamper-evident artifact chain from a provenance manifest.")
    runtime_worker_provenance_replay.add_argument("--manifest", required=True, help="Project-local provenance manifest JSON path.")
    runtime_worker_provenance_replay.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_worker_provenance_replay.set_defaults(func=cmd_runtime)
    runtime_worker_release_candidate = runtime_worker_result_sub.add_parser("release-candidate", help="Write a deterministic release candidate export package from a provenance manifest.")
    runtime_worker_release_candidate.add_argument("--provenance-manifest", required=True, help="Project-local provenance manifest JSON path.")
    runtime_worker_release_candidate.add_argument("--out", required=True, help="Project-local release candidate package output path.")
    runtime_worker_release_candidate.add_argument("--format", choices=["json", "text"], default="json", help="Release candidate package output format. Default: json.")
    runtime_worker_release_candidate.add_argument("--review-target", default="AgentOffice static release candidate", help="Review target recorded in the package.")
    runtime_worker_release_candidate.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_worker_release_candidate.set_defaults(func=cmd_runtime)
    runtime_worker_external_review_handoff = runtime_worker_result_sub.add_parser("external-review-handoff", help="Write a deterministic external reviewer handoff packet.")
    runtime_worker_external_review_handoff.add_argument("--release-candidate", required=True, help="Project-local release candidate package JSON path.")
    runtime_worker_external_review_handoff.add_argument("--out", required=True, help="Project-local external review handoff output path.")
    runtime_worker_external_review_handoff.add_argument("--format", choices=["json", "text"], default="json", help="External review handoff output format. Default: json.")
    runtime_worker_external_review_handoff.add_argument("--review-target", default="AgentOffice static release candidate", help="Review target recorded in the handoff.")
    runtime_worker_external_review_handoff.add_argument("--expected-marker", required=True, help="Expected marker in the external reviewer output.")
    runtime_worker_external_review_handoff.add_argument("--attestation-import-path", required=True, help="Project-local path where reviewer attestation import should be written later.")
    runtime_worker_external_review_handoff.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_worker_external_review_handoff.set_defaults(func=cmd_runtime)
    runtime_worker_archive_index = runtime_worker_result_sub.add_parser("archive-index", help="Write a deterministic evidence archive index.")
    runtime_worker_archive_index.add_argument("--release-candidate", required=True, help="Project-local release candidate package JSON path.")
    runtime_worker_archive_index.add_argument("--external-review-handoff", required=True, help="Project-local external review handoff JSON path.")
    runtime_worker_archive_index.add_argument("--out", required=True, help="Project-local evidence archive index output path.")
    runtime_worker_archive_index.add_argument("--format", choices=["json", "text"], default="json", help="Evidence archive index output format. Default: json.")
    runtime_worker_archive_index.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_worker_archive_index.set_defaults(func=cmd_runtime)
    runtime_worker_archive_verify = runtime_worker_result_sub.add_parser("archive-verify", help="Verify an evidence archive index and referenced artifacts.")
    runtime_worker_archive_verify.add_argument("--index", required=True, help="Project-local evidence archive index JSON path.")
    runtime_worker_archive_verify.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_worker_archive_verify.set_defaults(func=cmd_runtime)
    runtime_worker_reviewer_archive_import = runtime_worker_result_sub.add_parser("reviewer-archive-import", help="Import external reviewer output into the static evidence archive chain.")
    runtime_worker_reviewer_archive_import.add_argument("--reviewer-output", required=True, help="Project-local external reviewer output artifact path.")
    runtime_worker_reviewer_archive_import.add_argument("--archive-index", required=True, help="Project-local evidence archive index JSON path.")
    runtime_worker_reviewer_archive_import.add_argument("--expected-marker", required=True, help="Expected marker in the external reviewer output.")
    runtime_worker_reviewer_archive_import.add_argument("--out", required=True, help="Project-local reviewer archive import output path.")
    runtime_worker_reviewer_archive_import.add_argument("--format", choices=["json", "text"], default="json", help="Reviewer import output format. Default: json.")
    runtime_worker_reviewer_archive_import.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_worker_reviewer_archive_import.set_defaults(func=cmd_runtime)
    runtime_worker_release_closure = runtime_worker_result_sub.add_parser("release-closure", help="Write a deterministic release closure bundle from RC, archive, and reviewer import evidence.")
    runtime_worker_release_closure.add_argument("--release-candidate", required=True, help="Project-local release candidate package JSON path.")
    runtime_worker_release_closure.add_argument("--external-review-handoff", required=True, help="Project-local external review handoff JSON path.")
    runtime_worker_release_closure.add_argument("--archive-index", required=True, help="Project-local evidence archive index JSON path.")
    runtime_worker_release_closure.add_argument("--reviewer-import", required=True, help="Project-local external reviewer archive import JSON path.")
    runtime_worker_release_closure.add_argument("--provenance-manifest", required=True, help="Project-local provenance manifest JSON path.")
    runtime_worker_release_closure.add_argument("--out", required=True, help="Project-local release closure bundle output path.")
    runtime_worker_release_closure.add_argument("--format", choices=["json", "text"], default="json", help="Release closure output format. Default: json.")
    runtime_worker_release_closure.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_worker_release_closure.set_defaults(func=cmd_runtime)
    runtime_worker_archive_replay = runtime_worker_result_sub.add_parser("archive-replay", help="Replay-verify archive index, release candidate, and release closure bundle.")
    runtime_worker_archive_replay.add_argument("--archive-index", required=True, help="Project-local evidence archive index JSON path.")
    runtime_worker_archive_replay.add_argument("--release-candidate", required=True, help="Project-local release candidate package JSON path.")
    runtime_worker_archive_replay.add_argument("--release-closure", required=True, help="Project-local release closure bundle JSON path.")
    runtime_worker_archive_replay.add_argument("--out", required=True, help="Project-local archive replay verification output path.")
    runtime_worker_archive_replay.add_argument("--format", choices=["json", "text"], default="json", help="Archive replay output format. Default: json.")
    runtime_worker_archive_replay.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_worker_archive_replay.set_defaults(func=cmd_runtime)
    runtime_worker_final_readiness = runtime_worker_result_sub.add_parser("final-readiness", help="Write final delivery readiness from release closure and archive replay verification.")
    runtime_worker_final_readiness.add_argument("--release-closure", required=True, help="Project-local release closure bundle JSON path.")
    runtime_worker_final_readiness.add_argument("--archive-replay", required=True, help="Project-local archive replay verification JSON path.")
    runtime_worker_final_readiness.add_argument("--out", required=True, help="Project-local final delivery readiness output path.")
    runtime_worker_final_readiness.add_argument("--format", choices=["json", "text"], default="json", help="Final readiness output format. Default: json.")
    runtime_worker_final_readiness.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_worker_final_readiness.set_defaults(func=cmd_runtime)
    runtime_worker_review_recovery = runtime_worker_result_sub.add_parser("review-recovery", help="Write a failed-review recovery packet from a blocked release closure.")
    runtime_worker_review_recovery.add_argument("--release-closure", required=True, help="Project-local release closure bundle JSON path.")
    runtime_worker_review_recovery.add_argument("--out", required=True, help="Project-local review recovery packet output path.")
    runtime_worker_review_recovery.add_argument("--format", choices=["json", "text"], default="json", help="Review recovery output format. Default: json.")
    runtime_worker_review_recovery.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_worker_review_recovery.set_defaults(func=cmd_runtime)
    runtime_worker_compact_archive = runtime_worker_result_sub.add_parser("compact-archive", help="Write a compact long-term evidence archive index.")
    runtime_worker_compact_archive.add_argument("--archive-index", required=True, help="Project-local evidence archive index JSON path.")
    runtime_worker_compact_archive.add_argument("--release-closure", required=True, help="Project-local release closure bundle JSON path.")
    runtime_worker_compact_archive.add_argument("--archive-replay", required=True, help="Project-local archive replay verification JSON path.")
    runtime_worker_compact_archive.add_argument("--final-readiness", required=True, help="Project-local final delivery readiness JSON path.")
    runtime_worker_compact_archive.add_argument("--out", required=True, help="Project-local compact archive index output path.")
    runtime_worker_compact_archive.add_argument("--format", choices=["json", "text"], default="json", help="Compact archive output format. Default: json.")
    runtime_worker_compact_archive.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_worker_compact_archive.set_defaults(func=cmd_runtime)
    runtime_worker_compact_verify = runtime_worker_result_sub.add_parser("compact-verify", help="Verify a compact long-term evidence archive index.")
    runtime_worker_compact_verify.add_argument("--index", required=True, help="Project-local compact archive index JSON path.")
    runtime_worker_compact_verify.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_worker_compact_verify.set_defaults(func=cmd_runtime)
    runtime_worker_rc_promotion_gate = runtime_worker_result_sub.add_parser("rc-promotion-gate", help="Write a static release-candidate promotion gate packet without releasing or tagging.")
    runtime_worker_rc_promotion_gate.add_argument("--final-readiness", required=True, help="Project-local final delivery readiness JSON path.")
    runtime_worker_rc_promotion_gate.add_argument("--compact-index", required=True, help="Project-local compact archive index JSON path.")
    runtime_worker_rc_promotion_gate.add_argument("--release-closure", required=True, help="Project-local release closure bundle JSON path.")
    runtime_worker_rc_promotion_gate.add_argument("--out", required=True, help="Project-local RC promotion gate output path.")
    runtime_worker_rc_promotion_gate.add_argument("--format", choices=["json", "text"], default="json", help="RC promotion gate output format. Default: json.")
    runtime_worker_rc_promotion_gate.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_worker_rc_promotion_gate.set_defaults(func=cmd_runtime)
    runtime_worker_release_candidate_export = runtime_worker_result_sub.add_parser("release-candidate-export", help="Write a reviewer-ready release candidate export packet from RC and archive evidence.")
    runtime_worker_release_candidate_export.add_argument("--release-candidate", required=True, help="Project-local release candidate package JSON path.")
    runtime_worker_release_candidate_export.add_argument("--archive-index", required=True, help="Project-local evidence archive index JSON path.")
    runtime_worker_release_candidate_export.add_argument("--out", required=True, help="Project-local release candidate export packet output path.")
    runtime_worker_release_candidate_export.add_argument("--format", choices=["json", "text"], default="json", help="Release candidate export output format. Default: json.")
    runtime_worker_release_candidate_export.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_worker_release_candidate_export.set_defaults(func=cmd_runtime)
    runtime_worker_promotion_evidence = runtime_worker_result_sub.add_parser("promotion-evidence", help="Write a reviewer-ready promotion evidence packet without releasing or tagging.")
    runtime_worker_promotion_evidence.add_argument("--release-candidate", required=True, help="Project-local release candidate package JSON path.")
    runtime_worker_promotion_evidence.add_argument("--archive-index", required=True, help="Project-local evidence archive index JSON path.")
    runtime_worker_promotion_evidence.add_argument("--release-closure", required=True, help="Project-local release closure bundle JSON path.")
    runtime_worker_promotion_evidence.add_argument("--archive-replay", required=True, help="Project-local archive replay verification JSON path.")
    runtime_worker_promotion_evidence.add_argument("--final-readiness", required=True, help="Project-local final readiness JSON path.")
    runtime_worker_promotion_evidence.add_argument("--compact-index", required=True, help="Project-local compact archive index JSON path.")
    runtime_worker_promotion_evidence.add_argument("--promotion-gate", required=True, help="Project-local RC promotion gate JSON path.")
    runtime_worker_promotion_evidence.add_argument("--final-mainline", default="not_recorded_static_pre_release", help="Final mainline commit recorded in the evidence packet when known.")
    runtime_worker_promotion_evidence.add_argument("--out", required=True, help="Project-local promotion evidence packet output path.")
    runtime_worker_promotion_evidence.add_argument("--format", choices=["json", "text"], default="json", help="Promotion evidence output format. Default: json.")
    runtime_worker_promotion_evidence.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_worker_promotion_evidence.set_defaults(func=cmd_runtime)
    runtime_worker_dry_run_publish = runtime_worker_result_sub.add_parser("dry-run-publish", help="Write a dry-run publish packet without tag, release, push, or default-branch mutation.")
    runtime_worker_dry_run_publish.add_argument("--promotion-evidence", required=True, help="Project-local promotion evidence packet JSON path.")
    runtime_worker_dry_run_publish.add_argument("--release-candidate-export", required=True, help="Project-local release candidate export packet JSON path.")
    runtime_worker_dry_run_publish.add_argument("--promotion-gate", required=True, help="Project-local RC promotion gate JSON path.")
    runtime_worker_dry_run_publish.add_argument("--candidate-name", required=True, help="Candidate release name recorded in the dry-run packet.")
    runtime_worker_dry_run_publish.add_argument("--target-branch", required=True, help="Target branch that a future real publish would use.")
    runtime_worker_dry_run_publish.add_argument("--target-commit", required=True, help="Target commit that a future real publish would use.")
    runtime_worker_dry_run_publish.add_argument("--out", required=True, help="Project-local dry-run publish packet output path.")
    runtime_worker_dry_run_publish.add_argument("--format", choices=["json", "text"], default="json", help="Dry-run publish output format. Default: json.")
    runtime_worker_dry_run_publish.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_worker_dry_run_publish.set_defaults(func=cmd_runtime)

    p = sub.add_parser("autonomy", help="Plan and operate local autonomous delivery workflows without external execution.")
    autonomy_sub = p.add_subparsers(dest="autonomy_action", required=True)
    autonomy_plan = autonomy_sub.add_parser("plan", help="Generate a deterministic local autonomous delivery mission plan.")
    autonomy_plan.add_argument("--goal", required=True, help="Autonomous delivery goal to plan: release-ops, post-v1, or autonomous-delivery.")
    autonomy_plan.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    autonomy_plan.set_defaults(func=cmd_autonomy)
    autonomy_init = autonomy_sub.add_parser("init", help="Initialize a local autonomous run ledger.")
    autonomy_init.add_argument("--goal", required=True, help="Autonomous delivery goal for the run ledger.")
    autonomy_init.add_argument("--path", required=True, help="Project-local or temp run ledger directory.")
    autonomy_init.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    autonomy_init.set_defaults(func=cmd_autonomy)
    autonomy_status = autonomy_sub.add_parser("status", help="Read a local autonomous run ledger.")
    autonomy_status.add_argument("--path", required=True, help="Project-local or temp run ledger directory.")
    autonomy_status.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    autonomy_status.set_defaults(func=cmd_autonomy)
    autonomy_checkpoint = autonomy_sub.add_parser("checkpoint", help="Append a checkpoint to a local autonomous run ledger.")
    autonomy_checkpoint.add_argument("--path", required=True, help="Project-local or temp run ledger directory.")
    autonomy_checkpoint.add_argument("--name", required=True, help="Checkpoint name.")
    autonomy_checkpoint.add_argument("--status", required=True, choices=["pending", "running", "passed", "failed", "skipped", "blocked"], help="Checkpoint status.")
    autonomy_checkpoint.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    autonomy_checkpoint.set_defaults(func=cmd_autonomy)
    autonomy_report = autonomy_sub.add_parser("report", help="Summarize a local autonomous run ledger.")
    autonomy_report.add_argument("--path", required=True, help="Project-local or temp run ledger directory.")
    autonomy_report.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    autonomy_report.set_defaults(func=cmd_autonomy)
    autonomy_validate = autonomy_sub.add_parser("validate", help="Run an allowlisted local validation suite and record transcripts.")
    autonomy_validate.add_argument("--path", required=True, help="Project-local or temp run ledger directory.")
    autonomy_validate.add_argument("--suite", required=True, help="Validation suite: minimal, release, or full.")
    autonomy_validate.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    autonomy_validate.set_defaults(func=cmd_autonomy)
    autonomy_review_packet = autonomy_sub.add_parser("review-packet", help="Generate a local Markdown review packet from a commit range.")
    autonomy_review_packet.add_argument("--base", required=True, help="Base commit or ref for diff evidence.")
    autonomy_review_packet.add_argument("--head", required=True, help="Head commit or ref for diff evidence.")
    autonomy_review_packet.add_argument("--out", required=True, help="Review packet Markdown output path under project root or temp directory.")
    autonomy_review_packet.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    autonomy_review_packet.set_defaults(func=cmd_autonomy)
    autonomy_merge_packet = autonomy_sub.add_parser("merge-packet", help="Generate a local merge gate packet without merging.")
    autonomy_merge_packet.add_argument("--source", required=True, help="Source branch or ref to merge later.")
    autonomy_merge_packet.add_argument("--target", required=True, help="Target branch or ref for merge planning.")
    autonomy_merge_packet.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    autonomy_merge_packet.set_defaults(func=cmd_autonomy)

    autonomy_queue = autonomy_sub.add_parser("queue", help="Manage a local autonomous goal queue.")
    queue_sub = autonomy_queue.add_subparsers(dest="queue_action", required=True)
    queue_init = queue_sub.add_parser("init", help="Initialize a local goal queue.")
    queue_init.add_argument("--path", required=True, help="Project-local or temp queue directory.")
    queue_init.add_argument("--goal", help="Goal name recorded in the queue.")
    queue_init.add_argument("--template", help="Optional deterministic template to materialize.")
    queue_init.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    queue_init.set_defaults(func=cmd_autonomy)
    queue_add = queue_sub.add_parser("add", help="Add a task to a local goal queue.")
    queue_add.add_argument("--path", required=True, help="Project-local or temp queue directory.")
    queue_add.add_argument("--id", required=True, help="Task id.")
    queue_add.add_argument("--kind", required=True, help="Task kind.")
    queue_add.add_argument("--suite", help="Validation suite for validate-suite tasks.")
    queue_add.add_argument("--depends-on", action="append", help="Dependency task id. Repeatable.")
    queue_add.add_argument("--max-attempts", type=int, default=1, help="Maximum attempts for retryable failures.")
    queue_add.add_argument("--base", help="Base ref for review-packet tasks.")
    queue_add.add_argument("--head", help="Head ref for review-packet tasks.")
    queue_add.add_argument("--source", help="Source ref for merge-packet tasks.")
    queue_add.add_argument("--target", help="Target ref for merge-packet tasks.")
    queue_add.add_argument("--out", help="Output path for review-packet tasks.")
    queue_add.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    queue_add.set_defaults(func=cmd_autonomy)
    for queue_name in ("status", "validate", "next"):
        queue_parser = queue_sub.add_parser(queue_name, help=f"Queue {queue_name}.")
        queue_parser.add_argument("--path", required=True, help="Project-local or temp queue directory.")
        queue_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
        queue_parser.set_defaults(func=cmd_autonomy)
    queue_inspect = queue_sub.add_parser("inspect", help="Inspect queue status, failures, recovery hints, and evidence without writing.")
    queue_inspect.add_argument("--path", required=True, help="Project-local or temp queue directory.")
    queue_inspect.add_argument("--ledger-limit", type=int, default=5, help="Number of recent ledger records to include.")
    queue_inspect.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    queue_inspect.set_defaults(func=cmd_autonomy)
    run_goal = autonomy_sub.add_parser("run-goal", help="Run ready tasks from a local goal queue using built-in allowlisted actions.")
    run_goal.add_argument("--path", required=True, help="Project-local or temp queue directory.")
    run_goal.add_argument("--max-steps", type=int, default=1, help="Maximum tasks to run.")
    run_goal.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    run_goal.set_defaults(func=cmd_autonomy)
    resume = autonomy_sub.add_parser("resume", help="Resume a local goal queue.")
    resume.add_argument("--path", required=True, help="Project-local or temp queue directory.")
    resume.add_argument("--max-steps", type=int, default=1, help="Maximum tasks to run.")
    resume.add_argument("--retry-failed", action="store_true", help="Retry failed tasks when retry policy allows it.")
    resume.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    resume.set_defaults(func=cmd_autonomy)
    recover_plan = autonomy_sub.add_parser("recover-plan", help="Explain the next resume or retry action without writing or executing tasks.")
    recover_plan.add_argument("--path", required=True, help="Project-local or temp queue directory.")
    recover_plan.add_argument("--max-steps", type=int, default=1, help="Maximum tasks to include in the dry-run plan.")
    recover_plan.add_argument("--retry-failed", action="store_true", help="Include retryable failed tasks in the dry-run plan.")
    recover_plan.add_argument("--ledger-limit", type=int, default=5, help="Number of recent ledger records to include.")
    recover_plan.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    recover_plan.set_defaults(func=cmd_autonomy)
    classify = autonomy_sub.add_parser("classify", help="Classify an autonomy failure and retry policy.")
    classify.add_argument("--kind", required=True, help="Failure class.")
    classify.add_argument("--attempts", type=int, default=0, help="Current attempts.")
    classify.add_argument("--max-attempts", type=int, default=1, help="Maximum attempts.")
    classify.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    classify.set_defaults(func=cmd_autonomy)
    goal_template = autonomy_sub.add_parser("goal-template", help="Print a deterministic goal queue template.")
    goal_template.add_argument("--name", required=True, help="Template name.")
    goal_template.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    goal_template.set_defaults(func=cmd_autonomy)
    goal_report = autonomy_sub.add_parser("goal-report", help="Write a Markdown report for a local goal queue.")
    goal_report.add_argument("--path", required=True, help="Project-local or temp queue directory.")
    goal_report.add_argument("--out", required=True, help="Markdown report output path under project root or temp directory.")
    goal_report.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    goal_report.set_defaults(func=cmd_autonomy)
    goal_handoff = autonomy_sub.add_parser("goal-handoff", help="Write an operator or reviewer handoff packet for a local goal queue.")
    goal_handoff.add_argument("--path", required=True, help="Project-local or temp queue directory.")
    goal_handoff.add_argument("--out", required=True, help="Markdown handoff output path under project root or temp directory.")
    goal_handoff.add_argument("--ledger-limit", type=int, default=5, help="Number of recent ledger records to include.")
    goal_handoff.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    goal_handoff.set_defaults(func=cmd_autonomy)

    p = sub.add_parser("v1", help="Generate and verify AgentOffice v1 final delivery packets without external execution.")
    v1_sub = p.add_subparsers(dest="v1_action", required=True)
    final_delivery = v1_sub.add_parser("final-delivery", help="Generate the deterministic AgentOffice v1 final delivery packet.")
    final_delivery.add_argument("--out", help="Optional JSON output path under the project root or temp directory.")
    final_delivery.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    final_delivery.set_defaults(func=cmd_v1)
    verify_final_delivery = v1_sub.add_parser("verify-final-delivery", help="Verify an AgentOffice v1 final delivery packet.")
    verify_final_delivery.add_argument("--path", required=True, help="Final delivery packet JSON path to verify.")
    verify_final_delivery.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    verify_final_delivery.set_defaults(func=cmd_v1)
    verify_release_archive = v1_sub.add_parser("verify-release-archive", help="Verify a local v1 release archive and checksum without external calls.")
    verify_release_archive.add_argument("--archive", required=True, help="Release archive .tar.gz path to verify.")
    verify_release_archive.add_argument("--sha256", required=True, help="Sidecar SHA256 file path for the release archive.")
    verify_release_archive.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    verify_release_archive.set_defaults(func=cmd_v1)
    verify_github_readback = v1_sub.add_parser("verify-github-release-readback", help="Verify local GitHub release publish/readback evidence without network calls.")
    verify_github_readback.add_argument("--dir", required=True, help="Readback directory containing state.json and optional release readback files.")
    verify_github_readback.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    verify_github_readback.set_defaults(func=cmd_v1)
    post_v1_roadmap = v1_sub.add_parser("post-v1-roadmap", help="Print the deterministic post-v1 release operations roadmap.")
    post_v1_roadmap.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    post_v1_roadmap.set_defaults(func=cmd_v1)
    release_state = v1_sub.add_parser("release-state", help="Print tokenless local v1 release state without network calls.")
    release_state.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    release_state.set_defaults(func=cmd_v1)
    github_handoff = v1_sub.add_parser("github-release-handoff", help="Print tokenless GitHub Release operator handoff guidance.")
    github_handoff.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    github_handoff.set_defaults(func=cmd_v1)
    github_plan = v1_sub.add_parser("github-release-plan", help="Print a dry-run GitHub Release publish plan without writes.")
    github_plan.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    github_plan.set_defaults(func=cmd_v1)
    release_candidate = v1_sub.add_parser("release-candidate", help="Print a local release candidate readiness packet without tagging or release writes.")
    release_candidate.add_argument("--version", required=True, help="Candidate version, for example v1.1.0.")
    release_candidate.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    release_candidate.set_defaults(func=cmd_v1)

    p = sub.add_parser("run-bundle", help="Build, preview, inspect, validate, list, summarize, export, or check static local run bundles without executing providers.")
    p.add_argument("bundle_action", nargs="?", choices=["preview", "inspect", "validate", "list", "status", "intake", "results", "handoff", "review", "gate", "workflow", "export-review"], help="Bundle action.")
    p.add_argument("--objective", help="Objective id to bundle, for example P6-17.")
    p.add_argument("--profile", help="Provider profile name to use for the static bundle.")
    p.add_argument("--run-id", help="Static run bundle id.")
    p.add_argument("--out", help="Explicit output directory for bundle writes or artifact file for export-review.")
    p.add_argument("--path", help="Static run bundle directory for inspect, validate, status, intake, results, handoff, review, gate, workflow, or export-review.")
    p.add_argument("--root", help="Static run bundle catalog root for list.")
    p.add_argument("--actor", help="Static actor result owner: codex, reviewer, or judge.")
    p.add_argument("--artifact", help="Project-local artifact file to intake as actor result metadata.")
    p.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    p.set_defaults(func=cmd_run_bundle)

    p = sub.add_parser("review", help="Generate phase lifecycle review bundles, prompts, attestations, and merge packets.")
    review_sub = p.add_subparsers(dest="review_action", required=True)
    preflight_status = review_sub.add_parser("preflight-status", help="Classify merge-gate git status with historical artifact tolerance.")
    preflight_status.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    preflight_status.set_defaults(func=cmd_review)

    bundle = review_sub.add_parser("bundle", help="Generate a Markdown review bundle and Claude prompt without provider calls.")
    bundle.add_argument("--baseline", required=True, help="Baseline commit for diff evidence.")
    bundle.add_argument("--head", required=True, help="Reviewed head commit.")
    bundle.add_argument("--branch", required=True, help="Reviewed branch name.")
    bundle.add_argument("--report", required=True, help="Implementation report Markdown path.")
    bundle.add_argument("--out", required=True, help="Review bundle Markdown output path.")
    bundle.add_argument("--prompt-out", required=True, help="Claude review prompt output path.")
    bundle.add_argument("--title", required=True, help="Review bundle title.")
    bundle.add_argument("--bundle-marker", required=True, help="Marker written into the generated bundle.")
    bundle.add_argument("--review-marker", required=True, help="Marker Claude must output on PASS.")
    bundle.add_argument("--focus", help="Review focus text or a path to a UTF-8 focus file.")
    bundle.add_argument("--run-validation", action="store_true", help="Run the default validation command set and capture transcripts.")
    bundle.add_argument("--validation-fixture-dir", help="Read fixed validation transcripts from a fixture directory instead of running commands.")
    bundle.add_argument("--allow-dirty", action="store_true", help="Allow tracked dirty state and record it in the bundle.")
    bundle.add_argument("--mkdirs", action="store_true", help="Create missing output parent directories.")
    bundle.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    bundle.set_defaults(func=cmd_review)

    prompt = review_sub.add_parser("prompt", help="Generate a Claude artifact review prompt from existing bundle metadata.")
    prompt.add_argument("--baseline", required=True, help="Baseline commit for the review.")
    prompt.add_argument("--head", required=True, help="Reviewed head commit.")
    prompt.add_argument("--branch", required=True, help="Reviewed branch name.")
    prompt.add_argument("--report", required=True, help="Implementation report Markdown path.")
    prompt.add_argument("--bundle", required=True, help="Review bundle Markdown path.")
    prompt.add_argument("--out", required=True, help="Claude prompt output path.")
    prompt.add_argument("--review-marker", required=True, help="Marker Claude must output on PASS.")
    prompt.add_argument("--title", help="Prompt title.")
    prompt.add_argument("--mkdirs", action="store_true", help="Create missing output parent directories.")
    prompt.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    prompt.set_defaults(func=cmd_review)

    attest = review_sub.add_parser("attest", help="Verify Claude review verdict and marker, then write an attestation.")
    attest.add_argument("--review-report", required=True, help="Claude review output Markdown/text path.")
    attest.add_argument("--expected-marker", required=True, help="Required PASS marker.")
    attest.add_argument("--expected-verdict", default="pass", help="Expected verdict. Default: pass.")
    attest.add_argument("--out", required=True, help="Attestation Markdown output path.")
    attest.add_argument("--mkdirs", action="store_true", help="Create missing output parent directories.")
    attest.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    attest.set_defaults(func=cmd_review)

    merge_packet = review_sub.add_parser("merge-packet", help="Generate a merge-gate packet without executing merge or push.")
    merge_packet.add_argument("--baseline", required=True, help="Mainline baseline before merge.")
    merge_packet.add_argument("--source-branch", required=True, help="Source branch to merge later.")
    merge_packet.add_argument("--source-commit", required=True, help="Source commit to merge later.")
    merge_packet.add_argument("--implementation-report", required=True, help="Implementation report Markdown path.")
    merge_packet.add_argument("--review-bundle", required=True, help="Review bundle Markdown path.")
    merge_packet.add_argument("--review-attestation", help="Optional Claude review attestation Markdown path.")
    merge_packet.add_argument("--out", required=True, help="Merge-gate packet Markdown output path.")
    merge_packet.add_argument("--merge-marker", default="MERGE_GATE_PASS_MAINLINE_SYNCED", help="Suggested merge-gate completion marker.")
    merge_packet.add_argument("--mkdirs", action="store_true", help="Create missing output parent directories.")
    merge_packet.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    merge_packet.set_defaults(func=cmd_review)

    codex_gate = review_sub.add_parser("codex-gate", help="Generate a Codex-only delivery lane readiness report without merge or provider calls.")
    codex_gate.add_argument("--baseline", required=True, help="Baseline commit for diff evidence.")
    codex_gate.add_argument("--head", required=True, help="Reviewed head commit.")
    codex_gate.add_argument("--branch", required=True, help="Reviewed branch name.")
    codex_gate.add_argument("--out", required=True, help="Codex-only readiness report Markdown output path.")
    codex_gate.add_argument("--allow-dirty", action="store_true", help="Allow tracked dirty state and record it in the report.")
    codex_gate.add_argument("--mkdirs", action="store_true", help="Create missing output parent directories.")
    codex_gate.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    codex_gate.set_defaults(func=cmd_review)

    reviewed_delivery = review_sub.add_parser("reviewed-delivery", help="Run static reviewed-delivery orchestration from review output to codex-deliver.")
    reviewed_delivery.add_argument("--source", required=True, help="Source branch for the delivery run.")
    reviewed_delivery.add_argument("--target", required=True, help="Target branch for the delivery run.")
    reviewed_delivery.add_argument("--expected-source-head", required=True, help="Expected source branch head commit.")
    reviewed_delivery.add_argument("--expected-target-head", required=True, help="Expected target branch head commit.")
    reviewed_delivery.add_argument("--implementation-report", required=True, help="Implementation report Markdown path.")
    reviewed_delivery.add_argument("--review-bundle", required=True, help="Review bundle Markdown path.")
    reviewed_delivery.add_argument("--review-report", required=True, help="Claude review output Markdown/text path.")
    reviewed_delivery.add_argument("--expected-marker", required=True, help="Required PASS marker in the review output.")
    reviewed_delivery.add_argument("--expected-verdict", default="pass", help="Expected review verdict. Default: pass.")
    reviewed_delivery.add_argument("--out-dir", required=True, help="Directory for generated attestation, merge-packet, and codex-deliver reports.")
    reviewed_delivery.add_argument("--merge-marker", default="MERGE_GATE_PASS_MAINLINE_SYNCED", help="Suggested merge-gate completion marker.")
    reviewed_delivery.add_argument("--phase", help="Phase id recorded in the delivery report.")
    reviewed_delivery.add_argument("--run-id", help="Run id used for report naming and delivery identity.")
    reviewed_delivery.add_argument("--merge-authorized", action="store_true", help="Authorize merge execution when all reviewed-delivery gates pass.")
    reviewed_delivery.add_argument("--push-authorized", action="store_true", help="Authorize push execution after a successful authorized merge.")
    reviewed_delivery.add_argument("--allow-dirty", action="store_true", help="Allow tracked dirty state and record it as readiness evidence.")
    reviewed_delivery.add_argument("--mkdirs", action="store_true", help="Create missing output directories.")
    reviewed_delivery.add_argument("--evidence-bundle-out", help="Optional static reviewed-delivery evidence/readback bundle output path.")
    reviewed_delivery.add_argument("--evidence-bundle-format", choices=["json", "text"], default="json", help="Evidence bundle format when --evidence-bundle-out is set. Default: json.")
    reviewed_delivery.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    reviewed_delivery.set_defaults(func=cmd_review)

    codex_deliver = review_sub.add_parser("codex-deliver", help="Generate a one-click Codex delivery readiness report without merge or push by default.")
    codex_deliver.add_argument("--source", required=True, help="Source branch for the delivery run.")
    codex_deliver.add_argument("--target", required=True, help="Target branch for the delivery run.")
    codex_deliver.add_argument("--expected-source-head", required=True, help="Expected source branch head commit.")
    codex_deliver.add_argument("--expected-target-head", required=True, help="Expected target branch head commit.")
    codex_deliver.add_argument("--out", required=True, help="Codex delivery runner report Markdown output path.")
    codex_deliver.add_argument("--phase", help="Phase id recorded in the report.")
    codex_deliver.add_argument("--run-id", help="Run id recorded in the report.")
    codex_deliver.add_argument("--merge-authorized", action="store_true", help="Authorize merge execution when readiness and push gates pass.")
    codex_deliver.add_argument("--push-authorized", action="store_true", help="Authorize push execution after a successful authorized merge.")
    codex_deliver.add_argument("--allow-dirty", action="store_true", help="Allow tracked dirty state and record it as readiness evidence.")
    codex_deliver.add_argument("--mkdirs", action="store_true", help="Create missing output parent directories.")
    codex_deliver.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    codex_deliver.set_defaults(func=cmd_review)

    p = sub.add_parser("review-artifact", help="Export, verify, or close a Claude review artifact without calling providers.")
    review_sub = p.add_subparsers(dest="review_artifact_action", required=True)
    export = review_sub.add_parser("export", help="Export a Git commit-range review artifact.")
    export.add_argument("--base", required=True, help="Base commit for diff evidence.")
    export.add_argument("--review", required=True, help="Review commit for diff evidence and file snapshots.")
    export.add_argument("--branch", required=True, help="Branch name recorded in the integrity guard.")
    export.add_argument("--out", required=True, help="Markdown artifact output path. The .sha256 sidecar is written next to it.")
    export.add_argument("--title", required=True, help="Artifact title.")
    export.add_argument("--gate-mode", choices=["claude_pass", "codex_interim", "codex_self_check", "unknown"], default="unknown", help="Review gate mode recorded in the artifact. Default: unknown.")
    export.add_argument("--claude-status", choices=["pass", "pending", "unavailable", "not_required", "unknown"], default="unknown", help="Claude artifact review status recorded in the review gate. Default: unknown.")
    export.add_argument("--codex-self-check-status", choices=["pass", "fail", "not_run", "unknown"], default="not_run", help="Codex self-check status recorded in the review gate. Default: not_run.")
    export.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    export.set_defaults(func=cmd_review_artifact)
    close = review_sub.add_parser("close-pending", help="Close a Codex interim pending Claude review artifact with a Claude PASS attestation.")
    close.add_argument("--artifact", required=True, help="Codex interim review artifact path to close.")
    close.add_argument("--sha256", required=True, help="SHA256 sidecar for the interim artifact.")
    close.add_argument("--claude-attestation", help="Short Claude PASS attestation used for machine validation.")
    close.add_argument("--claude-review", help="Deprecated alias for --claude-attestation; do not pass verbose review reports here.")
    close.add_argument("--allow-fixture-attestation", action="store_true", help="Allow attestation_type=fixture for smoke tests only.")
    close.add_argument("--source-review-report", help="Optional full Claude review report kept as snapshot/hash evidence only.")
    close.add_argument("--out", required=True, help="Closure Markdown artifact output path. The .sha256 sidecar is written next to it.")
    close.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    close.set_defaults(func=cmd_review_artifact)
    check = review_sub.add_parser("self-check", help="Verify an exported review artifact and sidecar.")
    _add_review_artifact_check_args(check)
    check.set_defaults(func=cmd_review_artifact)
    verify = review_sub.add_parser("verify", help="Alias for self-check; verify an exported review artifact and sidecar.")
    _add_review_artifact_check_args(verify)
    verify.set_defaults(func=cmd_review_artifact)

    registry = review_sub.add_parser("registry", help="List, inspect, and summarize local review artifacts without providers.")
    registry_sub = registry.add_subparsers(dest="registry_action", required=True)
    registry_list = registry_sub.add_parser("list", help="List local review, closure, report, sha256, and run-bundle artifacts.")
    _add_repeatable_root_arg(registry_list)
    registry_list.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    registry_list.set_defaults(func=cmd_review_artifact)
    registry_inspect = registry_sub.add_parser("inspect", help="Inspect one artifact path without traceback on malformed inputs.")
    registry_inspect.add_argument("--path", required=True, help="Artifact path to inspect.")
    registry_inspect.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    registry_inspect.set_defaults(func=cmd_review_artifact)
    registry_status = registry_sub.add_parser("status", help="Summarize local artifact registry state.")
    _add_repeatable_root_arg(registry_status)
    registry_status.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    registry_status.set_defaults(func=cmd_review_artifact)
    lifecycle = review_sub.add_parser("lifecycle", help="Summarize and verify artifact lifecycle state without closing pending artifacts.")
    lifecycle_sub = lifecycle.add_subparsers(dest="lifecycle_action", required=True)
    for lifecycle_name in ("status", "verify"):
        lifecycle_parser = lifecycle_sub.add_parser(lifecycle_name, help=f"Artifact lifecycle {lifecycle_name}.")
        _add_repeatable_root_arg(lifecycle_parser)
        lifecycle_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
        lifecycle_parser.set_defaults(func=cmd_review_artifact)

    p = sub.add_parser("task-graph", help="Create and inspect deterministic framework task graphs without scheduling workers.")
    task_graph_sub = p.add_subparsers(dest="task_graph_action", required=True)
    task_graph_create = task_graph_sub.add_parser("create", help="Create a framework goal and minimal task graph.")
    task_graph_create.add_argument("--workspace-id", required=True, help="Stable workspace id.")
    task_graph_create.add_argument("--goal-id", required=True, help="Stable goal id.")
    task_graph_create.add_argument("--root", required=True, help="Root directory that contains the .ai/workspaces store.")
    task_graph_create.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    task_graph_create.set_defaults(func=cmd_task_graph)
    task_graph_ready = task_graph_sub.add_parser("ready", help="Compute ready tasks and blocked reasons for a framework goal.")
    task_graph_ready.add_argument("--workspace-id", required=True, help="Stable workspace id.")
    task_graph_ready.add_argument("--goal-id", required=True, help="Stable goal id.")
    task_graph_ready.add_argument("--root", required=True, help="Root directory that contains the .ai/workspaces store.")
    task_graph_ready.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    task_graph_ready.set_defaults(func=cmd_task_graph)

    p = sub.add_parser("runtime-event", help="Append and list deterministic runtime events inside a workspace run.")
    runtime_event_sub = p.add_subparsers(dest="runtime_event_action", required=True)
    runtime_event_append = runtime_event_sub.add_parser("append", help="Append one runtime event to an existing workspace run.")
    runtime_event_append.add_argument("--workspace-id", required=True, help="Stable workspace id.")
    runtime_event_append.add_argument("--run-id", required=True, help="Stable run id.")
    runtime_event_append.add_argument("--event-type", required=True, help="Stable event type, for example run.created.")
    runtime_event_append.add_argument("--actor", required=True, help="Stable actor name, for example runtime.")
    runtime_event_append.add_argument("--root", required=True, help="Root directory that contains the .ai/workspaces store.")
    runtime_event_append.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_event_append.set_defaults(func=cmd_runtime_event)
    runtime_event_list = runtime_event_sub.add_parser("list", help="List runtime events for an existing workspace run.")
    runtime_event_list.add_argument("--workspace-id", required=True, help="Stable workspace id.")
    runtime_event_list.add_argument("--run-id", required=True, help="Stable run id.")
    runtime_event_list.add_argument("--root", required=True, help="Root directory that contains the .ai/workspaces store.")
    runtime_event_list.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runtime_event_list.set_defaults(func=cmd_runtime_event)

    p = sub.add_parser("workspace", help="Manage deterministic framework workspaces and runs without provider calls.")
    workspace_sub = p.add_subparsers(dest="workspace_action", required=True)
    workspace_init = workspace_sub.add_parser("init", help="Initialize a framework workspace store.")
    workspace_init.add_argument("--workspace-id", required=True, help="Stable workspace id.")
    workspace_init.add_argument("--root", required=True, help="Root directory that contains the .ai/workspaces store.")
    workspace_init.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    workspace_init.set_defaults(func=cmd_workspace)
    workspace_inspect = workspace_sub.add_parser("inspect", help="Inspect a framework workspace store.")
    workspace_inspect.add_argument("--workspace-id", required=True, help="Stable workspace id.")
    workspace_inspect.add_argument("--root", required=True, help="Root directory that contains the .ai/workspaces store.")
    workspace_inspect.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    workspace_inspect.set_defaults(func=cmd_workspace)
    workspace_run_create = workspace_sub.add_parser("run-create", help="Create a framework run directory inside a workspace.")
    workspace_run_create.add_argument("--workspace-id", required=True, help="Stable workspace id.")
    workspace_run_create.add_argument("--run-id", required=True, help="Stable run id.")
    workspace_run_create.add_argument("--root", required=True, help="Root directory that contains the .ai/workspaces store.")
    workspace_run_create.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    workspace_run_create.set_defaults(func=cmd_workspace)

    p = sub.add_parser("doctor", help="Check AgentOffice adapter configuration without executing real adapters.")
    p.add_argument("--adapter", choices=["mock", "codex", "gemini", "grok", "claude"], help="Limit adapter diagnostics to one adapter.")
    view = p.add_mutually_exclusive_group()
    view.add_argument("--adapters", action="store_true", help="Print staged adapter mode table only.")
    view.add_argument("--profiles", action="store_true", help="Print static profile plan audit only.")
    p.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("export-evidence", help="Create a deterministic local evidence package for external review.")
    p.add_argument("--out", required=True, help="Output directory for manifest.json and README.md.")
    _add_repeatable_root_arg(p)
    p.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    p.set_defaults(func=cmd_export_evidence)
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
