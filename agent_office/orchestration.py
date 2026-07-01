from __future__ import annotations

import hashlib
import json
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
PACKET_ROLES = ("planner", "router", "implementer", "reviewer", "verifier", "synthesizer", "judge")
REQUIRED_FILES = (
    "manifest.json",
    "task_understanding.md",
    "decomposition.md",
    "task_graph.json",
    "planner_packet.md",
    "router_packet.md",
    "implementer_packet.md",
    "reviewer_packet.md",
    "verifier_packet.md",
    "synthesizer_packet.md",
    "judge_packet.md",
    "phase_report.md",
    "README.md",
)
VALIDATION_COMMANDS = (
    "python3 -m agent_office orchestrate inspect --path <artifact-dir> --json",
    "python3 -m agent_office orchestrate validate --path <artifact-dir> --json",
    "attach project-specific validation output before synthesis or judge approval",
)
REVIEW_GATE_HINT = "Review phase_report.md, manifest.json, task_graph.json, and validation output before approval or merge."
FORBIDDEN_ACTIONS = [
    "do not read .env",
    "do not print env vars",
    "do not claim tests passed unless test output is provided",
    "do not make external provider calls in static mode",
    "do not merge/push/tag unless explicitly authorized",
]
SAFETY = {
    "mode": "static",
    "external_call_made": False,
    "provider_calls": [],
    "env_required": False,
    "dotenv_read": False,
    "env_vars_printed": False,
    "repo_mutation": False,
}
TASK_TYPE_RULES = (
    ("code_review", ("review", "audit", "inspect", "merge risk", "\u5ba1\u67e5", "\u5ba1\u6838")),
    ("debugging", ("bug", "fail", "failure", "error", "traceback", "debug", "regression")),
    ("software_change", ("implement", "add", "fix", "change", "modify", "patch", "\u4fee\u6539")),
    ("research", ("research", "compare", "investigate", "study", "\u7814\u7a76")),
    ("planning", ("plan", "roadmap", "scope", "proposal", "\u89c4\u5212")),
    ("documentation", ("docs", "readme", "document", "documentation", "\u6587\u6863")),
)


class OrchestrationError(ValueError):
    pass


def orchestrate_run_payload(*, task: str, mode: str, out: str | Path) -> dict[str, Any]:
    command = _command_text("orchestrate run", ["--task", task, "--mode", mode, "--out", str(out), "--json"])
    errors: list[str] = []
    warnings: list[str] = []
    if mode != "static":
        errors.append("only_static_mode_supported")
    if not task.strip():
        errors.append("task_required")
    out_path = Path(out)
    if out_path.exists() and out_path.is_symlink():
        errors.append("output_path_symlink_refused")
    if out_path.exists() and not out_path.is_dir():
        errors.append("output_path_not_directory")
    if errors:
        return _run_error_payload(command, out_path, task, mode, warnings, errors)

    try:
        out_path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        errors.append(f"output_directory_create_failed: {exc}")
        return _run_error_payload(command, out_path, task, mode, warnings, errors)
    understanding = task_understanding(task)
    decomposition = decompose_task(task, understanding["task_type"])
    assignments = role_assignments(understanding["task_type"])
    graph = task_graph(task, assignments, understanding["task_type"])
    orchestration_id = _orchestration_id(task)
    source_state = _git_source_state()
    created_files = list(REQUIRED_FILES)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "orchestration_id": orchestration_id,
        "mode": "static",
        "task": task,
        "external_call_made": False,
        "provider_calls": [],
        "task_understanding": understanding,
        "decomposition": decomposition,
        "role_assignments": assignments,
        "task_graph": graph,
        "created_files": created_files,
        "next_actions": next_actions(understanding["task_type"]),
        "safety": dict(SAFETY),
        "source_state": source_state,
        "generated_artifacts": {
            "artifact_root": ".",
            "manifest_path": "manifest.json",
            "phase_report_path": "phase_report.md",
        },
        "validation_commands": list(VALIDATION_COMMANDS),
        "review_gate_hint": REVIEW_GATE_HINT,
        "known_followups": [],
    }
    write_errors = _write_orchestration_files(out_path, manifest)
    errors.extend(write_errors)
    return {
        "valid": not errors,
        "command": command,
        "path": str(out_path),
        "manifest_path": str(out_path / "manifest.json"),
        "phase_report_path": str(out_path / "phase_report.md"),
        "orchestration_id": orchestration_id,
        "mode": "static",
        "task_type": understanding["task_type"],
        "external_call_made": False,
        "provider_calls": [],
        "source_state": source_state["state"],
        "source_commit": source_state["source_commit"],
        "baseline_commit": source_state["baseline_commit"],
        "validation_commands": _validation_commands_for_path(out_path),
        "review_gate_hint": REVIEW_GATE_HINT,
        "known_followups": [],
        "created_files": created_files if not errors else [],
        "warnings": warnings,
        "errors": errors,
    }


