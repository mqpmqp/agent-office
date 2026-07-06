# AgentOffice Framework Runtime Trunk Batch Report

Marker: `AGENTOFFICE_FRAMEWORK_RUNTIME_TRUNK_BATCH_COMPLETE_BRANCH_PUSHED`

## Branch

- Branch: `framework/runtime-trunk-batch`
- Target mainline: `phase6/mainline`
- Baseline HEAD: `508201ea3c3b1257f4ae8a118d564fd8a9ba0a6f`
- Final branch HEAD: recorded by `git rev-parse HEAD` after commit/push; a commit cannot embed its own SHA in a tracked report without changing that SHA.

## Preflight Recovery

- Preflight allowed existing historical untracked artifacts in `/opt/agent-office`.
- Tracked files were required clean before branch creation.
- Mainline HEAD and `origin/phase6/mainline` both matched `508201ea3c3b1257f4ae8a118d564fd8a9ba0a6f`.
- Existing untracked artifacts were not cleaned, moved, deleted, or staged.

## Changed Files

- `agent_office/framework_runtime.py`
- `agent_office/cli.py`
- `agent_office/framework_status.py`
- `agent_office/doctor.py`
- `tests/test_framework_runtime.py`
- `tests/test_framework_status.py`
- `README.md`
- `AGENTOFFICE_FRAMEWORK_RUNTIME_TRUNK_BATCH_REPORT.md`

## What Implemented

- Added a deterministic local Framework Runtime Trunk over existing workspace/run/task graph/packet/result/event storage.
- Added local worker adapter contract with `local_echo_worker` producing structured `agentoffice.actor_result` output from framework packets.
- Added dispatch loop that reads ready tasks, emits or reuses packets, writes actor results, appends runtime events, and updates task graph state.
- Added deterministic review and judge stubs that intake actor results/reviews and update task state to `reviewed`, `accepted`, or `rejected`.
- Added resume logic for incomplete runs and replay logic for runtime event logs.
- Added evidence export for run/task/packet/result/event/review/judge/worker-contract evidence bundles.
- Extended framework status and doctor output to advertise runtime trunk capability.

## CLI Commands Added/Changed

- Added `python3 -m agent_office framework-runtime workers [--json]`.
- Added `python3 -m agent_office framework-runtime dispatch --workspace-id ... --run-id ... --goal-id ... --root ... [--task-id ...] [--json]`.
- Added `python3 -m agent_office framework-runtime review --workspace-id ... --run-id ... --goal-id ... --root ... (--result-id ... | --task-id ...) [--json]`.
- Added `python3 -m agent_office framework-runtime judge --workspace-id ... --run-id ... --goal-id ... --root ... (--review-id ... | --task-id ...) [--json]`.
- Added `python3 -m agent_office framework-runtime status/list/inspect/resume/replay/evidence`.
- Extended `framework-status` JSON/text with `runtime_trunk` local-only contract details.
- Extended `doctor` text/JSON with `framework_runtime` local-only contract details.
- Preserved legacy `packet --objective ... --profile ... --actor ...` behavior.

## JSON/Text Contracts

- New JSON kinds include:
  - `agentoffice.framework_runtime_worker_contract`
  - `agentoffice.framework_runtime_dispatch`
  - `agentoffice.framework_runtime_review`
  - `agentoffice.framework_runtime_review_intake`
  - `agentoffice.framework_runtime_judge`
  - `agentoffice.framework_runtime_judge_intake`
  - `agentoffice.framework_runtime_status`
  - `agentoffice.framework_runtime_run_list`
  - `agentoffice.framework_runtime_inspect`
  - `agentoffice.framework_runtime_resume`
  - `agentoffice.framework_runtime_replay`
  - `agentoffice.framework_runtime_evidence_bundle`
  - `agentoffice.framework_runtime_evidence_export`
- Text output explicitly includes local stub / no external provider wording for runtime worker, review, judge, status, resume, replay, and evidence surfaces.

## Safety Boundaries Verified

- Runtime trunk does not read `.env`.
- Runtime trunk does not print environment variables.
- Runtime trunk does not call OpenAI, Claude, Gemini, Grok, or any provider/model API.
- Runtime trunk does not perform network requests.
- Runtime trunk does not execute external adapters or real runtime workers.
- Worker/review/judge outputs record local stub and provider/network/env flags as false.
- ID validation rejects path traversal for workspace/run/goal/task/packet/result/review/judge ids.
- Runtime root handling rejects explicit `..` traversal and symlink roots.
- Errors are routed through structured CLI errors without bare tracebacks.

## Backward Compatibility Notes

- Existing Slice 1-4 workspace, runtime-event, task-graph, packet, and actor-result commands were preserved.
- Legacy packet mode was tested with `packet --objective P6-10 --profile lowest-cost --actor codex --json`.
- Existing P6 profile smoke commands still pass.
- Existing runtime foundation commands were not refactored.

## Exact Validation Commands And Results

