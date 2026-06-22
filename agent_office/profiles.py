from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


ALLOWED_ROLES = ("context", "implement", "review", "judge")
ALLOWED_PROVIDERS = (
    "chatgpt-manual",
    "codex",
    "mock",
    "gemini",
    "grok",
    "claude",
    "openai-api",
)

# ponytail: static preview metadata only; runtime provider routing belongs in a future phase.
PROVIDER_EXECUTION_CATEGORIES: Mapping[str, str] = MappingProxyType(
    {
        "chatgpt-manual": "manual",
        "codex": "local-cli",
        "mock": "mock",
        "gemini": "optional-provider",
        "grok": "optional-provider",
        "claude": "optional-provider",
        "openai-api": "future-api",
    }
)


class ProfileError(ValueError):
    pass


@dataclass(frozen=True)
class ProviderProfile:
    name: str
    roles: Mapping[str, str]


_BUILT_IN_PROFILES: Mapping[str, ProviderProfile] = MappingProxyType(
    {
        "lowest-cost": ProviderProfile(
            name="lowest-cost",
            roles=MappingProxyType(
                {
                    "context": "chatgpt-manual",
                    "implement": "codex",
                    "review": "chatgpt-manual",
                    "judge": "chatgpt-manual",
                }
            ),
        ),
        "mock-ci": ProviderProfile(
            name="mock-ci",
            roles=MappingProxyType(
                {
                    "context": "mock",
                    "implement": "mock",
                    "review": "mock",
                    "judge": "mock",
                }
            ),
        ),
        "multi-vendor": ProviderProfile(
            name="multi-vendor",
            roles=MappingProxyType(
                {
                    "context": "gemini",
                    "implement": "codex",
                    "review": "grok",
                    "judge": "claude",
                }
            ),
        ),
    }
)


def default_profile_name() -> str:
    return "lowest-cost"


def list_profiles() -> tuple[str, ...]:
    return tuple(_BUILT_IN_PROFILES)


def get_profile(name: str) -> ProviderProfile:
    try:
        profile = _BUILT_IN_PROFILES[name]
    except KeyError as exc:
        raise ProfileError(f"Unknown provider profile: {name}") from exc
    validate_profile(profile)
    return profile


def provider_execution_category(provider: str) -> str:
    try:
        return PROVIDER_EXECUTION_CATEGORIES[provider]
    except KeyError as exc:
        raise ProfileError(f"Unknown provider execution category: {provider}") from exc


def profile_plan_payload(name: str) -> dict[str, object]:
    profile = get_profile(name)
    default_name = default_profile_name()
    return {
        "profile": profile.name,
        "default_profile": default_name,
        "is_default": profile.name == default_name,
        "execution_enabled": False,
        "provider_calls": False,
        "artifact_writes": False,
        "roles": [
            {
                "role": role,
                "provider": profile.roles[role],
                "execution": provider_execution_category(profile.roles[role]),
            }
            for role in ALLOWED_ROLES
        ],
    }


def validate_profile(profile: ProviderProfile | Mapping[str, object]) -> None:
    name, roles = _profile_name_and_roles(profile)
    expected_roles = set(ALLOWED_ROLES)
    actual_roles = set(roles)
    unknown_roles = sorted(actual_roles - expected_roles)
    if unknown_roles:
        raise ProfileError(f"Profile `{name}` contains unknown role(s): {', '.join(unknown_roles)}")
    missing_roles = sorted(expected_roles - actual_roles)
    if missing_roles:
        raise ProfileError(f"Profile `{name}` is missing role(s): {', '.join(missing_roles)}")

    unknown_providers = sorted({provider for provider in roles.values() if provider not in ALLOWED_PROVIDERS})
    if unknown_providers:
        raise ProfileError(f"Profile `{name}` contains unknown provider(s): {', '.join(unknown_providers)}")

    if name == default_profile_name():
        default_providers = set(roles.values())
        if "openai-api" in default_providers:
            raise ProfileError("openai-api is allowed in the registry but cannot be a default provider.")


def _profile_name_and_roles(profile: ProviderProfile | Mapping[str, object]) -> tuple[str, Mapping[str, str]]:
    if isinstance(profile, ProviderProfile):
        return profile.name, profile.roles
    raw_name = profile.get("name", "<unnamed>")
    raw_roles = profile.get("roles", {})
    if not isinstance(raw_name, str):
        raise ProfileError("Profile name must be a string.")
    if not isinstance(raw_roles, Mapping):
        raise ProfileError(f"Profile `{raw_name}` roles must be a mapping.")
    roles: dict[str, str] = {}
    for role, provider in raw_roles.items():
        if not isinstance(role, str):
            raise ProfileError(f"Profile `{raw_name}` role names must be strings.")
        if not isinstance(provider, str):
            raise ProfileError(f"Profile `{raw_name}` provider for role `{role}` must be a string.")
        roles[role] = provider
    return raw_name, roles
