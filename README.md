# AgentOffice

AgentOffice is a minimal file-based orchestrator for four AI roles:

- Gemini: context scan and compressed summary.
- Codex: implementation, bug fixes, and tests.
- Grok Build: red-team review.
- Claude Code: final decision only.

The agents do not freely chat. Every task is coordinated through files under:

```text
.ai/tasks/<TASK_ID>/
  task.json
  brief.md
  gemini-context.md
  codex-report.md
  patch.diff
  grok-review.md
  final-for-claude.md
  claude-decision.md
```

## Claude Token Rule

Mock Claude reads only `final-for-claude.md`. P5-05 adds a staged real Claude final judge dry-run that can also review bounded staged artifacts under `.ai/context/`, `.ai/codex/`, and `.ai/grok/`.

- Claude does not read the full repository.
- Claude does not read full logs.
- Claude does not read the full diff.
- `final-for-claude.md` is capped at 4000 characters.
- Claude final judge dry-run writes only `.ai/claude/final-judge.md` and `.ai/claude/metadata.json`.
- Each task allows at most 2 rework rounds.

## Install

No third-party dependencies are required.

```bash
python -m pip install -e .
```

After install, the CLI command is:

```bash
agent-office --help
```

Without installation, use:

```bash
python -m agent_office --help
```

## Commands

```bash
agent-office new <TASK_ID>
agent-office context <TASK_ID> --mock
agent-office context <TASK_ID> --real --adapter gemini --timeout 120
agent-office implement <TASK_ID> --mock
agent-office implement <TASK_ID> --real --adapter codex --timeout 1200
agent-office redteam <TASK_ID> --mock
agent-office redteam <TASK_ID> --real --adapter grok --timeout 120
agent-office summarize <TASK_ID> --mock
agent-office final <TASK_ID> --mock
agent-office final <TASK_ID> --real --adapter claude --dry-run --timeout 120
agent-office judge <TASK_ID> --real --adapter claude --dry-run --timeout 120
agent-office status <TASK_ID>
agent-office run-demo <TASK_ID> --mock
agent-office run-staged <TASK_ID> --dry-run --reset
agent-office run-staged <TASK_ID> --dry-run --real --adapter gemini
agent-office adapters
agent-office doctor
agent-office doctor --adapter codex
agent-office doctor --adapter gemini
agent-office doctor --adapter grok
agent-office doctor --adapter claude
agent-office doctor --adapters
agent-office doctor --json
python -m agent_office.doctor --adapters
```

## State Machine

```text
CREATED
CONTEXT_READY
IMPLEMENTED
REVIEWED
SUMMARIZED
CLAUDE_DECIDED
APPROVED
REQUEST_CHANGES
REJECTED
```

`CLAUDE_DECIDED` is recorded in `task.json` history. The task state then moves to one of:

- `APPROVED`
- `REQUEST_CHANGES`
- `REJECTED`

## Mock Demo

```bash
agent-office run-demo demo-task --mock
```

or:

```bash
python -m agent_office run-demo demo-task --mock
```

Repeat the same demo safely with `--reset`:

```bash
python -m agent_office run-demo demo-task --mock --reset
```

`--reset` deletes only `.ai/tasks/<TASK_ID>/` for the task being run, then recreates the deterministic mock workflow from scratch. It does not relax the state machine and does not affect other task directories.

To clean demo tasks manually:

```bash
rm -rf .ai/tasks/DEMO-*
```

## Staged Full Dry Run

P6-01 adds a dry-run orchestration command that only chains existing stages:

```bash
python -m agent_office run-staged <TASK_ID> --dry-run --reset
```

It runs:

```text
new -> context -> implement -> redteam -> summarize -> judge -> status
```

All stages are mock by default, even if adapter environment variables are present. To exercise one staged real dry-run adapter, enable exactly one adapter explicitly:

```bash
export AGENTOFFICE_GEMINI_MODE=real
export AGENTOFFICE_GEMINI_DRY_RUN=true
export GEMINI_API_KEY=replace-with-real-key-outside-git
python -m agent_office run-staged <TASK_ID> --dry-run --real --adapter gemini --reset
```

Use `codex`, `grok`, or `claude` in the same shape to exercise one corresponding stage. `run-staged` refuses `--real` without a single `--adapter`, refuses adapter selection without `--real`, and requires `--dry-run`.

Safety boundaries:

- No real provider request is sent while `--dry-run` is active.
- No patch is applied.
- No git commit is made.
- `.env` is not read and environment variable values are not printed.
- The existing task state machine is reused unchanged.
- Runtime artifacts stay under ignored `.ai/**` paths.
- Each `run-staged` invocation clears stale staged runtime directories: `.ai/context/`, `.ai/codex/`, `.ai/grok/`, `.ai/claude/`, and `.ai/finalize/`.
- Before a selected real dry-run stage, AgentOffice copies only the current task's existing artifacts into the matching staged directories so adapters do not review evidence from a previous task.

