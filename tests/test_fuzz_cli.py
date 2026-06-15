"""Tests for the `canarchy fuzz` CLI surface (`fuzz payload|replay|arbitration-id`)."""

from __future__ import annotations

import contextlib
import io
import json
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from canarchy.cli import EXIT_OK, main

FIXTURES = Path(__file__).parent / "fixtures"


def run_cli(*argv: str) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = main(argv)
    return exit_code, stdout.getvalue(), stderr.getvalue()


# ---------------------------------------------------------------------------
# fuzz payload — dry-run path
# ---------------------------------------------------------------------------


def test_fuzz_payload_dry_run_emits_jsonl_with_run_id_and_no_transport():
    exit_code, stdout, _stderr = run_cli(
        "fuzz",
        "payload",
        "can0",
        "--id",
        "0x123",
        "--strategy",
        "bitflip",
        "--max",
        "3",
        "--seed",
        "1",
        "--dry-run",
        "--jsonl",
    )
    assert exit_code == 0
    lines = [json.loads(line) for line in stdout.splitlines() if line.strip()]
    # Alert + 3 frame events + final dry-run warning alert.
    frames = [evt for evt in lines if evt.get("event_type") == "frame"]
    assert len(frames) == 3
    # Every frame event carries a run_id and dry_run=true.
    run_ids = {evt["payload"]["run_id"] for evt in frames}
    assert len(run_ids) == 1
    (run_id,) = run_ids
    assert uuid.UUID(run_id)
    assert all(evt["payload"]["dry_run"] is True for evt in frames)
    # And the frame.dry_run flag the spec calls for.
    assert all(evt["payload"]["frame"]["dry_run"] is True for evt in frames)


def test_fuzz_payload_dry_run_is_deterministic_for_same_seed():
    args = (
        "fuzz",
        "payload",
        "can0",
        "--id",
        "0x100",
        "--strategy",
        "bitflip",
        "--max",
        "5",
        "--seed",
        "42",
        "--dry-run",
        "--jsonl",
    )
    _, out_a, _ = run_cli(*args)
    _, out_b, _ = run_cli(*args)
    frames_a = [
        json.loads(line)["payload"]["frame"]["data"]
        for line in out_a.splitlines()
        if line.strip() and json.loads(line)["event_type"] == "frame"
    ]
    frames_b = [
        json.loads(line)["payload"]["frame"]["data"]
        for line in out_b.splitlines()
        if line.strip() and json.loads(line)["event_type"] == "frame"
    ]
    assert frames_a == frames_b
    assert len(frames_a) == 5


def test_fuzz_payload_dry_run_skips_active_ack_prompt():
    """`--dry-run` opens no transport and therefore needs no acknowledgement."""

    # No --ack-active and no `[safety].require_active_ack` config — the
    # dry-run path must succeed silently.
    exit_code, stdout, _ = run_cli(
        "fuzz",
        "payload",
        "can0",
        "--id",
        "0x123",
        "--strategy",
        "boundary",
        "--max",
        "4",
        "--dry-run",
        "--json",
    )
    assert exit_code == 0
    payload = json.loads(stdout)
    assert payload["ok"] is True
    assert payload["data"]["mode"] == "dry_run"
    assert payload["data"]["dry_run"] is True


def test_fuzz_payload_repair_crc_fixes_last_byte():
    """--repair-crc recomputes the Stellantis CRC-8 in the last byte."""
    from canarchy.checksum import chrysler_message_checksum

    exit_code, stdout, _ = run_cli(
        "fuzz",
        "payload",
        "can0",
        "--id",
        "0x123",
        "--strategy",
        "bitflip",
        "--data",
        "010000",
        "--max",
        "3",
        "--seed",
        "0",
        "--repair-crc",
        "--dry-run",
        "--jsonl",
    )
    assert exit_code == EXIT_OK
    lines = [json.loads(line) for line in stdout.splitlines() if line.strip()]
    frames = [evt for evt in lines if evt.get("event_type") == "frame"]
    assert len(frames) == 3
    for evt in frames:
        data_hex = evt["payload"]["frame"]["data"]
        payload = bytes.fromhex(data_hex)
        assert len(payload) == 3
        expected_crc = chrysler_message_checksum(payload)
        assert payload[2] == expected_crc, f"CRC mismatch in {data_hex}"


