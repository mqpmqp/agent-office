# Framework Runtime WP2 Job Lifecycle Core Report

Status: complete

Branch:
- framework/runtime-wp2-job-lifecycle-core

Base:
- phase6/mainline @ 9cc72a90a0011030a7d614a13fc1c770c96b7b9b

Scope:
- Add local/static framework runtime job persistence.
- Add `framework-runtime job create/list/show/cancel/fail`.
- Preserve existing `framework-runtime resume` and `framework-runtime evidence` behavior.
- Keep implementation local-only: no database, daemon, scheduler, network, provider, Codex, or Claude worker connection.

State path:
- `.ai/workspaces/<workspace-id>/runs/<run-id>/jobs/<job-id>.json`
- This follows the existing run-local framework runtime layout used by packets, results, reviews, judges, and evidence.

Job schema:
- `job_id`
- `status`
- `created_at`
- `updated_at`
- `objective`
- `metadata`
- `evidence_refs`
- `transition_log`

Status and transition model:
- create writes `pending`.
- cancel is allowed from `pending` or `running` and writes `cancelled`.
- fail is allowed from `pending` or `running` and writes `failed`.
- terminal statuses are `succeeded`, `failed`, and `cancelled`.
- terminal jobs cannot be cancelled or failed again.
- invalid job transitions return non-zero CLI behavior; with `--json`, they return `agentoffice.framework_runtime_job_error`.

Evidence binding:
- `job create --evidence-ref <path>` records local/static evidence references.
- `job show` and `job list` expose `evidence_refs`.
- No artifact storage or provider integration was added.

Changed files:
- agent_office/framework_runtime.py
- agent_office/cli.py
- tests/test_framework_runtime.py
- README.md
- FRAMEWORK_RUNTIME_WP2_JOB_LIFECYCLE_CORE_REPORT.md

Validation:
- python3 -m compileall agent_office tests: passed
- python3 -m unittest: passed
- python3 -m unittest discover -s tests -p 'test_*.py': passed
- python3 -m unittest tests.test_framework_runtime: passed
- python3 -m agent_office doctor --adapters: passed
- ./scripts/verify.sh: passed
- ./scripts/smoke-test.sh P6-PROFILES: passed
- python3 -m agent_office run-staged P6-PROFILES --dry-run --reset: passed
- git diff --check: passed
- CLI smoke: passed

Safety:
- .env not read
- env vars not printed
- provider/runtime/adapter external behavior not triggered
- real Codex/Claude/provider workers not connected
- no default branch change
- no tag
- historical untracked artifacts left untouched
