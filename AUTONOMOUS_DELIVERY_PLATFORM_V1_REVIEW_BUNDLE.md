# AgentOffice Autonomous Delivery Platform V1 Review Bundle

Marker: AUTONOMOUS_DELIVERY_PLATFORM_V1_REVIEW_BUNDLE

## Baseline

- baseline: `41825cb10a993ab73016d7254471a8dd7db761b3`
- branch: `phase52/autonomous-delivery-platform-v1`
- head: `df39f1a0032bd51712b190e9cbec3755148a3c6c`

## Commit List

```text
d6d89b9 Document autonomous delivery workflow
10e2284 Add V1.1 release operations surfaces
3a8e7d1 Add autonomy merge packet generator
2059d16 Add autonomy review packet generator
d4735a6 Add autonomy validation recorder
5626a4f Add autonomy run ledger and checkpoints
aabcdb4 Add autonomy mission planner
```

## Diff Stat

```text
 AUTONOMOUS_DELIVERY_PLATFORM_V1_REPORT.md | 151 +++++++
 README.md                                 |  61 +++
 agent_office/autonomy.py                  | 665 ++++++++++++++++++++++++++++++
 agent_office/cli.py                       | 137 +++++-
 agent_office/v1_post_release_ops.py       | 172 ++++++++
 tests/test_autonomy_plan_cli.py           | 357 ++++++++++++++++
 tests/test_v1_post_release_ops_cli.py     |  66 +++
 7 files changed, 1608 insertions(+), 1 deletion(-)
```

## Name Status

```text
A	AUTONOMOUS_DELIVERY_PLATFORM_V1_REPORT.md
M	README.md
A	agent_office/autonomy.py
M	agent_office/cli.py
M	agent_office/v1_post_release_ops.py
A	tests/test_autonomy_plan_cli.py
M	tests/test_v1_post_release_ops_cli.py
```

## Validation Summary

```text
compileall.txt	0	python3 -m compileall agent_office tests
unittest.txt	0	python3 -m unittest
unittest_discover.txt	0	python3 -m unittest discover -s tests -p test_*.py
doctor_adapters.txt	0	python3 -m agent_office doctor --adapters
verify_sh.txt	0	./scripts/verify.sh
smoke_test_p6_profiles.txt	0	./scripts/smoke-test.sh P6-PROFILES
run_staged_p6_profiles_dry_run_reset.txt	0	python3 -m agent_office run-staged P6-PROFILES --dry-run --reset
lowest_cost_profile_plan.json	0	python3 -m agent_office profiles --name lowest-cost --plan --json
v1_final_delivery_json.txt	0	python3 -m agent_office v1 final-delivery --json
v1_final_delivery_text.txt	0	python3 -m agent_office v1 final-delivery
autonomy_plan_json.txt	0	python3 -m agent_office autonomy plan --goal autonomous-delivery --json
release_state_json.txt	0	python3 -m agent_office v1 release-state --json
github_release_handoff_json.txt	0	python3 -m agent_office v1 github-release-handoff --json
github_release_plan_json.txt	0	python3 -m agent_office v1 github-release-plan --json
release_candidate_json.txt	0	python3 -m agent_office v1 release-candidate --version v1.1.0 --json
merge_packet_json.txt	0	python3 -m agent_office autonomy merge-packet --source phase52/autonomous-delivery-platform-v1 --target phase6/mainline --json
git_diff_check.txt	0	git diff --check
```

## Implementation Report

```text
# AgentOffice Autonomous Delivery Platform V1 Report

Status: running.

## Mission

Build AgentOffice into an Autonomous Delivery Platform V1 over a long unattended run.

## Baseline

- known mainline ancestor: `41825cb10a993ab73016d7254471a8dd7db761b3`
- actual mainline head at start: `41825cb10a993ab73016d7254471a8dd7db761b3`
- v1.0.0 tag commit: `91a8e38cd8d3db540e8c5655304f0f1e4d8f8213`
- branch: `phase52/autonomous-delivery-platform-v1`

## Safety

- .env not read
- env vars not printed
- token not printed
- provider/runtime/adapter external behavior forbidden
- no tag mutation
- no GitHub Release mutation by default
- no mainline merge


## Milestone A - Autonomous Mission Planner

Status: implemented.

Commands:

`ash
python3 -m agent_office autonomy plan --goal release-ops --json
python3 -m agent_office autonomy plan --goal release-ops
python3 -m agent_office autonomy plan --goal post-v1 --json
python3 -m agent_office autonomy plan --goal post-v1
python3 -m agent_office autonomy plan --goal autonomous-delivery --json
python3 -m agent_office autonomy plan --goal autonomous-delivery
`

Coverage:

- deterministic local JSON/text mission plans
- phases, tasks, validation commands, stop conditions, safety boundaries, artifacts, review handoff, merge gate handoff
- unknown goal clean CLI failure without traceback

## Milestone B - Autonomous Run Ledger And Checkpoints

Status: implemented.

Commands:

`ash
python3 -m agent_office autonomy init --goal autonomous-delivery --path .ai/autonomy/runs/demo --json
python3 -m agent_office autonomy status --path .ai/autonomy/runs/demo --json
python3 -m agent_office autonomy checkpoint --path .ai/autonomy/runs/demo --name preflight --status passed --json
python3 -m agent_office autonomy report --path .ai/autonomy/runs/demo --json
`

Coverage:

- stable local ledger.json with checkpoints, artifacts, and validation_records lists
- status transitions through allowlisted checkpoint statuses
- path traversal, symlink, missing, malformed, and invalid ledger failures return clean CLI errors
- project-root/temp path boundary enforced

## Milestone C - Local Validation Recorder

Status: implemented.

Commands:

`ash
python3 -m agent_office autonomy validate --path .ai/autonomy/runs/demo --suite minimal --json
python3 -m agent_office autonomy validate --path .ai/autonomy/runs/demo --suite release --json
python3 -m agent_office autonomy validate --path .ai/autonomy/runs/demo --suite full --json
`

Coverage:

- allowlisted suites only: minimal, release, full
- no user-supplied shell command execution
- records command text, argv, exit code, stdout path, stderr path, and duration
- appends validation records into the run ledger and updates ledger status
- failed command results are preserved and returned as clean JSON/text failure

## Milestone D - Review Packet Generator

Status: implemented.

Commands:

`ash
python3 -m agent_office autonomy review-packet --base <base_commit> --head HEAD --out /tmp/review-packet.md --json
python3 -m agent_office autonomy review-packet --base <base_commit> --head HEAD --out /tmp/review-packet.md
`

Coverage:

- local Markdown review bundle generation without provider calls
- includes branch, base/head, commits, diff stat, name-status, full diff, safety boundaries, and changed file snapshots
- rejects traversal, .env, symlink, directory, and outside-root output paths
- missing git refs return clean CLI errors

## Milestone E - Merge Gate Packet Generator

Status: implemented.

Commands:

`ash
python3 -m agent_office autonomy merge-packet --source phase52/autonomous-delivery-platform-v1 --target phase6/mainline --json
python3 -m agent_office autonomy merge-packet --source phase52/autonomous-delivery-platform-v1 --target phase6/mainline
`

Coverage:

- local-only source/target ref inspection
- records source head, target head, merge-base, changed files, required validations, required reports, stop conditions, exact merge commands, post-merge validation, and rollback notes
- does not execute merge or mutate branches
- missing source/target refs return clean CLI errors

## Milestone F - Release Operations System V1.1

Status: implemented.

Commands:

`ash
python3 -m agent_office v1 release-state --json
python3 -m agent_office v1 github-release-handoff --json
python3 -m agent_office v1 github-release-plan --json
python3 -m agent_office v1 release-candidate --version v1.1.0 --json
`

Coverage:

- tokenless release-state honesty: skipped_no_token remains skipped, not published
- GitHub Release operator handoff and dry-run plan perform no network or GitHub writes
- release-candidate packet does not create tags or releases
- invalid candidate versions return clean failures

## Milestone G - Longrun Operator Docs

Status: implemented.

Coverage:

- README documents autonomy plan, ledger, validation, review packet, merge packet, release ops handoff, no-token release behavior, safety boundaries, and recommended operator workflow
- existing README content was appended, not rewritten
```

## Self-Review

```text
# AgentOffice Autonomous Delivery Platform V1 Self-Review

Marker: AUTONOMOUS_DELIVERY_PLATFORM_V1_SELF_REVIEW_COMPLETE

## Verdict

- verdict: pass
- branch: `phase52/autonomous-delivery-platform-v1`
- head: `df39f1a0032bd51712b190e9cbec3755148a3c6c`
- baseline: `41825cb10a993ab73016d7254471a8dd7db761b3`
- github write performed: none
- provider/runtime/adapter external behavior: not triggered

## Implemented Milestones

- A: autonomy mission planner
- B: autonomy run ledger and checkpoints
- C: autonomy validation recorder
- D: autonomy review packet generator
- E: autonomy merge packet generator
- F: V1.1 release operations surfaces
- G: longrun operator docs

## Skipped Milestones

- none

## Commits

```text
d6d89b9 Document autonomous delivery workflow
10e2284 Add V1.1 release operations surfaces
3a8e7d1 Add autonomy merge packet generator
2059d16 Add autonomy review packet generator
d4735a6 Add autonomy validation recorder
5626a4f Add autonomy run ledger and checkpoints
aabcdb4 Add autonomy mission planner
```

## Changed Files

```text
A	AUTONOMOUS_DELIVERY_PLATFORM_V1_REPORT.md
M	README.md
A	agent_office/autonomy.py
M	agent_office/cli.py
M	agent_office/v1_post_release_ops.py
A	tests/test_autonomy_plan_cli.py
M	tests/test_v1_post_release_ops_cli.py
```

## Tests Added Or Changed

- `tests/test_autonomy_plan_cli.py`
- `tests/test_v1_post_release_ops_cli.py`

## New CLI Commands

- `python3 -m agent_office autonomy plan --goal <release-ops|post-v1|autonomous-delivery>`
- `python3 -m agent_office autonomy init/status/checkpoint/report`
- `python3 -m agent_office autonomy validate --suite <minimal|release|full>`
- `python3 -m agent_office autonomy review-packet --base <base> --head <head> --out <path>`
- `python3 -m agent_office autonomy merge-packet --source <source> --target <target>`
- `python3 -m agent_office v1 release-state`
- `python3 -m agent_office v1 github-release-handoff`
- `python3 -m agent_office v1 github-release-plan`
- `python3 -m agent_office v1 release-candidate --version v1.1.0`

## Validation Results

```text
compileall.txt	0	python3 -m compileall agent_office tests
unittest.txt	0	python3 -m unittest
unittest_discover.txt	0	python3 -m unittest discover -s tests -p test_*.py
doctor_adapters.txt	0	python3 -m agent_office doctor --adapters
verify_sh.txt	0	./scripts/verify.sh
smoke_test_p6_profiles.txt	0	./scripts/smoke-test.sh P6-PROFILES
run_staged_p6_profiles_dry_run_reset.txt	0	python3 -m agent_office run-staged P6-PROFILES --dry-run --reset
lowest_cost_profile_plan.json	0	python3 -m agent_office profiles --name lowest-cost --plan --json
v1_final_delivery_json.txt	0	python3 -m agent_office v1 final-delivery --json
v1_final_delivery_text.txt	0	python3 -m agent_office v1 final-delivery
autonomy_plan_json.txt	0	python3 -m agent_office autonomy plan --goal autonomous-delivery --json
release_state_json.txt	0	python3 -m agent_office v1 release-state --json
github_release_handoff_json.txt	0	python3 -m agent_office v1 github-release-handoff --json
github_release_plan_json.txt	0	python3 -m agent_office v1 github-release-plan --json
release_candidate_json.txt	0	python3 -m agent_office v1 release-candidate --version v1.1.0 --json
merge_packet_json.txt	0	python3 -m agent_office autonomy merge-packet --source phase52/autonomous-delivery-platform-v1 --target phase6/mainline --json
git_diff_check.txt	0	git diff --check
```

## Safety Boundary Confirmation

- `.env` was not read.
- environment variables were not printed.
- token values were not printed.
- no `env`, `printenv`, or `set` command was run.
- no `gh` or package installation was attempted.
- no real provider/runtime/adapter/model behavior was triggered.
- no tag was created, overwritten, or deleted.
- no GitHub Release was created, overwritten, deleted, or published.
- no GitHub release assets were deleted or overwritten.
- no force push was performed.
- no merge into `phase6/mainline` was performed.

## Remaining Risks

- GitHub Release remains token-gated and skipped without operator credentials.
- Review packet generation includes full diffs and capped snapshots; very large files are truncated in snapshots.
- `autonomy validate full` can be long-running because it intentionally runs the full local gate.

## Merge Gate Recommendation

Ready for external review and merge-gate preparation. Do not merge without explicit human authorization and a fresh target/source head check.
```

## README Excerpt

```text
AgentOffice includes a local-only autonomous delivery workflow for long-running, reviewable delivery branches. These commands do not read `.env`, print environment variables, call providers or models, mutate tags, create GitHub Releases, or merge into `phase6/mainline`.

Mission planning:

```bash
python3 -m agent_office autonomy plan --goal release-ops --json
python3 -m agent_office autonomy plan --goal post-v1 --json
python3 -m agent_office autonomy plan --goal autonomous-delivery --json
```

Run ledger and checkpoints:

```bash
python3 -m agent_office autonomy init --goal autonomous-delivery --path .ai/autonomy/runs/demo --json
python3 -m agent_office autonomy status --path .ai/autonomy/runs/demo --json
python3 -m agent_office autonomy checkpoint --path .ai/autonomy/runs/demo --name preflight --status passed --json
python3 -m agent_office autonomy report --path .ai/autonomy/runs/demo --json
```

Validation recorder:

```bash
python3 -m agent_office autonomy validate --path .ai/autonomy/runs/demo --suite minimal --json
python3 -m agent_office autonomy validate --path .ai/autonomy/runs/demo --suite release --json
python3 -m agent_office autonomy validate --path .ai/autonomy/runs/demo --suite full --json
```

`autonomy validate` only runs built-in allowlisted suites. It is not a general shell runner. Each command record stores the command text, argv, exit code, stdout path, stderr path, and duration in the run ledger.

Review and merge gate packets:

```bash
python3 -m agent_office autonomy review-packet --base <base_commit> --head HEAD --out /tmp/review-packet.md --json
python3 -m agent_office autonomy merge-packet --source phase52/autonomous-delivery-platform-v1 --target phase6/mainline --json
```

`review-packet` writes a Markdown bundle with commit list, diff stat, name-status, full diff, file snapshots, safety boundaries, caveats, and review focus. `merge-packet` emits source/target heads, merge-base, changed files, required validations, required reports, exact merge commands, post-merge validation, and rollback notes; it does not execute a merge.

Release operations handoff:

```bash
python3 -m agent_office v1 release-state --json
python3 -m agent_office v1 github-release-handoff --json
python3 -m agent_office v1 github-release-plan --json
python3 -m agent_office v1 release-candidate --version v1.1.0 --json
```

No-token release behavior is explicit: `skipped_no_token` remains `publish_state=skipped`, never `published`. Release handoff and plan packets are dry-run/operator packets and perform no GitHub writes.

Recommended operator workflow:

1. Create or resume a feature branch.
2. Generate an autonomy plan for the goal.
3. Initialize a run ledger under `.ai/autonomy/runs/<run-id>`.
4. Add checkpoints after preflight, implementation, validation, review packet, and merge packet steps.
5. Run `minimal` validation after each milestone and `full` validation before review.
6. Generate a review packet and merge packet.
7. Review the branch; merge only after explicit human authorization and a fresh merge gate.
```

## Changed File Snapshots

### AUTONOMOUS_DELIVERY_PLATFORM_V1_REPORT.md

truncated: false

```text
# AgentOffice Autonomous Delivery Platform V1 Report

Status: running.

## Mission

Build AgentOffice into an Autonomous Delivery Platform V1 over a long unattended run.

## Baseline

- known mainline ancestor: `41825cb10a993ab73016d7254471a8dd7db761b3`
- actual mainline head at start: `41825cb10a993ab73016d7254471a8dd7db761b3`
- v1.0.0 tag commit: `91a8e38cd8d3db540e8c5655304f0f1e4d8f8213`
- branch: `phase52/autonomous-delivery-platform-v1`

## Safety

- .env not read
- env vars not printed
- token not printed
- provider/runtime/adapter external behavior forbidden
- no tag mutation
- no GitHub Release mutation by default
- no mainline merge


## Milestone A - Autonomous Mission Planner

Status: implemented.

Commands:

`ash
python3 -m agent_office autonomy plan --goal release-ops --json
python3 -m agent_office autonomy plan --goal release-ops
python3 -m agent_office autonomy plan --goal post-v1 --json
python3 -m agent_office autonomy plan --goal post-v1
python3 -m agent_office autonomy plan --goal autonomous-delivery --json
python3 -m agent_office autonomy plan --goal autonomous-delivery
`

Coverage:

- deterministic local JSON/text mission plans
- phases, tasks, validation commands, stop conditions, safety boundaries, artifacts, review handoff, merge gate handoff
- unknown goal clean CLI failure without traceback

## Milestone B - Autonomous Run Ledger And Checkpoints

Status: implemented.

Commands:

`ash
python3 -m agent_office autonomy init --goal autonomous-delivery --path .ai/autonomy/runs/demo --json
python3 -m agent_office autonomy status --path .ai/autonomy/runs/demo --json
python3 -m agent_office autonomy checkpoint --path .ai/autonomy/runs/demo --name preflight --status passed --json
python3 -m agent_office autonomy report --path .ai/autonomy/runs/demo --json
`

Coverage:

- stable local ledger.json with checkpoints, artifacts, and validation_records lists
- status transitions through allowlisted checkpoint statuses
- path traversal, symlink, missing, malformed, and invalid ledger failures return clean CLI errors
- project-root/temp path boundary enforced

## Milestone C - Local Validation Recorder

Status: implemented.

Commands:

`ash
python3 -m agent_office autonomy validate --path .ai/autonomy/runs/demo --suite minimal --json
python3 -m agent_office autonomy validate --path .ai/autonomy/runs/demo --suite release --json
python3 -m agent_office autonomy validate --path .ai/autonomy/runs/demo --suite full --json
`

Coverage:

- allowlisted suites only: minimal, release, full
- no user-supplied shell command execution
- records command text, argv, exit code, stdout path, stderr path, and duration
- appends validation records into the run ledger and updates ledger status
- failed command results are preserved and returned as clean JSON/text failure

## Milestone D - Review Packet Generator

Status: implemented.

Commands:

`ash
python3 -m agent_office autonomy review-packet --base <base_commit> --head HEAD --out /tmp/review-packet.md --json
python3 -m agent_office autonomy review-packet --base <base_commit> --head HEAD --out /tmp/review-packet.md
`

Coverage:

- local Markdown review bundle generation without provider calls
- includes branch, base/head, commits, diff stat, name-status, full diff, safety boundaries, and changed file snapshots
- rejects traversal, .env, symlink, directory, and outside-root output paths
- missing git refs return clean CLI errors

## Milestone E - Merge Gate Packet Generator

Status: implemented.

Commands:

`ash
python3 -m agent_office autonomy merge-packet --source phase52/autonomous-delivery-platform-v1 --target phase6/mainline --json
python3 -m agent_office autonomy merge-packet --source phase52/autonomous-delivery-platform-v1 --target phase6/mainline
`

Coverage:

- local-only source/target ref inspection
- records source head, target head, merge-base, changed files, required validations, required reports, stop conditions, exact merge commands, post-merge validation, and rollback notes
- does not execute merge or mutate branches
- missing source/target refs return clean CLI errors

## Milestone F - Release Operations System V1.1

Status: implemented.

Commands:

`ash
python3 -m agent_office v1 release-state --json
python3 -m agent_office v1 github-release-handoff --json
python3 -m agent_office v1 github-release-plan --json
python3 -m agent_office v1 release-candidate --version v1.1.0 --json
`

Coverage:

- tokenless release-state honesty: skipped_no_token remains skipped, not published
- GitHub Release operator handoff and dry-run plan perform no network or GitHub writes
- release-candidate packet does not create tags or releases
- invalid candidate versions return clean failures

## Milestone G - Longrun Operator Docs

Status: implemented.

Coverage:

- README documents autonomy plan, ledger, validation, review packet, merge packet, release ops handoff, no-token release behavior, safety boundaries, and recommended operator workflow
- existing README content was appended, not rewritten
```
### README.md

truncated: true

```text
# AgentOffice

AgentOffice is a minimal file-based orchestrator for four AI roles:

- Gemini: context scan and compressed summary.
- Codex: implementation, bug fixes, and tests.
- Grok Build: red-team review.
- Claude Code: final decision only.

The agents do not freely chat. Every task is coordinated through files under:

```text
.ai/tasks/<TASK_ID>/
  task.json
  brief.md
  gemini-context.md
  codex-report.md
  patch.diff
  grok-review.md
  final-for-claude.md
  claude-decision.md
