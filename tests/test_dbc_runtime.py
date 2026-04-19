from __future__ import annotations

from pathlib import Path

from canarchy.dbc import inspect_database
from canarchy.dbc_runtime import inspect_database_runtime, load_runtime_database


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

    assert runtime_payload["database"] == current_payload["database"]
    assert runtime_payload["messages"][0]["name"] == current_payload["messages"][0]["name"]
    assert runtime_payload["messages"][1]["signals"][0]["unit"] == current_payload["messages"][1]["signals"][0]["unit"]
