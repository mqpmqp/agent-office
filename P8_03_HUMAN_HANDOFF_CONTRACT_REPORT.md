# P8-03 Human Handoff Contract Report

## Branch And Baseline

- Repo path: `/opt/agent-office`
- Branch: `phase8/p8-03-scope-spec-gate`
- Starting HEAD: `5be23a25095bdc7edf8346f23448cb52236fb4a7`
- origin/phase6/mainline at start: `5be23a25095bdc7edf8346f23448cb52236fb4a7`
- Tracked working tree before implementation: clean
- Scope report read: `P8_03_SCOPE_SPEC_GATE_REPORT.md`
- Commit: assigned after this report is included in the implementation commit
- Push: pending at report write time

## Changed Files

- `agent_office/run_bundle.py`
- `tests/test_run_bundle_cli.py`
- `P8_03_HUMAN_HANDOFF_CONTRACT_REPORT.md`

`agent_office/cli.py` was inspected but did not require a code change because the existing dispatch already routes `run-bundle handoff` to JSON or text output correctly.

## Implemented Human-Readable Contract

The existing command was hardened, not replaced:

```text
python3 -m agent_office run-bundle handoff --path <bundle>
```

The deterministic text output now includes these sections in stable order:

- run identity: schema version, handoff schema version, path, run id, objective, profile, objective summary
- required files
- expected files
- file summary with status, kind, and parsed flag
- actor packet identities for codex, reviewer, and judge
- actor readiness for codex, reviewer, and judge
- result presence for codex, reviewer, and judge
- validation commands
- execution boundary
- safety flags
- reviewer guidance
- judge guidance
- external behavior flags
- final read-only and no-execution markers

The formatter also reports actor result artifact metadata when static actor result metadata exists. It does not read or execute artifact content.

## JSON Compatibility Confirmation

P8-01 JSON handoff compatibility was preserved:

```text
python3 -m agent_office run-bundle handoff --path .ai/runs/P8-HANDOFF --json
```

The JSON payload still returns `kind=static_run_bundle_handoff`, preserves the existing field order and semantics, keeps `read_only=true`, keeps `execution_enabled=false`, and keeps `provider_calls=[]`.

## Tests Added Or Updated

Focused tests were added in `tests/test_run_bundle_cli.py`:

- human-readable handoff positive contract with exact deterministic line order
- human-readable handoff idempotence/read-only snapshot check
- human-readable handoff result presence and artifact metadata without source artifact reads
- human-readable missing-bundle negative case returning exit code 2 without traceback

Existing JSON handoff tests remain in place and continue to verify the P8-01 deterministic JSON contract.

## Positive Validation Results

All required validation passed after implementation:

- `python3 -m unittest tests.test_run_bundle_cli -q`: passed, 43 tests
- `python3 -m compileall agent_office tests`: passed
- `python3 -m unittest`: passed, 231 tests
- `python3 -m unittest discover -s tests -p 'test_*.py'`: passed, 231 tests
- `python3 -m agent_office doctor --adapters`: passed; mock adapters reported ok
- `./scripts/verify.sh`: passed; mock workflow reached APPROVED
- `./scripts/smoke-test.sh P6-PROFILES`: passed; mock workflow reached APPROVED
- `python3 -m agent_office run-staged P6-PROFILES --dry-run --reset`: passed; dry-run workflow reached APPROVED
- `python3 -m agent_office profiles --name lowest-cost --plan --json`: passed; execution disabled, provider calls false, artifact writes false
- `python3 -m agent_office run-bundle handoff --path .ai/runs/P8-HANDOFF --json`: passed
- `python3 -m agent_office run-bundle handoff --path .ai/runs/P8-HANDOFF`: passed
- `git diff --check`: passed

## Negative Validation Results

Executed negative case:

```text
python3 -m agent_office run-bundle handoff --path .ai/runs/P8-HANDOFF-MISSING --json
```

Result:

- Exit code: 2
- Traceback present: no
- Error: `Run bundle path is not a directory: .ai/runs/P8-HANDOFF-MISSING`

Existing focused tests continue to cover invalid path, bad bundle, symlink path, path traversal, and non-UTF-8 required-file handoff failures as exit code 2 without traceback.

## Safety Boundary Confirmation

- `.env` was read: no
- Environment variables were printed: no
- Provider external behavior triggered: no
- Runtime external behavior triggered: no
- Adapter external behavior triggered: no; only required doctor/mock status check was run
- Real runner triggered: no
- Artifact content executed: no
- P8-01 JSON deterministic contract broken: no
- Invalid bundle/path exit-2 no-traceback convention broken: no
- Tag created: no
- Default branch changed: no
- Force push performed: no
- Unrelated files modified: no

## Implementation Status

Implementation completed for the existing human-readable `run-bundle handoff` contract. No new mode was added.

P8_03_HUMAN_HANDOFF_CONTRACT_COMPLETE