def test_fuzz_payload_repair_crc_on_8_byte_payload():
    """--repair-crc works on 8-byte Stellantis messages."""
    from canarchy.checksum import chrysler_message_checksum

    exit_code, stdout, _ = run_cli(
        "fuzz",
        "payload",
        "can0",
        "--id",
        "0x123",
        "--strategy",
        "bitflip",
        "--data",
        "1122334455667700",
        "--max",
        "2",
        "--seed",
        "0",
        "--repair-crc",
        "--dry-run",
        "--jsonl",
    )
    assert exit_code == EXIT_OK
    lines = [json.loads(line) for line in stdout.splitlines() if line.strip()]
    frames = [evt for evt in lines if evt.get("event_type") == "frame"]
    assert len(frames) == 2
    for evt in frames:
        payload = bytes.fromhex(evt["payload"]["frame"]["data"])
        assert len(payload) == 8
        assert payload[7] == chrysler_message_checksum(payload)


def test_fuzz_payload_repair_crc_not_applied_without_flag():
    """Without --repair-crc, the last byte is not fixed."""
    exit_code, stdout, _ = run_cli(
        "fuzz",
        "payload",
        "can0",
        "--id",
        "0x123",
        "--strategy",
        "bitflip",
        "--data",
        "010000",
        "--max",
        "3",
        "--seed",
        "0",
        "--dry-run",
        "--jsonl",
    )
    assert exit_code == EXIT_OK
    lines = [json.loads(line) for line in stdout.splitlines() if line.strip()]
    frames = [evt for evt in lines if evt.get("event_type") == "frame"]
    assert len(frames) == 3
    # At least one frame should have a CRC that doesn't match
    from canarchy.checksum import chrysler_message_checksum

    mismatches = 0
    for evt in frames:
        payload = bytes.fromhex(evt["payload"]["frame"]["data"])
        if payload[2] != chrysler_message_checksum(payload):
            mismatches += 1
    assert mismatches > 0


# ---------------------------------------------------------------------------
# fuzz payload — validation
# ---------------------------------------------------------------------------


def test_fuzz_payload_invalid_hex_id_returns_structured_error():
    exit_code, stdout, _ = run_cli(
        "fuzz",
        "payload",
        "can0",
        "--id",
        "not-hex",
        "--strategy",
        "bitflip",
        "--max",
        "2",
        "--dry-run",
        "--json",
    )
    assert exit_code != 0
    payload = json.loads(stdout)
    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "INVALID_FRAME_ID"


def test_fuzz_payload_29bit_id_without_extended_infers_extended():
    # A 29-bit --id without --extended is built as an extended frame (matching
    # `send` / `xcp scan`) instead of raising an uncaught CanFrame ValueError.
    exit_code, stdout, _ = run_cli(
        "fuzz",
        "payload",
        "can0",
        "--id",
        "0x18DAF110",
        "--strategy",
        "random",
        "--max",
        "1",
        "--dry-run",
        "--json",
    )
    assert exit_code == 0
    payload = json.loads(stdout)
    assert payload["ok"] is True
    frames = [evt for evt in payload["data"]["events"] if evt.get("event_type") == "frame"]
    assert frames
    assert all(evt["payload"]["frame"]["is_extended_id"] is True for evt in frames)
    assert all(evt["payload"]["frame"]["arbitration_id"] == 0x18DAF110 for evt in frames)


def test_fuzz_payload_id_above_29bit_range_returns_structured_error():
    # An id past the 29-bit ceiling is a structured user error, not a traceback.
    exit_code, stdout, _ = run_cli(
        "fuzz",
        "payload",
        "can0",
        "--id",
        "0xFFFFFFFF",
        "--strategy",
        "random",
        "--max",
        "1",
        "--dry-run",
        "--json",
    )
    assert exit_code != 0
    payload = json.loads(stdout)
    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "INVALID_FRAME_ID"


