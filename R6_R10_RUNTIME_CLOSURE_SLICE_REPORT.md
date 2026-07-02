# R6-R10 Runtime Closure Slice Report

## Baseline

- Trusted target baseline: `phase6/mainline == origin/phase6/mainline == 2fd49805eb2d71b0d954cc11a4fb14dc30887a46`
- Preflight gate used: `git status --short --untracked-files=no`
- Existing untracked artifacts were preserved and not staged.

## Branch

- Source branch: `phase40/r6-r10-runtime-closure-slice`
- Branch start: `2fd49805eb2d71b0d954cc11a4fb14dc30887a46`
- Feature commit: recorded in final delivery readback after commit creation.

## Changed Files

- `agent_office/runtime_foundation.py`
- `agent_office/cli.py`
- `tests/test_runtime_foundation_cli.py`
- `README.md`
- `R6_R10_RUNTIME_CLOSURE_SLICE_REPORT.md`

## Implemented Scope

R6 Run lifecycle packet:

- Added `runtime packet` for a deterministic lifecycle packet with workspace status, task counts, task graph readback, memory/event summaries, file statuses, and safety boundaries.

R7 Workspace evidence:

- Added `runtime evidence --out ... --format {json,text}` for local workspace evidence bundles.
- Evidence includes lifecycle packet, replay-readback contract, file digests, and safety boundaries.
- Output paths must remain project-local and refuse `.env`, traversal, symlink outputs, symlink parents, directories, and missing parents.

R8 Replay-readback contract:

- Added `runtime replay` to compare manifest status, graph order/status, memory JSONL, and event JSONL.
- Tampered graph/readback mismatches return stable JSON/text and a non-zero exit without traceback.

R9 Closure packet:

- Added `runtime close` to produce a local closure packet from packet + replay evidence.
- Completed workspaces return `closure_packet_valid=true`, `closure_ready=true`, and `readiness=ready`.
- Invalid replay or non-terminal workspaces block closure with explicit `blocking_reasons`.

R10 Reviewable contract stability:

- Added focused tests for packet/evidence/replay/close JSON contracts, text output, output safety errors, and tamper detection.
- README documents only the minimal command surface.

## Explicitly Not Implemented

- No provider calls.
- No model calls.
- No external adapter calls.
- No Claude/Codex/OpenAI/Gemini/browser/shell worker integration.
- No daemon.
- No concurrent worker pool.
- No queue service.
- No database.
- No vector store.
- No `.env` reads.
- No environment variable printing.
- No default branch mutation outside `review codex-deliver`.
- No force push.
- No tag creation.

## CLI Examples

```bash
python3 -m agent_office runtime packet --workspace .ai/workspaces/demo --json
python3 -m agent_office runtime replay --workspace .ai/workspaces/demo --json
python3 -m agent_office runtime evidence --workspace .ai/workspaces/demo --out .ai/workspaces/demo/evidence.json --format json --json
python3 -m agent_office runtime evidence --workspace .ai/workspaces/demo --out .ai/workspaces/demo/evidence.md --format text --json
python3 -m agent_office runtime close --workspace .ai/workspaces/demo --out .ai/workspaces/demo/closure_packet.json --json
```

## Test Results

Passed:

- `python3 -m compileall agent_office tests`
- `python3 -m unittest tests.test_runtime_foundation_cli` (`15` tests)
- `python3 -m unittest` (`370` tests)
- `python3 -m unittest discover -s tests -p 'test_*.py'` (`370` tests)
- `python3 -m agent_office doctor --adapters`
- `./scripts/verify.sh`
- `./scripts/smoke-test.sh P6-PROFILES`
- `python3 -m agent_office run-staged P6-PROFILES --dry-run --reset`
- `python3 -m agent_office review codex-deliver --help`
- `python3 -m agent_office review reviewed-delivery --help`
- `python3 -m agent_office runtime --help`
- `python3 -m agent_office runtime init --help`
- `python3 -m agent_office runtime plan --help`
- `python3 -m agent_office runtime run --help`
- `python3 -m agent_office runtime status --help`
- `python3 -m agent_office runtime packet --help`
- `python3 -m agent_office runtime replay --help`
- `python3 -m agent_office runtime evidence --help`
- `python3 -m agent_office runtime close --help`
- `git diff --check`

## Smoke Results

Smoke workspace: `.ai/workspaces/R6-R10-SMOKE`

Passed sequence:

```bash
python3 -m agent_office runtime init --workspace .ai/workspaces/R6-R10-SMOKE --goal "R6-R10 runtime closure smoke" --json
python3 -m agent_office runtime plan --workspace .ai/workspaces/R6-R10-SMOKE --task "inspect:Inspect workspace" --task "implement:Implement deterministic local result" --task "review:Review deterministic result" --depends implement:inspect --depends review:implement --json
python3 -m agent_office runtime run --workspace .ai/workspaces/R6-R10-SMOKE --adapter local-static --execute-local --json
python3 -m agent_office runtime packet --workspace .ai/workspaces/R6-R10-SMOKE --json
python3 -m agent_office runtime replay --workspace .ai/workspaces/R6-R10-SMOKE --json
python3 -m agent_office runtime evidence --workspace .ai/workspaces/R6-R10-SMOKE --out .ai/workspaces/R6-R10-SMOKE/evidence.json --format json --json
python3 -m agent_office runtime evidence --workspace .ai/workspaces/R6-R10-SMOKE --out .ai/workspaces/R6-R10-SMOKE/evidence.md --format text --json
python3 -m agent_office runtime close --workspace .ai/workspaces/R6-R10-SMOKE --out .ai/workspaces/R6-R10-SMOKE/closure_packet.json --json
python3 -m agent_office runtime status --workspace .ai/workspaces/R6-R10-SMOKE --json
```

Final smoke status:

- workspace_status: `completed`
- completed_task_ids: `inspect`, `implement`, `review`
- replay_valid: `true`
- closure_packet_valid: `true`
- closure_ready: `true`
- readiness: `ready`
- evidence JSON/text and closure packet were written and read back.

The smoke workspace was removed after validation to avoid adding new untracked artifact noise.

## Safety Boundaries

- Runtime evidence and closure output paths are project-local only.
- `.env` paths are refused.
- Path traversal is refused.
- Symlink output files and symlink output parents are refused.
- Runtime readback uses local manifest/task graph/memory/events only.
- Provider/model/runtime external adapter behavior remains not triggered.

## Delivery Method

- Feature branch is pushed to `origin/phase40/r6-r10-runtime-closure-slice`.
- Safe-mode delivery must run through `python3 -m agent_office review codex-deliver` with merge/push disabled.
- Authorized delivery must run through `python3 -m agent_office review codex-deliver --merge-authorized --push-authorized`.
- No reviewed-delivery path is used unless a real saved review output, attestation, and merge packet exist.

## Final Mainline Sync Status

- Pending until `review codex-deliver` safe-mode and authorized delivery complete.
