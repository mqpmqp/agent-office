# Staged Full Dry Run

P6-01 adds a command-level orchestration wrapper:

```bash
python -m agent_office run-staged <TASK_ID> --dry-run --reset
```

The command runs existing stages only:

```text
new -> context -> implement -> redteam -> summarize -> judge -> status
```

It does not add workflow features, task states, patch application, git commits, or provider transport.

## Defaults

Every adapter remains mock by default. `run-staged` sets each step to mock unless one real adapter is selected explicitly.

The command also ignores `AGENTOFFICE_AGENT_MODE=real` for automatic full-loop real execution. This prevents environment drift from turning a full dry run into a multi-provider run.

## One Real Adapter At A Time

To exercise a real dry-run stage, all of these are required:

- `--dry-run`
- `--real`
- exactly one `--adapter gemini|codex|grok|claude`
- the matching `AGENTOFFICE_<ADAPTER>_MODE=real`
- the adapter required environment variable

Example:

```bash
export AGENTOFFICE_GEMINI_MODE=real
export AGENTOFFICE_GEMINI_DRY_RUN=true
export GEMINI_API_KEY=replace-with-real-key-outside-git
python -m agent_office run-staged P6-GEMINI --dry-run --real --adapter gemini --reset
```

All other stages remain mock. Enabling all real adapters in one invocation is refused by design.

## Safety Guarantees

- No real provider request is sent while `--dry-run` is active.
- No patch is applied.
- No source file is modified by adapter output.
- No git commit is made.
- `.env` is not read.
- Environment variable values are not printed.
- Runtime artifacts stay under ignored `.ai/**` locations.
- The existing four-agent state machine remains unchanged.

## Verification

Run:

```bash
python3 -m compileall -q agent_office
python3 -m unittest discover -s tests -p 'test_*.py'
python3 -m agent_office doctor --adapters
bash scripts/verify.sh
bash scripts/smoke-test.sh P6-STAGED-DRY-RUN
python3 -m agent_office run-staged P6-STAGED-DRY-RUN --dry-run --reset
```
