"""Tests for the cannelloni CAN-over-UDP codec and CLI (#418)."""

from __future__ import annotations

import contextlib
import io
import json
import socket
import struct
import unittest
from pathlib import Path

from canarchy.cannelloni import (
    CannelloniError,
    decode_packet,
    encode_packet,
    encode_packets,
    frames_from_bytes,
)
from canarchy.models import CanFrame
from canarchy.transport import LocalTransport

FIXTURES = Path(__file__).parent / "fixtures"


def run_cli(*argv: str) -> tuple[int, str, str]:
    from canarchy.cli import main

    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = main(argv)
    return exit_code, stdout.getvalue(), stderr.getvalue()


class CodecReferenceTests(unittest.TestCase):
    """The encoder matches a hand-computed cannelloni wire reference (#418)."""

    def test_classic_standard_frame_matches_reference_bytes(self) -> None:
        frame = CanFrame(arbitration_id=0x123, data=bytes.fromhex("11223344"))
        packet = encode_packet([frame], seq_no=7)

        # header: version=2 op=0 seq=7 count=1 ; frame: can_id=0x00000123 len=4 data
        expected = (
            struct.pack(">BBBH", 2, 0, 7, 1)
            + struct.pack(">I", 0x123)
            + b"\x04"
            + bytes.fromhex("11223344")
        )
        self.assertEqual(packet, expected)

    def test_decode_reads_header_and_frames(self) -> None:
        frame = CanFrame(arbitration_id=0x123, data=bytes.fromhex("11223344"))
        packet, consumed = decode_packet(encode_packet([frame], seq_no=9))
        self.assertEqual(consumed, len(encode_packet([frame], seq_no=9)))
        self.assertEqual(packet.version, 2)
        self.assertEqual(packet.seq_no, 9)
        self.assertEqual(len(packet.frames), 1)
        self.assertEqual(packet.frames[0].arbitration_id, 0x123)


class CodecRoundTripTests(unittest.TestCase):
    def test_round_trip_all_frame_types(self) -> None:
        frames = [
            CanFrame(
                arbitration_id=0x18FEEE31,
                data=bytes.fromhex("0102030405060708"),
                is_extended_id=True,
            ),
            CanFrame(arbitration_id=0x200, data=b"", is_remote_frame=True),
            CanFrame(arbitration_id=0x300, data=b"", is_error_frame=True),
            CanFrame(
                arbitration_id=0x7FF,
                data=bytes(16),
                frame_format="can_fd",
                bitrate_switch=True,
                error_state_indicator=True,
            ),
        ]
        decoded = frames_from_bytes(encode_packet(frames))
        self.assertEqual(len(decoded), len(frames))
        for original, got in zip(frames, decoded):
            self.assertEqual(got.arbitration_id, original.arbitration_id)
            self.assertEqual(got.is_extended_id, original.is_extended_id)
            self.assertEqual(got.is_remote_frame, original.is_remote_frame)
            self.assertEqual(got.is_error_frame, original.is_error_frame)
            self.assertEqual(got.frame_format, original.frame_format)
            self.assertEqual(got.bitrate_switch, original.bitrate_switch)
            self.assertEqual(got.error_state_indicator, original.error_state_indicator)
            self.assertEqual(got.data, original.data)

    def test_concatenated_datagrams_decode_in_order(self) -> None:
        a = CanFrame(arbitration_id=0x100, data=b"\x01")
        b = CanFrame(arbitration_id=0x200, data=b"\x02")
        stream = encode_packet([a]) + encode_packet([b])
        decoded = frames_from_bytes(stream)
        self.assertEqual([f.arbitration_id for f in decoded], [0x100, 0x200])

    def test_encode_packets_chunks_by_max_count(self) -> None:
        frames = [CanFrame(arbitration_id=i, data=b"\x00") for i in range(5)]
        datagrams = encode_packets(frames, max_count=2)
        self.assertEqual(len(datagrams), 3)  # 2 + 2 + 1
        self.assertEqual(len(frames_from_bytes(b"".join(datagrams))), 5)

    def test_truncated_datagram_raises(self) -> None:
        good = encode_packet([CanFrame(arbitration_id=0x123, data=b"\xaa\xbb")])
        with self.assertRaises(CannelloniError) as ctx:
            decode_packet(good[:-1])
        self.assertEqual(ctx.exception.code, "CANNELLONI_TRUNCATED")

    def test_unsupported_version_raises(self) -> None:
        bad = bytearray(encode_packet([CanFrame(arbitration_id=0x1, data=b"")]))
        bad[0] = 9
        with self.assertRaises(CannelloniError) as ctx:
            decode_packet(bytes(bad))
        self.assertEqual(ctx.exception.code, "CANNELLONI_VERSION_UNSUPPORTED")