def test_fuzz_payload_invalid_rate_returns_structured_error():
    exit_code, stdout, _ = run_cli(
        "fuzz",
        "payload",
        "can0",
        "--id",
        "0x100",
        "--strategy",
        "bitflip",
        "--max",
        "2",
        "--rate",
        "0",
        "--dry-run",
        "--json",
    )
    assert exit_code != 0
    payload = json.loads(stdout)
    assert payload["errors"][0]["code"] == "INVALID_RATE"


def test_fuzz_payload_random_strategy_honours_dlc_flag():
    """`--strategy random --dlc 4` produces 4-byte frames even without --data.

    Regression for Codex P2 on PR #351: the random strategy previously
    inherited the baseline length (8) and silently ignored `--dlc`.
    """

    _, stdout, _ = run_cli(
        "fuzz",
        "payload",
        "can0",
        "--id",
        "0x100",
        "--strategy",
        "random",
        "--dlc",
        "4",
        "--max",
        "3",
        "--seed",
        "1",
        "--dry-run",
        "--jsonl",
    )
    frames = [
        json.loads(line)
        for line in stdout.splitlines()
        if line.strip() and json.loads(line)["event_type"] == "frame"
    ]
    assert len(frames) == 3
    for frame in frames:
        # `data` is hex-encoded; 4 bytes → 8 hex chars.
        assert len(frame["payload"]["frame"]["data"]) == 8
        assert frame["payload"]["frame"]["dlc"] == 4


def test_fuzz_payload_invalid_dlc_returns_structured_error():
    """`fuzz payload --strategy boundary --dlc -1` must not crash with a traceback.

    Regression for Codex P1 on PR #351: the engine raises `ValueError`
    on invalid DLC, and the CLI must translate that into a structured
    `INVALID_ARGUMENTS` envelope.
    """

    exit_code, stdout, _ = run_cli(
        "fuzz",
        "payload",
        "can0",
        "--id",
        "0x100",
        "--strategy",
        "boundary",
        "--dlc",
        "-1",
        "--dry-run",
        "--json",
    )
    assert exit_code != 0
    payload = json.loads(stdout)
    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "INVALID_ARGUMENTS"


def test_fuzz_payload_invalid_run_id_returns_structured_error():
    exit_code, stdout, _ = run_cli(
        "fuzz",
        "payload",
        "can0",
        "--id",
        "0x100",
        "--strategy",
        "bitflip",
        "--max",
        "2",
        "--run-id",
        "not-a-uuid",
        "--dry-run",
        "--json",
    )
    assert exit_code != 0
    payload = json.loads(stdout)
    assert payload["errors"][0]["code"] == "ACTIVE_TRANSMIT_INVALID_RUN_ID"


def test_fuzz_payload_explicit_run_id_round_trips():
    forced = "0193bf6e-1e3e-7a8c-b6b1-d0e7d3a8f4f0"
    _, stdout, _ = run_cli(
        "fuzz",
        "payload",
        "can0",
        "--id",
        "0x100",
        "--strategy",
        "bitflip",
        "--max",
        "1",
        "--run-id",
        forced,
        "--dry-run",
        "--json",
    )
    payload = json.loads(stdout)
    assert payload["data"]["run_id"] == forced


# ---------------------------------------------------------------------------
# fuzz arbitration-id
# ---------------------------------------------------------------------------


def test_fuzz_arbitration_id_dry_run_walks_inclusive_range():
    exit_code, stdout, _ = run_cli(
        "fuzz",
        "arbitration-id",
        "can0",
        "--range",
        "0x100:0x103",
        "--rate",
        "100",
        "--dry-run",
        "--jsonl",
    )
    assert exit_code == 0
    frames = [
        json.loads(line)
        for line in stdout.splitlines()
        if line.strip() and json.loads(line)["event_type"] == "frame"
    ]
    ids = [evt["payload"]["frame"]["arbitration_id"] for evt in frames]
    assert ids == [0x100, 0x101, 0x102, 0x103]


