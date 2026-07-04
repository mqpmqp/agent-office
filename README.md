# AgentOffice

AgentOffice is a minimal file-based orchestrator for four AI roles:

- Gemini: context scan and compressed summary.
- Codex: implementation, bug fixes, and tests.
- Grok Build: red-team review.
- Claude Code: final decision only.

The agents do not freely chat. Every task is coordinated through files under:

```text
.ai/tasks/<TASK_ID>/
  task.json
  brief.md
  gemini-context.md
  codex-report.md
  patch.diff
  grok-review.md
  final-for-claude.md
  claude-decision.md
```

## Auditable Multi-Agent Orchestration

AgentOffice is evolving from a static workflow/gate tool into an auditable multi-agent orchestration system.

The first orchestration core accepts one high-level task and creates a white-box multi-agent execution graph. Unlike black-box orchestration systems, AgentOffice keeps artifacts, task graphs, role packets, validation state, and safety boundaries inspectable.

Current orchestration mode is static only. It does not call external providers, runtimes, adapters, or model APIs.
Generated orchestration artifacts are deterministic for identical inputs and do not embed wall-clock timestamps.
Task-derived artifacts remain byte-identical for identical inputs. Provenance-bearing artifacts vary with git/worktree source state: `manifest.json`, `phase_report.md`, and the artifact `README.md` record `source_commit`, `baseline_commit`, clean/dirty/unavailable state, and any tracked pending-change paths when present.
Generated phase reports do not use a placeholder commit value; tracked uncommitted changes are reported as `pending_change_state=tracked_changes_pending`.

```bash
python3 -m agent_office orchestrate run --task "Review this change safely" --mode static --out /tmp/ao-orch --json
python3 -m agent_office orchestrate inspect --path /tmp/ao-orch --json
python3 -m agent_office orchestrate validate --path /tmp/ao-orch --json
```

## Runtime Foundation Slice

The runtime foundation slice is local, deterministic, and static. It writes only a project-local workspace manifest, task graph, JSONL memory/events, and local/static task results. It does not read `.env`, print environment values, call providers, call models, start daemons, run background workers, or execute external adapters.

```bash
python3 -m agent_office runtime init --workspace .ai/workspaces/demo --goal "demo" --json
python3 -m agent_office runtime plan --workspace .ai/workspaces/demo --task "inspect:Inspect" --task "review:Review" --depends review:inspect --json
python3 -m agent_office runtime run --workspace .ai/workspaces/demo --adapter local-static --dry-run --json
python3 -m agent_office runtime run --workspace .ai/workspaces/demo --adapter local-static --execute-local --json
python3 -m agent_office runtime status --workspace .ai/workspaces/demo --json
python3 -m agent_office runtime packet --workspace .ai/workspaces/demo --json
python3 -m agent_office runtime replay --workspace .ai/workspaces/demo --json
python3 -m agent_office runtime evidence --workspace .ai/workspaces/demo --out .ai/workspaces/demo/evidence.json --format json --json
python3 -m agent_office runtime close --workspace .ai/workspaces/demo --out .ai/workspaces/demo/closure_packet.json --json
python3 -m agent_office runtime governance --workspace .ai/workspaces/demo --closure-packet .ai/workspaces/demo/closure_packet.json --evidence-out .ai/workspaces/demo/runtime-governance-evidence.json --format json
python3 -m agent_office runtime job create --workspace .ai/workspaces/demo --job-id demo-job --json
python3 -m agent_office runtime job status --workspace .ai/workspaces/demo --job-id demo-job --json
python3 -m agent_office runtime worker-adapter --list --json
python3 -m agent_office runtime worker-adapter --name external-prototype --describe --json
python3 -m agent_office runtime worker-gate --workspace .ai/workspaces/demo --adapter external-prototype --json
python3 -m agent_office runtime worker-packet --workspace .ai/workspaces/demo --adapter external-prototype --job-id demo-job --out .ai/workspaces/demo/worker-invocation-packet.json --json
python3 -m agent_office runtime worker-result intake --workspace .ai/workspaces/demo --packet .ai/workspaces/demo/worker-invocation-packet.json --result .ai/workspaces/demo/worker-result.json --json
python3 -m agent_office runtime worker-result replay --workspace .ai/workspaces/demo --packet .ai/workspaces/demo/worker-invocation-packet.json --result .ai/workspaces/demo/worker-result.json --json
python3 -m agent_office runtime worker-result audit-closure --workspace .ai/workspaces/demo --packet .ai/workspaces/demo/worker-invocation-packet.json --result .ai/workspaces/demo/worker-result.json --out .ai/workspaces/demo/worker-audit-closure.json --json
python3 -m agent_office runtime worker-result delivery-bundle --workspace .ai/workspaces/demo --packet .ai/workspaces/demo/worker-invocation-packet.json --result .ai/workspaces/demo/worker-result.json --audit-closure .ai/workspaces/demo/worker-audit-closure.json --out .ai/workspaces/demo/worker-delivery-bundle.json --json
python3 -m agent_office runtime worker-result reviewer-attestation --reviewer-artifact .ai/workspaces/demo/reviewer-output.md --marker R20_REVIEW_COMPLETE --out .ai/workspaces/demo/reviewer-attestation.json --json
python3 -m agent_office runtime worker-result closure-evidence --reviewer-attestation .ai/workspaces/demo/reviewer-attestation.json --out .ai/workspaces/demo/closure-evidence.json --json
python3 -m agent_office runtime worker-result merge-readiness --delivery-bundle .ai/workspaces/demo/worker-delivery-bundle.json --reviewer-attestation .ai/workspaces/demo/reviewer-attestation.json --closure-evidence .ai/workspaces/demo/closure-evidence.json --baseline <target-head> --source-branch <source-branch> --source-head <source-head> --target-branch phase6/mainline --out .ai/workspaces/demo/merge-readiness.json --json
python3 -m agent_office runtime worker-result delivery-gate --merge-readiness .ai/workspaces/demo/merge-readiness.json --out .ai/workspaces/demo/delivery-gate.json --json
python3 -m agent_office runtime worker-result rejection-packet --delivery-gate .ai/workspaces/demo/delivery-gate.json --out .ai/workspaces/demo/rejection-packet.json --json
python3 -m agent_office runtime worker-result audit-replay --packet .ai/workspaces/demo/rejection-packet.json --out .ai/workspaces/demo/audit-replay.json --json
python3 -m agent_office runtime worker-result provenance-manifest --reviewer-attestation .ai/workspaces/demo/reviewer-attestation.json --closure-evidence .ai/workspaces/demo/closure-evidence.json --merge-readiness .ai/workspaces/demo/merge-readiness.json --delivery-gate .ai/workspaces/demo/delivery-gate.json --rejection-packet .ai/workspaces/demo/rejection-packet.json --audit-replay .ai/workspaces/demo/audit-replay.json --out .ai/workspaces/demo/provenance-manifest.json --json
python3 -m agent_office runtime worker-result provenance-verify --manifest .ai/workspaces/demo/provenance-manifest.json --json
python3 -m agent_office runtime worker-result provenance-replay --manifest .ai/workspaces/demo/provenance-manifest.json --json
python3 -m agent_office runtime worker-result release-candidate --provenance-manifest .ai/workspaces/demo/provenance-manifest.json --out .ai/workspaces/demo/release-candidate.json --review-target "AgentOffice release candidate" --json
python3 -m agent_office runtime worker-result external-review-handoff --release-candidate .ai/workspaces/demo/release-candidate.json --out .ai/workspaces/demo/external-review-handoff.json --review-target "AgentOffice release candidate" --expected-marker R29_EXTERNAL_REVIEW_COMPLETE --attestation-import-path .ai/workspaces/demo/imported-reviewer-attestation.json --json
python3 -m agent_office runtime worker-result archive-index --release-candidate .ai/workspaces/demo/release-candidate.json --external-review-handoff .ai/workspaces/demo/external-review-handoff.json --out .ai/workspaces/demo/archive-index.json --json
python3 -m agent_office runtime worker-result archive-verify --index .ai/workspaces/demo/archive-index.json --json
python3 -m agent_office runtime worker-result reviewer-archive-import --reviewer-output .ai/workspaces/demo/external-reviewer-output.md --archive-index .ai/workspaces/demo/archive-index.json --expected-marker R29_EXTERNAL_REVIEW_COMPLETE --out .ai/workspaces/demo/reviewer-import.json --json
python3 -m agent_office runtime worker-result release-closure --release-candidate .ai/workspaces/demo/release-candidate.json --external-review-handoff .ai/workspaces/demo/external-review-handoff.json --archive-index .ai/workspaces/demo/archive-index.json --reviewer-import .ai/workspaces/demo/reviewer-import.json --provenance-manifest .ai/workspaces/demo/provenance-manifest.json --out .ai/workspaces/demo/release-closure.json --json
python3 -m agent_office runtime worker-result archive-replay --archive-index .ai/workspaces/demo/archive-index.json --release-candidate .ai/workspaces/demo/release-candidate.json --release-closure .ai/workspaces/demo/release-closure.json --out .ai/workspaces/demo/archive-replay.json --json
python3 -m agent_office runtime worker-result final-readiness --release-closure .ai/workspaces/demo/release-closure.json --archive-replay .ai/workspaces/demo/archive-replay.json --out .ai/workspaces/demo/final-readiness.json --json
python3 -m agent_office runtime worker-result review-recovery --release-closure .ai/workspaces/demo/release-closure.json --out .ai/workspaces/demo/review-recovery.json --json
python3 -m agent_office runtime worker-result compact-archive --archive-index .ai/workspaces/demo/archive-index.json --release-closure .ai/workspaces/demo/release-closure.json --archive-replay .ai/workspaces/demo/archive-replay.json --final-readiness .ai/workspaces/demo/final-readiness.json --out .ai/workspaces/demo/compact-index.json --json
python3 -m agent_office runtime worker-result compact-verify --index .ai/workspaces/demo/compact-index.json --json
python3 -m agent_office runtime worker-result rc-promotion-gate --final-readiness .ai/workspaces/demo/final-readiness.json --compact-index .ai/workspaces/demo/compact-index.json --release-closure .ai/workspaces/demo/release-closure.json --out .ai/workspaces/demo/promotion-gate.json --json
python3 -m agent_office runtime worker-result release-candidate-export --release-candidate .ai/workspaces/demo/release-candidate.json --archive-index .ai/workspaces/demo/archive-index.json --out .ai/workspaces/demo/release-candidate-export.json --json
python3 -m agent_office runtime worker-result promotion-evidence --release-candidate .ai/workspaces/demo/release-candidate.json --archive-index .ai/workspaces/demo/archive-index.json --release-closure .ai/workspaces/demo/release-closure.json --archive-replay .ai/workspaces/demo/archive-replay.json --final-readiness .ai/workspaces/demo/final-readiness.json --compact-index .ai/workspaces/demo/compact-index.json --promotion-gate .ai/workspaces/demo/promotion-gate.json --final-mainline <final-mainline-head> --out .ai/workspaces/demo/promotion-evidence.json --json
python3 -m agent_office runtime worker-result dry-run-publish --promotion-evidence .ai/workspaces/demo/promotion-evidence.json --release-candidate-export .ai/workspaces/demo/release-candidate-export.json --promotion-gate .ai/workspaces/demo/promotion-gate.json --candidate-name "AgentOffice release candidate" --target-branch phase6/mainline --target-commit <final-mainline-head> --out .ai/workspaces/demo/dry-run-publish.json --json
```