def orchestrate_inspect_payload(*, path: str | Path) -> dict[str, Any]:
    command = _command_text("orchestrate inspect", ["--path", str(path), "--json"])
    manifest, warnings, errors = _load_manifest(Path(path))
    summary: dict[str, Any] = {}
    if manifest:
        task_graph_value = manifest.get("task_graph") if isinstance(manifest.get("task_graph"), dict) else {}
        understanding = manifest.get("task_understanding") if isinstance(manifest.get("task_understanding"), dict) else {}
        role_assignments_value = manifest.get("role_assignments") if isinstance(manifest.get("role_assignments"), list) else []
        source_state = manifest.get("source_state") if isinstance(manifest.get("source_state"), dict) else {}
        generated_artifacts = manifest.get("generated_artifacts") if isinstance(manifest.get("generated_artifacts"), dict) else {}
        summary = {
            "orchestration_id": manifest.get("orchestration_id"),
            "mode": manifest.get("mode"),
            "task": manifest.get("task"),
            "task_type": understanding.get("task_type"),
            "risk_level": understanding.get("risk_level"),
            "external_call_made": manifest.get("external_call_made"),
            "provider_calls": manifest.get("provider_calls"),
            "role_count": len(role_assignments_value),
            "graph_node_count": len(task_graph_value.get("nodes", [])),
            "graph_edge_count": len(task_graph_value.get("edges", [])),
            "next_actions": manifest.get("next_actions", []),
            "source_state": source_state.get("state"),
            "source_commit": source_state.get("source_commit"),
            "baseline_commit": source_state.get("baseline_commit"),
            "phase_report_path": generated_artifacts.get("phase_report_path"),
            "validation_commands": manifest.get("validation_commands", []),
            "review_gate_hint": manifest.get("review_gate_hint"),
        }
    return {
        "valid": bool(manifest and not errors),
        "command": command,
        "path": str(path),
        **summary,
        "warnings": warnings,
        "errors": errors,
    }


