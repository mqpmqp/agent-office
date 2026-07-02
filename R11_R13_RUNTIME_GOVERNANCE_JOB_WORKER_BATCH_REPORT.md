# R11-R13 Runtime Governance / Job Persistence / Worker Adapter Batch Report

Marker: R11_R13_RUNTIME_GOVERNANCE_JOB_WORKER_BATCH_REPORT_COMPLETE

## Baseline

- trusted baseline: `phase6/mainline == origin/phase6/mainline == 774dd6382d3259b3593ca8923e381e28a369fb2f`
- preflight branch: `phase6/mainline`
- preflight local HEAD: `774dd6382d3259b3593ca8923e381e28a369fb2f`
- preflight origin/phase6/mainline: `774dd6382d3259b3593ca8923e381e28a369fb2f`
- tracked cleanliness gate: `git status --short --untracked-files=no` clean before branch creation
- untracked artifacts: preserved; no `git clean`, archive, move, or cleanup

## Branch

- source branch: `phase41/r11-r13-runtime-governance-job-worker`
- target branch: `phase6/mainline`

## Feature Commit

The feature commit is the source branch HEAD created after this report is staged. The exact SHA is captured in the final handoff and codex-deliver reports because a commit cannot reliably embed its own final SHA in tracked content.

## Changed Files

- `agent_office/runtime_foundation.py`
- `agent_office/cli.py`
- `tests/test_runtime_foundation_cli.py`
- `README.md`
- `R11_R13_RUNTIME_GOVERNANCE_JOB_WORKER_BATCH_REPORT.md`

No `agent_office/review_lifecycle.py` change was needed; existing reviewed-delivery evidence bundle tests were run unchanged as regression coverage.

## R11 Implemented Scope: Runtime Governance Bridge

Implemented `python3 -m agent_office runtime governance` as a local evidence/readback command.

Capabilities:

- reads current runtime status and replay readback
- reads a project-local runtime closure packet JSON file
- checks workspace identity, task counts, replay validity, closure packet validity, and closure readiness
- writes project-local governance evidence in JSON or text format
- outputs `runtime_governance_ready: true/false`
- records closure packet path and SHA-256 hash
- carries safety boundaries and explicit boundary statements

Safety/path behavior:

- evidence output is project-local only
- closure packet input is project-local only
- traversal is rejected
- `.env` paths are rejected
- symlink output and symlink output parent are rejected
- no merge, push, delivery, provider call, model call, external adapter, daemon, queue, DB, or vector store is triggered

## R12 Implemented Scope: Runtime Job Persistence

Implemented `python3 -m agent_office runtime job` with local static state in `runtime-job.json` under the runtime workspace.

Subcommands:

```bash
python3 -m agent_office runtime job create --workspace .ai/workspaces/demo --job-id demo-job --json
python3 -m agent_office runtime job status --workspace .ai/workspaces/demo --job-id demo-job --json
python3 -m agent_office runtime job cancel --workspace .ai/workspaces/demo --job-id demo-job --json
python3 -m agent_office runtime job fail --workspace .ai/workspaces/demo --job-id demo-job --reason "test failure" --json
python3 -m agent_office runtime job resume --workspace .ai/workspaces/demo --job-id demo-job --json
```

Capabilities:

- local deterministic job id and state readback
- states: `created`, `running`, `completed`, `failed`, `cancelled`
- deterministic logical timestamps: `logical-000001`, etc.
- repeated status readback does not mutate state
- cancelled jobs cannot execute
- failed jobs cannot execute until an allowed resume
- runtime execution updates a present job to `running`, then `completed` or `failed`
- failed task execution still blocks downstream tasks through the existing graph state

Non-scope:

- no daemon
- no queue service
- no DB
- no concurrent worker pool
- no wall-clock scheduling

## R13 Implemented Scope: External Worker Adapter Prototype

Implemented `external-prototype` as a contract stub only.

Commands:

```bash
python3 -m agent_office runtime worker-adapter --list --json
python3 -m agent_office runtime worker-adapter --name external-prototype --describe --json
python3 -m agent_office runtime run --workspace .ai/workspaces/demo --adapter external-prototype --dry-run --json
```

Contract:

