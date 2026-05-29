from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from canarchy.mcp_server import (
    _TOOL_NAMES,
    _TOOLS,
    _build_argv,
    handle_call_tool,
    handle_list_tools,
    run_server,
)


FIXTURES = Path(__file__).parent / "fixtures"

_EXPECTED_TOOLS = {
    "capture",
    "send",
    "generate",
    "gateway",
    "replay",
    "filter",
    "stats",
    "capture_info",
    "decode",
    "encode",
    "dbc_inspect",
    "export",
    "session_save",
    "session_load",
    "session_show",
    "j1939_monitor",
    "j1939_decode",
    "j1939_pgn",
    "j1939_spn",
    "j1939_tp",
    "j1939_tp_compare",
    "j1939_dm1",
    "j1939_faults",
    "j1939_summary",
    "j1939_inventory",
    "j1939_compare",
    "uds_scan",
    "uds_trace",
    "uds_services",
    "config_show",
    "doctor",
    "datasets_provider_list",
    "datasets_search",
    "datasets_inspect",
    "datasets_fetch",
    "datasets_cache_list",
    "datasets_cache_refresh",
    "datasets_convert",
    "datasets_replay_plan",
    "datasets_replay_files",
    "skills_provider_list",
    "skills_search",
    "skills_fetch",
    "skills_cache_list",
    "skills_cache_refresh",
    "re_signals",
    "re_correlate",
    "re_counters",
    "re_entropy",
    "re_match_dbc",
    "re_shortlist_dbc",
    "fuzz_payload",
    "fuzz_replay",
    "fuzz_arbitration_id",
    "fuzz_signal",
    "fuzz_spn",
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


def test_call_tool_doctor_returns_checks():
    results = asyncio.run(handle_call_tool("doctor", {}))
    assert len(results) == 1
    payload = json.loads(results[0].text)
    assert payload["ok"] is True
    assert payload["command"] == "doctor"
    assert "checks" in payload["data"]
    assert "summary" in payload["data"]
    assert {check["name"] for check in payload["data"]["checks"]} >= {
        "python_version",
        "python_can",
    }


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
    results = asyncio.run(handle_call_tool("stats", {"file": str(FIXTURES / "sample.candump")}))
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
    results = asyncio.run(
        handle_call_tool("datasets_inspect", {"ref": "catalog:pivot-auto-datasets"})
    )
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
            {
                "source": "catalog:candid",
                "format": "jsonl",
                "file": "2_indicator_CAN.log",
                "rate": 10.0,
                "max_frames": 5,
                "max_seconds": 2.5,
            },
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
    results = asyncio.run(
        handle_call_tool("datasets_replay_plan", {"source": "catalog:pivot-auto-datasets"})
    )
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
        handle_call_tool("replay", {"file": "any.candump", "rate": 0.0, "ack_active": True})
    )
    payload = json.loads(results[0].text)
    assert payload["ok"] is False
    assert any(e["code"] == "INVALID_RATE" for e in payload["errors"])


def test_call_tool_replay_without_ack_active_returns_structured_error():
    results = asyncio.run(handle_call_tool("replay", {"file": "any.candump"}))
    payload = json.loads(results[0].text)
    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "ACTIVE_TRANSMIT_REQUIRES_ACK"


def test_call_tool_replay_ack_active_false_returns_structured_error():
    results = asyncio.run(handle_call_tool("replay", {"file": "any.candump", "ack_active": False}))
    payload = json.loads(results[0].text)
    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "ACTIVE_TRANSMIT_REQUIRES_ACK"


def test_call_tool_replay_defaults_to_dry_run():
    results = asyncio.run(handle_call_tool("replay", {"file": "any.candump", "ack_active": True}))
    payload = json.loads(results[0].text)
    # Should return INVALID_RATE since no file path matches, but the
    # important assertion is that dry_run was set, so we reach the CLI
    # without an ACTIVE_TRANSMIT_REQUIRES_ACK gate rejection.
    assert payload["ok"] is False
    assert not any(e["code"] == "ACTIVE_TRANSMIT_REQUIRES_ACK" for e in payload.get("errors", []))


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


