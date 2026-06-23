from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .packets import ALLOWED_ACTORS, PacketError, execution_packet_payload, packet_contract_validation_payload
from .planner import PlanningError, execution_blueprint_payload


class RunBundleError(ValueError):
    pass


RUN_BUNDLE_SCHEMA_VERSION = 1
HANDOFF_SCHEMA_VERSION = 1
REVIEW_PACKET_SCHEMA_VERSION = 1
RUN_BUNDLE_REQUIRED_FILES = (
    "run.json",
    "plan.json",
    "packets/codex.json",
    "packets/reviewer.json",
    "packets/judge.json",
    "validation.json",
    "README.md",
)
RUN_BUNDLE_RESULTS_DIR = "results"
RUN_BUNDLE_OBJECTIVE_ALIASES = {
    "P6-PROFILES": "P6-17",
}


def run_bundle_preview_payload(objective_id: str, profile_name: str, run_id: str, *, allow_alias: bool = False) -> dict[str, object]:
    _validate_run_id(run_id)
    resolved_objective_id = _resolve_preview_objective(objective_id) if allow_alias else objective_id
    try:
        plan = execution_blueprint_payload(resolved_objective_id, profile_name)
        packets = {actor: execution_packet_payload(resolved_objective_id, profile_name, actor) for actor in ALLOWED_ACTORS}
        packet_validations = {
            actor: packet_contract_validation_payload(resolved_objective_id, profile_name, actor) for actor in ALLOWED_ACTORS
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


def _resolve_preview_objective(objective_id: str) -> str:
    # ponytail: P6-PROFILES is a smoke/staged id; only explicit preview maps it to static P6-17.
    return RUN_BUNDLE_OBJECTIVE_ALIASES.get(objective_id, objective_id)


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
    _mkdir(out_root, "run bundle output directory")
    for relative, target in targets:
        _mkdir(target.parent, f"run bundle parent directory: {relative}")
        if _is_symlink(target, relative):
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
    results: dict[str, dict[str, object]] = {}
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
        try:
            results = _load_actor_results(root)
        except RunBundleError as exc:
            errors.append(str(exc))
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
        "result_presence": _result_presence(results),
        "status": "invalid" if errors else "ready",
        "errors": errors,
        "external_behavior": _read_only_external_behavior(),
    }


def intake_actor_result_payload(path: str | Path, actor: str, artifact: str | Path, project_root: Path) -> dict[str, object]:
    _validate_actor(actor)
    bundle = _load_existing_bundle(path, project_root)
    run = _validate_loaded_bundle(bundle)
    root = _expect_path(bundle, "root")
    artifact_path = _resolve_artifact_path(artifact, project_root)
    result = _actor_result_payload(actor, artifact_path, project_root)
    target = _safe_target(root, f"{RUN_BUNDLE_RESULTS_DIR}/{actor}.json")
    if _is_symlink(target, f"{RUN_BUNDLE_RESULTS_DIR}/{actor}.json"):
        raise RunBundleError(f"Refusing to overwrite symlink actor result: {target}")
    _mkdir(target.parent, f"actor result parent directory: {actor}")
    _write_json(target, result)
    results = _load_actor_results(root)
    return {
        "kind": "static_actor_result_intake",
        "schema_version": RUN_BUNDLE_SCHEMA_VERSION,
        "path": str(root),
        "run_id": run["run_id"],
        "actor": actor,
        "result_file": f"{RUN_BUNDLE_RESULTS_DIR}/{actor}.json",
        "result": result,
        "result_presence": _result_presence(results),
        "execution_enabled": False,
        "provider_calls": [],
        "external_behavior": _local_write_external_behavior(),
    }


def results_run_bundle_payload(path: str | Path, project_root: Path) -> dict[str, object]:
    bundle = _load_existing_bundle(path, project_root)
    run = _validate_loaded_bundle(bundle)
    root = _expect_path(bundle, "root")
    results = _load_actor_results(root)
    return {
        "kind": "static_actor_results",
        "schema_version": RUN_BUNDLE_SCHEMA_VERSION,
        "path": str(root),
        "run_id": run["run_id"],
        "results": [results[actor] for actor in ALLOWED_ACTORS if actor in results],
        "result_presence": _result_presence(results),
        "execution_enabled": False,
        "provider_calls": [],
        "external_behavior": _read_only_external_behavior(),
    }



