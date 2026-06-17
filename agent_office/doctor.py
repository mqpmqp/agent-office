from __future__ import annotations

import importlib
import json
import os
import platform
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .adapters.registry import adapter_catalog


REQUIRED_GITIGNORE_PATTERNS = [
    ".env",
    ".env.*",
    "!.env.example",
    ".ai/tasks/",
    ".ai/logs/",
    ".ai/tmp/",
    ".ai/finalize/",
]
CODEX_ENV = [
    "AGENTOFFICE_CODEX_CMD",
    "AGENTOFFICE_CODEX_TIMEOUT_SECONDS",
]
GEMINI_ENV = [
    "AGENTOFFICE_GEMINI_CMD",
    "AGENTOFFICE_GEMINI_TIMEOUT_SECONDS",
    "AGENTOFFICE_GEMINI_MAX_FILES",
    "AGENTOFFICE_GEMINI_MAX_OUTPUT_CHARS",
]
GROK_ENV = [
    "AGENTOFFICE_GROK_CMD",
    "AGENTOFFICE_GROK_TIMEOUT_SECONDS",
]
CLAUDE_ENV = [
    "AGENTOFFICE_CLAUDE_CMD",
    "AGENTOFFICE_CLAUDE_TIMEOUT_SECONDS",
    "AGENTOFFICE_CLAUDE_MAX_INPUT_CHARS",
    "AGENTOFFICE_CLAUDE_MAX_OUTPUT_CHARS",
]


@dataclass(frozen=True)
class EnvCheck:
    name: str
    configured: bool


def env_configured(name: str) -> bool:
    return bool(os.environ.get(name, "").strip())


def collect_doctor(project_root: Path, adapter_filter: str | None = None) -> dict[str, Any]:
    gitignore_patterns = read_gitignore_patterns(project_root)
    catalog = adapter_catalog()
    adapters = {
        name: {
            "roles": data["roles"],
            "real": data["real"],
            "implemented": data.get("implemented", True),
            "configured": adapter_configured(name),
            "env": [env.__dict__ for env in adapter_env(name)],
        }
        for name, data in catalog.items()
        if adapter_filter is None or name == adapter_filter
    }
    if adapter_filter is not None and adapter_filter not in catalog:
        adapters = {}

    return {
        "project_path": str(project_root),
        "python": {
            "version": platform.python_version(),
            "executable": Path(sys.executable).name,
        },
        "agent_office_importable": module_importable("agent_office"),
        "gitignore": {
            "exists": (project_root / ".gitignore").exists(),
            "required": {
                pattern: pattern in gitignore_patterns for pattern in REQUIRED_GITIGNORE_PATTERNS
            },
        },
        "scripts": {
            "verify_sh": (project_root / "scripts" / "verify.sh").exists(),
            "smoke_test_sh": (project_root / "scripts" / "smoke-test.sh").exists(),
        },
        "registry": {
            "contains": {name: name in catalog for name in ["mock", "codex", "gemini", "grok", "claude"]},
            "adapters": adapters,
        },
        "safe": {
            "env_file_read": False,
            "real_adapter_executed": False,
            "task_created": False,
        },
    }


def adapter_configured(name: str) -> bool:
    if name == "mock":
        return True
    if name == "codex":
        return env_configured("AGENTOFFICE_CODEX_CMD")
    if name == "gemini":
        return env_configured("AGENTOFFICE_GEMINI_CMD")
    if name == "grok":
        return env_configured("AGENTOFFICE_GROK_CMD")
    if name == "claude":
        return env_configured("AGENTOFFICE_CLAUDE_CMD")
    return False


def adapter_env(name: str) -> list[EnvCheck]:
    if name == "codex":
        names = CODEX_ENV
    elif name == "gemini":
        names = GEMINI_ENV
    elif name == "grok":
        names = GROK_ENV
    elif name == "claude":
        names = CLAUDE_ENV
    else:
        names = []
    return [EnvCheck(env_name, env_configured(env_name)) for env_name in names]


def module_importable(name: str) -> bool:
    try:
        importlib.import_module(name)
    except Exception:
        return False
    return True


def read_gitignore_patterns(project_root: Path) -> set[str]:
    path = project_root / ".gitignore"
    if not path.exists():
        return set()
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def format_adapters(project_root: Path) -> str:
    catalog = adapter_catalog()
    lines = ["Supported adapters:"]
    for name, data in catalog.items():
        configured = adapter_configured(name)
        roles = ", ".join(data["roles"])
        if data.get("implemented", True) is False:
            status = "not implemented"
        else:
            status = "real" if data["real"] else "mock"
        lines.append(f"- {name}: mode={status}; roles={roles}; configured={str(configured).lower()}")
    return "\n".join(lines)


def format_doctor(report: dict[str, Any]) -> str:
    lines = [
        "AgentOffice doctor",
        f"- project_path: {report['project_path']}",
        f"- python_version: {report['python']['version']}",
        f"- python_executable: {report['python']['executable']}",
        f"- agent_office_importable: {bool_text(report['agent_office_importable'])}",
        f"- scripts/verify.sh: {bool_text(report['scripts']['verify_sh'])}",
        f"- scripts/smoke-test.sh: {bool_text(report['scripts']['smoke_test_sh'])}",
        "- gitignore:",
    ]
    for pattern, present in report["gitignore"]["required"].items():
        lines.append(f"  - {pattern}: {bool_text(present)}")
    lines.append("- registry:")
    for name, present in report["registry"]["contains"].items():
        lines.append(f"  - {name}: {bool_text(present)}")
    lines.append("- adapters:")
    for name, data in report["registry"]["adapters"].items():
        roles = ", ".join(data["roles"])
        lines.append(
            f"  - {name}: real={bool_text(data['real'])}; implemented={bool_text(data.get('implemented', True))}; roles={roles}; configured={bool_text(data['configured'])}"
        )
        for env in data["env"]:
            lines.append(f"    - {env['name']}: configured={bool_text(env['configured'])}")
    lines.extend(
        [
            "- safety:",
            f"  - env_file_read: {bool_text(report['safe']['env_file_read'])}",
            f"  - real_adapter_executed: {bool_text(report['safe']['real_adapter_executed'])}",
            f"  - task_created: {bool_text(report['safe']['task_created'])}",
        ]
    )
    return "\n".join(lines)


def bool_text(value: bool) -> str:
    return str(bool(value)).lower()


def doctor_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, ensure_ascii=False)
