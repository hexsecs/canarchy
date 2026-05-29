"""Tests for the pure-function fuzzing engine (`canarchy.fuzzing`)."""

from __future__ import annotations

from pathlib import Path

import pytest

from canarchy import fuzzing
from canarchy.models import CanFrame

FIXTURES = Path(__file__).parent / "fixtures"


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
        # With 1-second gaps the ±5ms jitter never needs to clamp, so the
        # mutated timestamp stays within ±5ms of the original.
        assert abs((mutated.timestamp or 0.0) - (original.timestamp or 0.0)) <= 5e-3 + 1e-9
    # Monotonicity is part of the contract regardless of input spacing.
    timestamps = [(f.timestamp or 0.0) for f in out]
    assert timestamps == sorted(timestamps)


def test_mutate_replay_timing_preserves_monotonicity_for_close_frames():
    """Regression for Codex P1 on PR #345.

    When adjacent frames are closer than 10ms apart, independent ±5ms
    offsets could otherwise reorder them. The mutator must clamp so
    the output sequence remains non-decreasing.
    """
    # Five frames 2ms apart — well under the ±5ms jitter window.
    frames = [
        CanFrame(arbitration_id=0x100 + i, data=bytes([i]), timestamp=i * 0.002) for i in range(5)
    ]
    # Try a range of seeds so we exercise both signs of the jitter.
    for seed in range(20):
        out = list(fuzzing.mutate_replay(frames, strategy="timing", seed=seed))
        timestamps = [(f.timestamp or 0.0) for f in out]
        assert timestamps == sorted(timestamps), (
            f"non-monotonic output with seed={seed}: {timestamps}"
        )


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
# signal_payload (DBC-aware)
# ---------------------------------------------------------------------------


def _sample_message(name: str = "EngineStatus1"):
    import cantools

    database = cantools.database.load_file(str(FIXTURES / "sample.dbc"))
    return database.get_message_by_name(name)


def _complex_message(name: str):
    import cantools

    database = cantools.database.load_file(str(FIXTURES / "complex.dbc"))
    return database.get_message_by_name(name)


def _decode(message, payload: bytes, signal: str):
    return message.decode(payload, decode_choices=False)[signal]


def test_signal_payload_in_bounds_stays_within_declared_range():
    message = _sample_message()
    payloads = list(
        fuzzing.signal_payload(
            message=message, signal="CoolantTemp", mode="in_bounds", seed=1, count=16
        )
    )
    assert len(payloads) == 16
    # CoolantTemp declares [0, 210] degC.
    for payload in payloads:
        value = _decode(message, payload, "CoolantTemp")
        assert 0 <= value <= 210


def test_signal_payload_in_bounds_respects_scale_and_offset():
    """Load uses scale 0.4 — sampled values must still land in [0, 100]."""
    message = _sample_message()
    payloads = list(
        fuzzing.signal_payload(message=message, signal="Load", mode="in_bounds", seed=3, count=12)
    )
    for payload in payloads:
        value = _decode(message, payload, "Load")
        assert 0 <= value <= 100


def test_signal_payload_in_bounds_rounds_non_lsb_aligned_bounds_inward():
    """Regression for Codex P2 on PR #374.

    A signal whose declared min/max do not fall on a raw lsb must not emit
    decoded values outside [minimum, maximum]. With scale 0.4 and bounds
    [0.1, 99.8], naive round() maps to raw [0, 250] -> phys 0.0 / 100.0,
    which are outside the declared range. Directional rounding (ceil the
    lower bound, floor the upper) keeps every in_bounds value inside.
    """
    import cantools

    dbc = (
        'VERSION ""\n'
        "BS_:\n"
        "BU_: ECU\n"
        "BO_ 100 Msg: 1 ECU\n"
        ' SG_ Scaled : 0|8@1+ (0.4,0) [0.1|99.8] "" ECU\n'
    )
    database = cantools.database.load_string(dbc, database_format="dbc")
    message = database.get_message_by_name("Msg")
    payloads = list(
        fuzzing.signal_payload(message=message, signal="Scaled", mode="in_bounds", seed=0, count=64)
    )
    assert payloads
    for payload in payloads:
        value = message.decode(payload)["Scaled"]
        assert 0.1 <= value <= 99.8


