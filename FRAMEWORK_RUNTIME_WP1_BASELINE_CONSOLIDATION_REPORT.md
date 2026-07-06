# Framework Runtime WP1 Baseline Consolidation Report

Status: complete

Branch:
- framework/runtime-wp1-baseline-consolidation

Base:
- phase6/mainline @ aecfea0a5be84389a8ba53cdd37fa6b12ad6d0df

Scope:
- Consolidate the current Framework Runtime trunk baseline.
- Clarify README status, CLI surfaces, safety boundary, report index, and next WP path.
- Pin the current CLI/help contract with focused baseline test naming.
- Do not add runtime behavior.

Current baseline:
- The Framework Runtime trunk is a deterministic local dogfood loop over workspace store, run metadata, task graph, packets, actor results, runtime events, local worker stub, review stub, judge stub, status, inspect, list, resume, replay, and evidence export.
- The runtime is local/static only in this baseline.
- The broader `runtime` command namespace remains separate from the `framework-runtime` trunk surface.

CLI surfaces indexed:
- `workspace`
- `task-graph`
- `packet`
- `actor-result`
- `framework-runtime`
- `runtime`

Report index:
- `AGENTOFFICE_FRAMEWORK_RUNTIME_TRUNK_BATCH_REPORT.md`: original trunk batch implementation report.
- `FRAMEWORK_RUNTIME_TRUNK_BATCH_REVIEW_FIX_REPORT.md`: review-fix hardening report for symlink and UTF-8 read failures.
- `FRAMEWORK_RUNTIME_WP1_BASELINE_CONSOLIDATION_REPORT.md`: this baseline consolidation report.

Changed files:
- README.md
- tests/test_framework_runtime.py
- FRAMEWORK_RUNTIME_WP1_BASELINE_CONSOLIDATION_REPORT.md

Validation:
- python3 -m compileall agent_office tests: passed
- python3 -m unittest: passed
- python3 -m unittest discover -s tests -p 'test_*.py': passed
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

Next WP:
- WP2 Job Lifecycle Core should start from this baseline and add job lifecycle behavior only through an explicit plan and verification gate.
