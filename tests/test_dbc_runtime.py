from __future__ import annotations

from pathlib import Path
import pytest

from canarchy.dbc import decode_frames, encode_message, inspect_database
from canarchy.dbc_runtime import (
    decode_frames_runtime,
    encode_message_runtime,
    inspect_database_runtime,
    load_runtime_database,
)
from canarchy.transport import LocalTransport


FIXTURES = Path(__file__).parent / "fixtures"


def test_load_runtime_database_reads_sample_fixture() -> None:
    database = load_runtime_database(str(FIXTURES / "sample.dbc"))
    message = database.get_message_by_name("EngineStatus1")
    assert message is not None
    assert message.frame_id == 0x18FEEE31


def test_inspect_database_runtime_returns_normalized_metadata() -> None:
    inspection = inspect_database_runtime(str(FIXTURES / "sample.dbc"))

    payload = inspection.to_payload()
    assert payload["database"]["format"] == "dbc"
    assert payload["database"]["message_count"] == 2
    assert payload["messages"][0]["name"] == "EngineSpeed1"
    assert payload["messages"][1]["signals"][0]["unit"] == "degC"


def test_inspect_database_runtime_filters_to_message() -> None:
    inspection = inspect_database_runtime(str(FIXTURES / "sample.dbc"), message_name="EngineStatus1")

    payload = inspection.to_payload()
    assert payload["message"] == "EngineStatus1"
    assert len(payload["messages"]) == 1
    assert payload["messages"][0]["name"] == "EngineStatus1"


def test_inspect_database_runtime_matches_current_inspection_shape() -> None:
    current_payload, _ = inspect_database(str(FIXTURES / "sample.dbc"))
    runtime_payload = inspect_database_runtime(str(FIXTURES / "sample.dbc")).to_payload()

    assert runtime_payload == current_payload


def test_encode_message_runtime_preserves_message_identity_but_differs_in_payload() -> None:
    signals = {"CoolantTemp": 55, "OilTemp": 65, "Load": 40, "LampState": 1}

    current_frame, current_events = encode_message(str(FIXTURES / "sample.dbc"), "EngineStatus1", signals)
    runtime_frame, runtime_events = encode_message_runtime(
        str(FIXTURES / "sample.dbc"),
        "EngineStatus1",
        signals,
    )

    # cantools and canmatrix do not currently produce identical payload bytes for this fixture,
    # so this test captures the shared command contract while leaving the backend difference explicit.
    assert runtime_frame.arbitration_id == current_frame.arbitration_id
    assert runtime_frame.is_extended_id == current_frame.is_extended_id
    assert runtime_frame.dlc == current_frame.dlc
    assert runtime_frame.data.hex() != current_frame.data.hex()
    assert runtime_events[0]["payload"]["frame"]["arbitration_id"] == current_events[0]["payload"]["frame"]["arbitration_id"]


def test_decode_frames_runtime_matches_current_decode_result_with_float_tolerance() -> None:
    frames = LocalTransport().frames_from_file(str(FIXTURES / "sample.candump"))

    current_events = decode_frames(frames, str(FIXTURES / "sample.dbc"))
    runtime_events = decode_frames_runtime(frames, str(FIXTURES / "sample.dbc"))

    assert len(runtime_events) == len(current_events)
    for runtime_event, current_event in zip(runtime_events, current_events, strict=True):
        assert runtime_event["event_type"] == current_event["event_type"]
        assert runtime_event["source"] == current_event["source"]
        assert runtime_event["timestamp"] == current_event["timestamp"]
        if runtime_event["event_type"] == "decoded_message":
            assert runtime_event["payload"]["frame"] == current_event["payload"]["frame"]
            assert runtime_event["payload"]["message_name"] == current_event["payload"]["message_name"]
            for signal_name, runtime_value in runtime_event["payload"]["signals"].items():
                assert runtime_value == pytest.approx(current_event["payload"]["signals"][signal_name])
        else:
            assert runtime_event["payload"]["message_name"] == current_event["payload"]["message_name"]
            assert runtime_event["payload"]["signal_name"] == current_event["payload"]["signal_name"]
            assert (runtime_event["payload"]["units"] or "") == (current_event["payload"]["units"] or "")
            assert runtime_event["payload"]["value"] == pytest.approx(current_event["payload"]["value"])
