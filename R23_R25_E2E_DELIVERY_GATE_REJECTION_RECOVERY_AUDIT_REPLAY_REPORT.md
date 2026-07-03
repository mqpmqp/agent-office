# R23-R25 E2E Delivery Gate / Rejection Recovery / Audit Replay Report

## Baseline
- target branch: `phase6/mainline`
- target_before: `b09c5b03d6e947d835fcd340a4f97afecdc15c9b`
- origin/phase6/mainline before work: `b09c5b03d6e947d835fcd340a4f97afecdc15c9b`
- previous marker: `R20_R22_REVIEWER_ATTESTATION_CLOSURE_EVIDENCE_MERGE_READINESS_COMPLETE_MAINLINE_SYNCED`

## Source Branch
- source branch: `phase45/r23-r25-e2e-delivery-gate-rejection-recovery`
- source head: set after commit `Add delivery gate rejection recovery replay`

## Changed Files
- `README.md`
- `agent_office/cli.py`
- `agent_office/runtime_foundation.py`
- `tests/test_runtime_foundation_cli.py`
- `R23_R25_E2E_DELIVERY_GATE_REJECTION_RECOVERY_AUDIT_REPLAY_REPORT.md`

No `agent_office/review_lifecycle.py` change was needed after inspection; codex-deliver remains the only merge/push gate.

## Implemented Commands
- `python3 -m agent_office runtime worker-result delivery-gate`
- `python3 -m agent_office runtime worker-result rejection-packet`
- `python3 -m agent_office runtime worker-result audit-replay`

All three commands are static and deterministic. They support `--help`; delivery gate and rejection packet support JSON/text artifact writes via explicit `--out`; audit replay supports JSON/text console output.

## Delivery Gate Contract
`delivery-gate` consumes an R20-R22 merge-readiness packet and verifies:
- reviewer attestation present
- closure evidence imported
- closure evidence gate-readable
- external-worker replay ready
- audit closure ready
- delivery bundle ready
- merge-readiness ready
- `invocation_allowed=false`
- `external_execution_refused=true`
- provider/model/browser/shell calls false

On pass it writes a deterministic delivery gate summary with `delivery_gate_pass=true`, `gate_status=pass`, empty rejection reasons, and `next_action=safe delivery`.

On fail it writes a deterministic rejected gate summary with exact `rejection_reasons`, `next_required_evidence`, `recovery_guidance`, and `next_action=recover required evidence`. Predicate failures are rejected cleanly without traceback.

## Rejection Recovery Contract
`rejection-packet` consumes a delivery gate summary and writes a deterministic rejection recovery packet. Rejected packets include:
- original readiness
- rejected flag
- exact rejection reasons
- next required evidence
- recovery guidance
- recovery status
- rerun command guidance
- replay/governance readiness fields

The recovery flow is static: regenerate or re-import fixed evidence, regenerate merge-readiness, rerun delivery-gate, then re-check readiness.

## Audit Packet Replay Contract
`audit-replay` reads prior static audit packets without executing anything. Supported inputs:
- worker audit closure packets
- merge-readiness packets
- delivery gate summaries
- rejection recovery packets

Replay output includes original readiness, rejection reasons, recovery status, `replay_ready`, and `governance_ready`.

## Positive Smoke Summaries
Temporary smoke workspace: `.ai/workspaces/R23-R25-SMOKE.*`; created by `mktemp` and removed by trap cleanup.

- delivery gate pass JSON: `pass=True`, `next_action=safe delivery`
- delivery gate pass text: artifact write confirmed
- delivery gate reject JSON: `pass=False`, reasons included `closure_evidence_not_imported` and `merge_readiness_not_ready`
- delivery gate reject text: artifact write confirmed
- rejection packet write: `rejected=True`, `recovery_status=blocked_until_evidence_fixed`
- audit replay JSON: `original_readiness=False`, `recovery_status=blocked_until_evidence_fixed`
- audit replay text: output confirmed
- recovery rerun JSON: `pass=True`, `next_action=safe delivery`
- recovery rerun text: artifact write confirmed

## Negative Smoke Summaries
- missing artifact -> `runtime_worker_delivery_gate_merge_readiness_missing`
- bad predicate -> rejection reasons included `merge_readiness_not_ready` and `provider_calls_not_false`
- malformed artifact -> `runtime_worker_delivery_gate_merge_readiness_invalid`

Unit tests also cover missing marker, empty artifact, path traversal, delivery gate rejects missing reviewer attestation, missing closure evidence, invocation allowed true, external execution refused false, and provider/model/browser/shell call flags true.

## Recovery Flow Summary
The recovery test flow created a rejected merge-readiness packet with missing closure evidence, ran delivery-gate to produce rejection reasons, wrote a rejection recovery packet, replayed that packet, re-imported fixed closure evidence, regenerated merge-readiness, and reran delivery-gate to readiness.

## Validation Commands and Outputs
- `python3 -m compileall agent_office tests` -> passed.
- `python3 -m unittest tests.test_runtime_foundation_cli` -> 33 tests passed.
- `python3 -m unittest tests.test_review_lifecycle_cli` -> 27 tests passed.
- `python3 -m unittest` -> 388 tests passed.
- `python3 -m unittest discover -s tests -p 'test_*.py'` -> 388 tests passed.
- `python3 -m agent_office doctor --adapters` -> gemini/codex/grok/claude mock adapters reported `ok`.
- `./scripts/verify.sh` -> `verify ok`.
- `./scripts/smoke-test.sh P6-PROFILES` -> `smoke test ok: P6-PROFILES`.
- `python3 -m agent_office run-staged P6-PROFILES --dry-run --reset` -> final status `APPROVED`.
- `python3 -m agent_office --help` -> help rendered successfully.
- `git diff --check` -> passed.

## Safety Boundaries
- `.env` was not read.
- Environment variables were not printed.
- No provider/model/browser/shell calls were triggered.
- No real external worker execution was triggered.
- No real reviewer/model/provider execution was triggered.
- No daemon, queue, DB, or vector store was introduced.
- No force push, tag, or default branch change is part of this implementation.
- Historical untracked artifacts were not staged, deleted, renamed, archived, or cleaned.

## Untracked Artifacts Note
The task preserved existing untracked artifacts. Validation used project scripts requested by the handoff and a unique temporary R23-R25 smoke workspace that was removed after smoke completion. No `git clean`, `git add .`, or `git add -A` was used.

## Codex-Deliver Safe Mode Result
Pending until after the source branch commit creates a stable source head. The required safe-mode report will be written to:

`/opt/agent-office/R23_R25_CODEX_DELIVER_SAFE_MODE_REPORT.md`

## Authorized Delivery Result
Pending on safe-mode readiness and clean validation. If authorized delivery succeeds, the required report will be written to:

`/opt/agent-office/R23_R25_CODEX_DELIVER_AUTHORIZED_REPORT.md`

## Final Marker
`R23_R25_E2E_DELIVERY_GATE_REJECTION_RECOVERY_AUDIT_REPLAY_SOURCE_READY_FOR_CODEX_DELIVER`
