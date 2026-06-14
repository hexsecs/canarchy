"""cannelloni wire-format codec for CAN-over-UDP interop.

[cannelloni](https://github.com/mguentner/cannelloni) tunnels SocketCAN frames
over UDP/TCP/SCTP. CANarchy speaks its UDP datagram framing so captures can be
sent to, or decoded from, cannelloni endpoints such as the UTHP / TCAT
appliances' remote-bus setups.

Wire format (version 2), all multi-byte integers big-endian:

    datagram = header frame*
    header   = version(1) op_code(1) seq_no(1) count(2)
    frame    = can_id(4) len(1) [flags(1) if CAN FD] data(dlc bytes unless RTR)

``can_id`` carries the Linux SocketCAN flag bits (EFF / RTR / ERR) in its high
bits. ``len`` stores the data length; the ``0x80`` bit marks a CAN FD frame,
which is followed by a one-byte flags field (BRS / ESI).

This module is pure (codec) plus a thin UDP socket sender; it opens no live
hardware. The sender honours the caller's active-transmit gating.
"""

from __future__ import annotations

import socket
import struct
from dataclasses import dataclass

from canarchy.models import CanFrame

CANNELLONI_VERSION = 2

OP_DATA = 0
OP_ACK = 1
OP_NACK = 2

# Linux SocketCAN can_id flag bits.
_CAN_EFF_FLAG = 0x80000000
_CAN_RTR_FLAG = 0x40000000
_CAN_ERR_FLAG = 0x20000000
_CAN_EFF_MASK = 0x1FFFFFFF
_CAN_SFF_MASK = 0x000007FF

# cannelloni len-byte / FD flag bits.
_CANFD_FRAME = 0x80
_CANFD_BRS = 0x01
_CANFD_ESI = 0x02

_HEADER = struct.Struct(">BBBH")  # version, op_code, seq_no, count
_MAX_COUNT = 0xFFFF

# Maximum CAN data lengths the wire `len` byte may declare.
_MAX_CLASSIC_DLC = 8
_MAX_FD_DLC = 64

# cannelloni's default receive-buffer / MTU. A stock peer drops datagrams
# larger than this, so chunking caps encoded byte size by default.
DEFAULT_MTU = 1500


