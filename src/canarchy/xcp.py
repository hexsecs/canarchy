"""XCP (Universal Measurement and Calibration Protocol) helpers, XCP-on-CAN.

XCP is the ASAM master/slave protocol used for ECU calibration and measurement.
The master sends Command Transfer Objects (CTOs) on a request CAN id; the slave
answers on a response CAN id, and streams measured values as Data Transfer
Objects (DTOs). CANarchy speaks enough of the command layer to discover
responders (`scan`), pair command/response transactions from a capture
(`trace`), and surface raw DAQ measurement payloads (`read`) — all through the
existing frame-based transport, with the same structured-event envelope used by
the UDS workflows.

This module is pure: it parses :class:`~canarchy.models.CanFrame` lists into
:class:`~canarchy.models.XcpTransactionEvent` /
:class:`~canarchy.models.XcpMeasurementEvent` objects and builds the single
CONNECT request frame used by an active scan. It opens no live hardware.
"""

from __future__ import annotations

from dataclasses import dataclass

from canarchy.models import CanFrame, XcpMeasurementEvent, XcpTransactionEvent

# Conventional XCP-on-CAN identifiers. Real deployments configure these per
# slave in the A2L; these defaults are overridable on the CLI.
XCP_DEFAULT_REQUEST_ID = 0x3E0
XCP_DEFAULT_RESPONSE_ID = 0x3E1

# Largest standard (11-bit) CAN id; anything above is an extended (29-bit) id.
_CAN_SFF_MAX = 0x7FF

# Response packet identifiers (first byte of a slave CTO response).
PID_RES = 0xFF  # positive response
PID_ERR = 0xFE  # error
PID_EV = 0xFD  # event
PID_SERV = 0xFC  # service request

# The CONNECT command and its "normal" mode byte.
CMD_CONNECT = 0xFF
CONNECT_MODE_NORMAL = 0x00

# CONNECT response resource bit flags.
_RESOURCE_FLAGS: tuple[tuple[int, str], ...] = (
    (0x01, "cal_pag"),
    (0x04, "daq"),
    (0x08, "stim"),
    (0x10, "pgm"),
)


@dataclass(slots=True, frozen=True)
class XcpCommand:
    code: int
    name: str
    category: str


# Standard XCP command codes (ASAM MCD-1 XCP). Not exhaustive, but covers the
# standard command set plus the common DAQ / calibration / programming verbs.
XCP_COMMAND_CATALOG: tuple[XcpCommand, ...] = (
    XcpCommand(0xFF, "CONNECT", "standard"),
    XcpCommand(0xFE, "DISCONNECT", "standard"),
    XcpCommand(0xFD, "GET_STATUS", "standard"),
    XcpCommand(0xFC, "SYNCH", "standard"),
    XcpCommand(0xFB, "GET_COMM_MODE_INFO", "standard"),
    XcpCommand(0xFA, "GET_ID", "standard"),
    XcpCommand(0xF9, "SET_REQUEST", "standard"),
    XcpCommand(0xF8, "GET_SEED", "standard"),
    XcpCommand(0xF7, "UNLOCK", "standard"),
    XcpCommand(0xF6, "SET_MTA", "standard"),
    XcpCommand(0xF5, "UPLOAD", "standard"),
    XcpCommand(0xF4, "SHORT_UPLOAD", "standard"),
    XcpCommand(0xF3, "BUILD_CHECKSUM", "standard"),
    XcpCommand(0xF2, "TRANSPORT_LAYER_CMD", "standard"),
    XcpCommand(0xF1, "USER_CMD", "standard"),
    XcpCommand(0xF0, "DOWNLOAD", "calibration"),
    XcpCommand(0xEF, "DOWNLOAD_NEXT", "calibration"),
    XcpCommand(0xEE, "DOWNLOAD_MAX", "calibration"),
    XcpCommand(0xED, "SHORT_DOWNLOAD", "calibration"),
    XcpCommand(0xEC, "MODIFY_BITS", "calibration"),
    XcpCommand(0xEB, "SET_CAL_PAGE", "calibration"),
    XcpCommand(0xEA, "GET_CAL_PAGE", "calibration"),
    XcpCommand(0xE9, "GET_PAG_PROCESSOR_INFO", "calibration"),
    XcpCommand(0xE8, "GET_SEGMENT_INFO", "calibration"),
    XcpCommand(0xE7, "GET_PAGE_INFO", "calibration"),
    XcpCommand(0xE6, "SET_SEGMENT_MODE", "calibration"),
    XcpCommand(0xE5, "GET_SEGMENT_MODE", "calibration"),
    XcpCommand(0xE4, "COPY_CAL_PAGE", "calibration"),
    XcpCommand(0xE3, "CLEAR_DAQ_LIST", "daq"),
    XcpCommand(0xE2, "SET_DAQ_PTR", "daq"),
    XcpCommand(0xE1, "WRITE_DAQ", "daq"),
    XcpCommand(0xE0, "SET_DAQ_LIST_MODE", "daq"),
    XcpCommand(0xDF, "GET_DAQ_LIST_MODE", "daq"),
    XcpCommand(0xDE, "START_STOP_DAQ_LIST", "daq"),
    XcpCommand(0xDD, "START_STOP_SYNCH", "daq"),
    XcpCommand(0xDC, "GET_DAQ_CLOCK", "daq"),
    XcpCommand(0xDB, "READ_DAQ", "daq"),
    XcpCommand(0xDA, "GET_DAQ_PROCESSOR_INFO", "daq"),
    XcpCommand(0xD9, "GET_DAQ_RESOLUTION_INFO", "daq"),
    XcpCommand(0xD8, "GET_DAQ_LIST_INFO", "daq"),
    XcpCommand(0xD7, "GET_DAQ_EVENT_INFO", "daq"),
    XcpCommand(0xD6, "FREE_DAQ", "daq"),
    XcpCommand(0xD5, "ALLOC_DAQ", "daq"),
    XcpCommand(0xD4, "ALLOC_ODT", "daq"),
    XcpCommand(0xD3, "ALLOC_ODT_ENTRY", "daq"),
    XcpCommand(0xD2, "PROGRAM_START", "programming"),
    XcpCommand(0xD1, "PROGRAM_CLEAR", "programming"),
    XcpCommand(0xD0, "PROGRAM", "programming"),
    XcpCommand(0xCF, "PROGRAM_RESET", "programming"),
    XcpCommand(0xCE, "GET_PGM_PROCESSOR_INFO", "programming"),
    XcpCommand(0xCD, "GET_SECTOR_INFO", "programming"),
    XcpCommand(0xCC, "PROGRAM_PREPARE", "programming"),
    XcpCommand(0xCB, "PROGRAM_FORMAT", "programming"),
    XcpCommand(0xCA, "PROGRAM_NEXT", "programming"),
    XcpCommand(0xC9, "PROGRAM_MAX", "programming"),
    XcpCommand(0xC8, "PROGRAM_VERIFY", "programming"),
)

