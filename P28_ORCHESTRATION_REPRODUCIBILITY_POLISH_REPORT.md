# P28 Orchestration Reproducibility Polish Report

Marker: P28_ORCHESTRATION_REPRODUCIBILITY_POLISH_COMPLETE
Branch: phase28/orchestration-reproducibility-polish
Base: phase6/mainline @ 041b1686adcc38ab97c71053b098508ecf81e9b6
Commit: pending at report generation; final branch HEAD is authoritative after commit/push.

## Scope
Removed the wall-clock timestamp from static orchestration manifests so identical orchestration inputs generate byte-identical artifacts across fresh output directories.

## Changed files
- `agent_office/orchestration.py` - removed manifest `created_at`, `_utc_now()`, and the unused datetime import.
- `tests/test_orchestration_cli.py` - updated manifest order assertions, added byte reproducibility coverage, and added symlink output refusal coverage.
- `README.md` - documented deterministic orchestration artifacts without wall-clock timestamps.
- `P28_ORCHESTRATION_REPRODUCIBILITY_POLISH_REPORT.md` - this report.

## Behavior
- Generated artifact files are byte-identical for identical task and mode inputs.
- CLI JSON output still includes output-path-specific fields and is not the reproducibility target.
- Static provider/runtime/adapter safety behavior is unchanged.

## Validation
Validation was run on `phase28/orchestration-reproducibility-polish` before commit.

- `python3 -m compileall agent_office tests` - passed.
- `python3 -m unittest` - passed, 325 tests.
- `python3 -m unittest discover -s tests -p 'test_*.py'` - passed, 325 tests.
- `python3 -m agent_office doctor --adapters` - passed.
- `./scripts/verify.sh` - passed.
- `./scripts/smoke-test.sh P6-PROFILES` - passed.
- `python3 -m agent_office run-staged P6-PROFILES --dry-run --reset` - passed.
- `python3 -m unittest tests.test_orchestration_cli` - passed, 8 tests.
- `python3 -m agent_office orchestrate --help` - passed.
- `python3 -m agent_office orchestrate run --help` - passed.
- `python3 -m agent_office orchestrate inspect --help` - passed.
- `python3 -m agent_office orchestrate validate --help` - passed.
- `git diff --check` - passed.

## Focused smoke
The review bundle includes a focused smoke that generates orchestration output twice with the same input and compares every generated artifact file with exact byte equality.

## Safety
- `.env` read: no.
- Environment variables printed: no.
- Provider/runtime/adapter external behavior: not triggered.
- Real model/provider calls: none.
- Force push: no.
- Tag: none.
- Default branch changed: no.

## Follow-up
No known follow-up for P28. Runtime/provider-backed orchestration remains out of scope.

P28_ORCHESTRATION_REPRODUCIBILITY_POLISH_COMPLETE
