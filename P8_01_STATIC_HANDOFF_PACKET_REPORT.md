# P8-01 Static Handoff Packet Report

## Scope

P8-01 implemented a static reviewer-ready handoff packet surface for existing run bundles.
The implementation is read-only for handoff itself and does not enable execution.

## Branch And Revision

- Branch: phase8/p8-00-scope-spec-gate
- Starting HEAD: 426eab43d1ac0f1446c328581fc5f920f1608b74
- Work branch reused: yes
- Created new branch: no

## Changed Files

- agent_office/run_bundle.py
- agent_office/cli.py
- tests/test_run_bundle_cli.py
- P8_01_STATIC_HANDOFF_PACKET_REPORT.md

## Implemented CLI Contract

Command:

```text
python3 -m agent_office run-bundle handoff --path .ai/runs/P8-HANDOFF --json
```

Contract:

- Reads an existing bundle from `--path`.
- Requires the same static bundle safety validation as status/results surfaces.
- Does not create, modify, or normalize bundle files.
- Does not write artifacts or result files.
- Does not execute actors, providers, runtime adapters, real runners, or artifact content.
- Returns deterministic JSON by default when `--json` is supplied.
- Returns exit code 2 for invalid input without a traceback.

## Handoff JSON Fields

The JSON payload includes:

- `kind`: `static_run_bundle_handoff`
- `handoff_schema_version`: static handoff schema version
- `schema_version`: bundle schema version
- `path`: absolute bundle path
- `run_id`
- `objective`
- `profile`
- `objective_summary`
- `profile_summary`
- `required_files`
- `expected_files`
- `files`
- `actor_packet_identities`
- `actor_readiness`
- `result_presence`
- `validation_commands`
- `execution_enabled`
- `provider_calls`
- `execution_boundary`
- `safety_flags`
- `external_behavior_triggered`
- `artifact_content_executed`
- `read_only`
- `non_goals`
- `reviewer_guidance`
- `judge_guidance`
- `external_behavior`

## Static Handoff Semantics

- `codex`, `reviewer`, and `judge` packet identities are derived from existing packet metadata.
- Actor readiness reports whether each static packet is reviewer-ready and whether result metadata exists.
- Result presence is metadata-only and never executes or opens artifact payloads.
- Validation commands are generated from the bundle run id and bundle path.
- External behavior fields remain false for static handoff.

## Tests Added Or Extended

- Added deterministic JSON contract coverage for `run-bundle handoff`.
- Added read-only bundle snapshot coverage to prove handoff does not modify bundle files.
- Added result-presence coverage without relying on artifact source files after intake.
- Extended read-only command safety coverage to include `handoff`.
- Extended non-UTF-8 required file rejection coverage to include `handoff`.
- Added negative handoff cases for missing bundle, malformed bundle, path traversal, unsafe symlink bundle path, and symlinked required file.

## Validation Snapshot

All required validation commands completed successfully:

- `python3 -m unittest tests.test_run_bundle_cli -q`: passed, 40 tests
- `python3 -m compileall agent_office tests`: passed
- `python3 -m unittest`: passed, 228 tests
- `python3 -m unittest discover -s tests -p 'test_*.py'`: passed, 228 tests
- `python3 -m agent_office doctor --adapters`: passed; reported mock adapters as ok
- `./scripts/verify.sh`: passed; mock workflow reached APPROVED
- `./scripts/smoke-test.sh P6-PROFILES`: passed; mock workflow reached APPROVED
- `python3 -m agent_office run-staged P6-PROFILES --dry-run --reset`: passed; dry-run workflow reached APPROVED
- `python3 -m agent_office profiles --name lowest-cost --plan --json`: passed; plan remained execution disabled with no provider calls or artifact writes
- `python3 -m agent_office run-bundle --objective P6-17 --profile lowest-cost --run-id P8-HANDOFF --json`: passed; preview only, no artifact writes
- `python3 -m agent_office run-bundle --objective P6-17 --profile lowest-cost --run-id P8-HANDOFF --out .ai/runs/P8-HANDOFF --json`: passed; wrote static validation bundle
- `python3 -m agent_office run-bundle status --path .ai/runs/P8-HANDOFF --json`: passed; status ready with result presence false
- `python3 -m agent_office run-bundle handoff --path .ai/runs/P8-HANDOFF --json`: passed; emitted static handoff JSON
- `git diff --check`: passed

## Negative Validation

New handoff negatives are covered by `tests.test_run_bundle_cli` and return exit code 2 without tracebacks:

- missing bundle path
- malformed bundle missing required actor packet
- non-UTF-8 required file
- path traversal in required files
- symlink bundle path
- symlinked required file inside bundle

Existing intake/results/bundle-write negatives remain covered by the same focused test file and return exit code 2 without tracebacks:

- unknown actor
- missing artifact source
- artifact source outside project
- symlink artifact source
- directory artifact source
- missing bundle intake/results path
- malformed bundle intake/results path
- symlinked result target
- symlinked bundle write/create target
- missing run json
- malformed run json
- missing required judge packet
- `execution_enabled` set true
- non-empty `provider_calls`
- missing actor packet

## Safety Boundary Booleans

- `.env` read: no
- Environment variables printed: no
- Provider calls triggered: no
