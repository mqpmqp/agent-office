# Framework Runtime WP1-WP7 Conditional Delta Triage

Source review:
- `FRAMEWORK_RUNTIME_WP1_WP7_CLAUDE_ARTIFACT_REVIEW_OUTPUT.md`

Triage status:
- WP1-WP7 architecture verdict remains `CONDITIONAL PASS`.
- No WP1-WP7 blocker requires code rollback inside the reviewed local/static scope.
- WP8 should not start as an unrestricted scheduler implementation until the required deltas below are closed or explicitly accepted as carry-forward risk.

## Executive Decision

Proceed only with a narrow WP8 scheduler planning slice unless P0 deltas are addressed first.

Allowed next step:
- WP8 scheduler contract/design or bounded local tick prototype that uses only `framework-runtime execution` / WP6-WP7 execution-loop APIs.

Not allowed as next step without further review:
- Scheduler calling legacy `framework-runtime executor`, `dispatch`, or `resume` as its execution backend.
- Provider/Codex/Claude/runtime adapter execution.
- Daemon/background worker/message queue behavior.

## P0 Deltas Before WP8 Implementation

### P0-1: Pin The Scheduler Execution Substrate

Finding source:
- Major finding 1: policy gate does not cover all framework-runtime execution-like surfaces.

Current evidence:
- `agent_office/framework_runtime.py` gates `execution_loop_run_once_payload` through `policy_decision_payload` before local worker-result intake.
- `agent_office/cli.py` exposes `framework-runtime execution run-once/loop --capability-id`, defaulting to `local.execution.dispatch`.
- Legacy local stub surfaces still exist: `framework-runtime executor`, `framework-runtime dispatch`, and `framework-runtime resume`.

Required delta:
- Document and enforce for WP8 that scheduler uses the WP6/WP7 execution-loop surface only.
- Explicitly classify legacy executor/dispatch/resume as local-only compatibility surfaces, not scheduler targets.

Recommended minimal fix:
- Add README/report language before WP8 handoff.
- Add a WP8 handoff invariant: scheduler dispatch must produce a policy decision before job creation or worker-result intake.

Acceptance evidence:
- README or WP8 plan states the execution-loop-only scheduler substrate.
- Focused tests or design checks assert scheduler-intended dispatch emits policy decisions and denied capabilities create no worker result.

### P0-2: Resolve Runtime Vocabulary Boundary For Scheduler

Finding source:
- Major finding 4: two runtime vocabularies remain adjacent.

Current evidence:
- `framework_runtime.py` uses job statuses `pending/running/succeeded/failed/cancelled` and terminal task statuses `accepted/rejected/skipped`.
- `runtime_foundation.py` retains older `pending/completed/failed/blocked` task states and `created/running/completed/failed/cancelled` job states.
- README notes the older `runtime` prototype remains local-only, but it does not make it the WP8 scheduler substrate.

Required delta:
- WP8 must name `framework_runtime.py` WP6/WP7 execution-loop state as canonical for the scheduler.
- Any reference to older `runtime` scheduler/prototype must be explicitly non-canonical for Framework Runtime WP8.

Recommended minimal fix:
- Add a small state vocabulary table to the WP8 plan or README section.

Acceptance evidence:
- WP8 handoff includes task/job/orchestration/execution-loop state mapping.
- No WP8 code path calls `runtime_foundation.runtime_scheduler_payload` as the Framework Runtime scheduler backend.

## P1 Deltas Before Merge/External Review Closure

### P1-1: Generate Supplemental Source Snapshot Bundle

Finding source:
- Major finding 2: artifact source snapshot omitted `agent_office/cli.py` and README despite reports saying they changed.

Current evidence:
- Current repo contains CLI policy/execution wiring in `agent_office/cli.py`.
- Existing review bundle omitted direct snapshots for `agent_office/cli.py` and `README.md`.

