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
CONTRACT_SCHEMA_VERSION = "packet-contract-v1"
PACKET_REQUIRED_SECTIONS = (
    "packet_version",
    "objective",
    "profile",
    "blueprint",
    "actor",
    "instructions",
    "safety_constraints",
    "allowed_actions",
    "forbidden_actions",
    "validation_commands",
    "success_criteria",
    "failure_criteria",
    "handoff_summary",
    "execution_enabled",
    "env_required",
    "provider_calls",
    "runtime_calls",
    "adapter_calls",
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


def packet_contract_validation_payload(objective_id: str, profile_name: str, actor: str) -> dict[str, object]:
    packet = execution_packet_payload(objective_id, profile_name, actor)
    objective = packet.get("objective")
    profile = packet.get("profile")
    checks: list[dict[str, str]] = []
    external_behavior = {
        "provider_calls": False,
        "runtime_adapter_calls": False,
        "env_reads": False,
        "env_var_printing": False,
        "artifact_writes": False,
    }

    _add_check(checks, "known_objective", isinstance(objective, dict) and objective.get("id") == objective_id)
    _add_check(checks, "known_profile", isinstance(profile, dict) and profile.get("selected") == profile_name)
    _add_check(checks, "known_actor", actor in ALLOWED_ACTORS and packet.get("actor") == actor)
    _add_check(checks, "packet_schema_version_present", packet.get("packet_version") == PACKET_VERSION)
    _add_check(checks, "identity_fields_match_requested_inputs", _packet_identity(packet) == _requested_identity(objective_id, profile_name, actor))
    _add_check(checks, "deterministic_identity_fields_present", _packet_identity(packet) == _requested_identity(objective_id, profile_name, actor))
    _add_check(checks, "required_packet_sections_present", all(section in packet for section in PACKET_REQUIRED_SECTIONS))
    _add_check(checks, "execution_enabled_false", packet.get("execution_enabled") is False)
    _add_check(checks, "provider_calls_false", _provider_calls_disabled(packet.get("provider_calls")))
    _add_check(checks, "runtime_adapter_calls_false", packet.get("runtime_calls") is False and packet.get("adapter_calls") is False)
    _add_check(checks, "env_reads_false", packet.get("env_required") is False and _has_text(packet, "do_not_read_dotenv"))
    _add_check(checks, "env_var_printing_false", _has_text(packet, "do_not_print_env_vars") or _has_text(packet, "print env vars"))
    # ponytail: validation allows future artifact write descriptions, but not execution flags.
    _add_check(checks, "artifact_writes_false", _artifact_writes_disabled(packet.get("artifact_writes", False)))
    _add_check(checks, "no_real_execution_performed", packet.get("execution_enabled") is False and not any(external_behavior.values()))

    return {
        "valid": _checks_pass(checks),
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "objective": objective_id,
        "profile": profile_name,
        "actor": actor,
        "packet_identity": _packet_identity(packet),
        "checks": checks,
        "external_behavior": external_behavior,
    }


def _add_check(checks: list[dict[str, str]], name: str, passed: bool) -> None:
    checks.append({"name": name, "status": "pass" if passed else "fail"})


def _checks_pass(checks: list[dict[str, str]]) -> bool:
    return all(check["status"] == "pass" for check in checks)


def _requested_identity(objective_id: str, profile_name: str, actor: str) -> dict[str, object]:
    return {
        "packet_version": PACKET_VERSION,
        "objective": objective_id,
        "profile": profile_name,
        "actor": actor,
    }


def _packet_identity(packet: dict[str, object]) -> dict[str, object]:
    objective = packet.get("objective")
    profile = packet.get("profile")
    return {
        "packet_version": packet.get("packet_version"),
        "objective": objective.get("id") if isinstance(objective, dict) else None,
        "profile": profile.get("selected") if isinstance(profile, dict) else None,
        "actor": packet.get("actor"),
    }


def _artifact_writes_disabled(value: object) -> bool:
    if value is False:
        return True
    if isinstance(value, dict):
        return value.get("description_only") is True and value.get("executed") is False
    return False


def _provider_calls_disabled(value: object) -> bool:
    if value is False:
        return True
    if not isinstance(value, list):
        return False
    return all(isinstance(item, dict) and item.get("call_enabled") is False for item in value)


def _has_text(value: object, text: str) -> bool:
    if isinstance(value, str):
        return text in value
    if isinstance(value, dict):
        return any(_has_text(child, text) for child in value.values())
    if isinstance(value, list):
        return any(_has_text(child, text) for child in value)
    return False


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
