# P30 Orchestration Provenance Doc Test Polish Report

Marker: P30_ORCHESTRATION_PROVENANCE_DOC_TEST_POLISH_COMPLETE

Branch: phase30/orchestration-provenance-doc-test-polish
Baseline: b3614d562595e17a7ad52e12221cc4c4ff27978c
Commit: final branch HEAD is emitted in the P30 closeout; this report is part of that branch history.
Pushed: yes; origin/phase30/orchestration-provenance-doc-test-polish was updated after validation.

## Changed files

- README.md
- tests/test_orchestration_cli.py
- P30_ORCHESTRATION_PROVENANCE_DOC_TEST_POLISH_REPORT.md

## What changed

- Qualified orchestration reproducibility wording in README without restructuring the document.
- Added focused unavailable source-state coverage in `tests/test_orchestration_cli.py` by patching `_git_output` to simulate git metadata unavailability.
- No orchestration implementation behavior changed.

## README wording summary

- Task-derived artifacts remain byte-identical for identical inputs.
- Provenance-bearing artifacts vary with git/worktree source state.
- The README now names `manifest.json`, `phase_report.md`, and artifact `README.md` as provenance-bearing files.
- The README now documents that `source_commit`, `baseline_commit`, clean/dirty/unavailable state, and tracked pending-change paths can vary by repo state.

## Unavailable source_state test summary

- The new test asserts unavailable git metadata returns `source_state=unavailable`.
- It verifies no traceback, no forged commit, and no clean/dirty misclassification.
- It confirms the manifest, CLI payload, and phase report keep the same stable source-state schema.

## Validation commands

- python3 -m compileall agent_office tests
- python3 -m unittest
- python3 -m unittest discover -s tests -p 'test_*.py'
- python3 -m agent_office doctor --adapters
- ./scripts/verify.sh
- ./scripts/smoke-test.sh P6-PROFILES
- python3 -m agent_office run-staged P6-PROFILES --dry-run --reset
- python3 -m agent_office orchestrate --help
- python3 -m unittest tests.test_orchestration_cli
- git diff --check

## Validation result summary

- compileall: passed
- unittest: passed, 328 tests
- unittest discover: passed, 328 tests
- doctor --adapters: passed
- verify.sh: passed
- smoke-test.sh P6-PROFILES: passed
- run-staged P6-PROFILES dry-run reset: passed
- orchestrate --help: passed
- focused orchestration CLI tests: passed, 11 tests
- git diff --check: passed

## Safety summary

- .env read: no
- env vars printed: no
- real provider/model calls: none
- external provider/runtime/adapter behavior triggered: no
- default branch changed: no
- merge performed: no
- force push: no
- tag: none

## Known follow-ups

- none required for P30.
