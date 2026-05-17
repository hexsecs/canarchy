"""Pure-function mutation generators for active-transmit fuzzing.

Every generator in this module is deterministic given a seed, performs
no transport / file / wall-clock side effects, and returns plain
Python iterables so the call site can decide pacing, transmission, or
dry-run capture. The CLI exposure lives in `canarchy.cli`; the safety
gates live in the active-transmit safety design
(`docs/design/active-transmit-safety.md`).

Design constraints (per :issue:`310`):

* deterministic for the same seed
* no transport / no file I/O / no time.sleep / no monotonic
* small, composable functions — each generator is independently
  testable with no shared state
"""

from __future__ import annotations

import random
from collections.abc import Iterable, Iterator
from dataclasses import replace
from typing import Literal

from canarchy.models import CanFrame

__all__ = [
    "ReplayStrategy",
    "arbitration_id_range",
    "bitflip_payload",
    "boundary_payload",
    "mutate_replay",
    "random_payload",
]

ReplayStrategy = Literal["timing", "payload-bitflip"]

# Maximum payload length the generators emit. Classic CAN tops out at 8;
# CAN FD allows 64. We use 64 as the upper bound to be future-proof.
_MAX_DLC = 64


# ---------------------------------------------------------------------------
# Payload mutators
# ---------------------------------------------------------------------------


def bitflip_payload(data: bytes, *, seed: int, max_mutations: int) -> Iterator[bytes]:
    """Yield up to ``max_mutations`` single-bit-flip variants of ``data``.

    The first ``len(data) * 8`` outputs walk every bit position in order
    (lowest-byte, lowest-bit first). After the walk completes, additional
    outputs flip a single random bit drawn from a seeded RNG. The walk
    order is fixed; the post-walk choices are seeded so the same
    ``(seed, max_mutations)`` pair always yields the same sequence.

    Returns no variants when ``data`` is empty or ``max_mutations`` is
    zero.
    """

    if max_mutations < 0:
        raise ValueError("max_mutations must be zero or greater")
    if not data:
        return
    bit_count = len(data) * 8
    rng = random.Random(seed)
    emitted = 0
    # Phase 1 — exhaustive single-bit walk.
    for bit in range(bit_count):
        if emitted >= max_mutations:
            return
        yield _flip_bit(data, bit)
        emitted += 1
    # Phase 2 — seeded single-bit picks. Duplicates with phase 1 are
    # allowed; callers asking for more than `bit_count` mutations already
    # accepted that they will see repeats.
    while emitted < max_mutations:
        yield _flip_bit(data, rng.randrange(bit_count))
        emitted += 1


def random_payload(*, dlc: int, seed: int, count: int) -> Iterator[bytes]:
    """Yield ``count`` random payloads of length ``dlc`` bytes."""

    if count < 0:
        raise ValueError("count must be zero or greater")
    _validate_dlc(dlc)
    rng = random.Random(seed)
    for _ in range(count):
        yield bytes(rng.randrange(0, 256) for _ in range(dlc))


def boundary_payload(*, dlc: int) -> Iterator[bytes]:
    """Yield canonical boundary payloads for the given ``dlc``.

    Order is fixed and deterministic:

    1. all-zero (``00 00 ... 00``)
    2. all-one (``FF FF ... FF``)
    3. alternating ``AA 55 AA 55 ...``
    4. alternating ``55 AA 55 AA ...``
    5. walking-one: ``dlc * 8`` payloads each with exactly one bit set
    6. walking-zero: ``dlc * 8`` payloads each with exactly one bit
       cleared from the all-ones baseline
    """

    _validate_dlc(dlc)
    if dlc == 0:
        # An empty payload still has one canonical value; emit it once.
        yield b""
        return
    yield bytes(dlc)
    yield bytes([0xFF] * dlc)
    yield bytes((0xAA if i % 2 == 0 else 0x55) for i in range(dlc))
    yield bytes((0x55 if i % 2 == 0 else 0xAA) for i in range(dlc))
    zero = bytes(dlc)
    for bit in range(dlc * 8):
        yield _flip_bit(zero, bit)
    ones = bytes([0xFF] * dlc)
    for bit in range(dlc * 8):
        yield _flip_bit(ones, bit)


# ---------------------------------------------------------------------------
# Replay mutators
# ---------------------------------------------------------------------------


def mutate_replay(
    frames: Iterable[CanFrame], *, strategy: ReplayStrategy, seed: int
) -> Iterator[CanFrame]:
    """Yield a mutated stream of ``frames`` according to ``strategy``.

    Two strategies are supported:

    * ``timing`` — perturbs each frame's timestamp by a small seeded
      offset in milliseconds; arbitration id and payload are preserved.
    * ``payload-bitflip`` — flips exactly one seeded bit in each
      non-empty payload; timestamp and arbitration id are preserved.

    Both strategies are pure functions of (input frame, seed, index).
    The input iterable is consumed once and is not materialised.
    """

    if strategy not in ("timing", "payload-bitflip"):
        raise ValueError(
            f"Unknown replay strategy: {strategy!r}. Supported: 'timing', 'payload-bitflip'."
        )
    rng = random.Random(seed)
    for index, frame in enumerate(frames):
        if strategy == "timing":
            # Offsets in [-5ms, +5ms] keep the replay roughly recognisable
            # while still exercising downstream timing-sensitive code.
            offset_ms = rng.uniform(-5.0, 5.0)
            new_ts = (frame.timestamp or 0.0) + offset_ms / 1000.0
            yield replace(frame, timestamp=new_ts)
        else:  # payload-bitflip
            if not frame.data:
                yield frame
                continue
            bit = rng.randrange(len(frame.data) * 8)
            yield replace(frame, data=_flip_bit(frame.data, bit))
        # `index` only exists to keep the seeded RNG advancing in a
        # predictable way per frame; suppress linter noise about an
        # unused name without changing semantics.
        del index


# ---------------------------------------------------------------------------
# Arbitration-ID iteration
# ---------------------------------------------------------------------------


def arbitration_id_range(start: int, end: int, *, extended: bool, step: int = 1) -> Iterator[int]:
    """Yield arbitration IDs in ``[start, end]`` with the given ``step``.

    Both bounds are inclusive. Validates that ``start`` and ``end`` fit
    in the 11-bit (standard) or 29-bit (extended) address space.
    """

    if start < 0 or end < 0:
        raise ValueError("arbitration IDs must be non-negative")
    if step <= 0:
        raise ValueError("step must be a positive integer")
    if end < start:
        raise ValueError("end must be greater than or equal to start")
    max_id = 0x1FFFFFFF if extended else 0x7FF
    if end > max_id:
        kind = "extended" if extended else "standard"
        raise ValueError(f"end {end!r} exceeds the {kind} CAN address range (max {hex(max_id)})")
    current = start
    while current <= end:
        yield current
        current += step


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _flip_bit(data: bytes, bit: int) -> bytes:
    """Return a copy of ``data`` with ``bit`` toggled.

    Bit numbering is little-endian: bit 0 is the low bit of the first
    byte. Bit ``len(data) * 8 - 1`` is the high bit of the last byte.
    """

    byte_index, bit_offset = divmod(bit, 8)
    mutated = bytearray(data)
    mutated[byte_index] ^= 1 << bit_offset
    return bytes(mutated)


def _validate_dlc(dlc: int) -> None:
    if dlc < 0 or dlc > _MAX_DLC:
        raise ValueError(f"dlc must be in [0, {_MAX_DLC}]; got {dlc!r}")
