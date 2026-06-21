# Skills Direction Correction

This note corrects the Phase 6 direction after `phase6/skills-registry`.

## Correct Interpretation

The six packaged skills are Codex operator skills. They are intended to help the human/Codex development workflow around AgentOffice:

- `superpowers-engineering`: better engineering process.
- `openai-business-apps`: business workflow routing when relevant connectors exist.
- `claude-mem`: local durable memory for project handoff.
- `agent-reach-research`: public research workflow when tools can access sources.
- `gitnexus-code-map`: repository understanding before refactors.
- `humanizer-zh`: Chinese documentation polish.

They are not part of the AgentOffice runtime protocol.

## What Should Not Happen

- Do not treat these skills as a fifth AgentOffice stage.
- Do not make the v0.5 adapter loop depend on local Codex skills.
- Do not commit local `.codex/skills` folders into the AgentOffice repository.
- Do not merge or tag `phase6/skills-registry` as a release line unless the user explicitly asks for runtime skill management.

## Correct Mainline

AgentOffice remains a four-agent office:

```text
Gemini context -> Codex implement -> Grok redteam -> Claude final judge
```

The stable baseline remains:

```text
beta-v0.5-four-real-adapter-dry-run-loop
```

Future development should return to AgentOffice core capabilities:

- controlled end-to-end staged dry runs
- mocked provider transport boundaries
- patch approval and apply workflow
- task queue and locking
- GitHub PR workflow
- dashboard or operator UI

## Branch Guidance

- Keep `phase6/skills-packaging` as documentation for local Codex skill wrappers.
- Keep `phase6/skills-registry` as experimental and do not merge it by default.
- Start the next core AgentOffice branch from `beta-v0.5-four-real-adapter-dry-run-loop` or from `phase6/skills-packaging`, depending on whether the local skills documentation should be retained.
