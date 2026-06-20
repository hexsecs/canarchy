"""cantools-backed DBC runtime adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from weakref import WeakKeyDictionary

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


# Parsed databases are cached by resolved path and file mtime so repeated
# lookups (e.g. per-DTC J1939 SPN resolution over a whole capture) parse each
# DBC at most once instead of re-reading it from disk on every access.
_DATABASE_CACHE: dict[str, tuple[float, int, cantools.database.Database]] = {}


def load_runtime_database(dbc_path: str) -> cantools.database.Database:
    from canarchy.dbc_provider import resolve_dbc_ref

    resolved = resolve_dbc_ref(dbc_path)
    path = Path(resolved)

    try:
        stat = path.stat()
        cache_key = str(path)
        cached = _DATABASE_CACHE.get(cache_key)
        if cached is not None and cached[0] == stat.st_mtime and cached[1] == stat.st_size:
            return cached[2]
        database = cantools.database.load_file(str(path))
        _DATABASE_CACHE[cache_key] = (stat.st_mtime, stat.st_size, database)
        return database
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


def generate_c_source_runtime(
    dbc_path: str,
    *,
    out_dir: str | None = None,
    database_name: str | None = None,
    floating_point_numbers: bool = True,
    bit_fields: bool = False,
    use_float: bool = False,
    node_name: str | None = None,
    use_round: bool = False,
) -> dict[str, Any]:
    """Generate C source and header files from a database using cantools.

    Returns a dict with ``out_dir``, ``database_name``, and ``files`` (a list
    of dicts each with ``path``, ``kind`` (``header`` / ``source`` /
    ``fuzzer_source`` / ``fuzzer_makefile``), and ``size_bytes``).
    """
    from cantools.database.can.c_source import generate as generate_c_source

    database = load_runtime_database(dbc_path)

    # Derive the database name from the source path when not given.
    stem = Path(dbc_path).stem
    resolved_name = database_name or stem

    # Sanitise for use as a C identifier prefix.
    safe_prefix = "".join(c if c.isalnum() or c == "_" else "_" for c in resolved_name)
    if safe_prefix[0].isdigit():
        safe_prefix = f"_{safe_prefix}"

    # Output directory.
    dest = Path(out_dir) if out_dir else Path.cwd()
    if not dest.exists():
        raise DbcError(
            code="DBC_GENERATE_C_DIR_MISSING",
            message=(
                f"Output directory '{dest}' does not exist. "
                f"Create it or specify an existing directory with --out-dir."
            ),
            hint="Use --out-dir to specify an existing output directory.",
        )

    header_name = f"{stem}.h"
    source_name = f"{stem}.c"
    fuzzer_source_name = f"{stem}_fuzzer.c"

    try:
        header, source, fuzzer_source, makefile = generate_c_source(
            database,
            database_name=safe_prefix,
            header_name=header_name,
            source_name=source_name,
            fuzzer_source_name=fuzzer_source_name,
            floating_point_numbers=floating_point_numbers,
            bit_fields=bit_fields,
            use_float=use_float,
            node_name=node_name,
            use_round=use_round,
        )
    except Exception as exc:
        raise DbcError(
            code="DBC_GENERATE_C_FAILED",
            message="Failed to generate C source from the database.",
            hint=(
                "Check that the database is valid and the requested options are "
                "compatible with the database contents."
            ),
        ) from exc

    files: list[dict[str, Any]] = []
    entries: list[tuple[str, str, str]] = [
        (header_name, "header", header),
        (source_name, "source", source),
        (fuzzer_source_name, "fuzzer_source", fuzzer_source),
        (f"{stem}_fuzzer.mk", "fuzzer_makefile", makefile),
    ]

    for filename, kind, content in entries:
        file_path = dest / filename
        try:
            file_path.write_text(content, encoding="utf-8")
        except OSError as exc:
            raise DbcError(
                code="DBC_GENERATE_C_WRITE_FAILED",
                message=f"Failed to write '{file_path}'.",
                hint="Check that the output directory is writable.",
            ) from exc
        files.append(
            {
                "path": str(file_path),
                "kind": kind,
                "size_bytes": len(content.encode("utf-8")),
            }
        )

    return {
        "out_dir": str(dest),
        "database_name": safe_prefix,
        "files": files,
        "file_count": len(files),
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


def database_timing_map_runtime(dbc_path: str) -> dict[int, dict[str, Any]]:
    """Return per-frame-id timing metadata (cycle time and send type) from a database.

    Keys are integer arbitration ids; values carry ``cycle_time_ms`` (the
    cantools cycle time in milliseconds, or ``None``) and ``send_type`` (the raw
    send-type string where the database provides one, else ``None``). Used by
    `re anomalies` to restrict timing checks to messages declared cyclic.
    """
    database = load_runtime_database(dbc_path)
    timing: dict[int, dict[str, Any]] = {}
    for message in database.messages:
        timing[int(message.frame_id)] = {
            "cycle_time_ms": getattr(message, "cycle_time", None),
            "send_type": getattr(message, "send_type", None),
        }
    return timing


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


# SPN -> metadata indexes keyed (weakly) by the database object, so a single
# linear pass over the DBC is reused across every per-DTC lookup and the index
# is dropped automatically when the database is evicted/garbage-collected.
_SPN_INDEX_CACHE: "WeakKeyDictionary[cantools.database.Database, dict[int, dict[str, Any]]]" = (
    WeakKeyDictionary()
)


def _spn_metadata_index(database: cantools.database.Database) -> dict[int, dict[str, Any]]:
    cached = _SPN_INDEX_CACHE.get(database)
    if cached is not None:
        return cached
    index: dict[int, dict[str, Any]] = {}
    for message in database.messages:
        for signal in message.signals:
            spn = getattr(signal, "spn", None)
            if spn is None or spn in index:
                continue
            index[spn] = {
                "message_name": message.name,
                "signal_name": signal.name,
                "units": signal.unit or None,
                "frame_id": int(message.frame_id),
            }
    _SPN_INDEX_CACHE[database] = index
    return index


def lookup_j1939_spn_metadata_runtime(dbc_path: str, spn: int) -> dict[str, Any] | None:
    database = load_runtime_database(dbc_path)
    return _spn_metadata_index(database).get(spn)


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


# --- encode name resolution (#413) ------------------------------------------
#
# The built-in J1939 decoder displays SAE labels ("Engine Speed", message
# "EEC1") while the DBC defines raw names ("EngineSpeed" in "EngineSpeed1").
# `encode` resolves both spellings so a decoded signal can be re-encoded by
# its displayed name without a manual DBC lookup.


def _normalized_name(name: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]", "", name.lower())


def _message_pgn(message: Any) -> int | None:
    if not bool(message.is_extended_frame):
        return None
    try:
        return decompose_arbitration_id(int(message.frame_id)).pgn
    except ValueError:
        return None


def _resolve_encode_message(
    database: Any, message_name: str, signal_names: list[str] | None = None
) -> tuple[Any, dict[str, Any]]:
    """Resolve a requested message name to a DBC message.

    Tries, in order: the exact DBC name; a case/spacing-insensitive match;
    and the SAE PGN label/name from the bundled J1939 catalog (e.g. "EEC1"
    resolves to the DBC message whose frame id carries PGN 61444). When a PGN
    label matches several messages (same PGN from different source
    addresses), the supplied signal names break the tie. Ambiguous or failed
    lookups raise `DBC_MESSAGE_NOT_FOUND` with suggestions.
    """
    from canarchy.j1939_metadata import pgn_lookup

    try:
        message = database.get_message_by_name(message_name)
        return message, {"requested": message_name, "resolved": message.name, "via": "exact"}
    except KeyError:
        pass

    wanted = _normalized_name(message_name)
    normalized_matches = [m for m in database.messages if _normalized_name(m.name) == wanted]
    if len(normalized_matches) == 1:
        message = normalized_matches[0]
        return message, {"requested": message_name, "resolved": message.name, "via": "normalized"}

    pgn_label_matches = []
    for candidate in database.messages:
        pgn = _message_pgn(candidate)
        if pgn is None:
            continue
        meta = pgn_lookup(pgn) or {}
        labels = {meta.get("label"), meta.get("name")}
        if any(label and _normalized_name(str(label)) == wanted for label in labels):
            pgn_label_matches.append((candidate, pgn))
    if len(pgn_label_matches) > 1 and signal_names:
        # Same PGN can appear once per source address; only candidates whose
        # signals can absorb every supplied name stay in the running.
        def _absorbs_all(candidate: Any) -> bool:
            resolved, _ = _resolve_encode_signal_names(
                candidate, {name: None for name in signal_names}
            )
            known = {signal.name for signal in candidate.signals}
            return all(name in known for name in resolved)

        narrowed = [(c, p) for c, p in pgn_label_matches if _absorbs_all(c)]
        if len(narrowed) == 1:
            pgn_label_matches = narrowed
    if len(pgn_label_matches) == 1:
        message, pgn = pgn_label_matches[0]
        return message, {
            "requested": message_name,
            "resolved": message.name,
            "via": "pgn_label",
            "pgn": pgn,
        }
    if len(pgn_label_matches) > 1:
        names = sorted(candidate.name for candidate, _ in pgn_label_matches)
        raise DbcError(
            code="DBC_MESSAGE_NOT_FOUND",
            message=f"Message name '{message_name}' matches multiple DBC messages by PGN.",
            hint=f"Use one of the exact DBC message names: {', '.join(names)}.",
            detail={"candidates": names},
        )

    import difflib

    catalog: dict[str, str] = {}
    for candidate in database.messages:
        catalog.setdefault(_normalized_name(candidate.name), candidate.name)
        pgn = _message_pgn(candidate)
        meta = pgn_lookup(pgn) or {} if pgn is not None else {}
        label = meta.get("label")
        if label:
            catalog.setdefault(_normalized_name(str(label)), f"{label} ({candidate.name})")
    close = difflib.get_close_matches(wanted, list(catalog), n=3, cutoff=0.6)
    suggestions = [catalog[key] for key in close]
    raise DbcError(
        code="DBC_MESSAGE_NOT_FOUND",
        message=f"DBC message '{message_name}' was not found.",
        hint=(
            f"Did you mean: {', '.join(suggestions)}? "
            if suggestions
            else "Use a message name that exists in the selected DBC. "
        )
        + "Message names also match case/spacing-insensitively and by SAE PGN label.",
        detail={"suggestions": suggestions} if suggestions else None,
    )


def _resolve_encode_signal_names(
    message: Any, signals: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Map supplied signal names onto the message's DBC signal names.

    Falls back from the exact name to a case/spacing-insensitive match and
    then to the bundled SAE SPN name of a signal carrying an SPN attribute.
    Unresolvable names are passed through for the caller's unknown-signal
    error path.
    """
    from canarchy.j1939_metadata import spn_lookup

    known = {signal.name for signal in message.signals}
    by_normalized = {_normalized_name(signal.name): signal.name for signal in message.signals}
    by_spn_name: dict[str, str] = {}
    for signal in message.signals:
        spn = getattr(signal, "spn", None)
        if spn is None:
            continue
        meta = spn_lookup(int(spn))
        if meta and meta.get("name"):
            by_spn_name.setdefault(_normalized_name(str(meta["name"])), signal.name)

    resolved: dict[str, Any] = {}
    aliases: list[dict[str, str]] = []
    for name, value in signals.items():
        if name in known:
            resolved[name] = value
            continue
        wanted = _normalized_name(name)
        target = by_normalized.get(wanted)
        via = "normalized"
        if target is None:
            target = by_spn_name.get(wanted)
            via = "spn_name"
        if target is None or target in resolved:
            resolved[name] = value
            continue
        resolved[target] = value
        aliases.append({"requested": name, "resolved": target, "via": via})
    return resolved, aliases


