# P9 Large AgentOffice Workflow Batch Report

## Branch

- Branch: `phase9/p9-large-agentoffice-workflow-batch`
- Baseline HEAD: `92e606e8ac929d3404ed1eedd593c0b2da1f5e6d`
- origin/phase6/mainline at start: `92e606e8ac929d3404ed1eedd593c0b2da1f5e6d`
- Final commit: assigned after this report is committed; immutable commit SHA is reported in the final completion response.

## Chosen P9 Target

Build a first-class, static Claude Code review packet for run bundles:

```text
python3 -m agent_office run-bundle review --path <bundle>
python3 -m agent_office run-bundle review --path <bundle> --json
```

## Why This Target

P8 completed static preview, handoff, validation, status, result intake, and human-readable handoff contracts. The remaining operator gap was a single deterministic surface that tells Claude Code exactly what to inspect, what evidence is present, which commands reproduce the review, and which safety boundaries must not move. A `review` action builds on P8 instead of adding runtime behavior or changing provider/adapter paths.

## Files Changed

- `agent_office/run_bundle.py`
- `agent_office/cli.py`
- `tests/test_run_bundle_cli.py`
- `README.md`
- `P9_LARGE_AGENTOFFICE_WORKFLOW_BATCH_REPORT.md`

## Implementation Summary

- Added `REVIEW_PACKET_SCHEMA_VERSION = 1`.
- Added `review_run_bundle_payload()` to compose a read-only review packet from existing handoff, validation, status, actor readiness, and result metadata.
- Added `format_run_bundle_review()` for deterministic text output.
- Added review helper contracts for required review files, reviewer commands, actor-specific review focus, reviewer obligations, preserved safety invariants, risk focus, and non-goals.
- Added `run-bundle review` CLI dispatch and help.
- Documented the review packet contract in README.
- Extended tests so `review` participates in read-only/no-write checks and non-UTF-8 expected-error coverage.

## CLI Contract Added

```text
python3 -m agent_office run-bundle review --path <bundle>
python3 -m agent_office run-bundle review --path <bundle> --json
```

Required input:

- `--path`: project-local static run bundle directory.

Expected behavior:

- Reads only static run-bundle metadata and actor result metadata.
- Emits text by default and deterministic JSON with `--json`.
- Exits `2` without traceback for missing bundle, unsafe path traversal, bad JSON, non-UTF-8, missing required files, and malformed bundle contracts.
- Does not write `.ai/runs/*`, mutate the bundle, execute artifacts, call providers, call runtimes, or call adapters.

## JSON/Text Contract Added

JSON top-level field order is pinned by tests:

```text
kind
review_schema_version
schema_version
path
run_id
objective
profile
review_goal
readiness
required_review_files
actor_evidence
validation
status
reviewer_commands
reviewer_contract
safety_flags
execution_boundary
external_behavior
read_only
execution_enabled
provider_calls
known_limitations
```

Key values:

- `kind=static_run_bundle_review_packet`
- `review_schema_version=1`
- `schema_version=1`
- `readiness.claude_review_ready=true` when bundle validation passes and actor packets are reviewer-ready.
- `readiness.judge_ready=true` only when all actor result metadata is present too.
- `execution_enabled=false`
- `provider_calls=[]`
- `read_only=true`

Text output starts with:

```text
AgentOffice static run bundle review packet
schema_version: 1
review_schema_version: 1
```

It includes stable headings for readiness, required review files, actor evidence, validation, status, reviewer commands, reviewer contract, safety flags, execution boundary, known limitations, and the final no-execution marker.

## Tests Added Or Changed

Added in `tests/test_run_bundle_cli.py`:

- `test_run_bundle_review_json_contract_is_static_and_deterministic`
- `test_run_bundle_review_text_contract_is_static_and_deterministic`
- `test_run_bundle_review_reports_result_evidence_without_reading_artifacts`
- `test_run_bundle_review_rejects_missing_bundle_without_traceback`
- `test_run_bundle_review_rejects_bad_bundle_without_traceback`
- `test_run_bundle_review_rejects_path_traversal_without_traceback`

Updated:

- read-only lifecycle test now includes `run-bundle review`.
- non-UTF-8 expected-error lifecycle coverage now includes `run-bundle review`.

## Validation Commands And Results

- `python3 -m unittest tests.test_run_bundle_cli -q`: PASS, ran 54 tests.
- `python3 -m compileall agent_office tests`: PASS.
- `python3 -m unittest`: PASS, ran 242 tests.
- `python3 -m unittest discover -s tests -p 'test_*.py'`: PASS, ran 242 tests.
- `python3 -m agent_office doctor --adapters`: PASS, all adapters mock/ok.
- `./scripts/verify.sh`: PASS, mock workflow reached `APPROVED`.

## Manual Smoke Commands And Results

Temporary bundle path:

```text
.ai/runs/P9-REVIEW-SMOKE
```

The path was removed after smoke validation and was not staged.

Commands/results:

- Create bundle with `run-bundle preview --objective P6-17 --profile lowest-cost --run-id P9-REVIEW-SMOKE --out .ai/runs/P9-REVIEW-SMOKE --json`: PASS.
- `python3 -m agent_office run-bundle review --path .ai/runs/P9-REVIEW-SMOKE --json`: PASS; JSON kind, readiness, no-execution fields, and review command were asserted.
- `python3 -m agent_office run-bundle review --path .ai/runs/P9-REVIEW-SMOKE`: PASS; header, readiness, and no-execution marker were asserted.
- Missing path `.ai/runs/P9-MISSING`: PASS, exit `2`, no traceback.
- Traversal path `../outside-bundle`: PASS, exit `2`, no traceback.
- Bad JSON in `run.json`: PASS, exit `2`, no traceback.
- Cleanup of `.ai/runs/P9-REVIEW-SMOKE`: PASS.

## Known Limitations

- The review packet is static metadata only. It does not execute actors or artifact content.
- Actor result artifacts are represented by intake metadata. Review does not reread source artifact bytes.
- `claude_review_ready` and `judge_ready` intentionally differ. Claude review can proceed with a valid bundle and reviewer-ready packets; judge readiness also requires all actor result metadata.
- The report cannot embed the immutable SHA of the commit that contains itself. The final commit SHA is reported after commit creation.

## Claude Code Review Instructions

Please review:

- `agent_office/run_bundle.py`: new review payload, formatting, helper contracts, readiness semantics, JSON field order, and no-write behavior.
- `agent_office/cli.py`: `review` dispatch, help text, and expected exit `2` error surface through `AgentOfficeError`.
- `tests/test_run_bundle_cli.py`: deterministic JSON/text coverage, no-write snapshots, actor result metadata behavior after source artifacts are removed, and negative path coverage.
- `README.md`: public contract clarity and safety statements.

Focus on:

- Whether `review` accidentally widens execution behavior or reads artifact contents.
- Whether `claude_review_ready` vs `judge_ready` is clear and useful.
- Whether helper composition from handoff/validate/status can hide an inconsistent edge case.
- Whether expected user errors remain uniform and traceback-free.
- Whether any historical P8 contract was weakened.

## Safety Confirmation

- `.env` not read.
- Environment variable values not printed.
- Provider external behavior not triggered.
- Runtime external behavior not triggered.
- Adapter external behavior not triggered, except the allowed `doctor --adapters` mock status check.
- Real runner not triggered.
- Artifact content not executed.
- No tag created.
- No force push.
- Not merged to `phase6/mainline`.
- Historical untracked reports, audit bundles, tarballs, sha256 files, and audit directories ignored and not committed.
- `.ai/runs/*` temporary smoke bundle removed and not committed.
