# P55 Kernel Runtime Semantic Collapse Report

## Baseline

- baseline commit: `f70604b0b31231cff967f02f8293fd186b8f97ee`
- source branch baseline: `phase6/mainline`
- working branch: `phase55-kernel/runtime-semantic-collapse`

## Changed files

- `README.md`
- `agent_office/runtime_foundation.py`
- `agent_office/runtime_kernel/__init__.py`
- `agent_office/runtime_kernel/event_log.py`
- `agent_office/runtime_kernel/executor.py`
- `agent_office/runtime_kernel/kernel.py`
- `agent_office/runtime_kernel/scheduler.py`
- `agent_office/runtime_kernel/validator.py`
- `tests/test_local_multi_agent_runtime_cli.py`
- `tests/test_runtime_kernel.py`

## New kernel files

- `event_log.py`: deterministic append/read JSONL event stream with path and symlink safety.
- `kernel.py`: reducer, replay, state read, and kernel-owned next-action generation.
- `executor.py`: the only local runtime mutator; emits task transition events only.
- `scheduler.py`: pure state projection into ready/blocked/running/completed/failed/skipped buckets.
- `validator.py`: event, transition, and replay invariant validation.

## Collapsed / deprecated semantics

- Runtime state is now reduced from `events.jsonl`; the acceptance rule is `state = reduce(event_log)`.
- `runtime workspace init` appends `RUN_CREATED`; the workspace remains an artifact/run folder.
- `runtime memory write` appends `MEMORY_RECORDED`; `memory.jsonl` is refreshed as a projection cache only.
- `runtime planner` remains a deterministic compile-time static plan compiler and appends `TASK_DEFINED`; it is not a runtime brain.
- `runtime scheduler` reads reduced kernel state and writes only a projection cache at the legacy scheduler ledger path.
- `runtime parallel` uses the executor facade, which emits `TASK_STARTED` and `TASK_COMPLETED`/`TASK_FAILED`; executor output ledgers are projection caches.
- `runtime orchestrate` remains a compatibility/manual sequence helper and derives resume next action from the kernel.
- Legacy `goal-queue.json`, `scheduler-ledger.json`, `executor-ledger.json`, and `memory.jsonl` are no longer canonical state sources for local multi-agent runtime V1.

## CLI compatibility notes

The existing public local runtime commands are preserved:

- `runtime workspace init/status/inspect/report/packet`
- `runtime memory write/list/inspect/summarize`
- `runtime planner`
- `runtime scheduler`
- `runtime parallel`
- `runtime orchestrate`

Compatibility artifacts still exist at legacy paths so older consumers can inspect files, but runtime status and next action now come from the kernel reducer/projection path.

## Safety boundary confirmation

- no `.env` read
- no environment variable output
- no provider call
- no model call
- no adapter external behavior
- no network agent behavior
- no daemon introduced
- no GitHub Release mutation
- no tag mutation
- no merge
- local-only, deterministic, testable runtime semantics retained

## Validation commands and results

- `python3 -m unittest tests.test_runtime_kernel tests.test_local_multi_agent_runtime_cli -v` -> passed, 13 tests
- `python3 -m unittest` -> passed, 470 tests in 246.605s
- `python3 -m compileall agent_office tests` -> passed
- `python3 -m unittest discover -s tests -p 'test_*.py'` -> passed, 470 tests in 223.920s
- `python3 -m agent_office doctor --adapters` -> passed, all adapters reported mock/local ok
- `./scripts/verify.sh` -> passed, `verify ok`
- `./scripts/smoke-test.sh P6-PROFILES` -> passed, `smoke test ok: P6-PROFILES`
- `python3 -m agent_office run-staged P6-PROFILES --dry-run --reset` -> passed, state `APPROVED`
- Runtime help smoke passed for `runtime`, `runtime workspace`, `runtime memory`, `runtime scheduler`, `runtime planner`, `runtime parallel`, and `runtime orchestrate`
- Runtime facade smoke passed on `.ai/local-runtime/p55-kernel-smoke-4`; event log contained 9 events and printed `P55_RUNTIME_FACADE_SMOKE_OK`
- Accidental report heredoc command substitution reran `python3 -m unittest` and `python3 -m unittest discover -s tests -p 'test_*.py'`; both completed successfully. No merge, tag, release, provider, model, adapter, or environment output behavior was triggered.

## New tests summary

- Added direct kernel tests for deterministic event append/read/filter contracts.
- Added reducer/replay determinism and kernel-only next-action coverage.
- Added memory/workspace projection coverage proving artifacts are not state sources.
- Added scheduler pure projection coverage.
- Added executor event emission coverage proving executor does not decide next action.
- Added missing event log, bad JSON, and symlink negative coverage.
- Updated local runtime CLI tests to use event-log fixtures instead of mutating `goal-queue.json` or `memory.jsonl` as canonical state.

## Known limitations

- Legacy local runtime artifacts are retained as compatibility projection caches; they are not removed in this phase.
- Re-running the static planner appends a new plan event sequence. The reducer remains deterministic and folds by task id, but event history is append-only by design.
- Older non-local runtime foundation commands remain outside this semantic-collapse patch unless they directly intersected the local P55-P60 facade.

## Next recommended phase

Run a review-only phase focused on pruning or documenting older non-local runtime foundation status helpers that still read legacy workspace artifacts, without adding P61-P75 capabilities or expanding Autopilot/dashboard behavior.
