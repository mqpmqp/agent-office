from __future__ import annotations

import os
import re
from abc import ABC
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


SECRET_ENV_RE = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|AUTH|COOKIE)", re.IGNORECASE)
SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b([A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|AUTH|COOKIE)[A-Z0-9_]*)\s*[:=]\s*([^\s'\"`]+)"
)
SECRET_VALUE_RE = re.compile(
    r"(?i)\b(?:sk-[A-Za-z0-9_-]{12,}|xox[baprs]-[A-Za-z0-9-]{12,}|gh[pousr]_[A-Za-z0-9_]{12,}|Bearer\s+[A-Za-z0-9._=-]{12,})"
)


class AdapterError(RuntimeError):
    """Base error for adapter failures."""


class AdapterUnavailable(AdapterError):
    """Raised when a requested real adapter is not configured or supported."""


@dataclass(frozen=True)
class AdapterInvocation:
    task_id: str
    project_root: Path
    paths: Any
    timeout_seconds: int | None = None
    max_rework_rounds: int = 2
    final_for_claude_limit: int = 4000


@dataclass(frozen=True)
class AdapterResult:
    detail: str
    decision: str | None = None
    stdout: str = ""
    stderr: str = ""
    metadata: dict[str, object] = field(default_factory=dict)


class AgentAdapter(ABC):
    name = "base"

    def context(self, invocation: AdapterInvocation) -> AdapterResult:
        raise AdapterUnavailable(f"{self.name} does not support context.")

    def implement(self, invocation: AdapterInvocation) -> AdapterResult:
        raise AdapterUnavailable(f"{self.name} does not support implement.")

    def redteam(self, invocation: AdapterInvocation) -> AdapterResult:
        raise AdapterUnavailable(f"{self.name} does not support redteam.")

    def final(self, invocation: AdapterInvocation) -> AdapterResult:
        raise AdapterUnavailable(f"{self.name} does not support final.")


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def mask_secrets(text: str, environ: dict[str, str] | None = None) -> str:
    if not text:
        return ""
    masked = SECRET_ASSIGNMENT_RE.sub(lambda m: f"{m.group(1)}=***", text)
    masked = SECRET_VALUE_RE.sub("***", masked)
    env = environ if environ is not None else os.environ
    for name, value in env.items():
        if not value or len(value) < 4 or not SECRET_ENV_RE.search(name):
            continue
        masked = masked.replace(value, "***")
    return masked


def read_text(path: Path, max_chars: int | None = None) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8")
    if max_chars is not None and len(text) > max_chars:
        return text[:max_chars] + "\n...[truncated]..."
    return text
