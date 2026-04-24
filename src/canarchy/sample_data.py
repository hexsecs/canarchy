"""Explicit sample/reference data providers.

These helpers exist to keep deterministic example protocol data separate from the
transport backend abstraction. The scaffold backend models deterministic transport
behavior, while the sample providers below model reference protocol outputs for
commands that are not yet truly transport-backed.
"""

from __future__ import annotations

from canarchy.models import CanFrame, UdsTransactionEvent


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
