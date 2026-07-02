# R20-R22 Reviewer Attestation / Closure Evidence / Merge Readiness Report

## Baseline
- target branch: `phase6/mainline`
- target_before: `9d1659f69e541659a51af8d4caf3f19f76264bbb`
- origin/phase6/mainline before work: `9d1659f69e541659a51af8d4caf3f19f76264bbb`
- previous marker: `R17_R19_EXTERNAL_WORKER_REPLAY_AUDIT_CLOSURE_LOOP_COMPLETE_MAINLINE_SYNCED`

## Source Branch
- source branch: `phase44/r20-r22-reviewer-attestation-closure-merge-readiness`
- source head: set after commit `Add reviewer attestation closure merge readiness`

## Changed Files
- `README.md`
- `agent_office/cli.py`
- `agent_office/runtime_foundation.py`
- `tests/test_runtime_foundation_cli.py`
- `R20_R22_REVIEWER_ATTESTATION_CLOSURE_EVIDENCE_MERGE_READINESS_REPORT.md`

No `agent_office/review_lifecycle.py` change was needed after inspection; the existing codex-deliver workflow remains the delivery gate.

## Implemented Commands
- `python3 -m agent_office runtime worker-result reviewer-attestation`
- `python3 -m agent_office runtime worker-result closure-evidence`
- `python3 -m agent_office runtime worker-result merge-readiness`

All three commands support `--help`, `--json`, default text output, deterministic explicit `--out` writes, and clean JSON errors with exit code `2` when `--json` is used.

## Reviewer Attestation Contract
`reviewer-attestation` reads a saved reviewer artifact (`.md` or `.json`) from a project-local path and writes a deterministic reviewer attestation packet.

Packet fields include:
- reviewer artifact path, SHA256, and byte count
- verdict
- marker
- review type
- review caveat
- findings summary
- reviewed artifacts
- reviewed bundle summary
- safety caveat
- invocation refusal and provider/model/browser/shell false flags

Clean refusal/error coverage:
- missing reviewer artifact
- empty reviewer artifact
- missing marker
- malformed JSON
- non-UTF-8 artifact
- path traversal
- symlink input when supported by the platform

## Closure Evidence Import Contract
`closure-evidence` imports a JSON reviewer attestation into formal closure evidence at an explicit project-local output path.

Evidence fields include:
- reviewer attestation source path, SHA256, and byte count
- original reviewer artifact source
- verdict, marker, review type, findings summary, reviewed artifacts, reviewed bundle summary, and safety caveat
- `closure_evidence_imported=true`
- `gate_readable=true`
- `audit_replayable=true`
- invocation refusal and provider/model/browser/shell false flags

The command does not call providers, models, browsers, shells, real reviewers, daemons, queues, databases, or vector stores.

## Merge-Readiness Packet Contract
`merge-readiness` composes:
- R17-R19 external worker delivery bundle
- R20 reviewer attestation
- R21 closure evidence

Packet fields include:
- baseline, source branch, source head, target branch
- external worker replay readiness
- audit closure readiness
- reviewer attestation presence
- closure evidence import status
- delivery bundle readiness
- invocation_allowed=false
- external_execution_refused=true
- provider/model/browser/shell calls false
- validation commands
- next action: `safe delivery` when ready, otherwise `stop`

## JSON/Text Examples Summary
- reviewer attestation JSON reported `verdict=pass`, marker `R20_REVIEW_COMPLETE`, and provider/model/browser/shell calls false.
- reviewer attestation text wrote a reviewer-ready Markdown packet with artifact hash, byte count, verdict, marker, caveats, and reviewed artifacts.
- closure evidence JSON reported `closure_evidence_imported=true` and `gate_readable=true`.
- closure evidence text wrote a reviewer-readable static evidence packet.
- merge-readiness JSON reported `merge_readiness_ready=true`, `external_worker_replay_ready=true`, and `next_action=safe delivery`.
- merge-readiness text wrote a reviewer-ready static packet with readiness fields and validation commands.

## Positive Smoke Summaries
Temporary smoke workspace: `.ai/workspaces/R20-R22-SMOKE.*`; created by `mktemp` and removed by trap cleanup.

- reviewer attestation JSON: `verdict=pass`, marker `R20_REVIEW_COMPLETE`, provider/model/browser/shell false.
- reviewer attestation text: artifact write confirmed.
- closure evidence JSON: `closure_evidence_imported=True`, `gate_readable=True`.
- closure evidence text: artifact write confirmed.
- merge-readiness JSON: `ready=True`, `next_action=safe delivery`, `replay_ready=True`.
- merge-readiness text: artifact write confirmed.
- replay summary: `replay_ready=True`, `governance_ready=True`, completed task count `3`.

## Negative Smoke Summaries
- missing reviewer artifact -> `runtime_worker_reviewer_artifact_missing`
- missing marker -> `runtime_worker_reviewer_artifact_marker_missing`
- malformed reviewer JSON -> `runtime_worker_reviewer_artifact_invalid_json`

Unit tests also cover empty reviewer artifacts, non-UTF-8 reviewer artifacts, path traversal, bad closure attestation, missing closure evidence, and symlink input when supported by the platform.

## Validation Commands and Outputs
- `python3 -m compileall agent_office tests` -> passed.
- `python3 -m unittest tests.test_runtime_foundation_cli` -> 30 tests passed.
- `python3 -m unittest tests.test_review_lifecycle_cli` -> 27 tests passed.
- `python3 -m unittest` -> 385 tests passed.
- `python3 -m unittest discover -s tests -p 'test_*.py'` -> 385 tests passed.
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
The task preserved existing untracked artifacts. Validation used project scripts requested by the handoff and a unique temporary R20-R22 smoke workspace that was removed after smoke completion. No `git clean`, `git add .`, or `git add -A` was used.

## Codex-Deliver Safe Mode Result
Pending until after the source branch commit creates a stable source head. The required safe-mode report will be written to:

`/opt/agent-office/R20_R22_CODEX_DELIVER_SAFE_MODE_REPORT.md`

## Authorized Delivery Result
Pending on safe-mode readiness and clean validation. If authorized delivery succeeds, the required report will be written to:

`/opt/agent-office/R20_R22_CODEX_DELIVER_AUTHORIZED_REPORT.md`

## Final Marker
`R20_R22_REVIEWER_ATTESTATION_CLOSURE_EVIDENCE_MERGE_READINESS_SOURCE_READY_FOR_CODEX_DELIVER`
