"""cantools-backed DBC runtime adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import cantools

from canarchy.dbc import DbcError, normalize_value
from canarchy.dbc_types import DatabaseInfo, DatabaseInspection, MessageInfo, SignalInfo
from canarchy.models import CanFrame, DecodedMessageEvent, FrameEvent, SignalValueEvent, serialize_events


def load_runtime_database(dbc_path: str) -> cantools.database.Database:
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


def _signal_choices(signal: Any) -> dict[str, str] | None:
    choices = getattr(signal, "choices", None)
    if not choices:
        return None
    return {str(key): str(value) for key, value in choices.items()}


def _signal_info(signal: Any, *, message_name: str) -> SignalInfo:
    multiplexer_ids = getattr(signal, "multiplexer_ids", None)
    return SignalInfo(
        name=signal.name,
        message_name=message_name,
        start_bit=int(signal.start),
        length=int(signal.length),
        byte_order=str(signal.byte_order),
        is_signed=bool(signal.is_signed),
        scale=normalize_value(signal.scale),
        offset=normalize_value(signal.offset),
        minimum=normalize_value(signal.minimum) if signal.minimum is not None else None,
        maximum=normalize_value(signal.maximum) if signal.maximum is not None else None,
        unit=signal.unit or None,
        choices=_signal_choices(signal),
        is_multiplexer=bool(getattr(signal, "is_multiplexer", False)),
        multiplexer_ids=[int(value) for value in multiplexer_ids] if multiplexer_ids else None,
    )


def _message_info(message: Any) -> MessageInfo:
    senders = sorted(str(sender) for sender in getattr(message, "senders", []) if sender)
    signals = [_signal_info(signal, message_name=message.name) for signal in message.signals]
    cycle_time_ms = getattr(message, "cycle_time", None)
    return MessageInfo(
        name=message.name,
        arbitration_id=int(message.frame_id),
        arbitration_id_hex=f"0x{message.frame_id:X}",
        is_extended_id=bool(message.is_extended_frame),
        length=int(message.length),
        cycle_time_ms=0 if cycle_time_ms is None else int(cycle_time_ms),
        senders=senders,
        signals=signals,
    )


def inspect_database_runtime(
    dbc_path: str,
    *,
    message_name: str | None = None,
) -> DatabaseInspection:
    database = load_runtime_database(dbc_path)

    if message_name is not None:
        try:
            message = database.get_message_by_name(message_name)
        except KeyError as exc:
            raise DbcError(
                code="DBC_MESSAGE_NOT_FOUND",
                message=f"DBC message '{message_name}' was not found.",
                hint="Use a message name that exists in the selected DBC.",
            ) from exc
        selected_messages = [message]
    else:
        selected_messages = sorted(database.messages, key=lambda current: current.name)

    messages = [_message_info(message) for message in selected_messages]
    node_names = {sender for message in messages for sender in message.senders}
    return DatabaseInspection(
        database=DatabaseInfo(
            path=dbc_path,
            format="dbc",
            message_count=len(database.messages),
            signal_count=sum(len(message.signals) for message in database.messages),
            node_count=len(node_names),
        ),
        messages=messages,
        selected_message=message_name,
    )


def decode_frames_runtime(frames: list[CanFrame], dbc_path: str) -> list[dict[str, Any]]:
    database = load_runtime_database(dbc_path)
    events: list[dict[str, Any]] = []
    for frame in frames:
        try:
            message = database.get_message_by_frame_id(frame.arbitration_id)
        except KeyError:
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
            signal_name: normalize_value(signal_value)
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


def encode_message_runtime(
    dbc_path: str,
    message_name: str,
    signals: dict[str, Any],
    *,
    interface: str | None = None,
) -> tuple[CanFrame, list[dict[str, Any]]]:
    database = load_runtime_database(dbc_path)

    try:
        message = database.get_message_by_name(message_name)
    except KeyError as exc:
        raise DbcError(
            code="DBC_MESSAGE_NOT_FOUND",
            message=f"DBC message '{message_name}' was not found.",
            hint="Use a message name that exists in the selected DBC.",
        ) from exc

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
        arbitration_id=int(message.frame_id),
        data=encoded,
        interface=interface,
        is_extended_id=bool(message.is_extended_frame),
        timestamp=0.0,
    )
    return frame, serialize_events([FrameEvent(frame=frame, source="dbc.encode").to_event()])