def handoff_run_bundle_payload(path: str | Path, project_root: Path) -> dict[str, object]:
    bundle = _load_existing_bundle(path, project_root)
    run = _validate_loaded_bundle(bundle)
    root = _expect_path(bundle, "root")
    json_files = _expect_dict(bundle, "json")
    plan = _expect_dict(json_files, "plan.json")
    validation = _expect_dict(json_files, "validation.json")
    objective = _expect_dict(run, "objective")
    profile = _expect_dict(run, "profile")
    results = _load_actor_results(root)
    result_presence = _result_presence(results)
    expected_files = validation.get("required_files")
    if not _string_list(expected_files):
        expected_files = list(RUN_BUNDLE_REQUIRED_FILES)

    actor_packet_identities: dict[str, object] = {}
    actor_readiness: dict[str, object] = {}
    for actor in ALLOWED_ACTORS:
        packet = _expect_dict(json_files, f"packets/{actor}.json")
        identity = _actor_packet_identity(packet)
        packet_ready = _packet_ready(actor, identity)
        readiness: dict[str, object] = {
            "actor": actor,
            "packet_present": True,
            "packet_identity": identity,
            "result_present": result_presence[actor],
            "ready_for_reviewer": packet_ready,
            "ready_for_judge": packet_ready and result_presence[actor],
        }
        result = results.get(actor)
        if result is not None:
            artifact = result.get("artifact")
            if isinstance(artifact, dict):
                readiness["artifact"] = {
                    "path": artifact.get("path"),
                    "size_bytes": artifact.get("size_bytes"),
                    "sha256": artifact.get("sha256"),
                }
        actor_packet_identities[actor] = identity
        actor_readiness[actor] = readiness

    execution_boundary = {
        "execution_enabled": False,
        "provider_calls": [],
        "runtime_calls": False,
        "adapter_calls": False,
        "real_runner": False,
        "external_behavior_triggered": False,
        "artifact_content_executed": False,
    }
    safety_flags = {
        "no_env_read_expected": True,
        "no_env_vars_printed_expected": True,
        "no_provider_runtime_adapter_expected": True,
        "no_real_runner_expected": True,
        "read_only": True,
    }
    return {
        "kind": "static_run_bundle_handoff",
        "handoff_schema_version": HANDOFF_SCHEMA_VERSION,
        "schema_version": RUN_BUNDLE_SCHEMA_VERSION,
        "path": str(root),
        "run_id": run["run_id"],
        "objective": objective,
        "profile": profile,
        "objective_summary": objective.get("summary"),
        "profile_summary": {
            "selected": profile.get("selected"),
            "default": profile.get("default"),
            "is_default": profile.get("is_default"),
        },
        "required_files": list(RUN_BUNDLE_REQUIRED_FILES),
        "expected_files": list(expected_files),
        "files": _bundle_file_statuses(bundle),
        "actor_packet_identities": actor_packet_identities,
        "actor_readiness": actor_readiness,
        "result_presence": result_presence,
        "validation_commands": _handoff_validation_commands(plan, path),
        "execution_enabled": False,
        "provider_calls": [],
        "execution_boundary": execution_boundary,
        "safety_flags": safety_flags,
        "external_behavior_triggered": False,
        "artifact_content_executed": False,
        "read_only": True,
        "non_goals": [
            "Do not execute actors from this handoff.",
            "Do not call providers, runtimes, adapters, or a real runner.",
            "Do not read .env or print environment variable values.",
            "Do not modify the run bundle or actor result artifacts.",
        ],
        "reviewer_guidance": [
            "Confirm required files and actor result presence before review.",
            "Use validation_commands as the local read-only review checklist.",
            "Report missing or invalid evidence without modifying the bundle.",
        ],
        "judge_guidance": [
            "Decide only from static bundle evidence and reviewer findings.",
            "Reject or request changes if required files, actor readiness, or safety flags are incomplete.",
        ],
        "external_behavior": _read_only_external_behavior(),
    }



