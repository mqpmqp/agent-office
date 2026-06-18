from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .base import AdapterInvocation, AdapterResult, AdapterUnavailable, AgentAdapter, mask_secrets, read_text, write_file
from .modes import load_adapter_mode_config, validate_adapter_mode


CLAUDE_OUTPUT_DIR = Path(".ai") / "claude"
CLAUDE_REPORT_OUTPUT = ".ai/claude/final-judge.md"
CLAUDE_METADATA_OUTPUT = ".ai/claude/metadata.json"
VALID_DECISIONS = {"APPROVE", "REQUEST_CHANGES", "REJECT"}
DECISION_TO_STATE = {
    "APPROVE": "APPROVED",
    "REQUEST_CHANGES": "REQUEST_CHANGES",
    "REJECT": "REJECTED",
}


class ClaudeAdapter(AgentAdapter):
    name = "claude"

    def final(self, invocation: AdapterInvocation) -> AdapterResult:
        started = time.monotonic()
        config = load_adapter_mode_config("claude")
        validation = validate_adapter_mode(config)
        if validation.errors:
            raise AdapterUnavailable("; ".join(validation.errors))
        if not config.dry_run:
            return self._send_real_request(invocation, config, validation)

        inputs = self._load_final_inputs(invocation, config.max_input_chars)
        decision = self._decide(inputs)
        risk_flags = self._risk_flags(inputs)
        report_text = self._build_report(invocation, inputs, decision, risk_flags)
        if len(report_text) > config.max_output_chars:
            suffix = "\n\n[TRUNCATED BY AGENTOFFICE CLAUDE DRY-RUN ADAPTER]\n"
            report_text = report_text[: max(0, config.max_output_chars - len(suffix))] + suffix

        metadata = self._metadata(
            validation_env_ok=validation.env_ok,
            validation_status=validation.status,
            decision=decision,
            risk_flags=risk_flags,
            started=started,
            input_chars=sum(len(value) for value in inputs.values()),
            output_chars=len(report_text),
            error=None,
        )
        self._safe_write_text(invocation.project_root, claude_report_path(invocation.project_root), report_text)
        self._safe_write_json(invocation.project_root, claude_metadata_path(invocation.project_root), metadata)

        return AdapterResult(
            f"Claude real final judge dry-run decision: {decision}.",
            decision=DECISION_TO_STATE[decision],
            metadata=metadata,
        )

    def _send_real_request(self, invocation, config, validation) -> AdapterResult:
        raise AdapterUnavailable(
            "Claude non-dry-run API calls are not implemented in P5-05. "
            "Set AGENTOFFICE_CLAUDE_DRY_RUN=true or use --mock."
        )

    def _load_final_inputs(self, invocation: AdapterInvocation, max_input_chars: int) -> dict[str, str]:
        project_root = invocation.project_root
        final_packet_path = project_root / ".ai" / "finalize" / "final-for-claude.md"
        if not final_packet_path.exists() and invocation.paths.final_for_claude.exists():
            final_packet_path = invocation.paths.final_for_claude

        context_path = project_root / ".ai" / "context" / "gemini-context.md"
        if not context_path.exists() and invocation.paths.gemini_context.exists():
            context_path = invocation.paths.gemini_context

        codex_patch_path = project_root / ".ai" / "codex" / "patch.diff"
        if not codex_patch_path.exists() and invocation.paths.patch_diff.exists():
            codex_patch_path = invocation.paths.patch_diff

        codex_report_path = project_root / ".ai" / "codex" / "codex-report.md"
        if not codex_report_path.exists() and invocation.paths.codex_report.exists():
            codex_report_path = invocation.paths.codex_report

        grok_report_path = project_root / ".ai" / "grok" / "redteam-report.md"
        if not grok_report_path.exists() and invocation.paths.grok_review.exists():
            grok_report_path = invocation.paths.grok_review

        raw_inputs = {
            "final_packet": mask_secrets(read_text(final_packet_path, 8000)),
            "gemini_context": mask_secrets(read_text(context_path, 6000)),
            "codex_patch": mask_secrets(read_text(codex_patch_path, 8000)),
            "codex_report": mask_secrets(read_text(codex_report_path, 6000)),
            "codex_metadata": mask_secrets(read_text(project_root / ".ai" / "codex" / "metadata.json", 4000)),
            "grok_report": mask_secrets(read_text(grok_report_path, 6000)),
            "grok_metadata": mask_secrets(read_text(project_root / ".ai" / "grok" / "metadata.json", 4000)),
        }
        if not raw_inputs["final_packet"]:
            raw_inputs["final_packet"] = self._build_minimal_final_packet(invocation, raw_inputs)

        if not any(value.strip() for value in raw_inputs.values()):
            raise AdapterUnavailable("Claude final judge dry-run has no evidence to review.")

        clipped: dict[str, str] = {}
        consumed = 0
        for name, value in raw_inputs.items():
            remaining = max_input_chars - consumed
            if remaining <= 0:
                clipped[name] = ""
                continue
            clipped_value = value[:remaining]
            clipped[name] = clipped_value
            consumed += len(clipped_value)
        return clipped

    def _build_minimal_final_packet(self, invocation: AdapterInvocation, inputs: dict[str, str]) -> str:
        available = [
            name
            for name in ("gemini_context", "codex_patch", "codex_report", "codex_metadata", "grok_report", "grok_metadata")
            if inputs.get(name, "").strip()
        ]
        missing = [
            name
            for name in ("gemini_context", "codex_patch", "codex_report", "codex_metadata", "grok_report", "grok_metadata")
            if not inputs.get(name, "").strip()
        ]
        available_text = "\n".join(f"- {name}" for name in available) if available else "- None."
        missing_text = "\n".join(f"- {name}" for name in missing) if missing else "- None."
        return f"""# Final For Claude

Task `{invocation.task_id}` did not have a prebuilt final-for-claude.md packet.
AgentOffice built this minimal evidence index from existing staged artifacts.

## Evidence Available

{available_text}

## Evidence Missing

{missing_text}

## Constraint

Claude must make a final review decision only and must not apply changes.
"""

    def _decide(self, inputs: dict[str, str]) -> str:
        combined = "\n".join(inputs.values()).upper()
        grok_metadata = self._parse_json(inputs.get("grok_metadata", ""))
        recommendation = str(grok_metadata.get("recommendation", "")).upper()
        if "FORCE_REJECT" in combined or recommendation == "BLOCK":
            return "REJECT"
        if "FORCE_REQUEST_CHANGES" in combined or recommendation == "REQUEST_CODEX_REVISION":
            return "REQUEST_CHANGES"
        if "BLOCKING ISSUES" in combined and "NONE" not in combined:
            return "REQUEST_CHANGES"
        return "APPROVE"

    def _risk_flags(self, inputs: dict[str, str]) -> list[str]:
        flags: list[str] = []
        grok_metadata = self._parse_json(inputs.get("grok_metadata", ""))
        raw_flags = grok_metadata.get("risk_flags", [])
        if isinstance(raw_flags, list):
            flags.extend(str(flag) for flag in raw_flags if str(flag).strip())
        if not inputs.get("final_packet", "").strip():
            flags.append("missing_final_packet")
        if not inputs.get("grok_report", "").strip():
            flags.append("missing_grok_report")
        return sorted(set(flags))

    def _build_report(
        self,
        invocation: AdapterInvocation,
        inputs: dict[str, str],
        decision: str,
        risk_flags: list[str],
    ) -> str:
        if decision not in VALID_DECISIONS:
            decision = "REQUEST_CHANGES"
        flags_text = "\n".join(f"- {flag}" for flag in risk_flags) if risk_flags else "- None."
        evidence = self._evidence_reviewed(inputs)
        required_changes = "- None." if decision == "APPROVE" else "- Address the risk flags and rerun the staged review loop."
        reasons = self._decision_reasons(decision, inputs, risk_flags)
        return f"""# Claude Final Judge

Mode: real dry-run
Adapter: claude
Role: final_judge
Final-judge-only: true
Real request sent: false

## Decision

{decision}

## Reasons

{reasons}

## Required Changes

{required_changes}

## Risk Flags

{flags_text}

## Evidence Reviewed

{evidence}

## Safety Notes

- Claude made the final review decision only and did not apply changes.
- Claude did not modify source files.
- Claude did not generate or apply patches.
- Claude did not execute commands or shell.
- Claude did not send a real Anthropic API request.
- Claude did not read `.env`, private keys, token files, or secret files.

## Non-Goals

- No Gemini, Codex, or Grok behavior changes.
- No source mutation.
- No git commit, deployment action, or patch application.
- No non-dry-run Claude API transport in P5-05.
"""

    def _decision_reasons(self, decision: str, inputs: dict[str, str], risk_flags: list[str]) -> str:
        if decision == "APPROVE":
            return "- Available staged evidence does not require a deterministic dry-run block."
        if decision == "REJECT":
            return "- Grok or the final packet indicates a blocking condition."
        if risk_flags:
            return "- Staged evidence contains risk flags that require another implementation pass."
        if not inputs.get("grok_report", "").strip():
            return "- Grok review evidence is missing, so changes should be requested."
        return "- The final packet explicitly requested changes."

    def _evidence_reviewed(self, inputs: dict[str, str]) -> str:
        labels = [
            ("final_packet", ".ai/finalize/final-for-claude.md or .ai/tasks/<TASK_ID>/final-for-claude.md"),
            ("gemini_context", ".ai/context/gemini-context.md or .ai/tasks/<TASK_ID>/gemini-context.md"),
            ("codex_patch", ".ai/codex/patch.diff or .ai/tasks/<TASK_ID>/patch.diff"),
            ("codex_report", ".ai/codex/codex-report.md or .ai/tasks/<TASK_ID>/codex-report.md"),
            ("codex_metadata", ".ai/codex/metadata.json"),
            ("grok_report", ".ai/grok/redteam-report.md or .ai/tasks/<TASK_ID>/grok-review.md"),
            ("grok_metadata", ".ai/grok/metadata.json"),
        ]
        return "\n".join(f"- {label}: {'present' if inputs.get(name, '').strip() else 'missing'}" for name, label in labels)

    def _metadata(
        self,
        validation_env_ok: bool,
        validation_status: str,
        decision: str,
        risk_flags: list[str],
        started: float,
        input_chars: int,
        output_chars: int,
        error: str | None,
    ) -> dict[str, object]:
        if decision not in VALID_DECISIONS:
            decision = "REQUEST_CHANGES"
        return {
            "adapter": "claude",
            "role": "final_judge",
            "mode": "real",
            "dry_run": True,
            "fallback_used": False,
            "real_request_sent": False,
            "report_path": CLAUDE_REPORT_OUTPUT,
            "env_ok": validation_env_ok,
            "status": validation_status,
            "decision": decision,
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
            claude_report_path(project_root).resolve(),
            claude_metadata_path(project_root).resolve(),
        }
        if path.resolve() not in allowed:
            raise AdapterUnavailable("Claude adapter refused to write outside .ai/claude allowed files.")

    def _parse_json(self, text: str) -> dict[str, Any]:
        if not text.strip():
            return {}
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}


def claude_output_dir(project_root: Path) -> Path:
    return project_root / CLAUDE_OUTPUT_DIR


def claude_report_path(project_root: Path) -> Path:
    return project_root / CLAUDE_REPORT_OUTPUT


def claude_metadata_path(project_root: Path) -> Path:
    return project_root / CLAUDE_METADATA_OUTPUT
