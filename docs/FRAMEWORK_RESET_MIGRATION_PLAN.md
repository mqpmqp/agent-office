# Framework Reset Migration Plan

Companion to `AGENTOFFICE_FUGU_LIKE_FRAMEWORK.md` (target) and `ARCHITECTURE_DEBT_AUDIT.md`
(current state). This plan maps existing code to the target architecture, slice by slice, with
explicit freeze/promote/replace decisions. No big-bang refactor; every slice is small, tested, and
leaves the existing 464-test suite green.

---

## 1. Disposition of existing modules

| Existing module | Disposition | Absorbed by (slice) |
|---|---|---|
| `framework_types.py`, `framework_status.py` (new) | **core — grow carefully** | all slices reference it |
| `runtime_foundation.py` — workspace/task-graph/memory/events portions | promote pattern, reimplement cleanly | Slices 1–3 |
| `runtime_foundation.py` — worker packet/result intake | freeze; compatibility reader | Slice 4 |
| `runtime_foundation.py` — attestation/gate/merge-readiness/delivery-gate | freeze; schemas inform V2 | Slice 5 |
| `runtime_foundation.py` — provenance/archive/RC/promotion/publish factories | freeze (legacy evidence chain) | none (kept for replay of old runs) |
| `run_bundle.py` | freeze; compatibility reader | Slice 4 |
| `review_lifecycle.py`, `review_artifact.py`, `artifact_registry.py` | freeze; V2 supersedes | Slice 5 |
| `autonomy.py`, `autonomy_executor.py` | freeze; queue semantics inform tick | Slice 8 |
| `orchestration.py` | freeze (static artifact generator) | Slice 3 informs task-graph schema |
| `objectives.py`, `profiles.py`, `planner.py`, `packets.py` | freeze (P5/P6 static specs) | Slice 4 packet schema |
| `adapters/*` | keep; becomes provider layer behind roles | Slices 7, 9 |
| `doctor.py` | keep (presence-only env checks) | Slice 9 extends |
| `v1_final_delivery.py`, `v1_post_release_ops.py` | freeze (release-era) | none |
| `cli.py` | thin-dispatch rule from now on; shrink opportunistically | every slice |

"Freeze" means: keep working, keep tested, add no new features, add no new marker constants.

## 2. Slice order and deliverables

### Slice 1 — Workspace Store
Durable workspace and run directories under `.ai/workspaces/<workspace_id>/`.
Deliver: `WorkspaceSpec`, `RunSpec`, `workspace init`, `workspace inspect`, `run create`.
No scheduler. New module: `agent_office/workspace.py`.

### Slice 2 — Runtime Event Log
Append-only `events.jsonl` with deterministic tests.
Deliver: `append_event()`, `read_events()`, content-derived `event_id`, stable clock injection.
New module: `agent_office/runtime_events.py`.

### Slice 3 — Task Graph Kernel
Goal decomposition and dependencies as durable state.
Deliver: `task_graph.json`, ready-task computation, blocked-task explanation, task state
transitions per the state machines in framework doc §9.
New module: `agent_office/runtime_kernel.py` (kernel grows here, not in `runtime_foundation.py`).

### Slice 4 — Packet / Result Intake V2
Unify run-bundle and worker packet/result logic under the runtime domain model.
Deliver: packet emit, actor result intake, evidence refs, `schema_version`, compatibility with
existing run-bundle artifacts (reader, not rewrite).

### Slice 5 — Review / Gate V2
Separate Review from GateDecision.
Deliver: review artifact schema, gate decision schema, pending-Claude-follow-up handling,
attestation import, merge-readiness packet. Legacy `review`/`review-artifact` commands keep
working against old artifacts.

### Slice 6 — Recovery UX
Deliver the detection matrix from framework doc §13: wrong-environment detector, dirty tracked
worktree detector, untracked artifact inventory, stale branch detector, provider-disabled
explanation, "next safe command" output.

### Slice 7 — Manual / External Worker Adapter
Human/manual/external result loops without model calls.
Deliver: manual packet, manual result import, external worker placeholder, provider calls still
disabled by default.

### Slice 8 — Runtime Tick
First deterministic tick loop: `runtime tick --workspace <id> --run <id>`.
Deliver: compute next action, emit packet or wait state, accept result, request review. No daemon.

### Slice 9 — Provider Adapter Gate
Prepare future real provider calls safely.
Deliver: provider registry, adapter capability model, explicit authorization flag, dry-run
default, mock tests only. Vendor-named adapters become providers selectable per role.

### Slice 10 — API / UI Boundary
Machine-readable state for a future UI/dashboard.
Deliver: status JSON, workspace summary, run summary, task-graph summary, review/gate summary.

## 3. Rules during migration

1. Domain first, CLI second — new commands are thin dispatchers into new modules.
2. Runtime state must be durable; every transition leaves an event.
3. Role is not provider; provider calls disabled by default; manual execution first-class.
4. Merge gate stays separate from review verdict.
5. No phase-specific names (`P6-...`, `R41-...`) in new long-term code.
6. No trading-bot content, references, or reuse.
7. No hidden environment dependency; no `.env` reads; no env value printing.
8. No daemon until the tick model is proven; no `git clean`; no artifact deletion;
   no force-push; no tags; no default-branch changes.
9. Tests never depend on historical untracked artifacts.
10. Each slice lands on its own branch with docs + tests + green legacy suite.

## 4. Definition of done for the reset itself

- [x] `docs/ARCHITECTURE_DEBT_AUDIT.md` — current state, classified findings
- [x] `docs/AGENTOFFICE_FUGU_LIKE_FRAMEWORK.md` — normative target
- [x] `docs/FRAMEWORK_RESET_MIGRATION_PLAN.md` — this file
- [x] `agent_office/framework_types.py` — canonical domain registry (roles, providers, state machines, core objects)
- [x] `agent_office/framework_status.py` — deterministic status contract
- [x] `framework-status` CLI command (`--json` and text), local-only, no env reads, no provider calls
- [x] `tests/test_framework_status.py` — schema stability + invariant tests
- [x] Full legacy suite still green

---

Marker: `AGENTOFFICE_FRAMEWORK_RESET_MIGRATION_PLAN_V1`
