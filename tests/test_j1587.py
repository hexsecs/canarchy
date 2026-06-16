from __future__ import annotations

import json
import unittest
from pathlib import Path

from canarchy.cli import EXIT_OK, EXIT_USER_ERROR
from canarchy.j1587 import (
    J1587Parameter,
    decode_events,
    decode_parameter_value,
    iter_j1708_messages_from_file,
    j1587_pids_payload,
    parse_j1708_message,
)
from canarchy.transport import TransportError
from tests.test_cli import run_cli

FIXTURES = Path(__file__).parent / "fixtures"


def _message(mid: int, payload: bytes, *, bad_checksum: bool = False) -> bytes:
    """Build a raw J1708 message with a valid (or deliberately invalid) checksum."""

    body = bytes([mid]) + payload
    checksum = (-sum(body)) % 256
    if bad_checksum:
        checksum = (checksum + 1) % 256
    return body + bytes([checksum])


class ParseJ1708MessageTests(unittest.TestCase):
    def test_too_short_message_raises(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least a MID and checksum byte"):
            parse_j1708_message(bytes([0x80]))

    def test_valid_checksum_is_recognized(self) -> None:
        raw = _message(0x80, bytes([70, 0x01]))
        message = parse_j1708_message(raw)

        self.assertEqual(message.mid, 0x80)
        self.assertTrue(message.checksum_valid)
        self.assertEqual(message.parameters, (J1587Parameter(pid=70, data=bytes([0x01])),))

    def test_invalid_checksum_is_flagged(self) -> None:
        raw = _message(0x80, bytes([70, 0x01]), bad_checksum=True)
        message = parse_j1708_message(raw)

        self.assertFalse(message.checksum_valid)

    def test_pid_under_128_takes_one_data_byte(self) -> None:
        raw = _message(0x80, bytes([70, 0x01]))
        message = parse_j1708_message(raw)

        self.assertEqual(message.parameters, (J1587Parameter(pid=70, data=bytes([0x01])),))

    def test_pid_128_to_191_takes_two_data_bytes(self) -> None:
        raw = _message(0x80, bytes([190, 0x70, 0x17]))
        message = parse_j1708_message(raw)

        self.assertEqual(message.parameters, (J1587Parameter(pid=190, data=bytes([0x70, 0x17])),))

    def test_pid_192_and_above_uses_explicit_length_byte(self) -> None:
        raw = _message(0x80, bytes([200, 3, 0x01, 0x02, 0x03]))
        message = parse_j1708_message(raw)

        self.assertEqual(
            message.parameters, (J1587Parameter(pid=200, data=bytes([0x01, 0x02, 0x03])),)
        )

    def test_extended_pid_marker_forms_16bit_pid(self) -> None:
        raw = _message(0x80, bytes([254, 10, 2, 0xAA, 0xBB]))
        message = parse_j1708_message(raw)

        self.assertEqual(message.parameters, (J1587Parameter(pid=266, data=bytes([0xAA, 0xBB])),))

    def test_multiple_parameters_in_one_message(self) -> None:
        raw = _message(0x80, bytes([70, 0x01, 190, 0x70, 0x17]))
        message = parse_j1708_message(raw)

        self.assertEqual(
            message.parameters,
            (
                J1587Parameter(pid=70, data=bytes([0x01])),
                J1587Parameter(pid=190, data=bytes([0x70, 0x17])),
            ),
        )

    def test_truncated_extended_pid_raises(self) -> None:
        raw = _message(0x80, bytes([254]))
        with self.assertRaisesRegex(ValueError, "truncated extended PID"):
            parse_j1708_message(raw)

    def test_truncated_parameter_length_raises(self) -> None:
        raw = _message(0x80, bytes([200]))
        with self.assertRaisesRegex(ValueError, "truncated parameter length"):
            parse_j1708_message(raw)

    def test_truncated_parameter_data_raises(self) -> None:
        raw = _message(0x80, bytes([200, 3, 0x01]))
        with self.assertRaisesRegex(ValueError, "truncated parameter data"):
            parse_j1708_message(raw)


class DecodeParameterValueTests(unittest.TestCase):
    def test_known_pid_resolves_name_value_and_units(self) -> None:
        name, value, units = decode_parameter_value(190, bytes([0x70, 0x17]))

        self.assertEqual(name, "Engine Speed")
        self.assertEqual(value, 1500.0)
        self.assertEqual(units, "rpm")

    def test_negative_offset_is_applied(self) -> None:
        # Engine Coolant Temperature: resolution 1.0, offset -40.0
        name, value, units = decode_parameter_value(110, bytes([0x6E]))

        self.assertEqual(name, "Engine Coolant Temperature")
        self.assertEqual(value, 70.0)
        self.assertEqual(units, "degC")

    def test_all_ones_sentinel_returns_none_value(self) -> None:
        name, value, units = decode_parameter_value(190, bytes([0xFF, 0xFF]))

        self.assertEqual(name, "Engine Speed")
        self.assertIsNone(value)
        self.assertEqual(units, "rpm")

    def test_unknown_pid_returns_all_none(self) -> None:
        name, value, units = decode_parameter_value(50, bytes([0xAA]))

        self.assertIsNone(name)
        self.assertIsNone(value)
        self.assertIsNone(units)


class DecodeEventsTests(unittest.TestCase):
    def test_flattens_one_event_per_parameter(self) -> None:
        raw = _message(0x80, bytes([70, 0x01, 190, 0x70, 0x17]))
        message = parse_j1708_message(raw, timestamp=1.5)

        events = decode_events([message])

        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].mid, 0x80)
        self.assertEqual(events[0].pid, 70)
        self.assertEqual(events[0].timestamp, 1.5)
        self.assertEqual(events[1].pid, 190)
        self.assertEqual(events[1].value, 1500.0)
        self.assertTrue(events[0].checksum_valid)

    def test_checksum_failure_is_propagated_to_events(self) -> None:
        raw = _message(0x80, bytes([70, 0x01]), bad_checksum=True)
        message = parse_j1708_message(raw)

        events = decode_events([message])

        self.assertFalse(events[0].checksum_valid)