def review_run_bundle_payload(path: str | Path, project_root: Path) -> dict[str, object]:
    handoff = handoff_run_bundle_payload(path, project_root)
    validation = validate_run_bundle_payload(path, project_root)
    status = status_run_bundle_payload(path, project_root)
    result_presence = _expect_dict(handoff, "result_presence")
    actor_readiness = _expect_dict(handoff, "actor_readiness")

    actor_evidence: list[dict[str, object]] = []
    for actor in ALLOWED_ACTORS:
        readiness = actor_readiness.get(actor)
        if not isinstance(readiness, dict):
            readiness = {}
        artifact = readiness.get("artifact") if isinstance(readiness.get("artifact"), dict) else None
        actor_evidence.append(
            {
                "actor": actor,
                "packet_file": f"packets/{actor}.json",
                "packet_ready": readiness.get("ready_for_reviewer") is True,
                "result_present": result_presence.get(actor) is True,
                "result_file": f"{RUN_BUNDLE_RESULTS_DIR}/{actor}.json",
                "artifact": artifact,
                "review_focus": _actor_review_focus(actor),
            }
        )

    bundle_valid = validation.get("valid") is True and status.get("status") == "ready"
    packets_ready = all(item["packet_ready"] is True for item in actor_evidence)
    actor_results_complete = all(item["result_present"] is True for item in actor_evidence)
    return {
        "kind": "static_run_bundle_review_packet",
        "review_schema_version": REVIEW_PACKET_SCHEMA_VERSION,
        "schema_version": RUN_BUNDLE_SCHEMA_VERSION,
        "path": handoff["path"],
        "run_id": handoff["run_id"],
        "objective": handoff["objective"],
        "profile": handoff["profile"],
        "review_goal": "Give Claude Code one deterministic, read-only packet for reviewing the static AgentOffice run bundle lifecycle.",
        "readiness": {
            "bundle_valid": bundle_valid,
            "status": status.get("status"),
            "packets_ready_for_reviewer": packets_ready,
            "actor_results_complete": actor_results_complete,
            "claude_review_ready": bundle_valid and packets_ready,
            "judge_ready": bundle_valid and packets_ready and actor_results_complete,
        },
        "required_review_files": _review_required_files(handoff.get("files")),
        "actor_evidence": actor_evidence,
        "validation": {
            "valid": validation.get("valid") is True,
            "checks": validation.get("checks") if isinstance(validation.get("checks"), list) else [],
        },
        "status": {
            "state": status.get("status"),
            "errors": status.get("errors") if isinstance(status.get("errors"), list) else [],
        },
        "reviewer_commands": _review_validation_commands(handoff.get("validation_commands"), path),
        "reviewer_contract": _reviewer_contract(),
        "safety_flags": handoff["safety_flags"],
        "execution_boundary": handoff["execution_boundary"],
        "external_behavior": _read_only_external_behavior(),
        "read_only": True,
        "execution_enabled": False,
        "provider_calls": [],
        "known_limitations": [
            "This packet summarizes static bundle metadata only; it does not execute actors or artifact content.",
            "Actor result artifacts are represented by intake metadata; source artifact bytes are not reread during review.",
            "judge_ready requires all actor result metadata to be present; claude_review_ready only requires a valid static bundle and reviewer-ready packets.",
        ],
    }