## Verify

```bash
bash scripts/verify.sh
bash scripts/smoke-test.sh demo-task
```

Both scripts are repeatable. `smoke-test.sh` runs the requested task with `--reset`; `verify.sh` uses a fixed local verification task and resets it before each run.

## Adapter Diagnostics

List supported adapters without executing real providers:

```bash
python -m agent_office adapters
```

Check project and adapter configuration:

```bash
python -m agent_office doctor
python -m agent_office doctor --adapter codex
python -m agent_office doctor --adapter gemini
python -m agent_office doctor --adapter grok
python -m agent_office doctor --adapter claude
python -m agent_office doctor --adapters
python -m agent_office.doctor --adapters
python -m agent_office doctor --json
```

`doctor` does not read `.env`, does not execute real Codex, Gemini, Grok, or Claude commands, does not create tasks, and does not print environment variable values. It reports only `configured=true` or `configured=false`.

The staged adapter table shows the safe mode registry:

```text
adapter | mode | dry_run | env_ok | fallback | status
gemini | mock | false | true | false | ok
codex | mock | false | true | false | ok
grok | mock | false | true | false | ok
claude | mock | false | true | false | ok
```

## Staged Real Adapter Mode Registry

All provider adapters default to `mode=mock`. Passing `--real` is not enough to run a provider. The matching adapter must also be explicitly staged with:

```bash
export AGENTOFFICE_GEMINI_MODE=real
export GEMINI_API_KEY=replace-with-real-key-outside-git
```

When an adapter is in `mode=real`, `dry_run` defaults to `true`. In dry-run mode AgentOffice validates configuration but does not send a provider request. To keep a workflow moving during staged tests, set fallback explicitly:

```bash
export AGENTOFFICE_GEMINI_DRY_RUN=true
export AGENTOFFICE_GEMINI_FALLBACK_TO_MOCK=true
python -m agent_office context <TASK_ID> --real --adapter gemini
```

The task continues with mock output and records `fallback_used=true` in the transition detail. If `fallback_to_mock=false`, the workflow fails safely.

Non-dry-run provider execution is rejected unless it is explicitly allowed for that adapter:

```bash
export AGENTOFFICE_CODEX_DRY_RUN=false
export AGENTOFFICE_CODEX_ALLOW_NON_DRY_RUN=true
```

Use the equivalent `AGENTOFFICE_CODEX_*`, `AGENTOFFICE_GROK_*`, and `AGENTOFFICE_CLAUDE_*` variables for the other adapters where applicable. The P5 dry-run adapters do not execute shell commands by default. This staged gate does not read `.env` and does not print environment values.

## Gemini Context Adapter

Mock mode remains the default context path:

```bash
python -m agent_office context <TASK_ID> --mock
```

The real Gemini adapter is available only for the `context` stage. In P5-02 it supports a safe dry-run path. Gemini does not modify code, does not execute commands, and does not make final decisions. It receives the task brief plus selected safe project context, then writes:

```text
.ai/context/gemini-context.md
```

The generated file must include these sections:

```text
# Gemini Context
## Task Summary
## Relevant Project Facts
## Current Architecture
## Safety Boundaries
## Files Reviewed
## Suggested Implementation Notes
## Risks / Unknowns
## Non-Goals
```

To enable Gemini real context dry-run:

```bash
export AGENTOFFICE_AGENT_MODE=real
export AGENTOFFICE_GEMINI_MODE=real
export AGENTOFFICE_GEMINI_DRY_RUN=true
export AGENTOFFICE_GEMINI_FALLBACK_TO_MOCK=true
export GEMINI_API_KEY=replace-with-real-key-outside-git
export AGENTOFFICE_GEMINI_TIMEOUT_SECONDS=120
export AGENTOFFICE_GEMINI_MAX_FILES=80
export AGENTOFFICE_GEMINI_MAX_INPUT_CHARS=20000
export AGENTOFFICE_GEMINI_MAX_OUTPUT_CHARS=12000
python -m agent_office context <TASK_ID> --real --adapter gemini --timeout 120
```

Dry-run validates `GEMINI_API_KEY` presence but sends no network request. The adapter metadata records `dry_run=true`, `real_request_sent=false`, and `output_path=.ai/context/gemini-context.md`.

The adapter refuses real mode when `GEMINI_API_KEY` is missing unless `AGENTOFFICE_GEMINI_FALLBACK_TO_MOCK=true`. With fallback enabled, the workflow continues with the deterministic mock context and records `fallback_used=true`.

