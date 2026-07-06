# AgentOffice Architecture Debt Audit

Status: framework reset baseline (branch `architecture/fugu-like-framework-reset`, base `phase6/mainline`).
Scope: tracked code only. No historical `.ai/` artifacts or untracked reports were used as evidence.
Method: static inspection of `agent_office/`, `tests/`, `scripts/`, `docs/`, root reports; grep sweeps for
env reads, network use, vendor names, phase names; full test-suite baseline run (464 tests, all passing).

---

## 1. Current module inventory

| Module | Lines | What it actually is |
|---|---|---|
| `agent_office/runtime_foundation.py` | 6,125 | Mega-module: workspace manifest, task graph, JSONL memory/events, jobs, worker packets/results, plus ~25 release/archive/provenance/promotion packet builders |
| `agent_office/cli.py` | 2,826 | Argparse tree for every command; contains business logic (adapter mode resolution, `os.environ` mutation for dry-run propagation) |
| `agent_office/run_bundle.py` | 2,400 | Static run-bundle build/preview/inspect/validate/intake/export |
| `agent_office/review_artifact.py` | 1,847 | Commit-range review artifact export/verify/close-pending |
| `agent_office/review_lifecycle.py` | 1,689 | Review bundle, Claude prompt, attestation, merge packet, codex-gate, reviewed-delivery |
| `agent_office/autonomy_executor.py` | 985 | Local goal queue runner with allowlisted actions, path safety checks |
| `agent_office/artifact_registry.py` | 905 | Registry list/inspect/status over local review/report/sha256 artifacts |
| `agent_office/orchestration.py` | 820 | Static orchestration artifact directory (task graph, packets, manifest) |
| `agent_office/v1_post_release_ops.py` | 713 | Post-v1 release-state / GitHub-release handoff text (tokenless, no network) |
| `agent_office/autonomy.py` | 665 | Autonomy mission plan, run ledger, checkpoints, review/merge packets |
| `agent_office/v1_final_delivery.py` | 465 | v1 release archive verify / readiness packets |
| `agent_office/doctor.py` | 378 | Adapter config checks (env presence only, values never printed) |
| `agent_office/objectives.py` | 366 | Static P5/P6 phase objective specs |
| `agent_office/packets.py` | 293 | Static execution packet builder + contract checks |
| `agent_office/profiles.py` | 243 | Provider profiles (lowest-cost, mock-ci, multi-vendor) |
| `agent_office/planner.py` | 82 | Static execution blueprint |
| `agent_office/adapters/` | ~9 files | `base`, `claude`, `codex`, `gemini`, `grok`, `mock`, `modes`, `patch_validator`, `registry` — vendor-named adapters, mode gate defaults to `mock` |

New in this reset: `agent_office/framework_types.py`, `agent_office/framework_status.py` (see §10).

## 2. Current CLI command inventory

Top-level commands registered in `agent_office/cli.py` (`build_parser`, line ~1983 onward):

- `new`, per-step commands, `run-staged`, `status`, `adapters`, `profiles`, `objectives`, `plan`, `packet`
- `orchestrate` — `run | inspect | validate`
- `runtime` — `init | plan | run | status | packet | replay | evidence | close | closure-packet |
  governance | workspace * | memory (write|list|inspect|summarize) | scheduler | planner | parallel |
  orchestrate | job (create|status|cancel|fail|resume) | worker-adapter | worker-gate | worker-packet |
  worker-result *` — where `worker-result` alone has ~30 sub-subcommands
  (`intake, replay, audit-closure, delivery-bundle, reviewer-attestation, closure-evidence,
  merge-readiness, delivery-gate, rejection-packet, audit-replay, provenance-manifest,
  provenance-verify, provenance-replay, release-candidate, external-review-handoff, archive-index,
  archive-verify, reviewer-archive-import, release-closure, archive-replay, final-readiness,
  review-recovery, compact-archive, compact-verify, rc-promotion-gate, release-candidate-export,
  promotion-evidence, dry-run-publish`)
