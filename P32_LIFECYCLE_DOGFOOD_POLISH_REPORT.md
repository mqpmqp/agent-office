# P32 Lifecycle Dogfood Polish Report

Marker: P32_LIFECYCLE_DOGFOOD_POLISH_COMPLETE

## Summary

P32 dogfoods the P31 lifecycle review system by making the default `review bundle --run-validation` evidence set include the focused review lifecycle CLI suite, and by documenting the standard operator sequence for future phases.

## Branch

phase32/lifecycle-dogfood-polish

## Baseline

1321cbe8a48282b2e9ac8d1e8eb0f4baa98094a0

## Original Reviewed Commit

089010f34f79d2685a30f5cebd3f48ff7384ca1d

## Review-Fix Commit

The review-fix commit is the commit containing `P32_CLAUDE_REVIEW_FIX_REPORT.md`; record and verify it with `git rev-parse HEAD` after the review-fix commit is created. The final readback and review-fix delta artifact provide the exact hash.

## Changed Files

- README.md
- agent_office/review_lifecycle.py
- tests/test_review_lifecycle_cli.py
- P32_LIFECYCLE_DOGFOOD_POLISH_REPORT.md

## Exact Delta Summary

- Added `tests.test_review_lifecycle_cli` to `DEFAULT_VALIDATION_COMMANDS` so lifecycle review bundles capture their own focused CLI suite by default.
- Added a focused test asserting the default validation evidence includes `python3 -m unittest tests.test_review_lifecycle_cli`.
- Documented the standard lifecycle path: `review bundle -> Claude artifact review -> review attest -> review merge-packet -> separately authorized merge gate`.
- Clarified that `review` is the phase lifecycle path and `review-artifact` remains the lower-level artifact exporter/verifier/registry/closure toolkit.

## Bundle-Captured Validation Commands

These commands are captured inside `/opt/agent-office/P32_REVIEW_ARTIFACT_BUNDLE.md` when `review bundle --run-validation` runs:

- python3 -m compileall agent_office tests
- python3 -m unittest
- python3 -m unittest discover -s tests -p 'test_*.py'
- python3 -m agent_office doctor --adapters
- ./scripts/verify.sh
- ./scripts/smoke-test.sh P6-PROFILES
- python3 -m agent_office run-staged P6-PROFILES --dry-run --reset
- python3 -m agent_office orchestrate --help
- python3 -m unittest tests.test_orchestration_cli
- python3 -m unittest tests.test_review_lifecycle_cli
- git diff --check

## Separately Run Codex Validation Commands

These commands were run by Codex during P32 validation but were not all captured inside the initial review bundle:

- python3 -m compileall agent_office tests
- python3 -m unittest
- python3 -m unittest discover -s tests -p 'test_*.py'
- python3 -m unittest tests.test_review_lifecycle_cli
- python3 -m agent_office doctor --adapters
- ./scripts/verify.sh
- ./scripts/smoke-test.sh P6-PROFILES
- python3 -m agent_office run-staged P6-PROFILES --dry-run --reset
- python3 -m agent_office review --help
- python3 -m agent_office review bundle --help
- python3 -m agent_office review prompt --help
- python3 -m agent_office review attest --help
- python3 -m agent_office review merge-packet --help
- git diff --check

## Validation Result Summary

All required P32 validation commands passed. Focused review lifecycle tests passed with 12 tests before the review-fix delta; the review-fix report records the updated focused test count and validation results.

## Dogfood Artifacts

P32 used `python3 -m agent_office review bundle --run-validation` to generate:

- /opt/agent-office/P32_REVIEW_ARTIFACT_BUNDLE.md
- /opt/agent-office/P32_CLAUDE_REVIEW_PROMPT.md

Claude review output was not fabricated. Attestation and merge-packet generation require a real saved Claude review output.

## Safety Summary

- `.env` not read.
- env vars not printed.
- no provider/model/runtime/adapter external behavior triggered.
- no merge performed.
- no force push.
- no tag.
- no historical P31 report or artifact rewritten.

## Known Follow-ups

- Upload the P32 review-fix delta artifact bundle to Claude for artifact-based review.
- Save the real Claude output and run `review attest` only after a true PASS output exists.
