# Real Agent Integration Plan

## Current Phase

AgentOffice v0.5 uses a staged real-adapter dry-run framework. P6-01 adds a controlled full dry-run orchestration command on top of that framework. All adapters default to `mode=mock`; real mode is impossible unless that specific adapter is explicitly configured with `AGENTOFFICE_<ADAPTER>_MODE=real`.

Implemented staged adapters:

- P5-02: Gemini context dry-run.
- P5-03: Codex patch-only dry-run.
- P5-04: Grok review-only dry-run.
- P5-05: Claude final-decision dry-run.

No adapter sends a real provider request while `dry_run=true`. Do not enable all real adapters at once.

P6-01 command:

```bash
python3 -m agent_office run-staged <TASK_ID> --dry-run --reset
```

This runs `new -> context -> implement -> redteam -> summarize -> judge -> status`. It defaults every stage to mock and can exercise only one explicitly selected real dry-run adapter per invocation.

## Adapter Boundary

AgentOffice owns the state machine, task protocol, and safe artifact paths. Provider-specific code belongs behind adapter boundaries and must not print secrets or write outside the allowed runtime directories.

```text
AgentOffice CLI
  -> adapter mode registry
    -> mock adapter
    -> staged real dry-run adapter
      -> ignored .ai/<adapter>/ artifacts
```

## Environment Gates

Doctor checks only whether variables are present; it does not print values and does not read `.env`.

- Gemini: `GEMINI_API_KEY`
- Codex: `OPENAI_API_KEY`
- Grok: `XAI_API_KEY`
- Claude: `ANTHROPIC_API_KEY`

Every real adapter rejects non-dry-run mode unless `AGENTOFFICE_<ADAPTER>_ALLOW_NON_DRY_RUN=true`. P5-05 still does not implement real Claude network transport.

## Stage Responsibilities

Gemini context dry-run:

- Reads task brief and safe project context.
- Writes `.ai/context/gemini-context.md`.
- Does not modify code or make final decisions.

Codex patch-only dry-run:

- Reads task brief, Gemini context, and safe project context.
- Writes `.ai/codex/patch.diff`, `.ai/codex/codex-report.md`, and `.ai/codex/metadata.json`.
- Does not apply patches, execute commands, or commit.

Grok review-only dry-run:

- Reads staged Gemini/Codex artifacts.
- Writes `.ai/grok/redteam-report.md` and `.ai/grok/metadata.json`.
- Does not modify source files or generate patches.

Claude final-decision dry-run:

- Reads bounded final/staged evidence.
- Writes `.ai/claude/final-judge.md` and `.ai/claude/metadata.json`.
- Makes a final review decision only.
- Does not apply changes, execute commands, or send a real Anthropic request.

## Safe Enablement Examples

Gemini:

```bash
export AGENTOFFICE_GEMINI_MODE=real
export AGENTOFFICE_GEMINI_DRY_RUN=true
export GEMINI_API_KEY=replace-with-real-key-outside-git
python3 -m agent_office context <TASK_ID> --real --adapter gemini --dry-run --timeout 120
```

Codex:

```bash
export AGENTOFFICE_CODEX_MODE=real
export AGENTOFFICE_CODEX_DRY_RUN=true
export OPENAI_API_KEY=replace-with-real-key-outside-git
python3 -m agent_office implement <TASK_ID> --real --adapter codex --dry-run --timeout 1200
```

Grok:

```bash
export AGENTOFFICE_GROK_MODE=real
export AGENTOFFICE_GROK_DRY_RUN=true
export XAI_API_KEY=replace-with-real-key-outside-git
python3 -m agent_office redteam <TASK_ID> --real --adapter grok --dry-run --timeout 120
```

Claude:

```bash
export AGENTOFFICE_CLAUDE_MODE=real
export AGENTOFFICE_CLAUDE_DRY_RUN=true
export ANTHROPIC_API_KEY=replace-with-real-key-outside-git
python3 -m agent_office judge <TASK_ID> --real --adapter claude --dry-run --timeout 120
```

## Next Phases

1. Review P6-01 staged full dry-run orchestration in branch `phase6/staged-full-dry-run`.
2. Add mocked HTTP/client boundaries before any non-dry-run provider call.
3. Add operator approval gates for any future patch application or real network request.
4. Keep `scripts/verify.sh` and mock workflow as the baseline regression checks.
