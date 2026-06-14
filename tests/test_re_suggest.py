"""Tests for `re suggest` heuristic + optional-LLM name suggestions (#332)."""

from __future__ import annotations

import contextlib
import io
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from canarchy.re_suggest import suggest_for_candidate, suggest_names

FIXTURES = Path(__file__).parent / "fixtures"
EEC1_FIXTURE = FIXTURES / "re_suggest_eec1.candump"


def run_cli(*argv: str) -> tuple[int, str, str]:
    from canarchy.cli import main

    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = main(argv)
    return exit_code, stdout.getvalue(), stderr.getvalue()


def _candidate(**overrides) -> dict:
    base = {
        "arbitration_id": 0x18F00400,
        "arbitration_id_hex": "0x18F00400",
        "start_bit": 24,
        "bit_length": 8,
        "score": 0.5,
        "observed_min": 0,
        "observed_max": 200,
        "change_rate": 0.5,
        "pgn": 61444,
        "pgn_label": "EEC1",
        "pgn_name": "Electronic Engine Controller 1",
    }
    base.update(overrides)
    return base


class HeuristicSuggestionTests(unittest.TestCase):
    def test_spn_overlap_names_engine_speed(self) -> None:
        # Bits 24..31 overlap SPN 190 (Engine Speed, PGN 61444, bytes 3..4).
        result = suggest_for_candidate(_candidate(start_bit=24, bit_length=8))
        self.assertEqual(result["suggested_name"], "Engine Speed")
        self.assertEqual(result["suggested_source"], "spn")
        self.assertTrue(any(s["source"] == "spn" for s in result["suggestions"]))

    def test_dbc_reference_suggests_message_signal(self) -> None:
        dbc_signals = {
            0x18F00400: [
                {
                    "name": "MyEngineRpm",
                    "length": 8,
                    "start": 24,
                    "byte_order": "little_endian",
                    "unit": "rpm",
                }
            ]
        }
        result = suggest_for_candidate(
            _candidate(pgn=None, pgn_label=None, pgn_name=None), dbc_signals
        )
        names = [s["name"] for s in result["suggestions"]]
        self.assertIn("MyEngineRpm", names)
        self.assertEqual(result["suggested_source"], "dbc")

    def test_dbc_suggestion_respects_bit_position(self) -> None:
        # Two same-length signals: only the one overlapping the candidate's bytes
        # should be suggested (a byte-7 candidate is not the byte-0 signal).
        dbc_signals = {
            0x200: [
                {"name": "FirstByteSig", "length": 8, "start": 0, "byte_order": "little_endian"},
                {"name": "ByteSevenSig", "length": 8, "start": 56, "byte_order": "little_endian"},
            ]
        }
        candidate = _candidate(
            arbitration_id=0x200,
            start_bit=56,
            bit_length=8,
            pgn=None,
            pgn_label=None,
            pgn_name=None,
        )
        result = suggest_for_candidate(candidate, dbc_signals)
        dbc_names = [s["name"] for s in result["suggestions"] if s["source"] == "dbc"]
        self.assertEqual(dbc_names, ["ByteSevenSig"])
        self.assertEqual(result["suggested_name"], "ByteSevenSig")

    def test_pgn_fallback_when_no_spn_overlap(self) -> None:
        # A bit range with no decodable SPN overlap falls back to the PGN label.
        result = suggest_for_candidate(_candidate(start_bit=0, bit_length=4, pgn=0xEF00))
        sources = [s["source"] for s in result["suggestions"]]
        self.assertNotIn("spn", sources)
        self.assertIn("heuristic", sources)

    def test_heuristic_template_always_present(self) -> None:
        result = suggest_for_candidate(_candidate(pgn=None, pgn_label=None, pgn_name=None))
        self.assertEqual(result["suggested_source"], "heuristic")
        self.assertTrue(result["suggested_name"].startswith("active_value_"))

    def test_suggest_names_maps_all(self) -> None:
        results = suggest_names([_candidate(), _candidate(start_bit=0, bit_length=8)])
        self.assertEqual(len(results), 2)
        self.assertTrue(all("suggestions" in r for r in results))