def format_run_bundle_review(payload: dict[str, object]) -> str:
    lines = [
        "AgentOffice static run bundle review packet",
        f"schema_version: {payload['schema_version']}",
        f"review_schema_version: {payload['review_schema_version']}",
        f"path: {payload['path']}",
        f"run_id: {payload['run_id']}",
        f"objective: {_format_handoff_objective(payload.get('objective'))}",
        f"profile: {_format_handoff_profile(payload.get('profile'))}",
        f"review_goal: {payload['review_goal']}",
        "readiness:",
    ]
    readiness = payload.get("readiness")
    if isinstance(readiness, dict):
        for key in (
            "bundle_valid",
            "status",
            "packets_ready_for_reviewer",
            "actor_results_complete",
            "claude_review_ready",
            "judge_ready",
        ):
            lines.append(f"  {key}: {_format_scalar(readiness.get(key))}")

    lines.append("required_review_files:")
    files = payload.get("required_review_files")
    if isinstance(files, list):
        for item in files:
            if isinstance(item, dict):
                lines.append(
                    f"  - {item.get('path')}: {item.get('status')}; "
                    f"kind={item.get('kind')}; parsed={_format_scalar(item.get('parsed'))}; "
                    f"purpose={item.get('purpose')}"
                )

    lines.append("actor_evidence:")
    evidence = payload.get("actor_evidence")
    if isinstance(evidence, list):
        for item in evidence:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"  - {item.get('actor')}: packet_file={item.get('packet_file')}; "
                f"packet_ready={_format_scalar(item.get('packet_ready'))}; "
                f"result_present={_format_scalar(item.get('result_present'))}; "
                f"result_file={item.get('result_file')}"
            )
            artifact = item.get("artifact")
            if isinstance(artifact, dict):
                lines.append(
                    f"    artifact: path={_format_scalar(artifact.get('path'))}; "
                    f"size_bytes={_format_scalar(artifact.get('size_bytes'))}; "
                    f"sha256={_format_scalar(artifact.get('sha256'))}"
                )
            focus = item.get("review_focus")
            if isinstance(focus, list):
                for value in focus:
                    lines.append(f"    focus: {value}")

    validation = payload.get("validation")
    lines.append("validation:")
    if isinstance(validation, dict):
        lines.append(f"  valid: {_format_scalar(validation.get('valid'))}")
        checks = validation.get("checks")
        if isinstance(checks, list):
            for check in checks:
                if isinstance(check, dict):
                    lines.append(f"  - {check.get('name')}: {check.get('status')}")

    status = payload.get("status")
    lines.append("status:")
    if isinstance(status, dict):
        lines.append(f"  state: {_format_scalar(status.get('state'))}")
        errors = status.get("errors")
        if isinstance(errors, list) and errors:
            for error in errors:
                lines.append(f"  error: {error}")
        else:
            lines.append("  errors: []")

    lines.append("reviewer_commands:")
    commands = payload.get("reviewer_commands")
    if isinstance(commands, list):
        for command in commands:
            lines.append(f"  - {command}")

    contract = payload.get("reviewer_contract")
    if isinstance(contract, dict):
        lines.append("reviewer_contract:")
        for section in ("must_review", "must_preserve", "risk_focus", "non_goals"):
            lines.append(f"  {section}:")
            values = contract.get(section)
            if isinstance(values, list):
                for value in values:
                    lines.append(f"    - {value}")

    lines.append("safety_flags:")
    safety_flags = payload.get("safety_flags")
    if isinstance(safety_flags, dict):
        for key in (
            "no_env_read_expected",
            "no_env_vars_printed_expected",
            "no_provider_runtime_adapter_expected",
            "no_real_runner_expected",
            "read_only",
        ):
            lines.append(f"  {key}: {_format_scalar(safety_flags.get(key))}")

    lines.append("execution_boundary:")
    boundary = payload.get("execution_boundary")
    if isinstance(boundary, dict):
        for key in (
            "execution_enabled",
            "provider_calls",
            "runtime_calls",
            "adapter_calls",
            "real_runner",
            "external_behavior_triggered",
            "artifact_content_executed",
        ):
            lines.append(f"  {key}: {_format_scalar(boundary.get(key))}")

    lines.append("known_limitations:")
    limitations = payload.get("known_limitations")
    if isinstance(limitations, list):
        for value in limitations:
            lines.append(f"  - {value}")

    lines.extend(
        [
            "read_only: true",
            "execution_enabled: false",
            "provider_calls: []",
            "provider/runtime/adapter execution: not triggered",
        ]
    )
    return "\n".join(lines)


def _review_required_files(files: object) -> list[dict[str, object]]:
    status_by_path = {item.get("path"): item for item in files if isinstance(item, dict)} if isinstance(files, list) else {}
    purposes = {
        "run.json": "run identity, actor list, and static safety flags",
        "plan.json": "objective/profile plan and validation command source",
        "packets/codex.json": "Codex implementation packet evidence",
        "packets/reviewer.json": "Reviewer packet evidence",
        "packets/judge.json": "Judge packet evidence",
        "validation.json": "structural bundle validation contract",
        "README.md": "human bundle summary",
    }
    review_files: list[dict[str, object]] = []
    for relative in RUN_BUNDLE_REQUIRED_FILES:
        item = status_by_path.get(relative)
        review_files.append(
            {
                "path": relative,
                "status": item.get("status") if isinstance(item, dict) else "unknown",
                "kind": item.get("kind") if isinstance(item, dict) else ("markdown" if relative.endswith(".md") else "json"),
                "parsed": item.get("parsed") if isinstance(item, dict) else False,
                "purpose": purposes[relative],
            }
        )
    return review_files


def _review_validation_commands(commands: object, path: str | Path) -> list[str]:
    result: list[str] = []
    if isinstance(commands, list):
        for command in commands:
            if isinstance(command, str) and command not in result:
                result.append(command)
    path_text = str(path)
    for command in (
        f"python3 -m agent_office run-bundle inspect --path {path_text} --json",
        f"python3 -m agent_office run-bundle validate --path {path_text} --json",
        f"python3 -m agent_office run-bundle status --path {path_text} --json",
        f"python3 -m agent_office run-bundle results --path {path_text} --json",
        f"python3 -m agent_office run-bundle handoff --path {path_text} --json",
        f"python3 -m agent_office run-bundle review --path {path_text} --json",
    ):
        if command not in result:
            result.append(command)
    return result


