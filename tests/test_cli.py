from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from canarchy.cli import EXIT_OK, EXIT_TRANSPORT_ERROR, EXIT_USER_ERROR, main
from canarchy.transport import PythonCanBackend, TransportError


FIXTURES = Path(__file__).parent / "fixtures"


def run_cli(*argv: str) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = main(argv)
    return exit_code, stdout.getvalue(), stderr.getvalue()


@contextlib.contextmanager
def working_directory(path: str):
    original = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(original)


class FakeBus:
    def __init__(self, messages: list[object] | None = None) -> None:
        self.messages = list(messages or [])

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def recv(self, timeout: float | None = None):
        del timeout
        if self.messages:
            return self.messages.pop(0)
        return None

    def shutdown(self) -> None:
        return None


class CliTests(unittest.TestCase):
    def fake_message(self, arbitration_id: int, data: bytes, *, is_extended_id: bool = False):
        return type(
            "FakeMessage",
            (),
            {
                "arbitration_id": arbitration_id,
                "data": data,
                "is_extended_id": is_extended_id,
                "is_remote_frame": False,
                "is_error_frame": False,
                "is_fd": False,
                "bitrate_switch": False,
                "error_state_indicator": False,
                "timestamp": 0.0,
            },
        )()

    def test_help_exits_successfully(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as ctx:
                main(("--help",))
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("CLI-first CAN security research toolkit", stdout.getvalue())

    def test_missing_subcommand_returns_user_error(self) -> None:
        exit_code, stdout, stderr = run_cli()
        self.assertEqual(exit_code, EXIT_USER_ERROR)
        self.assertIn("INVALID_ARGUMENTS", stdout)
        self.assertIn("the following arguments are required: command_name", stdout)
        self.assertIn("Run `canarchy --help`", stdout)
        self.assertEqual(stderr, "")

    def test_capture_json_output_is_structured(self) -> None:
        exit_code, stdout, stderr = run_cli("capture", "can0", "--json")
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")

        payload = json.loads(stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["command"], "capture")
        self.assertEqual(payload["data"]["interface"], "can0")
        self.assertEqual(payload["data"]["display"], "structured")
        self.assertEqual(payload["data"]["mode"], "passive")
        self.assertEqual(payload["data"]["status"], "implemented")
        self.assertEqual(payload["data"]["implementation"], "scaffold transport")
        self.assertEqual(payload["data"]["transport_backend"], "scaffold")
        self.assertEqual(len(payload["data"]["events"]), 2)
        self.assertEqual(payload["data"]["events"][0]["event_type"], "frame")
        self.assertEqual(payload["data"]["events"][0]["payload"]["frame"]["interface"], "can0")
        self.assertEqual(payload["warnings"], [])

    def test_send_json_output_marks_active_mode(self) -> None:
        exit_code, stdout, stderr = run_cli("send", "can0", "0x123", "11223344", "--json")
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")

        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["mode"], "active")
        self.assertEqual(payload["data"]["status"], "implemented")
        self.assertEqual(payload["data"]["implementation"], "scaffold transport")
        self.assertEqual(payload["data"]["transport_backend"], "scaffold")
        self.assertEqual(payload["data"]["frame"]["arbitration_id"], 0x123)
        self.assertEqual(payload["data"]["events"][0]["event_type"], "alert")
        self.assertEqual(
            payload["warnings"][0],
            "Active transmission is intentionally distinct from passive monitoring workflows.",
        )

    def test_capture_candump_table_output_is_pretty_printed(self) -> None:
        exit_code, stdout, stderr = run_cli("capture", "can0", "--candump")
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")
        lines = stdout.strip().splitlines()
        self.assertEqual(lines[0], "(0.000000) can0 18FEEE31#11223344")
        self.assertEqual(lines[1], "(0.100000) can0 18F00431#AABBCCDD")

    def test_capture_candump_raw_output_matches_dump_lines(self) -> None:
        exit_code, stdout, stderr = run_cli("capture", "can0", "--candump", "--raw")
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")
        lines = stdout.strip().splitlines()
        self.assertEqual(lines[0], "(0.000000) can0 18FEEE31#11223344")
        self.assertEqual(lines[1], "(0.100000) can0 18F00431#AABBCCDD")

    def test_capture_candump_json_keeps_structured_payload(self) -> None:
        exit_code, stdout, stderr = run_cli("capture", "can0", "--candump", "--json")
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["display"], "candump")
        self.assertEqual(payload["data"]["events"][0]["event_type"], "frame")

    def test_filter_json_output_returns_matching_frames(self) -> None:
        exit_code, stdout, _ = run_cli(
            "filter", str(FIXTURES / "sample.candump"), "id==0x18FEEE31", "--json"
        )
        self.assertEqual(exit_code, EXIT_OK)

        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["mode"], "passive")
        self.assertEqual(len(payload["data"]["events"]), 1)
        self.assertEqual(
            payload["data"]["events"][0]["payload"]["frame"]["arbitration_id"], 0x18FEEE31
        )

    def test_stats_json_output_returns_summary(self) -> None:
        exit_code, stdout, _ = run_cli("stats", str(FIXTURES / "sample.candump"), "--json")
        self.assertEqual(exit_code, EXIT_OK)

        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["mode"], "passive")
        self.assertEqual(payload["data"]["total_frames"], 3)
        self.assertEqual(payload["data"]["unique_arbitration_ids"], 3)

    def test_nested_j1939_command_works(self) -> None:
        exit_code, stdout, _ = run_cli("j1939", "monitor", "--pgn", "65262", "--raw")
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stdout.strip(), "j1939 monitor")

    def test_j1939_monitor_returns_observations(self) -> None:
        exit_code, stdout, _ = run_cli("j1939", "monitor", "--json")
        self.assertEqual(exit_code, EXIT_OK)

        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["mode"], "passive")
        self.assertEqual(payload["data"]["events"][0]["event_type"], "j1939_pgn")
        self.assertEqual(payload["data"]["events"][0]["payload"]["pgn"], 65262)
        self.assertEqual(payload["data"]["events"][0]["payload"]["source_address"], 0x31)
        self.assertEqual(payload["data"]["events"][0]["payload"]["priority"], 6)

    def test_j1939_monitor_pgn_filter_is_applied(self) -> None:
        exit_code, stdout, _ = run_cli("j1939", "monitor", "--pgn", "65262", "--json")
        self.assertEqual(exit_code, EXIT_OK)

        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["pgn_filter"], 65262)
        self.assertEqual(len(payload["data"]["events"]), 1)
        self.assertEqual(payload["data"]["events"][0]["payload"]["pgn"], 65262)

    def test_j1939_decode_returns_j1939_events(self) -> None:
        exit_code, stdout, _ = run_cli(
            "j1939", "decode", str(FIXTURES / "sample.candump"), "--json"
        )
        self.assertEqual(exit_code, EXIT_OK)

        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["file"], str(FIXTURES / "sample.candump"))
        self.assertEqual(payload["data"]["events"][1]["payload"]["pgn"], 61444)

    def test_j1939_monitor_table_output_is_pretty_printed(self) -> None:
        exit_code, stdout, stderr = run_cli("j1939", "monitor", "--pgn", "65262", "--table")
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")
        self.assertIn("command: j1939 monitor", stdout)
        self.assertIn("pgn_filter: 65262", stdout)
        self.assertIn("observations:", stdout)
        self.assertIn("pgn=65262", stdout)
        self.assertIn("sa=0x31", stdout)
        self.assertIn("da=broadcast", stdout)
        self.assertIn("prio=6", stdout)
        self.assertIn("data=11223344", stdout)

    def test_j1939_decode_table_output_is_pretty_printed(self) -> None:
        exit_code, stdout, stderr = run_cli(
            "j1939", "decode", str(FIXTURES / "sample.candump"), "--table"
        )
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")
        self.assertIn("command: j1939 decode", stdout)
        self.assertIn(f"file: {FIXTURES / 'sample.candump'}", stdout)
        self.assertIn("pgn=61444", stdout)
        self.assertIn("sa=0x31", stdout)

    def test_uds_scan_returns_transaction_events(self) -> None:
        exit_code, stdout, stderr = run_cli("uds", "scan", "can0", "--json")
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")

        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["mode"], "active")
        self.assertEqual(payload["data"]["responder_count"], 2)
        self.assertEqual(payload["data"]["events"][0]["event_type"], "uds_transaction")
        self.assertEqual(
            payload["data"]["events"][0]["payload"]["service_name"], "DiagnosticSessionControl"
        )
        self.assertEqual(
            payload["warnings"][1],
            "UDS scanning is active and should be used intentionally on a controlled bus.",
        )

    def test_uds_trace_returns_transaction_events(self) -> None:
        exit_code, stdout, stderr = run_cli("uds", "trace", "can0", "--json")
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")

        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["mode"], "passive")
        self.assertEqual(payload["data"]["transaction_count"], 2)
        self.assertEqual(payload["data"]["events"][1]["payload"]["service"], 0x27)
        self.assertEqual(payload["data"]["events"][1]["payload"]["service_name"], "SecurityAccess")

    def test_uds_transport_error_returns_backend_exit_code(self) -> None:
        exit_code, stdout, stderr = run_cli("uds", "scan", "offline0", "--json")
        self.assertEqual(exit_code, EXIT_TRANSPORT_ERROR)
        self.assertEqual(stderr, "")

        payload = json.loads(stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["errors"][0]["code"], "TRANSPORT_UNAVAILABLE")

    def test_session_save_load_and_show_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with working_directory(temp_dir):
                exit_code, stdout, stderr = run_cli(
                    "session",
                    "save",
                    "lab-a",
                    "--interface",
                    "can0",
                    "--dbc",
                    "tests/fixtures/sample.dbc",
                    "--capture",
                    "capture.log",
                    "--json",
                )
                self.assertEqual(exit_code, EXIT_OK)
                self.assertEqual(stderr, "")
                payload = json.loads(stdout)
                self.assertEqual(payload["data"]["mode"], "stateful")
                self.assertEqual(payload["data"]["session"]["name"], "lab-a")
                self.assertEqual(payload["data"]["session"]["context"]["interface"], "can0")

                exit_code, stdout, _ = run_cli("session", "load", "lab-a", "--json")
                self.assertEqual(exit_code, EXIT_OK)
                payload = json.loads(stdout)
                self.assertEqual(payload["data"]["session"]["name"], "lab-a")
                self.assertEqual(payload["data"]["session"]["context"]["capture"], "capture.log")

                exit_code, stdout, _ = run_cli("session", "show", "--json")
                self.assertEqual(exit_code, EXIT_OK)
                payload = json.loads(stdout)
                self.assertEqual(payload["data"]["active_session"]["name"], "lab-a")
                self.assertEqual(payload["data"]["sessions"][0]["name"], "lab-a")

    def test_session_load_missing_returns_user_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with working_directory(temp_dir):
                exit_code, stdout, stderr = run_cli("session", "load", "missing", "--json")
                self.assertEqual(exit_code, EXIT_USER_ERROR)
                self.assertEqual(stderr, "")
                payload = json.loads(stdout)
                self.assertEqual(payload["errors"][0]["code"], "SESSION_NOT_FOUND")

    def test_shell_command_reuses_cli_parser(self) -> None:
        exit_code, stdout, stderr = run_cli("shell", "--command", "capture can0 --raw")
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")
        self.assertEqual(stdout.strip(), "capture")

    def test_usage_error_respects_json_output(self) -> None:
        exit_code, stdout, stderr = run_cli("decode", "capture.log", "--json")
        self.assertEqual(exit_code, EXIT_USER_ERROR)
        self.assertEqual(stderr, "")

        payload = json.loads(stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["command"], "cli")
        self.assertEqual(payload["errors"][0]["code"], "INVALID_ARGUMENTS")

    def test_replay_rate_validation_returns_structured_error(self) -> None:
        exit_code, stdout, stderr = run_cli(
            "replay", str(FIXTURES / "sample.candump"), "--rate", "0", "--json"
        )
        self.assertEqual(exit_code, EXIT_USER_ERROR)
        self.assertEqual(stderr, "")

        payload = json.loads(stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["command"], "replay")
        self.assertEqual(payload["errors"][0]["code"], "INVALID_RATE")
        self.assertEqual(payload["data"]["rate"], 0.0)

    def test_replay_json_output_is_structured(self) -> None:
        exit_code, stdout, stderr = run_cli(
            "replay", str(FIXTURES / "sample.candump"), "--rate", "2.0", "--json"
        )
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")

        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["mode"], "active")
        self.assertEqual(payload["data"]["frame_count"], 3)
        self.assertEqual(payload["data"]["duration"], 0.1)
        self.assertEqual(payload["data"]["events"][0]["event_type"], "replay_event")
        self.assertEqual(
            payload["warnings"][1],
            "Replay schedules active frame transmission; use it intentionally on a controlled bus.",
        )

    def test_replay_missing_source_returns_transport_error(self) -> None:
        exit_code, stdout, _ = run_cli("replay", "missing.log", "--json")
        self.assertEqual(exit_code, EXIT_TRANSPORT_ERROR)

        payload = json.loads(stdout)
        self.assertEqual(payload["errors"][0]["code"], "CAPTURE_SOURCE_UNAVAILABLE")

    def test_jsonl_output_is_single_json_line(self) -> None:
        exit_code, stdout, _ = run_cli("capture", "can0", "--jsonl")
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(len(stdout.strip().splitlines()), 1)

        payload = json.loads(stdout)
        self.assertEqual(payload["command"], "capture")

    def test_raw_error_output_is_message_only(self) -> None:
        exit_code, stdout, _ = run_cli("j1939", "pgn", "300000", "--raw")
        self.assertEqual(exit_code, EXIT_USER_ERROR)
        self.assertEqual(stdout.strip(), "J1939 PGN must be between 0 and 262143.")

    def test_transport_error_returns_backend_exit_code(self) -> None:
        exit_code, stdout, stderr = run_cli("capture", "offline0", "--json")
        self.assertEqual(exit_code, EXIT_TRANSPORT_ERROR)
        self.assertEqual(stderr, "")

        payload = json.loads(stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["errors"][0]["code"], "TRANSPORT_UNAVAILABLE")

    def test_capture_uses_python_can_backend_when_requested(self) -> None:
        fake_bus = FakeBus(
            [
                self.fake_message(0x123, bytes.fromhex("11223344")),
                self.fake_message(0x18FEEE31, bytes.fromhex("AABBCCDD"), is_extended_id=True),
            ]
        )
        with patch.dict(
            os.environ,
            {
                "CANARCHY_TRANSPORT_BACKEND": "python-can",
                "CANARCHY_PYTHON_CAN_INTERFACE": "virtual",
            },
            clear=False,
        ):
            with patch.object(PythonCanBackend, "_open_bus", return_value=fake_bus):
                exit_code, stdout, stderr = run_cli("capture", "can0", "--json")

        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertEqual(len(payload["data"]["events"]), 2)
        self.assertEqual(payload["data"]["transport_backend"], "python-can")
        self.assertEqual(payload["data"]["python_can_interface"], "virtual")
        self.assertEqual(payload["data"]["implementation"], "live transport")
        self.assertEqual(payload["data"]["events"][0]["payload"]["frame"]["arbitration_id"], 0x123)
        self.assertFalse(payload["data"]["events"][0]["payload"]["frame"]["is_extended_id"])
        self.assertEqual(
            payload["data"]["events"][1]["payload"]["frame"]["arbitration_id"], 0x18FEEE31
        )
        self.assertTrue(payload["data"]["events"][1]["payload"]["frame"]["is_extended_id"])

    def test_capture_candump_uses_python_can_backend_when_requested(self) -> None:
        fake_bus = FakeBus(
            [
                self.fake_message(0x123, bytes.fromhex("11223344")),
                self.fake_message(0x18FEEE31, bytes.fromhex("AABBCCDD"), is_extended_id=True),
            ]
        )
        with patch.dict(
            os.environ,
            {
                "CANARCHY_TRANSPORT_BACKEND": "python-can",
                "CANARCHY_PYTHON_CAN_INTERFACE": "virtual",
            },
            clear=False,
        ):
            with patch.object(PythonCanBackend, "_open_bus", return_value=fake_bus):
                exit_code, stdout, stderr = run_cli("capture", "vcan0", "--candump")

        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")
        lines = stdout.strip().splitlines()
        self.assertEqual(lines[0], "(0.000000) vcan0 123#11223344")
        self.assertEqual(lines[1], "(0.000000) vcan0 18FEEE31#AABBCCDD")

    def test_python_can_backend_error_returns_backend_exit_code(self) -> None:
        with patch.dict(os.environ, {"CANARCHY_TRANSPORT_BACKEND": "python-can"}, clear=False):
            with patch.object(
                PythonCanBackend,
                "_open_bus",
                side_effect=TransportError(
                    "TRANSPORT_UNAVAILABLE",
                    "python-can is not installed.",
                    "Install the `python-can` dependency or select the scaffold backend.",
                ),
            ):
                exit_code, stdout, stderr = run_cli("capture", "can0", "--json")

        self.assertEqual(exit_code, EXIT_TRANSPORT_ERROR)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertEqual(payload["errors"][0]["code"], "TRANSPORT_UNAVAILABLE")

    def test_filter_expression_error_returns_backend_exit_code(self) -> None:
        exit_code, stdout, _ = run_cli(
            "filter", str(FIXTURES / "sample.candump"), "unknown", "--json"
        )
        self.assertEqual(exit_code, EXIT_TRANSPORT_ERROR)

        payload = json.loads(stdout)
        self.assertEqual(payload["errors"][0]["code"], "FILTER_EXPRESSION_UNSUPPORTED")

    def test_invalid_candump_file_returns_structured_transport_error(self) -> None:
        exit_code, stdout, stderr = run_cli("stats", str(FIXTURES / "invalid.candump"), "--json")
        self.assertEqual(exit_code, EXIT_TRANSPORT_ERROR)
        self.assertEqual(stderr, "")

        payload = json.loads(stdout)
        self.assertEqual(payload["errors"][0]["code"], "CAPTURE_SOURCE_INVALID")
        self.assertIn("line 1", payload["errors"][0]["message"])


if __name__ == "__main__":
    unittest.main()
