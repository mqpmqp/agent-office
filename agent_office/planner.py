from __future__ import annotations

from .objectives import ObjectiveSpecError, objective_detail_payload
from .profiles import ProfileError, profile_plan_payload


class PlanningError(ValueError):
    pass


PLANNING_VALIDATION_COMMANDS = (
    "python3 -m agent_office objectives --show P6-10",
    "python3 -m agent_office objectives --show P6-10 --json",
    "python3 -m agent_office objectives --validate",
    "python3 -m agent_office objectives --validate --json",
    "python3 -m agent_office plan --objective P6-10 --profile lowest-cost",
    "python3 -m agent_office plan --objective P6-10 --profile lowest-cost --json",
)
SAFETY_CONSTRAINTS = (
    "local_static_objective_registry_only",
    "local_static_profile_plan_only",
    "execution_disabled",
    "do_not_read_dotenv",
    "do_not_print_env_vars",
    "do_not_call_providers",
    "do_not_call_runtime",
    "do_not_call_adapters",
)


def execution_blueprint_payload(objective_id: str, profile_name: str) -> dict[str, object]:
    try:
        objective = objective_detail_payload(objective_id)
        profile_plan = profile_plan_payload(profile_name)
    except (ObjectiveSpecError, ProfileError) as exc:
        raise PlanningError(str(exc)) from exc

    provider_calls = [
        {
            "role": str(role["role"]),
            "provider": str(role["provider"]),
            "execution_category": str(role["execution_category"]),
            "call_enabled": False,
        }
        for role in profile_plan["roles"]
        if isinstance(role, dict)
    ]

    return {
        "kind": "execution_blueprint",
        "schema_version": 1,
        "objective_id": objective["phase"],
        "objective_name": objective["title"],
        "objective_summary": objective["objective"],
        "selected_profile": profile_plan["selected_profile"],
        "default_profile": profile_plan["default_profile"],
        "is_default": profile_plan["is_default"],
        "execution_enabled": False,
        "provider_calls": provider_calls,
        "runtime_calls": False,
        "adapter_calls": False,
        "env_required": False,
        "safety_constraints": list(SAFETY_CONSTRAINTS),
        "validation_commands": _merged_validation_commands(objective["validation"]),
        "next_actor": "human_or_codex",
        "next_action_summary": "Review the static blueprint, then hand implementation to a human or Codex after validation gates pass.",
    }


def _merged_validation_commands(objective_commands: object) -> list[str]:
    commands = [str(command) for command in objective_commands] if isinstance(objective_commands, list) else []
    for command in PLANNING_VALIDATION_COMMANDS:
        if command not in commands:
            commands.append(command)
    return commands
