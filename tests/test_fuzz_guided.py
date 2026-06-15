"""Tests for response-feedback guided fuzzing (#350).

The loop is exercised against in-process mocked responders — no live bus.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from canarchy.fuzz_feedback import (
    FeedbackTracker,
    ResponseObservation,
    fingerprint_response,
)
from canarchy.fuzz_guided import load_corpus, run_guided_fuzz, save_corpus
from canarchy.models import CanFrame


def run_cli(*argv: str) -> tuple[int, str, str]:
    from canarchy.cli import main

    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = main(argv)
    return exit_code, stdout.getvalue(), stderr.getvalue()


def _nrc_frame(code: int) -> CanFrame:
    return CanFrame(
        arbitration_id=0x7E8, data=bytes([0x03, 0x7F, 0x27, code]) + bytes(4), timestamp=0.0
    )


def _reactive_responder(payload: bytes) -> ResponseObservation:
    # High first byte -> a UDS negative response whose NRC varies with byte 1.
    if payload and payload[0] >= 0x80:
        code = payload[1] if len(payload) > 1 else 0x10
        return ResponseObservation(frames=(_nrc_frame(code),), elapsed=0.002, silent=False)
    return ResponseObservation(frames=(), elapsed=0.0, silent=True)


class FingerprintTests(unittest.TestCase):
    def test_nrc_marker(self) -> None:
        fp = fingerprint_response(
            ResponseObservation(frames=(_nrc_frame(0x35),), elapsed=0.002), signals=("nrc",)
        )
        self.assertIn("nrc:27:35", fp.markers)

    def test_silence_marker(self) -> None:
        fp = fingerprint_response(ResponseObservation(silent=True), signals=("silence", "timing"))
        self.assertIn("silence", fp.markers)

    def test_signal_selection_filters_categories(self) -> None:
        obs = ResponseObservation(frames=(_nrc_frame(0x35),), elapsed=0.002)
        fp = fingerprint_response(obs, signals=("timing",))
        self.assertFalse(any(m.startswith("nrc") for m in fp.markers))
        self.assertTrue(any(m.startswith("timing") for m in fp.markers))

    def test_tracker_scores_only_new_markers(self) -> None:
        tracker = FeedbackTracker()
        fp = fingerprint_response(
            ResponseObservation(frames=(_nrc_frame(0x35),), elapsed=0.002), signals=("nrc",)
        )
        gain1, new1 = tracker.score_and_observe(fp)
        self.assertGreater(gain1, 0)
        self.assertIn("nrc:27:35", new1)
        gain2, _ = tracker.score_and_observe(fp)
        self.assertEqual(gain2, 0)


class GuidedLoopTests(unittest.TestCase):
    def test_discovers_new_behaviours(self) -> None:
        result = run_guided_fuzz(
            [bytes(8)], _reactive_responder, max_iterations=300, rng_seed=1, max_payload=8
        )
        self.assertEqual(result.iterations, 300)
        self.assertGreater(result.new_behaviour_count, 0)
        self.assertGreater(result.unique_markers, 1)
        self.assertEqual(result.stop_reason, "max_iterations")

    def test_deterministic_under_fixed_seed(self) -> None:
        a = run_guided_fuzz(
            [bytes(8)], _reactive_responder, max_iterations=200, rng_seed=7, max_payload=8
        )
        b = run_guided_fuzz(
            [bytes(8)], _reactive_responder, max_iterations=200, rng_seed=7, max_payload=8
        )
        self.assertEqual(
            (a.iterations, a.new_behaviour_count, a.unique_markers, a.corpus_size),
            (b.iterations, b.new_behaviour_count, b.unique_markers, b.corpus_size),
        )
        self.assertEqual([f.new_markers for f in a.findings], [f.new_markers for f in b.findings])

    def test_corpus_pruning_caps_size(self) -> None:
        result = run_guided_fuzz(
            [bytes(8)],
            _reactive_responder,
            max_iterations=400,
            max_corpus=8,
            rng_seed=2,
            max_payload=8,
        )
        self.assertLessEqual(result.corpus_size, 8)

    def test_kill_switch_stops_mid_campaign(self) -> None:
        calls = {"n": 0}

        def kill() -> bool:
            calls["n"] += 1
            return calls["n"] > 5

        result = run_guided_fuzz(
            [bytes(8)], _reactive_responder, max_iterations=300, rng_seed=1, kill_switch=kill
        )
        self.assertEqual(result.stop_reason, "kill_switch")
        self.assertLessEqual(result.iterations, 6)

    def test_zero_budget_transmits_nothing(self) -> None:
        # The campaign budget bounds priming too: max_iterations=0 sends nothing.
        calls = {"n": 0}

        def counting_responder(payload: bytes) -> ResponseObservation:
            calls["n"] += 1
            return ResponseObservation(silent=True)

        result = run_guided_fuzz([bytes(8), bytes(8)], counting_responder, max_iterations=0)
        self.assertEqual(calls["n"], 0)
        self.assertEqual(result.iterations, 0)
        self.assertEqual(result.stop_reason, "max_iterations")

    def test_priming_counts_against_budget(self) -> None:
        # With three seeds and a budget of two, only two transmissions happen.
        calls = {"n": 0}

        def counting_responder(payload: bytes) -> ResponseObservation:
            calls["n"] += 1
            return ResponseObservation(silent=True)

        result = run_guided_fuzz(
            [bytes(8), bytes(8), bytes(8)], counting_responder, max_iterations=2
        )
        self.assertEqual(calls["n"], 2)
        self.assertEqual(result.iterations, 2)

    def test_nonpositive_max_corpus_is_clamped(self) -> None:
        # Defensive: the engine never prunes the corpus to empty.
        result = run_guided_fuzz(
            [bytes(8)],
            _reactive_responder,
            max_iterations=120,
            max_corpus=0,
            rng_seed=1,
            max_payload=8,
        )
        self.assertGreaterEqual(result.corpus_size, 1)

    def test_pacing_re_checks_budget_and_stops_before_transmitting(self) -> None:
        # Codex review on #350: a pacing delay that crosses max_seconds must end
        # the campaign rather than permit one more transmission past the budget.
        now = {"t": 0.0}
        calls = {"n": 0}

        def clock() -> float:
            return now["t"]

        def sleep(seconds: float) -> None:
            now["t"] += seconds

        def counting_responder(payload: bytes) -> ResponseObservation:
            calls["n"] += 1
            return ResponseObservation(silent=True)

        result = run_guided_fuzz(
            [bytes(8)],
            counting_responder,
            max_iterations=100,
            max_seconds=0.5,
            clock=clock,
            sleep=sleep,
            pace_seconds=1.0,
        )
        # The first pacing sleep advances the clock to 1.0 >= 0.5, so nothing is
        # ever transmitted.
        self.assertEqual(calls["n"], 0)
        self.assertEqual(result.iterations, 0)
        self.assertEqual(result.stop_reason, "max_seconds")

    def test_pacing_delays_each_transmission(self) -> None:
        sleeps: list[float] = []

        def sleep(seconds: float) -> None:
            sleeps.append(seconds)

        result = run_guided_fuzz(
            [bytes(8)],
            _reactive_responder,
            max_iterations=3,
            sleep=sleep,
            pace_seconds=0.01,
            max_payload=8,
        )
        # One pacing delay precedes each of the three transmissions.
        self.assertEqual(sleeps, [0.01, 0.01, 0.01])
        self.assertEqual(result.iterations, 3)

    def test_corpus_persistence_round_trip(self) -> None:
        import tempfile

        result = run_guided_fuzz(
            [bytes(8)], _reactive_responder, max_iterations=120, rng_seed=4, max_payload=8
        )
        with tempfile.TemporaryDirectory() as tmp:
            save_corpus(tmp, result.seeds)
            self.assertTrue((Path(tmp) / "lineage.json").is_file())
            loaded = load_corpus(tmp)
            self.assertEqual(len(loaded), result.corpus_size)


class CliTests(unittest.TestCase):
    def test_dry_run_plans_without_transport(self) -> None:
        exit_code, stdout, _ = run_cli(
            "fuzz", "guided", "--id", "0x123", "--dry-run", "--max-iterations", "50", "--json"
        )
        self.assertEqual(exit_code, 0)
        data = json.loads(stdout)["data"]
        self.assertEqual(data["mode"], "dry_run")
        self.assertEqual(data["initial_seed_count"], 1)
        self.assertTrue(data["planned_mutations"])

    def test_invalid_signals_error(self) -> None:
        exit_code, stdout, _ = run_cli(
            "fuzz", "guided", "--id", "0x123", "--signals", "nope", "--dry-run", "--json"
        )
        self.assertEqual(exit_code, 1)
        self.assertEqual(json.loads(stdout)["errors"][0]["code"], "FUZZ_GUIDED_INVALID_SIGNALS")

    def test_invalid_id_error(self) -> None:
        exit_code, stdout, _ = run_cli("fuzz", "guided", "--id", "not-an-id", "--dry-run", "--json")
        self.assertEqual(exit_code, 1)
        self.assertEqual(json.loads(stdout)["errors"][0]["code"], "FUZZ_GUIDED_INVALID_ID")

    def test_invalid_max_corpus_error(self) -> None:
        exit_code, stdout, _ = run_cli(
            "fuzz", "guided", "--id", "0x123", "--max-corpus", "0", "--dry-run", "--json"
        )
        self.assertEqual(exit_code, 1)
        self.assertEqual(json.loads(stdout)["errors"][0]["code"], "FUZZ_GUIDED_INVALID_MAX_CORPUS")

    def test_29bit_id_without_extended_infers_extended(self) -> None:
        # A 29-bit --id without --extended runs as an extended frame instead of
        # crashing with an uncaught CanFrame ValueError (Codex review on #350).
        with patch.dict(
            os.environ,
            {"CANARCHY_TRANSPORT_BACKEND": "scaffold", "CANARCHY_MCP_NONINTERACTIVE_ACK": "1"},
        ):
            exit_code, stdout, _ = run_cli(
                "fuzz",
                "guided",
                "vcan0",
                "--id",
                "0x18DAF110",
                "--ack-active",
                "--max-iterations",
                "2",
                "--json",
            )
        self.assertEqual(exit_code, 0)
        data = json.loads(stdout)["data"]
        self.assertEqual(data["mode"], "active")
        self.assertTrue(data["extended"])

    def test_dry_run_infers_extended_for_29bit_id(self) -> None:
        exit_code, stdout, _ = run_cli(
            "fuzz", "guided", "--id", "0x18DAF110", "--dry-run", "--json"
        )
        self.assertEqual(exit_code, 0)
        self.assertTrue(json.loads(stdout)["data"]["extended"])

    def test_id_above_29bit_range_returns_structured_error(self) -> None:
        exit_code, stdout, _ = run_cli(
            "fuzz", "guided", "--id", "0x20000000", "--dry-run", "--json"
        )
        self.assertEqual(exit_code, 1)
        self.assertEqual(json.loads(stdout)["errors"][0]["code"], "FUZZ_GUIDED_INVALID_ID")

    def test_active_path_over_scaffold_backend(self) -> None:
        with patch.dict(
            os.environ,
            {"CANARCHY_TRANSPORT_BACKEND": "scaffold", "CANARCHY_MCP_NONINTERACTIVE_ACK": "1"},
        ):
            exit_code, stdout, _ = run_cli(
                "fuzz",
                "guided",
                "vcan0",
                "--id",
                "0x123",
                "--ack-active",
                "--max-iterations",
                "20",
                "--json",
            )
        self.assertEqual(exit_code, 0)
        data = json.loads(stdout)["data"]
        self.assertEqual(data["mode"], "active")
        self.assertEqual(data["iterations"], 20)
        self.assertEqual(data["stop_reason"], "max_iterations")


class McpGateTests(unittest.TestCase):
    def test_tool_is_active_gated(self) -> None:
        import asyncio

        from canarchy.mcp_server import _ACTIVE_TRANSMIT_TOOLS, _TOOL_NAMES, handle_call_tool

        self.assertIn("fuzz_guided", _TOOL_NAMES)
        self.assertIn("fuzz_guided", _ACTIVE_TRANSMIT_TOOLS)
        # Without ack_active the MCP gate refuses before any transport call.
        result = asyncio.run(handle_call_tool("fuzz_guided", {"id": "0x123"}))
        payload = json.loads(result[0].text)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["errors"][0]["code"], "ACTIVE_TRANSMIT_REQUIRES_ACK")

    def test_argv_defaults_to_dry_run(self) -> None:
        from canarchy.mcp_server import _build_argv

        argv = _build_argv("fuzz_guided", {"id": "0x123", "ack_active": True})
        self.assertIn("--ack-active", argv)
        self.assertIn("--dry-run", argv)
