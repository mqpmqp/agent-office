# AgentOffice — FUGU-like Target Framework

```text
AgentOffice = Local-first Multi-Agent Office Runtime
```

Status: normative target architecture, adopted at the framework reset
(branch `architecture/fugu-like-framework-reset`). Everything in this document overrides
phase-era conventions where they conflict. Machine-readable summary:
`python3 -m agent_office framework-status --json`.

---

## 1. Product definition

AgentOffice is a **local-first, file-driven, auditable, recoverable multi-agent office runtime**.
It manages task decomposition, execution, evidence archiving, review, decision, and delivery across
multiple agents, models, tools, and human roles.

The canonical flow:

```text
User Goal
→ Goal Intake
→ Task Graph
→ Role Assignment
→ Agent Packet Generation
→ Local Runtime Scheduling
→ Actor Execution / Manual Execution / External Worker Execution
→ Result Intake
→ Evidence Bundle
→ Review / Judge / Gate
→ Recovery / Retry / Escalation
→ Final Delivery / Archive
```

## 2. Non-goals

AgentOffice is **not**:

- a trading bot or Binance futures bot (that is a separate project line; never read/merge its content)
- a single-AI-agent wrapper or prompt collection
- a pure CLI demo or pure artifact generator
- a single-pass review pipeline
- a prompt relay script for Codex/Claude
- a hosted SaaS, a daemon, or a background service (until the tick model is proven)

## 3. Core domain model

Long-term objects. Every object declares: purpose, stable identifier, persisted location, key
input/output fields, lifecycle states, owner subsystem, CLI/API exposure. Canonical registry in
code: `agent_office/framework_types.py` (`CORE_OBJECTS`).

| Object | Purpose | Stable ID | Persisted at | Owner subsystem | CLI/API exposure |
|---|---|---|---|---|---|
| **Workspace** | Long-lived office boundary holding goals and runs | `ws_<slug>` | `.ai/workspaces/<workspace_id>/workspace.json` | storage | `workspace init/inspect` (Slice 1) |
| **Goal** | One user objective under a workspace | `goal_<slug>` | `goals/<goal_id>/goal.json` | core | `goal create/show` (Slice 1/3) |
| **Task** | One unit of work inside a goal | `task_<slug>` | inside `task_graph.json` | core | via task-graph commands |
| **TaskGraph** | Decomposition of a goal with dependencies | goal-scoped | `goals/<goal_id>/task_graph.json` | core | `taskgraph plan/ready` (Slice 3) |
| **Role** | A responsibility (never a vendor) | role name | `framework_types.py` constants | core | `framework-status` |
| **Agent** | An executing instance of a role | `agent_<slug>` | workspace `workspace.json` registry | core | agent registry (later slice) |
| **Provider** | Replaceable backing implementation | provider name | adapter registry | adapters | `doctor`, provider gate (Slice 9) |
| **Adapter** | Interface between a provider and the runtime | provider-scoped | `agent_office/adapters/` | adapters | `doctor --adapters` |
| **Packet** | Execution contract handed to an actor | `pkt_<slug>` | `runs/<run_id>/packets/` | runtime | packet emit (Slice 4) |
| **Run** | One execution attempt of a goal | `run_<slug>` | `runs/<run_id>/run.json` | runtime | `run create/status` (Slice 1) |
| **RunState** | Durable state machine position of a run | run-scoped | `run.json` | runtime | run status |
| **RuntimeEvent** | Append-only record of every transition | `evt_<hash>` | `runs/<run_id>/events.jsonl` | runtime | event readback (Slice 2) |
| **ActorResult** | What an actor returned for a packet | packet-scoped | `runs/<run_id>/results/` | runtime | result intake (Slice 4) |
| **EvidenceBundle** | Reviewable proof of a run's work | run-scoped | `runs/<run_id>/evidence/` | review | evidence build |
| **Review** | Verdict + findings on evidence | review-scoped | `runs/<run_id>/reviews/` | review | Review/Gate V2 (Slice 5) |
| **GateDecision** | Merge/deliver decision, separate from Review | gate-scoped | `runs/<run_id>/reviews/` | review | Review/Gate V2 (Slice 5) |
| **Delivery** | Final handoff package | run-scoped | `runs/<run_id>/delivery/` | review | delivery commands |
| **Archive** | Immutable long-term record with hashes | workspace-scoped | workspace archive index | storage | archive verify |

Rules:

- `workspace_id` and `goal_id` are stable; `run_id` may be minted many times per goal.
- A run never overwrites a previous run.
- `events.jsonl` is append-only.
- Every packet, result, review, and evidence file is independently re-verifiable.

## 4. Runtime model

```text
runtime_model = deterministic_cli_tick_first
```

The runtime kernel is the long-term core. Minimum responsibilities:

1. load workspace
2. load run state
3. append runtime event
4. compute next ready tasks
5. emit packets
6. accept actor results
7. transition task/run state
8. build evidence bundle
9. request review
10. apply gate decision

