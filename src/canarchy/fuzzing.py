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

import math
import random
from collections.abc import Iterable, Iterator
from dataclasses import replace
from typing import Any, Literal

from canarchy.models import CanFrame

__all__ = [
    "ReplayStrategy",
    "SignalFuzzMode",
    "arbitration_id_range",
    "bitflip_payload",
    "boundary_payload",
    "mutate_replay",
    "random_payload",
    "signal_payload",
]

ReplayStrategy = Literal["timing", "payload-bitflip"]
SignalFuzzMode = Literal["in_bounds", "out_of_bounds", "boundary", "enum_gaps", "full_field"]

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
    prev_mutated_ts: float | None = None
    for frame in frames:
        if strategy == "timing":
            # Offsets in [-5ms, +5ms] keep the replay roughly recognisable
            # while still exercising downstream timing-sensitive code.
            # The result is clamped so the mutated stream remains
            # non-decreasing in time: when the proposed offset would
            # make this frame's timestamp earlier than the previous
            # mutated frame's, we float it to that previous timestamp
            # instead. Downstream replay schedulers depend on
            # monotonicity.
            offset_ms = rng.uniform(-5.0, 5.0)
            proposed = (frame.timestamp or 0.0) + offset_ms / 1000.0
            if prev_mutated_ts is not None and proposed < prev_mutated_ts:
                proposed = prev_mutated_ts
            prev_mutated_ts = proposed
            yield replace(frame, timestamp=proposed)
        else:  # payload-bitflip
            if not frame.data:
                yield frame
                continue
            bit = rng.randrange(len(frame.data) * 8)
            yield replace(frame, data=_flip_bit(frame.data, bit))


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
# DBC signal-aware mutation
# ---------------------------------------------------------------------------


def signal_payload(
    *,
    message: Any,
    signal: str,
    mode: SignalFuzzMode,
    seed: int,
    count: int,
    baseline: dict[str, int] | None = None,
) -> Iterator[bytes]:
    """Yield full-message payloads that mutate a single DBC ``signal``.

    ``message`` is a cantools message object (as returned by
    ``canarchy.dbc_runtime.load_runtime_database`` →
    ``get_message_by_name``). The generator respects the signal's bit
    layout, length, byte order, scale, offset, declared minimum /
    maximum, and choice set by working in *raw* signal space and encoding
    with ``scaling=False, strict=False`` so out-of-range values can be
    emitted without cantools rejecting them.

    Other signals are held at ``baseline`` (a mapping of signal name →
    raw value) or zero when no baseline is supplied. Every payload is a
    pure function of ``(message, signal, mode, seed, count, baseline)``.

    Modes:

    * ``in_bounds`` — ``count`` uniformly-sampled raw values inside the
      declared ``[min, max]`` range (seeded).
    * ``out_of_bounds`` — values one lsb past the declared min / max plus
      the representable type extrema, restricted to values strictly
      outside the declared range. Yields nothing for a bound whose
      just-past value is not representable.
    * ``boundary`` — declared min, max, and min / max ± 1 lsb, restricted
      to representable values.
    * ``enum_gaps`` — every representable raw value that is **not** a
      defined choice; only valid for signals with a choice set.
    * ``full_field`` — sweeps the entire representable raw field,
      ignoring the declared DBC bounds. When the field is wider than
      ``count``, emits evenly spaced samples that include both extrema.

    For the finite modes (``out_of_bounds``, ``boundary``, ``enum_gaps``,
    ``full_field``) ``count`` caps the number of payloads emitted. Raising on misuse is
    deferred to first iteration: ``count < 0``, an unknown ``signal``, an
    unknown ``mode``, or ``enum_gaps`` on a signal without choices all
    raise ``ValueError``.
    """

    if count < 0:
        raise ValueError("count must be zero or greater")

    try:
        sig = message.get_signal_by_name(signal)
    except KeyError as exc:
        message_name = getattr(message, "name", message)
        raise ValueError(f"signal {signal!r} is not defined on message {message_name!r}") from exc

    length = int(sig.length)
    is_signed = bool(sig.is_signed)
    scale = float(sig.scale) if sig.scale is not None else 1.0
    offset = float(sig.offset) if sig.offset is not None else 0.0
    raw_lo, raw_hi = _raw_signal_bounds(length, is_signed)

    if sig.minimum is not None and sig.maximum is not None and scale != 0.0:
        # Convert the declared physical bounds to raw, rounding *inward* so
        # the resulting raw interval never decodes outside [minimum, maximum]
        # for signals whose bounds are not aligned to a raw lsb. The two
        # physical endpoints map to raw endpoints `a` and `b`; a negative
        # scale flips their order, so we take ceil of the smaller (lower
        # raw edge) and floor of the larger (upper raw edge).
        a = (float(sig.minimum) - offset) / scale
        b = (float(sig.maximum) - offset) / scale
        dmin_raw = math.ceil(min(a, b))
        dmax_raw = math.floor(max(a, b))
        if dmin_raw > dmax_raw:
            # Declared range spans less than one lsb: collapse to the single
            # nearest representable raw value so the modes stay well-defined.
            dmin_raw = dmax_raw = round((a + b) / 2)
    else:
        dmin_raw, dmax_raw = raw_lo, raw_hi
    dmin_raw = max(raw_lo, min(raw_hi, dmin_raw))
    dmax_raw = max(raw_lo, min(raw_hi, dmax_raw))

    baseline_raw: dict[str, int] = {member.name: 0 for member in message.signals}
    if baseline:
        baseline_raw.update(baseline)

    emitted = 0
    for raw_value in _signal_raw_candidates(
        mode,
        sig,
        raw_lo=raw_lo,
        raw_hi=raw_hi,
        dmin_raw=dmin_raw,
        dmax_raw=dmax_raw,
        seed=seed,
        count=count,
    ):
        if emitted >= count:
            return
        values = dict(baseline_raw)
        values[signal] = int(raw_value)
        try:
            yield message.encode(values, scaling=False, strict=False)
        except Exception as exc:  # pragma: no cover - defensive
            raise ValueError(f"failed to encode message with {signal}={raw_value}: {exc}") from exc
        emitted += 1