def _actor_review_focus(actor: str) -> list[str]:
    focus = {
        "codex": [
            "implementation evidence matches the objective and does not exceed the static packet",
            "tests and verification commands cover changed behavior",
        ],
        "reviewer": [
            "review findings are evidence-backed and distinguish blockers from limitations",
            "safety boundaries remain explicit in the handoff and review packet",
        ],
        "judge": [
            "final decision uses static bundle evidence only",
            "missing actor results prevent judge readiness even when Claude review can proceed",
        ],
    }
    return focus[actor]


def _reviewer_contract() -> dict[str, list[str]]:
    return {
        "must_review": [
            "run identity, objective, and profile are consistent across run.json, plan.json, packets, and validation.json.",
            "actor packets are present, static, and reviewer-ready before judging result evidence.",
            "actor result metadata, when present, records artifact path, size, and sha256 without executing content.",
            "validation and smoke commands are reproducible from this packet.",
        ],
        "must_preserve": [
            "No .env reads or environment variable value printing.",
            "No provider, runtime, adapter, or real runner external behavior.",
            "No artifact content execution from review, handoff, status, validate, inspect, list, or results actions.",
            "Expected user errors exit without traceback.",
        ],
        "risk_focus": [
            "Path traversal, symlink, missing file, bad JSON, and non-UTF-8 surfaces remain uniform.",
            "JSON field order and text headings remain deterministic for reviewer automation.",
            "judge_ready stays stricter than claude_review_ready when actor results are missing.",
        ],
        "non_goals": [
            "Do not execute actors from the review packet.",
            "Do not call providers or real adapters.",
            "Do not mutate the bundle while reviewing it.",
        ],
    }


def format_run_bundle_handoff(payload: dict[str, object]) -> str:
    lines = [
        "AgentOffice static run bundle handoff",
        f"schema_version: {payload['schema_version']}",
        f"handoff_schema_version: {payload['handoff_schema_version']}",
        f"path: {payload['path']}",
        f"run_id: {payload['run_id']}",
        f"objective: {_format_handoff_objective(payload.get('objective'))}",
        f"profile: {_format_handoff_profile(payload.get('profile'))}",
        f"objective_summary: {payload.get('objective_summary')}",
        "required_files:",
    ]

    for relative in payload.get("required_files", []):
        lines.append(f"  - {relative}")
    lines.append("expected_files:")
    for relative in payload.get("expected_files", []):
        lines.append(f"  - {relative}")

    lines.append("file_summary:")
    files = payload.get("files")
    if isinstance(files, list):
        for item in files:
            if isinstance(item, dict):
                lines.append(
                    f"  - {item.get('path')}: {item.get('status')}; "
                    f"kind={item.get('kind')}; parsed={_format_scalar(item.get('parsed'))}"
                )

    lines.append("actor_packet_identities:")
    identities = payload.get("actor_packet_identities")
    if isinstance(identities, dict):
        for actor in ALLOWED_ACTORS:
            item = identities.get(actor)
            if isinstance(item, dict):
                lines.append(
                    f"  - {actor}: packet_version={_format_scalar(item.get('packet_version'))}; "
                    f"objective={_format_scalar(item.get('objective'))}; "
                    f"profile={_format_scalar(item.get('profile'))}; "
                    f"execution_enabled={_format_scalar(item.get('execution_enabled'))}; "
                    f"env_required={_format_scalar(item.get('env_required'))}; "
                    f"runtime_calls={_format_scalar(item.get('runtime_calls'))}; "
                    f"adapter_calls={_format_scalar(item.get('adapter_calls'))}"
                )

    lines.append("actor_readiness:")
    readiness = payload.get("actor_readiness")
    if isinstance(readiness, dict):
        for actor in ALLOWED_ACTORS:
            item = readiness.get(actor)
            if isinstance(item, dict):
                lines.append(
                    f"  - {actor}: packet_present={_format_scalar(item.get('packet_present'))}; "
                    f"result_present={_format_scalar(item.get('result_present'))}; "
                    f"ready_for_reviewer={_format_scalar(item.get('ready_for_reviewer'))}; "
                    f"ready_for_judge={_format_scalar(item.get('ready_for_judge'))}"
                )
                artifact = item.get("artifact")
                if isinstance(artifact, dict):
                    lines.append(
                        f"    artifact: path={_format_scalar(artifact.get('path'))}; "
                        f"size_bytes={_format_scalar(artifact.get('size_bytes'))}; "
                        f"sha256={_format_scalar(artifact.get('sha256'))}"
                    )

    lines.append("result_presence:")
    result_presence = payload.get("result_presence")
    if isinstance(result_presence, dict):
        for actor in ALLOWED_ACTORS:
            lines.append(f"  - {actor}: {_format_scalar(result_presence.get(actor))}")

    lines.append("validation_commands:")
    for command in payload.get("validation_commands", []):
        lines.append(f"  - {command}")

    lines.append("execution_boundary:")
    boundary = payload.get("execution_boundary")
    if isinstance(boundary, dict):
        for key in (
            "execution_enabled",
            "provider_calls",
            "runtime_calls",
            "adapter_calls",
            "real_runner",
            "external_behavior_triggered",
            "artifact_content_executed",
        ):
            lines.append(f"  {key}: {_format_scalar(boundary.get(key))}")

    lines.append("safety_flags:")
    safety_flags = payload.get("safety_flags")
    if isinstance(safety_flags, dict):
        for key in (
            "no_env_read_expected",
            "no_env_vars_printed_expected",
            "no_provider_runtime_adapter_expected",
            "no_real_runner_expected",
            "read_only",
        ):
            lines.append(f"  {key}: {_format_scalar(safety_flags.get(key))}")

    for section in ("reviewer_guidance", "judge_guidance"):
        lines.append(f"{section}:")
        values = payload.get(section)
        if isinstance(values, list):
            for value in values:
                lines.append(f"  - {value}")

    lines.append("external_behavior:")
    external_behavior = payload.get("external_behavior")
    if isinstance(external_behavior, dict):
        for key in (
            "env_reads",
            "env_var_printing",
            "provider_calls",
            "runtime_calls",
            "adapter_calls",
            "artifact_writes",
            "real_runner",
        ):
            lines.append(f"  {key}: {_format_scalar(external_behavior.get(key))}")

    lines.extend(
        [
            "read_only: true",
            "artifact_content_executed: false",
            "provider/runtime/adapter execution: not triggered",
        ]
    )
    return "\n".join(lines)


