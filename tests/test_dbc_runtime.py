from __future__ import annotations

from pathlib import Path

from canarchy.dbc import decode_frames, encode_message, inspect_database
from canarchy.dbc_runtime import (
    decode_frames_runtime,
    decode_j1939_spn_runtime,
    encode_message_runtime,
    inspect_database_runtime,
    load_runtime_database,
)
from canarchy.models import CanFrame
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
    inspection = inspect_database_runtime(
        str(FIXTURES / "sample.dbc"), message_name="EngineStatus1"
    )

    payload = inspection.to_payload()
    assert payload["message"] == "EngineStatus1"
    assert len(payload["messages"]) == 1
    assert payload["messages"][0]["name"] == "EngineStatus1"


def test_inspect_database_runtime_matches_current_inspection_shape() -> None:
    current_payload, _ = inspect_database(str(FIXTURES / "sample.dbc"))
    runtime_payload = inspect_database_runtime(str(FIXTURES / "sample.dbc")).to_payload()

    assert runtime_payload == current_payload


def test_encode_message_runtime_parity_with_primary_encode() -> None:
    signals = {"CoolantTemp": 55, "OilTemp": 65, "Load": 40, "LampState": 1}

    current_frame, current_events = encode_message(
        str(FIXTURES / "sample.dbc"), "EngineStatus1", signals
    )
    runtime_frame, runtime_events = encode_message_runtime(
        str(FIXTURES / "sample.dbc"),
        "EngineStatus1",
        signals,
    )

    # Both encode_message and encode_message_runtime now use cantools internally,
    # so they produce identical results.
    assert runtime_frame.arbitration_id == current_frame.arbitration_id
    assert runtime_frame.is_extended_id == current_frame.is_extended_id
    assert runtime_frame.dlc == current_frame.dlc
    assert runtime_frame.data.hex() == current_frame.data.hex()
    assert (
        runtime_events[0]["payload"]["frame"]["arbitration_id"]
        == current_events[0]["payload"]["frame"]["arbitration_id"]
    )


def test_decode_frames_runtime_parity_with_primary_decode() -> None:
    frames = LocalTransport().frames_from_file(str(FIXTURES / "sample.candump"))

    current_events = decode_frames(frames, str(FIXTURES / "sample.dbc"))
    runtime_events = decode_frames_runtime(frames, str(FIXTURES / "sample.dbc"))

    # Both decode_frames and decode_frames_runtime now use cantools internally,
    # so they produce identical results.
    assert len(runtime_events) == len(current_events)
    for runtime_event, current_event in zip(runtime_events, current_events, strict=True):
        assert runtime_event == current_event


def test_complex_dbc_fixture_loads_both_backends() -> None:
    current_payload, _ = inspect_database(str(FIXTURES / "complex.dbc"))
    runtime_payload = inspect_database_runtime(str(FIXTURES / "complex.dbc")).to_payload()

    assert (
        current_payload["database"]["message_count"]
        == runtime_payload["database"]["message_count"]
        == 15
    )


def test_complex_dbc_fixture_decode_parity() -> None:
    frames = LocalTransport().frames_from_file(str(FIXTURES / "complex.candump"))

    current_events = decode_frames(frames, str(FIXTURES / "complex.dbc"))
    runtime_events = decode_frames_runtime(frames, str(FIXTURES / "complex.dbc"))

    assert len(current_events) == len(runtime_events) == 68
    for ce, re in zip(current_events, runtime_events, strict=True):
        if ce["event_type"] == "decoded_message":
            assert ce["payload"]["message_name"] == re["payload"]["message_name"]


def test_complex_dbc_fixture_encode_preserves_message_identity() -> None:
    signals = {"CoolantTemp": 55, "OilTemp": 65, "Load": 40, "LampState": 1}

    current_frame, _ = encode_message(str(FIXTURES / "complex.dbc"), "EngineStatus1", signals)
    runtime_frame, _ = encode_message_runtime(
        str(FIXTURES / "complex.dbc"),
        "EngineStatus1",
        signals,
    )

    assert current_frame.arbitration_id == runtime_frame.arbitration_id
    assert current_frame.dlc == runtime_frame.dlc


def test_decode_j1939_spn_runtime_error_value_returns_none() -> None:
    # j1939_sample.dbc: SPN 175 = EngineOilTemp, signal at bit 8, length 8, (1,-40) degC
    # 0xFF at byte 1 is the J1939 not-available indicator for an 8-bit signal
    frame = CanFrame(
        arbitration_id=0x18FEEE31,
        data=bytes([0x00, 0xFF, 0x00, 0x00]),
        timestamp=0.0,
        is_extended_id=True,
    )
    obs = decode_j1939_spn_runtime([frame], str(FIXTURES / "j1939_sample.dbc"), 175)
    assert len(obs) == 1
    assert obs[0]["value"] is None


def test_decode_j1939_spn_runtime_valid_value_returns_scaled_result() -> None:
    # j1939_sample.dbc: SPN 175 = EngineOilTemp, signal at bit 8, length 8, (1,-40) degC
    # raw 0x8C = 140 -> value = 140 * 1 + (-40) = 100.0 degC
    frame = CanFrame(
        arbitration_id=0x18FEEE31,
        data=bytes([0x00, 0x8C, 0x00, 0x00]),
        timestamp=0.0,
        is_extended_id=True,
    )
    obs = decode_j1939_spn_runtime([frame], str(FIXTURES / "j1939_sample.dbc"), 175)
    assert len(obs) == 1
    assert obs[0]["value"] == 100.0
