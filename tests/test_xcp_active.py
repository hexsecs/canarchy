"""Tests for active XCP workflows (canarchy.xcp_active)."""

from __future__ import annotations

import unittest
from collections.abc import Callable

from canarchy.models import CanFrame
from canarchy.xcp_active import (
    CMD_GET_ID,
    CMD_GET_STATUS,
    MAX_DUMP_BYTES,
    TransportXcpClient,
    XcpActiveError,
    XcpClient,
    XcpResponse,
    command_frame,
    dump,
    info,
    plan_dump_chunks,
    set_mta_request,
    short_upload_request,
)


class FakeXcpClient(XcpClient):
    """Programmable client: a rule maps a command payload to a response (or None)."""

    def __init__(
        self, rule: Callable[[bytes], bytes | None], *, request_id=0x3E0, response_id=0x3E1
    ) -> None:
        self.rule = rule
        self.request_id = request_id
        self.response_id = response_id
        self.calls: list[bytes] = []

    def command(self, payload: bytes, *, timeout=None) -> XcpResponse:
        self.calls.append(bytes(payload))
        response = self.rule(bytes(payload))
        return XcpResponse(
            request_id=self.request_id,
            response_id=self.response_id,
            command=payload[0] if payload else 0,
            request=bytes(payload),
            response=response,
        )


def _connect_response() -> bytes:
    # PID_RES, resource, comm_mode_basic(little), max_cto=8, max_dto(2)=64, versions
    return bytes([0xFF, 0x14, 0x00, 0x08, 0x40, 0x00, 0x01, 0x01])


def _err(code: int) -> bytes:
    return bytes([0xFE, code])


class CommandFrameTest(unittest.TestCase):
    def test_builds_raw_cto(self) -> None:
        frame = command_frame(0x3E0, bytes([0xFF, 0x00]))
        self.assertEqual(frame.data, bytes([0xFF, 0x00]))
        self.assertFalse(frame.is_extended_id)

    def test_rejects_empty(self) -> None:
        with self.assertRaises(XcpActiveError) as ctx:
            command_frame(0x3E0, b"")
        self.assertEqual(ctx.exception.code, "XCP_EMPTY_COMMAND")

    def test_rejects_oversize(self) -> None:
        with self.assertRaises(XcpActiveError) as ctx:
            command_frame(0x3E0, b"\x00" * 9)
        self.assertEqual(ctx.exception.code, "XCP_COMMAND_TOO_LONG")


class TransportClientTest(unittest.TestCase):
    def test_selects_response_on_response_id(self) -> None:
        class T:
            def transaction(self, _interface, _frame):
                return [
                    CanFrame(arbitration_id=0x111, data=b"\x01\x02"),
                    CanFrame(arbitration_id=0x3E1, data=_connect_response()),
                ]

        client = TransportXcpClient(
            transport=T(), interface="can0", request_id=0x3E0, response_id=0x3E1
        )
        response = client.command(bytes([0xFF, 0x00]))
        self.assertTrue(response.positive)
        self.assertEqual(response.response, _connect_response())

    def test_no_response(self) -> None:
        class T:
            def transaction(self, _interface, _frame):
                return []

        client = TransportXcpClient(
            transport=T(), interface="can0", request_id=0x3E0, response_id=0x3E1
        )
        response = client.command(bytes([0xFF, 0x00]))
        self.assertFalse(response.responded)
        self.assertEqual(response.status, "no_response")


class ResponseStatusTest(unittest.TestCase):
    def test_status_variants(self) -> None:
        positive = XcpResponse(0x3E0, 0x3E1, 0xFD, b"\xfd", b"\xff\x00")
        unsupported = XcpResponse(0x3E0, 0x3E1, 0xFB, b"\xfb", _err(0x20))
        other_err = XcpResponse(0x3E0, 0x3E1, 0xF5, b"\xf5", _err(0x22))
        silent = XcpResponse(0x3E0, 0x3E1, 0xFD, b"\xfd", None)
        self.assertEqual(positive.status, "positive")
        self.assertEqual(unsupported.status, "unsupported")
        self.assertTrue(unsupported.unsupported)
        self.assertEqual(other_err.status, "error")
        self.assertEqual(other_err.error_name, "ERR_OUT_OF_RANGE")
        self.assertEqual(silent.status, "no_response")


