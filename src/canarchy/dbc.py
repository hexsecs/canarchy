"""DBC-backed decode, encode, and inspection helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from decimal import Decimal
from typing import Any

from canmatrix import ArbitrationId, CanMatrix, formats

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


def load_database(dbc_path: str) -> CanMatrix:
    path = Path(dbc_path)
    if not path.exists():
        raise DbcError(
            code="DBC_NOT_FOUND",
            message=f"DBC file '{dbc_path}' was not found.",
            hint="Pass a readable DBC file path with `--dbc`.",
        )

    try:
        database = formats.loadp_flat(str(path))
    except Exception as exc:  # pragma: no cover
        raise DbcError(
            code="DBC_LOAD_FAILED",
            message="Failed to parse DBC file.",
            hint="Validate the DBC syntax and line endings.",
        ) from exc

    if not database.frames:
        raise DbcError(
            code="DBC_LOAD_FAILED",
            message="Failed to parse DBC file.",
            hint="Validate the DBC syntax and line endings.",
        )

    return database


def decode_frames(frames: list[CanFrame], dbc_path: str) -> list[dict[str, Any]]:
    database = load_database(dbc_path)
    events = []
    for frame in frames:
        message = database.frame_by_id(
            ArbitrationId(id=frame.arbitration_id, extended=frame.is_extended_id)
        )
        if message is None:
            continue

        try:
            decoded = message.decode(frame.data)
        except Exception as exc:  # pragma: no cover
            raise DbcError(
                code="DBC_DECODE_FAILED",
                message=f"Failed to decode frame 0x{frame.arbitration_id:X} with the selected DBC.",
                hint="Check that the capture and DBC definitions match the same protocol and message layout.",
            ) from exc

        decoded_signals = {
            signal_name: normalize_value(signal_value.phys_value)
            for signal_name, signal_value in decoded.items()
        }

        events.append(
            DecodedMessageEvent(
                message_name=message.name,
                frame=frame,
                signals=decoded_signals,
                source="dbc.decode",
            ).to_event()
        )
        for signal_name, value in decoded_signals.items():
            signal = message.signal_by_name(signal_name)
            events.append(
                SignalValueEvent(
                    message_name=message.name,
                    signal_name=signal_name,
                    value=value,
                    units=signal.unit,
                    source="dbc.decode",
                ).to_event()
            )

    return serialize_events(events)


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
    database = load_database(dbc_path)

    message = database.frame_by_name(message_name)
    if message is None:
        raise DbcError(
            code="DBC_MESSAGE_NOT_FOUND",
            message=f"DBC message '{message_name}' was not found.",
            hint="Use a message name that exists in the selected DBC.",
        )

    known_signals = {signal.name for signal in message.signals}
    unknown_signals = sorted(set(signals) - known_signals)
    if unknown_signals:
        raise DbcError(
            code="DBC_SIGNAL_INVALID",
            message=(
                f"Message '{message_name}' does not define signal(s): {', '.join(unknown_signals)}."
            ),
            hint="Use only signal names that exist in the selected DBC message.",
        )

    try:
        encoded = message.encode(signals)
    except Exception as exc:  # pragma: no cover
        raise DbcError(
            code="DBC_SIGNAL_INVALID",
            message=f"Failed to encode message '{message_name}' with the provided signals.",
            hint="Check the signal names, types, ranges, and required values for the selected DBC message.",
        ) from exc

    frame = CanFrame(
        arbitration_id=message.arbitration_id.id,
        data=encoded,
        interface=interface,
        is_extended_id=message.arbitration_id.extended,
        timestamp=0.0,
    )
    events = serialize_events([FrameEvent(frame=frame, source="dbc.encode").to_event()])
    return frame, events
