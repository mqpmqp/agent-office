# AgentOffice Framework Runtime WP9 Scope Gate Report

Marker: WP9_SCOPE_GATE_COMPLETE_NO_IMPLEMENTATION

Status: scope gate only; no WP9 implementation performed.

## Baseline

- Repository: `mqpmqp/agent-office`
- Required stable branch before scope gate: `phase6/mainline`
- Verified preflight branch before WP9 branch creation: `phase6/mainline`
- Verified preflight local HEAD: `1f85fa8063f96756bb55cef254ee464b1806bd2b`
- Verified preflight origin HEAD: `1f85fa8063f96756bb55cef254ee464b1806bd2b`
- WP8 runtime implementation baseline for WP9/WP10: `a1eea368b853459f2ed05d194524e589cb21f8fd`
- WP9 scope branch created for this gate: `framework/runtime-wp9-scope-gate`
- Scope gate branch HEAD: `1f85fa8063f96756bb55cef254ee464b1806bd2b`
- Tracked working tree before report generation: clean

Read evidence:

- `FRAMEWORK_RUNTIME_WP8_SCHEDULER_KERNEL_V1_CLOSURE_INDEX.md`
- `FRAMEWORK_RUNTIME_WP8_SCHEDULER_KERNEL_V1_MERGE_GATE_PACKET.md`
- `FRAMEWORK_RUNTIME_WP8_SCHEDULER_KERNEL_V1_FINAL_SELF_REVIEW_REPORT.md`

## WP8 Inherited Contracts

WP9 must inherit these contracts without weakening them:

- Local/static execution boundary remains the default: `provider_calls=false`, `network_calls=false`, `env_reads=false`, and `external_worker_calls=false` on runtime payloads.
- Do not read `.env`; do not print environment variables; keep EnvGuard-style tests for command paths that could accidentally inspect `os.environ`.
- Framework Runtime errors that reach JSON CLI mode must remain structured JSON error envelopes, not tracebacks.
- WP8 scheduler task states remain authoritative for scheduler flow: `pending`, `selected`, `dispatched`, `waiting_result`, `completed`, `failed`, `paused`, `blocked`, `retry_scheduled`.
- Scheduler retry remains bounded and only valid for failed scheduler tasks; retry exhausted behavior must remain idempotent.
- `task_status:` and `task_terminal:` blocked reasons must not be silently cleared by dependency eligibility refresh.
- Scheduler job IDs stay goal-namespaced as `sched-<goal_id>-<task_id>[-rN]`; cross-goal silent job reuse remains forbidden.
- Scheduler request/status missing graph paths must continue to return stable FrameworkRuntimeError JSON envelopes.
- Execution policy boundary stays local-only by default: only `local.execution.dispatch` is allowed for deterministic dispatch; real/external capabilities remain forbidden.
- Worker adapter intake remains deterministic local result intake; no Codex/Claude/real worker connection is implied by WP9 unless a later reviewed plan explicitly changes the contract.
- External re-review status inherited from WP8 closure is `SKIPPED_TOOL_UNAVAILABLE`; do not claim Claude re-review completion.
- WP8 closure index defines `a1eea368b853459f2ed05d194524e589cb21f8fd` as the clean implementation baseline; later closure-index commits are archive/readback documentation only.

## Candidate WP9 Touch Points

Read-only inspection found these likely WP9 scope surfaces:

1. Framework Runtime core surface: `agent_office/framework_runtime.py`
   - Job lifecycle and transition helpers.
   - Executor run-once/loop/status deterministic stubs.
   - Worker adapter contract and worker result intake.
   - Orchestration plan/show/validate/run-local path.
   - Execution loop run-once/loop/status path and policy decision writes.
   - WP8 scheduler request/run/status/pause/resume/retry/result-intake path.

2. CLI routing and help surface: `agent_office/cli.py`
   - `cmd_framework_runtime` dispatch table.
   - Parser/help entries for `framework-runtime` subcommands.
   - JSON error envelope behavior for job/executor/worker/orchestration/execution/policy/scheduler actions.

3. Task graph and store boundaries:
   - `agent_office/task_graph.py` for graph normalization and ready/blocked semantics.
   - `agent_office/workspace_store.py` for id validation, atomic writes, and workspace/run path boundaries.
   - `agent_office/runtime_events.py` for event log append/list semantics.

4. Evidence/reporting surfaces:
   - `framework_runtime_evidence_payload` inside `agent_office/framework_runtime.py`.
   - Existing root WP reports and README sections that document runtime behavior and validation commands.

5. Test consolidation surface: `tests/test_framework_runtime.py`
   - Existing WP1-WP8 coverage is concentrated in one large test file.
   - WP9 should either append a focused class for its contract or split only if a reviewed plan accepts that larger test organization change.

## Files Likely Affected

For a minimal WP9 implementation slice, likely affected files are:

- `agent_office/framework_runtime.py`
- `agent_office/cli.py`
- `tests/test_framework_runtime.py`
- `README.md`
- a new root report such as `FRAMEWORK_RUNTIME_WP9_<SCOPE>_REPORT.md`