class CliHeuristicTests(unittest.TestCase):
    def test_cli_heuristic_path_names_candidates(self) -> None:
        exit_code, stdout, _ = run_cli("re", "suggest", str(EEC1_FIXTURE), "--json")
        self.assertEqual(exit_code, 0)
        data = json.loads(stdout)["data"]
        self.assertEqual(data["mode"], "passive")
        self.assertGreater(data["candidate_count"], 0)
        spn_named = [c for c in data["candidates"] if c.get("suggested_source") == "spn"]
        self.assertTrue(spn_named)
        self.assertIn("Engine Speed", {c["suggested_name"] for c in spn_named})
        self.assertNotIn("external_enrichment", data)

    def test_cli_file_flag_form(self) -> None:
        exit_code, stdout, _ = run_cli(
            "re", "suggest", "--file", str(EEC1_FIXTURE), "--limit", "5", "--json"
        )
        self.assertEqual(exit_code, 0)
        self.assertLessEqual(json.loads(stdout)["data"]["candidate_count"], 5)


class CliLlmPathTests(unittest.TestCase):
    def test_llm_declined_without_confirmation_errors(self) -> None:
        # No --yes and no non-interactive env: a non-YES reply declines the call.
        with patch("sys.stdin", io.StringIO("no\n")):
            exit_code, stdout, _ = run_cli(
                "re", "suggest", str(EEC1_FIXTURE), "--llm", "anthropic", "--json"
            )
        self.assertEqual(exit_code, 1)
        payload = json.loads(stdout)
        self.assertEqual(payload["errors"][0]["code"], "LLM_CONFIRMATION_DECLINED")

    def test_llm_enrichment_with_mocked_client(self) -> None:
        class _FakeClient:
            def suggest(self, items):
                return {0: {"name": "engine_rpm_llm", "rationale": "fits EEC1"}}

        from canarchy import llm_suggest

        with (
            patch.dict(os.environ, {"CANARCHY_LLM_NONINTERACTIVE": "1"}),
            patch.object(llm_suggest, "_build_client", return_value=_FakeClient()),
        ):
            exit_code, stdout, _ = run_cli(
                "re", "suggest", str(EEC1_FIXTURE), "--llm", "anthropic", "--json"
            )
        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout)
        data = payload["data"]
        self.assertEqual(data["external_enrichment"]["provider"], "anthropic")
        self.assertTrue(data["external_enrichment"]["confirmed"])
        self.assertEqual(data["candidates"][0]["suggested_name"], "engine_rpm_llm")
        self.assertEqual(data["candidates"][0]["suggested_source"], "llm")
        self.assertTrue(any("EXTERNAL_SERVICE_CALLED" in w for w in payload["warnings"]))

    def test_unsupported_llm_provider_errors(self) -> None:
        with patch.dict(os.environ, {"CANARCHY_LLM_NONINTERACTIVE": "1"}):
            exit_code, stdout, _ = run_cli(
                "re", "suggest", str(EEC1_FIXTURE), "--llm", "nope", "--json"
            )
        self.assertEqual(exit_code, 1)
        self.assertEqual(json.loads(stdout)["errors"][0]["code"], "LLM_PROVIDER_UNSUPPORTED")

    def test_anthropic_client_validates_malformed_response(self) -> None:
        # A syntactically valid but wrong-shaped provider reply must become a
        # structured LlmError, not a traceback.
        import requests

        from canarchy.llm_suggest import LlmError, _AnthropicClient

        class _Resp:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return {"content": [{"text": '{"not": "a list"}'}]}

        with (
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
            patch.object(requests, "post", return_value=_Resp()),
        ):
            client = _AnthropicClient(model=None)
            with self.assertRaises(LlmError) as ctx:
                client.suggest([{"index": 0, "arbitration_id_hex": "0x1"}])
        self.assertEqual(ctx.exception.code, "LLM_REQUEST_FAILED")


class McpExposureTests(unittest.TestCase):
    def test_re_suggest_tool_is_heuristic_only(self) -> None:
        from canarchy.mcp_server import _TOOL_NAMES, _build_argv

        self.assertIn("re_suggest", _TOOL_NAMES)
        argv = _build_argv("re_suggest", {"file": "cap.candump", "reference_dbc": "x.dbc"})
        self.assertEqual(
            argv, ["re", "suggest", "cap.candump", "--reference-dbc", "x.dbc", "--json"]
        )
        # No llm parameter is accepted on the MCP surface.
        from canarchy.mcp_server import _TOOLS

        schema = next(t for t in _TOOLS if t.name == "re_suggest").inputSchema
        self.assertNotIn("llm", schema["properties"])