Worker invocation packets, worker result intake, replay, audit closure, delivery bundles, reviewer attestations, closure evidence imports, merge-readiness packets, delivery gates, rejection recovery packets, audit replays, and provenance manifests are static governance contracts. They do not call models, providers, browsers, shells, external workers, or real reviewers. Reviewer attestation reads a saved Markdown/JSON artifact and records its path, SHA256, byte count, verdict, marker, caveat, findings summary, reviewed artifacts, and safety caveat. Closure evidence imports only a JSON reviewer attestation into an explicit project-local output path. Merge readiness composes the delivery bundle, reviewer attestation, and closure evidence into a deterministic packet. Delivery gate consumes that merge-readiness packet and passes only when the reviewer attestation, closure evidence, worker replay/audit/delivery predicates, invocation refusal, external execution refusal, and provider/model/browser/shell false flags are all present. Rejection packets record exact reasons, next required evidence, and recovery guidance. Audit replay reads prior audit, merge-readiness, delivery-gate, or rejection packets without executing anything.

The provenance manifest chains the R23-R25 artifacts into a deterministic, tamper-evident sequence: reviewer attestation -> closure evidence -> merge-readiness -> delivery gate -> rejection recovery -> audit replay. Each manifest artifact entry records an artifact id, role, project-local path, SHA256, byte count, parent artifact ids, replay status, and readiness/gate predicate summary. `generated_at` is the stable value `deterministic-static-v1`, not a wall-clock timestamp.

`provenance-verify` rereads every artifact listed in the manifest and rejects cleanly when an artifact is missing, modified, replaced, malformed, symlinked, path-traversing, out of order, duplicated, cyclic, missing a required role, or carrying unsafe predicates such as `invocation_allowed=true`, `external_execution_refused=false`, or provider/model/browser/shell call flags set to true. Rejections return exact `rejection_reasons` plus `recovery_guidance`; for example, restore or regenerate the static evidence, regenerate the manifest with canonical parent links, then rerun `provenance-verify` and `provenance-replay`.

`provenance-replay` is read-only. It first verifies the manifest, then reports original readiness, artifact integrity, delivery gate pass/fail state, rejection/recovery status, replay readiness, and governance readiness. A tampered chain returns `chain_replay_ready=false` without a traceback.

`release-candidate` exports a deterministic release candidate package from a verified provenance manifest. The package records the provenance manifest, delivery gate, reviewer attestation, closure evidence, merge-readiness packet, rejection recovery packet, audit replay result, and tamper-evident replay summary. Each included artifact records role, project-local path, SHA256, byte count, parent linkage, archive readiness, and replay readiness. `generated_at` is the stable value `deterministic-static-v1`.

`external-review-handoff` writes a reviewer-ready packet from the release candidate package. It records the review target, artifact chain root and terminal artifact, included evidence list, integrity verification and replay instructions, expected reviewer output marker, attestation import path, and the artifact-only caveat: reviewers must not claim VPS validation unless they actually ran it. This command does not call a reviewer, model, or provider.

`archive-index` writes a deterministic evidence archive index covering the release candidate package, artifact chain, and external review handoff. `archive-verify` rereads every indexed record and rejects cleanly on missing artifacts, SHA or byte-count mismatch, duplicate record ids, missing parents, required role gaps, stale package contents, malformed JSON, path traversal, symlinks, unsafe predicates, `archive_ready=false`, or `replay_ready=false`. Rejections include exact reasons plus recovery guidance: restore or regenerate the missing/tampered static evidence, regenerate the release candidate and archive index from the current provenance manifest, then rerun `archive-verify`.

`reviewer-archive-import` imports a saved external reviewer output artifact into the static archive chain. It accepts Markdown or JSON reviewer output, requires the expected marker, records verdict, caveat, findings summary, reviewed artifact chain, source marker, SHA256, byte count, role, parents, archive readiness, and replay readiness, and rejects empty, malformed, non-UTF-8, missing-marker, traversal, or symlinked inputs cleanly.

`release-closure` composes the release candidate package, external review handoff, archive index, reviewer import, and provenance manifest into a deterministic release closure bundle. It closes only when the reviewer verdict is `pass`, the expected marker matches, archive/provenance replay is ready, and all static refusal predicates remain intact. Failed or conditional reviewer verdicts produce a blocked closure with exact reasons and recovery guidance.

`archive-replay`, `final-readiness`, and `review-recovery` complete the static closure loop. Archive replay rechecks the archive index, release candidate package, and closure bundle. Final readiness emits `delivery_ready` and `promotion_ready` only when closure and replay pass. Review recovery records the failed-review evidence needed to import fixed reviewer output, regenerate closure, rerun replay, and recheck readiness.

`compact-archive` and `compact-verify` build and verify a long-term compact evidence index without dropping integrity fields: record id, role, path, SHA256, byte count, parents, source marker, archive readiness, replay readiness, and terminal status are retained. Verification rejects duplicate ids, missing parents, missing roles, tamper, malformed JSON, traversal, symlinks, and bad static predicates.

`rc-promotion-gate` consumes final readiness, compact archive verification, and release closure evidence to write a static promotion packet. It never publishes a release, creates a tag, changes the default branch, or calls a provider/model/browser/shell. Pass output sets `promotion_ready=true`; failures include exact reasons and recovery guidance.

`release-candidate-export` rereads the release candidate package plus archive index and writes a reviewer-ready export packet with a stable manifest, digest, record count, expected roles, and readiness summary. It rejects duplicate roles, missing roles, malformed JSON, traversal paths, tampered records, and unsafe static predicates cleanly without relying on unrelated untracked artifacts.

`promotion-evidence` summarizes release closure, archive replay, compact archive terminal status, promotion gate result, reviewed source/target/final-mainline refs, validation references, negative recovery coverage, and no-real-promotion proof into JSON or text. The command is still static release-preparation evidence only. `promotion_ready=true` means the evidence packet is ready for review; it is not a real release and it does not create a tag, create a GitHub release, push, or mutate the default branch.

`dry-run-publish` describes what a future explicitly authorized publish would require. It records target branch, target commit, candidate release id/name, source evidence references, promotion gate status, approval checklist, and required artifacts while keeping `would_create_tag=false`, `would_create_release=false`, `would_push=false`, and `would_change_default_branch=false`. Real release/tag/default-branch promotion remains a later independent gate requiring explicit authorization.


## v1 Final Delivery Packet

P49 is the final implementation batch for AgentOffice v1. It adds a deterministic final delivery packet and verifier so reviewers can inspect the v1 delivery state without running providers, runtimes, models, external workers, or adapters.

Generate the packet as JSON or reviewer-ready text:

```bash
python3 -m agent_office v1 final-delivery --json
python3 -m agent_office v1 final-delivery
python3 -m agent_office v1 final-delivery --out /tmp/agentoffice-v1-final-delivery.json --json
```

Verify a saved packet:

```bash
python3 -m agent_office v1 verify-final-delivery --path /tmp/agentoffice-v1-final-delivery.json --json
python3 -m agent_office v1 verify-final-delivery --path /tmp/agentoffice-v1-final-delivery.json
```

