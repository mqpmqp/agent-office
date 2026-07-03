# R32-R40 Release Closure Promotion Loop Report

## Baseline

- target branch: phase6/mainline
- target_before: 51fda13d2e5e164daa558994ef6b7fcf97e5df73
- origin/phase6/mainline before work: 51fda13d2e5e164daa558994ef6b7fcf97e5df73
- previous marker: R29_R31_RELEASE_CANDIDATE_EXPORT_REVIEW_HANDOFF_ARCHIVE_INDEX_COMPLETE_MAINLINE_SYNCED

## Source Branch

- source branch: phase48/r32-r40-release-closure-promotion-loop
- source head: set after commit `Add release closure promotion loop`

## Changed Files

- README.md
- agent_office/cli.py
- agent_office/runtime_foundation.py
- tests/test_runtime_foundation_cli.py
- R32_R40_RELEASE_CLOSURE_PROMOTION_LOOP_REPORT.md

No `agent_office/review_lifecycle.py` change was needed after inspection; the existing `codex-deliver` remains the only merge/push gate.

## Implemented Commands

- `python3 -m agent_office runtime worker-result reviewer-archive-import`
- `python3 -m agent_office runtime worker-result release-closure`
- `python3 -m agent_office runtime worker-result archive-replay`
- `python3 -m agent_office runtime worker-result final-readiness`
- `python3 -m agent_office runtime worker-result review-recovery`
- `python3 -m agent_office runtime worker-result compact-archive`
- `python3 -m agent_office runtime worker-result compact-verify`
- `python3 -m agent_office runtime worker-result rc-promotion-gate`

All commands are deterministic, static, project-local artifact readers/writers. They do not call providers, models, browsers, shells, external workers, real reviewers, daemons, queues, databases, or vector stores.

## Reviewer Output Import Contract

`reviewer-archive-import` imports saved Markdown or JSON external reviewer output. It verifies the expected marker, parses verdict, marker, caveat, findings summary, reviewed artifact chain, reviewed bundle summary, and safety caveat, then records a deterministic archive import record with role, parents, source marker, SHA256, byte count, archive readiness, and replay readiness.

Clean rejects cover missing marker, empty input, malformed JSON, non-UTF-8 input, path traversal, missing files, symlinked paths, and invalid archive index evidence.

## Release Closure Bundle Contract

`release-closure` composes the release candidate package, external review handoff, archive index, reviewer import, and provenance manifest. It emits `closure_status=closed` only when reviewer verdict is pass, expected marker matches, archive and provenance chains verify, replay is ready, and static refusal predicates remain intact.

Blocked closures include exact rejection reasons, required evidence, recovery guidance, and `next_action=run failed review recovery loop`.

## Archive Replay Verification Contract

`archive-replay` replays the archive index, release candidate package, and release closure bundle. It reuses archive verification, checks release candidate source linkage, closure status, archive readiness, replay readiness, and static refusal predicates.

Tamper, missing evidence, stale package/source mismatch, blocked closure, and predicate drift produce clean rejections with recovery guidance.

## Final Delivery Readiness Contract

`final-readiness` consumes release closure and archive replay verification. Pass output sets `delivery_ready=true`, `promotion_ready=true`, and `next_action=run release candidate promotion gate`. Fail output includes exact reasons, required evidence, and a recovery path while preserving `invocation_allowed=false`, `external_execution_refused=true`, and provider/model/browser/shell flags false.

## Failed Review Recovery Loop Contract

`review-recovery` consumes a blocked release closure and emits a recovery packet with original closure status, original review verdict, rejection reasons, required evidence, and a recovery path:

1. Import fixed external reviewer output with the expected marker and verdict PASS.
2. Regenerate release closure from fixed import and current archive evidence.
3. Rerun archive replay and final readiness.
4. Run compact archive, compact verify, and RC promotion gate after readiness passes.

The smoke flow covered fail -> fixed import -> replay -> readiness pass.

## Compact Archive Index Contract

`compact-archive` creates a long-term compact index retaining record id, role, path, SHA256, byte count, parents, source marker, archive readiness, replay readiness, and terminal status. The compact index includes the R29 archive roles plus external reviewer import, release closure, archive replay, and final delivery readiness.

`compact-verify` rereads compact records and rejects duplicate ids, missing parents, missing required roles, SHA mismatch, byte-count mismatch, malformed JSON, path traversal, symlinks, unsafe static predicates, archive_ready=false, replay_ready=false, and terminal status gaps.

## RC Promotion Gate Contract

`rc-promotion-gate` consumes final readiness, compact archive index, and release closure bundle. It emits a static promotion packet only. It never publishes a release, creates a tag, changes the default branch, force-pushes, or calls providers/models/browsers/shells.

