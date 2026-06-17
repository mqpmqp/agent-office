# Completed Work

- Added a real Grok adapter for the `redteam` stage only.
- Wired `redteam --real --adapter grok --timeout <seconds>`.
- Added Grok to adapter registry and adapter doctor diagnostics.
- Kept mock workflow, Gemini context, Codex implement, summarize, and final behavior unchanged.
- Kept Claude real final judge unimplemented.

# Files Changed

- `.env.example`
- `README.md`
- `agent_office/cli.py`
- `agent_office/adapters/grok.py`
- `agent_office/adapters/registry.py`
- `agent_office/doctor.py`
- `docs/adapter-doctor.md`
- `docs/agent-roles.md`
- `docs/architecture.md`
- `docs/task-protocol.md`
- `docs/reports/grok-adapter-report.md`

# Commands Run

```bash
rm -rf .ai/tasks/DEMO-GROK-GUARD
python3 -m agent_office new DEMO-GROK-GUARD
python3 -m agent_office context DEMO-GROK-GUARD --mock
python3 -m agent_office implement DEMO-GROK-GUARD --mock
python3 -m agent_office redteam DEMO-GROK-GUARD --real --adapter grok
python3 -m compileall -q agent_office
python3 -m agent_office adapters
python3 -m agent_office doctor
python3 -m agent_office doctor --adapter grok
python3 -m agent_office doctor --json
python3 -m agent_office run-demo DEMO-GROK-ADAPTER --mock --reset
bash scripts/smoke-test.sh DEMO-GROK-SMOKE
bash scripts/verify.sh
```

# Test Results

- Compile: PASS
- `adapters`: PASS
- `doctor`: PASS
- `doctor --adapter grok`: PASS
- `doctor --json`: PASS
- Mock demo: PASS
- Smoke test: PASS, printed `smoke test ok: DEMO-GROK-SMOKE`
- Verify: PASS, printed `verify ok`

# Guard Test Result

PASS. With `AGENTOFFICE_GROK_CMD` unset, real Grok redteam failed clearly:

```text
Grok real adapter is not configured. Set AGENTOFFICE_GROK_CMD to an executable name/path or use --mock.
```

The guard task remained in `IMPLEMENTED` and no fake `grok-review.md` was created.

# Git Commit

Commit message: `add Grok redteam adapter phase 3`

# Git Tag

Expected tag: `phase3-grok-adapter`

# Remaining Risks

- Real Grok command behavior depends on the operator-provided executable.
- The adapter requires real Grok to write `grok-review.md`; it does not infer success from stdout.
- Claude final judge remains mock-only.
- Concurrency/task locking remains future work.

# How To Enable Real Grok Adapter

```bash
cd /opt/agent-office
export AGENTOFFICE_AGENT_MODE=real
export AGENTOFFICE_GROK_CMD=grok
export AGENTOFFICE_GROK_TIMEOUT_SECONDS=120
export AGENTOFFICE_GROK_MAX_OUTPUT_CHARS=12000
python3 -m agent_office redteam <TASK_ID> --real --adapter grok --timeout 120
```

`AGENTOFFICE_GROK_CMD` must be a single executable name or path with no shell syntax or inline arguments.

# Rollback To Mock Mode

```bash
cd /opt/agent-office
unset AGENTOFFICE_GROK_CMD
export AGENTOFFICE_AGENT_MODE=mock
python3 -m agent_office redteam <TASK_ID> --mock
bash scripts/verify.sh
```

# Next Phase Recommendation

Implement Claude final judge adapter next. It should remain restricted to `final-for-claude.md` and should be added to doctor before real execution is enabled.