- `python3 -m compileall agent_office tests` -> OK.
- `python3 -m unittest tests.test_framework_runtime tests.test_framework_status -q` -> 17 tests OK.
- `python3 -m unittest tests.test_framework_runtime tests.test_packet_result tests.test_task_graph tests.test_runtime_events tests.test_workspace_store tests.test_framework_status -q` -> 56 tests OK.
- `python3 -m unittest` -> 520 tests OK in 264.583s.
- `python3 -m unittest discover -s tests -p 'test_*.py'` -> 520 tests OK in 272.325s.
- `python3 -m agent_office doctor --adapters` -> adapter mode table OK, all mock adapters status `ok`.
- `./scripts/verify.sh` -> `verify ok`.
- `./scripts/smoke-test.sh P6-PROFILES` -> `smoke test ok: P6-PROFILES`.
- `python3 -m agent_office run-staged P6-PROFILES --dry-run --reset` -> final state `APPROVED`.
- `python3 -m agent_office framework-status --json` -> includes `runtime_trunk.status=available`, `provider_calls_enabled=false`, `env_reads_allowed=false`.
- `python3 -m agent_office framework-status` -> text includes `runtime trunk: available` and `runtime worker adapters: local_echo_worker`.
- `git diff --check` -> OK.

## E2E Smoke Commands And Results

Smoke path: `/tmp/agentoffice-runtime-trunk-smoke`.

Commands executed:

```bash
rm -rf /tmp/agentoffice-runtime-trunk-smoke
mkdir -p /tmp/agentoffice-runtime-trunk-smoke
python3 -m agent_office workspace init --workspace-id ws-demo --root /tmp/agentoffice-runtime-trunk-smoke --json
python3 -m agent_office workspace run-create --workspace-id ws-demo --run-id run-demo --root /tmp/agentoffice-runtime-trunk-smoke --json
python3 -m agent_office task-graph create --workspace-id ws-demo --goal-id goal-demo --root /tmp/agentoffice-runtime-trunk-smoke --json
python3 -m agent_office packet emit --workspace-id ws-demo --run-id run-demo --goal-id goal-demo --task-id task-a --root /tmp/agentoffice-runtime-trunk-smoke --json
python3 -m agent_office framework-runtime dispatch --workspace-id ws-demo --run-id run-demo --goal-id goal-demo --task-id task-a --root /tmp/agentoffice-runtime-trunk-smoke --json
python3 -m agent_office framework-runtime review --workspace-id ws-demo --run-id run-demo --goal-id goal-demo --result-id res_task-a --root /tmp/agentoffice-runtime-trunk-smoke --json
python3 -m agent_office framework-runtime judge --workspace-id ws-demo --run-id run-demo --goal-id goal-demo --review-id rev_task-a --root /tmp/agentoffice-runtime-trunk-smoke --json
python3 -m agent_office runtime-event list --workspace-id ws-demo --run-id run-demo --root /tmp/agentoffice-runtime-trunk-smoke --json
python3 -m agent_office framework-runtime status --workspace-id ws-demo --run-id run-demo --goal-id goal-demo --root /tmp/agentoffice-runtime-trunk-smoke --json
python3 -m agent_office framework-runtime list --workspace-id ws-demo --root /tmp/agentoffice-runtime-trunk-smoke --json
python3 -m agent_office framework-runtime inspect --workspace-id ws-demo --run-id run-demo --goal-id goal-demo --task-id task-a --root /tmp/agentoffice-runtime-trunk-smoke --json
python3 -m agent_office framework-runtime resume --workspace-id ws-demo --run-id run-demo --goal-id goal-demo --root /tmp/agentoffice-runtime-trunk-smoke --json
python3 -m agent_office framework-runtime replay --workspace-id ws-demo --run-id run-demo --root /tmp/agentoffice-runtime-trunk-smoke --json
python3 -m agent_office framework-runtime evidence --workspace-id ws-demo --run-id run-demo --goal-id goal-demo --root /tmp/agentoffice-runtime-trunk-smoke --format json --json
python3 -m agent_office framework-runtime evidence --workspace-id ws-demo --run-id run-demo --goal-id goal-demo --root /tmp/agentoffice-runtime-trunk-smoke --format text
```

Result:

- `E2E_RUNTIME_TRUNK_SMOKE_OK`
- `resume_actions 3`
- `replay_events 17`
- Evidence artifact: `/tmp/agentoffice-runtime-trunk-smoke/.ai/workspaces/ws-demo/runs/run-demo/evidence/framework_runtime_evidence.json`

## Known Limitations

- Worker, review, and judge are deterministic local stubs only; no provider-backed adapter is implemented or invoked.
- Evidence export writes under the run evidence directory rather than bundling an archive file.
- Resume executes deterministic local stages for ready/incomplete tasks but does not implement parallel scheduling or external worker queues.
- The committed report cannot embed its containing commit SHA without changing that SHA; final pushed HEAD is recorded by the final command output.

## Next Recommended Trunk Batch

Implement Review/Gate V2 on top of the runtime trunk evidence model: gate policies, merge-readiness predicates, review artifact intake, and deterministic gate summaries that consume runtime evidence bundles without provider calls by default.
