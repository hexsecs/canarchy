from __future__ import annotations

import json
import unittest
from pathlib import Path

from canarchy.cli import EXIT_OK, EXIT_USER_ERROR
from canarchy.j2497 import (
    decode_events,
    iter_j2497_frames_from_file,
    j2497_mids_payload,
    parse_j2497_frame,
)
from canarchy.transport import TransportError
from tests.test_cli import run_cli

FIXTURES = Path(__file__).parent / "fixtures"


def _frame(mid: int, payload: bytes, *, bad_checksum: bool = False) -> bytes:
    """Build a raw J2497 frame with a valid (or deliberately invalid) checksum."""

    body = bytes([mid]) + payload
    checksum = (-sum(body)) % 256
    if bad_checksum:
        checksum = (checksum + 1) % 256
    return body + bytes([checksum])


class ParseJ2497FrameTests(unittest.TestCase):
    def test_too_short_frame_raises(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least a MID and checksum byte"):
            parse_j2497_frame(bytes([0x89]))

    def test_valid_checksum_is_recognized(self) -> None:
        raw = _frame(0x89, bytes([0x2C, 0x01]))
        message = parse_j2497_frame(raw)

        self.assertEqual(message.mid, 0x89)
        self.assertTrue(message.checksum_valid)
        self.assertEqual(message.data, bytes([0x2C, 0x01]))

    def test_invalid_checksum_is_flagged(self) -> None:
        raw = _frame(0x89, bytes([0x2C, 0x01]), bad_checksum=True)
        message = parse_j2497_frame(raw)

        self.assertFalse(message.checksum_valid)

    def test_data_is_bytes_between_mid_and_checksum(self) -> None:
        raw = _frame(0x8A, bytes([0x90, 0x12, 0x34]))
        message = parse_j2497_frame(raw)

        self.assertEqual(message.mid, 0x8A)
        self.assertEqual(message.data, bytes([0x90, 0x12, 0x34]))

    def test_empty_data_frame_is_accepted(self) -> None:
        # A bare MID + checksum is a legal (data-less) frame.
        raw = _frame(0x89, b"")
        message = parse_j2497_frame(raw)

        self.assertEqual(message.mid, 0x89)
        self.assertEqual(message.data, b"")
        self.assertTrue(message.checksum_valid)


class DecodeEventsTests(unittest.TestCase):
    def test_one_event_per_frame_resolves_known_mid(self) -> None:
        raw = _frame(0x89, bytes([0x2C, 0x01]))
        message = parse_j2497_frame(raw, timestamp=1.5)

        events = decode_events([message])

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].mid, 0x89)
        self.assertEqual(events[0].name, "Brakes - Trailer #1 (ABS)")
        self.assertEqual(events[0].data, bytes([0x2C, 0x01]))
        self.assertEqual(events[0].timestamp, 1.5)
        self.assertTrue(events[0].checksum_valid)

    def test_unknown_mid_resolves_to_none_name(self) -> None:
        raw = _frame(0xC0, bytes([0x11, 0xAB]))
        message = parse_j2497_frame(raw)

        events = decode_events([message])

        self.assertIsNone(events[0].name)

    def test_checksum_failure_is_propagated_to_events(self) -> None:
        raw = _frame(0x89, bytes([0x2C, 0x01]), bad_checksum=True)
        message = parse_j2497_frame(raw)

        events = decode_events([message])

        self.assertFalse(events[0].checksum_valid)


class J2497MetadataTests(unittest.TestCase):
    def test_mid_lookup_known_value(self) -> None:
        from canarchy.j2497_metadata import mid_lookup

        meta = mid_lookup(137)
        self.assertIsNotNone(meta)
        self.assertEqual(meta["name"], "Brakes - Trailer #1 (ABS)")

    def test_mid_lookup_unknown_returns_none(self) -> None:
        from canarchy.j2497_metadata import mid_lookup

        self.assertIsNone(mid_lookup(192))

    def test_mids_payload_is_sorted_by_mid(self) -> None:
        payload = j2497_mids_payload()

        mids = [entry["mid"] for entry in payload]
        self.assertEqual(mids, sorted(mids))
        self.assertIn(137, mids)


