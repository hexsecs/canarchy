"""Tests for the pure-function fuzzing engine (`canarchy.fuzzing`)."""

from __future__ import annotations

import pytest

from canarchy import fuzzing
from canarchy.models import CanFrame


# ---------------------------------------------------------------------------
# bitflip_payload
# ---------------------------------------------------------------------------


def _hamming(a: bytes, b: bytes) -> int:
    """Number of differing bits between two equal-length byte strings."""
    assert len(a) == len(b)
    diff = 0
    for x, y in zip(a, b, strict=True):
        diff += bin(x ^ y).count("1")
    return diff


def test_bitflip_payload_walks_every_bit_exactly_once_within_walk_phase():
    data = b"\x00\x00\x00\x00"
    variants = list(fuzzing.bitflip_payload(data, seed=0, max_mutations=len(data) * 8))
    assert len(variants) == len(data) * 8
    # Every walk-phase output differs from the input in exactly one bit.
    for variant in variants:
        assert _hamming(variant, data) == 1
    # And every bit position is covered exactly once.
    bit_positions = {
        next(i for i in range(len(data) * 8) if (variant[i // 8] >> (i % 8)) & 1)
        for variant in variants
    }
    assert bit_positions == set(range(len(data) * 8))


def test_bitflip_payload_is_deterministic_for_same_seed():
    data = b"\xaa\xbb\xcc"
    out_a = list(fuzzing.bitflip_payload(data, seed=42, max_mutations=64))
    out_b = list(fuzzing.bitflip_payload(data, seed=42, max_mutations=64))
    assert out_a == out_b


def test_bitflip_payload_different_seeds_diverge_after_walk_phase():
    data = b"\x00\x00"  # 16-bit walk, then seeded picks
    out_a = list(fuzzing.bitflip_payload(data, seed=1, max_mutations=32))
    out_b = list(fuzzing.bitflip_payload(data, seed=2, max_mutations=32))
    walk = len(data) * 8
    # Walk phase identical regardless of seed.
    assert out_a[:walk] == out_b[:walk]
    # Post-walk phase diverges. (Two seeds picking from 16 positions
    # might collide on a single sample; check the full tail.)
    assert out_a[walk:] != out_b[walk:]


def test_bitflip_payload_empty_or_zero_yields_nothing():
    assert list(fuzzing.bitflip_payload(b"", seed=0, max_mutations=10)) == []
    assert list(fuzzing.bitflip_payload(b"\x00", seed=0, max_mutations=0)) == []


def test_bitflip_payload_negative_max_mutations_rejected():
    with pytest.raises(ValueError):
        list(fuzzing.bitflip_payload(b"\x00", seed=0, max_mutations=-1))


# ---------------------------------------------------------------------------
# random_payload
# ---------------------------------------------------------------------------


def test_random_payload_count_and_length_match_request():
    out = list(fuzzing.random_payload(dlc=4, seed=7, count=10))
    assert len(out) == 10
    assert all(len(p) == 4 for p in out)


def test_random_payload_is_deterministic_for_same_seed():
    a = list(fuzzing.random_payload(dlc=8, seed=99, count=20))
    b = list(fuzzing.random_payload(dlc=8, seed=99, count=20))
    assert a == b


def test_random_payload_different_seeds_diverge():
    a = list(fuzzing.random_payload(dlc=8, seed=1, count=5))
    b = list(fuzzing.random_payload(dlc=8, seed=2, count=5))
    assert a != b


def test_random_payload_dlc_zero_yields_empty_bytes():
    out = list(fuzzing.random_payload(dlc=0, seed=0, count=3))
    assert out == [b"", b"", b""]


def test_random_payload_count_zero_yields_nothing():
    assert list(fuzzing.random_payload(dlc=8, seed=0, count=0)) == []


def test_random_payload_invalid_dlc_rejected():
    with pytest.raises(ValueError):
        list(fuzzing.random_payload(dlc=-1, seed=0, count=1))
    with pytest.raises(ValueError):
        list(fuzzing.random_payload(dlc=65, seed=0, count=1))


def test_random_payload_negative_count_rejected():
    with pytest.raises(ValueError):
        list(fuzzing.random_payload(dlc=4, seed=0, count=-1))


# ---------------------------------------------------------------------------
# boundary_payload
# ---------------------------------------------------------------------------


def test_boundary_payload_includes_canonical_patterns():
    out = list(fuzzing.boundary_payload(dlc=4))
    # First four entries are the canonical patterns in a fixed order.
    assert out[0] == b"\x00\x00\x00\x00"
    assert out[1] == b"\xff\xff\xff\xff"
    assert out[2] == b"\xaa\x55\xaa\x55"
    assert out[3] == b"\x55\xaa\x55\xaa"


def test_boundary_payload_walking_one_and_walking_zero_are_complete():
    dlc = 4
    out = list(fuzzing.boundary_payload(dlc=dlc))
    bit_count = dlc * 8
    walking_one = out[4 : 4 + bit_count]
    walking_zero = out[4 + bit_count : 4 + 2 * bit_count]
    assert len(walking_one) == bit_count
    assert len(walking_zero) == bit_count
    # Each walking-one variant has exactly one set bit.
    assert all(_hamming(v, b"\x00" * dlc) == 1 for v in walking_one)
    # Each walking-zero variant has exactly one cleared bit relative to 0xFF.
    ones = b"\xff" * dlc
    assert all(_hamming(v, ones) == 1 for v in walking_zero)


def test_boundary_payload_dlc_zero_yields_single_empty_payload():
    out = list(fuzzing.boundary_payload(dlc=0))
    assert out == [b""]


def test_boundary_payload_is_deterministic():
    a = list(fuzzing.boundary_payload(dlc=4))
    b = list(fuzzing.boundary_payload(dlc=4))
    assert a == b


# ---------------------------------------------------------------------------
# mutate_replay
# ---------------------------------------------------------------------------


def _frames(*payloads: bytes) -> list[CanFrame]:
    return [
        CanFrame(arbitration_id=0x100 + i, data=payload, timestamp=float(i))
        for i, payload in enumerate(payloads)
    ]


def test_mutate_replay_timing_preserves_payload_and_id():
    frames = _frames(b"\x01", b"\x02", b"\x03")
    out = list(fuzzing.mutate_replay(frames, strategy="timing", seed=0))
    assert len(out) == 3
    for original, mutated in zip(frames, out, strict=True):
        assert mutated.data == original.data
        assert mutated.arbitration_id == original.arbitration_id
        # Timestamp must shift by at most 5ms in either direction.
        assert abs((mutated.timestamp or 0.0) - (original.timestamp or 0.0)) <= 5e-3 + 1e-9


def test_mutate_replay_payload_bitflip_changes_exactly_one_bit():
    frames = _frames(b"\xaa\x55", b"\xff\x00")
    out = list(fuzzing.mutate_replay(frames, strategy="payload-bitflip", seed=0))
    for original, mutated in zip(frames, out, strict=True):
        assert mutated.arbitration_id == original.arbitration_id
        assert mutated.timestamp == original.timestamp
        assert _hamming(mutated.data, original.data) == 1


def test_mutate_replay_payload_bitflip_passes_empty_frames_through():
    frames = [CanFrame(arbitration_id=0x100, data=b"")]
    out = list(fuzzing.mutate_replay(frames, strategy="payload-bitflip", seed=0))
    assert out == frames


def test_mutate_replay_is_deterministic_for_same_seed():
    frames = _frames(b"\x01\x02", b"\x03\x04")
    a = list(fuzzing.mutate_replay(frames, strategy="timing", seed=5))
    b = list(fuzzing.mutate_replay(frames, strategy="timing", seed=5))
    assert [(f.arbitration_id, f.data, f.timestamp) for f in a] == [
        (f.arbitration_id, f.data, f.timestamp) for f in b
    ]


def test_mutate_replay_unknown_strategy_rejected():
    with pytest.raises(ValueError):
        list(fuzzing.mutate_replay(_frames(b"\x01"), strategy="nope", seed=0))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# arbitration_id_range
# ---------------------------------------------------------------------------


def test_arbitration_id_range_inclusive_bounds_standard():
    out = list(fuzzing.arbitration_id_range(0x100, 0x103, extended=False))
    assert out == [0x100, 0x101, 0x102, 0x103]


def test_arbitration_id_range_inclusive_bounds_extended():
    out = list(fuzzing.arbitration_id_range(0x1FFFFFFC, 0x1FFFFFFF, extended=True))
    assert out == [0x1FFFFFFC, 0x1FFFFFFD, 0x1FFFFFFE, 0x1FFFFFFF]


def test_arbitration_id_range_with_step():
    out = list(fuzzing.arbitration_id_range(0, 16, extended=False, step=4))
    assert out == [0, 4, 8, 12, 16]


def test_arbitration_id_range_rejects_out_of_band_standard():
    with pytest.raises(ValueError):
        list(fuzzing.arbitration_id_range(0x000, 0x800, extended=False))


def test_arbitration_id_range_rejects_out_of_band_extended():
    with pytest.raises(ValueError):
        list(fuzzing.arbitration_id_range(0x000, 0x20000000, extended=True))


def test_arbitration_id_range_rejects_negative_bounds():
    with pytest.raises(ValueError):
        list(fuzzing.arbitration_id_range(-1, 5, extended=False))


def test_arbitration_id_range_rejects_inverted_bounds():
    with pytest.raises(ValueError):
        list(fuzzing.arbitration_id_range(0x200, 0x100, extended=False))


def test_arbitration_id_range_rejects_non_positive_step():
    with pytest.raises(ValueError):
        list(fuzzing.arbitration_id_range(0x100, 0x110, extended=False, step=0))
    with pytest.raises(ValueError):
        list(fuzzing.arbitration_id_range(0x100, 0x110, extended=False, step=-1))


# ---------------------------------------------------------------------------
# Module-level invariants
# ---------------------------------------------------------------------------


def test_fuzzing_module_has_no_transport_or_io_imports():
    """Spec invariant: the engine must not import transport or I/O modules."""
    import canarchy.fuzzing as mod

    banned = {"socket", "selectors", "asyncio", "can", "canarchy.transport", "time"}
    referenced = set(getattr(mod, "__dict__", {}).keys())
    # Module attributes can include `time` if explicitly imported; assert
    # none of the banned names is bound at module level.
    assert banned.isdisjoint(referenced), f"banned imports leaked: {banned & referenced}"