def test_fuzz_arbitration_id_out_of_band_returns_structured_error():
    exit_code, stdout, _ = run_cli(
        "fuzz",
        "arbitration-id",
        "can0",
        "--range",
        "0x100:0x800",  # 0x800 > standard 11-bit cap (0x7FF)
        "--dry-run",
        "--json",
    )
    assert exit_code != 0
    payload = json.loads(stdout)
    assert payload["errors"][0]["code"] == "INVALID_FUZZ_RANGE"


def test_fuzz_arbitration_id_missing_colon_returns_structured_error():
    exit_code, stdout, _ = run_cli(
        "fuzz", "arbitration-id", "can0", "--range", "0x100", "--dry-run", "--json"
    )
    assert exit_code != 0
    payload = json.loads(stdout)
    assert payload["errors"][0]["code"] == "INVALID_FUZZ_RANGE"


# ---------------------------------------------------------------------------
# fuzz replay
# ---------------------------------------------------------------------------


def test_fuzz_replay_requires_interface_when_not_dry_run():
    exit_code, stdout, _ = run_cli(
        "fuzz",
        "replay",
        "--file",
        str(FIXTURES / "j1939_heavy_vehicle.candump"),
        "--strategy",
        "timing",
        "--json",
    )
    assert exit_code != 0
    payload = json.loads(stdout)
    assert payload["errors"][0]["code"] == "MISSING_INPUT"


def test_fuzz_replay_dry_run_emits_monotonic_timestamps():
    exit_code, stdout, _ = run_cli(
        "fuzz",
        "replay",
        "--file",
        str(FIXTURES / "j1939_heavy_vehicle.candump"),
        "--strategy",
        "timing",
        "--seed",
        "0",
        "--max",
        "4",
        "--dry-run",
        "--jsonl",
    )
    assert exit_code == 0
    frame_events = [
        json.loads(line)
        for line in stdout.splitlines()
        if line.strip() and json.loads(line)["event_type"] == "frame"
    ]
    assert len(frame_events) <= 4
    timestamps = [evt["payload"]["frame"]["timestamp"] for evt in frame_events]
    assert timestamps == sorted(timestamps)


# ---------------------------------------------------------------------------
# Active-ack gate (with require_active_ack via config)
# ---------------------------------------------------------------------------


def test_fuzz_payload_live_mode_requires_ack_when_config_demands_it():
    """When `[safety].require_active_ack=true`, live fuzz refuses without --ack-active."""

    # The CLI binds `active_ack_required` at import time, so patch the
    # binding inside `canarchy.cli` (not the original in `canarchy.transport`).
    from canarchy import cli as _cli

    with patch.object(_cli, "active_ack_required", return_value=True):
        exit_code, stdout, _ = run_cli(
            "fuzz",
            "payload",
            "can0",
            "--id",
            "0x100",
            "--strategy",
            "bitflip",
            "--max",
            "2",
            "--json",
        )
    assert exit_code != 0
    payload = json.loads(stdout)
    assert payload["errors"][0]["code"] == "ACTIVE_ACK_REQUIRED"


# ---------------------------------------------------------------------------
# fuzz payload — AFL-style strategies (havoc / splice / interesting)
# ---------------------------------------------------------------------------


def test_fuzz_payload_havoc_dry_run_is_deterministic():
    args = (
        "fuzz",
        "payload",
        "can0",
        "--id",
        "0x123",
        "--strategy",
        "havoc",
        "--data",
        "11223344",
        "--max",
        "8",
        "--seed",
        "5",
        "--dry-run",
        "--jsonl",
    )
    _, out_a, _ = run_cli(*args)
    _, out_b, _ = run_cli(*args)
    data_a = [evt["payload"]["frame"]["data"] for evt in _signal_frames(out_a)]
    data_b = [evt["payload"]["frame"]["data"] for evt in _signal_frames(out_b)]
    assert data_a == data_b
    assert len(data_a) == 8