def _format_handoff_objective(value: object) -> str:
    if isinstance(value, dict):
        objective_id = value.get("id")
        name = value.get("name")
        if name:
            return f"{objective_id} - {name}"
        return _format_scalar(objective_id)
    return _format_scalar(value)


def _format_handoff_profile(value: object) -> str:
    if isinstance(value, dict):
        selected = value.get("selected")
        default = value.get("default")
        is_default = value.get("is_default")
        return f"{selected} (default={default}; is_default={_format_scalar(is_default)})"
    return _format_scalar(value)


def _format_scalar(value: object) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if value is None:
        return "null"
    return str(value)


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
    lines.append("results:")
    result_presence = payload.get("result_presence")
    if isinstance(result_presence, dict):
        for actor in ALLOWED_ACTORS:
            lines.append(f"  - {actor}: {str(bool(result_presence.get(actor))).lower()}")
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


def format_actor_result_intake(payload: dict[str, object]) -> str:
    result = _expect_dict(payload, "result")
    artifact = _expect_dict(result, "artifact")
    return "\n".join(
        [
            "AgentOffice static actor result intake",
            f"path: {payload['path']}",
            f"run_id: {payload['run_id']}",
            f"actor: {payload['actor']}",
            f"artifact: {artifact['path']}",
            f"result_file: {payload['result_file']}",
            "execution_enabled: false",
            "provider_calls: []",
            "provider/runtime/adapter execution: not triggered",
        ]
    )


def format_run_bundle_results(payload: dict[str, object]) -> str:
    lines = [
        "AgentOffice static actor results",
        f"path: {payload['path']}",
        f"run_id: {payload['run_id']}",
        "results:",
    ]
    for result in payload["results"]:
        if isinstance(result, dict):
            artifact = result.get("artifact")
            path = artifact.get("path") if isinstance(artifact, dict) else None
            lines.append(f"  - {result.get('actor')}: {path}")
    lines.extend(["execution_enabled: false", "provider_calls: []", "provider/runtime/adapter execution: not triggered"])
    return "\n".join(lines)


def _load_existing_bundle(path: str | Path, project_root: Path) -> dict[str, object]:
    root = _resolve_bundle_path(path, project_root)
    if root.is_symlink() or not root.is_dir():
        raise RunBundleError(f"Run bundle path is not a directory: {path}")
    json_files: dict[str, object] = {}
    text_files: dict[str, str] = {}
    for relative in RUN_BUNDLE_REQUIRED_FILES:
        target = _safe_existing_bundle_file(root, relative)
        if not _exists(target, relative):
            raise RunBundleError(f"Missing run bundle file: {relative}")
        if _is_symlink(target, relative) or not _is_file(target, relative):
            raise RunBundleError(f"Invalid run bundle file: {relative}")
        if relative.endswith(".json"):
            json_files[relative] = _read_json_file(target, relative)
        else:
            text_files[relative] = _read_text_file(target, relative)
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
    if _is_symlink(requested, str(path)):
        raise RunBundleError(f"Refusing symlink run bundle path: {path}")
    try:
        resolved = requested.resolve(strict=False)
    except OSError as exc:
        raise RunBundleError(f"Unable to resolve run bundle path: {path}") from exc
    if resolved != base and base not in resolved.parents:
        raise RunBundleError(f"Refusing to read run bundle outside project root: {path}")
    return resolved


