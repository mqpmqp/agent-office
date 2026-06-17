from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

from .base import AdapterInvocation, AdapterResult, AdapterUnavailable, AgentAdapter, mask_secrets, read_text, write_file


DEFAULT_CODEX_TIMEOUT_SECONDS = 1200


class CodexAdapter(AgentAdapter):
    name = "codex"

    def implement(self, invocation: AdapterInvocation) -> AdapterResult:
        command = self._command_from_env()
        timeout = invocation.timeout_seconds or self._timeout_from_env()
        prompt = self._build_prompt(invocation)
        log_dir = invocation.project_root / ".ai" / "logs" / invocation.task_id
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "codex-adapter.log"
        error_path = log_dir / "codex-adapter-error.md"

        for stale_artifact in (invocation.paths.codex_report, invocation.paths.patch_diff):
            if stale_artifact.exists():
                stale_artifact.unlink()

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
            self._write_failure(error_path, "timeout", f"Codex command exceeded {timeout} seconds.", stdout, stderr)
            raise AdapterUnavailable(
                f"Codex adapter timed out after {timeout} seconds. Use --mock or increase --timeout."
            ) from exc
        except OSError as exc:
            message = mask_secrets(str(exc))
            self._write_failure(error_path, "execution error", message, "", "")
            raise AdapterUnavailable(f"Codex adapter could not start: {message}. Use --mock to run the safe path.") from exc

        stdout = mask_secrets(completed.stdout)
        stderr = mask_secrets(completed.stderr)
        write_file(
            log_path,
            f"""# Codex Adapter Log

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
                f"Codex adapter failed with exit code {completed.returncode}. See sanitized log in .ai/logs/{invocation.task_id}/."
            )

        if not invocation.paths.codex_report.exists():
            self._write_failure(error_path, "missing codex-report.md", "Real Codex did not write codex-report.md.", stdout, stderr)
            raise AdapterUnavailable("Real Codex completed but did not generate codex-report.md.")
        if not invocation.paths.patch_diff.exists() or invocation.paths.patch_diff.stat().st_size == 0:
            self._write_failure(error_path, "missing patch.diff", "Real Codex did not write a non-empty patch.diff.", stdout, stderr)
            raise AdapterUnavailable("Real Codex completed but did not generate a non-empty patch.diff.")

        return AdapterResult(
            "Codex real adapter completed and produced codex-report.md plus patch.diff.",
            stdout=stdout,
            stderr=stderr,
            metadata={"log": str(log_path.relative_to(invocation.project_root))},
        )

    def _command_from_env(self) -> list[str]:
        raw = os.environ.get("AGENTOFFICE_CODEX_CMD", "").strip()
        if not raw:
            raise AdapterUnavailable(
                "Codex real adapter is not configured. Set AGENTOFFICE_CODEX_CMD to an executable name/path or use --mock."
            )
        if any(ch in raw for ch in "\n\r\t;&|<>`$"):
            raise AdapterUnavailable("AGENTOFFICE_CODEX_CMD must be a single executable name/path without shell syntax.")
        parts = shlex.split(raw)
        if len(parts) != 1:
            raise AdapterUnavailable("AGENTOFFICE_CODEX_CMD must not include arguments. Adapter arguments are controlled.")
        return parts

    def _timeout_from_env(self) -> int:
        raw = os.environ.get("AGENTOFFICE_CODEX_TIMEOUT_SECONDS", "").strip()
        if not raw:
            return DEFAULT_CODEX_TIMEOUT_SECONDS
        try:
            value = int(raw)
        except ValueError as exc:
            raise AdapterUnavailable("AGENTOFFICE_CODEX_TIMEOUT_SECONDS must be an integer.") from exc
        if value <= 0:
            raise AdapterUnavailable("AGENTOFFICE_CODEX_TIMEOUT_SECONDS must be positive.")
        return value

    def _build_prompt(self, invocation: AdapterInvocation) -> str:
        agents_path = invocation.project_root / "AGENTS.md"
        agents_section = read_text(agents_path, 4000) if agents_path.exists() else "(AGENTS.md not present.)"
        brief = read_text(invocation.paths.brief, 8000)
        gemini = read_text(invocation.paths.gemini_context, 8000)
        report_path = self._display_path(invocation.project_root, invocation.paths.codex_report)
        patch_path = self._display_path(invocation.project_root, invocation.paths.patch_diff)
        return f"""You are the real Codex implement adapter for AgentOffice task `{invocation.task_id}`.

Rules:
- Work only inside this project root: {invocation.project_root}
- Do not read `.env`, key files, tokens, secrets, or unrelated project directories.
- Do not access `/opt/binance-futures-local-bot`.
- Do not modify system directories such as `/etc/systemd` or `/etc/nginx`.
- Use the task protocol files as the source of truth.
- If you cannot complete the implementation safely, exit non-zero and explain why.

Required outputs:
- Write a concise implementation report to `{report_path}`.
- Write a non-empty unified diff to `{patch_path}`.

AGENTS.md:
{agents_section}

brief.md:
{brief}

gemini-context.md:
{gemini}
"""

    def _display_path(self, project_root: Path, path: Path) -> str:
        try:
            return str(path.relative_to(project_root))
        except ValueError:
            return str(path)

    def _write_failure(self, path: Path, reason: str, detail: str, stdout: str, stderr: str) -> None:
        write_file(
            path,
            f"""# Codex Adapter Error

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

