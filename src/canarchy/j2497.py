"""J2497 (PLC4TRUCKS) protocol helpers.

J2497 (SAE J2497, "Power Line Carrier Communications for Commercial
Vehicles", commonly "PLC4TRUCKS") carries diagnostic messages between a
tractor and its trailer(s) over the trailer power line rather than a
dedicated data bus. At the message layer it reuses the J1708/J1587 frame
format: each message is ``MID <message-data...> checksum`` where ``MID``
identifies the originating ECU (commonly a trailer ABS controller) and the
checksum byte is chosen so the byte sum of the whole message is congruent to
0 mod 256.

This module decodes captured J2497 frames into structured messages — the
source MID (resolved against a bundled trailer-oriented MID catalog where
known), the raw message-data bytes, and a checksum-valid flag. The
message-data bytes themselves follow the J1587 PID framing rules; use
``canarchy j1587 decode`` for PID-level resolution of that content.

This is a clean-room implementation of the public J2497 / J1708 framing
semantics. It reuses no code or data from hardware-oriented PLC tooling
(e.g. PLC4TRUCKSduck), which carries its own license. Live J2497 access
requires a power-line carrier modem and is out of scope; CANarchy is the
analysis layer over already-captured frames.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

from canarchy.j2497_metadata import known_mids, mid_lookup
from canarchy.models import J2497ObservationEvent
from canarchy.transport import TransportError

J2497_LINE_RE = re.compile(r"^\((?P<timestamp>\d+(?:\.\d+)?)\)\s+j2497\s+(?P<data>[0-9A-Fa-f]+)$")


@dataclass(slots=True, frozen=True)
class J2497Message:
    """A decoded J2497 frame: source MID, message data, and checksum status."""

    mid: int
    data: bytes
    checksum_valid: bool
    raw: bytes
    timestamp: float | None = None


def parse_j2497_frame(raw: bytes, *, timestamp: float | None = None) -> J2497Message:
    """Parse a raw J2497 frame (MID, message data, checksum) from ``raw`` bytes.

    J2497 reuses the J1708/J1587 message format. The message-data bytes are
    everything between the source MID and the trailing checksum byte; the
    checksum is valid when the byte sum of the whole frame is congruent to 0
    mod 256. The data is treated opaquely here (PID-level resolution is the
    job of ``canarchy j1587 decode``), so frames are not rejected for
    imperfect PID framing.
    """

    if len(raw) < 2:
        raise ValueError("a J2497 frame must contain at least a MID and checksum byte")

    checksum_valid = (sum(raw) % 256) == 0
    return J2497Message(
        mid=raw[0],
        data=bytes(raw[1:-1]),
        checksum_valid=checksum_valid,
        raw=raw,
        timestamp=timestamp,
    )


def decode_events(
    messages: Iterable[J2497Message], *, source: str = "j2497"
) -> list[J2497ObservationEvent]:
    """Flatten J2497 frames into one observation event per frame."""

    events: list[J2497ObservationEvent] = []
    for message in messages:
        meta = mid_lookup(message.mid)
        events.append(
            J2497ObservationEvent(
                mid=message.mid,
                data=message.data,
                name=meta.get("name") if meta else None,
                checksum_valid=message.checksum_valid,
                source=source,
                timestamp=message.timestamp,
            )
        )
    return events


def j2497_mids_payload() -> list[dict[str, object]]:
    """The bundled MID catalog, for ``canarchy j2497 mids``."""

    return [{"mid": mid, **mid_lookup(mid)} for mid in sorted(known_mids())]  # type: ignore[misc]


def iter_j2497_frames_from_file(
    file_name: str,
    *,
    offset: int = 0,
    max_frames: int | None = None,
    seconds: float | None = None,
) -> Iterator[J2497Message]:
    """Yield :class:`J2497Message` records from a J2497 capture file.

    Each non-blank line must read ``(timestamp) j2497 <hex>`` where ``<hex>``
    is the full raw frame (MID, message data, checksum). Malformed lines and
    missing files raise :class:`TransportError`.
    """

    if file_name == "-":
        handle = sys.stdin
        path: Path | None = None
    else:
        path = Path(file_name)
        if not path.is_file():
            raise TransportError(
                "J2497_SOURCE_UNAVAILABLE",
                f"Capture source '{file_name}' is not available.",
                "Provide a readable J2497 capture file with lines like "
                "'(0.000000) j2497 892C014A'.",
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

            match = J2497_LINE_RE.match(stripped)
            if match is None:
                raise TransportError(
                    "J2497_SOURCE_INVALID",
                    f"Failed to parse J2497 capture line {line_number} in '{file_name}'.",
                    "Use lines like '(0.000000) j2497 892C014A' (timestamp, "
                    "literal 'j2497', then the hex-encoded frame bytes).",
                )

            hex_data = match.group("data")
            if len(hex_data) % 2 != 0:
                raise TransportError(
                    "J2497_SOURCE_INVALID",
                    f"J2497 capture line {line_number} in '{file_name}' has an odd "
                    "number of hex digits.",
                    "Encode the frame bytes as whole bytes (an even number of hex digits).",
                )

            timestamp = float(match.group("timestamp"))
            raw = bytes.fromhex(hex_data)
            try:
                message = parse_j2497_frame(raw, timestamp=timestamp)
            except ValueError as exc:
                raise TransportError(
                    "J2497_SOURCE_INVALID",
                    f"J2497 capture line {line_number} in '{file_name}' is malformed: {exc}.",
                    "Each frame needs at least a MID byte and a checksum byte.",
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
