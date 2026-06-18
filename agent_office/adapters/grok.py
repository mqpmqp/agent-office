from __future__ import annotations

import json
import time
from pathlib import Path

from .base import AdapterInvocation, AdapterResult, AdapterUnavailable, AgentAdapter, mask_secrets, read_text, write_file
from .modes import load_adapter_mode_config, validate_adapter_mode
from .patch_validator import PatchValidationResult, validate_patch_diff


GROK_OUTPUT_DIR = Path(".ai") / "grok"
GROK_REPORT_OUTPUT = ".ai/grok/redteam-report.md"
GROK_METADATA_OUTPUT = ".ai/grok/metadata.json"
VALID_RECOMMENDATIONS = {"PASS_TO_CLAUDE", "REQUEST_CODEX_REVISION", "BLOCK"}


class GrokAdapter(AgentAdapter):
    name = "grok"

    def redteam(self, invocation: AdapterInvocation) -> AdapterResult:
        started = time.monotonic()
        config = load_adapter_mode_config("grok")
        validation = validate_adapter_mode(config)
        if validation.errors:
            raise AdapterUnavailable("; ".join(validation.errors))
        if not config.dry_run:
            return self._send_real_request(invocation, config, validation)

        inputs = self._load_review_inputs(invocation, config.max_input_chars)
        patch_validation = validate_patch_diff(inputs["codex_patch"])
        risk_flags = list(patch_validation.risk_flags)
        recommendation = self._recommendation(patch_validation)
        report_text = self._build_report(invocation, inputs, patch_validation, recommendation)
        if len(report_text) > config.max_output_chars:
            suffix = "\n\n[TRUNCATED BY AGENTOFFICE GROK DRY-RUN ADAPTER]\n"
            report_text = report_text[: max(0, config.max_output_chars - len(suffix))] + suffix

        metadata = self._metadata(
            validation_env_ok=validation.env_ok,
            validation_status=validation.status,
            recommendation=recommendation,
            risk_flags=risk_flags,
            started=started,
            input_chars=sum(len(value) for value in inputs.values()),
            output_chars=len(report_text),
            error=None,
        )

        self._safe_write_text(invocation.project_root, grok_report_path(invocation.project_root), report_text)
        self._safe_write_json(invocation.project_root, grok_metadata_path(invocation.project_root), metadata)

        return AdapterResult(
            "Grok real redteam dry-run generated review-only artifacts under .ai/grok/.",
            metadata=metadata,
        )

    def _send_real_request(self, invocation, config, validation) -> AdapterResult:
        raise AdapterUnavailable(
            "Grok non-dry-run API calls are not implemented in P5-04. "
            "Set AGENTOFFICE_GROK_DRY_RUN=true or use --mock."
        )

    def _load_review_inputs(self, invocation: AdapterInvocation, max_input_chars: int) -> dict[str, str]:
        project_root = invocation.project_root
        patch_path = project_root / ".ai" / "codex" / "patch.diff"
        report_path = project_root / ".ai" / "codex" / "codex-report.md"
        metadata_path = project_root / ".ai" / "codex" / "metadata.json"

        if not patch_path.exists() and invocation.paths.patch_diff.exists():
            patch_path = invocation.paths.patch_diff
        if not report_path.exists() and invocation.paths.codex_report.exists():
            report_path = invocation.paths.codex_report

        if not patch_path.exists() or patch_path.stat().st_size == 0:
            raise AdapterUnavailable("Grok dry-run cannot review because patch.diff is missing.")

        context_text = read_text(project_root / ".ai" / "context" / "gemini-context.md", 6000)
        if not context_text:
            context_text = read_text(invocation.paths.gemini_context, 6000)
        inputs = {
            "gemini_context": mask_secrets(context_text),
            "codex_patch": mask_secrets(read_text(patch_path, 12000)),
            "codex_report": mask_secrets(read_text(report_path, 8000)),
            "codex_metadata": mask_secrets(read_text(metadata_path, 4000)),
            "patch_path": str(self._display_path(project_root, patch_path)),
            "report_path": str(self._display_path(project_root, report_path)) if report_path.exists() else "(missing)",
        }
        total = 0
        clipped: dict[str, str] = {}
        for name, value in inputs.items():
            remaining = max_input_chars - total
            if remaining <= 0:
                clipped[name] = ""
                continue
            clipped_value = value[:remaining]
            clipped[name] = clipped_value
            total += len(clipped_value)
        return clipped

    def _build_report(
        self,
        invocation: AdapterInvocation,
        inputs: dict[str, str],
        patch_validation: PatchValidationResult,
        recommendation: str,
    ) -> str:
        reasons = "\n".join(f"- {reason}" for reason in patch_validation.reasons) if patch_validation.reasons else "- None."
        risk_flags = "\n".join(f"- {flag}" for flag in patch_validation.risk_flags) if patch_validation.risk_flags else "- None."
        return f"""# Grok Redteam Report

Mode: real dry-run
Adapter: grok
Role: redteam
Review-only: true
Real request sent: false

## Review Summary

Grok reviewed the proposed patch for task `{invocation.task_id}` and did not apply changes.

## Inputs Reviewed

- Gemini context: `{'.ai/context/gemini-context.md' if inputs['gemini_context'] else 'missing'}`
- Codex patch: `{inputs['patch_path']}`
- Codex report: `{inputs['report_path']}`
- Codex metadata: `{'.ai/codex/metadata.json' if inputs['codex_metadata'] else 'missing'}`

## Patch Risk Assessment

- Patch validation status: `{patch_validation.status}`
- Risk flags:
{risk_flags}
- Reasons:
{reasons}

## Safety Issues

- Grok did not modify source files.
- Grok did not apply patches.
- Grok did not execute commands or shell.
- Grok did not send a real xAI/Grok API request.

## Logic Issues

- Dry-run review cannot prove semantic correctness.
- Human review is still required before any patch is applied.

## Missing Tests

- Run `python3 -m unittest discover -s tests -p 'test_*.py'`.
- Run `bash scripts/verify.sh`.
- Add focused tests if the proposed patch changes behavior.

## Security Concerns

- Do not apply patches that touch `.env`, private keys, credentials, or adapter safety defaults.
- Do not enable all real adapters at once.
- Do not set `dry_run=false` or `allow_non_dry_run=true` by default.

## Possible Regression Risks

- Patch proposals can drift from the current source tree if not applied immediately after review.
- The dry-run report is deterministic and does not replace a real model review.

## Recommendation

{recommendation}
"""

    def _recommendation(self, patch_validation: PatchValidationResult) -> str:
        if patch_validation.status == "rejected":
            return "BLOCK"
        return "PASS_TO_CLAUDE"

    def _metadata(
        self,
        validation_env_ok: bool,
        validation_status: str,
        recommendation: str,
        risk_flags: list[str],
        started: float,
        input_chars: int,
        output_chars: int,
        error: str | None,
    ) -> dict[str, object]:
        if recommendation not in VALID_RECOMMENDATIONS:
            recommendation = "BLOCK"
        return {
            "adapter": "grok",
            "role": "redteam",
            "mode": "real",
            "dry_run": True,
            "fallback_used": False,
            "real_request_sent": False,
            "report_path": GROK_REPORT_OUTPUT,
            "env_ok": validation_env_ok,
            "status": validation_status,
            "recommendation": recommendation,
            "risk_flags": risk_flags,
            "error": error,
            "latency_ms": int((time.monotonic() - started) * 1000),
            "estimated_cost_usd": None,
            "input_chars": input_chars,
            "output_chars": output_chars,
        }

    def _safe_write_text(self, project_root: Path, path: Path, content: str) -> None:
        self._assert_allowed_output(project_root, path)
        write_file(path, mask_secrets(content))

    def _safe_write_json(self, project_root: Path, path: Path, data: dict[str, object]) -> None:
        self._assert_allowed_output(project_root, path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def _assert_allowed_output(self, project_root: Path, path: Path) -> None:
        allowed = {
            grok_report_path(project_root).resolve(),
            grok_metadata_path(project_root).resolve(),
        }
        if path.resolve() not in allowed:
            raise AdapterUnavailable("Grok adapter refused to write outside .ai/grok allowed files.")

    def _display_path(self, project_root: Path, path: Path) -> str:
        try:
            return str(path.relative_to(project_root))
        except ValueError:
            return str(path)


def grok_output_dir(project_root: Path) -> Path:
    return project_root / GROK_OUTPUT_DIR


def grok_report_path(project_root: Path) -> Path:
    return project_root / GROK_REPORT_OUTPUT


def grok_metadata_path(project_root: Path) -> Path:
    return project_root / GROK_METADATA_OUTPUT
