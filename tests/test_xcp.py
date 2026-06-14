"""Tests for the XCP (measurement/calibration) workflows (#327)."""

from __future__ import annotations

import contextlib
import io
import json
import os
import unittest
from unittest.mock import patch

from canarchy.models import CanFrame
from canarchy.transport import LocalTransport, PythonCanBackend
from canarchy.xcp import (
    XCP_DEFAULT_REQUEST_ID,
    XCP_DEFAULT_RESPONSE_ID,
    connect_request_frame,
    parse_connect_response,
    xcp_command_name,
    xcp_read_measurements,
    xcp_scan_transactions,
    xcp_trace_transactions,
)


def run_cli(*argv: str) -> tuple[int, str, str]:
    from canarchy.cli import main

    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = main(argv)
    return exit_code, stdout.getvalue(), stderr.getvalue()


def _frame(arbitration_id: int, data_hex: str, timestamp: float) -> CanFrame:
    return CanFrame(
        arbitration_id=arbitration_id,
        data=bytes.fromhex(data_hex),
        interface="can0",
        timestamp=timestamp,
    )


class XcpCodecTests(unittest.TestCase):
    def test_command_name_lookup(self) -> None:
        self.assertEqual(xcp_command_name(0xFF), "CONNECT")
        self.assertEqual(xcp_command_name(0xDA), "GET_DAQ_PROCESSOR_INFO")
        self.assertEqual(xcp_command_name(0x42), "CMD0x42")

    def test_parse_connect_response_fields(self) -> None:
        info = parse_connect_response(bytes.fromhex("FF14C00800080101"))
        self.assertEqual(info["resource"], 0x14)
        self.assertEqual(info["resources"], ["daq", "pgm"])
        self.assertEqual(info["byte_order"], "little")
        self.assertEqual(info["max_cto"], 8)
        self.assertEqual(info["max_dto"], 2048)
        self.assertEqual(info["protocol_layer_version"], 1)
        self.assertEqual(info["transport_layer_version"], 1)

    def test_connect_request_frame_is_connect(self) -> None:
        frame = connect_request_frame(request_id=0x3E0)
        self.assertEqual(frame.arbitration_id, 0x3E0)
        self.assertEqual(frame.data, bytes([0xFF, 0x00]))


class XcpScanTests(unittest.TestCase):
    def test_scan_pairs_connect_with_positive_response(self) -> None:
        frames = [
            _frame(XCP_DEFAULT_REQUEST_ID, "FF00", 0.0),
            _frame(XCP_DEFAULT_RESPONSE_ID, "FF14C00800080101", 0.1),
        ]
        events = xcp_scan_transactions(frames, source="t")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].command_name, "CONNECT")
        self.assertTrue(events[0].positive)
        self.assertEqual(events[0].connect_info["resources"], ["daq", "pgm"])

    def test_scan_reports_error_response(self) -> None:
        frames = [
            _frame(XCP_DEFAULT_REQUEST_ID, "FF00", 0.0),
            _frame(XCP_DEFAULT_RESPONSE_ID, "FE24", 0.1),  # ERR_ACCESS_DENIED
        ]
        events = xcp_scan_transactions(frames, source="t")
        self.assertEqual(len(events), 1)
        self.assertFalse(events[0].positive)
        self.assertEqual(events[0].error_name, "ERR_ACCESS_DENIED")

    def test_scan_ignores_unrelated_ids(self) -> None:
        frames = [
            _frame(XCP_DEFAULT_REQUEST_ID, "FF00", 0.0),
            _frame(0x123, "DEADBEEF", 0.05),
            _frame(XCP_DEFAULT_RESPONSE_ID, "FF14C00800080101", 0.1),
        ]
        events = xcp_scan_transactions(frames, source="t")
        self.assertEqual(len(events), 1)


class XcpTraceTests(unittest.TestCase):
    def test_trace_pairs_commands_with_responses(self) -> None:
        frames = [
            _frame(XCP_DEFAULT_REQUEST_ID, "FD", 0.0),  # GET_STATUS
            _frame(XCP_DEFAULT_RESPONSE_ID, "FF091D0000", 0.1),
            _frame(XCP_DEFAULT_REQUEST_ID, "F80000", 0.2),  # GET_SEED
            _frame(XCP_DEFAULT_RESPONSE_ID, "FE25", 0.3),  # ERR_ACCESS_LOCKED
        ]
        events = xcp_trace_transactions(frames, source="t")
        self.assertEqual([e.command_name for e in events], ["GET_STATUS", "GET_SEED"])
        self.assertTrue(events[0].positive)
        self.assertFalse(events[1].positive)
        self.assertEqual(events[1].error_name, "ERR_ACCESS_LOCKED")

    def test_trace_skips_orphan_response(self) -> None:
        frames = [_frame(XCP_DEFAULT_RESPONSE_ID, "FF00", 0.0)]
        self.assertEqual(xcp_trace_transactions(frames, source="t"), [])


