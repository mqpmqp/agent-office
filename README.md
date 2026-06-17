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
agent-office implement <TASK_ID> --mock
agent-office redteam <TASK_ID> --mock
agent-office summarize <TASK_ID> --mock
agent-office final <TASK_ID> --mock
agent-office status <TASK_ID>
agent-office run-demo <TASK_ID> --mock
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

## Verify

```bash
bash scripts/verify.sh
bash scripts/smoke-test.sh demo-task
```

## MVP Boundaries

- Real provider calls are intentionally not implemented.
- No real keys are read or printed.
- Provider adapters can be added later behind the same artifact protocol.
- The orchestrator owns task state, queue discipline, logs, and artifact management.