class J2497MidOverrideTests(unittest.TestCase):
    """Fleet/OEM MID extensions merge over the bundled catalog (#416)."""

    def _reload_mid_cache(self) -> None:
        from canarchy import j2497_metadata

        j2497_metadata._mid_data.cache_clear()
        j2497_metadata.known_mids.cache_clear()

    def test_mid_overrides_resolve_proprietary_names(self) -> None:
        import os
        import tempfile

        from canarchy.j2497_metadata import mid_lookup

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump({"200": {"name": "OEM Trailer Telematics"}}, fh)
            override_path = fh.name

        saved = os.environ.get("CANARCHY_J2497_MID_OVERRIDES")
        os.environ["CANARCHY_J2497_MID_OVERRIDES"] = override_path
        self._reload_mid_cache()
        try:
            meta = mid_lookup(200)
            self.assertIsNotNone(meta)
            self.assertEqual(meta["name"], "OEM Trailer Telematics")
            # Bundled entries survive the merge.
            self.assertEqual(mid_lookup(137)["name"], "Brakes - Trailer #1 (ABS)")
        finally:
            if saved is None:
                os.environ.pop("CANARCHY_J2497_MID_OVERRIDES", None)
            else:
                os.environ["CANARCHY_J2497_MID_OVERRIDES"] = saved
            os.unlink(override_path)
            self._reload_mid_cache()


class IterJ2497FramesFromFileTests(unittest.TestCase):
    def test_parses_fixture_frames(self) -> None:
        messages = list(iter_j2497_frames_from_file(str(FIXTURES / "j2497_sample.j2497")))

        self.assertEqual(len(messages), 6)
        checksum_failures = sum(1 for message in messages if not message.checksum_valid)
        self.assertEqual(checksum_failures, 1)

    def test_offset_and_max_frames_limit_results(self) -> None:
        messages = list(
            iter_j2497_frames_from_file(
                str(FIXTURES / "j2497_sample.j2497"), offset=2, max_frames=1
            )
        )

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].timestamp, 0.1)

    def test_missing_file_raises_source_unavailable(self) -> None:
        with self.assertRaises(TransportError) as ctx:
            list(iter_j2497_frames_from_file("/tmp/does-not-exist.j2497"))

        self.assertEqual(ctx.exception.code, "J2497_SOURCE_UNAVAILABLE")

    def test_line_not_matching_format_raises_source_invalid(self) -> None:
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".j2497", delete=False) as fh:
            fh.write("not a valid line\n")
            path = fh.name

        with self.assertRaises(TransportError) as ctx:
            list(iter_j2497_frames_from_file(path))

        self.assertEqual(ctx.exception.code, "J2497_SOURCE_INVALID")

    def test_odd_length_hex_raises_source_invalid(self) -> None:
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".j2497", delete=False) as fh:
            fh.write("(0.000000) j2497 892C0\n")
            path = fh.name

        with self.assertRaises(TransportError) as ctx:
            list(iter_j2497_frames_from_file(path))

        self.assertEqual(ctx.exception.code, "J2497_SOURCE_INVALID")
        self.assertIn("odd number of hex digits", str(ctx.exception))

    def test_truncated_frame_raises_source_invalid(self) -> None:
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".j2497", delete=False) as fh:
            # A bare MID byte with no checksum is too short to be a frame.
            fh.write("(0.000000) j2497 89\n")
            path = fh.name

        with self.assertRaises(TransportError) as ctx:
            list(iter_j2497_frames_from_file(path))

        self.assertEqual(ctx.exception.code, "J2497_SOURCE_INVALID")
        self.assertIn("is malformed", str(ctx.exception))


