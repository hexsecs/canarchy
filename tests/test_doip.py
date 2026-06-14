"""Tests for the DoIP (Diagnostic over IP) transport and UDS workflows (#326).

The responder fixture is an in-process TCP server bound to loopback, so the
end-to-end CLI tests exercise the real socket path with no live network.
"""

from __future__ import annotations

import contextlib
import io
import json
import socket
import struct
import threading
import unittest

from canarchy.doip import (
    DEFAULT_SOURCE_ADDRESS,
    PT_DIAGNOSTIC_MESSAGE,
    PT_DIAGNOSTIC_MESSAGE_ACK,
    PT_DIAGNOSTIC_MESSAGE_NACK,
    PT_ROUTING_ACTIVATION_REQUEST,
    PT_ROUTING_ACTIVATION_RESPONSE,
    DoipConnection,
    DoipError,
    decode_message,
    encode_diagnostic_message,
    encode_message,
    encode_routing_activation_request,
    is_doip_target,
    parse_diagnostic_message,
    parse_doip_target,
)


def run_cli(*argv: str) -> tuple[int, str, str]:
    from canarchy.cli import main

    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = main(argv)
    return exit_code, stdout.getvalue(), stderr.getvalue()


class DoipResponder:
    """A loopback DoIP gateway/ECU that scripts UDS responses.

    ``responses`` maps a UDS request (bytes) to a UDS response (bytes). A
    request in ``silent`` is acknowledged at the transport layer but receives
    no diagnostic response, exercising the client's timeout-skip path.
    """

    def __init__(
        self,
        responses: dict[bytes, bytes],
        *,
        entity_address: int = 0x0E80,
        activation_code: int = 0x10,
        silent: tuple[bytes, ...] = (),
        nack_requests: tuple[bytes, ...] = (),
    ) -> None:
        self.responses = responses
        self.entity_address = entity_address
        self.activation_code = activation_code
        self.silent = set(silent)
        self.nack_requests = set(nack_requests)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(8)
        self._stop = False
        self._thread = threading.Thread(target=self._serve, daemon=True)

    @property
    def port(self) -> int:
        return self._sock.getsockname()[1]

    def __enter__(self) -> DoipResponder:
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop = True
        with contextlib.suppress(OSError):
            self._sock.close()
        self._thread.join(timeout=2)

    def _serve(self) -> None:
        while not self._stop:
            try:
                client, _addr = self._sock.accept()
            except OSError:
                return
            with contextlib.suppress(Exception):
                self._handle(client)

    def _handle(self, client: socket.socket) -> None:
        client.settimeout(2)
        conn = DoipConnection(client)
        tester = DEFAULT_SOURCE_ADDRESS
        try:
            while not self._stop:
                message = conn.recv_message()
                if message.payload_type == PT_ROUTING_ACTIVATION_REQUEST:
                    (tester,) = struct.unpack_from(">H", message.payload, 0)
                    payload = (
                        struct.pack(">HHB", tester, self.entity_address, self.activation_code)
                        + b"\x00\x00\x00\x00"
                    )
                    conn.send_raw(encode_message(PT_ROUTING_ACTIVATION_RESPONSE, payload))
                elif message.payload_type == PT_DIAGNOSTIC_MESSAGE:
                    _src, _tgt, request = parse_diagnostic_message(message.payload)
                    ack = struct.pack(">HHB", self.entity_address, tester, 0x00)
                    conn.send_raw(encode_message(PT_DIAGNOSTIC_MESSAGE_ACK, ack))
                    if request in self.nack_requests:
                        nack = struct.pack(">HHB", self.entity_address, tester, 0x03)
                        conn.send_raw(encode_message(PT_DIAGNOSTIC_MESSAGE_NACK, nack))
                        continue
                    if request in self.silent:
                        continue
                    response = self.responses.get(request)
                    if response is not None:
                        conn.send_raw(
                            encode_diagnostic_message(self.entity_address, tester, response)
                        )
        except DoipError:
            return
        finally:
            with contextlib.suppress(OSError):
                client.close()