def orchestrate_validate_payload(*, path: str | Path) -> dict[str, Any]:
    command = _command_text("orchestrate validate", ["--path", str(path), "--json"])
    root = Path(path)
    warnings: list[str] = []
    errors: list[str] = []
    missing = [name for name in REQUIRED_FILES if not (root / name).is_file()]
    checks: list[dict[str, str]] = []
    _add_check(checks, "path_exists", root.exists() and root.is_dir())
    _add_check(checks, "required_files_present", not missing)
    if missing:
        errors.append("missing_required_files")
    manifest, manifest_warnings, manifest_errors = _load_manifest(root)
    warnings.extend(manifest_warnings)
    errors.extend(manifest_errors)
    _add_check(checks, "manifest_json_parseable", bool(manifest))
    if manifest:
        graph = manifest.get("task_graph") if isinstance(manifest.get("task_graph"), dict) else {}
        _add_check(checks, "external_call_made_false", manifest.get("external_call_made") is False)
        _add_check(checks, "provider_calls_empty", manifest.get("provider_calls") == [])
        _add_check(checks, "task_graph_has_nodes", bool(graph.get("nodes")))
        _add_check(checks, "task_graph_has_edges", bool(graph.get("edges")))
        _add_check(checks, "task_graph_has_execution_order", bool(graph.get("execution_order")))
        safety = manifest.get("safety") if isinstance(manifest.get("safety"), dict) else {}
        _add_check(checks, "dotenv_not_required", safety.get("dotenv_read") is False and safety.get("env_required") is False)
    else:
        for name in ("external_call_made_false", "provider_calls_empty", "task_graph_has_nodes", "task_graph_has_edges", "task_graph_has_execution_order", "dotenv_not_required"):
            _add_check(checks, name, False)
    valid = not errors and all(check["status"] == "pass" for check in checks)
    return {
        "valid": valid,
        "command": command,
        "path": str(path),
        "required_files": list(REQUIRED_FILES),
        "missing_files": missing,
        "checks": checks,
        "warnings": _dedupe(warnings),
        "errors": _dedupe(errors),
    }


def task_understanding(task: str) -> dict[str, Any]:
    task_type_value = classify_task(task)
    return {
        "task": task,
        "inferred_intent": _intent_for_type(task_type_value),
        "task_type": task_type_value,
        "risk_level": _risk_level(task, task_type_value),
        "requires_code_change": task_type_value in {"software_change", "debugging", "documentation"},
        "requires_external_provider": False,
        "assumptions": [
            "static mode only",
            "future agents consume generated packets manually or through a later runtime",
            "validation evidence must be attached before claims of success",
        ],
        "non_goals": [
            "call external model APIs",
            "execute providers or adapters",
            "merge, push, or tag changes",
            "read .env or print environment variables",
        ],
    }


def classify_task(task: str) -> str:
    normalized = task.lower()
    for task_type_value, needles in TASK_TYPE_RULES:
        if any(needle in normalized for needle in needles):
            return task_type_value
    return "unknown"


def decompose_task(task: str, task_type_value: str) -> dict[str, Any]:
    subtasks = _subtasks_for_type(task_type_value)
    return {
        "objective": task,
        "subtasks": subtasks,
        "dependencies": _dependencies(subtasks),
        "expected_artifacts": [
            "task_understanding.md",
            "decomposition.md",
            "task_graph.json",
            "role packets",
            "final orchestration artifact",
        ],
        "validation_strategy": _validation_strategy(task_type_value),
    }


def role_assignments(task_type_value: str) -> list[dict[str, Any]]:
    emphasis = _role_emphasis(task_type_value)
    return [
        {
            "role": role,
            "responsibility": _responsibility(role, task_type_value, emphasis.get(role, "supporting")),
            "input_artifacts": _role_inputs(role),
            "output_artifacts": _role_outputs(role),
            "allowed_actions": _allowed_actions(role),
            "forbidden_actions": list(FORBIDDEN_ACTIONS),
        }
        for role in PACKET_ROLES
    ]


def task_graph(task: str, assignments: list[dict[str, Any]], task_type_value: str) -> dict[str, Any]:
    nodes = [
        {
            "id": role["role"],
            "role": role["role"],
            "packet": f"{role['role']}_packet.md",
            "expected_artifacts": role["output_artifacts"],
        }
        for role in assignments
    ]
    order = [role["role"] for role in assignments]
    return {
        "graph_id": _graph_id(task),
        "nodes": nodes,
        "edges": [{"from": order[index], "to": order[index + 1]} for index in range(len(order) - 1)],
        "execution_order": order,
        "stop_conditions": [
            "required input artifact missing",
            "safety boundary would be violated",
            "validation evidence contradicts success claim",
        ],
        "success_criteria": [
            f"{task_type_value} orchestration path is complete",
            "all packets include evidence requirements and forbidden actions",
            "final judge can approve or request changes using captured artifacts",
        ],
    }


