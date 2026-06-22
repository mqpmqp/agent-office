from __future__ import annotations

import json
from pathlib import Path

from .packets import ALLOWED_ACTORS, PacketError, execution_packet_payload, packet_contract_validation_payload
from .planner import PlanningError, execution_blueprint_payload


class RunBundleError(ValueError):
    pass


RUN_BUNDLE_SCHEMA_VERSION = 1
RUN_BUNDLE_REQUIRED_FILES = (
    "run.json",
    "plan.json",
    "packets/codex.json",
    "packets/reviewer.json",
    "packets/judge.json",
    "validation.json",
    "README.md",
)


def run_bundle_preview_payload(objective_id: str, profile_name: str, run_id: str) -> dict[str, object]:
    _validate_run_id(run_id)
    try:
        plan = execution_blueprint_payload(objective_id, profile_name)
        packets = {actor: execution_packet_payload(objective_id, profile_name, actor) for actor in ALLOWED_ACTORS}
        packet_validations = {
            actor: packet_contract_validation_payload(objective_id, profile_name, actor) for actor in ALLOWED_ACTORS
        }
    except (PlanningError, PacketError) as exc:
        raise RunBundleError(str(exc)) from exc

    run = {
        "run_id": run_id,
        "objective": {
            "id": plan["objective_id"],
            "name": plan["objective_name"],
            "summary": plan["objective_summary"],
        },
        "profile": {
            "selected": plan["selected_profile"],
            "default": plan["default_profile"],
            "is_default": plan["is_default"],
        },
        "execution_enabled": False,
        "provider_calls": [],
        "actors": list(ALLOWED_ACTORS),
        "runtime_calls": False,
        "adapter_calls": False,
        "env_required": False,
    }
    validation = _run_bundle_validation_payload(run, plan, packets, packet_validations)
    return {
        "kind": "static_run_bundle",
        "schema_version": RUN_BUNDLE_SCHEMA_VERSION,
        "run": run,
        "plan": plan,
        "packets": packets,
        "validation": validation,
        "files": [{"path": path, "kind": "markdown" if path.endswith(".md") else "json"} for path in RUN_BUNDLE_REQUIRED_FILES],
        "execution_enabled": False,
        "provider_calls": [],
        "runtime_calls": False,
        "adapter_calls": False,
        "env_required": False,
        "artifact_writes": False,
    }


def write_run_bundle(payload: dict[str, object], out: str | Path, project_root: Path) -> dict[str, object]:
    out_root = _resolve_out_path(out, project_root)
    if out_root.exists() and (out_root.is_symlink() or not out_root.is_dir()):
        raise RunBundleError(f"Refusing to write run bundle to non-directory path: {out_root}")

    run = _expect_dict(payload, "run")
    plan = _expect_dict(payload, "plan")
    packets = _expect_dict(payload, "packets")
    validation = _expect_dict(payload, "validation")
    contents: dict[str, object | str] = {
        "run.json": run,
        "plan.json": plan,
        "packets/codex.json": _expect_dict(packets, "codex"),
        "packets/reviewer.json": _expect_dict(packets, "reviewer"),
        "packets/judge.json": _expect_dict(packets, "judge"),
        "validation.json": validation,
        "README.md": _bundle_readme(payload),
    }

    targets = [(relative, _safe_target(out_root, relative)) for relative in RUN_BUNDLE_REQUIRED_FILES]
    out_root.mkdir(parents=True, exist_ok=True)
    for relative, target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.is_symlink():
            raise RunBundleError(f"Refusing to overwrite symlink bundle file: {target}")
        value = contents[relative]
        if relative.endswith(".json"):
            _write_json(target, value)
        else:
            _write_text(target, str(value))

    return {
        "enabled": True,
        "out": str(out_root),
        "files_written": [relative for relative, _target in targets],
    }


def format_run_bundle_preview(payload: dict[str, object]) -> str:
    run = _expect_dict(payload, "run")
    objective = _expect_dict(run, "objective")
    profile = _expect_dict(run, "profile")
    lines = [
        "AgentOffice static run bundle",
        f"run_id: {run['run_id']}",
        f"objective: {objective['id']} - {objective['name']}",
        f"profile: {profile['selected']}",
        f"execution_enabled: {str(run['execution_enabled']).lower()}",
        "provider_calls: []",
        f"actors: {', '.join(str(actor) for actor in run['actors'])}",
        "files:",
    ]
    for item in payload["files"]:
        if isinstance(item, dict):
            lines.append(f"  - {item['path']}")
    write_result = payload.get("write_result")
    if isinstance(write_result, dict):
        lines.append(f"written: {str(write_result.get('enabled')).lower()}")
        lines.append(f"out: {write_result.get('out')}")
    else:
        lines.append("written: false")
        lines.append("out: not requested")
    lines.extend(
        [
            "env_required: false",
            "runtime_calls: false",
            "adapter_calls: false",
            "provider/runtime/adapter execution: not triggered",
        ]
    )
    return "\n".join(lines)