Potentially affected only if WP9 changes graph/store/event contracts:

- `agent_office/task_graph.py`
- `agent_office/workspace_store.py`
- `agent_office/runtime_events.py`

Avoid touching unless WP9 explicitly targets real adapters or provider integration:

- `agent_office/adapters/*`
- autonomy/daemon/background runner surfaces
- legacy `runtime scheduler` namespace

## Tests Likely Affected

Expected focused tests for WP9 depend on the chosen slice, but should at minimum include:

- CLI help smoke for any new `framework-runtime` subcommand or option.
- JSON success and JSON error envelope coverage for the new WP9 command path.
- EnvGuard coverage proving no environment read/write occurs.
- Local/static payload assertions: `provider_calls=false`, `network_calls=false`, `env_reads=false`, `external_worker_calls=false`.
- Evidence/event log assertions if WP9 writes new state, events, or evidence refs.
- Idempotency or terminal-state regression tests for any state-machine transitions.
- Policy-deny tests if WP9 dispatches jobs or touches capability decisions.
- Scheduler regression tests if WP9 composes with WP8 scheduler: priority tie-break, dependency blocking, paused exclusion, retry exhaustion, task-status block preservation, goal-namespaced job ids, and result-intake lifecycle.

Likely verification commands for a future implementation branch:

- `python3 -m compileall agent_office tests`
- `python3 -m unittest tests.test_framework_runtime`
- `python3 -m unittest`
- `python3 -m unittest discover -s tests -p 'test_*.py'`
- `python3 -m agent_office doctor --adapters`
- `./scripts/verify.sh`
- `./scripts/smoke-test.sh P6-PROFILES`
- `python3 -m agent_office run-staged P6-PROFILES --dry-run --reset`
- CLI help smoke for changed framework-runtime surfaces
- `git diff --check`

## Regression Risks

- Divergent scheduler/execution-loop semantics: WP5/WP6 execution loop and WP8 scheduler now overlap in dispatch/job/result concepts; WP9 should choose one integration seam instead of creating a third parallel state machine.
- Silent state mutation from status/read paths: WP8 explicitly fixed phantom transitions; WP9 status-like commands must not persist or mutate unless documented.
- Cross-goal/run ID reuse: any new job/result/policy/evidence identifiers must include enough namespace to avoid silent reuse across goals.
- Error envelope regressions: direct `TaskGraphError`, `WorkspaceStoreError`, or JSON path errors must be wrapped as `FrameworkRuntimeError` for JSON CLI paths.
- Policy bypass: any path that creates or dispatches work must pass through local capability policy or clearly remain read-only.
- External behavior creep: adapters named Codex/Claude/Gemini/Grok exist, but WP9 scope must not accidentally connect real workers/providers.
- Large-file coupling: `agent_office/framework_runtime.py` and `tests/test_framework_runtime.py` are already large; broad refactors could obscure safety regressions.
- Documentation drift: README and root reports must match command behavior if WP9 changes public CLI contracts.

## Safety Boundaries

For WP9 implementation planning, keep these hard boundaries:

- Do not read `.env`.
- Do not print environment variables.
- Do not trigger real provider/runtime/adapter external behavior.
- Do not start daemon, background loop, or sleep loop behavior.
- Do not call Claude or claim Claude re-review unless a future environment actually provides that review and records evidence.
- Keep real/external capabilities denied by default.
- Preserve local/static deterministic mode as the default for docs, tests, payloads, and reports.
- Do not modify legacy runtime scheduler surface unless a future validation failure proves a minimal compatibility fix is required.
- Keep branch isolation and review-gate discipline for any future WP9 code branch.

## Implementation Recommendation

Recommended WP9 direction: make WP9 a narrow contract-integration slice that formalizes how later runtime work should compose with the WP8 scheduler, rather than implementing a new worker/provider runtime.

Preferred first WP9 slice:

- Add a read-only or local-static contract surface that reports the relationship between orchestration, execution loop, policy decisions, worker result intake, and the WP8 scheduler state.
- Reuse existing state files and evidence refs instead of introducing a new runtime store.
- If a new CLI action is needed, place it under `framework-runtime` with explicit JSON/text output and no external side effects.
- Add focused tests around contracts, evidence refs, error envelopes, no-env reads, and WP8 scheduler regression invariants.
- Keep docs/report updates small and concrete.

Not recommended for first WP9 slice:

- Real provider/adapter execution.
- Daemonized scheduling or autonomous loops.
- A broad split/refactor of `framework_runtime.py` before behavior is pinned by a smaller contract test.
- Replacing WP8 scheduler semantics with another state machine.

Recommended next handoff should ask the implementer to choose one named WP9 contract, define exact commands and state/evidence outputs, then run the full WP8/WP9 regression list before any merge gate.

## Scope Gate Result

WP9 scope gate is complete. No WP9 implementation, code change, commit, push, merge, tag, provider call, adapter call, `.env` read, or env var print was performed.
