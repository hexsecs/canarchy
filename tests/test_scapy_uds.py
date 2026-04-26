from __future__ import annotations

import unittest
from unittest.mock import patch

from canarchy import scapy_uds


class ScapyUdsTests(unittest.TestCase):
    def tearDown(self) -> None:
        scapy_uds._load_uds_packet_class.cache_clear()

    def test_scapy_uds_available_false_when_dependency_missing(self) -> None:
        with patch("canarchy.scapy_uds.import_module", side_effect=ImportError):
            scapy_uds._load_uds_packet_class.cache_clear()
            self.assertFalse(scapy_uds.scapy_uds_available())
            self.assertIsNone(scapy_uds.inspect_uds_payload(bytes.fromhex("1003")))

    def test_inspect_uds_payload_uses_loaded_packet_decoder(self) -> None:
        class FakePacket:
            def __init__(self, payload: bytes) -> None:
                self.payload = payload
                self.fields = {"sid": payload[0], "data": payload[1:]}

            def summary(self) -> str:
                return "UDS / FakePacket"

        with patch("canarchy.scapy_uds._load_uds_packet_class", return_value=FakePacket):
            decoded = scapy_uds.inspect_uds_payload(bytes.fromhex("1003"))

        self.assertEqual(
            decoded,
            {
                "summary": "UDS / FakePacket",
                "fields": {"sid": 0x10, "data": "03"},
            },
        )
