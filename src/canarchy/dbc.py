"""DBC-backed decode, encode, and inspection helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from decimal import Decimal
from typing import Any



from canarchy.dbc_types import DatabaseInfo, DatabaseInspection, MessageInfo, SignalInfo
from canarchy.models import (
    CanFrame,
    DecodedMessageEvent,
    FrameEvent,
    SignalValueEvent,
    serialize_events,
)


@dataclass(slots=True)
class DbcError(Exception):
    code: str
    message: str
    hint: str

    def __str__(self) -> str:
        return self.message


def normalize_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    return value


def byte_order_name(is_little_endian: bool) -> str:
    return "little_endian" if is_little_endian else "big_endian"


def signal_choices(signal: Any) -> dict[str, str] | None:
    values = getattr(signal, "values", None)
    if not values:
        return None
    return {str(key): str(value) for key, value in values.items()}


def signal_metadata(signal: Any, *, message_name: str) -> SignalInfo:
    multiplexer_ids = getattr(signal, "mux_val", None)
    return SignalInfo(
        byte_order=byte_order_name(signal.is_little_endian),
        choices=signal_choices(signal),
        is_multiplexer=bool(getattr(signal, "is_multiplexer", False)),
        is_signed=bool(signal.is_signed),
        length=int(signal.size),
        maximum=normalize_value(signal.max) if signal.max is not None else None,
        message_name=message_name,
        minimum=normalize_value(signal.min) if signal.min is not None else None,
        multiplexer_ids=[int(multiplexer_ids)] if multiplexer_ids is not None else None,
        name=signal.name,
        offset=normalize_value(signal.offset),
        scale=normalize_value(signal.factor),
        start_bit=int(signal.start_bit),
        unit=signal.unit or None,
    )


def message_metadata(message: Any) -> MessageInfo:
    senders = sorted(str(sender) for sender in getattr(message, "transmitters", []) if sender)
    signals = [signal_metadata(signal, message_name=message.name) for signal in message.signals]
    return MessageInfo(
        arbitration_id=int(message.arbitration_id.id),
        arbitration_id_hex=f"0x{message.arbitration_id.id:X}",
        cycle_time_ms=getattr(message, "cycle_time", None),
        is_extended_id=bool(message.arbitration_id.extended),
        length=int(message.size),
        name=message.name,
        senders=senders,
        signals=signals,
    )


def decode_frames(frames: list[CanFrame], dbc_path: str) -> list[dict[str, Any]]:
    from canarchy.dbc_runtime import decode_frames_runtime

    return decode_frames_runtime(frames, dbc_path)


def inspect_database(
    dbc_path: str,
    *,
    message_name: str | None = None,
    signals_only: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    from canarchy.dbc_runtime import inspect_database_runtime

    inspection = inspect_database_runtime(dbc_path, message_name=message_name)
    return inspection.to_payload(signals_only=signals_only), inspection.to_events()
def encode_message(
    dbc_path: str,
    message_name: str,
    signals: dict[str, Any],
    *,
    interface: str | None = None,
) -> tuple[CanFrame, list[dict[str, Any]]]:
    from canarchy.dbc_runtime import encode_message_runtime

    return encode_message_runtime(dbc_path, message_name, signals, interface=interface)
