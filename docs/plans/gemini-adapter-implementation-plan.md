# Gemini Adapter Implementation Plan

## Phase 2 Scope

Phase 2 adds a real Gemini adapter for the `context` stage only.

Non-goals:

- No real Grok Build adapter.
- No real Claude Code adapter.
- No changes to the Codex adapter beyond shared CLI routing compatibility.
- No systemd or nginx changes.
- No access to `/opt/binance-futures-local-bot`.

## Implemented File Plan

Add:

- `agent_office/adapters/gemini.py`

Modify:

- `agent_office/adapters/registry.py`
- `agent_office/cli.py`
- `.env.example`
- `README.md`
- `docs/architecture.md`
- `docs/task-protocol.md`
- `docs/agent-roles.md`

## Adapter Contract

Command:

```bash
python3 -m agent_office context <TASK_ID> --real --adapter gemini --timeout 120
```

Environment variables:

```text
AGENTOFFICE_GEMINI_CMD=
AGENTOFFICE_GEMINI_TIMEOUT_SECONDS=120
AGENTOFFICE_GEMINI_MAX_FILES=80
AGENTOFFICE_GEMINI_MAX_OUTPUT_CHARS=12000
```

Input:

- `.ai/tasks/<TASK_ID>/brief.md`
- safe project file-tree summary
- `README.md`
- `docs/`
- `AGENTS.md` when present

Output:

- `.ai/tasks/<TASK_ID>/gemini-context.md`

Required sections:

- `# Relevant Files`
- `# Why These Files Matter`
- `# Test Entry Points`
- `# Implementation Hints`
- `# Risks`

## Safety Requirements

- Run with `shell=False`.
- Reject shell syntax or inline args in `AGENTOFFICE_GEMINI_CMD`.
- Enforce timeout.
- Enforce max file count and max output length.
- Mask token/key/secret-like values in logs.
- Do not read `.env`, key files, pem files, token files, secret files, runtime task logs, or unrelated project directories.

## Validation

Required:

```bash
python3 -m compileall -q agent_office
python3 -m agent_office run-demo DEMO-GEMINI-ADAPTER --mock --reset
bash scripts/smoke-test.sh DEMO-GEMINI-SMOKE
bash scripts/verify.sh
```

Guard:

```bash
python3 -m agent_office context DEMO-GEMINI-GUARD --real --adapter gemini
```

Expected when `AGENTOFFICE_GEMINI_CMD` is unset:

- command fails
- message mentions `AGENTOFFICE_GEMINI_CMD` or `--mock`
- no `gemini-context.md` is written
- state remains `CREATED`
