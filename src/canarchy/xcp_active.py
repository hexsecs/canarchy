"""Active XCP-on-CAN workflows: slave info and bounded memory upload (dump).

Passive capture parsing lives in :mod:`canarchy.xcp`; this module adds the
*active* master workflows that transmit Command Transfer Objects (CTOs) and read
the slave's responses: ``info`` (CONNECT plus the optional GET_STATUS /
GET_COMM_MODE_INFO / GET_ID capability queries) and ``dump`` (CONNECT, then
SET_MTA + UPLOAD — or SHORT_UPLOAD — over a bounded, chunked address range).
These mirror CaringCaribou's XCP info/dump modes while preserving CANarchy's
structured-event envelope and active-transmit safety model.

Every workflow is written against a small :class:`XcpClient` seam — "send one
CTO, observe at most one response CTO" — so the workflow logic is pure and
unit-testable with a fake client, and :class:`TransportXcpClient` is the only
piece that touches live hardware. XCP-on-CAN CTOs are single CAN frames (no
ISO-TP framing), so no reassembly is needed.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from canarchy.models import CanFrame, XcpTransactionEvent
from canarchy.xcp import (
    PID_ERR,
    PID_RES,
    XCP_ERROR_CODES,
    parse_connect_response,
    xcp_command_name,
)

_CAN_SFF_MAX = 0x7FF

# Command codes used by the active workflows.
CMD_CONNECT = 0xFF
CMD_GET_STATUS = 0xFD
CMD_GET_COMM_MODE_INFO = 0xFB
CMD_GET_ID = 0xFA
CMD_SET_MTA = 0xF6
CMD_UPLOAD = 0xF5
CMD_SHORT_UPLOAD = 0xF4

CONNECT_MODE_NORMAL = 0x00

# "Command unknown" — the slave does not implement an optional command.
ERR_CMD_UNKNOWN = 0x20

# Bounds so a stray invocation cannot run away on a live bus.
MAX_DUMP_BYTES = 0x10000
DEFAULT_DUMP_CHUNK = 4
# A classic-CAN CTO carries at most 7 data bytes after the 1-byte PID.
MAX_CTO_DATA = 7
DEFAULT_PER_REQUEST_TIMEOUT = 0.2


class XcpActiveError(Exception):
    """Raised for operator-input / bounds / protocol problems."""

    def __init__(self, code: str, message: str, hint: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint


# --- response model ----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class XcpResponse:
    """One command CTO and the single response CTO it elicited (if any)."""

    request_id: int
    response_id: int
    command: int
    request: bytes
    response: bytes | None
    elapsed: float | None = None

    @property
    def responded(self) -> bool:
        return self.response is not None and len(self.response) > 0

    @property
    def positive(self) -> bool:
        return self.responded and self.response[0] == PID_RES

    @property
    def error(self) -> bool:
        return self.responded and self.response[0] == PID_ERR

    @property
    def error_code(self) -> int | None:
        if self.error and len(self.response) >= 2:
            return self.response[1]
        return None

    @property
    def error_name(self) -> str | None:
        code = self.error_code
        if code is None:
            return None
        return XCP_ERROR_CODES.get(code, f"ERR0x{code:02X}")

    @property
    def unsupported(self) -> bool:
        """True when the slave answered "command unknown" (optional command)."""
        return self.error_code == ERR_CMD_UNKNOWN

    @property
    def status(self) -> str:
        if not self.responded:
            return "no_response"
        if self.positive:
            return "positive"
        if self.unsupported:
            return "unsupported"
        if self.error:
            return "error"
        return "other"

    def to_record(self) -> dict[str, object]:
        return {
            "command": self.command,
            "command_name": xcp_command_name(self.command),
            "request": self.request.hex(),
            "response": self.response.hex() if self.response is not None else None,
            "status": self.status,
            "error_code": self.error_code,
            "error_name": self.error_name,
            "elapsed_ms": round(self.elapsed * 1000, 3) if self.elapsed is not None else None,
        }

    def to_event(self, *, source: str) -> XcpTransactionEvent | None:
        if not self.responded:
            return None
        connect_info = (
            parse_connect_response(self.response)
            if self.command == CMD_CONNECT and self.positive
            else None
        )
        return XcpTransactionEvent(
            request_id=self.request_id,
            response_id=self.response_id,
            command=self.command,
            command_name=xcp_command_name(self.command),
            request_data=self.request,
            response_data=self.response,
            positive=self.positive,
            error_code=self.error_code,
            error_name=self.error_name,
            connect_info=connect_info,
            source=source,
        )


# --- client seam -------------------------------------------------------------


class XcpClient:
    """Send one XCP CTO and observe at most one response CTO."""

    request_id: int
    response_id: int

    def command(
        self, payload: bytes, *, timeout: float | None = None
    ) -> XcpResponse:  # pragma: no cover - interface
        raise NotImplementedError


def command_frame(request_id: int, payload: bytes) -> CanFrame:
    """Build the raw XCP command CTO frame (no ISO-TP framing)."""
    if not payload:
        raise XcpActiveError(
            code="XCP_EMPTY_COMMAND",
            message="An XCP command needs at least a command code byte.",
            hint="Pass a non-empty command payload.",
        )
    if len(payload) > 8:
        raise XcpActiveError(
            code="XCP_COMMAND_TOO_LONG",
            message=f"XCP CTO of {len(payload)} bytes exceeds the 8-byte CAN frame limit.",
            hint="XCP-on-CAN CTOs must fit one classic CAN frame.",
        )
    return CanFrame(
        arbitration_id=request_id,
        data=bytes(payload),
        is_extended_id=request_id > _CAN_SFF_MAX,
    )


class SilentXcpClient(XcpClient):
    """Records commands but never observes a response (used off a live bus)."""

    def __init__(self, request_id: int, response_id: int) -> None:
        self.request_id = request_id
        self.response_id = response_id
        self.calls: list[bytes] = []

    def command(self, payload: bytes, *, timeout: float | None = None) -> XcpResponse:
        self.calls.append(bytes(payload))
        return XcpResponse(
            request_id=self.request_id,
            response_id=self.response_id,
            command=payload[0] if payload else 0,
            request=bytes(payload),
            response=None,
        )


@dataclass(slots=True)
class TransportXcpClient(XcpClient):
    transport: object
    interface: str
    request_id: int
    response_id: int

    def command(self, payload: bytes, *, timeout: float | None = None) -> XcpResponse:
        frame = command_frame(self.request_id, payload)
        started = time.perf_counter()
        frames = self.transport.transaction(self.interface, frame, timeout=timeout)
        elapsed = time.perf_counter() - started
        response = _select_response(list(frames), self.response_id)
        return XcpResponse(
            request_id=self.request_id,
            response_id=self.response_id,
            command=payload[0] if payload else 0,
            request=bytes(payload),
            response=response,
            elapsed=elapsed,
        )


def _select_response(frames: list[CanFrame], response_id: int) -> bytes | None:
    for frame in frames:
        if frame.arbitration_id == response_id and frame.data:
            return bytes(frame.data)
    return None


# --- response parsers --------------------------------------------------------


def parse_get_status(data: bytes) -> dict[str, object]:
    info: dict[str, object] = {}
    if len(data) >= 2:
        info["session_status"] = data[1]
    if len(data) >= 3:
        info["resource_protection"] = data[2]
    return info


def parse_get_comm_mode_info(data: bytes) -> dict[str, object]:
    info: dict[str, object] = {}
    if len(data) >= 3:
        info["comm_mode_optional"] = data[2]
    if len(data) >= 5:
        info["max_bs"] = data[4]
    if len(data) >= 6:
        info["min_st"] = data[5]
    if len(data) >= 7:
        info["queue_size"] = data[6]
    if len(data) >= 8:
        info["driver_version"] = data[7]
    return info


def parse_get_id(data: bytes, *, byte_order: str = "little") -> dict[str, object]:
    info: dict[str, object] = {}
    if len(data) >= 2:
        info["mode"] = data[1]
    if len(data) >= 8:
        info["length"] = int.from_bytes(data[4:8], byte_order)
    return info


# --- info workflow -----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class XcpInfo:
    connect: XcpResponse
    connect_info: dict[str, object]
    status: XcpResponse | None = None
    comm_mode: XcpResponse | None = None
    identification: XcpResponse | None = None

    def exchanges(self) -> list[XcpResponse]:
        return [
            exchange
            for exchange in (self.connect, self.status, self.comm_mode, self.identification)
            if exchange is not None
        ]


def connect(client: XcpClient, *, timeout: float = DEFAULT_PER_REQUEST_TIMEOUT) -> XcpResponse:
    return client.command(bytes([CMD_CONNECT, CONNECT_MODE_NORMAL]), timeout=timeout)


def _require_connected(response: XcpResponse) -> dict[str, object]:
    if not response.responded:
        raise XcpActiveError(
            code="XCP_NO_RESPONSE",
            message="No response to the XCP CONNECT command.",
            hint="Confirm the request/response CAN ids and that an XCP slave is present.",
        )
    if not response.positive:
        raise XcpActiveError(
            code="XCP_ERROR_RESPONSE",
            message=(
                f"XCP CONNECT was rejected: {response.error_name or 'error'} "
                f"(0x{(response.error_code or 0):02X})."
            ),
            hint="The slave refused CONNECT; check protection state and ids.",
        )
    return parse_connect_response(response.response)


def info(client: XcpClient, *, timeout: float = DEFAULT_PER_REQUEST_TIMEOUT) -> XcpInfo:
    """CONNECT, then query the optional GET_STATUS / GET_COMM_MODE_INFO / GET_ID."""
    connect_response = connect(client, timeout=timeout)
    connect_info = _require_connected(connect_response)
    status = client.command(bytes([CMD_GET_STATUS]), timeout=timeout)
    comm_mode = client.command(bytes([CMD_GET_COMM_MODE_INFO]), timeout=timeout)
    identification = client.command(bytes([CMD_GET_ID, 0x01]), timeout=timeout)
    return XcpInfo(
        connect=connect_response,
        connect_info=connect_info,
        status=status,
        comm_mode=comm_mode,
        identification=identification,
    )


# --- dump workflow -----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DumpChunk:
    address: int
    size: int
    data: bytes | None
    exchanges: list[XcpResponse] = field(default_factory=list)

    def to_record(self) -> dict[str, object]:
        return {
            "address": self.address,
            "size": self.size,
            "data": self.data.hex() if self.data is not None else None,
            "status": "complete" if self.data is not None else "incomplete",
        }


def plan_dump_chunks(address: int, total_size: int, chunk_size: int) -> list[tuple[int, int]]:
    """Split ``[address, address+total_size)`` into ``(address, size)`` chunks."""
    if address < 0:
        raise XcpActiveError(
            code="XCP_INVALID_ADDRESS",
            message=f"Dump address {address} must be non-negative.",
            hint="Pass --address as a non-negative integer.",
        )
    if total_size < 1:
        raise XcpActiveError(
            code="XCP_INVALID_SIZE",
            message=f"Dump size {total_size} must be at least 1 byte.",
            hint="Pass --size with a positive byte count.",
        )
    if total_size > MAX_DUMP_BYTES:
        raise XcpActiveError(
            code="XCP_DUMP_TOO_LARGE",
            message=f"Dump size {total_size} exceeds the bounded maximum of {MAX_DUMP_BYTES} bytes.",
            hint=f"Upload at most {MAX_DUMP_BYTES} bytes per invocation.",
        )
    if address + total_size - 1 > 0xFFFFFFFF:
        raise XcpActiveError(
            code="XCP_ADDRESS_OUT_OF_RANGE",
            message=(
                f"Dump range ends at 0x{address + total_size - 1:X}, beyond the 32-bit XCP "
                "address space (0xFFFFFFFF)."
            ),
            hint="Lower --address or --size so the range stays within 32 bits.",
        )
    if not 1 <= chunk_size <= MAX_CTO_DATA:
        raise XcpActiveError(
            code="XCP_INVALID_CHUNK_SIZE",
            message=f"Chunk size {chunk_size} must be between 1 and {MAX_CTO_DATA}.",
            hint=f"A single CTO carries at most {MAX_CTO_DATA} data bytes.",
        )
    chunks: list[tuple[int, int]] = []
    offset = 0
    while offset < total_size:
        size = min(chunk_size, total_size - offset)
        chunks.append((address + offset, size))
        offset += size
    return chunks


def set_mta_request(
    address: int, *, address_extension: int = 0, byte_order: str = "little"
) -> bytes:
    return bytes([CMD_SET_MTA, 0x00, 0x00, address_extension & 0xFF]) + address.to_bytes(
        4, byte_order
    )


def short_upload_request(
    address: int, size: int, *, address_extension: int = 0, byte_order: str = "little"
) -> bytes:
    return bytes(
        [CMD_SHORT_UPLOAD, size & 0xFF, 0x00, address_extension & 0xFF]
    ) + address.to_bytes(4, byte_order)


def dump(
    client: XcpClient,
    *,
    address: int,
    size: int,
    chunk_size: int = DEFAULT_DUMP_CHUNK,
    address_extension: int = 0,
    short_upload: bool = False,
    timeout: float = DEFAULT_PER_REQUEST_TIMEOUT,
) -> tuple[XcpResponse, list[DumpChunk]]:
    """CONNECT, then upload a bounded chunked address range.

    Returns the CONNECT exchange and the per-chunk results. Uploading stops at
    the first chunk that does not return data, leaving the dump incomplete.
    """
    chunks_plan = plan_dump_chunks(address, size, chunk_size)
    connect_response = connect(client, timeout=timeout)
    connect_info = _require_connected(connect_response)
    byte_order = "big" if connect_info.get("byte_order") == "big" else "little"
    max_cto = connect_info.get("max_cto")
    if isinstance(max_cto, int) and max_cto > 0 and chunk_size > max_cto - 1:
        raise XcpActiveError(
            code="XCP_CHUNK_EXCEEDS_MAX_CTO",
            message=(
                f"Chunk size {chunk_size} exceeds the slave's MAX_CTO-1 ({max_cto - 1}) data bytes."
            ),
            hint=f"Lower --chunk-size to at most {max_cto - 1}.",
        )

    results: list[DumpChunk] = []
    for chunk_address, chunk_len in chunks_plan:
        exchanges: list[XcpResponse] = []
        if short_upload:
            response = client.command(
                short_upload_request(
                    chunk_address,
                    chunk_len,
                    address_extension=address_extension,
                    byte_order=byte_order,
                ),
                timeout=timeout,
            )
            exchanges.append(response)
        else:
            mta = client.command(
                set_mta_request(
                    chunk_address, address_extension=address_extension, byte_order=byte_order
                ),
                timeout=timeout,
            )
            exchanges.append(mta)
            if not mta.positive:
                results.append(DumpChunk(chunk_address, chunk_len, None, exchanges))
                break
            response = client.command(bytes([CMD_UPLOAD, chunk_len]), timeout=timeout)
            exchanges.append(response)
        data = response.response[1 : 1 + chunk_len] if response.positive else None
        # A positive response with fewer bytes than requested is a truncated
        # upload, not a complete chunk; treat it as incomplete and stop.
        if data is not None and len(data) < chunk_len:
            data = None
        results.append(DumpChunk(chunk_address, chunk_len, data, exchanges))
        if data is None:
            break
    return connect_response, results