def test_signal_payload_out_of_bounds_falls_outside_declared_range():
    message = _sample_message()
    payloads = list(
        fuzzing.signal_payload(
            message=message, signal="CoolantTemp", mode="out_of_bounds", seed=0, count=64
        )
    )
    assert payloads, "out_of_bounds should emit at least one frame for a sub-range signal"
    for payload in payloads:
        value = _decode(message, payload, "CoolantTemp")
        assert value < 0 or value > 210


def test_signal_payload_boundary_includes_min_max_and_one_lsb_steps():
    message = _sample_message()
    payloads = list(
        fuzzing.signal_payload(
            message=message, signal="CoolantTemp", mode="boundary", seed=0, count=64
        )
    )
    values = {_decode(message, payload, "CoolantTemp") for payload in payloads}
    # 1 lsb == scale == 1 degC for CoolantTemp; declared [0, 210].
    assert {0, 210, 1, 209, -1, 211} <= values


def test_signal_payload_boundary_drops_unrepresentable_steps():
    """LampState spans the full 8-bit range [0, 255]; min-1 / max+1 are not representable."""
    message = _sample_message()
    payloads = list(
        fuzzing.signal_payload(
            message=message, signal="LampState", mode="boundary", seed=0, count=64
        )
    )
    values = {_decode(message, payload, "LampState") for payload in payloads}
    assert values == {0, 255, 1, 254}


def test_signal_payload_out_of_bounds_empty_for_full_range_signal():
    """When the declared range already spans the representable range, nothing is out of bounds."""
    message = _sample_message()
    payloads = list(
        fuzzing.signal_payload(
            message=message, signal="LampState", mode="out_of_bounds", seed=0, count=64
        )
    )
    assert payloads == []


def test_signal_payload_full_field_sweeps_entire_representable_range():
    """full_field ignores the declared bounds and spans the whole field."""
    message = _sample_message()
    # CoolantTemp is 8-bit unsigned -> representable physical range
    # [-40, 215] (raw 0..255 with offset -40). Declared range is only
    # [0, 210], so full_field must reach below 0 and above 210.
    payloads = list(
        fuzzing.signal_payload(
            message=message, signal="CoolantTemp", mode="full_field", seed=0, count=256
        )
    )
    values = [_decode(message, payload, "CoolantTemp") for payload in payloads]
    assert len(values) == 256
    assert min(values) == -40
    assert max(values) == 215


def test_signal_payload_full_field_covers_full_range_signal_with_no_out_of_bounds():
    """The motivating case: a signal whose declared range == its field range.

    `out_of_bounds` is empty for LampState ([0, 255] over an 8-bit field),
    but `full_field` still sweeps every value.
    """
    message = _sample_message()
    payloads = list(
        fuzzing.signal_payload(
            message=message, signal="LampState", mode="full_field", seed=0, count=256
        )
    )
    values = sorted(_decode(message, payload, "LampState") for payload in payloads)
    assert values == list(range(256))


def test_signal_payload_full_field_evenly_spaced_when_count_below_field_size():
    message = _sample_message()
    payloads = list(
        fuzzing.signal_payload(
            message=message, signal="LampState", mode="full_field", seed=0, count=5
        )
    )
    # Raw values span [0, 255] with both extrema included, evenly spaced.
    values = sorted(_decode(message, payload, "LampState") for payload in payloads)
    assert values == [0, 64, 128, 191, 255]


def test_signal_payload_full_field_is_deterministic():
    message = _sample_message()
    a = list(
        fuzzing.signal_payload(
            message=message, signal="LampState", mode="full_field", seed=0, count=17
        )
    )
    b = list(
        fuzzing.signal_payload(
            message=message, signal="LampState", mode="full_field", seed=99, count=17
        )
    )
    # Deterministic and seed-independent (full_field does not use the seed).
    assert a == b


