#!/usr/bin/env python3
"""Atheris fuzz harness for the ISO-TP reassembler.

Targets ``canarchy.uds.reassemble_uds_pdus`` (the reassembler behind
``uds scan`` / ``uds trace``). Arbitrary bytes are carved into a sequence
of CAN frames and fed to the reassembler, which is expected to consume
any frame stream without raising.

Run after ``pip install .[fuzz]``::

    python tests/fuzz/fuzz_isotp_reassembly.py -max_total_time=30 \\
        tests/fuzz/corpora/isotp
"""

from __future__ import annotations

import sys

from canarchy.models import CanFrame
from canarchy.uds import reassemble_uds_pdus


def _frames_from_bytes(data: bytes) -> list[CanFrame]:
    """Carve fuzzer bytes into CAN frames.

    Record layout: 4 bytes big-endian arbitration id (masked to 29 bits),
    1 byte length (taken mod 9 → classic 0..8), then that many payload
    bytes. Trailing bytes too short for a full record are ignored.
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


def TestOneInput(data: bytes) -> None:
    reassemble_uds_pdus(_frames_from_bytes(data))


def _main() -> None:
    import atheris

    atheris.instrument_all()
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    _main()
