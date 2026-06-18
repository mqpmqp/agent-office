from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Mapping


ADAPTER_MODE_NAMES = ("gemini", "codex", "grok", "claude")
VALID_MODES = {"mock", "real", "disabled"}


@dataclass(frozen=True)
class AdapterModeConfig:
    name: str
    role: str
    mode: str
    enabled: bool
    dry_run: bool
    fallback_to_mock: bool
    timeout_seconds: int
    max_input_chars: int
    max_output_chars: int
    max_cost_usd: float
    required_env: tuple[str, ...]
    can_read_files: bool
    can_write_files: bool
    can_execute_commands: bool
    can_network: bool
    allowed_input_files: tuple[str, ...]
    allowed_output_files: tuple[str, ...]
    allow_non_dry_run: bool = False
    config_errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class AdapterModeValidation:
    name: str
    mode: str
    dry_run: bool
    env_ok: bool
    fallback_to_mock: bool
    status: str
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.errors and self.status in {"ok", "disabled"}


ADAPTER_MODE_SPECS: dict[str, dict[str, object]] = {
    "gemini": {
        "role": "context",
        "timeout_seconds": 120,
        "max_input_chars": 20000,
        "max_output_chars": 12000,
        "required_env": ("AGENTOFFICE_GEMINI_CMD",),
        "can_read_files": True,
        "can_write_files": True,
        "allowed_input_files": ("brief.md", "README.md", "docs/**", "AGENTS.md"),
        "allowed_output_files": ("gemini-context.md",),
    },
    "codex": {
        "role": "implement",
        "timeout_seconds": 1200,
        "max_input_chars": 24000,
        "max_output_chars": 12000,
        "required_env": ("AGENTOFFICE_CODEX_CMD",),
        "can_read_files": True,
        "can_write_files": True,
        "allowed_input_files": ("brief.md", "gemini-context.md", "AGENTS.md"),
        "allowed_output_files": ("codex-report.md", "patch.diff"),
    },
    "grok": {
        "role": "redteam",
        "timeout_seconds": 120,
        "max_input_chars": 24000,
        "max_output_chars": 12000,
        "required_env": ("AGENTOFFICE_GROK_CMD",),
        "can_read_files": True,
        "can_write_files": True,
        "allowed_input_files": ("brief.md", "codex-report.md", "patch.diff"),
        "allowed_output_files": ("grok-review.md",),
    },
    "claude": {
        "role": "final",
        "timeout_seconds": 120,
        "max_input_chars": 12000,
        "max_output_chars": 8000,
        "required_env": ("AGENTOFFICE_CLAUDE_CMD",),
        "can_read_files": True,
        "can_write_files": True,
        "allowed_input_files": ("final-for-claude.md",),
        "allowed_output_files": ("claude-decision.md",),
    },
}


def adapter_for_role(role: str) -> str | None:
    for name, spec in ADAPTER_MODE_SPECS.items():
        if spec["role"] == role:
            return name
    return None


def load_adapter_mode_registry(environ: Mapping[str, str] | None = None) -> dict[str, AdapterModeConfig]:
    env = environ if environ is not None else os.environ
    return {name: load_adapter_mode_config(name, env) for name in ADAPTER_MODE_NAMES}


def load_adapter_mode_config(name: str, environ: Mapping[str, str] | None = None) -> AdapterModeConfig:
    if name not in ADAPTER_MODE_SPECS:
        raise KeyError(f"Unknown adapter mode config: {name}")
    env = environ if environ is not None else os.environ
    spec = ADAPTER_MODE_SPECS[name]
    prefix = f"AGENTOFFICE_{name.upper()}_"
    errors: list[str] = []

    mode = env.get(prefix + "MODE", "mock").strip().lower() or "mock"
    enabled = _bool_env(env, prefix + "ENABLED", mode != "disabled", errors)
    if mode == "disabled":
        enabled = False
    dry_run = _bool_env(env, prefix + "DRY_RUN", mode == "real", errors)
    timeout = _int_env(env, prefix + "TIMEOUT_SECONDS", int(spec["timeout_seconds"]), errors)
    max_input = _int_env(env, prefix + "MAX_INPUT_CHARS", int(spec["max_input_chars"]), errors)
    max_output = _int_env(env, prefix + "MAX_OUTPUT_CHARS", int(spec["max_output_chars"]), errors)
    max_cost = _float_env(env, prefix + "MAX_COST_USD", 0.0, errors)

    return AdapterModeConfig(
        name=name,
        role=str(spec["role"]),
        mode=mode,
        enabled=enabled,
        dry_run=dry_run,
        fallback_to_mock=_bool_env(env, prefix + "FALLBACK_TO_MOCK", False, errors),
        timeout_seconds=timeout,
        max_input_chars=max_input,
        max_output_chars=max_output,
        max_cost_usd=max_cost,
        required_env=tuple(spec["required_env"]),  # type: ignore[arg-type]
        can_read_files=_bool_env(env, prefix + "CAN_READ_FILES", bool(spec["can_read_files"]), errors),
        can_write_files=_bool_env(env, prefix + "CAN_WRITE_FILES", bool(spec["can_write_files"]), errors),
        can_execute_commands=_bool_env(env, prefix + "CAN_EXECUTE_COMMANDS", False, errors),
        can_network=_bool_env(env, prefix + "CAN_NETWORK", False, errors),
        allowed_input_files=tuple(spec["allowed_input_files"]),  # type: ignore[arg-type]
        allowed_output_files=tuple(spec["allowed_output_files"]),  # type: ignore[arg-type]
        allow_non_dry_run=_bool_env(env, prefix + "ALLOW_NON_DRY_RUN", False, errors),
        config_errors=tuple(errors),
    )


