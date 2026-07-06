"""Deterministic framework-status contract for the FUGU-like reset.

Exposes the framework's architectural invariants as a stable, local-only,
machine-readable document. Reads nothing from disk, the environment, or the
network; the output is a pure function of `framework_types`.
"""

from __future__ import annotations

import json

from . import framework_types as ft


def build_framework_status() -> dict[str, object]:
    return {
        "schema_version": ft.SCHEMA_VERSION,
        "product": ft.PRODUCT_NAME,
        "architecture_target": ft.ARCHITECTURE_TARGET,
        "mode": "framework_reset",
        "runtime_model": ft.RUNTIME_MODEL,
        "provider_calls_enabled": False,
        "env_reads_allowed": False,
        "trading_bot_scope": False,
        "core_objects": list(ft.CORE_OBJECTS),
        "next_slices": list(ft.NEXT_SLICES),
    }


def render_framework_status_json() -> str:
    return json.dumps(build_framework_status(), indent=2, sort_keys=False)


def render_framework_status_text() -> str:
    status = build_framework_status()
    lines = [
        f"{status['product']}: {status['architecture_target']}",
        f"mode: {status['mode']}",
        f"runtime model: {status['runtime_model']}",
        f"provider calls enabled: {status['provider_calls_enabled']}",
        f"env reads allowed: {status['env_reads_allowed']}",
        f"trading bot scope: {status['trading_bot_scope']}",
        "core objects: " + ", ".join(status["core_objects"]),
        "next slices: " + ", ".join(status["next_slices"]),
        "docs: docs/AGENTOFFICE_FUGU_LIKE_FRAMEWORK.md",
    ]
    return "\n".join(lines)