def _raw_signal_bounds(length: int, is_signed: bool) -> tuple[int, int]:
    """Return the representable raw ``(low, high)`` for a signal field."""

    if length <= 0:
        raise ValueError(f"signal length must be positive; got {length!r}")
    if is_signed:
        return -(1 << (length - 1)), (1 << (length - 1)) - 1
    return 0, (1 << length) - 1


def _signal_raw_candidates(
    mode: SignalFuzzMode,
    sig: Any,
    *,
    raw_lo: int,
    raw_hi: int,
    dmin_raw: int,
    dmax_raw: int,
    seed: int,
    count: int,
) -> Iterator[int]:
    """Yield raw signal values for ``mode`` (capped by the caller)."""

    if mode == "in_bounds":
        rng = random.Random(seed)
        for _ in range(count):
            yield rng.randint(dmin_raw, dmax_raw)
        return
    if mode == "boundary":
        seen: set[int] = set()
        for value in (dmin_raw, dmax_raw, dmin_raw - 1, dmin_raw + 1, dmax_raw - 1, dmax_raw + 1):
            if raw_lo <= value <= raw_hi and value not in seen:
                seen.add(value)
                yield value
        return
    if mode == "out_of_bounds":
        seen = set()
        for value in (dmin_raw - 1, dmax_raw + 1, raw_lo, raw_hi):
            outside = value < dmin_raw or value > dmax_raw
            if raw_lo <= value <= raw_hi and outside and value not in seen:
                seen.add(value)
                yield value
        return
    if mode == "enum_gaps":
        choices = getattr(sig, "choices", None)
        if not choices:
            raise ValueError(
                f"signal {sig.name!r} has no choice set; enum_gaps mode is not applicable"
            )
        defined = {int(key) for key in choices}
        for value in range(raw_lo, raw_hi + 1):
            if value not in defined:
                yield value
        return
    if mode == "full_field":
        # Sweep the entire representable raw field, ignoring the declared
        # DBC bounds. When the field is larger than `count`, emit evenly
        # spaced samples that always include both extrema so coverage spans
        # the whole field rather than just its low end. Deterministic; the
        # seed is unused.
        if count <= 0:
            return
        total = raw_hi - raw_lo + 1
        if total <= count:
            yield from range(raw_lo, raw_hi + 1)
            return
        if count == 1:
            yield raw_lo
            return
        seen: set[int] = set()
        for i in range(count):
            value = raw_lo + round(i * (total - 1) / (count - 1))
            if value not in seen:
                seen.add(value)
                yield value
        return
    raise ValueError(
        f"unknown signal fuzz mode: {mode!r}. Supported: 'in_bounds', "
        "'out_of_bounds', 'boundary', 'enum_gaps', 'full_field'."
    )


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
