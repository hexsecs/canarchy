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

    def test_decompose_matches_canj1939_reference(self) -> None:
        """The arithmetic decoder must match the can-j1939 library bit-for-bit.

        Guards the performance rewrite in issue #441 against semantic drift.
        """
        import j1939 as can_j1939

        def reference(arbitration_id: int) -> tuple[int, ...]:
            mid = can_j1939.MessageId(can_id=arbitration_id)
            pgn = can_j1939.ParameterGroupNumber()
            pgn.from_message_id(mid)
            if pgn.is_pdu1_format:
                pgn_value = (pgn.data_page << 16) | (pgn.pdu_format << 8)
                destination = pgn.pdu_specific
            else:
                pgn_value = pgn.value
                destination = None
            return (
                mid.priority,
                pgn.data_page,
                pgn.pdu_format,
                pgn.pdu_specific,
                mid.source_address,
                pgn_value,
                destination if destination is not None else -1,
            )

        sample_ids = [
            0x00000000,
            0x1FFFFFFF,
            0x18FEEE31,
            0x18EAFF31,
            0x18EBFF31,
            0x0CF00400,
            0x18FECA31,
            0x10ECFF00,
        ]
        sample_ids += [(idx * 2654435761) & 0x1FFFFFFF for idx in range(2000)]

        for arbitration_id in sample_ids:
            identifier = decompose_arbitration_id(arbitration_id)
            got = (
                identifier.priority,
                identifier.data_page,
                identifier.pdu_format,
                identifier.pdu_specific,
                identifier.source_address,
                identifier.pgn,
                identifier.destination_address
                if identifier.destination_address is not None
                else -1,
            )
            self.assertEqual(got, reference(arbitration_id), hex(arbitration_id))


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


class FmiCatalogTests(unittest.TestCase):
    """Bundled SAE J1939-73 FMI catalog resolves FMIs to descriptions (#409)."""

    def test_fmi_lookup_known_values(self) -> None:
        from canarchy.j1939_metadata import fmi_lookup

        self.assertEqual(fmi_lookup(3), "Voltage Above Normal, Or Shorted To High Source")
        self.assertEqual(fmi_lookup(5), "Current Below Normal Or Open Circuit")
        self.assertEqual(fmi_lookup(31), "Condition Exists")

    def test_fmi_lookup_out_of_range_returns_none(self) -> None:
        from canarchy.j1939_metadata import fmi_lookup

        self.assertIsNone(fmi_lookup(32))
        self.assertIsNone(fmi_lookup(-1))

    def test_dm1_dtcs_carry_spn_name_and_fmi_description(self) -> None:
        from pathlib import Path

        from canarchy.j1939_decoder import get_j1939_decoder
        from canarchy.transport import LocalTransport

        fixtures = Path(__file__).parent / "fixtures"
        frames = LocalTransport().frames_from_file(str(fixtures / "j1939_dm1_spn175.candump"))
        messages = get_j1939_decoder().dm1_messages(frames)

        self.assertEqual(len(messages), 1)
        dtc = messages[0]["dtcs"][0]
        self.assertEqual(dtc["spn"], 175)
        self.assertEqual(dtc["name"], "Engine Oil Temperature 1")
        self.assertEqual(dtc["fmi"], 5)
        self.assertEqual(dtc["fmi_description"], "Current Below Normal Or Open Circuit")


class SpnOverrideTests(unittest.TestCase):
    """OEM/proprietary SPN extensions merge over the bundled catalog (#409)."""

    def _reload_spn_cache(self) -> None:
        from canarchy import j1939_metadata

        j1939_metadata._spn_data.cache_clear()
        j1939_metadata.decodable_spns.cache_clear()

    def test_spn_overrides_resolve_proprietary_names(self) -> None:
        import json
        import os
        import tempfile

        from canarchy.j1939_metadata import spn_lookup

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump({"520001": {"name": "OEM Proprietary Lane Camera Status"}}, fh)
            override_path = fh.name

        saved = os.environ.get("CANARCHY_J1939_SPN_OVERRIDES")
        os.environ["CANARCHY_J1939_SPN_OVERRIDES"] = override_path
        self._reload_spn_cache()
        try:
            meta = spn_lookup(520001)
            self.assertIsNotNone(meta)
            self.assertEqual(meta["name"], "OEM Proprietary Lane Camera Status")
            # Bundled entries survive the merge.
            self.assertEqual(spn_lookup(175)["name"], "Engine Oil Temperature 1")
        finally:
            if saved is None:
                os.environ.pop("CANARCHY_J1939_SPN_OVERRIDES", None)
            else:
                os.environ["CANARCHY_J1939_SPN_OVERRIDES"] = saved
            os.unlink(override_path)
            self._reload_spn_cache()