The packet top-level contract includes `schema_version`, `packet_type`, `phase`, `status`, `repo`, `delivery`, `contracts`, `validation`, `artifacts`, `review`, `merge_gate`, `safety`, `non_goals`, and `next_actions`. Text output contains `AGENTOFFICE_V1_FINAL_DELIVERY_PACKET`; verifier text emits `AGENTOFFICE_V1_FINAL_DELIVERY_VERIFY_PASS` or `AGENTOFFICE_V1_FINAL_DELIVERY_VERIFY_FAIL`.

## Post-v1 Release Operations

Post-v1 release operations add local-only verification surfaces for the v1.0.0 release archive and GitHub release readback evidence. These commands do not read `.env`, do not print environment variables, and do not call providers, runtimes, models, external workers, or adapters.

Verify the release archive and its sidecar checksum:

```bash
python3 -m agent_office v1 verify-release-archive --archive /opt/agent-office/agentoffice-v1.0.0-final-delivery-archive.tar.gz --sha256 /opt/agent-office/agentoffice-v1.0.0-final-delivery-archive.tar.gz.sha256 --json
python3 -m agent_office v1 verify-release-archive --archive /opt/agent-office/agentoffice-v1.0.0-final-delivery-archive.tar.gz --sha256 /opt/agent-office/agentoffice-v1.0.0-final-delivery-archive.tar.gz.sha256
```

Verify local GitHub release publish/readback evidence without making network requests:

```bash
python3 -m agent_office v1 verify-github-release-readback --dir /opt/agent-office/V1_0_0_GITHUB_RELEASE_API_LONGRUN_READBACK --json
python3 -m agent_office v1 verify-github-release-readback --dir /opt/agent-office/V1_0_0_GITHUB_RELEASE_API_LONGRUN_READBACK
```

Print the deterministic post-v1 roadmap packet:

```bash
python3 -m agent_office v1 post-v1-roadmap --json
python3 -m agent_office v1 post-v1-roadmap
```

Codex-only closure output files for the user-approved P49 path:

- `P49_CODEX_SELF_REVIEW_OUTPUT.md`
- `P49_CODEX_REVIEW_FIX_REPORT.md` only if the self-review requires a fix
- `P49_CODEX_MERGE_GATE_REPORT.md`
- `P49_V1_FINAL_RELEASE_DECLARATION.md` after mainline merge validation

External artifact review is not a prerequisite when the operator explicitly chooses Codex-only closure. Do not create, cite, or imply external reviewer output unless that review actually occurred and is saved as evidence.

Merge gate prerequisites:

1. P49 source branch is pushed.
2. P49 Codex self-review is complete.
3. Any required Codex review-fix delta is complete and validated.
4. Codex merge gate passes under explicit operator authorization.
5. v1 final release declaration happens only after merge and post-merge validation.

Safety constraints: the packet and verifier do not read `.env`, do not print environment variable values, do not trigger provider/runtime/adapter external behavior, do not tag, do not force push, and do not mutate the default branch.

## Claude Token Rule

Mock Claude reads only `final-for-claude.md`. P5-05 adds a staged real Claude final judge dry-run that can also review bounded staged artifacts under `.ai/context/`, `.ai/codex/`, and `.ai/grok/`.

- Claude does not read the full repository.
- Claude does not read full logs.
- Claude does not read the full diff.
- `final-for-claude.md` is capped at 4000 characters.
- Claude final judge dry-run writes only `.ai/claude/final-judge.md` and `.ai/claude/metadata.json`.
- Each task allows at most 2 rework rounds.

## Install

No third-party dependencies are required.

```bash
python -m pip install -e .
```

After install, the CLI command is:

```bash
agent-office --help
```

Without installation, use:

```bash
python -m agent_office --help
```

## Commands

```bash
agent-office new <TASK_ID>
agent-office context <TASK_ID> --mock
agent-office context <TASK_ID> --real --adapter gemini --timeout 120
agent-office implement <TASK_ID> --mock
agent-office implement <TASK_ID> --real --adapter codex --timeout 1200
agent-office redteam <TASK_ID> --mock
agent-office redteam <TASK_ID> --real --adapter grok --timeout 120
agent-office summarize <TASK_ID> --mock
agent-office final <TASK_ID> --mock
agent-office final <TASK_ID> --real --adapter claude --dry-run --timeout 120
agent-office judge <TASK_ID> --real --adapter claude --dry-run --timeout 120
agent-office status <TASK_ID>
agent-office run-demo <TASK_ID> --mock
agent-office run-staged <TASK_ID> --dry-run --reset
agent-office run-staged <TASK_ID> --dry-run --real --adapter gemini
agent-office adapters
agent-office doctor
agent-office doctor --adapter codex
agent-office doctor --adapter gemini
agent-office doctor --adapter grok
agent-office doctor --adapter claude
agent-office doctor --adapters
agent-office profiles --name lowest-cost --plan --audit
agent-office profiles --name lowest-cost --plan --audit --json
agent-office objectives --phase P6-10
agent-office objectives --phase P6-10 --json
agent-office orchestrate run --task "Review this change safely" --mode static --out /tmp/ao-orch --json
agent-office orchestrate inspect --path /tmp/ao-orch --json
agent-office orchestrate validate --path /tmp/ao-orch --json
agent-office runtime init --workspace .ai/workspaces/demo --goal "demo" --json
agent-office runtime plan --workspace .ai/workspaces/demo --task "inspect:Inspect" --task "review:Review" --depends review:inspect --json
agent-office runtime run --workspace .ai/workspaces/demo --adapter local-static --dry-run --json
agent-office runtime run --workspace .ai/workspaces/demo --adapter local-static --execute-local --json
agent-office runtime status --workspace .ai/workspaces/demo --json
agent-office runtime packet --workspace .ai/workspaces/demo --json
agent-office runtime replay --workspace .ai/workspaces/demo --json
agent-office runtime evidence --workspace .ai/workspaces/demo --out .ai/workspaces/demo/evidence.json --format json --json
agent-office runtime close --workspace .ai/workspaces/demo --out .ai/workspaces/demo/closure_packet.json --json
agent-office profiles --plan --audit
agent-office profiles --plan --audit --json
agent-office doctor --profiles
agent-office doctor --json
python -m agent_office.doctor --adapters
python -m agent_office.doctor --profiles
agent-office run-bundle preview --objective P6-17 --profile lowest-cost --json
agent-office run-bundle validate --path .ai/runs/<RUN_ID> --json
agent-office run-bundle status --path .ai/runs/<RUN_ID> --json
agent-office run-bundle handoff --path .ai/runs/<RUN_ID> --json
agent-office run-bundle review --path .ai/runs/<RUN_ID> --json
agent-office run-bundle gate --path .ai/runs/<RUN_ID> --json
agent-office run-bundle workflow --path .ai/runs/<RUN_ID> --json
agent-office run-bundle export-review --path .ai/runs/<RUN_ID> --out /tmp/agentoffice-review.md
agent-office run-bundle export-review --path .ai/runs/<RUN_ID> --out /tmp/agentoffice-review.md --json
```

## State Machine

```text
CREATED
CONTEXT_READY
IMPLEMENTED
REVIEWED
SUMMARIZED
CLAUDE_DECIDED
APPROVED
REQUEST_CHANGES
REJECTED
```

`CLAUDE_DECIDED` is recorded in `task.json` history. The task state then moves to one of:

- `APPROVED`
- `REQUEST_CHANGES`
- `REJECTED`

## Mock Demo

```bash
agent-office run-demo demo-task --mock
```

or:

```bash
python -m agent_office run-demo demo-task --mock
```

Repeat the same demo safely with `--reset`:

```bash
python -m agent_office run-demo demo-task --mock --reset
```

`--reset` deletes only `.ai/tasks/<TASK_ID>/` for the task being run, then recreates the deterministic mock workflow from scratch. It does not relax the state machine and does not affect other task directories.

To clean demo tasks manually:

```bash
rm -rf .ai/tasks/DEMO-*
```

## Staged Full Dry Run

P6-01 adds a dry-run orchestration command that only chains existing stages:

```bash
python -m agent_office run-staged <TASK_ID> --dry-run --reset
```

It runs:

```text
new -> context -> implement -> redteam -> summarize -> judge -> status
```

All stages are mock by default, even if adapter environment variables are present. To exercise one staged real dry-run adapter, enable exactly one adapter explicitly:

```bash
export AGENTOFFICE_GEMINI_MODE=real
export AGENTOFFICE_GEMINI_DRY_RUN=true
export GEMINI_API_KEY=replace-with-real-key-outside-git
python -m agent_office run-staged <TASK_ID> --dry-run --real --adapter gemini --reset
```

Use `codex`, `grok`, or `claude` in the same shape to exercise one corresponding stage. `run-staged` refuses `--real` without a single `--adapter`, refuses adapter selection without `--real`, and requires `--dry-run`.

Safety boundaries:

- No real provider request is sent while `--dry-run` is active.
- No patch is applied.
- No git commit is made.
- `.env` is not read and environment variable values are not printed.
- The existing task state machine is reused unchanged.
- Runtime artifacts stay under ignored `.ai/**` paths.
- Each `run-staged` invocation clears stale staged runtime directories: `.ai/context/`, `.ai/codex/`, `.ai/grok/`, `.ai/claude/`, and `.ai/finalize/`.
- Before a selected real dry-run stage, AgentOffice copies only the current task's existing artifacts into the matching staged directories so adapters do not review evidence from a previous task.