- `external-prototype` appears in worker adapter listing
- describe output states `external_execution_enabled: false`
- provider/model/shell/browser flags are false
- dry-run is allowed
- execute-local is rejected with `runtime_external_prototype_execute_refused`
- unsupported adapters still produce the existing clean unsupported-adapter error

## Explicit Non-Goals

This batch does not implement:

- a real external worker adapter
- Claude/Codex/OpenAI/Gemini/browser/shell execution
- provider/model calls
- daemon lifecycle
- queue service
- DB persistence
- vector memory
- concurrent worker pool
- delivery semantics changes
- default branch changes
- tags or force push

## CLI Examples

```bash
python3 -m agent_office runtime governance --workspace .ai/workspaces/demo --closure-packet .ai/workspaces/demo/runtime-closure-packet.json --evidence-out .ai/workspaces/demo/runtime-governance-evidence.json --format json
python3 -m agent_office runtime governance --workspace .ai/workspaces/demo --closure-packet .ai/workspaces/demo/runtime-closure-packet.json --evidence-out .ai/workspaces/demo/runtime-governance-evidence.txt --format text
python3 -m agent_office runtime job create --workspace .ai/workspaces/demo --job-id demo-job --json
python3 -m agent_office runtime job status --workspace .ai/workspaces/demo --job-id demo-job --json
python3 -m agent_office runtime worker-adapter --list --json
python3 -m agent_office runtime worker-adapter --name external-prototype --describe --json
```

## Validation Output Summary

Passed:

- `python3 -m compileall agent_office tests`
- `python3 -m unittest tests.test_runtime_foundation_cli` - 21 tests
- `python3 -m unittest tests.test_review_lifecycle_cli` - 27 tests
- `python3 -m unittest` - 376 tests
- `python3 -m unittest discover -s tests -p 'test_*.py'` - 376 tests
- `python3 -m agent_office doctor --adapters`
- `./scripts/verify.sh`
- `./scripts/smoke-test.sh P6-PROFILES`
- `python3 -m agent_office run-staged P6-PROFILES --dry-run --reset`
- `python3 -m agent_office review codex-deliver --help`
- `python3 -m agent_office review reviewed-delivery --help`
- runtime help commands for `runtime`, `init`, `plan`, `run`, `status`, `governance`, `job`, and `worker-adapter`
- `git diff --check`

## Smoke Output Summary

Passed local smoke on temporary workspace `.ai/workspaces/R11-R13-SMOKE`.

Smoke results:

- runtime init/plan succeeded
- job create wrote `runtime-job.json` with state `created`
- local-static dry-run did not execute tasks
- local-static execute completed 3 tasks
- job status moved to `completed`
- status reported workspace `completed`, 3 completed tasks, memory count 3
- replay returned `replay_valid=true`
- runtime evidence JSON output succeeded
- `runtime closure-packet` wrote a valid closure packet
- governance JSON and text evidence returned `runtime_governance_ready=true`
- worker adapter list included `external-prototype`, `local-static`, and `noop`
- external-prototype describe reported external execution disabled
- external-prototype dry-run succeeded
- external-prototype execute-local returned clean error `runtime_external_prototype_execute_refused`

The smoke workspace was newly created for this run and removed afterward. Existing untracked artifacts were preserved.

## Safety Boundaries

Confirmed by implementation, tests, validation, and smoke:

- `.env` not read
- env vars not printed
- no provider/model calls
- no real external adapter behavior
- no Claude/Codex/OpenAI/Gemini/browser/shell worker integration
- no daemon
- no worker pool
- no queue service
- no DB
- no vector store
- no merge/push/tag from runtime commands
- delivery remains gated by `review codex-deliver`

Explicit runtime boundary:

- local/static/deterministic runtime only
- not real multi-agent runtime

## Delivery Method

Delivery must use `python3 -m agent_office review codex-deliver`:

1. safe-mode report first, proving `merge_executed=false`, `push_executed=false`, and non-destructive behavior
2. authorized delivery only with `--merge-authorized --push-authorized`, proving `merge_executed=true` and `push_executed=true`

No Claude review output is forged or used for reviewed-delivery in this batch.

## Final Mainline Sync Status

Pending at report creation. The final synchronized mainline SHA is captured by the authorized codex-deliver report, post-merge validation, and final handoff output after this feature branch is delivered.
