# Framework Runtime WP6 Local Execution Loop V1 Report

marker: FRAMEWORK_RUNTIME_WP6_LOCAL_EXECUTION_LOOP_V1_COMPLETE

branch: framework/runtime-wp6-local-execution-loop-v1
baseline HEAD: 5ef4772f001db181b5c2af96dc4a22f5c0ca4cbb
commit HEAD: final pushed branch HEAD; exact hash is reported in the final response
pushed: yes, after final push step

## Changed files

- README.md
- agent_office/cli.py
- agent_office/framework_runtime.py
- tests/test_framework_runtime.py
- FRAMEWORK_RUNTIME_WP6_LOCAL_EXECUTION_LOOP_V1_REPORT.md

## Local Execution Loop Description

WP6 adds `framework-runtime execution` with local-only commands:

- `status`: preview or show the persisted deterministic execution-loop state for one workspace/run/goal.
- `run-once`: create or load execution-loop state and advance at most one WP5 orchestration dispatch.
- `loop`: repeat `run-once` until terminal state or `--max-iterations` is reached.

The loop consumes the WP5 orchestration plan and uses existing WP2/WP4 primitives for deterministic local job creation and deterministic worker-result intake. It does not execute external workers, providers, adapters, daemons, queues, shells, or network calls.

## State Transition Model

The persisted state file is:

```text
.ai/workspaces/<workspace-id>/runs/<run-id>/execution_loops/<goal-id>.json
```

Explicit states:

- `planned`: deterministic execution-loop state prepared from the orchestration plan.
- `running`: local loop has started and may have pending dispatches.
- `succeeded`: every planned dispatch has succeeded locally and its task is accepted.
- `blocked`: the underlying orchestration plan has blocked dependencies or unsupported task state.
- `failed`: reserved terminal state for future explicit local failure handling; WP6 does not use provider failures because no provider execution exists.

Normal transition path: `planned -> running -> succeeded`.
Blocked transition path: `planned -> blocked`.

Per-dispatch behavior:

- job id is the task id.
- `run-once` advances at most one pending dispatch.
- deterministic worker-result intake advances the job to `succeeded`.
- the task graph status advances to `accepted` after the local worker result exists.
- `loop` is only a bounded repeat of `run-once`; it does not start a daemon or background worker.

## Deterministic Guarantees

- Same workspace/run/goal/task graph input yields the same initial execution-loop state.
- Dispatch order comes from the WP5 orchestration plan and task graph dependency ordering.
- No wall-clock timestamps are added; transition stamps are stable sequence labels.
- `run-once` has a fixed one-dispatch ceiling.
- Re-running after terminal state is idempotent and returns `progressed=false`.
- No `.env` reads, environment printing, provider calls, network calls, external adapter calls, daemon starts, background worker starts, message queues, or real worker connections were added.

## Evidence/Event Behavior

WP6 records execution-loop state in the run-local store and exposes it through `framework-runtime status` and `framework-runtime evidence`.

Runtime events appended by execution-loop commands:

- `execution_loop.planned`
- `execution_loop.started`
- `execution_loop.task_dispatched`
- `execution_loop.task_succeeded`
- `execution_loop.succeeded`
- `execution_loop.blocked` when validation blocks execution

Evidence refs include the task graph, execution-loop state, local job files, deterministic worker-result files, and event log.

## Validation Results

Passed on final code state:

- `python3 -m compileall agent_office tests`: passed
- `python3 -m unittest`: passed, 540 tests OK
- `python3 -m unittest discover -s tests -p 'test_*.py'`: passed, 540 tests OK
- `python3 -m unittest tests.test_framework_runtime`: passed, 27 tests OK
- `python3 -m agent_office doctor --adapters`: passed, all mock adapters ok
- `./scripts/verify.sh`: passed, verify ok
- `./scripts/smoke-test.sh P6-PROFILES`: passed, smoke test ok
- `python3 -m agent_office run-staged P6-PROFILES --dry-run --reset`: passed
- `git diff --check`: passed

CLI smoke passed:

- `python3 -m agent_office framework-runtime --help`
- `python3 -m agent_office framework-runtime execution --help`
- `python3 -m agent_office framework-runtime execution run-once --help`
- `python3 -m agent_office framework-runtime execution loop --help`
- `python3 -m agent_office framework-runtime execution status --help`
- `python3 -m agent_office framework-runtime orchestration --help`
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
- no external execution
- WP7 not implemented
- `.env` was not read
- environment variables were not printed
- default branch was not modified
- no tag was created
- historical untracked artifacts were not cleaned

FRAMEWORK_RUNTIME_WP6_LOCAL_EXECUTION_LOOP_V1_COMPLETE