class CannelloniCliTests(unittest.TestCase):
    def test_decode_cli_against_capture_round_trip(self) -> None:
        frames = LocalTransport().frames_from_file(str(FIXTURES / "sample.candump"))
        payload = encode_packet(frames, seq_no=1)
        path = FIXTURES / "cannelloni_sample.bin"
        path.write_bytes(payload)

        exit_code, stdout, _ = run_cli("cannelloni", "decode", "--file", str(path), "--json")
        self.assertEqual(exit_code, 0)
        data = json.loads(stdout)["data"]
        self.assertEqual(data["frame_count"], len(frames))
        decoded_ids = [e["payload"]["frame"]["arbitration_id"] for e in data["events"]]
        self.assertEqual(decoded_ids, [f.arbitration_id for f in frames])

    def test_send_dry_run_plans_datagrams_without_socket(self) -> None:
        exit_code, stdout, _ = run_cli(
            "cannelloni",
            "send",
            "127.0.0.1:20000",
            "--file",
            str(FIXTURES / "sample.candump"),
            "--dry-run",
            "--json",
        )
        self.assertEqual(exit_code, 0)
        data = json.loads(stdout)["data"]
        self.assertEqual(data["mode"], "dry_run")
        self.assertEqual(data["datagram_count"], 1)
        # The planned datagram decodes back to the capture frames.
        decoded = frames_from_bytes(bytes.fromhex(data["datagrams"][0]))
        self.assertEqual(len(decoded), 3)

    def test_send_invalid_target_returns_structured_error(self) -> None:
        exit_code, stdout, _ = run_cli(
            "cannelloni",
            "send",
            "no-port-here",
            "--file",
            str(FIXTURES / "sample.candump"),
            "--dry-run",
            "--json",
        )
        self.assertNotEqual(exit_code, 0)
        payload = json.loads(stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["errors"][0]["code"], "CANNELLONI_INVALID_TARGET")

    def test_send_transmits_over_loopback_udp(self) -> None:
        receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        receiver.bind(("127.0.0.1", 0))
        receiver.settimeout(5)
        port = receiver.getsockname()[1]
        try:
            import os
            from unittest.mock import patch

            with patch.dict(os.environ, {"CANARCHY_MCP_NONINTERACTIVE_ACK": "1"}):
                exit_code, stdout, _ = run_cli(
                    "cannelloni",
                    "send",
                    f"127.0.0.1:{port}",
                    "--file",
                    str(FIXTURES / "sample.candump"),
                    "--ack-active",
                    "--json",
                )
            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(stdout)["data"]["mode"], "active")
            datagram, _addr = receiver.recvfrom(65535)
            received = frames_from_bytes(datagram)
            self.assertEqual(
                [f.arbitration_id for f in received], [0x18FEEE31, 0x18F00431, 0x18FEF100]
            )
        finally:
            receiver.close()


class CannelloniMcpTests(unittest.TestCase):
    def test_decode_exposed_send_excluded(self) -> None:
        from canarchy.mcp_server import _TOOL_NAMES, _build_argv

        self.assertIn("cannelloni_decode", _TOOL_NAMES)
        self.assertNotIn("cannelloni_send", _TOOL_NAMES)
        self.assertEqual(
            _build_argv("cannelloni_decode", {"file": "x.bin"}),
            ["cannelloni", "decode", "--file", "x.bin", "--json"],
        )


class CodecBoundsTests(unittest.TestCase):
    """MTU chunking and DLC validation (PR #429 review)."""

    def test_encode_packets_caps_datagrams_by_mtu(self) -> None:
        # 64 full-size CAN FD frames would be one count-chunk (~4.6 KB) but must
        # split into several datagrams once the 1500-byte MTU is applied.
        frames = [
            CanFrame(arbitration_id=i & 0x7FF, data=bytes(64), frame_format="can_fd")
            for i in range(64)
        ]
        datagrams = encode_packets(frames, max_count=64)  # default MTU 1500
        self.assertGreater(len(datagrams), 1)
        self.assertTrue(all(len(d) <= 1500 for d in datagrams))
        self.assertEqual(len(frames_from_bytes(b"".join(datagrams))), 64)

    def test_encode_packets_mtu_none_disables_byte_cap(self) -> None:
        frames = [
            CanFrame(arbitration_id=i & 0x7FF, data=bytes(64), frame_format="can_fd")
            for i in range(64)
        ]
        datagrams = encode_packets(frames, max_count=64, max_bytes=None)
        self.assertEqual(len(datagrams), 1)
        self.assertGreater(len(datagrams[0]), 1500)

    def test_oversize_single_frame_emitted_alone(self) -> None:
        frames = [CanFrame(arbitration_id=0x1, data=bytes(64), frame_format="can_fd")]
        datagrams = encode_packets(frames, max_bytes=10)  # smaller than the frame
        self.assertEqual(len(datagrams), 1)

    def test_invalid_classic_dlc_raises_structured_error(self) -> None:
        # header(count=1) + can_id + len=9 + 9 data bytes: non-truncated but invalid.
        bad = struct.pack(">BBBH", 2, 0, 0, 1) + struct.pack(">I", 0x123) + b"\x09" + bytes(9)
        with self.assertRaises(CannelloniError) as ctx:
            decode_packet(bad)
        self.assertEqual(ctx.exception.code, "CANNELLONI_INVALID_DLC")

    def test_invalid_fd_dlc_raises_structured_error(self) -> None:
        bad = (
            struct.pack(">BBBH", 2, 0, 0, 1)
            + struct.pack(">I", 0x1)
            + bytes([0x80 | 65])
            + b"\x00"
            + bytes(65)
        )
        with self.assertRaises(CannelloniError) as ctx:
            decode_packet(bad)
        self.assertEqual(ctx.exception.code, "CANNELLONI_INVALID_DLC")

    def test_decode_cli_returns_structured_error_for_invalid_dlc(self) -> None:
        bad = struct.pack(">BBBH", 2, 0, 0, 1) + struct.pack(">I", 0x123) + b"\x09" + bytes(9)
        path = FIXTURES / "cannelloni_invalid_dlc.bin"
        path.write_bytes(bad)
        try:
            exit_code, stdout, _ = run_cli("cannelloni", "decode", "--file", str(path), "--json")
            self.assertNotEqual(exit_code, 0)
            payload = json.loads(stdout)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["errors"][0]["code"], "CANNELLONI_INVALID_DLC")
        finally:
            path.unlink(missing_ok=True)