Allowed input is limited to the task brief and safe project files such as `README.md`, `AGENTS.md`, `SPEC.md`, `docs/**`, `agent_office/**`, `tests/**`, `scripts/**`, `pyproject.toml`, `requirements.txt`, and `.env.example`. Gemini must not read `.env`, key files, token files, secret files, `.ai/logs/**`, `.ai/tmp/**`, `.ai/tasks/**`, backup archives, or unrelated projects.

Non-dry-run Gemini network calls remain guarded. Set `AGENTOFFICE_GEMINI_DRY_RUN=false` and `AGENTOFFICE_GEMINI_ALLOW_NON_DRY_RUN=true` only for a separately reviewed real API rollout.

Rollback to mock mode:

```bash
unset GEMINI_API_KEY
export AGENTOFFICE_GEMINI_MODE=mock
export AGENTOFFICE_AGENT_MODE=mock
python -m agent_office context <TASK_ID> --mock
```

## Codex Adapter

Mock mode remains the default and safest path:

```bash
python -m agent_office implement <TASK_ID> --mock
```

The real Codex adapter is available only for the `implement` stage. In P5-03 it is patch-only dry-run. It does not directly modify source files, does not execute commands, does not call OpenAI/Codex network APIs, and does not apply patches automatically.

To enable Codex real implement dry-run:

```bash
export AGENTOFFICE_AGENT_MODE=real
export AGENTOFFICE_CODEX_MODE=real
export AGENTOFFICE_CODEX_DRY_RUN=true
export AGENTOFFICE_CODEX_FALLBACK_TO_MOCK=true
export OPENAI_API_KEY=replace-with-real-key-outside-git
export AGENTOFFICE_CODEX_TIMEOUT_SECONDS=1200
python -m agent_office implement <TASK_ID> --real --adapter codex --timeout 1200
```

Dry-run validates `OPENAI_API_KEY` presence but sends no network request. It writes only:

```text
.ai/codex/patch.diff
.ai/codex/codex-report.md
.ai/codex/metadata.json
```

The generated patch is a proposal only. AgentOffice does not apply it, does not run `git apply`, and does not commit it. A human must review and apply any patch in a separate step.

The patch safety validator rejects patches that modify `.env`, add obvious secrets, touch private keys, delete guard tests, weaken adapter safety defaults, enable all real adapters, set `dry_run=false` by default, set `allow_non_dry_run=true` by default, set `can_execute_commands=true` by default, target paths outside the allowed review set, or include unsafe live trading action markers.

If `OPENAI_API_KEY` is missing and `AGENTOFFICE_CODEX_FALLBACK_TO_MOCK=true`, the workflow continues with the deterministic mock implementation and records `fallback_used=true`. If fallback is false, the workflow fails safely.

Rollback to mock mode:

```bash
unset OPENAI_API_KEY
export AGENTOFFICE_CODEX_MODE=mock
export AGENTOFFICE_AGENT_MODE=mock
python -m agent_office run-demo DEMO-FINAL --mock --reset
```

## Grok Red-Team Adapter

Mock mode remains the default review path:

```bash
python -m agent_office redteam <TASK_ID> --mock
```

The real Grok adapter is available only for the `redteam` stage. In P5-04 it is review-only dry-run. Grok does not modify code, does not generate patches, does not apply patches, does not execute commands, and does not call the xAI/Grok network API while `dry_run=true`.

Grok primarily reviews:

```text
.ai/context/gemini-context.md
.ai/codex/patch.diff
.ai/codex/codex-report.md
.ai/codex/metadata.json
```

It writes only:

```text
.ai/grok/redteam-report.md
.ai/grok/metadata.json
```

The generated review must include:

```text
# Grok Redteam Report
## Review Summary
## Inputs Reviewed
## Patch Risk Assessment
## Safety Issues
## Logic Issues
## Missing Tests
## Security Concerns
## Possible Regression Risks
## Recommendation
```

The recommendation is exactly one of:

```text
PASS_TO_CLAUDE
REQUEST_CODEX_REVISION
BLOCK
```

To enable Grok real redteam dry-run:

```bash
export AGENTOFFICE_AGENT_MODE=real
export AGENTOFFICE_GROK_MODE=real
export AGENTOFFICE_GROK_DRY_RUN=true
export AGENTOFFICE_GROK_FALLBACK_TO_MOCK=true
export XAI_API_KEY=replace-with-real-key-outside-git
export AGENTOFFICE_GROK_TIMEOUT_SECONDS=120
export AGENTOFFICE_GROK_MAX_INPUT_CHARS=24000
export AGENTOFFICE_GROK_MAX_OUTPUT_CHARS=12000
python -m agent_office redteam <TASK_ID> --real --adapter grok --timeout 120
```

Dry-run validates `XAI_API_KEY` presence but sends no network request. If `XAI_API_KEY` is missing and `AGENTOFFICE_GROK_FALLBACK_TO_MOCK=true`, the workflow continues with deterministic mock review and records `fallback_used=true`.

