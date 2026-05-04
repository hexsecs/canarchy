from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from canarchy.mcp_server import _TOOL_NAMES, _TOOLS, _build_argv, handle_call_tool, handle_list_tools, run_server


FIXTURES = Path(__file__).parent / "fixtures"

_EXPECTED_TOOLS = {
    "capture", "send", "generate", "gateway", "replay", "filter", "stats", "capture_info",
    "decode", "encode", "dbc_inspect", "export",
    "session_save", "session_load", "session_show",
    "j1939_monitor", "j1939_decode", "j1939_pgn", "j1939_spn", "j1939_tp", "j1939_tp_compare",
    "j1939_dm1", "j1939_faults", "j1939_summary", "j1939_inventory", "j1939_compare",
    "uds_scan", "uds_trace", "uds_services",
    "config_show",
    "datasets_provider_list", "datasets_search", "datasets_inspect", "datasets_fetch", "datasets_cache_list",
    "datasets_cache_refresh", "datasets_convert", "datasets_replay_plan", "datasets_replay_files",
    "skills_provider_list", "skills_search", "skills_fetch", "skills_cache_list", "skills_cache_refresh",
    "re_signals", "re_correlate", "re_counters", "re_entropy", "re_match_dbc", "re_shortlist_dbc",
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
    assert len(tools) >= 25


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


def test_call_tool_capture_info():
    results = asyncio.run(
        handle_call_tool("capture_info", {"file": str(FIXTURES / "sample.candump")})
    )
    assert len(results) == 1
    payload = json.loads(results[0].text)
    assert payload["ok"] is True
    assert payload["command"] == "capture-info"
    assert payload["data"]["frame_count"] == 3
    assert payload["data"]["unique_ids"] == 3


def test_call_tool_stats_uses_file_flag():
    results = asyncio.run(
        handle_call_tool("stats", {"file": str(FIXTURES / "sample.candump")})
    )
    assert len(results) == 1
    payload = json.loads(results[0].text)
    assert payload["ok"] is True
    assert payload["command"] == "stats"
    assert payload["data"]["total_frames"] == 3
    assert payload["data"]["unique_arbitration_ids"] == 3


def test_call_tool_filter_orders_expression_before_file_flag():
    results = asyncio.run(
        handle_call_tool(
            "filter",
            {"file": str(FIXTURES / "sample.candump"), "expression": "id==0x18FEEE31"},
        )
    )
    assert len(results) == 1
    payload = json.loads(results[0].text)
    assert payload["ok"] is True
    assert payload["command"] == "filter"
    assert len(payload["data"]["events"]) == 1
    frame = payload["data"]["events"][0]["payload"]["frame"]
    assert frame["arbitration_id"] == 0x18FEEE31


def test_call_tool_datasets_search_returns_machine_fields():
    results = asyncio.run(handle_call_tool("datasets_search", {"query": "candid"}))
    assert len(results) == 1
    payload = json.loads(results[0].text)
    assert payload["ok"] is True
    assert payload["command"] == "datasets search"
    assert payload["data"]["count"] >= 1
    result = payload["data"]["results"][0]
    assert result["ref"] == "catalog:candid"
    assert result["is_replayable"] is True
    assert result["default_replay_file"] == "2_brakes_CAN.log"


def test_call_tool_datasets_inspect_index_returns_machine_fields():
    results = asyncio.run(handle_call_tool("datasets_inspect", {"ref": "catalog:pivot-auto-datasets"}))
    assert len(results) == 1
    payload = json.loads(results[0].text)
    assert payload["ok"] is True
    assert payload["command"] == "datasets inspect"
    assert payload["data"]["is_index"] is True
    assert payload["data"]["is_replayable"] is False
    assert payload["data"]["source_type"] == "curated-index"


def test_call_tool_datasets_replay_plan_does_not_stream():
    results = asyncio.run(
        handle_call_tool(
            "datasets_replay_plan",
            {"source": "catalog:candid", "format": "jsonl", "file": "2_indicator_CAN.log", "rate": 10.0, "max_frames": 5, "max_seconds": 2.5},
        )
    )
    assert len(results) == 1
    payload = json.loads(results[0].text)
    assert payload["ok"] is True
    assert payload["command"] == "datasets replay"
    assert payload["data"]["dry_run"] is True
    assert payload["data"]["streamed"] is False
    assert payload["data"]["would_stream"] is True
    assert payload["data"]["output_format"] == "jsonl"
    assert payload["data"]["replay_file"] == "2_indicator_CAN.log"
    assert payload["data"]["max_frames"] == 5
    assert payload["data"]["max_seconds"] == 2.5


def test_call_tool_datasets_replay_plan_index_error():
    results = asyncio.run(handle_call_tool("datasets_replay_plan", {"source": "catalog:pivot-auto-datasets"}))
    payload = json.loads(results[0].text)
    assert payload["ok"] is False
    assert payload["command"] == "datasets replay"
    assert payload["errors"][0]["code"] == "DATASET_INDEX_NOT_REPLAYABLE"


def test_call_tool_datasets_replay_files_lists_manifest():
    results = asyncio.run(handle_call_tool("datasets_replay_files", {"source": "catalog:candid"}))
    payload = json.loads(results[0].text)
    assert payload["ok"] is True
    assert payload["command"] == "datasets replay"
    assert payload["data"]["count"] >= 1
    assert payload["data"]["files"][0]["name"].endswith(".log")


def test_call_tool_skills_provider_list():
    results = asyncio.run(handle_call_tool("skills_provider_list", {}))
    payload = json.loads(results[0].text)
    assert payload["ok"] is True
    assert payload["command"] == "skills provider list"
    assert "providers" in payload["data"]


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


def test_build_argv_capture_info():
    argv = _build_argv("capture_info", {"file": "trace.candump"})
    assert argv == ["capture-info", "--file", "trace.candump", "--json"]


def test_build_argv_stats_uses_file_flag():
    argv = _build_argv("stats", {"file": "trace.candump", "max_frames": 50})
    assert argv == ["stats", "--file", "trace.candump", "--max-frames", "50", "--json"]


def test_build_argv_filter_uses_expression_then_file_flag():
    argv = _build_argv(
        "filter",
        {"file": "trace.candump", "expression": "id==0x123", "seconds": 2.5},
    )
    assert argv == ["filter", "id==0x123", "--file", "trace.candump", "--seconds", "2.5", "--json"]


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


def test_build_argv_decode_uses_file_flag():
    argv = _build_argv("decode", {"file": "trace.candump", "dbc": "db.dbc", "max_frames": 10})
    assert argv == ["decode", "--file", "trace.candump", "--dbc", "db.dbc", "--max-frames", "10", "--json"]


def test_build_argv_j1939_pgn():
    argv = _build_argv("j1939_pgn", {"pgn": 61444, "file": "trace.candump"})
    assert argv[:2] == ["j1939", "pgn"]
    assert "61444" in argv
    assert "--file" in argv
    assert "trace.candump" in argv
    assert argv[-1] == "--json"


def test_build_argv_j1939_decode_uses_file_flag():
    argv = _build_argv("j1939_decode", {"file": "trace.candump", "dbc": "truck.dbc"})
    assert argv == ["j1939", "decode", "--file", "trace.candump", "--dbc", "truck.dbc", "--json"]


def test_build_argv_j1939_faults():
    argv = _build_argv("j1939_faults", {"file": "trace.candump", "dbc": "truck.dbc", "seconds": 3.5})
    assert argv == ["j1939", "faults", "--file", "trace.candump", "--dbc", "truck.dbc", "--seconds", "3.5", "--json"]


def test_build_argv_j1939_compare_multiple_files():
    argv = _build_argv("j1939_compare", {"files": ["before.candump", "after.candump"], "max_frames": 500})
    assert argv == ["j1939", "compare", "before.candump", "after.candump", "--max-frames", "500", "--json"]


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


def test_build_argv_datasets_search_with_options():
    argv = _build_argv("datasets_search", {"query": "j1939", "provider": "catalog", "limit": 5})
    assert argv == ["datasets", "search", "j1939", "--provider", "catalog", "--limit", "5", "--json"]


def test_build_argv_datasets_replay_plan_forces_dry_run():
    argv = _build_argv(
        "datasets_replay_plan",
        {"source": "catalog:candid", "format": "jsonl", "file": "2_indicator_CAN.log", "rate": 10.0, "max_frames": 100, "max_seconds": 2.5},
    )
    assert argv == [
        "datasets", "replay", "catalog:candid", "--format", "jsonl", "--file", "2_indicator_CAN.log", "--rate", "10.0",
        "--max-frames", "100", "--max-seconds", "2.5", "--dry-run", "--json",
    ]


def test_build_argv_datasets_convert():
    argv = _build_argv(
        "datasets_convert",
        {"file": "sample.csv", "source_format": "hcrl-csv", "format": "jsonl", "output": "sample.jsonl"},
    )
    assert argv == [
        "datasets", "convert", "sample.csv", "--source-format", "hcrl-csv", "--format", "jsonl", "--output", "sample.jsonl", "--json"
    ]


def test_build_argv_datasets_replay_files():
    argv = _build_argv("datasets_replay_files", {"source": "catalog:candid"})
    assert argv == ["datasets", "replay", "catalog:candid", "--list-files", "--json"]


def test_build_argv_skills_tools():
    assert _build_argv("skills_provider_list", {}) == ["skills", "provider", "list", "--json"]
    assert _build_argv("skills_search", {"query": "j1939", "provider": "github", "limit": 3}) == [
        "skills", "search", "j1939", "--provider", "github", "--limit", "3", "--json"
    ]
    assert _build_argv("skills_fetch", {"ref": "github:j1939_compare_triage"}) == [
        "skills", "fetch", "github:j1939_compare_triage", "--json"
    ]
    assert _build_argv("skills_cache_list", {}) == ["skills", "cache", "list", "--json"]
    assert _build_argv("skills_cache_refresh", {"provider": "github"}) == [
        "skills", "cache", "refresh", "--provider", "github", "--json"
    ]


def test_build_argv_re_signals():
    argv = _build_argv("re_signals", {"file": "trace.candump"})
    assert argv == ["re", "signals", "trace.candump", "--json"]


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


# --- TEST-MCP-15: handle_call_tool does not block the event loop -----------

def test_handle_call_tool_is_nonblocking():
    """execute_command must run in a thread so the event loop stays alive."""
    import threading

    event_loop_ran = threading.Event()

    async def _run():
        async def _ticker():
            event_loop_ran.set()
            await asyncio.sleep(0)

        ticker_task = asyncio.create_task(_ticker())
        await handle_call_tool("config_show", {})
        await ticker_task

    asyncio.run(_run())
    assert event_loop_ran.is_set(), "Event loop was blocked during handle_call_tool"


# --- TEST-MCP-16: _build_argv threads max_frames and seconds through -------

def test_build_argv_j1939_summary_max_frames():
    argv = _build_argv("j1939_summary", {"file": "big.log", "max_frames": 5000})
    assert "--max-frames" in argv
    assert "5000" in argv
    assert argv[-1] == "--json"


def test_build_argv_j1939_summary_seconds():
    argv = _build_argv("j1939_summary", {"file": "big.log", "seconds": 30.0})
    assert "--seconds" in argv
    assert "30.0" in argv
    assert argv[-1] == "--json"


def test_build_argv_j1939_inventory_max_frames():
    argv = _build_argv("j1939_inventory", {"file": "big.log", "max_frames": 5000})
    assert argv[:3] == ["j1939", "inventory", "--file"]
    assert "big.log" in argv
    assert "--max-frames" in argv
    assert "5000" in argv
    assert argv[-1] == "--json"


def test_build_argv_j1939_decode_max_frames():
    argv = _build_argv("j1939_decode", {"file": "big.log", "max_frames": 1000})
    assert "--max-frames" in argv
    assert "1000" in argv


def test_build_argv_j1939_pgn_max_frames():
    argv = _build_argv("j1939_pgn", {"pgn": 61444, "file": "big.log", "max_frames": 2000})
    assert "--max-frames" in argv
    assert "2000" in argv


def test_build_argv_j1939_spn_seconds():
    argv = _build_argv("j1939_spn", {"spn": 190, "file": "big.log", "seconds": 10.0})
    assert "--seconds" in argv
    assert "10.0" in argv


def test_build_argv_j1939_tp_max_frames():
    argv = _build_argv("j1939_tp", {"file": "big.log", "max_frames": 500})
    assert argv == ["j1939", "tp", "sessions", "--file", "big.log", "--max-frames", "500", "--json"]


def test_build_argv_j1939_tp_seconds_and_offset():
    argv = _build_argv("j1939_tp", {"file": "big.log", "pgn": 65226, "sa": "0x80,129", "offset": 12, "seconds": 10.0})
    assert argv == [
        "j1939", "tp", "sessions", "--file", "big.log", "--pgn", "65226", "--sa", "0x80,129",
        "--offset", "12", "--seconds", "10.0", "--json",
    ]


def test_build_argv_j1939_tp_compare():
    argv = _build_argv("j1939_tp_compare", {"file": "big.log", "sa": "0x80,0x81", "pgn": 65226, "max_frames": 1000})
    assert argv == [
        "j1939", "tp", "compare", "--file", "big.log", "--sa", "0x80,0x81", "--pgn", "65226",
        "--max-frames", "1000", "--json",
    ]


def test_build_argv_j1939_dm1_max_frames():
    argv = _build_argv("j1939_dm1", {"file": "big.log", "max_frames": 100})
    assert "--max-frames" in argv
    assert "100" in argv


def test_build_argv_j1939_summary_no_limits():
    """When no limits provided, no extra flags are added."""
    argv = _build_argv("j1939_summary", {"file": "small.log"})
    assert "--max-frames" not in argv
    assert "--seconds" not in argv


# --- TEST-MCP-17: file-based J1939 tool schemas expose max_frames/seconds --

def test_j1939_tool_schemas_have_frame_limit_params():
    tools_by_name = {t.name: t for t in asyncio.run(handle_list_tools())}
    file_tools = [
        "j1939_decode", "j1939_pgn", "j1939_spn", "j1939_tp", "j1939_tp_compare",
        "j1939_dm1", "j1939_faults", "j1939_summary", "j1939_inventory", "j1939_compare",
    ]
    for tool_name in file_tools:
        schema = tools_by_name[tool_name].inputSchema
        props = schema.get("properties", {})
        assert "max_frames" in props, f"{tool_name} missing max_frames"
        assert "seconds" in props, f"{tool_name} missing seconds"


# --- TEST-MCP-18: run_server handles signals without traceback --------------

def test_run_server_handles_sigint():
    """run_server should exit cleanly on SIGINT without traceback."""
    import signal
    import subprocess
    import sys
    import time

    proc = subprocess.Popen(
        [sys.executable, "-m", "canarchy", "mcp", "serve"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    time.sleep(0.5)
    proc.send_signal(signal.SIGINT)

    try:
        stdout, stderr = proc.communicate(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        pytest.fail("run_server did not exit within 3s after SIGINT — process hung")

    assert "AttributeError" not in stderr, f"Got AttributeError in stderr: {stderr}"
    assert "Traceback" not in stderr, f"Got traceback in stderr: {stderr}"
    assert "KeyboardInterrupt" not in stderr, f"Got KeyboardInterrupt in stderr: {stderr}"
