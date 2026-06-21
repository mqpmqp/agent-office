# Skills Packaging

AgentOffice v0.6 starts a skills packaging layer for operator and agent workflows. These skills are local Codex skill wrappers installed under:

```text
C:\Users\Administrator\.codex\skills\
```

They are workflow wrappers, not vendored copies of third-party repositories. They do not include external project code, credentials, or platform tokens.

## Packaged Skills

### superpowers-engineering

Purpose: senior engineering workflow for non-trivial code changes.

Use for:

- requirement breakdown
- codebase inspection
- implementation planning
- test-first or test-alongside development
- final self-review

### openai-business-apps

Purpose: role-based routing for business workflows.

Use for:

- data analysis planning
- CRM and sales operations workflows
- research synthesis
- content strategy
- presentation and document workflows

This skill checks available connectors/tools before claiming app access.

### claude-mem

Purpose: sanitized local project memory.

Includes:

```text
scripts/memory.py
```

Default memory store:

```text
~/.codex/memory/claude-mem.jsonl
```

It masks token/key/secret-like values before writing memory entries.

### agent-reach-research

Purpose: public multi-platform research workflow.

Use for:

- user feedback synthesis
- trend discovery
- competitor and creator research
- platform-specific discourse summaries

It only uses platforms that are actually available through tools, connectors, browser access, or user-provided exports. It must not invent access to Twitter, Reddit, YouTube, Xiaohongshu, Bilibili, WeChat, or any other platform.

### gitnexus-code-map

Purpose: repository code mapping before refactors or deep debugging.

Includes:

```text
scripts/build_code_map.py
```

The script scans safe source files, skips secret/runtime directories, and writes a Markdown code map.

### humanizer-zh

Purpose: Chinese editing pass that removes AI-like tone and improves readability while preserving facts and commands.

Use for:

- README and docs polishing
- release notes
- operator instructions
- Chinese public copy

## Validation

Each skill was validated with:

```text
quick_validate.py
```

The two bundled scripts were smoke-tested:

- `claude-mem/scripts/memory.py`
- `gitnexus-code-map/scripts/build_code_map.py`

## Safety Notes

- Skills do not store or print secrets.
- Skills do not grant external platform access by themselves.
- Platform access still depends on installed connectors, tools, browser state, or operator-provided exports.
- AgentOffice runtime behavior is unchanged by these local skills.