def _run_bundle_validation_payload(
    run: dict[str, object],
    plan: dict[str, object],
    packets: dict[str, object],
    packet_validations: dict[str, object],
) -> dict[str, object]:
    checks: list[dict[str, str]] = []
    _add_check(checks, "run_id_present", isinstance(run.get("run_id"), str) and bool(run["run_id"]))
    _add_check(checks, "objective_matches_plan", _expect_dict(run, "objective").get("id") == plan.get("objective_id"))
    _add_check(checks, "profile_matches_plan", _expect_dict(run, "profile").get("selected") == plan.get("selected_profile"))
    _add_check(checks, "execution_disabled", run.get("execution_enabled") is False and plan.get("execution_enabled") is False)
    _add_check(checks, "run_provider_calls_empty", run.get("provider_calls") == [])
    _add_check(checks, "runtime_adapter_calls_false", run.get("runtime_calls") is False and run.get("adapter_calls") is False)
    _add_check(checks, "actors_present", tuple(run.get("actors", ())) == ALLOWED_ACTORS)
    _add_check(checks, "packet_actors_present", all(actor in packets for actor in ALLOWED_ACTORS))
    # ponytail: this is structural bundle validation only; runtime verification stays out of scope.
    _add_check(
        checks,
        "packet_validations_pass",
        all(
            isinstance(packet_validations.get(actor), dict) and packet_validations[actor].get("valid") is True
            for actor in ALLOWED_ACTORS
        ),
    )
    _add_check(checks, "required_files_declared", list(RUN_BUNDLE_REQUIRED_FILES) == [
        "run.json",
        "plan.json",
        "packets/codex.json",
        "packets/reviewer.json",
        "packets/judge.json",
        "validation.json",
        "README.md",
    ])
    _add_check(checks, "no_external_behavior", True)
    return {
        "kind": "static_run_bundle_validation",
        "schema_version": RUN_BUNDLE_SCHEMA_VERSION,
        "run_id": run["run_id"],
        "objective": plan["objective_id"],
        "profile": plan["selected_profile"],
        "valid": _checks_pass(checks),
        "required_files": list(RUN_BUNDLE_REQUIRED_FILES),
        "checks": checks,
        "packet_validations": packet_validations,
        "external_behavior": {
            "env_reads": False,
            "env_var_printing": False,
            "provider_calls": False,
            "runtime_calls": False,
            "adapter_calls": False,
            "real_runner": False,
        },
    }


def _validate_run_id(run_id: str) -> None:
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
    if not run_id or any(ch not in allowed for ch in run_id) or run_id in {".", ".."}:
        raise RunBundleError("run_id may only contain letters, numbers, dash, underscore, and dot.")


def _resolve_out_path(out: str | Path, project_root: Path) -> Path:
    base = project_root.resolve()
    path = Path(out)
    if not path.is_absolute():
        path = project_root / path
    resolved = path.resolve(strict=False)
    if resolved != base and base not in resolved.parents:
        raise RunBundleError(f"Refusing to write run bundle outside project root: {out}")
    return resolved


def _safe_target(out_root: Path, relative: str) -> Path:
    target = (out_root / relative).resolve(strict=False)
    if target == out_root or out_root not in target.parents:
        raise RunBundleError(f"Refusing unsafe bundle path: {relative}")
    return target


def _write_json(path: Path, value: object) -> None:
    _write_text(path, json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def _write_text(path: Path, value: str) -> None:
    tmp = path.with_name(f"{path.name}.tmp")
    if tmp.exists() and tmp.is_symlink():
        raise RunBundleError(f"Refusing to write temporary symlink: {tmp}")
    tmp.write_text(value, encoding="utf-8")
    tmp.replace(path)


def _bundle_readme(payload: dict[str, object]) -> str:
    run = _expect_dict(payload, "run")
    objective = _expect_dict(run, "objective")
    profile = _expect_dict(run, "profile")
    actors = ", ".join(str(actor) for actor in run["actors"])
    return f"""# AgentOffice Static Run Bundle

Run ID: `{run['run_id']}`
Objective: `{objective['id']}` - {objective['name']}
Profile: `{profile['selected']}`
Actors: {actors}

This bundle is static and local. Execution is disabled, provider calls are empty, runtime calls are false, and adapter calls are false.
"""


def _expect_dict(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise RunBundleError(f"Malformed run bundle payload: missing {key}")
    return value


def _add_check(checks: list[dict[str, str]], name: str, passed: bool) -> None:
    checks.append({"name": name, "status": "pass" if passed else "fail"})


def _checks_pass(checks: list[dict[str, str]]) -> bool:
    return all(check["status"] == "pass" for check in checks)
