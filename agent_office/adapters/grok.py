from __future__ import annotations

import os
import shlex
import subprocess

from .base import AdapterInvocation, AdapterResult, AdapterUnavailable, AgentAdapter, mask_secrets, read_text, write_file


DEFAULT_GROK_TIMEOUT_SECONDS = 120
DEFAULT_GROK_MAX_OUTPUT_CHARS = 12000
REQUIRED_HEADINGS = [
    "# Blocking Issues",
    "# Non-blocking Issues",
    "# Missing Tests",
    "# Security Risks",
    "# Performance Risks",
    "# Verdict",
]


class GrokAdapter(AgentAdapter):
    name = "grok"

    def redteam(self, invocation: AdapterInvocation) -> AdapterResult:
        command = self._command_from_env()
        timeout = invocation.timeout_seconds or self._timeout_from_env()
        max_output_chars = self._max_output_chars_from_env()
        prompt = self._build_prompt(invocation)
        log_dir = invocation.project_root / ".ai" / "logs" / invocation.task_id
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "grok-adapter.log"
        error_path = log_dir / "grok-adapter-error.md"

        if invocation.paths.grok_review.exists():
            invocation.paths.grok_review.unlink()

        try:
            completed = subprocess.run(
                command,
                input=prompt,
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
            self._write_failure(error_path, "timeout", f"Grok command exceeded {timeout} seconds.", stdout, stderr)
            raise AdapterUnavailable(
                f"Grok adapter timed out after {timeout} seconds. Use --mock or increase --timeout."
            ) from exc
        except OSError as exc:
            message = mask_secrets(str(exc))
            self._write_failure(error_path, "execution error", message, "", "")
            raise AdapterUnavailable(f"Grok adapter could not start: {message}. Use --mock to run the safe path.") from exc

        stdout = mask_secrets(completed.stdout)
        stderr = mask_secrets(completed.stderr)
        write_file(
            log_path,
            f"""# Grok Adapter Log

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
                f"Grok adapter failed with exit code {completed.returncode}. See sanitized log in .ai/logs/{invocation.task_id}/."
            )

        if not invocation.paths.grok_review.exists():
            self._write_failure(error_path, "missing grok-review.md", "Real Grok did not write grok-review.md.", stdout, stderr)
            raise AdapterUnavailable("Real Grok completed but did not generate grok-review.md.")

        review_text = invocation.paths.grok_review.read_text(encoding="utf-8")
        if not review_text.strip():
            self._write_failure(error_path, "empty grok-review.md", "Real Grok wrote an empty grok-review.md.", stdout, stderr)
            raise AdapterUnavailable("Real Grok generated an empty grok-review.md.")

        missing = [heading for heading in REQUIRED_HEADINGS if heading not in review_text]
        if missing:
            self._write_failure(
                error_path,
                "invalid grok-review.md",
                "Missing required headings: " + ", ".join(missing),
                stdout,
                stderr,
            )
            raise AdapterUnavailable("Real Grok generated grok-review.md but required sections are missing.")

        if len(review_text) > max_output_chars:
            suffix = "\n\n[TRUNCATED BY AGENTOFFICE GROK ADAPTER]\n"
            review_text = review_text[: max(0, max_output_chars - len(suffix))] + suffix
            invocation.paths.grok_review.write_text(review_text, encoding="utf-8")

        return AdapterResult(
            "Grok real adapter completed and produced grok-review.md.",
            stdout=stdout,
            stderr=stderr,
            metadata={"log": str(log_path.relative_to(invocation.project_root))},
        )

    def _command_from_env(self) -> list[str]:
        raw = os.environ.get("AGENTOFFICE_GROK_CMD", "").strip()
        if not raw:
            raise AdapterUnavailable(
                "Grok real adapter is not configured. Set AGENTOFFICE_GROK_CMD to an executable name/path or use --mock."
            )
        if any(ch in raw for ch in "\n\r\t;&|<>`$"):
            raise AdapterUnavailable("AGENTOFFICE_GROK_CMD must be a single executable name/path without shell syntax.")
        parts = shlex.split(raw)
        if len(parts) != 1:
            raise AdapterUnavailable("AGENTOFFICE_GROK_CMD must not include arguments. Adapter arguments are controlled.")
        return parts

    def _timeout_from_env(self) -> int:
        return self._positive_int_env("AGENTOFFICE_GROK_TIMEOUT_SECONDS", DEFAULT_GROK_TIMEOUT_SECONDS)

    def _max_output_chars_from_env(self) -> int:
        return self._positive_int_env("AGENTOFFICE_GROK_MAX_OUTPUT_CHARS", DEFAULT_GROK_MAX_OUTPUT_CHARS)

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

    def _build_prompt(self, invocation: AdapterInvocation) -> str:
        review_path = self._display_path(invocation, invocation.paths.grok_review)
        brief = read_text(invocation.paths.brief, 8000)
        codex_report = read_text(invocation.paths.codex_report, 8000)
        patch_diff = read_text(invocation.paths.patch_diff, 12000)
        return f"""You are the real Grok red-team review adapter for AgentOffice task `{invocation.task_id}`.

Rules:
- Review only. Do not modify code.
- Do not generate patches.
- Do not read `.env`, key files, pem files, token files, secret files, or unrelated project directories.
- Do not access `/opt/binance-futures-local-bot`.
- Do not scan the full repository.
- Do not modify system directories such as `/etc/systemd` or `/etc/nginx`.
- Use only the task protocol files included below.
- Write the review artifact to `{review_path}`.
- The output must include exactly these top-level sections:
  - # Blocking Issues
  - # Non-blocking Issues
  - # Missing Tests
  - # Security Risks
  - # Performance Risks
  - # Verdict
- If you cannot complete safely, exit non-zero and explain why.

brief.md:
{brief}

codex-report.md:
{codex_report}

patch.diff:
```diff
{patch_diff}
```
"""

    def _display_path(self, invocation: AdapterInvocation, path) -> str:
        try:
            return str(path.relative_to(invocation.project_root))
        except ValueError:
            return str(path)

    def _write_failure(self, path, reason: str, detail: str, stdout: str, stderr: str) -> None:
        write_file(
            path,
            f"""# Grok Adapter Error

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
