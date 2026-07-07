# Framework Runtime WP7 Execution Policy + Capability Boundary V1 Report

marker: FRAMEWORK_RUNTIME_WP7_EXECUTION_POLICY_CAPABILITY_BOUNDARY_V1_COMPLETE

branch: framework/runtime-wp7-execution-policy-capability-boundary-v1
baseline HEAD: d132840f1927e446c18c20613ddde80bb38344b4
commit HEAD: final pushed branch HEAD; exact hash is reported in the final response
pushed: yes, after final push step

## Changed files

- README.md
- agent_office/cli.py
- agent_office/framework_runtime.py
- tests/test_framework_runtime.py
- FRAMEWORK_RUNTIME_WP7_EXECUTION_POLICY_CAPABILITY_BOUNDARY_V1_REPORT.md

## Implemented Commands And Contracts

WP7 adds a local/static capability and policy contract:

- `framework-runtime policy capabilities`: shows deterministic capability declarations.
- `framework-runtime policy check --capability-id <id>`: checks one capability without executing anything.
- `framework-runtime execution run-once --capability-id <id>`: checks policy before dispatching one local execution-loop task.
- `framework-runtime execution loop --capability-id <id>`: repeats the same gated run-once behavior.

Capability declaration fields are intentionally small: `capability_id`, `worker`, `action`, `status`, `allowed`, `reason_code`, and static safety flags. Local deterministic capabilities are `local-only`; real provider/Codex/Claude execution capabilities are `forbidden`; unknown capabilities are denied with `UNKNOWN_CAPABILITY`.

## Policy Gate Behavior

Allowed path:

- policy decision is written under `.ai/workspaces/<workspace-id>/runs/<run-id>/policy_decisions/<job-id>.json`.
- `policy.allowed` event is appended.
- execution loop continues to local job creation and deterministic worker-result intake.
- task advances to `accepted`.

Denied path:

- policy decision is written under `policy_decisions/`.
- `policy.denied` and `execution_loop.policy_denied` events are appended.
- a local job is created or updated and moved to terminal `failed` with transition `policy_denied`.
- task advances to terminal `rejected`.
- no worker result is created.
- no real provider/runtime/adapter/model/API/network behavior is triggered.

## Runtime Evidence

Framework runtime status/evidence now includes `policy_decisions`. The evidence bundle also includes the local capability contract so reviewers can inspect both declarations and decisions.

## Validation Results

Passed on final code state:

- `python3 -m compileall agent_office tests`: passed
- `python3 -m unittest`: passed, 544 tests OK
- `python3 -m unittest discover -s tests -p 'test_*.py'`: passed, 544 tests OK
- `python3 -m unittest tests.test_framework_runtime`: passed, 31 tests OK
- `python3 -m agent_office doctor --adapters`: passed, all mock adapters ok
- `./scripts/verify.sh`: passed, verify ok
- `./scripts/smoke-test.sh P6-PROFILES`: passed, smoke test ok
- `python3 -m agent_office run-staged P6-PROFILES --dry-run --reset`: passed
- `git diff --check`: passed

WP7 focused CLI smoke passed:

- `python3 -m agent_office framework-runtime policy --help`
- `python3 -m agent_office framework-runtime policy capabilities --help`
- `python3 -m agent_office framework-runtime policy check --help`
- `python3 -m agent_office framework-runtime policy capabilities --json`
- `python3 -m agent_office framework-runtime policy check --capability-id local.execution.dispatch --json`
- `python3 -m agent_office framework-runtime policy check --capability-id external.provider.execute --json`
- allowed local execution smoke with `--capability-id local.execution.dispatch`
- denied forbidden capability smoke with `--capability-id external.provider.execute`

## Safety Boundaries

- no `.env` reads
- no environment variable printing
- no real Codex worker
- no real Claude worker
- no provider/model/API integration
- no daemon/background execution
- no network behavior
- no message queue
- no external orchestration or execution
- default branch not modified
- no merge
- no tag
- historical untracked artifacts not cleaned

## Known Limitations

- Capability policy is intentionally static and local-only.
- No user/role-based permission system is implemented.
- Denied execution stops the current local execution loop by moving it to `blocked`.
- WP8+ external execution policy negotiation is not implemented.

FRAMEWORK_RUNTIME_WP7_EXECUTION_POLICY_CAPABILITY_BOUNDARY_V1_COMPLETE