V1 is **not** a daemon and has no background workers. It is a deterministic, CLI-driven tick:

```text
agent-office runtime tick --workspace <id> --run <id>
```

Each tick: read current state → compute next step → append event(s) → emit/update packet or
`next_action` → exit. Idempotent by construction: re-running a tick with unchanged inputs appends no
new state-changing events. Locking is file-based and scoped to the run directory.

What the kernel is **not** (distinctions the phase era blurred):

```text
static orchestration artifact ≠ runtime
review bundle ≠ runtime
CLI command ≠ runtime
state json ≠ runtime kernel
```

## 5. Workspace model

A Workspace is a long-lived boundary, not a single-run directory.

```text
.ai/
  workspaces/
    <workspace_id>/
      workspace.json
      goals/
        <goal_id>/
          goal.json
          task_graph.json
      runs/
        <run_id>/
          run.json
          events.jsonl
          packets/
          results/
          reviews/
          evidence/
          delivery/
          logs/
```

The legacy layouts (`.ai/tasks/`, runtime-foundation workspaces, orchestration output dirs,
run-bundle dirs, autonomy queues) remain readable but frozen; new work targets this layout only.

## 6. Agent / role / provider model

**Role** is a responsibility. Standard roles:

```text
context_agent
planner_agent
implementation_agent
review_agent
judge_agent
delivery_agent
human_approver
external_worker
```

**Agent** is an executing instance of a role. **Provider** is the replaceable implementation behind
an agent:

```text
manual | local_mock | codex | claude | gemini | grok | future_provider
```

**Adapter** is the provider interface. Hard rules:

- Role logic never depends on a provider name. (`gemini`=context, `codex`=impl, `grok`=review,
  `claude`=judge was the phase-era binding; it becomes a *default provider mapping*, not identity.)
- Provider calls are disabled by default; enabling a real provider requires an explicit
  authorization flag (Slice 9).
- No `.env` reads in the framework. No env var printing anywhere. No network/model calls in tests.
- Manual/human execution is first-class, not a fallback.

## 7. Packet / result / evidence model

**Packet** (execution contract) must carry: role, task_id, objective, allowed files, forbidden
actions, validation command, expected output, evidence requirements, stop conditions.

**ActorResult** must carry: actor identity, task_id, status, changed files, validation commands,
validation result, evidence files, summary, blockers.

**EvidenceBundle** must carry: diff, changed files, validation output, smoke output, review output,
gate decision, archive hash.

The existing `run-bundle` and `runtime worker-packet/worker-result` contracts are prior art; Slice 4
unifies them under these schemas with `schema_version` and compatibility readers.

## 8. Review / gate model

**Review is not a merge gate; a merge gate is not a review.** Two separate artifacts:

Review:

```text
verdict: pass | conditional_pass | fail
findings: blocker | major | minor | nit
missing_tests, safety_risks, regression_risks, recommended_delta, marker
```

GateDecision:

```text
decision: allow_merge | block_merge | require_fix | require_human
reason, required_evidence, review_refs, attestation_refs
```

Mandatory artifact-based caveat, preserved from the phase era:

```text
Claude did not execute commands unless it actually ran them in the correct repo.
Validation outputs from VPS are evidence artifacts, not Claude-executed proof.
```

## 9. Event log

Append-only, one JSON object per line in `runs/<run_id>/events.jsonl`:

```json
{
  "schema_version": 1,
  "event_id": "evt_...",
  "workspace_id": "ws_...",
  "goal_id": "goal_...",
  "run_id": "run_...",
  "task_id": "task_...",
  "event_type": "task.ready",
  "actor": "runtime",
  "created_at": "ISO-8601",
  "payload": {},
  "evidence_refs": []
}
```

Events must be deterministic enough for tests: the kernel accepts an injected clock (or stable
timestamp source), and `event_id` derives from content, not randomness.

### Goal state machine

```text
goal.created → goal.planned → goal.packetized → goal.running → goal.review_pending
→ goal.gate_pending → goal.passed | goal.failed → goal.archived
```

### Task state machine

```text
task.created → task.ready → task.dispatched → task.result_pending → task.result_received
→ task.review_pending → task.accepted | task.rejected | task.blocked | task.skipped
```

Tasks support: dependencies, role assignment, required evidence, validation command, review
requirement, retry policy, human approval requirement.

## 10. Storage layout

- All durable state lives under `.ai/workspaces/` (see §5), project-local, file-backed.
- Derived artifacts carry `schema_version` and content hashes; provenance-bearing artifacts may
  record git source state.
- Root-level report files are a **closed** output location; run evidence goes in
  `runs/<run_id>/`.
- Repo hygiene gates (long-term rules):
  - tracked code cleanliness gate: `git status --short --untracked-files=no`
  - artifact inventory gate: separate check over reports/bundles/`.ai/` output
  - merge gate must not fail on historical untracked artifacts
  - never `git clean`, never delete historical artifacts without explicit authorization

## 11. CLI / API boundary

