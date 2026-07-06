# Framework Runtime Trunk Batch Review Fix Report

Status: complete

Branch:
- framework/runtime-trunk-batch-review-fix

Base HEAD:
- 5ed2dda320ca3349eacff11ca2a9dcc5cf28ac56

Changed files:
- agent_office/framework_runtime.py
- agent_office/runtime_events.py
- agent_office/workspace_store.py
- tests/test_framework_runtime.py

What changed:
- Hardened framework runtime JSON directory reads to reject symlinked children, non-file children, and resolved paths outside the runtime directory before reading payloads.
- Converted non-UTF-8 JSON state and runtime event logs into structured runtime/store errors instead of uncaught tracebacks.
- Added regression coverage for symlinked JSON child rejection and non-UTF-8 structured error handling.

Validation:
- python3 -m compileall agent_office tests: passed
- python3 -m unittest tests.test_framework_runtime: passed
- python3 -m unittest: passed
- python3 -m unittest discover -s tests -p 'test_*.py': passed
- python3 -m agent_office doctor --adapters: passed
- ./scripts/verify.sh: passed
- ./scripts/smoke-test.sh P6-PROFILES: passed
- python3 -m agent_office run-staged P6-PROFILES --dry-run --reset: passed
- git diff --check: passed

Safety:
- .env not read
- env vars not printed
- provider/runtime/adapter external behavior not triggered
- no merge
- no tag
- no default branch change