def test_signal_payload_enum_gaps_emits_only_undefined_choices():
    message = _complex_message("HVAC_Mode")
    payloads = list(
        fuzzing.signal_payload(
            message=message, signal="HVAC_Mode", mode="enum_gaps", seed=0, count=64
        )
    )
    values = sorted(_decode(message, payload, "HVAC_Mode") for payload in payloads)
    # 4-bit signal [0, 15]; choices defined for 0..5, so gaps are 6..15.
    assert values == [6, 7, 8, 9, 10, 11, 12, 13, 14, 15]


def test_signal_payload_enum_gaps_respects_count_cap():
    message = _complex_message("HVAC_Mode")
    payloads = list(
        fuzzing.signal_payload(
            message=message, signal="HVAC_Mode", mode="enum_gaps", seed=0, count=3
        )
    )
    assert len(payloads) == 3


def test_signal_payload_is_deterministic_for_same_seed():
    message = _sample_message()
    a = list(
        fuzzing.signal_payload(
            message=message, signal="CoolantTemp", mode="in_bounds", seed=7, count=10
        )
    )
    b = list(
        fuzzing.signal_payload(
            message=message, signal="CoolantTemp", mode="in_bounds", seed=7, count=10
        )
    )
    assert a == b


def test_signal_payload_holds_other_signals_at_baseline_zero():
    message = _sample_message()
    payload = next(
        fuzzing.signal_payload(
            message=message, signal="CoolantTemp", mode="boundary", seed=0, count=1
        )
    )
    decoded = message.decode(payload, decode_choices=False)
    assert decoded["OilTemp"] == -40  # raw 0 -> physical 0 - 40
    assert decoded["Load"] == 0
    assert decoded["LampState"] == 0


def test_signal_payload_unknown_signal_raises():
    message = _sample_message()
    with pytest.raises(ValueError):
        list(
            fuzzing.signal_payload(
                message=message, signal="DoesNotExist", mode="in_bounds", seed=0, count=1
            )
        )


def test_signal_payload_enum_gaps_without_choices_raises():
    message = _sample_message()
    with pytest.raises(ValueError):
        list(
            fuzzing.signal_payload(
                message=message, signal="CoolantTemp", mode="enum_gaps", seed=0, count=1
            )
        )


def test_signal_payload_negative_count_raises():
    message = _sample_message()
    with pytest.raises(ValueError):
        list(
            fuzzing.signal_payload(
                message=message, signal="CoolantTemp", mode="in_bounds", seed=0, count=-1
            )
        )


def test_signal_payload_unknown_mode_raises():
    message = _sample_message()
    with pytest.raises(ValueError):
        list(
            fuzzing.signal_payload(
                message=message,
                signal="CoolantTemp",
                mode="nope",  # type: ignore[arg-type]
                seed=0,
                count=1,
            )
        )


# ---------------------------------------------------------------------------
# spn_payload (J1939 SPN-aware)
# ---------------------------------------------------------------------------

# SPN 110 (Engine Coolant Temperature): PGN 65262, byte 0, 1 byte, res 1,
# offset -40 -> operational range [-40, 210] degC, raw [0, 0xFA].


def test_spn_payload_in_bounds_stays_within_operational_raw_range():
    payloads = list(fuzzing.spn_payload(spn=110, mode="in_bounds", seed=1, count=32))
    assert len(payloads) == 32
    for payload in payloads:
        assert len(payload) == 8
        assert payload[0] <= 0xFA  # operational max for a 1-byte SPN


def test_spn_payload_not_available_emits_all_ones_sentinel():
    (payload,) = list(fuzzing.spn_payload(spn=110, mode="not_available", seed=0, count=4))
    assert payload[0] == 0xFF


def test_spn_payload_error_emits_error_sentinel():
    (payload,) = list(fuzzing.spn_payload(spn=110, mode="error", seed=0, count=4))
    assert payload[0] == 0xFE


def test_spn_payload_boundary_covers_operational_edges():
    payloads = list(fuzzing.spn_payload(spn=110, mode="boundary", seed=0, count=8))
    raws = {payload[0] for payload in payloads}
    # min, max, min+1lsb, max-1lsb, max+1lsb (min-1lsb == -1 is omitted).
    assert raws == {0x00, 0xFA, 0x01, 0xF9, 0xFB}


