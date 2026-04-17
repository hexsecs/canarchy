from __future__ import annotations

import os
import queue
import threading
import time
import uuid
import unittest
from unittest.mock import patch

from canarchy.models import CanFrame
from canarchy.transport import (
    PythonCanBackend,
    ScaffoldCanBackend,
    TransportError,
    build_live_backend,
    python_can,
)


class FakeMessage:
    def __init__(self, arbitration_id: int, data: bytes, *, is_extended_id: bool = False) -> None:
        self.arbitration_id = arbitration_id
        self.data = data
        self.is_extended_id = is_extended_id
        self.is_remote_frame = False
        self.is_error_frame = False
        self.is_fd = False
        self.bitrate_switch = False
        self.error_state_indicator = False
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
