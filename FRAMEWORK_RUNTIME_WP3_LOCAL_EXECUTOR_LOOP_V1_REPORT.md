# Framework Runtime WP3 Local Executor Loop V1 Report

marker: FRAMEWORK_RUNTIME_WP3_LOCAL_EXECUTOR_LOOP_V1_COMPLETE

branch: framework/runtime-wp3-local-executor-loop-v1
baseline HEAD: 38b810069a84c475440f032675409d78fa542dea
commit HEAD: recorded in final response after commit creation and push; this report is included in that pushed HEAD.
pushed: yes, after final push step

## Changed files

- README.md
- agent_office/cli.py
- agent_office/framework_runtime.py
- tests/test_framework_runtime.py
- FRAMEWORK_RUNTIME_WP3_LOCAL_EXECUTOR_LOOP_V1_REPORT.md

## Implemented CLI

Existing commands preserved:

- framework-runtime job create
- framework-runtime job list
- framework-runtime job show
- framework-runtime job cancel
- framework-runtime job fail
- framework-runtime resume
- framework-runtime evidence

New WP3 executor commands:

- framework-runtime executor run-once
- framework-runtime executor loop
- framework-runtime executor status

## Local Executor State Transition Contract

WP3 extends the WP2 local job lifecycle with a deterministic local stub executor named local_executor_stub. Jobs remain run-local JSON records under .ai/workspaces/<workspace-id>/runs/<run-id>/jobs/<job-id>.json.

The executor only reads local runtime state and writes local runtime state. It does not call providers, Codex, Claude, external adapters, network services, or background daemons.

State transitions:

- create keeps the WP2 initial state: pending.
- executor run-once chooses an existing running job first, otherwise the first pending job by sorted job id.
- pending jobs transition pending -> running using action executor_start.
- default deterministic outcome transitions running -> succeeded using action executor_succeeded.
- metadata executor_outcome=failed transitions running -> failed using action executor_failed.
- cancelled, failed, and succeeded are terminal and are not progressed by the executor.
- loop repeats run-once until no running/pending jobs remain or --max-iterations is reached.
- cancel/fail commands from WP2 remain available only from pending/running and reject terminal jobs.

The requested queued/running family is preserved through the existing WP2 pending/running/succeeded/failed/cancelled contract; no new queued alias was added because WP2 uses pending as the queued state.

## Evidence/Event Files Touched Or Generated

Runtime state paths used by WP3:

- .ai/workspaces/<workspace-id>/runs/<run-id>/jobs/<job-id>.json
- .ai/workspaces/<workspace-id>/runs/<run-id>/executor_results/<job-id>.json
- .ai/workspaces/<workspace-id>/runs/<run-id>/events.jsonl
- .ai/workspaces/<workspace-id>/runs/<run-id>/evidence/framework_runtime_evidence.json
- .ai/workspaces/<workspace-id>/runs/<run-id>/evidence/framework_runtime_evidence.text

New event types:

- executor.job_started
- executor.job_succeeded
- executor.job_failed

Evidence export now includes jobs and executor_results inside the existing framework_runtime_evidence bundle status payload.

## Validation Commands And Results

Passed on final code state:

- python3 -m compileall agent_office tests: passed
- python3 -m unittest: passed, 529 tests OK
- python3 -m unittest discover -s tests -p 'test_*.py': passed, 529 tests OK
- python3 -m unittest tests.test_framework_runtime: passed, 16 tests OK
- python3 -m agent_office doctor --adapters: passed, all mock adapters ok
- ./scripts/verify.sh: passed, verify ok
- ./scripts/smoke-test.sh P6-PROFILES: passed, smoke test ok
- python3 -m agent_office run-staged P6-PROFILES --dry-run --reset: passed
- git diff --check: passed

WP3 CLI smoke passed:

- python3 -m agent_office framework-runtime --help
- python3 -m agent_office framework-runtime job --help
- python3 -m agent_office framework-runtime executor --help
- python3 -m agent_office framework-runtime executor run-once --help
- python3 -m agent_office framework-runtime executor loop --help
- python3 -m agent_office framework-runtime executor status --help
- python3 -m agent_office framework-runtime resume --help
- python3 -m agent_office framework-runtime evidence --help

## Safety Confirmation

- .env was not read.
- Environment variables were not printed.
- No real provider worker connected.
- No real Codex worker connected.
- No real Claude worker connected.
- No external runtime/adapter behavior was triggered by WP3 executor code.
- No daemon, background service, or resident worker was started.
- No network behavior was added.
- The default branch was not changed.
- No tag was created.
- Historical untracked artifacts were left untouched.
- WP4 was not implemented.

FRAMEWORK_RUNTIME_WP3_LOCAL_EXECUTOR_LOOP_V1_COMPLETE
