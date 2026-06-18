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
from .doctor import bool_text, collect_doctor, doctor_json, format_adapters, format_doctor


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASKS_ROOT = PROJECT_ROOT / ".ai" / "tasks"
FINAL_FOR_CLAUDE_LIMIT = 4000
MAX_REWORK_ROUNDS = 2

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

    if config.name not in {"gemini", "codex", "grok"} and config.dry_run:
        reason = f"{config.name} adapter dry_run=true; real command was not executed."
        return maybe_fallback_to_mock(role, args, paths, config.name, config.fallback_to_mock, reason)

    if config.name not in {"gemini", "codex", "grok"} and not config.can_execute_commands:
        reason = (
            f"{config.name} adapter cannot execute commands unless "
            f"AGENTOFFICE_{config.name.upper()}_CAN_EXECUTE_COMMANDS=true."
        )
        return maybe_fallback_to_mock(role, args, paths, config.name, config.fallback_to_mock, reason)

    try:
        adapter = get_adapter(role, "real", config.name)
        method = getattr(adapter, role)
        return method(build_invocation(args, paths))
    except AdapterError as exc:
        return maybe_fallback_to_mock(role, args, paths, config.name, config.fallback_to_mock, str(exc))


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
        )
        if name == "new" and task_paths(args.task_id).root.exists():
            print(f"skip new: task already exists ({args.task_id})")
            continue
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
        if name == "run-demo":
            step.add_argument("--reset", action="store_true", help="Delete an existing task with this ID before running.")
        step.set_defaults(func=func)

    p = sub.add_parser("status", help="Print task state and artifact presence.")
    p.add_argument("task_id")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("adapters", help="List supported adapters without executing them.")
    p.set_defaults(func=cmd_adapters)

    p = sub.add_parser("doctor", help="Check AgentOffice adapter configuration without executing real adapters.")
    p.add_argument("--adapter", choices=["mock", "codex", "gemini", "grok", "claude"], help="Limit adapter diagnostics to one adapter.")
    p.add_argument("--adapters", action="store_true", help="Print staged adapter mode table only.")
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
