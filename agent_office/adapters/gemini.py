from __future__ import annotations

import time
import os
from pathlib import Path

from .base import AdapterInvocation, AdapterResult, AdapterUnavailable, AgentAdapter, mask_secrets, read_text, write_file
from .modes import load_adapter_mode_config, validate_adapter_mode


DEFAULT_GEMINI_MAX_FILES = 80
GEMINI_CONTEXT_RELATIVE_PATH = Path(".ai") / "context" / "gemini-context.md"
GEMINI_CONTEXT_OUTPUT = ".ai/context/gemini-context.md"
REQUIRED_HEADINGS = [
    "# Gemini Context",
    "## Task Summary",
    "## Relevant Project Facts",
    "## Current Architecture",
    "## Safety Boundaries",
    "## Files Reviewed",
    "## Suggested Implementation Notes",
    "## Risks / Unknowns",
    "## Non-Goals",
]
ALLOWED_ROOT_FILES = {
    "README.md",
    "AGENTS.md",
    "SPEC.md",
    "pyproject.toml",
    "requirements.txt",
    ".env.example",
}
ALLOWED_TOP_LEVEL_DIRS = {
    "docs",
    "agent_office",
    "tests",
    "scripts",
}
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
DENY_FILE_MARKERS = ("key", "pem", "token", "secret", "password", "auth", "cookie")
DENY_SUFFIXES = {".tar", ".tgz", ".gz", ".zip", ".7z", ".rar", ".bak"}