_COMMAND_BY_CODE: dict[int, XcpCommand] = {cmd.code: cmd for cmd in XCP_COMMAND_CATALOG}

XCP_ERROR_CODES: dict[int, str] = {
    0x00: "ERR_CMD_SYNCH",
    0x10: "ERR_CMD_BUSY",
    0x11: "ERR_DAQ_ACTIVE",
    0x12: "ERR_PGM_ACTIVE",
    0x20: "ERR_CMD_UNKNOWN",
    0x21: "ERR_CMD_SYNTAX",
    0x22: "ERR_OUT_OF_RANGE",
    0x23: "ERR_WRITE_PROTECTED",
    0x24: "ERR_ACCESS_DENIED",
    0x25: "ERR_ACCESS_LOCKED",
    0x26: "ERR_PAGE_NOT_VALID",
    0x27: "ERR_MODE_NOT_VALID",
    0x28: "ERR_SEGMENT_NOT_VALID",
    0x29: "ERR_SEQUENCE",
    0x2A: "ERR_DAQ_CONFIG",
    0x30: "ERR_MEMORY_OVERFLOW",
    0x31: "ERR_GENERIC",
    0x32: "ERR_VERIFY",
    0x33: "ERR_RESOURCE_TEMPORARY_NOT_ACCESSIBLE",
}


def xcp_command_name(code: int) -> str:
    """Return the catalog name for an XCP command code, or a hex fallback."""
    command = _COMMAND_BY_CODE.get(code)
    return command.name if command else f"CMD0x{code:02X}"


def xcp_commands_payload() -> list[dict[str, object]]:
    return [
        {"category": cmd.category, "code": cmd.code, "name": cmd.name}
        for cmd in XCP_COMMAND_CATALOG
    ]


def connect_request_frame(
    interface: str | None = None, request_id: int = XCP_DEFAULT_REQUEST_ID
) -> CanFrame:
    """The XCP CONNECT command frame an active scan transmits."""
    return CanFrame(
        arbitration_id=request_id,
        data=bytes([CMD_CONNECT, CONNECT_MODE_NORMAL]),
        interface=interface,
        is_extended_id=request_id > _CAN_SFF_MAX,
    )


