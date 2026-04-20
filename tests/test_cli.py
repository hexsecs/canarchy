from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from canarchy.cli import EXIT_OK, EXIT_TRANSPORT_ERROR, EXIT_USER_ERROR, main
from canarchy.models import CanFrame
from canarchy.transport import PythonCanBackend, TransportError


FIXTURES = Path(__file__).parent / "fixtures"


def run_cli(*argv: str, input: str | None = None) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    stdin_stub = io.StringIO(input) if input is not None else None
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        if stdin_stub is not None:
            # Patch sys.stdin for this call
            import sys
            original_stdin = sys.stdin
            try:
                sys.stdin = stdin_stub
                exit_code = main(argv)
            finally:
                sys.stdin = original_stdin
        else:
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
    def __init__(
        self,
        messages: list[object] | None = None,
        *,
        end_exception: type[BaseException] | None = None,
    ) -> None:
        self.messages = list(messages or [])
        self.end_exception = end_exception
        self.sent_messages: list[object] = []
        self.shutdown_called = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def recv(self, timeout: float | None = None):
        del timeout
        if self.messages:
            return self.messages.pop(0)
        if self.end_exception is not None:
            raise self.end_exception()
        return None

    def send(self, message: object) -> None:
        self.sent_messages.append(message)

    def shutdown(self) -> None:
        self.shutdown_called = True


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

    def fake_message_with_flags(
        self,
        arbitration_id: int,
        data: bytes,
        *,
        is_extended_id: bool = False,
        is_remote_frame: bool = False,
        is_error_frame: bool = False,
        is_fd: bool = False,
        bitrate_switch: bool = False,
        error_state_indicator: bool = False,
    ):
        return type(
            "FakeMessage",
            (),
            {
                "arbitration_id": arbitration_id,
                "data": data,
                "is_extended_id": is_extended_id,
                "is_remote_frame": is_remote_frame,
                "is_error_frame": is_error_frame,
                "is_fd": is_fd,
                "bitrate_switch": bitrate_switch,
                "error_state_indicator": error_state_indicator,
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

    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"})
    def test_capture_json_output_streams_one_event_per_line(self, _mock_cfg) -> None:
        exit_code, stdout, stderr = run_cli("capture", "can0", "--json")
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")

        lines = stdout.strip().splitlines()
        self.assertEqual(len(lines), 2)

        first_event = json.loads(lines[0])
        second_event = json.loads(lines[1])
        self.assertEqual(first_event["event_type"], "frame")
        self.assertEqual(first_event["payload"]["frame"]["interface"], "can0")
        self.assertEqual(second_event["event_type"], "frame")

    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"})
    def test_send_json_output_marks_active_mode(self, _mock_cfg) -> None:
        exit_code, stdout, stderr = run_cli("send", "can0", "0x123", "11223344", "--json")
        self.assertEqual(exit_code, EXIT_OK)
        self.assertIn("warning: `send` will transmit a CAN frame", stderr)

        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["mode"], "active")
        self.assertEqual(payload["data"]["status"], "implemented")
        self.assertEqual(payload["data"]["implementation"], "scaffold transport")
        self.assertEqual(payload["data"]["transport_backend"], "scaffold")
        self.assertEqual(payload["data"]["frame"]["arbitration_id"], 0x123)
        self.assertEqual(payload["data"]["events"][0]["event_type"], "alert")
        self.assertEqual(payload["warnings"], [])

    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"})
    def test_send_preflight_warning_happens_before_transport(self, _mock_cfg) -> None:
        observed_stderr: dict[str, str] = {}

        def fake_send_events(_transport, _interface, _frame):
            import sys

            observed_stderr["value"] = sys.stderr.getvalue()
            return []

        with patch("canarchy.cli.LocalTransport.send_events", new=fake_send_events):
            exit_code, stdout, stderr = run_cli("send", "can0", "0x123", "11223344", "--json")

        self.assertEqual(exit_code, EXIT_OK)
        self.assertIn("warning: `send` will transmit a CAN frame", stderr)
        self.assertIn("warning: `send` will transmit a CAN frame", observed_stderr["value"])
        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["events"], [])

    @patch(
        "canarchy.transport._load_user_config",
        return_value={
            "CANARCHY_TRANSPORT_BACKEND": "scaffold",
            "CANARCHY_REQUIRE_ACTIVE_ACK": "true",
        },
    )
    def test_send_requires_ack_when_configured(self, _mock_cfg) -> None:
        with patch(
            "canarchy.cli.LocalTransport.send_events",
            side_effect=AssertionError("send should not be reached without ack"),
        ):
            exit_code, stdout, stderr = run_cli("send", "can0", "0x123", "11223344", "--json")

        self.assertEqual(exit_code, EXIT_USER_ERROR)
        self.assertIn("warning: `send` will transmit a CAN frame", stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["errors"][0]["code"], "ACTIVE_ACK_REQUIRED")

    @patch(
        "canarchy.transport._load_user_config",
        return_value={
            "CANARCHY_TRANSPORT_BACKEND": "scaffold",
            "CANARCHY_REQUIRE_ACTIVE_ACK": "true",
        },
    )
    def test_send_ack_flag_allows_active_transmission(self, _mock_cfg) -> None:
        exit_code, stdout, stderr = run_cli(
            "send", "can0", "0x123", "11223344", "--ack-active", "--json", input="YES\n"
        )

        self.assertEqual(exit_code, EXIT_OK)
        self.assertIn("warning: `send` will transmit a CAN frame", stderr)
        self.assertIn("confirm: type YES to send on `can0`:", stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["mode"], "active")

    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"})
    def test_send_ack_flag_requires_confirmation_before_transport(self, _mock_cfg) -> None:
        observed_stderr: dict[str, str] = {}

        def fake_send_events(_transport, _interface, _frame):
            import sys

            observed_stderr["value"] = sys.stderr.getvalue()
            return []

        with patch("canarchy.cli.LocalTransport.send_events", new=fake_send_events):
            exit_code, stdout, stderr = run_cli(
                "send", "can0", "0x123", "11223344", "--ack-active", "--json", input="YES\n"
            )

        self.assertEqual(exit_code, EXIT_OK)
        self.assertIn("confirm: type YES to send on `can0`:", stderr)
        self.assertIn("confirm: type YES to send on `can0`:", observed_stderr["value"])
        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["events"], [])

    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"})
    def test_send_ack_flag_decline_blocks_transmission(self, _mock_cfg) -> None:
        with patch(
            "canarchy.cli.LocalTransport.send_events",
            side_effect=AssertionError("send should not be reached without confirmation"),
        ):
            exit_code, stdout, stderr = run_cli(
                "send", "can0", "0x123", "11223344", "--ack-active", "--json", input="no\n"
            )

        self.assertEqual(exit_code, EXIT_USER_ERROR)
        self.assertIn("confirm: type YES to send on `can0`:", stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["errors"][0]["code"], "ACTIVE_CONFIRMATION_DECLINED")

    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"})
    def test_capture_candump_streams_fixture_frames_on_scaffold(self, _mock_cfg) -> None:
        exit_code, stdout, stderr = run_cli("capture", "can0", "--candump")
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")

        lines = stdout.strip().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith("("))
        self.assertIn(" can0 ", lines[0])
        self.assertIn("#", lines[0])

    def test_capture_json_uses_live_backend_when_requested(self) -> None:
        fake_bus = FakeBus(
            [
                self.fake_message(0x123, bytes.fromhex("11223344")),
                self.fake_message(0x18FEEE31, bytes.fromhex("AABBCCDD"), is_extended_id=True),
            ],
            end_exception=KeyboardInterrupt,
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
                exit_code, stdout, stderr = run_cli("capture", "vcan0", "--json")

        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")
        lines = stdout.strip().splitlines()
        self.assertEqual(len(lines), 2)
        first_event = json.loads(lines[0])
        second_event = json.loads(lines[1])
        self.assertEqual(first_event["payload"]["frame"]["arbitration_id"], 0x123)
        self.assertFalse(first_event["payload"]["frame"]["is_extended_id"])
        self.assertEqual(second_event["payload"]["frame"]["arbitration_id"], 0x18FEEE31)
        self.assertTrue(second_event["payload"]["frame"]["is_extended_id"])

    def test_gateway_json_output_contains_forwarded_frame_event(self) -> None:
        src_bus = FakeBus([self.fake_message(0x123, bytes.fromhex("11223344"))])
        dst_bus = FakeBus()
        open_bus_calls: list[tuple[str, str]] = []

        def fake_open_bus(backend: PythonCanBackend, interface: str):
            open_bus_calls.append((backend.bus_interface, interface))
            return {"src0": src_bus, "dst0": dst_bus}[interface]

        with patch.dict(os.environ, {"CANARCHY_TRANSPORT_BACKEND": "python-can"}, clear=False):
            with patch.object(PythonCanBackend, "_open_bus", new=fake_open_bus):
                with patch.object(PythonCanBackend, "_encode_message", return_value=object()):
                    exit_code, stdout, stderr = run_cli(
                        "gateway",
                        "src0",
                        "dst0",
                        "--src-backend",
                        "virtual",
                        "--dst-backend",
                        "udp_multicast",
                        "--count",
                        "1",
                        "--json",
                    )

        self.assertEqual(exit_code, EXIT_OK)
        self.assertIn("warning: `gateway` will forward traffic", stderr)
        payload = json.loads(stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["command"], "gateway")
        self.assertEqual(payload["data"]["status"], "implemented")
        self.assertEqual(payload["data"]["implementation"], "live transport gateway")
        self.assertEqual(payload["data"]["forwarded_frames"], 1)
        self.assertEqual(payload["data"]["events"][0]["source"], "gateway.src->dst")
        self.assertEqual(payload["data"]["events"][0]["payload"]["frame"]["interface"], "src0")
        self.assertEqual(open_bus_calls, [("virtual", "src0"), ("udp_multicast", "dst0")])
        self.assertEqual(len(dst_bus.sent_messages), 1)

    def test_gateway_bidirectional_json_labels_both_directions(self) -> None:
        src_bus = FakeBus([self.fake_message(0x123, bytes.fromhex("1122"))])
        dst_bus = FakeBus([self.fake_message(0x456, bytes.fromhex("3344"))])

        def fake_open_bus(backend: PythonCanBackend, interface: str):
            return {"src0": src_bus, "dst0": dst_bus}[interface]

        with patch.dict(
            os.environ,
            {
                "CANARCHY_TRANSPORT_BACKEND": "python-can",
                "CANARCHY_CAPTURE_TIMEOUT": "0.01",
            },
            clear=False,
        ):
            with patch.object(PythonCanBackend, "_open_bus", new=fake_open_bus):
                with patch.object(PythonCanBackend, "_encode_message", return_value=object()):
                    exit_code, stdout, stderr = run_cli(
                        "gateway",
                        "src0",
                        "dst0",
                        "--bidirectional",
                        "--count",
                        "2",
                        "--json",
                    )

        self.assertEqual(exit_code, EXIT_OK)
        self.assertIn("warning: `gateway` will forward traffic", stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["forwarded_frames"], 2)
        self.assertEqual(
            {event["source"] for event in payload["data"]["events"]},
            {"gateway.src->dst", "gateway.dst->src"},
        )

    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"})
    def test_gateway_requires_live_backend(self, _mock_cfg) -> None:
        with patch.dict(os.environ, {}, clear=True):
            exit_code, stdout, stderr = run_cli("gateway", "src0", "dst0", "--count", "1", "--json")

        self.assertEqual(exit_code, EXIT_TRANSPORT_ERROR)
        self.assertIn("warning: `gateway` will forward traffic", stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["errors"][0]["code"], "GATEWAY_LIVE_BACKEND_REQUIRED")

    def test_gateway_invalid_count_returns_user_error(self) -> None:
        exit_code, stdout, stderr = run_cli("gateway", "src0", "dst0", "--count", "0", "--json")

        self.assertEqual(exit_code, EXIT_USER_ERROR)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertEqual(payload["errors"][0]["code"], "INVALID_COUNT")

    def test_gateway_channel_error_returns_transport_error(self) -> None:
        def fake_open_bus(backend: PythonCanBackend, interface: str):
            raise TransportError(
                "TRANSPORT_UNAVAILABLE",
                f"Interface '{interface}' is not available.",
                "Check that the python-can interface and channel are configured correctly.",
            )

        with patch.dict(os.environ, {"CANARCHY_TRANSPORT_BACKEND": "python-can"}, clear=False):
            with patch.object(PythonCanBackend, "_open_bus", new=fake_open_bus):
                exit_code, stdout, stderr = run_cli(
                    "gateway", "missing0", "dst0", "--count", "1", "--json"
                )

        self.assertEqual(exit_code, EXIT_TRANSPORT_ERROR)
        self.assertIn("warning: `gateway` will forward traffic", stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["errors"][0]["code"], "TRANSPORT_UNAVAILABLE")

    def test_gateway_table_output_prints_header_and_direction(self) -> None:
        src_bus = FakeBus([self.fake_message(0x18FEEE31, bytes.fromhex("11223344"), is_extended_id=True)])
        dst_bus = FakeBus()

        def fake_open_bus(backend: PythonCanBackend, interface: str):
            return {"src0": src_bus, "dst0": dst_bus}[interface]

        with patch.dict(os.environ, {"CANARCHY_TRANSPORT_BACKEND": "python-can"}, clear=False):
            with patch.object(PythonCanBackend, "_open_bus", new=fake_open_bus):
                with patch.object(PythonCanBackend, "_encode_message", return_value=object()):
                    exit_code, stdout, stderr = run_cli(
                        "gateway", "src0", "dst0", "--count", "1", "--table"
                    )

        self.assertEqual(exit_code, EXIT_OK)
        self.assertIn("warning: `gateway` will forward traffic", stderr)
        self.assertIn("gateway: src=src0 dst=dst0", stdout)
        self.assertIn("src0 18FEEE31#11223344  [src->dst]", stdout)

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
        self.assertEqual(payload["data"]["implementation"], "file-backed analysis")
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
        self.assertEqual(payload["data"]["implementation"], "sample/reference provider")

    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"})
    def test_j1939_monitor_with_interface_uses_transport_path(self, _mock_cfg) -> None:
        exit_code, stdout, _ = run_cli("j1939", "monitor", "can0", "--json")
        self.assertEqual(exit_code, EXIT_OK)

        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["interface"], "can0")
        self.assertEqual(payload["data"]["implementation"], "transport-backed")
        self.assertEqual(len(payload["data"]["events"]), 2)

    def test_j1939_monitor_pgn_filter_is_applied(self) -> None:
        exit_code, stdout, _ = run_cli("j1939", "monitor", "--pgn", "65262", "--json")
        self.assertEqual(exit_code, EXIT_OK)

        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["pgn_filter"], 65262)
        self.assertEqual(len(payload["data"]["events"]), 1)
        self.assertEqual(payload["data"]["events"][0]["payload"]["pgn"], 65262)

    def test_j1939_summary_returns_capture_reconnaissance_fields(self) -> None:
        exit_code, stdout, stderr = run_cli(
            "j1939",
            "summary",
            str(FIXTURES / "j1939_heavy_vehicle.candump"),
            "--json",
        )
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")

        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["total_frames"], 8)
        self.assertEqual(payload["data"]["interfaces"], ["can0"])
        self.assertEqual(payload["data"]["unique_arbitration_ids"], 4)
        self.assertEqual(payload["data"]["first_timestamp"], 0.0)
        self.assertEqual(payload["data"]["last_timestamp"], 0.55)
        self.assertEqual(payload["data"]["top_pgns"][0], {"pgn": 65262, "frame_count": 3})
        self.assertEqual(payload["data"]["top_source_addresses"][0], {"source_address": 0x31, "frame_count": 8})
        self.assertTrue(payload["data"]["dm1"]["present"])
        self.assertEqual(payload["data"]["dm1"]["message_count"], 1)
        self.assertEqual(payload["data"]["dm1"]["active_dtc_count"], 2)
        self.assertEqual(payload["data"]["tp"]["session_count"], 1)
        self.assertEqual(payload["data"]["tp"]["complete_session_count"], 1)

    def test_j1939_summary_surfaces_printable_tp_identifiers(self) -> None:
        exit_code, stdout, stderr = run_cli(
            "j1939",
            "summary",
            str(FIXTURES / "j1939_tp_printable_id.candump"),
            "--json",
        )
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")

        payload = json.loads(stdout)
        self.assertEqual(
            payload["data"]["tp"]["printable_identifiers"],
            [
                {
                    "text": "VIN1234",
                    "transfer_pgn": 65259,
                    "source_address": 0x31,
                    "destination_address": 255,
                    "session_type": "bam",
                    "payload_label": "component_identification",
                    "heuristic": True,
                }
            ],
        )

    def test_j1939_summary_table_output_is_pretty_printed(self) -> None:
        exit_code, stdout, stderr = run_cli(
            "j1939",
            "summary",
            str(FIXTURES / "j1939_tp_printable_id.candump"),
            "--table",
        )
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")
        self.assertIn("command: j1939 summary", stdout)
        self.assertIn("top_pgns:", stdout)
        self.assertIn("printable_identifiers:", stdout)
        self.assertIn("text=VIN1234", stdout)

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

    def test_j1939_decode_with_dbc_adds_provenance_and_dbc_events(self) -> None:
        exit_code, stdout, stderr = run_cli(
            "j1939",
            "decode",
            str(FIXTURES / "sample.candump"),
            "--dbc",
            str(FIXTURES / "j1939_sample.dbc"),
            "--json",
        )
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")

        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["dbc"], str(FIXTURES / "j1939_sample.dbc"))
        self.assertEqual(payload["data"]["dbc_source"]["provider"], "local")
        self.assertEqual(payload["data"]["dbc_matched_messages"], 2)
        decoded_events = [
            event for event in payload["data"]["dbc_events"] if event["event_type"] == "decoded_message"
        ]
        self.assertEqual(len(decoded_events), 2)
        self.assertEqual(decoded_events[0]["payload"]["message_name"], "EngineTemperature1")

    def test_j1939_spn_requires_capture_file(self) -> None:
        exit_code, stdout, stderr = run_cli("j1939", "spn", "110", "--json")
        self.assertEqual(exit_code, EXIT_USER_ERROR)
        self.assertEqual(stderr, "")

        payload = json.loads(stdout)
        self.assertEqual(payload["errors"][0]["code"], "CAPTURE_FILE_REQUIRED")

    def test_j1939_spn_returns_structured_observations(self) -> None:
        exit_code, stdout, stderr = run_cli(
            "j1939",
            "spn",
            "110",
            "--file",
            str(FIXTURES / "sample.candump"),
            "--json",
        )
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")

        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["decoder"], "curated_spn_map")
        self.assertEqual(payload["data"]["observation_count"], 1)
        observation = payload["data"]["observations"][0]
        self.assertEqual(observation["spn"], 110)
        self.assertEqual(observation["pgn"], 65262)
        self.assertEqual(observation["source_address"], 0x31)
        self.assertEqual(observation["value"], -23.0)
        self.assertEqual(observation["units"], "degC")

    def test_j1939_spn_uses_configured_default_dbc_when_flag_absent(self) -> None:
        with patch(
            "canarchy.transport._load_user_config",
            return_value={"CANARCHY_J1939_DBC": str(FIXTURES / "j1939_sample.dbc")},
        ):
            exit_code, stdout, stderr = run_cli(
                "j1939",
                "spn",
                "110",
                "--file",
                str(FIXTURES / "sample.candump"),
                "--json",
            )

        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["dbc_source"]["provider"], "local")
        self.assertEqual(payload["data"]["dbc_matched_messages"], 1)
        signal_events = [event for event in payload["data"]["dbc_events"] if event["event_type"] == "signal"]
        self.assertTrue(any(event["payload"]["signal_name"] == "EngineCoolantTemp" for event in signal_events))

    def test_j1939_spn_supports_non_curated_spn_via_dbc_flag(self) -> None:
        exit_code, stdout, stderr = run_cli(
            "j1939",
            "spn",
            "175",
            "--file",
            str(FIXTURES / "sample.candump"),
            "--dbc",
            str(FIXTURES / "j1939_sample.dbc"),
            "--json",
        )

        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["decoder"], "dbc_spn_map")
        self.assertEqual(payload["data"]["observation_count"], 1)
        observation = payload["data"]["observations"][0]
        self.assertEqual(observation["spn"], 175)
        self.assertEqual(observation["name"], "EngineOilTemp")
        self.assertEqual(observation["value"], -6)
        self.assertEqual(observation["raw"], "22")

    def test_j1939_spn_supports_non_curated_spn_via_default_dbc(self) -> None:
        with patch(
            "canarchy.transport._load_user_config",
            return_value={"CANARCHY_J1939_DBC": str(FIXTURES / "j1939_sample.dbc")},
        ):
            exit_code, stdout, stderr = run_cli(
                "j1939",
                "spn",
                "175",
                "--file",
                str(FIXTURES / "sample.candump"),
                "--json",
            )

        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["decoder"], "dbc_spn_map")
        self.assertEqual(payload["data"]["observations"][0]["name"], "EngineOilTemp")

    def test_j1939_spn_extracts_raw_for_non_byte_aligned_dbc_signal(self) -> None:
        exit_code, stdout, stderr = run_cli(
            "j1939",
            "spn",
            "1234",
            "--file",
            str(FIXTURES / "j1939_nonbyte.candump"),
            "--dbc",
            str(FIXTURES / "j1939_sample.dbc"),
            "--json",
        )

        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        observation = payload["data"]["observations"][0]
        self.assertEqual(payload["data"]["decoder"], "dbc_spn_map")
        self.assertEqual(observation["name"], "NibbleSignal")
        self.assertEqual(observation["value"], 291)
        self.assertEqual(observation["raw"], "123")

    def test_j1939_pgn_with_dbc_adds_dbc_events(self) -> None:
        exit_code, stdout, stderr = run_cli(
            "j1939",
            "pgn",
            "65262",
            "--file",
            str(FIXTURES / "sample.candump"),
            "--dbc",
            str(FIXTURES / "j1939_sample.dbc"),
            "--json",
        )
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["dbc_matched_messages"], 1)
        self.assertEqual(payload["data"]["dbc_events"][0]["payload"]["message_name"], "EngineTemperature1")

    def test_j1939_pgn_with_dbc_signal_events_include_non_byte_aligned_raw(self) -> None:
        exit_code, stdout, stderr = run_cli(
            "j1939",
            "pgn",
            "61444",
            "--file",
            str(FIXTURES / "j1939_nonbyte.candump"),
            "--dbc",
            str(FIXTURES / "j1939_sample.dbc"),
            "--json",
        )
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")

        payload = json.loads(stdout)
        signal_events = [event for event in payload["data"]["dbc_events"] if event["event_type"] == "signal"]
        nibble = next(event for event in signal_events if event["payload"]["signal_name"] == "NibbleSignal")
        self.assertEqual(nibble["payload"]["raw"], "123")
        self.assertEqual(nibble["payload"]["value"], 291)

    def test_j1939_tp_returns_bam_session_summary(self) -> None:
        exit_code, stdout, stderr = run_cli(
            "j1939",
            "tp",
            str(FIXTURES / "j1939_dm1_tp.candump"),
            "--json",
        )
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")

        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["session_count"], 1)
        session = payload["data"]["sessions"][0]
        self.assertEqual(session["session_type"], "bam")
        self.assertEqual(session["transfer_pgn"], 65226)
        self.assertEqual(session["source_address"], 0x31)
        self.assertTrue(session["complete"])
        self.assertEqual(session["packet_count"], 2)
        self.assertEqual(session["reassembled_data"], "000000006e000501be000702")
        self.assertIsNone(session["decoded_text"])
        self.assertFalse(session["decoded_text_heuristic"])
        self.assertIsNone(session["payload_label"])

    def test_j1939_tp_returns_rts_cts_session_summary(self) -> None:
        exit_code, stdout, stderr = run_cli(
            "j1939",
            "tp",
            str(FIXTURES / "j1939_dm1_rts_cts.candump"),
            "--json",
        )
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")

        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["session_count"], 1)
        session = payload["data"]["sessions"][0]
        self.assertEqual(session["session_type"], "rts_cts")
        self.assertEqual(session["transfer_pgn"], 65226)
        self.assertEqual(session["source_address"], 0x31)
        self.assertEqual(session["destination_address"], 0x22)
        self.assertTrue(session["complete"])
        self.assertTrue(session["acknowledged"])
        self.assertEqual(session["cts_count"], 1)
        self.assertEqual(session["packet_count"], 2)
        self.assertEqual(session["reassembled_data"], "00000000af000501")
        self.assertIsNone(session["decoded_text"])

    def test_j1939_tp_surfaces_printable_identification_text(self) -> None:
        exit_code, stdout, stderr = run_cli(
            "j1939",
            "tp",
            str(FIXTURES / "j1939_tp_printable_id.candump"),
            "--json",
        )
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")

        payload = json.loads(stdout)
        session = payload["data"]["sessions"][0]
        self.assertEqual(session["transfer_pgn"], 65259)
        self.assertEqual(session["payload_label"], "component_identification")
        self.assertEqual(session["payload_label_source"], "known_transfer_pgn")
        self.assertEqual(session["decoded_text"], "VIN1234")
        self.assertEqual(session["decoded_text_encoding"], "ascii")
        self.assertTrue(session["decoded_text_heuristic"])

    def test_j1939_tp_table_output_shows_printable_text_when_present(self) -> None:
        exit_code, stdout, stderr = run_cli(
            "j1939",
            "tp",
            str(FIXTURES / "j1939_tp_printable_id.candump"),
            "--table",
        )
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")
        self.assertIn("label=component_identification", stdout)
        self.assertIn("text=VIN1234", stdout)

    def test_j1939_dm1_returns_direct_and_transport_messages(self) -> None:
        exit_code, stdout, stderr = run_cli(
            "j1939",
            "dm1",
            str(FIXTURES / "j1939_dm1_tp.candump"),
            "--json",
        )
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")

        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["message_count"], 2)
        self.assertEqual(payload["data"]["source_count"], 2)
        direct_message = payload["data"]["messages"][1]
        tp_message = payload["data"]["messages"][0]
        self.assertEqual(tp_message["transport"], "tp")
        self.assertEqual(tp_message["active_dtc_count"], 2)
        self.assertEqual(tp_message["dtcs"][0]["spn"], 110)
        self.assertEqual(tp_message["dtcs"][1]["spn"], 190)
        self.assertEqual(direct_message["transport"], "direct")
        self.assertEqual(direct_message["source_address"], 0x22)
        self.assertEqual(direct_message["dtcs"][0]["fmi"], 3)

    def test_j1939_dm1_returns_rts_cts_transport_message(self) -> None:
        exit_code, stdout, stderr = run_cli(
            "j1939",
            "dm1",
            str(FIXTURES / "j1939_dm1_rts_cts.candump"),
            "--json",
        )
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")

        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["message_count"], 1)
        message = payload["data"]["messages"][0]
        self.assertEqual(message["transport"], "tp")
        self.assertEqual(message["source_address"], 0x31)
        self.assertEqual(message["destination_address"], 0x22)
        self.assertEqual(message["active_dtc_count"], 1)
        self.assertEqual(message["dtcs"][0]["spn"], 175)
        self.assertEqual(message["dtcs"][0]["fmi"], 5)

    def test_j1939_dm1_with_dbc_enriches_non_curated_dtc_names(self) -> None:
        exit_code, stdout, stderr = run_cli(
            "j1939",
            "dm1",
            str(FIXTURES / "j1939_dm1_spn175.candump"),
            "--dbc",
            str(FIXTURES / "j1939_sample.dbc"),
            "--json",
        )
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")

        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["dbc_source"]["provider"], "local")
        self.assertEqual(payload["data"]["dbc_spn_matches"], 1)
        dtc = payload["data"]["messages"][0]["dtcs"][0]
        self.assertEqual(dtc["spn"], 175)
        self.assertEqual(dtc["name"], "EngineOilTemp")
        self.assertEqual(dtc["dbc_signal_name"], "EngineOilTemp")
        self.assertEqual(dtc["dbc_message_name"], "EngineTemperature1")
        self.assertEqual(dtc["units"], "degC")

    def test_j1939_dm1_uses_configured_default_dbc(self) -> None:
        with patch(
            "canarchy.transport._load_user_config",
            return_value={"CANARCHY_J1939_DBC": str(FIXTURES / "j1939_sample.dbc")},
        ):
            exit_code, stdout, stderr = run_cli(
                "j1939",
                "dm1",
                str(FIXTURES / "j1939_dm1_spn175.candump"),
                "--json",
            )

        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        dtc = payload["data"]["messages"][0]["dtcs"][0]
        self.assertEqual(payload["data"]["dbc_spn_matches"], 1)
        self.assertEqual(dtc["name"], "EngineOilTemp")

    def test_j1939_dm1_table_output_is_pretty_printed(self) -> None:
        exit_code, stdout, stderr = run_cli(
            "j1939",
            "dm1",
            str(FIXTURES / "j1939_dm1_tp.candump"),
            "--table",
        )
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")
        self.assertIn("command: j1939 dm1", stdout)
        self.assertIn("messages:", stdout)
        self.assertIn("transport=tp", stdout)
        self.assertIn("spn=110/fmi=5", stdout)

    def test_j1939_decode_max_frames_limits_analysis(self) -> None:
        exit_code, stdout, stderr = run_cli(
            "j1939",
            "decode",
            str(FIXTURES / "j1939_heavy_vehicle.candump"),
            "--max-frames",
            "3",
            "--json",
        )
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")

        payload = json.loads(stdout)
        self.assertEqual(len(payload["data"]["events"]), 3)

    def test_j1939_tp_seconds_limits_analysis_window(self) -> None:
        exit_code, stdout, stderr = run_cli(
            "j1939",
            "tp",
            str(FIXTURES / "j1939_dm1_tp.candump"),
            "--seconds",
            "0.08",
            "--json",
        )
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")

        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["session_count"], 1)
        self.assertFalse(payload["data"]["sessions"][0]["complete"])
        self.assertEqual(payload["data"]["sessions"][0]["packet_count"], 1)

    def test_j1939_decode_rejects_window_flags_with_stdin(self) -> None:
        event = {
            "event_type": "frame",
            "payload": {
                "frame": CanFrame(
                    arbitration_id=0x18FEEE31,
                    data=bytes.fromhex("7DFFFFFF"),
                    timestamp=0.0,
                    is_extended_id=True,
                ).to_payload()
            },
            "source": "test.stdin",
            "timestamp": 0.0,
        }
        exit_code, stdout, stderr = run_cli(
            "j1939",
            "decode",
            "--stdin",
            "--seconds",
            "1.0",
            "--json",
            input=json.dumps(event) + "\n",
        )
        self.assertEqual(exit_code, EXIT_USER_ERROR)
        self.assertEqual(stderr, "")

        payload = json.loads(stdout)
        self.assertEqual(payload["errors"][0]["code"], "ANALYSIS_WINDOW_REQUIRES_FILE")

    def test_j1939_dm1_rejects_invalid_max_frames(self) -> None:
        exit_code, stdout, stderr = run_cli(
            "j1939",
            "dm1",
            str(FIXTURES / "j1939_dm1_tp.candump"),
            "--max-frames",
            "0",
            "--json",
        )
        self.assertEqual(exit_code, EXIT_USER_ERROR)
        self.assertEqual(stderr, "")

        payload = json.loads(stdout)
        self.assertEqual(payload["errors"][0]["code"], "INVALID_MAX_FRAMES")

    def test_j1939_tp_rejects_invalid_seconds(self) -> None:
        exit_code, stdout, stderr = run_cli(
            "j1939",
            "tp",
            str(FIXTURES / "j1939_dm1_tp.candump"),
            "--seconds",
            "-1",
            "--json",
        )
        self.assertEqual(exit_code, EXIT_USER_ERROR)
        self.assertEqual(stderr, "")

        payload = json.loads(stdout)
        self.assertEqual(payload["errors"][0]["code"], "INVALID_ANALYSIS_SECONDS")

    def test_j1939_dm1_json_keeps_deprecated_conversion_warning_structured(self) -> None:
        exit_code, stdout, stderr = run_cli(
            "j1939",
            "dm1",
            str(FIXTURES / "j1939_dm1_deprecated_conversion.candump"),
            "--json",
        )
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")

        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["message_count"], 2)
        self.assertEqual(
            payload["warnings"],
            [
                "One or more DM1 DTCs use deprecated SPN conversion modes; conversion details are reported in structured output."
            ],
        )
        self.assertEqual(payload["data"]["messages"][0]["dtcs"][0]["conversion_method"], 1)

    def test_j1939_dm1_jsonl_emits_json_records_when_warning_present(self) -> None:
        exit_code, stdout, stderr = run_cli(
            "j1939",
            "dm1",
            str(FIXTURES / "j1939_dm1_deprecated_conversion.candump"),
            "--jsonl",
        )
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")

        records = [json.loads(line) for line in stdout.splitlines()]
        self.assertEqual(len(records), 3)
        self.assertEqual(records[0]["transport"], "direct")
        self.assertEqual(records[1]["transport"], "direct")
        self.assertEqual(records[2]["event_type"], "alert")
        self.assertEqual(records[2]["payload"]["level"], "warning")

    def test_uds_scan_returns_transaction_events(self) -> None:
        with patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"}):
            exit_code, stdout, stderr = run_cli("uds", "scan", "can0", "--json")
        self.assertEqual(exit_code, EXIT_OK)
        self.assertIn("warning: `uds scan` will transmit diagnostic requests", stderr)

        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["mode"], "active")
        self.assertEqual(payload["data"]["implementation"], "sample/reference provider")
        self.assertEqual(payload["data"]["responder_count"], 2)
        self.assertEqual(payload["data"]["events"][0]["event_type"], "uds_transaction")
        self.assertEqual(
            payload["data"]["events"][0]["payload"]["service_name"], "DiagnosticSessionControl"
        )
        self.assertEqual(payload["warnings"], [])

    def test_uds_trace_returns_transaction_events(self) -> None:
        with patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"}):
            exit_code, stdout, stderr = run_cli("uds", "trace", "can0", "--json")
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")

        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["mode"], "passive")
        self.assertEqual(payload["data"]["implementation"], "sample/reference provider")
        self.assertEqual(payload["data"]["transaction_count"], 2)
        self.assertEqual(payload["data"]["events"][1]["payload"]["service"], 0x27)
        self.assertEqual(payload["data"]["events"][1]["payload"]["service_name"], "SecurityAccess")

    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "python-can", "CANARCHY_PYTHON_CAN_INTERFACE": "virtual"})
    @patch("canarchy.transport.LocalTransport.capture")
    def test_uds_trace_with_python_can_backend_reports_transport_backed(self, capture_mock, _mock_cfg) -> None:
        capture_mock.return_value = [
            CanFrame(
                arbitration_id=0x7E0,
                data=bytes.fromhex("0210030000000000"),
                interface="can0",
                timestamp=0.0,
            ),
            CanFrame(
                arbitration_id=0x7E8,
                data=bytes.fromhex("0450030032000000"),
                interface="can0",
                timestamp=0.1,
            ),
        ]

        exit_code, stdout, stderr = run_cli("uds", "trace", "can0", "--json")
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")

        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["implementation"], "transport-backed")
        self.assertEqual(payload["data"]["transport_backend"], "python-can")
        self.assertEqual(payload["data"]["events"][0]["payload"]["service"], 0x10)

    def test_uds_scan_table_output_is_pretty_printed(self) -> None:
        with patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"}):
            exit_code, stdout, stderr = run_cli("uds", "scan", "can0", "--table")
        self.assertEqual(exit_code, EXIT_OK)
        self.assertIn("warning: `uds scan` will transmit diagnostic requests", stderr)
        self.assertIn("command: uds scan", stdout)
        self.assertIn("interface: can0", stdout)
        self.assertIn("responders:", stdout)
        self.assertIn("transactions:", stdout)
        self.assertIn("service=0x10", stdout)
        self.assertIn("name=DiagnosticSessionControl", stdout)
        self.assertIn("req_id=0x7DF", stdout)
        self.assertIn("resp_id=0x7E8", stdout)

    def test_uds_trace_table_output_is_pretty_printed(self) -> None:
        with patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"}):
            exit_code, stdout, stderr = run_cli("uds", "trace", "can0", "--table")
        self.assertEqual(exit_code, EXIT_OK)
        self.assertIn("command: uds trace", stdout)
        self.assertIn("interface: can0", stdout)
        self.assertIn("transactions:", stdout)
        self.assertIn("service=0x27", stdout)
        self.assertIn("name=SecurityAccess", stdout)

    def test_uds_services_returns_catalog(self) -> None:
        exit_code, stdout, stderr = run_cli("uds", "services", "--json")
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")

        payload = json.loads(stdout)
        self.assertEqual(payload["command"], "uds services")
        self.assertEqual(payload["data"]["mode"], "reference")
        self.assertGreater(payload["data"]["service_count"], 5)
        services = payload["data"]["services"]
        self.assertEqual(services[0]["service"], 0x10)
        self.assertEqual(services[0]["name"], "DiagnosticSessionControl")
        self.assertEqual(services[0]["positive_response_service"], 0x50)
        self.assertTrue(services[0]["requires_subfunction"])
        self.assertEqual(services[6]["name"], "SecurityAccess")

    def test_uds_services_table_output_is_pretty_printed(self) -> None:
        exit_code, stdout, stderr = run_cli("uds", "services", "--table")
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")
        self.assertIn("command: uds services", stdout)
        self.assertIn("catalog:", stdout)
        self.assertIn("sid=0x10 name=DiagnosticSessionControl positive=0x50", stdout)
        self.assertIn("sid=0x27 name=SecurityAccess positive=0x67", stdout)

    def test_uds_services_raw_output_is_command_name(self) -> None:
        exit_code, stdout, stderr = run_cli("uds", "services", "--raw")
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")
        self.assertEqual(stdout.strip(), "uds services")

    def test_uds_transport_error_returns_backend_exit_code(self) -> None:
        with patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"}):
            exit_code, stdout, stderr = run_cli("uds", "scan", "offline0", "--json")
        self.assertEqual(exit_code, EXIT_TRANSPORT_ERROR)
        self.assertIn("warning: `uds scan` will transmit diagnostic requests", stderr)

        payload = json.loads(stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["errors"][0]["code"], "TRANSPORT_UNAVAILABLE")

    def test_re_counters_returns_ranked_candidates(self) -> None:
        exit_code, stdout, stderr = run_cli(
            "re",
            "counters",
            str(FIXTURES / "re_counter_nibble.candump"),
            "--json",
        )
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")

        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["mode"], "passive")
        self.assertEqual(payload["data"]["analysis"], "counter_detection")
        self.assertGreater(payload["data"]["candidate_count"], 0)
        best = payload["data"]["candidates"][0]
        self.assertEqual(best["arbitration_id"], 0x123)
        self.assertEqual(best["start_bit"], 0)
        self.assertEqual(best["bit_length"], 4)
        self.assertIn("adjacent samples increment", best["rationale"])

    def test_re_counters_detects_rollover(self) -> None:
        exit_code, stdout, stderr = run_cli(
            "re",
            "counters",
            str(FIXTURES / "re_counter_rollover.candump"),
            "--json",
        )
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")

        payload = json.loads(stdout)
        rollover_candidate = next(
            candidate
            for candidate in payload["data"]["candidates"]
            if candidate["arbitration_id"] == 0x200
            and candidate["start_bit"] == 8
            and candidate["bit_length"] == 8
        )
        self.assertTrue(rollover_candidate["rollover_detected"])

    def test_re_counters_non_counter_returns_empty_candidates(self) -> None:
        exit_code, stdout, stderr = run_cli(
            "re",
            "counters",
            str(FIXTURES / "re_non_counter.candump"),
            "--json",
        )
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")

        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["candidate_count"], 0)
        self.assertEqual(payload["data"]["candidates"], [])
        self.assertEqual(payload["warnings"][0], "No likely counters met the current heuristic threshold.")

    def test_re_counters_low_sample_returns_empty_candidates(self) -> None:
        exit_code, stdout, stderr = run_cli(
            "re",
            "counters",
            str(FIXTURES / "re_low_sample.candump"),
            "--json",
        )
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")

        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["candidate_count"], 0)
        self.assertEqual(payload["data"]["candidates"], [])

    def test_re_counters_table_output_is_ranked(self) -> None:
        exit_code, stdout, stderr = run_cli(
            "re",
            "counters",
            str(FIXTURES / "re_counter_nibble.candump"),
            "--table",
        )
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")
        self.assertIn("command: re counters", stdout)
        self.assertIn("analysis: counter_detection", stdout)
        self.assertIn("candidate_count:", stdout)
        self.assertIn("id=0x123", stdout)
        self.assertIn("start=0", stdout)
        self.assertIn("len=4", stdout)

    def test_re_counters_missing_capture_returns_transport_error(self) -> None:
        exit_code, stdout, stderr = run_cli(
            "re",
            "counters",
            str(FIXTURES / "missing-re-file.candump"),
            "--json",
        )
        self.assertEqual(exit_code, EXIT_TRANSPORT_ERROR)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertEqual(payload["errors"][0]["code"], "CAPTURE_SOURCE_UNAVAILABLE")

    def test_re_entropy_returns_ranked_id_summaries(self) -> None:
        exit_code, stdout, stderr = run_cli(
            "re",
            "entropy",
            str(FIXTURES / "re_entropy_mixed.candump"),
            "--json",
        )
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")

        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["mode"], "passive")
        self.assertEqual(payload["data"]["analysis"], "entropy_ranking")
        self.assertEqual(payload["data"]["candidate_count"], 4)
        self.assertEqual(payload["data"]["candidates"][0]["arbitration_id"], 0x102)

    def test_re_entropy_marks_low_sample_candidates(self) -> None:
        exit_code, stdout, stderr = run_cli(
            "re",
            "entropy",
            str(FIXTURES / "re_entropy_mixed.candump"),
            "--json",
        )
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")

        payload = json.loads(stdout)
        low_sample = next(
            candidate for candidate in payload["data"]["candidates"] if candidate["arbitration_id"] == 0x103
        )
        self.assertTrue(low_sample["low_sample"])
        self.assertEqual(low_sample["frame_count"], 5)

    def test_re_entropy_table_output_is_ranked(self) -> None:
        exit_code, stdout, stderr = run_cli(
            "re",
            "entropy",
            str(FIXTURES / "re_entropy_mixed.candump"),
            "--table",
        )
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")
        self.assertIn("command: re entropy", stdout)
        self.assertIn("analysis: entropy_ranking", stdout)
        self.assertIn("id=0x102", stdout)
        self.assertIn("mean=3.322", stdout)
        self.assertIn("byte=0 entropy=3.322 unique=10", stdout)

    def test_re_entropy_missing_capture_returns_transport_error(self) -> None:
        exit_code, stdout, stderr = run_cli(
            "re",
            "entropy",
            str(FIXTURES / "missing-entropy-file.candump"),
            "--json",
        )
        self.assertEqual(exit_code, EXIT_TRANSPORT_ERROR)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertEqual(payload["errors"][0]["code"], "CAPTURE_SOURCE_UNAVAILABLE")

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
                    str(FIXTURES / "sample.candump"),
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
                self.assertEqual(
                    payload["data"]["session"]["context"]["capture"],
                    str(FIXTURES / "sample.candump"),
                )

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

    def test_export_capture_file_to_json_writes_structured_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "capture-export.json"
            exit_code, stdout, stderr = run_cli(
                "export",
                str(FIXTURES / "sample.candump"),
                str(destination),
                "--json",
            )

            self.assertEqual(exit_code, EXIT_OK)
            self.assertEqual(stderr, "")
            payload = json.loads(stdout)
            self.assertEqual(payload["data"]["artifact_type"], "event_stream")
            self.assertEqual(payload["data"]["export_format"], "json")
            self.assertEqual(payload["data"]["exported_events"], 3)

            artifact = json.loads(destination.read_text())
            self.assertTrue(artifact["ok"])
            self.assertEqual(artifact["command"], "export")
            self.assertEqual(artifact["data"]["artifact_type"], "event_stream")
            self.assertEqual(artifact["data"]["source"]["kind"], "capture_file")
            self.assertEqual(len(artifact["data"]["events"]), 3)
            self.assertEqual(artifact["data"]["events"][0]["event_type"], "frame")

    def test_export_capture_file_to_jsonl_writes_one_event_per_line(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "capture-export.jsonl"
            exit_code, stdout, stderr = run_cli(
                "export",
                str(FIXTURES / "sample.candump"),
                str(destination),
                "--json",
            )

            self.assertEqual(exit_code, EXIT_OK)
            self.assertEqual(stderr, "")
            lines = destination.read_text().splitlines()
            self.assertEqual(len(lines), 3)
            first_event = json.loads(lines[0])
            self.assertEqual(first_event["event_type"], "frame")
            self.assertEqual(first_event["source"], "export.capture_file")

    def test_export_session_to_json_writes_session_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with working_directory(temp_dir):
                exit_code, stdout, stderr = run_cli(
                    "session",
                    "save",
                    "lab-a",
                    "--interface",
                    "can0",
                    "--capture",
                    str(FIXTURES / "sample.candump"),
                    "--json",
                )
                self.assertEqual(exit_code, EXIT_OK)
                self.assertEqual(stderr, "")

                destination = Path(temp_dir) / "session-export.json"
                exit_code, stdout, stderr = run_cli(
                    "export",
                    "session:lab-a",
                    str(destination),
                    "--json",
                )

                self.assertEqual(exit_code, EXIT_OK)
                self.assertEqual(stderr, "")
                payload = json.loads(stdout)
                self.assertEqual(payload["data"]["artifact_type"], "session_record")
                self.assertEqual(payload["data"]["source_kind"], "session")

                artifact = json.loads(destination.read_text())
                self.assertEqual(artifact["data"]["artifact_type"], "session_record")
                self.assertEqual(artifact["data"]["session"]["name"], "lab-a")
                self.assertEqual(artifact["data"]["source"]["value"], "lab-a")

    def test_export_session_to_jsonl_returns_user_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with working_directory(temp_dir):
                exit_code, stdout, stderr = run_cli("session", "save", "lab-a", "--json")
                self.assertEqual(exit_code, EXIT_OK)
                self.assertEqual(stderr, "")

                destination = Path(temp_dir) / "session-export.jsonl"
                exit_code, stdout, stderr = run_cli(
                    "export",
                    "session:lab-a",
                    str(destination),
                    "--json",
                )

                self.assertEqual(exit_code, EXIT_USER_ERROR)
                self.assertEqual(stderr, "")
                payload = json.loads(stdout)
                self.assertEqual(payload["errors"][0]["code"], "EXPORT_EVENTS_UNAVAILABLE")

    def test_export_rejects_unsupported_source(self) -> None:
        exit_code, stdout, stderr = run_cli("export", "unknown-source", "artifact.json", "--json")

        self.assertEqual(exit_code, EXIT_USER_ERROR)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertEqual(payload["errors"][0]["code"], "EXPORT_SOURCE_UNSUPPORTED")

    def test_export_rejects_unsupported_destination_suffix(self) -> None:
        exit_code, stdout, stderr = run_cli(
            "export",
            str(FIXTURES / "sample.candump"),
            "artifact.txt",
            "--json",
        )

        self.assertEqual(exit_code, EXIT_USER_ERROR)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertEqual(payload["errors"][0]["code"], "EXPORT_FORMAT_UNSUPPORTED")

    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"})
    def test_shell_command_reuses_cli_parser(self, _mock_cfg) -> None:
        exit_code, stdout, stderr = run_cli("shell", "--command", "capture can0 --raw")
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")
        self.assertIn(" can0 ", stdout)
        self.assertIn("#", stdout)

    def test_tui_starts_and_renders_initial_shell(self) -> None:
        with patch("builtins.input", side_effect=EOFError):
            exit_code, stdout, stderr = run_cli("tui")

        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")
        self.assertIn("== CANarchy TUI ==", stdout)
        self.assertIn("[Bus Status]", stdout)
        self.assertIn("[Live Traffic]", stdout)
        self.assertIn("[Alerts]", stdout)
        self.assertIn("[Command Entry]", stdout)

    def test_tui_command_executes_shared_command_path(self) -> None:
        exit_code, stdout, stderr = run_cli("tui", "--command", "j1939 monitor --pgn 65262")

        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")
        self.assertIn("command: j1939 monitor", stdout)
        self.assertIn("mode: passive", stdout)
        self.assertIn("j1939 pgn=65262", stdout)

    def test_tui_command_surfaces_shared_errors(self) -> None:
        exit_code, stdout, stderr = run_cli("tui", "--command", "j1939 pgn 300000")

        self.assertEqual(exit_code, EXIT_USER_ERROR)
        self.assertEqual(stderr, "")
        self.assertIn("error: INVALID_PGN: J1939 PGN must be between 0 and 262143.", stdout)

    def test_tui_command_rejects_nested_frontends(self) -> None:
        exit_code, stdout, stderr = run_cli("tui", "--command", "shell --command 'capture can0 --raw'")

        self.assertEqual(exit_code, EXIT_USER_ERROR)
        self.assertEqual(stderr, "")
        self.assertIn("TUI_COMMAND_UNSUPPORTED", stdout)

    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"})
    def test_shell_survives_help_flag_in_command(self, _mock_cfg) -> None:
        """--help inside the shell must not exit the session."""
        # After one command containing --help (which raises SystemExit) the shell
        # should stay alive and accept a second command.
        inputs = iter(["capture --help", "capture can0 --raw", EOFError()])

        def fake_input(_prompt):
            val = next(inputs)
            if isinstance(val, BaseException):
                raise val
            return val

        with patch("builtins.input", side_effect=fake_input):
            exit_code, stdout, _ = run_cli("shell")

        self.assertEqual(exit_code, EXIT_OK)
        self.assertIn(" can0 ", stdout)
        self.assertIn("#", stdout)

    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"})
    def test_shell_survives_keyboard_interrupt_during_command(self, _mock_cfg) -> None:
        """Ctrl+C during a command must not exit the shell."""
        call_count = 0

        def fake_main(argv):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise KeyboardInterrupt
            # second call succeeds normally
            return 0

        inputs = iter(["stats tests/fixtures/sample.candump", "capture can0 --raw", EOFError()])

        def fake_input(_prompt):
            val = next(inputs)
            if isinstance(val, BaseException):
                raise val
            return val

        with patch("builtins.input", side_effect=fake_input), \
                patch("canarchy.cli.main", side_effect=fake_main):
            exit_code, _, _ = run_cli("shell")

        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(call_count, 2)

    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"})
    def test_shell_survives_keyboard_interrupt_at_prompt(self, _mock_cfg) -> None:
        """Ctrl+C at the input prompt must not exit the shell."""
        inputs = iter([KeyboardInterrupt(), "capture can0 --raw", EOFError()])

        def fake_input(_prompt):
            val = next(inputs)
            if isinstance(val, BaseException):
                raise val
            return val

        with patch("builtins.input", side_effect=fake_input):
            exit_code, stdout, _ = run_cli("shell")

        self.assertEqual(exit_code, EXIT_OK)
        self.assertIn(" can0 ", stdout)
        self.assertIn("#", stdout)

    def test_tui_survives_help_flag_in_command(self) -> None:
        """--help inside the TUI must not exit the session."""
        inputs = iter(["stats --help", "quit"])

        def fake_input(_prompt):
            val = next(inputs)
            return val

        with patch("builtins.input", side_effect=fake_input):
            exit_code, _, _ = run_cli("tui")

        self.assertEqual(exit_code, EXIT_OK)

    def test_tui_survives_keyboard_interrupt_during_command(self) -> None:
        """Ctrl+C during a TUI command must not exit the session."""
        from canarchy.tui import _run_tui_command, TuiState

        state = TuiState()
        call_count = 0

        def raising_execute(_argv):
            nonlocal call_count
            call_count += 1
            raise KeyboardInterrupt

        result = _run_tui_command("capture can0 --raw", state, raising_execute)
        self.assertEqual(result, 0)
        self.assertEqual(call_count, 1)

    def test_tui_survives_keyboard_interrupt_at_prompt(self) -> None:
        """Ctrl+C at the TUI prompt must not exit the session."""
        inputs = iter([KeyboardInterrupt(), "quit"])

        def fake_input(_prompt):
            val = next(inputs)
            if isinstance(val, BaseException):
                raise val
            return val

        with patch("builtins.input", side_effect=fake_input):
            exit_code, _, _ = run_cli("tui")

        self.assertEqual(exit_code, EXIT_OK)

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
        self.assertEqual(payload["warnings"], [])

    def test_replay_missing_source_returns_transport_error(self) -> None:
        exit_code, stdout, _ = run_cli("replay", "missing.log", "--json")
        self.assertEqual(exit_code, EXIT_TRANSPORT_ERROR)

        payload = json.loads(stdout)
        self.assertEqual(payload["errors"][0]["code"], "CAPTURE_SOURCE_UNAVAILABLE")

    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"})
    def test_jsonl_output_emits_one_event_per_line_for_event_commands(self, _mock_cfg) -> None:
        exit_code, stdout, _ = run_cli("capture", "can0", "--jsonl")
        self.assertEqual(exit_code, EXIT_OK)
        lines = stdout.strip().splitlines()
        self.assertEqual(len(lines), 2)

        first_event = json.loads(lines[0])
        second_event = json.loads(lines[1])
        self.assertEqual(first_event["event_type"], "frame")
        self.assertEqual(second_event["event_type"], "frame")

    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"})
    def test_jsonl_output_does_not_emit_extra_warning_lines_for_uds_scan(self, _mock_cfg) -> None:
        exit_code, stdout, _ = run_cli("uds", "scan", "can0", "--jsonl")
        self.assertEqual(exit_code, EXIT_OK)

        lines = stdout.strip().splitlines()
        self.assertEqual(len(lines), 2)
        for line in lines:
            self.assertEqual(json.loads(line)["event_type"], "uds_transaction")

    def test_jsonl_output_falls_back_to_result_line_for_eventless_commands(self) -> None:
        exit_code, stdout, _ = run_cli("uds", "services", "--jsonl")
        self.assertEqual(exit_code, EXIT_OK)
        lines = stdout.strip().splitlines()
        self.assertEqual(len(lines), 1)

        payload = json.loads(lines[0])
        self.assertEqual(payload["command"], "uds services")
        self.assertIn("services", payload["data"])

    def test_jsonl_error_output_is_single_result_line(self) -> None:
        exit_code, stdout, _ = run_cli("j1939", "pgn", "300000", "--jsonl")
        self.assertEqual(exit_code, EXIT_USER_ERROR)
        lines = stdout.strip().splitlines()
        self.assertEqual(len(lines), 1)
        payload = json.loads(lines[0])
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["errors"][0]["code"], "INVALID_PGN")

    def test_raw_error_output_is_message_only(self) -> None:
        exit_code, stdout, _ = run_cli("j1939", "pgn", "300000", "--raw")
        self.assertEqual(exit_code, EXIT_USER_ERROR)
        self.assertEqual(stdout.strip(), "J1939 PGN must be between 0 and 262143.")

    def test_j1939_pgn_requires_capture_file(self) -> None:
        exit_code, stdout, stderr = run_cli("j1939", "pgn", "65262", "--json")
        self.assertEqual(exit_code, EXIT_USER_ERROR)
        self.assertEqual(stderr, "")

        payload = json.loads(stdout)
        self.assertEqual(payload["errors"][0]["code"], "CAPTURE_FILE_REQUIRED")

    def test_j1939_pgn_uses_real_capture_file(self) -> None:
        exit_code, stdout, stderr = run_cli(
            "j1939",
            "pgn",
            "65262",
            "--file",
            str(FIXTURES / "sample.candump"),
            "--json",
        )
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")

        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["file"], str(FIXTURES / "sample.candump"))
        self.assertEqual(payload["data"]["events"][0]["payload"]["pgn"], 65262)

    def test_j1939_decode_routes_through_decoder_abstraction(self) -> None:
        frame = CanFrame(arbitration_id=0x18FEEE31, data=bytes.fromhex("7DFFFFFF"), timestamp=0.0, is_extended_id=True)
        event = SimpleNamespace(
            to_payload=lambda: {
                "event_type": "j1939_pgn",
                "payload": {
                    "destination_address": None,
                    "frame": frame.to_payload(),
                    "pgn": 65262,
                    "priority": 6,
                    "source_address": 49,
                },
                "source": "test.decoder",
                "timestamp": 0.0,
            }
        )
        fake_decoder = SimpleNamespace(
            supported_spns=lambda: {110},
            decode_events=lambda frames: [event],
            decode_pgn_events=lambda frames, pgn: [],
            spn_observations=lambda frames, spn: [],
            transport_protocol_sessions=lambda frames: [],
            dm1_messages=lambda frames: [],
        )

        with (
            patch("canarchy.cli.get_j1939_decoder", return_value=fake_decoder),
            patch("canarchy.cli.LocalTransport.iter_frames_from_file", return_value=iter([frame])),
        ):
            exit_code, stdout, stderr = run_cli(
                "j1939",
                "decode",
                str(FIXTURES / "j1939_heavy_vehicle.candump"),
                "--json",
            )

        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["events"][0]["source"], "test.decoder")
        self.assertEqual(payload["data"]["events"][0]["payload"]["pgn"], 65262)

    def test_j1939_spn_routes_through_decoder_abstraction(self) -> None:
        frame = CanFrame(arbitration_id=0x18FEEE31, data=bytes.fromhex("7DFFFFFF"), timestamp=0.0, is_extended_id=True)
        observations = [{
            "destination_address": None,
            "name": "Engine Coolant Temperature",
            "pgn": 65262,
            "raw": "7d",
            "source_address": 49,
            "spn": 110,
            "timestamp": 0.0,
            "units": "degC",
            "value": 85.0,
        }]
        fake_decoder = SimpleNamespace(
            supported_spns=lambda: {110},
            decode_events=lambda frames: [],
            decode_pgn_events=lambda frames, pgn: [],
            spn_observations=lambda frames, spn: observations,
            transport_protocol_sessions=lambda frames: [],
            dm1_messages=lambda frames: [],
        )

        with (
            patch("canarchy.cli.get_j1939_decoder", return_value=fake_decoder),
            patch("canarchy.cli.LocalTransport.iter_frames_from_file", return_value=iter([frame])),
        ):
            exit_code, stdout, stderr = run_cli(
                "j1939",
                "spn",
                "110",
                "--file",
                str(FIXTURES / "j1939_heavy_vehicle.candump"),
                "--json",
            )

        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["decoder"], "curated_spn_map")
        self.assertEqual(payload["data"]["observations"], observations)

    def test_j1939_tp_and_dm1_route_through_decoder_abstraction(self) -> None:
        frame = CanFrame(arbitration_id=0x18ECFF31, data=bytes.fromhex("200C0002FFCAFE00"), timestamp=0.0, is_extended_id=True)
        sessions = [{
            "complete": True,
            "control": 32,
            "decoded_text": None,
            "decoded_text_encoding": None,
            "decoded_text_heuristic": False,
            "destination_address": 255,
            "packet_count": 2,
            "payload_label": None,
            "payload_label_source": None,
            "priority": 6,
            "reassembled_data": "000000006e000501be000702",
            "session_type": "bam",
            "source_address": 49,
            "timestamp": 0.0,
            "total_bytes": 12,
            "total_packets": 2,
            "transfer_pgn": 65226,
        }]
        messages = [{
            "active_dtc_count": 2,
            "destination_address": 255,
            "dtcs": [],
            "lamp_status": {"amber_warning": "off", "mil": "off", "protect": "off", "red_stop": "off"},
            "source_address": 49,
            "timestamp": 0.0,
            "transport": "tp",
        }]
        fake_decoder = SimpleNamespace(
            supported_spns=lambda: {110},
            decode_events=lambda frames: [],
            decode_pgn_events=lambda frames, pgn: [],
            spn_observations=lambda frames, spn: [],
            transport_protocol_sessions=lambda frames: sessions,
            dm1_messages=lambda frames: messages,
        )

        with (
            patch("canarchy.cli.get_j1939_decoder", return_value=fake_decoder),
            patch("canarchy.cli.LocalTransport.iter_frames_from_file", return_value=iter([frame])),
        ):
            tp_exit_code, tp_stdout, tp_stderr = run_cli(
                "j1939",
                "tp",
                str(FIXTURES / "j1939_dm1_tp.candump"),
                "--json",
            )
            dm1_exit_code, dm1_stdout, dm1_stderr = run_cli(
                "j1939",
                "dm1",
                str(FIXTURES / "j1939_dm1_tp.candump"),
                "--json",
            )

        self.assertEqual(tp_exit_code, EXIT_OK)
        self.assertEqual(tp_stderr, "")
        self.assertEqual(json.loads(tp_stdout)["data"]["sessions"], sessions)
        self.assertEqual(dm1_exit_code, EXIT_OK)
        self.assertEqual(dm1_stderr, "")
        self.assertEqual(json.loads(dm1_stdout)["data"]["messages"], messages)

    def test_j1939_pgn_routes_through_decoder_abstraction(self) -> None:
        frame = CanFrame(arbitration_id=0x18FEEE31, data=bytes.fromhex("7DFFFFFF"), timestamp=0.0, is_extended_id=True)
        event = SimpleNamespace(
            to_payload=lambda: {
                "event_type": "j1939_pgn",
                "payload": {
                    "destination_address": None,
                    "frame": frame.to_payload(),
                    "pgn": 65262,
                    "priority": 6,
                    "source_address": 49,
                },
                "source": "test.decoder",
                "timestamp": 0.0,
            }
        )
        fake_decoder = SimpleNamespace(
            supported_spns=lambda: {110},
            decode_events=lambda frames: [],
            decode_pgn_events=lambda frames, pgn: [event],
            spn_observations=lambda frames, spn: [],
            transport_protocol_sessions=lambda frames: [],
            dm1_messages=lambda frames: [],
        )

        with (
            patch("canarchy.cli.get_j1939_decoder", return_value=fake_decoder),
            patch("canarchy.cli.LocalTransport.iter_frames_from_file", return_value=iter([frame])),
        ):
            exit_code, stdout, stderr = run_cli(
                "j1939",
                "pgn",
                "65262",
                "--file",
                str(FIXTURES / "j1939_heavy_vehicle.candump"),
                "--json",
            )

        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["pgn"], 65262)
        self.assertEqual(payload["data"]["events"][0]["source"], "test.decoder")

    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"})
    def test_generate_fixed_id_and_data_returns_frame_events(self, _mock_cfg) -> None:
        exit_code, stdout, stderr = run_cli(
            "generate", "can0", "--id", "0x123", "--dlc", "4", "--data", "11223344", "--json"
        )
        self.assertEqual(exit_code, EXIT_OK)
        self.assertIn("warning: `generate` will transmit generated frames", stderr)

        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["mode"], "active")
        self.assertEqual(payload["data"]["frame_count"], 1)
        self.assertEqual(payload["data"]["transport_backend"], "scaffold")
        self.assertEqual(payload["warnings"], [])
        alert_event = payload["data"]["events"][0]
        self.assertEqual(alert_event["event_type"], "alert")
        self.assertEqual(alert_event["payload"]["code"], "ACTIVE_TRANSMIT")
        frame_event = payload["data"]["events"][1]
        self.assertEqual(frame_event["event_type"], "frame")
        self.assertEqual(frame_event["payload"]["frame"]["arbitration_id"], 0x123)
        self.assertEqual(frame_event["payload"]["frame"]["data"], "11223344")

    @patch("canarchy.transport.time.sleep")
    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"})
    def test_generate_count_produces_correct_number_of_frames(self, _mock_cfg, mock_sleep) -> None:
        exit_code, stdout, stderr = run_cli(
            "generate",
            "can0",
            "--id",
            "0x7DF",
            "--dlc",
            "2",
            "--data",
            "I",
            "--count",
            "3",
            "--gap",
            "100",
            "--json",
        )
        self.assertEqual(exit_code, EXIT_OK)
        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["frame_count"], 3)
        frame_events = [e for e in payload["data"]["events"] if e["event_type"] == "frame"]
        self.assertEqual(len(frame_events), 3)
        self.assertEqual(frame_events[0]["timestamp"], 0.0)
        self.assertEqual(frame_events[1]["timestamp"], 0.1)
        self.assertEqual(frame_events[2]["timestamp"], 0.2)
        self.assertEqual(mock_sleep.call_count, 2)
        mock_sleep.assert_called_with(0.1)

    @patch("canarchy.transport.time.sleep")
    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"})
    def test_generate_incrementing_data_produces_rolling_bytes(self, _mock_cfg, _mock_sleep) -> None:
        exit_code, stdout, stderr = run_cli(
            "generate", "can0", "--id", "0x100", "--dlc", "2", "--data", "I", "--count", "2", "--json"
        )
        self.assertEqual(exit_code, EXIT_OK)
        payload = json.loads(stdout)
        frame_events = [e for e in payload["data"]["events"] if e["event_type"] == "frame"]
        self.assertEqual(frame_events[0]["payload"]["frame"]["data"], "0001")
        self.assertEqual(frame_events[1]["payload"]["frame"]["data"], "0203")

    @patch("canarchy.transport.time.sleep")
    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"})
    def test_generate_random_produces_frame_events(self, _mock_cfg, _mock_sleep) -> None:
        exit_code, stdout, stderr = run_cli("generate", "can0", "--count", "5", "--json")
        self.assertEqual(exit_code, EXIT_OK)
        self.assertIn("warning: `generate` will transmit generated frames", stderr)
        payload = json.loads(stdout)
        frame_events = [e for e in payload["data"]["events"] if e["event_type"] == "frame"]
        self.assertEqual(len(frame_events), 5)

    @patch("canarchy.transport.time.sleep")
    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"})
    def test_generate_table_output_is_pretty_printed(self, _mock_cfg, _mock_sleep) -> None:
        exit_code, stdout, stderr = run_cli(
            "generate", "can0", "--id", "0x123", "--dlc", "4", "--data", "AABBCCDD", "--count", "2", "--table"
        )
        self.assertEqual(exit_code, EXIT_OK)
        self.assertIn("command: generate", stdout)
        self.assertIn("interface: can0", stdout)
        self.assertIn("frames: 2", stdout)
        self.assertIn("123#AABBCCDD", stdout)

    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"})
    def test_generate_extended_flag_sets_29bit_id(self, _mock_cfg) -> None:
        exit_code, stdout, stderr = run_cli(
            "generate", "can0", "--id", "0x100", "--dlc", "0", "--data", "R", "--extended", "--json"
        )
        self.assertEqual(exit_code, EXIT_OK)
        payload = json.loads(stdout)
        frame_event = payload["data"]["events"][1]
        self.assertTrue(frame_event["payload"]["frame"]["is_extended_id"])

    # --- Gap option tests ---

    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"})
    def test_generate_default_gap_is_200ms(self, _mock_cfg) -> None:
        exit_code, stdout, _ = run_cli(
            "generate", "can0", "--id", "0x1", "--dlc", "1", "--data", "FF", "--json"
        )
        self.assertEqual(exit_code, EXIT_OK)
        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["gap_ms"], 200.0)

    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"})
    def test_generate_gap_zero_gives_zero_timestamps(self, _mock_cfg) -> None:
        exit_code, stdout, _ = run_cli(
            "generate", "can0", "--id", "0x1", "--dlc", "1", "--data", "AA",
            "--count", "3", "--gap", "0", "--json"
        )
        self.assertEqual(exit_code, EXIT_OK)
        payload = json.loads(stdout)
        frame_events = [e for e in payload["data"]["events"] if e["event_type"] == "frame"]
        self.assertEqual(len(frame_events), 3)
        for evt in frame_events:
            self.assertEqual(evt["timestamp"], 0.0)

    @patch("canarchy.transport.time.sleep")
    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"})
    def test_generate_gap_sets_timestamp_spacing(self, _mock_cfg, mock_sleep) -> None:
        exit_code, stdout, _ = run_cli(
            "generate", "can0", "--id", "0x1", "--dlc", "1", "--data", "AA",
            "--count", "4", "--gap", "500", "--json"
        )
        self.assertEqual(exit_code, EXIT_OK)
        payload = json.loads(stdout)
        frame_events = [e for e in payload["data"]["events"] if e["event_type"] == "frame"]
        self.assertEqual(len(frame_events), 4)
        self.assertAlmostEqual(frame_events[0]["timestamp"], 0.0)
        self.assertAlmostEqual(frame_events[1]["timestamp"], 0.5)
        self.assertAlmostEqual(frame_events[2]["timestamp"], 1.0)
        self.assertAlmostEqual(frame_events[3]["timestamp"], 1.5)
        self.assertEqual(mock_sleep.call_count, 3)
        mock_sleep.assert_called_with(0.5)

    @patch("canarchy.transport.time.sleep")
    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"})
    def test_generate_gap_reflects_in_data_field(self, _mock_cfg, mock_sleep) -> None:
        exit_code, stdout, _ = run_cli(
            "generate", "can0", "--id", "0x1", "--dlc", "1", "--data", "AA",
            "--count", "2", "--gap", "750", "--json"
        )
        self.assertEqual(exit_code, EXIT_OK)
        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["gap_ms"], 750.0)
        self.assertEqual(payload["data"]["gap"], 750.0)
        self.assertEqual(mock_sleep.call_count, 1)
        mock_sleep.assert_called_with(0.75)

    @patch("canarchy.transport.time.sleep")
    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"})
    def test_generate_fractional_gap_spacing(self, _mock_cfg, mock_sleep) -> None:
        exit_code, stdout, _ = run_cli(
            "generate", "can0", "--id", "0x1", "--dlc", "1", "--data", "AA",
            "--count", "3", "--gap", "50.5", "--json"
        )
        self.assertEqual(exit_code, EXIT_OK)
        payload = json.loads(stdout)
        frame_events = [e for e in payload["data"]["events"] if e["event_type"] == "frame"]
        self.assertAlmostEqual(frame_events[0]["timestamp"], 0.0, places=5)
        self.assertAlmostEqual(frame_events[1]["timestamp"], 0.0505, places=5)
        self.assertAlmostEqual(frame_events[2]["timestamp"], 0.101, places=5)
        self.assertEqual(mock_sleep.call_count, 2)
        mock_sleep.assert_called_with(0.0505)

    # --- stdin composition tests ---

    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"})
    def test_decode_stdin_jsonl_composition(self, _mock_cfg):
        """Test that decode can read JSONL FrameEvents from stdin and decode them."""
        # Generate a frame that matches a signal in the sample DBC
        frame_json = ('{"event_type": "frame", "payload": {"frame": '
                      '{"arbitration_id": 419360305, "data": "11223344", '
                      '"is_extended_id": true, "timestamp": 0.0, "interface": "can0"}}, '
                      '"source": "test"}')
        
        exit_code, stdout, _ = run_cli(
            "decode", "--stdin", "--dbc", str(FIXTURES / "sample.dbc"), "--jsonl",
            input=frame_json
        )
        
        self.assertEqual(exit_code, EXIT_OK)
        lines = stdout.strip().splitlines()
        # Should have decoded_message event plus signal events
        self.assertGreater(len(lines), 1)
        
        # First line should be decoded_message
        decoded_event = json.loads(lines[0])
        self.assertEqual(decoded_event["event_type"], "decoded_message")
        self.assertEqual(decoded_event["payload"]["message_name"], "EngineStatus1")
        self.assertIn("CoolantTemp", decoded_event["payload"]["signals"])

    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"})
    def test_filter_stdin_jsonl_composition(self, _mock_cfg):
        """Test that filter can read JSONL FrameEvents from stdin and filter them."""
        # Generate two frames - one matching filter, one not
        frame1_json = ('{"event_type": "frame", "payload": {"frame": '
                      '{"arbitration_id": 419360305, "data": "11223344", '
                      '"is_extended_id": true, "timestamp": 0.0, "interface": "can0"}}, '
                      '"source": "test"}')
        frame2_json = ('{"event_type": "frame", "payload": {"frame": '
                      '{"arbitration_id": 123, "data": "deadbeef", '
                      '"is_extended_id": false, "timestamp": 0.1, "interface": "can0"}}, '
                      '"source": "test"}')
        input_data = frame1_json + "\n" + frame2_json + "\n"
        
        exit_code, stdout, _ = run_cli(
            "filter", "--stdin", "id==0x18FEEE31", "--jsonl",
            input=input_data
        )
        
        self.assertEqual(exit_code, EXIT_OK)
        lines = stdout.strip().splitlines()
        # Should only get the matching frame back
        self.assertEqual(len(lines), 1)
        
        frame_event = json.loads(lines[0])
        self.assertEqual(frame_event["event_type"], "frame")
        self.assertEqual(frame_event["payload"]["frame"]["arbitration_id"], 419360305)
        self.assertEqual(frame_event["payload"]["frame"]["data"], "11223344")

    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"})
    def test_j1939_decode_stdin_jsonl_composition(self, _mock_cfg):
        """Test that j1939 decode can read JSONL FrameEvents from stdin and decode them."""
        # Generate a J1939 frame
        frame_json = ('{"event_type": "frame", "payload": {"frame": '
                      '{"arbitration_id": 419360305, "data": "11223344", '
                      '"is_extended_id": true, "timestamp": 0.0, "interface": "can0"}}, '
                      '"source": "test"}')
        
        exit_code, stdout, _ = run_cli(
            "j1939", "decode", "--stdin", "--jsonl",
            input=frame_json
        )
        
        self.assertEqual(exit_code, EXIT_OK)
        lines = stdout.strip().splitlines()
        # Should have J1939 observation event
        self.assertEqual(len(lines), 1)
        
        observation_event = json.loads(lines[0])
        self.assertEqual(observation_event["event_type"], "j1939_pgn")
        self.assertEqual(observation_event["payload"]["pgn"], 65262)
        self.assertEqual(observation_event["payload"]["source_address"], 49)

    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"})
    def test_stdin_validation_invalid_json(self, _mock_cfg):
        """Test that invalid JSON in stdin produces appropriate error."""
        exit_code, stdout, _ = run_cli(
            "decode", "--stdin", "--dbc", str(FIXTURES / "sample.dbc"), "--json",
            input="not json at all\n"
        )
        
        self.assertEqual(exit_code, EXIT_USER_ERROR)
        payload = json.loads(stdout)
        self.assertEqual(payload["errors"][0]["code"], "INVALID_STREAM_EVENT")
        self.assertIn("Invalid JSON", payload["errors"][0]["message"])

    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"})
    def test_stdin_validation_wrong_event_type(self, _mock_cfg):
        """Test that non-frame events in stdin produce appropriate error."""
        exit_code, stdout, _ = run_cli(
            "decode", "--stdin", "--dbc", str(FIXTURES / "sample.dbc"), "--json",
            input='{"event_type": "alert", "payload": {"message": "test"}}\n'
        )
        
        self.assertEqual(exit_code, EXIT_USER_ERROR)
        payload = json.loads(stdout)
        self.assertEqual(payload["errors"][0]["code"], "INVALID_STREAM_EVENT")
        self.assertIn("Expected frame event", payload["errors"][0]["message"])

    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"})
    def test_stdin_mutually_exclusive_with_file(self, _mock_cfg):
        """Test that specifying both --stdin and a file produces an error."""
        exit_code, stdout, _ = run_cli(
            "decode", "--stdin", str(FIXTURES / "sample.candump"),
            "--dbc", str(FIXTURES / "sample.dbc"), "--json"
        )
        
        self.assertEqual(exit_code, EXIT_USER_ERROR)
        payload = json.loads(stdout)
        self.assertEqual(payload["errors"][0]["code"], "STDIN_AND_FILE_SPECIFIED")

    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"})
    def test_stdin_required_when_no_file(self, _mock_cfg):
        """Test that specifying neither --stdin nor a file produces an error."""
        exit_code, stdout, _ = run_cli(
            "decode", "--dbc", str(FIXTURES / "sample.dbc"), "--json"
        )
        
        self.assertEqual(exit_code, EXIT_USER_ERROR)
        payload = json.loads(stdout)
        self.assertEqual(payload["errors"][0]["code"], "MISSING_INPUT")

    # --- ID option tests ---

    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"})
    def test_generate_id_without_0x_prefix(self, _mock_cfg) -> None:
        exit_code, stdout, _ = run_cli(
            "generate", "can0", "--id", "7DF", "--dlc", "2", "--data", "1234", "--json"
        )
        self.assertEqual(exit_code, EXIT_OK)
        payload = json.loads(stdout)
        frame_event = payload["data"]["events"][1]
        self.assertEqual(frame_event["payload"]["frame"]["arbitration_id"], 0x7DF)

    @patch("canarchy.transport.time.sleep")
    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"})
    def test_generate_id_r_default_produces_random_ids(self, _mock_cfg, _mock_sleep) -> None:
        exit_code, stdout, _ = run_cli(
            "generate", "can0", "--count", "3", "--json"
        )
        self.assertEqual(exit_code, EXIT_OK)
        payload = json.loads(stdout)
        frame_events = [e for e in payload["data"]["events"] if e["event_type"] == "frame"]
        self.assertEqual(len(frame_events), 3)
        for evt in frame_events:
            arb_id = evt["payload"]["frame"]["arbitration_id"]
            self.assertGreaterEqual(arb_id, 0)

    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"})
    def test_generate_large_id_forces_extended(self, _mock_cfg) -> None:
        exit_code, stdout, _ = run_cli(
            "generate", "can0", "--id", "0x18FEEE31", "--dlc", "8", "--data", "AABBCCDDEEFF0011", "--json"
        )
        self.assertEqual(exit_code, EXIT_OK)
        payload = json.loads(stdout)
        frame_event = payload["data"]["events"][1]
        self.assertEqual(frame_event["payload"]["frame"]["arbitration_id"], 0x18FEEE31)
        self.assertTrue(frame_event["payload"]["frame"]["is_extended_id"])

    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"})
    def test_generate_id_zero(self, _mock_cfg) -> None:
        exit_code, stdout, _ = run_cli(
            "generate", "can0", "--id", "0x0", "--dlc", "1", "--data", "FF", "--json"
        )
        self.assertEqual(exit_code, EXIT_OK)
        payload = json.loads(stdout)
        frame_event = payload["data"]["events"][1]
        self.assertEqual(frame_event["payload"]["frame"]["arbitration_id"], 0)

    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"})
    def test_generate_id_max_standard(self, _mock_cfg) -> None:
        exit_code, stdout, _ = run_cli(
            "generate", "can0", "--id", "0x7FF", "--dlc", "1", "--data", "00", "--json"
        )
        self.assertEqual(exit_code, EXIT_OK)
        payload = json.loads(stdout)
        frame_event = payload["data"]["events"][1]
        self.assertEqual(frame_event["payload"]["frame"]["arbitration_id"], 0x7FF)
        self.assertFalse(frame_event["payload"]["frame"]["is_extended_id"])

    # --- DLC option tests ---

    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"})
    def test_generate_dlc_zero_produces_empty_data(self, _mock_cfg) -> None:
        exit_code, stdout, _ = run_cli(
            "generate", "can0", "--id", "0x1", "--dlc", "0", "--data", "R", "--json"
        )
        self.assertEqual(exit_code, EXIT_OK)
        payload = json.loads(stdout)
        frame_event = payload["data"]["events"][1]
        self.assertEqual(frame_event["payload"]["frame"]["data"], "")
        self.assertEqual(frame_event["payload"]["frame"]["dlc"], 0)

    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"})
    def test_generate_dlc_eight_produces_eight_byte_frame(self, _mock_cfg) -> None:
        exit_code, stdout, _ = run_cli(
            "generate", "can0", "--id", "0x1", "--dlc", "8", "--data", "R", "--json"
        )
        self.assertEqual(exit_code, EXIT_OK)
        payload = json.loads(stdout)
        frame_event = payload["data"]["events"][1]
        self.assertEqual(frame_event["payload"]["frame"]["dlc"], 8)
        self.assertEqual(len(frame_event["payload"]["frame"]["data"]), 16)  # 8 bytes = 16 hex chars

    # --- Data option tests ---

    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"})
    def test_generate_data_r_produces_hex_payload(self, _mock_cfg) -> None:
        exit_code, stdout, _ = run_cli(
            "generate", "can0", "--id", "0x1", "--dlc", "4", "--data", "R", "--json"
        )
        self.assertEqual(exit_code, EXIT_OK)
        payload = json.loads(stdout)
        frame_event = payload["data"]["events"][1]
        data_hex = frame_event["payload"]["frame"]["data"]
        self.assertEqual(len(data_hex), 8)  # 4 bytes = 8 hex chars
        int(data_hex, 16)  # must be valid hex

    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"})
    def test_generate_data_uppercase_hex_accepted(self, _mock_cfg) -> None:
        exit_code, stdout, _ = run_cli(
            "generate", "can0", "--id", "0x1", "--dlc", "4", "--data", "DEADBEEF", "--json"
        )
        self.assertEqual(exit_code, EXIT_OK)
        payload = json.loads(stdout)
        frame_event = payload["data"]["events"][1]
        self.assertEqual(frame_event["payload"]["frame"]["data"].upper(), "DEADBEEF")

    @patch("canarchy.transport.time.sleep")
    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"})
    def test_generate_incrementing_data_rolls_across_frames(self, _mock_cfg, _mock_sleep) -> None:
        exit_code, stdout, _ = run_cli(
            "generate", "can0", "--id", "0x1", "--dlc", "4", "--data", "I", "--count", "3", "--json"
        )
        self.assertEqual(exit_code, EXIT_OK)
        payload = json.loads(stdout)
        frame_events = [e for e in payload["data"]["events"] if e["event_type"] == "frame"]
        self.assertEqual(frame_events[0]["payload"]["frame"]["data"], "00010203")
        self.assertEqual(frame_events[1]["payload"]["frame"]["data"], "04050607")
        self.assertEqual(frame_events[2]["payload"]["frame"]["data"], "08090a0b")

    # --- Count option tests ---

    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"})
    def test_generate_default_count_is_one(self, _mock_cfg) -> None:
        exit_code, stdout, _ = run_cli(
            "generate", "can0", "--id", "0x1", "--dlc", "1", "--data", "FF", "--json"
        )
        self.assertEqual(exit_code, EXIT_OK)
        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["frame_count"], 1)
        frame_events = [e for e in payload["data"]["events"] if e["event_type"] == "frame"]
        self.assertEqual(len(frame_events), 1)

    @patch("canarchy.transport.time.sleep")
    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"})
    def test_generate_count_ten(self, _mock_cfg, mock_sleep) -> None:
        exit_code, stdout, _ = run_cli(
            "generate", "can0", "--id", "0x1", "--dlc", "1", "--data", "AA", "--count", "10", "--json"
        )
        self.assertEqual(exit_code, EXIT_OK)
        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["frame_count"], 10)
        frame_events = [e for e in payload["data"]["events"] if e["event_type"] == "frame"]
        self.assertEqual(len(frame_events), 10)
        self.assertEqual(mock_sleep.call_count, 9)

    # --- Output mode tests ---

    @patch("canarchy.transport.time.sleep")
    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"})
    def test_generate_jsonl_output_emits_one_event_per_line(self, _mock_cfg, _mock_sleep) -> None:
        exit_code, stdout, _ = run_cli(
            "generate", "can0", "--id", "0x1", "--dlc", "1", "--data", "AA", "--count", "2", "--jsonl"
        )
        self.assertEqual(exit_code, EXIT_OK)
        lines = [l for l in stdout.strip().splitlines() if l.strip()]
        # alert event + 2 frame events
        self.assertGreaterEqual(len(lines), 3)
        for line in lines:
            json.loads(line)  # each line must be valid JSON
        event_types = [json.loads(l)["event_type"] for l in lines]
        self.assertIn("alert", event_types)
        self.assertEqual(event_types.count("frame"), 2)

    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"})
    def test_generate_raw_output_emits_command_name(self, _mock_cfg) -> None:
        exit_code, stdout, _ = run_cli(
            "generate", "can0", "--id", "0x1", "--dlc", "1", "--data", "AA", "--raw"
        )
        self.assertEqual(exit_code, EXIT_OK)
        self.assertIn("generate", stdout.strip())

    # --- Result data fields ---

    @patch("canarchy.transport.time.sleep")
    @patch("canarchy.transport._load_user_config", return_value={"CANARCHY_TRANSPORT_BACKEND": "scaffold"})
    def test_generate_result_data_contains_expected_fields(self, _mock_cfg, _mock_sleep) -> None:
        exit_code, stdout, _ = run_cli(
            "generate", "can0", "--id", "0x123", "--dlc", "4", "--data", "11223344",
            "--count", "2", "--gap", "300", "--json"
        )
        self.assertEqual(exit_code, EXIT_OK)
        payload = json.loads(stdout)
        data = payload["data"]
        self.assertEqual(data["interface"], "can0")
        self.assertEqual(data["mode"], "active")
        self.assertEqual(data["frame_count"], 2)
        self.assertEqual(data["gap_ms"], 300.0)
        self.assertEqual(data["transport_backend"], "scaffold")
        self.assertFalse(data["extended"])
        self.assertEqual(data["id"], "0x123")
        self.assertEqual(data["dlc"], "4")

    def test_generate_invalid_id_returns_user_error(self) -> None:
        exit_code, stdout, stderr = run_cli("generate", "can0", "--id", "ZZZZ", "--json")
        self.assertEqual(exit_code, EXIT_USER_ERROR)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertEqual(payload["errors"][0]["code"], "INVALID_FRAME_ID")

    def test_generate_invalid_dlc_returns_user_error(self) -> None:
        exit_code, stdout, stderr = run_cli("generate", "can0", "--dlc", "99", "--json")
        self.assertEqual(exit_code, EXIT_USER_ERROR)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertEqual(payload["errors"][0]["code"], "INVALID_DLC")

    def test_generate_invalid_payload_returns_user_error(self) -> None:
        exit_code, stdout, stderr = run_cli("generate", "can0", "--data", "XYZ", "--json")
        self.assertEqual(exit_code, EXIT_USER_ERROR)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertEqual(payload["errors"][0]["code"], "INVALID_FRAME_DATA")

    def test_generate_invalid_count_returns_user_error(self) -> None:
        exit_code, stdout, stderr = run_cli("generate", "can0", "--count", "0", "--json")
        self.assertEqual(exit_code, EXIT_USER_ERROR)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertEqual(payload["errors"][0]["code"], "INVALID_COUNT")

    def test_generate_negative_gap_returns_user_error(self) -> None:
        exit_code, stdout, stderr = run_cli("generate", "can0", "--gap", "-1", "--json")
        self.assertEqual(exit_code, EXIT_USER_ERROR)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertEqual(payload["errors"][0]["code"], "INVALID_GAP")

    def test_transport_error_returns_backend_exit_code(self) -> None:
        exit_code, stdout, stderr = run_cli("capture", "offline0", "--json")
        self.assertEqual(exit_code, EXIT_TRANSPORT_ERROR)
        self.assertEqual(stderr, "")

        payload = json.loads(stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["errors"][0]["code"], "TRANSPORT_UNAVAILABLE")

    def test_capture_jsonl_uses_python_can_backend_when_requested(self) -> None:
        fake_bus = FakeBus(
            [
                self.fake_message(0x123, bytes.fromhex("11223344")),
                self.fake_message(0x18FEEE31, bytes.fromhex("AABBCCDD"), is_extended_id=True),
            ],
            end_exception=KeyboardInterrupt,
        )
        with patch.dict(
            os.environ,
            {
                "CANARCHY_TRANSPORT_BACKEND": "python-can",
                "CANARCHY_PYTHON_CAN_INTERFACE": "virtual",
                "CANARCHY_CAPTURE_LIMIT": "3",
            },
            clear=False,
        ):
            with patch.object(PythonCanBackend, "_open_bus", return_value=fake_bus):
                exit_code, stdout, stderr = run_cli("capture", "can0", "--jsonl")

        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")
        lines = stdout.strip().splitlines()
        self.assertEqual(len(lines), 2)
        payloads = [json.loads(line) for line in lines]
        self.assertEqual(payloads[0]["payload"]["frame"]["arbitration_id"], 0x123)
        self.assertFalse(payloads[0]["payload"]["frame"]["is_extended_id"])
        self.assertEqual(payloads[1]["payload"]["frame"]["arbitration_id"], 0x18FEEE31)
        self.assertTrue(payloads[1]["payload"]["frame"]["is_extended_id"])

    def test_capture_candump_uses_python_can_backend_when_requested(self) -> None:
        fake_bus = FakeBus(
            [
                self.fake_message(0x123, bytes.fromhex("11223344")),
                self.fake_message(0x18FEEE31, bytes.fromhex("AABBCCDD"), is_extended_id=True),
            ],
            end_exception=KeyboardInterrupt,
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

    def test_capture_candump_formats_fd_rtr_and_error_frames(self) -> None:
        fake_bus = FakeBus(
            [
                self.fake_message_with_flags(
                    0x123,
                    bytes.fromhex("1122334455667788"),
                    is_fd=True,
                    bitrate_switch=True,
                    error_state_indicator=True,
                ),
                self.fake_message_with_flags(0x123, b"", is_remote_frame=True),
                self.fake_message_with_flags(
                    0x80,
                    bytes.fromhex("0000000000000000"),
                    is_error_frame=True,
                ),
            ],
            end_exception=KeyboardInterrupt,
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
        self.assertEqual(lines[0], "(0.000000) vcan0 123##31122334455667788")
        self.assertEqual(lines[1], "(0.000000) vcan0 123#R")
        self.assertEqual(lines[2], "(0.000000) vcan0 20000080#0000000000000000")

    def test_capture_json_transport_error_is_structured_for_streaming_path(self) -> None:
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

    def test_unsupported_capture_file_format_returns_transport_error(self) -> None:
        exit_code, stdout, stderr = run_cli("stats", str(FIXTURES / "sample.dbc"), "--json")
        self.assertEqual(exit_code, EXIT_TRANSPORT_ERROR)
        self.assertEqual(stderr, "")

        payload = json.loads(stdout)
        self.assertEqual(payload["errors"][0]["code"], "CAPTURE_FORMAT_UNSUPPORTED")
        self.assertIn("unsupported file format", payload["errors"][0]["message"])


class CompletionTests(unittest.TestCase):
    """Tests for tab completion in the shell and TUI."""

    def _completions(self, line: str, text: str = "") -> list[str]:
        """Run the completer against *line* and return all candidate strings."""
        from canarchy.completion import CanarchyCompleter

        completer = CanarchyCompleter()

        with patch("canarchy.completion.readline") as mock_rl:
            mock_rl.get_line_buffer.return_value = line
            results = []
            state = 0
            while True:
                candidate = completer.complete(text, state)
                if candidate is None:
                    break
                results.append(candidate)
                state += 1
        return results

    # ── First token: top-level commands ──────────────────────────────────────

    def test_empty_line_offers_all_top_level_commands(self) -> None:
        results = self._completions("", "")
        # Strip trailing spaces for comparison
        names = [r.strip() for r in results]
        self.assertIn("capture", names)
        self.assertIn("j1939", names)
        self.assertIn("uds", names)
        self.assertIn("generate", names)
        self.assertIn("exit", names)
        # shell and tui must NOT appear in the interactive prompt completions
        self.assertNotIn("shell", names)
        self.assertNotIn("tui", names)

    def test_partial_command_filters_correctly(self) -> None:
        results = self._completions("ca", "ca")
        names = [r.strip() for r in results]
        self.assertIn("capture", names)
        self.assertNotIn("generate", names)
        self.assertNotIn("send", names)

    def test_j_prefix_returns_j1939(self) -> None:
        results = self._completions("j", "j")
        names = [r.strip() for r in results]
        self.assertIn("j1939", names)
        self.assertNotIn("capture", names)

    def test_exit_and_quit_appear_in_completions(self) -> None:
        results = self._completions("", "")
        names = [r.strip() for r in results]
        self.assertIn("exit", names)
        self.assertIn("quit", names)

    # ── Subcommand completion ─────────────────────────────────────────────────

    def test_j1939_space_offers_subcommands(self) -> None:
        results = self._completions("j1939 ", "")
        names = [r.strip() for r in results]
        self.assertIn("monitor", names)
        self.assertIn("decode", names)
        self.assertIn("pgn", names)
        self.assertIn("spn", names)
        self.assertIn("tp", names)
        self.assertIn("dm1", names)

    def test_j1939_partial_subcommand_filters(self) -> None:
        results = self._completions("j1939 m", "m")
        names = [r.strip() for r in results]
        self.assertIn("monitor", names)
        self.assertNotIn("decode", names)

    def test_session_subcommands(self) -> None:
        results = self._completions("session ", "")
        names = [r.strip() for r in results]
        self.assertIn("save", names)
        self.assertIn("load", names)
        self.assertIn("show", names)

    def test_uds_subcommands(self) -> None:
        results = self._completions("uds ", "")
        names = [r.strip() for r in results]
        self.assertIn("scan", names)
        self.assertIn("trace", names)
        self.assertIn("services", names)

    # ── Flag completion ───────────────────────────────────────────────────────

    def test_capture_flags_include_candump_and_output_modes(self) -> None:
        results = self._completions("capture can0 ", "")
        names = [r.strip() for r in results]
        self.assertIn("--candump", names)
        self.assertIn("--json", names)
        self.assertIn("--jsonl", names)
        self.assertIn("--table", names)
        self.assertIn("--raw", names)

    def test_generate_flags_include_gap_and_count(self) -> None:
        results = self._completions("generate can0 ", "")
        names = [r.strip() for r in results]
        self.assertIn("--ack-active", names)
        self.assertIn("--gap", names)
        self.assertIn("--count", names)
        self.assertIn("--id", names)
        self.assertIn("--dlc", names)
        self.assertIn("--data", names)
        self.assertIn("--extended", names)

    def test_decode_flags_include_dbc(self) -> None:
        results = self._completions("decode trace.candump ", "")
        names = [r.strip() for r in results]
        self.assertIn("--dbc", names)
        self.assertIn("--json", names)

    def test_j1939_monitor_flags_include_pgn(self) -> None:
        results = self._completions("j1939 monitor ", "")
        names = [r.strip() for r in results]
        self.assertIn("--pgn", names)
        self.assertIn("--json", names)

    def test_dbc_inspect_flags_include_message_and_signals_only(self) -> None:
        results = self._completions("dbc inspect tests/fixtures/sample.dbc ", "")
        names = [r.strip() for r in results]
        self.assertIn("--message", names)
        self.assertIn("--signals-only", names)
        self.assertIn("--json", names)

    def test_j1939_pgn_flags_include_file(self) -> None:
        results = self._completions("j1939 pgn 65262 ", "")
        names = [r.strip() for r in results]
        self.assertIn("--file", names)
        self.assertIn("--dbc", names)
        self.assertIn("--max-frames", names)
        self.assertIn("--seconds", names)

    def test_j1939_decode_flags_include_dbc(self) -> None:
        results = self._completions("j1939 decode ", "")
        names = [r.strip() for r in results]
        self.assertIn("--dbc", names)
        self.assertIn("--max-frames", names)
        self.assertIn("--seconds", names)

    def test_j1939_dm1_flags_include_dbc(self) -> None:
        results = self._completions("j1939 dm1 tests/fixtures/j1939_dm1_spn175.candump ", "")
        names = [r.strip() for r in results]
        self.assertIn("--dbc", names)
        self.assertIn("--max-frames", names)
        self.assertIn("--seconds", names)

    def test_j1939_summary_flags_include_bounds(self) -> None:
        results = self._completions("j1939 summary ", "")
        names = [r.strip() for r in results]
        self.assertIn("--max-frames", names)
        self.assertIn("--seconds", names)

    def test_session_save_flags_include_interface_and_dbc(self) -> None:
        results = self._completions("session save mylab ", "")
        names = [r.strip() for r in results]
        self.assertIn("--interface", names)
        self.assertIn("--dbc", names)
        self.assertIn("--capture", names)

    def test_partial_flag_filters_correctly(self) -> None:
        results = self._completions("capture can0 --j", "--j")
        names = [r.strip() for r in results]
        self.assertIn("--json", names)
        self.assertIn("--jsonl", names)
        self.assertNotIn("--table", names)
        self.assertNotIn("--candump", names)

    def test_flags_not_offered_for_unknown_command(self) -> None:
        # Unknown command falls back to output-mode flags only
        results = self._completions("unknowncmd ", "")
        names = [r.strip() for r in results]
        self.assertIn("--json", names)

    # ── File path completion after file-expecting flags ───────────────────────

    def test_completion_after_dbc_flag_uses_path_completion(self) -> None:
        """After --dbc, completions should come from the filesystem, not flags."""
        from canarchy.completion import CanarchyCompleter

        completer = CanarchyCompleter()
        with patch("canarchy.completion.readline") as mock_rl:
            mock_rl.get_line_buffer.return_value = "decode trace.candump --dbc "
            with patch("canarchy.completion.glob.glob", return_value=["tests/fixtures/sample.dbc"]):
                candidate = completer.complete("tests/", 0)
        self.assertIsNotNone(candidate)
        self.assertIn("sample.dbc", candidate)

    def test_completion_after_file_flag_uses_path_completion(self) -> None:
        from canarchy.completion import CanarchyCompleter

        completer = CanarchyCompleter()
        with patch("canarchy.completion.readline") as mock_rl:
            mock_rl.get_line_buffer.return_value = "j1939 pgn 65262 --file "
            with patch("canarchy.completion.glob.glob", return_value=["tests/fixtures/sample.candump"]):
                candidate = completer.complete("tests/", 0)
        self.assertIsNotNone(candidate)
        self.assertIn("sample.candump", candidate)

    # ── install_completion smoke test ─────────────────────────────────────────

    def test_install_completion_registers_completer(self) -> None:
        """install_completion should call readline.set_completer without raising."""
        from canarchy.completion import install_completion

        with patch("canarchy.completion.readline") as mock_rl, \
                patch("canarchy.completion.atexit"):
            mock_rl.__doc__ = "GNU readline"
            mock_rl.read_history_file.side_effect = FileNotFoundError
            install_completion()
            mock_rl.set_completer.assert_called_once()
            mock_rl.parse_and_bind.assert_called_once_with("tab: complete")

    def test_install_completion_uses_libedit_binding_on_macos(self) -> None:
        from canarchy.completion import install_completion

        with patch("canarchy.completion.readline") as mock_rl, \
                patch("canarchy.completion.atexit"):
            mock_rl.__doc__ = "libedit-based readline"
            mock_rl.read_history_file.side_effect = FileNotFoundError
            install_completion()
            mock_rl.parse_and_bind.assert_called_once_with("bind ^I rl_complete")

    def test_install_completion_is_silent_when_readline_unavailable(self) -> None:
        """Should not raise if readline is None (unavailable platform)."""
        import canarchy.completion as completion_mod
        original = completion_mod.readline
        try:
            completion_mod.readline = None  # type: ignore[assignment]
            # Should not raise
            completion_mod.install_completion()
        finally:
            completion_mod.readline = original


class ConfigShowTests(unittest.TestCase):
    """Tests for `canarchy config show`."""

    def test_config_show_defaults_json(self) -> None:
        """All-default config returns python-can/socketcan with source=default for every field."""
        with (
            patch("canarchy.transport._load_user_config", return_value={}),
            patch.dict(os.environ, {}, clear=True),
        ):
            exit_code, stdout, _ = run_cli("config", "show", "--json")
        self.assertEqual(exit_code, EXIT_OK)
        payload = json.loads(stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["backend"], "python-can")
        self.assertEqual(payload["data"]["interface"], "socketcan")
        self.assertEqual(payload["data"]["capture_limit"], 2)
        self.assertFalse(payload["data"]["require_active_ack"])
        self.assertIsNone(payload["data"]["j1939_dbc"])
        sources = payload["data"]["sources"]
        self.assertEqual(sources["backend"], "default")
        self.assertEqual(sources["interface"], "default")
        self.assertEqual(sources["capture_limit"], "default")
        self.assertEqual(sources["capture_timeout"], "default")
        self.assertEqual(sources["require_active_ack"], "default")
        self.assertEqual(sources["j1939_dbc"], "default")

    def test_config_show_file_config_overrides_default(self) -> None:
        """Values set in the config file appear with source=file."""
        file_cfg = {
            "CANARCHY_TRANSPORT_BACKEND": "python-can",
            "CANARCHY_PYTHON_CAN_INTERFACE": "udp_multicast",
        }
        with (
            patch("canarchy.transport._load_user_config", return_value=file_cfg),
            patch.dict(os.environ, {}, clear=True),
        ):
            exit_code, stdout, _ = run_cli("config", "show", "--json")
        self.assertEqual(exit_code, EXIT_OK)
        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["backend"], "python-can")
        self.assertEqual(payload["data"]["interface"], "udp_multicast")
        sources = payload["data"]["sources"]
        self.assertEqual(sources["backend"], "file")
        self.assertEqual(sources["interface"], "file")
        # capture_limit and capture_timeout not in file_config → default
        self.assertEqual(sources["capture_limit"], "default")
        self.assertEqual(sources["capture_timeout"], "default")

    def test_config_show_env_var_overrides_file(self) -> None:
        """Environment variables take precedence over the config file."""
        file_cfg = {
            "CANARCHY_TRANSPORT_BACKEND": "python-can",
            "CANARCHY_PYTHON_CAN_INTERFACE": "udp_multicast",
        }
        env_override = {"CANARCHY_TRANSPORT_BACKEND": "scaffold"}
        with (
            patch("canarchy.transport._load_user_config", return_value=file_cfg),
            patch.dict(os.environ, env_override, clear=False),
        ):
            # Remove the key first so patch.dict controls it cleanly
            os.environ.pop("CANARCHY_PYTHON_CAN_INTERFACE", None)
            exit_code, stdout, _ = run_cli("config", "show", "--json")
        self.assertEqual(exit_code, EXIT_OK)
        payload = json.loads(stdout)
        # env var wins for backend
        self.assertEqual(payload["data"]["backend"], "scaffold")
        sources = payload["data"]["sources"]
        self.assertEqual(sources["backend"], "env")
        # interface came from file
        self.assertEqual(sources["interface"], "file")

    def test_config_show_table_output(self) -> None:
        """Table output includes backend, interface, and config-file path."""
        with (
            patch("canarchy.transport._load_user_config", return_value={}),
            patch.dict(os.environ, {}, clear=True),
        ):
            exit_code, stdout, _ = run_cli("config", "show", "--table")
        self.assertEqual(exit_code, EXIT_OK)
        self.assertIn("backend: python-can", stdout)
        self.assertIn("interface: socketcan", stdout)
        self.assertIn("require_active_ack: False", stdout)
        self.assertIn("j1939_dbc: None", stdout)
        self.assertIn("config file:", stdout)

    def test_config_show_config_file_found_false_when_missing(self) -> None:
        """config_file_found is False when the config file does not exist."""
        with (
            patch("canarchy.transport._load_user_config", return_value={}),
            patch("canarchy.transport.Path.home", return_value=Path("/nonexistent/home")),
            patch.dict(os.environ, {}, clear=True),
        ):
            exit_code, stdout, _ = run_cli("config", "show", "--json")
        self.assertEqual(exit_code, EXIT_OK)
        payload = json.loads(stdout)
        self.assertFalse(payload["data"]["config_file_found"])
        self.assertIn("config_file", payload["data"])

    def test_config_show_capture_limit_from_file(self) -> None:
        """capture_limit set in file config shows source=file."""
        file_cfg = {
            "CANARCHY_CAPTURE_LIMIT": "10",
            "CANARCHY_CAPTURE_TIMEOUT": "0.5",
        }
        with (
            patch("canarchy.transport._load_user_config", return_value=file_cfg),
            patch.dict(os.environ, {}, clear=True),
        ):
            exit_code, stdout, _ = run_cli("config", "show", "--json")
        self.assertEqual(exit_code, EXIT_OK)
        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["capture_limit"], 10)
        self.assertAlmostEqual(payload["data"]["capture_timeout"], 0.5)
        sources = payload["data"]["sources"]
        self.assertEqual(sources["capture_limit"], "file")
        self.assertEqual(sources["capture_timeout"], "file")

    def test_config_show_active_ack_from_file(self) -> None:
        file_cfg = {"CANARCHY_REQUIRE_ACTIVE_ACK": "true"}
        with (
            patch("canarchy.transport._load_user_config", return_value=file_cfg),
            patch.dict(os.environ, {}, clear=True),
        ):
            exit_code, stdout, _ = run_cli("config", "show", "--json")

        self.assertEqual(exit_code, EXIT_OK)
        payload = json.loads(stdout)
        self.assertTrue(payload["data"]["require_active_ack"])
        self.assertEqual(payload["data"]["sources"]["require_active_ack"], "file")

    def test_config_show_j1939_dbc_from_file(self) -> None:
        file_cfg = {"CANARCHY_J1939_DBC": "tests/fixtures/j1939_sample.dbc"}
        with (
            patch("canarchy.transport._load_user_config", return_value=file_cfg),
            patch.dict(os.environ, {}, clear=True),
        ):
            exit_code, stdout, _ = run_cli("config", "show", "--json")

        self.assertEqual(exit_code, EXIT_OK)
        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["j1939_dbc"], "tests/fixtures/j1939_sample.dbc")
        self.assertEqual(payload["data"]["sources"]["j1939_dbc"], "file")


if __name__ == "__main__":
    unittest.main()