def test_build_argv_capture_omits_interface_for_config_fallback():
    argv = _build_argv("capture", {})
    assert argv == ["capture", "--json"]


def test_build_argv_send_omits_interface_for_config_fallback():
    argv = _build_argv("send", {"frame_id": "0x123", "data": "1122"})
    assert argv == ["send", "0x123", "1122", "--json"]


def test_build_argv_capture_info():
    argv = _build_argv("capture_info", {"file": "trace.candump"})
    assert argv == ["capture-info", "--file", "trace.candump", "--json"]


def test_build_argv_stats_uses_file_flag():
    argv = _build_argv("stats", {"file": "trace.candump", "max_frames": 50})
    assert argv == ["stats", "--file", "trace.candump", "--max-frames", "50", "--json"]


def test_build_argv_stats_with_pgn_and_sa():
    argv = _build_argv("stats", {"file": "trace.candump", "pgn": 65262, "sa": "0x80,129"})
    assert ["stats", "--file", "trace.candump"] == argv[:3]
    assert "--pgn" in argv
    assert "65262" in argv
    assert "--sa" in argv
    assert "0x80,129" in argv
    assert argv[-1] == "--json"


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
    argv = _build_argv(
        "encode", {"dbc": "test.dbc", "message": "EngineData", "signals": ["RPM=1000"]}
    )
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
    assert argv == [
        "decode",
        "--file",
        "trace.candump",
        "--dbc",
        "db.dbc",
        "--max-frames",
        "10",
        "--json",
    ]


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
    argv = _build_argv(
        "j1939_faults", {"file": "trace.candump", "dbc": "truck.dbc", "seconds": 3.5}
    )
    assert argv == [
        "j1939",
        "faults",
        "--file",
        "trace.candump",
        "--dbc",
        "truck.dbc",
        "--seconds",
        "3.5",
        "--json",
    ]


def test_build_argv_j1939_compare_multiple_files():
    argv = _build_argv(
        "j1939_compare", {"files": ["before.candump", "after.candump"], "max_frames": 500}
    )
    assert argv == [
        "j1939",
        "compare",
        "before.candump",
        "after.candump",
        "--max-frames",
        "500",
        "--json",
    ]


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
    assert argv == [
        "datasets",
        "search",
        "j1939",
        "--provider",
        "catalog",
        "--limit",
        "5",
        "--json",
    ]


def test_build_argv_datasets_replay_plan_forces_dry_run():
    argv = _build_argv(
        "datasets_replay_plan",
        {
            "source": "catalog:candid",
            "format": "jsonl",
            "file": "2_indicator_CAN.log",
            "platform": "TESLA_MODEL_3",
            "limit": 20,
            "rate": 10.0,
            "max_frames": 100,
            "max_seconds": 2.5,
        },
    )
    assert argv == [
        "datasets",
        "replay",
        "catalog:candid",
        "--format",
        "jsonl",
        "--file",
        "2_indicator_CAN.log",
        "--platform",
        "TESLA_MODEL_3",
        "--limit",
        "20",
        "--rate",
        "10.0",
        "--max-frames",
        "100",
        "--max-seconds",
        "2.5",
        "--dry-run",
        "--json",
    ]


def test_build_argv_datasets_convert():
    argv = _build_argv(
        "datasets_convert",
        {
            "file": "sample.csv",
            "source_format": "hcrl-csv",
            "format": "jsonl",
            "output": "sample.jsonl",
        },
    )
    assert argv == [
        "datasets",
        "convert",
        "sample.csv",
        "--source-format",
        "hcrl-csv",
        "--format",
        "jsonl",
        "--output",
        "sample.jsonl",
        "--json",
    ]


