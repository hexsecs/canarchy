from __future__ import annotations

import unittest

from canarchy.j1939 import decompose_arbitration_id


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