```text
CLI      = thin command dispatch (argparse only; no business logic)
Core     = pure deterministic domain logic (types, state machines, planning)
Runtime  = state machine + scheduler + event log (kernel)
Storage  = file-backed read/write abstraction (workspace store)
Review   = artifact/review/gate subsystem
Adapters = provider/manual/external-worker boundary
```

Machine-readable status surfaces (`--json` on every framework command) are the future API/UI
boundary (Slice 10). No HTTP server is in scope.

## 12. Safety model

Hard boundaries (framework-wide, enforced by tests where possible):

```text
- Do not read `.env`             - Do not force-push
- Do not print env vars          - Do not tag
- No provider/model/network      - Do not change default branch
  calls by default               - Do not use git clean
- Do not touch trading-bot /     - Do not delete historical artifacts
  Binance repos                  - No broad refactor without proof
- No background daemon
```

Allowed: inspect tracked code, write docs, add minimal pure-Python scaffold, add tests, run local
deterministic validation, commit/push explicit framework branches only.

`framework-status` asserts the load-bearing invariants in JSON:
`provider_calls_enabled: false`, `env_reads_allowed: false`, `trading_bot_scope: false`.

## 13. Recovery model

Every failure mode gets: detection rule, safe-stop behavior, whether automatic fix is allowed,
required human action, and a report marker. Initial matrix (implemented incrementally, Slice 6):

| Failure | Detection | Safe stop | Auto-fix? | Human action | Marker |
|---|---|---|---|---|---|
| Wrong environment | repo root / `git remote -v` mismatch | stop before any write | no | operator relocates | `..._WRONG_ENVIRONMENT_STOPPED` |
| Dirty tracked worktree | `git status --short --untracked-files=no` non-empty | stop before checkout/commit | no | human reviews diff | `DIRTY_TRACKED_WORKTREE` |
| Untracked artifact noise | artifact inventory scan | continue; never clean | no deletion | optional archival | `UNTRACKED_ARTIFACT_INVENTORY` |
| Missing review output | review ref unresolvable | gate → `require_fix` | no | reviewer re-runs | `MISSING_REVIEW_OUTPUT` |
| Failed validation | validation command exit ≠ 0 | task → `task.rejected` | retry per policy | on retry exhaustion | `VALIDATION_FAILED` |
| Pending Claude follow-up | open pending artifact | gate → `require_human` | no | attestation import | `PENDING_FOLLOWUP` |
| Stale branch | base ref moved | stop before push | rebase only if clean | human confirms | `STALE_BRANCH` |
| Origin mismatch | remote URL ≠ expected | stop | no | operator fixes remote | `ORIGIN_MISMATCH` |
| Provider disabled | adapter gate closed | emit manual packet instead | n/a (by design) | explicit authorization flag | `PROVIDER_DISABLED` |
| Adapter failure | adapter error result | task → `task.blocked` | retry per policy | human on exhaustion | `ADAPTER_FAILURE` |
| Partial result intake | result schema incomplete | result quarantined | no | actor resubmits | `PARTIAL_RESULT_INTAKE` |

## 14. Migration plan from current code

Detailed mapping in `docs/FRAMEWORK_RESET_MIGRATION_PLAN.md`. Summary:

- **Freeze**: `runtime_foundation.py` packet factories, `worker-result` tree, root reports,
  phase objectives, vendor-role identity.
- **Promote**: JSONL event pattern, mock-by-default adapter gate, path-safety refusals,
  deterministic artifact discipline, tracked-only cleanliness gate.
- **Replace** (by slice): workspace store → event log → task-graph kernel → packet/result intake V2
  → review/gate V2 → recovery UX → manual/external adapter → runtime tick → provider gate →
  API/UI boundary.
- **Never**: big-bang refactor, deletion of legacy modules, breaking existing 464 tests.

## 15. Test strategy

- Every new framework module ships with deterministic `unittest` tests; no network, no `.env`,
  no env-var values, no reliance on historical `.ai/` or root-report artifacts.
- Schema stability tests: JSON contracts (like `framework-status`) are asserted key-by-key so
  accidental contract drift fails CI.
- State machine tests: every legal transition and at least one illegal transition per machine.
- Event log tests use injected clocks; artifacts asserted byte-stable for identical inputs.
- Legacy suites keep passing untouched; compatibility readers get golden-file tests.

## 16. Next 5 implementation slices

```text
1. workspace_store        — WorkspaceSpec/RunSpec, workspace init/inspect, run create
2. runtime_event_log      — events.jsonl, append_event()/read_events(), stable clock injection
3. task_graph_kernel      — task_graph.json, ready-task computation, state transitions
4. packet_result_intake   — unify run-bundle packet/result under the runtime domain model
5. review_gate_v2         — Review separated from GateDecision; attestation import
```

(Slices 6–10 — recovery UX, manual/external worker adapter, runtime tick, provider adapter gate,
API/UI boundary — follow in `FRAMEWORK_RESET_MIGRATION_PLAN.md`.)

---

Marker: `AGENTOFFICE_FUGU_LIKE_FRAMEWORK_V1`