class DoipTargetParsingTests(unittest.TestCase):
    def test_parse_minimal_target_applies_defaults(self) -> None:
        target = parse_doip_target("doip://192.0.2.10?logical_address=0x0E80")
        self.assertEqual(target.host, "192.0.2.10")
        self.assertEqual(target.port, 13400)
        self.assertEqual(target.logical_address, 0x0E80)
        self.assertEqual(target.source_address, DEFAULT_SOURCE_ADDRESS)
        self.assertEqual(target.activation_type, 0x00)

    def test_parse_full_target_reads_all_parameters(self) -> None:
        target = parse_doip_target(
            "doip://host:13401?logical_address=3712&source_address=0x0E01&activation_type=0xE0&timeout=0.5"
        )
        self.assertEqual(target.port, 13401)
        self.assertEqual(target.logical_address, 3712)
        self.assertEqual(target.source_address, 0x0E01)
        self.assertEqual(target.activation_type, 0xE0)
        self.assertEqual(target.timeout, 0.5)

    def test_is_doip_target_discriminates(self) -> None:
        self.assertTrue(is_doip_target("doip://h?logical_address=1"))
        self.assertTrue(is_doip_target("DOIP://h?logical_address=1"))
        self.assertFalse(is_doip_target("can0"))
        self.assertFalse(is_doip_target("vcan0"))
        self.assertFalse(is_doip_target(None))

    def test_invalid_targets_raise_structured_error(self) -> None:
        for bad in (
            "doip://host",  # missing logical_address
            "doip://?logical_address=1",  # missing host
            "doip://host?logical_address=0x1FFFF",  # out of 16-bit range
            "doip://host?logical_address=nope",  # non-integer
            "http://host?logical_address=1",  # wrong scheme
            "doip://host?logical_address=1&timeout=-1",  # non-positive timeout
        ):
            with self.subTest(bad=bad), self.assertRaises(DoipError) as ctx:
                parse_doip_target(bad)
            self.assertEqual(ctx.exception.code, "DOIP_INVALID_TARGET")


class DoipCodecTests(unittest.TestCase):
    def test_routing_activation_round_trip(self) -> None:
        data = encode_routing_activation_request(0x0E00, 0x00)
        message, consumed = decode_message(data)
        self.assertEqual(consumed, len(data))
        self.assertEqual(message.payload_type, PT_ROUTING_ACTIVATION_REQUEST)
        (source,) = struct.unpack_from(">H", message.payload, 0)
        self.assertEqual(source, 0x0E00)

    def test_diagnostic_message_round_trip(self) -> None:
        data = encode_diagnostic_message(0x0E00, 0x0E80, b"\x10\x01")
        message, _ = decode_message(data)
        source, target, user_data = parse_diagnostic_message(message.payload)
        self.assertEqual(source, 0x0E00)
        self.assertEqual(target, 0x0E80)
        self.assertEqual(user_data, b"\x10\x01")

    def test_concatenated_messages_decode_in_order(self) -> None:
        stream = encode_message(0x8002, b"\x0e\x80\x0e\x00\x00") + encode_diagnostic_message(
            0x0E80, 0x0E00, b"\x50\x01"
        )
        first, consumed = decode_message(stream)
        self.assertEqual(first.payload_type, 0x8002)
        second, _ = decode_message(stream[consumed:])
        self.assertEqual(second.payload_type, PT_DIAGNOSTIC_MESSAGE)

    def test_version_inverse_mismatch_raises(self) -> None:
        bad = bytearray(encode_diagnostic_message(0x0E00, 0x0E80, b"\x10\x01"))
        bad[1] = 0x00  # corrupt the inverse-version byte
        with self.assertRaises(DoipError) as ctx:
            decode_message(bytes(bad))
        self.assertEqual(ctx.exception.code, "DOIP_PROTOCOL_ERROR")

    def test_truncated_message_raises(self) -> None:
        data = encode_diagnostic_message(0x0E00, 0x0E80, b"\x10\x01")
        with self.assertRaises(DoipError) as ctx:
            decode_message(data[:-1])
        self.assertEqual(ctx.exception.code, "DOIP_PROTOCOL_ERROR")


