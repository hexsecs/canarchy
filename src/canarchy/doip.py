"""DoIP (Diagnostic over IP, ISO 13400-2) transport for UDS workflows.

DoIP tunnels UDS diagnostic messages over a TCP connection to a vehicle
gateway, reaching an ECU by its 16-bit logical address rather than a CAN
arbitration id. CANarchy speaks enough of the protocol — generic header,
routing activation, and diagnostic-message exchange — to run the existing
``uds scan`` / ``uds trace`` workflows against a ``doip://`` endpoint and emit
the same canonical :class:`~canarchy.models.UdsTransactionEvent` envelope.

Wire format (all multi-byte integers big-endian):

    message = header payload
    header  = protocol_version(1) inverse_version(1) payload_type(2) payload_length(4)

The diagnostic-message payload (type ``0x8001``) carries ``source_address(2)``,
``target_address(2)``, and the raw UDS PDU as ``user_data``. There is no ISO-TP
segmentation: DoIP frames the whole UDS message itself.

This module pairs a pure codec (header/payload encode + decode) with a thin TCP
connection. Opening a connection transmits, so the callers in ``cli`` gate the
DoIP workflows behind the active-transmit safety model, and the network egress
is a CLI-only operator action (not exposed through the MCP server).
"""

from __future__ import annotations

import socket
import struct
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlsplit

from canarchy.models import UdsTransactionEvent, serialize_events
from canarchy.uds import enrich_uds_transactions, uds_service_name

DOIP_DEFAULT_PORT = 13400
DOIP_PROTOCOL_VERSION = 0x02  # ISO 13400-2:2012
_INVERSE_VERSION = DOIP_PROTOCOL_VERSION ^ 0xFF

# Default tester (client) logical address when the target omits one. 0x0E00 is
# the conventional external-tester address from ISO 13400.
DEFAULT_SOURCE_ADDRESS = 0x0E00
DEFAULT_ACTIVATION_TYPE = 0x00  # default activation
DEFAULT_TIMEOUT = 2.0

# DoIP payload types used here.
PT_GENERIC_NACK = 0x0000
PT_ROUTING_ACTIVATION_REQUEST = 0x0005
PT_ROUTING_ACTIVATION_RESPONSE = 0x0006
PT_DIAGNOSTIC_MESSAGE = 0x8001
PT_DIAGNOSTIC_MESSAGE_ACK = 0x8002
PT_DIAGNOSTIC_MESSAGE_NACK = 0x8003

# Routing activation response code that means "routing successfully activated".
ROUTING_ACTIVATION_SUCCESS = 0x10

ROUTING_ACTIVATION_RESPONSE_CODES: dict[int, str] = {
    0x00: "DeniedUnknownSourceAddress",
    0x01: "DeniedAllSocketsRegistered",
    0x02: "DeniedSourceAddressMismatch",
    0x03: "DeniedSourceAddressAlreadyRegistered",
    0x04: "DeniedMissingAuthentication",
    0x05: "DeniedRejectedConfirmation",
    0x06: "DeniedUnsupportedActivationType",
    0x10: "RoutingSuccessfullyActivated",
    0x11: "RoutingWillBeActivatedConfirmationRequired",
}

DIAGNOSTIC_NACK_CODES: dict[int, str] = {
    0x02: "InvalidSourceAddress",
    0x03: "UnknownTargetAddress",
    0x04: "DiagnosticMessageTooLarge",
    0x05: "OutOfMemory",
    0x06: "TargetUnreachable",
    0x07: "UnknownNetwork",
    0x08: "TransportProtocolError",
}

_HEADER = struct.Struct(">BBHI")  # version, inverse_version, payload_type, payload_length
_MAX_PAYLOAD = (
    0x00FFFFFF  # cap an advertised payload length so a hostile peer cannot exhaust memory
)

# Session-control subfunctions probed by `uds scan` over DoIP (default,
# programming, extended) and the request/response sequence used by `uds trace`.
_SCAN_REQUESTS: tuple[bytes, ...] = (b"\x10\x01", b"\x10\x02", b"\x10\x03")
_TRACE_REQUESTS: tuple[bytes, ...] = (b"\x10\x01", b"\x3e\x00")


