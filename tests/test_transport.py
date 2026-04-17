from __future__ import annotations

import os
import queue
import threading
import time
import uuid
import unittest
from pathlib import Path
from unittest.mock import patch

from canarchy.models import CanFrame
from canarchy.transport import (
    PythonCanBackend,
    ScaffoldCanBackend,
    TransportError,
    build_live_backend,
    load_candump_file,
    parse_candump_line,
    python_can,
)


FIXTURES = Path(__file__).parent / "fixtures"


class FakeMessage:
    def __init__(
        self,
        arbitration_id: int,
        data: bytes,
        *,
        is_extended_id: bool = False,
        is_remote_frame: bool = False,
        is_error_frame: bool = False,
        is_fd: bool = False,
        bitrate_switch: bool = False,
        error_state_indicator: bool = False,
    ) -> None:
        self.arbitration_id = arbitration_id
        self.data = data
        self.is_extended_id = is_extended_id
        self.is_remote_frame = is_remote_frame
        self.is_error_frame = is_error_frame
        self.is_fd = is_fd
        self.bitrate_switch = bitrate_switch
        self.error_state_indicator = error_state_indicator
        self.timestamp = 0.0


class FakeBus:
    def __init__(self, messages: list[object] | None = None) -> None:
        self.messages = list(messages or [])
        self.sent_messages: list[object] = []
        self.shutdown_called = False

    def recv(self, timeout: float | None = None):
        del timeout
        if self.messages:
            return self.messages.pop(0)
        return None

    def send(self, message: object) -> None:
        self.sent_messages.append(message)

    def shutdown(self) -> None:
        self.shutdown_called = True


