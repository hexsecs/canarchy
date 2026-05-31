"""cantools-backed DBC runtime adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import cantools
from cantools.database.utils import create_encode_decode_formats, decode_data

from canarchy.checksum import CrcAlgorithm, compute_checksum, detect_algorithm_from_dbc
from canarchy.dbc import DbcError, normalize_value
from canarchy.dbc_types import DatabaseInfo, DatabaseInspection, MessageInfo, SignalInfo
from canarchy.j1939 import decompose_arbitration_id
from canarchy.models import (
    CanFrame,
    DecodedMessageEvent,
    FrameEvent,
    SignalValueEvent,
    serialize_events,
)


# Database formats cantools can load, keyed by lowercase filename suffix.
# DBC is the default for unknown suffixes, matching cantools' own behaviour.
_DATABASE_FORMATS: dict[str, str] = {
    ".arxml": "arxml",
    ".dbc": "dbc",
    ".kcd": "kcd",
    ".sym": "sym",
}


def detect_database_format(path: str) -> str:
    """Return the database format for *path* based on its filename suffix.

    Mirrors cantools' extension-based format selection (`.arxml` / `.dbc` /
    `.kcd` / `.sym`); anything else falls back to ``dbc``.
    """
    return _DATABASE_FORMATS.get(Path(path).suffix.lower(), "dbc")


def load_runtime_database(dbc_path: str) -> cantools.database.Database:
    from canarchy.dbc_provider import resolve_dbc_ref

    resolved = resolve_dbc_ref(dbc_path)
    path = Path(resolved)

    try:
        return cantools.database.load_file(str(path))
    except DbcError:
        raise
    except Exception as exc:  # pragma: no cover
        raise DbcError(
            code="DBC_LOAD_FAILED",
            message=f"Failed to parse {detect_database_format(str(path)).upper()} database file.",
            hint="Validate the database syntax, encoding, and line endings.",
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


def _message_info(message: Any, *, include_layout: bool = False) -> MessageInfo:
    senders = sorted(str(sender) for sender in getattr(message, "senders", []) if sender)
    signals = [_signal_info(signal, message_name=message.name) for signal in message.signals]
    cycle_time_ms = getattr(message, "cycle_time", None)
    layout = signal_tree = signal_choices = None
    if include_layout:
        from cantools.subparsers.dump import formatting

        layout = formatting.layout_string(message)
        signal_tree = formatting.signal_tree_string(message)
        signal_choices = formatting.signal_choices_string(message)
    return MessageInfo(
        name=message.name,
        arbitration_id=int(message.frame_id),
        arbitration_id_hex=f"0x{message.frame_id:X}",
        is_extended_id=bool(message.is_extended_frame),
        length=int(message.length),
        cycle_time_ms=0 if cycle_time_ms is None else int(cycle_time_ms),
        senders=senders,
        signals=signals,
        layout=layout,
        signal_tree=signal_tree,
        signal_choices=signal_choices,
    )


def inspect_database_runtime(
    dbc_path: str,
    *,
    message_name: str | None = None,
    include_layout: bool = False,
) -> DatabaseInspection:
    from canarchy.dbc_provider import resolve_dbc_ref

    database = load_runtime_database(dbc_path)
    database_format = detect_database_format(resolve_dbc_ref(dbc_path))

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

    messages = [
        _message_info(message, include_layout=include_layout) for message in selected_messages
    ]
    node_names = {sender for message in messages for sender in message.senders}
    return DatabaseInspection(
        database=DatabaseInfo(
            path=dbc_path,
            format=database_format,
            message_count=len(database.messages),
            signal_count=sum(len(message.signals) for message in database.messages),
            node_count=len(node_names),
        ),
        messages=messages,
        selected_message=message_name,
    )


_DATABASE_SERIALIZERS: dict[str, str] = {
    "dbc": "as_dbc_string",
    "kcd": "as_kcd_string",
    "sym": "as_sym_string",
}


def convert_database_runtime(
    dbc_path: str,
    target_format: str,
    *,
    out_path: str | None = None,
) -> tuple[str, str | None, int, int]:
    """Serialize a loaded database into another cantools-supported format.

    Returns the serialized content, the path it was written to (or ``None``
    when returned to the caller for stdout), and the message/signal counts.
    """

    serializer_name = _DATABASE_SERIALIZERS.get(target_format)
    if serializer_name is None:
        raise DbcError(
            code="DBC_CONVERT_UNSUPPORTED_FORMAT",
            message=f"Unsupported target format '{target_format}'.",
            hint=f"Choose one of: {', '.join(sorted(_DATABASE_SERIALIZERS))}.",
        )

    database = load_runtime_database(dbc_path)

    try:
        content = getattr(database, serializer_name)()
    except Exception as exc:
        raise DbcError(
            code="DBC_CONVERT_FAILED",
            message=f"Failed to serialize the database as {target_format.upper()}.",
            hint=(
                "The target format may not be able to express a feature used by the "
                "source database; try a different target or simplify the source."
            ),
        ) from exc

    written: str | None = None
    if out_path is not None:
        try:
            Path(out_path).write_text(content, encoding="utf-8")
        except OSError as exc:
            raise DbcError(
                code="DBC_CONVERT_WRITE_FAILED",
                message=f"Failed to write the converted database to '{out_path}'.",
                hint="Check that the output directory exists and is writable.",
            ) from exc
        written = out_path

    message_count = len(database.messages)
    signal_count = sum(len(message.signals) for message in database.messages)
    return content, written, message_count, signal_count


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
                    raw=_signal_raw_hex(message, signal, frame.data),
                    value=value,
                    units=signal.unit,
                    source="dbc.decode",
                ).to_event()
            )

    return serialize_events(events)


def dbc_supports_spn_runtime(dbc_path: str, spn: int) -> bool:
    database = load_runtime_database(dbc_path)
    for message in database.messages:
        for signal in message.signals:
            if getattr(signal, "spn", None) == spn:
                return True
    return False


def lookup_j1939_spn_metadata_runtime(dbc_path: str, spn: int) -> dict[str, Any] | None:
    database = load_runtime_database(dbc_path)
    for message in database.messages:
        for signal in message.signals:
            if getattr(signal, "spn", None) != spn:
                continue
            return {
                "message_name": message.name,
                "signal_name": signal.name,
                "units": signal.unit or None,
                "frame_id": int(message.frame_id),
            }
    return None


def decode_j1939_spn_runtime(
    frames: list[CanFrame], dbc_path: str, spn: int
) -> list[dict[str, Any]]:
    database = load_runtime_database(dbc_path)
    matching_signals: dict[int, Any] = {}
    for message in database.messages:
        for signal in message.signals:
            if getattr(signal, "spn", None) == spn:
                matching_signals[int(message.frame_id)] = signal
                break

    observations: list[dict[str, Any]] = []
    for frame in frames:
        signal = matching_signals.get(frame.arbitration_id)
        if signal is None:
            continue
        try:
            message = database.get_message_by_frame_id(frame.arbitration_id)
            decoded = message.decode(frame.data)
        except Exception as exc:  # pragma: no cover
            raise DbcError(
                code="DBC_DECODE_FAILED",
                message=f"Failed to decode frame 0x{frame.arbitration_id:X} with the selected DBC.",
                hint="Check that the capture and DBC definitions match the same protocol and message layout.",
            ) from exc

        identifier = decompose_arbitration_id(frame.arbitration_id)
        value = normalize_value(decoded[signal.name])
        raw = _signal_raw_hex(message, signal, frame.data)
        if raw is not None and int(raw, 16) == (1 << signal.length) - 1:
            value = None
        observations.append(
            {
                "spn": spn,
                "name": signal.name,
                "pgn": identifier.pgn,
                "source_address": identifier.source_address,
                "destination_address": identifier.destination_address,
                "units": signal.unit or None,
                "raw": raw,
                "value": value,
                "timestamp": frame.timestamp,
            }
        )
    return observations


def _signal_raw_hex(message: Any, signal: Any, data: bytes) -> str | None:
    if signal.start % 8 == 0 and signal.length % 8 == 0:
        start = signal.start // 8
        end = start + (signal.length // 8)
        return data[start:end].hex()

    try:
        formats = create_encode_decode_formats([signal], message.length)
        raw_values = decode_data(
            data,
            message.length,
            [signal],
            formats,
            decode_choices=False,
            scaling=False,
            allow_truncated=False,
            allow_excess=False,
        )
    except Exception as exc:  # pragma: no cover
        raise DbcError(
            code="DBC_DECODE_FAILED",
            message=f"Failed to extract raw signal '{signal.name}' from the selected DBC.",
            hint="Check that the DBC signal definition matches the captured frame layout.",
        ) from exc

    raw_value = raw_values.get(signal.name)
    if raw_value is None:
        return None
    if isinstance(raw_value, int):
        width = max((signal.length + 3) // 4, 1)
        masked = raw_value & ((1 << signal.length) - 1)
        return f"{masked:0{width}x}"
    return str(raw_value)


def _checksum_signal(message: Any) -> Any | None:
    """Return the CHECKSUM signal if the message has one, else None."""
    for signal in message.signals:
        if signal.name == "CHECKSUM":
            return signal
    return None


def _checksum_byte_index(signal: Any) -> int:
    """Derive the checksum byte index from a signal's start bit and length."""
    return (signal.start + signal.length - 1) // 8