def next_actions(task_type_value: str) -> list[str]:
    return [
        "review manifest.json and task_graph.json",
        "hand role packets to future static or provider-backed workers",
        "capture validation outputs before synthesis or judge approval",
        f"apply {task_type_value} route-specific review criteria",
    ]


def format_orchestrate_run(payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            "AgentOffice orchestration artifact generated",
            f"path: {payload.get('path')}",
            f"orchestration_id: {payload.get('orchestration_id')}",
            f"mode: {payload.get('mode')}",
            f"task_type: {payload.get('task_type')}",
            f"external_call_made: {str(payload.get('external_call_made')).lower()}",
            f"provider_calls: {payload.get('provider_calls')}",
            f"source_state: {payload.get('source_state')}",
            f"source_commit: {payload.get('source_commit')}",
            f"baseline_commit: {payload.get('baseline_commit')}",
            f"phase_report_path: {payload.get('phase_report_path')}",
            f"review_gate_hint: {payload.get('review_gate_hint')}",
            f"created_files: {len(payload.get('created_files', []))}",
            f"valid: {str(payload.get('valid')).lower()}",
            f"errors: {len(payload.get('errors', []))}",
        ]
    )


def format_orchestrate_inspect(payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            "AgentOffice orchestration summary",
            f"path: {payload.get('path')}",
            f"orchestration_id: {payload.get('orchestration_id')}",
            f"task_type: {payload.get('task_type')}",
            f"risk_level: {payload.get('risk_level')}",
            f"role_count: {payload.get('role_count')}",
            f"graph_node_count: {payload.get('graph_node_count')}",
            f"external_call_made: {str(payload.get('external_call_made')).lower()}",
            f"source_state: {payload.get('source_state')}",
            f"source_commit: {payload.get('source_commit')}",
            f"baseline_commit: {payload.get('baseline_commit')}",
            f"phase_report_path: {payload.get('phase_report_path')}",
            f"review_gate_hint: {payload.get('review_gate_hint')}",
            f"valid: {str(payload.get('valid')).lower()}",
            f"errors: {len(payload.get('errors', []))}",
        ]
    )


def format_orchestrate_validate(payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            "AgentOffice orchestration validation",
            f"path: {payload.get('path')}",
            f"valid: {str(payload.get('valid')).lower()}",
            f"missing_files: {len(payload.get('missing_files', []))}",
            f"checks: {len(payload.get('checks', []))}",
            f"errors: {len(payload.get('errors', []))}",
        ]
    )


