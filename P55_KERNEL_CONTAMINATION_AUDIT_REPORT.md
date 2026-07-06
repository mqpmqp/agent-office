# P55 Kernel Contamination Audit Report

## Scope

- repo: `/opt/agent-office`
- base branch: `phase6/mainline`
- base head: `f70604b0b31231cff967f02f8293fd186b8f97ee`
- candidate branch: `phase55-kernel/runtime-semantic-collapse`
- original candidate head: `43a8e01cbaca28738d8605ce84a69e3cc384bd6d`
- audit mode: tracked code, tests, README, and reports only

## Diff summary

Original candidate changed 11 tracked files:

- `P55_KERNEL_RUNTIME_SEMANTIC_COLLAPSE_REPORT.md`
- `README.md`
- `agent_office/runtime_foundation.py`
- `agent_office/runtime_kernel/__init__.py`
- `agent_office/runtime_kernel/event_log.py`
- `agent_office/runtime_kernel/executor.py`
- `agent_office/runtime_kernel/kernel.py`
- `agent_office/runtime_kernel/scheduler.py`
- `agent_office/runtime_kernel/validator.py`
- `tests/test_local_multi_agent_runtime_cli.py`
- `tests/test_runtime_kernel.py`

Diff stat at audit start:

```text
P55_KERNEL_RUNTIME_SEMANTIC_COLLAPSE_REPORT.md | 100 +++++++++++++++++++++++
README.md                                      |  12 +--
agent_office/runtime_foundation.py             |  92 ++++++++++++++++-----
agent_office/runtime_kernel/__init__.py        |  18 +++++
agent_office/runtime_kernel/event_log.py       |  83 +++++++++++++++++++
agent_office/runtime_kernel/executor.py        |  26 ++++++
agent_office/runtime_kernel/kernel.py          | 106 +++++++++++++++++++++++++
agent_office/runtime_kernel/scheduler.py       |  77 ++++++++++++++++++
agent_office/runtime_kernel/validator.py       |  52 ++++++++++++
tests/test_local_multi_agent_runtime_cli.py    |  64 ++++++---------
tests/test_runtime_kernel.py                   | 102 ++++++++++++++++++++++++
11 files changed, 665 insertions(+), 67 deletions(-)
```

## Audit findings by severity

### Workspace noise

- The VPS working tree still contains historical untracked artifacts outside the candidate diff. The audit used `git status --short --untracked-files=no` as requested and did not delete `.ai/`, reports, bundles, archives, or historical artifacts.
- Validation commands refreshed ignored/local `.ai` task runtime state. No tracked artifact cleanup was performed.

### Tracked code blocker

- `git diff --check phase6/mainline..HEAD` failed on the original candidate because `tests/test_runtime_kernel.py` contained a trailing CR/whitespace line at the module entrypoint. This would create merge-gate noise and fail the required whitespace check.

### Tracked code major

- `agent_office/runtime_kernel/validator.py` used `event[ type]` in the unsupported-event-type error message. Invalid event types would raise an unstable raw key error instead of the expected deterministic `EventLogError("runtime_event_type_invalid", ...)`. This violates the validator gate requirement to not hide or destabilize failures.

### Tracked code minor

- No Binance futures bot or trading-bot content was found in the P55 changed code.
- No new provider/model/network subprocess path was added by the runtime kernel files.
- `runtime doctor --help` is not implemented as a runtime subcommand; the validation command allows this with `|| true`, so this is not a blocker.

### Docs/report mismatch

- `P55_KERNEL_RUNTIME_SEMANTIC_COLLAPSE_REPORT.md` includes an accidental-heredoc note from the implementation run. It is noisy but factual and not a merge blocker.
- README P55 runtime section matches the implemented event-sourced semantics at the level checked in this audit.

### No-action nits

- The new kernel package uses single-quoted strings while nearby older code often uses double quotes. This is style noise only and not worth a broad rewrite.
- Planner reruns are append-only and can add repeated static plan events; the reducer remains deterministic and the limitation is already documented.

## Review-fix decision

Blocker/major count was greater than zero, so a minimal review-fix delta was applied:

- normalized `tests/test_runtime_kernel.py` to remove BOM/CR trailing whitespace
- fixed `validator.py` unsupported event type message to use `event["type"]`
- added a focused test proving invalid event types raise stable `EventLogError` with `runtime_event_type_invalid`

No large refactor, artifact cleanup, merge, tag, or default-branch change was performed.

## Validation results

- `python3 -m compileall agent_office tests` -> passed
- `python3 -m unittest` -> passed, 471 tests in 221.706s
- `python3 -m unittest discover -s tests -p 'test_*.py'` -> passed, 471 tests in 223.920s
- `python3 -m agent_office doctor --adapters` -> passed, all mock adapters ok
- `./scripts/verify.sh` -> passed, `verify ok`
- `./scripts/smoke-test.sh P6-PROFILES` -> passed, `smoke test ok: P6-PROFILES`
- `python3 -m agent_office run-staged P6-PROFILES --dry-run --reset` -> passed, final state `APPROVED`
- `python3 -m agent_office runtime --help` -> passed, exit 0
- `python3 -m agent_office runtime doctor --help || true` -> command returned exit 2 because `runtime doctor` is not a registered subcommand; accepted by required `|| true`
- `git diff --check` -> passed

## Safety confirmation

- no `.env` read
- no environment values printed
- no provider/model/runtime adapter external behavior triggered
- no historical artifacts deleted
- `.ai/` not deleted
- no `git clean`
- no force-push
- no tag
- no merge to mainline
- no Binance futures bot or trading-bot content introduced

## Final decision

Minimal review-fix is required and complete. Candidate branch should be pushed after commit.

Marker after push: `P55_KERNEL_CONTAMINATION_REVIEW_FIX_COMPLETE_BRANCH_PUSHED`