# P27 Orchestration Review Fix Report

Marker: P27_REVIEW_FIX_COMPLETE
Branch: phase27/p27-orchestration-review-fix
Base branch: phase27/fugu-like-orchestration-core
Original P27 commit: 8afbe35022b1d862b9b517309c570d7c25ab9544
Commit: pending at report generation; final branch HEAD is authoritative after commit/push.

## Finding
Static self-review found that `orchestrate run` could raise a traceback when the requested output path had a parent component that was an existing file rather than a directory.

Reproducer before the fix:

```bash
python3 -m agent_office orchestrate run --task Review-output-failure --mode static --out /tmp/agentoffice-p27-invalid-parent/child --json
```

Observed failure before the fix: `NotADirectoryError` traceback from `Path.mkdir(parents=True, exist_ok=True)`.

## Fix
- Wrapped output directory creation in `orchestrate_run_payload` with `OSError` handling.
- Returned the existing structured JSON error payload with `valid: false` and `output_directory_create_failed`.
- Added a focused CLI regression test proving the path returns exit code 2 without a traceback.

## Safety
- `.env` read: no.
- Environment variables printed: no.
- Provider/runtime/adapter external behavior: not triggered by the fix.
- Merge/push/tag behavior: no merge or tag performed; branch push is expected after validation.

## Validation
Validation was rerun on `phase27/p27-orchestration-review-fix`.

- `python3 -m compileall agent_office tests` - passed.
- `python3 -m unittest` - passed, 323 tests.
- `python3 -m unittest discover -s tests -p 'test_*.py'` - passed, 323 tests.
- `python3 -m agent_office doctor --adapters` - passed, mock adapters ok.
- `./scripts/verify.sh` - passed.
- `./scripts/smoke-test.sh P6-PROFILES` - passed.
- `python3 -m agent_office run-staged P6-PROFILES --dry-run --reset` - passed.
- `git diff --check` - passed.
- `python3 -m unittest tests.test_orchestration_cli` - passed, 6 tests.
- `python3 -m agent_office orchestrate --help` - passed.
- `python3 -m agent_office orchestrate run --help` - passed.
- `python3 -m agent_office orchestrate inspect --help` - passed.
- `python3 -m agent_office orchestrate validate --help` - passed.

P27_REVIEW_FIX_COMPLETE