class J2497CliTests(unittest.TestCase):
    def test_decode_returns_j2497_events(self) -> None:
        exit_code, stdout, _ = run_cli(
            "j2497", "decode", "--file", str(FIXTURES / "j2497_sample.j2497"), "--json"
        )
        self.assertEqual(exit_code, EXIT_OK)

        payload = json.loads(stdout)
        data = payload["data"]
        self.assertEqual(data["mode"], "passive")
        self.assertEqual(data["frame_count"], 6)
        self.assertEqual(data["checksum_failures"], 1)

        first = data["events"][0]["payload"]
        self.assertEqual(first["mid"], 0x89)
        self.assertEqual(first["name"], "Brakes - Trailer #1 (ABS)")
        self.assertEqual(first["data"], "2c01")
        self.assertTrue(first["checksum_valid"])

    def test_decode_flags_invalid_checksum(self) -> None:
        exit_code, stdout, _ = run_cli(
            "j2497", "decode", "--file", str(FIXTURES / "j2497_sample.j2497"), "--json"
        )
        self.assertEqual(exit_code, EXIT_OK)

        payload = json.loads(stdout)
        checksum_flags = [event["payload"]["checksum_valid"] for event in payload["data"]["events"]]
        self.assertIn(False, checksum_flags)

    def test_decode_jsonl_output(self) -> None:
        exit_code, stdout, _ = run_cli(
            "j2497", "decode", "--file", str(FIXTURES / "j2497_sample.j2497"), "--jsonl"
        )
        self.assertEqual(exit_code, EXIT_OK)

        lines = [json.loads(line) for line in stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 6)
        self.assertEqual(lines[0]["event_type"], "j2497_message")

    def test_decode_text_output_is_pretty_printed(self) -> None:
        exit_code, stdout, stderr = run_cli(
            "j2497", "decode", "--file", str(FIXTURES / "j2497_sample.j2497"), "--text"
        )
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")
        self.assertIn("command: j2497 decode", stdout)
        self.assertIn(f"file: {FIXTURES / 'j2497_sample.j2497'}", stdout)
        self.assertIn("frames: 6", stdout)
        self.assertIn("checksum_failures: 1", stdout)
        self.assertIn("mid=137 name=Brakes - Trailer #1 (ABS) data=2c01", stdout)
        self.assertIn("checksum=invalid", stdout)

    def test_decode_max_frames_limits_results(self) -> None:
        exit_code, stdout, _ = run_cli(
            "j2497",
            "decode",
            "--file",
            str(FIXTURES / "j2497_sample.j2497"),
            "--max-frames",
            "1",
            "--json",
        )
        self.assertEqual(exit_code, EXIT_OK)

        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["frame_count"], 1)

    def test_decode_rejects_zero_max_frames(self) -> None:
        exit_code, stdout, _ = run_cli(
            "j2497",
            "decode",
            "--file",
            str(FIXTURES / "j2497_sample.j2497"),
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
            "j2497",
            "decode",
            "--file",
            str(FIXTURES / "j2497_sample.j2497"),
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
            "j2497", "decode", "--file", "/tmp/does-not-exist.j2497", "--json"
        )
        self.assertEqual(exit_code, EXIT_USER_ERROR)

        payload = json.loads(stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["errors"][0]["code"], "J2497_SOURCE_UNAVAILABLE")

    def test_decode_malformed_line_returns_structured_error(self) -> None:
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".j2497", delete=False) as fh:
            # A bare MID byte with no checksum is too short to be a frame.
            fh.write("(0.000000) j2497 89\n")
            path = fh.name

        exit_code, stdout, _ = run_cli("j2497", "decode", "--file", path, "--json")
        self.assertEqual(exit_code, EXIT_USER_ERROR)

        payload = json.loads(stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["errors"][0]["code"], "J2497_SOURCE_INVALID")

    def test_mids_returns_bundled_catalog(self) -> None:
        exit_code, stdout, _ = run_cli("j2497", "mids", "--json")
        self.assertEqual(exit_code, EXIT_OK)

        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["mode"], "reference")
        self.assertGreaterEqual(payload["data"]["mid_count"], 8)
        mids = {entry["mid"]: entry for entry in payload["data"]["mids"]}
        self.assertEqual(mids[137]["name"], "Brakes - Trailer #1 (ABS)")

    def test_mids_text_output_is_pretty_printed(self) -> None:
        exit_code, stdout, stderr = run_cli("j2497", "mids", "--text")
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")
        self.assertIn("command: j2497 mids", stdout)
        self.assertIn("catalog:", stdout)
        self.assertIn("mid=137 name=Brakes - Trailer #1 (ABS)", stdout)


if __name__ == "__main__":
    unittest.main()
