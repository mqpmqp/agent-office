# P21-P23 Evidence Release Batch Report

## Status
Complete: P21 registry, P22 lifecycle status/verify, and P23 evidence package export are implemented and verified.

Completion marker: P21_P23_EVIDENCE_RELEASE_BATCH_COMPLETE

## Start branch / start HEAD
- start branch: phase6/mainline
- start HEAD: 2b9d6c16585199fe936d0de63c33fe6dbc17d9d2
- origin/phase6/mainline: 2b9d6c16585199fe936d0de63c33fe6dbc17d9d2

## New branch
- phase23/p21-p23-evidence-release-batch

## Implemented commands
- python3 -m agent_office review-artifact registry --help
- python3 -m agent_office review-artifact registry list --json
- python3 -m agent_office review-artifact registry list --root <path> --json
- python3 -m agent_office review-artifact registry inspect --path <artifact> --json
- python3 -m agent_office review-artifact registry status --json
- python3 -m agent_office review-artifact lifecycle --help
- python3 -m agent_office review-artifact lifecycle status --json
- python3 -m agent_office review-artifact lifecycle status --root <path> --json
- python3 -m agent_office review-artifact lifecycle verify --json
- python3 -m agent_office review-artifact lifecycle verify --root <path> --json
- python3 -m agent_office export-evidence --help
- python3 -m agent_office export-evidence --out <dir> --json
- python3 -m agent_office export-evidence --out <dir> --root <path> --json

## Changed files
- agent_office/artifact_registry.py
- agent_office/cli.py
- tests/test_evidence_cli.py
- README.md
- P21_P23_EVIDENCE_RELEASE_BATCH_REPORT.md

## P21 summary
Added a static local artifact registry with deterministic default scans for /tmp/agentoffice-* artifacts, root-level *REPORT.md files, and .ai/runs/* bundles. Repeatable --root scans bypass defaults. Registry entries include stable path/kind/existence/size/sidecar/detected_fields/warnings/errors keys and handle missing paths, empty roots, bad JSON, non-UTF8 content, bad sidecars, and SHA mismatch without traceback.

## P22 summary
Added lifecycle status and lifecycle verify on top of the registry. Status summarizes known, verified, pending-like, real closure, fixture-only, and pending-closed artifacts. Verify reuses the existing review-artifact self-check contract for markdown artifacts with sidecars and existing run-bundle validation for run bundles. It does not run close-pending or close any pending artifact. Scan completion exits 0; unverifiable or invalid artifacts are reported in JSON invalid/skipped results.

## P23 summary
Added export-evidence for a deterministic external review package. The command writes manifest.json and README.md, creates the output directory if missing, overwrites only known generated files, preserves unrelated output files, and is intended for /tmp output in this batch. Manifest and README omit wall-clock timestamps.

## Validation commands and results
- python3 -m compileall agent_office tests: passed
- python3 -m unittest: passed, 317 tests
- python3 -m unittest discover -s tests -p 'test_*.py': passed, 317 tests
- python3 -m unittest tests.test_evidence_cli -v: passed, 5 tests
- python3 -m unittest tests.test_review_artifact_cli tests.test_run_bundle_cli -q: passed, 124 tests
- python3 -m agent_office doctor --adapters: passed
- ./scripts/verify.sh: passed
- ./scripts/smoke-test.sh P6-PROFILES: passed
- python3 -m agent_office run-staged P6-PROFILES --dry-run --reset: passed
- python3 -m agent_office review-artifact --help: passed
- python3 -m agent_office review-artifact self-check --help: passed
- python3 -m agent_office review-artifact verify --help: passed
- python3 -m agent_office review-artifact close-pending --help: passed
- python3 -m agent_office review-artifact export --help: passed
- python3 -m agent_office review-artifact registry --help: passed
- python3 -m agent_office review-artifact registry list --json: passed
- python3 -m agent_office review-artifact registry status --json: passed
- python3 -m agent_office review-artifact lifecycle --help: passed
- python3 -m agent_office review-artifact lifecycle status --json: passed
- python3 -m agent_office review-artifact lifecycle verify --json: passed with non-fatal invalid/skipped artifact reporting
- python3 -m agent_office export-evidence --help: passed
- python3 -m agent_office export-evidence --out /tmp/agentoffice-p23-evidence --json: passed
- test -s /tmp/agentoffice-p23-evidence/manifest.json: passed
- test -s /tmp/agentoffice-p23-evidence/README.md: passed
- python3 -m agent_office review-artifact verify --artifact /tmp/agentoffice-p19-real-claude-closure.md --sha256 /tmp/agentoffice-p19-real-claude-closure.md.sha256 --json: passed because the P19 real closure artifact was present
- git diff --check: passed

## Evidence package output path
- /tmp/agentoffice-p23-evidence

## Known warnings / limitations
- Default registry scan reported 134 known artifacts: 8 closure artifacts, 73 report artifacts, 11 sha256 files, 11 json files, 19 markdown files, 9 run bundles, and 3 unknown entries.
- Registry scan recorded 10 warnings and 0 command-level errors from existing local artifacts.
- Lifecycle verify completed with checked_count=19, verified_count=11, invalid_count=8, skipped_count=115. Invalid/skipped entries are expected non-fatal scan results for historical artifacts that do not satisfy the current review-artifact or run-bundle verification contract.
- Historical untracked artifacts already present under /opt/agent-office were not cleaned up or staged.
- Artifact kind detection is intentionally conservative and marker/filename based.
- Files larger than 1 MiB are recorded but not content-inspected by registry scans.

## Safety constraints observed
- no .env read
- no env vars printed
- no provider/runtime/adapter external behavior
- no real model/provider calls
- no network access except git fetch during preflight and later git push
- no symlink following in registry scans
- no .git content scanning
- no close-pending execution from lifecycle commands
- no pending artifact auto-closure
- no /tmp evidence package added to git
- no force push, tag, or merge to mainline

## Push status placeholder
- push status: pending until commit and push complete

P21_P23_EVIDENCE_RELEASE_BATCH_COMPLETE
