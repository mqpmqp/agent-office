from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from agent_office.packets import (
    CONTRACT_SCHEMA_VERSION,
    PACKET_VERSION,
    execution_packet_payload,
    packet_contract_validation_payload,
)


class PacketContractValidationTests(unittest.TestCase):
    def test_codex_contract_validation_payload_is_stable_and_valid(self) -> None:
        payload = packet_contract_validation_payload("P6-10", "lowest-cost", "codex")

        self.assertEqual(
            list(payload),
            [
                "valid",
                "schema_version",
                "objective",
                "profile",
                "actor",
                "packet_identity",
                "checks",
                "external_behavior",
            ],
        )
        self.assertTrue(payload["valid"])
        self.assertEqual(payload["schema_version"], CONTRACT_SCHEMA_VERSION)
        self.assertEqual(payload["objective"], "P6-10")
        self.assertEqual(payload["profile"], "lowest-cost")
        self.assertEqual(payload["actor"], "codex")
        self.assertEqual(
            payload["packet_identity"],
            {
                "packet_version": PACKET_VERSION,
                "objective": "P6-10",
                "profile": "lowest-cost",
                "actor": "codex",
            },
        )
        self.assertEqual(
            [check["name"] for check in payload["checks"]],
            [
                "known_objective",
                "known_profile",
                "known_actor",
                "packet_schema_version_present",
                "identity_fields_match_requested_inputs",
                "deterministic_identity_fields_present",
                "required_packet_sections_present",
                "execution_enabled_false",
                "provider_calls_false",
                "runtime_adapter_calls_false",
                "env_reads_false",
                "env_var_printing_false",
                "artifact_writes_false",
                "no_real_execution_performed",
            ],
        )
        self.assertEqual({check["status"] for check in payload["checks"]}, {"pass"})
        self.assertEqual(
            payload["external_behavior"],
            {
                "provider_calls": False,
                "runtime_adapter_calls": False,
                "env_reads": False,
                "env_var_printing": False,
                "artifact_writes": False,
            },
        )
        json.dumps(payload)

    def test_contract_validation_covers_all_packet_actors(self) -> None:
        for actor in ("codex", "reviewer", "judge"):
            with self.subTest(actor=actor):
                payload = packet_contract_validation_payload("P6-10", "lowest-cost", actor)

                self.assertTrue(payload["valid"])
                self.assertEqual(payload["actor"], actor)
                self.assertEqual(payload["external_behavior"]["provider_calls"], False)
                self.assertEqual(payload["external_behavior"]["runtime_adapter_calls"], False)

    def test_p6_16_contract_validation_covers_all_packet_actors(self) -> None:
        for actor in ("codex", "reviewer", "judge"):
            with self.subTest(actor=actor):
                payload = packet_contract_validation_payload("P6-16", "lowest-cost", actor)

                self.assertTrue(payload["valid"])
                self.assertEqual(payload["schema_version"], CONTRACT_SCHEMA_VERSION)
                self.assertEqual(payload["objective"], "P6-16")
                self.assertEqual(payload["profile"], "lowest-cost")
                self.assertEqual(payload["actor"], actor)
                self.assertEqual(
                    payload["packet_identity"],
                    {
                        "packet_version": PACKET_VERSION,
                        "objective": "P6-16",
                        "profile": "lowest-cost",
                        "actor": actor,
                    },
                )
                self.assertEqual({check["status"] for check in payload["checks"]}, {"pass"})
                self.assertEqual(
                    payload["external_behavior"],
                    {
                        "provider_calls": False,
                        "runtime_adapter_calls": False,
                        "env_reads": False,
                        "env_var_printing": False,
                        "artifact_writes": False,
                    },
                )

    def test_contract_failure_is_reported_without_throwing(self) -> None:
        bad_packet = execution_packet_payload("P6-10", "lowest-cost", "codex")
        bad_packet["execution_enabled"] = True
        bad_packet["artifact_writes"] = True

        with patch("agent_office.packets.execution_packet_payload", return_value=bad_packet):
            payload = packet_contract_validation_payload("P6-10", "lowest-cost", "codex")

        self.assertFalse(payload["valid"])
        self.assertIn(
            {"name": "execution_enabled_false", "status": "fail"},
            payload["checks"],
        )
        self.assertIn(
            {"name": "artifact_writes_false", "status": "fail"},
            payload["checks"],
        )

    def test_unknown_inputs_raise_clear_errors(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown objective: UNKNOWN"):
            packet_contract_validation_payload("UNKNOWN", "lowest-cost", "codex")
        with self.assertRaisesRegex(ValueError, "Unknown provider profile: UNKNOWN"):
            packet_contract_validation_payload("P6-10", "UNKNOWN", "codex")
        with self.assertRaisesRegex(ValueError, "Unknown packet actor: UNKNOWN"):
            packet_contract_validation_payload("P6-10", "lowest-cost", "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
