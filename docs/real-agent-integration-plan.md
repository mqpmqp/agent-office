# Real Agent Integration Plan

## Current Phase

Phase 1 implements the Codex adapter接入层 for the `implement` stage only. Gemini, Grok Build, and Claude Code remain mock providers.

## Adapter Boundary

AgentOffice remains the state machine and file protocol owner. Real adapters plug in behind the existing commands and must preserve the same task artifacts.

```text
AgentOffice CLI
  -> adapter registry
    -> mock adapter or real Codex adapter
      -> .ai/tasks/<TASK_ID>/ artifacts
```

## Phase 1: Codex Adapter

Real Codex execution is opt-in:

```bash
export AGENTOFFICE_AGENT_MODE=real
export AGENTOFFICE_CODEX_CMD=codex
export AGENTOFFICE_CODEX_TIMEOUT_SECONDS=1200
python3 -m agent_office implement <TASK_ID> --real --adapter codex --timeout 1200
```

Mock mode remains the default:

```bash
python3 -m agent_office implement <TASK_ID> --mock
```

If `AGENTOFFICE_CODEX_CMD` is not configured, the real adapter refuses to run and tells the operator to use `--mock`.

## Codex Input Protocol

The Codex adapter reads only:

- `.ai/tasks/<TASK_ID>/brief.md`
- `.ai/tasks/<TASK_ID>/gemini-context.md`
- `AGENTS.md` if present

It must not read `.env`, key files, token files, unrelated project directories, `/opt/binance-futures-local-bot`, or system service directories.

## Codex Output Protocol

The Codex adapter must write:

- `.ai/tasks/<TASK_ID>/codex-report.md`
- `.ai/tasks/<TASK_ID>/patch.diff`

If `patch.diff` is missing or empty, AgentOffice reports a clear error and does not transition the task to `IMPLEMENTED`.

## Safety Controls

- Commands run with `shell=False`.
- `AGENTOFFICE_CODEX_CMD` must be one executable name or path, without inline arguments.
- Adapter timeout comes from `--timeout` or `AGENTOFFICE_CODEX_TIMEOUT_SECONDS`.
- stdout/stderr are captured and sanitized.
- token/key/secret-like values are masked before logs are written.
- sanitized logs go under `.ai/logs/<TASK_ID>/`.

## Later Phases

1. Gemini real context adapter.
2. Grok Build real red-team adapter.
3. Claude final judge adapter restricted to `final-for-claude.md`.
4. Optional CLIProxyAPI gateway if it preserves timeout, cwd isolation, exit code handling, and log redaction.

Until those phases are implemented, `context`, `redteam`, `summarize`, and `final` should be run in mock mode.
