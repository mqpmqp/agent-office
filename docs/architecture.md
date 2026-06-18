# AgentOffice Architecture

AgentOffice is a local, file-based coordinator for a four-agent workflow. The MVP deliberately uses deterministic mock providers so the task protocol can be verified without API keys, browser sessions, or network access.

## Components

- `agent_office/cli.py`: command-line orchestrator, task state machine, artifact writer, and adapter dispatcher.
- `agent_office/adapters/`: mock adapter plus opt-in real Gemini context, Codex implement, Grok red-team, and Claude final judge adapters.
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
5. Claude Code makes the final judge decision and does not apply changes.

## Mock Mode

Mock mode writes deterministic artifacts and never calls real provider APIs. It is used for local verification, VPS smoke tests, and protocol development.

The Phase 5 staged adapter registry keeps all adapters in `mode=mock` by default. P5-02 adds Gemini context dry-run, P5-03 adds Codex patch-only dry-run, P5-04 adds Grok review-only dry-run, and P5-05 adds Claude final-decision dry-run. Provider-specific authentication, browser state, or API calls belong behind adapter boundaries and must not be written into task artifacts.

Gemini is read-only against source code. It receives `brief.md`, a safe project file-tree summary, and allowed docs such as `README.md`, `docs/`, and `AGENTS.md` when present. It must not read `.env`, key files, token files, secret files, runtime task outputs, or unrelated project directories.

Grok is read-only against source code and repository state. It reviews only task artifacts: `brief.md`, `codex-report.md`, and `patch.diff`. It must not scan the full repository, modify code, or generate patches.

Claude is final-judge-only. In mock mode it reads the task `final-for-claude.md`. In P5-05 real dry-run it may review the bounded staged artifacts under `.ai/finalize/`, `.ai/context/`, `.ai/codex/`, and `.ai/grok/`, then writes only `.ai/claude/final-judge.md` and `.ai/claude/metadata.json`. It must not read `.env`, scan the repository, execute commands, apply patches, or modify source files.

## Token Control

Claude Code is intentionally constrained to compressed or staged evidence, capped by `AGENTOFFICE_CLAUDE_MAX_INPUT_CHARS`. This keeps final review cheap and predictable, and prevents Claude from reading full repository context, full logs, or uncontrolled diffs.

## Adapter Diagnostics

`python -m agent_office adapters` lists supported adapters. `python -m agent_office doctor` checks project structure, `.gitignore` safety rules, scripts, registry contents, and whether Codex/Gemini/Grok/Claude environment variables are present.

Doctor does not read `.env`, execute adapter commands, send real provider requests, create tasks, or print environment variable values.
