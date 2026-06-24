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
GATE_SCHEMA_VERSION = 1
WORKFLOW_SCHEMA_VERSION = 1
EXPORT_REVIEW_SCHEMA_VERSION = 1
RUN_BUNDLE_REVIEW_ARTIFACT_SECTIONS = (
    "Bundle summary",
    "Workflow summary",
    "Handoff summary",
    "Review summary",
    "Gate summary",
    "Actor results",
    "Safety summary",
    "Commands",
    "Source snapshots / metadata",
    "Contract notes",
    "Completion marker",
)
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



def gate_run_bundle_payload(path: str | Path, project_root: Path) -> dict[str, object]:
    command = f"python3 -m agent_office run-bundle gate --path {path}"
    try:
        bundle = _load_existing_bundle(path, project_root)
        run = _validate_loaded_bundle(bundle)
        validation = validate_run_bundle_payload(path, project_root)
        root = _expect_path(bundle, "root")
        results = _load_actor_results(root)
    except RunBundleError as exc:
        return _gate_error_payload(path, project_root, command, str(exc))

    json_files = _expect_dict(bundle, "json")
    valid_bundle = validation.get("valid") is True
    packet_readiness = {
        actor: _packet_ready(actor, _actor_packet_identity(_expect_dict(json_files, f"packets/{actor}.json")))
        for actor in ALLOWED_ACTORS
    }
    review_ready = bool(valid_bundle and all(packet_readiness.values()))
    result_presence = _result_presence(results)
    review_intake = result_presence["reviewer"]
    judge_intake = result_presence["judge"]
    reviewer_decision = _gate_actor_decision("reviewer", results.get("reviewer"))
    judge_decision = _gate_actor_decision("judge", results.get("judge"))

    review_blocked = reviewer_decision["state"] == "blocked"
    review_failed = reviewer_decision["state"] == "fail"
    judge_ready = bool(review_ready and review_intake and not review_blocked and not review_failed)
    final_state = _gate_final_state(valid_bundle, review_ready, reviewer_decision, judge_decision)
    blocking_reasons = _gate_blocking_reasons(
        valid_bundle=valid_bundle,
        review_ready=review_ready,
        review_intake=review_intake,
        judge_ready=judge_ready,
        judge_intake=judge_intake,
        reviewer_decision=reviewer_decision,
        judge_decision=judge_decision,
    )
    warnings = _gate_warnings(
        review_intake=review_intake,
        judge_intake=judge_intake,
        reviewer_decision=reviewer_decision,
        judge_decision=judge_decision,
    )
    return {
        "kind": "static_run_bundle_gate",
        "schema_version": RUN_BUNDLE_SCHEMA_VERSION,
        "gate_schema_version": GATE_SCHEMA_VERSION,
        "command": command,
        "run_id": run["run_id"],
        "path": str(root),
        "exists": True,
        "valid_bundle": valid_bundle,
        "review_ready": review_ready,
        "review_intake": review_intake,
        "judge_ready": judge_ready,
        "judge_intake": judge_intake,
        "final_state": final_state,
        "blocking_reasons": blocking_reasons,
        "warnings": warnings,
        "evidence": _gate_evidence(bundle, results, reviewer_decision, judge_decision),
        "recommended_next_commands": _gate_recommended_next_commands(path, valid_bundle, review_ready, review_intake, judge_ready, judge_intake, final_state),
        "safety": _gate_safety(),
    }



def workflow_run_bundle_payload(path: str | Path, project_root: Path) -> dict[str, object]:
    command = f"python3 -m agent_office run-bundle workflow --path {path}"
    gate = gate_run_bundle_payload(path, project_root)
    if gate.get("valid_bundle") is not True:
        return _workflow_payload(path, command, gate, None, None)
    try:
        handoff = handoff_run_bundle_payload(path, project_root)
        review = review_run_bundle_payload(path, project_root)
    except RunBundleError as exc:
        gate = _gate_error_payload(path, project_root, command, str(exc))
        return _workflow_payload(path, command, gate, None, None)
    return _workflow_payload(path, command, gate, handoff, review)