## Verify

```bash
bash scripts/verify.sh
bash scripts/smoke-test.sh demo-task
```

Both scripts are repeatable. `smoke-test.sh` runs the requested task with `--reset`; `verify.sh` uses a fixed local verification task and resets it before each run.

## Static Run Bundle Review Packet

P9 adds a read-only reviewer packet for static run bundles:

```bash
python -m agent_office run-bundle review --path .ai/runs/<RUN_ID>
python -m agent_office run-bundle review --path .ai/runs/<RUN_ID> --json
```

The JSON contract is deterministic and starts with:

```text
kind=static_run_bundle_review_packet
review_schema_version=1
schema_version=1
```

It summarizes run identity, objective/profile, bundle readiness, required review files, actor packet/result evidence, validation status, reviewer commands, reviewer contract, safety flags, execution boundary, and known limitations. It is stricter than handoff for reviewer workflow: `claude_review_ready` requires a valid bundle and reviewer-ready packets, while `judge_ready` also requires all actor result metadata to be present.

The action is static and local. It does not read `.env`, print environment values, execute actor artifacts, call providers, call adapters, call runtimes, create `.ai/` outputs, or mutate the bundle.

`run-bundle review` exits 0 when the bundle is readable. Automation should read `readiness.claude_review_ready` and `readiness.judge_ready` from the payload instead of treating the process exit code as review readiness.


## Static Run Bundle Closure Gate

P10 adds a deterministic local closure gate for reviewer and judge workflow state:

```bash
python -m agent_office run-bundle gate --path .ai/runs/<RUN_ID>
python -m agent_office run-bundle gate --path .ai/runs/<RUN_ID> --json
```

The command reports whether the bundle is ready for Claude/reviewer review, whether reviewer and judge results have been intaked, whether judge can run, and the final static state: `pass`, `fail`, `blocked`, or `incomplete`. The JSON contract includes `schema_version`, `command`, `run_id`, `path`, `exists`, `valid_bundle`, `review_ready`, `review_intake`, `judge_ready`, `judge_intake`, `final_state`, `blocking_reasons`, `warnings`, `evidence`, `recommended_next_commands`, and `safety`.

Exit code `0` means the bundle was readable and valid enough to produce a gate payload. It does not mean the workflow passed: `final_state` may still be `fail`, `blocked`, or `incomplete`. Automation must inspect `final_state` and `blocking_reasons`, not the process exit code, before treating a run as accepted.

`run-bundle gate` reads only local bundle files and intaked `results/*.json` metadata. It does not read `.env`, print environment values, execute result artifacts, call providers, call adapters, call runtimes, create `.ai/` outputs, or mutate the bundle.

Current decision population limitation: `run-bundle intake` records artifact metadata and static safety metadata only; it does not record actor decision fields. `run-bundle gate` consumes static decision fields from `results/<actor>.json`, so those decisions currently must be authored externally, by actor tooling, or by a future intake extension.

## Static Run Bundle Workflow Summary

P11 adds a read-only closure summary layer over handoff, review, and gate state:

```bash
python -m agent_office run-bundle workflow --path .ai/runs/<RUN_ID>
python -m agent_office run-bundle workflow --path .ai/runs/<RUN_ID> --json
```

The JSON payload is deterministic and includes `schema_version`, `workflow_schema_version`, `valid_bundle`, `run_id`, `objective`, `profile`, `path`, `phase`, `summary`, `readiness`, `gate`, `actors`, `missing_actors`, `blocking_reasons`, `warnings`, `safety`, and `commands`. Text output is the same operator summary in a reviewer-friendly form: run identity, bundle validity, handoff/review/gate readiness, gate final state, safe-to-merge flag, next action, blocking reasons, warnings, and copy-paste commands.

`missing_actors` is informational. Not every missing actor result is a gate blocker; specifically, missing `codex` result metadata does not block `summary.safe_to_merge=true` when the reviewer/judge gate state is already pass. Automation should still rely on `summary.safe_to_merge`, `summary.final_state`, and `blocking_reasons` for decisions.

Exit code `0` means the workflow payload was readable. It does not mean the run is safe to merge. Automation must inspect `summary.safe_to_merge`, `summary.final_state`, and `blocking_reasons`.

Final-state precedence is deterministic:

- Invalid, missing, unsafe, malformed, or non-UTF8 bundles set `summary.final_state=invalid`, `summary.safe_to_merge=false`, and `summary.next_action=fix_bundle`.
- Gate `pass` sets `summary.safe_to_merge=true` and `summary.next_action=merge`.
- Gate `fail` sets `summary.safe_to_merge=false` and `summary.next_action=fix_actor_results`.
- Gate `blocked` sets `summary.safe_to_merge=false` and `summary.next_action=blocked`.
- Gate `incomplete` chooses the nearest missing closure step: missing review readiness or missing reviewer result maps to `run_review`; intaked reviewer/judge metadata without static decision fields maps to `fix_actor_results`; remaining missing gate closure maps to `run_gate`.

`run-bundle workflow` is static and local. It does not read `.env`, print environment values, execute actor artifacts, call providers, call adapters, call runtimes, create `.ai/` outputs, write `.ai/runs/*`, or mutate bundle/result/artifact files. It inherits the current gate/intake limitation: intake records artifact and safety metadata only, while gate and workflow consume static decision fields that must currently be authored externally, by actor tooling, or by a future intake extension.

## Static Run Bundle Review Artifact Export

P12 adds a controlled local export for a single Markdown review artifact plus a matching SHA256 file:

```bash
python3 -m agent_office run-bundle export-review --path .ai/runs/<RUN_ID> --out /tmp/agentoffice-review.md
python3 -m agent_office run-bundle export-review --path .ai/runs/<RUN_ID> --out /tmp/agentoffice-review.md --json
```

The export turns the existing static bundle, handoff, review, gate, workflow, and result metadata into one reviewer-friendly Markdown file. It also writes `<out>.sha256`. `--out` is required so the command never defaults to writing a report in the repository root.

The `.sha256` sidecar stores the artifact basename, not an absolute path, for example:

```text
<sha256>  agentoffice-review.md
```

Run `sha256sum -c` from the artifact directory:

```bash
cd /tmp && sha256sum -c agentoffice-review.md.sha256
```

JSON and text output include the exact `sha256_verify_command`/verification command in this directory-aware form.

Safety boundary:

- No `.env` reads and no environment variable value printing.
- No provider, adapter, runtime, real runner, or model calls.
- No actor artifact execution and no actor artifact content copy; actor artifacts are represented by path, size, sha256, and static metadata only.
- No writes under `.ai/runs/*` and no mutation of bundle/result/source artifact files.
- Relative `--out` paths stay inside the project root; absolute `--out` paths are allowed for operator exports when the parent directory already exists.

Exit code `0` means the artifact and `<out>.sha256` were written. Exit code `2` means invalid input, unsafe path, missing bundle, invalid bundle, unsafe output, or I/O failure. JSON mode returns a stable error payload without traceback.

Operator workflow from Windows PowerShell:

```powershell
$dst = "$env:USERPROFILE\Desktop\<ARTIFACT_DIR>"
New-Item -ItemType Directory -Force -Path $dst
scp -o BatchMode=yes agentoffice-vps:/path/to/artifact.md $dst\
scp -o BatchMode=yes agentoffice-vps:/path/to/artifact.md.sha256 $dst\
cd $dst
Get-FileHash .\artifact.md -Algorithm SHA256
Get-Content .\artifact.md.sha256
# Compare the Get-FileHash Hash value to the first field in artifact.md.sha256.
```

When verifying on the VPS with `sha256sum -c`, first `cd` into the artifact directory because the sidecar intentionally uses the bare artifact basename.

Positive smoke recipe:

```bash
python3 -m agent_office run-bundle preview --objective P6-17 --profile lowest-cost --run-id EXPORT-REVIEW-SMOKE --out .tmp-export-review-smoke/bundle --json
python3 -m agent_office run-bundle export-review --path .tmp-export-review-smoke/bundle --out /tmp/agentoffice-review.md --json
cd /tmp && sha256sum -c agentoffice-review.md.sha256
```

Negative smokes should still pass a valid `--out` path so the failing condition is the bundle path, not output validation:

```bash
python3 -m agent_office run-bundle export-review --path .ai/runs/MISSING --out /tmp/agentoffice-review-missing.md --json
python3 -m agent_office run-bundle export-review --path ../bad --out /tmp/agentoffice-review-unsafe.md --json
```

Upload both the Markdown artifact and `.sha256` file to Claude/reviewer so review can be artifact-based and hash-checkable. Claude/reviewer can review uploaded artifacts and hashes, but should not claim to have personally executed VPS validation unless it actually did.

## Claude Review Artifact Exporter

P14 adds a commit-range review artifact exporter for Claude artifact-based review:

```bash
python3 -m agent_office review-artifact export \
  --base <base_commit> \
  --review <review_commit> \
  --branch <branch_name> \
  --out /tmp/agentoffice-p14-review.md \
  --title "P14 Claude Review Artifact"

python3 -m agent_office review-artifact export \
  --base <base_commit> \
  --review <review_commit> \
  --branch <branch_name> \
  --out /tmp/agentoffice-p14-review.md \
  --title "P14 Claude Review Artifact" \
  --json
```