- `autonomy` — `plan | init | status | checkpoint | report | validate | review-packet | merge-packet |
  queue * | run-goal | resume`
- `v1` — `verify-release-archive | verify-github-release-readback | post-v1-roadmap | release-state |
  github-release-handoff | github-release-plan | release-candidate`
- `run-bundle`, `review` (`preflight-status | bundle | prompt | attest | merge-packet | codex-gate |
  reviewed-delivery | codex-deliver`), `review-artifact` (`export | close-pending | self-check | verify |
  registry * | lifecycle *`), `doctor`, `export-evidence`, `run-demo`
- New in this reset: `framework-status`

This is roughly **100+ leaf commands**. The CLI surface is the architecture; the domain model is not.

## 3. Current domain concept inventory

Concepts that exist today, and where they live:

- **Task workspace** (`.ai/tasks/<TASK_ID>/`) — original 4-role file protocol (`cli.py`, README)
- **Runtime workspace** (`runtime init/plan/run`) — manifest + task graph + JSONL memory/events (`runtime_foundation.py`)
- **Orchestration artifact directory** (`orchestration.py`) — static task graph + packets + manifest
- **Run bundle** (`run_bundle.py`) — static packet/result/intake contract
- **Autonomy queue/ledger** (`autonomy.py`, `autonomy_executor.py`) — goal queue with checkpoints
- **Objectives/profiles/packets/plans** — static P5/P6 specs
- **Jobs** (`runtime job`) — created/running/completed/failed/cancelled state files
- **Worker packets/results** (`runtime worker-*`) — external worker contract without execution

There are at least **four overlapping "workspace" notions** and **three overlapping "task graph"
notions**. None of them is the durable, long-lived Workspace/Goal/Run model the FUGU-like target
requires (see `AGENTOFFICE_FUGU_LIKE_FRAMEWORK.md` §5).

## 4. Current review / gate / artifact concept inventory

- Review bundle + Claude prompt + attestation + merge packet (`review_lifecycle.py`)
- Commit-range review artifact + sidecar sha256 + close-pending (`review_artifact.py`)
- Artifact registry list/inspect/status (`artifact_registry.py`)
- Run-bundle reviewer-ready packet (`run_bundle.py`)
- Worker delivery bundle → reviewer attestation → closure evidence → merge readiness → delivery gate →
  rejection packet → provenance manifest → release candidate → archive chain (`runtime_foundation.py`,
  ~30 `AGENT_OFFICE_*` marker constants)
- Autonomy review-packet / merge-packet (`autonomy.py`)
- Merge-gate git preflight with historical-artifact tolerance (`review preflight-status`)

**Same ideas implemented 4–6 times** with different schemas, markers, and CLI verbs. Review verdicts
and gate decisions are entangled in most of them.

## 5. Long-term core (keep, promote)

- Deterministic, file-backed artifact discipline (no timestamps in derived artifacts, sha256 sidecars)
- Append-only JSONL memory/event pattern in `runtime_foundation.py` (the *pattern*, not the module)
- Mock-by-default adapter mode gate (`adapters/modes.py`: `AGENTOFFICE_AGENT_MODE` defaults to `mock`,
  `real` requires explicit config; env *presence* checks only)
- Path-safety refusals in `autonomy_executor.py` (traversal / `.env` component rejection)
- Tracked-only cleanliness gate (`review preflight-status` with historical-artifact tolerance)
- The safety caveat string discipline (`REVIEWER_ARTIFACT_SAFETY_CAVEAT`)
- Test discipline: 464 deterministic tests, no network, no env values

## 6. Legacy compatibility (keep working, stop extending)

- `.ai/tasks/<TASK_ID>/` 4-role file protocol and `run-demo`
- `run-bundle` static contract (subsume into Packet/Result intake V2 — Slice 4)
- `review` / `review-artifact` lifecycles (subsume into Review/Gate V2 — Slice 5)
- P5/P6 `objectives`, `profiles`, `run-staged` (frozen static specs)
- `autonomy` queue/ledger (fold into Runtime Tick — Slice 8)

