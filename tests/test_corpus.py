"""Tests for corpus.py and the `re corpus` CLI command."""

from __future__ import annotations

import contextlib
import io
import json
import unittest
from pathlib import Path

from canarchy.corpus import corpus_analysis

FIXTURES = Path(__file__).parent / "fixtures"


def run_cli(*argv: str) -> tuple[int, str, str]:
    from canarchy.cli import main

    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = main(argv)
    return exit_code, stdout.getvalue(), stderr.getvalue()


class CorpusAnalysisTests(unittest.TestCase):
    def test_single_capture_returns_valid_structure(self) -> None:
        result = corpus_analysis([str(FIXTURES / "complex.candump")])
        self.assertEqual(result["capture_count"], 1)
        for key in (
            "captures",
            "capture_count",
            "total_frames",
            "coverage",
            "id_set_changes",
            "cycle_time_drift",
            "signal_stability",
            "summary",
        ):
            self.assertIn(key, result)

    def test_two_captures_coverage_matrix(self) -> None:
        result = corpus_analysis(
            [
                str(FIXTURES / "complex.candump"),
                str(FIXTURES / "sample.candump"),
            ]
        )
        self.assertGreater(len(result["coverage"]), 0)
        for entry in result["coverage"]:
            self.assertEqual(len(entry["frame_counts"]), 2)

    def test_three_captures_summary_fields(self) -> None:
        result = corpus_analysis(
            [
                str(FIXTURES / "re_signals_mixed.candump"),
                str(FIXTURES / "re_counter_nibble.candump"),
                str(FIXTURES / "anomaly_input.candump"),
            ]
        )
        summary = result["summary"]
        for key in ("unique_ids", "stable_ids", "drifting_ids", "new_ids"):
            self.assertIn(key, summary)

    def test_id_set_changes_always_vs_sometimes(self) -> None:
        result = corpus_analysis(
            [
                str(FIXTURES / "complex.candump"),
                str(FIXTURES / "sample.candump"),
            ]
        )
        changes = result["id_set_changes"]
        always = set(changes["always_present"])
        sometimes = set(changes["sometimes_present"])
        only_one = set(changes["only_in_one"])
        self.assertTrue(always.isdisjoint(sometimes))
        self.assertTrue(always.isdisjoint(only_one))
        self.assertTrue(sometimes.isdisjoint(only_one))
        all_seen = {entry["arbitration_id"] for entry in result["coverage"]}
        self.assertTrue(always | sometimes | only_one <= all_seen)

    def test_signal_stability_scores_in_range(self) -> None:
        result = corpus_analysis(
            [
                str(FIXTURES / "re_signals_mixed.candump"),
                str(FIXTURES / "anomaly_baseline.candump"),
            ]
        )
        for entry in result["signal_stability"]:
            self.assertGreaterEqual(entry["stability_score"], 0.0)
            self.assertLessEqual(entry["stability_score"], 1.0)

    def test_cycle_time_drift_present_for_shared_ids(self) -> None:
        result = corpus_analysis(
            [
                str(FIXTURES / "complex.candump"),
                str(FIXTURES / "sample.candump"),
            ]
        )
        self.assertIn("cycle_time_drift", result)
        self.assertIsInstance(result["cycle_time_drift"], list)

    def test_offset_reduces_frame_count(self) -> None:
        path = str(FIXTURES / "complex.candump")
        full = corpus_analysis([path], offset=0)
        offset5 = corpus_analysis([path], offset=5)
        self.assertLessEqual(offset5["total_frames"], full["total_frames"])

    def test_empty_files_returns_zero_state(self) -> None:
        result = corpus_analysis([])
        self.assertEqual(result["capture_count"], 0)
        self.assertEqual(result["total_frames"], 0)
        self.assertEqual(result["coverage"], [])
        self.assertEqual(result["summary"]["unique_ids"], 0)


class CorpusCliTests(unittest.TestCase):
    def test_re_corpus_single_file_json(self) -> None:
        code, out, _ = run_cli("re", "corpus", str(FIXTURES / "complex.candump"), "--json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertTrue(data["ok"])
        self.assertIn("coverage", data["data"])
        self.assertIn("summary", data["data"])

    def test_re_corpus_two_files_json(self) -> None:
        code, out, _ = run_cli(
            "re",
            "corpus",
            str(FIXTURES / "complex.candump"),
            str(FIXTURES / "sample.candump"),
            "--json",
        )
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertTrue(data["ok"])
        self.assertEqual(data["data"]["capture_count"], 2)

    def test_re_corpus_no_files_returns_error(self) -> None:
        code, out, _ = run_cli("re", "corpus", "--json")
        self.assertNotEqual(code, 0)
        data = json.loads(out)
        self.assertFalse(data["ok"])
        error_codes = [e["code"] for e in data.get("errors", [])]
        self.assertIn("CORPUS_NO_FILES", error_codes)

    def test_re_corpus_text_output(self) -> None:
        code, out, _ = run_cli("re", "corpus", str(FIXTURES / "complex.candump"))
        self.assertEqual(code, 0)
        self.assertIn("command: re corpus", out)

    def test_re_corpus_warning_single_capture(self) -> None:
        code, out, _ = run_cli("re", "corpus", str(FIXTURES / "complex.candump"), "--json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        warnings = data.get("warnings", [])
        self.assertTrue(
            any("2+" in w for w in warnings),
            f"Expected a '2+' warning but got: {warnings}",
        )

    def test_re_corpus_negative_offset_rejected(self) -> None:
        code, out, _ = run_cli(
            "re", "corpus", str(FIXTURES / "complex.candump"), "--offset", "-1", "--json"
        )
        self.assertNotEqual(code, 0)
        data = json.loads(out)
        self.assertFalse(data["ok"])
        error_codes = [e["code"] for e in data.get("errors", [])]
        self.assertIn("INVALID_ANALYSIS_OFFSET", error_codes)

    def test_re_corpus_negative_max_frames_rejected(self) -> None:
        code, out, _ = run_cli(
            "re", "corpus", str(FIXTURES / "complex.candump"), "--max-frames", "-5", "--json"
        )
        self.assertNotEqual(code, 0)
        data = json.loads(out)
        self.assertFalse(data["ok"])
        error_codes = [e["code"] for e in data.get("errors", [])]
        self.assertIn("INVALID_MAX_FRAMES", error_codes)

    def test_re_corpus_negative_seconds_rejected(self) -> None:
        code, out, _ = run_cli(
            "re", "corpus", str(FIXTURES / "complex.candump"), "--seconds", "-1", "--json"
        )
        self.assertNotEqual(code, 0)
        data = json.loads(out)
        self.assertFalse(data["ok"])
        error_codes = [e["code"] for e in data.get("errors", [])]
        self.assertIn("INVALID_ANALYSIS_SECONDS", error_codes)


if __name__ == "__main__":
    unittest.main()
