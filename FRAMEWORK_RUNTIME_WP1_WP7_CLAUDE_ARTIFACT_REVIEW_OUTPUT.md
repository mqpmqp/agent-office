# AgentOffice Framework Runtime WP1-WP7 Artifact-Based Review

verdict: CONDITIONAL PASS

## Artifact-Based Caveat

This is an artifact-based static review of `framework_runtime_wp1_wp7_review_artifact_bundle.tar.gz`. I reviewed the bundle contents: README, reports, source snapshots, history, and validation artifacts. I did not perform an execution-environment review and do not treat validation files as proof that I personally ran the project commands.

Important validation caveat: the artifact-generation handoff records that the first `python3 -m unittest` run hung and was terminated before bundle generation continued. The bundled `validation/unittest.txt` contains `Ran 544 tests in 287.914s` and `OK`, but this review should not flatten the validation story into a clean pass. `validation/unittest_discovery.txt` contains only progress dots and no final unittest summary, so discovery validation is incomplete as an artifact.

## Architecture Assessment

WP1-WP7 mostly form a coherent local framework-runtime substrate. The main runtime path is:

- WP2 job lifecycle stores run-local jobs under `.ai/workspaces/<workspace-id>/runs/<run-id>/jobs/<job-id>.json` with deterministic transition stamps.
- WP4 worker result intake consumes local/static worker-result payloads, transitions jobs to `succeeded` or `failed`, records event log entries, and adds evidence refs.
- WP5 orchestration plans from the task graph and can glue local jobs, worker results, task acceptance, events, and evidence.
- WP6 execution loop turns the WP5 plan into a bounded run-once/loop state machine that advances one dispatch at a time.
- WP7 policy gate is correctly placed in the WP6 execution-loop dispatch path before local job creation and worker-result intake. Deny paths record `policy_decisions`, emit `policy.denied` and `execution_loop.policy_denied`, fail the local job, reject the task, and do not create a worker result.

The architecture is intentionally local/static and deterministic. The boundary data repeatedly marks `provider_calls`, `network_calls`, `env_reads`, `external_worker_calls`, real Codex, and real Claude as false. This is consistent across the reviewed runtime payloads, worker adapter contract, capability contract, status, evidence export, and tests.

The main architectural concern is boundary scope, not the core WP5-WP7 path. The older `framework-runtime executor` and legacy `framework-runtime dispatch/resume` paths still exist beside the WP6/WP7 execution-loop path. They remain local stubs, but they are not under the WP7 capability-policy gate. That is acceptable only if documented as legacy/local-only compatibility, not as the future scheduler execution substrate.

There is also a parallel older `runtime`/`runtime_foundation.py` model with different state vocabulary (`pending/completed/failed/blocked`, `created/running/completed`) versus framework-runtime vocabulary (`created/accepted/rejected/skipped`, `pending/running/succeeded/failed/cancelled`). This is not a WP1-WP7 blocker because WP1 explicitly kept the broader runtime namespace separate, but it is real WP8 design debt if scheduler abstractions are not pinned to the framework-runtime contracts.

## Files Reviewed