## 7. Temporary phase artifacts

- ~56 tracked root-level `*_REPORT.md` / `*_REVIEW_BUNDLE.md` / `*.sha256` files (P8…P60, R1…R45,
  AUTONOMOUS_*, POST_V1_*). Historical evidence; do **not** delete (safety rule), do **not** add more
  at root — new evidence goes under workspace `runs/<run_id>/` (target layout).
- `docs/reports/`, `docs/plans/` phase-scoped documents.
- `deploy/systemd.service.example` — implies a daemon; contradicts the no-daemon rule. Do not extend.

## 8. Contamination

- **No functional trading-bot code exists in this repo.** The only Binance references are defensive
  guard strings ("Do not access `/opt/binance-futures-local-bot`") in `adapters/codex.py:117`,
  `adapters/gemini.py:120`, `docs/plans/gemini-adapter-implementation-plan.md`, `docs/adapter-doctor.md`,
  `docs/agent-roles.md`. Keep the guard, but it hard-codes a sibling project's path into long-term
  prompts — generalize to a deny-list config in a later slice.
- **Session/context-level contamination is real**: this reset task itself arrived through a session
  rooted in the trading-bot repo. Rule reaffirmed: AgentOffice never reads, references, migrates, or
  merges trading-bot content.

## 9. Do-not-extend list

1. `agent_office/runtime_foundation.py` — frozen. No new marker constants, no new packet builders.
2. `agent_office/cli.py` — no new business logic; new commands may only dispatch to modules.
3. `runtime worker-result` subcommand tree — closed; successors live in Review/Gate V2.
4. Root-level report files — closed as an output location.
5. Vendor-named adapter roles as *identity* (`gemini`=context, `codex`=impl, `grok`=review,
   `claude`=judge) — closed; role↔provider binding moves to the role/provider model.
6. Phase-ID-driven objectives (`P6-PROFILES` etc.) as the primary planning noun — closed for new work.

## 10. Must be extracted next (findings → severity)

| Finding | Severity | Action |
|---|---|---|
| No first-class Workspace/Goal/TaskGraph/Run domain model; four ad-hoc workspace notions | **blocker** | Slices 1–3 (workspace store, event log, task-graph kernel) |
| `runtime_foundation.py` (6,125 lines) mixes kernel-ish state with release packet factories | **blocker** | Freeze; extract kernel into `runtime_kernel` slice; leave packet factories as legacy |
| Review vs GateDecision entangled, implemented 4–6× | **major** | Review/Gate V2 (Slice 5) with separate schemas |
| Vendor identity leakage: `ADAPTER_MODE_NAMES=("gemini","codex","grok","claude")`, pyproject description, README product definition | **major** | Role/provider split (framework doc §7); adapters become providers behind roles |
| CLI holds business logic incl. `os.environ` mutation (`cli.py:465–497`) and mode resolution (`cli.py:422`) | **major** | Thin-dispatch rule; move logic to core modules as touched |
| Phase-name leakage into long-term code (`objectives.py` 51 refs, `cli.py` 15, `orchestration.py` 14) | **major** | Freeze phase nouns; new planning nouns are Goal/Task |
| ~30 `AGENT_OFFICE_*` marker constants + parallel schemas in one module | **minor** | Single marker/schema registry in framework types (started: `framework_types.py`) |
| Root report sprawl blocks naive `git status` hygiene | **minor** | Tracked-only gate is already the rule; artifact inventory gate stays separate |
| `deploy/systemd.service.example` daemon implication | **minor** | Mark legacy; no daemon until tick model proven |
| Binance guard path hard-coded in prompts | **nit / legacy-compatible** | Generalize to deny-list later |
| `.env.example` at repo root of a no-`.env` project | **nit** | Document as adapter-era legacy; framework never reads it |
| `doctor.py` env presence checks | **no-action** | By design: presence only, values never printed |

---

Marker: `AGENTOFFICE_ARCHITECTURE_DEBT_AUDIT_V1`
