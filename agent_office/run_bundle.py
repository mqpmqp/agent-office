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


def inspect_run_bundle_payload(path: str | Path, project_root: Path) -> dict[str, object]:
    bundle = _load_existing_bundle(path, project_root)
    run = _validate_loaded_bundle(bundle)
    objective = _expect_dict(run, "objective")
    profile = _expect_dict(run, "profile")
    return {
        "kind": "static_run_bundle_inspection",
        "schema_version": RUN_BUNDLE_SCHEMA_VERSION,
        "path": str(bundle["root"]),
        "run_id": run["run_id"],
        "objective": objective,
        "profile": profile,
        "execution_enabled": False,
        "provider_calls": [],
        "actors": list(ALLOWED_ACTORS),
        "files": _bundle_file_statuses(bundle),
        "external_behavior": _read_only_external_behavior(),
    }


def validate_run_bundle_payload(path: str | Path, project_root: Path) -> dict[str, object]:
    bundle = _load_existing_bundle(path, project_root)
    run = _validate_loaded_bundle(bundle)
    objective = _expect_dict(run, "objective")
    profile = _expect_dict(run, "profile")
    checks: list[dict[str, str]] = []
    _add_check(checks, "required_files_present", True)
    _add_check(checks, "json_files_parse", True)
    _add_check(checks, "run_id_present", isinstance(run.get("run_id"), str) and bool(run["run_id"]))
    _add_check(checks, "objective_present", isinstance(objective.get("id"), str) and bool(objective["id"]))
    _add_check(checks, "profile_present", isinstance(profile.get("selected"), str) and bool(profile["selected"]))
    _add_check(checks, "execution_enabled_false", run.get("execution_enabled") is False)
    _add_check(checks, "provider_calls_empty", run.get("provider_calls") == [])
    _add_check(checks, "actors_present", tuple(run.get("actors", ())) == ALLOWED_ACTORS)
    _add_check(checks, "packet_actors_present", _packet_actors_present(bundle))
    _add_check(checks, "validation_file_present", isinstance(bundle["json"]["validation.json"], dict))
    _add_check(checks, "readme_present", isinstance(bundle["text"]["README.md"], str) and bool(bundle["text"]["README.md"].strip()))
    _add_check(checks, "no_external_behavior", True)
    return {
        "kind": "static_run_bundle_validation_result",
        "schema_version": RUN_BUNDLE_SCHEMA_VERSION,
        "path": str(bundle["root"]),
        "run_id": run["run_id"],
        "objective": objective["id"],
        "profile": profile["selected"],
        "valid": _checks_pass(checks),
        "required_files": list(RUN_BUNDLE_REQUIRED_FILES),
        "files": _bundle_file_statuses(bundle),
        "checks": checks,
        "external_behavior": _read_only_external_behavior(),
    }


def list_run_bundles_payload(root: str | Path, project_root: Path) -> dict[str, object]:
    catalog_root = _resolve_bundle_path(root, project_root)
    if catalog_root.is_symlink() or not catalog_root.is_dir():
        raise RunBundleError(f"Run bundle root is not a directory: {root}")
    bundles = [status_run_bundle_payload(child, project_root) for child in sorted(catalog_root.iterdir()) if child.is_dir()]
    return {
        "kind": "static_run_bundle_catalog",
        "schema_version": RUN_BUNDLE_SCHEMA_VERSION,
        "root": str(catalog_root),
        "count": len(bundles),
        "bundles": bundles,
        "external_behavior": _read_only_external_behavior(),
    }


