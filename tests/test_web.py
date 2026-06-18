"""Tests for the read-only web dashboard (`canarchy web serve`, #324)."""

from __future__ import annotations

import base64
import concurrent.futures
import json
import os
import socket
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from canarchy.transport import LocalTransport
from canarchy.web import (
    WebDashboardServer,
    WebDependencyError,
    build_dashboard_events,
    encode_ws_text_frame,
    parse_bind,
    read_ws_frame,
    websocket_accept_key,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _frames(name: str):
    return LocalTransport().frames_from_file(str(FIXTURES / name))


def _start_server(events, **kwargs):
    server = WebDashboardServer(
        "127.0.0.1:0", events=events, source={"file": "test.candump"}, **kwargs
    )
    server.start_background()
    return server


def _ws_connect(server) -> socket.socket:
    host, port = server.server_address[0], server.server_address[1]
    sock = socket.create_connection((host, port), timeout=5)
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    sock.sendall(
        (
            f"GET /ws HTTP/1.1\r\nHost: {host}:{port}\r\n"
            "Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
        ).encode("ascii")
    )
    response = b""
    while b"\r\n\r\n" not in response:
        response += sock.recv(4096)
    assert b"101" in response.split(b"\r\n", 1)[0]
    assert websocket_accept_key(key).encode("ascii") in response
    return sock


def _http_get(server, path: str):
    host, port = server.server_address[0], server.server_address[1]
    return urllib.request.urlopen(f"http://{host}:{port}{path}", timeout=5)


# --- TEST-WEB-01: event stream construction ---------------------------------


def test_build_dashboard_events_emits_frame_and_j1939_events() -> None:
    events = build_dashboard_events(_frames("j1939_heavy_vehicle.candump"))

    types = {event["event_type"] for event in events}
    assert "frame" in types
    assert "j1939_pgn" in types
    j1939 = next(event for event in events if event["event_type"] == "j1939_pgn")
    assert "pgn_label" in j1939["payload"]
    assert "source_address_name" in j1939["payload"]


def test_build_dashboard_events_decodes_signals_with_dbc() -> None:
    events = build_dashboard_events(
        _frames("j1939_heavy_vehicle.candump"),
        dbc_path=str(FIXTURES / "j1939_sample.dbc"),
    )

    decoded = [event for event in events if event["event_type"] == "decoded_message"]
    assert decoded
    assert "signals" in decoded[0]["payload"]
    assert decoded[0]["payload"]["message_name"]


def test_build_dashboard_events_includes_uds_transactions(tmp_path) -> None:
    capture = tmp_path / "uds.candump"
    capture.write_text(
        "(0.000000) can0 7E0#0210030000000000\n(0.010000) can0 7E8#0650030032013700\n"
    )
    events = build_dashboard_events(LocalTransport().frames_from_file(str(capture)))

    uds = [event for event in events if event["event_type"] == "uds_transaction"]
    assert len(uds) == 1
    assert uds[0]["payload"]["service_name"]


def test_events_are_timestamp_ordered() -> None:
    events = build_dashboard_events(_frames("j1939_heavy_vehicle.candump"))
    timestamps = [e["timestamp"] for e in events if e["timestamp"] is not None]
    assert timestamps == sorted(timestamps)


# --- TEST-WEB-02: server startup + HTTP surface ------------------------------


def test_server_serves_spa_and_status_against_fixture_capture() -> None:
    events = build_dashboard_events(_frames("j1939_heavy_vehicle.candump"))
    server = _start_server(events)
    try:
        spa = _http_get(server, "/").read().decode("utf-8")
        assert "CANarchy Dashboard" in spa
        assert "WebSocket" in spa

        status = json.loads(_http_get(server, "/api/status").read())
        assert status["ok"] is True
        assert status["read_only"] is True
        assert status["event_count"] == len(events)
        assert status["clients"] == 0
    finally:
        server.stop()


def test_unknown_path_returns_404() -> None:
    server = _start_server([])
    try:
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            _http_get(server, "/nope")
        assert exc_info.value.code == 404
    finally:
        server.stop()


# --- TEST-WEB-03: WebSocket smoke --------------------------------------------


def test_websocket_streams_envelope_events() -> None:
    events = build_dashboard_events(
        _frames("j1939_heavy_vehicle.candump"),
        dbc_path=str(FIXTURES / "j1939_sample.dbc"),
    )
    server = _start_server(events, rate=0.0)  # rate 0 disables pacing
    try:
        sock = _ws_connect(server)
        received: list[dict] = []
        while True:
            frame = read_ws_frame(sock)
            if frame is None:
                break
            opcode, payload = frame
            if opcode == 0x8:  # close after stream completes
                break
            if opcode == 0x1:
                received.append(json.loads(payload))
        sock.close()

        types = {event["event_type"] for event in received}
        assert "frame" in types
        assert "j1939_pgn" in types
        assert "decoded_message" in types
        # The completion alert is the documented end-of-stream marker.
        assert received[-1]["event_type"] == "alert"
        assert received[-1]["payload"]["code"] == "STREAM_COMPLETE"
        # Every streamed object is a canonical envelope event.
        assert all({"event_type", "payload", "source", "timestamp"} <= set(e) for e in received)
    finally:
        server.stop()


# --- TEST-WEB-04: read-only surface ------------------------------------------


def test_write_methods_are_rejected() -> None:
    server = _start_server([])
    try:
        host, port = server.server_address[0], server.server_address[1]
        for method in ("POST", "PUT", "DELETE", "PATCH"):
            request = urllib.request.Request(f"http://{host}:{port}/", data=b"x", method=method)
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(request, timeout=5)
            assert exc_info.value.code == 405
            body = json.loads(exc_info.value.read())
            assert body["errors"][0]["code"] == "WEB_READ_ONLY"
    finally:
        server.stop()


# --- TEST-WEB-05: bind validation --------------------------------------------


def test_parse_bind_rejects_malformed_addresses() -> None:
    assert parse_bind("127.0.0.1:8474") == ("127.0.0.1", 8474)
    for bad in ("8474", "localhost:", "localhost:notaport", "localhost:70000"):
        with pytest.raises(WebDependencyError) as exc_info:
            parse_bind(bad)
        assert exc_info.value.code == "WEB_BIND_INVALID"


def test_ws_text_frame_round_trip() -> None:
    # Server frames are unmasked; the reader handles both masked and unmasked.
    for payload in ("x", "y" * 200, "z" * 70000):
        encoded = encode_ws_text_frame(payload)
        left, right = socket.socketpair()
        try:
            left.settimeout(5)
            right.settimeout(5)
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                send = executor.submit(left.sendall, encoded)
                opcode, decoded = read_ws_frame(right)
                send.result(timeout=5)
            assert opcode == 0x1
            assert decoded.decode("utf-8") == payload
        finally:
            left.close()
            right.close()


# --- TEST-WEB-06: CLI surface -------------------------------------------------


def test_cli_web_serve_missing_file_returns_structured_error(capsys) -> None:
    from canarchy.cli import main

    exit_code = main(["web", "serve", "--file", "/tmp/does-not-exist.candump", "--json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code != 0
    assert payload["ok"] is False
    assert payload["command"] == "web serve"


def test_cli_web_serve_bad_dbc_returns_structured_error(capsys) -> None:
    """#324 review: a bad --dbc ref yields a DBC_* envelope, not a traceback."""
    from canarchy.cli import EXIT_DECODE_ERROR, main

    exit_code = main(
        [
            "web",
            "serve",
            "--file",
            str(FIXTURES / "j1939_heavy_vehicle.candump"),
            "--dbc",
            "/tmp/does-not-exist.dbc",
            "--bind",
            "127.0.0.1:0",
            "--json",
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == EXIT_DECODE_ERROR
    assert payload["ok"] is False
    assert payload["command"] == "web serve"
    assert payload["errors"][0]["code"].startswith("DBC_")


def test_cli_web_serve_starts_and_reports_url(capsys) -> None:
    from unittest.mock import patch

    from canarchy.cli import main

    with patch("canarchy.web.WebDashboardServer.serve_forever", return_value=None):
        exit_code = main(
            [
                "web",
                "serve",
                "--file",
                str(FIXTURES / "j1939_heavy_vehicle.candump"),
                "--bind",
                "127.0.0.1:0",
                "--json",
            ]
        )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["data"]["read_only"] is True
    assert payload["data"]["url"].startswith("http://127.0.0.1:")
    assert payload["data"]["event_count"] > 0
    assert any("read-only" in warning for warning in payload["warnings"])
