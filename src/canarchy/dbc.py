"""DBC-backed decode and encode helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cantools

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


def load_database(dbc_path: str) -> cantools.database.Database:
    path = Path(dbc_path)
    if not path.exists():
        raise DbcError(
            code="DBC_NOT_FOUND",
            message=f"DBC file '{dbc_path}' was not found.",
            hint="Pass a readable DBC file path with `--dbc`.",
        )

    try:
        return cantools.database.load_file(str(path))
    except Exception as exc:  # pragma: no cover
        raise DbcError(
            code="DBC_LOAD_FAILED",
            message="Failed to parse DBC file.",
            hint="Validate the DBC syntax and line endings.",
        ) from exc


def decode_frames(frames: list[CanFrame], dbc_path: str) -> list[dict[str, Any]]:
    database = load_database(dbc_path)
    events = []
    for frame in frames:
        try:
            message = database.get_message_by_frame_id(frame.arbitration_id)
        except KeyError:
            continue

        try:
            decoded_signals = message.decode(frame.data, allow_truncated=True)
        except Exception as exc:  # pragma: no cover
            raise DbcError(
                code="DBC_DECODE_FAILED",
                message=f"Failed to decode frame 0x{frame.arbitration_id:X} with the selected DBC.",
                hint="Check that the capture and DBC definitions match the same protocol and message layout.",
            ) from exc

        events.append(
            DecodedMessageEvent(
                message_name=message.name,
                frame=frame,
                signals=decoded_signals,
                source="dbc.decode",
            ).to_event()
        )
        for signal_name, value in decoded_signals.items():
            signal = message.get_signal_by_name(signal_name)
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

    try:
        message = database.get_message_by_name(message_name)
    except KeyError as exc:
        raise DbcError(
            code="DBC_MESSAGE_NOT_FOUND",
            message=f"DBC message '{message_name}' was not found.",
            hint="Use a message name that exists in the selected DBC.",
        ) from exc

    try:
        encoded = message.encode(signals)
    except Exception as exc:  # pragma: no cover
        raise DbcError(
            code="DBC_ENCODE_FAILED",
            message=f"Failed to encode message '{message_name}' with the provided signals.",
            hint="Check the signal names, types, and required values for the selected DBC message.",
        ) from exc

    frame = CanFrame(
        arbitration_id=message.frame_id,
        data=encoded,
        interface=interface,
        is_extended_id=message.is_extended_frame,
        timestamp=0.0,
    )
    events = serialize_events([FrameEvent(frame=frame, source="dbc.encode").to_event()])
    return frame, events