def _signal_name_suggestions(message: Any, unknown_signals: list[str]) -> list[str]:
    from canarchy.j1939_metadata import spn_lookup
    import difflib

    catalog: dict[str, str] = {}
    for signal in message.signals:
        catalog.setdefault(_normalized_name(signal.name), signal.name)
        spn = getattr(signal, "spn", None)
        meta = spn_lookup(int(spn)) if spn is not None else None
        if meta and meta.get("name"):
            catalog.setdefault(
                _normalized_name(str(meta["name"])), f"{meta['name']} ({signal.name})"
            )

    suggestions: list[str] = []
    for name in unknown_signals:
        close = difflib.get_close_matches(_normalized_name(name), list(catalog), n=2, cutoff=0.5)
        suggestions += [catalog[key] for key in close if catalog[key] not in suggestions]
    return suggestions


def _fill_missing_signals(
    message: Any, signals: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Default unsupplied signals so a single-signal encode round-trips.

    Each missing signal takes its DBC initial value when declared, otherwise
    0 clamped into the declared range. Multiplexed messages are left alone —
    their required-signal set depends on the selector value.
    """
    if getattr(message, "is_multiplexed", lambda: False)():
        return signals, []

    filled: list[dict[str, Any]] = []
    resolved = dict(signals)
    for signal in message.signals:
        if signal.name in resolved or signal.name == "CHECKSUM":
            continue
        initial = getattr(signal, "initial", None)
        if initial is not None:
            value = normalize_value(initial)
        else:
            value = 0
            minimum = normalize_value(signal.minimum) if signal.minimum is not None else None
            maximum = normalize_value(signal.maximum) if signal.maximum is not None else None
            if minimum is not None and value < minimum:
                value = minimum
            if maximum is not None and value > maximum:
                value = maximum
        choices = getattr(signal, "choices", None)
        if choices and value not in set(choices.keys()):
            # Raw choice keys are what message.encode accepts numerically;
            # fall back to the smallest defined choice.
            value = sorted(choices.keys())[0]
        resolved[signal.name] = value
        filled.append({"signal": signal.name, "value": value})
    return resolved, filled


def encode_message_runtime(
    dbc_path: str,
    message_name: str,
    signals: dict[str, Any],
    *,
    interface: str | None = None,
    crc_algorithm: str | None = None,
) -> tuple[CanFrame, list[dict[str, Any]], dict[str, Any]]:
    database = load_runtime_database(dbc_path)

    message, message_resolution = _resolve_encode_message(
        database, message_name, signal_names=list(signals)
    )
    signals, signal_aliases = _resolve_encode_signal_names(message, signals)
    resolution: dict[str, Any] = {
        "message": message_resolution,
        "signal_aliases": signal_aliases,
        "filled_signals": [],
    }

    known_signals = {signal.name for signal in message.signals}
    unknown_signals = sorted(set(signals) - known_signals)
    if unknown_signals:
        suggestions = _signal_name_suggestions(message, unknown_signals)
        raise DbcError(
            code="DBC_SIGNAL_INVALID",
            message=(
                f"Message '{message.name}' does not define signal(s): {', '.join(unknown_signals)}."
            ),
            hint=(
                f"Did you mean: {', '.join(suggestions)}? "
                if suggestions
                else "Use only signal names that exist in the selected DBC message. "
            )
            + "Signal names also match case/spacing-insensitively and by SAE SPN name.",
            detail={"unknown_signals": unknown_signals, "suggestions": suggestions},
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

    resolved_signals, filled = _fill_missing_signals(message, signals)
    resolution["filled_signals"] = filled
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
            message=f"Failed to encode message '{message.name}' with the provided signals.",
            hint="Check the signal names, types, ranges, and required values for the selected DBC message.",
        ) from exc

    frame = CanFrame(
        arbitration_id=int(message.frame_id),
        data=encoded,
        interface=interface,
        is_extended_id=bool(message.is_extended_frame),
        timestamp=0.0,
    )
    events = serialize_events([FrameEvent(frame=frame, source="dbc.encode").to_event()])
    return frame, events, resolution