- `README_FOR_CLAUDE.md`
- `reports/FRAMEWORK_RUNTIME_TRUNK_BATCH_REVIEW_FIX_REPORT.md`
- `reports/FRAMEWORK_RUNTIME_WP1_BASELINE_CONSOLIDATION_REPORT.md`
- `reports/FRAMEWORK_RUNTIME_WP2_JOB_LIFECYCLE_CORE_REPORT.md`
- `reports/FRAMEWORK_RUNTIME_WP3_LOCAL_EXECUTOR_LOOP_V1_REPORT.md`
- `reports/FRAMEWORK_RUNTIME_WP4_WORKER_ADAPTER_CONTRACT_RESULT_INTAKE_REPORT.md`
- `reports/FRAMEWORK_RUNTIME_WP5_LOCAL_ORCHESTRATION_CONTRACT_V1_REPORT.md`
- `reports/FRAMEWORK_RUNTIME_WP6_LOCAL_EXECUTION_LOOP_V1_REPORT.md`
- `reports/FRAMEWORK_RUNTIME_WP7_EXECUTION_POLICY_CAPABILITY_BOUNDARY_V1_REPORT.md`
- `files/agent_office/framework_runtime.py`
- `files/agent_office/framework_status.py`
- `files/agent_office/framework_types.py`
- `files/agent_office/orchestration.py`
- `files/agent_office/runtime_events.py`
- `files/agent_office/runtime_foundation.py`
- `files/tests/test_framework_runtime.py`
- `files/tests/test_framework_status.py`
- `files/tests/test_local_multi_agent_runtime_cli.py`
- `files/tests/test_orchestration_cli.py`
- `files/tests/test_runtime_events.py`
- `files/tests/test_runtime_foundation_cli.py`
- `history/framework_runtime_files.txt`
- `history/framework_runtime_history.txt`
- `diff/current_diff_check.txt`
- `diff/runtime_history_stat.txt`

Artifact completeness note: `history/framework_runtime_files.txt` shows `agent_office/cli.py` and `README.md` changed across the WP series, but the `files/` snapshot does not include them. CLI behavior is therefore reviewed indirectly through tests and reports, not direct CLI source inspection.

## Validation Artifacts Reviewed

- `validation/compileall.txt`: compileall listed `agent_office`, `agent_office/adapters`, `agent_office/runtime_kernel`, `tests`, and fixture dirs without visible failure text.
- `validation/doctor_adapters.txt`: mock adapters for gemini, codex, grok, claude show `status ok`.
- `validation/unittest.txt`: records `Ran 544 tests in 287.914s` and `OK`, but must be read together with the external artifact-generation caveat that the first unittest run hung/was terminated.
- `validation/unittest_discovery.txt`: incomplete artifact; only dots, no final summary.
- `validation/verify.txt`: records `verify ok` for the demo workflow.
- `diff/current_diff_check.txt`: empty, indicating no diff-check output in the artifact.

## Blocker Findings

None for a conditional architecture pass within the stated WP1-WP7 local/static scope.

## Major Findings

1. Policy gate does not cover all framework-runtime execution-like surfaces.

`execution_loop_run_once_payload` gates dispatch through `policy_decision_payload` before creating/intaking worker results. However, legacy `executor_run_once_payload`, `executor_loop_payload`, `dispatch_payload`, and `resume_payload` can still progress local runtime state without writing policy decisions. They appear intentionally local-only, but WP7 is titled `Execution Policy + Capability Boundary`; future readers may assume all execution paths are gated. Before WP8, either route scheduler work exclusively through WP6/WP7 execution-loop APIs or explicitly label older executor/dispatch/resume paths as legacy local stubs outside the policy boundary.

2. Artifact source snapshot omits CLI and README files that reports say changed.

The bundle includes tests and runtime core snapshots, but not `agent_office/cli.py` or `README.md`. Because WP5-WP7 add user-facing commands and flags, direct review of CLI parser wiring, default capability handling, and help text is incomplete. Tests strongly imply the wiring exists, but artifact-based architecture review should include the source of every changed runtime command surface.

3. Validation evidence is mixed and should not be treated as clean green.

The bundle contains an `OK` unittest summary, but the artifact-generation note says the first unittest run hung and was terminated. The discovery artifact lacks a final summary. This is not an architecture blocker, but it is a release-gate concern: the review packet should preserve the nuance and ideally include a clean bounded rerun or a timeout-labeled incomplete result.

4. Two runtime vocabularies remain adjacent.

`framework_runtime.py` uses `pending/running/succeeded/failed/cancelled` for jobs and `accepted/rejected/skipped` as terminal task states. `runtime_foundation.py` uses older `pending/completed/failed/blocked` task states and `created/running/completed/failed/cancelled` job states. The reports say the broader runtime namespace remains separate, so this is not an immediate defect. It is, however, a scheduler-readiness risk unless WP8 names the canonical substrate and avoids crossing these models implicitly.

