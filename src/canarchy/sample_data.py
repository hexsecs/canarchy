"""Explicit sample/reference data providers.

These helpers exist to keep deterministic example protocol data separate from the
transport backend abstraction. The scaffold backend models deterministic transport
behavior, while the sample providers below model reference protocol outputs for
commands that are not yet truly transport-backed.
"""

from __future__ import annotations

from canarchy.models import (
    CanFrame,
    UdsTransactionEvent,
    XcpMeasurementEvent,
    XcpTransactionEvent,
)
from canarchy.xcp import (
    XCP_DEFAULT_REQUEST_ID,
    XCP_DEFAULT_RESPONSE_ID,
    XCP_ERROR_CODES,
    parse_connect_response,
    xcp_command_name,
)


def scaffold_transport_frames() -> list[CanFrame]:
    return [
        CanFrame(
            arbitration_id=0x18FEEE31,
            data=bytes.fromhex("11223344"),
            frame_format="can",
            interface="can0",
            is_extended_id=True,
            timestamp=0.0,
        ),
        CanFrame(
            arbitration_id=0x18F00431,
            data=bytes.fromhex("AABBCCDD"),
            frame_format="can",
            interface="can0",
            is_extended_id=True,
            timestamp=0.1,
        ),
        CanFrame(
            arbitration_id=0x18FEF100,
            data=bytes.fromhex("0102030405060708"),
            frame_format="can",
            interface="can1",
            is_extended_id=True,
            timestamp=0.2,
        ),
    ]


def sample_j1939_monitor_frames() -> list[CanFrame]:
    return [frame for frame in scaffold_transport_frames() if frame.is_extended_id]


def sample_uds_scan_transactions() -> list[UdsTransactionEvent]:
    return [
        UdsTransactionEvent(
            request_id=0x7DF,
            response_id=0x7E8,
            service=0x10,
            service_name="DiagnosticSessionControl",
            request_data=bytes.fromhex("1001"),
            response_data=bytes.fromhex("5001003201F4"),
            ecu_address=0x7E8,
            source="transport.uds.scan",
            timestamp=0.0,
        ),
        UdsTransactionEvent(
            request_id=0x7DF,
            response_id=0x7E9,
            service=0x22,
            service_name="ReadDataByIdentifier",
            request_data=bytes.fromhex("22F190"),
            response_data=bytes.fromhex("62F19056494E31323334353637383930313233"),
            ecu_address=0x7E9,
            source="transport.uds.scan",
            timestamp=0.1,
        ),
    ]


def sample_uds_trace_transactions() -> list[UdsTransactionEvent]:
    return [
        UdsTransactionEvent(
            request_id=0x7E0,
            response_id=0x7E8,
            service=0x10,
            service_name="DiagnosticSessionControl",
            request_data=bytes.fromhex("1003"),
            response_data=bytes.fromhex("5003003201F4"),
            ecu_address=0x7E8,
            source="transport.uds.trace",
            timestamp=0.0,
        ),
        UdsTransactionEvent(
            request_id=0x7E0,
            response_id=0x7E8,
            service=0x27,
            service_name="SecurityAccess",
            request_data=bytes.fromhex("2701"),
            response_data=bytes.fromhex("6701123456789ABCDEF0"),
            ecu_address=0x7E8,
            source="transport.uds.trace",
            timestamp=0.2,
        ),
    ]


def _xcp_transaction(
    command: int,
    request_data: str,
    response_data: str,
    *,
    source: str,
    timestamp: float,
) -> XcpTransactionEvent:
    response = bytes.fromhex(response_data)
    positive = bool(response) and response[0] == 0xFF
    is_error = bool(response) and response[0] == 0xFE
    error_code = response[1] if is_error and len(response) >= 2 else None
    error_name = XCP_ERROR_CODES.get(error_code) if error_code is not None else None
    connect_info = parse_connect_response(response) if command == 0xFF and positive else None
    return XcpTransactionEvent(
        request_id=XCP_DEFAULT_REQUEST_ID,
        response_id=XCP_DEFAULT_RESPONSE_ID,
        command=command,
        command_name=xcp_command_name(command),
        request_data=bytes.fromhex(request_data),
        response_data=response,
        positive=positive,
        error_code=error_code,
        error_name=error_name,
        connect_info=connect_info,
        source=source,
        timestamp=timestamp,
    )


def sample_xcp_scan_transactions() -> list[XcpTransactionEvent]:
    return [
        _xcp_transaction(
            0xFF,
            "FF00",
            "FF14C00800080101",
            source="transport.xcp.scan",
            timestamp=0.0,
        ),
    ]


def sample_xcp_trace_transactions() -> list[XcpTransactionEvent]:
    return [
        _xcp_transaction(0xFD, "FD", "FF091D0000", source="transport.xcp.trace", timestamp=0.0),
        _xcp_transaction(
            0xF4, "F40400000004", "FF11223344", source="transport.xcp.trace", timestamp=0.1
        ),
        _xcp_transaction(0xF8, "F80000", "FE25", source="transport.xcp.trace", timestamp=0.2),
    ]


def sample_xcp_read_measurements() -> list[XcpMeasurementEvent]:
    return [
        XcpMeasurementEvent(
            response_id=XCP_DEFAULT_RESPONSE_ID,
            pid=0x00,
            data=bytes.fromhex("11223344"),
            source="transport.xcp.read",
            timestamp=0.0,
        ),
        XcpMeasurementEvent(
            response_id=XCP_DEFAULT_RESPONSE_ID,
            pid=0x01,
            data=bytes.fromhex("AABBCCDD"),
            source="transport.xcp.read",
            timestamp=0.1,
        ),
    ]