def _write_orchestration_files(out: Path, manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    files = {
        "task_understanding.md": _task_understanding_markdown(manifest),
        "decomposition.md": _decomposition_markdown(manifest),
        "task_graph.json": json.dumps(manifest["task_graph"], indent=2, ensure_ascii=False) + "\n",
        "phase_report.md": _phase_report_markdown(manifest),
        "README.md": _readme_markdown(manifest),
    }
    for assignment in manifest["role_assignments"]:
        files[f"{assignment['role']}_packet.md"] = _packet_markdown(manifest, assignment)
    files["manifest.json"] = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    for filename, content in files.items():
        path = out / filename
        if path.exists() and path.is_symlink():
            errors.append(f"refusing_to_write_symlink: {filename}")
            continue
        try:
            path.write_text(content, encoding="utf-8")
        except OSError as exc:
            errors.append(f"write_failed: {filename}: {exc}")
    return errors


def _task_understanding_markdown(manifest: dict[str, Any]) -> str:
    item = manifest["task_understanding"]
    lines = ["# Task Understanding", ""]
    for key in ("task", "inferred_intent", "task_type", "risk_level", "requires_code_change", "requires_external_provider"):
        lines.append(f"- {key}: {item[key]}")
    lines.extend(["", "## Assumptions"])
    lines.extend(f"- {value}" for value in item["assumptions"])
    lines.extend(["", "## Non-goals"])
    lines.extend(f"- {value}" for value in item["non_goals"])
    return "\n".join(lines) + "\n"


def _decomposition_markdown(manifest: dict[str, Any]) -> str:
    item = manifest["decomposition"]
    lines = ["# Decomposition", "", f"objective: {item['objective']}", "", "## Subtasks"]
    for subtask in item["subtasks"]:
        lines.append(f"- {subtask['id']}: {subtask['title']} ({subtask['owner']})")
    lines.extend(["", "## Dependencies"])
    lines.extend(f"- {edge['from']} -> {edge['to']}" for edge in item["dependencies"])
    lines.extend(["", "## Expected Artifacts"])
    lines.extend(f"- {artifact}" for artifact in item["expected_artifacts"])
    lines.extend(["", "## Validation Strategy"])
    lines.extend(f"- {step}" for step in item["validation_strategy"])
    return "\n".join(lines) + "\n"


def _readme_markdown(manifest: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# AgentOffice Static Orchestration Artifact",
            "",
            "This directory is a white-box static multi-agent orchestration artifact.",
            "It does not call external providers, runtimes, adapters, or model APIs.",
            "",
            "## Summary",
            f"- orchestration_id: {manifest['orchestration_id']}",
            f"- mode: {manifest['mode']}",
            f"- task_type: {manifest['task_understanding']['task_type']}",
            f"- external_call_made: {str(manifest['external_call_made']).lower()}",
            f"- provider_calls: {manifest['provider_calls']}",
            f"- source_state: {manifest['source_state']['state']}",
            f"- source_commit: {manifest['source_state']['source_commit']}",
            f"- baseline_commit: {manifest['source_state']['baseline_commit']}",
            f"- phase_report_path: {manifest['generated_artifacts']['phase_report_path']}",
            "",
            "## Files",
            *[f"- {filename}" for filename in REQUIRED_FILES],
            "",
            "## Next Actions",
            *[f"- {action}" for action in manifest["next_actions"]],
            "",
        ]
    )


def _phase_report_markdown(manifest: dict[str, Any]) -> str:
    source = manifest["source_state"]
    artifacts = manifest["generated_artifacts"]
    lines = [
        "# AgentOffice Orchestration Phase Report",
        "",
        "marker: ORCHESTRATION_REVIEWABLE_PHASE_REPORT",
        f"orchestration_id: {manifest['orchestration_id']}",
        f"mode: {manifest['mode']}",
        f"task_type: {manifest['task_understanding']['task_type']}",
        "",
        "## Generated Artifacts",
        f"- artifact_root: {artifacts['artifact_root']}",
        f"- manifest_path: {artifacts['manifest_path']}",
        f"- phase_report_path: {artifacts['phase_report_path']}",
        "",
        "## Source State",
        f"- source_branch: {source['source_branch']}",
        f"- source_commit: {source['source_commit']}",
        f"- source_state: {source['state']}",
        f"- baseline_ref: {source['baseline_ref']}",
        f"- baseline_commit: {source['baseline_commit']}",
        f"- tracked_dirty: {str(source['tracked_dirty']).lower()}",
        f"- pending_change_state: {source['pending_change_state']}",
        f"- pending_change_count: {source['pending_change_count']}",
        "",
        "## Validation",
    ]
    lines.extend(f"- {command}" for command in manifest["validation_commands"])
    lines.extend(
        [
            "",
            "## Next Action",
            f"- {manifest['review_gate_hint']}",
            "",
            "## Known Follow-ups",
        ]
    )
    followups = manifest.get("known_followups", [])
    if followups:
        lines.extend(f"- {item}" for item in followups)
    else:
        lines.append("- none")
    pending_changes = source.get("pending_changes", [])
    if pending_changes:
        lines.extend(["", "## Pending Tracked Changes"])
        lines.extend(f"- {item}" for item in pending_changes)
    lines.append("")
    return "\n".join(lines)