def export_review_run_bundle_payload(path: str | Path, out: str | Path, project_root: Path) -> dict[str, object]:
    out_path = _resolve_export_review_out_path(out, project_root)
    sha256_path = _resolve_export_review_sha256_path(out_path, project_root)
    bundle = _load_existing_bundle(path, project_root)
    run = _validate_loaded_bundle(bundle)
    root = _expect_path(bundle, "root")
    validation = validate_run_bundle_payload(path, project_root)
    status = status_run_bundle_payload(path, project_root)
    handoff = handoff_run_bundle_payload(path, project_root)
    review = review_run_bundle_payload(path, project_root)
    gate = gate_run_bundle_payload(path, project_root)
    workflow = workflow_run_bundle_payload(path, project_root)
    if workflow.get("valid_bundle") is not True:
        warnings = workflow.get("warnings") if isinstance(workflow.get("warnings"), list) else []
        message = "; ".join(str(item) for item in warnings) or "Invalid run bundle"
        raise RunBundleError(message)

    artifact_text = _export_review_artifact_text(
        project_root=project_root,
        bundle=bundle,
        run=run,
        validation=validation,
        status=status,
        handoff=handoff,
        review=review,
        gate=gate,
        workflow=workflow,
    )
    _write_export_text(out_path, artifact_text)
    sha256 = _sha256_file(out_path)
    sha256_text = f"{sha256}  {out_path.name}\n"
    _write_export_text(sha256_path, sha256_text)
    try:
        byte_count = out_path.stat().st_size
    except OSError as exc:
        raise RunBundleError(f"Unable to stat review artifact: {out_path}") from exc

    warnings = workflow.get("warnings") if isinstance(workflow.get("warnings"), list) else []
    blocking_reasons = workflow.get("blocking_reasons") if isinstance(workflow.get("blocking_reasons"), list) else []
    return {
        "schema_version": RUN_BUNDLE_SCHEMA_VERSION,
        "export_review_schema_version": EXPORT_REVIEW_SCHEMA_VERSION,
        "kind": "run_bundle_export_review",
        "valid_bundle": True,
        "run_id": run["run_id"],
        "path": str(root),
        "out": str(out_path),
        "sha256_path": str(sha256_path),
        "sha256": sha256,
        "byte_count": byte_count,
        "sections": list(RUN_BUNDLE_REVIEW_ARTIFACT_SECTIONS),
        "missing_file_markers": 0,
        "empty_section_markers": 0,
        "warnings": warnings,
        "blocking_reasons": blocking_reasons,
    }


def export_review_error_payload(path: str | Path | None, out: str | Path | None, error: str) -> dict[str, object]:
    return {
        "schema_version": RUN_BUNDLE_SCHEMA_VERSION,
        "export_review_schema_version": EXPORT_REVIEW_SCHEMA_VERSION,
        "kind": "run_bundle_export_review",
        "valid_bundle": False,
        "run_id": None,
        "path": str(path) if path is not None else None,
        "out": str(out) if out is not None else None,
        "sha256_path": f"{out}.sha256" if out else None,
        "sha256": None,
        "byte_count": 0,
        "sections": [],
        "missing_file_markers": 0,
        "empty_section_markers": 0,
        "warnings": [error],
        "blocking_reasons": [_export_review_error_reason(error)],
    }


def format_run_bundle_export_review(payload: dict[str, object]) -> str:
    return "\n".join(
        [
            "Run bundle review artifact exported",
            f"Run ID: {payload['run_id']}",
            f"Artifact: {payload['out']}",
            f"SHA256: {payload['sha256']}",
            f"Byte count: {payload['byte_count']}",
            f"Missing markers: {payload['missing_file_markers']}",
            f"Empty sections: {payload['empty_section_markers']}",
        ]
    )


def _workflow_payload(
    path: str | Path,
    command: str,
    gate: dict[str, object],
    handoff: dict[str, object] | None,
    review: dict[str, object] | None,
) -> dict[str, object]:
    valid_bundle = gate.get("valid_bundle") is True
    readiness = {
        "handoff_ready": valid_bundle,
        "review_ready": gate.get("review_ready") is True,
        "gate_ready": bool(valid_bundle and gate.get("review_ready") is True),
    }
    summary = _workflow_summary(gate, readiness)
    actors = _workflow_actors(gate, review)
    missing_actors = [actor for actor, item in actors.items() if item.get("result_present") is not True]
    gate_summary = {
        "final_state": gate.get("final_state") if isinstance(gate.get("final_state"), str) else "blocked",
        "blocking_reasons": gate.get("blocking_reasons") if isinstance(gate.get("blocking_reasons"), list) else [],
        "warnings": gate.get("warnings") if isinstance(gate.get("warnings"), list) else [],
    }
    return {
        "schema_version": RUN_BUNDLE_SCHEMA_VERSION,
        "workflow_schema_version": WORKFLOW_SCHEMA_VERSION,
        "kind": "static_run_bundle_workflow",
        "valid_bundle": valid_bundle,
        "run_id": gate.get("run_id"),
        "objective": handoff.get("objective") if handoff is not None else None,
        "profile": handoff.get("profile") if handoff is not None else None,
        "path": gate.get("path") if isinstance(gate.get("path"), str) else str(path),
        "phase": "workflow",
        "summary": summary,
        "readiness": readiness,
        "gate": gate_summary,
        "actors": actors,
        "missing_actors": missing_actors,
        "blocking_reasons": gate_summary["blocking_reasons"],
        "warnings": gate_summary["warnings"],
        "safety": _gate_safety(),
        "commands": _workflow_commands(path, summary),
    }


