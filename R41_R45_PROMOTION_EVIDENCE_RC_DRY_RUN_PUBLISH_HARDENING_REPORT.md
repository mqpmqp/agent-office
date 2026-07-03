# R41-R45 Promotion Evidence / RC Export / Dry-run Publish Hardening Report

marker: R41_R45_PROMOTION_EVIDENCE_RC_DRY_RUN_PUBLISH_HARDENING_COMPLETE_PENDING_DELIVERY

## Branches and Refs

- source_branch: phase49/r41-r45-promotion-evidence-rc-dry-run-publish-hardening
- source_head: pending commit at report write; final source head is recorded in the delivery summary
- target_branch: phase6/mainline
- target_before: e760b454dac64651d7c26b08249c6bddcb7df406
- final_mainline: pending codex-deliver authorized merge

## Changed Files

- README.md
- agent_office/cli.py
- agent_office/runtime_foundation.py
- tests/test_runtime_foundation_cli.py
- R41_R45_PROMOTION_EVIDENCE_RC_DRY_RUN_PUBLISH_HARDENING_REPORT.md

## Command Surface Added

- python3 -m agent_office runtime worker-result release-candidate-export
- python3 -m agent_office runtime worker-result promotion-evidence
- python3 -m agent_office runtime worker-result dry-run-publish

## Implementation Summary

- Added deterministic release candidate export packets with stable manifest digest, expected roles, record count, readiness summary, and clean archive validation.
- Added deterministic promotion evidence packets summarizing reviewed refs, release closure, archive replay, compact archive terminal status, promotion gate result, validation references, negative/recovery coverage, and no-real-promotion proof.
- Added dry-run publish packets that describe a possible future publish while forcing would_create_tag=false, would_create_release=false, would_push=false, and would_change_default_branch=false.
- Hardened archive and compact archive verification to reject duplicate roles in addition to duplicate record ids.
- Added JSON/text positive coverage, replay-style reread coverage, duplicate/missing/traversal/malformed clean rejects, promotion-not-ready dry-run rejection, and help coverage.

## Validation Commands

Passed:

- python3 -m compileall agent_office tests
- python3 -m unittest tests.test_runtime_foundation_cli
- python3 -m unittest tests.test_review_lifecycle_cli
- python3 -m unittest
- python3 -m unittest discover -s tests -p "test_*.py"
- python3 -m agent_office doctor --adapters
- ./scripts/verify.sh
- ./scripts/smoke-test.sh P6-PROFILES
- python3 -m agent_office run-staged P6-PROFILES --dry-run --reset
- python3 -m agent_office --help
- python3 -m agent_office runtime worker-result --help
- python3 -m agent_office runtime worker-result release-candidate-export --help
- python3 -m agent_office runtime worker-result promotion-evidence --help
- python3 -m agent_office runtime worker-result dry-run-publish --help
- git diff --check

## Test Counts

- focused runtime foundation CLI suite: 45 tests
- review lifecycle CLI suite: 27 tests
- full unittest suite: 400 tests
- unittest discover suite: 400 tests

## Smoke Summary

- doctor --adapters reported all built-in adapters ok in mock mode.
- verify.sh completed VERIFY-DEMO and printed verify ok.
- smoke-test.sh P6-PROFILES completed with smoke test ok.
- run-staged P6-PROFILES --dry-run --reset completed through APPROVED state.

## Negative Validation Summary

Covered by tests/test_runtime_foundation_cli.py:

- duplicate release candidate archive role rejects cleanly.
- required archive role missing rejects cleanly.
- archive record path traversal rejects cleanly.
- malformed archive JSON rejects cleanly.
- malformed reviewer JSON rejects cleanly.
- promotion gate not ready produces publish_ready=false and does not claim tag/release/push/default-branch action.
- all negative paths assert no traceback text.

## Safety Boundaries

Confirmed:

- no .env reads were added.
- no env var printing was added.
- no provider/model/browser/shell calls were added.
- no real external worker execution was added.
- no real reviewer/model/provider execution was added.
- no daemon/queue/DB/vector store was added.
- no force push/tag/default branch change occurred.
- no real release/tag/default branch promotion occurred.
- existing untracked artifacts were preserved and not staged.

## Git Status at Report Write

- current branch: phase49/r41-r45-promotion-evidence-rc-dry-run-publish-hardening
- tracked tree: dirty only with planned touchpoints before staging
- informational untracked artifact count before report write: 518
