from __future__ import annotations

from .base import AdapterInvocation, AdapterResult, AgentAdapter, read_text, write_file


class MockAdapter(AgentAdapter):
    name = "mock"

    def context(self, invocation: AdapterInvocation) -> AdapterResult:
        write_file(
            invocation.paths.gemini_context,
            f"""# Gemini Context Summary

Mode: mock

## Compressed Repository Context

- Project uses file-based task collaboration under `.ai/tasks/{invocation.task_id}/`.
- No free-form AI chat is allowed; every agent has a fixed job and fixed artifact.
- Claude token budget is protected by forcing Claude to read only `final-for-claude.md`.

## Relevant Constraints

- Max rework rounds: {invocation.max_rework_rounds}
- Final summary limit: {invocation.final_for_claude_limit} characters
- Real secrets must not be read or printed.
""",
        )
        return AdapterResult("Gemini mock context generated.")

    def implement(self, invocation: AdapterInvocation) -> AdapterResult:
        write_file(
            invocation.paths.codex_report,
            f"""# Codex Implementation Report

Mode: mock

## Work Completed

- Created deterministic MVP artifacts for task `{invocation.task_id}`.
- Preserved the task directory protocol.
- Did not call external providers or read secrets.

## Verification

- Mock implementation completed.
- Patch artifact generated.
""",
        )
        write_file(
            invocation.paths.patch_diff,
            f"""diff --git a/mock-target.txt b/mock-target.txt
new file mode 100644
--- /dev/null
+++ b/mock-target.txt
@@ -0,0 +1,3 @@
+Task: {invocation.task_id}
+Implemented-by: Codex mock
+Status: deterministic MVP artifact
""",
        )
        return AdapterResult("Codex mock implementation generated.")

    def redteam(self, invocation: AdapterInvocation) -> AdapterResult:
        write_file(
            invocation.paths.grok_review,
            """# Grok Build Red-Team Review

Mode: mock

## Verdict

PASS_FOR_CLAUDE_SUMMARY

## Findings

- No uncontrolled multi-agent chat detected.
- Required artifacts are present.
- Claude is restricted to the final compressed artifact.
- No secret access is required in mock mode.

## Residual Risks

- Real provider adapters are intentionally absent in the MVP.
- Production use needs queue locking and provider-specific authentication hardening.
""",
        )
        return AdapterResult("Grok Build mock red-team review generated.")

    def final(self, invocation: AdapterInvocation) -> AdapterResult:
        final_text = read_text(invocation.paths.final_for_claude)
        decision = "APPROVED"
        if "FORCE_REQUEST_CHANGES" in final_text:
            decision = "REQUEST_CHANGES"
        elif "FORCE_REJECT" in final_text:
            decision = "REJECTED"
        write_file(
            invocation.paths.claude_decision,
            f"""# Claude Decision

Mode: mock

Decision: {decision}

## Scope Read By Claude

- Read: `final-for-claude.md`
- Did not read: full repository
- Did not read: full logs
- Did not read: full diff

## Rationale

The compressed artifact was sufficient for a mock MVP decision.
""",
        )
        return AdapterResult(f"Claude mock decision: {decision}.", decision=decision)