def _safe_existing_bundle_file(root: Path, relative: str) -> Path:
    target = root / relative
    try:
        resolved = target.resolve(strict=False)
    except OSError as exc:
        raise RunBundleError(f"Unable to resolve run bundle file: {relative}") from exc
    if root not in resolved.parents:
        raise RunBundleError(f"Refusing unsafe bundle path: {relative}")
    return target


def _read_json_file(path: Path, relative: str) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        raise RunBundleError(f"Invalid UTF-8 in run bundle file: {relative}") from exc
    except json.JSONDecodeError as exc:
        raise RunBundleError(f"Invalid JSON in run bundle file: {relative}") from exc
    except OSError as exc:
        raise RunBundleError(f"Unable to read run bundle file: {relative}") from exc


def _read_text_file(path: Path, relative: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise RunBundleError(f"Invalid UTF-8 in run bundle file: {relative}") from exc
    except OSError as exc:
        raise RunBundleError(f"Unable to read run bundle file: {relative}") from exc


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


def _load_actor_results(root: Path) -> dict[str, dict[str, object]]:
    results: dict[str, dict[str, object]] = {}
    for actor in ALLOWED_ACTORS:
        relative = f"{RUN_BUNDLE_RESULTS_DIR}/{actor}.json"
        target = _safe_existing_bundle_file(root, relative)
        if not _exists(target, relative):
            continue
        if _is_symlink(target, relative) or not _is_file(target, relative):
            raise RunBundleError(f"Invalid actor result file: {relative}")
        value = _read_json_file(target, relative)
        if not isinstance(value, dict):
            raise RunBundleError(f"Malformed actor result file: {relative}")
        if value.get("actor") != actor:
            raise RunBundleError(f"Actor result mismatch: {relative}")
        if value.get("execution_enabled") is not False:
            raise RunBundleError(f"Actor result execution_enabled must be false: {relative}")
        if value.get("provider_calls") != []:
            raise RunBundleError(f"Actor result provider_calls must be empty: {relative}")
        results[actor] = value
    return results



def _actor_packet_identity(packet: dict[str, object]) -> dict[str, object]:
    objective = packet.get("objective") if isinstance(packet.get("objective"), dict) else {}
    profile = packet.get("profile") if isinstance(packet.get("profile"), dict) else {}
    return {
        "actor": packet.get("actor"),
        "packet_version": packet.get("packet_version"),
        "objective": objective.get("id"),
        "profile": profile.get("selected"),
        "execution_enabled": packet.get("execution_enabled"),
        "env_required": packet.get("env_required"),
        "runtime_calls": packet.get("runtime_calls"),
        "adapter_calls": packet.get("adapter_calls"),
    }


def _packet_ready(actor: str, identity: dict[str, object]) -> bool:
    return (
        identity.get("actor") == actor
        and identity.get("execution_enabled") is False
        and identity.get("env_required") is False
        and identity.get("runtime_calls") is False
        and identity.get("adapter_calls") is False
    )


def _handoff_validation_commands(plan: dict[str, object], path: str | Path) -> list[str]:
    commands: list[str] = []
    raw_commands = plan.get("validation_commands")
    if isinstance(raw_commands, list):
        for command in raw_commands:
            if isinstance(command, str) and command not in commands:
                commands.append(command)
    path_text = str(path)
    for command in (
        f"python3 -m agent_office run-bundle validate --path {path_text} --json",
        f"python3 -m agent_office run-bundle status --path {path_text} --json",
        f"python3 -m agent_office run-bundle handoff --path {path_text} --json",
    ):
        if command not in commands:
            commands.append(command)
    return commands


def _string_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)

def _result_presence(results: dict[str, dict[str, object]]) -> dict[str, bool]:
    return {actor: actor in results for actor in ALLOWED_ACTORS}


