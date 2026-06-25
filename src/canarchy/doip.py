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

import contextlib
import socket
import struct
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlsplit

from canarchy.models import UdsTransactionEvent, serialize_events
from canarchy.uds import (
    UDS_NEGATIVE_RESPONSE_CODES,
    UDS_SERVICE_CATALOG,
    enrich_uds_transactions,
    uds_service_name,
)

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


# --- vehicle identification (UDP discovery) ----------------------------------

PT_VEHICLE_IDENTIFICATION_REQUEST = 0x0001
# A vehicle-identification response and an unsolicited announcement share a type.
PT_VEHICLE_IDENTIFICATION_RESPONSE = 0x0004

# UDS service ids whose absence (or a not-supported NRC) means "unsupported".
_SERVICE_ABSENT_NRCS = frozenset({0x11, 0x7F})


@dataclass(slots=True, frozen=True)
class DoipEntity:
    """A DoIP entity learned from a vehicle-identification response."""

    host: str
    logical_address: int
    vin: str | None
    eid: str
    gid: str
    further_action: int

    def to_record(self) -> dict[str, object]:
        return {
            "host": self.host,
            "logical_address": self.logical_address,
            "vin": self.vin,
            "eid": self.eid,
            "gid": self.gid,
            "further_action": self.further_action,
        }


def encode_vehicle_identification_request() -> bytes:
    return encode_message(PT_VEHICLE_IDENTIFICATION_REQUEST, b"")


def parse_vehicle_identification_response(host: str, payload: bytes) -> DoipEntity:
    """Parse a VehicleIdentificationResponse / AnnouncementMessage payload."""
    if len(payload) < 32:
        raise DoipError(
            code="DOIP_PROTOCOL_ERROR",
            message="DoIP vehicle-identification response is too short.",
            hint="Expected at least 32 bytes (VIN, address, EID, GID, further action).",
        )
    vin_bytes = payload[0:17]
    logical_address = int.from_bytes(payload[17:19], "big")
    eid = payload[19:25]
    gid = payload[25:31]
    further_action = payload[31]
    vin = vin_bytes.decode("ascii", "replace").strip("\x00").strip() or None
    return DoipEntity(
        host=host,
        logical_address=logical_address,
        vin=vin,
        eid=eid.hex(),
        gid=gid.hex(),
        further_action=further_action,
    )


# A discovery sender sends the request and returns observed (host, type, payload).
IdentificationSender = Callable[[str, int, float], Iterable[tuple[str, int, bytes]]]


def _udp_identification_sender(
    host: str, port: int, timeout: float
) -> list[tuple[str, int, bytes]]:
    request = encode_vehicle_identification_request()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    with contextlib.suppress(OSError):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(timeout)
    results: list[tuple[str, int, bytes]] = []
    try:
        try:
            sock.sendto(request, (host, port))
        except OSError as exc:
            raise DoipError(
                code="DOIP_CONNECTION_FAILED",
                message=f"Could not send DoIP discovery request to {host}:{port}: {exc}.",
                hint="Confirm the host/broadcast address is reachable on this network.",
            ) from exc
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                data, addr = sock.recvfrom(4096)
            except (TimeoutError, OSError):
                break
            with contextlib.suppress(DoipError):
                message, _ = decode_message(data)
                results.append((addr[0], message.payload_type, message.payload))
    finally:
        sock.close()
    return results


def discover_entities(
    host: str = "255.255.255.255",
    *,
    port: int = DOIP_DEFAULT_PORT,
    timeout: float = DEFAULT_TIMEOUT,
    sender: IdentificationSender | None = None,
) -> list[DoipEntity]:
    """Broadcast a DoIP vehicle-identification request and collect responders."""
    if timeout <= 0:
        raise DoipError(
            code="DOIP_INVALID_TARGET",
            message="DoIP discovery timeout must be positive.",
            hint="Pass --timeout greater than zero.",
        )
    sender = sender or _udp_identification_sender
    entities: list[DoipEntity] = []
    for src_host, payload_type, payload in sender(host, port, timeout):
        if payload_type != PT_VEHICLE_IDENTIFICATION_RESPONSE:
            continue
        entities.append(parse_vehicle_identification_response(src_host, payload))
    return entities


# --- active diagnostic workflows over a DoIP TCP session ---------------------


def _collect_exchanges(
    target: DoipTarget,
    requests: Sequence[bytes],
    *,
    connect=_connect,
) -> list[tuple[bytes, bytes | None]]:
    """Activate routing, then run each UDS request, mapping a timeout to None."""
    sock = connect(target)
    conn = DoipConnection(sock)
    results: list[tuple[bytes, bytes | None]] = []
    try:
        _activate_routing(conn, target)
        for request in requests:
            try:
                response = _diagnostic_exchange(conn, target, request)
            except DoipError as exc:
                if exc.code == "DOIP_TIMEOUT":
                    response = None
                else:
                    raise
            results.append((bytes(request), response))
    finally:
        conn.close()
    return results


def _exchange_status(response: bytes | None) -> tuple[str, int | None, str | None]:
    if not response:
        return "no_response", None, None
    if response[:1] == b"\x7f" and len(response) >= 3:
        code = response[2]
        return "negative", code, UDS_NEGATIVE_RESPONSE_CODES.get(code, f"ResponseCode0x{code:02X}")
    return "positive", None, None


