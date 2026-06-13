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

    current_frame, current_events, _ = encode_message(
        str(FIXTURES / "sample.dbc"), "EngineStatus1", signals
    )
    runtime_frame, runtime_events, _ = encode_message_runtime(
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

    current_frame, _, _ = encode_message(str(FIXTURES / "complex.dbc"), "EngineStatus1", signals)
    runtime_frame, _, _ = encode_message_runtime(
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


_CHECKSUM_DBC = str(FIXTURES / "checksum_sample.dbc")


def test_encode_auto_checksum_sets_valid_crc_on_short_message() -> None:
    frame, _, _ = encode_message_runtime(
        _CHECKSUM_DBC,
        "TestButtons",
        {"Button1": 1, "Button2": 0, "Button3": 1, "COUNTER": 0},
    )
    assert frame.dlc == 3
    assert len(frame.data) == 3

    from canarchy.checksum import chrysler_message_checksum

    checksum_byte = frame.data[2]
    expected = chrysler_message_checksum(bytes(frame.data))
    assert checksum_byte == expected


def test_encode_auto_checksum_sets_valid_crc_on_long_message() -> None:
    frame, _, _ = encode_message_runtime(
        _CHECKSUM_DBC,
        "TestSensor",
        {"Value": 12345, "STATUS": 7, "COUNTER": 0},
    )
    assert frame.dlc == 8
    assert len(frame.data) == 8

    from canarchy.checksum import chrysler_message_checksum

    checksum_byte = frame.data[7]
    expected = chrysler_message_checksum(bytes(frame.data))
    assert checksum_byte == expected


def test_encode_auto_checksum_respects_explicit_checksum() -> None:
    frame, _, _ = encode_message_runtime(
        _CHECKSUM_DBC,
        "TestButtons",
        {"Button1": 1, "Button2": 0, "Button3": 1, "COUNTER": 0, "CHECKSUM": 0xAB},
    )
    assert frame.data[2] == 0xAB


def test_encode_auto_checksum_coverage_for_no_checksum_signal() -> None:
    frame, _, _ = encode_message_runtime(
        str(FIXTURES / "sample.dbc"),
        "EngineStatus1",
        {"CoolantTemp": 55, "OilTemp": 65, "Load": 40, "LampState": 1},
    )
    assert frame.dlc == 4


# --- decode -> encode round-trip and name resolution (#413) ------------------

_J1939_DBC = str(FIXTURES / "j1939_sample.dbc")


def test_encode_resolves_sae_pgn_label_and_signal_name() -> None:
    """The issue's exact example: encode EEC1 "Engine Speed=1200"."""
    frame, _, resolution = encode_message_runtime(_J1939_DBC, "EEC1", {"Engine Speed": 1200})

    assert frame.arbitration_id == 0x18F00431
    assert resolution["message"] == {
        "requested": "EEC1",
        "resolved": "EngineSpeed1",
        "via": "pgn_label",
        "pgn": 61444,
    }
    assert resolution["signal_aliases"] == [
        {"requested": "Engine Speed", "resolved": "EngineSpeed", "via": "normalized"}
    ]
    # 1200 rpm / 0.125 = 9600 = 0x2580, little-endian at byte 1.
    assert frame.data[1:3] == bytes([0x80, 0x25])


def test_encode_resolves_spn_catalog_name() -> None:
    """SPN 110's SAE name differs from the DBC name: spn_name resolution."""
    frame, _, resolution = encode_message_runtime(
        _J1939_DBC, "EngineTemperature1", {"Engine Coolant Temperature": 85}
    )

    assert resolution["signal_aliases"] == [
        {
            "requested": "Engine Coolant Temperature",
            "resolved": "EngineCoolantTemp",
            "via": "spn_name",
        }
    ]
    assert frame.data[0] == 125  # 85 degC with -40 offset


def test_encode_decode_round_trip_by_displayed_names() -> None:
    """A decoded frame re-encodes byte-identically via its displayed names."""
    original, _, _ = encode_message_runtime(
        _J1939_DBC,
        "EngineSpeed1",
        {"Reserved": 7, "EngineSpeed": 1872.5, "TorqueMode": 3},
    )
    decoded_events = decode_frames_runtime([original], _J1939_DBC)
    signal_values = {
        event["payload"]["signal_name"]: event["payload"]["value"]
        for event in decoded_events
        if event["event_type"] == "signal"
    }
    assert signal_values["EngineSpeed"] == 1872.5

    round_tripped, _, resolution = encode_message_runtime(_J1939_DBC, "EEC1", signal_values)

    assert round_tripped.data == original.data
    assert round_tripped.arbitration_id == original.arbitration_id
    assert resolution["filled_signals"] == []


def test_encode_fills_unsupplied_signals_and_reports_them() -> None:
    frame, _, resolution = encode_message_runtime(_J1939_DBC, "EngineSpeed1", {"EngineSpeed": 1200})

    filled = {entry["signal"] for entry in resolution["filled_signals"]}
    assert filled == {"Reserved", "TorqueMode"}
    assert frame.data[0] == 0 and frame.data[3] == 0


def test_encode_pgn_label_tie_break_by_signal_names() -> None:
    """Two fixture messages share PGN 61444; the signals disambiguate."""
    from canarchy.dbc import DbcError

    frame, _, resolution = encode_message_runtime(_J1939_DBC, "EEC1", {"NibbleSignal": 5})
    assert resolution["message"]["resolved"] == "EngineBitfield1"

    # Without signals to break the tie the ambiguity is a structured error.
    try:
        encode_message_runtime(_J1939_DBC, "EEC1", {})
    except DbcError as exc:
        assert exc.code == "DBC_MESSAGE_NOT_FOUND"
        assert set(exc.detail["candidates"]) == {"EngineSpeed1", "EngineBitfield1"}
    else:
        raise AssertionError("ambiguous PGN label should raise")


def test_encode_unknown_names_suggest_close_matches() -> None:
    from canarchy.dbc import DbcError

    try:
        encode_message_runtime(_J1939_DBC, "EngineSpede1", {})
    except DbcError as exc:
        assert exc.code == "DBC_MESSAGE_NOT_FOUND"
        assert "EngineSpeed1" in (exc.detail or {}).get("suggestions", [])
    else:
        raise AssertionError("unknown message should raise")

    try:
        encode_message_runtime(_J1939_DBC, "EngineSpeed1", {"EngineSped": 100})
    except DbcError as exc:
        assert exc.code == "DBC_SIGNAL_INVALID"
        assert "EngineSpeed" in exc.detail["suggestions"]
    else:
        raise AssertionError("unknown signal should raise")


def test_encode_exact_names_keep_exact_resolution() -> None:
    _, _, resolution = encode_message_runtime(
        _J1939_DBC,
        "EngineSpeed1",
        {"Reserved": 0, "EngineSpeed": 1200, "TorqueMode": 0},
    )
    assert resolution["message"]["via"] == "exact"
    assert resolution["signal_aliases"] == []
    assert resolution["filled_signals"] == []