class CannelloniError(Exception):
    """Raised when a cannelloni datagram is malformed or cannot be built."""

    def __init__(self, code: str, message: str, hint: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint


@dataclass(slots=True, frozen=True)
class CannelloniPacket:
    version: int
    op_code: int
    seq_no: int
    frames: tuple[CanFrame, ...]


def _frame_to_can_id(frame: CanFrame) -> int:
    mask = _CAN_EFF_MASK if frame.is_extended_id else _CAN_SFF_MASK
    can_id = frame.arbitration_id & mask
    if frame.is_extended_id:
        can_id |= _CAN_EFF_FLAG
    if frame.is_remote_frame:
        can_id |= _CAN_RTR_FLAG
    if frame.is_error_frame:
        can_id |= _CAN_ERR_FLAG
    return can_id


def _can_id_to_fields(can_id: int) -> tuple[int, bool, bool, bool]:
    extended = bool(can_id & _CAN_EFF_FLAG)
    remote = bool(can_id & _CAN_RTR_FLAG)
    error = bool(can_id & _CAN_ERR_FLAG)
    mask = _CAN_EFF_MASK if extended else _CAN_SFF_MASK
    return can_id & mask, extended, remote, error


def encode_frame(frame: CanFrame) -> bytes:
    """Encode a single CAN frame in cannelloni wire form."""
    out = bytearray(struct.pack(">I", _frame_to_can_id(frame)))
    is_fd = frame.frame_format == "can_fd"
    length = len(frame.data)
    out.append(length | _CANFD_FRAME if is_fd else length)
    if is_fd:
        flags = 0
        if frame.bitrate_switch:
            flags |= _CANFD_BRS
        if frame.error_state_indicator:
            flags |= _CANFD_ESI
        out.append(flags)
    if not frame.is_remote_frame:
        out += frame.data
    return bytes(out)


def encode_packet(
    frames: list[CanFrame] | tuple[CanFrame, ...],
    *,
    seq_no: int = 0,
    op_code: int = OP_DATA,
) -> bytes:
    """Encode frames into one cannelloni UDP datagram."""
    if len(frames) > _MAX_COUNT:
        raise CannelloniError(
            code="CANNELLONI_TOO_MANY_FRAMES",
            message=f"A cannelloni datagram holds at most {_MAX_COUNT} frames; got {len(frames)}.",
            hint="Chunk the frames (e.g. --max-count) into multiple datagrams.",
        )
    body = b"".join(encode_frame(frame) for frame in frames)
    return _HEADER.pack(CANNELLONI_VERSION, op_code & 0xFF, seq_no & 0xFF, len(frames)) + body


def encode_packets(
    frames: list[CanFrame],
    *,
    seq_no: int = 0,
    max_count: int = _MAX_COUNT,
    max_bytes: int | None = DEFAULT_MTU,
) -> list[bytes]:
    """Encode frames into one or more datagrams.

    Each datagram holds at most ``max_count`` frames and, when ``max_bytes`` is
    set (default :data:`DEFAULT_MTU`), at most that many encoded bytes so a
    stock cannelloni peer's MTU/receive buffer is not overrun by, for example,
    full-size CAN FD frames. ``max_bytes=None`` disables the byte cap. A single
    frame whose encoding already exceeds ``max_bytes`` is still emitted alone.
    """
    if max_count < 1:
        raise CannelloniError(
            code="CANNELLONI_INVALID_MAX_COUNT",
            message="max_count must be at least 1.",
            hint="Pass a positive --max-count.",
        )

    datagrams: list[bytes] = []
    chunk: list[CanFrame] = []
    chunk_bytes = _HEADER.size

    def _flush() -> None:
        nonlocal chunk, chunk_bytes
        if chunk:
            datagrams.append(encode_packet(chunk, seq_no=(seq_no + len(datagrams)) & 0xFF))
            chunk = []
            chunk_bytes = _HEADER.size

    for frame in frames:
        frame_size = len(encode_frame(frame))
        over_count = len(chunk) >= max_count
        over_bytes = max_bytes is not None and chunk and chunk_bytes + frame_size > max_bytes
        if over_count or over_bytes:
            _flush()
        chunk.append(frame)
        chunk_bytes += frame_size
    _flush()
    return datagrams


def _decode_frame(data: bytes, offset: int) -> tuple[CanFrame, int]:
    if offset + 5 > len(data):
        raise CannelloniError(
            code="CANNELLONI_TRUNCATED",
            message="cannelloni frame header is truncated.",
            hint="The datagram ended mid-frame; confirm the source is a valid cannelloni stream.",
        )
    (can_id,) = struct.unpack_from(">I", data, offset)
    length_byte = data[offset + 4]
    offset += 5
    is_fd = bool(length_byte & _CANFD_FRAME)
    dlc = length_byte & ~_CANFD_FRAME
    max_dlc = _MAX_FD_DLC if is_fd else _MAX_CLASSIC_DLC
    if dlc > max_dlc:
        raise CannelloniError(
            code="CANNELLONI_INVALID_DLC",
            message=(
                f"cannelloni frame declares data length {dlc}, exceeding the "
                f"{'CAN FD' if is_fd else 'classic CAN'} maximum of {max_dlc}."
            ),
            hint="Confirm the source is a valid cannelloni stream.",
        )
    bitrate_switch = error_state_indicator = False
    if is_fd:
        if offset >= len(data):
            raise CannelloniError(
                code="CANNELLONI_TRUNCATED",
                message="cannelloni CAN FD flags byte is missing.",
                hint="Confirm the source is a valid cannelloni stream.",
            )
        flags = data[offset]
        offset += 1
        bitrate_switch = bool(flags & _CANFD_BRS)
        error_state_indicator = bool(flags & _CANFD_ESI)

    arbitration_id, extended, remote, error = _can_id_to_fields(can_id)
    payload = b""
    if not remote:
        if offset + dlc > len(data):
            raise CannelloniError(
                code="CANNELLONI_TRUNCATED",
                message=f"cannelloni frame payload is truncated (need {dlc} data bytes).",
                hint="Confirm the source is a valid cannelloni stream.",
            )
        payload = bytes(data[offset : offset + dlc])
        offset += dlc

    frame = CanFrame(
        arbitration_id=arbitration_id,
        data=payload,
        is_extended_id=extended,
        is_remote_frame=remote,
        is_error_frame=error,
        bitrate_switch=bitrate_switch,
        error_state_indicator=error_state_indicator,
        frame_format="can_fd" if is_fd else "can",
    )
    return frame, offset


def decode_packet(data: bytes) -> tuple[CannelloniPacket, int]:
    """Decode one cannelloni datagram from the front of ``data``.

    Returns the packet and the offset past it, so concatenated datagrams can be
    decoded sequentially.
    """
    if len(data) < _HEADER.size:
        raise CannelloniError(
            code="CANNELLONI_TRUNCATED",
            message="cannelloni datagram is shorter than its 5-byte header.",
            hint="Confirm the input is raw cannelloni datagram bytes.",
        )
    version, op_code, seq_no, count = _HEADER.unpack_from(data, 0)
    if version != CANNELLONI_VERSION:
        raise CannelloniError(
            code="CANNELLONI_VERSION_UNSUPPORTED",
            message=f"Unsupported cannelloni version {version}; expected {CANNELLONI_VERSION}.",
            hint="CANarchy speaks cannelloni wire version 2.",
        )
    offset = _HEADER.size
    frames: list[CanFrame] = []
    for _ in range(count):
        frame, offset = _decode_frame(data, offset)
        frames.append(frame)
    return CannelloniPacket(version, op_code, seq_no, tuple(frames)), offset


def decode_stream(data: bytes) -> list[CannelloniPacket]:
    """Decode one or more concatenated cannelloni datagrams from ``data``."""
    packets: list[CannelloniPacket] = []
    offset = 0
    total = len(data)
    while offset < total:
        packet, consumed = decode_packet(data[offset:])
        packets.append(packet)
        offset += consumed
    return packets


def frames_from_bytes(data: bytes) -> list[CanFrame]:
    """Decode every CAN frame from one or more concatenated datagrams."""
    frames: list[CanFrame] = []
    for packet in decode_stream(data):
        frames.extend(packet.frames)
    return frames


def send_frames_udp(
    host: str,
    port: int,
    frames: list[CanFrame],
    *,
    seq_no: int = 0,
    max_count: int = _MAX_COUNT,
    sock: socket.socket | None = None,
) -> list[bytes]:
    """Send frames to ``host:port`` as cannelloni UDP datagrams.

    Returns the datagrams that were sent. A caller-supplied ``sock`` is used as
    is (and not closed); otherwise a transient UDP socket is opened and closed.
    """
    datagrams = encode_packets(frames, seq_no=seq_no, max_count=max_count)
    owned = sock is None
    udp = sock or socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        for datagram in datagrams:
            udp.sendto(datagram, (host, port))
    finally:
        if owned:
            udp.close()
    return datagrams
