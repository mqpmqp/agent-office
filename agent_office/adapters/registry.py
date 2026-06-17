from __future__ import annotations

from .base import AdapterUnavailable, AgentAdapter
from .codex import CodexAdapter
from .gemini import GeminiAdapter
from .mock import MockAdapter


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
    if adapter_name == "mock":
        return MockAdapter()
    if role in {"redteam", "final"}:
        raise AdapterUnavailable(f"Real adapter for `{role}` is not implemented yet. Use --mock.")
    raise AdapterUnavailable(f"No real adapter is available for role `{role}`. Use --mock.")