def status_run_bundle_payload(path: str | Path, project_root: Path) -> dict[str, object]:
    root = _resolve_bundle_path(path, project_root)
    errors: list[str] = []
    run: dict[str, object] = {}
    files: list[dict[str, object]] = []
    try:
        bundle = _load_existing_bundle(path, project_root)
        try:
            run = _validate_loaded_bundle(bundle)
        except RunBundleError as exc:
            errors.append(str(exc))
            json_files = _expect_dict(bundle, "json")
            maybe_run = json_files.get("run.json")
            if isinstance(maybe_run, dict):
                run = maybe_run
        files = _bundle_file_statuses(bundle)
    except RunBundleError as exc:
        errors.append(str(exc))
    objective = run.get("objective") if isinstance(run.get("objective"), dict) else None
    profile = run.get("profile") if isinstance(run.get("profile"), dict) else None
    provider_calls = run.get("provider_calls") if isinstance(run.get("provider_calls"), list) else []
    actors = run.get("actors") if isinstance(run.get("actors"), list) else []
    return {
        "kind": "static_run_bundle_status",
        "schema_version": RUN_BUNDLE_SCHEMA_VERSION,
        "path": str(root),
        "run_id": run.get("run_id") if isinstance(run.get("run_id"), str) else None,
        "objective": objective,
        "profile": profile,
        "actors": actors,
        "execution_enabled": run.get("execution_enabled"),
        "provider_calls": provider_calls,
        "required_files": list(RUN_BUNDLE_REQUIRED_FILES),
        "files": files,
        "status": "invalid" if errors else "ready",
        "errors": errors,
        "external_behavior": _read_only_external_behavior(),
    }


def format_run_bundle_catalog(payload: dict[str, object]) -> str:
    lines = [
        "AgentOffice static run bundle catalog",
        f"root: {payload['root']}",
        f"count: {payload['count']}",
        "bundles:",
    ]
    for item in payload["bundles"]:
        if isinstance(item, dict):
            lines.append(f"  - {Path(str(item['path'])).name}: {item['status']}")
    lines.append("provider/runtime/adapter execution: not triggered")
    return "\n".join(lines)


def format_run_bundle_inspection(payload: dict[str, object]) -> str:
    lines = [
        "AgentOffice static run bundle inspection",
        f"path: {payload['path']}",
        f"run_id: {payload['run_id']}",
        f"objective: {_format_identity(payload['objective'])}",
        f"profile: {_format_identity(payload['profile'])}",
        f"execution_enabled: {str(payload['execution_enabled']).lower()}",
        "provider_calls: []",
        f"actors: {', '.join(str(actor) for actor in payload['actors'])}",
        "files:",
    ]
    for item in payload["files"]:
        if isinstance(item, dict):
            lines.append(f"  - {item['path']}: {item['status']}")
    lines.append("provider/runtime/adapter execution: not triggered")
    return "\n".join(lines)


def format_run_bundle_validation(payload: dict[str, object]) -> str:
    lines = [
        "AgentOffice static run bundle validation",
        f"path: {payload['path']}",
        f"run_id: {payload['run_id']}",
        f"objective: {payload['objective']}",
        f"profile: {payload['profile']}",
        f"valid: {str(payload['valid']).lower()}",
        "checks:",
    ]
    for check in payload["checks"]:
        if isinstance(check, dict):
            lines.append(f"  - {check['name']}: {check['status']}")
    lines.append("provider/runtime/adapter execution: not triggered")
    return "\n".join(lines)


def format_run_bundle_status(payload: dict[str, object]) -> str:
    lines = [
        "AgentOffice static run bundle status",
        f"path: {payload['path']}",
        f"run_id: {payload['run_id']}",
        f"objective: {_format_identity(payload['objective'])}",
        f"profile: {_format_identity(payload['profile'])}",
        f"actors: {', '.join(str(actor) for actor in payload['actors'])}",
        f"execution_enabled: {str(payload['execution_enabled']).lower()}",
        f"provider_calls: {payload['provider_calls']}",
        "required_files:",
    ]
    for relative in payload["required_files"]:
        lines.append(f"  - {relative}")
    lines.append(f"status: {payload['status']}")
    errors = payload.get("errors")
    if isinstance(errors, list) and errors:
        lines.append("errors:")
        for error in errors:
            lines.append(f"  - {error}")
    else:
        lines.append("errors: []")
    lines.append("provider/runtime/adapter execution: not triggered")
    return "\n".join(lines)