class DoipCliTests(unittest.TestCase):
    def _target(self, port: int, logical: int = 0x0E80, **params: object) -> str:
        query = f"logical_address=0x{logical:04X}"
        for key, value in params.items():
            query += f"&{key}={value}"
        return f"doip://127.0.0.1:{port}?{query}"

    def test_scan_enumerates_sessions_over_loopback(self) -> None:
        responses = {
            b"\x10\x01": bytes.fromhex("500100320032"),
            b"\x10\x02": bytes.fromhex("7F1022"),  # NRC ConditionsNotCorrect
            b"\x10\x03": bytes.fromhex("500300320032"),
        }
        with DoipResponder(responses) as server:
            exit_code, stdout, _ = run_cli("uds", "scan", self._target(server.port), "--json")
        self.assertEqual(exit_code, 0)
        data = json.loads(stdout)["data"]
        self.assertEqual(data["mode"], "active")
        self.assertEqual(data["transport"], "doip")
        self.assertEqual(data["logical_address"], 0x0E80)
        self.assertEqual(data["responder_count"], 3)
        events = data["events"]
        services = [event["payload"]["service"] for event in events]
        self.assertEqual(services, [0x10, 0x10, 0x10])
        # The middle probe is a negative response surfaced as a transaction.
        nrcs = [event["payload"]["negative_response_code"] for event in events]
        self.assertIn(0x22, nrcs)

    def test_trace_runs_session_and_tester_present(self) -> None:
        responses = {
            b"\x10\x01": bytes.fromhex("500100320032"),
            b"\x3e\x00": bytes.fromhex("7E00"),
        }
        with DoipResponder(responses) as server:
            exit_code, stdout, _ = run_cli("uds", "trace", self._target(server.port), "--json")
        self.assertEqual(exit_code, 0)
        data = json.loads(stdout)["data"]
        self.assertEqual(data["mode"], "active")
        self.assertEqual(data["transport"], "doip")
        self.assertEqual(data["transaction_count"], 2)
        names = [event["payload"]["service_name"] for event in data["events"]]
        self.assertEqual(names, ["DiagnosticSessionControl", "TesterPresent"])

    def test_scan_skips_silent_probe(self) -> None:
        responses = {
            b"\x10\x01": bytes.fromhex("500100320032"),
            b"\x10\x03": bytes.fromhex("500300320032"),
        }
        with DoipResponder(responses, silent=(b"\x10\x02",)) as server:
            exit_code, stdout, _ = run_cli(
                "uds", "scan", self._target(server.port, timeout=0.3), "--json"
            )
        self.assertEqual(exit_code, 0)
        data = json.loads(stdout)["data"]
        self.assertEqual(data["responder_count"], 2)

    def test_invalid_target_returns_user_error(self) -> None:
        exit_code, stdout, _ = run_cli("uds", "scan", "doip://127.0.0.1:13400", "--json")
        self.assertEqual(exit_code, 1)
        payload = json.loads(stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["errors"][0]["code"], "DOIP_INVALID_TARGET")

    def test_unreachable_endpoint_returns_transport_error(self) -> None:
        # Bind then close a socket to obtain a port nothing is listening on.
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()
        exit_code, stdout, _ = run_cli("uds", "scan", self._target(port, timeout=0.3), "--json")
        self.assertEqual(exit_code, 2)
        payload = json.loads(stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["errors"][0]["code"], "DOIP_CONNECTION_FAILED")

    def test_diagnostic_nack_returns_transport_error(self) -> None:
        with DoipResponder({}, nack_requests=(b"\x10\x01",)) as server:
            exit_code, stdout, _ = run_cli("uds", "scan", self._target(server.port), "--json")
        self.assertEqual(exit_code, 2)
        payload = json.loads(stdout)
        self.assertEqual(payload["errors"][0]["code"], "DOIP_DIAGNOSTIC_NACK")


class DoipSafetyGateTests(unittest.TestCase):
    def test_scan_and_trace_require_ack_when_configured(self) -> None:
        import os
        from unittest.mock import patch

        target = "doip://127.0.0.1:13400?logical_address=0x0E80"
        with patch.dict(os.environ, {"CANARCHY_REQUIRE_ACTIVE_ACK": "1"}):
            for action in ("scan", "trace"):
                with self.subTest(action=action):
                    exit_code, stdout, _ = run_cli("uds", action, target, "--json")
                    self.assertEqual(exit_code, 1)
                    payload = json.loads(stdout)
                    self.assertEqual(payload["errors"][0]["code"], "ACTIVE_ACK_REQUIRED")


class DoipMcpExclusionTests(unittest.TestCase):
    def test_uds_tools_reject_doip_targets(self) -> None:
        import asyncio

        from canarchy.mcp_server import handle_call_tool

        target = "doip://127.0.0.1:13400?logical_address=0x0E80"
        for tool in ("uds_scan", "uds_trace"):
            with self.subTest(tool=tool):
                result = asyncio.run(handle_call_tool(tool, {"interface": target}))
                payload = json.loads(result[0].text)
                self.assertFalse(payload["ok"])
                self.assertEqual(payload["errors"][0]["code"], "DOIP_MCP_EXCLUDED")
