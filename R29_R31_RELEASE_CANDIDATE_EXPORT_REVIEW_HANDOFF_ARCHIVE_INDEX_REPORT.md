# R29-R31 Release Candidate Export / External Review Handoff / Evidence Archive Index Report

## Scope

R29-R31 adds deterministic, static release-candidate and evidence-archive tooling for the runtime worker-result chain. The implementation does not execute providers, reviewers, browsers, shells, external workers, daemons, queues, databases, or vector stores.

Baseline before this branch:

- target branch: phase6/mainline
- target_before: 521860087686d8826231a4ea27829007d1f27c75
- source branch: phase47/r29-r31-release-candidate-export-archive-index
- previous phase marker: R26_R28_ARTIFACT_CHAIN_PROVENANCE_TAMPER_REPLAY_COMPLETE_MAINLINE_SYNCED

## Changed Files

- README.md
- agent_office/cli.py
- agent_office/runtime_foundation.py
- tests/test_runtime_foundation_cli.py
- R29_R31_RELEASE_CANDIDATE_EXPORT_REVIEW_HANDOFF_ARCHIVE_INDEX_REPORT.md

## Implemented Contracts

### R29 release candidate export

Added:

```bash
python3 -m agent_office runtime worker-result release-candidate
```

The command reads the static worker-result chain artifacts and emits JSON or text. It can also write the release-candidate package to a deterministic artifact path. The package includes deterministic records for provenance manifest, delivery gate, reviewer attestation, closure evidence, merge readiness, rejection recovery, and audit replay artifacts.

### R30 external review handoff

Added:

```bash
python3 -m agent_office runtime worker-result external-review-handoff
```

The command consumes a release-candidate package and emits JSON or text. It can write a deterministic external-review handoff artifact that preserves static refusal predicates, included artifacts, provenance linkage, replay summary, reviewer-facing caveats, and non-execution constraints.

### R31 evidence archive index and verification

Added:

```bash
python3 -m agent_office runtime worker-result archive-index
python3 -m agent_office runtime worker-result archive-verify
```

The archive index records the required roles:

- release_candidate
- provenance_manifest
- delivery_gate
- reviewer_attestation
- closure_evidence
- merge_readiness
- rejection_recovery
- audit_replay
- external_review_handoff

Each record includes role, record id, canonical path, parent role, parent id, byte count, and sha256. Verification checks archive integrity and produces deterministic pass/reject JSON or text with exact rejection reasons and recovery guidance.

## Positive Smoke Evidence

The R29-R31 smoke flow generated runtime worker-result evidence in a temporary project-local `.ai/workspaces/r29-r31-smoke-*` workspace and verified:

- release candidate JSON: `archive_ready=True`, `replay_ready=True`, `artifact_count=7`
- release candidate text: archive-ready line present
- external review handoff JSON: marker `R29_EXTERNAL_REVIEW_COMPLETE`, review caveat present
- external review handoff text: marker line present
- archive index JSON: `archive_ready=True`, `replay_ready=True`, `record_count=9`
- archive index text: archive-ready line present
- archive verify JSON: `archive_valid=True`, `archive_ready=True`, `replay_ready=True`
- archive verify text: archive-valid line present

## Negative Smoke Evidence

The smoke flow also verified deterministic rejection and recovery outputs for:

- tampered package and stale package: `sha256_mismatch:delivery_gate`, `byte_count_mismatch:delivery_gate`, `sha256_mismatch:release_candidate`, `stale_package:delivery_gate`
- missing release-candidate artifact: `artifact_missing:release_candidate`
- duplicate record id: `archive_record_count_mismatch`, `duplicate_record_id:provenance_manifest`
- stale package only: `stale_package:delivery_gate`
- malformed archive index: `runtime_worker_archive_index_invalid`
- CLI help coverage for `release-candidate`, `external-review-handoff`, `archive-index`, and `archive-verify`

Targeted unit tests cover additional rejection predicates, including missing package/handoff/archive data, sha mismatch, byte mismatch, duplicate record id, parent missing, required role missing, stale package, `archive_ready=false`, `replay_ready=false`, `invocation_allowed=true`, `external_execution_refused=false`, provider/model/browser/shell flags set true, malformed JSON, empty artifacts, and path traversal/symlink-style unsafe archive paths.

## Validation

Pre-commit validation passed on the VPS:

```bash
python3 -m compileall agent_office tests
python3 -m unittest tests.test_review_lifecycle_cli
python3 -m unittest tests.test_runtime_foundation_cli
python3 -m unittest
python3 -m unittest discover -s tests -p 'test_*.py'
python3 -m agent_office doctor --adapters
./scripts/verify.sh
./scripts/smoke-test.sh P6-PROFILES
python3 -m agent_office run-staged P6-PROFILES --dry-run --reset
python3 -m agent_office --help
git diff --check
```

Observed test counts:

- `tests.test_review_lifecycle_cli`: 27 tests
- `tests.test_runtime_foundation_cli`: 39 tests
- `python3 -m unittest`: 394 tests
- `python3 -m unittest discover -s tests -p 'test_*.py'`: 394 tests

## Safety Boundaries

Preserved boundaries:

- `.env` was not read.
- Environment variables were not printed.
- No provider/model/browser/shell adapters were invoked for real execution.
- No real external worker or reviewer execution was performed.
- No daemon, queue, database, or vector store was introduced.
- No force push, tag, or default branch change is required.
- Existing untracked artifacts were preserved and not staged.

## Git Hygiene

- Tracked-only cleanliness gate: `git status --short --untracked-files=no`
- Informational untracked artifact count before report: 514
- Staging plan: explicit touchpoints only; no `git add .` and no `git add -A`
- Delivery plan: `python3 -m agent_office review codex-deliver` safe-mode first, then authorized merge/push only if safe-mode is ready.

## Report Marker

R29_R31_RELEASE_CANDIDATE_EXPORT_REVIEW_HANDOFF_ARCHIVE_INDEX_READY_FOR_CODEX_DELIVER