def test_spn_payload_out_of_bounds_is_one_lsb_past_operational_max():
    payloads = list(fuzzing.spn_payload(spn=110, mode="out_of_bounds", seed=0, count=8))
    assert [payload[0] for payload in payloads] == [0xFB]


def test_spn_payload_targets_only_its_own_bytes_and_defaults_rest_to_ff():
    (payload,) = list(fuzzing.spn_payload(spn=110, mode="boundary", seed=0, count=1))
    # byte 0 is the SPN (min == 0x00); the rest stay at the 0xFF baseline.
    assert payload == b"\x00" + b"\xff" * 7


def test_spn_payload_sentinel_widths_match_j1939_spec():
    # Pure-function sentinel/operational-max helpers across 1/2/4-byte SPNs.
    assert fuzzing._spn_not_available_raw(1) == 0xFF
    assert fuzzing._spn_not_available_raw(2) == 0xFFFF
    assert fuzzing._spn_not_available_raw(4) == 0xFFFFFFFF
    assert fuzzing._spn_error_raw(1) == 0xFE
    assert fuzzing._spn_error_raw(2) == 0xFEFF
    assert fuzzing._spn_error_raw(4) == 0xFEFFFFFF
    assert fuzzing._spn_operational_max(1) == 0xFA
    assert fuzzing._spn_operational_max(2) == 0xFAFF
    assert fuzzing._spn_operational_max(4) == 0xFAFFFFFF


def test_spn_payload_width_2_sentinels_are_little_endian():
    # SPN 27 (EGR Valve Position): 2-byte SPN at byte 0.
    meta = _spn_meta(27)
    start, width = meta["start"], meta["length"]
    assert width == 2
    (na,) = list(fuzzing.spn_payload(spn=27, mode="not_available", seed=0, count=1))
    assert int.from_bytes(na[start : start + width], "little") == 0xFFFF
    (err,) = list(fuzzing.spn_payload(spn=27, mode="error", seed=0, count=1))
    assert int.from_bytes(err[start : start + width], "little") == 0xFEFF


def test_spn_payload_width_4_sentinels_match_spec():
    # SPN 182 (Engine Trip Fuel): 4-byte SPN at byte 0.
    meta = _spn_meta(182)
    start, width = meta["start"], meta["length"]
    assert width == 4
    (na,) = list(fuzzing.spn_payload(spn=182, mode="not_available", seed=0, count=1))
    assert int.from_bytes(na[start : start + width], "little") == 0xFFFFFFFF
    (err,) = list(fuzzing.spn_payload(spn=182, mode="error", seed=0, count=1))
    assert int.from_bytes(err[start : start + width], "little") == 0xFEFFFFFF
    in_bounds = list(fuzzing.spn_payload(spn=182, mode="in_bounds", seed=3, count=20))
    for payload in in_bounds:
        assert int.from_bytes(payload[start : start + width], "little") <= 0xFAFFFFFF


def test_spn_payload_is_deterministic_for_same_seed():
    a = list(fuzzing.spn_payload(spn=110, mode="in_bounds", seed=7, count=16))
    b = list(fuzzing.spn_payload(spn=110, mode="in_bounds", seed=7, count=16))
    assert a == b


def test_spn_payload_unknown_spn_raises():
    with pytest.raises(ValueError):
        list(fuzzing.spn_payload(spn=987654, mode="in_bounds", seed=0, count=1))


def test_spn_payload_incomplete_metadata_raises():
    # SPN 695 (Engine Override Control Mode) is present with only a name —
    # no layout fields. Must raise ValueError, not a raw KeyError.
    with pytest.raises(ValueError):
        list(fuzzing.spn_payload(spn=695, mode="in_bounds", seed=0, count=1))


def test_spn_payload_mismatched_pgn_raises():
    with pytest.raises(ValueError):
        list(fuzzing.spn_payload(spn=110, pgn=1, mode="in_bounds", seed=0, count=1))


def test_spn_payload_negative_count_raises():
    with pytest.raises(ValueError):
        list(fuzzing.spn_payload(spn=110, mode="in_bounds", seed=0, count=-1))


def test_spn_payload_unknown_mode_raises():
    with pytest.raises(ValueError):
        list(fuzzing.spn_payload(spn=110, mode="nope", seed=0, count=1))  # type: ignore[arg-type]


