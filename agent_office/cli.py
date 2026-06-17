from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


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


def require_mock(mock: bool, command: str) -> None:
    if not mock:
        raise AgentOfficeError(
            f"{command} currently supports --mock only. Provider adapters are intentionally not wired in the MVP."
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
    require_mock(args.mock, "context")
    paths = task_paths(args.task_id)
    task = load_task(paths)
    require_state(task, {"CREATED", "REQUEST_CHANGES"})
    write_file(
        paths.gemini_context,
        f"""# Gemini Context Summary

Mode: mock

## Compressed Repository Context

- Project uses file-based task collaboration under `.ai/tasks/{args.task_id}/`.
- No free-form AI chat is allowed; every agent has a fixed job and fixed artifact.
- Claude token budget is protected by forcing Claude to read only `final-for-claude.md`.

## Relevant Constraints

- Max rework rounds: {MAX_REWORK_ROUNDS}
- Final summary limit: {FINAL_FOR_CLAUDE_LIMIT} characters
- Real secrets must not be read or printed.
""",
    )
    transition(paths, task, "CONTEXT_READY", "Gemini mock context generated.")
    print("state=CONTEXT_READY")
    return 0


def cmd_implement(args: argparse.Namespace) -> int:
    require_mock(args.mock, "implement")
    paths = task_paths(args.task_id)
    task = load_task(paths)
    require_state(task, {"CONTEXT_READY", "REQUEST_CHANGES"})
    if task["state"] == "REQUEST_CHANGES":
        if int(task.get("rework_rounds", 0)) >= MAX_REWORK_ROUNDS:
            raise AgentOfficeError("Max rework rounds reached.")
        task["rework_rounds"] = int(task.get("rework_rounds", 0)) + 1
    write_file(
        paths.codex_report,
        f"""# Codex Implementation Report

Mode: mock

## Work Completed

- Created deterministic MVP artifacts for task `{args.task_id}`.
- Preserved the task directory protocol.
- Did not call external providers or read secrets.

## Verification

- Mock implementation completed.
- Patch artifact generated.
""",
    )
    write_file(
        paths.patch_diff,
        f"""diff --git a/mock-target.txt b/mock-target.txt
new file mode 100644
--- /dev/null
+++ b/mock-target.txt
@@ -0,0 +1,3 @@
+Task: {args.task_id}
+Implemented-by: Codex mock
+Status: deterministic MVP artifact
""",
    )
    transition(paths, task, "IMPLEMENTED", "Codex mock implementation generated.")
    print("state=IMPLEMENTED")
    return 0


def cmd_redteam(args: argparse.Namespace) -> int:
    require_mock(args.mock, "redteam")
    paths = task_paths(args.task_id)
    task = load_task(paths)
    require_state(task, {"IMPLEMENTED"})
    write_file(
        paths.grok_review,
        f"""# Grok Build Red-Team Review

Mode: mock

## Verdict

PASS_FOR_CLAUDE_SUMMARY

## Findings

- No uncontrolled multi-agent chat detected.
- Required artifacts are present.
- Claude is restricted to the final compressed artifact.
- No secret access is required in mock mode.

## Residual Risks

- Real provider adapters are intentionally absent in the MVP.
- Production use needs queue locking and provider-specific authentication hardening.
""",
    )
    transition(paths, task, "REVIEWED", "Grok Build mock red-team review generated.")
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
    require_mock(args.mock, "summarize")
    paths = task_paths(args.task_id)
    task = load_task(paths)
    require_state(task, {"REVIEWED"})
    write_file(paths.final_for_claude, build_final_summary(paths, task))
    transition(paths, task, "SUMMARIZED", "Orchestrator wrote Claude-only compressed summary.")
    print(f"state=SUMMARIZED final_chars={len(paths.final_for_claude.read_text(encoding='utf-8'))}")
    return 0


def cmd_final(args: argparse.Namespace) -> int:
    require_mock(args.mock, "final")
    paths = task_paths(args.task_id)
    task = load_task(paths)
    require_state(task, {"SUMMARIZED"})
    final_text = paths.final_for_claude.read_text(encoding="utf-8")
    decision = "APPROVED"
    if "FORCE_REQUEST_CHANGES" in final_text:
        decision = "REQUEST_CHANGES"
    elif "FORCE_REJECT" in final_text:
        decision = "REJECTED"
    append_history(task, "SUMMARIZED->CLAUDE_DECIDED", "Claude mock read final-for-claude.md only.")
    write_file(
        paths.claude_decision,
        f"""# Claude Decision

Mode: mock

Decision: {decision}

## Scope Read By Claude

- Read: `final-for-claude.md`
- Did not read: full repository
- Did not read: full logs
- Did not read: full diff

## Rationale

The compressed artifact was sufficient for a mock MVP decision.
""",
    )
    transition(paths, task, decision, f"Claude mock decision: {decision}.")
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


def cmd_run_demo(args: argparse.Namespace) -> int:
    require_mock(args.mock, "run-demo")
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
        step_args = argparse.Namespace(task_id=args.task_id, mock=True)
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
        step.set_defaults(func=func)

    p = sub.add_parser("status", help="Print task state and artifact presence.")
    p.add_argument("task_id")
    p.set_defaults(func=cmd_status)
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

