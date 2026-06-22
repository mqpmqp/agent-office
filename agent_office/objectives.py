from __future__ import annotations

import json


class ObjectiveSpecError(ValueError):
    pass


OBJECTIVE_SPEC_REQUIRED_FIELDS = (
    "kind",
    "phase",
    "title",
    "status",
    "objective",
    "source_phases",
    "cli_contract",
    "json_contract",
    "tests",
    "validation",
    "safety",
)
OBJECTIVE_REGISTRY_VALIDATION_CHECKS = (
    "objective_ids_unique",
    "required_fields_present",
    "output_order_stable",
    "json_serializable",
    "static_safe_registry",
)
OBJECTIVE_STATIC_SAFETY_FLAGS = (
    "env_file_read",
    "env_vars_printed",
    "provider_calls",
    "runtime_execution",
    "adapter_execution",
    "artifact_writes",
)
P6_10_VALIDATION_COMMANDS = (
    "python3 -m compileall agent_office tests",
    "python3 -m unittest",
    "python3 -m unittest discover -s tests -p 'test_*.py'",
    "./scripts/verify.sh",
    "python3 -m agent_office profiles --name lowest-cost --plan",
    "python3 -m agent_office profiles --name lowest-cost --plan --json",
    "python3 -m agent_office profiles --name lowest-cost --plan --audit",
    "python3 -m agent_office profiles --name lowest-cost --plan --audit --json",
    "python3 -m agent_office doctor --profiles",
    "python3 -m agent_office doctor --profiles --json",
    "python3 -m agent_office.doctor --profiles",
    "./scripts/smoke-test.sh P6-PROFILES",
    "python3 -m agent_office run-staged P6-PROFILES --dry-run --reset",
    "python3 -m agent_office objectives --phase P6-10",
    "python3 -m agent_office objectives --phase P6-10 --json",
)
P6_16_VALIDATION_COMMANDS = (
    "python3 -m compileall agent_office tests",
    "python3 -m unittest",
    "python3 -m unittest discover -s tests -p 'test_*.py'",
    "./scripts/verify.sh",
    "python3 -m agent_office objectives --phase P6-10 --json",
    "python3 -m agent_office objectives --phase P6-16",
    "python3 -m agent_office objectives --phase P6-16 --json",
    "python3 -m agent_office objectives --show P6-16",
    "python3 -m agent_office objectives --show P6-16 --json",
    "python3 -m agent_office objectives --validate",
    "python3 -m agent_office objectives --validate --json",
    "python3 -m agent_office plan --objective P6-16 --profile lowest-cost",
    "python3 -m agent_office plan --objective P6-16 --profile lowest-cost --json",
    "python3 -m agent_office packet --objective P6-16 --profile lowest-cost --actor codex --json",
    "python3 -m agent_office packet --objective P6-16 --profile lowest-cost --actor reviewer --json",
    "python3 -m agent_office packet --objective P6-16 --profile lowest-cost --actor judge --json",
    "python3 -m agent_office packet --objective P6-16 --profile lowest-cost --actor codex --validate --json",
    "python3 -m agent_office packet --objective P6-16 --profile lowest-cost --actor reviewer --validate --json",
    "python3 -m agent_office packet --objective P6-16 --profile lowest-cost --actor judge --validate --json",
)


def default_objective_phase() -> str:
    return "P6-10"


def list_objective_phases() -> tuple[str, ...]:
    return ("P6-10", "P6-16")


def objective_registry_payloads() -> tuple[dict[str, object], ...]:
    return tuple(objective_spec_payload(phase) for phase in list_objective_phases())


def objective_listing_payload() -> dict[str, object]:
    objectives = []
    for phase in list_objective_phases():
        spec = objective_spec_payload(phase)
        objectives.append(
            {
                "phase": spec["phase"],
                "title": spec["title"],
                "status": spec["status"],
                "objective": spec["objective"],
            }
        )
    # ponytail: static local listing only; this intentionally does not discover files or read environment.
    return {
        "kind": "objective_listing",
        "default_phase": default_objective_phase(),
        "objectives": objectives,
    }


def objective_detail_payload(objective_id: str) -> dict[str, object]:
    if objective_id not in list_objective_phases():
        raise ObjectiveSpecError(f"Unknown objective: {objective_id}")
    return objective_spec_payload(objective_id)