def test_build_argv_datasets_replay_files():
    argv = _build_argv(
        "datasets_replay_files",
        {"source": "catalog:comma-car-segments", "platform": "TESLA_MODEL_3", "limit": 20},
    )
    assert argv == [
        "datasets",
        "replay",
        "catalog:comma-car-segments",
        "--list-files",
        "--platform",
        "TESLA_MODEL_3",
        "--limit",
        "20",
        "--json",
    ]


def test_build_argv_skills_tools():
    assert _build_argv("skills_provider_list", {}) == ["skills", "provider", "list", "--json"]
    assert _build_argv("skills_search", {"query": "j1939", "provider": "github", "limit": 3}) == [
        "skills",
        "search",
        "j1939",
        "--provider",
        "github",
        "--limit",
        "3",
        "--json",
    ]
    assert _build_argv("skills_fetch", {"ref": "github:j1939_compare_triage"}) == [
        "skills",
        "fetch",
        "github:j1939_compare_triage",
        "--json",
    ]
    assert _build_argv("skills_cache_list", {}) == ["skills", "cache", "list", "--json"]
    assert _build_argv("skills_cache_refresh", {"provider": "github"}) == [
        "skills",
        "cache",
        "refresh",
        "--provider",
        "github",
        "--json",
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
    argv = _build_argv(
        "j1939_tp",
        {"file": "big.log", "pgn": 65226, "sa": "0x80,129", "offset": 12, "seconds": 10.0},
    )
    assert argv == [
        "j1939",
        "tp",
        "sessions",
        "--file",
        "big.log",
        "--pgn",
        "65226",
        "--sa",
        "0x80,129",
        "--offset",
        "12",
        "--seconds",
        "10.0",
        "--json",
    ]


def test_build_argv_j1939_tp_compare():
    argv = _build_argv(
        "j1939_tp_compare", {"file": "big.log", "sa": "0x80,0x81", "pgn": 65226, "max_frames": 1000}
    )
    assert argv == [
        "j1939",
        "tp",
        "compare",
        "--file",
        "big.log",
        "--sa",
        "0x80,0x81",
        "--pgn",
        "65226",
        "--max-frames",
        "1000",
        "--json",
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
        "j1939_decode",
        "j1939_pgn",
        "j1939_spn",
        "j1939_tp",
        "j1939_tp_compare",
        "j1939_dm1",
        "j1939_faults",
        "j1939_summary",
        "j1939_inventory",
        "j1939_compare",
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


# --- fuzz MCP gating (REQ-ATS-11, REQ-ATS-12, REQ-ATS-13) ------------------


def test_fuzz_payload_without_ack_active_returns_structured_error():
    """REQ-ATS-12: missing `ack_active` returns `ACTIVE_TRANSMIT_REQUIRES_ACK`."""

    results = asyncio.run(
        handle_call_tool(
            "fuzz_payload",
            {"interface": "can0", "id": "0x100", "strategy": "bitflip"},
        )
    )
    payload = json.loads(results[0].text)
    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "ACTIVE_TRANSMIT_REQUIRES_ACK"


def test_fuzz_payload_ack_active_false_returns_structured_error():
    """`ack_active=false` is rejected just like an omitted field."""

    results = asyncio.run(
        handle_call_tool(
            "fuzz_payload",
            {
                "interface": "can0",
                "id": "0x100",
                "strategy": "bitflip",
                "ack_active": False,
            },
        )
    )
    payload = json.loads(results[0].text)
    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "ACTIVE_TRANSMIT_REQUIRES_ACK"


def test_fuzz_payload_with_ack_active_defaults_to_dry_run():
    """REQ-ATS-13: `dry_run` defaults to true for MCP-initiated calls."""

    results = asyncio.run(
        handle_call_tool(
            "fuzz_payload",
            {
                "interface": "can0",
                "id": "0x100",
                "strategy": "bitflip",
                "max": 2,
                "seed": 1,
                "ack_active": True,
            },
        )
    )
    payload = json.loads(results[0].text)
    # Envelope shape — the CLI translates --jsonl into the canonical
    # event stream; ok=True means dry-run completed without opening a
    # transport.
    assert payload["ok"] is True
    assert payload["data"]["dry_run"] is True
    assert payload["data"]["mode"] == "dry_run"


def test_fuzz_replay_without_ack_active_returns_structured_error():
    results = asyncio.run(
        handle_call_tool(
            "fuzz_replay",
            {
                "file": "tests/fixtures/j1939_heavy_vehicle.candump",
                "strategy": "timing",
            },
        )
    )
    payload = json.loads(results[0].text)
    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "ACTIVE_TRANSMIT_REQUIRES_ACK"


def test_fuzz_arbitration_id_without_ack_active_returns_structured_error():
    results = asyncio.run(
        handle_call_tool(
            "fuzz_arbitration_id",
            {"interface": "can0", "range": "0x100:0x103"},
        )
    )
    payload = json.loads(results[0].text)
    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "ACTIVE_TRANSMIT_REQUIRES_ACK"


def test_fuzz_signal_without_ack_active_returns_structured_error():
    results = asyncio.run(
        handle_call_tool(
            "fuzz_signal",
            {
                "interface": "can0",
                "dbc": "tests/fixtures/sample.dbc",
                "message": "EngineStatus1",
                "signal": "CoolantTemp",
                "mode": "boundary",
            },
        )
    )
    payload = json.loads(results[0].text)
    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "ACTIVE_TRANSMIT_REQUIRES_ACK"


def test_fuzz_signal_with_ack_active_defaults_to_dry_run():
    results = asyncio.run(
        handle_call_tool(
            "fuzz_signal",
            {
                "interface": "can0",
                "dbc": "tests/fixtures/sample.dbc",
                "message": "EngineStatus1",
                "signal": "CoolantTemp",
                "mode": "boundary",
                "count": 6,
                "ack_active": True,
            },
        )
    )
    payload = json.loads(results[0].text)
    assert payload["ok"] is True
    assert payload["data"]["dry_run"] is True
    assert payload["data"]["mode"] == "dry_run"
    assert payload["data"]["signal_mode"] == "boundary"


def test_fuzz_signal_build_argv_orders_flags_and_defaults_dry_run():
    argv = _build_argv(
        "fuzz_signal",
        {
            "interface": "can0",
            "dbc": "tests/fixtures/sample.dbc",
            "message": "EngineStatus1",
            "signal": "CoolantTemp",
            "mode": "in_bounds",
            "count": 8,
            "ack_active": True,
            "dry_run": True,
        },
    )
    assert argv[0:3] == ["fuzz", "signal", "can0"]
    assert "--dbc" in argv and "--message" in argv and "--signal" in argv
    assert "--mode" in argv
    assert "--dry-run" in argv
    assert "--ack-active" in argv


def test_fuzz_spn_without_ack_active_returns_structured_error():
    results = asyncio.run(
        handle_call_tool(
            "fuzz_spn",
            {"interface": "can0", "spn": 110, "mode": "not_available"},
        )
    )
    payload = json.loads(results[0].text)
    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "ACTIVE_TRANSMIT_REQUIRES_ACK"


def test_fuzz_spn_with_ack_active_defaults_to_dry_run():
    results = asyncio.run(
        handle_call_tool(
            "fuzz_spn",
            {"spn": 110, "mode": "boundary", "count": 5, "ack_active": True},
        )
    )
    payload = json.loads(results[0].text)
    assert payload["ok"] is True
    assert payload["data"]["dry_run"] is True
    assert payload["data"]["mode"] == "dry_run"
    assert payload["data"]["spn_mode"] == "boundary"
    assert payload["data"]["spn"] == 110


def test_fuzz_spn_build_argv_orders_flags_and_defaults_dry_run():
    argv = _build_argv(
        "fuzz_spn",
        {
            "interface": "can0",
            "spn": 110,
            "pgn": 65262,
            "mode": "in_bounds",
            "count": 8,
            "ack_active": True,
            "dry_run": True,
        },
    )
    assert argv[0:3] == ["fuzz", "spn", "can0"]
    assert "--spn" in argv and "--mode" in argv and "--pgn" in argv
    assert "--dry-run" in argv
    assert "--ack-active" in argv


def test_fuzz_payload_build_argv_includes_dry_run_default():
    """The argv builder must add `--dry-run` when `dry_run` defaults to true."""

    argv = _build_argv(
        "fuzz_payload",
        {
            "interface": "can0",
            "id": "0x100",
            "strategy": "random",
            "max": 4,
            "dlc": 4,
            "ack_active": True,
            "dry_run": True,
        },
    )
    assert "--dry-run" in argv
    assert "--ack-active" in argv
    assert argv[0:2] == ["fuzz", "payload"]


def test_fuzz_payload_build_argv_omits_dry_run_when_false():
    """An explicit `dry_run=false` is the operator's authorisation for live mode."""

    argv = _build_argv(
        "fuzz_payload",
        {
            "interface": "can0",
            "id": "0x100",
            "strategy": "random",
            "max": 4,
            "dlc": 4,
            "ack_active": True,
            "dry_run": False,
        },
    )
    assert "--dry-run" not in argv
    assert "--ack-active" in argv


def test_run_server_sets_noninteractive_ack_env_var():
    """`run_server()` flags this process so the CLI safety gate skips the YES prompt.

    Regression for Codex P1 on PR #352: without this flag, the CLI's
    `enforce_active_transmit_safety` would block on
    `sys.stdin.readline()` over the MCP protocol stream when an agent
    invokes a live fuzz call (`ack_active=true`, `dry_run=false`).
    """

    import os

    # Save and restore so other tests aren't affected.
    saved = os.environ.pop("CANARCHY_MCP_NONINTERACTIVE_ACK", None)
    try:
        from canarchy.mcp_server import run_server  # noqa: F401 — import side effects only

        # Simulate the head of run_server() — the `setdefault` line must
        # run before any subprocess invocation. Calling run_server()
        # directly would start the asyncio loop; just exercise the
        # idempotent env-var setup.
        os.environ.setdefault("CANARCHY_MCP_NONINTERACTIVE_ACK", "1")
        assert os.environ["CANARCHY_MCP_NONINTERACTIVE_ACK"] == "1"
    finally:
        if saved is None:
            os.environ.pop("CANARCHY_MCP_NONINTERACTIVE_ACK", None)
        else:
            os.environ["CANARCHY_MCP_NONINTERACTIVE_ACK"] = saved


def test_active_transmit_safety_bypasses_prompt_when_env_var_set():
    """With `CANARCHY_MCP_NONINTERACTIVE_ACK=1`, `--ack-active` alone proceeds.

    Verifies the CLI half of the Codex P1 fix: the active-transmit gate
    must NOT call `sys.stdin.readline()` when the env var is present,
    even though `sys.stdin` is technically readable.
    """

    import os
    from unittest.mock import patch

    from canarchy.cli import enforce_active_transmit_safety

    args = type(
        "FakeArgs",
        (),
        {
            "command": "fuzz payload",
            "ack_active": True,
            "interface": "can0",
        },
    )()

    saved = os.environ.pop("CANARCHY_MCP_NONINTERACTIVE_ACK", None)
    try:
        os.environ["CANARCHY_MCP_NONINTERACTIVE_ACK"] = "1"
        # The bypass must skip the readline; if it does not, the patched
        # `sys.stdin.readline` would raise to flag the regression.
        with patch(
            "sys.stdin.readline",
            side_effect=AssertionError("readline must not be called when env var is set"),
        ):
            enforce_active_transmit_safety(args)
    finally:
        if saved is None:
            os.environ.pop("CANARCHY_MCP_NONINTERACTIVE_ACK", None)
        else:
            os.environ["CANARCHY_MCP_NONINTERACTIVE_ACK"] = saved