```

## Auditable Multi-Agent Orchestration

AgentOffice is evolving from a static workflow/gate tool into an auditable multi-agent orchestration system.

The first orchestration core accepts one high-level task and creates a white-box multi-agent execution graph. Unlike black-box orchestration systems, AgentOffice keeps artifacts, task graphs, role packets, validation state, and safety boundaries inspectable.

Current orchestration mode is static only. It does not call external providers, runtimes, adapters, or model APIs.
Generated orchestration artifacts are deterministic for identical inputs and do not embed wall-clock timestamps.
Task-derived artifacts remain byte-identical for identical inputs. Provenance-bearing artifacts vary with git/worktree source state: `manifest.json`, `phase_report.md`, and the artifact `README.md` record `source_commit`, `baseline_commit`, clean/dirty/unavailable state, and any tracked pending-change paths when present.
Generated phase reports do not use a placeholder commit value; tracked uncommitted changes are reported as `pending_change_state=tracked_changes_pending`.

```bash
python3 -m agent_office orchestrate run --task "Review this change safely" --mode static --out /tmp/ao-orch --json
python3 -m agent_office orchestrate inspect --path /tmp/ao-orch --json
python3 -m agent_office orchestrate validate --path /tmp/ao-orch --json
```

## Runtime Foundation Slice

The runtime foundation slice is local, deterministic, and static. It writes only a project-local workspace manifest, task graph, JSONL memory/events, and local/static task results. It does not read `.env`, print environment values, call providers, call models, start daemons, run background workers, or execute external adapters.

```bash
python3 -m agent_office runtime init --workspace .ai/workspaces/demo --goal "demo" --json
python3 -m agent_office runtime plan --workspace .ai/workspaces/demo --task "inspect:Inspect" --task "review:Review" --depends review:inspect --json
python3 -m agent_office runtime run --workspace .ai/workspaces/demo --adapter local-static --dry-run --json
python3 -m agent_office runtime run --workspace .ai/workspaces/demo --adapter local-static --execute-local --json
python3 -m agent_office runtime status --workspace .ai/workspaces/demo --json
python3 -m agent_office runtime packet --workspace .ai/workspaces/demo --json
python3 -m agent_office runtime replay --workspace .ai/workspaces/demo --json
python3 -m agent_office runtime evidence --workspace .ai/workspaces/demo --out .ai/workspaces/demo/evidence.json --format json --json
python3 -m agent_office runtime close --workspace .ai/workspaces/demo --out .ai/workspaces/demo/closure_packet.json --json
python3 -m agent_office runtime governance --workspace .ai/workspaces/demo --closure-packet .ai/workspaces/demo/closure_packet.json --evidence-out .ai/workspaces/demo/runtime-governance-evidence.json --format json
python3 -m agent_office runtime job create --workspace .ai/workspaces/demo --job-id demo-job --json
python3 -m agent_office runtime job status --workspace .ai/workspaces/demo --job-id demo-job --json
python3 -m agent_office runtime worker-adapter --list --json
python3 -m agent_office runtime worker-adapter --name external-prototype --describe --json
python3 -m agent_office runtime worker-gate --workspace .ai/workspaces/demo --adapter external-prototype --json
python3 -m agent_office runtime worker-packet --workspace .ai/workspaces/demo --adapter external-prototype --job-id demo-job --out .ai/workspaces/demo/worker-invocation-packet.json --json
python3 -m agent_office runtime worker-result intake --workspace .ai/workspaces/demo --packet .ai/workspaces/demo/worker-invocation-packet.json --result .ai/workspaces/demo/worker-result.json --json
python3 -m agent_office runtime worker-result replay --workspace .ai/workspaces/demo --packet .ai/workspaces/demo/worker-invocation-packet.json --result .ai/workspaces/demo/worker-result.json --json
python3 -m agent_office runtime worker-result audit-closure --workspace .ai/workspaces/demo --packet .ai/workspaces/demo/worker-invocation-packet.json --result .ai/workspaces/demo/worker-result.json --out .ai/workspaces/demo/worker-audit-closure.json --json
python3 -m agent_office runtime worker-result delivery-bundle --workspace .ai/workspaces/demo --packet .ai/workspaces/demo/worker-invocation-packet.json --result .ai/workspaces/demo/worker-result.json --audit-closure .ai/workspaces/demo/worker-audit-closure.json --out .ai/workspaces/demo/worker-delivery-bundle.json --json
python3 -m agent_office runtime worker-result reviewer-attestation --reviewer-artifact .ai/workspaces/demo/reviewer-output.md --marker R20_REVIEW_COMPLETE --out .ai/workspaces/demo/reviewer-attestation.json --json
python3 -m agent_office runtime worker-result closure-evidence --reviewer-attestation .ai/workspaces/demo/reviewer-attestation.json --out .ai/workspaces/demo/closure-evidence.json --json
python3 -m agent_office runtime worker-result merge-readiness --delivery-bundle .ai/workspaces/demo/worker-delivery-bundle.json --reviewer-attestation .ai/workspaces/demo/reviewer-attestation.json --closure-evidence .ai/workspaces/demo/closure-evidence.json --baseline <target-head> --source-branch <source-branch> --source-head <source-head> --target-branch phase6/mainline --out .ai/workspaces/demo/merge-readiness.json --json
python3 -m agent_office runtime worker-result delivery-gate --merge-readiness .ai/workspaces/demo/merge-readiness.json --out .ai/workspaces/demo/delivery-gate.json --json
python3 -m agent_office runtime worker-result rejection-packet --delivery-gate .ai/workspaces/demo/delivery-gate.json --out .ai/workspaces/demo/rejection-packet.json --json
python3 -m agent_office runtime worker-result audit-replay --packet .ai/workspaces/demo/rejection-packet.json --out .ai/workspaces/demo/audit-replay.json --json
python3 -m agent_office runtime worker-result provenance-manifest --reviewer-attestation .ai/workspaces/demo/reviewer-attestation.json --closure-evidence .ai/workspaces/demo/closure-evidence.json --merge-readiness .ai/workspaces/demo/merge-readiness.json --delivery-gate .ai/workspaces/demo/delivery-gate.json --rejection-packet .ai/workspaces/demo/rejection-packet.json --audit-replay .ai/workspaces/demo/audit-replay.json --out .ai/workspaces/demo/provenance-manifest.json --json
python3 -m agent_office runtime worker-result provenance-verify --manifest .ai/workspaces/demo/provenance-manifest.json --json
python3 -m agent_office runtime worker-result provenance-replay --manifest .ai/workspaces/demo/provenance-manifest.json --json
python3 -m agent_office runtime worker-result release-candidate --provenance-manifest .ai/workspaces/demo/provenance-manifest.json --out .ai/workspaces/demo/release-candidate.json --review-target "AgentOffice release candidate" --json
python3 -m agent_office runtime worker-result external-review-handoff --release-candidate .ai/workspaces/demo/release-candidate.json --out .ai/workspaces/demo/external-review-handoff.json --review-target "AgentOffice release candidate" --expected-marker R29_EXTERNAL_REVIEW_COMPLETE --attestation-import-path .ai/workspaces/demo/imported-reviewer-attestation.json --json
python3 -m agent_office runtime worker-result archive-index --release-candidate .ai/workspaces/demo/release-candidate.json --external-review-handoff .ai/workspaces/demo/external-review-handoff.json --out .ai/workspaces/demo/archive-index.json --json
python3 -m agent_office runtime worker-result archive-verify --index .ai/workspaces/demo/archive-index.json --json
python3 -m agent_office runtime worker-result reviewer-archive-import --reviewer-output .ai/workspaces/demo/external-reviewer-output.md --archive-index .ai/workspaces/demo/archive-index.json --expected-marker R29_EXTERNAL_REVIEW_COMPLETE --out .ai/workspaces/demo/reviewer-import.json --json
python3 -m agent_office runtime worker-result release-closure --release-candidate .ai/workspaces/demo/release-candidate.json --external-review-handoff .ai/workspaces/demo/external-review-handoff.json --archive-index .ai/workspaces/demo/archive-index.json --reviewer-import .ai/workspaces/demo/reviewer-import.json --provenance-manifest .ai/workspaces/demo/provenance-manifest.json --out .ai/workspaces/demo/release-closure.json --json
python3 -m agent_office runtime worker-result archive-replay --archive-index .ai/workspaces/demo/archive-index.json --release-candidate .ai/workspaces/demo/release-candidate.json --release-closure .ai/workspaces/demo/release-closure.json --out .ai/workspaces/demo/archive-replay.json --json
python3 -m agent_office runtime worker-result final-readiness --release-closure .ai/workspaces/demo/release-closure.json --archive-replay .ai/workspaces/demo/archive-replay.json --out .ai/workspaces/demo/final-readiness.json --json
python3 -m agent_office runtime worker-result review-recovery --release-closure .ai/workspaces/demo/release-closure.json --out .ai/workspaces/demo/review-recovery.json --json
python3 -m agent_office runtime worker-result compact-archive --archive-index .ai/workspaces/demo/archive-index.json --release-closure .ai/workspaces/demo/release-closure.json --archive-replay .ai/workspaces/demo/archive-replay.json --final-readiness .ai/workspaces/demo/final-readiness.json --out .ai/workspaces/demo/compact-index.json --json
python3 -m agent_office runtime worker-result compact-verify --index .ai/workspaces/demo/compact-index.json --json
python3 -m agent_office runtime worker-result rc-promotion-gate --final-readiness .ai/workspaces/demo/final-readiness.json --compact-index .ai/workspaces/demo/compact-index.json --release-closure .ai/workspaces/demo/release-closure.json --out .ai/workspaces/demo/promotion-gate.json --json
python3 -m agent_office runtime worker-result release-candidate-export --release-candidate .ai/workspaces/demo/release-candidate.json --archive-index .ai/workspaces/demo/archive-index.json --out .ai/workspaces/demo/release-candidate-export.json --json
python3 -m agent_office runtime worker-result promotion-evidence --release-candidate .ai/workspaces/demo/release-candidate.json --archive-index .ai/workspaces/demo/archive-index.json --release-closure .ai/workspaces/demo/release-closure.json --archive-replay .ai/workspaces/demo/archive-replay.json --final-readiness .ai/workspaces/demo/final-readiness.json --compact-index .ai/workspaces/demo/compact-index.json --promotion-gate .ai/workspaces/demo/promotion-gate.json --final-mainline <final-mainline-head> --out .ai/workspaces/demo/promotion-evidence.json --json
python3 -m agent_office runtime worker-result dry-run-publish --promotion-evidence .ai/workspaces/demo/promotion-evidence.json --release-candidate-export .ai/workspaces/demo/release-candidate-export.json --promotion-gate .ai/workspaces/demo/promotion-gate.json --candidate-name "AgentOffice release candidate" --target-branch phase6/mainline --target-commit <final-mainline-head> --out .ai/workspaces/demo/dry-run-publish.json --json
```

Worker invocation packets, worker result intake, replay, audit closure, delivery bundles, reviewer attestations, closure evidence imports, merge-readiness packets, delivery gates, rejection recovery packets, audit replays, and provenance manifests are static governance contracts. They do not call models, providers, browsers, shells, external workers, or real reviewers. Reviewer attestation reads a saved Markdown/JSON artifact and records its path, SHA256, byte count, verdict, marker, caveat, findings summary, reviewed artifacts, and safety caveat. Closure evidence imports only a JSON reviewer attestation into an explicit project-local output path. Merge readiness composes the delivery bundle, reviewer attestation, and closure evidence into a deterministic packet. Delivery gate consumes that merge-readiness packet and passes only when the reviewer attestation, closure evidence, worker replay/audit/delivery predicates, invocation refusal, external execution refusal, and provider/model/browser/shell false flags are all present. Rejection packets record exact reasons, next required evidence, and recovery guidance. Audit replay reads prior audit, merge-readiness, delivery-gate, or rejection packets without executing anything.

The provenance manifest chains the R23-R25 artifacts into a deterministic, tamper-evident sequence: reviewer attestation -> closure evidence -> merge-readiness -> delivery gate -> rejection recovery -> audit replay. Each manifest artifact entry records an artifact id, role, project-local path, SHA256, byte count, parent artifact ids, replay status, and readiness/gate predicate summary. `generated_at` is the stable value `deterministic-static-v1`, not a wall-clock timestamp.

`provenance-verify` rereads every artifact listed in the manifest and rejects cleanly when an artifact is missing, modified, replaced, malformed, symlinked, path-traversing, out of order, duplicated, cyclic, missing a required role, or carrying unsafe predicates such as `invocation_allowed=true`, `external_execution_refused=false`, or provider/model/browser/shell call flags set to true. Rejections return exact `rejection_reasons` plus `recovery_guidance`; for example, restore or regenerate the static evidence, regenerate the manifest with canonical parent links, then rerun `provenance-verify` and `provenance-replay`.

`provenance-replay` is read-only. It first verifies the manifest, then reports original readiness, artifact integrity, delivery gate pass/fail state, rejection/recovery status, replay readiness, and governance readiness. A tampered chain returns `chain_replay_ready=false` without a traceback.

`release-candidate` exports a deterministic release candidate package from a verified provenance manifest. The package records the provenance manifest, delivery gate, reviewer attestation, closure evidence, merge-readiness packet, rejection recovery packet, audit replay result, and tamper-evident replay summary. Each included artifact records role, project-local path, SHA256, byte count, parent linkage, archive readiness, and replay readiness. `generated_at` is the stable value `deterministic-static-v1`.

`external-review-handoff` writes a reviewer-ready packet from the release candidate package. It records the review target, artifact chain root and terminal artifact, included evidence list, integrity verification and replay instructions, expected reviewer output marker, attestation import path, and the artifact-only caveat: reviewers must not claim VPS validation unless they actually ran it. This command does not call a reviewer, model, or provider.

`archive-index` writes a deterministic evidence archive index covering the release candidate package, artifact chain, and external review handoff. `archive-verify` rereads every indexed record and rejects cleanly on missing artifacts, SHA or byte-count mismatch, duplicate record ids, missing parents, required role gaps, stale package contents, malformed JSON, path traversal, symlinks, unsafe predicates, `archive_ready=false`, or `replay_ready=false`. Rejections include exact reasons plus recovery guidance: restore or regenerate the missing/tampered static evidence, regenerate the release candidate and archive index from the current provenance manifest, then rerun `archive-verify`.

`reviewer-archive-import` imports a saved external reviewer output artifact into the static archive chain. It accepts Markdown or JSON reviewer output, requires the expected marker, records verdict, caveat, findings summary, reviewed artifact chain, source marker, SHA256, byte count, role, parents, archive readiness, and replay readiness, and rejects empty, malformed, non-UTF-8, missing-marker, traversal, or symlinked inputs cleanly.

`release-closure` composes the release candidate package, external review handoff, archive index, reviewer import, and provenance manifest into a deterministic release closure bundle. It closes only when the reviewer verdict is `pass`, the expected marker matches, archive/provenance replay is ready, and all static refusal predicates remain intact. Failed or conditional reviewer verdicts produce a blocked closure with exact reasons and recovery guidance.

`archive-replay`, `final-readiness`, and `review-recovery` complete the static closure loop. Archive replay rechecks the archive index, release candidate package, and closure bundle. Final readiness emits `delivery_ready` and `promotion_ready` only when closure and replay pass. Review recovery records the failed-review evidence needed to import fixed reviewer output, regenerate closure, rerun replay, and recheck readiness.

`compact-archive` and `compact-verify` build and verify a long-term compact evidence index without dropping integrity fields: record id, role, path, SHA256, byte count, parents, source marker, archive readiness, replay readiness, and terminal status are retained. Verification rejects duplicate ids, missing parents, missing roles, tamper, malformed JSON, traversal, symlinks, and bad static predicates.

`rc-promotion-gate` consumes final readiness, compact archive verification, and release closure evidence to write a static promotion packet. It never publishes a release, creates a tag, changes the default branch, or calls a provider/model/browser/shell. Pass output sets `promotion_ready=true`; failures include exact reasons and recovery guidance.

`release-candidate-export` rereads the release candidate package plus archive index and writes a reviewer-ready export packet with a stable manifest, digest, record count, expected roles, and readiness summary. It rejects duplicate roles, missing roles, malformed JSON, traversal paths, tampered records, and unsafe static predicates cleanly without relying on unrelated untracked artifacts.

`promotion-evidence` summarizes release closure, archive replay, compact archive terminal status, promotion gate result, reviewed source/target/final-mainline refs, validation references, negative recovery coverage, and no-real-promotion proof into JSON or text. The command is still static release-preparation evidence only. `promotion_ready=true` means the evidence packet is ready for review; it is not a real release and it does not create a tag, create a GitHub release, push, or mutate the default branch.

`dry-run-publish` describes what a future explicitly authorized publish would require. It records target branch, target commit, candidate release id/name, source evidence references, promotion gate status, approval checklist, and required artifacts while keeping `would_create_tag=false`, `would_create_release=false`, `would_push=false`, and `would_change_default_branch=false`. Real release/tag/default-branch promotion remains a later independent gate requiring explicit authorization.


## v1 Final Delivery Packet

P49 is the final implementation batch for AgentOffice v1. It adds a deterministic final delivery packet and verifier so reviewers can inspect the v1 delivery state without running providers, runtimes, models, external workers, or adapters.

Generate the packet as JSON or reviewer-ready text:

```bash
python3 -m agent_office v1 final-delivery --json
python3 -m agent_office v1 final-delivery
python3 -m agent_office v1 final-delivery --out /tmp/agentoffice-v1-final-delivery.json --json
```

Verify a saved packet:

```bash
python3 -m agent_office v1 verify-final-delivery --path /tmp/agentoffice-v1-final-delivery.json --json
python3 -m agent_office v1 verify-final-delivery --path /tmp/agentoffice-v1-final-delivery.json
```

The packet top-level contract includes `schema_version`, `packet_type`, `phase`, `status`, `repo`, `delivery`, `contracts`, `validation`, `artifacts`, `review`, `merge_gate`, `safety`, `non_goals`, and `next_actions`. Text output contains `AGENTOFFICE_V1_FINAL_DELIVERY_PACKET`; verifier text emits `AGENTOFFICE_V1_FINAL_DELIVERY_VERIFY_PASS` or `AGENTOFFICE_V1_FINAL_DELIVERY_VERIFY_FAIL`.

## Post-v1 Release Operations

Post-v1 release operations add local-only verification surfaces for the v1.0.0 release archive and GitHub release readback evidence. These commands do not read `.env`, do not print environment variables, and do not call providers, runtimes, models, external workers, or adapters.

Verify the release archive and its sidecar checksum:

```bash
python3 -m agent_office v1 verify-release-archive --archive /opt/agent-office/agentoffice-v1.0.0-final-delivery-archive.tar.gz --sha256 /opt/agent-office/agentoffice-v1.0.0-final-delivery-archive.tar.gz.sha256 --json
python3 -m agent_office v1 verify-release-archive --archive /opt/agent-office/agentoffice-v1.0.0-final-delivery-archive.tar.gz --sha256 /opt/agent-office/agentoffice-v1.0.0-final-delivery-archive.tar.gz.sha256
```

Verify local GitHub release publish/readback evidence without making network requests:

```bash
python3 -m agent_office v1 verify-github-release-readback --dir /opt/agent-office/V1_0_0_GITHUB_RELEASE_API_LONGRUN_READBACK --json
python3 -m agent_office v1 verify-github-release-readback --dir /opt/agent-office/V1_0_0_GITHUB_RELEASE_API_LONGRUN_READBACK
```

Print the deterministic post-v1 roadmap packet:

```bash
python3 -m agent_office v1 post-v1-roadmap --json
python3 -m agent_office v1 post-v1-roadmap
```

Codex-only closure output files for the user-approved P49 path:

- `P49_CODEX_SELF_REVIEW_OUTPUT.md`
- `P49_CODEX_REVIEW_FIX_REPORT.md` only if the self-review requires a fix
- `P49_CODEX_MERGE_GATE_REPORT.md`
- `P49_V1_FINAL_RELEASE_DECLARATION.md` after mainline merge validation

External artifact review is not a prerequisite when the operator explicitly chooses Codex-only closure. Do not create, cite, or imply external reviewer output unless that review actually occurred and is saved as evidence.

Merge gate prerequisites:

1. P49 source branch is pushed.
2. P49 Codex self-review is complete.
3. Any required Codex review-fix delta is complete and validated.
4. Codex merge gate passes under explicit operator authorization.
5. v1 final release declaration happens only after merge and post-merge validation.

Safety constraints: the packet and verifier do not read `.env`, do not print environment variable values, do not trigger provider/runtime/adapter external behavior, do not tag, do not force push, and do not mutate the default branch.

## Claude Token Rule

Mock Claude reads only `final-for-claude.md`. P5-05 adds a staged real Claude final judge dry-run that can also review bounded staged artifacts under `.ai/context/`, `.ai/codex/`, and `.ai/grok/`.

- Claude does not read the full repository.
- Claude does not read full logs.
- Claude does not read the full diff.
- `final-for-claude.md` is capped at 4000 characters.
- Claude final judge dry-run writes only `.ai/claude/final-judge.md` and `.ai/claude/metadata.json`.
- Each task allows at most 2 rework rounds.

## Install

No third-party dependencies are required.

```bash
python -m pip install -e .
```

After install, the CLI command is:

```bash
agent-office --help
```

Without installation, use:

```bash
python -m agent_office --help
```

## Commands

```bash
agent-office new <TASK_ID>
agent-office context <TASK_ID> --mock
agent-office context <TASK_ID> --real --adapter gemini --timeout 120
agent-office implement <TASK_ID> --mock
agent-office implement <TASK_ID> --real --adapter codex --timeout 1200
agent-office redteam <TASK_ID> --mock
agent-office redteam <TASK_ID> --real --adapter grok --timeout 120
agent-office summarize <TASK_ID> --mock
agent-office final <TASK_ID> --mock
agent-office final <TASK_ID> --real --adapter claude --dry-run --timeout 120
agent-office judge <TASK_ID> --real --adapter claude --dry-run --timeout 120
agent-office status <TASK_ID>
agent-office run-demo <TASK_ID> --mock
agent-office run-staged <TASK_ID> --dry-run --reset
agent-office run-staged <TASK_ID> --dry-run --real --adapter gemini
agent-office adapters
agent-office doctor
agent-office doctor --adapter codex
agent-office doctor --adapter gemini
agent-office doctor --adapter grok
agent-office doctor --adapter claude
agent-office doctor --adapters
agent-office profiles --name lowest-cost --plan --audit
agent-office profiles --name lowest-cost --plan --audit --json
agent-office objectives --phase P6-10
agent-office objectives --phase P6-10 --json
agent-office orchestrate run --task "Review this change safely" --mode static --out /tmp/ao-orch --json
agent-office orchestrate inspect --path /tmp/ao-orch --json
agent-office orchestrate validate --path /tmp/ao-orch --json
agent-office runtime init --workspace .ai/workspaces/demo --goal "demo" --json
agent-office runtime plan --workspace .ai/workspaces/demo --task "inspect:Inspect" --task "review:Review" --depends review:inspect --json
agent-office runtime run --workspace .ai/workspaces/demo --adapter local-static --dry-run --json
agent-office runtime run --workspace .ai/workspaces/demo --adapter local-static --execute-local --json
agent-office runtime status --workspace .ai/workspaces/demo --json
agent-office runtime packet --workspace .ai/workspaces/demo --json
agent-office runtime replay --workspace .ai/workspaces/demo --json
agent-office runtime evidence --workspace .ai/workspaces/demo --out .ai/workspaces/demo/evidence.json --format json --json
agent-office runtime close --workspace .ai/workspaces/demo --out .ai/workspaces/demo/closure_packet.json --json
agent-office profiles --plan --audit
agent-office profiles --plan --audit --json
agent-office doctor --profiles
agent-office doctor --json
python -m agent_office.doctor --adapters
python -m agent_office.doctor --profiles
agent-office run-bundle preview --objective P6-17 --profile lowest-cost --json
agent-office run-bundle validate --path .ai/runs/<RUN_ID> --json
agent-office run-bundle status --path .ai/runs/<RUN_ID> --json
agent-office run-bundle handoff --path .ai/runs/<RUN_ID> --json
agent-office run-bundle review --path .ai/runs/<RUN_ID> --json
agent-office run-bundle gate --path .ai/runs/<RUN_ID> --json
agent-office run-bundle workflow --path .ai/runs/<RUN_ID> --json
agent-office run-bundle export-review --path .ai/runs/<RUN_ID> --out /tmp/agentoffice-review.md
agent-office run-bundle export-review --path .ai/runs/<RUN_ID> --out /tmp/agentoffice-review.md --json
```

## State Machine

```text
CREATED
CONTEXT_READY
IMPLEMENTED
REVIEWED
SUMMARIZED
CLAUDE_DECIDED
APPROVED
REQUEST_CHANGES
REJECTED
```

`CLAUDE_DECIDED` is recorded in `task.json` history. The task state then moves to one of:

- `APPROVED`
- `REQUEST_CHANGES`
- `REJECTED`

## Mock Demo

```bash
agent-office run-demo demo-task --mock
```

or:

```bash
python -m agent_office run-demo demo-task --mock
```

Repeat the same demo safely with `--reset`:

```bash
python -m agent_office run-demo demo-task --mock --reset
```

`--reset` deletes only `.ai/tasks/<TASK_ID>/` for the task being run, then recreates the deterministic mock workflow from scratch. It does not relax the state machine and does not affect other task directories.

To clean demo tasks manually:

```bash
rm -rf .ai/tasks/DEMO-*
```

## Staged Full Dry Run

P6-01 adds a dry-run orchestration command that only chains existing stages:

```bash
python -m agent_office run-staged <TASK_ID> --dry-run --reset
```

It runs:

```text
new -> context -> implement -> redteam -> summarize -> judge -> status
```

All stages are mock by default, even if adapter environment variables are present. To exercise one staged real dry-run adapter, enable exactly one adapter explicitly:

```bash
export AGENTOFFICE_GEMINI_MODE=real
export AGENTOFFICE_GEMINI_DRY_RUN=true
export GEMINI_API_KEY=replace-with-real-key-outside-git
python -m agent_office run-staged <TASK_ID> --dry-run --real --adapter gemini --reset
```

Use `codex`, `grok`, or `claude` in the same shape to exercise one corresponding stage. `run-staged` refuses `--real` without a single `--adapter`, refuses adapter selection without `--real`, and requires `--dry-run`.

Safety boundaries:

- No real provider request is sent while `--dry-run` is active.
- No patch is applied.
- No git commit is made.
- `.env` is not read and environment variable values are not printed.
- The existing task state machine is reused unchanged.
- Runtime artifacts stay under ignored `.ai/**` paths.
- Each `run-staged` invocation clears stale staged runtime directories: `.ai/context/`, `.ai/codex/`, `.ai/grok/`, `.ai/claude/`, and `.ai/finalize/`.
- Before a selected real dry-run stage, AgentOffice copies only the current task's existing artifacts into the matching staged directories so adapters do not review evidence from a previous task.

## Verify

```bash
bash scripts/verify.sh
bash scripts/smoke-test.sh demo-task
```

Both scripts are repeatable. `smoke-test.sh` runs the requested task with `--reset`; `verify.sh` uses a fixed local verification task and resets it before each run.

## Static Run Bundle Review Packet

P9 adds a read-only reviewer packet for static run bundles:

```bash
python -m agent_office run-bundle review --path .ai/runs/<RUN_ID>
python -m agent_office run-bundle review --path .ai/runs/<RUN_ID> --json
```

The JSON contract is deterministic and starts with:

```text
kind=static_run_bundle_review_packet
review_schema_version=1
schema_version=1
```

It summarizes run identity, objective/profile, bundle readiness, required review files, actor packet/result evidence, validation status, reviewer commands, reviewer contract, safety flags, execution boundary, and known limitations. It is stri
```
### agent_office/autonomy.py

truncated: true

```text
from __future__ import annotations

from typing import Any

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


SCHEMA_VERSION = 1
PLAN_PACKET_TYPE = "agentoffice_autonomy_mission_plan"
PLAN_MARKER = "AGENTOFFICE_AUTONOMY_MISSION_PLAN"
LEDGER_PACKET_TYPE = "agentoffice_autonomy_run_ledger"
LEDGER_MARKER = "AGENTOFFICE_AUTONOMY_RUN_LEDGER"
ALLOWED_LEDGER_STATUSES = {"pending", "running", "passed", "failed", "skipped", "blocked"}
VALIDATION_SUITES = {"minimal", "release", "full"}


class AutonomyError(RuntimeError):
    pass


SAFETY_BOUNDARIES = [
    ".env is never read",
    "environment variables and token values are never printed",
    "provider, runtime, adapter, and model external behavior is not triggered",
    "GitHub tags and releases are not created, overwritten, or deleted",
    "phase6/mainline is not merged or mutated by autonomy commands",
    "validation uses local allowlisted commands only",
]

STOP_CONDITIONS = [
    "tracked worktree changes exist before a write-oriented milestone starts",
    "required baseline commit or release tag does not match the expected value",
    "a validation suite fails after one focused repair attempt",
    "a milestone requires credentials, tokens, or external provider access",
    "an output path targets .env, a symlink, or path traversal outside the project/output root",
]


def autonomy_plan_payload(goal: str) -> dict[str, Any]:
    normalized = goal.strip().lower()
    plans = _plans()
    if normalized not in plans:
        supported = ", ".join(sorted(plans))
        raise AutonomyError(f"unknown autonomy goal: {goal}. supported goals: {supported}.")
    plan = plans[normalized]
    return {
        "schema_version": SCHEMA_VERSION,
        "packet_type": PLAN_PACKET_TYPE,
        "goal": normalized,
        "status": "ready",
        "local_only": True,
        "network_required": False,
        "provider_runtime_adapter_external_behavior": False,
        "phases": plan["phases"],
        "validation_commands": plan["validation_commands"],
        "stop_conditions": STOP_CONDITIONS,
        "safety_boundaries": SAFETY_BOUNDARIES,
        "expected_artifacts": plan["expected_artifacts"],
        "review_handoff": plan["review_handoff"],
        "merge_gate_handoff": plan["merge_gate_handoff"],
    }


def format_autonomy_plan(payload: dict[str, Any]) -> str:
    lines = [
        PLAN_MARKER,
        f"goal: {payload['goal']}",
        f"status: {payload['status']}",
        f"local_only: {_bool_text(bool(payload['local_only']))}",
        f"network_required: {_bool_text(bool(payload['network_required']))}",
        "phases:",
    ]
    for phase in payload["phases"]:
        lines.append(f"  - {phase['id']}: {phase['name']}")
        lines.append(f"    objective: {phase['objective']}")
        lines.append("    tasks:")
        for task in phase["tasks"]:
            lines.append(f"      * {task}")
    lines.append("validation_commands:")
    for command in payload["validation_commands"]:
        lines.append(f"  - {command}")
    lines.append("stop_conditions:")
    for condition in payload["stop_conditions"]:
        lines.append(f"  - {condition}")
    lines.append("safety_boundaries:")
    for boundary in payload["safety_boundaries"]:
        lines.append(f"  - {boundary}")
    lines.append("expected_artifacts:")
    for artifact in payload["expected_artifacts"]:
        lines.append(f"  - {artifact}")
    lines.append("review_handoff:")
    for item in payload["review_handoff"]:
        lines.append(f"  - {item}")
    lines.append("merge_gate_handoff:")
    for item in payload["merge_gate_handoff"]:
        lines.append(f"  - {item}")
    return "\n".join(lines)


def _plans() -> dict[str, dict[str, Any]]:
    return {
        "release-ops": {
            "phases": [
                _phase("release-state", "Release State Inspection", "Summarize tokenless local release status without GitHub writes.", ["verify v1.0.0 archive and checksum if artifacts are present", "verify local GitHub release readback evidence", "classify skipped_no_token honestly as skipped, not published"]),
                _phase("handoff", "Operator Handoff", "Produce deterministic release handoff and dry-run publish guidance.", ["list required assets and exact manual release checks", "record commands that remain token-gated", "document no-write default behavior"]),
            ],
            "validation_commands": _common_validation() + [
                "python3 -m agent_office v1 verify-release-archive --archive /opt/agent-office/agentoffice-v1.0.0-final-delivery-archive.tar.gz --sha256 /opt/agent-office/agentoffice-v1.0.0-final-delivery-archive.tar.gz.sha256 --json",
                "python3 -m agent_office v1 verify-github-release-readback --dir /opt/agent-office/V1_0_0_GITHUB_RELEASE_API_LONGRUN_READBACK --json",
            ],
            "expected_artifacts": ["release-state JSON/text packet", "GitHub release handoff packet", "dry-run publish plan packet"],
            "review_handoff": ["review release-state honesty and no-token behavior", "confirm no GitHub write path runs without explicit operator action"],
            "merge_gate_handoff": ["require archive/readback verification output", "require no tag or release mutation in git/release logs"],
        },
        "post-v1": {
            "phases": [
                _phase("roadmap", "Post-V1 Roadmap", "Turn v1 release outputs into reviewable post-v1 operating lanes.", ["emit deterministic roadmap JSON/text", "separate hotfix, release-ops, and artifact-review lanes", "preserve mainline and release immutability boundaries"]),
                _phase("evidence", "Evidence Closure", "Collect local validation and review evidence for the next branch gate.", ["record validation commands and results", "generate review packet inputs", "generate merge gate inputs without merging"]),
            ],
            "validation_commands": _common_validation() + ["python3 -m agent_office v1 post-v1-roadmap --json"],
            "expected_artifacts": ["post-v1 roadmap packet", "review evidence bundle", "merge gate packet"],
            "review_handoff": ["review roadmap lane scope and safety non-goals", "check validation evidence before merge discussion"],
            "merge_gate_handoff": ["confirm source branch is pushed and target branch is unchanged", "run full local validation before any no-ff merge"],
        },
        "autonomous-delivery": {
            "phases": [
                _phase("plan", "Autonomous Mission Planner", "Create deterministic local mission plans for delivery goals.", ["emit stable JSON/text plans", "include phases, tasks, validation, stop conditions, and handoffs", "fail cleanly for unknown goals"]),
                _phase("ledger", "Run Ledger And Checkpoints", "Persist resumable local run state for long unattended delivery work.", ["initialize a run ledger under an operator-selected path", "record checkpoints, artifacts, and validation results", "reject traversal, symlink, malformed, and .env paths"]),
                _phase("validate", "Validation Recorder", "Run allowlisted local validation suites and save transcripts.", ["support minimal, release, and full validation suites", "record command, exit code, stdout/stderr paths, and duration", "avoid arbitrary shell command execution"]),
                _phase("review-packet", "Review Packet Generator", "Generate local review bundles without calling Claude or any provider.", ["include commit list, diff stat, name-status, full diff, and snapshots", "summarize validation and caveats", "reject unsafe output paths"]),
                _phase("merge-packet", "Merge Gate Packet Generator", "Generate merge instructions and stop conditions without executing a merge.", ["record source, target, heads, merge-base, and changed files", "emit exact validation and merge commands", "document rollback notes and required reports"]),
            ],
            "validation_commands": _common_validation() + ["python3 -m agent_office autonomy plan --goal autonomous-delivery --json", "python3 -m agent_office autonomy plan --goal autonomous-delivery"],
            "expected_artifacts": ["AUTONOMOUS_DELIVERY_PLATFORM_V1_REPORT.md", "AUTONOMOUS_DELIVERY_PLATFORM_V1_SELF_REVIEW.md", "AUTONOMOUS_DELIVERY_PLATFORM_V1_REVIEW_BUNDLE.md", "AUTONOMOUS_DELIVERY_PLATFORM_V1_REVIEW_BUNDLE.md.sha256"],
            "review_handoff": ["review each milestone as an independently shippable local-only feature", "verify ledger, validation, review, and merge packets do not read .env or call providers", "check tests cover positive, negative, and deterministic output paths"],
            "merge_gate_handoff": ["do not merge automatically", "require final full validation and pushed feature branch", "attach self-review, review bundle, and SHA256 sidecar"],
        },
    }


def _phase(identifier: str, name: str, objective: str, tasks: list[str]) -> dict[str, Any]:
    return {"id": identifier, "name": name, "objective": objective, "tasks": tasks}


def _common_validation() -> list[str]:
    return [
        "python3 -m compileall agent_office tests",
        "python3 -m unittest discover -s tests -p 'test_*.py'",
        "git diff --check",
    ]


def _bool_text(value: bool) -> str:
    return "true" if value else "false"



def autonomy_init_payload(path: str, goal: str, project_root: Path) -> dict[str, Any]:
    run_dir = _safe_run_dir(path, project_root, must_exist=False)
    normalized_goal = goal.strip().lower()
    if normalized_goal not in _plans():
        supported = ", ".join(sorted(_plans()))
        raise AutonomyError(f"unknown autonomy goal: {goal}. supported goals: {supported}.")
    run_dir.mkdir(parents=True, exist_ok=True)
    ledger = {
        "schema_version": SCHEMA_VERSION,
        "packet_type": LEDGER_PACKET_TYPE,
        "goal": normalized_goal,
        "status": "running",
        "path": str(run_dir),
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "checkpoints": [],
        "artifacts": [],
        "validation_records": [],
    }
    _write_ledger(run_dir, ledger)
    return _ledger_response("init", ledger)


def autonomy_status_payload(path: str, project_root: Path) -> dict[str, Any]:
    run_dir = _safe_run_dir(path, project_root, must_exist=True)
    ledger = _read_ledger(run_dir)
    return _ledger_response("status", ledger)


def autonomy_checkpoint_payload(path: str, name: str, status: str, project_root: Path) -> dict[str, Any]:
    if status not in ALLOWED_LEDGER_STATUSES:
        raise AutonomyError(f"invalid checkpoint status: {status}.")
    if not name.strip():
        raise AutonomyError("checkpoint name is required.")
    run_dir = _safe_run_dir(path, project_root, must_exist=True)
    ledger = _read_ledger(run_dir)
    checkpoint = {"name": name.strip(), "status": status, "recorded_at": _now_iso()}
    ledger["checkpoints"].append(checkpoint)
    ledger["status"] = status
    ledger["updated_at"] = checkpoint["recorded_at"]
    _write_ledger(run_dir, ledger)
    return _ledger_response("checkpoint", ledger, checkpoint=checkpoint)


def autonomy_report_payload(path: str, project_root: Path) -> dict[str, Any]:
    run_dir = _safe_run_dir(path, project_root, must_exist=True)
    ledger = _read_ledger(run_dir)
    summary = {
        "checkpoint_count": len(ledger["checkpoints"]),
        "artifact_count": len(ledger["artifacts"]),
        "validation_record_count": len(ledger["validation_records"]),
        "latest_checkpoint": ledger["checkpoints"][-1] if ledger["checkpoints"] else None,
    }
    return _ledger_response("report", ledger, summary=summary)



def autonomy_validate_payload(path: str, suite: str, project_root: Path) -> dict[str, Any]:
    if suite not in VALIDATION_SUITES:
        supported = ", ".join(sorted(VALIDATION_SUITES))
        raise AutonomyError(f"unknown validation suite: {suite}. supported suites: {supported}.")
    run_dir = _safe_run_dir(path, project_root, must_exist=True)
    ledger = _read_ledger(run_dir)
    validation_dir = run_dir / "validation" / _validation_run_id(suite)
    validation_dir.mkdir(parents=True, exist_ok=False)
    commands = _validation_commands(suite)
    records = []
    for index, command in enumerate(commands, start=1):
        records.append(_run_validation_command(command, index, validation_dir, project_root))
    ok = all(record["exit_code"] == 0 for record in records)
    validation_record = {
        "suite": suite,
        "status": "passed" if ok else "failed",
        "recorded_at": _now_iso(),
        "commands": records,
    }
    ledger["validation_records"].append(validation_record)
    ledger["status"] = validation_record["status"]
    ledger["updated_at"] = validation_record["recorded_at"]
    _write_ledger(run_dir, ledger)
    return {"ok": ok, "action": "validate", "suite": suite, "ledger": ledger, "validation": validation_record}


def format_autonomy_validation(payload: dict[str, Any]) -> str:
    validation = payload["validation"]
    lines = [
        "AGENTOFFICE_AUTONOMY_VALIDATION",
        f"suite: {payload['suite']}",
        f"status: {validation['status']}",
        f"ok: {_bool_text(bool(payload['ok']))}",
        "commands:",
    ]
    for record in validation["commands"]:
        lines.append(f"  - {record['command']}: exit_code={record['exit_code']} duration_seconds={record['duration_seconds']}")
        lines.append(f"    stdout: {record['stdout_path']}")
        lines.append(f"    stderr: {record['stderr_path']}")
    return "\n".join(lines)


def autonomy_review_packet_payload(base: str, head: str, out: str, project_root: Path) -> dict[str, Any]:
    out_path = _safe_output_file(out, project_root)
    base_commit = _git_capture(["rev-parse", "--verify", base], project_root, "review_packet_base").strip()
    head_commit = _git_capture(["rev-parse", "--verify", head], project_root, "review_packet_head").strip()
    branch = _git_capture(["branch", "--show-current"], project_root, "review_packet_branch").strip() or "detached"
    commits = _git_capture(["log", "--oneline", f"{base_commit}..{head_commit}"], project_root, "review_packet_log").splitlines()
    diff_stat = _git_capture(["diff", "--stat", base_commit, head_commit], project_root, "review_packet_diff_stat")
    name_status = _git_capture(["diff", "--name-status", base_commit, head_commit], project_root, "review_packet_name_status")
    full_diff = _git_capture(["diff", "--no-ext-diff", base_commit, head_commit], project_root, "review_packet_full_diff")
    snapshots = _changed_file_snapshots(name_status, head_commit, project_root)
    bundle = _format_review_packet_markdown(
        base_commit=base_commit,
        head_commit=head_commit,
        branch=branch,
        commits=commits,
        diff_stat=diff_stat,
        name_status=name_status,
        full_diff=full_diff,
        snapshots=snapshots,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists() and out_path.is_symlink():
        raise AutonomyError("review packet output symlink refused.")
    out_path.write_text(bundle, encoding="utf-8")
    return {
        "ok": True,
        "action": "review-packet",
        "base": base_commit,
        "head": head_commit,
        "branch": branch,
        "out": str(out_path),
        "commit_count": len(commits),
        "snapshot_count": len(snapshots),
        "safety_boundaries": SAFETY_BOUNDARIES,
    }


def format_autonomy_review_packet(payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            "AGENTOFFICE_AUTONOMY_REVIEW_PACKET",
            f"ok: {_bool_text(bool(payload['ok']))}",
            f"branch: {payload['branch']}",
            f"base: {payload['base']}",
            f"head: {payload['head']}",
            f"out: {payload['out']}",
            f"commits: {payload['commit_count']}",
            f"snapshots: {payload['snapshot_count']}",
        ]
    )


def autonomy_merge_packet_payload(source: str, target: str, project_root: Path) -> dict[str, Any]:
    source_head = _git_capture(["rev-parse", "--verify", source], project_root, "merge_packet_source").strip()
    target_head = _git_capture(["rev-parse", "--verify", target], project_root, "merge_packet_target").strip()
    merge_base = _git_capture(["merge-base", target_head, source_head], project_root, "merge_packet_merge_base").strip()
    changed_files_text = _git_capture(["diff", "--name-status", merge_base, source_head], project_root, "merge_packet_changed_files")
    changed_files = [line for line in changed_files_text.splitlines() if line.strip()]
    payload = {
        "ok": True,
        "action": "merge-packet",
        "source_branch": source,
        "target_branch": target,
        "source_head": source_head,
        "target_head": target_head,
        "merge_base": merge_base,
        "changed_files": changed_files,
        "required_validations": [
            "python3 -m compileall agent_office tests",
            "python3 -m unittest",
            "python3 -m unittest discover -s tests -p 'test_*.py'",
            "python3 -m agent_office doctor --adapters",
            "./scripts/verify.sh",
            "git diff --check",
        ],
        "reports_required": [
            "AUTONOMOUS_DELIVERY_PLATFORM_V1_REPORT.md",
            "AUTONOMOUS_DELIVERY_PLATFORM_V1_SELF_REVIEW.md",
            "AUTONOMOUS_DELIVERY_PLATFORM_V1_REVIEW_BUNDLE.md",
            "AUTONOMOUS_DELIVERY_PLATFORM_V1_REVIEW_BUNDLE.md.sha256",
        ],
        "stop_conditions": STOP_CONDITIONS + [
            "source or target head differs from this packet at merge time",
            "feature branch has unpushed commits",
            "review bundle or self-review is missing",
        ],
        "merge_commands": [
            f"git checkout {target}",
            f"git pull --ff-only origin {target}",
            f"git merge --no-ff --no-commit {source}",
            "python3 -m compileall agent_office tests",
            "python3 -m unittest discover -s tests -p 'test_*.py'",
            "git diff --check --cached",
            f"git commit -m 'Merge {source}'",
        ],
        "post_merge_validation": [
            "python3 -m compileall agent_office tests",
            "python3 -m unittest",
            "python3 -m unittest discover -s tests -p 'test_*.py'",
            "git diff --check",
        ],
        "rollback_notes": [
            "Before commit, abort a staged merge with git merge --abort.",
            "After commit, revert the merge commit instead of force pushing.",
            "Do not delete or overwrite tags or GitHub Releases during rollback.",
        ],
        "merge_performed": False,
    }
    return payload


def format_autonomy_merge_packet(payload: dict[str, Any]) -> str:
    lines = [
        "AGENTOFFICE_AUTONOMY_MERGE_PACKET",
        f"ok: {_bool_text(bool(payload['ok']))}",
        f"source_branch: {payload['source_branch']}",
        f"target_branch: {payload['target_branch']}",
        f"source_head: {payload['source_head']}",
        f"target_head: {payload['target_head']}",
        f"merge_base: {payload['merge_base']}",
        "changed_files:",
    ]
    lines.extend(f"  - {item}" for item in payload["changed_files"] or ["none"])
    lines.append("required_validations:")
    lines.extend(f"  - {item}" for item in payload["required_validations"])
    lines.append("reports_required:")
    lines.extend(f"  - {item}" for item in payload["reports_required"])
    lines.append("stop_conditions:")
    lines.extend(f"  - {item}" for item in payload["stop_conditions"])
    lines.append("exact_merge_commands:")
    lines.extend(f"  - {item}" for item in payload["merge_commands"])
    lines.append("post_merge_validation:")
    lines.extend(f"  - {item}" for item in payload["post_merge_validation"])
    lines.append("rollback_notes:")
    lines.extend(f"  - {item}" for item in payload["rollback_notes"])
    lines.append("merge_performed: false")
    return "\n".join(lines)

def format_autonomy_ledger(payload: dict[str, Any]) -> str:
    ledger = payload["ledger"]
    lines = [
        LEDGER_MARKER,
        f"action: {payload['action']}",
        f"goal: {ledger['goal']}",
        f"status: {ledger['status']}",
        f"path: {ledger['path']}",
        f"checkpoints: {len(ledger['checkpoints'])}",
        f"artifacts: {len(ledger['artifacts'])}",
        f"validation_records: {len(ledger['validation_records'])}",
    ]
    checkpoint = payload.get("checkpoint")
    if checkpoint:
        lines.append(f"latest_checkpoint: {checkpoint['name']} ({checkpoint['status']})")
    summary = payload.get("summary")
    if summary:
        lines.append("summary:")
        lines.append(f"  checkpoint_count: {summary['checkpoint_count']}")
        lines.append(f"  artifact_count: {summary['artifact_count']}")
        lines.append(f"  validation_record_count: {summary['validation_record_count']}")
        latest = summary.get("latest_checkpoint")
        lines.append(f"  latest_checkpoint: {latest['name'] + ' (' + latest['status'] + ')' if latest else 'none'}")
    return "\n".join(lines)


def _ledger_response(action: str, ledger: dict[str, Any], **extra: Any) -> dict[str, Any]:
    payload = {"ok": True, "action": action, "ledger": ledger}
    payload.update(extra)
    return payload



def _safe_output_file(path: str, project_root: Path) -> Path:
    if not str(path).strip():
        raise AutonomyError("output path is required.")
    candidate = Path(path)
    if any(part in {"..", ""} for part in candidate.parts) or any(part == ".env" for part in candidate.parts):
        raise AutonomyError("output path contains refused traversal or .env component.")
    if not candidate.is_absolute():
        candidate = project_root / candidate
    _reject_symlink_components(candidate if candidate.exists() else candidate.parent)
    candidate = candidate.resolve(strict=False)
    root = project_root.resolve(strict=False)
    tmp = Path(os.getenv("TMPDIR", "/tmp")).resolve(strict=False)
    if not _is_relative_to(candidate, root) and not _is_relative_to(candidate, tmp):
        raise AutonomyError("output path must stay under the project root or temp directory.")
    if candidate.exists() and candidate.is_dir():
        raise AutonomyError("output path is a directory.")
    return candidate


def _git_capture(args: list[str], project_root: Path, label: str) -> str:
    result = subprocess.run(["git", *args], cwd=project_root, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "git command failed").strip().splitlines()
        detail = message[0] if message else "git command failed"
        raise AutonomyError(f"{label} failed: {detail}")
    return result.stdout


def _changed_file_snapshots(name_status: str, head_commit: str, project_root: Path) -> list[dict[str, Any]]:
    snapshots = []
    for raw_line in name_status.splitlines():
        parts = raw_line.split("\t")
        if len(parts) < 2:
            continue
        status = parts[0]
        file_path = parts[-1]
        path_obj = Path(file_path)
        if status.startswith("D") or any(part == ".env" for part in path_obj.parts):
            snapshots.append({"path": file_path, "status": status, "skipped": True, "reason": "deleted_or_refused_path"})
            continue
        result = subprocess.run(["git", "show", f"{head_commit}:{file_path}"], cwd=project_root, text=True, capture_output=True, check=False)
        if result.returncode != 0:
            snapshots.append({"path": file_path, "status": status, "skipped": True, "reason": "snapshot_unavailable"})
            continue
        content = result.stdout
        truncated = len(content) > 20000
        snapshots.append({"path": file_path, "status": status, "skipped": False, "truncated": truncated, "content": content[:20000]})
    return snapshots


def _format_review_packet_markdown(*, base_commit: str, head_commit: str, branch: str, commits: list[str], diff_stat: str, name_status: str, full_diff: str, snapshots: list[dict[str, Any]]) -> str:
    lines = [
        "# AgentOffice Autonomy Review Packet",
        "",
        "Marker: AGENTOFFICE_AUTONOMY_REVIEW_PACKET",
        "",
        "## Scope",
        "",
        f"- branch: `{branch}`",
        f"- base: `{base_commit}`",
        f"- head: `{head_commit}`",
        "",
        "## Safety Boundaries",
        "",
    ]
    lines.extend(f"- {boundary}" for boundary in SAFETY_BOUNDARIES)
    lines.extend(["", "## Commit List", "", "```text"])
    lines.extend(commits or ["none"])
    lines.extend(["```", "", "## Diff Stat", "", "```text", diff_stat.rstrip() or "none", "```", "", "## Name Status", "", "```text", name_status.rstrip() or "none", "```", "", "## Full Diff", "", "```diff", full_diff.rstrip() or "none", "```", "", "## Changed File Snapshots", ""])
    for snapshot in snapshots:
        lines.append(f"### {snapshot['path']}")
        lines.append("")
        lines.append(f"- status: `{snapshot['status']}`")
        if snapshot.get("skipped"):
            lines.append(f"- skipped: `{snapshot['reason']}`")
            lines.append("")
            continue
        lines.append(f"- truncated: `{_bool_text(bool(snapshot['truncated']))}`")
        lines.append("")
        lines.append("```text")
        lines.append(str(snapshot["content"]).rstrip())
        lines.append("```")
        lines.append("")
    lines.extend(["## Validation Summary", "", "Validation is supplied by the active autonomy ledger or external gate report.", "", "## Requested Review Focus", "", "- correctness of changed behavior", "- safety boundary preservation", "- deterministic output contracts", "- missing tests or operator caveats", "", "## Known Caveats", "", "- This packet is generated locally and does not call external reviewers or providers.", ""])
    return "\n".join(lines)

def _safe_run_dir(path: str, project_root: Path, *, must_exist: bool) -> Path:
    if not str(path).strip():
        raise AutonomyError("run path is required.")
    candidate = Path(path)
    if any(part in {"..", ""} for part in candidate.parts) or any(part == ".env" for part in candidate.parts):
        raise AutonomyError("run path contains refused traversal or .env component.")
    if not candidate.is_absolute():
        candidate = project_root / candidate
    _reject_symlink_components(candidate)
    candidate = candidate.resolve(strict=False)
    root = project_root.resolve(strict=False)
    tmp = Path(os.getenv("TMPDIR", "/tmp")).resolve(strict=False)
    if not _is_relative_to(candidate, root) and not _is_relative_to(candidate, tmp):
        raise AutonomyError("run path must stay under the project root or temp directory.")
    current = candidate if candidate.exists() else candidate.parent
    while current != current.parent:
        if current.exists() and current.is_symlink():
            raise AutonomyError("run path symlink refused.")
        if current == root or current == tmp:
            break
        current = current.parent
    if must_exist and not candidate.exists():
        raise AutonomyError("run ledger path is missing.")
    if candidate.exists() and not candidate.is_dir():
        raise AutonomyError("run ledger path is not a directory.")
    return candidate


def _reject_symlink_components(path: Path) -> None:
    current = path
    candidates = []
    while current != current.parent:
        candidates.append(current)
        current = current.parent
    for candidate in candidates:
        if candidate.exists() and candidate.is_symlink():
            raise AutonomyError("run path symlink refused.")


def _ledger_path(run_dir: Path) -> Path:
    return run_dir / "ledger.json"


def _read_ledger(run_dir: Path) -> dict[str, Any]:
    path = _ledger_path(run_dir)
    if path.is_symlink():
        raise AutonomyError("run ledger symlink refused.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AutonomyError("run ledger file is missing.") from exc
    except json.JSONDecodeError as exc:
        raise AutonomyError("run ledger file is malformed JSON.") from exc
    except OSError as exc:
        raise AutonomyError("run ledger file is unreadable.") from exc
    if not isinstance(data, dict):
        raise AutonomyError("run ledger file must contain a JSON object.")
    for key in ("schema_version", "packet_type", "goal", "status", "path", "created_at", "updated_at", "checkpoints", "artifacts", "validation_records"):
        if key not in data:
            raise AutonomyError(f"run ledger missing required key: {key}.")
    if data["packet_type"] != LEDGER_PACKET_TYPE:
        raise AutonomyError("run ledger packet type is invalid.")
    if data["status"] not in ALLOWED_LEDGER_STATUSES:
        raise AutonomyError("run ledger status is invalid.")
    for key in ("checkpoints", "artifacts", "validation_records"):
        if not isinstance(data[key], list):
            raise AutonomyError(f"run ledger {key} must be a list.")
    return data


def _write_ledger(run_dir: Path, ledger: dict[str, Any]) -> None:
    path = _ledger_path(run_dir)
    if path.exists() and path.is_symlink():
        raise AutonomyError("run ledger symlink refused.")
    tmp_path = run_dir / "ledger.json.tmp"
    tmp_path.write_text(json.dumps(ledger, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    tmp_path.replace(path)



def _validation_commands(suite: str) -> list[list[str]]:
    minimal = [
        ["python3", "-m", "compileall", "agent_office", "tests"],
        ["python3", "-m", "unittest", "tests.test_autonomy_plan_cli"],
        ["git", "diff", "--check"],
    ]
    release = [
        ["python3", "-m", "agent_office", "v1", "final-delivery", "--json"],
        ["python3", "-m", "agent_office", "v1", "verify-release-a
```
### agent_office/cli.py

truncated: true

```text
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .adapters.base import AdapterError, AdapterInvocation, AdapterResult, mask_secrets
from .adapters.mock import MockAdapter
from .adapters.modes import adapter_for_role, load_adapter_mode_config, validate_adapter_mode
from .adapters.registry import get_adapter
from .doctor import (
    bool_text,
    collect_doctor,
    collect_profile_plan_audit,
    doctor_json,
    format_adapters,
    format_doctor,
    format_profile_plan_audit,
)
from .artifact_registry import (
    export_evidence_payload,
    format_export_evidence,
    format_lifecycle_status,
    format_lifecycle_verify,
    format_registry_inspect,
    format_registry_list,
    format_registry_status,
    lifecycle_status_payload,
    lifecycle_verify_payload,
    registry_inspect_payload,
    registry_list_payload,
    registry_status_payload,
)
from .orchestration import (
    format_orchestrate_inspect,
    format_orchestrate_run,
    format_orchestrate_validate,
    orchestrate_inspect_payload,
    orchestrate_run_payload,
    orchestrate_validate_payload,
)
from .runtime_foundation import (
    RuntimeFoundationError,
    format_runtime_payload,
    runtime_close_payload,
    runtime_evidence_payload,
    runtime_error_payload,
    runtime_governance_payload,
    runtime_init_payload,
    runtime_job_payload,
    runtime_packet_payload,
    runtime_plan_payload,
    runtime_replay_payload,
    runtime_run_payload,
    runtime_status_payload,
    runtime_worker_adapter_payload,
    runtime_worker_audit_closure_payload,
    runtime_worker_archive_index_payload,
    runtime_worker_archive_replay_verification_payload,
    runtime_worker_archive_verify_payload,
    runtime_worker_audit_replay_payload,
    runtime_worker_compact_archive_payload,
    runtime_worker_compact_archive_verify_payload,
    runtime_worker_closure_evidence_payload,
    runtime_worker_external_review_handoff_payload,
    runtime_worker_delivery_bundle_payload,
    runtime_worker_failed_review_recovery_payload,
    runtime_worker_final_delivery_readiness_payload,
    runtime_worker_delivery_gate_payload,
    runtime_worker_gate_payload,
    runtime_worker_invocation_packet_payload,
    runtime_worker_merge_readiness_payload,
    runtime_worker_provenance_manifest_payload,
    runtime_worker_provenance_replay_payload,
    runtime_worker_provenance_verify_payload,
    runtime_worker_rc_promotion_gate_payload,
    runtime_worker_release_candidate_export_payload,
    runtime_worker_promotion_evidence_payload,
    runtime_worker_dry_run_publish_payload,
    runtime_worker_rejection_packet_payload,
    runtime_worker_release_candidate_payload,
    runtime_worker_release_closure_payload,
    runtime_worker_result_intake_payload,
    runtime_worker_reviewer_archive_import_payload,
    runtime_worker_result_replay_payload,
    runtime_worker_reviewer_attestation_payload,
)
from .objectives import (
    ObjectiveSpecError,
    objective_detail_payload,
    objective_listing_payload,
    objective_registry_validation_payload,
    objective_spec_payload,
)
from .planner import PlanningError, execution_blueprint_payload
from .packets import (
    PacketError,
    execution_packet_payload,
    packet_contract_validation_payload,
)
from .profiles import (
    ALLOWED_ROLES,
    ProfileError,
    default_profile_name,
    get_profile,
    list_profiles,
    profile_plan_payload,
    profile_plan_contract_audit_payload,
    profile_plans_payload,
    profile_plans_contract_audit_payload,
)
from .review_artifact import (
    ReviewArtifactError,
    close_pending_review_artifact_error_payload,
    close_pending_review_artifact_payload,
    export_review_artifact_payload,
    format_review_artifact_close_pending,
    format_review_artifact_export,
    format_review_artifact_self_check,
    review_artifact_error_payload,
    self_check_review_artifact_payload,
)
from . import review_lifecycle
from .run_bundle import (
    RunBundleError,
    export_review_error_payload,
    export_review_run_bundle_payload,
    format_actor_result_intake,
    format_run_bundle_catalog,
    format_run_bundle_gate,
    format_run_bundle_handoff,
    format_run_bundle_inspection,
    format_run_bundle_preview,
    format_run_bundle_review,
    format_run_bundle_results,
    format_run_bundle_status,
    format_run_bundle_validation,
    format_run_bundle_workflow,
    format_run_bundle_export_review,
    gate_run_bundle_payload,
    handoff_run_bundle_payload,
    inspect_run_bundle_payload,
    intake_actor_result_payload,
    list_run_bundles_payload,
    results_run_bundle_payload,
    review_run_bundle_payload,
    run_bundle_preview_payload,
    status_run_bundle_payload,
    validate_run_bundle_payload,
    workflow_run_bundle_payload,
    write_run_bundle,
)

from .v1_final_delivery import (
    V1FinalDeliveryError,
    build_final_delivery_packet,
    final_delivery_error_payload,
    format_final_delivery_packet,
    format_final_delivery_verify,
    verify_final_delivery_packet,
    write_final_delivery_packet,
)
from .v1_post_release_ops import (
    format_github_release_handoff,
    format_github_release_plan,
    format_github_release_readback_verify,
    format_post_v1_roadmap,
    format_release_archive_verify,
    format_release_candidate,
    format_release_state,
    github_release_handoff_payload,
    github_release_plan_payload,
    post_v1_roadmap_payload,
    release_candidate_payload,
    release_state_payload,
    verify_github_release_readback_payload,
    verify_release_archive_payload,
)
from .autonomy import (
    AutonomyError,
    autonomy_checkpoint_payload,
    autonomy_init_payload,
    autonomy_merge_packet_payload,
    autonomy_plan_payload,
    autonomy_report_payload,
    autonomy_review_packet_payload,
    autonomy_status_payload,
    autonomy_validate_payload,
    format_autonomy_ledger,
    format_autonomy_merge_packet,
    format_autonomy_plan,
    format_autonomy_review_packet,
    format_autonomy_validation,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASKS_ROOT = PROJECT_ROOT / ".ai" / "tasks"
FINAL_FOR_CLAUDE_LIMIT = 4000
MAX_REWORK_ROUNDS = 2
DRY_RUN_REAL_ADAPTERS = {"gemini", "codex", "grok", "claude"}
STAGED_REAL_ADAPTER_ROLES = {
    "gemini": "context",
    "codex": "implement",
    "grok": "redteam",
    "claude": "final",
}
STAGED_RUNTIME_DIR_NAMES = ("context", "codex", "grok", "claude", "finalize")
STAGED_ARTIFACT_DESTINATION_PARTS = (
    (".ai", "context", "gemini-context.md"),
    (".ai", "codex", "patch.diff"),
    (".ai", "codex", "codex-report.md"),
    (".ai", "grok", "redteam-report.md"),
    (".ai", "finalize", "final-for-claude.md"),
)

STATES = {
    "CREATED",
    "CONTEXT_READY",
    "IMPLEMENTED",
    "REVIEWED",
    "SUMMARIZED",
    "CLAUDE_DECIDED",
    "APPROVED",
    "REQUEST_CHANGES",
    "REJECTED",
}

TERMINAL_STATES = {"APPROVED", "REJECTED"}


class AgentOfficeError(RuntimeError):
    pass


@dataclass(frozen=True)
class TaskPaths:
    root: Path
    task_json: Path
    brief: Path
    gemini_context: Path
    codex_report: Path
    patch_diff: Path
    grok_review: Path
    final_for_claude: Path
    claude_decision: Path


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def task_paths(task_id: str) -> TaskPaths:
    root = TASKS_ROOT / task_id
    return TaskPaths(
        root=root,
        task_json=root / "task.json",
        brief=root / "brief.md",
        gemini_context=root / "gemini-context.md",
        codex_report=root / "codex-report.md",
        patch_diff=root / "patch.diff",
        grok_review=root / "grok-review.md",
        final_for_claude=root / "final-for-claude.md",
        claude_decision=root / "claude-decision.md",
    )


def validate_task_id(task_id: str) -> None:
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
    if not task_id or any(ch not in allowed for ch in task_id):
        raise AgentOfficeError("TASK_ID may only contain letters, numbers, dash, underscore, and dot.")
    if task_id in {".", ".."}:
        raise AgentOfficeError("TASK_ID is invalid.")


def reset_task(task_id: str) -> None:
    validate_task_id(task_id)
    paths = task_paths(task_id)
    resolved_root = paths.root.resolve()
    resolved_tasks_root = TASKS_ROOT.resolve()
    if resolved_tasks_root not in resolved_root.parents:
        raise AgentOfficeError(f"Refusing to reset task outside tasks root: {paths.root}")
    if paths.root.exists():
        shutil.rmtree(paths.root)


def clear_staged_runtime_dirs() -> None:
    ai_root = (PROJECT_ROOT / ".ai").resolve()
    for name in STAGED_RUNTIME_DIR_NAMES:
        path = PROJECT_ROOT / ".ai" / name
        resolved = path.resolve()
        expected = (PROJECT_ROOT / ".ai" / name).resolve()
        if resolved != expected or resolved.parent != ai_root:
            raise AgentOfficeError(f"Refusing to clear unsafe staged runtime path: {path}")
        if not path.exists():
            continue
        if path.is_symlink() or not path.is_dir():
            raise AgentOfficeError(f"Refusing to clear non-directory staged runtime path: {path}")
        shutil.rmtree(path)


def allowed_staged_artifact_destinations() -> set[Path]:
    return {(PROJECT_ROOT.joinpath(*parts)).resolve() for parts in STAGED_ARTIFACT_DESTINATION_PARTS}


def copy_task_artifact_if_exists(paths: TaskPaths, source: Path, destination: Path) -> bool:
    if source.is_symlink():
        raise AgentOfficeError(f"Refusing to stage symlink task artifact: {source}")
    if not source.exists():
        return False
    if not source.is_file():
        raise AgentOfficeError(f"Refusing to stage non-file task artifact: {source}")
    resolved_source = source.resolve()
    resolved_task_root = paths.root.resolve()
    if resolved_source != resolved_task_root and resolved_task_root not in resolved_source.parents:
        raise AgentOfficeError(f"Refusing to stage artifact outside current task root: {source}")
    resolved_destination = destination.resolve()
    if resolved_destination not in allowed_staged_artifact_destinations():
        raise AgentOfficeError(f"Refusing to stage artifact to unsupported destination: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    return True


def stage_current_task_artifacts(adapter_name: str, paths: TaskPaths) -> None:
    staged_context = PROJECT_ROOT / ".ai" / "context" / "gemini-context.md"
    staged_codex_patch = PROJECT_ROOT / ".ai" / "codex" / "patch.diff"
    staged_codex_report = PROJECT_ROOT / ".ai" / "codex" / "codex-report.md"
    staged_grok_report = PROJECT_ROOT / ".ai" / "grok" / "redteam-report.md"
    staged_final_packet = PROJECT_ROOT / ".ai" / "finalize" / "final-for-claude.md"

    if adapter_name in {"codex", "grok", "claude"}:
        copy_task_artifact_if_exists(paths, paths.gemini_context, staged_context)
    if adapter_name in {"grok", "claude"}:
        copy_task_artifact_if_exists(paths, paths.patch_diff, staged_codex_patch)
        copy_task_artifact_if_exists(paths, paths.codex_report, staged_codex_report)
    if adapter_name == "claude":
        copy_task_artifact_if_exists(paths, paths.grok_review, staged_grok_report)
        copy_task_artifact_if_exists(paths, paths.final_for_claude, staged_final_packet)


def load_task(paths: TaskPaths) -> dict[str, Any]:
    if not paths.task_json.exists():
        raise AgentOfficeError(f"Task does not exist: {paths.root}")
    return json.loads(paths.task_json.read_text(encoding="utf-8"))


def save_task(paths: TaskPaths, task: dict[str, Any]) -> None:
    task["updated_at"] = now_iso()
    tmp = paths.task_json.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(task, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(paths.task_json)


def append_history(task: dict[str, Any], event: str, detail: str) -> None:
    task.setdefault("history", []).append({"at": now_iso(), "event": event, "detail": detail})


def transition(paths: TaskPaths, task: dict[str, Any], new_state: str, detail: str) -> None:
    if new_state not in STATES:
        raise AgentOfficeError(f"Unknown state: {new_state}")
    old_state = task["state"]
    task["state"] = new_state
    append_history(task, f"{old_state}->{new_state}", detail)
    save_task(paths, task)


def require_state(task: dict[str, Any], allowed: set[str]) -> None:
    state = task["state"]
    if state not in allowed:
        raise AgentOfficeError(f"Invalid state {state}; expected one of: {', '.join(sorted(allowed))}")
    if state in TERMINAL_STATES:
        raise AgentOfficeError(f"Task is terminal: {state}")


def resolve_mode(args: argparse.Namespace, role: str) -> str:
    mock = bool(getattr(args, "mock", False))
    real = bool(getattr(args, "real", False))
    if mock and real:
        raise AgentOfficeError("Use only one of --mock or --real.")
    if real:
        return "real"
    if mock:
        return "mock"
    if role in {"context", "implement", "run-demo"}:
        env_mode = os.environ.get("AGENTOFFICE_AGENT_MODE", "mock").strip().lower()
        if env_mode == "real":
            return "real"
    return "mock"


def require_mock_mode(args: argparse.Namespace, role: str) -> None:
    if resolve_mode(args, role) == "real":
        raise AgentOfficeError(f"{role} real adapter is not implemented in this phase. Use --mock.")


def build_invocation(args: argparse.Namespace, paths: TaskPaths) -> AdapterInvocation:
    timeout = getattr(args, "timeout", None)
    if timeout is not None and timeout <= 0:
        raise AgentOfficeError("--timeout must be a positive integer.")
    return AdapterInvocation(
        task_id=args.task_id,
        project_root=PROJECT_ROOT,
        paths=paths,
        timeout_seconds=timeout,
        max_rework_rounds=MAX_REWORK_ROUNDS,
        final_for_claude_limit=FINAL_FOR_CLAUDE_LIMIT,
    )


def run_adapter(role: str, args: argparse.Namespace, paths: TaskPaths):
    mode = resolve_mode(args, role)
    adapter_name = getattr(args, "adapter", None)
    if mode == "real":
        return run_real_adapter(role, args, paths, adapter_name)
    try:
        adapter = get_adapter(role, mode, adapter_name)
        method = getattr(adapter, role)
        return method(build_invocation(args, paths))
    except AdapterError as exc:
        raise AgentOfficeError(str(exc)) from exc


def run_real_adapter(role: str, args: argparse.Namespace, paths: TaskPaths, adapter_name: str | None) -> AdapterResult:
    config_name = adapter_name if adapter_name not in {None, "mock"} else adapter_for_role(role)
    if not config_name:
        raise AgentOfficeError(f"No staged real adapter is registered for role `{role}`. Use --mock.")
    dry_run_var = f"AGENTOFFICE_{config_name.upper()}_DRY_RUN"
    previous_dry_run = os.environ.get(dry_run_var)
    if bool(getattr(args, "dry_run", False)):
        os.environ[dry_run_var] = "true"
    try:
        config = load_adapter_mode_config(config_name)
        if config.role != role:
            raise AgentOfficeError(f"Adapter `{config.name}` is registered for role `{config.role}`, not `{role}`.")
        if config.mode != "real":
            raise AgentOfficeError(
                f"{config.name} adapter mode is `{config.mode}`. Set AGENTOFFICE_{config.name.upper()}_MODE=real explicitly or use --mock."
            )

        validation = validate_adapter_mode(config)
        if validation.errors:
            reason = "; ".join(validation.errors)
            return maybe_fallback_to_mock(role, args, paths, config.name, config.fallback_to_mock, reason)

        if config.name not in DRY_RUN_REAL_ADAPTERS and config.dry_run:
            reason = f"{config.name} adapter dry_run=true; real command was not executed."
            return maybe_fallback_to_mock(role, args, paths, config.name, config.fallback_to_mock, reason)

        try:
            adapter = get_adapter(role, "real", config.name)
            method = getattr(adapter, role)
            return method(build_invocation(args, paths))
        except AdapterError as exc:
            return maybe_fallback_to_mock(role, args, paths, config.name, config.fallback_to_mock, str(exc))
    finally:
        if bool(getattr(args, "dry_run", False)):
            if previous_dry_run is None:
                os.environ.pop(dry_run_var, None)
            else:
                os.environ[dry_run_var] = previous_dry_run


def maybe_fallback_to_mock(
    role: str,
    args: argparse.Namespace,
    paths: TaskPaths,
    adapter_name: str,
    fallback_to_mock: bool,
    reason: str,
) -> AdapterResult:
    safe_reason = mask_secrets(reason)
    if not fallback_to_mock:
        raise AgentOfficeError(f"{adapter_name} real adapter failed safely: {safe_reason}")
    mock = MockAdapter()
    method = getattr(mock, role)
    result = method(build_invocation(args, paths))
    metadata = dict(result.metadata)
    metadata.update({"fallback_used": True, "real_adapter": adapter_name, "fallback_reason": safe_reason})
    return AdapterResult(
        detail=f"{result.detail} fallback_used=true; real_adapter={adapter_name}; reason={safe_reason}",
        decision=result.decision,
        stdout=result.stdout,
        stderr=result.stderr,
        metadata=metadata,
    )


def write_file(path: Path, content: str) -> None:
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def read_if_exists(path: Path, max_chars: int | None = None) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8")
    if max_chars is not None and len(text) > max_chars:
        return text[:max_chars] + "\n...[truncated]..."
    return text


def cmd_new(args: argparse.Namespace) -> int:
    validate_task_id(args.task_id)
    paths = task_paths(args.task_id)
    if paths.root.exists():
        raise AgentOfficeError(f"Task already exists: {paths.root}")
    paths.root.mkdir(parents=True)
    task = {
        "task_id": args.task_id,
        "state": "CREATED",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "rework_rounds": 0,
        "max_rework_rounds": MAX_REWORK_ROUNDS,
        "final_for_claude_limit": FINAL_FOR_CLAUDE_LIMIT,
        "agents": {
            "gemini": "context scan and compressed summary",
            "codex": "implementation, bug fixing, tests",
            "grok_build": "red-team review",
            "claude_code": "final decision only from final-for-claude.md",
            "orchestrator": "state machine, task queue, logs, artifacts",
        },
        "history": [{"at": now_iso(), "event": "CREATED", "detail": "Task workspace initialized."}],
    }
    save_task(paths, task)
    write_file(
        paths.brief,
        f"""# Task Brief

Task ID: `{args.task_id}`

## Goal

Describe the user request here before running real providers.

## Collaboration Rules

- Agents communicate through files in this directory.
- Gemini writes `gemini-context.md`.
- Codex writes `codex-report.md` and `patch.diff`.
- Grok Build writes `grok-review.md`.
- Orchestrator writes `final-for-claude.md`.
- Claude reads only `final-for-claude.md` and writes `claude-decision.md`.
""",
    )
    print(f"created {paths.root}")
    return 0


def cmd_context(args: argparse.Namespace) -> int:
    paths = task_paths(args.task_id)
    task = load_task(paths)
    require_state(task, {"CREATED", "REQUEST_CHANGES"})
    result = run_adapter("context", args, paths)
    transition(paths, task, "CONTEXT_READY", result.detail)
    print("state=CONTEXT_READY")
    return 0


def cmd_implement(args: argparse.Namespace) -> int:
    paths = task_paths(args.task_id)
    task = load_task(paths)
    require_state(task, {"CONTEXT_READY", "REQUEST_CHANGES"})
    if task["state"] == "REQUEST_CHANGES":
        if int(task.get("rework_rounds", 0)) >= MAX_REWORK_ROUNDS:
            raise AgentOfficeError("Max rework rounds reached.")
        task["rework_rounds"] = int(task.get("rework_rounds", 0)) + 1
    result = run_adapter("implement", args, paths)
    transition(paths, task, "IMPLEMENTED", result.detail)
    print("state=IMPLEMENTED")
    return 0


def cmd_redteam(args: argparse.Namespace) -> int:
    paths = task_paths(args.task_id)
    task = load_task(paths)
    require_state(task, {"IMPLEMENTED"})
    result = run_adapter("redteam", args, paths)
    transition(paths, task, "REVIEWED", result.detail)
    print("state=REVIEWED")
    return 0


def build_final_summary(paths: TaskPaths, task: dict[str, Any]) -> str:
    brief = read_if_exists(paths.brief, 800)
    gemini = read_if_exists(paths.gemini_context, 900)
    codex = read_if_exists(paths.codex_report, 900)
    review = read_if_exists(paths.grok_review, 900)
    patch_head = read_if_exists(paths.patch_diff, 800)
    summary = f"""# Final For Claude

Claude must read only this file for task `{task['task_id']}`.

## Current State

- State before Claude decision: {task['state']}
- Rework rounds used: {task.get('rework_rounds', 0)} / {task.get('max_rework_rounds', MAX_REWORK_ROUNDS)}
- Final summary limit: {task.get('final_for_claude_limit', FINAL_FOR_CLAUDE_LIMIT)} characters

## Task Brief Snapshot

{brief}

## Gemini Context Snapshot

{gemini}

## Codex Implementation Snapshot

{codex}

## Grok Build Review Snapshot

{review}

## Patch Preview Only

Claude receives only this preview, not the full repository or full logs.

```diff
{patch_head}
```

## Decision Options

- APPROVED
- REQUEST_CHANGES
- REJECTED
"""
    limit = int(task.get("final_for_claude_limit", FINAL_FOR_CLAUDE_LIMIT))
    if len(summary) > limit:
        suffix = "\n\n[TRUNCATED BY ORCHESTRATOR TO PROTECT CLAUDE TOKENS]\n"
        summary = summary[: max(0, limit - len(suffix))] + suffix
    return summary


def cmd_summarize(args: argparse.Namespace) -> int:
    require_mock_mode(args, "summarize")
    paths = task_paths(args.task_id)
    task = load_task(paths)
    require_state(task, {"REVIEWED"})
    write_file(paths.final_for_claude, build_final_summary(paths, task))
    transition(paths, task, "SUMMARIZED", "Orchestrator wrote Claude-only compressed summary.")
    print(f"state=SUMMARIZED final_chars={len(paths.final_for_claude.read_text(encoding='utf-8'))}")
    return 0


def cmd_final(args: argparse.Namespace) -> int:
    paths = task_paths(args.task_id)
    task = load_task(paths)
    require_state(task, {"SUMMARIZED"})
    result = run_adapter("final", args, paths)
    decision = result.decision
    if decision not in {"APPROVED", "REQUEST_CHANGES", "REJECTED"}:
        raise AgentOfficeError("Final adapter returned an invalid decision.")
    append_history(task, "SUMMARIZED->CLAUDE_DECIDED", "Claude final adapter read final-for-claude.md only.")
    transition(paths, task, decision, result.detail)
    print(f"state={decision}")
    return 0


def cmd_judge(args: argparse.Namespace) -> int:
    paths = task_paths(args.task_id)
    task = load_task(paths)
    require_state(task, {"REVIEWED", "SUMMARIZED"})
    if task["state"] == "REVIEWED":
        write_file(paths.final_for_claude, build_final_summary(paths, task))
        transition(paths, task, "SUMMARIZED", "Orchestrator wrote Claude-only compressed summary for judge.")
    return cmd_final(args)


def cmd_status(args: argparse.Namespace) -> int:
    paths = task_paths(args.task_id)
    task = load_task(paths)
    files = [
        paths.task_json,
        paths.brief,
        paths.gemini_context,
        paths.codex_report,
        paths.patch_diff,
        paths.grok_review,
        paths.final_for_claude,
        paths.claude_decision,
    ]
    print(json.dumps({
        "task_id": task["task_id"],
        "state": task["state"],
        "rework_rounds": task.get("rework_rounds", 0),
        "max_rework_rounds": task.get("max_rework_rounds", MAX_REWORK_ROUNDS),
        "files": {p.name: p.exists() for p in files},
    }, indent=2, ensure_ascii=False))
    return 0


def cmd_adapters(args: argparse.Namespace) -> int:
    print(format_adapters(PROJECT_ROOT))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    if bool(getattr(args, "profiles", False)):
        audit = collect_profile_plan_audit()
        if args.json:
            print(json.dumps(audit, indent=2, ensure_ascii=False))
        else:
            print(format_profile_plan_audit(audit))
        return 0

    report = collect_doctor(PROJECT_ROOT, adapter_filter=args.adapter)
    if args.adapters:
        if args.json:
            print(json.dumps(report["adapter_modes"]["rows"], indent=2, ensure_ascii=False))
        else:
            print(format_adapter_rows(report["adapter_modes"]["rows"]))
    elif args.json:
        print(doctor_json(report))
    else:
        print(format_doctor(report))
    return 0


def format_adapter_rows(rows: list[dict[str, object]]) -> str:
    lines = ["adapter | mode | dry_run | env_ok | fallback | status"]
    for row in rows:
        lines.append(
            " | ".join(
                [
                    str(row["adapter"]),
                    str(row["mode"]),
                    bool_text(bool(row["dry_run"])),
                    bool_text(bool(row["env_ok"])),
                    bool_text(bool(row["fallback"])),
                    str(row["status"]),
                ]
            )
        )
    return "\n".join(lines)


def profile_payload(name: str | None = None) -> dict[str, object]:
    profile_names = list_profiles()
    selected_names = (name,) if name else profile_names
    try:
        profiles = []
        for profile_name in selected_names:
            profile = get_profile(profile_name)
            profiles.append(
                {
                    "name": profile.name,
                    "roles": {role: profile.roles[role] for role in ALLOWED_ROLES},
                }
            )
    except ProfileError as exc:
        raise AgentOfficeError(str(exc)) from exc
    return {
        "default_profile": default_profile_name(),
        "available_profiles": list(profile_names),
        "profiles": profiles,
    }


def format_profiles(payload: dict[str, object]) -> str:
    lines = [
        "AgentOffice provider profiles",
        f"default: {payload['default_profile']}",
        f"available: {', '.join(str(name) for name in payload['available_profiles'])}",
    ]
    for profile in payload["profiles"]:
        if not isinstance(profile, dict):
            continue
        lines.append("")
        lines.append(str(profile["name"]))
        roles = profile["roles"]
        if not isinstance(roles, dict):
            continue
        for role in ALLOWED_ROLES:
            lines.append(f"  {role}: {roles[role]}")
    return "\n".join(lines)


def format_profile_plan(payload: dict[str, object]) -> str:
    lines = [
        "AgentOffice profile plan preview",
        f"selected_profile: {payload['selected_profile']}",
        f"default_profile: {payload['default_profile']}",
        f"is_default: {str(payload['is_default']).lower()}",
        f"execution_enabled: {str(payload['execution_enabled']).lower()}",
        f"provider_calls: {str(payload['provider_calls']).lower()}",
        f"artifact_writes: {str(payload['artifact_writes']).lower()}",
        "",
        "roles:",
    ]
    for role in payload["roles"]:
        if not isinstance(role, dict):
            continue
        lines.append(f"  {role['role']}: {role['provider']} ({role['execution_category']})")
    return "\n".join(lines)


def format_profile_plans(payload: dict[str, object]) -> str:
    lines = [
        "AgentOffice profile plan previews",
        f"default_profile: {payload['default_profile']}",
        f"available_profiles: {', '.join(str(name) for name in payload['available_profiles'])}",
        "",
    ]
    plans = payload["plans"]
    if not isinstance(plans, list):
        return "\n".join(lines).rstrip()
    for index, plan in enumerate(plans):
        if not isinstance(plan, dict):
            continue
        if index:
            lines.append("")
        lines.append(format_profile_plan(plan))
    return "\n".join(lines)


def format_profile_plan_contract_audit(payload: dict[str, object]) -> str:
    provider_calls = payload["provider_calls"]
    provider_calls_count = len(provider_calls) if isinstance(provider_calls, list) else int(bool(provider_calls))
    lines = [
        "Profile plan contract audit",
        f"selected_profile: {payload['selected_profile']}",
        f"default_profile: {payload['default_profile']}",
        f"is_default: {str(payload['is_default']).lower()}",
        f"execution_enabled: {str(payload['execution_enabled']).lower()}",
        f"provider_calls_count: {provider_calls_count}",
        f"contract_status: {payload['status']}",
        "checks:",
    ]
    checks = payload["checks"]
    if isinstance(checks, list):
        for check in checks:
            if isinstance(check, dict):
                lines.append(f"  {check['name']}: {check['status']}")
    lines.append("provider/runtime/adapter execution: not triggered")
    return "\n".join(lines)


def format_profile_plan_contract_audits(payload: dict[str, object]) -> str:
    lines = [
        "Profile plan contract audits",
        f"default_profile: {payload['default_profile']}",
        f"available_profiles: {', '.join(str(name) for name in payload['available_profiles'])}",
        f"contract_status: {payload['status']}",
        "",
    ]
    audits = payload["audits"]
    if isinstance(audits, list):
        for index, audit in enumerate(audits):
            if not isinstance(audit, dict):
                continue
            if index:
                lines.append("")
            lines.append(format_profile_plan_contract_audit(audit))
    return "\n".join(lines).rstr
```
### agent_office/v1_post_release_ops.py

truncated: false

```text
from __future__ import annotations

import hashlib
import json
import re
import tarfile
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
RELEASE_COMMIT = "91a8e38cd8d3db540e8c5655304f0f1e4d8f8213"
RELEASE_TAG = "v1.0.0"
RELEASE_TITLE = "AgentOffice v1.0.0"
MAINLINE_BRANCH = "phase6/mainline"
POST_V1_BRANCH = "phase50/post-v1-release-ops-foundation"
ARCHIVE_ROOT = "V1_0_0_FINAL_DELIVERY_ARCHIVE"
ARCHIVE_PACKET_TYPE = "agentoffice_v1_release_archive_verification"
READBACK_PACKET_TYPE = "agentoffice_v1_github_release_readback_verification"
ROADMAP_PACKET_TYPE = "agentoffice_post_v1_roadmap"
ARCHIVE_VERIFY_PASS_MARKER = "AGENTOFFICE_V1_RELEASE_ARCHIVE_VERIFY_PASS"
ARCHIVE_VERIFY_FAIL_MARKER = "AGENTOFFICE_V1_RELEASE_ARCHIVE_VERIFY_FAIL"
READBACK_VERIFY_PASS_MARKER = "AGENTOFFICE_V1_GITHUB_RELEASE_READBACK_VERIFY_PASS"
READBACK_VERIFY_FAIL_MARKER = "AGENTOFFICE_V1_GITHUB_RELEASE_READBACK_VERIFY_FAIL"
ROADMAP_MARKER = "AGENTOFFICE_POST_V1_ROADMAP"

REQUIRED_ARCHIVE_MEMBERS = (
    f"{ARCHIVE_ROOT}/README_FOR_RELEASE_ARCHIVE.md",
    f"{ARCHIVE_ROOT}/SHA256SUMS",
)

REQUIRED_RELEASE_ASSETS = (
    "V1_0_0_TAG_VERIFICATION_READBACK.md",
    "agentoffice-v1.0.0-final-delivery-archive.tar.gz",
    "agentoffice-v1.0.0-final-delivery-archive.tar.gz.sha256",
    "V1_0_0_RELEASE_ARCHIVE_REPORT.md",
)

READBACK_STATUS_TO_PUBLISH_STATE = {
    "published": "published",
    "verified_existing": "verified_existing",
    "skipped_no_token": "skipped",
    "skipped_api_error": "skipped",
    "partial_remote_state": "partial_remote_state",
}


def verify_release_archive_payload(archive: str, sha256: str) -> dict[str, Any]:
    errors: list[str] = []
    archive_path = _safe_file_path(archive, "release_archive", errors)
    sha_path = _safe_file_path(sha256, "release_archive_sha256", errors)
    payload: dict[str, Any] = {
        "ok": False,
        "packet_type": ARCHIVE_PACKET_TYPE,
        "schema_version": SCHEMA_VERSION,
        "archive": str(archive),
        "sha256": str(sha256),
        "external_sha256": None,
        "expected_external_sha256": None,
        "external_sha256_match": False,
        "required_members_present": False,
        "internal_sha256_ok": False,
        "checked_files": 0,
        "errors": errors,
    }
    if errors or archive_path is None or sha_path is None:
        return payload

    expected = _read_expected_sha256(sha_path, errors)
    actual = _file_sha256(archive_path, errors)
    payload["expected_external_sha256"] = expected
    payload["external_sha256"] = actual
    if expected and actual:
        payload["external_sha256_match"] = expected == actual
        if expected != actual:
            errors.append("release_archive_sha256_mismatch")

    archive_result = _verify_archive_members(archive_path, errors)
    payload["required_members_present"] = archive_result["required_members_present"]
    payload["internal_sha256_ok"] = archive_result["internal_sha256_ok"]
    payload["checked_files"] = archive_result["checked_files"]
    payload["ok"] = not errors
    return payload


def format_release_archive_verify(payload: dict[str, Any]) -> str:
    marker = ARCHIVE_VERIFY_PASS_MARKER if payload["ok"] else ARCHIVE_VERIFY_FAIL_MARKER
    lines = [
        marker,
        f"ok: {_bool_text(bool(payload['ok']))}",
        f"archive: {payload['archive']}",
        f"sha256: {payload['sha256']}",
        f"external_sha256_match: {_bool_text(bool(payload['external_sha256_match']))}",
        f"required_members_present: {_bool_text(bool(payload['required_members_present']))}",
        f"internal_sha256_ok: {_bool_text(bool(payload['internal_sha256_ok']))}",
        f"checked_files: {payload['checked_files']}",
        "errors:",
    ]
    errors = payload["errors"]
    if errors:
        lines.extend(f"  - {error}" for error in errors)
    else:
        lines.append("  - none")
    return "\n".join(lines)


def verify_github_release_readback_payload(directory: str) -> dict[str, Any]:
    errors: list[str] = []
    readback_dir = _safe_dir_path(directory, "github_release_readback", errors)
    payload: dict[str, Any] = {
        "ok": False,
        "packet_type": READBACK_PACKET_TYPE,
        "schema_version": SCHEMA_VERSION,
        "dir": str(directory),
        "status": "unknown",
        "publish_state": "unknown",
        "release_url": None,
        "assets": [],
        "errors": errors,
    }
    if errors or readback_dir is None:
        return payload

    state_path = readback_dir / "state.json"
    state = _read_json_object(state_path, "github_release_readback_state", errors)
    if state is None:
        return payload

    status = _string_value(state.get("status")) or "unknown"
    publish_state = _string_value(state.get("publish_state")) or "unknown"
    release_url = _string_value(state.get("release_url"))
    assets = _asset_names(state)

    release_json_path = readback_dir / "release.json"
    if release_json_path.exists():
        release = _read_json_object(release_json_path, "github_release_readback_release", errors)
        if release is not None:
            release_url = release_url or _string_value(release.get("html_url"))
            assets = assets or _asset_names(release)

    expected_publish_state = READBACK_STATUS_TO_PUBLISH_STATE.get(status)
    if expected_publish_state is None:
        errors.append(f"github_release_readback_unknown_status:{status}")
    elif publish_state != expected_publish_state:
        errors.append(f"github_release_readback_publish_state_mismatch:{publish_state}:{expected_publish_state}")

    if status in {"published", "verified_existing"}:
        if not release_url:
            errors.append("github_release_readback_missing_release_url")
        elif not _valid_release_url(release_url):
            errors.append("github_release_readback_invalid_release_url")
        missing_assets = [name for name in REQUIRED_RELEASE_ASSETS if name not in assets]
        if missing_assets:
            errors.append("github_release_readback_missing_assets:" + ",".join(missing_assets))
    elif status in {"skipped_no_token", "skipped_api_error"}:
        if publish_state != "skipped":
            errors.append("github_release_readback_skipped_state_not_skipped")
    elif status == "partial_remote_state":
        errors.append("github_release_readback_partial_remote_state")

    if release_url and not _valid_release_url(release_url):
        if "github_release_readback_invalid_release_url" not in errors:
            errors.append("github_release_readback_invalid_release_url")

    payload.update(
        {
            "status": status,
            "publish_state": publish_state,
            "release_url": release_url,
            "assets": assets,
            "ok": not errors,
        }
    )
    return payload


def format_github_release_readback_verify(payload: dict[str, Any]) -> str:
    marker = READBACK_VERIFY_PASS_MARKER if payload["ok"] else READBACK_VERIFY_FAIL_MARKER
    lines = [
        marker,
        f"ok: {_bool_text(bool(payload['ok']))}",
        f"status: {payload['status']}",
        f"publish_state={payload['publish_state']}",
        f"release_url: {payload['release_url'] or 'n/a'}",
        "assets:",
    ]
    assets = payload["assets"]
    if assets:
        lines.extend(f"  - {asset}" for asset in assets)
    else:
        lines.append("  - none")
    lines.append("errors:")
    errors = payload["errors"]
    if errors:
        lines.extend(f"  - {error}" for error in errors)
    else:
        lines.append("  - none")
    return "\n".join(lines)


def post_v1_roadmap_payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "packet_type": ROADMAP_PACKET_TYPE,
        "status": "ready_for_review",
        "baseline": {
            "tag": RELEASE_TAG,
            "release_title": RELEASE_TITLE,
            "release_commit": RELEASE_COMMIT,
            "mainline_branch": MAINLINE_BRANCH,
            "post_v1_branch": POST_V1_BRANCH,
        },
        "lanes": [
            {
                "id": "v1.0.1-hotfix",
                "label": "v1.0.1 hotfix lane",
                "focus": [
                    "small correctness fixes found by v1 release review",
                    "documentation clarifications with no runtime behavior change",
                    "targeted verifier fixes with regression tests",
                ],
            },
            {
                "id": "v1.1-release-ops",
                "label": "v1.1 release ops lane",
                "focus": [
                    "idempotent release readback and archive verification surfaces",
                    "review bundle lifecycle evidence",
                    "operator handoff packets before any remote release write",
                ],
            },
            {
                "id": "artifact-review-automation",
                "label": "artifact review automation lane",
                "focus": [
                    "single-file reviewer bundles with checksums",
                    "local self-checks for exported review artifacts",
                    "clear PASS marker import requirements",
                ],
            },
            {
                "id": "external-worker-adapter-hardening",
                "label": "external worker adapter hardening lane",
                "focus": [
                    "dry-run first worker handoffs",
                    "explicit boundaries for real provider calls",
                    "failure readbacks that avoid secrets and environment dumps",
                ],
            },
            {
                "id": "provider-runtime-safety",
                "label": "provider/runtime safety lane",
                "focus": [
                    "static doctor and profile checks before real execution",
                    "no .env reads in release verification surfaces",
                    "no provider, runtime, model, or adapter execution in roadmap commands",
                ],
            },
        ],
        "non_goals": [
            "automatic merge to phase6/mainline",
            "tag creation or mutation",
            "GitHub release deletion or asset overwrite",
            "real provider/model/runtime/adapter execution",
            "reading .env or printing environment variables",
        ],
        "validation_commands": [
            "python3 -m compileall agent_office tests",
            "python3 -m unittest discover -s tests -p 'test_*.py'",
            "python3 -m agent_office v1 verify-release-archive --archive /opt/agent-office/agentoffice-v1.0.0-final-delivery-archive.tar.gz --sha256 /opt/agent-office/agentoffice-v1.0.0-final-delivery-archive.tar.gz.sha256 --json",
            "python3 -m agent_office v1 verify-github-release-readback --dir /opt/agent-office/V1_0_0_GITHUB_RELEASE_API_LONGRUN_READBACK --json",
            "python3 -m agent_office v1 post-v1-roadmap --json",
            "git diff --check",
        ],
        "review_handoff_guidance": [
            "Attach POST_V1_LONGRUN_REVIEW_ARTIFACT_BUNDLE.md and its SHA256 sidecar.",
            "Ask Claude artifact review to inspect the full diff and validation outputs without executing commands.",
            "Require marker POST_V1_LONGRUN_ARTIFACT_REVIEW_COMPLETE before any merge discussion.",
        ],
        "safety": {
            "dotenv_read": False,
            "env_vars_printed": False,
            "provider_runtime_adapter_external_behavior": False,
            "real_model_provider_connection": False,
            "merge_performed": False,
            "tag_created": False,
            "force_push": False,
            "default_branch_mutation": False,
        },
    }


def format_post_v1_roadmap(payload: dict[str, Any]) -> str:
    baseline = payload["baseline"]
    lines = [
        ROADMAP_MARKER,
        f"status: {payload['status']}",
        f"release_tag: {baseline['tag']}",
        f"release_commit: {baseline['release_commit']}",
        f"post_v1_branch: {baseline['post_v1_branch']}",
        "lanes:",
    ]
    for lane in payload["lanes"]:
        lines.append(f"  - {lane['label']} ({lane['id']})")
        for item in lane["focus"]:
            lines.append(f"    * {item}")
    lines.append("non_goals:")
    for item in payload["non_goals"]:
        lines.append(f"  - {item}")
    lines.append("validation_commands:")
    for command in payload["validation_commands"]:
        lines.append(f"  - {command}")
    lines.append("review_handoff_guidance:")
    for item in payload["review_handoff_guidance"]:
        lines.append(f"  - {item}")
    return "\n".join(lines)



def release_state_payload() -> dict[str, Any]:
    archive = Path("/opt/agent-office/agentoffice-v1.0.0-final-delivery-archive.tar.gz")
    sha256 = Path("/opt/agent-office/agentoffice-v1.0.0-final-delivery-archive.tar.gz.sha256")
    readback = Path("/opt/agent-office/V1_0_0_GITHUB_RELEASE_API_LONGRUN_READBACK")
    return {
        "schema_version": SCHEMA_VERSION,
        "packet_type": "agentoffice_v1_release_state",
        "release_tag": RELEASE_TAG,
        "release_commit": RELEASE_COMMIT,
        "mainline_branch": MAINLINE_BRANCH,
        "archive_present": archive.exists() and archive.is_file() and not archive.is_symlink(),
        "sha256_present": sha256.exists() and sha256.is_file() and not sha256.is_symlink(),
        "github_release_status": "skipped_no_token",
        "publish_state": "skipped",
        "release_url": None,
        "readback_dir_present": readback.exists() and readback.is_dir() and not readback.is_symlink(),
        "github_write_performed": False,
        "network_required": False,
        "token_required_for_publish": True,
        "safety": _release_ops_safety(),
    }


def github_release_handoff_payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "packet_type": "agentoffice_v1_github_release_handoff",
        "release_tag": RELEASE_TAG,
        "release_title": RELEASE_TITLE,
        "status": "tokenless_handoff_ready",
        "github_write_performed": False,
        "network_required": False,
        "operator_steps": [
            "Confirm v1.0.0 tag points at the recorded release commit.",
            "Verify release archive and SHA256 sidecar locally.",
            "Create or verify the GitHub Release only from an authenticated operator session.",
            "Upload required assets without deleting or overwriting existing release assets unless explicitly approved.",
            "Save readback evidence and run verify-github-release-readback.",
        ],
        "required_assets": list(REQUIRED_RELEASE_ASSETS),
        "safety": _release_ops_safety(),
    }


def github_release_plan_payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "packet_type": "agentoffice_v1_github_release_plan",
        "release_tag": RELEASE_TAG,
        "release_title": RELEASE_TITLE,
        "plan_type": "dry_run_only",
        "github_write_performed": False,
        "network_required": False,
        "preflight": [
            "verify tag commit matches release commit",
            "verify archive checksum and internal SHA256SUMS",
            "verify required release notes and reports are present",
            "confirm token scope and operator approval before any remote write",
        ],
        "write_steps_when_authorized": [
            "create draft release if it does not exist",
            "upload required assets exactly once",
            "read back release JSON and asset list",
            "run local readback verifier",
        ],
        "stop_conditions": [
            "missing token or explicit operator approval",
            "existing release has conflicting assets",
            "tag commit mismatch",
            "partial remote state",
        ],
        "safety": _release_ops_safety(),
    }


def release_candidate_payload(version: str) -> dict[str, Any]:
    if not re.fullmatch(r"v\d+\.\d+\.\d+", version):
        return {
            "ok": False,
            "schema_version": SCHEMA_VERSION,
            "packet_type": "agentoffice_v1_release_candidate",
            "version": version,
            "errors": ["release_candidate_invalid_version"],
        }
    return {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "packet_type": "agentoffice_v1_release_candidate",
        "version": version,
        "base_release": RELEASE_TAG,
        "base_commit": RELEASE_COMMIT,
        "status": "candidate_plan_ready",
        "github_write_performed": False,
        "tag_created": False,
        "network_required": False,
        "required_validations": [
            "python3 -m compileall agent_office tests",
            "python3 -m unittest",
            "python3 -m unittest discover -s tests -p 'test_*.py'",
            "python3 -m agent_office doctor --adapters",
            "./scripts/verify.sh",
            "git diff --check",
        ],
        "required_packets": [
            "release-state",
            "github-release-handoff",
            "github-release-plan",
            "merge gate packet",
            "review bundle",
        ],
        "safety": _release_ops_safety(),
        "errors": [],
    }


def format_release_state(payload: dict[str, Any]) -> str:
    return "\n".join([
        "AGENTOFFICE_V1_RELEASE_STATE",
        f"release_tag: {payload['release_tag']}",
        f"release_commit: {payload['release_commit']}",
        f"archive_present: {_bool_text(bool(payload['archive_present']))}",
        f"sha256_present: {_bool_text(bool(payload['sha256_present']))}",
        f"github_release_status: {payload['github_release_status']}",
        f"publish_state: {payload['publish_state']}",
        "github_write_performed: false",
        "network_required: false",
    ])


def format_github_release_handoff(payload: dict[str, Any]) -> str:
    lines = ["AGENTOFFICE_V1_GITHUB_RELEASE_HANDOFF", f"status: {payload['status']}", "github_write_performed: false", "operator_steps:"]
    lines.extend(f"  - {step}" for step in payload["operator_steps"])
    lines.append("required_assets:")
    lines.extend(f"  - {asset}" for asset in payload["required_assets"])
    return "\n".join(lines)


def format_github_release_plan(payload: dict[str, Any]) -> str:
    lines = ["AGENTOFFICE_V1_GITHUB_RELEASE_PLAN", f"plan_type: {payload['plan_type']}", "github_write_performed: false", "preflight:"]
    lines.extend(f"  - {step}" for step in payload["preflight"])
    lines.append("stop_conditions:")
    lines.extend(f"  - {condition}" for condition in payload["stop_conditions"])
    return "\n".join(lines)


def format_release_candidate(payload: dict[str, Any]) -> str:
    marker = "AGENTOFFICE_V1_RELEASE_CANDIDATE" if payload["ok"] else "AGENTOFFICE_V1_RELEASE_CANDIDATE_FAIL"
    lines = [marker, f"ok: {_bool_text(bool(payload['ok']))}", f"version: {payload['version']}"]
    if payload["ok"]:
        lines.extend([f"base_release: {payload['base_release']}", "github_write_performed: false", "tag_created: false", "required_validations:"])
        lines.extend(f"  - {command}" for command in payload["required_validations"])
    else:
        lines.append("errors:")
        lines.extend(f"  - {error}" for error in payload["errors"])
    return "\n".join(lines)


def _release_ops_safety() -> dict[str, bool]:
    return {
        "dotenv_read": False,
        "env_vars_printed": False,
        "token_printed": False,
        "github_write_performed": False,
        "tag_created": False,
        "tag_deleted": False,
        "release_deleted": False,
        "release_asset_deleted": False,
        "network_required": False,
        "provider_runtime_adapter_external_behavior": False,
    }

def _safe_file_path(path: str, code_prefix: str, errors: list[str]) -> Path | None:
    if not str(path).strip():
        errors.append(f"{code_prefix}_missing_path")
        return None
    candidate = Path(path)
    if _has_dotenv_component(candidate):
        errors.append(f"{code_prefix}_dotenv_refused")
        return None
    if not candidate.exists():
        errors.append(f"{code_prefix}_missing")
        return None
    if candidate.is_symlink():
        errors.append(f"{code_prefix}_symlink")
        return None
    if candidate.is_dir():
        errors.append(f"{code_prefix}_directory")
        return None
    if not candidate.is_file():
        errors.append(f"{code_prefix}_not_file")
        return None
    return candidate.resolve()


def _safe_dir_path(path: str, code_prefix: str, errors: list[str]) -> Path | None:
    if not str(path).strip():
        errors.append(f"{code_prefix}_missing_path")
        return None
    candidate = Path(path)
    if _has_dotenv_component(candidate):
        errors.append(f"{code_prefix}_dotenv_refused")
        return None
    if not candidate.exists():
        errors.append(f"{code_prefix}_missing")
        return None
    if candidate.is_symlink():
        errors.append(f"{code_prefix}_symlink")
        return None
    if not candidate.is_dir():
        errors.append(f"{code_prefix}_not_directory")
        return None
    return candidate.resolve()


def _read_expected_sha256(path: Path, errors: list[str]) -> str | None:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        errors.append("release_archive_sha256_non_utf8")
        return None
    except OSError:
        errors.append("release_archive_sha256_unreadable")
        return None
    for token in text.replace("\n", " ").split():
        if re.fullmatch(r"[0-9a-fA-F]{64}", token):
            return token.lower()
    errors.append("release_archive_sha256_missing_digest")
    return None


def _file_sha256(path: Path, errors: list[str]) -> str | None:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        errors.append("release_archive_unreadable")
        return None
    return digest.hexdigest()


def _verify_archive_members(path: Path, errors: list[str]) -> dict[str, Any]:
    result = {"required_members_present": False, "internal_sha256_ok": False, "checked_files": 0}
    try:
        with tarfile.open(path, "r:gz") as tar:
            members = tar.getmembers()
            member_by_name = {member.name: member for member in members}
            for member in members:
                if _unsafe_archive_name(member.name):
                    errors.append(f"release_archive_unsafe_member:{member.name}")
            missing_required = [name for name in REQUIRED_ARCHIVE_MEMBERS if name not in member_by_name]
            if missing_required:
                for name in missing_required:
                    if name.endswith("README_FOR_RELEASE_ARCHIVE.md"):
                        errors.append("release_archive_missing_internal_manifest")
                    elif name.endswith("SHA256SUMS"):
                        errors.append("release_archive_missing_internal_sha256sums")
                    else:
                        errors.append(f"release_archive_missing_required_member:{name}")
                return result
            result["required_members_present"] = True
            sums_member = member_by_name[f"{ARCHIVE_ROOT}/SHA256SUMS"]
            sums_file = tar.extractfile(sums_member)
            if sums_file is None:
                errors.append("release_archive_internal_sha256sums_unreadable")
                return result
            try:
                sums_text = sums_file.read().decode("utf-8")
            except UnicodeDecodeError:
                errors.append("release_archive_internal_sha256sums_non_utf8")
                return result
            entries = _parse_internal_sha256sums(sums_text, errors)
            for member in members:
                if member.isfile() and member.name != f"{ARCHIVE_ROOT}/SHA256SUMS" and member.name not in entries:
                    errors.append(f"release_archive_internal_sha256_missing_entry:{member.name}")
            for member_name, expected in entries.items():
                member = member_by_name.get(member_name)
                if member is None:
                    errors.append(f"release_archive_internal_sha256_missing_member:{member_name}")
                    continue
                if not member.isfile():
                    errors.append(f"release_archive_internal_sha256_not_regular_file:{member_name}")
                    continue
                extracted = tar.extractfile(member)
                if extracted is None:
                    errors.append(f"release_archive_internal_sha256_unreadable:{member_name}")
                    continue
                actual = hashlib.sha256(extracted.read()).hexdigest()
                result["checked_files"] += 1
                if actual != expected:
                    errors.append(f"release_archive_bad_internal_checksum:{member_name}")
            result["internal_sha256_ok"] = not any(
                error.startswith("release_archive_internal_sha256") or error.startswith("release_archive_bad_internal_checksum")
                for error in errors
            )
            return result
    except (tarfile.TarError, OSError, EOFError):
        errors.append("release_archive_corrupt_tar")
        return result


def _parse_internal_sha256sums(text: str, errors: list[str]) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
            errors.append(f"release_archive_internal_sha256sums_malformed:{line_number}")
            continue
        rel_path = parts[1].strip()
        if rel_path.startswith("*"):
            rel_path = rel_path[1:].strip()
        while rel_path.startswith("./"):
            rel_path = rel_path[2:]
        if not rel_path or _unsafe_archive_name(rel_path):
            errors.append(f"release_archive_internal_sha256sums_unsafe_path:{line_number}")
            continue
        member_name = rel_path if rel_path.startswith(f"{ARCHIVE_ROOT}/") else f"{ARCHIVE_ROOT}/{rel_path}"
        entries[member_name] = parts[0].lower()
    if not entries:
        errors.append("release_archive_internal_sha256sums_empty")
    return entries


def _read_json_object(path: Path, code_prefix: str, errors: list[str]) -> dict[str, Any] | None:
    if _has_dotenv_component(path):
        errors.append(f"{code_prefix}_dotenv_refused")
        return None
    if not path.exists():
        errors.append(f"{code_prefix}_missing")
        return None
    if path.is_symlink():
        errors.append(f"{code_prefix}_symlink")
        return None
    if path.is_dir():
        errors.append(f"{code_prefix}_directory")
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        errors.append(f"{code_prefix}_non_utf8")
        return None
    except OSError:
        errors.append(f"{code_prefix}_unreadable")
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        errors.append(f"{code_prefix}_malformed_json")
        return None
    if not isinstance(data, dict):
        errors.append(f"{code_prefix}_not_object")
        return None
    return data


def _asset_names(data: dict[str, Any]) -> list[str]:
    raw_assets = data.get("assets_uploaded")
    if raw_assets is None:
        raw_assets = data.get("assets")
    if not isinstance(raw_assets, list):
        return []
    names: list[str] = []
    for asset in raw_assets:
        if isinstance(asset, str):
            names.append(asset)
        elif isinstance(asset, dict) and isinstance(asset.get("name"), str):
            names.append(asset["name"])
    return names


def _string_value(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _valid_release_url(url: str) -> bool:
    return url.startswith("https://github.com/mqpmqp/agent-office/releases")


def _has_dotenv_component(path: Path) -> bool:
    return any(part == ".env" for part in path.parts)


def _unsafe_archive_name(name: str) -> bool:
    normalized = name.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part and part != "."]
    return normalized.startswith("/") or any(part == ".." for part in parts)


def _bool_text(value: bool) -> str:
    return "true" if value else "false"
```
### tests/test_autonomy_plan_cli.py

truncated: false

```text
from __future__ import annotations

import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from agent_office import cli


def run_cli(argv: list[str], project_root: Path) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with patch.object(cli, "PROJECT_ROOT", project_root), redirect_stdout(stdout), redirect_stderr(stderr):
        code = cli.main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


def make_git_repo(root: Path) -> tuple[str, str]:
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=root, check=True, capture_output=True, text=True)
    (root / "sample.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "add", "sample.txt"], cwd=root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=root, check=True, capture_output=True, text=True)
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True).stdout.strip()
    (root / "sample.txt").write_text("one\ntwo\n", encoding="utf-8")
    (root / "extra.txt").write_text("extra\n", encoding="utf-8")
    subprocess.run(["git", "add", "sample.txt", "extra.txt"], cwd=root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "head"], cwd=root, check=True, capture_output=True, text=True)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True).stdout.strip()
    return base, head


class AutonomyPlanCliTests(unittest.TestCase):
    maxDiff = None

    def test_autonomy_plan_positive_json_for_all_goals(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            results = {
                goal: run_cli(["autonomy", "plan", "--goal", goal, "--json"], root)
                for goal in ["release-ops", "post-v1", "autonomous-delivery"]
            }

        for goal, result in results.items():
            with self.subTest(goal=goal):
                self.assertEqual(result[0], 0, result[1] + result[2])
                payload = json.loads(result[1])
                self.assertEqual(payload["schema_version"], 1)
                self.assertEqual(payload["packet_type"], "agentoffice_autonomy_mission_plan")
                self.assertEqual(payload["goal"], goal)
                self.assertEqual(payload["status"], "ready")
                self.assertTrue(payload["local_only"])
                self.assertFalse(payload["network_required"])
                self.assertFalse(payload["provider_runtime_adapter_external_behavior"])
                self.assertGreaterEqual(len(payload["phases"]), 1)
                self.assertGreaterEqual(len(payload["validation_commands"]), 3)
                self.assertIn(".env is never read", payload["safety_boundaries"])
                self.assertIn("phase6/mainline is not merged or mutated by autonomy commands", payload["safety_boundaries"])
                self.assertGreaterEqual(len(payload["expected_artifacts"]), 1)
                self.assertGreaterEqual(len(payload["review_handoff"]), 1)
                self.assertGreaterEqual(len(payload["merge_gate_handoff"]), 1)
                self.assertNotIn("Traceback", result[1] + result[2])

    def test_autonomy_plan_positive_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_cli(["autonomy", "plan", "--goal", "autonomous-delivery"], Path(tmpdir))

        self.assertEqual(result[0], 0, result[1] + result[2])
        self.assertIn("AGENTOFFICE_AUTONOMY_MISSION_PLAN", result[1])
        self.assertIn("goal: autonomous-delivery", result[1])
        self.assertIn("phases:", result[1])
        self.assertIn("validation_commands:", result[1])
        self.assertIn("review_handoff:", result[1])
        self.assertIn("merge_gate_handoff:", result[1])
        self.assertNotIn("Traceback", result[1] + result[2])

    def test_autonomy_plan_unknown_goal_is_clean_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_cli(["autonomy", "plan", "--goal", "unknown"], Path(tmpdir))

        self.assertEqual(result[0], 2)
        self.assertIn("unknown autonomy goal", result[2])
        self.assertNotIn("Traceback", result[1] + result[2])

    def test_autonomy_plan_json_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            first = run_cli(["autonomy", "plan", "--goal", "post-v1", "--json"], root)
            second = run_cli(["autonomy", "plan", "--goal", "post-v1", "--json"], root)

        self.assertEqual(first[0], 0, first[1] + first[2])
        self.assertEqual(second[0], 0, second[1] + second[2])
        self.assertEqual(first[1], second[1])
        self.assertNotIn("Traceback", first[1] + first[2] + second[1] + second[2])


class AutonomyLedgerCliTests(unittest.TestCase):
    maxDiff = None

    def test_autonomy_ledger_init_status_checkpoint_report_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            run_path = root / ".ai" / "autonomy" / "runs" / "demo"
            init = run_cli(["autonomy", "init", "--goal", "autonomous-delivery", "--path", str(run_path), "--json"], root)
            status = run_cli(["autonomy", "status", "--path", str(run_path), "--json"], root)
            checkpoint = run_cli(["autonomy", "checkpoint", "--path", str(run_path), "--name", "preflight", "--status", "passed", "--json"], root)
            report = run_cli(["autonomy", "report", "--path", str(run_path), "--json"], root)

        for result in [init, status, checkpoint, report]:
            self.assertEqual(result[0], 0, result[1] + result[2])
            self.assertNotIn("Traceback", result[1] + result[2])
        init_payload = json.loads(init[1])
        self.assertTrue(init_payload["ok"])
        self.assertEqual(init_payload["action"], "init")
        self.assertEqual(init_payload["ledger"]["goal"], "autonomous-delivery")
        self.assertEqual(init_payload["ledger"]["status"], "running")
        checkpoint_payload = json.loads(checkpoint[1])
        self.assertEqual(checkpoint_payload["ledger"]["status"], "passed")
        self.assertEqual(checkpoint_payload["checkpoint"]["name"], "preflight")
        report_payload = json.loads(report[1])
        self.assertEqual(report_payload["summary"]["checkpoint_count"], 1)
        self.assertEqual(report_payload["summary"]["latest_checkpoint"]["status"], "passed")

    def test_autonomy_ledger_text_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            run_path = root / ".ai" / "autonomy" / "runs" / "demo"
            init = run_cli(["autonomy", "init", "--goal", "post-v1", "--path", str(run_path)], root)

        self.assertEqual(init[0], 0, init[1] + init[2])
        self.assertIn("AGENTOFFICE_AUTONOMY_RUN_LEDGER", init[1])
        self.assertIn("action: init", init[1])
        self.assertIn("goal: post-v1", init[1])
        self.assertNotIn("Traceback", init[1] + init[2])

    def test_autonomy_ledger_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_cli(["autonomy", "init", "--goal", "post-v1", "--path", "../outside", "--json"], Path(tmpdir))

        self.assertEqual(result[0], 2)
        self.assertIn("refused traversal", result[2])
        self.assertNotIn("Traceback", result[1] + result[2])

    def test_autonomy_ledger_rejects_symlink_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target = root / "target"
            target.mkdir()
            link = root / "link"
            link.symlink_to(target, target_is_directory=True)
            result = run_cli(["autonomy", "init", "--goal", "post-v1", "--path", str(link), "--json"], root)

        self.assertEqual(result[0], 2)
        self.assertIn("symlink refused", result[2])
        self.assertNotIn("Traceback", result[1] + result[2])

    def test_autonomy_ledger_malformed_ledger_is_clean_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            run_path = root / ".ai" / "autonomy" / "runs" / "demo"
            run_path.mkdir(parents=True)
            (run_path / "ledger.json").write_text("{bad json", encoding="utf-8")
            result = run_cli(["autonomy", "status", "--path", str(run_path), "--json"], root)

        self.assertEqual(result[0], 2)
        self.assertIn("malformed JSON", result[2])
        self.assertNotIn("Traceback", result[1] + result[2])


class AutonomyValidationCliTests(unittest.TestCase):
    maxDiff = None

    def test_autonomy_validate_minimal_records_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            run_path = root / ".ai" / "autonomy" / "runs" / "demo"
            init = run_cli(["autonomy", "init", "--goal", "autonomous-delivery", "--path", str(run_path), "--json"], root)
            completed = subprocess.CompletedProcess(args=["fake"], returncode=0, stdout="ok out", stderr="")
            with patch("agent_office.autonomy.subprocess.run", return_value=completed) as run_mock:
                result = run_cli(["autonomy", "validate", "--path", str(run_path), "--suite", "minimal", "--json"], root)
            self.assertEqual(init[0], 0, init[1] + init[2])
            self.assertEqual(result[0], 0, result[1] + result[2])
            self.assertEqual(run_mock.call_count, 3)
            payload = json.loads(result[1])
            first = payload["validation"]["commands"][0]
            self.assertTrue(Path(first["stdout_path"]).exists())
            self.assertTrue(Path(first["stderr_path"]).exists())
            self.assertEqual(Path(first["stdout_path"]).read_text(encoding="utf-8"), "ok out")

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["validation"]["suite"], "minimal")
        self.assertEqual(payload["validation"]["status"], "passed")
        self.assertEqual(len(payload["validation"]["commands"]), 3)
        self.assertEqual(first["exit_code"], 0)
        self.assertEqual(payload["ledger"]["validation_records"][0]["status"], "passed")
        self.assertNotIn("Traceback", result[1] + result[2])

    def test_autonomy_validate_records_failed_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            run_path = root / ".ai" / "autonomy" / "runs" / "demo"
            init = run_cli(["autonomy", "init", "--goal", "autonomous-delivery", "--path", str(run_path), "--json"], root)
            results = [
                subprocess.CompletedProcess(args=["fake1"], returncode=0, stdout="ok", stderr=""),
                subprocess.CompletedProcess(args=["fake2"], returncode=7, stdout="", stderr="bad"),
                subprocess.CompletedProcess(args=["fake3"], returncode=0, stdout="ok", stderr=""),
            ]
            with patch("agent_office.autonomy.subprocess.run", side_effect=results):
                result = run_cli(["autonomy", "validate", "--path", str(run_path), "--suite", "minimal", "--json"], root)
            payload = json.loads(result[1])
            failed_stderr = Path(payload["validation"]["commands"][1]["stderr_path"]).read_text(encoding="utf-8")

        self.assertEqual(init[0], 0, init[1] + init[2])
        self.assertEqual(result[0], 2)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["validation"]["status"], "failed")
        self.assertEqual(payload["validation"]["commands"][1]["exit_code"], 7)
        self.assertEqual(failed_stderr, "bad")
        self.assertEqual(payload["ledger"]["status"], "failed")
        self.assertNotIn("Traceback", result[1] + result[2])

    def test_autonomy_validate_unknown_suite_is_clean_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            run_path = root / ".ai" / "autonomy" / "runs" / "demo"
            init = run_cli(["autonomy", "init", "--goal", "autonomous-delivery", "--path", str(run_path), "--json"], root)
            result = run_cli(["autonomy", "validate", "--path", str(run_path), "--suite", "unknown", "--json"], root)

        self.assertEqual(init[0], 0, init[1] + init[2])
        self.assertEqual(result[0], 2)
        self.assertIn("unknown validation suite", result[2])
        self.assertNotIn("Traceback", result[1] + result[2])


class AutonomyReviewPacketCliTests(unittest.TestCase):
    maxDiff = None

    def test_autonomy_review_packet_positive_json_and_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            base, head = make_git_repo(root)
            out = root / "review-packet.md"
            result = run_cli(["autonomy", "review-packet", "--base", base, "--head", head, "--out", str(out), "--json"], root)
            bundle = out.read_text(encoding="utf-8")

        self.assertEqual(result[0], 0, result[1] + result[2])
        payload = json.loads(result[1])
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["base"], base)
        self.assertEqual(payload["head"], head)
        self.assertEqual(payload["commit_count"], 1)
        self.assertGreaterEqual(payload["snapshot_count"], 2)
        self.assertIn("# AgentOffice Autonomy Review Packet", bundle)
        self.assertIn("## Full Diff", bundle)
        self.assertIn("sample.txt", bundle)
        self.assertIn("extra.txt", bundle)
        self.assertIn(".env is never read", bundle)
        self.assertNotIn("Traceback", result[1] + result[2])

    def test_autonomy_review_packet_text_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            base, head = make_git_repo(root)
            out = root / "review-packet.md"
            result = run_cli(["autonomy", "review-packet", "--base", base, "--head", head, "--out", str(out)], root)

        self.assertEqual(result[0], 0, result[1] + result[2])
        self.assertIn("AGENTOFFICE_AUTONOMY_REVIEW_PACKET", result[1])
        self.assertIn(f"base: {base}", result[1])
        self.assertNotIn("Traceback", result[1] + result[2])

    def test_autonomy_review_packet_rejects_unsafe_out(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            base, head = make_git_repo(root)
            traversal = run_cli(["autonomy", "review-packet", "--base", base, "--head", head, "--out", "../packet.md", "--json"], root)
            target = root / "target.md"
            target.write_text("target", encoding="utf-8")
            link = root / "link.md"
            link.symlink_to(target)
            symlink = run_cli(["autonomy", "review-packet", "--base", base, "--head", head, "--out", str(link), "--json"], root)

        self.assertEqual(traversal[0], 2)
        self.assertIn("refused traversal", traversal[2])
        self.assertEqual(symlink[0], 2)
        self.assertIn("symlink refused", symlink[2])
        self.assertNotIn("Traceback", traversal[1] + traversal[2] + symlink[1] + symlink[2])

    def test_autonomy_review_packet_missing_ref_is_clean_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _base, head = make_git_repo(root)
            result = run_cli(["autonomy", "review-packet", "--base", "missing-ref", "--head", head, "--out", str(root / "packet.md"), "--json"], root)

        self.assertEqual(result[0], 2)
        self.assertIn("review_packet_base failed", result[2])
        self.assertNotIn("Traceback", result[1] + result[2])


class AutonomyMergePacketCliTests(unittest.TestCase):
    maxDiff = None

    def test_autonomy_merge_packet_positive_json_and_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            base, head = make_git_repo(root)
            subprocess.run(["git", "branch", "target", base], cwd=root, check=True, capture_output=True, text=True)
            subprocess.run(["git", "branch", "source", head], cwd=root, check=True, capture_output=True, text=True)
            json_result = run_cli(["autonomy", "merge-packet", "--source", "source", "--target", "target", "--json"], root)
            text_result = run_cli(["autonomy", "merge-packet", "--source", "source", "--target", "target"], root)

        self.assertEqual(json_result[0], 0, json_result[1] + json_result[2])
        payload = json.loads(json_result[1])
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["source_branch"], "source")
        self.assertEqual(payload["target_branch"], "target")
        self.assertEqual(payload["source_head"], head)
        self.assertEqual(payload["target_head"], base)
        self.assertFalse(payload["merge_performed"])
        self.assertTrue(any("sample.txt" in item for item in payload["changed_files"]))
        self.assertIn("git merge --no-ff --no-commit source", payload["merge_commands"])
        self.assertEqual(text_result[0], 0, text_result[1] + text_result[2])
        self.assertIn("AGENTOFFICE_AUTONOMY_MERGE_PACKET", text_result[1])
        self.assertIn("merge_performed: false", text_result[1])
        self.assertNotIn("Traceback", json_result[1] + json_result[2] + text_result[1] + text_result[2])

    def test_autonomy_merge_packet_missing_source_is_clean_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            base, _head = make_git_repo(root)
            subprocess.run(["git", "branch", "target", base], cwd=root, check=True, capture_output=True, text=True)
            result = run_cli(["autonomy", "merge-packet", "--source", "missing", "--target", "target", "--json"], root)

        self.assertEqual(result[0], 2)
        self.assertIn("merge_packet_source failed", result[2])
        self.assertNotIn("Traceback", result[1] + result[2])

    def test_autonomy_merge_packet_missing_target_is_clean_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _base, head = make_git_repo(root)
            subprocess.run(["git", "branch", "source", head], cwd=root, check=True, capture_output=True, text=True)
            result = run_cli(["autonomy", "merge-packet", "--source", "source", "--target", "missing", "--json"], root)

        self.assertEqual(result[0], 2)
        self.assertIn("merge_packet_target failed", result[2])
        self.assertNotIn("Traceback", result[1] + result[2])


if __name__ == "__main__":
    unittest.main()
```
### tests/test_v1_post_release_ops_cli.py

truncated: false

```text
from __future__ import annotations

import hashlib
import io
import json
import tarfile
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from agent_office import cli


REQUIRED_ASSETS = [
    "V1_0_0_TAG_VERIFICATION_READBACK.md",
    "agentoffice-v1.0.0-final-delivery-archive.tar.gz",
    "agentoffice-v1.0.0-final-delivery-archive.tar.gz.sha256",
    "V1_0_0_RELEASE_ARCHIVE_REPORT.md",
]


def run_cli(argv: list[str], project_root: Path) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with patch.object(cli, "PROJECT_ROOT", project_root), redirect_stdout(stdout), redirect_stderr(stderr):
        code = cli.main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


def write_archive(root: Path, *, missing_manifest: bool = False, bad_checksum: bool = False) -> tuple[Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    archive = root / "release.tar.gz"
    sha = root / "release.tar.gz.sha256"
    files = {
        "README_FOR_RELEASE_ARCHIVE.md": b"release archive\n",
        "reports/report.md": b"report\n",
    }
    if missing_manifest:
        files.pop("README_FOR_RELEASE_ARCHIVE.md")
    sums = []
    for rel_path, content in sorted(files.items()):
        digest = hashlib.sha256(content).hexdigest()
        if bad_checksum and rel_path == "reports/report.md":
            digest = "0" * 64
        sums.append(f"{digest}  ./{rel_path}\n".encode("utf-8"))
    with tarfile.open(archive, "w:gz") as tar:
        for rel_path, content in sorted(files.items()):
            info = tarfile.TarInfo(f"V1_0_0_FINAL_DELIVERY_ARCHIVE/{rel_path}")
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
        sums_content = b"".join(sums)
        sums_info = tarfile.TarInfo("V1_0_0_FINAL_DELIVERY_ARCHIVE/SHA256SUMS")
        sums_info.size = len(sums_content)
        tar.addfile(sums_info, io.BytesIO(sums_content))
    sha.write_text(f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive}\n", encoding="utf-8")
    return archive, sha


class V1PostReleaseOpsCliTests(unittest.TestCase):
    maxDiff = None

    def test_release_archive_verify_positive_json_and_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            archive, sha = write_archive(root)
            json_result = run_cli(["v1", "verify-release-archive", "--archive", str(archive), "--sha256", str(sha), "--json"], root)
            text_result = run_cli(["v1", "verify-release-archive", "--archive", str(archive), "--sha256", str(sha)], root)

        self.assertEqual(json_result[0], 0, json_result[1] + json_result[2])
        payload = json.loads(json_result[1])
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["packet_type"], "agentoffice_v1_release_archive_verification")
        self.assertTrue(payload["external_sha256_match"])
        self.assertTrue(payload["required_members_present"])
        self.assertTrue(payload["internal_sha256_ok"])
        self.assertEqual(payload["checked_files"], 2)
        self.assertEqual(payload["errors"], [])
        self.assertEqual(text_result[0], 0, text_result[2])
        self.assertIn("AGENTOFFICE_V1_RELEASE_ARCHIVE_VERIFY_PASS", text_result[1])
        self.assertNotIn("Traceback", json_result[1] + json_result[2] + text_result[1] + text_result[2])

    def test_release_archive_negative_inputs_are_clean_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            archive, sha = write_archive(root)
            missing_sha = root / "missing.sha256"
            mismatch_sha = root / "mismatch.sha256"
            mismatch_sha.write_text(f"{'1' * 64}  {archive}\n", encoding="utf-8")
            corrupt_tar = root / "corrupt.tar.gz"
            corrupt_tar.write_bytes(b"not a tar")
            corrupt_sha = root / "corrupt.tar.gz.sha256"
            corrupt_sha.write_text(f"{hashlib.sha256(corrupt_tar.read_bytes()).hexdigest()}  {corrupt_tar}\n", encoding="utf-8")
            missing_manifest, missing_manifest_sha = write_archive(root / "missing", missing_manifest=True)
            bad_internal, bad_internal_sha = write_archive(root / "bad", bad_checksum=True)
            cases = [
                (["--archive", str(root / "missing.tar.gz"), "--sha256", str(sha), "--json"], "release_archive_missing"),
                (["--archive", str(archive), "--sha256", str(missing_sha), "--json"], "release_archive_sha256_missing"),
                (["--archive", str(archive), "--sha256", str(mismatch_sha), "--json"], "release_archive_sha256_mismatch"),
                (["--archive", str(corrupt_tar), "--sha256", str(corrupt_sha), "--json"], "release_archive_corrupt_tar"),
                (["--archive", str(missing_manifest), "--sha256", str(missing_manifest_sha), "--json"], "release_archive_missing_internal_manifest"),
                (["--archive", str(bad_internal), "--sha256", str(bad_internal_sha), "--json"], "release_archive_bad_internal_checksum"),
            ]
            results = [(run_cli(["v1", "verify-release-archive", *argv], root), expected) for argv, expected in cases]
            text_failure = run_cli(["v1", "verify-release-archive", "--archive", str(archive), "--sha256", str(mismatch_sha)], root)

        for result, expected in results:
            with self.subTest(expected=expected):
                self.assertEqual(result[0], 2, result[1] + result[2])
                payload = json.loads(result[1])
                self.assertFalse(payload["ok"])
                self.assertTrue(any(expected in error for error in payload["errors"]), payload["errors"])
                self.assertNotIn("Traceback", result[1] + result[2])
        self.assertEqual(text_failure[0], 2)
        self.assertIn("AGENTOFFICE_V1_RELEASE_ARCHIVE_VERIFY_FAIL", text_failure[1])
        self.assertNotIn("Traceback", text_failure[1] + text_failure[2])

    def test_github_release_readback_published_positive(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            readback = root / "readback"
            readback.mkdir()
            (readback / "state.json").write_text(
                json.dumps(
                    {
                        "status": "published",
                        "publish_state": "published",
                        "release_url": "https://github.com/mqpmqp/agent-office/releases/tag/v1.0.0",
                        "release_published": True,
                        "assets_uploaded": REQUIRED_ASSETS,
                    }
                ),
                encoding="utf-8",
            )
            json_result = run_cli(["v1", "verify-github-release-readback", "--dir", str(readback), "--json"], root)
            text_result = run_cli(["v1", "verify-github-release-readback", "--dir", str(readback)], root)

        self.assertEqual(json_result[0], 0, json_result[1] + json_result[2])
        payload = json.loads(json_result[1])
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["packet_type"], "agentoffice_v1_github_release_readback_verification")
        self.assertEqual(payload["status"], "published")
        self.assertEqual(payload["publish_state"], "published")
        self.assertEqual(payload["assets"], REQUIRED_ASSETS)
        self.assertEqual(text_result[0], 0, text_result[2])
        self.assertIn("AGENTOFFICE_V1_GITHUB_RELEASE_READBACK_VERIFY_PASS", text_result[1])
        self.assertNotIn("Traceback", json_result[1] + json_result[2] + text_result[1] + text_result[2])

    def test_github_release_readback_verified_existing_positive(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            readback = root / "readback"
            readback.mkdir()
            (readback / "state.json").write_text(
                json.dumps(
                    {
                        "status": "verified_existing",
                        "publish_state": "verified_existing",
                        "release_url": "https://github.com/mqpmqp/agent-office/releases/tag/v1.0.0",
                        "release_published": True,
                    }
                ),
                encoding="utf-8",
            )
            (readback / "release.json").write_text(
                json.dumps({"html_url": "https://github.com/mqpmqp/agent-office/releases/tag/v1.0.0", "assets": [{"name": name} for name in REQUIRED_ASSETS]}),
                encoding="utf-8",
            )
            result = run_cli(["v1", "verify-github-release-readback", "--dir", str(readback), "--json"], root)

        self.assertEqual(result[0], 0, result[1] + result[2])
        payload = json.loads(result[1])
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "verified_existing")
        self.assertEqual(payload["publish_state"], "verified_existing")
        self.assertEqual(payload["assets"], REQUIRED_ASSETS)
        self.assertNotIn("Traceback", result[1] + result[2])

    def test_github_release_readback_skipped_no_token_positive(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            readback = root / "readback"
            readback.mkdir()
            (readback / "state.json").write_text(json.dumps({"status": "skipped_no_token", "publish_state": "skipped", "reason": "release_publish_skipped_token_missing"}), encoding="utf-8")
            json_result = run_cli(["v1", "verify-github-release-readback", "--dir", str(readback), "--json"], root)
            text_result = run_cli(["v1", "verify-github-release-readback", "--dir", str(readback)], root)

        self.assertEqual(json_result[0], 0, json_result[1] + json_result[2])
        payload = json.loads(json_result[1])
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "skipped_no_token")
        self.assertEqual(payload["publish_state"], "skipped")
        self.assertIn("publish_state=skipped", text_result[1])
        self.assertNotIn("Traceback", json_result[1] + json_result[2] + text_result[1] + text_result[2])

    def test_github_release_readback_negative_inputs_are_clean_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            partial = root / "partial"
            partial.mkdir()
            (partial / "state.json").write_text(json.dumps({"status": "partial_remote_state", "publish_state": "partial_remote_state", "assets_uploaded": [REQUIRED_ASSETS[0]]}), encoding="utf-8")
            malformed = root / "malformed"
            malformed.mkdir()
            (malformed / "state.json").write_text("{bad json", encoding="utf-8")
            cases = [
                (root / "missing", "github_release_readback_missing"),
                (partial, "github_release_readback_partial_remote_state"),
                (malformed, "github_release_readback_state_malformed_json"),
            ]
            results = [(run_cli(["v1", "verify-github-release-readback", "--dir", str(path), "--json"], root), expected) for path, expected in cases]
            text_failure = run_cli(["v1", "verify-github-release-readback", "--dir", str(partial)], root)

        for result, expected in results:
            with self.subTest(expected=expected):
                self.assertEqual(result[0], 2, result[1] + result[2])
                payload = json.loads(result[1])
                self.assertFalse(payload["ok"])
                self.assertTrue(any(expected in error for error in payload["errors"]), payload["errors"])
                self.assertNotIn("Traceback", result[1] + result[2])
        self.assertEqual(text_failure[0], 2)
        self.assertIn("AGENTOFFICE_V1_GITHUB_RELEASE_READBACK_VERIFY_FAIL", text_failure[1])
        self.assertNotIn("Traceback", text_failure[1] + text_failure[2])

    def test_post_v1_roadmap_json_and_text_are_stable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            first_json = run_cli(["v1", "post-v1-roadmap", "--json"], root)
            second_json = run_cli(["v1", "post-v1-roadmap", "--json"], root)
            text_result = run_cli(["v1", "post-v1-roadmap"], root)

        self.assertEqual(first_json[0], 0, first_json[2])
        self.assertEqual(second_json[0], 0, second_json[2])
        self.assertEqual(first_json[1], second_json[1])
        payload = json.loads(first_json[1])
        self.assertEqual(payload["packet_type"], "agentoffice_post_v1_roadmap")
        lane_labels = [lane["label"] for lane in payload["lanes"]]
        self.assertIn("v1.0.1 hotfix lane", lane_labels)
        self.assertIn("v1.1 release ops lane", lane_labels)
        self.assertIn("artifact review automation lane", lane_labels)
        self.assertIn("external worker adapter hardening lane", lane_labels)
        self.assertIn("provider/runtime safety lane", lane_labels)
        self.assertIn("validation_commands", payload)
        self.assertFalse(payload["safety"]["dotenv_read"])
        self.assertFalse(payload["safety"]["provider_runtime_adapter_external_behavior"])
        self.assertEqual(text_result[0], 0, text_result[2])
        self.assertIn("AGENTOFFICE_POST_V1_ROADMAP", text_result[1])
        self.assertIn("v1.0.1 hotfix lane", text_result[1])
        self.assertNotIn("Traceback", first_json[1] + first_json[2] + text_result[1] + text_result[2])

    def test_release_ops_v11_surfaces_are_tokenless_and_local(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            commands = [
                ["v1", "release-state", "--json"],
                ["v1", "github-release-handoff", "--json"],
                ["v1", "github-release-plan", "--json"],
                ["v1", "release-candidate", "--version", "v1.1.0", "--json"],
            ]
            results = [run_cli(command, root) for command in commands]

        for result in results:
            self.assertEqual(result[0], 0, result[1] + result[2])
            payload = json.loads(result[1])
            self.assertFalse(payload.get("github_write_performed", False))
            self.assertFalse(payload.get("network_required", False))
            self.assertNotIn("Traceback", result[1] + result[2])
        release_state = json.loads(results[0][1])
        self.assertEqual(release_state["packet_type"], "agentoffice_v1_release_state")
        self.assertEqual(release_state["publish_state"], "skipped")
        self.assertEqual(release_state["github_release_status"], "skipped_no_token")
        handoff = json.loads(results[1][1])
        self.assertEqual(handoff["packet_type"], "agentoffice_v1_github_release_handoff")
        self.assertIn("required_assets", handoff)
        plan = json.loads(results[2][1])
        self.assertEqual(plan["plan_type"], "dry_run_only")
        candidate = json.loads(results[3][1])
        self.assertTrue(candidate["ok"])
        self.assertFalse(candidate["tag_created"])

    def test_release_ops_v11_text_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            results = [
                run_cli(["v1", "release-state"], root),
                run_cli(["v1", "github-release-handoff"], root),
                run_cli(["v1", "github-release-plan"], root),
                run_cli(["v1", "release-candidate", "--version", "v1.1.0"], root),
            ]

        markers = [
            "AGENTOFFICE_V1_RELEASE_STATE",
            "AGENTOFFICE_V1_GITHUB_RELEASE_HANDOFF",
            "AGENTOFFICE_V1_GITHUB_RELEASE_PLAN",
            "AGENTOFFICE_V1_RELEASE_CANDIDATE",
        ]
        for result, marker in zip(results, markers):
            self.assertEqual(result[0], 0, result[1] + result[2])
            self.assertIn(marker, result[1])
            self.assertIn("github_write_performed: false", result[1])
            self.assertNotIn("Traceback", result[1] + result[2])

    def test_release_candidate_invalid_version_is_clean_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            json_result = run_cli(["v1", "release-candidate", "--version", "1.1.0", "--json"], root)
            text_result = run_cli(["v1", "release-candidate", "--version", "1.1.0"], root)

        self.assertEqual(json_result[0], 2)
        payload = json.loads(json_result[1])
        self.assertFalse(payload["ok"])
        self.assertIn("release_candidate_invalid_version", payload["errors"])
        self.assertEqual(text_result[0], 2)
        self.assertIn("AGENTOFFICE_V1_RELEASE_CANDIDATE_FAIL", text_result[1])
        self.assertNotIn("Traceback", json_result[1] + json_result[2] + text_result[1] + text_result[2])
```


## Full Diff

```diff
diff --git a/AUTONOMOUS_DELIVERY_PLATFORM_V1_REPORT.md b/AUTONOMOUS_DELIVERY_PLATFORM_V1_REPORT.md
new file mode 100644
index 0000000..43f0a5d
--- /dev/null
+++ b/AUTONOMOUS_DELIVERY_PLATFORM_V1_REPORT.md
@@ -0,0 +1,151 @@
+# AgentOffice Autonomous Delivery Platform V1 Report
+
+Status: running.
+
+## Mission
+
+Build AgentOffice into an Autonomous Delivery Platform V1 over a long unattended run.
+
+## Baseline
+
+- known mainline ancestor: `41825cb10a993ab73016d7254471a8dd7db761b3`
+- actual mainline head at start: `41825cb10a993ab73016d7254471a8dd7db761b3`
+- v1.0.0 tag commit: `91a8e38cd8d3db540e8c5655304f0f1e4d8f8213`
+- branch: `phase52/autonomous-delivery-platform-v1`
+
+## Safety
+
+- .env not read
+- env vars not printed
+- token not printed
+- provider/runtime/adapter external behavior forbidden
+- no tag mutation
+- no GitHub Release mutation by default
+- no mainline merge
+
+
+## Milestone A - Autonomous Mission Planner
+
+Status: implemented.
+
+Commands:
+
+`ash
+python3 -m agent_office autonomy plan --goal release-ops --json
+python3 -m agent_office autonomy plan --goal release-ops
+python3 -m agent_office autonomy plan --goal post-v1 --json
+python3 -m agent_office autonomy plan --goal post-v1
+python3 -m agent_office autonomy plan --goal autonomous-delivery --json
+python3 -m agent_office autonomy plan --goal autonomous-delivery
+`
+
+Coverage:
+
+- deterministic local JSON/text mission plans
+- phases, tasks, validation commands, stop conditions, safety boundaries, artifacts, review handoff, merge gate handoff
+- unknown goal clean CLI failure without traceback
+
+## Milestone B - Autonomous Run Ledger And Checkpoints
+
+Status: implemented.
+
+Commands:
+
+`ash
+python3 -m agent_office autonomy init --goal autonomous-delivery --path .ai/autonomy/runs/demo --json
+python3 -m agent_office autonomy status --path .ai/autonomy/runs/demo --json
+python3 -m agent_office autonomy checkpoint --path .ai/autonomy/runs/demo --name preflight --status passed --json
+python3 -m agent_office autonomy report --path .ai/autonomy/runs/demo --json
+`
+
+Coverage:
+
+- stable local ledger.json with checkpoints, artifacts, and validation_records lists
+- status transitions through allowlisted checkpoint statuses
+- path traversal, symlink, missing, malformed, and invalid ledger failures return clean CLI errors
+- project-root/temp path boundary enforced
+
+## Milestone C - Local Validation Recorder
+
+Status: implemented.
+
+Commands:
+
+`ash
+python3 -m agent_office autonomy validate --path .ai/autonomy/runs/demo --suite minimal --json
+python3 -m agent_office autonomy validate --path .ai/autonomy/runs/demo --suite release --json
+python3 -m agent_office autonomy validate --path .ai/autonomy/runs/demo --suite full --json
+`
+
+Coverage:
+
+- allowlisted suites only: minimal, release, full
+- no user-supplied shell command execution
+- records command text, argv, exit code, stdout path, stderr path, and duration
+- appends validation records into the run ledger and updates ledger status
+- failed command results are preserved and returned as clean JSON/text failure
+
+## Milestone D - Review Packet Generator
+
+Status: implemented.
+
+Commands:
+
+`ash
+python3 -m agent_office autonomy review-packet --base <base_commit> --head HEAD --out /tmp/review-packet.md --json
+python3 -m agent_office autonomy review-packet --base <base_commit> --head HEAD --out /tmp/review-packet.md
+`
+
+Coverage:
+
+- local Markdown review bundle generation without provider calls
+- includes branch, base/head, commits, diff stat, name-status, full diff, safety boundaries, and changed file snapshots
+- rejects traversal, .env, symlink, directory, and outside-root output paths
+- missing git refs return clean CLI errors
+
+## Milestone E - Merge Gate Packet Generator
+
+Status: implemented.
+
+Commands:
+
+`ash
+python3 -m agent_office autonomy merge-packet --source phase52/autonomous-delivery-platform-v1 --target phase6/mainline --json
+python3 -m agent_office autonomy merge-packet --source phase52/autonomous-delivery-platform-v1 --target phase6/mainline
+`
+
+Coverage:
+
+- local-only source/target ref inspection
+- records source head, target head, merge-base, changed files, required validations, required reports, stop conditions, exact merge commands, post-merge validation, and rollback notes
+- does not execute merge or mutate branches
+- missing source/target refs return clean CLI errors
+
+## Milestone F - Release Operations System V1.1
+
+Status: implemented.
+
+Commands:
+
+`ash
+python3 -m agent_office v1 release-state --json
+python3 -m agent_office v1 github-release-handoff --json
+python3 -m agent_office v1 github-release-plan --json
+python3 -m agent_office v1 release-candidate --version v1.1.0 --json
+`
+
+Coverage:
+
+- tokenless release-state honesty: skipped_no_token remains skipped, not published
+- GitHub Release operator handoff and dry-run plan perform no network or GitHub writes
+- release-candidate packet does not create tags or releases
+- invalid candidate versions return clean failures
+
+## Milestone G - Longrun Operator Docs
+
+Status: implemented.
+
+Coverage:
+
+- README documents autonomy plan, ledger, validation, review packet, merge packet, release ops handoff, no-token release behavior, safety boundaries, and recommended operator workflow
+- existing README content was appended, not rewritten
diff --git a/README.md b/README.md
index 428270a..74fcad1 100755
--- a/README.md
+++ b/README.md
@@ -1202,3 +1202,64 @@ P35 dogfoods the one-click Codex delivery runner introduced by P34. The intended
 5. verify local and remote `phase6/mainline` are synced to the resulting merge commit.

 This flow remains static and local to git/repository state; it must not read `.env`, print environment variables, or trigger provider/model/runtime/adapter behavior.
+
+## Autonomous Delivery Platform V1
+
+AgentOffice includes a local-only autonomous delivery workflow for long-running, reviewable delivery branches. These commands do not read `.env`, print environment variables, call providers or models, mutate tags, create GitHub Releases, or merge into `phase6/mainline`.
+
+Mission planning:
+
+```bash
+python3 -m agent_office autonomy plan --goal release-ops --json
+python3 -m agent_office autonomy plan --goal post-v1 --json
+python3 -m agent_office autonomy plan --goal autonomous-delivery --json
+```
+
+Run ledger and checkpoints:
+
+```bash
+python3 -m agent_office autonomy init --goal autonomous-delivery --path .ai/autonomy/runs/demo --json
+python3 -m agent_office autonomy status --path .ai/autonomy/runs/demo --json
+python3 -m agent_office autonomy checkpoint --path .ai/autonomy/runs/demo --name preflight --status passed --json
+python3 -m agent_office autonomy report --path .ai/autonomy/runs/demo --json
+```
+
+Validation recorder:
+
+```bash
+python3 -m agent_office autonomy validate --path .ai/autonomy/runs/demo --suite minimal --json
+python3 -m agent_office autonomy validate --path .ai/autonomy/runs/demo --suite release --json
+python3 -m agent_office autonomy validate --path .ai/autonomy/runs/demo --suite full --json
+```
+
+`autonomy validate` only runs built-in allowlisted suites. It is not a general shell runner. Each command record stores the command text, argv, exit code, stdout path, stderr path, and duration in the run ledger.
+
+Review and merge gate packets:
+
+```bash
+python3 -m agent_office autonomy review-packet --base <base_commit> --head HEAD --out /tmp/review-packet.md --json
+python3 -m agent_office autonomy merge-packet --source phase52/autonomous-delivery-platform-v1 --target phase6/mainline --json
+```
+
+`review-packet` writes a Markdown bundle with commit list, diff stat, name-status, full diff, file snapshots, safety boundaries, caveats, and review focus. `merge-packet` emits source/target heads, merge-base, changed files, required validations, required reports, exact merge commands, post-merge validation, and rollback notes; it does not execute a merge.
+
+Release operations handoff:
+
+```bash
+python3 -m agent_office v1 release-state --json
+python3 -m agent_office v1 github-release-handoff --json
+python3 -m agent_office v1 github-release-plan --json
+python3 -m agent_office v1 release-candidate --version v1.1.0 --json
+```
+
+No-token release behavior is explicit: `skipped_no_token` remains `publish_state=skipped`, never `published`. Release handoff and plan packets are dry-run/operator packets and perform no GitHub writes.
+
+Recommended operator workflow:
+
+1. Create or resume a feature branch.
+2. Generate an autonomy plan for the goal.
+3. Initialize a run ledger under `.ai/autonomy/runs/<run-id>`.
+4. Add checkpoints after preflight, implementation, validation, review packet, and merge packet steps.
+5. Run `minimal` validation after each milestone and `full` validation before review.
+6. Generate a review packet and merge packet.
+7. Review the branch; merge only after explicit human authorization and a fresh merge gate.
diff --git a/agent_office/autonomy.py b/agent_office/autonomy.py
new file mode 100644
index 0000000..7b3117d
--- /dev/null
+++ b/agent_office/autonomy.py
@@ -0,0 +1,665 @@
+from __future__ import annotations
+
+from typing import Any
+
+import json
+import os
+import subprocess
+import time
+from datetime import datetime, timezone
+from pathlib import Path
+
+
+SCHEMA_VERSION = 1
+PLAN_PACKET_TYPE = "agentoffice_autonomy_mission_plan"
+PLAN_MARKER = "AGENTOFFICE_AUTONOMY_MISSION_PLAN"
+LEDGER_PACKET_TYPE = "agentoffice_autonomy_run_ledger"
+LEDGER_MARKER = "AGENTOFFICE_AUTONOMY_RUN_LEDGER"
+ALLOWED_LEDGER_STATUSES = {"pending", "running", "passed", "failed", "skipped", "blocked"}
+VALIDATION_SUITES = {"minimal", "release", "full"}
+
+
+class AutonomyError(RuntimeError):
+    pass
+
+
+SAFETY_BOUNDARIES = [
+    ".env is never read",
+    "environment variables and token values are never printed",
+    "provider, runtime, adapter, and model external behavior is not triggered",
+    "GitHub tags and releases are not created, overwritten, or deleted",
+    "phase6/mainline is not merged or mutated by autonomy commands",
+    "validation uses local allowlisted commands only",
+]
+
+STOP_CONDITIONS = [
+    "tracked worktree changes exist before a write-oriented milestone starts",
+    "required baseline commit or release tag does not match the expected value",
+    "a validation suite fails after one focused repair attempt",
+    "a milestone requires credentials, tokens, or external provider access",
+    "an output path targets .env, a symlink, or path traversal outside the project/output root",
+]
+
+
+def autonomy_plan_payload(goal: str) -> dict[str, Any]:
+    normalized = goal.strip().lower()
+    plans = _plans()
+    if normalized not in plans:
+        supported = ", ".join(sorted(plans))
+        raise AutonomyError(f"unknown autonomy goal: {goal}. supported goals: {supported}.")
+    plan = plans[normalized]
+    return {
+        "schema_version": SCHEMA_VERSION,
+        "packet_type": PLAN_PACKET_TYPE,
+        "goal": normalized,
+        "status": "ready",
+        "local_only": True,
+        "network_required": False,
+        "provider_runtime_adapter_external_behavior": False,
+        "phases": plan["phases"],
+        "validation_commands": plan["validation_commands"],
+        "stop_conditions": STOP_CONDITIONS,
+        "safety_boundaries": SAFETY_BOUNDARIES,
+        "expected_artifacts": plan["expected_artifacts"],
+        "review_handoff": plan["review_handoff"],
+        "merge_gate_handoff": plan["merge_gate_handoff"],
+    }
+
+
+def format_autonomy_plan(payload: dict[str, Any]) -> str:
+    lines = [
+        PLAN_MARKER,
+        f"goal: {payload['goal']}",
+        f"status: {payload['status']}",
+        f"local_only: {_bool_text(bool(payload['local_only']))}",
+        f"network_required: {_bool_text(bool(payload['network_required']))}",
+        "phases:",
+    ]
+    for phase in payload["phases"]:
+        lines.append(f"  - {phase['id']}: {phase['name']}")
+        lines.append(f"    objective: {phase['objective']}")
+        lines.append("    tasks:")
+        for task in phase["tasks"]:
+            lines.append(f"      * {task}")
+    lines.append("validation_commands:")
+    for command in payload["validation_commands"]:
+        lines.append(f"  - {command}")
+    lines.append("stop_conditions:")
+    for condition in payload["stop_conditions"]:
+        lines.append(f"  - {condition}")
+    lines.append("safety_boundaries:")
+    for boundary in payload["safety_boundaries"]:
+        lines.append(f"  - {boundary}")
+    lines.append("expected_artifacts:")
+    for artifact in payload["expected_artifacts"]:
+        lines.append(f"  - {artifact}")
+    lines.append("review_handoff:")
+    for item in payload["review_handoff"]:
+        lines.append(f"  - {item}")
+    lines.append("merge_gate_handoff:")
+    for item in payload["merge_gate_handoff"]:
+        lines.append(f"  - {item}")
+    return "\n".join(lines)
+
+
+def _plans() -> dict[str, dict[str, Any]]:
+    return {
+        "release-ops": {
+            "phases": [
+                _phase("release-state", "Release State Inspection", "Summarize tokenless local release status without GitHub writes.", ["verify v1.0.0 archive and checksum if artifacts are present", "verify local GitHub release readback evidence", "classify skipped_no_token honestly as skipped, not published"]),
+                _phase("handoff", "Operator Handoff", "Produce deterministic release handoff and dry-run publish guidance.", ["list required assets and exact manual release checks", "record commands that remain token-gated", "document no-write default behavior"]),
+            ],
+            "validation_commands": _common_validation() + [
+                "python3 -m agent_office v1 verify-release-archive --archive /opt/agent-office/agentoffice-v1.0.0-final-delivery-archive.tar.gz --sha256 /opt/agent-office/agentoffice-v1.0.0-final-delivery-archive.tar.gz.sha256 --json",
+                "python3 -m agent_office v1 verify-github-release-readback --dir /opt/agent-office/V1_0_0_GITHUB_RELEASE_API_LONGRUN_READBACK --json",
+            ],
+            "expected_artifacts": ["release-state JSON/text packet", "GitHub release handoff packet", "dry-run publish plan packet"],
+            "review_handoff": ["review release-state honesty and no-token behavior", "confirm no GitHub write path runs without explicit operator action"],
+            "merge_gate_handoff": ["require archive/readback verification output", "require no tag or release mutation in git/release logs"],
+        },
+        "post-v1": {
+            "phases": [
+                _phase("roadmap", "Post-V1 Roadmap", "Turn v1 release outputs into reviewable post-v1 operating lanes.", ["emit deterministic roadmap JSON/text", "separate hotfix, release-ops, and artifact-review lanes", "preserve mainline and release immutability boundaries"]),
+                _phase("evidence", "Evidence Closure", "Collect local validation and review evidence for the next branch gate.", ["record validation commands and results", "generate review packet inputs", "generate merge gate inputs without merging"]),
+            ],
+            "validation_commands": _common_validation() + ["python3 -m agent_office v1 post-v1-roadmap --json"],
+            "expected_artifacts": ["post-v1 roadmap packet", "review evidence bundle", "merge gate packet"],
+            "review_handoff": ["review roadmap lane scope and safety non-goals", "check validation evidence before merge discussion"],
+            "merge_gate_handoff": ["confirm source branch is pushed and target branch is unchanged", "run full local validation before any no-ff merge"],
+        },
+        "autonomous-delivery": {
+            "phases": [
+                _phase("plan", "Autonomous Mission Planner", "Create deterministic local mission plans for delivery goals.", ["emit stable JSON/text plans", "include phases, tasks, validation, stop conditions, and handoffs", "fail cleanly for unknown goals"]),
+                _phase("ledger", "Run Ledger And Checkpoints", "Persist resumable local run state for long unattended delivery work.", ["initialize a run ledger under an operator-selected path", "record checkpoints, artifacts, and validation results", "reject traversal, symlink, malformed, and .env paths"]),
+                _phase("validate", "Validation Recorder", "Run allowlisted local validation suites and save transcripts.", ["support minimal, release, and full validation suites", "record command, exit code, stdout/stderr paths, and duration", "avoid arbitrary shell command execution"]),
+                _phase("review-packet", "Review Packet Generator", "Generate local review bundles without calling Claude or any provider.", ["include commit list, diff stat, name-status, full diff, and snapshots", "summarize validation and caveats", "reject unsafe output paths"]),
+                _phase("merge-packet", "Merge Gate Packet Generator", "Generate merge instructions and stop conditions without executing a merge.", ["record source, target, heads, merge-base, and changed files", "emit exact validation and merge commands", "document rollback notes and required reports"]),
+            ],
+            "validation_commands": _common_validation() + ["python3 -m agent_office autonomy plan --goal autonomous-delivery --json", "python3 -m agent_office autonomy plan --goal autonomous-delivery"],
+            "expected_artifacts": ["AUTONOMOUS_DELIVERY_PLATFORM_V1_REPORT.md", "AUTONOMOUS_DELIVERY_PLATFORM_V1_SELF_REVIEW.md", "AUTONOMOUS_DELIVERY_PLATFORM_V1_REVIEW_BUNDLE.md", "AUTONOMOUS_DELIVERY_PLATFORM_V1_REVIEW_BUNDLE.md.sha256"],
+            "review_handoff": ["review each milestone as an independently shippable local-only feature", "verify ledger, validation, review, and merge packets do not read .env or call providers", "check tests cover positive, negative, and deterministic output paths"],
+            "merge_gate_handoff": ["do not merge automatically", "require final full validation and pushed feature branch", "attach self-review, review bundle, and SHA256 sidecar"],
+        },
+    }
+
+
+def _phase(identifier: str, name: str, objective: str, tasks: list[str]) -> dict[str, Any]:
+    return {"id": identifier, "name": name, "objective": objective, "tasks": tasks}
+
+
+def _common_validation() -> list[str]:
+    return [
+        "python3 -m compileall agent_office tests",
+        "python3 -m unittest discover -s tests -p 'test_*.py'",
+        "git diff --check",
+    ]
+
+
+def _bool_text(value: bool) -> str:
+    return "true" if value else "false"
+
+
+
+def autonomy_init_payload(path: str, goal: str, project_root: Path) -> dict[str, Any]:
+    run_dir = _safe_run_dir(path, project_root, must_exist=False)
+    normalized_goal = goal.strip().lower()
+    if normalized_goal not in _plans():
+        supported = ", ".join(sorted(_plans()))
+        raise AutonomyError(f"unknown autonomy goal: {goal}. supported goals: {supported}.")
+    run_dir.mkdir(parents=True, exist_ok=True)
+    ledger = {
+        "schema_version": SCHEMA_VERSION,
+        "packet_type": LEDGER_PACKET_TYPE,
+        "goal": normalized_goal,
+        "status": "running",
+        "path": str(run_dir),
+        "created_at": _now_iso(),
+        "updated_at": _now_iso(),
+        "checkpoints": [],
+        "artifacts": [],
+        "validation_records": [],
+    }
+    _write_ledger(run_dir, ledger)
+    return _ledger_response("init", ledger)
+
+
+def autonomy_status_payload(path: str, project_root: Path) -> dict[str, Any]:
+    run_dir = _safe_run_dir(path, project_root, must_exist=True)
+    ledger = _read_ledger(run_dir)
+    return _ledger_response("status", ledger)
+
+
+def autonomy_checkpoint_payload(path: str, name: str, status: str, project_root: Path) -> dict[str, Any]:
+    if status not in ALLOWED_LEDGER_STATUSES:
+        raise AutonomyError(f"invalid checkpoint status: {status}.")
+    if not name.strip():
+        raise AutonomyError("checkpoint name is required.")
+    run_dir = _safe_run_dir(path, project_root, must_exist=True)
+    ledger = _read_ledger(run_dir)
+    checkpoint = {"name": name.strip(), "status": status, "recorded_at": _now_iso()}
+    ledger["checkpoints"].append(checkpoint)
+    ledger["status"] = status
+    ledger["updated_at"] = checkpoint["recorded_at"]
+    _write_ledger(run_dir, ledger)
+    return _ledger_response("checkpoint", ledger, checkpoint=checkpoint)
+
+
+def autonomy_report_payload(path: str, project_root: Path) -> dict[str, Any]:
+    run_dir = _safe_run_dir(path, project_root, must_exist=True)
+    ledger = _read_ledger(run_dir)
+    summary = {
+        "checkpoint_count": len(ledger["checkpoints"]),
+        "artifact_count": len(ledger["artifacts"]),
+        "validation_record_count": len(ledger["validation_records"]),
+        "latest_checkpoint": ledger["checkpoints"][-1] if ledger["checkpoints"] else None,
+    }
+    return _ledger_response("report", ledger, summary=summary)
+
+
+
+def autonomy_validate_payload(path: str, suite: str, project_root: Path) -> dict[str, Any]:
+    if suite not in VALIDATION_SUITES:
+        supported = ", ".join(sorted(VALIDATION_SUITES))
+        raise AutonomyError(f"unknown validation suite: {suite}. supported suites: {supported}.")
+    run_dir = _safe_run_dir(path, project_root, must_exist=True)
+    ledger = _read_ledger(run_dir)
+    validation_dir = run_dir / "validation" / _validation_run_id(suite)
+    validation_dir.mkdir(parents=True, exist_ok=False)
+    commands = _validation_commands(suite)
+    records = []
+    for index, command in enumerate(commands, start=1):
+        records.append(_run_validation_command(command, index, validation_dir, project_root))
+    ok = all(record["exit_code"] == 0 for record in records)
+    validation_record = {
+        "suite": suite,
+        "status": "passed" if ok else "failed",
+        "recorded_at": _now_iso(),
+        "commands": records,
+    }
+    ledger["validation_records"].append(validation_record)
+    ledger["status"] = validation_record["status"]
+    ledger["updated_at"] = validation_record["recorded_at"]
+    _write_ledger(run_dir, ledger)
+    return {"ok": ok, "action": "validate", "suite": suite, "ledger": ledger, "validation": validation_record}
+
+
+def format_autonomy_validation(payload: dict[str, Any]) -> str:
+    validation = payload["validation"]
+    lines = [
+        "AGENTOFFICE_AUTONOMY_VALIDATION",
+        f"suite: {payload['suite']}",
+        f"status: {validation['status']}",
+        f"ok: {_bool_text(bool(payload['ok']))}",
+        "commands:",
+    ]
+    for record in validation["commands"]:
+        lines.append(f"  - {record['command']}: exit_code={record['exit_code']} duration_seconds={record['duration_seconds']}")
+        lines.append(f"    stdout: {record['stdout_path']}")
+        lines.append(f"    stderr: {record['stderr_path']}")
+    return "\n".join(lines)
+
+
+def autonomy_review_packet_payload(base: str, head: str, out: str, project_root: Path) -> dict[str, Any]:
+    out_path = _safe_output_file(out, project_root)
+    base_commit = _git_capture(["rev-parse", "--verify", base], project_root, "review_packet_base").strip()
+    head_commit = _git_capture(["rev-parse", "--verify", head], project_root, "review_packet_head").strip()
+    branch = _git_capture(["branch", "--show-current"], project_root, "review_packet_branch").strip() or "detached"
+    commits = _git_capture(["log", "--oneline", f"{base_commit}..{head_commit}"], project_root, "review_packet_log").splitlines()
+    diff_stat = _git_capture(["diff", "--stat", base_commit, head_commit], project_root, "review_packet_diff_stat")
+    name_status = _git_capture(["diff", "--name-status", base_commit, head_commit], project_root, "review_packet_name_status")
+    full_diff = _git_capture(["diff", "--no-ext-diff", base_commit, head_commit], project_root, "review_packet_full_diff")
+    snapshots = _changed_file_snapshots(name_status, head_commit, project_root)
+    bundle = _format_review_packet_markdown(
+        base_commit=base_commit,
+        head_commit=head_commit,
+        branch=branch,
+        commits=commits,
+        diff_stat=diff_stat,
+        name_status=name_status,
+        full_diff=full_diff,
+        snapshots=snapshots,
+    )
+    out_path.parent.mkdir(parents=True, exist_ok=True)
+    if out_path.exists() and out_path.is_symlink():
+        raise AutonomyError("review packet output symlink refused.")
+    out_path.write_text(bundle, encoding="utf-8")
+    return {
+        "ok": True,
+        "action": "review-packet",
+        "base": base_commit,
+        "head": head_commit,
+        "branch": branch,
+        "out": str(out_path),
+        "commit_count": len(commits),
+        "snapshot_count": len(snapshots),
+        "safety_boundaries": SAFETY_BOUNDARIES,
+    }
+
+
+def format_autonomy_review_packet(payload: dict[str, Any]) -> str:
+    return "\n".join(
+        [
+            "AGENTOFFICE_AUTONOMY_REVIEW_PACKET",
+            f"ok: {_bool_text(bool(payload['ok']))}",
+            f"branch: {payload['branch']}",
+            f"base: {payload['base']}",
+            f"head: {payload['head']}",
+            f"out: {payload['out']}",
+            f"commits: {payload['commit_count']}",
+            f"snapshots: {payload['snapshot_count']}",
+        ]
+    )
+
+
+def autonomy_merge_packet_payload(source: str, target: str, project_root: Path) -> dict[str, Any]:
+    source_head = _git_capture(["rev-parse", "--verify", source], project_root, "merge_packet_source").strip()
+    target_head = _git_capture(["rev-parse", "--verify", target], project_root, "merge_packet_target").strip()
+    merge_base = _git_capture(["merge-base", target_head, source_head], project_root, "merge_packet_merge_base").strip()
+    changed_files_text = _git_capture(["diff", "--name-status", merge_base, source_head], project_root, "merge_packet_changed_files")
+    changed_files = [line for line in changed_files_text.splitlines() if line.strip()]
+    payload = {
+        "ok": True,
+        "action": "merge-packet",
+        "source_branch": source,
+        "target_branch": target,
+        "source_head": source_head,
+        "target_head": target_head,
+        "merge_base": merge_base,
+        "changed_files": changed_files,
+        "required_validations": [
+            "python3 -m compileall agent_office tests",
+            "python3 -m unittest",
+            "python3 -m unittest discover -s tests -p 'test_*.py'",
+            "python3 -m agent_office doctor --adapters",
+            "./scripts/verify.sh",
+            "git diff --check",
+        ],
+        "reports_required": [
+            "AUTONOMOUS_DELIVERY_PLATFORM_V1_REPORT.md",
+            "AUTONOMOUS_DELIVERY_PLATFORM_V1_SELF_REVIEW.md",
+            "AUTONOMOUS_DELIVERY_PLATFORM_V1_REVIEW_BUNDLE.md",
+            "AUTONOMOUS_DELIVERY_PLATFORM_V1_REVIEW_BUNDLE.md.sha256",
+        ],
+        "stop_conditions": STOP_CONDITIONS + [
+            "source or target head differs from this packet at merge time",
+            "feature branch has unpushed commits",
+            "review bundle or self-review is missing",
+        ],
+        "merge_commands": [
+            f"git checkout {target}",
+            f"git pull --ff-only origin {target}",
+            f"git merge --no-ff --no-commit {source}",
+            "python3 -m compileall agent_office tests",
+            "python3 -m unittest discover -s tests -p 'test_*.py'",
+            "git diff --check --cached",
+            f"git commit -m 'Merge {source}'",
+        ],
+        "post_merge_validation": [
+            "python3 -m compileall agent_office tests",
+            "python3 -m unittest",
+            "python3 -m unittest discover -s tests -p 'test_*.py'",
+            "git diff --check",
+        ],
+        "rollback_notes": [
+            "Before commit, abort a staged merge with git merge --abort.",
+            "After commit, revert the merge commit instead of force pushing.",
+            "Do not delete or overwrite tags or GitHub Releases during rollback.",
+        ],
+        "merge_performed": False,
+    }
+    return payload
+
+
+def format_autonomy_merge_packet(payload: dict[str, Any]) -> str:
+    lines = [
+        "AGENTOFFICE_AUTONOMY_MERGE_PACKET",
+        f"ok: {_bool_text(bool(payload['ok']))}",
+        f"source_branch: {payload['source_branch']}",
+        f"target_branch: {payload['target_branch']}",
+        f"source_head: {payload['source_head']}",
+        f"target_head: {payload['target_head']}",
+        f"merge_base: {payload['merge_base']}",
+        "changed_files:",
+    ]
+    lines.extend(f"  - {item}" for item in payload["changed_files"] or ["none"])
+    lines.append("required_validations:")
+    lines.extend(f"  - {item}" for item in payload["required_validations"])
+    lines.append("reports_required:")
+    lines.extend(f"  - {item}" for item in payload["reports_required"])
+    lines.append("stop_conditions:")
+    lines.extend(f"  - {item}" for item in payload["stop_conditions"])
+    lines.append("exact_merge_commands:")
+    lines.extend(f"  - {item}" for item in payload["merge_commands"])
+    lines.append("post_merge_validation:")
+    lines.extend(f"  - {item}" for item in payload["post_merge_validation"])
+    lines.append("rollback_notes:")
+    lines.extend(f"  - {item}" for item in payload["rollback_notes"])
+    lines.append("merge_performed: false")
+    return "\n".join(lines)
+
+def format_autonomy_ledger(payload: dict[str, Any]) -> str:
+    ledger = payload["ledger"]
+    lines = [
+        LEDGER_MARKER,
+        f"action: {payload['action']}",
+        f"goal: {ledger['goal']}",
+        f"status: {ledger['status']}",
+        f"path: {ledger['path']}",
+        f"checkpoints: {len(ledger['checkpoints'])}",
+        f"artifacts: {len(ledger['artifacts'])}",
+        f"validation_records: {len(ledger['validation_records'])}",
+    ]
+    checkpoint = payload.get("checkpoint")
+    if checkpoint:
+        lines.append(f"latest_checkpoint: {checkpoint['name']} ({checkpoint['status']})")
+    summary = payload.get("summary")
+    if summary:
+        lines.append("summary:")
+        lines.append(f"  checkpoint_count: {summary['checkpoint_count']}")
+        lines.append(f"  artifact_count: {summary['artifact_count']}")
+        lines.append(f"  validation_record_count: {summary['validation_record_count']}")
+        latest = summary.get("latest_checkpoint")
+        lines.append(f"  latest_checkpoint: {latest['name'] + ' (' + latest['status'] + ')' if latest else 'none'}")
+    return "\n".join(lines)
+
+
+def _ledger_response(action: str, ledger: dict[str, Any], **extra: Any) -> dict[str, Any]:
+    payload = {"ok": True, "action": action, "ledger": ledger}
+    payload.update(extra)
+    return payload
+
+
+
+def _safe_output_file(path: str, project_root: Path) -> Path:
+    if not str(path).strip():
+        raise AutonomyError("output path is required.")
+    candidate = Path(path)
+    if any(part in {"..", ""} for part in candidate.parts) or any(part == ".env" for part in candidate.parts):
+        raise AutonomyError("output path contains refused traversal or .env component.")
+    if not candidate.is_absolute():
+        candidate = project_root / candidate
+    _reject_symlink_components(candidate if candidate.exists() else candidate.parent)
+    candidate = candidate.resolve(strict=False)
+    root = project_root.resolve(strict=False)
+    tmp = Path(os.getenv("TMPDIR", "/tmp")).resolve(strict=False)
+    if not _is_relative_to(candidate, root) and not _is_relative_to(candidate, tmp):
+        raise AutonomyError("output path must stay under the project root or temp directory.")
+    if candidate.exists() and candidate.is_dir():
+        raise AutonomyError("output path is a directory.")
+    return candidate
+
+
+def _git_capture(args: list[str], project_root: Path, label: str) -> str:
+    result = subprocess.run(["git", *args], cwd=project_root, text=True, capture_output=True, check=False)
+    if result.returncode != 0:
+        message = (result.stderr or result.stdout or "git command failed").strip().splitlines()
+        detail = message[0] if message else "git command failed"
+        raise AutonomyError(f"{label} failed: {detail}")
+    return result.stdout
+
+
+def _changed_file_snapshots(name_status: str, head_commit: str, project_root: Path) -> list[dict[str, Any]]:
+    snapshots = []
+    for raw_line in name_status.splitlines():
+        parts = raw_line.split("\t")
+        if len(parts) < 2:
+            continue
+        status = parts[0]
+        file_path = parts[-1]
+        path_obj = Path(file_path)
+        if status.startswith("D") or any(part == ".env" for part in path_obj.parts):
+            snapshots.append({"path": file_path, "status": status, "skipped": True, "reason": "deleted_or_refused_path"})
+            continue
+        result = subprocess.run(["git", "show", f"{head_commit}:{file_path}"], cwd=project_root, text=True, capture_output=True, check=False)
+        if result.returncode != 0:
+            snapshots.append({"path": file_path, "status": status, "skipped": True, "reason": "snapshot_unavailable"})
+            continue
+        content = result.stdout
+        truncated = len(content) > 20000
+        snapshots.append({"path": file_path, "status": status, "skipped": False, "truncated": truncated, "content": content[:20000]})
+    return snapshots
+
+
+def _format_review_packet_markdown(*, base_commit: str, head_commit: str, branch: str, commits: list[str], diff_stat: str, name_status: str, full_diff: str, snapshots: list[dict[str, Any]]) -> str:
+    lines = [
+        "# AgentOffice Autonomy Review Packet",
+        "",
+        "Marker: AGENTOFFICE_AUTONOMY_REVIEW_PACKET",
+        "",
+        "## Scope",
+        "",
+        f"- branch: `{branch}`",
+        f"- base: `{base_commit}`",
+        f"- head: `{head_commit}`",
+        "",
+        "## Safety Boundaries",
+        "",
+    ]
+    lines.extend(f"- {boundary}" for boundary in SAFETY_BOUNDARIES)
+    lines.extend(["", "## Commit List", "", "```text"])
+    lines.extend(commits or ["none"])
+    lines.extend(["```", "", "## Diff Stat", "", "```text", diff_stat.rstrip() or "none", "```", "", "## Name Status", "", "```text", name_status.rstrip() or "none", "```", "", "## Full Diff", "", "```diff", full_diff.rstrip() or "none", "```", "", "## Changed File Snapshots", ""])
+    for snapshot in snapshots:
+        lines.append(f"### {snapshot['path']}")
+        lines.append("")
+        lines.append(f"- status: `{snapshot['status']}`")
+        if snapshot.get("skipped"):
+            lines.append(f"- skipped: `{snapshot['reason']}`")
+            lines.append("")
+            continue
+        lines.append(f"- truncated: `{_bool_text(bool(snapshot['truncated']))}`")
+        lines.append("")
+        lines.append("```text")
+        lines.append(str(snapshot["content"]).rstrip())
+        lines.append("```")
+        lines.append("")
+    lines.extend(["## Validation Summary", "", "Validation is supplied by the active autonomy ledger or external gate report.", "", "## Requested Review Focus", "", "- correctness of changed behavior", "- safety boundary preservation", "- deterministic output contracts", "- missing tests or operator caveats", "", "## Known Caveats", "", "- This packet is generated locally and does not call external reviewers or providers.", ""])
+    return "\n".join(lines)
+
+def _safe_run_dir(path: str, project_root: Path, *, must_exist: bool) -> Path:
+    if not str(path).strip():
+        raise AutonomyError("run path is required.")
+    candidate = Path(path)
+    if any(part in {"..", ""} for part in candidate.parts) or any(part == ".env" for part in candidate.parts):
+        raise AutonomyError("run path contains refused traversal or .env component.")
+    if not candidate.is_absolute():
+        candidate = project_root / candidate
+    _reject_symlink_components(candidate)
+    candidate = candidate.resolve(strict=False)
+    root = project_root.resolve(strict=False)
+    tmp = Path(os.getenv("TMPDIR", "/tmp")).resolve(strict=False)
+    if not _is_relative_to(candidate, root) and not _is_relative_to(candidate, tmp):
+        raise AutonomyError("run path must stay under the project root or temp directory.")
+    current = candidate if candidate.exists() else candidate.parent
+    while current != current.parent:
+        if current.exists() and current.is_symlink():
+            raise AutonomyError("run path symlink refused.")
+        if current == root or current == tmp:
+            break
+        current = current.parent
+    if must_exist and not candidate.exists():
+        raise AutonomyError("run ledger path is missing.")
+    if candidate.exists() and not candidate.is_dir():
+        raise AutonomyError("run ledger path is not a directory.")
+    return candidate
+
+
+def _reject_symlink_components(path: Path) -> None:
+    current = path
+    candidates = []
+    while current != current.parent:
+        candidates.append(current)
+        current = current.parent
+    for candidate in candidates:
+        if candidate.exists() and candidate.is_symlink():
+            raise AutonomyError("run path symlink refused.")
+
+
+def _ledger_path(run_dir: Path) -> Path:
+    return run_dir / "ledger.json"
+
+
+def _read_ledger(run_dir: Path) -> dict[str, Any]:
+    path = _ledger_path(run_dir)
+    if path.is_symlink():
+        raise AutonomyError("run ledger symlink refused.")
+    try:
+        data = json.loads(path.read_text(encoding="utf-8"))
+    except FileNotFoundError as exc:
+        raise AutonomyError("run ledger file is missing.") from exc
+    except json.JSONDecodeError as exc:
+        raise AutonomyError("run ledger file is malformed JSON.") from exc
+    except OSError as exc:
+        raise AutonomyError("run ledger file is unreadable.") from exc
+    if not isinstance(data, dict):
+        raise AutonomyError("run ledger file must contain a JSON object.")
+    for key in ("schema_version", "packet_type", "goal", "status", "path", "created_at", "updated_at", "checkpoints", "artifacts", "validation_records"):
+        if key not in data:
+            raise AutonomyError(f"run ledger missing required key: {key}.")
+    if data["packet_type"] != LEDGER_PACKET_TYPE:
+        raise AutonomyError("run ledger packet type is invalid.")
+    if data["status"] not in ALLOWED_LEDGER_STATUSES:
+        raise AutonomyError("run ledger status is invalid.")
+    for key in ("checkpoints", "artifacts", "validation_records"):
+        if not isinstance(data[key], list):
+            raise AutonomyError(f"run ledger {key} must be a list.")
+    return data
+
+
+def _write_ledger(run_dir: Path, ledger: dict[str, Any]) -> None:
+    path = _ledger_path(run_dir)
+    if path.exists() and path.is_symlink():
+        raise AutonomyError("run ledger symlink refused.")
+    tmp_path = run_dir / "ledger.json.tmp"
+    tmp_path.write_text(json.dumps(ledger, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
+    tmp_path.replace(path)
+
+
+
+def _validation_commands(suite: str) -> list[list[str]]:
+    minimal = [
+        ["python3", "-m", "compileall", "agent_office", "tests"],
+        ["python3", "-m", "unittest", "tests.test_autonomy_plan_cli"],
+        ["git", "diff", "--check"],
+    ]
+    release = [
+        ["python3", "-m", "agent_office", "v1", "final-delivery", "--json"],
+        ["python3", "-m", "agent_office", "v1", "verify-release-archive", "--archive", "/opt/agent-office/agentoffice-v1.0.0-final-delivery-archive.tar.gz", "--sha256", "/opt/agent-office/agentoffice-v1.0.0-final-delivery-archive.tar.gz.sha256", "--json"],
+        ["python3", "-m", "agent_office", "v1", "verify-github-release-readback", "--dir", "/opt/agent-office/V1_0_0_GITHUB_RELEASE_API_LONGRUN_READBACK", "--json"],
+    ]
+    full = [
+        ["python3", "-m", "compileall", "agent_office", "tests"],
+        ["python3", "-m", "unittest"],
+        ["python3", "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"],
+        ["python3", "-m", "agent_office", "doctor", "--adapters"],
+        ["./scripts/verify.sh"],
+        ["./scripts/smoke-test.sh", "P6-PROFILES"],
+        ["python3", "-m", "agent_office", "run-staged", "P6-PROFILES", "--dry-run", "--reset"],
+        ["python3", "-m", "agent_office", "profiles", "--name", "lowest-cost", "--plan", "--json"],
+        ["git", "diff", "--check"],
+    ]
+    if suite == "minimal":
+        return minimal
+    if suite == "release":
+        return release
+    if suite == "full":
+        return full
+    raise AutonomyError(f"unknown validation suite: {suite}.")
+
+
+def _run_validation_command(command: list[str], index: int, validation_dir: Path, project_root: Path) -> dict[str, Any]:
+    started = time.monotonic()
+    result = subprocess.run(command, cwd=project_root, text=True, capture_output=True, check=False)
+    duration = round(time.monotonic() - started, 3)
+    stdout_path = validation_dir / f"{index:02d}-stdout.txt"
+    stderr_path = validation_dir / f"{index:02d}-stderr.txt"
+    stdout_path.write_text(result.stdout or "", encoding="utf-8")
+    stderr_path.write_text(result.stderr or "", encoding="utf-8")
+    return {
+        "command": _command_text(command),
+        "argv": command,
+        "exit_code": int(result.returncode),
+        "stdout_path": str(stdout_path),
+        "stderr_path": str(stderr_path),
+        "duration_seconds": duration,
+    }
+
+
+def _command_text(command: list[str]) -> str:
+    return " ".join(command)
+
+
+def _validation_run_id(suite: str) -> str:
+    safe_time = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
+    return f"{safe_time}-{suite}"
+
+def _now_iso() -> str:
+    return datetime.now(timezone.utc).isoformat(timespec="seconds")
+
+
+def _is_relative_to(path: Path, root: Path) -> bool:
+    try:
+        path.relative_to(root)
+        return True
+    except ValueError:
+        return False
diff --git a/agent_office/cli.py b/agent_office/cli.py
index bbf4069..a530959 100755
--- a/agent_office/cli.py
+++ b/agent_office/cli.py
@@ -167,13 +167,37 @@ from .v1_final_delivery import (
     write_final_delivery_packet,
 )
 from .v1_post_release_ops import (
+    format_github_release_handoff,
+    format_github_release_plan,
     format_github_release_readback_verify,
     format_post_v1_roadmap,
     format_release_archive_verify,
+    format_release_candidate,
+    format_release_state,
+    github_release_handoff_payload,
+    github_release_plan_payload,
     post_v1_roadmap_payload,
+    release_candidate_payload,
+    release_state_payload,
     verify_github_release_readback_payload,
     verify_release_archive_payload,
 )
+from .autonomy import (
+    AutonomyError,
+    autonomy_checkpoint_payload,
+    autonomy_init_payload,
+    autonomy_merge_packet_payload,
+    autonomy_plan_payload,
+    autonomy_report_payload,
+    autonomy_review_packet_payload,
+    autonomy_status_payload,
+    autonomy_validate_payload,
+    format_autonomy_ledger,
+    format_autonomy_merge_packet,
+    format_autonomy_plan,
+    format_autonomy_review_packet,
+    format_autonomy_validation,
+)


 PROJECT_ROOT = Path(__file__).resolve().parents[1]
@@ -1630,6 +1654,46 @@ def cmd_runtime(args: argparse.Namespace) -> int:
     return 0


+def cmd_autonomy(args: argparse.Namespace) -> int:
+    action = args.autonomy_action
+    try:
+        if action == "plan":
+            payload = autonomy_plan_payload(args.goal)
+            print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_autonomy_plan(payload))
+            return 0
+        if action == "init":
+            payload = autonomy_init_payload(args.path, args.goal, PROJECT_ROOT)
+            print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_autonomy_ledger(payload))
+            return 0
+        if action == "status":
+            payload = autonomy_status_payload(args.path, PROJECT_ROOT)
+            print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_autonomy_ledger(payload))
+            return 0
+        if action == "checkpoint":
+            payload = autonomy_checkpoint_payload(args.path, args.name, args.status, PROJECT_ROOT)
+            print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_autonomy_ledger(payload))
+            return 0
+        if action == "report":
+            payload = autonomy_report_payload(args.path, PROJECT_ROOT)
+            print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_autonomy_ledger(payload))
+            return 0
+        if action == "validate":
+            payload = autonomy_validate_payload(args.path, args.suite, PROJECT_ROOT)
+            print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_autonomy_validation(payload))
+            return 0 if payload["ok"] else 2
+        if action == "review-packet":
+            payload = autonomy_review_packet_payload(args.base, args.head, args.out, PROJECT_ROOT)
+            print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_autonomy_review_packet(payload))
+            return 0
+        if action == "merge-packet":
+            payload = autonomy_merge_packet_payload(args.source, args.target, PROJECT_ROOT)
+            print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_autonomy_merge_packet(payload))
+            return 0
+    except AutonomyError as exc:
+        raise AgentOfficeError(str(exc)) from exc
+    raise AgentOfficeError("autonomy requires plan, init, status, checkpoint, report, validate, review-packet, or merge-packet.")
+
+
 def cmd_v1(args: argparse.Namespace) -> int:
     action = args.v1_action
     if action == "final-delivery":
@@ -1660,7 +1724,23 @@ def cmd_v1(args: argparse.Namespace) -> int:
         payload = post_v1_roadmap_payload()
         print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_post_v1_roadmap(payload))
         return 0
-    raise AgentOfficeError("v1 requires final-delivery, verify-final-delivery, verify-release-archive, verify-github-release-readback, or post-v1-roadmap.")
+    if action == "release-state":
+        payload = release_state_payload()
+        print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_release_state(payload))
+        return 0
+    if action == "github-release-handoff":
+        payload = github_release_handoff_payload()
+        print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_github_release_handoff(payload))
+        return 0
+    if action == "github-release-plan":
+        payload = github_release_plan_payload()
+        print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_github_release_plan(payload))
+        return 0
+    if action == "release-candidate":
+        payload = release_candidate_payload(args.version)
+        print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else format_release_candidate(payload))
+        return 0 if payload["ok"] else 2
+    raise AgentOfficeError("v1 requires final-delivery, verify-final-delivery, verify-release-archive, verify-github-release-readback, post-v1-roadmap, release-state, github-release-handoff, github-release-plan, or release-candidate.")


 def cmd_run_demo(args: argparse.Namespace) -> int:
@@ -2180,6 +2260,48 @@ def build_parser() -> argparse.ArgumentParser:
     runtime_worker_dry_run_publish.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
     runtime_worker_dry_run_publish.set_defaults(func=cmd_runtime)

+    p = sub.add_parser("autonomy", help="Plan and operate local autonomous delivery workflows without external execution.")
+    autonomy_sub = p.add_subparsers(dest="autonomy_action", required=True)
+    autonomy_plan = autonomy_sub.add_parser("plan", help="Generate a deterministic local autonomous delivery mission plan.")
+    autonomy_plan.add_argument("--goal", required=True, help="Autonomous delivery goal to plan: release-ops, post-v1, or autonomous-delivery.")
+    autonomy_plan.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
+    autonomy_plan.set_defaults(func=cmd_autonomy)
+    autonomy_init = autonomy_sub.add_parser("init", help="Initialize a local autonomous run ledger.")
+    autonomy_init.add_argument("--goal", required=True, help="Autonomous delivery goal for the run ledger.")
+    autonomy_init.add_argument("--path", required=True, help="Project-local or temp run ledger directory.")
+    autonomy_init.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
+    autonomy_init.set_defaults(func=cmd_autonomy)
+    autonomy_status = autonomy_sub.add_parser("status", help="Read a local autonomous run ledger.")
+    autonomy_status.add_argument("--path", required=True, help="Project-local or temp run ledger directory.")
+    autonomy_status.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
+    autonomy_status.set_defaults(func=cmd_autonomy)
+    autonomy_checkpoint = autonomy_sub.add_parser("checkpoint", help="Append a checkpoint to a local autonomous run ledger.")
+    autonomy_checkpoint.add_argument("--path", required=True, help="Project-local or temp run ledger directory.")
+    autonomy_checkpoint.add_argument("--name", required=True, help="Checkpoint name.")
+    autonomy_checkpoint.add_argument("--status", required=True, choices=["pending", "running", "passed", "failed", "skipped", "blocked"], help="Checkpoint status.")
+    autonomy_checkpoint.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
+    autonomy_checkpoint.set_defaults(func=cmd_autonomy)
+    autonomy_report = autonomy_sub.add_parser("report", help="Summarize a local autonomous run ledger.")
+    autonomy_report.add_argument("--path", required=True, help="Project-local or temp run ledger directory.")
+    autonomy_report.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
+    autonomy_report.set_defaults(func=cmd_autonomy)
+    autonomy_validate = autonomy_sub.add_parser("validate", help="Run an allowlisted local validation suite and record transcripts.")
+    autonomy_validate.add_argument("--path", required=True, help="Project-local or temp run ledger directory.")
+    autonomy_validate.add_argument("--suite", required=True, help="Validation suite: minimal, release, or full.")
+    autonomy_validate.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
+    autonomy_validate.set_defaults(func=cmd_autonomy)
+    autonomy_review_packet = autonomy_sub.add_parser("review-packet", help="Generate a local Markdown review packet from a commit range.")
+    autonomy_review_packet.add_argument("--base", required=True, help="Base commit or ref for diff evidence.")
+    autonomy_review_packet.add_argument("--head", required=True, help="Head commit or ref for diff evidence.")
+    autonomy_review_packet.add_argument("--out", required=True, help="Review packet Markdown output path under project root or temp directory.")
+    autonomy_review_packet.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
+    autonomy_review_packet.set_defaults(func=cmd_autonomy)
+    autonomy_merge_packet = autonomy_sub.add_parser("merge-packet", help="Generate a local merge gate packet without merging.")
+    autonomy_merge_packet.add_argument("--source", required=True, help="Source branch or ref to merge later.")
+    autonomy_merge_packet.add_argument("--target", required=True, help="Target branch or ref for merge planning.")
+    autonomy_merge_packet.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
+    autonomy_merge_packet.set_defaults(func=cmd_autonomy)
+
     p = sub.add_parser("v1", help="Generate and verify AgentOffice v1 final delivery packets without external execution.")
     v1_sub = p.add_subparsers(dest="v1_action", required=True)
     final_delivery = v1_sub.add_parser("final-delivery", help="Generate the deterministic AgentOffice v1 final delivery packet.")
@@ -2202,6 +2324,19 @@ def build_parser() -> argparse.ArgumentParser:
     post_v1_roadmap = v1_sub.add_parser("post-v1-roadmap", help="Print the deterministic post-v1 release operations roadmap.")
     post_v1_roadmap.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
     post_v1_roadmap.set_defaults(func=cmd_v1)
+    release_state = v1_sub.add_parser("release-state", help="Print tokenless local v1 release state without network calls.")
+    release_state.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
+    release_state.set_defaults(func=cmd_v1)
+    github_handoff = v1_sub.add_parser("github-release-handoff", help="Print tokenless GitHub Release operator handoff guidance.")
+    github_handoff.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
+    github_handoff.set_defaults(func=cmd_v1)
+    github_plan = v1_sub.add_parser("github-release-plan", help="Print a dry-run GitHub Release publish plan without writes.")
+    github_plan.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
+    github_plan.set_defaults(func=cmd_v1)
+    release_candidate = v1_sub.add_parser("release-candidate", help="Print a local release candidate readiness packet without tagging or release writes.")
+    release_candidate.add_argument("--version", required=True, help="Candidate version, for example v1.1.0.")
+    release_candidate.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
+    release_candidate.set_defaults(func=cmd_v1)

     p = sub.add_parser("run-bundle", help="Build, preview, inspect, validate, list, summarize, export, or check static local run bundles without executing providers.")
     p.add_argument("bundle_action", nargs="?", choices=["preview", "inspect", "validate", "list", "status", "intake", "results", "handoff", "review", "gate", "workflow", "export-review"], help="Bundle action.")
diff --git a/agent_office/v1_post_release_ops.py b/agent_office/v1_post_release_ops.py
index c2693ea..dc404f4 100644
--- a/agent_office/v1_post_release_ops.py
+++ b/agent_office/v1_post_release_ops.py
@@ -316,6 +316,178 @@ def format_post_v1_roadmap(payload: dict[str, Any]) -> str:
     return "\n".join(lines)


+
+def release_state_payload() -> dict[str, Any]:
+    archive = Path("/opt/agent-office/agentoffice-v1.0.0-final-delivery-archive.tar.gz")
+    sha256 = Path("/opt/agent-office/agentoffice-v1.0.0-final-delivery-archive.tar.gz.sha256")
+    readback = Path("/opt/agent-office/V1_0_0_GITHUB_RELEASE_API_LONGRUN_READBACK")
+    return {
+        "schema_version": SCHEMA_VERSION,
+        "packet_type": "agentoffice_v1_release_state",
+        "release_tag": RELEASE_TAG,
+        "release_commit": RELEASE_COMMIT,
+        "mainline_branch": MAINLINE_BRANCH,
+        "archive_present": archive.exists() and archive.is_file() and not archive.is_symlink(),
+        "sha256_present": sha256.exists() and sha256.is_file() and not sha256.is_symlink(),
+        "github_release_status": "skipped_no_token",
+        "publish_state": "skipped",
+        "release_url": None,
+        "readback_dir_present": readback.exists() and readback.is_dir() and not readback.is_symlink(),
+        "github_write_performed": False,
+        "network_required": False,
+        "token_required_for_publish": True,
+        "safety": _release_ops_safety(),
+    }
+
+
+def github_release_handoff_payload() -> dict[str, Any]:
+    return {
+        "schema_version": SCHEMA_VERSION,
+        "packet_type": "agentoffice_v1_github_release_handoff",
+        "release_tag": RELEASE_TAG,
+        "release_title": RELEASE_TITLE,
+        "status": "tokenless_handoff_ready",
+        "github_write_performed": False,
+        "network_required": False,
+        "operator_steps": [
+            "Confirm v1.0.0 tag points at the recorded release commit.",
+            "Verify release archive and SHA256 sidecar locally.",
+            "Create or verify the GitHub Release only from an authenticated operator session.",
+            "Upload required assets without deleting or overwriting existing release assets unless explicitly approved.",
+            "Save readback evidence and run verify-github-release-readback.",
+        ],
+        "required_assets": list(REQUIRED_RELEASE_ASSETS),
+        "safety": _release_ops_safety(),
+    }
+
+
+def github_release_plan_payload() -> dict[str, Any]:
+    return {
+        "schema_version": SCHEMA_VERSION,
+        "packet_type": "agentoffice_v1_github_release_plan",
+        "release_tag": RELEASE_TAG,
+        "release_title": RELEASE_TITLE,
+        "plan_type": "dry_run_only",
+        "github_write_performed": False,
+        "network_required": False,
+        "preflight": [
+            "verify tag commit matches release commit",
+            "verify archive checksum and internal SHA256SUMS",
+            "verify required release notes and reports are present",
+            "confirm token scope and operator approval before any remote write",
+        ],
+        "write_steps_when_authorized": [
+            "create draft release if it does not exist",
+            "upload required assets exactly once",
+            "read back release JSON and asset list",
+            "run local readback verifier",
+        ],
+        "stop_conditions": [
+            "missing token or explicit operator approval",
+            "existing release has conflicting assets",
+            "tag commit mismatch",
+            "partial remote state",
+        ],
+        "safety": _release_ops_safety(),
+    }
+
+
+def release_candidate_payload(version: str) -> dict[str, Any]:
+    if not re.fullmatch(r"v\d+\.\d+\.\d+", version):
+        return {
+            "ok": False,
+            "schema_version": SCHEMA_VERSION,
+            "packet_type": "agentoffice_v1_release_candidate",
+            "version": version,
+            "errors": ["release_candidate_invalid_version"],
+        }
+    return {
+        "ok": True,
+        "schema_version": SCHEMA_VERSION,
+        "packet_type": "agentoffice_v1_release_candidate",
+        "version": version,
+        "base_release": RELEASE_TAG,
+        "base_commit": RELEASE_COMMIT,
+        "status": "candidate_plan_ready",
+        "github_write_performed": False,
+        "tag_created": False,
+        "network_required": False,
+        "required_validations": [
+            "python3 -m compileall agent_office tests",
+            "python3 -m unittest",
+            "python3 -m unittest discover -s tests -p 'test_*.py'",
+            "python3 -m agent_office doctor --adapters",
+            "./scripts/verify.sh",
+            "git diff --check",
+        ],
+        "required_packets": [
+            "release-state",
+            "github-release-handoff",
+            "github-release-plan",
+            "merge gate packet",
+            "review bundle",
+        ],
+        "safety": _release_ops_safety(),
+        "errors": [],
+    }
+
+
+def format_release_state(payload: dict[str, Any]) -> str:
+    return "\n".join([
+        "AGENTOFFICE_V1_RELEASE_STATE",
+        f"release_tag: {payload['release_tag']}",
+        f"release_commit: {payload['release_commit']}",
+        f"archive_present: {_bool_text(bool(payload['archive_present']))}",
+        f"sha256_present: {_bool_text(bool(payload['sha256_present']))}",
+        f"github_release_status: {payload['github_release_status']}",
+        f"publish_state: {payload['publish_state']}",
+        "github_write_performed: false",
+        "network_required: false",
+    ])
+
+
+def format_github_release_handoff(payload: dict[str, Any]) -> str:
+    lines = ["AGENTOFFICE_V1_GITHUB_RELEASE_HANDOFF", f"status: {payload['status']}", "github_write_performed: false", "operator_steps:"]
+    lines.extend(f"  - {step}" for step in payload["operator_steps"])
+    lines.append("required_assets:")
+    lines.extend(f"  - {asset}" for asset in payload["required_assets"])
+    return "\n".join(lines)
+
+
+def format_github_release_plan(payload: dict[str, Any]) -> str:
+    lines = ["AGENTOFFICE_V1_GITHUB_RELEASE_PLAN", f"plan_type: {payload['plan_type']}", "github_write_performed: false", "preflight:"]
+    lines.extend(f"  - {step}" for step in payload["preflight"])
+    lines.append("stop_conditions:")
+    lines.extend(f"  - {condition}" for condition in payload["stop_conditions"])
+    return "\n".join(lines)
+
+
+def format_release_candidate(payload: dict[str, Any]) -> str:
+    marker = "AGENTOFFICE_V1_RELEASE_CANDIDATE" if payload["ok"] else "AGENTOFFICE_V1_RELEASE_CANDIDATE_FAIL"
+    lines = [marker, f"ok: {_bool_text(bool(payload['ok']))}", f"version: {payload['version']}"]
+    if payload["ok"]:
+        lines.extend([f"base_release: {payload['base_release']}", "github_write_performed: false", "tag_created: false", "required_validations:"])
+        lines.extend(f"  - {command}" for command in payload["required_validations"])
+    else:
+        lines.append("errors:")
+        lines.extend(f"  - {error}" for error in payload["errors"])
+    return "\n".join(lines)
+
+
+def _release_ops_safety() -> dict[str, bool]:
+    return {
+        "dotenv_read": False,
+        "env_vars_printed": False,
+        "token_printed": False,
+        "github_write_performed": False,
+        "tag_created": False,
+        "tag_deleted": False,
+        "release_deleted": False,
+        "release_asset_deleted": False,
+        "network_required": False,
+        "provider_runtime_adapter_external_behavior": False,
+    }
+
 def _safe_file_path(path: str, code_prefix: str, errors: list[str]) -> Path | None:
     if not str(path).strip():
         errors.append(f"{code_prefix}_missing_path")
diff --git a/tests/test_autonomy_plan_cli.py b/tests/test_autonomy_plan_cli.py
new file mode 100644
index 0000000..ba331ee
--- /dev/null
+++ b/tests/test_autonomy_plan_cli.py
@@ -0,0 +1,357 @@
+from __future__ import annotations
+
+import io
+import json
+import subprocess
+import tempfile
+import unittest
+from contextlib import redirect_stderr, redirect_stdout
+from pathlib import Path
+from unittest.mock import patch
+
+from agent_office import cli
+
+
+def run_cli(argv: list[str], project_root: Path) -> tuple[int, str, str]:
+    stdout = io.StringIO()
+    stderr = io.StringIO()
+    with patch.object(cli, "PROJECT_ROOT", project_root), redirect_stdout(stdout), redirect_stderr(stderr):
+        code = cli.main(argv)
+    return code, stdout.getvalue(), stderr.getvalue()
+
+
+def make_git_repo(root: Path) -> tuple[str, str]:
+    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True, text=True)
+    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True, capture_output=True, text=True)
+    subprocess.run(["git", "config", "user.name", "Test User"], cwd=root, check=True, capture_output=True, text=True)
+    (root / "sample.txt").write_text("one\n", encoding="utf-8")
+    subprocess.run(["git", "add", "sample.txt"], cwd=root, check=True, capture_output=True, text=True)
+    subprocess.run(["git", "commit", "-m", "base"], cwd=root, check=True, capture_output=True, text=True)
+    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True).stdout.strip()
+    (root / "sample.txt").write_text("one\ntwo\n", encoding="utf-8")
+    (root / "extra.txt").write_text("extra\n", encoding="utf-8")
+    subprocess.run(["git", "add", "sample.txt", "extra.txt"], cwd=root, check=True, capture_output=True, text=True)
+    subprocess.run(["git", "commit", "-m", "head"], cwd=root, check=True, capture_output=True, text=True)
+    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True).stdout.strip()
+    return base, head
+
+
+class AutonomyPlanCliTests(unittest.TestCase):
+    maxDiff = None
+
+    def test_autonomy_plan_positive_json_for_all_goals(self) -> None:
+        with tempfile.TemporaryDirectory() as tmpdir:
+            root = Path(tmpdir)
+            results = {
+                goal: run_cli(["autonomy", "plan", "--goal", goal, "--json"], root)
+                for goal in ["release-ops", "post-v1", "autonomous-delivery"]
+            }
+
+        for goal, result in results.items():
+            with self.subTest(goal=goal):
+                self.assertEqual(result[0], 0, result[1] + result[2])
+                payload = json.loads(result[1])
+                self.assertEqual(payload["schema_version"], 1)
+                self.assertEqual(payload["packet_type"], "agentoffice_autonomy_mission_plan")
+                self.assertEqual(payload["goal"], goal)
+                self.assertEqual(payload["status"], "ready")
+                self.assertTrue(payload["local_only"])
+                self.assertFalse(payload["network_required"])
+                self.assertFalse(payload["provider_runtime_adapter_external_behavior"])
+                self.assertGreaterEqual(len(payload["phases"]), 1)
+                self.assertGreaterEqual(len(payload["validation_commands"]), 3)
+                self.assertIn(".env is never read", payload["safety_boundaries"])
+                self.assertIn("phase6/mainline is not merged or mutated by autonomy commands", payload["safety_boundaries"])
+                self.assertGreaterEqual(len(payload["expected_artifacts"]), 1)
+                self.assertGreaterEqual(len(payload["review_handoff"]), 1)
+                self.assertGreaterEqual(len(payload["merge_gate_handoff"]), 1)
+                self.assertNotIn("Traceback", result[1] + result[2])
+
+    def test_autonomy_plan_positive_text(self) -> None:
+        with tempfile.TemporaryDirectory() as tmpdir:
+            result = run_cli(["autonomy", "plan", "--goal", "autonomous-delivery"], Path(tmpdir))
+
+        self.assertEqual(result[0], 0, result[1] + result[2])
+        self.assertIn("AGENTOFFICE_AUTONOMY_MISSION_PLAN", result[1])
+        self.assertIn("goal: autonomous-delivery", result[1])
+        self.assertIn("phases:", result[1])
+        self.assertIn("validation_commands:", result[1])
+        self.assertIn("review_handoff:", result[1])
+        self.assertIn("merge_gate_handoff:", result[1])
+        self.assertNotIn("Traceback", result[1] + result[2])
+
+    def test_autonomy_plan_unknown_goal_is_clean_failure(self) -> None:
+        with tempfile.TemporaryDirectory() as tmpdir:
+            result = run_cli(["autonomy", "plan", "--goal", "unknown"], Path(tmpdir))
+
+        self.assertEqual(result[0], 2)
+        self.assertIn("unknown autonomy goal", result[2])
+        self.assertNotIn("Traceback", result[1] + result[2])
+
+    def test_autonomy_plan_json_is_deterministic(self) -> None:
+        with tempfile.TemporaryDirectory() as tmpdir:
+            root = Path(tmpdir)
+            first = run_cli(["autonomy", "plan", "--goal", "post-v1", "--json"], root)
+            second = run_cli(["autonomy", "plan", "--goal", "post-v1", "--json"], root)
+
+        self.assertEqual(first[0], 0, first[1] + first[2])
+        self.assertEqual(second[0], 0, second[1] + second[2])
+        self.assertEqual(first[1], second[1])
+        self.assertNotIn("Traceback", first[1] + first[2] + second[1] + second[2])
+
+
+class AutonomyLedgerCliTests(unittest.TestCase):
+    maxDiff = None
+
+    def test_autonomy_ledger_init_status_checkpoint_report_json(self) -> None:
+        with tempfile.TemporaryDirectory() as tmpdir:
+            root = Path(tmpdir)
+            run_path = root / ".ai" / "autonomy" / "runs" / "demo"
+            init = run_cli(["autonomy", "init", "--goal", "autonomous-delivery", "--path", str(run_path), "--json"], root)
+            status = run_cli(["autonomy", "status", "--path", str(run_path), "--json"], root)
+            checkpoint = run_cli(["autonomy", "checkpoint", "--path", str(run_path), "--name", "preflight", "--status", "passed", "--json"], root)
+            report = run_cli(["autonomy", "report", "--path", str(run_path), "--json"], root)
+
+        for result in [init, status, checkpoint, report]:
+            self.assertEqual(result[0], 0, result[1] + result[2])
+            self.assertNotIn("Traceback", result[1] + result[2])
+        init_payload = json.loads(init[1])
+        self.assertTrue(init_payload["ok"])
+        self.assertEqual(init_payload["action"], "init")
+        self.assertEqual(init_payload["ledger"]["goal"], "autonomous-delivery")
+        self.assertEqual(init_payload["ledger"]["status"], "running")
+        checkpoint_payload = json.loads(checkpoint[1])
+        self.assertEqual(checkpoint_payload["ledger"]["status"], "passed")
+        self.assertEqual(checkpoint_payload["checkpoint"]["name"], "preflight")
+        report_payload = json.loads(report[1])
+        self.assertEqual(report_payload["summary"]["checkpoint_count"], 1)
+        self.assertEqual(report_payload["summary"]["latest_checkpoint"]["status"], "passed")
+
+    def test_autonomy_ledger_text_output(self) -> None:
+        with tempfile.TemporaryDirectory() as tmpdir:
+            root = Path(tmpdir)
+            run_path = root / ".ai" / "autonomy" / "runs" / "demo"
+            init = run_cli(["autonomy", "init", "--goal", "post-v1", "--path", str(run_path)], root)
+
+        self.assertEqual(init[0], 0, init[1] + init[2])
+        self.assertIn("AGENTOFFICE_AUTONOMY_RUN_LEDGER", init[1])
+        self.assertIn("action: init", init[1])
+        self.assertIn("goal: post-v1", init[1])
+        self.assertNotIn("Traceback", init[1] + init[2])
+
+    def test_autonomy_ledger_rejects_path_traversal(self) -> None:
+        with tempfile.TemporaryDirectory() as tmpdir:
+            result = run_cli(["autonomy", "init", "--goal", "post-v1", "--path", "../outside", "--json"], Path(tmpdir))
+
+        self.assertEqual(result[0], 2)
+        self.assertIn("refused traversal", result[2])
+        self.assertNotIn("Traceback", result[1] + result[2])
+
+    def test_autonomy_ledger_rejects_symlink_path(self) -> None:
+        with tempfile.TemporaryDirectory() as tmpdir:
+            root = Path(tmpdir)
+            target = root / "target"
+            target.mkdir()
+            link = root / "link"
+            link.symlink_to(target, target_is_directory=True)
+            result = run_cli(["autonomy", "init", "--goal", "post-v1", "--path", str(link), "--json"], root)
+
+        self.assertEqual(result[0], 2)
+        self.assertIn("symlink refused", result[2])
+        self.assertNotIn("Traceback", result[1] + result[2])
+
+    def test_autonomy_ledger_malformed_ledger_is_clean_failure(self) -> None:
+        with tempfile.TemporaryDirectory() as tmpdir:
+            root = Path(tmpdir)
+            run_path = root / ".ai" / "autonomy" / "runs" / "demo"
+            run_path.mkdir(parents=True)
+            (run_path / "ledger.json").write_text("{bad json", encoding="utf-8")
+            result = run_cli(["autonomy", "status", "--path", str(run_path), "--json"], root)
+
+        self.assertEqual(result[0], 2)
+        self.assertIn("malformed JSON", result[2])
+        self.assertNotIn("Traceback", result[1] + result[2])
+
+
+class AutonomyValidationCliTests(unittest.TestCase):
+    maxDiff = None
+
+    def test_autonomy_validate_minimal_records_success(self) -> None:
+        with tempfile.TemporaryDirectory() as tmpdir:
+            root = Path(tmpdir)
+            run_path = root / ".ai" / "autonomy" / "runs" / "demo"
+            init = run_cli(["autonomy", "init", "--goal", "autonomous-delivery", "--path", str(run_path), "--json"], root)
+            completed = subprocess.CompletedProcess(args=["fake"], returncode=0, stdout="ok out", stderr="")
+            with patch("agent_office.autonomy.subprocess.run", return_value=completed) as run_mock:
+                result = run_cli(["autonomy", "validate", "--path", str(run_path), "--suite", "minimal", "--json"], root)
+            self.assertEqual(init[0], 0, init[1] + init[2])
+            self.assertEqual(result[0], 0, result[1] + result[2])
+            self.assertEqual(run_mock.call_count, 3)
+            payload = json.loads(result[1])
+            first = payload["validation"]["commands"][0]
+            self.assertTrue(Path(first["stdout_path"]).exists())
+            self.assertTrue(Path(first["stderr_path"]).exists())
+            self.assertEqual(Path(first["stdout_path"]).read_text(encoding="utf-8"), "ok out")
+
+        self.assertTrue(payload["ok"])
+        self.assertEqual(payload["validation"]["suite"], "minimal")
+        self.assertEqual(payload["validation"]["status"], "passed")
+        self.assertEqual(len(payload["validation"]["commands"]), 3)
+        self.assertEqual(first["exit_code"], 0)
+        self.assertEqual(payload["ledger"]["validation_records"][0]["status"], "passed")
+        self.assertNotIn("Traceback", result[1] + result[2])
+
+    def test_autonomy_validate_records_failed_command(self) -> None:
+        with tempfile.TemporaryDirectory() as tmpdir:
+            root = Path(tmpdir)
+            run_path = root / ".ai" / "autonomy" / "runs" / "demo"
+            init = run_cli(["autonomy", "init", "--goal", "autonomous-delivery", "--path", str(run_path), "--json"], root)
+            results = [
+                subprocess.CompletedProcess(args=["fake1"], returncode=0, stdout="ok", stderr=""),
+                subprocess.CompletedProcess(args=["fake2"], returncode=7, stdout="", stderr="bad"),
+                subprocess.CompletedProcess(args=["fake3"], returncode=0, stdout="ok", stderr=""),
+            ]
+            with patch("agent_office.autonomy.subprocess.run", side_effect=results):
+                result = run_cli(["autonomy", "validate", "--path", str(run_path), "--suite", "minimal", "--json"], root)
+            payload = json.loads(result[1])
+            failed_stderr = Path(payload["validation"]["commands"][1]["stderr_path"]).read_text(encoding="utf-8")
+
+        self.assertEqual(init[0], 0, init[1] + init[2])
+        self.assertEqual(result[0], 2)
+        self.assertFalse(payload["ok"])
+        self.assertEqual(payload["validation"]["status"], "failed")
+        self.assertEqual(payload["validation"]["commands"][1]["exit_code"], 7)
+        self.assertEqual(failed_stderr, "bad")
+        self.assertEqual(payload["ledger"]["status"], "failed")
+        self.assertNotIn("Traceback", result[1] + result[2])
+
+    def test_autonomy_validate_unknown_suite_is_clean_failure(self) -> None:
+        with tempfile.TemporaryDirectory() as tmpdir:
+            root = Path(tmpdir)
+            run_path = root / ".ai" / "autonomy" / "runs" / "demo"
+            init = run_cli(["autonomy", "init", "--goal", "autonomous-delivery", "--path", str(run_path), "--json"], root)
+            result = run_cli(["autonomy", "validate", "--path", str(run_path), "--suite", "unknown", "--json"], root)
+
+        self.assertEqual(init[0], 0, init[1] + init[2])
+        self.assertEqual(result[0], 2)
+        self.assertIn("unknown validation suite", result[2])
+        self.assertNotIn("Traceback", result[1] + result[2])
+
+
+class AutonomyReviewPacketCliTests(unittest.TestCase):
+    maxDiff = None
+
+    def test_autonomy_review_packet_positive_json_and_bundle(self) -> None:
+        with tempfile.TemporaryDirectory() as tmpdir:
+            root = Path(tmpdir)
+            base, head = make_git_repo(root)
+            out = root / "review-packet.md"
+            result = run_cli(["autonomy", "review-packet", "--base", base, "--head", head, "--out", str(out), "--json"], root)
+            bundle = out.read_text(encoding="utf-8")
+
+        self.assertEqual(result[0], 0, result[1] + result[2])
+        payload = json.loads(result[1])
+        self.assertTrue(payload["ok"])
+        self.assertEqual(payload["base"], base)
+        self.assertEqual(payload["head"], head)
+        self.assertEqual(payload["commit_count"], 1)
+        self.assertGreaterEqual(payload["snapshot_count"], 2)
+        self.assertIn("# AgentOffice Autonomy Review Packet", bundle)
+        self.assertIn("## Full Diff", bundle)
+        self.assertIn("sample.txt", bundle)
+        self.assertIn("extra.txt", bundle)
+        self.assertIn(".env is never read", bundle)
+        self.assertNotIn("Traceback", result[1] + result[2])
+
+    def test_autonomy_review_packet_text_output(self) -> None:
+        with tempfile.TemporaryDirectory() as tmpdir:
+            root = Path(tmpdir)
+            base, head = make_git_repo(root)
+            out = root / "review-packet.md"
+            result = run_cli(["autonomy", "review-packet", "--base", base, "--head", head, "--out", str(out)], root)
+
+        self.assertEqual(result[0], 0, result[1] + result[2])
+        self.assertIn("AGENTOFFICE_AUTONOMY_REVIEW_PACKET", result[1])
+        self.assertIn(f"base: {base}", result[1])
+        self.assertNotIn("Traceback", result[1] + result[2])
+
+    def test_autonomy_review_packet_rejects_unsafe_out(self) -> None:
+        with tempfile.TemporaryDirectory() as tmpdir:
+            root = Path(tmpdir)
+            base, head = make_git_repo(root)
+            traversal = run_cli(["autonomy", "review-packet", "--base", base, "--head", head, "--out", "../packet.md", "--json"], root)
+            target = root / "target.md"
+            target.write_text("target", encoding="utf-8")
+            link = root / "link.md"
+            link.symlink_to(target)
+            symlink = run_cli(["autonomy", "review-packet", "--base", base, "--head", head, "--out", str(link), "--json"], root)
+
+        self.assertEqual(traversal[0], 2)
+        self.assertIn("refused traversal", traversal[2])
+        self.assertEqual(symlink[0], 2)
+        self.assertIn("symlink refused", symlink[2])
+        self.assertNotIn("Traceback", traversal[1] + traversal[2] + symlink[1] + symlink[2])
+
+    def test_autonomy_review_packet_missing_ref_is_clean_failure(self) -> None:
+        with tempfile.TemporaryDirectory() as tmpdir:
+            root = Path(tmpdir)
+            _base, head = make_git_repo(root)
+            result = run_cli(["autonomy", "review-packet", "--base", "missing-ref", "--head", head, "--out", str(root / "packet.md"), "--json"], root)
+
+        self.assertEqual(result[0], 2)
+        self.assertIn("review_packet_base failed", result[2])
+        self.assertNotIn("Traceback", result[1] + result[2])
+
+
+class AutonomyMergePacketCliTests(unittest.TestCase):
+    maxDiff = None
+
+    def test_autonomy_merge_packet_positive_json_and_text(self) -> None:
+        with tempfile.TemporaryDirectory() as tmpdir:
+            root = Path(tmpdir)
+            base, head = make_git_repo(root)
+            subprocess.run(["git", "branch", "target", base], cwd=root, check=True, capture_output=True, text=True)
+            subprocess.run(["git", "branch", "source", head], cwd=root, check=True, capture_output=True, text=True)
+            json_result = run_cli(["autonomy", "merge-packet", "--source", "source", "--target", "target", "--json"], root)
+            text_result = run_cli(["autonomy", "merge-packet", "--source", "source", "--target", "target"], root)
+
+        self.assertEqual(json_result[0], 0, json_result[1] + json_result[2])
+        payload = json.loads(json_result[1])
+        self.assertTrue(payload["ok"])
+        self.assertEqual(payload["source_branch"], "source")
+        self.assertEqual(payload["target_branch"], "target")
+        self.assertEqual(payload["source_head"], head)
+        self.assertEqual(payload["target_head"], base)
+        self.assertFalse(payload["merge_performed"])
+        self.assertTrue(any("sample.txt" in item for item in payload["changed_files"]))
+        self.assertIn("git merge --no-ff --no-commit source", payload["merge_commands"])
+        self.assertEqual(text_result[0], 0, text_result[1] + text_result[2])
+        self.assertIn("AGENTOFFICE_AUTONOMY_MERGE_PACKET", text_result[1])
+        self.assertIn("merge_performed: false", text_result[1])
+        self.assertNotIn("Traceback", json_result[1] + json_result[2] + text_result[1] + text_result[2])
+
+    def test_autonomy_merge_packet_missing_source_is_clean_failure(self) -> None:
+        with tempfile.TemporaryDirectory() as tmpdir:
+            root = Path(tmpdir)
+            base, _head = make_git_repo(root)
+            subprocess.run(["git", "branch", "target", base], cwd=root, check=True, capture_output=True, text=True)
+            result = run_cli(["autonomy", "merge-packet", "--source", "missing", "--target", "target", "--json"], root)
+
+        self.assertEqual(result[0], 2)
+        self.assertIn("merge_packet_source failed", result[2])
+        self.assertNotIn("Traceback", result[1] + result[2])
+
+    def test_autonomy_merge_packet_missing_target_is_clean_failure(self) -> None:
+        with tempfile.TemporaryDirectory() as tmpdir:
+            root = Path(tmpdir)
+            _base, head = make_git_repo(root)
+            subprocess.run(["git", "branch", "source", head], cwd=root, check=True, capture_output=True, text=True)
+            result = run_cli(["autonomy", "merge-packet", "--source", "source", "--target", "missing", "--json"], root)
+
+        self.assertEqual(result[0], 2)
+        self.assertIn("merge_packet_target failed", result[2])
+        self.assertNotIn("Traceback", result[1] + result[2])
+
+
+if __name__ == "__main__":
+    unittest.main()
diff --git a/tests/test_v1_post_release_ops_cli.py b/tests/test_v1_post_release_ops_cli.py
index 57a2409..6498cd0 100644
--- a/tests/test_v1_post_release_ops_cli.py
+++ b/tests/test_v1_post_release_ops_cli.py
@@ -247,3 +247,69 @@ class V1PostReleaseOpsCliTests(unittest.TestCase):
         self.assertIn("AGENTOFFICE_POST_V1_ROADMAP", text_result[1])
         self.assertIn("v1.0.1 hotfix lane", text_result[1])
         self.assertNotIn("Traceback", first_json[1] + first_json[2] + text_result[1] + text_result[2])
+
+    def test_release_ops_v11_surfaces_are_tokenless_and_local(self) -> None:
+        with tempfile.TemporaryDirectory() as tmpdir:
+            root = Path(tmpdir)
+            commands = [
+                ["v1", "release-state", "--json"],
+                ["v1", "github-release-handoff", "--json"],
+                ["v1", "github-release-plan", "--json"],
+                ["v1", "release-candidate", "--version", "v1.1.0", "--json"],
+            ]
+            results = [run_cli(command, root) for command in commands]
+
+        for result in results:
+            self.assertEqual(result[0], 0, result[1] + result[2])
+            payload = json.loads(result[1])
+            self.assertFalse(payload.get("github_write_performed", False))
+            self.assertFalse(payload.get("network_required", False))
+            self.assertNotIn("Traceback", result[1] + result[2])
+        release_state = json.loads(results[0][1])
+        self.assertEqual(release_state["packet_type"], "agentoffice_v1_release_state")
+        self.assertEqual(release_state["publish_state"], "skipped")
+        self.assertEqual(release_state["github_release_status"], "skipped_no_token")
+        handoff = json.loads(results[1][1])
+        self.assertEqual(handoff["packet_type"], "agentoffice_v1_github_release_handoff")
+        self.assertIn("required_assets", handoff)
+        plan = json.loads(results[2][1])
+        self.assertEqual(plan["plan_type"], "dry_run_only")
+        candidate = json.loads(results[3][1])
+        self.assertTrue(candidate["ok"])
+        self.assertFalse(candidate["tag_created"])
+
+    def test_release_ops_v11_text_outputs(self) -> None:
+        with tempfile.TemporaryDirectory() as tmpdir:
+            root = Path(tmpdir)
+            results = [
+                run_cli(["v1", "release-state"], root),
+                run_cli(["v1", "github-release-handoff"], root),
+                run_cli(["v1", "github-release-plan"], root),
+                run_cli(["v1", "release-candidate", "--version", "v1.1.0"], root),
+            ]
+
+        markers = [
+            "AGENTOFFICE_V1_RELEASE_STATE",
+            "AGENTOFFICE_V1_GITHUB_RELEASE_HANDOFF",
+            "AGENTOFFICE_V1_GITHUB_RELEASE_PLAN",
+            "AGENTOFFICE_V1_RELEASE_CANDIDATE",
+        ]
+        for result, marker in zip(results, markers):
+            self.assertEqual(result[0], 0, result[1] + result[2])
+            self.assertIn(marker, result[1])
+            self.assertIn("github_write_performed: false", result[1])
+            self.assertNotIn("Traceback", result[1] + result[2])
+
+    def test_release_candidate_invalid_version_is_clean_failure(self) -> None:
+        with tempfile.TemporaryDirectory() as tmpdir:
+            root = Path(tmpdir)
+            json_result = run_cli(["v1", "release-candidate", "--version", "1.1.0", "--json"], root)
+            text_result = run_cli(["v1", "release-candidate", "--version", "1.1.0"], root)
+
+        self.assertEqual(json_result[0], 2)
+        payload = json.loads(json_result[1])
+        self.assertFalse(payload["ok"])
+        self.assertIn("release_candidate_invalid_version", payload["errors"])
+        self.assertEqual(text_result[0], 2)
+        self.assertIn("AGENTOFFICE_V1_RELEASE_CANDIDATE_FAIL", text_result[1])
+        self.assertNotIn("Traceback", json_result[1] + json_result[2] + text_result[1] + text_result[2])
```

## Known Caveats

- GitHub Release publishing is intentionally token-gated and was not performed.
- Validation transcripts are stored under `AUTONOMOUS_DELIVERY_PLATFORM_V1_VALIDATION/` and are not committed by default.
- Merge packet generation is advisory and does not merge.

## Exact Merge Gate Recommendation

Run `python3 -m agent_office autonomy merge-packet --source phase52/autonomous-delivery-platform-v1 --target phase6/mainline --json`, verify source/target heads, run full validation, then perform a reviewed no-ff merge only after explicit human authorization.