def objective_registry_validation_payload() -> dict[str, object]:
    specs = list(objective_registry_payloads())
    checks: list[dict[str, str]] = []
    errors: list[str] = []

    def add_check(name: str, passed: bool, error: str) -> None:
        checks.append({"name": name, "status": "pass" if passed else "fail"})
        if not passed:
            errors.append(error)

    objective_ids = [str(spec.get("phase", "")) for spec in specs]
    add_check(
        "objective_ids_unique",
        len(objective_ids) == len(set(objective_ids)),
        "Objective ids must be unique.",
    )

    missing_fields = {
        objective_id: [field for field in OBJECTIVE_SPEC_REQUIRED_FIELDS if field not in spec]
        for objective_id, spec in zip(objective_ids, specs)
    }
    missing_fields = {objective_id: fields for objective_id, fields in missing_fields.items() if fields}
    add_check(
        "required_fields_present",
        not missing_fields,
        f"Objective specs are missing required fields: {missing_fields}",
    )

    expected_order = list(list_objective_phases())
    add_check(
        "output_order_stable",
        objective_ids == expected_order,
        "Objective registry output order must match list_objective_phases().",
    )

    json_serializable = True
    json_error = "Objective registry must be JSON serializable."
    try:
        json.dumps({"listing": objective_listing_payload(), "objectives": specs}, sort_keys=True)
    except (TypeError, ValueError) as exc:
        json_serializable = False
        json_error = f"Objective registry must be JSON serializable: {exc}"
    add_check("json_serializable", json_serializable, json_error)

    add_check(
        "static_safe_registry",
        all(_spec_declares_static_safety(spec) for spec in specs),
        "Objective registry must declare no env/provider/runtime/adapter behavior.",
    )

    status = "pass" if all(check["status"] == "pass" for check in checks) else "fail"
    return {
        "kind": "objective_registry_validation",
        "default_phase": default_objective_phase(),
        "objectives_checked": len(specs),
        "checks": checks,
        "errors": errors,
        "status": status,
    }


def objective_spec_payload(phase: str | None = None) -> dict[str, object]:
    selected_phase = phase or default_objective_phase()
    if selected_phase not in list_objective_phases():
        raise ObjectiveSpecError(f"Unknown objective phase: {selected_phase}")

    if selected_phase == "P6-10":
        return _objective_spec(
            phase="P6-10",
            title="Objective Spec CLI Contract",
            objective=(
                "Expose a static, provider-safe objective spec surface that documents the phase objective, "
                "CLI contract, JSON contract, tests, validation commands, and safety boundaries without "
                "executing providers or reading environment configuration."
            ),
            source_phases=["P6-06", "P6-07", "P6-08", "P6-09"],
            cli_contract=[
                "python3 -m agent_office objectives --phase P6-10",
                "python3 -m agent_office objectives --phase P6-10 --json",
            ],
            tests=[
                "tests/test_objectives_cli.py::ObjectiveSpecPayloadTests",
                "tests/test_objectives_cli.py::ObjectiveSpecCliTests",
            ],
            validation=list(P6_10_VALIDATION_COMMANDS),
        )
    return _objective_spec(
        phase="P6-16",
        title="Static Multi-Objective Registry",
        objective=(
            "Expose a static multi-objective registry that can serve P6-10 and P6-16 objective specs "
            "through objectives, plan, packet, packet validation, and packet fixture tests without file "
            "discovery, environment reads, provider calls, runtime calls, adapter calls, or artifact writes."
        ),
        source_phases=["P6-10", "P6-11", "P6-12", "P6-13", "P6-14", "P6-15"],
        cli_contract=[
            "python3 -m agent_office objectives --phase P6-16",
            "python3 -m agent_office objectives --phase P6-16 --json",
            "python3 -m agent_office objectives --show P6-16",
            "python3 -m agent_office objectives --show P6-16 --json",
        ],
        tests=[
            "tests/test_objectives_cli.py::ObjectiveSpecPayloadTests",
            "tests/test_objectives_cli.py::ObjectiveSpecCliTests",
            "tests/test_planner_cli.py::PlannerPayloadTests",
            "tests/test_packets.py::PacketContractValidationTests",
            "tests/test_packets_cli.py::PacketPayloadTests",
            "tests/test_packets_cli.py::PacketCliTests",
        ],
        validation=list(P6_16_VALIDATION_COMMANDS),
    )


def _objective_spec(
    *,
    phase: str,
    title: str,
    objective: str,
    source_phases: list[str],
    cli_contract: list[str],
    tests: list[str],
    validation: list[str],
) -> dict[str, object]:
    # ponytail: static local registry only; this intentionally avoids file discovery and config loading.
    return {
        "kind": "objective_spec",
        "phase": phase,
        "title": title,
        "status": "ready",
        "objective": objective,
        "source_phases": source_phases,
        "cli_contract": cli_contract,
        "json_contract": {
            "schema_version": 1,
            "required_fields": list(OBJECTIVE_SPEC_REQUIRED_FIELDS),
        },
        "tests": tests,
        "validation": validation,
        "safety": {
            "env_file_read": False,
            "env_vars_printed": False,
            "provider_calls": False,
            "runtime_execution": False,
            "adapter_execution": False,
            "artifact_writes": False,
        },
    }


def _spec_declares_static_safety(spec: dict[str, object]) -> bool:
    safety = spec.get("safety")
    if not isinstance(safety, dict):
        return False
    return all(safety.get(flag) is False for flag in OBJECTIVE_STATIC_SAFETY_FLAGS)
