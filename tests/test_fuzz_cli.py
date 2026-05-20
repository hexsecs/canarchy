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


if __name__ == "__main__":
    unittest.main()
