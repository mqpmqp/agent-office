from __future__ import annotations

import argparse
import importlib
import json
import os
import platform
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .adapters.modes import adapter_mode_rows, collect_adapter_mode_status, format_adapter_mode_table
from .adapters.registry import adapter_catalog
from .skills_registry import skills_as_dicts


REQUIRED_GITIGNORE_PATTERNS = [
    ".env",
    ".env.*",
    "!.env.example",
    ".ai/tasks/",
    ".ai/logs/",
    ".ai/tmp/",
    ".ai/finalize/",
    ".ai/context/",
    ".ai/codex/",
    ".ai/grok/",
    ".ai/claude/",
]
CODEX_ENV = [
    "OPENAI_API_KEY",
    "AGENTOFFICE_CODEX_TIMEOUT_SECONDS",
    "AGENTOFFICE_CODEX_MAX_INPUT_CHARS",
    "AGENTOFFICE_CODEX_MAX_OUTPUT_CHARS",
]
GEMINI_ENV = [
    "GEMINI_API_KEY",
    "AGENTOFFICE_GEMINI_TIMEOUT_SECONDS",
    "AGENTOFFICE_GEMINI_MAX_FILES",
    "AGENTOFFICE_GEMINI_MAX_INPUT_CHARS",
    "AGENTOFFICE_GEMINI_MAX_OUTPUT_CHARS",
]
GROK_ENV = [
    "XAI_API_KEY",
    "AGENTOFFICE_GROK_TIMEOUT_SECONDS",
    "AGENTOFFICE_GROK_MAX_INPUT_CHARS",
    "AGENTOFFICE_GROK_MAX_OUTPUT_CHARS",
]
CLAUDE_ENV = [
    "ANTHROPIC_API_KEY",
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
    mode_status = collect_adapter_mode_status()
    mode_rows = adapter_mode_rows()
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
    if adapter_filter is not None:
        mode_status = {name: data for name, data in mode_status.items() if name == adapter_filter}
        mode_rows = [row for row in mode_rows if row["adapter"] == adapter_filter]

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
        "adapter_modes": {
            "rows": mode_rows,
            "adapters": mode_status,
        },
        "skills": {
            "registered": skills_as_dicts(project_root),
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
        return env_configured("OPENAI_API_KEY")
    if name == "gemini":
        return env_configured("GEMINI_API_KEY")
    if name == "grok":
        return env_configured("XAI_API_KEY")
    if name == "claude":
        return env_configured("ANTHROPIC_API_KEY")
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
    lines.append("- adapter mode registry:")
    lines.append("  adapter | mode | dry_run | env_ok | fallback | status")
    for row in report["adapter_modes"]["rows"]:
        lines.append(
            "  "
            + " | ".join(
                [
                    str(row["adapter"]),
                    str(row["mode"]),
                    bool_text(bool(row["dry_run"])),
                    bool_text(bool(row["env_ok"])),
                    bool_text(bool(row["fallback"])),
                    str(row["status"]),
                ]
            )
        )
    lines.append("- skills registry:")
    lines.append(f"  - registered: {len(report['skills']['registered'])}")
    for skill in report["skills"]["registered"]:
        lines.append(
            f"  - {skill['name']}: exists={bool_text(skill['exists'])}; validated={bool_text(skill['validated'])}; status={skill['status']}"
        )
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m agent_office.doctor")
    parser.add_argument("--adapter", choices=["codex", "gemini", "grok", "claude"], help="Limit diagnostics to one adapter.")
    parser.add_argument("--adapters", action="store_true", help="Print adapter mode table only.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    project_root = Path(__file__).resolve().parents[1]
    if args.adapters:
        rows = adapter_mode_rows()
        if args.adapter:
            rows = [row for row in rows if row["adapter"] == args.adapter]
        if args.json:
            print(json.dumps(rows, indent=2, ensure_ascii=False))
        elif args.adapter:
            print(_format_adapter_rows(rows))
        else:
            print(format_adapter_mode_table())
        return 0

    report = collect_doctor(project_root, adapter_filter=args.adapter)
    if args.json:
        print(doctor_json(report))
    else:
        print(format_doctor(report))
    return 0


def _format_adapter_rows(rows: list[dict[str, object]]) -> str:
    lines = ["adapter | mode | dry_run | env_ok | fallback | status"]
    for row in rows:
        lines.append(
            " | ".join(
                [
                    str(row["adapter"]),
                    str(row["mode"]),
                    bool_text(bool(row["dry_run"])),
                    bool_text(bool(row["env_ok"])),
                    bool_text(bool(row["fallback"])),
                    str(row["status"]),
                ]
            )
        )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
