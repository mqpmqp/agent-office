# R26-R28 Artifact Chain Provenance / Tamper-Evident Replay Report

## Baseline
- target branch: `phase6/mainline`
- target_before: `49a09d07ffdfaa638132fe0959ed1b897364d4d2`
- origin/phase6/mainline before work: `49a09d07ffdfaa638132fe0959ed1b897364d4d2`
- previous marker: `R23_R25_E2E_DELIVERY_GATE_REJECTION_RECOVERY_AUDIT_REPLAY_COMPLETE_MAINLINE_SYNCED`

## Source Branch
- source branch: `phase46/r26-r28-artifact-chain-provenance-replay`
- source head: set after commit `Add artifact chain provenance replay`

## Changed Files
- `README.md`
- `agent_office/cli.py`
- `agent_office/runtime_foundation.py`
- `tests/test_runtime_foundation_cli.py`
- `R26_R28_ARTIFACT_CHAIN_PROVENANCE_TAMPER_REPLAY_REPORT.md`

No `agent_office/review_lifecycle.py` change was needed after inspection; codex-deliver remains the only merge/push gate.

## Implemented Commands
- `python3 -m agent_office runtime worker-result provenance-manifest`
- `python3 -m agent_office runtime worker-result provenance-verify`
- `python3 -m agent_office runtime worker-result provenance-replay`

`runtime worker-result audit-replay` also gained optional `--out` and `--format` support so audit replay can be captured as a JSON/text artifact for the provenance chain. Existing console-only audit replay behavior remains supported.

## Manifest Schema Summary
The provenance manifest is deterministic and static. It records:
- `kind=runtime_worker_provenance_manifest`
- marker `AGENT_OFFICE_ARTIFACT_CHAIN_PROVENANCE_MANIFEST`
- `generated_at=deterministic-static-v1`
- `chain_root=reviewer_attestation`
- `terminal_artifact=audit_replay`
- `terminal_readiness_required=true`
- canonical `required_role_order`
- one artifact entry per required role

Each artifact entry records:
- artifact id
- role
- project-local path
- SHA256
- byte count
- parent artifact ids
- replay status
- readiness/gate predicate summary

The canonical chain is:

`reviewer_attestation -> closure_evidence -> merge_readiness -> delivery_gate -> rejection_recovery -> audit_replay`

## Chain Verification Contract
`provenance-verify` rereads the manifest and every listed artifact. It verifies:
- manifest schema, marker, chain root, terminal artifact, required role order, and artifact count
- artifact existence, project-local paths, no traversal, no `.env`, no symlinked artifacts, file type, SHA256, and byte count
- required roles present exactly once
- duplicate artifact ids and duplicate roles rejected
- canonical role order
- parent linkage, missing parents, parent order, and cycles
- payload schema and markers for each role
- source linkage across parent artifacts
- replay/readiness predicates for terminal readiness
- `invocation_allowed=false`
- `external_execution_refused=true`
- provider/model/browser/shell flags false

Clean rejects return `chain_valid=false`, exact `rejection_reasons`, and recovery guidance. Malformed manifest JSON returns the structured error code `runtime_worker_provenance_manifest_invalid` without traceback.

## Tamper-Evident Replay Contract
`provenance-replay` is read-only. It verifies the manifest first, then reports:
- `chain_replay_ready`
- original readiness
- artifact integrity validity
- parent linkage validity
- role order validity
- readiness predicate validity
- delivery gate pass/fail state
- rejection/recovery status
- replay/governance readiness

Any missing, modified, replaced, malformed, reordered, wrongly linked, cyclic, or unsafe-predicate artifact makes replay return `chain_replay_ready=false` with exact reasons and recovery guidance.

## Positive Smoke Summaries
Temporary smoke workspace: `.ai/workspaces/r26-r28-smoke-*`; created by `/tmp/r26_smoke.sh` and removed by trap cleanup.

- manifest generate JSON: `artifact_count=6`, `terminal_readiness=True`
- manifest generate text: `terminal_readiness` line present
- manifest verify JSON: `chain_valid=True`, `artifact_integrity_valid=True`
- manifest verify text: `chain_valid` line present
- chain replay JSON: `chain_replay_ready=True`, `original_readiness=True`, `recovery_status=not_required`
- chain replay text: `chain_replay_ready` line present

## Negative Smoke Summaries
- tampered delivery gate SHA -> `sha256_mismatch:delivery_gate` and downstream parent source mismatch
- missing delivery gate artifact -> `artifact_missing:delivery_gate`
- wrong parent linkage -> `parent_linkage_invalid:delivery_gate`, `parent_missing:delivery_gate:missing_parent`
- replay from tampered manifest -> `chain_replay_ready=False`
- malformed manifest -> `runtime_worker_provenance_manifest_invalid`
- help checks passed for `provenance-manifest`, `provenance-verify`, and `provenance-replay`

Unit tests additionally cover byte count mismatch, terminal artifact mismatch, parent order invalid, duplicate artifact id, cycle detection, missing required role, `provider_calls=true`, `invocation_allowed=true`, path traversal, symlinked artifact rejection, empty manifest rejection, JSON/text positive outputs, and no traceback on clean rejects.

## Recovery Guidance Summary
Recovery guidance is deterministic and reason-driven:
- restore or regenerate missing static artifacts
- restore recorded bytes or regenerate the manifest from current artifacts after intentional regeneration
- regenerate the manifest with canonical role order and parent links
- restore static refusal predicates before regenerating downstream artifacts
- regenerate readiness, delivery gate, rejection recovery, and audit replay from fixed evidence
- rerun `runtime worker-result provenance-verify` and `runtime worker-result provenance-replay`

## Validation Commands and Outputs
- `python3 -m compileall agent_office tests` -> passed.
- `python3 -m unittest tests.test_runtime_foundation_cli` -> 36 tests passed.
- `python3 -m unittest tests.test_review_lifecycle_cli` -> 27 tests passed.
- `python3 -m unittest` -> 391 tests passed.
- `python3 -m unittest discover -s tests -p 'test_*.py'` -> 391 tests passed.
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
- Existing untracked artifacts were not staged, deleted, renamed, archived, or cleaned.

## Untracked Artifacts Note
Existing untracked artifacts were preserved. Final informational untracked artifact count before report write was `512`. No `git clean`, `git add .`, or `git add -A` was used. Smoke used a project-local temporary workspace with trap cleanup plus `/tmp/r26_*` smoke output files outside the repo.

## Codex-Deliver Safe Mode Result
Pending until after the source branch commit creates a stable source head. The required safe-mode report will be written to:

`/opt/agent-office/R26_R28_CODEX_DELIVER_SAFE_MODE_REPORT.md`

## Authorized Delivery Result
Pending on safe-mode readiness and clean validation. If authorized delivery succeeds, the required report will be written to:

`/opt/agent-office/R26_R28_CODEX_DELIVER_AUTHORIZED_REPORT.md`

## Final Marker
`R26_R28_ARTIFACT_CHAIN_PROVENANCE_TAMPER_REPLAY_SOURCE_READY_FOR_CODEX_DELIVER`
