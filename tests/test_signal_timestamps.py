"""Regression coverage for independent DBC signal time series (#525)."""

import asyncio
import contextlib
import io
import json
from dataclasses import replace
from pathlib import Path

import pytest

from canarchy.cli import main
from canarchy.dbc import decode_frames
from canarchy.mcp_server import handle_call_tool
from canarchy.models import FrameEvent
from canarchy.transport import LocalTransport

FIXTURES = Path(__file__).parent / "fixtures"
DBC = str(FIXTURES / "sample.dbc")


def repeated_frames(timestamps):
    frame = LocalTransport().frames_from_file(str(FIXTURES / "sample.candump"))[0]
    return [replace(frame, timestamp=timestamp) for timestamp in timestamps]


def assert_signal_series(events, timestamps):
    # Deliberately ignore all parent events: each signal is independently usable.
    signals = [event for event in events if event["event_type"] == "signal"]
    series = [event for event in signals if event["payload"]["signal_name"] == "CoolantTemp"]
    assert [event["timestamp"] for event in series] == timestamps
    assert [event["payload"]["frame_index"] for event in series] == list(range(len(timestamps)))
    assert len({event["payload"]["value"] for event in series}) == 1
    assert len(signals) == 4 * len(timestamps)
    for event in signals:
        assert event["timestamp"] == timestamps[event["payload"]["frame_index"]]


def test_core_preserves_zero_distinct_and_unknown_source_timestamps():
    timestamps = [0.0, 1.25, None]
    assert_signal_series(decode_frames(repeated_frames(timestamps), DBC), timestamps)


@pytest.mark.parametrize("output", ["--json", "--jsonl"])
def test_stdin_signal_series_preserves_source_timestamps(monkeypatch, output):
    timestamps = [0.0, 1.25, None]
    stdin = (
        "\n".join(
            json.dumps(FrameEvent(frame=frame).to_event().to_payload())
            for frame in repeated_frames(timestamps)
        )
        + "\n"
    )
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        assert main(["decode", "--stdin", "--dbc", DBC, output]) == 0
    if output == "--json":
        events = json.loads(stdout.getvalue())["data"]["events"]
    else:
        events = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert_signal_series(events, timestamps)


@pytest.fixture
def repeated_capture(tmp_path):
    path = tmp_path / "repeated.candump"
    path.write_text("(0.000000) can0 18FEEE31#11223344\n(1.250000) can0 18FEEE31#11223344\n")
    return str(path)


def test_file_decode_preserves_repeated_signal_timestamps(repeated_capture):
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        assert main(["decode", "--file", repeated_capture, "--dbc", DBC, "--json"]) == 0
    assert_signal_series(json.loads(stdout.getvalue())["data"]["events"], [0.0, 1.25])


def test_mcp_decode_preserves_repeated_signal_timestamps(repeated_capture):
    result = asyncio.run(handle_call_tool("decode", {"file": repeated_capture, "dbc": DBC}))
    payload = json.loads(result.content[0].text)
    assert payload["ok"] is True
    assert_signal_series(payload["data"]["events"], [0.0, 1.25])
