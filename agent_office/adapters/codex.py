from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .base import AdapterInvocation, AdapterResult, AdapterUnavailable, AgentAdapter, mask_secrets, read_text, write_file
from .modes import load_adapter_mode_config, validate_adapter_mode
from .patch_validator import PatchValidationResult, validate_patch_diff


CODEX_OUTPUT_DIR = Path(".ai") / "codex"
CODEX_PATCH_OUTPUT = ".ai/codex/patch.diff"
CODEX_REPORT_OUTPUT = ".ai/codex/codex-report.md"
CODEX_METADATA_OUTPUT = ".ai/codex/metadata.json"
DEFAULT_CODEX_MAX_FILES = 80
ALLOWED_ROOT_FILES = {
    "README.md",
    "AGENTS.md",
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


class CodexAdapter(AgentAdapter):
    name = "codex"

    def implement(self, invocation: AdapterInvocation) -> AdapterResult:
        started = time.monotonic()
        config = load_adapter_mode_config("codex")
        validation = validate_adapter_mode(config)
        if validation.errors:
            raise AdapterUnavailable("; ".join(validation.errors))
        if not config.dry_run:
            return self._send_real_request(invocation, config, validation)

        prompt, inputs_reviewed = self._build_prompt(invocation, config.max_input_chars)
        patch_text = self._build_dry_run_patch(invocation)
        patch_validation = validate_patch_diff(patch_text)
        report_text = self._build_report(invocation, inputs_reviewed, patch_validation)
        metadata = self._metadata(
            validation_env_ok=validation.env_ok,
            validation_status=validation.status,
            patch_validation=patch_validation,
            started=started,
            input_chars=len(prompt),
            output_chars=len(patch_text) + len(report_text),
            error=None,
        )

        if not patch_validation.ok:
            metadata["error"] = "; ".join(patch_validation.reasons)
            self._safe_write_json(invocation.project_root, codex_metadata_path(invocation.project_root), metadata)
            raise AdapterUnavailable("Codex dry-run patch rejected: " + "; ".join(patch_validation.reasons))

        self._safe_write_text(invocation.project_root, codex_patch_path(invocation.project_root), patch_text)
        self._safe_write_text(invocation.project_root, codex_report_path(invocation.project_root), report_text)
        self._safe_write_json(invocation.project_root, codex_metadata_path(invocation.project_root), metadata)

        return AdapterResult(
            "Codex real implement dry-run generated patch-only artifacts under .ai/codex/.",
            metadata=metadata,
        )

    def _send_real_request(self, invocation, config, validation) -> AdapterResult:
        raise AdapterUnavailable(
            "Codex non-dry-run API calls are not implemented in P5-03. "
            "Set AGENTOFFICE_CODEX_DRY_RUN=true or use --mock."
        )

    def _build_prompt(self, invocation: AdapterInvocation, max_input_chars: int) -> tuple[str, list[str]]:
        brief = read_text(invocation.paths.brief, 8000)
        gemini_context = read_text(invocation.project_root / ".ai" / "context" / "gemini-context.md", 8000)
        files = self._allowed_context_files(invocation.project_root, self._max_files_from_env())
        sections: list[str] = []
        consumed = len(brief) + len(gemini_context)

        for path in files:
            rel = self._display_path(invocation.project_root, path)
            remaining = max_input_chars - consumed - 200
            if remaining <= 0:
                break
            text = mask_secrets(read_text(path, min(3000, remaining)))
            consumed += len(text)
            sections.append(f"\n## {rel}\n\n{text}")

        reviewed = [self._display_path(invocation.project_root, path) for path in files[: len(sections)]]
        prompt = f"""You are Codex, the AgentOffice implement adapter for task `{invocation.task_id}`.

Patch-only dry-run boundaries:
- Generate a patch proposal only.
- Do not apply the patch.
- Do not directly modify project source files.
- Do not execute commands or shell.
- Do not read `.env`, private keys, token files, secret files, logs, tmp files, or unrelated projects.
- Do not access `/opt/binance-futures-local-bot`.
- Write only `.ai/codex/patch.diff`, `.ai/codex/codex-report.md`, and `.ai/codex/metadata.json`.

Task brief:
{brief}

Gemini context:
{gemini_context}

Allowed project context:
{''.join(sections)}
"""
        if len(prompt) > max_input_chars:
            prompt = prompt[:max_input_chars] + "\n...[truncated by AgentOffice Codex adapter]..."
        return prompt, reviewed

    def _build_dry_run_patch(self, invocation: AdapterInvocation) -> str:
        task_id = invocation.task_id
        return f"""diff --git a/docs/codex-dry-run-proposal.md b/docs/codex-dry-run-proposal.md
new file mode 100644
--- /dev/null
+++ b/docs/codex-dry-run-proposal.md
@@ -0,0 +1,9 @@
+# Codex Dry-Run Patch Proposal
+
+Task: {task_id}
+
+This patch is a deterministic AgentOffice Codex dry-run artifact.
+It is not applied automatically.
+It does not modify source files during adapter execution.
+Human review is required before applying any proposed patch.
+Generated artifact path: .ai/codex/patch.diff
"""

    def _build_report(
        self,
        invocation: AdapterInvocation,
        inputs_reviewed: list[str],
        patch_validation: PatchValidationResult,
    ) -> str:
        reviewed = "\n".join(f"- {path}" for path in inputs_reviewed) if inputs_reviewed else "- Task brief and staged Gemini context only."
        reasons = "\n".join(f"- {reason}" for reason in patch_validation.reasons) if patch_validation.reasons else "- None."
        flags = "\n".join(f"- {flag}" for flag in patch_validation.risk_flags) if patch_validation.risk_flags else "- None."
        return f"""# Codex Implementation Report

Mode: real dry-run
Adapter: codex
Role: implement
Patch-only: true
Real request sent: false

## Task Summary

Task `{invocation.task_id}` requested an implementation pass. Codex generated a patch proposal only and did not apply changes.

## Inputs Reviewed

{reviewed}

## Proposed Changes

- Generated a deterministic dry-run patch proposal.
- Did not modify project source files.
- Did not execute commands.
- Did not call OpenAI or Codex network APIs.

## Patch Path

`.ai/codex/patch.diff`

## Tests Recommended

- `python3 -m compileall -q agent_office`
- `python3 -m unittest discover -s tests -p 'test_*.py'`
- `bash scripts/verify.sh`

## Safety Notes

- The patch was not applied automatically.
- Patch validation status: `{patch_validation.status}`
- Patch validation reasons:
{reasons}
- Patch validation risk flags:
{flags}

## Risks / Unknowns

- This is a deterministic dry-run proposal, not a real model-generated implementation.
- A human must review and explicitly apply any patch in a separate step.

## Non-Goals

- No Grok real adapter work.
- No Claude real adapter work.
- No source mutation from the real Codex adapter.
- No automatic patch application.
"""

    def _metadata(
        self,
        validation_env_ok: bool,
        validation_status: str,
        patch_validation: PatchValidationResult,
        started: float,
        input_chars: int,
        output_chars: int,
        error: str | None,
    ) -> dict[str, object]:
        return {
            "adapter": "codex",
            "role": "implement",
            "mode": "real",
            "dry_run": True,
            "fallback_used": False,
            "real_request_sent": False,
            "patch_path": CODEX_PATCH_OUTPUT,
            "report_path": CODEX_REPORT_OUTPUT,
            "env_ok": validation_env_ok,
            "status": validation_status,
            "patch_validation_status": patch_validation.status,
            "patch_validation_reasons": patch_validation.reasons,
            "patch_validation_risk_flags": patch_validation.risk_flags,
            "error": error,
            "latency_ms": int((time.monotonic() - started) * 1000),
            "estimated_cost_usd": None,
            "input_chars": input_chars,
            "output_chars": output_chars,
        }

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

    def _safe_write_text(self, project_root: Path, path: Path, content: str) -> None:
        self._assert_allowed_output(project_root, path)
        write_file(path, mask_secrets(content))

    def _safe_write_json(self, project_root: Path, path: Path, data: dict[str, object]) -> None:
        self._assert_allowed_output(project_root, path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def _assert_allowed_output(self, project_root: Path, path: Path) -> None:
        allowed = {
            codex_patch_path(project_root).resolve(),
            codex_report_path(project_root).resolve(),
            codex_metadata_path(project_root).resolve(),
        }
        if path.resolve() not in allowed:
            raise AdapterUnavailable("Codex adapter refused to write outside .ai/codex allowed files.")

    def _max_files_from_env(self) -> int:
        raw = os.environ.get("AGENTOFFICE_CODEX_MAX_FILES", "").strip()
        if not raw:
            return DEFAULT_CODEX_MAX_FILES
        try:
            value = int(raw)
        except ValueError as exc:
            raise AdapterUnavailable("AGENTOFFICE_CODEX_MAX_FILES must be an integer.") from exc
        if value <= 0:
            raise AdapterUnavailable("AGENTOFFICE_CODEX_MAX_FILES must be positive.")
        return value

    def _display_path(self, project_root: Path, path: Path) -> str:
        try:
            return str(path.relative_to(project_root))
        except ValueError:
            return str(path)


def codex_output_dir(project_root: Path) -> Path:
    return project_root / CODEX_OUTPUT_DIR


def codex_patch_path(project_root: Path) -> Path:
    return project_root / CODEX_PATCH_OUTPUT


def codex_report_path(project_root: Path) -> Path:
    return project_root / CODEX_REPORT_OUTPUT


def codex_metadata_path(project_root: Path) -> Path:
    return project_root / CODEX_METADATA_OUTPUT