class DoipError(Exception):
    """Raised when a DoIP target, connection, or message is invalid."""

    def __init__(self, code: str, message: str, hint: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint


@dataclass(slots=True, frozen=True)
class DoipTarget:
    host: str
    port: int
    logical_address: int
    source_address: int = DEFAULT_SOURCE_ADDRESS
    activation_type: int = DEFAULT_ACTIVATION_TYPE
    timeout: float = DEFAULT_TIMEOUT


@dataclass(slots=True, frozen=True)
class DoipMessage:
    payload_type: int
    payload: bytes


def is_doip_target(value: str | None) -> bool:
    """Return ``True`` when ``value`` looks like a ``doip://`` endpoint URI."""
    return isinstance(value, str) and value.strip().lower().startswith("doip://")


def _parse_address(raw: str, *, field_name: str) -> int:
    text = raw.strip()
    try:
        value = int(text, 0)
    except ValueError as exc:
        raise DoipError(
            code="DOIP_INVALID_TARGET",
            message=f"DoIP {field_name} {text!r} is not a valid integer.",
            hint="Use a hex (0x0E80) or decimal logical address.",
        ) from exc
    if not 0 <= value <= 0xFFFF:
        raise DoipError(
            code="DOIP_INVALID_TARGET",
            message=f"DoIP {field_name} 0x{value:X} is out of the 16-bit range.",
            hint="Logical addresses are 16-bit (0x0000-0xFFFF).",
        )
    return value


def parse_doip_target(target: str) -> DoipTarget:
    """Parse ``doip://<host>:<port>?logical_address=0x0E80`` into a target.

    ``port`` defaults to 13400, ``source_address`` to 0x0E00, ``activation_type``
    to 0x00, and ``timeout`` to 2.0 seconds. ``logical_address`` is mandatory.
    """
    parts = urlsplit(target.strip())
    if parts.scheme.lower() != "doip":
        raise DoipError(
            code="DOIP_INVALID_TARGET",
            message=f"DoIP target {target!r} must use the doip:// scheme.",
            hint="Use doip://<host>:<port>?logical_address=0x0E80.",
        )
    host = parts.hostname
    if not host:
        raise DoipError(
            code="DOIP_INVALID_TARGET",
            message=f"DoIP target {target!r} is missing a host.",
            hint="Use doip://<host>:<port>?logical_address=0x0E80.",
        )
    try:
        port = parts.port if parts.port is not None else DOIP_DEFAULT_PORT
    except ValueError as exc:
        raise DoipError(
            code="DOIP_INVALID_TARGET",
            message=f"DoIP target {target!r} has an invalid port.",
            hint="Ports are 1-65535; omit for the default 13400.",
        ) from exc

    query = parse_qs(parts.query)
    logical_values = query.get("logical_address") or query.get("target_address")
    if not logical_values:
        raise DoipError(
            code="DOIP_INVALID_TARGET",
            message=f"DoIP target {target!r} is missing the logical_address query parameter.",
            hint="Append ?logical_address=0x0E80 with the ECU's logical address.",
        )
    logical_address = _parse_address(logical_values[0], field_name="logical_address")

    source_values = query.get("source_address")
    source_address = (
        _parse_address(source_values[0], field_name="source_address")
        if source_values
        else DEFAULT_SOURCE_ADDRESS
    )

    activation_values = query.get("activation_type")
    activation_type = (
        _parse_address(activation_values[0], field_name="activation_type")
        if activation_values
        else DEFAULT_ACTIVATION_TYPE
    )
    if activation_type > 0xFF:
        raise DoipError(
            code="DOIP_INVALID_TARGET",
            message=f"DoIP activation_type 0x{activation_type:X} must be a single byte.",
            hint="activation_type is 8-bit (0x00-0xFF); 0x00 is the default.",
        )

    timeout = DEFAULT_TIMEOUT
    timeout_values = query.get("timeout")
    if timeout_values:
        try:
            timeout = float(timeout_values[0])
        except ValueError as exc:
            raise DoipError(
                code="DOIP_INVALID_TARGET",
                message=f"DoIP timeout {timeout_values[0]!r} is not a number.",
                hint="Pass ?timeout=<seconds> as a positive number.",
            ) from exc
        if timeout <= 0:
            raise DoipError(
                code="DOIP_INVALID_TARGET",
                message="DoIP timeout must be positive.",
                hint="Pass ?timeout=<seconds> greater than zero.",
            )

    return DoipTarget(
        host=host,
        port=port,
        logical_address=logical_address,
        source_address=source_address,
        activation_type=activation_type,
        timeout=timeout,
    )


# --- pure codec --------------------------------------------------------------


def encode_message(payload_type: int, payload: bytes) -> bytes:
    """Encode a DoIP message (generic header + payload)."""
    return (
        _HEADER.pack(DOIP_PROTOCOL_VERSION, _INVERSE_VERSION, payload_type, len(payload)) + payload
    )


def decode_message(data: bytes) -> tuple[DoipMessage, int]:
    """Decode one DoIP message from the front of ``data``.

    Returns the message and the offset past it, so a stream of concatenated
    messages can be decoded sequentially.
    """
    if len(data) < _HEADER.size:
        raise DoipError(
            code="DOIP_PROTOCOL_ERROR",
            message="DoIP message is shorter than its 8-byte generic header.",
            hint="Confirm the peer speaks DoIP (ISO 13400-2).",
        )
    version, inverse, payload_type, payload_length = _HEADER.unpack_from(data, 0)
    if inverse != (version ^ 0xFF):
        raise DoipError(
            code="DOIP_PROTOCOL_ERROR",
            message="DoIP header protocol-version / inverse-version mismatch.",
            hint="The stream is not a valid DoIP message; confirm the endpoint.",
        )
    if payload_length > _MAX_PAYLOAD:
        raise DoipError(
            code="DOIP_PROTOCOL_ERROR",
            message=f"DoIP payload length {payload_length} exceeds the supported maximum.",
            hint="The advertised length is implausible; confirm the endpoint.",
        )
    end = _HEADER.size + payload_length
    if end > len(data):
        raise DoipError(
            code="DOIP_PROTOCOL_ERROR",
            message="DoIP message payload is truncated.",
            hint="The peer sent fewer bytes than its header advertised.",
        )
    return DoipMessage(payload_type, bytes(data[_HEADER.size : end])), end


def encode_routing_activation_request(source_address: int, activation_type: int) -> bytes:
    payload = (
        struct.pack(">HB", source_address & 0xFFFF, activation_type & 0xFF) + b"\x00\x00\x00\x00"
    )
    return encode_message(PT_ROUTING_ACTIVATION_REQUEST, payload)


def parse_routing_activation_response(payload: bytes) -> tuple[int, int, int]:
    """Return ``(tester_address, entity_address, response_code)``."""
    if len(payload) < 5:
        raise DoipError(
            code="DOIP_PROTOCOL_ERROR",
            message="DoIP routing activation response is too short.",
            hint="Expected at least 5 bytes of routing-activation payload.",
        )
    tester, entity, code = struct.unpack_from(">HHB", payload, 0)
    return tester, entity, code


def encode_diagnostic_message(source_address: int, target_address: int, user_data: bytes) -> bytes:
    payload = struct.pack(">HH", source_address & 0xFFFF, target_address & 0xFFFF) + user_data
    return encode_message(PT_DIAGNOSTIC_MESSAGE, payload)


def parse_diagnostic_message(payload: bytes) -> tuple[int, int, bytes]:
    """Return ``(source_address, target_address, user_data)``."""
    if len(payload) < 4:
        raise DoipError(
            code="DOIP_PROTOCOL_ERROR",
            message="DoIP diagnostic message is missing its address header.",
            hint="Expected at least 4 bytes of source/target addresses.",
        )
    source, target = struct.unpack_from(">HH", payload, 0)
    return source, target, bytes(payload[4:])


# --- connection --------------------------------------------------------------


@dataclass(slots=True)
class DoipConnection:
    """A thin framed reader/writer over a connected DoIP TCP socket."""

    sock: socket.socket
    _buffer: bytearray = field(default_factory=bytearray)

    def send_raw(self, message: bytes) -> None:
        try:
            self.sock.sendall(message)
        except OSError as exc:
            raise DoipError(
                code="DOIP_CONNECTION_FAILED",
                message=f"DoIP socket write failed: {exc}.",
                hint="The connection dropped; confirm the endpoint is reachable.",
            ) from exc

    def recv_message(self) -> DoipMessage:
        # Buffer bytes until one full DoIP message is available, then return it.
        while True:
            if len(self._buffer) >= _HEADER.size:
                version, inverse, payload_type, payload_length = _HEADER.unpack_from(
                    self._buffer, 0
                )
                if inverse != (version ^ 0xFF):
                    raise DoipError(
                        code="DOIP_PROTOCOL_ERROR",
                        message="DoIP header protocol-version / inverse-version mismatch.",
                        hint="The stream is not a valid DoIP message; confirm the endpoint.",
                    )
                if payload_length > _MAX_PAYLOAD:
                    raise DoipError(
                        code="DOIP_PROTOCOL_ERROR",
                        message=f"DoIP payload length {payload_length} exceeds the supported maximum.",
                        hint="The advertised length is implausible; confirm the endpoint.",
                    )
                end = _HEADER.size + payload_length
                if len(self._buffer) >= end:
                    message = DoipMessage(payload_type, bytes(self._buffer[_HEADER.size : end]))
                    del self._buffer[:end]
                    return message
            self._fill()

    def _fill(self) -> None:
        try:
            chunk = self.sock.recv(4096)
        except TimeoutError as exc:
            raise DoipError(
                code="DOIP_TIMEOUT",
                message="Timed out waiting for a DoIP response.",
                hint="Confirm the endpoint is reachable and responsive; raise ?timeout=<seconds>.",
            ) from exc
        except OSError as exc:
            raise DoipError(
                code="DOIP_CONNECTION_FAILED",
                message=f"DoIP socket read failed: {exc}.",
                hint="The connection dropped mid-exchange; confirm the endpoint.",
            ) from exc
        if not chunk:
            raise DoipError(
                code="DOIP_CONNECTION_FAILED",
                message="DoIP peer closed the connection before a full response.",
                hint="The endpoint hung up; confirm routing activation succeeded.",
            )
        self._buffer.extend(chunk)

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


def _connect(target: DoipTarget) -> socket.socket:
    try:
        sock = socket.create_connection((target.host, target.port), timeout=target.timeout)
    except (TimeoutError, OSError) as exc:
        raise DoipError(
            code="DOIP_CONNECTION_FAILED",
            message=f"Could not connect to DoIP endpoint {target.host}:{target.port}: {exc}.",
            hint="Confirm the host, port, and that a DoIP gateway is listening.",
        ) from exc
    sock.settimeout(target.timeout)
    return sock


def _activate_routing(conn: DoipConnection, target: DoipTarget) -> None:
    conn.send_raw(encode_routing_activation_request(target.source_address, target.activation_type))
    message = conn.recv_message()
    if message.payload_type != PT_ROUTING_ACTIVATION_RESPONSE:
        raise DoipError(
            code="DOIP_PROTOCOL_ERROR",
            message=(
                f"Expected a routing activation response (0x{PT_ROUTING_ACTIVATION_RESPONSE:04X}), "
                f"got payload type 0x{message.payload_type:04X}."
            ),
            hint="Confirm the endpoint is a DoIP gateway.",
        )
    _tester, _entity, code = parse_routing_activation_response(message.payload)
    if code != ROUTING_ACTIVATION_SUCCESS:
        name = ROUTING_ACTIVATION_RESPONSE_CODES.get(code, f"ResponseCode0x{code:02X}")
        raise DoipError(
            code="DOIP_ROUTING_ACTIVATION_DENIED",
            message=f"DoIP routing activation was denied: {name} (0x{code:02X}).",
            hint="Check the tester source_address and activation_type for this gateway.",
        )


def _diagnostic_exchange(conn: DoipConnection, target: DoipTarget, request: bytes) -> bytes | None:
    """Send one UDS request and return the UDS response bytes, or ``None``.

    ``None`` means the gateway positively acknowledged the request but the ECU
    sent no diagnostic response (e.g. a silent probe). A DoIP negative
    acknowledgement raises :class:`DoipError`.
    """
    conn.send_raw(encode_diagnostic_message(target.source_address, target.logical_address, request))
    while True:
        message = conn.recv_message()
        if message.payload_type == PT_DIAGNOSTIC_MESSAGE_ACK:
            # Positive transport ack; the UDS response follows in its own message.
            continue
        if message.payload_type == PT_DIAGNOSTIC_MESSAGE_NACK:
            code = message.payload[4] if len(message.payload) >= 5 else 0
            name = DIAGNOSTIC_NACK_CODES.get(code, f"NackCode0x{code:02X}")
            raise DoipError(
                code="DOIP_DIAGNOSTIC_NACK",
                message=f"DoIP gateway rejected the diagnostic message: {name} (0x{code:02X}).",
                hint="Confirm the target logical address is reachable behind this gateway.",
            )
        if message.payload_type == PT_DIAGNOSTIC_MESSAGE:
            _source, _target, user_data = parse_diagnostic_message(message.payload)
            return user_data or None
        if message.payload_type == PT_GENERIC_NACK:
            raise DoipError(
                code="DOIP_PROTOCOL_ERROR",
                message="DoIP gateway returned a generic negative acknowledgement.",
                hint="The gateway could not process the message; confirm protocol version.",
            )
        # Ignore unrelated message types (e.g. alive-check) and keep reading.


def _run_sequence(
    target: DoipTarget,
    requests: tuple[bytes, ...],
    *,
    source: str,
    connect=_connect,
    skip_on_timeout: bool = False,
) -> list[UdsTransactionEvent]:
    sock = connect(target)
    conn = DoipConnection(sock)
    events: list[UdsTransactionEvent] = []
    try:
        _activate_routing(conn, target)
        for request in requests:
            try:
                response = _diagnostic_exchange(conn, target, request)
            except DoipError as exc:
                # `uds scan` treats a per-probe timeout as a silent ECU and keeps
                # probing; `uds trace` is a deliberate exchange, so a timeout is a
                # real DOIP_TIMEOUT error rather than an empty successful trace.
                if exc.code == "DOIP_TIMEOUT" and skip_on_timeout:
                    continue
                raise
            if not response:
                continue
            service = request[0]
            events.append(
                UdsTransactionEvent(
                    request_id=target.source_address,
                    response_id=target.logical_address,
                    service=service,
                    service_name=uds_service_name(service),
                    request_data=request,
                    response_data=response,
                    complete=True,
                    ecu_address=target.logical_address,
                    source=source,
                )
            )
    finally:
        conn.close()
    return enrich_uds_transactions(events)


def doip_scan_transactions(
    target: DoipTarget, *, source: str = "transport.doip.scan", connect=_connect
) -> list[UdsTransactionEvent]:
    """Probe default / programming / extended sessions on a DoIP ECU."""
    return _run_sequence(
        target, _SCAN_REQUESTS, source=source, connect=connect, skip_on_timeout=True
    )


def doip_trace_transactions(
    target: DoipTarget, *, source: str = "transport.doip.trace", connect=_connect
) -> list[UdsTransactionEvent]:
    """Run a short diagnostic-session + tester-present exchange over DoIP."""
    return _run_sequence(target, _TRACE_REQUESTS, source=source, connect=connect)


def doip_scan_events(target: DoipTarget, *, connect=_connect) -> list[dict[str, object]]:
    return serialize_events(
        [event.to_event() for event in doip_scan_transactions(target, connect=connect)]
    )


def doip_trace_events(target: DoipTarget, *, connect=_connect) -> list[dict[str, object]]:
    return serialize_events(
        [event.to_event() for event in doip_trace_transactions(target, connect=connect)]
    )
