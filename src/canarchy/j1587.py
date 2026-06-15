"""J1587/J1708 protocol helpers.

J1708 is the data-link layer for legacy heavy-vehicle diagnostics: an
asynchronous serial bus (RS-485, 9600 baud) carrying variable-length
messages. Each message is ``MID <parameters...> checksum`` where ``MID``
identifies the originating ECU and ``checksum`` is chosen so the byte sum of
the whole message is congruent to 0 mod 256.

A parameter begins with a PID (Parameter ID) byte. Per SAE J1587, the PID
value determines how many data bytes follow:

* ``0-127``   -- one data byte
* ``128-191`` -- two data bytes
* ``192-253`` -- a length byte, followed by that many data bytes
* ``254``     -- an extended PID: the next byte is added to 256 to form a
  16-bit PID (256-511), followed by a length byte and that many data bytes

This module parses that framing and resolves common PIDs against the
bundled catalog in ``canarchy.j1587_metadata`` (mirroring the
``canarchy.j1939``/``canarchy.j1939_metadata`` split).
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

from canarchy.j1587_metadata import decodable_pids, pid_lookup
from canarchy.models import J1587ObservationEvent
from canarchy.transport import TransportError

J1708_EXTENDED_PID_MARKER = 254

J1708_LINE_RE = re.compile(r"^\((?P<timestamp>\d+(?:\.\d+)?)\)\s+j1708\s+(?P<data>[0-9A-Fa-f]+)$")


@dataclass(slots=True, frozen=True)
class J1587Parameter:
    """A single PID/data parameter extracted from a J1708 message."""

    pid: int
    data: bytes


@dataclass(slots=True, frozen=True)
class J1708Message:
    """A decoded J1708 message: source MID, parameters, and checksum status."""

    mid: int
    parameters: tuple[J1587Parameter, ...]
    checksum_valid: bool
    raw: bytes
    timestamp: float | None = None


def parse_j1708_message(raw: bytes, *, timestamp: float | None = None) -> J1708Message:
    """Parse a raw J1708 message (MID, parameters, checksum) from ``raw`` bytes."""

    if len(raw) < 2:
        raise ValueError("a J1708 message must contain at least a MID and checksum byte")

    checksum_valid = (sum(raw) % 256) == 0
    mid = raw[0]
    parameters = tuple(_iter_parameters(raw[1:-1]))
    return J1708Message(
        mid=mid, parameters=parameters, checksum_valid=checksum_valid, raw=raw, timestamp=timestamp
    )


def _iter_parameters(payload: bytes) -> Iterator[J1587Parameter]:
    index = 0
    size = len(payload)
    while index < size:
        pid = payload[index]
        index += 1
        if pid == J1708_EXTENDED_PID_MARKER:
            if index >= size:
                raise ValueError("truncated extended PID in J1708 message")
            pid = 256 + payload[index]
            index += 1

        if pid <= 127:
            length = 1
        elif pid <= 191:
            length = 2
        else:
            if index >= size:
                raise ValueError("truncated parameter length in J1708 message")
            length = payload[index]
            index += 1

        data = payload[index : index + length]
        if len(data) < length:
            raise ValueError("truncated parameter data in J1708 message")
        yield J1587Parameter(pid=pid, data=data)
        index += length


def decode_parameter_value(pid: int, data: bytes) -> tuple[str | None, float | None, str | None]:
    """Resolve ``(name, value, units)`` for ``data`` against the bundled PID catalog.

    Returns ``(None, None, None)`` for PIDs without bundled metadata. A
    value of all-ones (the J1587 "data not available" sentinel) decodes to
    ``None`` with the name/units still populated. Metadata that lacks the
    fields needed to scale the raw bytes (for example a name-only PID
    override) yields ``value=None`` while still surfacing any name/units.
    """

    meta = pid_lookup(pid)
    if meta is None:
        return None, None, None

    name = meta.get("name")
    units = meta.get("units")
    if pid not in decodable_pids():
        return name, None, units

    byteorder = meta.get("byteorder", "little")
    raw_value = int.from_bytes(data, byteorder=byteorder)
    if raw_value == (1 << (len(data) * 8)) - 1:
        value = None
    else:
        value = raw_value * float(meta["resolution"]) + float(meta["offset"])
    return name, value, units


def decode_events(
    messages: Iterable[J1708Message], *, source: str = "j1587"
) -> list[J1587ObservationEvent]:
    """Flatten J1708 messages into one observation event per parameter."""

    events: list[J1587ObservationEvent] = []
    for message in messages:
        for parameter in message.parameters:
            name, value, units = decode_parameter_value(parameter.pid, parameter.data)
            events.append(
                J1587ObservationEvent(
                    mid=message.mid,
                    pid=parameter.pid,
                    raw=parameter.data,
                    name=name,
                    value=value,
                    units=units,
                    checksum_valid=message.checksum_valid,
                    source=source,
                    timestamp=message.timestamp,
                )
            )
    return events


def j1587_pids_payload() -> list[dict[str, object]]:
    """The bundled PID catalog, for ``canarchy j1587 pids``."""

    return [{"pid": pid, **pid_lookup(pid)} for pid in sorted(decodable_pids())]  # type: ignore[misc]


def iter_j1708_messages_from_file(
    file_name: str,
    *,
    offset: int = 0,
    max_frames: int | None = None,
    seconds: float | None = None,
) -> Iterator[J1708Message]:
    """Yield :class:`J1708Message` records from a J1708 capture file.

    Each non-blank line must read ``(timestamp) j1708 <hex>`` where ``<hex>``
    is the full raw message (MID, parameters, checksum). Malformed lines and
    missing files raise :class:`TransportError`.
    """

    if file_name == "-":
        handle = sys.stdin
        path: Path | None = None
    else:
        path = Path(file_name)
        if not path.is_file():
            raise TransportError(
                "J1587_SOURCE_UNAVAILABLE",
                f"Capture source '{file_name}' is not available.",
                "Provide a readable J1708 capture file with lines like "
                "'(0.000000) j1708 80BE70173B'.",
            )
        handle = path.open(encoding="utf-8")

    try:
        yielded = 0
        parsed_count = 0
        start_timestamp: float | None = None
        for line_number, raw_line in enumerate(handle, start=1):
            stripped = raw_line.strip()
            if not stripped:
                continue

            match = J1708_LINE_RE.match(stripped)
            if match is None:
                raise TransportError(
                    "J1587_SOURCE_INVALID",
                    f"Failed to parse J1708 capture line {line_number} in '{file_name}'.",
                    "Use lines like '(0.000000) j1708 80BE70173B' (timestamp, "
                    "literal 'j1708', then the hex-encoded message bytes).",
                )

            hex_data = match.group("data")
            if len(hex_data) % 2 != 0:
                raise TransportError(
                    "J1587_SOURCE_INVALID",
                    f"J1708 capture line {line_number} in '{file_name}' has an odd "
                    "number of hex digits.",
                    "Encode the message bytes as whole bytes (an even number of hex digits).",
                )

            timestamp = float(match.group("timestamp"))
            raw = bytes.fromhex(hex_data)
            try:
                message = parse_j1708_message(raw, timestamp=timestamp)
            except ValueError as exc:
                raise TransportError(
                    "J1587_SOURCE_INVALID",
                    f"J1708 capture line {line_number} in '{file_name}' is malformed: {exc}.",
                    "Each message needs at least a MID byte and a checksum byte, with "
                    "parameter lengths matching the J1587 PID framing rules.",
                ) from exc

            parsed_count += 1
            if parsed_count <= offset:
                continue
            if start_timestamp is None:
                start_timestamp = message.timestamp or 0.0
            if (
                seconds is not None
                and start_timestamp is not None
                and (message.timestamp or 0.0) - start_timestamp > seconds
            ):
                break

            yield message
            yielded += 1
            if max_frames is not None and yielded >= max_frames:
                break
    finally:
        if path is not None:
            handle.close()