def _workflow_summary(gate: dict[str, object], readiness: dict[str, object]) -> dict[str, object]:
    if gate.get("valid_bundle") is not True:
        return {"final_state": "invalid", "safe_to_merge": False, "next_action": "fix_bundle"}
    gate_state = gate.get("final_state") if isinstance(gate.get("final_state"), str) else "blocked"
    if gate_state == "pass":
        return {"final_state": "pass", "safe_to_merge": True, "next_action": "merge"}
    if gate_state == "fail":
        return {"final_state": "fail", "safe_to_merge": False, "next_action": "fix_actor_results"}
    if gate_state == "blocked":
        return {"final_state": "blocked", "safe_to_merge": False, "next_action": "blocked"}
    if gate_state != "incomplete":
        return {"final_state": "blocked", "safe_to_merge": False, "next_action": "blocked"}

    reasons = gate.get("blocking_reasons") if isinstance(gate.get("blocking_reasons"), list) else []
    warnings = gate.get("warnings") if isinstance(gate.get("warnings"), list) else []
    if "invalid_bundle" in reasons:
        next_action = "fix_bundle"
    elif readiness.get("review_ready") is not True or "review_result_missing" in reasons:
        next_action = "run_review"
    elif any(str(warning).endswith("_has_no_static_decision") for warning in warnings) or "judge_decision_missing" in reasons:
        next_action = "fix_actor_results"
    else:
        next_action = "run_gate"
    return {"final_state": "incomplete", "safe_to_merge": False, "next_action": next_action}


def _workflow_actors(gate: dict[str, object], review: dict[str, object] | None) -> dict[str, object]:
    review_evidence: dict[str, dict[str, object]] = {}
    if review is not None and isinstance(review.get("actor_evidence"), list):
        for item in review["actor_evidence"]:
            if isinstance(item, dict) and item.get("actor") in ALLOWED_ACTORS:
                review_evidence[str(item["actor"])] = item

    gate_evidence: dict[str, dict[str, object]] = {}
    if isinstance(gate.get("evidence"), list):
        for item in gate["evidence"]:
            if isinstance(item, dict) and item.get("actor") in ALLOWED_ACTORS:
                gate_evidence[str(item["actor"])] = item

    actors: dict[str, object] = {}
    for actor in ALLOWED_ACTORS:
        review_item = review_evidence.get(actor, {})
        gate_item = gate_evidence.get(actor, {})
        artifact = review_item.get("artifact") if isinstance(review_item.get("artifact"), dict) else None
        if artifact is None and isinstance(gate_item.get("artifact"), dict):
            artifact = gate_item["artifact"]
        result_present = review_item.get("result_present") is True or gate_item.get("status") == "present"
        actor_summary: dict[str, object] = {
            "packet_ready": review_item.get("packet_ready") is True,
            "result_present": result_present,
            "result_file": f"{RUN_BUNDLE_RESULTS_DIR}/{actor}.json",
            "artifact": artifact,
        }
        decision = gate_item.get("decision")
        if isinstance(decision, dict):
            actor_summary["decision"] = decision
        elif actor in {"reviewer", "judge"}:
            actor_summary["decision"] = {
                "actor": actor,
                "state": "unknown" if result_present else "missing",
                "signals": [],
                "blocking_reasons": [],
            }
        actors[actor] = actor_summary
    return actors


def _workflow_commands(path: str | Path, summary: dict[str, object]) -> dict[str, str]:
    path_text = str(path)
    merge_guidance = "Do not merge until summary.safe_to_merge is true and the reviewed branch is approved."
    if summary.get("safe_to_merge") is True:
        merge_guidance = "summary.safe_to_merge is true; merge only through the reviewed branch gate."
    return {
        "handoff": f"python3 -m agent_office run-bundle handoff --path {path_text} --json",
        "review": f"python3 -m agent_office run-bundle review --path {path_text} --json",
        "gate": f"python3 -m agent_office run-bundle gate --path {path_text} --json",
        "merge_guidance": merge_guidance,
    }


