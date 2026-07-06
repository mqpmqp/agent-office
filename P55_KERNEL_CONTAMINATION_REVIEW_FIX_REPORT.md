# P55 Kernel Contamination Review-Fix Report

## Summary

Applied a minimal review-fix delta for the P55 runtime kernel candidate branch.

## Fixed issues

1. `tests/test_runtime_kernel.py` contained BOM/CR trailing whitespace that failed `git diff --check phase6/mainline..HEAD` on the original candidate.
2. `agent_office/runtime_kernel/validator.py` formatted unsupported event type errors with `event[ type]`, producing an unstable raw key error instead of deterministic `EventLogError` behavior.

## Files changed by review-fix

- `agent_office/runtime_kernel/validator.py`
- `tests/test_runtime_kernel.py`
- `P55_KERNEL_CONTAMINATION_AUDIT_REPORT.md`
- `P55_KERNEL_CONTAMINATION_REVIEW_FIX_REPORT.md`

## Tests added or updated

- Added `test_invalid_event_type_raises_stable_error` to `tests/test_runtime_kernel.py`.

## Validation

- `python3 -m compileall agent_office tests` -> passed
- `python3 -m unittest` -> passed, 471 tests in 221.706s
- `python3 -m unittest discover -s tests -p 'test_*.py'` -> passed, 471 tests in 223.920s
- `python3 -m agent_office doctor --adapters` -> passed
- `./scripts/verify.sh` -> passed
- `./scripts/smoke-test.sh P6-PROFILES` -> passed
- `python3 -m agent_office run-staged P6-PROFILES --dry-run --reset` -> passed
- `python3 -m agent_office runtime --help` -> passed
- `python3 -m agent_office runtime doctor --help || true` -> accepted fallback; subcommand absent
- `git diff --check` -> passed

## Safety

No merge, tag, default-branch change, artifact cleanup, `.ai/` deletion, provider/model/runtime adapter external behavior, `.env` read, or unrelated code change was performed.