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
python3 -m agent_office doctor --adapter grok
python3 -m agent_office doctor --adapter claude
```

Produce machine-readable output:

```bash
python3 -m agent_office doctor --json
```

Print only the staged adapter mode registry:

```bash
python3 -m agent_office doctor --adapters
python3 -m agent_office.doctor --adapters
```

## What Doctor Checks

- Current project path.
- Python version.
- Whether `agent_office` can be imported.
- Required `.gitignore` runtime artifact rules.
- Whether `scripts/verify.sh` and `scripts/smoke-test.sh` exist.
- Whether the adapter registry contains `mock`, `codex`, `gemini`, `grok`, and `claude`.
- Whether Codex, Gemini, Grok, and Claude adapter environment variables are configured.
- The staged mode registry for Gemini, Codex, Grok, and Claude.

The staged mode table is:

```text
adapter | mode | dry_run | env_ok | fallback | status
```

## Configuration State

Doctor reports only `configured: true` or `configured: false`. It does not print environment variable values.

Provider adapters default to `mode=mock`. Real mode is impossible unless the specific adapter has `AGENTOFFICE_<ADAPTER>_MODE=real`. When an adapter is staged as real, `dry_run` defaults to `true`, so doctor can validate configuration without causing provider execution.

If required environment is missing for one real adapter, doctor marks only that adapter as `env_failed`. Other adapters can remain `ok`.

Codex variables checked:

- `AGENTOFFICE_CODEX_CMD`
- `AGENTOFFICE_CODEX_TIMEOUT_SECONDS`

Gemini variables checked:

- `AGENTOFFICE_GEMINI_CMD`
- `AGENTOFFICE_GEMINI_TIMEOUT_SECONDS`
- `AGENTOFFICE_GEMINI_MAX_FILES`
- `AGENTOFFICE_GEMINI_MAX_OUTPUT_CHARS`

Grok variables checked:

- `AGENTOFFICE_GROK_CMD`
- `AGENTOFFICE_GROK_TIMEOUT_SECONDS`

Claude variables checked:

- `AGENTOFFICE_CLAUDE_CMD`
- `AGENTOFFICE_CLAUDE_TIMEOUT_SECONDS`
- `AGENTOFFICE_CLAUDE_MAX_INPUT_CHARS`
- `AGENTOFFICE_CLAUDE_MAX_OUTPUT_CHARS`

## Why Values Are Not Printed

Provider command environments may sit next to credentials in operator shells. Doctor deliberately avoids reading `.env` and avoids printing variable values so secrets cannot leak into terminal history, chat logs, CI logs, or `.ai/` artifacts.

## Safety Guarantees

Doctor does not:

- read `.env`
- execute `AGENTOFFICE_CODEX_CMD`
- execute `AGENTOFFICE_GEMINI_CMD`
- execute `AGENTOFFICE_GROK_CMD`
- execute `AGENTOFFICE_CLAUDE_CMD`
- create tasks
- write `.ai/tasks/`
- scan unrelated projects
- access `/opt/binance-futures-local-bot`
- modify system directories

## Next Phase: Full Dry Run

After adding Claude final judge, doctor should show:

- registry contains `mock`, `codex`, `gemini`, `grok`, and `claude`
- mock workflow still passes `scripts/verify.sh`
- Codex, Gemini, Grok, and Claude configuration state is clear
- runtime artifact ignore rules are present

The next phase should run controlled end-to-end dry runs with explicit real adapter commands while keeping mock mode as the default fallback.
