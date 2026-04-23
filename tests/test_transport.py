from __future__ import annotations

import multiprocessing
import os
import queue
import threading
import time
import uuid
import unittest
from pathlib import Path
from unittest.mock import patch

from canarchy.models import CanFrame, UdsTransactionEvent
from canarchy.transport import (
    LocalTransport,
    PythonCanBackend,
    ScaffoldCanBackend,
    TransportBackendConfig,
    TransportError,
    build_live_backend,
    iter_candump_file,
    load_candump_file,
    parse_candump_line,
    python_can,
)


FIXTURES = Path(__file__).parent / "fixtures"


def _capture_one_frame_subprocess(channel: str, interface_type: str, out: multiprocessing.Queue) -> None:
    """Receive one frame in a subprocess and report whether it arrived."""
    import can  # type: ignore[import-untyped]
    bus = can.Bus(channel=channel, interface=interface_type, receive_own_messages=interface_type == "virtual")
    try:
        msg = bus.recv(timeout=1.0)
        out.put(msg is not None)
    finally:
        bus.shutdown()


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

    def test_load_candump_file_streams_without_read_text(self) -> None:
        with patch.object(Path, "read_text", side_effect=AssertionError("read_text should not be used")):
            frames = load_candump_file(FIXTURES / "sample.candump")

        self.assertEqual(len(frames), 3)

    def test_iter_candump_file_yields_real_frames(self) -> None:
        frames = list(iter_candump_file(FIXTURES / "sample.candump"))

        self.assertEqual(len(frames), 3)
        self.assertEqual(frames[0].interface, "can0")

    def test_iter_candump_file_respects_max_frames(self) -> None:
        frames = list(iter_candump_file(FIXTURES / "j1939_heavy_vehicle.candump", max_frames=3))

        self.assertEqual(len(frames), 3)
        self.assertEqual(frames[-1].timestamp, 0.2)

    def test_iter_candump_file_respects_offset(self) -> None:
        frames = list(iter_candump_file(FIXTURES / "j1939_heavy_vehicle.candump", offset=2))

        self.assertEqual(len(frames), 6)
        self.assertEqual(frames[0].timestamp, 0.2)

    def test_iter_candump_file_respects_offset_and_max_frames(self) -> None:
        frames = list(iter_candump_file(FIXTURES / "j1939_heavy_vehicle.candump", offset=2, max_frames=2))

        self.assertEqual(len(frames), 2)
        self.assertEqual(frames[0].timestamp, 0.2)

    def test_iter_candump_file_respects_seconds_window(self) -> None:
        frames = list(iter_candump_file(FIXTURES / "j1939_heavy_vehicle.candump", seconds=0.15))

        self.assertEqual(len(frames), 2)
        self.assertEqual([frame.timestamp for frame in frames], [0.0, 0.1])

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

    def test_user_config_file_sets_backend(self) -> None:
        import tempfile
        from canarchy.transport import _load_user_config

        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / ".canarchy"
            config_dir.mkdir()
            (config_dir / "config.toml").write_text(
                '[transport]\nbackend = "python-can"\ninterface = "udp_multicast"\n'
            )
            with patch("pathlib.Path.home", return_value=Path(tmp)):
                result = _load_user_config()

        self.assertEqual(result["CANARCHY_TRANSPORT_BACKEND"], "python-can")
        self.assertEqual(result["CANARCHY_PYTHON_CAN_INTERFACE"], "udp_multicast")

    def test_user_config_file_missing_returns_empty(self) -> None:
        import tempfile
        from canarchy.transport import _load_user_config

        with tempfile.TemporaryDirectory() as tmp:
            with patch("pathlib.Path.home", return_value=Path(tmp)):
                result = _load_user_config()

        self.assertEqual(result, {})

    def test_user_config_file_invalid_toml_returns_empty(self) -> None:
        import tempfile
        from canarchy.transport import _load_user_config

        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / ".canarchy"
            config_dir.mkdir()
            (config_dir / "config.toml").write_text("not valid toml ][[\n")
            with patch("pathlib.Path.home", return_value=Path(tmp)):
                result = _load_user_config()

        self.assertEqual(result, {})

    def test_env_var_overrides_config_file(self) -> None:
        import tempfile
        from canarchy.transport import transport_backend_config

        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / ".canarchy"
            config_dir.mkdir()
            (config_dir / "config.toml").write_text('[transport]\nbackend = "python-can"\n')
            with patch("pathlib.Path.home", return_value=Path(tmp)):
                with patch.dict(os.environ, {"CANARCHY_TRANSPORT_BACKEND": "scaffold"}, clear=False):
                    config = transport_backend_config()

        self.assertEqual(config.backend, "scaffold")

    def test_config_file_used_when_no_env_var(self) -> None:
        import tempfile
        from canarchy.transport import transport_backend_config

        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / ".canarchy"
            config_dir.mkdir()
            (config_dir / "config.toml").write_text(
                '[transport]\nbackend = "python-can"\ninterface = "udp_multicast"\n'
            )
            env = {k: v for k, v in os.environ.items()
                   if k not in {"CANARCHY_TRANSPORT_BACKEND", "CANARCHY_PYTHON_CAN_INTERFACE"}}
            with patch("pathlib.Path.home", return_value=Path(tmp)):
                with patch.dict(os.environ, env, clear=True):
                    config = transport_backend_config()

        self.assertEqual(config.backend, "python-can")
        self.assertEqual(config.python_can_interface, "udp_multicast")

    def test_build_live_backend_uses_explicit_scaffold_config(self) -> None:
        backend = build_live_backend(TransportBackendConfig(backend="scaffold"))
        self.assertIsInstance(backend, ScaffoldCanBackend)

    def test_scaffold_capture_stream_yields_fixture_frames(self) -> None:
        backend = ScaffoldCanBackend()

        frames = list(backend.capture_stream("can0"))

        self.assertEqual(len(frames), 2)
        self.assertEqual(frames[0].interface, "can0")
        self.assertEqual(frames[1].interface, "can0")

    def test_j1939_monitor_events_use_explicit_sample_provider(self) -> None:
        transport = LocalTransport(live_backend=ScaffoldCanBackend())

        with patch("canarchy.transport.sample_j1939_monitor_frames") as sample_provider:
            sample_provider.return_value = [
                CanFrame(
                    arbitration_id=0x18FEEE31,
                    data=bytes.fromhex("11223344"),
                    is_extended_id=True,
                    interface="can0",
                    timestamp=0.0,
                )
            ]

            events = transport.j1939_monitor_events()

        sample_provider.assert_called_once_with()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_type"], "j1939_pgn")

    def test_j1939_monitor_events_with_interface_use_transport_capture(self) -> None:
        transport = LocalTransport(live_backend=ScaffoldCanBackend())

        with patch.object(
            transport,
            "capture",
            return_value=[
                CanFrame(
                    arbitration_id=0x18FEEE31,
                    data=bytes.fromhex("11223344"),
                    is_extended_id=True,
                    interface="can0",
                    timestamp=0.0,
                ),
                CanFrame(
                    arbitration_id=0x123,
                    data=bytes.fromhex("AA"),
                    is_extended_id=False,
                    interface="can0",
                    timestamp=0.1,
                ),
            ],
        ) as capture_mock:
            events = transport.j1939_monitor_events(interface="can0")

        capture_mock.assert_called_once_with("can0")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_type"], "j1939_pgn")

    def test_uds_scan_events_use_explicit_sample_provider(self) -> None:
        transport = LocalTransport(live_backend=ScaffoldCanBackend())

        with patch("canarchy.transport.sample_uds_scan_transactions") as sample_provider:
            sample_provider.return_value = [
                UdsTransactionEvent(
                    request_id=0x7DF,
                    response_id=0x7E8,
                    service=0x10,
                    service_name="DiagnosticSessionControl",
                    request_data=bytes.fromhex("1001"),
                    response_data=bytes.fromhex("5001"),
                    ecu_address=0x7E8,
                    source="transport.uds.scan",
                    timestamp=0.0,
                )
            ]

            events = transport.uds_scan_events("can0")

        sample_provider.assert_called_once_with()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_type"], "uds_transaction")

    def test_uds_trace_events_with_python_can_backend_use_transport_capture(self) -> None:
        transport = LocalTransport(live_backend=PythonCanBackend(bus_interface="virtual"))

        with patch.object(
            transport,
            "capture",
            return_value=[
                CanFrame(
                    arbitration_id=0x7E0,
                    data=bytes.fromhex("0210030000000000"),
                    interface="can0",
                    timestamp=0.0,
                ),
                CanFrame(
                    arbitration_id=0x7E8,
                    data=bytes.fromhex("0450030032000000"),
                    interface="can0",
                    timestamp=0.1,
                ),
            ],
        ) as capture_mock:
            events = transport.uds_trace_events("can0")

        capture_mock.assert_called_once_with("can0")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_type"], "uds_transaction")
        self.assertEqual(events[0]["payload"]["service"], 0x10)

    def test_uds_scan_events_with_python_can_backend_send_request_and_capture_responses(self) -> None:
        transport = LocalTransport(live_backend=PythonCanBackend(bus_interface="virtual"))

        with patch.object(transport, "send") as send_mock, patch.object(
            transport,
            "capture",
            return_value=[
                CanFrame(
                    arbitration_id=0x7E8,
                    data=bytes.fromhex("0450010032000000"),
                    interface="can0",
                    timestamp=0.1,
                )
            ],
        ) as capture_mock:
            events = transport.uds_scan_events("can0")

        send_mock.assert_called_once()
        capture_mock.assert_called_once_with("can0")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["payload"]["request_id"], 0x7DF)
        self.assertEqual(events[0]["payload"]["service"], 0x10)

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
    def test_generate_frames_round_trip_in_same_process(self) -> None:
        """generate_events delivers all frames to a concurrent capture in the same process."""
        interface = f"canarchy-test-{uuid.uuid4().hex}"
        backend = PythonCanBackend(bus_interface="virtual", capture_limit=3, capture_timeout=1.0)
        frames = [
            CanFrame(arbitration_id=0x100, data=bytes.fromhex("AABBCCDD"), interface=interface),
            CanFrame(arbitration_id=0x200, data=bytes.fromhex("11223344"), interface=interface),
            CanFrame(arbitration_id=0x300, data=bytes.fromhex("DEADBEEF"), interface=interface),
        ]
        captured: queue.Queue[list[CanFrame]] = queue.Queue()

        def do_capture() -> None:
            captured.put(backend.capture(interface))

        t = threading.Thread(target=do_capture)
        t.start()
        time.sleep(0.05)
        for frame in frames:
            backend.send(interface, frame)
        t.join(timeout=3.0)

        self.assertFalse(t.is_alive(), "capture thread should have received all frames and exited")
        received = captured.get_nowait()
        self.assertEqual(len(received), 3)
        arb_ids = [f.arbitration_id for f in received]
        self.assertIn(0x100, arb_ids)
        self.assertIn(0x200, arb_ids)
        self.assertIn(0x300, arb_ids)

    @unittest.skipIf(python_can is None, "python-can is not installed")
    def test_virtual_bus_is_process_local(self) -> None:
        """Demonstrates that the python-can virtual bus does not bridge process boundaries.

        This is the root cause of frames generated by `canarchy generate` not appearing
        in `canarchy capture --candump` when the two commands run in separate terminals.
        Each process gets its own in-memory virtual bus state; messages sent in one
        process are invisible to buses opened in another process on the same channel.
        """
        channel = f"canarchy-test-{uuid.uuid4().hex}"
        result: multiprocessing.Queue = multiprocessing.Queue()

        p = multiprocessing.Process(target=_capture_one_frame_subprocess, args=(channel, "virtual", result))
        p.start()
        time.sleep(0.1)

        import can  # type: ignore[import-untyped]
        send_bus = can.Bus(channel=channel, interface="virtual", receive_own_messages=True)
        send_bus.send(can.Message(arbitration_id=0x123, data=b"\x11\x22", is_extended_id=False))
        send_bus.shutdown()

        p.join(timeout=2.0)

        received_anything = result.get_nowait() if not result.empty() else False
        self.assertFalse(
            received_anything,
            "Virtual bus delivered a message across process boundaries — "
            "this would mean the cross-process demo works, which contradicts the known limitation.",
        )

    @unittest.skipIf(python_can is None, "python-can is not installed")
    def test_udp_multicast_backend_round_trips_frame_across_processes(self) -> None:
        """udp_multicast delivers frames across process boundaries, fixing the cross-process demo.

        Use CANARCHY_PYTHON_CAN_INTERFACE=udp_multicast with a multicast address as the
        interface argument (e.g. 239.0.0.1) instead of virtual to enable cross-process
        send/capture workflows on macOS and Linux without hardware.

        Skipped automatically when multicast routing is unavailable (e.g. no network interface
        with a multicast route — common on macOS without `sudo route add -net 239.0.0.0/8 lo0`).
        """
        import socket
        channel = "239.0.0.1"

        # Probe multicast round-trip capability before spawning processes.
        # Simply opening a socket succeeds even without a multicast route, so we do
        # an actual send+recv loop-back probe with a short timeout instead.
        import can as _can
        _multicast_ok = False
        try:
            _probe_rx = _can.Bus(channel=channel, interface="udp_multicast", receive_own_messages=True)
            _probe_tx = _can.Bus(channel=channel, interface="udp_multicast", receive_own_messages=True)
            import can as _can2
            _probe_tx.send(_can2.Message(arbitration_id=0x7FF, data=b"\x00", is_extended_id=False))
            _got = _probe_rx.recv(timeout=0.25)
            _probe_rx.shutdown()
            _probe_tx.shutdown()
            _multicast_ok = _got is not None
        except Exception:
            pass
        if not _multicast_ok:
            self.skipTest("multicast round-trip unavailable on this host — add a route to 239.0.0.0/8 lo0 to enable")

        result: multiprocessing.Queue = multiprocessing.Queue()
        p = multiprocessing.Process(target=_capture_one_frame_subprocess, args=(channel, "udp_multicast", result))
        p.start()
        time.sleep(0.15)

        backend = PythonCanBackend(bus_interface="udp_multicast")
        backend.send(channel, CanFrame(arbitration_id=0x7DF, data=bytes.fromhex("1001")))

        p.join(timeout=3.0)

        received = result.get_nowait() if not result.empty() else False
        self.assertTrue(received, "udp_multicast should deliver frames across process boundaries")

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
