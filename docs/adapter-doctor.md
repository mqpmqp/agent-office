# Adapter Doctor

`doctor` is a safe configuration diagnostic command for AgentOffice adapters. It checks project structure and adapter configuration state without running real AI providers.

## Commands

List supported adapters:

```bash
python3 -m agent_office adapters
```

Run full diagnostics:

```bash
python3 -m agent_office doctor
```

Check one adapter:

```bash
python3 -m agent_office doctor --adapter codex
python3 -m agent_office doctor --adapter gemini
```

Produce machine-readable output:

```bash
python3 -m agent_office doctor --json
```

## What Doctor Checks

- Current project path.
- Python version.
- Whether `agent_office` can be imported.
- Required `.gitignore` runtime artifact rules.
- Whether `scripts/verify.sh` and `scripts/smoke-test.sh` exist.
- Whether the adapter registry contains `mock`, `codex`, and `gemini`.
- Whether Codex and Gemini adapter environment variables are configured.

## Configuration State

Doctor reports only `configured: true` or `configured: false`. It does not print environment variable values.

Codex variables checked:

- `AGENTOFFICE_CODEX_CMD`
- `AGENTOFFICE_CODEX_TIMEOUT_SECONDS`

Gemini variables checked:

- `AGENTOFFICE_GEMINI_CMD`
- `AGENTOFFICE_GEMINI_TIMEOUT_SECONDS`
- `AGENTOFFICE_GEMINI_MAX_FILES`
- `AGENTOFFICE_GEMINI_MAX_OUTPUT_CHARS`

## Why Values Are Not Printed

Provider command environments may sit next to credentials in operator shells. Doctor deliberately avoids reading `.env` and avoids printing variable values so secrets cannot leak into terminal history, chat logs, CI logs, or `.ai/` artifacts.

## Safety Guarantees

Doctor does not:

- read `.env`
- execute `AGENTOFFICE_CODEX_CMD`
- execute `AGENTOFFICE_GEMINI_CMD`
- create tasks
- write `.ai/tasks/`
- scan unrelated projects
- access `/opt/binance-futures-local-bot`
- modify system directories

## Next Phase: Grok Adapter

Before adding a Grok adapter, doctor should show:

- registry contains `mock`, `codex`, and `gemini`
- mock workflow still passes `scripts/verify.sh`
- Codex and Gemini configuration state is clear
- runtime artifact ignore rules are present

The Grok phase should add a read-only `redteam` adapter and then extend doctor to report Grok configuration without executing the Grok command.
