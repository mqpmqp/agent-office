# AgentOffice beta v0.5

Tag:

```text
beta-v0.5-four-real-adapter-dry-run-loop
```

Commit:

```text
8c97074 add Claude final judge dry-run phase 5
```

## Definition

beta v0.5 is the AgentOffice four real-adapter staged dry-run framework.

- Gemini real context: dry-run only.
- Codex real implement: patch-only dry-run.
- Grok real redteam: review-only dry-run.
- Claude real final judge: final-decision dry-run.

All adapters default to mock mode.

## Baseline

v0.4 established the four-agent loop:

```text
Gemini -> Codex -> Grok -> Claude
```

The v0.4 loop remains verifiable in mock mode.

## Phase 5 Milestones

P5-01 adapter registry:

- Added staged adapter mode config.
- Added dry-run, fallback, env validation, and capability fields.
- Defaulted all adapters to mock.

P5-02 Gemini context dry-run:

- Generates `.ai/context/gemini-context.md`.
- Does not modify code or send a real request.

P5-03 Codex patch-only dry-run:

- Generates `.ai/codex/patch.diff`, `.ai/codex/codex-report.md`, and `.ai/codex/metadata.json`.
- Does not apply patches or mutate source.

P5-04 Grok redteam dry-run:

- Generates `.ai/grok/redteam-report.md` and `.ai/grok/metadata.json`.
- Reviews only staged artifacts.

P5-05 Claude final judge dry-run:

- Generates `.ai/claude/final-judge.md` and `.ai/claude/metadata.json`.
- Makes a final decision only.

## Safety Properties

- No real API calls by default.
- Real mode requires explicit env and explicit adapter mode.
- Non-dry-run is rejected unless `allow_non_dry_run=true`.
- Real adapters do not mutate source files.
- Codex, Grok, and Claude do not apply patches.
- Doctor does not read `.env` and does not print secrets.
- Runtime artifacts under `.ai/` are ignored.

## Verification Status

Expected v0.5 verification:

```bash
python3 -m compileall -q agent_office
python3 -m unittest discover -s tests -p 'test_*.py'
python3 -m agent_office.doctor --adapters
python3 -m agent_office doctor --adapters --json
python3 -m agent_office run-demo DEMO-V0-5-FINAL --mock --reset
bash scripts/smoke-test.sh DEMO-V0-5-FINAL-SMOKE
bash scripts/verify.sh
git status
```

Expected results:

- 43 tests OK.
- `smoke test ok`.
- `verify ok`.
- all adapters default `mock/status=ok`.
- working tree clean.

## Backup

v0.5 backup path:

```text
/opt/agent-office-beta-v0.5-four-real-adapter-dry-run-2026-06-18-0818.tar.gz
```

## Next Phase Recommendations

- Build skills/capability packaging for operator workflows.
- Keep v0.5 tags immutable.
- Add mocked transport boundaries before any non-dry-run provider API call.
- Do not enable all real adapters at once.
- Keep mock verification as the release gate.