class XcpReadTests(unittest.TestCase):
    def test_read_extracts_dto_payloads_and_skips_cto(self) -> None:
        frames = [
            _frame(XCP_DEFAULT_RESPONSE_ID, "0011223344", 0.0),  # DTO pid 0x00
            _frame(XCP_DEFAULT_RESPONSE_ID, "01AABBCCDD", 0.1),  # DTO pid 0x01
            _frame(XCP_DEFAULT_RESPONSE_ID, "FF00", 0.2),  # CTO response, skipped
        ]
        events = xcp_read_measurements(frames, source="t")
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].pid, 0x00)
        self.assertEqual(events[0].data, bytes.fromhex("11223344"))
        self.assertEqual(events[1].pid, 0x01)


class XcpCliScaffoldTests(unittest.TestCase):
    def _run(self, *argv: str) -> dict:
        with patch.dict(os.environ, {"CANARCHY_TRANSPORT_BACKEND": "scaffold"}):
            exit_code, stdout, _ = run_cli(*argv)
        self.assertEqual(exit_code, 0, stdout)
        return json.loads(stdout)["data"]

    def test_scan_active_envelope(self) -> None:
        data = self._run("xcp", "scan", "vcan0", "--json")
        self.assertEqual(data["mode"], "active")
        self.assertEqual(data["responder_count"], 1)
        self.assertEqual(data["request_id"], XCP_DEFAULT_REQUEST_ID)
        self.assertEqual(data["events"][0]["payload"]["command_name"], "CONNECT")

    def test_trace_passive_envelope(self) -> None:
        data = self._run("xcp", "trace", "vcan0", "--json")
        self.assertEqual(data["mode"], "passive")
        self.assertEqual(data["transaction_count"], 3)

    def test_read_measurements(self) -> None:
        data = self._run("xcp", "read", "vcan0", "--json")
        self.assertEqual(data["mode"], "passive")
        self.assertEqual(data["measurement_count"], 2)
        self.assertEqual(data["events"][0]["event_type"], "xcp_measurement")

    def test_commands_reference(self) -> None:
        data = self._run("xcp", "commands", "--json")
        self.assertEqual(data["mode"], "reference")
        self.assertGreater(data["command_count"], 40)

    def test_invalid_id_returns_structured_error(self) -> None:
        with patch.dict(os.environ, {"CANARCHY_TRANSPORT_BACKEND": "scaffold"}):
            exit_code, stdout, _ = run_cli(
                "xcp", "scan", "vcan0", "--request-id", "not-an-id", "--json"
            )
        self.assertEqual(exit_code, 1)
        payload = json.loads(stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["errors"][0]["code"], "XCP_INVALID_ID")

    def test_scan_requires_ack_when_configured(self) -> None:
        with patch.dict(
            os.environ,
            {"CANARCHY_TRANSPORT_BACKEND": "scaffold", "CANARCHY_REQUIRE_ACTIVE_ACK": "1"},
        ):
            exit_code, stdout, _ = run_cli("xcp", "scan", "vcan0", "--json")
        self.assertEqual(exit_code, 1)
        payload = json.loads(stdout)
        self.assertEqual(payload["errors"][0]["code"], "ACTIVE_ACK_REQUIRED")


class XcpTransportTests(unittest.TestCase):
    def test_scan_events_send_connect_and_parse_responses(self) -> None:
        transport = LocalTransport(live_backend=PythonCanBackend(bus_interface="virtual"))
        with (
            patch.object(transport, "send") as send_mock,
            patch.object(
                transport,
                "capture",
                return_value=[
                    _frame(XCP_DEFAULT_RESPONSE_ID, "FF14C00800080101", 0.1),
                ],
            ) as capture_mock,
        ):
            events = transport.xcp_scan_events("can0")
        send_mock.assert_called_once()
        capture_mock.assert_called_once_with("can0")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["payload"]["command_name"], "CONNECT")


class XcpMcpTests(unittest.TestCase):
    def test_tools_exposed_and_argv(self) -> None:
        from canarchy.mcp_server import _TOOL_NAMES, _build_argv

        for tool in ("xcp_scan", "xcp_trace", "xcp_read", "xcp_commands"):
            self.assertIn(tool, _TOOL_NAMES)
        self.assertEqual(
            _build_argv("xcp_scan", {"interface": "can0", "request_id": "0x3E0"}),
            ["xcp", "scan", "can0", "--request-id", "0x3E0", "--json"],
        )
        self.assertEqual(_build_argv("xcp_commands", {}), ["xcp", "commands", "--json"])
