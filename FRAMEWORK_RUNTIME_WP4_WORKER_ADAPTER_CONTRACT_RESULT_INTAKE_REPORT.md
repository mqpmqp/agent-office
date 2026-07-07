# Framework Runtime WP4 Worker Adapter Contract / Result Intake Report

marker: FRAMEWORK_RUNTIME_WP4_WORKER_ADAPTER_CONTRACT_RESULT_INTAKE_COMPLETE

branch: framework/runtime-wp4-worker-adapter-contract-result-intake
baseline HEAD: eb4781d51a9dd4b7484a8f83340ba8eb94dc9d1a
commit HEAD: recorded in final response after commit creation and push; this report is included in that pushed HEAD.
pushed: yes, after final push step

## Changed files

- README.md
- agent_office/cli.py
- agent_office/framework_runtime.py
- tests/test_framework_runtime.py
- FRAMEWORK_RUNTIME_WP4_WORKER_ADAPTER_CONTRACT_RESULT_INTAKE_REPORT.md

## Implemented CLI

Existing commands preserved:

- framework-runtime job create/list/show/cancel/fail
- framework-runtime executor run-once/loop/status
- framework-runtime resume
- framework-runtime evidence

New WP4 worker commands:

- framework-runtime worker adapters
- framework-runtime worker result-intake
- framework-runtime worker result-show

## Worker Adapter Contract

WP4 adds a local/static worker adapter descriptor for `local_worker_adapter_stub`:

- mode: deterministic_local_stub
- input_kind: agentoffice.framework_runtime_job
- output_kind: agentoffice.framework_runtime_worker_result
- supported_result_statuses: failed, succeeded
- execution_enabled: false
- result_intake_enabled: true
- reads_env / prints_env / network_calls / provider_calls / external_runtime_calls: false
- codex_worker_connected / claude_worker_connected: false

The legacy packet worker contract remains available through `framework-runtime workers`; no real worker execution was added.

## Worker Result Intake Contract

`framework-runtime worker result-intake` accepts only deterministic local payload fields:

- workspace id
- run id
- job id
- adapter id, default `local_worker_adapter_stub`
- result status: succeeded or failed
- summary
- optional local evidence references

It writes `.ai/workspaces/<workspace-id>/runs/<run-id>/worker_results/<job-id>.json` and rejects missing jobs, terminal/cancelled jobs, unsupported adapters, empty summaries, duplicate terminal intake, and invalid result statuses.

## Job State Transition Behavior

- pending/running + succeeded result -> succeeded using transition action `worker_result_succeeded`
- pending/running + failed result -> failed using transition action `worker_result_failed`
- succeeded/failed/cancelled jobs are terminal and reject result intake
- job evidence refs are updated with worker result refs, event log refs, and supplied local evidence refs

## Evidence/Event Files Touched Or Generated

Runtime state paths used by WP4:

- .ai/workspaces/<workspace-id>/runs/<run-id>/jobs/<job-id>.json
- .ai/workspaces/<workspace-id>/runs/<run-id>/worker_results/<job-id>.json
- .ai/workspaces/<workspace-id>/runs/<run-id>/events.jsonl
- .ai/workspaces/<workspace-id>/runs/<run-id>/evidence/framework_runtime_evidence.json
- .ai/workspaces/<workspace-id>/runs/<run-id>/evidence/framework_runtime_evidence.text

New event types:

- worker_result.received
- worker_result.succeeded
- worker_result.failed

Evidence export now includes worker_results and the local worker adapter contract inside the existing framework_runtime_evidence bundle.

## Validation Commands And Results

Passed on final code state:

- python3 -m compileall agent_office tests: passed
- python3 -m unittest: passed, 532 tests OK
- python3 -m unittest discover -s tests -p 'test_*.py': passed, 532 tests OK
- python3 -m unittest tests.test_framework_runtime: passed, 19 tests OK
- python3 -m agent_office doctor --adapters: passed
- ./scripts/verify.sh: passed
- ./scripts/smoke-test.sh P6-PROFILES: passed
- python3 -m agent_office run-staged P6-PROFILES --dry-run --reset: passed
- git diff --check: passed

WP4 CLI smoke passed:

- python3 -m agent_office framework-runtime --help
- python3 -m agent_office framework-runtime job --help
- python3 -m agent_office framework-runtime executor --help
- python3 -m agent_office framework-runtime worker --help
- python3 -m agent_office framework-runtime worker adapters --help
- python3 -m agent_office framework-runtime worker result-intake --help
- python3 -m agent_office framework-runtime resume --help
- python3 -m agent_office framework-runtime evidence --help

## Safety Confirmation

- .env was not read.
- Environment variables were not printed.
- No real provider worker connected.
- No real Codex worker connected.
- No real Claude worker connected.
- No external runtime/adapter behavior was triggered by WP4 code.
- No daemon, background service, or resident worker was started.
- No network behavior was added.
- No real worker execution was implemented.
- The default branch was not changed.
- No tag was created.
- Historical untracked artifacts were left untouched.
- WP5 was not implemented.

FRAMEWORK_RUNTIME_WP4_WORKER_ADAPTER_CONTRACT_RESULT_INTAKE_COMPLETE