If no patch is available, Grok fails safely or falls back to mock depending on configuration. It must not invent a patch. Do not apply patches automatically and do not enable all real adapters at once.

Rollback to mock mode:

```bash
unset XAI_API_KEY
export AGENTOFFICE_GROK_MODE=mock
export AGENTOFFICE_AGENT_MODE=mock
python -m agent_office redteam <TASK_ID> --mock
```

## Claude Final Judge Adapter

Mock mode remains the default final decision path:

```bash
python -m agent_office final <TASK_ID> --mock
```

The real Claude adapter is available only for the `final` stage. P5-05 supports final-decision dry-run only. It does not send Anthropic API requests while `dry_run=true`.

Claude may review:

```text
.ai/finalize/final-for-claude.md
.ai/context/gemini-context.md
.ai/codex/patch.diff
.ai/codex/codex-report.md
.ai/codex/metadata.json
.ai/grok/redteam-report.md
.ai/grok/metadata.json
.ai/tasks/<TASK_ID>/final-for-claude.md
```

If `final-for-claude.md` is missing, the `judge` command can build a minimal final packet from existing staged Gemini/Codex/Grok artifacts. It does not invent missing evidence.

Claude must not modify source files, apply patches, commit, execute commands, run shell, or read `.env`, key files, token files, secret files, logs, tmp files, or unrelated projects.

The real Claude dry-run adapter writes only:

```text
.ai/claude/final-judge.md
.ai/claude/metadata.json
```

The generated report includes:

```text
# Claude Final Judge
## Decision
## Reasons
## Required Changes
## Risk Flags
## Evidence Reviewed
## Safety Notes
## Non-Goals
```

The decision is exactly one of:

```text
APPROVE
REQUEST_CHANGES
REJECT
```

The task state maps those to `APPROVED`, `REQUEST_CHANGES`, or `REJECTED`.

To enable Claude real final judge dry-run:

```bash
export AGENTOFFICE_AGENT_MODE=real
export AGENTOFFICE_CLAUDE_MODE=real
export AGENTOFFICE_CLAUDE_DRY_RUN=true
export AGENTOFFICE_CLAUDE_FALLBACK_TO_MOCK=true
export ANTHROPIC_API_KEY=replace-with-real-key-outside-git
export AGENTOFFICE_CLAUDE_TIMEOUT_SECONDS=120
export AGENTOFFICE_CLAUDE_MAX_INPUT_CHARS=16000
export AGENTOFFICE_CLAUDE_MAX_OUTPUT_CHARS=12000
python -m agent_office judge <TASK_ID> --real --adapter claude --dry-run --timeout 120
```

Dry-run validates `ANTHROPIC_API_KEY` presence but sends no network request. Metadata records `dry_run=true`, `real_request_sent=false`, `fallback_used=false`, `decision`, `risk_flags`, and `report_path=.ai/claude/final-judge.md`.

If `ANTHROPIC_API_KEY` is missing and `AGENTOFFICE_CLAUDE_FALLBACK_TO_MOCK=true`, the workflow continues with deterministic mock final output and records `fallback_used=true`. If fallback is false, the workflow fails safely.

Non-dry-run Claude API calls remain guarded and are not implemented in P5-05. Set `AGENTOFFICE_CLAUDE_DRY_RUN=false` and `AGENTOFFICE_CLAUDE_ALLOW_NON_DRY_RUN=true` only in a separately reviewed future phase with mocked tests first.

Rollback to mock mode:

```bash
unset ANTHROPIC_API_KEY
export AGENTOFFICE_CLAUDE_MODE=mock
export AGENTOFFICE_AGENT_MODE=mock
python -m agent_office final <TASK_ID> --mock
```

When Claude returns `REQUEST_CHANGES`, use the required changes and risk flags as the next Codex input. The existing max rework limit remains 2 rounds.

## Docs

- `docs/architecture.md`: system shape and role boundaries.
- `docs/task-protocol.md`: `.ai/tasks/<TASK_ID>/` file protocol.
- `docs/agent-roles.md`: Gemini, Codex, Grok Build, and Claude Code responsibilities.
- `docs/adapter-doctor.md`: safe adapter diagnostics.
- `docs/plans/gemini-adapter-implementation-plan.md`: Gemini adapter plan and Phase 2 notes.
- `docs/real-agent-integration-plan.md`: real adapter rollout plan and Phase status.
- `deploy/deploy.md`: VPS deployment notes for a human operator.
- `deploy/systemd.service.example`: example unit file only.

## MVP Boundaries

- Real provider calls are intentionally limited to Gemini `context`, Codex `implement`, Grok `redteam`, and Claude `final` adapters when explicitly enabled.
- No real keys are read or printed.
- The orchestrator owns task state, queue discipline, logs, and artifact management.