def parse_connect_response(data: bytes) -> dict[str, object]:
    """Parse a CONNECT positive response (first byte 0xFF) into a fields dict."""
    info: dict[str, object] = {}
    if len(data) >= 2:
        resource = data[1]
        info["resource"] = resource
        info["resources"] = [name for bit, name in _RESOURCE_FLAGS if resource & bit]
    if len(data) >= 3:
        comm_mode_basic = data[2]
        info["comm_mode_basic"] = comm_mode_basic
        # Bit 0 selects byte order for multi-byte response fields.
        info["byte_order"] = "big" if comm_mode_basic & 0x01 else "little"
    if len(data) >= 4:
        info["max_cto"] = data[3]
    if len(data) >= 6:
        byte_order = "big" if info.get("byte_order") == "big" else "little"
        info["max_dto"] = int.from_bytes(data[4:6], byte_order)
    if len(data) >= 7:
        info["protocol_layer_version"] = data[6]
    if len(data) >= 8:
        info["transport_layer_version"] = data[7]
    return info


def _response_status(data: bytes) -> tuple[bool, int | None, str | None]:
    """Return ``(positive, error_code, error_name)`` for a response payload."""
    if not data:
        return False, None, None
    if data[0] == PID_RES:
        return True, None, None
    if data[0] == PID_ERR:
        error_code = data[1] if len(data) >= 2 else None
        error_name = (
            XCP_ERROR_CODES.get(error_code, f"ERR0x{error_code:02X}")
            if error_code is not None
            else None
        )
        return False, error_code, error_name
    return False, None, None


def _transaction_from(
    request: CanFrame,
    response: CanFrame,
    *,
    source: str,
) -> XcpTransactionEvent:
    command = request.data[0]
    positive, error_code, error_name = _response_status(response.data)
    connect_info = (
        parse_connect_response(response.data) if command == CMD_CONNECT and positive else None
    )
    return XcpTransactionEvent(
        request_id=request.arbitration_id,
        response_id=response.arbitration_id,
        command=command,
        command_name=xcp_command_name(command),
        request_data=request.data,
        response_data=response.data,
        positive=positive,
        error_code=error_code,
        error_name=error_name,
        connect_info=connect_info,
        source=source,
        timestamp=response.timestamp,
    )


def xcp_scan_transactions(
    frames: list[CanFrame],
    *,
    request_id: int = XCP_DEFAULT_REQUEST_ID,
    response_id: int = XCP_DEFAULT_RESPONSE_ID,
    source: str,
) -> list[XcpTransactionEvent]:
    """Find CONNECT responders: pair the CONNECT request with each CTO response."""
    ordered = sorted(frames, key=lambda f: f.timestamp or 0.0)
    request = next(
        (
            frame
            for frame in ordered
            if frame.arbitration_id == request_id and frame.data and frame.data[0] == CMD_CONNECT
        ),
        None,
    )
    if request is None:
        request = connect_request_frame(request_id=request_id)

    events: list[XcpTransactionEvent] = []
    for frame in ordered:
        if frame.arbitration_id != response_id or not frame.data:
            continue
        if frame.data[0] not in (PID_RES, PID_ERR):
            continue
        events.append(_transaction_from(request, frame, source=source))
    return events


def xcp_trace_transactions(
    frames: list[CanFrame],
    *,
    request_id: int = XCP_DEFAULT_REQUEST_ID,
    response_id: int = XCP_DEFAULT_RESPONSE_ID,
    source: str,
) -> list[XcpTransactionEvent]:
    """Pair each command CTO on the request id with the next response CTO."""
    ordered = sorted(frames, key=lambda f: f.timestamp or 0.0)
    events: list[XcpTransactionEvent] = []
    pending: CanFrame | None = None
    for frame in ordered:
        if not frame.data:
            continue
        if frame.arbitration_id == request_id:
            pending = frame
            continue
        if frame.arbitration_id == response_id and frame.data[0] in (PID_RES, PID_ERR):
            if pending is None:
                continue
            events.append(_transaction_from(pending, frame, source=source))
            pending = None
    return events


def xcp_read_measurements(
    frames: list[CanFrame],
    *,
    response_id: int = XCP_DEFAULT_RESPONSE_ID,
    source: str,
) -> list[XcpMeasurementEvent]:
    """Surface DAQ DTOs on the response id as raw measurement payloads.

    A DTO's first byte is the packet identifier (ODT number, 0x00-0xFB); CTO
    response/error/event/service frames (PID >= 0xFC) are not measurements and
    are skipped. Signal-level decoding needs the slave's A2L and is out of scope.
    """
    ordered = sorted(frames, key=lambda f: f.timestamp or 0.0)
    events: list[XcpMeasurementEvent] = []
    for frame in ordered:
        if frame.arbitration_id != response_id or not frame.data:
            continue
        pid = frame.data[0]
        if pid >= PID_SERV:  # 0xFC..0xFF are CTO responses, not DAQ DTOs
            continue
        events.append(
            XcpMeasurementEvent(
                response_id=frame.arbitration_id,
                pid=pid,
                data=bytes(frame.data[1:]),
                source=source,
                timestamp=frame.timestamp,
            )
        )
    return events
