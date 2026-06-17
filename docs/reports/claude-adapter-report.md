# Completed Work

- Added a real Claude adapter for the `final` stage only.
- Wired `final --real --adapter claude --timeout <seconds>`.
- Added Claude to adapter registry and adapter doctor diagnostics.
- Enforced that real Claude reads only `final-for-claude.md`.
- Added input/output character limits for Claude token control.
- Kept mock workflow, Gemini context, Codex implement, and Grok redteam behavior unchanged.

# Files Changed

- `.env.example`
- `README.md`
- `agent_office/cli.py`
- `agent_office/adapters/claude.py`
- `agent_office/adapters/registry.py`
- `agent_office/doctor.py`
- `docs/adapter-doctor.md`
- `docs/agent-roles.md`
- `docs/architecture.md`
- `docs/task-protocol.md`
- `docs/reports/claude-adapter-report.md`

# Commands Run

```bash
rm -rf .ai/tasks/DEMO-CLAUDE-GUARD
python3 -m agent_office new DEMO-CLAUDE-GUARD
python3 -m agent_office context DEMO-CLAUDE-GUARD --mock
python3 -m agent_office implement DEMO-CLAUDE-GUARD --mock
python3 -m agent_office redteam DEMO-CLAUDE-GUARD --mock
python3 -m agent_office summarize DEMO-CLAUDE-GUARD --mock
python3 -m agent_office final DEMO-CLAUDE-GUARD --real --adapter claude
python3 -m compileall -q agent_office
python3 -m agent_office adapters
python3 -m agent_office doctor
python3 -m agent_office doctor --adapter claude
python3 -m agent_office doctor --json
python3 -m agent_office run-demo DEMO-CLAUDE-ADAPTER --mock --reset
bash scripts/smoke-test.sh DEMO-CLAUDE-SMOKE
bash scripts/verify.sh
```

# Test Results

- Compile: PASS
- `adapters`: PASS
- `doctor`: PASS
- `doctor --adapter claude`: PASS
- `doctor --json`: PASS
- Mock demo: PASS
- Smoke test: PASS
- Verify: PASS

# Guard Test Result

PASS. With `AGENTOFFICE_CLAUDE_CMD` unset, real Claude final failed clearly:

```text
Claude real adapter is not configured. Set AGENTOFFICE_CLAUDE_CMD to an executable name/path or use --mock.
```

The guard task remained in `SUMMARIZED` and no fake `claude-decision.md` was created.

# Git Commit

Commit message: `add Claude final judge adapter phase 4`

# Git Tag

Expected tag: `phase4-claude-final-adapter`

# Remaining Risks

- Real Claude command behavior depends on the operator-provided executable.
- The adapter requires real Claude to write `claude-decision.md`; it does not infer success from stdout.
- Full end-to-end real-provider dry runs are still future work.
- Concurrency/task locking remains future work.

# How To Enable Real Claude Adapter

```bash
cd /opt/agent-office
export AGENTOFFICE_AGENT_MODE=real
export AGENTOFFICE_CLAUDE_CMD=claude
export AGENTOFFICE_CLAUDE_TIMEOUT_SECONDS=120
export AGENTOFFICE_CLAUDE_MAX_INPUT_CHARS=12000
export AGENTOFFICE_CLAUDE_MAX_OUTPUT_CHARS=8000
python3 -m agent_office final <TASK_ID> --real --adapter claude --timeout 120
```

`AGENTOFFICE_CLAUDE_CMD` must be a single executable name or path with no shell syntax or inline arguments.

# Token Saving Guarantees

- Claude reads only `.ai/tasks/<TASK_ID>/final-for-claude.md`.
- Claude does not read the repository, `.env`, logs, `patch.diff`, `codex-report.md`, `grok-review.md`, or `gemini-context.md`.
- Input length is capped by `AGENTOFFICE_CLAUDE_MAX_INPUT_CHARS`.
- Oversized input fails and asks for stronger summarize-stage compression.
- Claude does not modify code or generate patches.

# Rollback To Mock Mode

```bash
cd /opt/agent-office
unset AGENTOFFICE_CLAUDE_CMD
export AGENTOFFICE_AGENT_MODE=mock
python3 -m agent_office final <TASK_ID> --mock
bash scripts/verify.sh
```

# Next Phase Recommendation

Run a controlled full dry run with explicit real adapter commands, one provider at a time, while keeping mock mode as the default fallback.
