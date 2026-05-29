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
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import replace
from typing import Any, Literal

from canarchy.models import CanFrame

__all__ = [
    "ReplayStrategy",
    "SignalFuzzMode",
    "SpnFuzzMode",
    "arbitration_id_range",
    "bitflip_payload",
    "boundary_payload",
    "havoc_payload",
    "interesting_values_payload",
    "mutate_replay",
    "random_payload",
    "signal_payload",
    "splice_payload",
    "spn_payload",
]

# AFL "interesting" numeric values (signed). The 16-bit set extends the
# 8-bit set; the 32-bit set extends the 16-bit set — matching AFL's
# INTERESTING_8 / _16 / _32 tables (afl-fuzz.c).
_INTERESTING_8 = (-128, -1, 0, 1, 16, 32, 64, 100, 127, 128, 255)
_INTERESTING_16 = _INTERESTING_8 + (-32768, -129, 128, 255, 256, 512, 1000, 1024, 4096, 32767)
_INTERESTING_32 = _INTERESTING_16 + (
    -2147483648,
    -100663046,
    -32769,
    32768,
    65535,
    65536,
    100663045,
    2147483647,
)

# AFL's arithmetic mutation magnitude ceiling (ARITH_MAX).
_ARITH_MAX = 35

ReplayStrategy = Literal["timing", "payload-bitflip"]
SignalFuzzMode = Literal["in_bounds", "out_of_bounds", "boundary", "enum_gaps", "full_field"]
SpnFuzzMode = Literal["in_bounds", "not_available", "error", "out_of_bounds", "boundary"]

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
# J1939 SPN-aware mutation
# ---------------------------------------------------------------------------


def spn_payload(
    *,
    spn: int,
    mode: SpnFuzzMode,
    seed: int,
    count: int,
    pgn: int | None = None,
    pgn_length: int = 8,
    baseline: int = 0xFF,
) -> Iterator[bytes]:
    """Yield full PGN payloads that mutate a single J1939 ``spn``.

    SPN layout (byte ``start``, byte ``length``, byte order, resolution,
    offset) is resolved from the built-in J1939 metadata
    (``canarchy.j1939_metadata``). Each emitted payload is ``pgn_length``
    bytes, filled with ``baseline`` (``0xFF`` — the J1939 "not available"
    idiom) and with the targeted SPN's bytes overwritten.

    Modes target the canonical J1939 sentinels and operational bounds.
    The operational raw maximum reserves the top of the field per
    SAE J1939: ``0xFA``, ``0xFAFF``, ``0xFAFFFFFF`` for 1 / 2 / 4-byte
    SPNs, with ``0xFB..0xFD`` reserved, ``0xFE..`` error, ``0xFF..`` not
    available.

    * ``in_bounds`` — ``count`` seeded uniform samples in the operational
      range ``[0, op_max]``.
    * ``not_available`` — the all-ones not-available sentinel
      (``0xFF`` / ``0xFFFF`` / ``0xFFFFFFFF``).
    * ``error`` — the error sentinel (``0xFE`` / ``0xFEFF`` /
      ``0xFEFFFFFF``).
    * ``out_of_bounds`` — one lsb past the operational max (one lsb past
      the min is raw ``-1``, which is not representable and is skipped).
    * ``boundary`` — ``0``, ``op_max``, and the representable ``± 1 lsb``
      neighbours.

    ``count`` caps the number of payloads. ``ValueError`` is raised for an
    unknown SPN, ``count < 0``, an SPN field that does not fit
    ``pgn_length``, or an unknown ``mode`` (deferred to first iteration).
    """

    from canarchy.j1939_metadata import decodable_spns, spn_lookup

    if count < 0:
        raise ValueError("count must be zero or greater")

    meta = spn_lookup(spn)
    if meta is None:
        raise ValueError(
            f"SPN {spn} has no built-in J1939 metadata; cannot derive its layout for fuzzing"
        )
    if spn not in decodable_spns():
        raise ValueError(
            f"SPN {spn} has incomplete J1939 metadata (missing layout fields); cannot fuzz it"
        )

    spn_pgn = int(meta["pgn"])
    if pgn is not None and pgn != spn_pgn:
        raise ValueError(f"SPN {spn} belongs to PGN {spn_pgn}, not the supplied PGN {pgn}")

    start = int(meta["start"])
    width = int(meta["length"])
    byteorder = meta.get("byteorder", "little")
    if width <= 0:
        raise ValueError(f"SPN {spn} has a non-positive byte width: {width!r}")
    if start < 0 or start + width > pgn_length:
        raise ValueError(
            f"SPN {spn} occupies bytes [{start}:{start + width}], which does not fit "
            f"a {pgn_length}-byte PGN payload"
        )

    field_max = (1 << (8 * width)) - 1
    op_max = _spn_operational_max(width)
    baseline_bytes = bytes([baseline & 0xFF]) * pgn_length

    emitted = 0
    for raw in _spn_raw_candidates(
        mode, width=width, op_max=op_max, field_max=field_max, seed=seed, count=count
    ):
        if emitted >= count:
            return
        payload = bytearray(baseline_bytes)
        payload[start : start + width] = int(raw).to_bytes(width, byteorder=byteorder)
        yield bytes(payload)
        emitted += 1