def _spn_meta(spn: int):
    from canarchy.j1939_metadata import spn_lookup

    return spn_lookup(spn)


# ---------------------------------------------------------------------------
# havoc_payload / splice_payload / interesting_values_payload (AFL-style)
# ---------------------------------------------------------------------------


def test_havoc_payload_is_deterministic_for_same_seed():
    base = b"\x11\x22\x33\x44"
    a = list(fuzzing.havoc_payload(base, seed=1, count=20))
    b = list(fuzzing.havoc_payload(base, seed=1, count=20))
    assert a == b
    assert len(a) == 20


def test_havoc_payload_is_diverse_and_mutates_the_input():
    base = b"\x11\x22\x33\x44"
    out = list(fuzzing.havoc_payload(base, seed=2, count=32))
    # Stacked mutations produce variety and (almost always) change the input.
    assert len(set(out)) > 1
    assert sum(variant != base for variant in out) >= len(out) - 1


def test_havoc_payload_clamps_to_max_dlc():
    out = list(fuzzing.havoc_payload(b"\x00" * 8, seed=3, count=50))
    assert all(len(variant) <= 64 for variant in out)


def test_havoc_payload_different_seeds_diverge():
    base = b"\x01\x02\x03\x04"
    a = list(fuzzing.havoc_payload(base, seed=1, count=16))
    b = list(fuzzing.havoc_payload(base, seed=2, count=16))
    assert a != b


def test_havoc_payload_negative_count_rejected():
    with pytest.raises(ValueError):
        list(fuzzing.havoc_payload(b"\x00", seed=0, count=-1))


def test_splice_payload_joins_prefix_and_suffix_from_corpus():
    corpus = [b"\xaa\xaa\xaa\xaa", b"\xbb\xbb\xbb\xbb\xbb\xbb"]
    out = list(fuzzing.splice_payload(corpus, seed=2, count=10))
    assert len(out) == 10
    # Every spliced byte must originate from one of the corpus byte values.
    allowed = {0xAA, 0xBB}
    for variant in out:
        assert set(variant) <= allowed


def test_splice_payload_is_deterministic_for_same_seed():
    corpus = [b"\x01\x02\x03", b"\x04\x05\x06\x07"]
    a = list(fuzzing.splice_payload(corpus, seed=9, count=12))
    b = list(fuzzing.splice_payload(corpus, seed=9, count=12))
    assert a == b


def test_splice_payload_empty_corpus_raises():
    with pytest.raises(ValueError):
        list(fuzzing.splice_payload([], seed=0, count=3))


def test_splice_payload_clamps_to_max_dlc():
    corpus = [b"\xaa" * 64, b"\xbb" * 64]
    out = list(fuzzing.splice_payload(corpus, seed=1, count=10))
    assert all(len(variant) <= 64 for variant in out)


def test_splice_payload_negative_count_rejected():
    with pytest.raises(ValueError):
        list(fuzzing.splice_payload([b"\x00"], seed=0, count=-1))


def test_interesting_values_payload_includes_known_patterns():
    out = list(fuzzing.interesting_values_payload(dlc=4))
    # 8-bit interesting values at byte 0 over a zero baseline.
    assert b"\xff\x00\x00\x00" in out  # 255
    assert b"\x7f\x00\x00\x00" in out  # 127
    assert b"\x80\x00\x00\x00" in out  # 128 / -128
    assert b"\x00\x00\x00\x00" in out  # 0
    # 16-bit little-endian interesting value (256) at word offset 0.
    assert b"\x00\x01\x00\x00" in out


def test_interesting_values_payload_is_deterministic_and_deduplicated():
    a = list(fuzzing.interesting_values_payload(dlc=4))
    b = list(fuzzing.interesting_values_payload(dlc=4))
    assert a == b
    assert len(a) == len(set(a))  # no duplicate payloads


def test_interesting_values_payload_dlc_zero_yields_nothing():
    assert list(fuzzing.interesting_values_payload(dlc=0)) == []


def test_interesting_values_payload_invalid_dlc_rejected():
    with pytest.raises(ValueError):
        list(fuzzing.interesting_values_payload(dlc=65))


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
