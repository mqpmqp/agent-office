from __future__ import annotations

import re
from dataclasses import dataclass, field


PATCH_PATH_RE = re.compile(r"^(?:diff --git a/([^ ]+) b/([^ ]+)|(?:---|\+\+\+) ([^\t\n ]+))", re.MULTILINE)
SECRET_ASSIGNMENT_RE = re.compile(
    r"(?im)^\+(?!\+\+)\s*[A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|AUTH|COOKIE)[A-Z0-9_]*\s*[:=]\s*['\"]?[^'\"\s]+"
)
SECRET_VALUE_RE = re.compile(
    r"(?i)(?:sk-[A-Za-z0-9_-]{12,}|xox[baprs]-[A-Za-z0-9-]{12,}|gh[pousr]_[A-Za-z0-9_]{12,}|Bearer\s+[A-Za-z0-9._=-]{12,})"
)
UNSAFE_TRADING_RE = re.compile(r"(?i)\bLIVE_(?:BUY|SELL|LONG|SHORT)\b")
SAFETY_DEFAULT_RE = re.compile(
    r"(?im)^\+(?!\+\+).*(?:DRY_RUN|dry_run)\s*[:=]\s*false|^\+(?!\+\+).*(?:ALLOW_NON_DRY_RUN|allow_non_dry_run)\s*[:=]\s*true|^\+(?!\+\+).*(?:CAN_EXECUTE_COMMANDS|can_execute_commands)\s*[:=]\s*true"
)
ALL_REAL_RE = re.compile(r"(?im)^\+(?!\+\+).*AGENTOFFICE_AGENT_MODE\s*=\s*real|^\+(?!\+\+).*all_real_adapters\s*[:=]\s*true")

ALLOWED_TOP_LEVEL = {
    ".gitignore",
    ".env.example",
    "README.md",
    "pyproject.toml",
    "requirements.txt",
}
ALLOWED_DIRS = {
    "agent_office",
    "docs",
    "tests",
    "scripts",
    "deploy",
}
PRIVATE_KEY_MARKERS = (".pem", ".key", "id_rsa", "id_ed25519", "private_key")


@dataclass(frozen=True)
class PatchValidationResult:
    status: str
    reasons: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def validate_patch_diff(patch_text: str) -> PatchValidationResult:
    reasons: list[str] = []
    risk_flags: list[str] = []
    paths = _extract_patch_paths(patch_text)

    if not patch_text.strip():
        reasons.append("patch is empty")
        risk_flags.append("empty_patch")

    for path in paths:
        lower = path.lower()
        if lower in {".env", "env"} or lower.startswith(".env.") or "/.env" in lower:
            reasons.append(f"patch modifies forbidden env file: {path}")
            risk_flags.append("env_file")
        if any(marker in lower for marker in PRIVATE_KEY_MARKERS):
            reasons.append(f"patch modifies private key material: {path}")
            risk_flags.append("private_key")
        if lower.startswith("/etc/") or lower.startswith("../") or lower.startswith("/"):
            reasons.append(f"patch targets path outside project safety boundary: {path}")
            risk_flags.append("outside_project")
        if not _is_allowed_project_path(path):
            reasons.append(f"patch targets path outside allowed review set: {path}")
            risk_flags.append("outside_allowed_files")
        if _is_guard_test_delete(patch_text, lower):
            reasons.append(f"patch deletes guard test content: {path}")
            risk_flags.append("guard_test_delete")

    if SECRET_ASSIGNMENT_RE.search(patch_text) or SECRET_VALUE_RE.search(patch_text):
        reasons.append("patch appears to add a secret or credential")
        risk_flags.append("secret_addition")
    if SAFETY_DEFAULT_RE.search(patch_text):
        reasons.append("patch weakens adapter safety defaults")
        risk_flags.append("weaken_safety_defaults")
    if ALL_REAL_RE.search(patch_text):
        reasons.append("patch appears to enable all real adapters")
        risk_flags.append("enable_all_real_adapters")
    if UNSAFE_TRADING_RE.search(patch_text):
        reasons.append("patch contains unsafe live trading action markers")
        risk_flags.append("unsafe_trading_action")

    if reasons:
        return PatchValidationResult("rejected", _unique(reasons), _unique(risk_flags))
    return PatchValidationResult("ok", [], [])


def _extract_patch_paths(patch_text: str) -> list[str]:
    paths: list[str] = []
    for match in PATCH_PATH_RE.finditer(patch_text):
        for value in match.groups():
            if not value:
                continue
            path = value
            if path == "/dev/null":
                continue
            if path.startswith("a/") or path.startswith("b/"):
                path = path[2:]
            paths.append(path)
    return _unique(paths)


def _is_allowed_project_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    if normalized in ALLOWED_TOP_LEVEL:
        return True
    first = normalized.split("/", 1)[0]
    return first in ALLOWED_DIRS


def _is_guard_test_delete(patch_text: str, lower_path: str) -> bool:
    if not lower_path.startswith("tests/"):
        return False
    deleted_lines = [line for line in patch_text.splitlines() if line.startswith("-") and not line.startswith("---")]
    if not deleted_lines:
        return False
    guard_markers = ("fallback", "dry_run", "secret", "env", "safety", "validator", "guard")
    if any(marker in lower_path for marker in guard_markers):
        return True
    return any("def test_" in line or line.lstrip("-").lstrip().startswith("class Test") for line in deleted_lines)


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result