def test_fuzz_payload_havoc_clamps_to_classic_dlc():
    """Regression for Codex P2 on PR #376.

    havoc starts from the default 8-byte seed and can insert bytes,
    growing past 8; classic CAN frames cap at 8 bytes, so the CLI must
    clamp rather than crash with a raw ValueError.
    """
    exit_code, stdout, _ = run_cli(
        "fuzz",
        "payload",
        "can0",
        "--id",
        "0x123",
        "--strategy",
        "havoc",
        "--max",
        "16",
        "--seed",
        "0",
        "--dry-run",
        "--jsonl",
    )
    assert exit_code == EXIT_OK
    frames = _signal_frames(stdout)
    assert len(frames) == 16
    assert all(len(bytes.fromhex(evt["payload"]["frame"]["data"])) <= 8 for evt in frames)


def test_fuzz_payload_splice_clamps_to_classic_dlc():
    """Splicing two 8-byte corpus frames can exceed 8 bytes; must clamp."""
    exit_code, stdout, _ = run_cli(
        "fuzz",
        "payload",
        "can0",
        "--id",
        "0x123",
        "--strategy",
        "splice",
        "--corpus",
        str(FIXTURES / "complex.candump"),
        "--max",
        "20",
        "--seed",
        "3",
        "--dry-run",
        "--jsonl",
    )
    assert exit_code == EXIT_OK
    frames = _signal_frames(stdout)
    assert frames
    assert all(len(bytes.fromhex(evt["payload"]["frame"]["data"])) <= 8 for evt in frames)


def test_fuzz_payload_interesting_dry_run_emits_known_values():
    exit_code, stdout, _ = run_cli(
        "fuzz",
        "payload",
        "can0",
        "--id",
        "0x123",
        "--strategy",
        "interesting",
        "--dlc",
        "2",
        "--max",
        "200",
        "--dry-run",
        "--jsonl",
    )
    assert exit_code == EXIT_OK
    datas = {evt["payload"]["frame"]["data"] for evt in _signal_frames(stdout)}
    assert "ff00" in datas  # 0xFF at byte 0
    assert "7f00" in datas  # 0x7F at byte 0


def test_fuzz_payload_splice_requires_corpus():
    exit_code, stdout, _ = run_cli(
        "fuzz",
        "payload",
        "can0",
        "--id",
        "0x123",
        "--strategy",
        "splice",
        "--max",
        "5",
        "--dry-run",
        "--json",
    )
    assert exit_code != 0
    payload = json.loads(stdout)
    assert payload["errors"][0]["code"] == "MISSING_INPUT"


def test_fuzz_payload_splice_with_corpus_emits_frames():
    exit_code, stdout, _ = run_cli(
        "fuzz",
        "payload",
        "can0",
        "--id",
        "0x123",
        "--strategy",
        "splice",
        "--corpus",
        str(FIXTURES / "complex.candump"),
        "--max",
        "6",
        "--seed",
        "1",
        "--dry-run",
        "--jsonl",
    )
    assert exit_code == EXIT_OK
    assert len(_signal_frames(stdout)) == 6


# ---------------------------------------------------------------------------
# fuzz signal (DBC-aware)
# ---------------------------------------------------------------------------


def _signal_frames(stdout: str) -> list[dict]:
    return [
        json.loads(line)
        for line in stdout.splitlines()
        if line.strip() and json.loads(line)["event_type"] == "frame"
    ]


def test_fuzz_signal_dry_run_plans_without_interface():
    exit_code, stdout, _ = run_cli(
        "fuzz",
        "signal",
        "--dbc",
        str(FIXTURES / "sample.dbc"),
        "--message",
        "EngineStatus1",
        "--signal",
        "CoolantTemp",
        "--mode",
        "boundary",
        "--count",
        "8",
        "--dry-run",
        "--jsonl",
    )
    assert exit_code == EXIT_OK
    frames = _signal_frames(stdout)
    assert frames
    # Boundary mode yields min, max, and the ±1 lsb steps.
    assert all(evt["payload"]["frame"]["dry_run"] is True for evt in frames)
    # Every frame targets the same (single) message arbitration id.
    arb_ids = {evt["payload"]["frame"]["arbitration_id"] for evt in frames}
    assert len(arb_ids) == 1