class J1587MetadataTests(unittest.TestCase):
    def test_pid_lookup_known_value(self) -> None:
        from canarchy.j1587_metadata import pid_lookup

        meta = pid_lookup(190)
        self.assertIsNotNone(meta)
        self.assertEqual(meta["name"], "Engine Speed")
        self.assertEqual(meta["units"], "rpm")

    def test_pid_lookup_unknown_returns_none(self) -> None:
        from canarchy.j1587_metadata import pid_lookup

        self.assertIsNone(pid_lookup(50))

    def test_decodable_pids_includes_bundled_catalog(self) -> None:
        from canarchy.j1587_metadata import decodable_pids

        pids = decodable_pids()
        self.assertIn(190, pids)
        self.assertIn(110, pids)

    def test_j1587_pids_payload_is_sorted_by_pid(self) -> None:
        payload = j1587_pids_payload()

        pids = [entry["pid"] for entry in payload]
        self.assertEqual(pids, sorted(pids))
        self.assertIn(190, pids)


class J1587PidOverrideTests(unittest.TestCase):
    """Fleet/OEM PID extensions merge over the bundled catalog (#415)."""

    def _reload_pid_cache(self) -> None:
        from canarchy import j1587_metadata

        j1587_metadata._pid_data.cache_clear()
        j1587_metadata.decodable_pids.cache_clear()

    def test_pid_overrides_resolve_proprietary_names(self) -> None:
        import os
        import tempfile

        from canarchy.j1587_metadata import pid_lookup

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump({"260": {"name": "OEM Proprietary Brake Pressure"}}, fh)
            override_path = fh.name

        saved = os.environ.get("CANARCHY_J1587_PID_OVERRIDES")
        os.environ["CANARCHY_J1587_PID_OVERRIDES"] = override_path
        self._reload_pid_cache()
        try:
            meta = pid_lookup(260)
            self.assertIsNotNone(meta)
            self.assertEqual(meta["name"], "OEM Proprietary Brake Pressure")
            # Bundled entries survive the merge.
            self.assertEqual(pid_lookup(190)["name"], "Engine Speed")
        finally:
            if saved is None:
                os.environ.pop("CANARCHY_J1587_PID_OVERRIDES", None)
            else:
                os.environ["CANARCHY_J1587_PID_OVERRIDES"] = saved
            os.unlink(override_path)
            self._reload_pid_cache()

    def test_name_only_override_decodes_without_scaling(self) -> None:
        # A proprietary override with only a name lacks the resolution/offset/
        # units needed to scale; decoding must surface the name (and any units)
        # with a null value instead of raising KeyError.
        import os
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump({"261": {"name": "OEM Proprietary Counter"}}, fh)
            override_path = fh.name

        saved = os.environ.get("CANARCHY_J1587_PID_OVERRIDES")
        os.environ["CANARCHY_J1587_PID_OVERRIDES"] = override_path
        self._reload_pid_cache()
        try:
            name, value, units = decode_parameter_value(261, bytes([0x12]))
            self.assertEqual(name, "OEM Proprietary Counter")
            self.assertIsNone(value)
            self.assertIsNone(units)
        finally:
            if saved is None:
                os.environ.pop("CANARCHY_J1587_PID_OVERRIDES", None)
            else:
                os.environ["CANARCHY_J1587_PID_OVERRIDES"] = saved
            os.unlink(override_path)
            self._reload_pid_cache()


