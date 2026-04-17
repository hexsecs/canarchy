from __future__ import annotations

import contextlib
import io
import json
import unittest

from canarchy.cli import EXIT_OK, EXIT_TRANSPORT_ERROR, EXIT_USER_ERROR, main


def run_cli(*argv: str) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = main(argv)
    return exit_code, stdout.getvalue(), stderr.getvalue()


class CliTests(unittest.TestCase):
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
        self.assertEqual(payload["data"]["mode"], "passive")
        self.assertEqual(payload["data"]["status"], "planned")
        self.assertEqual(len(payload["data"]["events"]), 2)
        self.assertEqual(payload["data"]["events"][0]["event_type"], "frame")
        self.assertEqual(payload["data"]["events"][0]["payload"]["frame"]["interface"], "can0")

    def test_send_json_output_marks_active_mode(self) -> None:
        exit_code, stdout, stderr = run_cli("send", "can0", "0x123", "11223344", "--json")
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")

        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["mode"], "active")
        self.assertEqual(payload["data"]["frame"]["arbitration_id"], 0x123)
        self.assertEqual(payload["data"]["events"][0]["event_type"], "alert")
        self.assertEqual(
            payload["warnings"][1],
            "Active transmission is intentionally distinct from passive monitoring workflows.",
        )

    def test_filter_json_output_returns_matching_frames(self) -> None:
        exit_code, stdout, _ = run_cli("filter", "capture.log", "id==0x18FEEE31", "--json")
        self.assertEqual(exit_code, EXIT_OK)

        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["mode"], "passive")
        self.assertEqual(len(payload["data"]["events"]), 1)
        self.assertEqual(
            payload["data"]["events"][0]["payload"]["frame"]["arbitration_id"], 0x18FEEE31
        )

    def test_stats_json_output_returns_summary(self) -> None:
        exit_code, stdout, _ = run_cli("stats", "capture.log", "--json")
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
        exit_code, stdout, _ = run_cli("j1939", "decode", "capture.log", "--json")
        self.assertEqual(exit_code, EXIT_OK)

        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["file"], "capture.log")
        self.assertEqual(payload["data"]["events"][1]["payload"]["pgn"], 61444)

    def test_usage_error_respects_json_output(self) -> None:
        exit_code, stdout, stderr = run_cli("decode", "capture.log", "--json")
        self.assertEqual(exit_code, EXIT_USER_ERROR)
        self.assertEqual(stderr, "")

        payload = json.loads(stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["command"], "cli")
        self.assertEqual(payload["errors"][0]["code"], "INVALID_ARGUMENTS")

    def test_replay_rate_validation_returns_structured_error(self) -> None:
        exit_code, stdout, stderr = run_cli("replay", "capture.log", "--rate", "0", "--json")
        self.assertEqual(exit_code, EXIT_USER_ERROR)
        self.assertEqual(stderr, "")

        payload = json.loads(stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["command"], "replay")
        self.assertEqual(payload["errors"][0]["code"], "INVALID_RATE")
        self.assertEqual(payload["data"]["rate"], 0.0)

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

    def test_filter_expression_error_returns_backend_exit_code(self) -> None:
        exit_code, stdout, _ = run_cli("filter", "capture.log", "unknown", "--json")
        self.assertEqual(exit_code, EXIT_TRANSPORT_ERROR)

        payload = json.loads(stdout)
        self.assertEqual(payload["errors"][0]["code"], "FILTER_EXPRESSION_UNSUPPORTED")


if __name__ == "__main__":
    unittest.main()
