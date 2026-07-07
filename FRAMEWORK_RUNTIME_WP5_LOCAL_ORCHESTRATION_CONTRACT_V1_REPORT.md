# Framework Runtime WP5 Local Orchestration Contract V1 Report

marker: FRAMEWORK_RUNTIME_WP5_LOCAL_ORCHESTRATION_CONTRACT_V1_COMPLETE

branch: framework/runtime-wp5-local-orchestration-contract-v1
baseline HEAD: d7ce0f382bc1910a4d1dded3fc6d04a6f79b858a
commit HEAD: final pushed branch HEAD; exact hash is reported in the final response
pushed: yes, after final push step

## Changed files

- README.md
- agent_office/cli.py
- agent_office/framework_runtime.py
- tests/test_framework_runtime.py
- FRAMEWORK_RUNTIME_WP5_LOCAL_ORCHESTRATION_CONTRACT_V1_REPORT.md

## Orchestration Contract Description

WP5 adds `framework-runtime orchestration` with local-only commands:

- `plan`: read the existing run and task graph and emit a deterministic orchestration request/plan contract.
- `show`: show persisted orchestration state when present, otherwise show the deterministic plan view.
- `validate`: validate dependency readiness and blocked tasks without execution.
- `run-local`: execute only local orchestration glue by creating deterministic run-local jobs, intaking deterministic local worker results, advancing task graph state, and writing orchestration evidence.

The contract uses existing WP2/WP3/WP4 primitives. It does not connect to any real worker, provider, daemon, queue, or external runtime.

## State Transition Model

The persisted state file is:

```text
.ai/workspaces/<workspace-id>/runs/<run-id>/orchestrations/<goal-id>.json
```

Explicit states:

- `planned`: deterministic plan prepared.
- `running`: `run-local` started local glue work.
- `succeeded`: all planned dispatches created local jobs, received deterministic worker results, and moved tasks to `accepted`.
- `blocked`: validation found blocked dependencies or unsupported task state before execution.
- `failed`: reserved explicit terminal state for future local failure handling; WP5 does not use it for provider failures because no provider execution exists.

Normal transition path: `planned -> running -> succeeded`.
Blocked transition path: `planned -> blocked`.

Job/task glue per dispatch:

- job id is the task id.
- job starts as WP2 `pending`.
- WP4 deterministic worker intake advances it to `succeeded`.
- task graph status advances to `accepted` after local worker result intake.

## Deterministic Guarantees

- Same workspace/run/goal/task graph input yields the same `plan` payload.
- Ordering is derived from task graph order while requiring dependencies to be accepted before dependent dispatch.
- No wall-clock timestamps are added; transition stamps are stable sequence labels.
- No `.env` reads, environment printing, provider calls, network calls, external adapter calls, daemon starts, or background worker starts were added.
- Re-running `run-local` after terminal persisted state is idempotent and reports `progressed=false`.

## Evidence/Event Behavior

WP5 records orchestration state in the run-local store and exposes it through `framework-runtime status` and `framework-runtime evidence`.

Runtime events appended by `run-local`:

- `orchestration.planned`
- `orchestration.started`
- `orchestration.task_dispatched`
- `orchestration.task_succeeded`
- `orchestration.succeeded`
- `orchestration.blocked` when validation blocks execution

Evidence refs include the task graph, orchestration state, local job files, deterministic worker-result files, and event log.

## Validation Results

Passed on final code state:

- `python3 -m compileall agent_office tests`: passed
- `python3 -m unittest`: passed, 536 tests OK
- `python3 -m unittest discover -s tests -p 'test_*.py'`: passed, 536 tests OK
- `python3 -m unittest tests.test_framework_runtime`: passed, 23 tests OK
- `python3 -m agent_office doctor --adapters`: passed, all mock adapters ok
- `./scripts/verify.sh`: passed, verify ok
- `./scripts/smoke-test.sh P6-PROFILES`: passed, smoke test ok
- `python3 -m agent_office run-staged P6-PROFILES --dry-run --reset`: passed
- `git diff --check`: passed

CLI smoke passed:

- `python3 -m agent_office framework-runtime --help`
- `python3 -m agent_office framework-runtime orchestration --help`
- `python3 -m agent_office framework-runtime orchestration plan --help`
- `python3 -m agent_office framework-runtime orchestration show --help`
- `python3 -m agent_office framework-runtime orchestration validate --help`
- `python3 -m agent_office framework-runtime orchestration run-local --help`
- `python3 -m agent_office framework-runtime executor --help`
- `python3 -m agent_office framework-runtime worker --help`
- `python3 -m agent_office framework-runtime evidence --help`

## Safety Confirmation

- no real Codex worker
- no real Claude worker
- no provider integration
- no daemon/background execution
- no network behavior
- no message queue
- no external orchestration
- WP6 not implemented
- `.env` was not read
- environment variables were not printed
- default branch was not modified
- no tag was created
- historical untracked artifacts were not cleaned

FRAMEWORK_RUNTIME_WP5_LOCAL_ORCHESTRATION_CONTRACT_V1_COMPLETE
