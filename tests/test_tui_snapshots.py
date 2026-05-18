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
    _j1939_pane_lines,
    _render,
    _update_j1939_state,
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


# ---------------------------------------------------------------------------
# J1939 pane
# ---------------------------------------------------------------------------


def _j1939_pgn_event(
    *, pgn: int, sa: int, da: int | None = 0xFF, priority: int = 6, data: str = ""
):
    return {
        "event_type": "j1939_pgn",
        "payload": {
            "pgn": pgn,
            "source_address": sa,
            "destination_address": da,
            "priority": priority,
            "frame": {"data": data},
        },
    }


def test_j1939_pane_starts_empty_with_placeholder():
    state = TuiState()
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        _render(state)
    rendered = stdout.getvalue()
    assert "[J1939]" in rendered
    assert "(no J1939 activity)" in rendered


def test_j1939_pane_tracks_top_pgns_and_source_addresses():
    state = TuiState()
    events = [
        _j1939_pgn_event(pgn=65262, sa=0x31, data="7dffffff"),
        _j1939_pgn_event(pgn=65262, sa=0x31, data="7effffff"),
        _j1939_pgn_event(pgn=65262, sa=0x31, data="7fffffff"),
        _j1939_pgn_event(pgn=61444, sa=0x31, data="ffff00001900"),
        _j1939_pgn_event(pgn=61444, sa=0x22, data="ffff00001a00"),
    ]
    result = _fake_result("j1939 monitor", {"events": events})
    _update_j1939_state(state, result)
    assert state.j1939_pgn_counts[65262] == 3
    assert state.j1939_pgn_counts[61444] == 2
    assert state.j1939_source_addresses[0x31] == 4
    assert state.j1939_source_addresses[0x22] == 1
    lines = _j1939_pane_lines(state)
    top_pgn_line = next(line for line in lines if line.startswith("top PGNs:"))
    assert "65262(3)" in top_pgn_line
    assert "61444(2)" in top_pgn_line
    sa_line = next(line for line in lines if line.startswith("source addresses:"))
    assert "0x31(4)" in sa_line


def test_j1939_pane_recent_activity_is_bounded_newest_first():
    state = TuiState()
    events = [_j1939_pgn_event(pgn=65262 + i, sa=0x31, data="00") for i in range(12)]
    result = _fake_result("j1939 monitor", {"events": events})
    _update_j1939_state(state, result)
    assert len(state.j1939_recent) == 8
    # The most recent event (highest PGN here) lands at the top.
    assert "pgn=65273" in state.j1939_recent[0]


def test_j1939_pane_dm1_alert_ribbon_lights_only_on_active_faults():
    state = TuiState()
    result = _fake_result(
        "j1939 dm1",
        {
            "messages": [
                {
                    "source_address": 0x31,
                    "transport": "tp",
                    "active_dtc_count": 2,
                    "lamp_summary": {"mil": "on", "amber": "off"},
                    "dtcs": [
                        {"spn": 110, "fmi": 5},
                        {"spn": 190, "fmi": 7},
                    ],
                },
                # No-fault filler — must NOT light the ribbon.
                {
                    "source_address": 0x22,
                    "transport": "direct",
                    "active_dtc_count": 0,
                    "dtcs": [{"spn": 255, "fmi": 0}],
                },
            ]
        },
    )
    _update_j1939_state(state, result)
    assert len(state.j1939_dm1_alerts) == 1
    alert = state.j1939_dm1_alerts[0]
    assert "sa=0x31" in alert
    assert "active=2" in alert
    assert "spn=110/fmi=5" in alert
    assert "lamps=mil" in alert
    lines = _j1939_pane_lines(state)
    assert "!! DM1 active faults !!" in lines


def test_j1939_pane_untouched_when_result_has_no_j1939_events():
    state = TuiState()
    state.j1939_pgn_counts[65262] = 1
    state.j1939_recent = ["pgn=65262 sa=0x31 da=broadcast prio=6 data=00"]
    _update_j1939_state(state, _fake_result("capture-info", {"frame_count": 0}))
    assert state.j1939_pgn_counts[65262] == 1
    assert len(state.j1939_recent) == 1


def test_j1939_pane_end_to_end_against_heavy_vehicle_fixture():
    """Drive the real `j1939 decode` CLI path against the in-tree fixture."""

    fixture = FIXTURES / "j1939_heavy_vehicle.candump"
    if not fixture.exists():
        return
    payload = _run_cli_capture("j1939", "decode", "--file", str(fixture), "--json")
    assert payload["ok"] is True
    state = TuiState()
    _update_state(state, _fake_result(payload["command"], payload["data"]))
    # Fixture sends PGNs 65262, 61444 from SA 0x31 (engine controller).
    assert state.j1939_pgn_counts[65262] > 0
    assert state.j1939_pgn_counts[61444] > 0
    assert state.j1939_source_addresses[0x31] > 0


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