def test_fuzz_signal_dry_run_is_deterministic_for_same_seed():
    args = (
        "fuzz",
        "signal",
        "--dbc",
        str(FIXTURES / "sample.dbc"),
        "--message",
        "EngineStatus1",
        "--signal",
        "CoolantTemp",
        "--mode",
        "in_bounds",
        "--count",
        "8",
        "--seed",
        "42",
        "--dry-run",
        "--jsonl",
    )
    _, out_a, _ = run_cli(*args)
    _, out_b, _ = run_cli(*args)
    data_a = [evt["payload"]["frame"]["data"] for evt in _signal_frames(out_a)]
    data_b = [evt["payload"]["frame"]["data"] for evt in _signal_frames(out_b)]
    assert data_a == data_b


def test_fuzz_signal_emits_metadata_in_json_envelope():
    exit_code, stdout, _ = run_cli(
        "fuzz",
        "signal",
        "--dbc",
        str(FIXTURES / "sample.dbc"),
        "--message",
        "EngineStatus1",
        "--signal",
        "CoolantTemp",
        "--mode",
        "out_of_bounds",
        "--dry-run",
        "--json",
    )
    assert exit_code == EXIT_OK
    payload = json.loads(stdout)
    assert payload["data"]["signal_mode"] == "out_of_bounds"
    assert payload["data"]["message"] == "EngineStatus1"
    assert payload["data"]["signal"] == "CoolantTemp"
    assert payload["data"]["mode"] == "dry_run"


def test_fuzz_signal_full_field_sweeps_entire_field():
    exit_code, stdout, _ = run_cli(
        "fuzz",
        "signal",
        "--dbc",
        str(FIXTURES / "sample.dbc"),
        "--message",
        "EngineStatus1",
        "--signal",
        "LampState",
        "--mode",
        "full_field",
        "--count",
        "256",
        "--dry-run",
        "--json",
    )
    assert exit_code == EXIT_OK
    payload = json.loads(stdout)
    assert payload["data"]["signal_mode"] == "full_field"
    # LampState is a full-range 8-bit signal: full_field sweeps all 256 values.
    assert payload["data"]["frame_count"] == 256


def test_fuzz_signal_unknown_message_returns_structured_error():
    exit_code, stdout, _ = run_cli(
        "fuzz",
        "signal",
        "--dbc",
        str(FIXTURES / "sample.dbc"),
        "--message",
        "NoSuchMessage",
        "--signal",
        "CoolantTemp",
        "--mode",
        "in_bounds",
        "--dry-run",
        "--json",
    )
    assert exit_code != 0
    payload = json.loads(stdout)
    assert payload["errors"][0]["code"] == "DBC_MESSAGE_NOT_FOUND"


def test_fuzz_signal_enum_gaps_on_plain_signal_returns_structured_error():
    exit_code, stdout, _ = run_cli(
        "fuzz",
        "signal",
        "--dbc",
        str(FIXTURES / "sample.dbc"),
        "--message",
        "EngineStatus1",
        "--signal",
        "CoolantTemp",
        "--mode",
        "enum_gaps",
        "--dry-run",
        "--json",
    )
    assert exit_code != 0
    payload = json.loads(stdout)
    assert payload["errors"][0]["code"] == "INVALID_FUZZ_SIGNAL"


def test_fuzz_signal_invalid_rate_returns_structured_error():
    exit_code, stdout, _ = run_cli(
        "fuzz",
        "signal",
        "can0",
        "--dbc",
        str(FIXTURES / "sample.dbc"),
        "--message",
        "EngineStatus1",
        "--signal",
        "CoolantTemp",
        "--mode",
        "boundary",
        "--rate",
        "0",
        "--dry-run",
        "--json",
    )
    assert exit_code != 0
    payload = json.loads(stdout)
    assert payload["errors"][0]["code"] == "INVALID_RATE"


# ---------------------------------------------------------------------------
# fuzz spn (J1939 SPN-aware)
# ---------------------------------------------------------------------------