class TransportBackendTests(unittest.TestCase):
    def test_load_candump_file_returns_real_frames(self) -> None:
        frames = load_candump_file(FIXTURES / "sample.candump")

        self.assertEqual(len(frames), 3)
        self.assertEqual(frames[0].timestamp, 0.0)
        self.assertEqual(frames[1].arbitration_id, 0x18F00431)
        self.assertTrue(frames[1].is_extended_id)
        self.assertEqual(frames[2].interface, "can1")

    def test_parse_candump_line_rejects_malformed_lines(self) -> None:
        with self.assertRaises(TransportError) as ctx:
            parse_candump_line(
                "not a candump line", path=FIXTURES / "invalid.candump", line_number=1
            )

        self.assertEqual(ctx.exception.code, "CAPTURE_SOURCE_INVALID")
        self.assertIn("line 1", ctx.exception.message)

    def test_parse_candump_line_rejects_invalid_hex_payload(self) -> None:
        with self.assertRaises(TransportError) as ctx:
            parse_candump_line(
                "(0.000000) can0 123#123",
                path=FIXTURES / "invalid_hex.candump",
                line_number=1,
            )

        self.assertEqual(ctx.exception.code, "CAPTURE_SOURCE_INVALID")
        self.assertIn("invalid hex payload", ctx.exception.message)

    def test_parse_candump_line_supports_can_fd_flags(self) -> None:
        frame = parse_candump_line(
            "(0.000000) can0 123##31122334455667788",
            path=FIXTURES / "sample.candump",
            line_number=1,
        )

        self.assertEqual(frame.frame_format, "can_fd")
        self.assertTrue(frame.bitrate_switch)
        self.assertTrue(frame.error_state_indicator)
        self.assertEqual(frame.data, bytes.fromhex("1122334455667788"))

    def test_parse_candump_line_supports_remote_frames(self) -> None:
        frame = parse_candump_line(
            "(0.000000) can0 123#R",
            path=FIXTURES / "sample.candump",
            line_number=1,
        )

        self.assertTrue(frame.is_remote_frame)
        self.assertEqual(frame.data, b"")

    def test_parse_candump_line_supports_error_frames(self) -> None:
        frame = parse_candump_line(
            "(0.000000) can0 20000080#0000000000000000",
            path=FIXTURES / "sample.candump",
            line_number=1,
        )

        self.assertTrue(frame.is_error_frame)
        self.assertEqual(frame.arbitration_id, 0x80)
        self.assertEqual(frame.data, bytes.fromhex("0000000000000000"))

    def test_parse_candump_line_rejects_unsupported_can_fd_flags(self) -> None:
        with self.assertRaises(TransportError) as ctx:
            parse_candump_line(
                "(0.000000) can0 123##411223344",
                path=FIXTURES / "sample.candump",
                line_number=1,
            )

        self.assertEqual(ctx.exception.code, "CAPTURE_SOURCE_INVALID")
        self.assertIn("unsupported CAN FD flags", ctx.exception.message)

    def test_build_live_backend_defaults_to_scaffold(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            backend = build_live_backend()
        self.assertIsInstance(backend, ScaffoldCanBackend)

    def test_build_live_backend_rejects_unknown_backend(self) -> None:
        with patch.dict(os.environ, {"CANARCHY_TRANSPORT_BACKEND": "unknown"}, clear=False):
            with self.assertRaises(TransportError) as ctx:
                build_live_backend()
        self.assertEqual(ctx.exception.code, "TRANSPORT_BACKEND_INVALID")

    def test_build_live_backend_uses_python_can_when_requested(self) -> None:
        with patch.dict(
            os.environ,
            {
                "CANARCHY_TRANSPORT_BACKEND": "python-can",
                "CANARCHY_PYTHON_CAN_INTERFACE": "virtual",
            },
            clear=False,
        ):
            backend = build_live_backend()
        self.assertIsInstance(backend, PythonCanBackend)
        self.assertEqual(backend.bus_interface, "virtual")

    def test_python_can_capture_decodes_live_frames(self) -> None:
        fake_bus = FakeBus(
            [FakeMessage(0x18FEEE31, bytes.fromhex("11223344"), is_extended_id=True)]
        )
        backend = PythonCanBackend(bus_interface="virtual")
        with patch.object(backend, "_open_bus", return_value=fake_bus):
            frames = backend.capture("can0")

        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].arbitration_id, 0x18FEEE31)
        self.assertTrue(frames[0].is_extended_id)
        self.assertEqual(frames[0].data, bytes.fromhex("11223344"))
        self.assertEqual(frames[0].interface, "can0")
        self.assertTrue(fake_bus.shutdown_called)

    def test_python_can_send_encodes_live_frames(self) -> None:
        fake_bus = FakeBus()
        backend = PythonCanBackend(bus_interface="virtual")
        frame = CanFrame(arbitration_id=0x123, data=bytes.fromhex("11223344"), interface=None)
        with patch.object(backend, "_open_bus", return_value=fake_bus):
            with patch("canarchy.transport.python_can.Message") as message_cls:
                message_cls.return_value = object()
                sent_frame = backend.send("can0", frame)

        self.assertEqual(sent_frame.interface, "can0")
        self.assertEqual(len(fake_bus.sent_messages), 1)
        message_cls.assert_called_once_with(
            arbitration_id=0x123,
            data=bytes.fromhex("11223344"),
            is_extended_id=False,
            is_remote_frame=False,
            is_error_frame=False,
            is_fd=False,
            bitrate_switch=False,
            error_state_indicator=False,
        )
        self.assertTrue(fake_bus.shutdown_called)

    @unittest.skipIf(python_can is None, "python-can is not installed")
    def test_python_can_virtual_backend_round_trips_frame(self) -> None:
        interface = f"canarchy-test-{uuid.uuid4().hex}"
        backend = PythonCanBackend(bus_interface="virtual", capture_limit=1, capture_timeout=0.5)
        frame = CanFrame(arbitration_id=0x123, data=bytes.fromhex("11223344"), interface=interface)
        captured_frames: queue.Queue[list[CanFrame]] = queue.Queue()

        def capture_frames() -> None:
            captured_frames.put(backend.capture(interface))

        capture_thread = threading.Thread(target=capture_frames)
        capture_thread.start()
        try:
            time.sleep(0.05)
            sent_frame = backend.send(interface, frame)
            capture_thread.join(timeout=2.0)
        finally:
            capture_thread.join(timeout=2.0)

        self.assertFalse(capture_thread.is_alive())
        self.assertEqual(sent_frame.interface, interface)
        self.assertIsNotNone(sent_frame.timestamp)
        frames = captured_frames.get_nowait()
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].arbitration_id, 0x123)
        self.assertEqual(frames[0].data, bytes.fromhex("11223344"))
        self.assertEqual(frames[0].interface, interface)


if __name__ == "__main__":
    unittest.main()
