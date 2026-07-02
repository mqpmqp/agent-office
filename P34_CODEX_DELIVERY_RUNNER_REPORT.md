# P34 Codex Delivery Runner Report

Marker: P34_CODEX_DELIVERY_RUNNER_COMPLETE

Summary:
- Added one-click Codex-only delivery runner contract.
- Default mode is safe/non-destructive.
- Merge/push requires explicit authorization.
- Claude review/attestation/merge-packet remains optional/legacy/lower-level, not mandatory.
- Runner standardizes self-review, validation, readiness, and report fields.

Runner interface:
- python3 -m agent_office review codex-deliver --source <branch> --target <branch> --expected-source-head <sha> --expected-target-head <sha> --out <report> [--phase <id>] [--run-id <id>] [--merge-authorized] [--push-authorized] [--json]

Changed files:
M	README.md
M	agent_office/cli.py
M	agent_office/review_lifecycle.py
M	tests/test_review_lifecycle_cli.py
A	P34_CODEX_DELIVERY_RUNNER_REPORT.md

Validation:
- compileall: passed
- tests.test_review_lifecycle_cli: passed
- full unittest: passed
- unittest discovery: passed
- doctor --adapters: passed
- verify.sh: passed
- smoke-test P6-PROFILES: passed
- run-staged P6-PROFILES dry-run reset: passed
- review help smokes: passed
- codex delivery runner smoke: passed
- git diff --check: passed
- git diff --name-status/stat self-review: passed

Safety:
- .env not read
- env vars not printed
- provider/model/runtime/adapter external behavior not triggered
- no force push
- no tag
- no Claude output generated
- no Claude attestation generated
- no Claude merge packet generated
