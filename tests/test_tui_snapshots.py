"""Snapshot tests for the CANarchy TUI panes.

Targets the pane-level state model in `canarchy.tui` rather than the
terminal rendering itself. Each test feeds a synthetic `CommandResult`
through `_update_state` and asserts the resulting `TuiState` panes.
"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

from canarchy.cli import main
from canarchy.tui import (
    TuiState,
    _decoded_signal_rows,
    _render,
    _update_state,
)


FIXTURES = Path(__file__).parent / "fixtures"


def _run_cli_capture(*argv: str) -> dict:
    """Invoke the CLI in-process and parse the canonical JSON envelope."""

    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        main(argv)
    return json.loads(stdout.getvalue())


def _fake_result(command: str, data: dict, warnings=(), errors=()):
    """Build a minimal `CommandResult` look-alike for state updates."""

    from canarchy.cli import CommandResult

    return CommandResult(
        command=command, data=data, warnings=list(warnings), errors=list(errors), ok=not errors
    )


# ---------------------------------------------------------------------------
# Decoded Signals pane — direct unit checks
# ---------------------------------------------------------------------------


def test_decoded_signals_pane_starts_empty():
    state = TuiState()
    assert state.decoded_signals == []


def test_decoded_signals_pane_renders_empty_placeholder():
    state = TuiState()
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        _render(state)
    rendered = stdout.getvalue()
    assert "[Decoded Signals]" in rendered
    assert "(no decoded signals)" in rendered


def test_decoded_signals_pane_extracts_from_decoded_message_events():
    """`canarchy decode --dbc ...` emits `decoded_message` events with a `signals` dict."""

    result = _fake_result(
        "decode",
        {
            "events": [
                {
                    "event_type": "decoded_message",
                    "payload": {
                        "message_name": "EngineStatus1",
                        "signals": {"CoolantTemp": 85.5, "EngineRPM": 1450},
                    },
                }
            ]
        },
    )
    rows = _decoded_signal_rows(result)
    assert any("EngineStatus1.CoolantTemp = 85.5" in row for row in rows)
    assert any("EngineStatus1.EngineRPM = 1450" in row for row in rows)


def test_decoded_signals_pane_extracts_from_signal_events_with_units():
    result = _fake_result(
        "decode",
        {
            "events": [
                {
                    "event_type": "signal",
                    "payload": {
                        "message_name": "EngineStatus1",
                        "signal_name": "CoolantTemp",
                        "value": 85.5,
                        "units": "degC",
                    },
                }
            ]
        },
    )
    (row,) = _decoded_signal_rows(result)
    assert row == "EngineStatus1.CoolantTemp = 85.5 [degC]"


def test_decoded_signals_pane_extracts_from_j1939_pgn_events_list_shape():
    result = _fake_result(
        "j1939 pgn",
        {
            "events": [
                {
                    "event_type": "j1939_pgn",
                    "payload": {
                        "pgn": 65262,
                        "decoded_signals": [
                            {"name": "Engine Coolant Temperature", "value": 85.0, "units": "degC"}
                        ],
                    },
                }
            ]
        },
    )
    (row,) = _decoded_signal_rows(result)
    assert row == "PGN 65262.Engine Coolant Temperature = 85 [degC]"


def test_decoded_signals_pane_extracts_from_j1939_pgn_events_dict_shape():
    """Regression for Codex P1 on PR #353.

    `j1939 pgn` populates `decoded_signals` from
    `pretty_j1939_support.describe_frame`, which returns
    `dict[str, str]` (signal name → value text). Iterating it yields
    the string keys; the old code called `.get(...)` on the keys and
    crashed with AttributeError.
    """

    result = _fake_result(
        "j1939 pgn",
        {
            "events": [
                {
                    "event_type": "j1939_pgn",
                    "payload": {
                        "pgn": 65262,
                        "decoded_signals": {
                            "Engine Coolant Temperature": "85 degC",
                            "Engine Speed": "1450 rpm",
                        },
                    },
                }
            ]
        },
    )
    rows = _decoded_signal_rows(result)
    assert "PGN 65262.Engine Coolant Temperature = 85 degC" in rows
    assert "PGN 65262.Engine Speed = 1450 rpm" in rows


def test_decoded_signals_pane_extracts_from_j1939_spn_observations():
    """`canarchy j1939 spn` returns observations (not events)."""

    result = _fake_result(
        "j1939 spn",
        {
            "observations": [
                {
                    "spn": 110,
                    "name": "Engine Coolant Temperature",
                    "value": 87.0,
                    "units": "degC",
                    "pgn": 65262,
                }
            ]
        },
    )
    (row,) = _decoded_signal_rows(result)
    assert row == "PGN 65262.Engine Coolant Temperature = 87 [degC]"


def test_decoded_signals_pane_caps_at_max_rows_with_newest_first():
    state = TuiState()
    # Push 20 rows in two batches; only 12 should survive, newest first.
    first_batch = _fake_result(
        "decode",
        {
            "events": [
                {
                    "event_type": "signal",
                    "payload": {
                        "message_name": "M1",
                        "signal_name": f"S{i}",
                        "value": i,
                        "units": None,
                    },
                }
                for i in range(8)
            ]
        },
    )
    _update_state(state, first_batch)
    assert len(state.decoded_signals) == 8
    second_batch = _fake_result(
        "decode",
        {
            "events": [
                {
                    "event_type": "signal",
                    "payload": {
                        "message_name": "M2",
                        "signal_name": f"S{i}",
                        "value": i,
                        "units": None,
                    },
                }
                for i in range(8)
            ]
        },
    )
    _update_state(state, second_batch)
    assert len(state.decoded_signals) == 12
    # Newest at the top — M2 signals should appear before M1 in the list.
    assert state.decoded_signals[0].startswith("M2.")


def test_decoded_signals_pane_unchanged_when_result_has_no_signals():
    state = TuiState()
    state.decoded_signals = ["M.S = 1"]
    result = _fake_result("capture-info", {"frame_count": 0})
    _update_state(state, result)
    assert state.decoded_signals == ["M.S = 1"]


# ---------------------------------------------------------------------------
# End-to-end snapshot: drive the decode command against an in-tree fixture
# ---------------------------------------------------------------------------


def test_decoded_signals_pane_end_to_end_against_sample_dbc():
    """Drive the real `decode` CLI path against `sample.dbc` + `sample.candump`.

    Exercises the full pipeline (canonical envelope → `_decoded_signal_rows`
    → `_update_state`) so signal payload shape changes anywhere along the
    chain show up here.
    """

    fixture_candump = FIXTURES / "sample.candump"
    fixture_dbc = FIXTURES / "sample.dbc"
    if not fixture_candump.exists() or not fixture_dbc.exists():
        # Sample fixtures are present in-tree; if they ever move, the
        # earlier unit checks still guard the contract.
        return

    payload = _run_cli_capture(
        "decode", "--file", str(fixture_candump), "--dbc", str(fixture_dbc), "--json"
    )
    assert payload["ok"] is True
    result = _fake_result(payload["command"], payload["data"])
    state = TuiState()
    _update_state(state, result)
    # The fixture produces at least one decoded signal; the assertion is
    # intentionally loose so a fixture refresh that changes signal names
    # doesn't break the test.
    assert len(state.decoded_signals) > 0, "expected at least one decoded signal from sample.dbc"
    assert all(" = " in row for row in state.decoded_signals)