class IterJ1708MessagesFromFileTests(unittest.TestCase):
    def test_parses_fixture_messages(self) -> None:
        messages = list(iter_j1708_messages_from_file(str(FIXTURES / "j1708_sample.j1708")))

        self.assertEqual(len(messages), 7)
        parameter_count = sum(len(message.parameters) for message in messages)
        self.assertEqual(parameter_count, 8)
        checksum_failures = sum(1 for message in messages if not message.checksum_valid)
        self.assertEqual(checksum_failures, 1)

    def test_offset_and_max_frames_limit_results(self) -> None:
        messages = list(
            iter_j1708_messages_from_file(
                str(FIXTURES / "j1708_sample.j1708"), offset=2, max_frames=1
            )
        )

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].timestamp, 0.1)

    def test_missing_file_raises_source_unavailable(self) -> None:
        with self.assertRaises(TransportError) as ctx:
            list(iter_j1708_messages_from_file("/tmp/does-not-exist.j1708"))

        self.assertEqual(ctx.exception.code, "J1587_SOURCE_UNAVAILABLE")

    def test_line_not_matching_format_raises_source_invalid(self) -> None:
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".j1708", delete=False) as fh:
            fh.write("not a valid line\n")
            path = fh.name

        with self.assertRaises(TransportError) as ctx:
            list(iter_j1708_messages_from_file(path))

        self.assertEqual(ctx.exception.code, "J1587_SOURCE_INVALID")

    def test_odd_length_hex_raises_source_invalid(self) -> None:
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".j1708", delete=False) as fh:
            fh.write("(0.000000) j1708 80BE701\n")
            path = fh.name

        with self.assertRaises(TransportError) as ctx:
            list(iter_j1708_messages_from_file(path))

        self.assertEqual(ctx.exception.code, "J1587_SOURCE_INVALID")
        self.assertIn("odd number of hex digits", str(ctx.exception))

    def test_truncated_message_raises_source_invalid(self) -> None:
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".j1708", delete=False) as fh:
            # A bare MID byte with no checksum is too short to be a message.
            fh.write("(0.000000) j1708 80\n")
            path = fh.name

        with self.assertRaises(TransportError) as ctx:
            list(iter_j1708_messages_from_file(path))

        self.assertEqual(ctx.exception.code, "J1587_SOURCE_INVALID")
        self.assertIn("is malformed", str(ctx.exception))


