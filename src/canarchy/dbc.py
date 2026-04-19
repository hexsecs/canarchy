"""DBC-backed decode and encode helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from decimal import Decimal
from typing import Any

from canmatrix import ArbitrationId, CanMatrix, formats

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