def _packet_markdown(manifest: dict[str, Any], assignment: dict[str, Any]) -> str:
    lines = [
        f"# AgentOffice Packet: {assignment['role']}",
        "",
        f"role: {assignment['role']}",
        f"task: {manifest['task']}",
        f"context: static {manifest['task_understanding']['task_type']} orchestration; external_call_made=false",
        "",
        "## Inputs",
    ]
    lines.extend(f"- {item}" for item in assignment["input_artifacts"])
    lines.extend(["", "## Allowed Actions"])
    lines.extend(f"- {item}" for item in assignment["allowed_actions"])
    lines.extend(["", "## Forbidden Actions"])
    lines.extend(f"- {item}" for item in assignment["forbidden_actions"])
    lines.extend(["", "## Expected Output"])
    lines.extend(f"- {item}" for item in assignment["output_artifacts"])
    lines.extend(
        [
            "",
            "## Evidence Requirements",
            "- cite input artifact filenames used",
            "- attach validation output before claiming success",
            "- record assumptions and unresolved risks",
            "",
            "## Stop Conditions",
        ]
    )
    lines.extend(f"- {item}" for item in manifest["task_graph"]["stop_conditions"])
    lines.append("")
    return "\n".join(lines)


def _subtasks_for_type(task_type_value: str) -> list[dict[str, str]]:
    common = [
        {"id": "understand", "title": "capture task intent, risk, assumptions, and non-goals", "owner": "planner"},
        {"id": "route", "title": "select role path and artifact flow", "owner": "router"},
    ]
    tail = [
        {"id": "synthesize", "title": "combine role outputs into a final artifact", "owner": "synthesizer"},
        {"id": "judge", "title": "approve, block, or request changes using evidence", "owner": "judge"},
    ]
    middle_by_type = {
        "software_change": [
            {"id": "implement", "title": "prepare scoped code-change packet", "owner": "implementer"},
            {"id": "review", "title": "review diff and safety boundaries", "owner": "reviewer"},
            {"id": "verify", "title": "run and capture validation evidence", "owner": "verifier"},
        ],
        "code_review": [
            {"id": "review", "title": "inspect artifact/code delta and risks", "owner": "reviewer"},
            {"id": "verify", "title": "check validation artifacts and contract coverage", "owner": "verifier"},
        ],
        "debugging": [
            {"id": "reproduce", "title": "isolate failure signals and reproduction evidence", "owner": "verifier"},
            {"id": "repair", "title": "prepare minimal fix packet", "owner": "implementer"},
            {"id": "review", "title": "review regression risk", "owner": "reviewer"},
        ],
        "research": [
            {"id": "investigate", "title": "collect static research questions and sources", "owner": "planner"},
            {"id": "synthesize_findings", "title": "summarize tradeoffs and evidence", "owner": "synthesizer"},
        ],
        "planning": [
            {"id": "plan", "title": "define scope, milestones, and decision gates", "owner": "planner"},
            {"id": "judge_scope", "title": "validate feasibility and boundaries", "owner": "judge"},
        ],
        "documentation": [
            {"id": "draft", "title": "prepare documentation update packet", "owner": "implementer"},
            {"id": "review_docs", "title": "check clarity and consistency", "owner": "reviewer"},
        ],
        "unknown": [
            {"id": "clarify", "title": "surface assumptions and safe next questions", "owner": "planner"},
            {"id": "judge_clarity", "title": "decide whether execution should proceed", "owner": "judge"},
        ],
    }
    return common + middle_by_type.get(task_type_value, middle_by_type["unknown"]) + tail


def _dependencies(subtasks: list[dict[str, str]]) -> list[dict[str, str]]:
    return [{"from": subtasks[index]["id"], "to": subtasks[index + 1]["id"]} for index in range(len(subtasks) - 1)]


def _validation_strategy(task_type_value: str) -> list[str]:
    base = [
        "validate manifest schema and required files",
        "confirm external_call_made is false and provider_calls is empty",
        "confirm every packet repeats forbidden actions",
    ]
    if task_type_value in {"software_change", "debugging", "documentation"}:
        base.append("run project tests before implementation claims are accepted")
    if task_type_value == "code_review":
        base.append("check review evidence, blocker findings, and merge readiness separately")
    return base