def _spn_operational_max(width: int) -> int:
    """Return the J1939 operational raw maximum for a ``width``-byte SPN.

    The top of the field is reserved (``0xFB..0xFF`` in the high byte), so
    the largest valid operational raw value is ``0xFA`` followed by all
    ``0xFF`` lower bytes: ``0xFA``, ``0xFAFF``, ``0xFAFFFFFF``.
    """

    high = 0xFA << (8 * (width - 1))
    low = (1 << (8 * (width - 1))) - 1
    return high | low


def _spn_not_available_raw(width: int) -> int:
    return (1 << (8 * width)) - 1


def _spn_error_raw(width: int) -> int:
    return _spn_not_available_raw(width) - (1 << (8 * (width - 1)))


def _spn_raw_candidates(
    mode: SpnFuzzMode,
    *,
    width: int,
    op_max: int,
    field_max: int,
    seed: int,
    count: int,
) -> Iterator[int]:
    """Yield raw SPN values for ``mode`` (capped by the caller)."""

    if mode == "in_bounds":
        rng = random.Random(seed)
        for _ in range(count):
            yield rng.randint(0, op_max)
        return
    if mode == "not_available":
        yield _spn_not_available_raw(width)
        return
    if mode == "error":
        yield _spn_error_raw(width)
        return
    if mode == "boundary":
        seen: set[int] = set()
        # min - 1 lsb == -1 is not representable and is omitted.
        for value in (0, op_max, 1, op_max - 1, op_max + 1):
            if 0 <= value <= field_max and value not in seen:
                seen.add(value)
                yield value
        return
    if mode == "out_of_bounds":
        value = op_max + 1
        if value <= field_max:
            yield value
        return
    raise ValueError(
        f"unknown SPN fuzz mode: {mode!r}. Supported: 'in_bounds', "
        "'not_available', 'error', 'out_of_bounds', 'boundary'."
    )


# ---------------------------------------------------------------------------
# AFL-style mutators (havoc / splice / interesting values)
# ---------------------------------------------------------------------------


def havoc_payload(data: bytes, *, seed: int, count: int) -> Iterator[bytes]:
    """Yield ``count`` AFL-havoc variants of ``data``.

    Each variant stacks a random sequence of basic mutations on a fresh
    copy of ``data``: single-bit flips, interesting-value injection (8 /
    16 / 32-bit), arithmetic ``± [1, 35]`` at 8 / 16 / 32-bit widths,
    random byte replacement, and block deletion / insertion / overwrite —
    the operators AFL's ``havoc`` stage uses. Output length is clamped to
    64 bytes (CAN FD maximum). Deterministic for a fixed ``seed``.
    """

    if count < 0:
        raise ValueError("count must be zero or greater")
    rng = random.Random(seed)
    base = bytes(data)
    for _ in range(count):
        buf = bytearray(base)
        for _ in range(rng.randint(1, 16)):
            _havoc_mutate(buf, rng)
            if len(buf) > _MAX_DLC:
                del buf[_MAX_DLC:]
        yield bytes(buf)


def splice_payload(corpus: Sequence[bytes], *, seed: int, count: int) -> Iterator[bytes]:
    """Yield ``count`` spliced variants drawn from ``corpus``.

    Each variant picks two seeds from ``corpus`` and joins a random prefix
    of the first with a random suffix of the second. Output length is
    clamped to 64 bytes. Deterministic for a fixed ``seed``. Raises
    ``ValueError`` when ``corpus`` is empty.
    """

    if count < 0:
        raise ValueError("count must be zero or greater")
    seeds = [bytes(entry) for entry in corpus]
    if not seeds:
        raise ValueError("corpus must contain at least one payload for splicing")
    rng = random.Random(seed)
    for _ in range(count):
        left = seeds[rng.randrange(len(seeds))]
        right = seeds[rng.randrange(len(seeds))]
        cut_left = rng.randint(0, len(left))
        cut_right = rng.randint(0, len(right))
        yield (left[:cut_left] + right[cut_right:])[:_MAX_DLC]


