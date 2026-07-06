# Framework Runtime Trunk Batch Codex Closure Report

Status: complete

Mode:
- Codex-only acceleration
- Claude review no longer required for this step

Review-fix merge:
- source branch: framework/runtime-trunk-batch-review-fix
- source head: 4fde25a3fe572e0f4cba8b2b04b0024b3dfe6b07
- merged into: phase6/mainline
- mainline before: 508201ea3c3b1257f4ae8a118d564fd8a9ba0a6f
- mainline after merge: aecfea0a5be84389a8ba53cdd37fa6b12ad6d0df
- pushed mainline: yes

Continuation branch:
- branch: framework/runtime-trunk-batch-codex-closure
- head: 533c0e82cfacad9f6ecc8de655e5f9aaea5ca7c9

Changed files:
- README.md
- tests/test_framework_runtime.py
- FRAMEWORK_RUNTIME_TRUNK_BATCH_CODEX_CLOSURE_REPORT.md

What changed:
- Added a public CLI smoke test that initializes a workspace/run/task graph, resumes the deterministic framework runtime trunk, reads status and replay, and exports text evidence.
- Added CLI help smoke coverage for framework-runtime, resume, and evidence commands.
- Added a structured negative-path replay test for a missing run.
- Documented the shorter resume-based runtime trunk smoke path and repeated the local-only safety boundary.

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
- CLI smoke: python3 -m agent_office --help passed; python3 -m agent_office runtime --help passed; python3 -m agent_office framework-runtime --help passed; python3 -m agent_office framework-runtime resume --help passed; python3 -m agent_office framework-runtime evidence --help passed

Safety:
- .env not read
- env vars not printed
- provider/runtime/adapter external behavior not triggered
- no tag
- no default branch change
- historical untracked artifacts left untouched

Notes:
- No new runtime abstraction was added because the framework-runtime CLI already exposed the deterministic trunk loop.
- The continuation closed the most obvious user-facing gap with README usage and focused CLI smoke coverage.
