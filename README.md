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

Claude reads only `final-for-claude.md`.

- Claude does not read the full repository.
- Claude does not read full logs.
- Claude does not read the full diff.
- `final-for-claude.md` is capped at 4000 characters.
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
agent-office final <TASK_ID> --real --adapter claude --timeout 120
agent-office status <TASK_ID>
agent-office run-demo <TASK_ID> --mock
agent-office adapters
agent-office doctor
agent-office doctor --adapter codex
agent-office doctor --adapter gemini
agent-office doctor --json
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
python -m agent_office doctor --json
```

`doctor` does not read `.env`, does not execute real Codex, Gemini, Grok, or Claude commands, does not create tasks, and does not print environment variable values. It reports only `configured=true` or `configured=false`.

## Gemini Context Adapter

Mock mode remains the default context path:

```bash
python -m agent_office context <TASK_ID> --mock
```

The real Gemini adapter is available only for the `context` stage. Gemini does not modify code. It receives the task brief plus a safe project file-tree summary and allowed docs, then must write:

```text
.ai/tasks/<TASK_ID>/gemini-context.md
```

The generated file must include these sections:

```text
# Relevant Files
# Why These Files Matter
# Test Entry Points
# Implementation Hints
# Risks
```

To enable the real Gemini adapter:

```bash
export AGENTOFFICE_AGENT_MODE=real
export AGENTOFFICE_GEMINI_CMD=gemini
export AGENTOFFICE_GEMINI_TIMEOUT_SECONDS=120
export AGENTOFFICE_GEMINI_MAX_FILES=80
export AGENTOFFICE_GEMINI_MAX_OUTPUT_CHARS=12000
python -m agent_office context <TASK_ID> --real --adapter gemini --timeout 120
```

`AGENTOFFICE_GEMINI_CMD` must be a single executable name or path, without shell syntax or extra arguments. AgentOffice runs it with `shell=False`, sends the prompt on stdin, captures stdout/stderr, and writes sanitized logs under `.ai/logs/<TASK_ID>/`.

The adapter refuses real execution when `AGENTOFFICE_GEMINI_CMD` is empty. It also fails if the command exits successfully but does not write a non-empty `gemini-context.md`.

Rollback to mock mode:

```bash
unset AGENTOFFICE_GEMINI_CMD
export AGENTOFFICE_AGENT_MODE=mock
python -m agent_office context <TASK_ID> --mock
```

## Codex Adapter

Mock mode remains the default and safest path:

```bash
python -m agent_office implement <TASK_ID> --mock
```

The real Codex adapter is available only for the `implement` stage. `context`, `redteam`, and `final` still use mock providers in this phase.

To enable the real Codex adapter, set an executable command in the environment:

```bash
export AGENTOFFICE_AGENT_MODE=real
export AGENTOFFICE_CODEX_CMD=codex
export AGENTOFFICE_CODEX_TIMEOUT_SECONDS=1200
python -m agent_office implement <TASK_ID> --real --adapter codex --timeout 1200
```

`AGENTOFFICE_CODEX_CMD` must be a single executable name or path, without shell syntax or extra arguments. AgentOffice runs it with `shell=False`, sends the task prompt on stdin, captures stdout/stderr, writes sanitized logs under `.ai/logs/<TASK_ID>/`, and requires the adapter to produce both:

```text
.ai/tasks/<TASK_ID>/codex-report.md
.ai/tasks/<TASK_ID>/patch.diff
```

If the real command is missing or does not produce a non-empty `patch.diff`, the task does not transition to `IMPLEMENTED`.

Rollback to mock mode:

```bash
unset AGENTOFFICE_CODEX_CMD
export AGENTOFFICE_AGENT_MODE=mock
python -m agent_office run-demo DEMO-FINAL --mock --reset
```

## Grok Red-Team Adapter

Mock mode remains the default review path:

```bash
python -m agent_office redteam <TASK_ID> --mock
```

The real Grok adapter is available only for the `redteam` stage. Grok does not modify code, does not generate patches, and does not scan the full repository. It reads only:

```text
.ai/tasks/<TASK_ID>/brief.md
.ai/tasks/<TASK_ID>/codex-report.md
.ai/tasks/<TASK_ID>/patch.diff
```

It must write:

```text
.ai/tasks/<TASK_ID>/grok-review.md
```

The generated review must include:

```text
# Blocking Issues
# Non-blocking Issues
# Missing Tests
# Security Risks
# Performance Risks
# Verdict
```

To enable the real Grok adapter:

```bash
export AGENTOFFICE_AGENT_MODE=real
export AGENTOFFICE_GROK_CMD=grok
export AGENTOFFICE_GROK_TIMEOUT_SECONDS=120
export AGENTOFFICE_GROK_MAX_OUTPUT_CHARS=12000
python -m agent_office redteam <TASK_ID> --real --adapter grok --timeout 120
```

`AGENTOFFICE_GROK_CMD` must be a single executable name or path, without shell syntax or extra arguments. If it is empty, real Grok execution is refused and the operator should use `--mock`.

Rollback to mock mode:

```bash
unset AGENTOFFICE_GROK_CMD
export AGENTOFFICE_AGENT_MODE=mock
python -m agent_office redteam <TASK_ID> --mock
```

## Claude Final Judge Adapter

Mock mode remains the default final decision path:

```bash
python -m agent_office final <TASK_ID> --mock
```

The real Claude adapter is available only for the `final` stage. Claude reads only:

```text
.ai/tasks/<TASK_ID>/final-for-claude.md
```

Claude does not read the repository, `.env`, logs, `patch.diff`, `codex-report.md`, `grok-review.md`, or `gemini-context.md`. Those upstream artifacts must already be compressed by the `summarize` stage into `final-for-claude.md`.

The real Claude adapter must write:

```text
.ai/tasks/<TASK_ID>/claude-decision.md
```

The generated decision must include:

```text
DECISION: APPROVE | REQUEST_CHANGES | REJECT

REASONS:
MUST_FIX:
NICE_TO_HAVE:
NEXT_ACTION_FOR_CODEX:
```

To enable the real Claude adapter:

```bash
export AGENTOFFICE_AGENT_MODE=real
export AGENTOFFICE_CLAUDE_CMD=claude
export AGENTOFFICE_CLAUDE_TIMEOUT_SECONDS=120
export AGENTOFFICE_CLAUDE_MAX_INPUT_CHARS=12000
export AGENTOFFICE_CLAUDE_MAX_OUTPUT_CHARS=8000
python -m agent_office final <TASK_ID> --real --adapter claude --timeout 120
```

`AGENTOFFICE_CLAUDE_CMD` must be a single executable name or path, without shell syntax or extra arguments. If `final-for-claude.md` exceeds `AGENTOFFICE_CLAUDE_MAX_INPUT_CHARS`, the adapter fails and asks the operator to re-run summarize with stronger compression. It never reads additional files to compensate.

Rollback to mock mode:

```bash
unset AGENTOFFICE_CLAUDE_CMD
export AGENTOFFICE_AGENT_MODE=mock
python -m agent_office final <TASK_ID> --mock
```

When Claude returns `DECISION: REQUEST_CHANGES`, the `NEXT_ACTION_FOR_CODEX` section should be used as the next Codex input. The existing max rework limit remains 2 rounds.

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