This is separate from `run-bundle export-review`. `run-bundle export-review` exports one static run bundle. `review-artifact export` exports a Git review packet for a base/review commit range, including diff evidence, changed-file snapshots from the review commit, captured validation transcripts, captured smoke transcripts, matching phase report snapshots when present, and the README snapshot.

Claude review boundary:

- Claude reviews the uploaded Markdown artifact and `.sha256` sidecar as artifact-based evidence.
- Claude must not claim it personally ran VPS validation unless it actually ran those commands itself.
- `validation_success=false` means one or more captured validation commands returned a nonzero exit. That is not an exporter traceback; it is evidence in the artifact.
- `smoke_success=false` means one or more captured smoke commands did not match the expected exit code. Failed smoke transcripts are included for review instead of being hidden.
- Reports must not claim validation passed when the artifact or JSON payload says `validation_success=false`.

Hard failures return exit code `2` with stable text/JSON and no traceback: malformed arguments, unresolved base/review commits, unsafe output paths, directory outputs, missing output parents, symlink outputs, Git identity failures, and artifact write/read/stat failures. Captured validation command failures and captured smoke command failures are not hard failures by default; they are recorded with command, expected exit, actual exit, stdout, and stderr.

The exporter artifact writer creates only the requested Markdown artifact and `<artifact>.sha256` sidecar. Captured validation commands may refresh ignored dry-run `.ai` task/runtime state; they must still not write `.ai/runs` or source files. The sidecar uses the bare artifact basename:

```text
<sha256>  agentoffice-p14-review.md
```

Run `sha256sum -c` from the artifact directory:

```bash
cd /tmp && sha256sum -c agentoffice-p14-review.md.sha256
```

## Phase Lifecycle Review System

The standard AgentOffice release flow is Codex-only by default:
Codex implementation -> codex-deliver safe report -> full validation -> authorized merge gate -> push mainline.

```bash
python3 -m agent_office review codex-deliver --help
python3 -m agent_office review codex-gate --help
python3 -m agent_office review reviewed-delivery --help
python3 -m agent_office review bundle --help
python3 -m agent_office review prompt --help
python3 -m agent_office review attest --help
python3 -m agent_office review merge-packet --help
```

Standard phase sequence:

1. Implement on the VPS and keep the tracked working tree scoped to the phase.
2. Run `review codex-deliver` in safe mode to write a stable JSON/text readiness report for the source and target heads.
3. Run Codex self-review with `git diff --name-status`, `git diff --stat`, `git diff --check`, and an out-of-scope change check.
4. Run full validation before commit and again inside the separately authorized merge gate.
5. Execute merge and push only in a separately authorized Codex merge gate.

`review codex-deliver` records phase/run identity, source and target heads, origin heads, tracked cleanliness, allowed untracked artifacts, changed files, diff stat, diff check, validation checklist, merge/push authorization, executed states, final target/origin status, blockers, and safety boundaries. Its default mode is safe and non-destructive; actual merge/push execution requires explicit `--merge-authorized`, `--push-authorized`, `--expected-source-head`, and `--expected-target-head` with all readiness gates passing.

`review reviewed-delivery` is a static orchestration wrapper for reviewed delivery closure. It verifies a saved Claude review output with `review attest`, generates a `review merge-packet`, then runs `review codex-deliver`; by default it is safe-mode only, and real merge/push still requires explicit `--merge-authorized --push-authorized` with strict source/target SHA guards.

It can also write a static evidence/readback bundle after orchestration:

```bash
python3 -m agent_office review reviewed-delivery ... --evidence-bundle-out /tmp/p38-reviewed-delivery-evidence.json --evidence-bundle-format json
python3 -m agent_office review reviewed-delivery ... --evidence-bundle-out /tmp/p38-reviewed-delivery-evidence.md --evidence-bundle-format text
```

`review codex-gate` remains a smaller static readiness report for a reviewed branch and commit range. It does not execute merge, push, tag, providers, runtimes, models, adapters, Claude output generation, Claude attestation generation, or Claude merge-packet generation. Codex-only does not mean skipping validation; merge gates remain explicit operator actions.

`review bundle`, `review prompt`, `review attest`, and `review merge-packet` remain available as optional/legacy/lower-level artifact-review tooling. They are not the default mandatory path for new implementation branches. `review-artifact` remains the lower-level commit-range artifact exporter, verifier, registry, and closure toolkit for existing review artifacts and run bundles.

The bundle and prompt commands prepare review materials; they do not call providers, runtimes, models, or adapters. Claude reviews uploaded bundles only as artifact-based evidence and must not claim it personally ran VPS tests unless it actually did. The attestation verifier checks stable structure signals such as `verdict: pass` and the expected review marker; it is optional/legacy evidence, not a default merge prerequisite. The merge-packet generator writes a checklist/report-ready Markdown packet only; it does not execute merge, push, tag, or default-branch mutation. The independent merge gate still performs preflight, validation, merge, post-merge validation, and push under explicit authorization.

Safety boundaries remain unchanged: lifecycle review commands refuse `.env` input paths, do not print environment variables, do not trigger real provider/model calls, reject symlink output paths, and return stable JSON/text errors without traceback.

JSON and text output include the exact directory-aware verification command as `sha256_verify_command` / `Verification command`.

Review gate status can be recorded directly in the artifact:

```bash
python3 -m agent_office review-artifact export \
  --base <base_commit> \
  --review <review_commit> \
  --branch <branch_name> \
  --out /tmp/agentoffice-review.md \
  --title "Review Artifact" \
  --gate-mode codex_interim \
  --claude-status pending \
  --codex-self-check-status pass \
  --json
```

Gate fields:

- `gate_mode`: `claude_pass`, `codex_interim`, `codex_self_check`, or `unknown`.
- `claude_review_status`: `pass`, `pending`, `unavailable`, `not_required`, or `unknown`.
- `codex_self_check_status`: `pass`, `fail`, `not_run`, or `unknown`.
- `codex_interim` means Codex self-check evidence is an interim gate only. It is not Claude review.
- `claude_status=pending` keeps `claude_artifact_review` in `follow_up_required`.
- `claude_pass` is only valid when `claude_review_status=pass`; self-check rejects mismatches to avoid a fake Claude PASS.

Default gate values are conservative and backward-compatible: `gate_mode=unknown`, `claude_review_status=unknown`, and `codex_self_check_status=not_run`.

JSON success output also includes stable self-audit fields for fallback review:

- `artifact_sha256` and the P14-compatible `sha256`
- `artifact_bytes` and the P14-compatible `byte_count`
- `validation_success`, `smoke_success`, and `command_failures`
- `section_audit` with section counts, snapshot counts, report count, README inclusion, and consistency warnings
- `evidence_consistency_warnings` for non-blocking report-vs-transcript mismatches

The Markdown artifact includes a `## Self-audit` section with the same review readiness summary. Validation command failures and smoke command failures are evidence, not exporter hard failures; the exporter exits 0 when it wrote the artifact and sidecar successfully, then records failed commands in `command_failures`.

Verify an exported artifact without Claude:

```bash
python3 -m agent_office review-artifact verify \
  --artifact /tmp/agentoffice-p14-review.md \
  --sha256 /tmp/agentoffice-p14-review.md.sha256 \
  --json
```

`review-artifact verify` is the repo-supported validation command. It verifies the sidecar from its own directory, the artifact hash, optional byte count claims in the sidecar, `MISSING_FILE_MARKERS: 0`, `EMPTY_SECTION_MARKERS: 0`, and all required sections. Exit code `0` means the artifact passed verification. Exit code `2` means stable JSON with `valid=false`, `failures`, and no traceback.

`review-artifact self-check` remains supported with the same arguments and output contract:

```bash
python3 -m agent_office review-artifact self-check --artifact /tmp/agentoffice-p14-review.md --sha256 /tmp/agentoffice-p14-review.md.sha256 --json
```

Verification is version-aware for artifacts generated before the `## Review gate status` section existed. A legacy artifact can pass only when SHA256 verification succeeds, marker counts are zero, pre-P16 core sections are present, and no empty-section markers are present. Legacy pass output is explicit: `legacy_artifact=true`, `legacy_gate_status_missing=true`, `warnings` includes `legacy_gate_status_missing`, and `follow_up_required` includes `claude_artifact_review`. This is not a Claude PASS and must not be treated as `gate_mode=claude_pass`; it means the historical artifact is intact and still needs Claude artifact-review follow-up. P15 post-merge artifact continuity checks are expected to pass in this legacy mode with that caveat.

Claude unavailable fallback:

- Run the Codex self-check gate and `review-artifact verify`.
- Treat that as an interim gate only.
- Still prefer Claude artifact review before merge when Claude is available.

Post-merge / pending Claude workflow:

- Generate a post-merge artifact with `--gate-mode codex_interim --claude-status pending --codex-self-check-status pass`.
- Run `review-artifact verify` and keep the JSON output with the merge report.
- Mark the merge report as Claude pending; do not claim Claude executed validation if Claude only reads the artifact later.
- When Claude is available, upload the same Markdown artifact and `.sha256` sidecar for artifact review.
- Save Claude's full review report for humans, but close the pending gate with a short Claude PASS attestation.
- A later Claude PASS attestation can close the pending `claude_artifact_review` follow-up.

Close a pending Claude artifact review after Claude recovers:

