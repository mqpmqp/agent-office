from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

from .base import AdapterInvocation, AdapterResult, AdapterUnavailable, AgentAdapter, mask_secrets, read_text, write_file


DEFAULT_GEMINI_TIMEOUT_SECONDS = 120
DEFAULT_GEMINI_MAX_FILES = 80
DEFAULT_GEMINI_MAX_OUTPUT_CHARS = 12000
REQUIRED_HEADINGS = [
    "# Relevant Files",
    "# Why These Files Matter",
    "# Test Entry Points",
    "# Implementation Hints",
    "# Risks",
]
SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "logs",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}
SKIP_AI_PARTS = {
    (".ai", "tasks"),
    (".ai", "logs"),
    (".ai", "tmp"),
}
DENY_FILE_MARKERS = (".env", ".key", ".pem", "token", "secret")
DOC_EXTENSIONS = {".md", ".txt"}


class GeminiAdapter(AgentAdapter):
    name = "gemini"

    def context(self, invocation: AdapterInvocation) -> AdapterResult:
        command = self._command_from_env()
        timeout = invocation.timeout_seconds or self._timeout_from_env()
        max_files = self._max_files_from_env()
        max_output_chars = self._max_output_chars_from_env()
        prompt = self._build_prompt(invocation, max_files)
        log_dir = invocation.project_root / ".ai" / "logs" / invocation.task_id
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "gemini-adapter.log"
        error_path = log_dir / "gemini-adapter-error.md"

        if invocation.paths.gemini_context.exists():
            invocation.paths.gemini_context.unlink()

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
            self._write_failure(error_path, "timeout", f"Gemini command exceeded {timeout} seconds.", stdout, stderr)
            raise AdapterUnavailable(
                f"Gemini adapter timed out after {timeout} seconds. Use --mock or increase --timeout."
            ) from exc
        except OSError as exc:
            message = mask_secrets(str(exc))
            self._write_failure(error_path, "execution error", message, "", "")
            raise AdapterUnavailable(f"Gemini adapter could not start: {message}. Use --mock to run the safe path.") from exc

        stdout = mask_secrets(completed.stdout)
        stderr = mask_secrets(completed.stderr)
        write_file(
            log_path,
            f"""# Gemini Adapter Log

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
                f"Gemini adapter failed with exit code {completed.returncode}. See sanitized log in .ai/logs/{invocation.task_id}/."
            )

        if not invocation.paths.gemini_context.exists():
            self._write_failure(error_path, "missing gemini-context.md", "Real Gemini did not write gemini-context.md.", stdout, stderr)
            raise AdapterUnavailable("Real Gemini completed but did not generate gemini-context.md.")

        context_text = invocation.paths.gemini_context.read_text(encoding="utf-8")
        if not context_text.strip():
            self._write_failure(error_path, "empty gemini-context.md", "Real Gemini wrote an empty gemini-context.md.", stdout, stderr)
            raise AdapterUnavailable("Real Gemini generated an empty gemini-context.md.")

        missing = [heading for heading in REQUIRED_HEADINGS if heading not in context_text]
        if missing:
            self._write_failure(
                error_path,
                "invalid gemini-context.md",
                "Missing required headings: " + ", ".join(missing),
                stdout,
                stderr,
            )
            raise AdapterUnavailable("Real Gemini generated gemini-context.md but required sections are missing.")

        if len(context_text) > max_output_chars:
            suffix = "\n\n[TRUNCATED BY AGENTOFFICE GEMINI ADAPTER]\n"
            context_text = context_text[: max(0, max_output_chars - len(suffix))] + suffix
            invocation.paths.gemini_context.write_text(context_text, encoding="utf-8")

        return AdapterResult(
            "Gemini real adapter completed and produced gemini-context.md.",
            stdout=stdout,
            stderr=stderr,
            metadata={"log": str(log_path.relative_to(invocation.project_root))},
        )

    def _command_from_env(self) -> list[str]:
        raw = os.environ.get("AGENTOFFICE_GEMINI_CMD", "").strip()
        if not raw:
            raise AdapterUnavailable(
                "Gemini real adapter is not configured. Set AGENTOFFICE_GEMINI_CMD to an executable name/path or use --mock."
            )
        if any(ch in raw for ch in "\n\r\t;&|<>`$"):
            raise AdapterUnavailable("AGENTOFFICE_GEMINI_CMD must be a single executable name/path without shell syntax.")
        parts = shlex.split(raw)
        if len(parts) != 1:
            raise AdapterUnavailable("AGENTOFFICE_GEMINI_CMD must not include arguments. Adapter arguments are controlled.")
        return parts

    def _timeout_from_env(self) -> int:
        return self._positive_int_env("AGENTOFFICE_GEMINI_TIMEOUT_SECONDS", DEFAULT_GEMINI_TIMEOUT_SECONDS)

    def _max_files_from_env(self) -> int:
        return self._positive_int_env("AGENTOFFICE_GEMINI_MAX_FILES", DEFAULT_GEMINI_MAX_FILES)

    def _max_output_chars_from_env(self) -> int:
        return self._positive_int_env("AGENTOFFICE_GEMINI_MAX_OUTPUT_CHARS", DEFAULT_GEMINI_MAX_OUTPUT_CHARS)

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

    def _build_prompt(self, invocation: AdapterInvocation, max_files: int) -> str:
        output_path = self._display_path(invocation.project_root, invocation.paths.gemini_context)
        file_tree = "\n".join(f"- {path}" for path in self._project_file_tree(invocation.project_root, max_files))
        docs = self._allowed_context_docs(invocation.project_root)
        brief = read_text(invocation.paths.brief, 8000)
        return f"""You are the real Gemini context adapter for AgentOffice task `{invocation.task_id}`.

Rules:
- Context only. Do not modify code.
- Work only inside this project root: {invocation.project_root}
- Do not read `.env`, key files, pem files, token files, secret files, or unrelated project directories.
- Do not access `/opt/binance-futures-local-bot`.
- Do not modify system directories such as `/etc/systemd` or `/etc/nginx`.
- Write the context artifact to `{output_path}`.
- The output must be concise and include exactly these top-level sections:
  - # Relevant Files
  - # Why These Files Matter
  - # Test Entry Points
  - # Implementation Hints
  - # Risks
- If you cannot complete safely, exit non-zero and explain why.

Task brief:
{brief}

Project file tree summary:
{file_tree}

Allowed repository context:
{docs}
"""

    def _project_file_tree(self, project_root: Path, max_files: int) -> list[str]:
        paths: list[str] = []
        for path in sorted(project_root.rglob("*")):
            if path.is_dir():
                continue
            if not self._is_safe_path(project_root, path):
                continue
            paths.append(self._display_path(project_root, path))
            if len(paths) >= max_files:
                paths.append(f"...[truncated at {max_files} files]...")
                break
        return paths

    def _allowed_context_docs(self, project_root: Path) -> str:
        candidates: list[Path] = []
        for name in ("AGENTS.md", "README.md"):
            path = project_root / name
            if path.exists() and self._is_safe_path(project_root, path):
                candidates.append(path)
        docs_root = project_root / "docs"
        if docs_root.exists():
            for path in sorted(docs_root.rglob("*")):
                if path.is_file() and path.suffix.lower() in DOC_EXTENSIONS and self._is_safe_path(project_root, path):
                    candidates.append(path)

        sections: list[str] = []
        for path in candidates[:20]:
            rel = self._display_path(project_root, path)
            sections.append(f"\n## {rel}\n\n{read_text(path, 4000)}")
        return "\n".join(sections) if sections else "(No allowed context docs found.)"

    def _is_safe_path(self, project_root: Path, path: Path) -> bool:
        try:
            rel = path.relative_to(project_root)
        except ValueError:
            return False
        parts = rel.parts
        if any(part in SKIP_DIRS for part in parts[:-1]):
            return False
        if len(parts) >= 2 and parts[:2] in SKIP_AI_PARTS:
            return False
        lower_name = path.name.lower()
        if lower_name == ".env" or lower_name.startswith(".env."):
            return False
        if any(marker in lower_name for marker in DENY_FILE_MARKERS):
            return False
        return True

    def _display_path(self, project_root: Path, path: Path) -> str:
        try:
            return str(path.relative_to(project_root))
        except ValueError:
            return str(path)

    def _write_failure(self, path: Path, reason: str, detail: str, stdout: str, stderr: str) -> None:
        write_file(
            path,
            f"""# Gemini Adapter Error

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