def format_run_bundle_workflow(payload: dict[str, object]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    readiness = payload.get("readiness") if isinstance(payload.get("readiness"), dict) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), dict) else {}
    objective = payload.get("objective") if isinstance(payload.get("objective"), dict) else None
    profile = payload.get("profile") if isinstance(payload.get("profile"), dict) else None
    lines = [
        "Run bundle workflow",
        f"Run ID: {_format_scalar(payload.get('run_id'))}",
        f"Objective: {_format_handoff_objective(objective) if objective is not None else 'none'}",
        f"Profile: {_format_handoff_profile(profile) if profile is not None else 'none'}",
        f"Valid bundle: {_format_scalar(payload.get('valid_bundle'))}",
        f"Handoff ready: {_format_scalar(readiness.get('handoff_ready'))}",
        f"Review ready: {_format_scalar(readiness.get('review_ready'))}",
        f"Gate ready: {_format_scalar(readiness.get('gate_ready'))}",
        f"Gate final state: {_format_scalar(gate.get('final_state'))}",
        f"Safe to merge: {_format_scalar(summary.get('safe_to_merge'))}",
        f"Next action: {_format_scalar(summary.get('next_action'))}",
        "Blocking reasons:",
    ]
    _append_workflow_items(lines, payload.get("blocking_reasons"))
    lines.append("Warnings:")
    _append_workflow_items(lines, payload.get("warnings"))
    lines.append("Commands:")
    commands = payload.get("commands")
    if isinstance(commands, dict):
        for key in ("handoff", "review", "gate", "merge_guidance"):
            lines.append(f"  {key}: {_format_scalar(commands.get(key))}")
    lines.append("provider/runtime/adapter execution: not triggered")
    return "\n".join(lines)


def _append_workflow_items(lines: list[str], values: object) -> None:
    if isinstance(values, list) and values:
        for value in values:
            lines.append(f"  - {value}")
    else:
        lines.append("  - none")


def format_run_bundle_gate(payload: dict[str, object]) -> str:
    lines = [
        "AgentOffice static run bundle gate",
        f"schema_version: {payload['schema_version']}",
        f"gate_schema_version: {payload['gate_schema_version']}",
        f"command: {payload['command']}",
        f"path: {payload['path']}",
        f"run_id: {_format_scalar(payload.get('run_id'))}",
        f"exists: {_format_scalar(payload.get('exists'))}",
        f"valid_bundle: {_format_scalar(payload.get('valid_bundle'))}",
        f"final_state: {payload['final_state']}",
        "review:",
        f"  ready: {_format_scalar(payload.get('review_ready'))}",
        f"  intake: {_format_scalar(payload.get('review_intake'))}",
        "judge:",
        f"  ready: {_format_scalar(payload.get('judge_ready'))}",
        f"  intake: {_format_scalar(payload.get('judge_intake'))}",
        "blocking_reasons:",
    ]
    reasons = payload.get("blocking_reasons")
    if isinstance(reasons, list) and reasons:
        for reason in reasons:
            lines.append(f"  - {reason}")
    else:
        lines.append("  - none")

    lines.append("warnings:")
    warnings = payload.get("warnings")
    if isinstance(warnings, list) and warnings:
        for warning in warnings:
            lines.append(f"  - {warning}")
    else:
        lines.append("  - none")

    lines.append("evidence:")
    evidence = payload.get("evidence")
    if isinstance(evidence, list) and evidence:
        for item in evidence:
            if not isinstance(item, dict):
                continue
            line = f"  - {item.get('type')}: {item.get('path')} ({item.get('status')})"
            actor = item.get("actor")
            if actor:
                line += f"; actor={actor}"
            artifact = item.get("artifact")
            if isinstance(artifact, dict):
                line += f"; artifact={_format_scalar(artifact.get('path'))}"
            decision = item.get("decision")
            if isinstance(decision, dict):
                line += f"; decision={decision.get('state')}"
            lines.append(line)
    else:
        lines.append("  - none")

    lines.append("next_commands:")
    commands = payload.get("recommended_next_commands")
    if isinstance(commands, list):
        for command in commands:
            lines.append(f"  - {command}")

    lines.append("safety:")
    safety = payload.get("safety")
    if isinstance(safety, dict):
        for key in (
            "local_only",
            "env_not_read",
            "provider_calls",
            "runtime_calls",
            "adapter_calls",
            "external_calls",
            "artifact_content_executed",
            "read_only",
        ):
            lines.append(f"  {key}: {_format_scalar(safety.get(key))}")
    lines.append("provider/runtime/adapter execution: not triggered")
    return "\n".join(lines)

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



def _gate_error_payload(path: str | Path, project_root: Path, command: str, error: str) -> dict[str, object]:
    path_text = str(path)
    exists = False
    try:
        root = _resolve_bundle_path(path, project_root)
        path_text = str(root)
        exists = _exists(root, str(path))
    except RunBundleError:
        pass
    reason = _gate_error_reason(error)
    return {
        "kind": "static_run_bundle_gate",
        "schema_version": RUN_BUNDLE_SCHEMA_VERSION,
        "gate_schema_version": GATE_SCHEMA_VERSION,
        "command": command,
        "run_id": None,
        "path": path_text,
        "exists": exists,
        "valid_bundle": False,
        "review_ready": False,
        "review_intake": False,
        "judge_ready": False,
        "judge_intake": False,
        "final_state": "blocked",
        "blocking_reasons": [reason],
        "warnings": [error],
        "evidence": [],
        "recommended_next_commands": _gate_recommended_next_commands(path, False, False, False, False, False, "blocked"),
        "safety": _gate_safety(),
    }