def _resolve_crc_algorithm(dbc_path: str, algorithm_override: str | None) -> CrcAlgorithm:
    """Resolve the CRC algorithm from an explicit flag or DBC detection."""
    if algorithm_override:
        return CrcAlgorithm(algorithm_override)
    detected = detect_algorithm_from_dbc(dbc_path)
    return detected if detected is not None else CrcAlgorithm.STELLANTIS


def _auto_compute_checksum(
    message: Any,
    checksum_signal: Any,
    signals: dict[str, Any],
    dbc_path: str,
    *,
    algorithm_override: str | None = None,
    arbitration_id: int | None = None,
) -> dict[str, Any]:
    """Encode with CHECKSUM=0, compute the correct CRC, return updated signals.

    Only triggers when the user did not supply a CHECKSUM value and the
    CHECKSUM signal is 8 bits wide. The algorithm is resolved from
    *algorithm_override* or auto-detected from the DBC name.
    """
    if "CHECKSUM" in signals:
        return signals
    if checksum_signal.length != 8:
        return signals

    try:
        temp_encoded = message.encode({**signals, "CHECKSUM": 0})
        temp_encoded_ff = message.encode({**signals, "CHECKSUM": 0xFF})
    except Exception:
        return signals

    if len(temp_encoded) == 0 or len(temp_encoded) != len(temp_encoded_ff):
        return signals
    differing = [i for i in range(len(temp_encoded)) if temp_encoded[i] != temp_encoded_ff[i]]
    if len(differing) != 1 or differing[0] != len(temp_encoded) - 1:
        return signals

    algorithm = _resolve_crc_algorithm(dbc_path, algorithm_override)
    crc = compute_checksum(algorithm, temp_encoded, address=arbitration_id)
    return {**signals, "CHECKSUM": crc}