def _role_emphasis(task_type_value: str) -> dict[str, str]:
    by_type = {
        "software_change": {"planner": "primary", "implementer": "primary", "reviewer": "primary", "verifier": "primary"},
        "code_review": {"reviewer": "primary", "verifier": "primary", "judge": "primary"},
        "debugging": {"implementer": "primary", "verifier": "primary", "reviewer": "primary"},
        "research": {"planner": "primary", "synthesizer": "primary"},
        "planning": {"planner": "primary", "judge": "primary"},
        "documentation": {"implementer": "primary", "reviewer": "primary", "synthesizer": "primary"},
    }
    return by_type.get(task_type_value, {"planner": "primary", "judge": "primary"})


def _responsibility(role: str, task_type_value: str, emphasis: str) -> str:
    base = {
        "planner": "understand the objective and define the safe work shape",
        "router": "map task type to role sequence and artifact flow",
        "implementer": "prepare the execution packet for scoped changes or analysis",
        "reviewer": "inspect outputs for contract, safety, and regression risks",
        "verifier": "collect validation evidence and reject unsupported success claims",
        "synthesizer": "combine role outputs into a final orchestration artifact",
        "judge": "make the final approve/block/request-changes decision from evidence",
    }[role]
    return f"{base}; emphasis={emphasis}; task_type={task_type_value}"


def _role_inputs(role: str) -> list[str]:
    mapping = {
        "planner": ["user task", "task_understanding.md"],
        "router": ["task_understanding.md", "decomposition.md"],
        "implementer": ["decomposition.md", "router_packet.md"],
        "reviewer": ["implementer_packet.md", "task_graph.json"],
        "verifier": ["reviewer_packet.md", "validation outputs"],
        "synthesizer": ["all role packets", "validation outputs"],
        "judge": ["final orchestration artifact", "validation outputs", "risk summary"],
    }
    return mapping[role]


def _role_outputs(role: str) -> list[str]:
    return [f"{role}_result.md", f"{role}_evidence.json"]


def _allowed_actions(role: str) -> list[str]:
    common = ["read declared input artifacts", "write declared output artifacts", "record assumptions and risks"]
    by_role = {
        "planner": ["decompose task", "define validation strategy"],
        "router": ["assign roles", "update execution graph"],
        "implementer": ["prepare scoped work plan", "describe required code/docs changes"],
        "reviewer": ["inspect artifacts", "report blockers, majors, minors, and nits"],
        "verifier": ["run authorized validation commands", "capture raw outputs"],
        "synthesizer": ["summarize evidence", "produce final artifact draft"],
        "judge": ["approve", "request changes", "block on missing evidence"],
    }
    return common + by_role[role]


def _intent_for_type(task_type_value: str) -> str:
    return {
        "software_change": "coordinate a safe code or documentation change",
        "code_review": "review artifacts and risks before approval",
        "research": "investigate options and synthesize evidence",
        "planning": "turn a goal into scoped milestones and gates",
        "debugging": "reproduce, repair, and verify a failure",
        "documentation": "improve project documentation safely",
        "unknown": "clarify task shape before execution",
    }[task_type_value]


def _risk_level(task: str, task_type_value: str) -> str:
    lowered = task.lower()
    if any(word in lowered for word in ("secret", "credential", "delete", "production", "security", "payment", "data loss")):
        return "high"
    if task_type_value in {"software_change", "debugging", "code_review"}:
        return "medium"
    return "low"