```bash
cat >/tmp/claude-pass-attestation.md <<'EOF'
# AgentOffice Claude Review Attestation

verdict: PASS
reviewer: claude
attestation_type: real
artifact_reviewed: agentoffice-review.md
artifact_sha256: <artifact_sha256>
review_marker: P19_REAL_ARTIFACT_REVIEW_COMPLETE
notes: artifact-based Claude review; Claude did not run VPS commands unless stated in the source report

P19_REAL_ARTIFACT_REVIEW_COMPLETE
EOF

python3 -m agent_office review-artifact close-pending \
  --artifact /tmp/agentoffice-review.md \
  --sha256 /tmp/agentoffice-review.md.sha256 \
  --claude-attestation /tmp/claude-pass-attestation.md \
  --source-review-report /tmp/claude-artifact-review-report.md \
  --out /tmp/agentoffice-claude-review-closure.md \
  --json

cd /tmp && sha256sum -c agentoffice-claude-review-closure.md.sha256
python3 -m agent_office review-artifact verify \
  --artifact /tmp/agentoffice-claude-review-closure.md \
  --sha256 /tmp/agentoffice-claude-review-closure.md.sha256 \
  --json
```

`close-pending` is local and static: it reads the prior artifact, the prior sidecar, a short Claude attestation, and optionally a saved full Claude review report; it writes only `<out>` and `<out>.sha256`; it does not call providers, adapters, runtimes, or `.ai/runs`. The closure artifact is deterministic and does not include a wall-clock timestamp.

Verbose Claude review reports should not be passed directly as machine verdict input. Use `--source-review-report` to bind the full report path/hash and short snapshot for audit, then pass the short contract file with `--claude-attestation`. The deprecated `--claude-review` flag is kept only as an alias for the short attestation path.

Claude attestation requirements are intentionally small and conservative. The attestation must include explicit key/value lines for `verdict: PASS`, `reviewer: claude`, `attestation_type: real`, `artifact_sha256: <artifact_sha256>`, and `review_marker: <MARKER>`, plus the same `*_ARTIFACT_REVIEW_COMPLETE` / `*_EVIDENCE_CLOSURE_REVIEW_COMPLETE` marker as a standalone line. The attested artifact hash must match the interim artifact hash. Attestations with conditional pass, fail, unresolved blockers, a missing or mismatched standalone marker, an unknown reviewer, an unknown attestation type, or an artifact hash mismatch are rejected with exit code `2`, stable JSON, and no traceback.

Attestation types:

- `real`: production closure evidence from an actual Claude artifact review. Verification requires `real_closure=true` and `fixture_only=false`.
- `fixture`: smoke-test-only closure evidence. It requires `--allow-fixture-attestation`, records `real_closure=false` and `fixture_only=true`, emits `fixture_only_closure`, and must not be used as real production Claude closure.

Closure artifacts currently keep the `P18_CLAUDE_PENDING_REVIEW_CLOSURE_ARTIFACT_COMPLETE` artifact-end marker for P18 self-check compatibility. P19 evidence-completion packets use their own `P19_REVIEW_FIX_EVIDENCE_COMPLETE` footer marker.

Gate status meanings:

- `codex_interim`: Codex self-check evidence allowed progress only as an interim gate; Claude artifact review remains pending.
- `claude_pending`: operator shorthand for a `codex_interim` artifact whose `follow_up_required` still includes `claude_artifact_review`.
- `claude_pass`: Claude artifact review PASS attestation has closed the pending follow-up. Verification requires `claude_review_status=pass`, `pending_closed=true`, and `follow_up_required=[]`.
- Legacy artifact with Claude follow-up: a pre-P16 artifact without `## Review gate status` can pass continuity checks only as legacy; it is not Claude PASS until `close-pending` binds a real Claude PASS attestation into a closure artifact.

PowerShell artifact handoff flow:

```powershell
$dst = "$env:USERPROFILE\Desktop\agentoffice-review"
New-Item -ItemType Directory -Force -Path $dst
scp -o BatchMode=yes agentoffice-vps:/tmp/agentoffice-review.md $dst\
scp -o BatchMode=yes agentoffice-vps:/tmp/agentoffice-review.md.sha256 $dst\
# Upload both files to Claude for artifact review. Save Claude's full report as claude-artifact-review-report.md.
# Create claude-pass-attestation.md with the short contract above after Claude returns PASS.
scp -o BatchMode=yes $dst\claude-artifact-review-report.md agentoffice-vps:/tmp/
scp -o BatchMode=yes $dst\claude-pass-attestation.md agentoffice-vps:/tmp/
ssh -o BatchMode=yes agentoffice-vps "cd /opt/agent-office && python3 -m agent_office review-artifact close-pending --artifact /tmp/agentoffice-review.md --sha256 /tmp/agentoffice-review.md.sha256 --claude-attestation /tmp/claude-pass-attestation.md --source-review-report /tmp/claude-artifact-review-report.md --out /tmp/agentoffice-claude-review-closure.md --json"
scp -o BatchMode=yes agentoffice-vps:/tmp/agentoffice-claude-review-closure.md $dst\
scp -o BatchMode=yes agentoffice-vps:/tmp/agentoffice-claude-review-closure.md.sha256 $dst\
```

Claude caveat: the closure records Claude's artifact review attestation. It does not prove Claude personally ran VPS validation unless the Claude source report explicitly says so.

PowerShell download and local check:

```powershell
$dst = "$env:USERPROFILE\Desktop\agentoffice-review"
New-Item -ItemType Directory -Force -Path $dst
scp -o BatchMode=yes agentoffice-vps:/tmp/agentoffice-p14-review.md $dst\
scp -o BatchMode=yes agentoffice-vps:/tmp/agentoffice-p14-review.md.sha256 $dst\
cd $dst
Get-FileHash .\agentoffice-p14-review.md -Algorithm SHA256
Get-Content .\agentoffice-p14-review.md.sha256
# Compare Get-FileHash.Hash to the first field in the sidecar.
```

VPS verification with `sha256sum -c` proves the file matches the sidecar in that VPS directory. PowerShell `Get-FileHash` after `scp` proves the downloaded local copy matches the sidecar hash. Both checks use the same SHA256 value, but they verify different file copies.

## Objective Specs

P6-09 is the P6-10 objective spec bootstrap. It converts the completed P6-06/P6-07/P6-08 profile plan, doctor, and audit surfaces into a concrete P6-10 objective that can be inspected locally before implementation work starts.

P6-10 adds a static objective spec CLI:

```bash
python -m agent_office objectives --phase P6-10
python -m agent_office objectives --phase P6-10 --json
```

The P6-10 objective is to expose a provider-safe objective spec surface that documents:

- objective and source phases
- public CLI contract
- machine-readable JSON contract
- tests covering the contract
- validation commands for release gates
- safety boundaries

The JSON contract includes:

```text
kind, phase, title, status, objective, source_phases, cli_contract, json_contract, tests, validation, safety
```

`objectives` does not read `.env`, print environment values, execute adapters, send provider requests, write files, or create `.ai/` runtime artifacts.

## Adapter Diagnostics

List supported adapters without executing real providers:

```bash
python -m agent_office adapters
```

Check project and adapter configuration:

```bash
python -m agent_office doctor
python -m agent_office doctor --adapter codex
python -m agent_office doctor --adapter gemini
python -m agent_office doctor --adapter grok
python -m agent_office doctor --adapter claude
python -m agent_office doctor --adapters
python -m agent_office.doctor --adapters
python -m agent_office doctor --profiles
python -m agent_office.doctor --profiles
python -m agent_office doctor --json
```

`doctor` does not read `.env`, does not execute real Codex, Gemini, Grok, or Claude commands, does not create tasks, and does not print environment variable values. It reports only `configured=true` or `configured=false`.

The staged adapter table shows the safe mode registry:

```text
adapter | mode | dry_run | env_ok | fallback | status
gemini | mock | false | true | false | ok
codex | mock | false | true | false | ok
grok | mock | false | true | false | ok
claude | mock | false | true | false | ok
```

The static profile plan audit shows every built-in profile without selecting a runtime profile or executing adapters:

```text
profile | default | execution_enabled | provider_calls | artifact_writes | roles | status
lowest-cost | true | false | false | false | context:chatgpt-manual(manual), implement:codex(local-cli), review:chatgpt-manual(manual), judge:chatgpt-manual(manual) | ok
```

The profile plan contract audit checks the local plan payload against the P6-08 static contract:

```bash
python -m agent_office profiles --name lowest-cost --plan --audit
python -m agent_office profiles --name lowest-cost --plan --audit --json
python -m agent_office profiles --plan --audit
python -m agent_office profiles --plan --audit --json
```

It reports required contract fields, pass/fail checks, `provider_calls_count: 0`, and `provider/runtime/adapter execution: not triggered`. It does not read `.env`, print environment values, execute adapters, send provider requests, write files, or create `.ai/` runtime artifacts.

## Staged Real Adapter Mode Registry

All provider adapters default to `mode=mock`. Passing `--real` is not enough to run a provider. The matching adapter must also be explicitly staged with:

```bash
export AGENTOFFICE_GEMINI_MODE=real
export GEMINI_API_KEY=replace-with-real-key-outside-git
```

When an adapter is in `mode=real`, `dry_run` defaults to `true`. In dry-run mode AgentOffice validates configuration but does not send a provider request. To keep a workflow moving during staged tests, set fallback explicitly:

