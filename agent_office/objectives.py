from __future__ import annotations


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


def default_objective_phase() -> str:
    return "P6-10"


def list_objective_phases() -> tuple[str, ...]:
    return (default_objective_phase(),)


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


def objective_spec_payload(phase: str | None = None) -> dict[str, object]:
    selected_phase = phase or default_objective_phase()
    if selected_phase != default_objective_phase():
        raise ObjectiveSpecError(f"Unknown objective phase: {selected_phase}")

    # ponytail: static local spec only; future phases can add registry loading when more than one spec exists.
    return {
        "kind": "objective_spec",
        "phase": "P6-10",
        "title": "Objective Spec CLI Contract",
        "status": "ready",
        "objective": (
            "Expose a static, provider-safe objective spec surface that documents the phase objective, "
            "CLI contract, JSON contract, tests, validation commands, and safety boundaries without "
            "executing providers or reading environment configuration."
        ),
        "source_phases": ["P6-06", "P6-07", "P6-08", "P6-09"],
        "cli_contract": [
            "python3 -m agent_office objectives --phase P6-10",
            "python3 -m agent_office objectives --phase P6-10 --json",
        ],
        "json_contract": {
            "schema_version": 1,
            "required_fields": list(OBJECTIVE_SPEC_REQUIRED_FIELDS),
        },
        "tests": [
            "tests/test_objectives_cli.py::ObjectiveSpecPayloadTests",
            "tests/test_objectives_cli.py::ObjectiveSpecCliTests",
        ],
        "validation": list(P6_10_VALIDATION_COMMANDS),
        "safety": {
            "env_file_read": False,
            "env_vars_printed": False,
            "provider_calls": False,
            "runtime_execution": False,
            "adapter_execution": False,
            "artifact_writes": False,
        },
    }
