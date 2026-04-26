from __future__ import annotations

import unittest
from unittest.mock import patch

from canarchy.models import CanFrame
from canarchy.uds import reassemble_uds_pdus, uds_scan_transactions, uds_trace_transactions


def _frame(arbitration_id: int, data_hex: str, timestamp: float) -> CanFrame:
    return CanFrame(
        arbitration_id=arbitration_id,
        data=bytes.fromhex(data_hex),
        interface="can0",
        timestamp=timestamp,
    )


class UdsIsoTpTests(unittest.TestCase):
    def test_reassemble_uds_pdus_keeps_single_frame_behavior(self) -> None:
        pdus = reassemble_uds_pdus([
            _frame(0x7E8, "0450030032000000", 0.1),
        ])

        self.assertEqual(len(pdus), 1)
        self.assertTrue(pdus[0].complete)
        self.assertEqual(pdus[0].payload, bytes.fromhex("50030032"))

    def test_reassemble_uds_pdus_reassembles_first_and_consecutive_frames(self) -> None:
        pdus = reassemble_uds_pdus([
            _frame(0x7E8, "100A670112345678", 0.1),
            _frame(0x7E0, "3000000000000000", 0.11),
            _frame(0x7E8, "219ABCDEF0000000", 0.12),
        ])

        self.assertEqual(len(pdus), 1)
        self.assertTrue(pdus[0].complete)
        self.assertEqual(pdus[0].payload, bytes.fromhex("6701123456789ABCDEF0"))

    def test_reassemble_uds_pdus_marks_missing_consecutive_frame_incomplete(self) -> None:
        pdus = reassemble_uds_pdus([
            _frame(0x7E8, "100A62F19056494E", 0.1),
        ])

        self.assertEqual(len(pdus), 1)
        self.assertFalse(pdus[0].complete)
        self.assertEqual(pdus[0].payload, bytes.fromhex("62F19056494E"))

    def test_reassemble_uds_pdus_marks_out_of_order_consecutive_frame_incomplete(self) -> None:
        pdus = reassemble_uds_pdus([
            _frame(0x7E8, "100A62F19056494E", 0.1),
            _frame(0x7E8, "229ABCDEF0000000", 0.12),
        ])

        self.assertEqual(len(pdus), 1)
        self.assertFalse(pdus[0].complete)
        self.assertEqual(pdus[0].payload, bytes.fromhex("62F19056494E"))

    def test_uds_trace_transactions_use_incomplete_reassembled_response(self) -> None:
        events = uds_trace_transactions(
            [
                _frame(0x7E0, "0227010000000000", 0.0),
                _frame(0x7E8, "100A670112345678", 0.1),
            ],
            source="transport.uds.trace",
        )

        self.assertEqual(len(events), 1)
        self.assertFalse(events[0].complete)
        self.assertEqual(events[0].service, 0x27)
        self.assertEqual(events[0].response_data, bytes.fromhex("670112345678"))

    def test_uds_scan_transactions_reassemble_multi_frame_response(self) -> None:
        events = uds_scan_transactions(
            [
                _frame(0x7E8, "100A5001003201F4", 0.1),
                _frame(0x7DF, "3000000000000000", 0.11),
                _frame(0x7E8, "2100000000000000", 0.12),
            ],
            source="transport.uds.scan",
        )

        self.assertEqual(len(events), 1)
        self.assertTrue(events[0].complete)
        self.assertEqual(events[0].service, 0x10)
        self.assertEqual(events[0].response_data, bytes.fromhex("5001003201F400000000"))

    @patch("canarchy.uds.uds_decoder_backend", return_value="scapy")
    @patch(
        "canarchy.uds.inspect_uds_payload",
        side_effect=[
            {"summary": "UDS / DiagnosticSessionControl"},
            {"summary": "UDS / PositiveResponse DiagnosticSessionControl"},
        ],
    )
    def test_uds_trace_transactions_include_optional_scapy_summaries(self, _inspect_mock, _decoder_mock) -> None:
        events = uds_trace_transactions(
            [
                _frame(0x7E0, "0210030000000000", 0.0),
                _frame(0x7E8, "0450030032000000", 0.1),
            ],
            source="transport.uds.trace",
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].decoder, "scapy")
        self.assertEqual(events[0].request_summary, "UDS / DiagnosticSessionControl")
        self.assertEqual(events[0].response_summary, "UDS / PositiveResponse DiagnosticSessionControl")

    def test_uds_trace_transactions_name_negative_response_codes(self) -> None:
        events = uds_trace_transactions(
            [
                _frame(0x7E0, "0227020000000000", 0.0),
                _frame(0x7E8, "037F273500000000", 0.1),
            ],
            source="transport.uds.trace",
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].service, 0x27)
        self.assertEqual(events[0].negative_response_code, 0x35)
        self.assertEqual(events[0].negative_response_name, "InvalidKey")
