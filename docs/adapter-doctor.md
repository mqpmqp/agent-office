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

- `OPENAI_API_KEY`
- `AGENTOFFICE_CODEX_TIMEOUT_SECONDS`
- `AGENTOFFICE_CODEX_MAX_INPUT_CHARS`
- `AGENTOFFICE_CODEX_MAX_OUTPUT_CHARS`

Gemini variables checked:

- `GEMINI_API_KEY`
- `AGENTOFFICE_GEMINI_TIMEOUT_SECONDS`
- `AGENTOFFICE_GEMINI_MAX_FILES`
- `AGENTOFFICE_GEMINI_MAX_INPUT_CHARS`
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

Provider command environments may sit next to credentials in operator shells. Gemini uses `GEMINI_API_KEY` and Codex uses `OPENAI_API_KEY` for future real network access. Doctor deliberately avoids reading `.env` and avoids printing variable values so secrets cannot leak into terminal history, chat logs, CI logs, or `.ai/` artifacts.

## Safety Guarantees

Doctor does not:

- read `.env`
- execute Codex commands
- send Codex network requests
- execute Gemini commands
- send Gemini network requests
- execute `AGENTOFFICE_GROK_CMD`
- execute `AGENTOFFICE_CLAUDE_CMD`
- create tasks
- write `.ai/tasks/`
- scan unrelated projects
- access `/opt/binance-futures-local-bot`
- modify system directories

## Gemini Real Context Dry-Run

P5-02 adds a staged Gemini real context dry-run. When:

```bash
export AGENTOFFICE_GEMINI_MODE=real
export AGENTOFFICE_GEMINI_DRY_RUN=true
export GEMINI_API_KEY=replace-with-real-key-outside-git
```

doctor should show Gemini `env_ok=true` and `status=ok`. The context command can then generate:

```text
.ai/context/gemini-context.md
```

No real Gemini API request is sent while `dry_run=true`. If `GEMINI_API_KEY` is missing, doctor marks only Gemini as `env_failed`; other adapters remain unaffected. If `AGENTOFFICE_GEMINI_FALLBACK_TO_MOCK=true`, the workflow can continue through mock context and records `fallback_used=true`.

## Codex Real Implement Patch-Only Dry-Run

P5-03 adds a staged Codex implement dry-run. When:

```bash
export AGENTOFFICE_CODEX_MODE=real
export AGENTOFFICE_CODEX_DRY_RUN=true
export OPENAI_API_KEY=replace-with-real-key-outside-git
```

doctor should show Codex `env_ok=true` and `status=ok`. The implement command can then generate:

```text
.ai/codex/patch.diff
.ai/codex/codex-report.md
.ai/codex/metadata.json
```

No real OpenAI/Codex API request is sent while `dry_run=true`. The patch is a proposal only; AgentOffice does not apply it, run commands, or commit it. Patch validation rejects env edits, secret additions, private-key paths, guard-test deletion, weakened safety defaults, all-real adapter activation, and unsafe live trading action markers.

## Next Phase: Full Dry Run

After adding Gemini context dry-run and Codex patch-only dry-run, doctor should show:

- registry contains `mock`, `codex`, `gemini`, `grok`, and `claude`
- mock workflow still passes `scripts/verify.sh`
- Codex, Gemini, Grok, and Claude configuration state is clear
- runtime artifact ignore rules are present

The next phase should continue controlled end-to-end dry runs while keeping mock mode as the default fallback. Do not enable all adapters at once.