def test_fuzz_spn_not_available_sentinel_dry_run():
    exit_code, stdout, _ = run_cli(
        "fuzz",
        "spn",
        "--spn",
        "110",
        "--mode",
        "not_available",
        "--dry-run",
        "--json",
    )
    assert exit_code == EXIT_OK
    payload = json.loads(stdout)
    assert payload["data"]["spn"] == 110
    assert payload["data"]["pgn"] == 65262
    assert payload["data"]["spn_mode"] == "not_available"
    frame = next(evt for evt in payload["data"]["events"] if evt.get("event_type") == "frame")
    assert frame["payload"]["frame"]["data"].startswith("ff")
    # PGN 65262 broadcast -> arbitration id 0x18FEEE00.
    assert frame["payload"]["frame"]["arbitration_id"] == 0x18FEEE00
    assert frame["payload"]["frame"]["is_extended_id"] is True


def test_fuzz_spn_boundary_sweeps_operational_edges():
    exit_code, stdout, _ = run_cli(
        "fuzz",
        "spn",
        "--spn",
        "110",
        "--mode",
        "boundary",
        "--count",
        "8",
        "--dry-run",
        "--jsonl",
    )
    assert exit_code == EXIT_OK
    frames = _signal_frames(stdout)
    first_bytes = {bytes.fromhex(evt["payload"]["frame"]["data"])[0] for evt in frames}
    assert first_bytes == {0x00, 0xFA, 0x01, 0xF9, 0xFB}


def test_fuzz_spn_unknown_spn_returns_structured_error():
    exit_code, stdout, _ = run_cli(
        "fuzz", "spn", "--spn", "987654", "--mode", "in_bounds", "--dry-run", "--json"
    )
    assert exit_code != 0
    payload = json.loads(stdout)
    assert payload["errors"][0]["code"] == "INVALID_FUZZ_SPN"


def test_fuzz_spn_incomplete_metadata_returns_structured_error():
    # SPN 695 exists in the metadata with only a name (no layout fields).
    # Must return INVALID_FUZZ_SPN, not crash with a KeyError.
    exit_code, stdout, _ = run_cli(
        "fuzz", "spn", "--spn", "695", "--mode", "in_bounds", "--dry-run", "--json"
    )
    assert exit_code != 0
    payload = json.loads(stdout)
    assert payload["errors"][0]["code"] == "INVALID_FUZZ_SPN"


def test_fuzz_spn_invalid_rate_returns_structured_error():
    exit_code, stdout, _ = run_cli(
        "fuzz",
        "spn",
        "can0",
        "--spn",
        "110",
        "--mode",
        "boundary",
        "--rate",
        "0",
        "--dry-run",
        "--json",
    )
    assert exit_code != 0
    payload = json.loads(stdout)
    assert payload["errors"][0]["code"] == "INVALID_RATE"


def test_fuzz_spn_live_mode_requires_ack_when_config_demands_it():
    from canarchy import cli as _cli

    with patch.object(_cli, "active_ack_required", return_value=True):
        exit_code, stdout, _ = run_cli(
            "fuzz", "spn", "can0", "--spn", "110", "--mode", "boundary", "--json"
        )
    assert exit_code != 0
    payload = json.loads(stdout)
    assert payload["errors"][0]["code"] == "ACTIVE_ACK_REQUIRED"


def test_fuzz_signal_live_mode_requires_ack_when_config_demands_it():
    from canarchy import cli as _cli

    with patch.object(_cli, "active_ack_required", return_value=True):
        exit_code, stdout, _ = run_cli(
            "fuzz",
            "signal",
            "can0",
            "--dbc",
            str(FIXTURES / "sample.dbc"),
            "--message",
            "EngineStatus1",
            "--signal",
            "CoolantTemp",
            "--mode",
            "boundary",
            "--json",
        )
    assert exit_code != 0
    payload = json.loads(stdout)
    assert payload["errors"][0]["code"] == "ACTIVE_ACK_REQUIRED"


if __name__ == "__main__":
    unittest.main()
