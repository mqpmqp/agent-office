from __future__ import annotations

import importlib
import os
import sys
import tempfile
import unittest
from collections.abc import MutableMapping
from pathlib import Path
from unittest.mock import patch

from agent_office.profiles import (
    ProfileError,
    ProviderProfile,
    default_profile_name,
    get_profile,
    list_profiles,
    validate_profile,
)


class EnvGuard(MutableMapping[str, str]):
    def __getitem__(self, key: str) -> str:
        raise AssertionError(f"environment was read: {key}")

    def __setitem__(self, key: str, value: str) -> None:
        raise AssertionError(f"environment was written: {key}")

    def __delitem__(self, key: str) -> None:
        raise AssertionError(f"environment was deleted: {key}")

    def __iter__(self):
        raise AssertionError("environment was iterated")

    def __len__(self) -> int:
        raise AssertionError("environment length was read")


class ProviderProfileTests(unittest.TestCase):
    def test_default_profile_is_lowest_cost(self) -> None:
        self.assertEqual(default_profile_name(), "lowest-cost")
        self.assertEqual(list_profiles()[0], "lowest-cost")

    def test_lowest_cost_profile(self) -> None:
        profile = get_profile("lowest-cost")
        self.assertEqual(profile.roles["context"], "chatgpt-manual")
        self.assertEqual(profile.roles["implement"], "codex")
        self.assertEqual(profile.roles["review"], "chatgpt-manual")
        self.assertEqual(profile.roles["judge"], "chatgpt-manual")

    def test_mock_ci_is_all_mock(self) -> None:
        profile = get_profile("mock-ci")
        self.assertEqual(set(profile.roles.values()), {"mock"})

    def test_multi_vendor_exists_but_is_not_default(self) -> None:
        profile = get_profile("multi-vendor")
        self.assertIn("multi-vendor", list_profiles())
        self.assertNotEqual(default_profile_name(), "multi-vendor")
        self.assertEqual(
            dict(profile.roles),
            {"context": "gemini", "implement": "codex", "review": "grok", "judge": "claude"},
        )

    def test_unknown_profile_raises(self) -> None:
        with self.assertRaisesRegex(ProfileError, "Unknown provider profile"):
            get_profile("missing")

    def test_illegal_provider_raises(self) -> None:
        profile = ProviderProfile(
            name="bad-provider",
            roles={"context": "mock", "implement": "codex", "review": "unknown", "judge": "mock"},
        )
        with self.assertRaisesRegex(ProfileError, "unknown provider"):
            validate_profile(profile)

    def test_illegal_role_raises(self) -> None:
        profile = ProviderProfile(
            name="bad-role",
            roles={"context": "mock", "implement": "codex", "review": "mock", "judge": "mock", "extra": "mock"},
        )
        with self.assertRaisesRegex(ProfileError, "unknown role"):
            validate_profile(profile)

    def test_openai_api_is_allowed_but_not_default(self) -> None:
        optional_profile = ProviderProfile(
            name="future-openai-api",
            roles={"context": "openai-api", "implement": "codex", "review": "mock", "judge": "mock"},
        )
        validate_profile(optional_profile)

        bad_default = ProviderProfile(
            name="lowest-cost",
            roles={"context": "openai-api", "implement": "codex", "review": "mock", "judge": "mock"},
        )
        with self.assertRaisesRegex(ProfileError, "cannot be a default provider"):
            validate_profile(bad_default)

    def test_importing_profiles_does_not_read_env(self) -> None:
        previous = sys.modules.pop("agent_office.profiles", None)
        try:
            with patch.object(os, "environ", EnvGuard()):
                module = importlib.import_module("agent_office.profiles")
                self.assertEqual(module.default_profile_name(), "lowest-cost")
        finally:
            sys.modules.pop("agent_office.profiles", None)
            if previous is not None:
                sys.modules["agent_office.profiles"] = previous

    def test_registry_functions_do_not_write_files(self) -> None:
        with patch.object(Path, "write_text", side_effect=AssertionError("write_text should not be called")):
            self.assertIn("lowest-cost", list_profiles())
            self.assertEqual(get_profile("mock-ci").roles["context"], "mock")
            validate_profile(get_profile("multi-vendor"))

    def test_registry_functions_do_not_create_ai_runtime_files(self) -> None:
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                get_profile("lowest-cost")
                validate_profile(get_profile("mock-ci"))
                self.assertFalse((Path(tmp) / ".ai").exists())
            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