## Minor Findings

1. Runtime events are useful but sparse.

`runtime_events.py` appends deterministic event IDs and event types, but event payloads and evidence refs are empty. The state files and evidence bundle compensate for now. For scheduler/debug readiness, richer event payloads would reduce replay ambiguity.

2. Policy decisions are static declarations only.

This is aligned with WP7 V1, but there is no role/user/workspace permission dimension yet. That is fine for local-only V1; it should be called out as intentionally not sufficient for real provider execution.

3. Orchestration and execution failure semantics are reserved more than implemented.

Both WP5 and WP6 include `failed` in the state model, but most real local failure paths become `blocked` or deterministic worker success. That is acceptable for V1 but should be tightened before adding non-stub scheduler behavior.

4. Discovery validation artifact is truncated/incomplete.

`unittest_discovery.txt` has dots only. Artifact consumers cannot determine count, duration, or final result from that file alone.

## Safety Risks

- No evidence of implicit real provider/runtime/adapter execution in the reviewed WP5-WP7 primary path.
- Worker adapter contract correctly declares deterministic local stub behavior and `execution_enabled: false` for worker adapters.
- Denied WP7 execution creates no worker result and emits denial events, which is the right fail-closed behavior.
- The main bypass risk is semantic: older local stub surfaces can progress state without policy decisions. They are not external-execution risks today, but they can become a capability-boundary bypass if WP8 scheduler or future adapters call them by habit.
- The artifact does not include direct CLI source, so argument defaults and command routing cannot be fully audited from source snapshots.

## Regression Risks

- Tightening policy gates globally could break existing tests or users of `framework-runtime executor`, `dispatch`, and `resume` unless migration is staged.
- Changing task/job vocabulary without a compatibility map could break evidence/status consumers.
- Adding WP8 scheduler on top of `runtime_foundation.py` instead of `framework_runtime.py` would fork the runtime substrate.
- Treating incomplete validation as fully passed could mask future hangs in test discovery or full unittest runs.

## WP8 Recommendation

Proceed to WP8 only as a conditional next step. WP8 scheduler should build on the WP6/WP7 execution-loop abstraction, not on legacy executor or old runtime-foundation surfaces. The scheduler contract should require:

- explicit capability id per dispatch,
- policy decision before job creation or worker result intake,
- bounded tick/run-once semantics first,
- no daemon or background worker until a later explicit WP,
- scheduler state stored run-locally like `execution_loops/`,
- evidence refs for policy decisions, jobs, worker results, and event logs,
- a clear mapping from scheduler states to existing execution-loop/job/task states.

Do not add real provider negotiation in WP8. If provider negotiation is planned, make it a later WP after policy primitives grow beyond static capability declarations.

## Minimal Delta Fixes If Required

1. Generate a supplemental review bundle that includes `agent_office/cli.py`, `README.md`, and any source files listed in history as changed for WP1-WP7.
2. Add or document an explicit boundary statement: WP7 policy gates `framework-runtime execution`, while legacy `executor`, `dispatch`, and `resume` remain local-only compatibility paths and are not scheduler targets.
3. Add focused tests that assert scheduler-intended APIs always write policy decisions before worker result intake, and that denied capability leaves no worker result.
4. Add a state vocabulary note/table for WP8: task states, job states, orchestration states, execution-loop states, and how old `runtime` namespace states differ.
5. Recreate validation artifacts with bounded timeouts and complete summaries, especially for `python3 -m unittest discover -s tests -p 'test_*.py'`.

## Confidence Level

Medium-high for architecture of the primary WP5-WP7 runtime path.

Medium for CLI and release readiness because the artifact omits `agent_office/cli.py` and README snapshots, and validation artifacts include a hang/termination caveat plus incomplete discovery output.

FRAMEWORK_RUNTIME_WP1_WP7_ARTIFACT_REVIEW_COMPLETE