def _load_existing_bundle(path: str | Path, project_root: Path) -> dict[str, object]:
    root = _resolve_bundle_path(path, project_root)
    if root.is_symlink() or not root.is_dir():
        raise RunBundleError(f"Run bundle path is not a directory: {path}")
    json_files: dict[str, object] = {}
    text_files: dict[str, str] = {}
    for relative in RUN_BUNDLE_REQUIRED_FILES:
        target = _safe_existing_bundle_file(root, relative)
        if not target.exists():
            raise RunBundleError(f"Missing run bundle file: {relative}")
        if target.is_symlink() or not target.is_file():
            raise RunBundleError(f"Invalid run bundle file: {relative}")
        if relative.endswith(".json"):
            json_files[relative] = _read_json_file(target, relative)
        else:
            text_files[relative] = target.read_text(encoding="utf-8")
    return {"root": root, "json": json_files, "text": text_files}


def _validate_loaded_bundle(bundle: dict[str, object]) -> dict[str, object]:
    json_files = _expect_dict(bundle, "json")
    run = _expect_dict(json_files, "run.json")
    if not isinstance(run.get("run_id"), str) or not run["run_id"]:
        raise RunBundleError("run.json missing run_id")
    _expect_dict(run, "objective")
    _expect_dict(run, "profile")
    if run.get("execution_enabled") is not False:
        raise RunBundleError("run.json execution_enabled must be false")
    if run.get("provider_calls") != []:
        raise RunBundleError("run.json provider_calls must be empty")
    if tuple(run.get("actors", ())) != ALLOWED_ACTORS:
        raise RunBundleError("run.json actors must be codex, reviewer, judge")
    for actor in ALLOWED_ACTORS:
        packet = _expect_dict(json_files, f"packets/{actor}.json")
        if packet.get("actor") != actor:
            raise RunBundleError(f"Packet actor mismatch: packets/{actor}.json")
        if packet.get("execution_enabled") is not False:
            raise RunBundleError(f"Packet execution_enabled must be false: packets/{actor}.json")
    return run


def _resolve_bundle_path(path: str | Path, project_root: Path) -> Path:
    base = project_root.resolve()
    requested = Path(path)
    if not requested.is_absolute():
        requested = project_root / requested
    if requested.is_symlink():
        raise RunBundleError(f"Refusing symlink run bundle path: {path}")
    resolved = requested.resolve(strict=False)
    if resolved != base and base not in resolved.parents:
        raise RunBundleError(f"Refusing to read run bundle outside project root: {path}")
    return resolved


def _safe_existing_bundle_file(root: Path, relative: str) -> Path:
    target = root / relative
    resolved = target.resolve(strict=False)
    if root not in resolved.parents:
        raise RunBundleError(f"Refusing unsafe bundle path: {relative}")
    return target


def _read_json_file(path: Path, relative: str) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RunBundleError(f"Invalid JSON in run bundle file: {relative}") from exc


def _bundle_file_statuses(bundle: dict[str, object]) -> list[dict[str, object]]:
    json_files = _expect_dict(bundle, "json")
    text_files = _expect_dict(bundle, "text")
    statuses: list[dict[str, object]] = []
    for relative in RUN_BUNDLE_REQUIRED_FILES:
        statuses.append(
            {
                "path": relative,
                "status": "present",
                "kind": "markdown" if relative.endswith(".md") else "json",
                "parsed": relative in json_files or relative in text_files,
            }
        )
    return statuses


def _packet_actors_present(bundle: dict[str, object]) -> bool:
    json_files = _expect_dict(bundle, "json")
    return all(_expect_dict(json_files, f"packets/{actor}.json").get("actor") == actor for actor in ALLOWED_ACTORS)


def _read_only_external_behavior() -> dict[str, bool]:
    return {
        "env_reads": False,
        "env_var_printing": False,
        "provider_calls": False,
        "runtime_calls": False,
        "adapter_calls": False,
        "artifact_writes": False,
        "real_runner": False,
    }


def _format_identity(value: object) -> str:
    if isinstance(value, dict):
        return str(value.get("id") or value.get("selected") or value)
    return str(value)


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
