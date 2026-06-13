"""Read-only browser dashboard over the canonical JSONL event envelope.

`canarchy web serve` starts a small HTTP + WebSocket server that streams the
same event objects the CLI emits (`frame`, `decoded_message`, `signal`,
`j1939_pgn`, `uds_transaction`) to a bundled single-file SPA. The CLI remains
the contract; the web layer is a view, like the TUI.

The implementation is intentionally dependency-light: the HTTP side is
`http.server` from the standard library and the WebSocket side is a minimal
RFC 6455 server (handshake, server->client text frames, ping/pong/close
handling). The server is read-only — it exposes no active-transmit endpoints
at all, and every non-GET request is rejected with 405.
"""

from __future__ import annotations

import base64
import hashlib
import importlib.resources
import json
import socket
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from canarchy.models import (
    CanFrame,
    FrameEvent,
    J1939ObservationEvent,
)

_WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
# Pacing cap so huge capture gaps do not stall the stream (matches replay).
_MAX_GAP_SECONDS = 1.0
DEFAULT_BIND = "127.0.0.1:8474"


class WebDependencyError(Exception):
    """Raised when the dashboard cannot start (bad bind, missing assets)."""

    def __init__(self, code: str, message: str, hint: str) -> None:
        super().__init__(message)
        self.code = code
        self.hint = hint


def parse_bind(bind: str) -> tuple[str, int]:
    """Parse a ``host:port`` bind string."""
    host, _, port_text = bind.rpartition(":")
    if not host or not port_text:
        raise WebDependencyError(
            code="WEB_BIND_INVALID",
            message=f"Bind address {bind!r} is not in <host>:<port> form.",
            hint="Pass --bind 127.0.0.1:8474 (or another host:port).",
        )
    try:
        port = int(port_text)
    except ValueError as exc:
        raise WebDependencyError(
            code="WEB_BIND_INVALID",
            message=f"Bind port {port_text!r} is not an integer.",
            hint="Pass --bind 127.0.0.1:8474 (or another host:port).",
        ) from exc
    if not 0 <= port <= 65535:
        raise WebDependencyError(
            code="WEB_BIND_INVALID",
            message=f"Bind port {port} is outside 0..65535.",
            hint="Pass a port between 0 (ephemeral) and 65535.",
        )
    return host, port


def load_spa() -> str:
    """Return the bundled single-page dashboard HTML."""
    return (
        importlib.resources.files("canarchy.resources.web")
        .joinpath("index.html")
        .read_text(encoding="utf-8")
    )


def build_dashboard_events(
    frames: list[CanFrame], *, dbc_path: str | None = None
) -> list[dict[str, Any]]:
    """Serialize capture frames into the dashboard's timestamp-ordered events.

    Emits per frame: a `frame` event, a `j1939_pgn` observation (annotated
    with the bundled PGN label and source-address name) for extended ids,
    and `decoded_message` + `signal` events when a database is supplied.
    UDS transactions reassembled from the capture are merged in by timestamp.
    """
    from canarchy.j1939 import decompose_arbitration_id
    from canarchy.j1939_metadata import pgn_lookup, source_address_lookup
    from canarchy.uds import enrich_uds_transactions, uds_trace_transactions

    database = None
    if dbc_path:
        from canarchy.dbc_runtime import load_runtime_database

        database = load_runtime_database(dbc_path)

    ordered: list[tuple[float, int, dict[str, Any]]] = []
    sequence = 0

    def _push(timestamp: float | None, event: dict[str, Any]) -> None:
        nonlocal sequence
        ordered.append((timestamp if timestamp is not None else 0.0, sequence, event))
        sequence += 1

    for frame in frames:
        _push(frame.timestamp, FrameEvent(frame=frame, source="web.serve").to_event().to_payload())

        if frame.is_extended_id:
            try:
                identifier = decompose_arbitration_id(frame.arbitration_id)
            except ValueError:
                identifier = None
            if identifier is not None:
                event = J1939ObservationEvent(
                    pgn=identifier.pgn,
                    source_address=identifier.source_address,
                    destination_address=identifier.destination_address,
                    priority=identifier.priority,
                    frame=frame,
                    source="web.serve",
                ).to_payload()
                meta = pgn_lookup(identifier.pgn) or {}
                event["payload"]["pgn_label"] = meta.get("label")
                event["payload"]["pgn_name"] = meta.get("name")
                event["payload"]["source_address_name"] = source_address_lookup(
                    identifier.source_address
                )
                _push(frame.timestamp, event)

        if database is not None:
            try:
                message = database.get_message_by_frame_id(frame.arbitration_id)
                decoded = message.decode(bytes(frame.data))
            except Exception:
                decoded = None
                message = None
            if decoded is not None and message is not None:
                signals = {name: _jsonable(value) for name, value in decoded.items()}
                _push(
                    frame.timestamp,
                    {
                        "event_type": "decoded_message",
                        "source": "web.serve",
                        "timestamp": frame.timestamp,
                        "payload": {
                            "frame": frame.to_payload(),
                            "message_name": message.name,
                            "signals": signals,
                        },
                    },
                )

    for transaction in enrich_uds_transactions(uds_trace_transactions(frames, source="web.serve")):
        _push(transaction.timestamp, transaction.to_payload())

    ordered.sort(key=lambda item: (item[0], item[1]))
    return [event for _, _, event in ordered]