def _load_manifest(path: Path) -> tuple[dict[str, Any] | None, list[str], list[str]]:
    warnings: list[str] = []
    errors: list[str] = []
    if path.is_symlink():
        return None, warnings, ["path_symlink_refused"]
    if not path.exists():
        return None, warnings, ["path_missing"]
    if not path.is_dir():
        return None, warnings, ["path_not_directory"]
    manifest_path = path / "manifest.json"
    if manifest_path.is_symlink():
        return None, warnings, ["manifest_symlink_refused"]
    if not manifest_path.is_file():
        return None, warnings, ["manifest_missing"]
    try:
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        return None, warnings, ["manifest_non_utf8"]
    except json.JSONDecodeError as exc:
        return None, warnings, [f"manifest_malformed: {exc.msg}"]
    except OSError as exc:
        return None, warnings, [f"manifest_read_error: {exc}"]
    if not isinstance(value, dict):
        return None, warnings, ["manifest_not_object"]
    return value, warnings, errors


def _run_error_payload(command: str, out_path: Path, task: str, mode: str, warnings: list[str], errors: list[str]) -> dict[str, Any]:
    return {
        "valid": False,
        "command": command,
        "path": str(out_path),
        "manifest_path": str(out_path / "manifest.json"),
        "phase_report_path": str(out_path / "phase_report.md"),
        "orchestration_id": _orchestration_id(task),
        "mode": mode,
        "task_type": classify_task(task),
        "external_call_made": False,
        "provider_calls": [],
        "created_files": [],
        "warnings": warnings,
        "errors": errors,
    }


def _git_source_state() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[1]
    unavailable = {
        "available": False,
        "source_branch": "unavailable",
        "source_commit": "unavailable",
        "state": "unavailable",
        "baseline_ref": "unavailable",
        "baseline_commit": "unavailable",
        "tracked_dirty": False,
        "pending_change_state": "unavailable",
        "pending_change_count": 0,
        "pending_changes": [],
    }
    if _git_output(root, ["rev-parse", "--is-inside-work-tree"]) != "true":
        return unavailable
    head = _git_output(root, ["rev-parse", "HEAD"])
    if not head:
        return unavailable
    branch = _git_output(root, ["rev-parse", "--abbrev-ref", "HEAD"]) or "detached"
    baseline_ref = _baseline_ref(root)
    baseline_commit = head
    if baseline_ref != "HEAD":
        baseline_commit = _git_output(root, ["merge-base", "HEAD", baseline_ref]) or head
    status_text = _git_output(root, ["status", "--porcelain=v1", "--untracked-files=no"])
    pending_changes = status_text.splitlines() if status_text else []
    tracked_dirty = bool(pending_changes)
    return {
        "available": True,
        "source_branch": branch,
        "source_commit": head,
        "state": "dirty" if tracked_dirty else "clean",
        "baseline_ref": baseline_ref,
        "baseline_commit": baseline_commit,
        "tracked_dirty": tracked_dirty,
        "pending_change_state": "tracked_changes_pending" if tracked_dirty else "none",
        "pending_change_count": len(pending_changes),
        "pending_changes": pending_changes,
    }


def _baseline_ref(root: Path) -> str:
    if _git_output(root, ["rev-parse", "--verify", "origin/phase6/mainline"]):
        return "origin/phase6/mainline"
    upstream = _git_output(root, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    return upstream or "HEAD"


def _git_output(root: Path, args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except OSError:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _validation_commands_for_path(path: Path) -> list[str]:
    return [
        _command_text("orchestrate inspect", ["--path", str(path), "--json"]),
        _command_text("orchestrate validate", ["--path", str(path), "--json"]),
        "attach project-specific validation output before synthesis or judge approval",
    ]


def _add_check(checks: list[dict[str, str]], name: str, passed: bool) -> None:
    checks.append({"name": name, "status": "pass" if passed else "fail"})


def _orchestration_id(task: str) -> str:
    return f"ao-orch-{hashlib.sha256(task.encode('utf-8')).hexdigest()[:12]}"


def _graph_id(task: str) -> str:
    return f"graph-{hashlib.sha256(('graph:' + task).encode('utf-8')).hexdigest()[:12]}"


def _command_text(base: str, parts: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in ["python3", "-m", "agent_office", *base.split(), *parts])


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