Pass output sets `promotion_ready=true`; fail output includes exact reasons and recovery guidance.

## Positive Smoke Summaries

Temporary smoke root: Python `TemporaryDirectory(prefix="r32-r40-smoke-")`; no VPS historical untracked artifacts were used.

- reviewer import JSON: `verdict=pass`, `archive_ready=True`, `replay_ready=True`
- release closure JSON: `closure_status=closed`, `delivery_ready=True`, `promotion_ready=True`
- archive replay JSON: `archive_replay_valid=True`, `archive_ready=True`, `replay_ready=True`
- final readiness JSON: `delivery_ready=True`, `promotion_ready=True`
- compact archive JSON: `record_count=13`, `terminal_status=ready`
- promotion gate JSON: `promotion_ready=True`, `real_release_executed=False`, `tag_created=False`
- text write checks passed for reviewer import, release closure, archive replay, final readiness, compact archive, and RC promotion gate
- help checks passed for all R32-R40 commands

## Negative Smoke Summaries

- failed review closure rejected with `reviewer_verdict_not_pass:fail` and `reviewer_import_replay_not_ready`
- compact duplicate rejected with `compact_record_count_mismatch` and `duplicate_record_id:provenance_manifest`
- compact missing role rejected with `compact_record_count_mismatch` and `required_role_missing:final_delivery_readiness`
- malformed reviewer JSON rejected with `runtime_worker_reviewer_artifact_invalid_json`
- reviewer path traversal rejected with `runtime_worker_reviewer_archive_import_reviewer_output_path_traversal`

Targeted unit tests additionally cover compact missing parent, SHA mismatch, bad final-readiness provider predicate, compact path traversal, compact symlink rejection where supported, RC promotion gate reject through invalid compact index, empty reviewer artifact, non-UTF-8 reviewer artifact, missing marker, and command help behavior without tracebacks.

## Recovery Smoke Summary

The failed-review recovery smoke used a fail verdict first, generated a blocked release closure and recovery packet, then imported fixed reviewer output with verdict PASS, regenerated release closure, replay, final readiness, compact archive, compact verification, and promotion gate. The fixed readiness packet reported `delivery_ready=True` and the fixed promotion gate reported `promotion_ready=True`.

## Validation Commands and Outputs

Narrow validation already passed before report write:

- `python3 -m compileall agent_office tests` -> passed
- `python3 -m unittest tests.test_runtime_foundation_cli` -> 43 tests passed
- `git diff --check` -> passed
- `/tmp/r32_smoke.py` -> passed
- help checks for all R32-R40 commands -> passed

Full validation passed before commit:

- `python3 -m compileall agent_office tests` -> passed
- `python3 -m unittest tests.test_runtime_foundation_cli` -> 43 tests passed
- `python3 -m unittest tests.test_review_lifecycle_cli` -> 27 tests passed
- `python3 -m unittest` -> 398 tests passed
- `python3 -m unittest discover -s tests -p 'test_*.py'` -> 398 tests passed
- `python3 -m agent_office doctor --adapters` -> gemini/codex/grok/claude mock adapters reported ok
- `./scripts/verify.sh` -> `verify ok`
- `./scripts/smoke-test.sh P6-PROFILES` -> `smoke test ok: P6-PROFILES`
- `python3 -m agent_office run-staged P6-PROFILES --dry-run --reset` -> final status APPROVED
- `python3 -m agent_office --help` -> help rendered successfully
- `git diff --check` -> passed

## Safety Boundaries

- `.env` was not read.
- Environment variables were not printed.
- No provider/model/browser/shell calls were triggered.
- No real external worker execution was triggered.
- No real reviewer/model/provider execution was triggered.
- No daemon, queue, database, or vector store was introduced.
- No release was published.
- No tag was created.
- No default branch was changed.
- No force push is part of this implementation.
- Existing untracked artifacts were not deleted, renamed, archived, cleaned, or staged.

## Untracked Artifacts Note

Existing untracked artifacts were preserved. Informational untracked artifact count before report write was `516`. No `git clean`, `git add .`, or `git add -A` was used. Tests and smoke used temporary fixtures and did not rely on VPS historical untracked artifacts.

## Codex-Deliver Safe Mode Result

Pending until the source branch commit creates a stable source head. The required safe-mode report will be written to:

`/opt/agent-office/R32_R40_CODEX_DELIVER_SAFE_MODE_REPORT.md`

## Authorized Delivery Result

Pending on safe-mode readiness and clean validation. If authorized delivery succeeds, the required report will be written to:

`/opt/agent-office/R32_R40_CODEX_DELIVER_AUTHORIZED_REPORT.md`

## Final Marker

R32_R40_RELEASE_CLOSURE_PROMOTION_LOOP_SOURCE_READY_FOR_CODEX_DELIVER
