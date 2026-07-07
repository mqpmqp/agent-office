# Framework Runtime WP8 Scheduler Kernel V1 Review Fix Report

Marker: FRAMEWORK_RUNTIME_WP8_SCHEDULER_KERNEL_V1_REVIEW_FIX_COMPLETE

Source review marker:
- FRAMEWORK_RUNTIME_WP8_SCHEDULER_KERNEL_V1_ARTIFACT_REVIEW_COMPLETE

Branch:
- source: framework/runtime-wp8-scheduler-kernel-v1
- review-fix: framework/runtime-wp8-scheduler-kernel-v1-review-fix

Fixes:
- B1: Scheduler state initialization now uses load_runtime_graph, so missing task graphs are wrapped as FrameworkRuntimeError and JSON CLI mode returns a stable error envelope instead of a traceback.
- M1: refresh_scheduler_counts is idempotent for failed terminal pools and status-only refreshes do not create phantom transitions for non-persisted scheduler state.
- M2: scheduler retry now only accepts failed scheduler tasks; non-failed task retries return FrameworkRuntimeError without mutating state, and exhausted failed retries are idempotent.
- M3: dependency eligibility refresh only clears dependency blocks; task_status/task_terminal blocks are preserved or restored as blocked across run/resume/result-intake refresh paths.
- M4: scheduler job ids are goal-namespaced as sched-<goal_id>-<task_id>[-rN], with metadata collision validation before reusing an existing job.

Changed files:
- agent_office/framework_runtime.py
- tests/test_framework_runtime.py
- FRAMEWORK_RUNTIME_WP8_SCHEDULER_KERNEL_V1_REVIEW_FIX_REPORT.md

Validation:
- python3 -m compileall agent_office tests: passed
- python3 -m unittest: passed (551 tests)
- python3 -m unittest discover -s tests -p 'test_*.py': passed (551 tests)
- python3 -m unittest tests.test_framework_runtime: passed (38 tests)
- python3 -m agent_office doctor --adapters: passed
- ./scripts/verify.sh: passed
- ./scripts/smoke-test.sh P6-PROFILES: passed
- python3 -m agent_office run-staged P6-PROFILES --dry-run --reset: passed
- CLI help smoke: passed
- git diff --check: passed

Safety:
- .env not read
- env vars not printed
- no real provider/runtime/adapter external behavior
- no daemon/background loop
- no merge/tag/default-branch change

Notes:
- M4 was fixed with full scheduler job-id namespace; no single-run cross-goal silent reuse fast-follow remains for this finding.