class GeminiAdapter(AgentAdapter):
    name = "gemini"

    def context(self, invocation: AdapterInvocation) -> AdapterResult:
        started = time.monotonic()
        config = load_adapter_mode_config("gemini")
        validation = validate_adapter_mode(config)
        if validation.errors:
            raise AdapterUnavailable("; ".join(validation.errors))
        if not config.dry_run:
            return self._send_real_request(invocation, config, validation)

        prompt, files_reviewed = self._build_prompt(invocation, config.max_input_chars)
        output_path = gemini_context_output_path(invocation.project_root)
        content = self._build_dry_run_context(invocation, prompt, files_reviewed)
        if len(content) > config.max_output_chars:
            suffix = "\n\n[TRUNCATED BY AGENTOFFICE GEMINI DRY-RUN ADAPTER]\n"
            content = content[: max(0, config.max_output_chars - len(suffix))] + suffix
        self._safe_write_context(invocation.project_root, output_path, content)
        latency_ms = int((time.monotonic() - started) * 1000)

        return AdapterResult(
            "Gemini real context dry-run generated .ai/context/gemini-context.md.",
            metadata={
                "adapter": "gemini",
                "role": "context",
                "mode": "real",
                "dry_run": True,
                "fallback_used": False,
                "real_request_sent": False,
                "output_path": GEMINI_CONTEXT_OUTPUT,
                "env_ok": validation.env_ok,
                "status": validation.status,
                "error": None,
                "latency_ms": latency_ms,
                "estimated_cost_usd": None,
                "input_chars": len(prompt),
                "output_chars": len(content),
            },
        )

    def _build_prompt(self, invocation: AdapterInvocation, max_input_chars: int) -> tuple[str, list[str]]:
        brief = read_text(invocation.paths.brief, 8000)
        files = self._allowed_context_files(invocation.project_root, self._max_files_from_env())
        sections: list[str] = []
        consumed = len(brief)

        for path in files:
            rel = self._display_path(invocation.project_root, path)
            remaining = max_input_chars - consumed - 200
            if remaining <= 0:
                break
            text = mask_secrets(read_text(path, min(4000, remaining)))
            consumed += len(text)
            sections.append(f"\n## {rel}\n\n{text}")

        reviewed = [self._display_path(invocation.project_root, path) for path in files[: len(sections)]]
        prompt = f"""You are Gemini, the AgentOffice context generator for task `{invocation.task_id}`.

Role boundaries:
- Generate context only.
- Do not implement code.
- Do not generate patches.
- Do not make final approval decisions.
- Read only the task brief and allowed safe project context.
- Do not read `.env`, private keys, token files, secret files, .ai/logs, .ai/tmp, or .ai/tasks directories beyond the current brief.
- Do not access `/opt/binance-futures-local-bot`.

Required output file:
{GEMINI_CONTEXT_OUTPUT}

Required sections:
{chr(10).join(REQUIRED_HEADINGS)}

Task brief:
{brief}

Allowed project context:
{''.join(sections)}
"""
        if len(prompt) > max_input_chars:
            prompt = prompt[:max_input_chars] + "\n...[truncated by AgentOffice Gemini adapter]..."
        return prompt, reviewed

    def _send_real_request(self, invocation, config, validation) -> AdapterResult:
        raise AdapterUnavailable(
            "Gemini non-dry-run API calls are not implemented in P5-02. "
            "Set AGENTOFFICE_GEMINI_DRY_RUN=true or use --mock."
        )

    def _build_dry_run_context(self, invocation: AdapterInvocation, prompt: str, files_reviewed: list[str]) -> str:
        brief = mask_secrets(read_text(invocation.paths.brief, 1200)).strip() or "(No task brief content found.)"
        files_text = "\n".join(f"- {name}" for name in files_reviewed) if files_reviewed else "- No allowed project files were reviewed."
        return f"""# Gemini Context

Mode: real dry-run
Adapter: gemini
Role: context
Dry run: true
Real request sent: false
Output path: {GEMINI_CONTEXT_OUTPUT}

## Task Summary

Task `{invocation.task_id}` needs project context only. Gemini is not implementing code and is not making final decisions.

Brief snapshot:

```text
{brief}
```

## Relevant Project Facts

- AgentOffice uses a file-based four-agent workflow.
- Mock mode remains the default.
- Real adapter activation is staged through the adapter mode registry.
- This dry-run generated the context artifact without sending a network request.
- Prompt size prepared for a future Gemini request: {len(prompt)} characters.

## Current Architecture

- Gemini owns the context stage.
- Codex owns implementation.
- Grok owns red-team review.
- Claude owns the final judge step from compressed context only.
- P5-02 only adds Gemini context dry-run behavior and does not change Codex, Grok, or Claude real adapters.

## Safety Boundaries

- Gemini must not implement code or generate patches.
- Gemini must not make final approval decisions.
- Gemini must not read `.env`, key files, token files, secret files, logs, tmp files, backup archives, or unrelated projects.
- Gemini may only write `{GEMINI_CONTEXT_OUTPUT}`.
- No real Gemini API request was sent in this dry-run.

## Files Reviewed

{files_text}

## Suggested Implementation Notes

- Keep mock mode as the default fallback.
- Use doctor output to confirm `GEMINI_API_KEY` presence before non-dry-run experiments.
- Keep adapter output bounded by configured input and output character limits.
- Preserve the v0.4 task protocol while treating `.ai/context/gemini-context.md` as the staged real-context artifact.

## Risks / Unknowns

- Real Gemini API transport is intentionally not enabled by this dry-run.
- Future non-dry-run work needs a separately reviewed network client and tests with a mocked client.
- The global `.ai/context/gemini-context.md` artifact is separate from the legacy per-task mock context file.

## Non-Goals

- No Codex real adapter work.
- No Grok real adapter work.
- No Claude real adapter work.
- No automatic execution, source-code writing, or command-running permissions.
"""

    def _allowed_context_files(self, project_root: Path, max_files: int) -> list[Path]:
        files: list[Path] = []
        for current_root, dirnames, filenames in os.walk(project_root):
            current = Path(current_root)
            try:
                rel_current = current.relative_to(project_root)
            except ValueError:
                continue
            if rel_current.parts and rel_current.parts[0] not in ALLOWED_TOP_LEVEL_DIRS:
                dirnames[:] = []
                continue
            if not rel_current.parts:
                dirnames[:] = sorted(
                    dirname
                    for dirname in dirnames
                    if dirname not in SKIP_DIRS and dirname != ".ai" and dirname in ALLOWED_TOP_LEVEL_DIRS
                )
            else:
                dirnames[:] = sorted(dirname for dirname in dirnames if dirname not in SKIP_DIRS and dirname != ".ai")
            for filename in sorted(filenames):
                path = current / filename
                if not self._is_allowed_context_path(project_root, path):
                    continue
                files.append(path)
                if len(files) >= max_files:
                    return files
        return files

    def _is_allowed_context_path(self, project_root: Path, path: Path) -> bool:
        try:
            rel = path.relative_to(project_root)
        except ValueError:
            return False
        parts = rel.parts
        if not parts:
            return False
        if any(part in SKIP_DIRS for part in parts[:-1]):
            return False
        if parts[0] == ".ai":
            return False
        lower_name = path.name.lower()
        if lower_name == ".env" or (lower_name.startswith(".env.") and lower_name != ".env.example"):
            return False
        if lower_name != ".env.example" and any(marker in lower_name for marker in DENY_FILE_MARKERS):
            return False
        if any(str(path).lower().endswith(suffix) for suffix in DENY_SUFFIXES):
            return False
        if len(parts) == 1:
            return parts[0] in ALLOWED_ROOT_FILES
        return parts[0] in ALLOWED_TOP_LEVEL_DIRS

    def _safe_write_context(self, project_root: Path, output_path: Path, content: str) -> None:
        expected = gemini_context_output_path(project_root).resolve()
        actual = output_path.resolve()
        if actual != expected:
            raise AdapterUnavailable("Gemini adapter refused to write outside .ai/context/gemini-context.md.")
        write_file(output_path, mask_secrets(content))

    def _max_files_from_env(self) -> int:
        raw = os.environ.get("AGENTOFFICE_GEMINI_MAX_FILES", "").strip()
        if not raw:
            return DEFAULT_GEMINI_MAX_FILES
        try:
            value = int(raw)
        except ValueError as exc:
            raise AdapterUnavailable("AGENTOFFICE_GEMINI_MAX_FILES must be an integer.") from exc
        if value <= 0:
            raise AdapterUnavailable("AGENTOFFICE_GEMINI_MAX_FILES must be positive.")
        return value

    def _display_path(self, project_root: Path, path: Path) -> str:
        try:
            return str(path.relative_to(project_root))
        except ValueError:
            return str(path)


def gemini_context_output_path(project_root: Path) -> Path:
    return project_root / GEMINI_CONTEXT_RELATIVE_PATH
