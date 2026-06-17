from __future__ import annotations

import os
import re
import shlex
import subprocess

from .base import AdapterInvocation, AdapterResult, AdapterUnavailable, AgentAdapter, mask_secrets, read_text, write_file


DEFAULT_CLAUDE_TIMEOUT_SECONDS = 120
DEFAULT_CLAUDE_MAX_INPUT_CHARS = 12000
DEFAULT_CLAUDE_MAX_OUTPUT_CHARS = 8000
DECISION_RE = re.compile(r"(?im)^DECISION:\s*(APPROVE|REQUEST_CHANGES|REJECT)\s*$")
DECISION_TO_STATE = {
    "APPROVE": "APPROVED",
    "REQUEST_CHANGES": "REQUEST_CHANGES",
    "REJECT": "REJECTED",
}


class ClaudeAdapter(AgentAdapter):
    name = "claude"

    def final(self, invocation: AdapterInvocation) -> AdapterResult:
        command = self._command_from_env()
        timeout = invocation.timeout_seconds or self._timeout_from_env()
        max_input_chars = self._max_input_chars_from_env()
        max_output_chars = self._max_output_chars_from_env()
        final_text = read_text(invocation.paths.final_for_claude)
        log_dir = invocation.project_root / ".ai" / "logs" / invocation.task_id
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "claude-adapter.log"
        error_path = log_dir / "claude-adapter-error.md"

        if not final_text.strip():
            self._write_failure(error_path, "missing final-for-claude.md", "Claude input is missing or empty.", "", "")
            raise AdapterUnavailable("Claude input final-for-claude.md is missing or empty.")
        if len(final_text) > max_input_chars:
            self._write_failure(
                error_path,
                "input too large",
                f"final-for-claude.md is {len(final_text)} chars; max is {max_input_chars}. Run summarize with stronger compression.",
                "",
                "",
            )
            raise AdapterUnavailable(
                "Claude input exceeds AGENTOFFICE_CLAUDE_MAX_INPUT_CHARS. Run summarize with stronger compression."
            )

        if invocation.paths.claude_decision.exists():
            invocation.paths.claude_decision.unlink()

        try:
            completed = subprocess.run(
                command,
                input=self._build_prompt(invocation, final_text),
                text=True,
                capture_output=True,
                cwd=str(invocation.project_root),
                timeout=timeout,
                shell=False,
                env=os.environ.copy(),
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = mask_secrets(exc.stdout or "")
            stderr = mask_secrets(exc.stderr or "")
            self._write_failure(error_path, "timeout", f"Claude command exceeded {timeout} seconds.", stdout, stderr)
            raise AdapterUnavailable(
                f"Claude adapter timed out after {timeout} seconds. Use --mock or increase --timeout."
            ) from exc
        except OSError as exc:
            message = mask_secrets(str(exc))
            self._write_failure(error_path, "execution error", message, "", "")
            raise AdapterUnavailable(f"Claude adapter could not start: {message}. Use --mock to run the safe path.") from exc

        stdout = mask_secrets(completed.stdout)
        stderr = mask_secrets(completed.stderr)
        write_file(
            log_path,
            f"""# Claude Adapter Log

Command: `{command[0]}`
Return code: {completed.returncode}

## Stdout

```text
{stdout[:8000]}
```

## Stderr

```text
{stderr[:8000]}
```
""",
        )

        if completed.returncode != 0:
            self._write_failure(error_path, "non-zero exit", f"Return code: {completed.returncode}", stdout, stderr)
            raise AdapterUnavailable(
                f"Claude adapter failed with exit code {completed.returncode}. See sanitized log in .ai/logs/{invocation.task_id}/."
            )

        if not invocation.paths.claude_decision.exists():
            self._write_failure(error_path, "missing claude-decision.md", "Real Claude did not write claude-decision.md.", stdout, stderr)
            raise AdapterUnavailable("Real Claude completed but did not generate claude-decision.md.")

        decision_text = invocation.paths.claude_decision.read_text(encoding="utf-8")
        if not decision_text.strip():
            self._write_failure(error_path, "empty claude-decision.md", "Real Claude wrote an empty claude-decision.md.", stdout, stderr)
            raise AdapterUnavailable("Real Claude generated an empty claude-decision.md.")
        if len(decision_text) > max_output_chars:
            self._write_failure(
                error_path,
                "output too large",
                f"claude-decision.md is {len(decision_text)} chars; max is {max_output_chars}.",
                stdout,
                stderr,
            )
            raise AdapterUnavailable("Real Claude generated claude-decision.md that exceeds AGENTOFFICE_CLAUDE_MAX_OUTPUT_CHARS.")

        match = DECISION_RE.search(decision_text)
        if not match:
            self._write_failure(error_path, "missing decision", "claude-decision.md does not contain DECISION: APPROVE | REQUEST_CHANGES | REJECT.", stdout, stderr)
            raise AdapterUnavailable("Real Claude generated claude-decision.md without a valid DECISION field.")

        decision = DECISION_TO_STATE[match.group(1)]
        return AdapterResult(
            f"Claude real adapter decision: {decision}.",
            decision=decision,
            stdout=stdout,
            stderr=stderr,
            metadata={"log": str(log_path.relative_to(invocation.project_root))},
        )

    def _command_from_env(self) -> list[str]:
        raw = os.environ.get("AGENTOFFICE_CLAUDE_CMD", "").strip()
        if not raw:
            raise AdapterUnavailable(
                "Claude real adapter is not configured. Set AGENTOFFICE_CLAUDE_CMD to an executable name/path or use --mock."
            )
        if any(ch in raw for ch in "\n\r\t;&|<>`$"):
            raise AdapterUnavailable("AGENTOFFICE_CLAUDE_CMD must be a single executable name/path without shell syntax.")
        parts = shlex.split(raw)
        if len(parts) != 1:
            raise AdapterUnavailable("AGENTOFFICE_CLAUDE_CMD must not include arguments. Adapter arguments are controlled.")
        return parts

    def _timeout_from_env(self) -> int:
        return self._positive_int_env("AGENTOFFICE_CLAUDE_TIMEOUT_SECONDS", DEFAULT_CLAUDE_TIMEOUT_SECONDS)

    def _max_input_chars_from_env(self) -> int:
        return self._positive_int_env("AGENTOFFICE_CLAUDE_MAX_INPUT_CHARS", DEFAULT_CLAUDE_MAX_INPUT_CHARS)

    def _max_output_chars_from_env(self) -> int:
        return self._positive_int_env("AGENTOFFICE_CLAUDE_MAX_OUTPUT_CHARS", DEFAULT_CLAUDE_MAX_OUTPUT_CHARS)

    def _positive_int_env(self, name: str, default: int) -> int:
        raw = os.environ.get(name, "").strip()
        if not raw:
            return default
        try:
            value = int(raw)
        except ValueError as exc:
            raise AdapterUnavailable(f"{name} must be an integer.") from exc
        if value <= 0:
            raise AdapterUnavailable(f"{name} must be positive.")
        return value

    def _build_prompt(self, invocation: AdapterInvocation, final_text: str) -> str:
        decision_path = self._display_path(invocation, invocation.paths.claude_decision)
        return f"""You are the real Claude final judge adapter for AgentOffice task `{invocation.task_id}`.

Rules:
- Final judge only. Do not modify code.
- Read only the compressed input included below from final-for-claude.md.
- Do not read the repository, `.env`, logs, patch.diff, codex-report.md, grok-review.md, or gemini-context.md.
- Do not generate patches.
- Write the final decision artifact to `{decision_path}`.
- The output must include:
  - DECISION: APPROVE | REQUEST_CHANGES | REJECT
  - REASONS:
  - MUST_FIX:
  - NICE_TO_HAVE:
  - NEXT_ACTION_FOR_CODEX:
- If you cannot complete safely, exit non-zero and explain why.

final-for-claude.md:
{final_text}
"""

    def _display_path(self, invocation: AdapterInvocation, path) -> str:
        try:
            return str(path.relative_to(invocation.project_root))
        except ValueError:
            return str(path)

    def _write_failure(self, path, reason: str, detail: str, stdout: str, stderr: str) -> None:
        write_file(
            path,
            f"""# Claude Adapter Error

Reason: {mask_secrets(reason)}

Detail: {mask_secrets(detail)}

## Sanitized Stdout

```text
{mask_secrets(stdout)[:8000]}
```

## Sanitized Stderr

```text
{mask_secrets(stderr)[:8000]}
```
""",
        )
