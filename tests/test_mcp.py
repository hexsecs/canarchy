from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from canarchy.mcp_server import _TOOL_NAMES, _TOOLS, _build_argv, handle_call_tool, handle_list_tools, run_server


FIXTURES = Path(__file__).parent / "fixtures"

_EXPECTED_TOOLS = {
    "capture", "send", "generate", "gateway", "replay", "filter", "stats",
    "decode", "encode", "dbc_inspect", "export",
    "session_save", "session_load", "session_show",
    "j1939_monitor", "j1939_decode", "j1939_pgn", "j1939_spn", "j1939_tp", "j1939_dm1",
    "uds_scan", "uds_trace", "uds_services",
    "config_show",
}


# --- TEST-MCP-01: server entry point is callable ---------------------------

def test_run_server_is_callable():
    assert callable(run_server)


# --- TEST-MCP-02 / TEST-MCP-03: tool discovery -----------------------------

def test_list_tools_returns_expected_names():
    tools = asyncio.run(handle_list_tools())
    names = {tool.name for tool in tools}
    assert _EXPECTED_TOOLS <= names


def test_list_tools_count():
    tools = asyncio.run(handle_list_tools())
    assert len(tools) >= 24


# --- TEST-MCP-04: tool metadata validity -----------------------------------

def test_each_tool_has_description_and_schema():
    tools = asyncio.run(handle_list_tools())
    for tool in tools:
        assert tool.description, f"Tool {tool.name!r} has no description"
        assert isinstance(tool.inputSchema, dict), f"Tool {tool.name!r} inputSchema is not a dict"
        assert "type" in tool.inputSchema, f"Tool {tool.name!r} inputSchema missing 'type'"


# --- TEST-MCP-05: config_show returns structured result --------------------

def test_call_tool_config_show():
    results = asyncio.run(handle_call_tool("config_show", {}))
    assert len(results) == 1
    payload = json.loads(results[0].text)
    assert payload["ok"] is True
    assert payload["command"] == "config show"
    assert "backend" in payload["data"]


# --- TEST-MCP-06: uds_services returns catalogue ---------------------------

def test_call_tool_uds_services():
    results = asyncio.run(handle_call_tool("uds_services", {}))
    assert len(results) == 1
    payload = json.loads(results[0].text)
    assert payload["ok"] is True
    assert payload["data"]["service_count"] > 0


# --- TEST-MCP-07: invalid frame_id returns structured error ----------------

def test_call_tool_send_invalid_frame_id():
    results = asyncio.run(
        handle_call_tool("send", {"interface": "can0", "frame_id": "not_hex", "data": "1122"})
    )
    payload = json.loads(results[0].text)
    assert payload["ok"] is False
    assert any(e["code"] == "INVALID_FRAME_ID" for e in payload["errors"])


# --- TEST-MCP-08: invalid rate returns structured error --------------------

def test_call_tool_replay_invalid_rate():
    results = asyncio.run(
        handle_call_tool("replay", {"file": "any.candump", "rate": 0.0})
    )
    payload = json.loads(results[0].text)
    assert payload["ok"] is False
    assert any(e["code"] == "INVALID_RATE" for e in payload["errors"])


# --- TEST-MCP-09: unknown tool name raises ValueError ----------------------

def test_call_tool_unknown_raises():
    with pytest.raises(ValueError, match="Unknown tool"):
        asyncio.run(handle_call_tool("nonexistent_tool", {}))


# --- TEST-MCP-10: mcp dependency in pyproject.toml ------------------------

def test_mcp_dependency_declared():
    pyproject = (Path(__file__).parent.parent / "pyproject.toml").read_text()
    assert "mcp>=" in pyproject or 'mcp"' in pyproject or "mcp =" in pyproject


# --- TEST-MCP-11: shell and tui are not MCP tools -------------------------

def test_shell_and_tui_not_exposed():
    names = {tool.name for tool in asyncio.run(handle_list_tools())}
    assert "shell" not in names
    assert "tui" not in names


# --- TEST-MCP-12: _build_argv produces correct argv -----------------------

def test_build_argv_capture():
    argv = _build_argv("capture", {"interface": "can0"})
    assert argv == ["capture", "can0", "--json"]


def test_build_argv_j1939_monitor_with_pgn():
    argv = _build_argv("j1939_monitor", {"interface": "can0", "pgn": 60160})
    assert argv[:3] == ["j1939", "monitor", "can0"]
    assert "--pgn" in argv
    assert "60160" in argv
    assert argv[-1] == "--json"


def test_build_argv_encode_with_signals():
    argv = _build_argv("encode", {"dbc": "test.dbc", "message": "EngineData", "signals": ["RPM=1000"]})
    assert "--dbc" in argv
    assert "test.dbc" in argv
    assert "EngineData" in argv
    assert "RPM=1000" in argv
    assert argv[-1] == "--json"


def test_build_argv_dbc_inspect_with_options():
    argv = _build_argv(
        "dbc_inspect",
        {"dbc": "test.dbc", "message": "EngineData", "signals_only": True},
    )
    assert argv[:3] == ["dbc", "inspect", "test.dbc"]
    assert "--message" in argv
    assert "EngineData" in argv
    assert "--signals-only" in argv
    assert argv[-1] == "--json"


def test_build_argv_j1939_pgn():
    argv = _build_argv("j1939_pgn", {"pgn": 61444, "file": "trace.candump"})
    assert argv[:2] == ["j1939", "pgn"]
    assert "61444" in argv
    assert "--file" in argv
    assert "trace.candump" in argv
    assert argv[-1] == "--json"


def test_build_argv_session_save_with_options():
    argv = _build_argv("session_save", {"name": "my-session", "interface": "can0", "dbc": "db.dbc"})
    assert argv[:3] == ["session", "save", "my-session"]
    assert "--interface" in argv
    assert "can0" in argv
    assert "--dbc" in argv
    assert "db.dbc" in argv
    assert argv[-1] == "--json"


def test_build_argv_generate_with_options():
    argv = _build_argv("generate", {"interface": "can0", "count": 5, "extended": True})
    assert "generate" in argv
    assert "can0" in argv
    assert "--count" in argv
    assert "5" in argv
    assert "--extended" in argv
    assert argv[-1] == "--json"


# --- TEST-MCP-13: _build_argv raises for unknown tool ---------------------

def test_build_argv_unknown_raises():
    with pytest.raises(ValueError, match="Unknown tool"):
        _build_argv("bad_tool", {})


# --- end-to-end: j1939_monitor returns structured events ------------------

def test_call_tool_j1939_monitor_returns_events():
    results = asyncio.run(handle_call_tool("j1939_monitor", {}))
    payload = json.loads(results[0].text)
    assert payload["ok"] is True
    assert "events" in payload["data"]


# --- end-to-end: tool names in _TOOL_NAMES set match _TOOLS list ----------

def test_tool_names_set_matches_tools_list():
    assert _TOOL_NAMES == {tool.name for tool in _TOOLS}