class J1587CliTests(unittest.TestCase):
    def test_decode_returns_j1587_events(self) -> None:
        exit_code, stdout, _ = run_cli(
            "j1587", "decode", "--file", str(FIXTURES / "j1708_sample.j1708"), "--json"
        )
        self.assertEqual(exit_code, EXIT_OK)

        payload = json.loads(stdout)
        data = payload["data"]
        self.assertEqual(data["mode"], "passive")
        self.assertEqual(data["message_count"], 7)
        self.assertEqual(data["parameter_count"], 8)
        self.assertEqual(data["checksum_failures"], 1)

        first = data["events"][0]["payload"]
        self.assertEqual(first["mid"], 0x80)
        self.assertEqual(first["pid"], 190)
        self.assertEqual(first["name"], "Engine Speed")
        self.assertEqual(first["value"], 1500.0)
        self.assertEqual(first["units"], "rpm")
        self.assertTrue(first["checksum_valid"])

    def test_decode_flags_invalid_checksum(self) -> None:
        exit_code, stdout, _ = run_cli(
            "j1587", "decode", "--file", str(FIXTURES / "j1708_sample.j1708"), "--json"
        )
        self.assertEqual(exit_code, EXIT_OK)

        payload = json.loads(stdout)
        checksum_flags = [event["payload"]["checksum_valid"] for event in payload["data"]["events"]]
        self.assertIn(False, checksum_flags)

    def test_decode_jsonl_output(self) -> None:
        exit_code, stdout, _ = run_cli(
            "j1587", "decode", "--file", str(FIXTURES / "j1708_sample.j1708"), "--jsonl"
        )
        self.assertEqual(exit_code, EXIT_OK)

        lines = [json.loads(line) for line in stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 8)
        self.assertEqual(lines[0]["event_type"], "j1587_parameter")

    def test_decode_text_output_is_pretty_printed(self) -> None:
        exit_code, stdout, stderr = run_cli(
            "j1587", "decode", "--file", str(FIXTURES / "j1708_sample.j1708"), "--text"
        )
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")
        self.assertIn("command: j1587 decode", stdout)
        self.assertIn(f"file: {FIXTURES / 'j1708_sample.j1708'}", stdout)
        self.assertIn("messages: 7", stdout)
        self.assertIn("checksum_failures: 1", stdout)
        self.assertIn("mid=128 pid=190 name=Engine Speed value=1500.0 units=rpm raw=7017", stdout)
        self.assertIn("checksum=invalid", stdout)

    def test_decode_max_frames_limits_results(self) -> None:
        exit_code, stdout, _ = run_cli(
            "j1587",
            "decode",
            "--file",
            str(FIXTURES / "j1708_sample.j1708"),
            "--max-frames",
            "1",
            "--json",
        )
        self.assertEqual(exit_code, EXIT_OK)

        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["message_count"], 1)

    def test_decode_rejects_zero_max_frames(self) -> None:
        exit_code, stdout, _ = run_cli(
            "j1587",
            "decode",
            "--file",
            str(FIXTURES / "j1708_sample.j1708"),
            "--max-frames",
            "0",
            "--json",
        )
        self.assertEqual(exit_code, EXIT_USER_ERROR)

        payload = json.loads(stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["errors"][0]["code"], "INVALID_MAX_FRAMES")

    def test_decode_rejects_negative_seconds(self) -> None:
        exit_code, stdout, _ = run_cli(
            "j1587",
            "decode",
            "--file",
            str(FIXTURES / "j1708_sample.j1708"),
            "--seconds",
            "-1",
            "--json",
        )
        self.assertEqual(exit_code, EXIT_USER_ERROR)

        payload = json.loads(stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["errors"][0]["code"], "INVALID_ANALYSIS_SECONDS")

    def test_decode_missing_file_returns_structured_error(self) -> None:
        exit_code, stdout, _ = run_cli(
            "j1587", "decode", "--file", "/tmp/does-not-exist.j1708", "--json"
        )
        self.assertEqual(exit_code, EXIT_USER_ERROR)

        payload = json.loads(stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["errors"][0]["code"], "J1587_SOURCE_UNAVAILABLE")

    def test_decode_malformed_line_returns_structured_error(self) -> None:
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".j1708", delete=False) as fh:
            fh.write("(0.000000) j1708 80BE701\n")
            path = fh.name

        exit_code, stdout, _ = run_cli("j1587", "decode", "--file", path, "--json")
        self.assertEqual(exit_code, EXIT_USER_ERROR)

        payload = json.loads(stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["errors"][0]["code"], "J1587_SOURCE_INVALID")

    def test_pids_returns_bundled_catalog(self) -> None:
        exit_code, stdout, _ = run_cli("j1587", "pids", "--json")
        self.assertEqual(exit_code, EXIT_OK)

        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["mode"], "reference")
        self.assertGreaterEqual(payload["data"]["pid_count"], 11)
        pids = {entry["pid"]: entry for entry in payload["data"]["pids"]}
        self.assertEqual(pids[190]["name"], "Engine Speed")
        self.assertEqual(pids[190]["units"], "rpm")

    def test_pids_text_output_is_pretty_printed(self) -> None:
        exit_code, stdout, stderr = run_cli("j1587", "pids", "--text")
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")
        self.assertIn("command: j1587 pids", stdout)
        self.assertIn("catalog:", stdout)
        self.assertIn("pid=190 name=Engine Speed units=rpm length=2", stdout)


if __name__ == "__main__":
    unittest.main()
