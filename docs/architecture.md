# AgentOffice Architecture

AgentOffice is a local, file-based coordinator for a four-agent workflow. The MVP deliberately uses deterministic mock providers so the task protocol can be verified without API keys, browser sessions, or network access.

## Components

- `agent_office/cli.py`: command-line orchestrator, task state machine, artifact writer, and adapter dispatcher.
- `agent_office/adapters/`: mock adapter plus opt-in real Gemini context and Codex implement adapters.
- `agent_office/doctor.py`: safe adapter and project diagnostics that never execute real providers.
- `.ai/tasks/<TASK_ID>/`: per-task workspace owned by the orchestrator.
- `scripts/smoke-test.sh`: repeatable end-to-end mock workflow check.
- `scripts/verify.sh`: repeatable baseline verification for packaging and VPS upload.
- `docs/`: operator and integration documentation.
- `deploy/`: example deployment files only; the project does not modify system directories.

## Role Flow

1. Gemini prepares compressed repository or task context.
2. Codex implements the requested change and records a patch/report.
3. Grok Build performs red-team review before final decision.
4. The orchestrator writes `final-for-claude.md`.
5. Claude Code reads only `final-for-claude.md` and writes the final decision.

## Mock Mode

Mock mode writes deterministic artifacts and never calls real provider APIs. It is used for local verification, VPS smoke tests, and protocol development.

The Phase 1 real Codex adapter preserves the same command surface and file protocol for `implement` only. Phase 2 adds a real Gemini adapter for `context` only. Provider-specific authentication, browser state, or API calls belong behind adapter boundaries and must not be written into task artifacts.

Gemini is read-only against source code. It receives `brief.md`, a safe project file-tree summary, and allowed docs such as `README.md`, `docs/`, and `AGENTS.md` when present. It must not read `.env`, key files, token files, secret files, runtime task outputs, or unrelated project directories.

## Token Control

Claude Code is intentionally constrained to `final-for-claude.md`, capped by the orchestrator. This keeps final review cheap and predictable, and prevents Claude from re-reading full repository context, full logs, or full diffs.

## Adapter Diagnostics

`python -m agent_office adapters` lists supported adapters. `python -m agent_office doctor` checks project structure, `.gitignore` safety rules, scripts, registry contents, and whether Codex/Gemini environment variables are present.

Doctor does not read `.env`, execute adapter commands, create tasks, or print environment variable values.