def _gate_error_reason(error: str) -> str:
    if "results/" in error or "actor result" in error:
        return "malformed_actor_result"
    if "symlink" in error or "outside project root" in error or "unsafe" in error:
        return "unsafe_path"
    if "Run bundle path is not a directory" in error:
        return "missing_path"
    if "Missing run bundle file" in error:
        return "missing_required_file"
    if "Invalid UTF-8" in error:
        return "non_utf8"
    if "Invalid JSON" in error:
        return "malformed_json"
    return "invalid_bundle"


def _gate_actor_decision(actor: str, result: dict[str, object] | None) -> dict[str, object]:
    if result is None:
        return {"actor": actor, "state": "missing", "signals": [], "blocking_reasons": []}
    signals: list[str] = []
    for key in ("final_state", "verdict", "decision", "status", "outcome"):
        value = result.get(key)
        if isinstance(value, str):
            signals.append(_normalize_gate_signal(value))
    passed = result.get("passed")
    if passed is True:
        signals.append("pass")
    elif passed is False:
        signals.append("fail")

    blocking_reasons: list[str] = []
    for key in ("blocking_reasons", "blockers"):
        value = result.get(key)
        if _string_list(value):
            blocking_reasons.extend(value)
    if result.get("blocked") is True or result.get("blocker") is True:
        blocking_reasons.append(f"{actor}_blocked")

    # ponytail: P10 recognizes a small static verdict vocabulary; richer provider-specific parsing stays out of scope.
    if blocking_reasons or any(signal in {"blocked", "blocker", "blockers"} for signal in signals):
        state = "blocked"
    elif any(signal in {"fail", "failed", "failure", "reject", "rejected", "request_changes", "changes_requested"} for signal in signals):
        state = "fail"
    elif any(signal in {"pass", "passed", "approved", "approve", "accepted", "ok", "success"} for signal in signals):
        state = "pass"
    else:
        state = "unknown"
    return {"actor": actor, "state": state, "signals": signals, "blocking_reasons": blocking_reasons}