```bash
export AGENTOFFICE_GEMINI_DRY_RUN=true
export AGENTOFFICE_GEMINI_FALLBACK_TO_MOCK=true
python -m agent_office context <TASK_ID> --real --adapter gemini
```

The task continues with mock output and records `fallback_used=true` in the transition detail. If `fallback_to_mock=false`, the workflow fails safely.

Non-dry-run provider execution is rejected unless it is explicitly allowed for that adapter:

```bash
export AGENTOFFICE_CODEX_DRY_RUN=false
export AGENTOFFICE_CODEX_ALLOW_NON_DRY_RUN=true
```

Use the equivalent `AGENTOFFICE_CODEX_*`, `AGENTOFFICE_GROK_*`, and `AGENTOFFICE_CLAUDE_*` variables for the other adapters where applicable. The P5 dry-run adapters do not execute shell commands by default. This staged gate does not read `.env` and does not print environment values.

## Gemini Context Adapter

Mock mode remains the default context path:

```bash
python -m agent_office context <TASK_ID> --mock
```

The real Gemini adapter is available only for the `context` stage. In P5-02 it supports a safe dry-run path. Gemini does not modify code, does not execute commands, and does not make final decisions. It receives the task brief plus selected safe project context, then writes:

```text
.ai/context/gemini-context.md
```

The generated file must include these sections:

```text
# Gemini Context
## Task Summary
## Relevant Project Facts
## Current Architecture
## Safety Boundaries
## Files Reviewed
## Suggested Implementation Notes
## Risks / Unknowns
## Non-Goals
```

To enable Gemini real context dry-run:

```bash
export AGENTOFFICE_AGENT_MODE=real
export AGENTOFFICE_GEMINI_MODE=real
export AGENTOFFICE_GEMINI_DRY_RUN=true
export AGENTOFFICE_GEMINI_FALLBACK_TO_MOCK=true
export GEMINI_API_KEY=replace-with-real-key-outside-git
export AGENTOFFICE_GEMINI_TIMEOUT_SECONDS=120
export AGENTOFFICE_GEMINI_MAX_FILES=80
export AGENTOFFICE_GEMINI_MAX_INPUT_CHARS=20000
export AGENTOFFICE_GEMINI_MAX_OUTPUT_CHARS=12000
python -m agent_office context <TASK_ID> --real --adapter gemini --timeout 120
```

Dry-run validates `GEMINI_API_KEY` presence but sends no network request. The adapter metadata records `dry_run=true`, `real_request_sent=false`, and `output_path=.ai/context/gemini-context.md`.

The adapter refuses real mode when `GEMINI_API_KEY` is missing unless `AGENTOFFICE_GEMINI_FALLBACK_TO_MOCK=true`. With fallback enabled, the workflow continues with the deterministic mock context and records `fallback_used=true`.

Allowed input is limited to the task brief and safe project files such as `README.md`, `AGENTS.md`, `SPEC.md`, `docs/**`, `agent_office/**`, `tests/**`, `scripts/**`, `pyproject.toml`, `requirements.txt`, and `.env.example`. Gemini must not read `.env`, key files, token files, secret files, `.ai/logs/**`, `.ai/tmp/**`, `.ai/tasks/**`, backup archives, or unrelated projects.

Non-dry-run Gemini network calls remain guarded. Set `AGENTOFFICE_GEMINI_DRY_RUN=false` and `AGENTOFFICE_GEMINI_ALLOW_NON_DRY_RUN=true` only for a separately reviewed real API rollout.

Rollback to mock mode:

```bash
unset GEMINI_API_KEY
export AGENTOFFICE_GEMINI_MODE=mock
export AGENTOFFICE_AGENT_MODE=mock
python -m agent_office context <TASK_ID> --mock
```

## Codex Adapter

Mock mode remains the default and safest path:

```bash
python -m agent_office implement <TASK_ID> --mock
```

The real Codex adapter is available only for the `implement` stage. In P5-03 it is patch-only dry-run. It does not directly modify source files, does not execute commands, does not call OpenAI/Codex network APIs, and does not apply patches automatically.

To enable Codex real implement dry-run:

```bash
export AGENTOFFICE_AGENT_MODE=real
export AGENTOFFICE_CODEX_MODE=real
export AGENTOFFICE_CODEX_DRY_RUN=true
export AGENTOFFICE_CODEX_FALLBACK_TO_MOCK=true
export OPENAI_API_KEY=replace-with-real-key-outside-git
export AGENTOFFICE_CODEX_TIMEOUT_SECONDS=1200
python -m agent_office implement <TASK_ID> --real --adapter codex --timeout 1200
```

Dry-run validates `OPENAI_API_KEY` presence but sends no network request. It writes only:

```text
.ai/codex/patch.diff
.ai/codex/codex-report.md
.ai/codex/metadata.json
```

The generated patch is a proposal only. AgentOffice does not apply it, does not run `git apply`, and does not commit it. A human must review and apply any patch in a separate step.

The patch safety validator rejects patches that modify `.env`, add obvious secrets, touch private keys, delete guard tests, weaken adapter safety defaults, enable all real adapters, set `dry_run=false` by default, set `allow_non_dry_run=true` by default, set `can_execute_commands=true` by default, target paths outside the allowed review set, or include unsafe live trading action markers.

If `OPENAI_API_KEY` is missing and `AGENTOFFICE_CODEX_FALLBACK_TO_MOCK=true`, the workflow continues with the deterministic mock implementation and records `fallback_used=true`. If fallback is false, the workflow fails safely.

Rollback to mock mode:

```bash
unset OPENAI_API_KEY
export AGENTOFFICE_CODEX_MODE=mock
export AGENTOFFICE_AGENT_MODE=mock
python -m agent_office run-demo DEMO-FINAL --mock --reset
```

## Grok Red-Team Adapter

Mock mode remains the default review path:

```bash
python -m agent_office redteam <TASK_ID> --mock
```

The real Grok adapter is available only for the `redteam` stage. In P5-04 it is review-only dry-run. Grok does not modify code, does not generate patches, does not apply patches, does not execute commands, and does not call the xAI/Grok network API while `dry_run=true`.

Grok primarily reviews:

```text
.ai/context/gemini-context.md
.ai/codex/patch.diff
.ai/codex/codex-report.md
.ai/codex/metadata.json
```

It writes only:

```text
.ai/grok/redteam-report.md
.ai/grok/metadata.json
```

The generated review must include:

```text
# Grok Redteam Report
## Review Summary
## Inputs Reviewed
## Patch Risk Assessment
## Safety Issues
## Logic Issues
## Missing Tests
## Security Concerns
## Possible Regression Risks
## Recommendation
```

The recommendation is exactly one of:

```text
PASS_TO_CLAUDE
REQUEST_CODEX_REVISION
BLOCK
```

To enable Grok real redteam dry-run:

```bash
export AGENTOFFICE_AGENT_MODE=real
export AGENTOFFICE_GROK_MODE=real
export AGENTOFFICE_GROK_DRY_RUN=true
export AGENTOFFICE_GROK_FALLBACK_TO_MOCK=true
export XAI_API_KEY=replace-with-real-key-outside-git
export AGENTOFFICE_GROK_TIMEOUT_SECONDS=120
export AGENTOFFICE_GROK_MAX_INPUT_CHARS=24000
export AGENTOFFICE_GROK_MAX_OUTPUT_CHARS=12000
python -m agent_office redteam <TASK_ID> --real --adapter grok --timeout 120
```

Dry-run validates `XAI_API_KEY` presence but sends no network request. If `XAI_API_KEY` is missing and `AGENTOFFICE_GROK_FALLBACK_TO_MOCK=true`, the workflow continues with deterministic mock review and records `fallback_used=true`.

If no patch is available, Grok fails safely or falls back to mock depending on configuration. It must not invent a patch. Do not apply patches automatically and do not enable all real adapters at once.

Rollback to mock mode:

```bash
unset XAI_API_KEY
export AGENTOFFICE_GROK_MODE=mock
export AGENTOFFICE_AGENT_MODE=mock
python -m agent_office redteam <TASK_ID> --mock
```

## Claude Final Judge Adapter

Mock mode remains the default final decision path:

```bash
python -m agent_office final <TASK_ID> --mock
```

The real Claude adapter is available only for the `final` stage. P5-05 supports final-decision dry-run only. It does not send Anthropic API requests while `dry_run=true`.

Claude may review:

```text
.ai/finalize/final-for-claude.md
.ai/context/gemini-context.md
.ai/codex/patch.diff
.ai/codex/codex-report.md
.ai/codex/metadata.json
.ai/grok/redteam-report.md
.ai/grok/metadata.json
.ai/tasks/<TASK_ID>/final-for-claude.md
```

If `final-for-claude.md` is missing, the `judge` command can build a minimal final packet from existing staged Gemini/Codex/Grok artifacts. It does not invent missing evidence.

Claude must not modify source files, apply patches, commit, execute commands, run shell, or read `.env`, key files, token files, secret files, logs, tmp files, or unrelated projects.

The real Claude dry-run adapter writes only:

```text
.ai/claude/final-judge.md
.ai/claude/metadata.json
```

The generated report includes:

```text
# Claude Final Judge
## Decision
## Reasons
## Required Changes
## Risk Flags
## Evidence Reviewed
## Safety Notes
## Non-Goals
```

The decision is exactly one of:

