"""PCAP/PCAPNG CAN frame reader using dpkt."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

from canarchy.models import CanFrame

DLT_CAN_SOCKETCAN = 227

CAN_EFF_FLAG = 0x80000000
CAN_RTR_FLAG = 0x40000000
CAN_ERR_FLAG = 0x20000000

CANFD_BRS = 0x01  # bit 0: bit rate switch
CANFD_ESI = 0x02  # bit 1: error state indicator
CANFD_FDF = 0x04  # bit 2: FD format indicator

PCAP_MAGICS = frozenset(
    {
        b"\xd4\xc3\xb2\xa1",
        b"\xa1\xb2\xc3\xd4",
        b"\x4c\x3b\x2a\x1d",
        b"\xa1\xb2\x3c\x4d",
        b"\x1a\xc3\xd3\x4c",
    }
)


def sniff_is_pcap(data: bytes) -> bool:
    return len(data) >= 4 and data[:4] in PCAP_MAGICS


def _parse_socketcan_buf(buf: bytes, *, timestamp: float) -> CanFrame:
    if len(buf) < 8:
        raise ValueError("buffer too short for CAN SocketCAN frame")

    can_id = int.from_bytes(buf[0:4], "little", signed=False)
    is_extended = bool(can_id & CAN_EFF_FLAG)
    is_remote = bool(can_id & CAN_RTR_FLAG)
    is_error = bool(can_id & CAN_ERR_FLAG)
    arbitration_id = can_id & 0x1FFFFFFF

    if is_error:
        return CanFrame(
            arbitration_id=arbitration_id,
            data=b"",
            timestamp=timestamp,
            is_extended_id=is_extended,
            is_remote_frame=False,
            is_error_frame=True,
        )

    dlc = buf[4]
    flags = buf[5] if len(buf) > 5 else 0
    is_fd = bool(flags & CANFD_FDF)
    bitrate_switch = bool(flags & CANFD_BRS)
    error_state_indicator = bool(flags & CANFD_ESI)

    if is_remote:
        return CanFrame(
            arbitration_id=arbitration_id,
            data=b"",
            timestamp=timestamp,
            is_extended_id=is_extended,
            is_remote_frame=True,
        )

    if is_fd:
        data = buf[8 : 8 + min(dlc, 64)]
        return CanFrame(
            arbitration_id=arbitration_id,
            data=data,
            timestamp=timestamp,
            is_extended_id=is_extended,
            frame_format="can_fd",
            bitrate_switch=bitrate_switch,
            error_state_indicator=error_state_indicator,
        )

    data = buf[8 : 8 + min(dlc, 8)]
    return CanFrame(
        arbitration_id=arbitration_id,
        data=data,
        timestamp=timestamp,
        is_extended_id=is_extended,
    )


def iter_pcap_file(
    path: Path,
    *,
    offset: int = 0,
    max_frames: int | None = None,
    seconds: float | None = None,
) -> Iterator[CanFrame]:
    from canarchy.transport import TransportError

    import dpkt

    skipped = 0
    yielded = 0
    start_timestamp: float | None = None

    with path.open("rb") as f:
        try:
            reader = dpkt.pcap.UniversalReader(f)
        except Exception as exc:
            raise TransportError(
                "CAPTURE_SOURCE_INVALID",
                f"Capture source '{path}' could not be read as pcap/pcapng.",
                "Verify the file is a valid pcap or pcapng file.",
            ) from exc

        linktype = reader.datalink()

    if linktype != DLT_CAN_SOCKETCAN:
        raise TransportError(
            "CAPTURE_FORMAT_UNSUPPORTED",
            f"Capture source '{path}' uses unsupported pcap linktype {linktype}.",
            "Only CAN SocketCAN (DLT 227) captures are supported.",
        )

    # Re-open for iteration (UniversalReader consumes the file object)
    with path.open("rb") as f:
        reader = dpkt.pcap.UniversalReader(f)
        for timestamp, buf in reader:
            if len(buf) < 8:
                continue

            try:
                frame = _parse_socketcan_buf(buf, timestamp=timestamp)
            except (ValueError, IndexError):
                continue

            if offset > 0 and skipped < offset:
                skipped += 1
                continue

            if seconds is not None:
                if start_timestamp is None:
                    start_timestamp = frame.timestamp
                if frame.timestamp is not None and start_timestamp is not None:
                    if frame.timestamp - start_timestamp > seconds:
                        break

            yield frame
            yielded += 1

            if max_frames is not None and yielded >= max_frames:
                break


def pcap_metadata(path: Path) -> dict[str, object]:
    """Return frame_count, duration_seconds, unique_ids for a pcap file."""
    from canarchy.transport import TransportError

    import dpkt

    frame_count = 0
    unique_ids: set[int] = set()
    first_ts: float | None = None
    last_ts: float | None = None

    with path.open("rb") as f:
        try:
            reader = dpkt.pcap.UniversalReader(f)
        except Exception:
            raise TransportError(
                "CAPTURE_SOURCE_INVALID",
                f"Capture source '{path}' could not be read as pcap/pcapng.",
                "Verify the file is a valid pcap or pcapng file.",
            ) from None

        linktype = reader.datalink()
        if linktype != DLT_CAN_SOCKETCAN:
            raise TransportError(
                "CAPTURE_FORMAT_UNSUPPORTED",
                f"Capture source '{path}' uses unsupported pcap linktype {linktype}.",
                "Only CAN SocketCAN (DLT 227) captures are supported.",
            )

        for timestamp, buf in reader:
            if len(buf) < 8:
                continue
            can_id = int.from_bytes(buf[0:4], "little", signed=False)
            arbitration_id = can_id & 0x1FFFFFFF
            unique_ids.add(arbitration_id)
            if first_ts is None:
                first_ts = timestamp
            last_ts = timestamp
            frame_count += 1

    if first_ts is None or last_ts is None:
        raise TransportError(
            "CAPTURE_SOURCE_INVALID",
            f"Capture source '{path}' contains no valid frames.",
            "Verify the file contains CAN SocketCAN frames.",
        )

    return {
        "frame_count": frame_count,
        "duration_seconds": max(0.0, last_ts - first_ts),
        "unique_ids": len(unique_ids),
        "first_timestamp": first_ts,
        "last_timestamp": last_ts,
    }
