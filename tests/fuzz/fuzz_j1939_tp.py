#!/usr/bin/env python3
"""Atheris fuzz harness for the J1939 transport-protocol reassembler.

Targets ``transport_protocol_sessions`` on the default J1939 decoder (the
TP.CM / TP.DT BAM and RTS/CTS reassembler). Arbitrary bytes are carved
into a sequence of extended-id CAN frames and fed to the reassembler,
which is expected to consume any frame stream without raising.

Run after ``pip install .[fuzz]``::

    python tests/fuzz/fuzz_j1939_tp.py -max_total_time=30 \\
        tests/fuzz/corpora/j1939_tp
"""

from __future__ import annotations

import sys

from canarchy.j1939_decoder import get_j1939_decoder
from canarchy.models import CanFrame


def _frames_from_bytes(data: bytes) -> list[CanFrame]:
    """Carve fuzzer bytes into extended-id CAN frames.

    Record layout: 4 bytes big-endian arbitration id (masked to 29 bits),
    1 byte length (mod 9 → classic 0..8), then that many payload bytes.
    """
    frames: list[CanFrame] = []
    index = 0
    length = len(data)
    while index + 5 <= length:
        arbitration_id = int.from_bytes(data[index : index + 4], "big") & 0x1FFFFFFF
        dlc = data[index + 4] % 9
        index += 5
        payload = data[index : index + dlc]
        index += dlc
        frames.append(CanFrame(arbitration_id=arbitration_id, data=payload, is_extended_id=True))
    return frames


_DECODER = get_j1939_decoder()


def TestOneInput(data: bytes) -> None:
    _DECODER.transport_protocol_sessions(_frames_from_bytes(data))


def _main() -> None:
    import atheris

    atheris.instrument_all()
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    _main()