```text
APPROVE
REQUEST_CHANGES
REJECT
```

The task state maps those to `APPROVED`, `REQUEST_CHANGES`, or `REJECTED`.

To enable Claude real final judge dry-run:

```bash
export AGENTOFFICE_AGENT_MODE=real
export AGENTOFFICE_CLAUDE_MODE=real
export AGENTOFFICE_CLAUDE_DRY_RUN=true
export AGENTOFFICE_CLAUDE_FALLBACK_TO_MOCK=true
export ANTHROPIC_API_KEY=replace-with-real-key-outside-git
export AGENTOFFICE_CLAUDE_TIMEOUT_SECONDS=120
export AGENTOFFICE_CLAUDE_MAX_INPUT_CHARS=16000
export AGENTOFFICE_CLAUDE_MAX_OUTPUT_CHARS=12000
python -m agent_office judge <TASK_ID> --real --adapter claude --dry-run --timeout 120
```

Dry-run validates `ANTHROPIC_API_KEY` presence but sends no network request. Metadata records `dry_run=true`, `real_request_sent=false`, `fallback_used=false`, `decision`, `risk_flags`, and `report_path=.ai/claude/final-judge.md`.

If `ANTHROPIC_API_KEY` is missing and `AGENTOFFICE_CLAUDE_FALLBACK_TO_MOCK=true`, the workflow continues with deterministic mock final output and records `fallback_used=true`. If fallback is false, the workflow fails safely.

Non-dry-run Claude API calls remain guarded and are not implemented in P5-05. Set `AGENTOFFICE_CLAUDE_DRY_RUN=false` and `AGENTOFFICE_CLAUDE_ALLOW_NON_DRY_RUN=true` only in a separately reviewed future phase with mocked tests first.

Rollback to mock mode:

```bash
unset ANTHROPIC_API_KEY
export AGENTOFFICE_CLAUDE_MODE=mock
export AGENTOFFICE_AGENT_MODE=mock
python -m agent_office final <TASK_ID> --mock
```

When Claude returns `REQUEST_CHANGES`, use the required changes and risk flags as the next Codex input. The existing max rework limit remains 2 rounds.

## Docs

- `docs/architecture.md`: system shape and role boundaries.
- `docs/task-protocol.md`: `.ai/tasks/<TASK_ID>/` file protocol.
- `docs/agent-roles.md`: Gemini, Codex, Grok Build, and Claude Code responsibilities.
- `docs/adapter-doctor.md`: safe adapter diagnostics.
- `docs/plans/gemini-adapter-implementation-plan.md`: Gemini adapter plan and Phase 2 notes.
- `docs/real-agent-integration-plan.md`: real adapter rollout plan and Phase status.
- `deploy/deploy.md`: VPS deployment notes for a human operator.
- `deploy/systemd.service.example`: example unit file only.

## MVP Boundaries

- Real provider calls are intentionally limited to Gemini `context`, Codex `implement`, Grok `redteam`, and Claude `final` adapters when explicitly enabled.
- No real keys are read or printed.
- The orchestrator owns task state, queue discipline, logs, and artifact management.

## Artifact Registry, Lifecycle, and Evidence Export

AgentOffice includes a static local artifact registry for release-review evidence. It does not call providers, adapters, runtimes, models, or the network; it does not read `.env`, print environment variables, follow symlinks, or read `.git` contents. Single-file content reads are capped at 1 MiB; oversized files are recorded with warnings instead of failing the scan.

Registry commands:

```bash
python3 -m agent_office review-artifact registry --help
python3 -m agent_office review-artifact registry list --json
python3 -m agent_office review-artifact registry list --root /tmp/some-fixtures --json
python3 -m agent_office review-artifact registry inspect --path /tmp/agentoffice-review.md --json
python3 -m agent_office review-artifact registry status --json
```

Default registry scan locations:

- `/tmp/agentoffice-*.md`
- `/tmp/agentoffice-*.json`
- `/tmp/agentoffice-*.sha256`
- `/opt/agent-office/*REPORT.md`
- `.ai/runs/*`

Passing one or more `--root` values makes the scan repeatable and limited to those roots. Missing, empty, malformed, non-UTF8, bad JSON, bad SHA, or SHA-mismatched artifacts are reported as warnings/errors in JSON without traceback.

Lifecycle commands:

```bash
python3 -m agent_office review-artifact lifecycle --help
python3 -m agent_office review-artifact lifecycle status --json
python3 -m agent_office review-artifact lifecycle status --root /tmp/some-fixtures --json
python3 -m agent_office review-artifact lifecycle verify --json
python3 -m agent_office review-artifact lifecycle verify --root /tmp/some-fixtures --json
```

`lifecycle status` summarizes known artifacts from the registry. `lifecycle verify` reuses the existing `review-artifact verify`/self-check contract where possible and validates static run bundles with the existing run-bundle validation helper. It does not execute `close-pending`, does not close pending artifacts, and exits successfully after completing the scan; unverifiable or invalid artifacts are listed in the JSON `invalid` or `skipped` arrays.

Evidence package command:

```bash
python3 -m agent_office export-evidence --help
rm -rf /tmp/agentoffice-p23-evidence
python3 -m agent_office export-evidence --out /tmp/agentoffice-p23-evidence --json
test -s /tmp/agentoffice-p23-evidence/manifest.json
test -s /tmp/agentoffice-p23-evidence/README.md
```

`export-evidence` creates a reviewer-readable package with:

- `manifest.json`: command map, validation commands, safety boundaries, repo branch/commit metadata, registry summary, lifecycle summary, and one example artifact validation result.
- `README.md`: system overview, current CLI command map, validation list, safety boundaries, known limitations, registry/lifecycle summaries, example validation summary, and reviewer instructions.

Existing output directories are allowed. The command deterministically overwrites its own `manifest.json` and `README.md` files and leaves unrelated files in the output directory untouched. The package is intended for `/tmp` output unless a reviewer explicitly asks for a repository path.


### P35 codex-deliver dogfood

P35 dogfoods the one-click Codex delivery runner introduced by P34. The intended delivery sequence is:

1. create and validate a small source branch;
2. run `python3 -m agent_office review codex-deliver` in safe mode without merge/push authorization;
3. confirm the target branch remains unchanged;
4. rerun the same delivery with `--merge-authorized --push-authorized`;
5. verify local and remote `phase6/mainline` are synced to the resulting merge commit.

This flow remains static and local to git/repository state; it must not read `.env`, print environment variables, or trigger provider/model/runtime/adapter behavior.

## Autonomous Delivery Platform V1

AgentOffice includes a local-only autonomous delivery workflow for long-running, reviewable delivery branches. These commands do not read `.env`, print environment variables, call providers or models, mutate tags, create GitHub Releases, or merge into `phase6/mainline`.

Mission planning:

```bash
python3 -m agent_office autonomy plan --goal release-ops --json
python3 -m agent_office autonomy plan --goal post-v1 --json
python3 -m agent_office autonomy plan --goal autonomous-delivery --json
```

Run ledger and checkpoints:

```bash
python3 -m agent_office autonomy init --goal autonomous-delivery --path .ai/autonomy/runs/demo --json
python3 -m agent_office autonomy status --path .ai/autonomy/runs/demo --json
python3 -m agent_office autonomy checkpoint --path .ai/autonomy/runs/demo --name preflight --status passed --json
python3 -m agent_office autonomy report --path .ai/autonomy/runs/demo --json
```

Validation recorder:

```bash
python3 -m agent_office autonomy validate --path .ai/autonomy/runs/demo --suite minimal --json
python3 -m agent_office autonomy validate --path .ai/autonomy/runs/demo --suite release --json
python3 -m agent_office autonomy validate --path .ai/autonomy/runs/demo --suite full --json
```

`autonomy validate` only runs built-in allowlisted suites. It is not a general shell runner. Each command record stores the command text, argv, exit code, stdout path, stderr path, and duration in the run ledger.

Review and merge gate packets:

```bash
python3 -m agent_office autonomy review-packet --base <base_commit> --head HEAD --out /tmp/review-packet.md --json
python3 -m agent_office autonomy merge-packet --source phase52/autonomous-delivery-platform-v1 --target phase6/mainline --json
```

`review-packet` writes a Markdown bundle with commit list, diff stat, name-status, full diff, file snapshots, safety boundaries, caveats, and review focus. `merge-packet` emits source/target heads, merge-base, changed files, required validations, required reports, exact merge commands, post-merge validation, and rollback notes; it does not execute a merge.

Release operations handoff:

```bash
python3 -m agent_office v1 release-state --json
python3 -m agent_office v1 github-release-handoff --json
python3 -m agent_office v1 github-release-plan --json
python3 -m agent_office v1 release-candidate --version v1.1.0 --json
```

No-token release behavior is explicit: `skipped_no_token` remains `publish_state=skipped`, never `published`. Release handoff and plan packets are dry-run/operator packets and perform no GitHub writes.

Recommended operator workflow:

1. Create or resume a feature branch.
2. Generate an autonomy plan for the goal.
3. Initialize a run ledger under `.ai/autonomy/runs/<run-id>`.
4. Add checkpoints after preflight, implementation, validation, review packet, and merge packet steps.
5. Run `minimal` validation after each milestone and `full` validation before review.
6. Generate a review packet and merge packet.
7. Review the branch; merge only after explicit human authorization and a fresh merge gate.