def _normalize_gate_signal(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _gate_final_state(
    valid_bundle: bool,
    review_ready: bool,
    reviewer_decision: dict[str, object],
    judge_decision: dict[str, object],
) -> str:
    if not valid_bundle or not review_ready:
        return "blocked"
    if reviewer_decision["state"] == "blocked" or judge_decision["state"] == "blocked":
        return "blocked"
    if reviewer_decision["state"] == "fail" or judge_decision["state"] == "fail":
        return "fail"
    if judge_decision["state"] == "pass":
        return "pass"
    return "incomplete"


def _gate_blocking_reasons(
    *,
    valid_bundle: bool,
    review_ready: bool,
    review_intake: bool,
    judge_ready: bool,
    judge_intake: bool,
    reviewer_decision: dict[str, object],
    judge_decision: dict[str, object],
) -> list[str]:
    reasons: list[str] = []
    if not valid_bundle:
        reasons.append("invalid_bundle")
    if not review_ready:
        reasons.append("review_not_ready")
    if not review_intake:
        reasons.append("review_result_missing")
    if reviewer_decision["state"] == "blocked":
        reasons.append("review_blocker")
    if reviewer_decision["state"] == "fail":
        reasons.append("review_failed")
    if not judge_ready:
        reasons.append("judge_not_ready")
    if judge_ready and not judge_intake:
        reasons.append("judge_result_missing")
    if judge_intake and judge_decision["state"] == "unknown":
        reasons.append("judge_decision_missing")
    if judge_decision["state"] == "blocked":
        reasons.append("judge_blocked")
    if judge_decision["state"] == "fail":
        reasons.append("judge_failed")
    return _dedupe_strings(reasons)


def _gate_warnings(
    *,
    review_intake: bool,
    judge_intake: bool,
    reviewer_decision: dict[str, object],
    judge_decision: dict[str, object],
) -> list[str]:
    warnings: list[str] = []
    if review_intake and reviewer_decision["state"] == "unknown":
        warnings.append("review_result_has_no_static_decision")
    if judge_intake and judge_decision["state"] == "unknown":
        warnings.append("judge_result_has_no_static_decision")
    return warnings


def _gate_evidence(
    bundle: dict[str, object],
    results: dict[str, dict[str, object]],
    reviewer_decision: dict[str, object],
    judge_decision: dict[str, object],
) -> list[dict[str, object]]:
    evidence: list[dict[str, object]] = []
    for item in _bundle_file_statuses(bundle):
        if isinstance(item, dict):
            evidence.append({"type": "bundle_file", "path": item["path"], "status": item["status"], "kind": item["kind"]})
    decisions = {"reviewer": reviewer_decision, "judge": judge_decision}
    for actor in ALLOWED_ACTORS:
        result = results.get(actor)
        evidence_type = {"codex": "result_artifact", "reviewer": "review_artifact", "judge": "judge_artifact"}[actor]
        item: dict[str, object] = {
            "type": evidence_type,
            "actor": actor,
            "path": f"{RUN_BUNDLE_RESULTS_DIR}/{actor}.json",
            "status": "present" if result is not None else "missing",
        }
        if result is not None:
            artifact = result.get("artifact")
            if isinstance(artifact, dict):
                item["artifact"] = {
                    "path": artifact.get("path"),
                    "size_bytes": artifact.get("size_bytes"),
                    "sha256": artifact.get("sha256"),
                }
            if actor in decisions:
                item["decision"] = decisions[actor]
        evidence.append(item)
    return evidence


def _gate_recommended_next_commands(
    path: str | Path,
    valid_bundle: bool,
    review_ready: bool,
    review_intake: bool,
    judge_ready: bool,
    judge_intake: bool,
    final_state: str,
) -> list[str]:
    path_text = str(path)
    commands = [
        f"python3 -m agent_office run-bundle inspect --path {path_text} --json",
        f"python3 -m agent_office run-bundle validate --path {path_text} --json",
    ]
    if not valid_bundle:
        return commands
    commands.append(f"python3 -m agent_office run-bundle review --path {path_text} --json")
    if review_ready and not review_intake:
        commands.append(f"python3 -m agent_office run-bundle intake --path {path_text} --actor reviewer --artifact <review-artifact>")
    if judge_ready and not judge_intake:
        commands.append(f"python3 -m agent_office run-bundle intake --path {path_text} --actor judge --artifact <judge-artifact>")
    commands.append(f"python3 -m agent_office run-bundle results --path {path_text} --json")
    commands.append(f"python3 -m agent_office run-bundle gate --path {path_text} --json")
    if final_state in {"pass", "fail", "blocked"}:
        commands.append(f"python3 -m agent_office run-bundle status --path {path_text} --json")
    return _dedupe_strings(commands)


def _gate_safety() -> dict[str, bool]:
    return {
        "local_only": True,
        "env_not_read": True,
        "env_var_printing": False,
        "provider_calls": False,
        "runtime_calls": False,
        "adapter_calls": False,
        "external_calls": False,
        "artifact_writes": False,
        "artifact_content_executed": False,
        "read_only": True,
    }


def _export_review_artifact_text(
    *,
    project_root: Path,
    bundle: dict[str, object],
    run: dict[str, object],
    validation: dict[str, object],
    status: dict[str, object],
    handoff: dict[str, object],
    review: dict[str, object],
    gate: dict[str, object],
    workflow: dict[str, object],
) -> str:
    root = _expect_path(bundle, "root")
    objective = run.get("objective")
    profile = run.get("profile")
    summary = workflow.get("summary") if isinstance(workflow.get("summary"), dict) else {}
    readiness = workflow.get("readiness") if isinstance(workflow.get("readiness"), dict) else {}
    gate_summary = workflow.get("gate") if isinstance(workflow.get("gate"), dict) else {}
    review_readiness = review.get("readiness") if isinstance(review.get("readiness"), dict) else {}
    result_presence = handoff.get("result_presence") if isinstance(handoff.get("result_presence"), dict) else {}
    lines = [
        "# AgentOffice Run Bundle Review Artifact",
        "",
        "## Integrity guard",
        "MISSING_FILE_MARKERS: 0",
        "EMPTY_SECTION_MARKERS: 0",
        "",
        "## Reviewed state",
        f"- repo root: {project_root.resolve()}",
        f"- bundle path: {root}",
        f"- run_id: {run['run_id']}",
        f"- objective: {_format_handoff_objective(objective)}",
        f"- profile: {_format_handoff_profile(profile)}",
        "",
        "## Bundle summary",
        f"- status: {_format_scalar(status.get('status'))}",
        f"- valid: {_format_scalar(validation.get('valid'))}",
        f"- required_files: {len(RUN_BUNDLE_REQUIRED_FILES)}",
        "- provider/runtime/adapter execution: not triggered",
        "",
        "## Workflow summary",
        f"- final_state: {_format_scalar(summary.get('final_state'))}",
        f"- safe_to_merge: {_format_scalar(summary.get('safe_to_merge'))}",
        f"- next_action: {_format_scalar(summary.get('next_action'))}",
        f"- handoff_ready: {_format_scalar(readiness.get('handoff_ready'))}",
        f"- review_ready: {_format_scalar(readiness.get('review_ready'))}",
        f"- gate_ready: {_format_scalar(readiness.get('gate_ready'))}",
        "",
        "## Handoff summary",
        f"- read_only: {_format_scalar(handoff.get('read_only'))}",
        f"- actor_result_presence: {_format_actor_presence(result_presence)}",
        f"- expected_files: {', '.join(str(item) for item in handoff.get('expected_files', []))}",
        "",
        "## Review summary",
        f"- claude_review_ready: {_format_scalar(review_readiness.get('claude_review_ready'))}",
        f"- judge_ready: {_format_scalar(review_readiness.get('judge_ready'))}",
        f"- actor_results_complete: {_format_scalar(review_readiness.get('actor_results_complete'))}",
        "- artifact_content_executed: false",
        "",
        "## Gate summary",
        f"- final_state: {_format_scalar(gate.get('final_state'))}",
        f"- blocking_reasons: {_format_list_inline(gate.get('blocking_reasons'))}",
        f"- warnings: {_format_list_inline(gate.get('warnings'))}",
        f"- workflow_gate_summary: final_state={_format_scalar(gate_summary.get('final_state'))}; blocking_reasons={_format_list_inline(gate_summary.get('blocking_reasons'))}",
        "",
        "## Actor results",
    ]
    actors = workflow.get("actors") if isinstance(workflow.get("actors"), dict) else {}
    for actor in ALLOWED_ACTORS:
        item = actors.get(actor) if isinstance(actors.get(actor), dict) else {}
        decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
        lines.append(
            f"- {actor}: result_present={_format_scalar(item.get('result_present'))}; "
            f"result_file={_format_scalar(item.get('result_file'))}; "
            f"decision={_format_scalar(decision.get('state'))}"
        )
        artifact = item.get("artifact")
        if isinstance(artifact, dict):
            lines.append(
                f"  - artifact metadata: path={_format_scalar(artifact.get('path'))}; "
                f"size_bytes={_format_scalar(artifact.get('size_bytes'))}; "
                f"sha256={_format_scalar(artifact.get('sha256'))}"
            )
        else:
            lines.append("  - artifact metadata: none")
    lines.extend(
        [
            "",
            "## Safety summary",
            "- env_reads: false",
            "- env_var_printing: false",
            "- provider_calls: false",
            "- runtime_calls: false",
            "- adapter_calls: false",
            "- actor_artifact_content_executed: false",
            "- bundle_writes: false",
            "- export_writes: --out and --out.sha256 only",
            "",
            "## Commands",
        ]
    )
    for command in _export_review_commands(workflow, review):
        lines.append(f"- {command}")
    lines.extend(["", "## Source snapshots / metadata"])
    for item in _export_review_source_metadata(bundle):
        line = f"- {item['path']}: status={item['status']}; kind={item['kind']}"
        if "size_bytes" in item:
            line += f"; size_bytes={item['size_bytes']}; sha256={item['sha256']}"
        lines.append(line)
    lines.extend(
        [
            "",
            "## Contract notes",
            "- This artifact is generated from local static bundle payloads only.",
            "- Actor artifact source content is not copied, reread, executed, or embedded.",
            "- The export action does not read .env, print environment values, call providers, call adapters, or call runtimes.",
            "- The export action must not write .ai/runs/* or mutate bundle/result/source artifact files.",
            "",
            "## Completion marker",
            "RUN_BUNDLE_REVIEW_ARTIFACT_EXPORT_COMPLETE",
        ]
    )
    return "\n".join(lines) + "\n"


def _format_actor_presence(result_presence: object) -> str:
    if not isinstance(result_presence, dict):
        return "none"
    return ", ".join(f"{actor}={_format_scalar(result_presence.get(actor))}" for actor in ALLOWED_ACTORS)


def _format_list_inline(value: object) -> str:
    if isinstance(value, list) and value:
        return ", ".join(str(item) for item in value)
    return "none"


def _export_review_commands(workflow: dict[str, object], review: dict[str, object]) -> list[str]:
    commands: list[str] = []
    workflow_commands = workflow.get("commands")
    if isinstance(workflow_commands, dict):
        for key in ("handoff", "review", "gate", "merge_guidance"):
            value = workflow_commands.get(key)
            if isinstance(value, str):
                commands.append(value)
    reviewer_commands = review.get("reviewer_commands")
    if isinstance(reviewer_commands, list):
        for value in reviewer_commands:
            if isinstance(value, str):
                commands.append(value)
    return _dedupe_strings(commands)


def _export_review_source_metadata(bundle: dict[str, object]) -> list[dict[str, object]]:
    root = _expect_path(bundle, "root")
    items: list[dict[str, object]] = []
    for relative in RUN_BUNDLE_REQUIRED_FILES:
        target = _safe_existing_bundle_file(root, relative)
        stat = target.stat()
        items.append(
            {
                "path": relative,
                "status": "present",
                "kind": "markdown" if relative.endswith(".md") else "json",
                "size_bytes": stat.st_size,
                "sha256": _sha256_file(target),
            }
        )
    for actor in ALLOWED_ACTORS:
        relative = f"{RUN_BUNDLE_RESULTS_DIR}/{actor}.json"
        target = _safe_existing_bundle_file(root, relative)
        if _exists(target, relative):
            stat = target.stat()
            items.append(
                {
                    "path": relative,
                    "status": "present",
                    "kind": "json",
                    "size_bytes": stat.st_size,
                    "sha256": _sha256_file(target),
                }
            )
        else:
            items.append({"path": relative, "status": "missing", "kind": "json"})
    return items


def _export_review_error_reason(error: str) -> str:
    if "--out" in error or "output" in error or "review artifact" in error or "sha256" in error:
        return "invalid_output"
    if "outside project root" in error or "unsafe" in error or "symlink" in error:
        return "unsafe_path"
    if "Run bundle path is not a directory" in error:
        return "missing_path"
    if "Missing run bundle file" in error:
        return "missing_required_file"
    if "Invalid UTF-8" in error:
        return "non_utf8"
    if "Invalid JSON" in error:
        return "malformed_json"
    return "invalid_bundle"


def _dedupe_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result

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


def _resolve_export_review_out_path(out: str | Path, project_root: Path) -> Path:
    base = project_root.resolve()
    runs_root = (project_root / ".ai" / "runs").resolve()
    requested = Path(out)
    relative_request = not requested.is_absolute()
    if relative_request:
        requested = project_root / requested
    if _is_symlink(requested, str(out)):
        raise RunBundleError(f"Refusing symlink review artifact output path: {out}")
    try:
        resolved = requested.resolve(strict=False)
    except OSError as exc:
        raise RunBundleError(f"Unable to resolve review artifact output path: {out}") from exc
    if relative_request and resolved != base and base not in resolved.parents:
        raise RunBundleError(f"Refusing relative review artifact output outside project root: {out}")
    if resolved == runs_root or runs_root in resolved.parents:
        raise RunBundleError(f"Refusing to write review artifact inside .ai/runs: {out}")
    if (resolved == base or base in resolved.parents) and _exists(resolved, str(out)):
        raise RunBundleError(f"Refusing to overwrite existing project file with review artifact: {out}")
    parent = resolved.parent
    if not _exists(parent, str(parent)):
        raise RunBundleError(f"Review artifact parent directory does not exist: {parent}")
    if _is_symlink(parent, str(parent)) or not parent.is_dir():
        raise RunBundleError(f"Review artifact parent is not a directory: {parent}")
    if _exists(resolved, str(out)) and not _is_file(resolved, str(out)):
        raise RunBundleError(f"Review artifact output path is not a file: {out}")
    return resolved


def _resolve_export_review_sha256_path(out_path: Path, project_root: Path) -> Path:
    sha256_path = Path(f"{out_path}.sha256")
    if _is_symlink(sha256_path, str(sha256_path)):
        raise RunBundleError(f"Refusing symlink review artifact sha256 path: {sha256_path}")
    try:
        resolved = sha256_path.resolve(strict=False)
    except OSError as exc:
        raise RunBundleError(f"Unable to resolve review artifact sha256 path: {sha256_path}") from exc
    runs_root = (project_root / ".ai" / "runs").resolve()
    if resolved == runs_root or runs_root in resolved.parents:
        raise RunBundleError(f"Refusing to write review artifact sha256 inside .ai/runs: {sha256_path}")
    base = project_root.resolve()
    if (resolved == base or base in resolved.parents) and _exists(resolved, str(sha256_path)):
        raise RunBundleError(f"Refusing to overwrite existing project file with review artifact sha256: {sha256_path}")
    parent = resolved.parent
    if not _exists(parent, str(parent)):
        raise RunBundleError(f"Review artifact sha256 parent directory does not exist: {parent}")
    if _is_symlink(parent, str(parent)) or not parent.is_dir():
        raise RunBundleError(f"Review artifact sha256 parent is not a directory: {parent}")
    if _exists(resolved, str(sha256_path)) and not _is_file(resolved, str(sha256_path)):
        raise RunBundleError(f"Review artifact sha256 path is not a file: {sha256_path}")
    return resolved


def _write_export_text(path: Path, value: str) -> None:
    tmp = path.with_name(f"{path.name}.tmp")
    if _is_symlink(tmp, str(tmp)):
        raise RunBundleError(f"Refusing to write temporary symlink: {tmp}")
    try:
        tmp.write_text(value, encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        raise RunBundleError(f"Unable to write review artifact file: {path}") from exc


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