class InfoTest(unittest.TestCase):
    def test_info_collects_capabilities(self) -> None:
        def rule(payload: bytes) -> bytes | None:
            cmd = payload[0]
            if cmd == 0xFF:
                return _connect_response()
            if cmd == CMD_GET_STATUS:
                return bytes([0xFF, 0x00, 0x00, 0x00, 0x00, 0x00])
            if cmd == 0xFB:  # GET_COMM_MODE_INFO
                return bytes([0xFF, 0x00, 0x01, 0x00, 0x02, 0x05, 0x00, 0x11])
            if cmd == CMD_GET_ID:
                return bytes([0xFF, 0x00, 0x00, 0x00, 0x10, 0x00, 0x00, 0x00])
            return _err(0x20)

        result = info(FakeXcpClient(rule))
        self.assertEqual(result.connect_info["max_cto"], 8)
        self.assertEqual(result.connect_info["resources"], ["daq", "pgm"])
        self.assertTrue(result.status.positive)
        self.assertTrue(result.comm_mode.positive)
        self.assertTrue(result.identification.positive)

    def test_info_marks_unsupported_optional(self) -> None:
        def rule(payload: bytes) -> bytes | None:
            if payload[0] == 0xFF:
                return _connect_response()
            return _err(0x20)  # everything else: command unknown

        result = info(FakeXcpClient(rule))
        self.assertEqual(result.status.status, "unsupported")
        self.assertEqual(result.comm_mode.status, "unsupported")

    def test_info_raises_on_no_connect(self) -> None:
        with self.assertRaises(XcpActiveError) as ctx:
            info(FakeXcpClient(lambda _p: None))
        self.assertEqual(ctx.exception.code, "XCP_NO_RESPONSE")

    def test_info_raises_on_connect_error(self) -> None:
        with self.assertRaises(XcpActiveError) as ctx:
            info(FakeXcpClient(lambda _p: _err(0x24)))
        self.assertEqual(ctx.exception.code, "XCP_ERROR_RESPONSE")


class DumpPlanTest(unittest.TestCase):
    def test_plan_chunks(self) -> None:
        self.assertEqual(plan_dump_chunks(0x100, 10, 4), [(0x100, 4), (0x104, 4), (0x108, 2)])

    def test_rejects_oversize(self) -> None:
        with self.assertRaises(XcpActiveError) as ctx:
            plan_dump_chunks(0, MAX_DUMP_BYTES + 1, 4)
        self.assertEqual(ctx.exception.code, "XCP_DUMP_TOO_LARGE")

    def test_rejects_chunk_too_big(self) -> None:
        with self.assertRaises(XcpActiveError) as ctx:
            plan_dump_chunks(0, 10, 8)
        self.assertEqual(ctx.exception.code, "XCP_INVALID_CHUNK_SIZE")

    def test_set_mta_encoding(self) -> None:
        self.assertEqual(
            set_mta_request(0x12345678, byte_order="big"),
            bytes([0xF6, 0x00, 0x00, 0x00, 0x12, 0x34, 0x56, 0x78]),
        )

    def test_short_upload_encoding(self) -> None:
        self.assertEqual(
            short_upload_request(0x1000, 4, byte_order="big"),
            bytes([0xF4, 0x04, 0x00, 0x00, 0x00, 0x00, 0x10, 0x00]),
        )


class DumpTest(unittest.TestCase):
    def test_dump_set_mta_upload(self) -> None:
        def rule(payload: bytes) -> bytes | None:
            cmd = payload[0]
            if cmd == 0xFF:
                return _connect_response()
            if cmd == 0xF6:  # SET_MTA
                return bytes([0xFF])
            if cmd == 0xF5:  # UPLOAD n
                n = payload[1]
                return bytes([0xFF]) + bytes(range(n))
            return _err(0x20)

        _connect, chunks = dump(FakeXcpClient(rule), address=0x2000, size=6, chunk_size=4)
        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0].data, bytes(range(4)))
        self.assertEqual(chunks[1].data, bytes(range(2)))

    def test_dump_short_upload(self) -> None:
        def rule(payload: bytes) -> bytes | None:
            if payload[0] == 0xFF:
                return _connect_response()
            if payload[0] == 0xF4:  # SHORT_UPLOAD
                n = payload[1]
                return bytes([0xFF]) + bytes([0xAB] * n)
            return _err(0x20)

        client = FakeXcpClient(rule)
        _connect, chunks = dump(client, address=0x10, size=4, chunk_size=4, short_upload=True)
        self.assertEqual(chunks[0].data, bytes([0xAB] * 4))
        # SHORT_UPLOAD does not issue SET_MTA.
        self.assertFalse(any(call[0] == 0xF6 for call in client.calls))

    def test_dump_stops_on_error(self) -> None:
        def rule(payload: bytes) -> bytes | None:
            if payload[0] == 0xFF:
                return _connect_response()
            if payload[0] == 0xF6:
                return bytes([0xFF])
            if payload[0] == 0xF5:
                return _err(0x22)  # ERR_OUT_OF_RANGE on upload
            return _err(0x20)

        _connect, chunks = dump(FakeXcpClient(rule), address=0x2000, size=8, chunk_size=4)
        self.assertEqual(len(chunks), 1)
        self.assertIsNone(chunks[0].data)

    def test_dump_raises_on_no_connect(self) -> None:
        with self.assertRaises(XcpActiveError) as ctx:
            dump(FakeXcpClient(lambda _p: None), address=0, size=4, chunk_size=4)
        self.assertEqual(ctx.exception.code, "XCP_NO_RESPONSE")


if __name__ == "__main__":
    unittest.main()