def validate_adapter_mode(
    config: AdapterModeConfig, environ: Mapping[str, str] | None = None
) -> AdapterModeValidation:
    env = environ if environ is not None else os.environ
    errors = list(config.config_errors)
    warnings: list[str] = []

    if config.mode not in VALID_MODES:
        errors.append(f"{config.name} mode must be one of: disabled, mock, real.")

    if config.mode == "disabled":
        return AdapterModeValidation(
            name=config.name,
            mode=config.mode,
            dry_run=config.dry_run,
            env_ok=True,
            fallback_to_mock=config.fallback_to_mock,
            status="disabled",
            errors=tuple(errors),
            warnings=tuple(warnings),
        )

    if not config.enabled:
        errors.append(f"{config.name} is not enabled.")

    env_ok = True
    if config.mode == "real":
        missing = [name for name in config.required_env if not env.get(name, "").strip()]
        env_ok = not missing
        if missing:
            errors.append("missing required env: " + ", ".join(missing))
        if not config.dry_run and not config.allow_non_dry_run:
            errors.append(
                f"{config.name} real mode without dry_run requires "
                f"AGENTOFFICE_{config.name.upper()}_ALLOW_NON_DRY_RUN=true."
            )
        if not config.dry_run and not config.can_execute_commands:
            errors.append(
                f"{config.name} command execution requires "
                f"AGENTOFFICE_{config.name.upper()}_CAN_EXECUTE_COMMANDS=true."
            )
    else:
        env_ok = True
        if config.dry_run:
            warnings.append(f"{config.name} dry_run is ignored while mode={config.mode}.")

    if errors:
        status = "env_failed" if config.mode == "real" and not env_ok else "invalid"
    else:
        status = "ok"

    return AdapterModeValidation(
        name=config.name,
        mode=config.mode,
        dry_run=config.dry_run,
        env_ok=env_ok,
        fallback_to_mock=config.fallback_to_mock,
        status=status,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def collect_adapter_mode_status(environ: Mapping[str, str] | None = None) -> dict[str, dict[str, object]]:
    env = environ if environ is not None else os.environ
    registry = load_adapter_mode_registry(env)
    result: dict[str, dict[str, object]] = {}
    for name, config in registry.items():
        validation = validate_adapter_mode(config, env)
        result[name] = {
            "config": asdict(config),
            "validation": asdict(validation),
        }
    return result


def adapter_mode_rows(environ: Mapping[str, str] | None = None) -> list[dict[str, object]]:
    env = environ if environ is not None else os.environ
    rows: list[dict[str, object]] = []
    for name, config in load_adapter_mode_registry(env).items():
        validation = validate_adapter_mode(config, env)
        rows.append(
            {
                "adapter": name,
                "mode": config.mode,
                "dry_run": config.dry_run,
                "env_ok": validation.env_ok,
                "fallback": config.fallback_to_mock,
                "status": validation.status,
            }
        )
    return rows


def format_adapter_mode_table(environ: Mapping[str, str] | None = None) -> str:
    lines = ["adapter | mode | dry_run | env_ok | fallback | status"]
    for row in adapter_mode_rows(environ):
        lines.append(
            " | ".join(
                [
                    str(row["adapter"]),
                    str(row["mode"]),
                    _bool_text(bool(row["dry_run"])),
                    _bool_text(bool(row["env_ok"])),
                    _bool_text(bool(row["fallback"])),
                    str(row["status"]),
                ]
            )
        )
    return "\n".join(lines)


def _bool_env(env: Mapping[str, str], name: str, default: bool, errors: list[str]) -> bool:
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    errors.append(f"{name} must be true or false.")
    return default


def _int_env(env: Mapping[str, str], name: str, default: int, errors: list[str]) -> int:
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw.strip())
    except ValueError:
        errors.append(f"{name} must be an integer.")
        return default
    if value <= 0:
        errors.append(f"{name} must be positive.")
        return default
    return value


def _float_env(env: Mapping[str, str], name: str, default: float, errors: list[str]) -> float:
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = float(raw.strip())
    except ValueError:
        errors.append(f"{name} must be a number.")
        return default
    if value < 0:
        errors.append(f"{name} must be non-negative.")
        return default
    return value


def _bool_text(value: bool) -> str:
    return str(bool(value)).lower()