def interesting_values_payload(*, dlc: int) -> Iterator[bytes]:
    """Yield ``dlc``-byte payloads seeding AFL "interesting" values.

    Enumerates, in a fixed order, every 8-bit interesting value at each
    byte offset, every 16-bit value at each word offset, and every 32-bit
    value at each dword offset, written little-endian over a zero
    baseline. Duplicates are suppressed. Deterministic; yields nothing for
    ``dlc == 0``.
    """

    _validate_dlc(dlc)
    if dlc == 0:
        return
    base = bytes(dlc)
    seen: set[bytes] = set()

    def _emit(offset: int, width: int, value: int) -> bytes | None:
        buf = bytearray(base)
        buf[offset : offset + width] = (value & ((1 << (8 * width)) - 1)).to_bytes(width, "little")
        candidate = bytes(buf)
        if candidate in seen:
            return None
        seen.add(candidate)
        return candidate

    for offset in range(dlc):
        for value in _INTERESTING_8:
            emitted = _emit(offset, 1, value)
            if emitted is not None:
                yield emitted
    if dlc >= 2:
        for offset in range(dlc - 1):
            for value in _INTERESTING_16:
                emitted = _emit(offset, 2, value)
                if emitted is not None:
                    yield emitted
    if dlc >= 4:
        for offset in range(dlc - 3):
            for value in _INTERESTING_32:
                emitted = _emit(offset, 4, value)
                if emitted is not None:
                    yield emitted


def _havoc_mutate(buf: bytearray, rng: random.Random) -> None:
    """Apply a single random AFL-havoc operator to ``buf`` in place.

    Operators whose preconditions are not met (e.g. a 32-bit write on a
    1-byte buffer) are no-ops for that round, mirroring AFL's stacked
    havoc loop where individual picks can be skipped.
    """

    op = rng.randint(0, 10)
    n = len(buf)
    if op == 0 and n > 0:  # single-bit flip
        bit = rng.randrange(n * 8)
        buf[bit // 8] ^= 1 << (bit % 8)
    elif op == 1 and n > 0:  # interesting 8
        buf[rng.randrange(n)] = rng.choice(_INTERESTING_8) & 0xFF
    elif op == 2 and n >= 2:  # interesting 16 (little-endian)
        pos = rng.randrange(n - 1)
        buf[pos : pos + 2] = (rng.choice(_INTERESTING_16) & 0xFFFF).to_bytes(2, "little")
    elif op == 3 and n >= 4:  # interesting 32 (little-endian)
        pos = rng.randrange(n - 3)
        buf[pos : pos + 4] = (rng.choice(_INTERESTING_32) & 0xFFFFFFFF).to_bytes(4, "little")
    elif op == 4 and n > 0:  # 8-bit arithmetic
        pos = rng.randrange(n)
        delta = rng.randint(1, _ARITH_MAX)
        buf[pos] = (buf[pos] + (delta if rng.random() < 0.5 else -delta)) & 0xFF
    elif op == 5 and n >= 2:  # 16-bit arithmetic (little-endian)
        pos = rng.randrange(n - 1)
        cur = int.from_bytes(buf[pos : pos + 2], "little")
        delta = rng.randint(1, _ARITH_MAX)
        cur = (cur + (delta if rng.random() < 0.5 else -delta)) & 0xFFFF
        buf[pos : pos + 2] = cur.to_bytes(2, "little")
    elif op == 6 and n >= 4:  # 32-bit arithmetic (little-endian)
        pos = rng.randrange(n - 3)
        cur = int.from_bytes(buf[pos : pos + 4], "little")
        delta = rng.randint(1, _ARITH_MAX)
        cur = (cur + (delta if rng.random() < 0.5 else -delta)) & 0xFFFFFFFF
        buf[pos : pos + 4] = cur.to_bytes(4, "little")
    elif op == 7 and n > 0:  # random byte replacement
        buf[rng.randrange(n)] ^= rng.randint(1, 255)
    elif op == 8 and n > 1:  # block deletion
        del_len = rng.randint(1, n - 1)
        start = rng.randrange(n - del_len + 1)
        del buf[start : start + del_len]
    elif op == 9:  # block insertion (cloned or random bytes)
        ins_len = rng.randint(1, 8)
        if n > 0 and rng.random() < 0.5:
            src = rng.randrange(n)
            chunk = bytes(buf[src : src + ins_len]) or bytes([rng.randint(0, 255)])
        else:
            chunk = bytes(rng.randint(0, 255) for _ in range(ins_len))
        pos = rng.randrange(n + 1)
        buf[pos:pos] = chunk
    elif op == 10 and n > 0:  # block overwrite (constant fill)
        ov_len = rng.randint(1, n)
        start = rng.randrange(n - ov_len + 1)
        buf[start : start + ov_len] = bytes([rng.randint(0, 255)]) * ov_len


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