def encode_message_runtime(
    dbc_path: str,
    message_name: str,
    signals: dict[str, Any],
    *,
    interface: str | None = None,
    crc_algorithm: str | None = None,
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

    for sig_name, sig_value in signals.items():
        signal = message.get_signal_by_name(sig_name)
        choices = getattr(signal, "choices", None)
        if choices:
            valid_labels = set(choices.values())
            valid_keys = set(choices.keys())
            if sig_value not in valid_labels and sig_value not in valid_keys:
                raise DbcError(
                    code="DBC_SIGNAL_INVALID",
                    message=f"Signal '{sig_name}' value {sig_value!r} is not a valid choice.",
                    hint=f"Valid choices for '{sig_name}': {', '.join(str(v) for v in sorted(valid_labels))}.",
                    detail={
                        "signal": sig_name,
                        "supplied": sig_value,
                        "choices": sorted(valid_labels),
                    },
                )
        else:
            minimum = normalize_value(signal.minimum) if signal.minimum is not None else None
            maximum = normalize_value(signal.maximum) if signal.maximum is not None else None
            if isinstance(sig_value, (int, float)) and minimum is not None and sig_value < minimum:
                raise DbcError(
                    code="DBC_SIGNAL_INVALID",
                    message=f"Signal '{sig_name}' value {sig_value} is below the minimum of {minimum}.",
                    hint=f"'{sig_name}' must be in the range {minimum}..{maximum}.",
                    detail={
                        "signal": sig_name,
                        "supplied": sig_value,
                        "minimum": minimum,
                        "maximum": maximum,
                    },
                )
            if isinstance(sig_value, (int, float)) and maximum is not None and sig_value > maximum:
                raise DbcError(
                    code="DBC_SIGNAL_INVALID",
                    message=f"Signal '{sig_name}' value {sig_value} exceeds the maximum of {maximum}.",
                    hint=f"'{sig_name}' must be in the range {minimum}..{maximum}.",
                    detail={
                        "signal": sig_name,
                        "supplied": sig_value,
                        "minimum": minimum,
                        "maximum": maximum,
                    },
                )

    resolved_signals = dict(signals)
    cs = _checksum_signal(message)
    if cs is not None:
        resolved_signals = _auto_compute_checksum(
            message,
            cs,
            resolved_signals,
            dbc_path,
            algorithm_override=crc_algorithm,
            arbitration_id=int(message.frame_id),
        )

    try:
        encoded = message.encode(resolved_signals)
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
