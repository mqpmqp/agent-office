from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


DEFAULT_REGISTRY_RELATIVE_PATH = Path("skills") / "registry.json"
SKILL_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}[a-z0-9]$")


@dataclass(frozen=True)
class SkillRegistryEntry:
    name: str
    purpose: str
    path: str
    expected_scripts: tuple[str, ...] = ()


@dataclass(frozen=True)
class SkillStatus:
    name: str
    purpose: str
    path: str
    exists: bool
    validated: bool
    scripts: tuple[str, ...]
    missing_scripts: tuple[str, ...]
    status: str
    errors: tuple[str, ...] = ()


def registry_path(project_root: Path) -> Path:
    raw = os.environ.get("AGENTOFFICE_SKILLS_REGISTRY", "").strip()
    if raw:
        return Path(raw).expanduser()
    return project_root / DEFAULT_REGISTRY_RELATIVE_PATH


def load_skill_registry(project_root: Path) -> list[SkillRegistryEntry]:
    path = registry_path(project_root)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    raw_skills = data.get("skills", []) if isinstance(data, dict) else []
    entries: list[SkillRegistryEntry] = []
    for item in raw_skills:
        if not isinstance(item, dict):
            continue
        entries.append(
            SkillRegistryEntry(
                name=str(item.get("name", "")).strip(),
                purpose=str(item.get("purpose", "")).strip(),
                path=str(item.get("path", "")).strip(),
                expected_scripts=tuple(str(script).strip() for script in item.get("expected_scripts", []) if str(script).strip()),
            )
        )
    return entries


def collect_skill_status(project_root: Path) -> list[SkillStatus]:
    return [validate_skill_entry(entry) for entry in load_skill_registry(project_root)]


def validate_skill_entry(entry: SkillRegistryEntry) -> SkillStatus:
    errors: list[str] = []
    if not SKILL_NAME_RE.match(entry.name):
        errors.append("invalid skill name")
    if not entry.purpose:
        errors.append("missing purpose")
    resolved_path = resolve_skill_path(entry.path)
    exists = resolved_path.exists() and resolved_path.is_dir()
    skill_md = resolved_path / "SKILL.md"
    if not exists:
        errors.append("skill path missing")
    elif not skill_md.exists():
        errors.append("SKILL.md missing")
    elif not validate_skill_frontmatter(skill_md, entry.name):
        errors.append("SKILL.md frontmatter invalid")

    missing_scripts = tuple(
        script
        for script in entry.expected_scripts
        if not (resolved_path / script).exists()
    )
    if missing_scripts:
        errors.append("expected scripts missing")

    validated = exists and not errors
    status = "ok" if validated else "missing" if not exists else "invalid"
    return SkillStatus(
        name=entry.name,
        purpose=entry.purpose,
        path=display_path(resolved_path),
        exists=exists,
        validated=validated,
        scripts=entry.expected_scripts,
        missing_scripts=missing_scripts,
        status=status,
        errors=tuple(errors),
    )


def validate_skill_frontmatter(skill_md: Path, expected_name: str) -> bool:
    text = skill_md.read_text(encoding="utf-8")
    lines = text.splitlines()
    if len(lines) < 4 or lines[0].strip() != "---":
        return False
    try:
        end = lines[1:].index("---") + 1
    except ValueError:
        return False
    frontmatter = lines[1:end]
    values: dict[str, str] = {}
    for line in frontmatter:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values.get("name") == expected_name and bool(values.get("description"))


def resolve_skill_path(raw_path: str) -> Path:
    expanded = os.path.expandvars(raw_path)
    return Path(expanded).expanduser()


def display_path(path: Path) -> str:
    home = Path.home()
    try:
        relative = path.resolve().relative_to(home.resolve())
    except (OSError, ValueError):
        return str(path)
    return "~/" + relative.as_posix()


def skills_as_dicts(project_root: Path) -> list[dict[str, Any]]:
    return [asdict(status) for status in collect_skill_status(project_root)]


def format_skills_table(project_root: Path) -> str:
    lines = ["skill | exists | validated | scripts | status | path"]
    for status in collect_skill_status(project_root):
        scripts = ",".join(status.scripts) if status.scripts else "-"
        lines.append(
            " | ".join(
                [
                    status.name,
                    bool_text(status.exists),
                    bool_text(status.validated),
                    scripts,
                    status.status,
                    status.path,
                ]
            )
        )
    return "\n".join(lines)


def format_skills_doctor(project_root: Path) -> str:
    statuses = collect_skill_status(project_root)
    lines = [
        "AgentOffice skills doctor",
        f"- registry: {display_path(registry_path(project_root))}",
        f"- registered_skills: {len(statuses)}",
        "- skills:",
    ]
    for status in statuses:
        lines.append(
            f"  - {status.name}: exists={bool_text(status.exists)}; validated={bool_text(status.validated)}; status={status.status}; path={status.path}"
        )
        if status.scripts:
            for script in status.scripts:
                present = script not in status.missing_scripts
                lines.append(f"    - script {script}: exists={bool_text(present)}")
        for error in status.errors:
            lines.append(f"    - error: {error}")
    lines.extend(
        [
            "- safety:",
            "  - env_file_read: false",
            "  - secrets_printed: false",
            "  - skill_files_committed: false",
        ]
    )
    return "\n".join(lines)


def bool_text(value: bool) -> str:
    return str(bool(value)).lower()