Required delta:
- Produce a supplemental artifact bundle containing at least:
  - `agent_office/cli.py`
  - `README.md`
  - existing WP1-WP7 review output
  - this triage artifact

Recommended minimal fix:
- Generate `FRAMEWORK_RUNTIME_WP1_WP7_CONDITIONAL_DELTA_SUPPLEMENTAL_BUNDLE` and sha256 in a separate collection step.

Acceptance evidence:
- Supplemental tarball plus sha256 exist.
- Reviewer can inspect CLI parser/action routing directly from artifacts.

### P1-2: Recreate Complete Validation Evidence With Bounded Runtime

Finding source:
- Major finding 3 and minor finding 4: validation artifacts are mixed; discovery output lacks a final summary.

Current evidence:
- Review records that artifact generation observed a hung first unittest run that was terminated.
- `validation/unittest.txt` contains `Ran 544 tests ... OK`, but must be treated with the hang caveat.
- `validation/unittest_discovery.txt` contains only progress dots and no summary.

Required delta:
- Re-run validation with explicit timeout/bounded command wrappers and capture complete exit status summaries.

Recommended minimal fix:
- Capture command, timeout, exit code, duration, stdout tail, and stderr tail for:
  - `python3 -m compileall agent_office tests`
  - `python3 -m unittest`
  - `python3 -m unittest discover -s tests -p 'test_*.py'`
  - `python3 -m agent_office doctor --adapters`
  - `./scripts/verify.sh`

Acceptance evidence:
- New validation artifact states each command result as passed/failed/timed_out.
- No validation artifact is represented as passed without a final summary or explicit timeout label.

## P2 Deltas / Carry-Forward Notes

### P2-1: Enrich Runtime Events Later

Finding source:
- Minor finding 1: runtime events are useful but sparse.

Triage:
- Not required for WP8 contract planning.
- Useful before debugger/replay UX work.

### P2-2: Expand Policy Beyond Static Capabilities Later

Finding source:
- Minor finding 2: policy decisions are static declarations only.

Triage:
- Acceptable for WP7 and local-only WP8 scheduler.
- Required before any real provider or role/user permission model.

### P2-3: Tighten Explicit Failure Semantics Later

Finding source:
- Minor finding 3: `failed` is reserved more than exercised in orchestration/execution-loop V1.

Triage:
- Acceptable for deterministic local V1.
- Should be revisited before non-stub worker execution or scheduler retry policy.

## Risk Register

| Risk | Severity | Disposition |
| --- | --- | --- |
| WP8 accidentally builds on legacy executor/dispatch/resume and bypasses policy decisions | P0 | Must be prevented in WP8 plan/handoff. |
| WP8 mixes old `runtime` vocabulary with Framework Runtime WP6/WP7 state | P0 | Must pin canonical substrate first. |
| Reviewer cannot inspect CLI/README in artifact-only review | P1 | Generate supplemental artifact bundle. |
| Validation artifact overclaims due to hung/partial unittest discovery | P1 | Regenerate bounded validation evidence. |
| Sparse event payloads reduce replay/debug value | P2 | Carry forward to observability work. |

## Recommended Next Action

Do the deltas in this order:

1. P0-1 and P0-2: update the WP8 handoff/plan with explicit scheduler substrate and state vocabulary boundaries.
2. P1-1: generate a supplemental source snapshot artifact for CLI/README review completeness.
3. P1-2: regenerate validation evidence with bounded command wrappers.
4. Only then start WP8 scheduler implementation, limited to local deterministic execution-loop ticks.

## Triage Verdict

WP1-WP7 can stand as a conditional local/static runtime foundation.

WP8 may proceed only if it is scoped to the WP6/WP7 execution-loop and policy boundary. If WP8 needs real providers, daemon behavior, queues, external workers, or old `runtime` scheduler integration, it requires a new architecture review before implementation.

FRAMEWORK_RUNTIME_WP1_WP7_CONDITIONAL_DELTA_TRIAGE_COMPLETE
