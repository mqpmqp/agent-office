# Cost-Aware Provider Profiles

P6-02 separates AgentOffice roles from vendor identities. The existing workflow names came from the first implementation path, but the durable model is role-based.

AgentOffice roles are not vendor identities. A role describes work that must happen in the file protocol. A provider describes who or what performs that work.

## Canonical Roles

AgentOffice uses four canonical roles:

- `context`: gather and compress task context.
- `implement`: produce implementation artifacts or patch proposals.
- `review`: red-team the proposed change and identify risks.
- `judge`: make the final approval, request changes, or reject decision.

These roles map onto the existing file protocol without changing the state machine.

## Built-In Profiles

### lowest-cost

This is the default profile.

```text
context: chatgpt-manual
implement: codex
review: chatgpt-manual
judge: chatgpt-manual
```

The lowest-cost engineering path is:

```text
ChatGPT manual context/review/judge + Codex implementation + AgentOffice file protocol
```

`chatgpt-manual` means a human operator uses ChatGPT Pro manually and copies bounded results into the AgentOffice file protocol. It is not OpenAI API usage, does not require an OpenAI API key, and does not send provider requests from AgentOffice.

### mock-ci

This profile is for repeatable CI and local smoke tests.

```text
context: mock
implement: mock
review: mock
judge: mock
```

### multi-vendor

This profile preserves the optional multi-vendor shape from earlier phases.

```text
context: gemini
implement: codex
review: grok
judge: claude
```

Gemini, Claude, and Grok are optional providers, not required subscriptions. They can be useful for experimentation, but AgentOffice must not require them for the default engineering path.

## Profile Visibility CLI

P6-03 adds a read-only CLI for inspecting the local profile registry:

```bash
python3 -m agent_office profiles
python3 -m agent_office profiles --name lowest-cost
python3 -m agent_office profiles --json
```

The command prints the default profile, available built-in profile names, and role-to-provider mappings. JSON output is intended for local validation and scripting.

This visibility command does not select a runtime profile, execute adapters, probe credentials, read `.env`, or send provider requests.

## Profile Plan Preview

P6-04 adds a read-only plan preview for one selected profile:

```bash
python3 -m agent_office profiles --name lowest-cost --plan
python3 -m agent_office profiles --name lowest-cost --plan --json
```

`--plan` requires `--name`. The preview shows the selected profile, the default profile, whether the selected profile is the default, the canonical role order, each role's provider, and a static local execution category.

Execution categories are static metadata only:

```text
chatgpt-manual -> manual
codex -> local-cli
mock -> mock
gemini -> optional-provider
grok -> optional-provider
claude -> optional-provider
openai-api -> future-api
```

The plan preview always reports:

```text
execution_enabled: false
provider_calls: false
artifact_writes: false
```

It does not select a runtime profile, probe installed CLIs, check credentials, read `.env`, send provider requests, import provider SDKs, write files, or create `.ai/` runtime artifacts.

## OpenAI API Provider

`openai-api` is an allowed provider name for future optional work. It is disabled by default and must not be used as the default provider in P6-02.

P6-02 does not implement OpenAI API transport, does not call any provider API, and does not add provider SDK imports.

## Runtime Boundary

P6-02 does not change runtime behavior.

- `run-staged` behavior is unchanged.
- Adapter mode defaults are unchanged.
- Mock verification remains the baseline.
- No `.env` file is read.
- No network request is sent by the provider profile registry.
- No runtime files are created under `.ai/`.

The profile registry is local metadata only. It is intended to guide future planning and operator routing before any P6-03 implementation work begins.

P6-03 keeps that boundary: profile visibility is reporting only. Runtime profile selection remains future work.

P6-04 keeps that boundary: profile plan preview is local static reporting only. Runtime profile selection remains future work.
