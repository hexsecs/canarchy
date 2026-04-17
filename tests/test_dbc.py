from __future__ import annotations

import contextlib
import io
import json
import unittest
from pathlib import Path

from canarchy.cli import EXIT_DECODE_ERROR, EXIT_OK, main
from canarchy.dbc import decode_frames, encode_message, load_database
from canarchy.transport import LocalTransport


FIXTURES = Path(__file__).parent / "fixtures"


def run_cli(*argv: str) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = main(argv)
    return exit_code, stdout.getvalue(), stderr.getvalue()


class DbcTests(unittest.TestCase):
    def test_load_database_succeeds_for_valid_fixture(self) -> None:
        database = load_database(str(FIXTURES / "sample.dbc"))
        self.assertEqual(database.get_message_by_name("EngineStatus1").frame_id, 0x18FEEE31)

    def test_decode_frames_returns_decoded_and_signal_events(self) -> None:
        frames = LocalTransport().frames_from_file("capture.log")
        events = decode_frames(frames, str(FIXTURES / "sample.dbc"))

        decoded_messages = [event for event in events if event["event_type"] == "decoded_message"]
        self.assertEqual(len(decoded_messages), 2)
        self.assertEqual(decoded_messages[0]["payload"]["message_name"], "EngineStatus1")
        self.assertEqual(decoded_messages[1]["payload"]["message_name"], "EngineSpeed1")

    def test_encode_message_returns_frame(self) -> None:
        frame, events = encode_message(
            str(FIXTURES / "sample.dbc"),
            "EngineStatus1",
            {"CoolantTemp": 55, "OilTemp": 65, "Load": 40, "LampState": 1},
        )

        self.assertEqual(frame.arbitration_id, 0x18FEEE31)
        self.assertTrue(frame.is_extended_id)
        self.assertEqual(events[0]["event_type"], "frame")

    def test_decode_cli_returns_structured_results(self) -> None:
        exit_code, stdout, stderr = run_cli(
            "decode",
            "capture.log",
            "--dbc",
            str(FIXTURES / "sample.dbc"),
            "--json",
        )
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")

        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["matched_messages"], 2)
        self.assertEqual(payload["data"]["events"][0]["payload"]["message_name"], "EngineStatus1")

    def test_encode_cli_returns_structured_frame(self) -> None:
        exit_code, stdout, stderr = run_cli(
            "encode",
            "--dbc",
            str(FIXTURES / "sample.dbc"),
            "EngineStatus1",
            "CoolantTemp=55",
            "OilTemp=65",
            "Load=40",
            "LampState=1",
            "--json",
        )
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")

        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["frame"]["arbitration_id"], 0x18FEEE31)
        self.assertEqual(payload["data"]["events"][0]["event_type"], "frame")

    def test_invalid_dbc_returns_decode_error(self) -> None:
        exit_code, stdout, _ = run_cli(
            "decode",
            "capture.log",
            "--dbc",
            str(FIXTURES / "invalid.dbc"),
            "--json",
        )
        self.assertEqual(exit_code, EXIT_DECODE_ERROR)

        payload = json.loads(stdout)
        self.assertEqual(payload["errors"][0]["code"], "DBC_LOAD_FAILED")
