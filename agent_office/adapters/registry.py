from __future__ import annotations

from .base import AdapterUnavailable, AgentAdapter
from .codex import CodexAdapter
from .gemini import GeminiAdapter
from .grok import GrokAdapter
from .mock import MockAdapter


def adapter_catalog() -> dict[str, dict[str, object]]:
    return {
        "mock": {"roles": ["context", "implement", "redteam", "final"], "real": False},
        "codex": {"roles": ["implement"], "real": True},
        "gemini": {"roles": ["context"], "real": True},
        "grok": {"roles": ["redteam"], "real": True},
        "claude": {"roles": ["final"], "real": True, "implemented": False},
    }


def get_adapter(role: str, mode: str, adapter_name: str | None) -> AgentAdapter:
    if mode == "mock":
        return MockAdapter()
    if mode != "real":
        raise AdapterUnavailable(f"Unknown adapter mode: {mode}")
    if role == "context":
        if adapter_name == "gemini":
            return GeminiAdapter()
        raise AdapterUnavailable("Real context requires --adapter gemini. Use --mock for the safe context path.")
    if role == "implement" and adapter_name in {None, "codex"}:
        return CodexAdapter()
    if role == "redteam":
        if adapter_name == "grok":
            return GrokAdapter()
        raise AdapterUnavailable("Real redteam requires --adapter grok. Use --mock for the safe redteam path.")
    if role == "final":
        raise AdapterUnavailable("Claude final judge real adapter is not implemented yet. Use --mock.")
    if adapter_name == "mock":
        return MockAdapter()
    raise AdapterUnavailable(f"No real adapter is available for role `{role}`. Use --mock.")
