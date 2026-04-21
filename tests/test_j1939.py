from __future__ import annotations

import unittest

from canarchy.j1939 import decompose_arbitration_id, spn_observations
from canarchy.models import CanFrame


class J1939Tests(unittest.TestCase):
    def test_decompose_broadcast_pgn_identifier(self) -> None:
        identifier = decompose_arbitration_id(0x18FEEE31)

        self.assertEqual(identifier.priority, 6)
        self.assertEqual(identifier.pgn, 65262)
        self.assertIsNone(identifier.destination_address)
        self.assertEqual(identifier.source_address, 0x31)

    def test_decompose_peer_to_peer_identifier(self) -> None:
        identifier = decompose_arbitration_id(0x18EAFF31)

        self.assertEqual(identifier.pgn, 59904)
        self.assertEqual(identifier.destination_address, 0xFF)
        self.assertEqual(identifier.pdu_format, 0xEA)

    def test_reject_invalid_29bit_identifier(self) -> None:
        with self.assertRaisesRegex(ValueError, "29-bit"):
            decompose_arbitration_id(0x3FFFFFFF)


class SpnObservationsTests(unittest.TestCase):
    # SPN 175 (Engine Oil Temperature 1): PGN 65262, start byte 2, length 2 bytes,
    # resolution 0.03125, offset -273.0. Frame ID 0x18FEEE31.

    def _make_frame(self, data: bytes) -> CanFrame:
        return CanFrame(
            arbitration_id=0x18FEEE31,
            data=data,
            timestamp=0.0,
            is_extended_id=True,
        )

    def test_16bit_error_value_returns_none(self) -> None:
        # 0xFFFF is the J1939 not-available indicator for 16-bit signals
        frame = self._make_frame(bytes([0x00, 0x00, 0xFF, 0xFF]))
        obs = spn_observations([frame], 175)
        self.assertEqual(len(obs), 1)
        self.assertIsNone(obs[0]["value"])
        self.assertEqual(obs[0]["raw"], "ffff")

    def test_valid_16bit_value_returns_scaled_result(self) -> None:
        # bytes [0x20, 0x22] little-endian = 0x2220 = 8736
        # value = 8736 * 0.03125 + (-273.0) = 0.0 degC
        frame = self._make_frame(bytes([0x00, 0x00, 0x20, 0x22]))
        obs = spn_observations([frame], 175)
        self.assertEqual(len(obs), 1)
        self.assertAlmostEqual(obs[0]["value"], 0.0)

    def test_8bit_error_value_returns_none(self) -> None:
        # SPN 110 (Engine Coolant Temperature): PGN 65262, start byte 0, length 1 byte
        # 0xFF is the J1939 not-available indicator for 8-bit signals
        frame = self._make_frame(bytes([0xFF, 0x00, 0x00, 0x00]))
        obs = spn_observations([frame], 110)
        self.assertEqual(len(obs), 1)
        self.assertIsNone(obs[0]["value"])

    def test_valid_8bit_value_returns_scaled_result(self) -> None:
        # SPN 110: raw 0x7D = 125, value = 125 * 1.0 + (-40.0) = 85.0 degC
        frame = self._make_frame(bytes([0x7D, 0x00, 0x00, 0x00]))
        obs = spn_observations([frame], 110)
        self.assertEqual(len(obs), 1)
        self.assertEqual(obs[0]["value"], 85.0)