def _actor_result_payload(actor: str, artifact_path: Path, project_root: Path) -> dict[str, object]:
    # ponytail: P7-04 records artifact metadata only; bundle-portable byte copies are out of scope.
    try:
        stat = artifact_path.stat()
    except OSError as exc:
        raise RunBundleError(f"Unable to stat artifact file: {artifact_path}") from exc
    return {
        "kind": "static_actor_result",
        "schema_version": RUN_BUNDLE_SCHEMA_VERSION,
        "actor": actor,
        "artifact": {
            "path": _project_relative_path(artifact_path, project_root),
            "size_bytes": stat.st_size,
            "sha256": _sha256_file(artifact_path),
        },
        "execution_enabled": False,
        "provider_calls": [],
        "runtime_calls": False,
        "adapter_calls": False,
        "real_runner": False,
    }


def _validate_actor(actor: str) -> None:
    if actor not in ALLOWED_ACTORS:
        raise RunBundleError("run-bundle actor must be codex, reviewer, or judge")


def _resolve_artifact_path(path: str | Path, project_root: Path) -> Path:
    base = project_root.resolve()
    requested = Path(path)
    if not requested.is_absolute():
        requested = project_root / requested
    if _is_symlink(requested, str(path)):
        raise RunBundleError(f"Refusing symlink artifact: {path}")
    try:
        resolved = requested.resolve(strict=False)
    except OSError as exc:
        raise RunBundleError(f"Unable to resolve artifact path: {path}") from exc
    if resolved != base and base not in resolved.parents:
        raise RunBundleError(f"Refusing artifact outside project root: {path}")
    if not _exists(requested, str(path)):
        raise RunBundleError(f"Missing artifact file: {path}")
    if not _is_file(requested, str(path)):
        raise RunBundleError(f"Artifact path is not a file: {path}")
    try:
        return requested.resolve(strict=True)
    except OSError as exc:
        raise RunBundleError(f"Unable to resolve artifact path: {path}") from exc


def _project_relative_path(path: Path, project_root: Path) -> str:
    return path.resolve().relative_to(project_root.resolve()).as_posix()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise RunBundleError(f"Unable to read artifact file: {path}") from exc
    return digest.hexdigest()


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


def _local_write_external_behavior() -> dict[str, bool]:
    behavior = _read_only_external_behavior()
    behavior["artifact_writes"] = True
    return behavior


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
    if _is_symlink(path, str(out)):
        raise RunBundleError(f"Refusing to write run bundle to symlink path: {out}")
    try:
        resolved = path.resolve(strict=False)
    except OSError as exc:
        raise RunBundleError(f"Unable to resolve run bundle output path: {out}") from exc
    if resolved != base and base not in resolved.parents:
        raise RunBundleError(f"Refusing to write run bundle outside project root: {out}")
    return resolved


def _safe_target(out_root: Path, relative: str) -> Path:
    target = out_root / relative
    if _is_symlink(target, relative):
        return target
    try:
        resolved = target.resolve(strict=False)
    except OSError as exc:
        raise RunBundleError(f"Unable to resolve bundle target: {relative}") from exc
    if resolved == out_root or out_root not in resolved.parents:
        raise RunBundleError(f"Refusing unsafe bundle path: {relative}")
    return target


def _write_json(path: Path, value: object) -> None:
    _write_text(path, json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def _write_text(path: Path, value: str) -> None:
    tmp = path.with_name(f"{path.name}.tmp")
    if _is_symlink(tmp, str(tmp)):
        raise RunBundleError(f"Refusing to write temporary symlink: {tmp}")
    try:
        tmp.write_text(value, encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        raise RunBundleError(f"Unable to write bundle file: {path}") from exc


def _exists(path: Path, label: str) -> bool:
    try:
        return path.exists()
    except OSError as exc:
        raise RunBundleError(f"Unable to access path: {label}") from exc


def _is_file(path: Path, label: str) -> bool:
    try:
        return path.is_file()
    except OSError as exc:
        raise RunBundleError(f"Unable to access path: {label}") from exc


def _is_symlink(path: Path, label: str) -> bool:
    try:
        return path.is_symlink()
    except OSError as exc:
        raise RunBundleError(f"Unable to access path: {label}") from exc


def _mkdir(path: Path, label: str) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RunBundleError(f"Unable to create directory: {label}") from exc


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


def _expect_path(payload: dict[str, object], key: str) -> Path:
    value = payload.get(key)
    if not isinstance(value, Path):
        raise RunBundleError(f"Malformed run bundle payload: missing {key}")
    return value


def _add_check(checks: list[dict[str, str]], name: str, passed: bool) -> None:
    checks.append({"name": name, "status": "pass" if passed else "fail"})


def _checks_pass(checks: list[dict[str, str]]) -> bool:
    return all(check["status"] == "pass" for check in checks)