def _exchange_record(request: bytes, response: bytes | None) -> dict[str, object]:
    status, code, name = _exchange_status(response)
    return {
        "request": request.hex(),
        "response": response.hex() if response is not None else None,
        "status": status,
        "negative_response_code": code,
        "negative_response_name": name,
    }


def _exchange_event(
    target: DoipTarget, request: bytes, response: bytes, *, source: str
) -> UdsTransactionEvent:
    service = request[0]
    return UdsTransactionEvent(
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


def _events_for(
    target: DoipTarget, results: Iterable[tuple[bytes, bytes | None]], *, source: str
) -> list[UdsTransactionEvent]:
    events = [
        _exchange_event(target, request, response, source=source)
        for request, response in results
        if response is not None
    ]
    return enrich_uds_transactions(events)


def doip_services(
    target: DoipTarget,
    *,
    services: Sequence[int] | None = None,
    connect=_connect,
    source: str = "transport.doip.services",
) -> tuple[list[dict[str, object]], list[UdsTransactionEvent]]:
    """Probe each candidate UDS service over DoIP and classify support."""
    service_ids = (
        list(services) if services is not None else [s.service for s in UDS_SERVICE_CATALOG]
    )
    results = _collect_exchanges(target, [bytes([sid]) for sid in service_ids], connect=connect)
    records: list[dict[str, object]] = []
    for (request, response), sid in zip(results, service_ids):
        status, code, _name = _exchange_status(response)
        supported = response is not None and (
            status == "positive" or code not in _SERVICE_ABSENT_NRCS
        )
        records.append(
            {
                "service": sid,
                "name": uds_service_name(sid),
                "supported": supported,
                **_exchange_record(request, response),
            }
        )
    return records, _events_for(target, results, source=source)


def doip_ecu_reset(
    target: DoipTarget,
    *,
    reset_type: int = 0x01,
    connect=_connect,
    source: str = "transport.doip.ecu-reset",
) -> tuple[dict[str, object], list[UdsTransactionEvent]]:
    results = _collect_exchanges(target, [bytes([0x11, reset_type & 0xFF])], connect=connect)
    request, response = results[0]
    return _exchange_record(request, response), _events_for(target, results, source=source)


def doip_tester_present(
    target: DoipTarget,
    *,
    suppress_response: bool = False,
    connect=_connect,
    source: str = "transport.doip.tester-present",
) -> tuple[dict[str, object], list[UdsTransactionEvent]]:
    subfunction = 0x80 if suppress_response else 0x00
    results = _collect_exchanges(target, [bytes([0x3E, subfunction])], connect=connect)
    request, response = results[0]
    return _exchange_record(request, response), _events_for(target, results, source=source)


def doip_security_seed(
    target: DoipTarget,
    *,
    level: int = 0x01,
    session: int | None = None,
    count: int = 1,
    connect=_connect,
    source: str = "transport.doip.security-seed",
) -> tuple[dict[str, object], list[UdsTransactionEvent]]:
    requests: list[bytes] = []
    if session is not None:
        requests.append(bytes([0x10, session & 0xFF]))
    requests.extend(bytes([0x27, level & 0xFF]) for _ in range(max(count, 1)))
    results = _collect_exchanges(target, requests, connect=connect)
    seeds: list[dict[str, object]] = []
    session_record: dict[str, object] | None = None
    index = 0
    for request, response in results:
        if request[0] == 0x10:
            session_record = _exchange_record(request, response)
            continue
        status, _code, _name = _exchange_status(response)
        seed = (
            response[2:].hex() if status == "positive" and response and len(response) >= 2 else None
        )
        seeds.append({"index": index, "seed": seed, **_exchange_record(request, response)})
        index += 1
    distinct = len({entry["seed"] for entry in seeds if entry["seed"] is not None})
    data: dict[str, object] = {
        "level": level,
        "session": session,
        "requested": max(count, 1),
        "collected": sum(1 for entry in seeds if entry["seed"] is not None),
        "distinct_seeds": distinct,
        "session_response": session_record,
        "seeds": seeds,
    }
    return data, _events_for(target, results, source=source)


def doip_dump_dids(
    target: DoipTarget,
    *,
    did_start: int,
    did_end: int,
    limit: int = 256,
    connect=_connect,
    source: str = "transport.doip.dump-dids",
) -> tuple[list[dict[str, object]], list[UdsTransactionEvent]]:
    dids = list(range(did_start, did_end + 1))[: max(limit, 1)]
    requests = [bytes([0x22, (did >> 8) & 0xFF, did & 0xFF]) for did in dids]
    results = _collect_exchanges(target, requests, connect=connect)
    records: list[dict[str, object]] = []
    for (request, response), did in zip(results, dids):
        status, _code, _name = _exchange_status(response)
        value = None
        if (
            status == "positive"
            and response
            and len(response) >= 3
            and response[1:3] == request[1:3]
        ):
            value = response[3:].hex()
        records.append(
            {
                "did": did,
                "value": value,
                "present": value is not None,
                **_exchange_record(request, response),
            }
        )
    return records, _events_for(target, results, source=source)