def _jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


# --- minimal RFC 6455 WebSocket helpers --------------------------------------


def websocket_accept_key(client_key: str) -> str:
    digest = hashlib.sha1((client_key + _WS_GUID).encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


def encode_ws_text_frame(payload: str) -> bytes:
    """Encode a single unmasked server->client text frame."""
    data = payload.encode("utf-8")
    length = len(data)
    header = bytearray([0x81])  # FIN + text opcode
    if length < 126:
        header.append(length)
    elif length < 1 << 16:
        header.append(126)
        header += struct.pack(">H", length)
    else:
        header.append(127)
        header += struct.pack(">Q", length)
    return bytes(header) + data


def _encode_ws_control_frame(opcode: int, data: bytes = b"") -> bytes:
    return bytes([0x80 | opcode, len(data)]) + data


def _read_exact(sock: socket.socket, count: int) -> bytes | None:
    chunks = b""
    while len(chunks) < count:
        chunk = sock.recv(count - len(chunks))
        if not chunk:
            return None
        chunks += chunk
    return chunks


def read_ws_frame(sock: socket.socket) -> tuple[int, bytes] | None:
    """Read one (client->server, masked) frame; returns (opcode, payload)."""
    header = _read_exact(sock, 2)
    if header is None:
        return None
    opcode = header[0] & 0x0F
    masked = bool(header[1] & 0x80)
    length = header[1] & 0x7F
    if length == 126:
        extended = _read_exact(sock, 2)
        if extended is None:
            return None
        length = struct.unpack(">H", extended)[0]
    elif length == 127:
        extended = _read_exact(sock, 8)
        if extended is None:
            return None
        length = struct.unpack(">Q", extended)[0]
    mask = b"\x00\x00\x00\x00"
    if masked:
        mask_bytes = _read_exact(sock, 4)
        if mask_bytes is None:
            return None
        mask = mask_bytes
    payload = _read_exact(sock, length) if length else b""
    if payload is None:
        return None
    if masked:
        payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    return opcode, payload


# --- server -------------------------------------------------------------------


class _DashboardHandler(BaseHTTPRequestHandler):
    server: WebDashboardServer  # type: ignore[assignment]
    protocol_version = "HTTP/1.1"

    # Quiet request logging; the CLI owns stderr.
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass

    def _reject_write(self) -> None:
        body = json.dumps(
            {
                "ok": False,
                "errors": [
                    {
                        "code": "WEB_READ_ONLY",
                        "message": "The CANarchy web dashboard is read-only.",
                        "hint": (
                            "Active-transmit workflows are CLI-only and gated by "
                            "the active-transmit safety model."
                        ),
                    }
                ],
            },
            sort_keys=True,
        ).encode("utf-8")
        self.send_response(405)
        self.send_header("Allow", "GET")
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_POST = do_PUT = do_DELETE = do_PATCH = _reject_write

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        if self.path == "/" or self.path == "/index.html":
            self._serve_spa()
        elif self.path == "/api/status":
            self._serve_status()
        elif self.path == "/ws":
            self._serve_websocket()
        else:
            self.send_error(404, "Not found")

    def _serve_spa(self) -> None:
        body = self.server.spa_html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_status(self) -> None:
        body = json.dumps(self.server.status_payload(), sort_keys=True).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_websocket(self) -> None:
        client_key = self.headers.get("Sec-WebSocket-Key")
        upgrade = (self.headers.get("Upgrade") or "").lower()
        if upgrade != "websocket" or not client_key:
            self.send_error(400, "WebSocket upgrade required")
            return
        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", websocket_accept_key(client_key))
        self.end_headers()
        self.close_connection = True

        sock = self.connection
        self.server.register_client()
        try:
            self._stream_events(sock)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            self.server.unregister_client()

    def _stream_events(self, sock: socket.socket) -> None:
        server = self.server
        sock.settimeout(_MAX_GAP_SECONDS)
        while True:
            previous_ts: float | None = None
            for event in server.events:
                if server.stopping.is_set():
                    return
                timestamp = event.get("timestamp")
                if (
                    server.rate > 0
                    and isinstance(timestamp, (int, float))
                    and previous_ts is not None
                    and timestamp > previous_ts
                ):
                    delay = (timestamp - previous_ts) / server.rate
                    if delay > 0:
                        time.sleep(min(delay, _MAX_GAP_SECONDS))
                if isinstance(timestamp, (int, float)):
                    previous_ts = timestamp
                sock.sendall(encode_ws_text_frame(json.dumps(event, sort_keys=True)))
                server.count_event()
                if not self._drain_client(sock):
                    return
            if not server.loop:
                break
        sock.sendall(
            encode_ws_text_frame(
                json.dumps(
                    {
                        "event_type": "alert",
                        "source": "web.serve",
                        "timestamp": None,
                        "payload": {
                            "level": "info",
                            "code": "STREAM_COMPLETE",
                            "message": "Capture stream complete.",
                        },
                    },
                    sort_keys=True,
                )
            )
        )
        sock.sendall(_encode_ws_control_frame(0x8))

    def _drain_client(self, sock: socket.socket) -> bool:
        """Service pending client frames; returns False when the client closed."""
        sock.setblocking(False)
        try:
            while True:
                try:
                    frame = read_ws_frame(sock)
                except (BlockingIOError, TimeoutError):
                    return True
                if frame is None:
                    return False
                opcode, payload = frame
                if opcode == 0x8:  # close
                    return False
                if opcode == 0x9:  # ping -> pong
                    sock.setblocking(True)
                    sock.sendall(_encode_ws_control_frame(0xA, payload))
                    sock.setblocking(False)
                # Anything else from the client is ignored: read-only surface.
        finally:
            sock.setblocking(True)
            sock.settimeout(_MAX_GAP_SECONDS)


class WebDashboardServer(ThreadingHTTPServer):
    """Read-only dashboard server bound to a host:port."""

    daemon_threads = True

    def __init__(
        self,
        bind: str,
        *,
        events: list[dict[str, Any]],
        source: dict[str, Any],
        rate: float = 1.0,
        loop: bool = False,
        spa_html: str | None = None,
    ) -> None:
        host, port = parse_bind(bind)
        self.events = events
        self.source = source
        self.rate = rate
        self.loop = loop
        self.spa_html = spa_html if spa_html is not None else load_spa()
        self.read_only = True
        self.started_at = time.time()
        self.stopping = threading.Event()
        self._lock = threading.Lock()
        self._clients = 0
        self._events_streamed = 0
        try:
            super().__init__((host, port), _DashboardHandler)
        except OSError as exc:
            raise WebDependencyError(
                code="WEB_BIND_FAILED",
                message=f"Could not bind the dashboard to {bind}: {exc}.",
                hint="Pick a free port with --bind, or stop the process using it.",
            ) from exc

    # -- shared state used by the handler --------------------------------
    def register_client(self) -> None:
        with self._lock:
            self._clients += 1

    def unregister_client(self) -> None:
        with self._lock:
            self._clients -= 1

    def count_event(self) -> None:
        with self._lock:
            self._events_streamed += 1

    def status_payload(self) -> dict[str, Any]:
        with self._lock:
            clients = self._clients
            streamed = self._events_streamed
        return {
            "ok": True,
            "read_only": self.read_only,
            "source": self.source,
            "event_count": len(self.events),
            "events_streamed": streamed,
            "clients": clients,
            "rate": self.rate,
            "loop": self.loop,
            "uptime_seconds": round(time.time() - self.started_at, 3),
        }

    @property
    def url(self) -> str:
        host, port = self.server_address[0], self.server_address[1]
        return f"http://{host}:{port}/"

    def serve_forever(self, poll_interval: float = 0.5) -> None:
        self._serving = True
        try:
            super().serve_forever(poll_interval)
        finally:
            self._serving = False

    def start_background(self) -> threading.Thread:
        thread = threading.Thread(target=self.serve_forever, daemon=True)
        thread.start()
        return thread

    def stop(self) -> None:
        self.stopping.set()
        # shutdown() blocks on serve_forever's exit handshake; only call it
        # when the serve loop actually ran (it may have been skipped or
        # patched out).
        if getattr(self, "_serving", False):
            self.shutdown()
        self.server_close()
