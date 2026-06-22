from __future__ import annotations

from .planner import PlanningError, execution_blueprint_payload


class PacketError(ValueError):
    pass


PACKET_VERSION = 1
ALLOWED_ACTORS = ("codex", "reviewer", "judge")
PACKET_VALIDATION_COMMANDS = (
    "python3 -m agent_office packet --objective P6-10 --profile lowest-cost --actor codex",
    "python3 -m agent_office packet --objective P6-10 --profile lowest-cost --actor codex --json",
    "python3 -m agent_office packet --objective P6-10 --profile lowest-cost --actor reviewer",
    "python3 -m agent_office packet --objective P6-10 --profile lowest-cost --actor reviewer --json",
    "python3 -m agent_office packet --objective P6-10 --profile lowest-cost --actor judge",
    "python3 -m agent_office packet --objective P6-10 --profile lowest-cost --actor judge --json",
)


def execution_packet_payload(objective_id: str, profile_name: str, actor: str) -> dict[str, object]:
    if actor not in ALLOWED_ACTORS:
        raise PacketError(f"Unknown packet actor: {actor}")
    try:
        blueprint = execution_blueprint_payload(objective_id, profile_name)
    except PlanningError as exc:
        raise PacketError(str(exc)) from exc

    behavior = _actor_behavior(actor)
    return {
        "packet_version": PACKET_VERSION,
        "objective": {
            "id": blueprint["objective_id"],
            "name": blueprint["objective_name"],
            "summary": blueprint["objective_summary"],
        },
        "profile": {
            "selected": blueprint["selected_profile"],
            "default": blueprint["default_profile"],
            "is_default": blueprint["is_default"],
        },
        "blueprint": blueprint,
        "actor": actor,
        "instructions": behavior["instructions"],
        "safety_constraints": blueprint["safety_constraints"],
        "allowed_actions": behavior["allowed_actions"],
        "forbidden_actions": behavior["forbidden_actions"],
        "validation_commands": _merged_validation_commands(blueprint["validation_commands"]),
        "success_criteria": behavior["success_criteria"],
        "failure_criteria": behavior["failure_criteria"],
        "handoff_summary": behavior["handoff_summary"],
        "execution_enabled": False,
        "env_required": False,
        "provider_calls": blueprint["provider_calls"],
        "runtime_calls": False,
        "adapter_calls": False,
    }


def _actor_behavior(actor: str) -> dict[str, list[str] | str]:
    if actor == "codex":
        return {
            "instructions": [
                "Read relevant files before changing code.",
                "Implement minimal scoped changes that satisfy the packet objective and existing project style.",
                "Run validation commands after implementation.",
                "Self-fix on validation failure, then rerun the full validation set.",
                "Commit and push branch only after validation passes.",
            ],
            "allowed_actions": [
                "inspect repository files",
                "edit P6-13 scoped files",
                "add focused tests",
                "run local validation commands",
                "commit and push the implementation branch after validation passes",
            ],
            "forbidden_actions": [
                "read `.env`",
                "print env vars",
                "trigger real provider/runtime/adapter behavior",
                "modify unrelated files",
                "bypass tests",
            ],
            "success_criteria": [
                "packet CLI text and JSON outputs are deterministic",
                "all validation commands pass",
                "negative cases fail clearly without traceback",
                "branch is committed and pushed only after validation passes",
            ],
            "failure_criteria": [
                "validation fails after self-fix attempts",
                "packet output requires environment or real provider/runtime/adapter behavior",
                "unrelated files are modified",
            ],
            "handoff_summary": "Implementation packet for Codex: make minimal scoped changes, validate, self-fix failures, then commit and push.",
        }
    if actor == "reviewer":
        return {
            "instructions": [
                "Inspect diff for the packet implementation.",
                "Check contract stability across text and JSON outputs.",
                "Check safety boundaries for env, provider, runtime, and adapter behavior.",
                "Check negative cases for clear nonzero failures without traceback.",
                "Verify deterministic JSON suitable for tests.",
                "Report risks without modifying code.",
            ],
            "allowed_actions": [
                "inspect diff",
                "run read-only validation commands",
                "compare JSON output against the expected contract",
                "report risks and missing evidence",
            ],
            "forbidden_actions": [
                "code changes",
                "commits",
                "pushes",
                "`.env` reads",
                "real provider/runtime/adapter behavior",
            ],
            "success_criteria": [
                "diff matches the requested packet contract",
                "safety boundaries remain static and local",
                "negative cases and deterministic JSON are verified",
                "review report identifies material risks without code changes",
            ],
            "failure_criteria": [
                "contract fields are missing or unstable",
                "safety boundary evidence is incomplete",
                "review modifies code or pushes changes",
            ],
            "handoff_summary": "Reviewer packet: inspect diff and contract evidence, then report risks without modifying code.",
        }
    return {
        "instructions": [
            "Decide pass/fail for the completed packet work.",
            "Confirm validation evidence covers required commands and negative cases.",
            "Confirm no boundary breach for env, provider, runtime, or adapter behavior.",
            "Approve merge or reject with reasons.",
        ],
        "allowed_actions": [
            "inspect validation evidence",
            "inspect final diff and status",
            "approve merge when all criteria pass",
            "reject with reasons when criteria fail",
        ],
        "forbidden_actions": [
            "implementation changes",
            "silent fixes",
            "bypassing failed validation",
            "pushing without explicit pass",
        ],
        "success_criteria": [
            "pass/fail decision is explicit",
            "validation evidence is complete",
            "no boundary breach is confirmed",
            "merge approval or rejection reasons are clear",
        ],
        "failure_criteria": [
            "validation evidence is missing or failed",
            "boundary breach is unresolved",
            "judge changes implementation instead of deciding",
        ],
        "handoff_summary": "Judge packet: decide pass/fail from validation evidence and approve merge or reject with reasons.",
    }


def _merged_validation_commands(blueprint_commands: object) -> list[str]:
    commands = [str(command) for command in blueprint_commands] if isinstance(blueprint_commands, list) else []
    for command in PACKET_VALIDATION_COMMANDS:
        if command not in commands:
            commands.append(command)
    return commands
