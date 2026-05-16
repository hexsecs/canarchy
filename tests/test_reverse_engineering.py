from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from canarchy.reverse_engineering import (
    ReferenceSeriesError,
    correlate_candidates,
    counter_candidates,
    entropy_candidates,
    load_reference_series,
    score_dbc_candidates,
    signal_analysis,
)
from canarchy.transport import LocalTransport


FIXTURES = Path(__file__).parent / "fixtures"


class ReverseEngineeringTests(unittest.TestCase):
    def test_counter_candidates_detect_nibble_counter(self) -> None:
        frames = LocalTransport().frames_from_file(str(FIXTURES / "re_counter_nibble.candump"))

        candidates = counter_candidates(frames)

        self.assertGreater(len(candidates), 0)
        best = candidates[0]
        self.assertEqual(best["arbitration_id"], 0x123)
        self.assertEqual(best["start_bit"], 0)
        self.assertEqual(best["bit_length"], 4)
        self.assertEqual(best["sample_count"], 6)
        self.assertFalse(best["rollover_detected"])

    def test_counter_candidates_detect_byte_rollover(self) -> None:
        frames = LocalTransport().frames_from_file(str(FIXTURES / "re_counter_rollover.candump"))

        candidates = counter_candidates(frames)

        self.assertGreater(len(candidates), 0)
        rollover_candidate = next(
            candidate
            for candidate in candidates
            if candidate["arbitration_id"] == 0x200
            and candidate["start_bit"] == 8
            and candidate["bit_length"] == 8
        )
        self.assertTrue(rollover_candidate["rollover_detected"])
        self.assertEqual(rollover_candidate["observed_min"], 0)
        self.assertEqual(rollover_candidate["observed_max"], 255)

    def test_counter_candidates_reject_non_counter_field(self) -> None:
        frames = LocalTransport().frames_from_file(str(FIXTURES / "re_non_counter.candump"))

        candidates = counter_candidates(frames)

        self.assertEqual(candidates, [])

    def test_counter_candidates_ignore_low_sample_capture(self) -> None:
        frames = LocalTransport().frames_from_file(str(FIXTURES / "re_low_sample.candump"))

        candidates = counter_candidates(frames)

        self.assertEqual(candidates, [])

    def test_entropy_candidates_rank_ids_by_mean_byte_entropy(self) -> None:
        frames = LocalTransport().frames_from_file(str(FIXTURES / "re_entropy_mixed.candump"))

        candidates = entropy_candidates(frames)

        self.assertEqual(candidates[0]["arbitration_id"], 0x102)
        self.assertEqual(candidates[-1]["arbitration_id"], 0x100)
        self.assertGreater(candidates[1]["mean_byte_entropy"], candidates[2]["mean_byte_entropy"])

    def test_entropy_candidates_compute_expected_byte_entropies(self) -> None:
        frames = LocalTransport().frames_from_file(str(FIXTURES / "re_entropy_mixed.candump"))

        candidates = entropy_candidates(frames)

        constant = next(
            candidate for candidate in candidates if candidate["arbitration_id"] == 0x100
        )
        alternating = next(
            candidate for candidate in candidates if candidate["arbitration_id"] == 0x101
        )
        high_entropy = next(
            candidate for candidate in candidates if candidate["arbitration_id"] == 0x102
        )

        self.assertEqual(constant["mean_byte_entropy"], 0.0)
        self.assertEqual(constant["max_byte_entropy"], 0.0)
        self.assertEqual(alternating["byte_entropies"][0]["entropy"], 1.0)
        self.assertEqual(alternating["byte_entropies"][1]["entropy"], 0.0)
        self.assertEqual(alternating["mean_byte_entropy"], 0.5)
        self.assertEqual(high_entropy["byte_entropies"][0]["entropy"], 3.322)
        self.assertEqual(high_entropy["byte_entropies"][1]["entropy"], 3.322)

    def test_entropy_candidates_mark_low_sample_ids(self) -> None:
        frames = LocalTransport().frames_from_file(str(FIXTURES / "re_entropy_mixed.candump"))

        candidates = entropy_candidates(frames)

        low_sample = next(
            candidate for candidate in candidates if candidate["arbitration_id"] == 0x103
        )
        self.assertTrue(low_sample["low_sample"])
        self.assertEqual(low_sample["frame_count"], 5)

    def test_signal_analysis_returns_ranked_candidates(self) -> None:
        frames = LocalTransport().frames_from_file(str(FIXTURES / "re_signals_mixed.candump"))

        analysis = signal_analysis(frames)

        self.assertGreater(analysis["candidate_count"], 0)
        best = analysis["candidates"][0]
        self.assertEqual(best["arbitration_id"], 0x300)
        self.assertEqual(best["start_bit"], 8)
        self.assertEqual(best["bit_length"], 8)
        self.assertEqual(best["sample_count"], 10)
        self.assertAlmostEqual(best["change_rate"], 0.444, places=3)
        self.assertIn("preferred signal band", best["rationale"])

    def test_signal_analysis_marks_low_sample_ids(self) -> None:
        frames = LocalTransport().frames_from_file(str(FIXTURES / "re_signals_mixed.candump"))

        analysis = signal_analysis(frames)

        self.assertEqual(analysis["low_sample_ids"], [0x301])
        low_sample = next(
            item for item in analysis["analysis_by_id"] if item["arbitration_id"] == 0x301
        )
        self.assertTrue(low_sample["low_sample"])
        self.assertEqual(low_sample["frame_count"], 4)
        self.assertEqual(low_sample["candidate_count"], 0)


class ScoreDbcCandidatesTests(unittest.TestCase):
    def _make_catalog(self) -> list[dict]:
        return [
            {
                "name": "toyota_tnga_k_pt_generated",
                "source_ref": "opendbc:toyota_tnga_k_pt_generated",
                "message_ids": [0x100, 0x200, 0x300, 0x400, 0x500],
            },
            {
                "name": "toyota_nodsu_pt_generated",
                "source_ref": "opendbc:toyota_nodsu_pt_generated",
                "message_ids": [0x100, 0x200, 0x600],
            },
            {
                "name": "honda_accord",
                "source_ref": "opendbc:honda_accord",
                "message_ids": [0xAA0, 0xAA1, 0xAA2],
            },
        ]

    def test_score_returns_candidates_sorted_by_score_descending(self) -> None:
        # 0x100–0x500 are capture IDs; toyota_tnga matches 5/5, nodsu matches 2/5
        capture_ids = {0x100: 10, 0x200: 10, 0x300: 10, 0x400: 10, 0x500: 10}

        results = score_dbc_candidates(capture_ids, self._make_catalog())

        self.assertEqual(results[0]["name"], "toyota_tnga_k_pt_generated")
        self.assertGreater(results[0]["score"], results[1]["score"])

    def test_score_excludes_zero_match_candidates(self) -> None:
        capture_ids = {0x100: 1, 0x200: 1}

        results = score_dbc_candidates(capture_ids, self._make_catalog())

        names = [r["name"] for r in results]
        self.assertNotIn("honda_accord", names)

    def test_score_output_shape(self) -> None:
        capture_ids = {0x100: 5, 0x200: 5, 0x999: 40}

        results = score_dbc_candidates(capture_ids, self._make_catalog())

        self.assertTrue(results)
        top = results[0]
        self.assertIn("name", top)
        self.assertIn("source_ref", top)
        self.assertIn("score", top)
        self.assertIn("matched_ids", top)
        self.assertIn("total_capture_ids", top)
        self.assertEqual(top["total_capture_ids"], 3)

    def test_score_frequency_weighted(self) -> None:
        # toyota_tnga matches 0x100 (1 frame) and 0x200 (99 frames)
        # honda matches 0xAA0 (50 frames)
        capture_ids = {0x100: 1, 0x200: 99, 0xAA0: 50}

        results = score_dbc_candidates(capture_ids, self._make_catalog())

        tnga = next(r for r in results if r["name"] == "toyota_tnga_k_pt_generated")
        honda = next(r for r in results if r["name"] == "honda_accord")
        # toyota accounts for 100/150 frames, honda for 50/150
        self.assertGreater(tnga["score"], honda["score"])

    def test_score_empty_catalog_returns_empty(self) -> None:
        self.assertEqual(score_dbc_candidates({0x100: 1}, []), [])

    def test_score_empty_capture_ids_returns_empty(self) -> None:
        self.assertEqual(score_dbc_candidates({}, self._make_catalog()), [])

    def test_score_skips_catalog_entries_without_message_ids(self) -> None:
        catalog = [{"name": "no_ids", "source_ref": "opendbc:no_ids", "message_ids": []}]
        self.assertEqual(score_dbc_candidates({0x100: 1}, catalog), [])


class MatchDbcCliTests(unittest.TestCase):
    """Test CLI output shape for re match-dbc and re shortlist-dbc using mocked catalog."""

    _MOCK_CATALOG = [
        {
            "name": "toyota_tnga_k_pt_generated",
            "source_ref": "opendbc:toyota_tnga_k_pt_generated",
            "message_ids": [0x18FEEE31, 0x18F00431],
        },
        {
            "name": "honda_accord",
            "source_ref": "opendbc:honda_accord",
            "message_ids": [0x1234],
        },
    ]

    def test_re_match_dbc_json_output_shape(self) -> None:
        from canarchy.cli import execute_command

        with patch("canarchy.cli._build_match_catalog", return_value=self._MOCK_CATALOG):
            exit_code, result = execute_command(
                ["re", "match-dbc", str(FIXTURES / "sample.candump"), "--json"]
            )

        self.assertEqual(exit_code, 0)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(result.ok)
        self.assertEqual(result.command, "re match-dbc")
        data = result.data
        self.assertIn("capture", data)
        self.assertIn("provider", data)
        self.assertIn("candidate_count", data)
        self.assertIn("candidates", data)
        self.assertIn("events", data)

    def test_re_match_dbc_candidates_structure(self) -> None:
        from canarchy.cli import execute_command

        with patch("canarchy.cli._build_match_catalog", return_value=self._MOCK_CATALOG):
            _, result = execute_command(
                ["re", "match-dbc", str(FIXTURES / "sample.candump"), "--json"]
            )

        assert result is not None
        candidates = result.data["candidates"]
        self.assertTrue(len(candidates) > 0)
        top = candidates[0]
        self.assertIn("name", top)
        self.assertIn("source_ref", top)
        self.assertIn("score", top)
        self.assertIn("matched_ids", top)
        self.assertIn("total_capture_ids", top)

    def test_re_shortlist_dbc_json_output_shape(self) -> None:
        from canarchy.cli import execute_command

        with patch("canarchy.cli._build_match_catalog", return_value=self._MOCK_CATALOG):
            exit_code, result = execute_command(
                [
                    "re",
                    "shortlist-dbc",
                    str(FIXTURES / "sample.candump"),
                    "--make",
                    "toyota",
                    "--json",
                ]
            )

        self.assertEqual(exit_code, 0)
        assert result is not None
        self.assertTrue(result.ok)
        self.assertEqual(result.command, "re shortlist-dbc")
        self.assertIn("make", result.data)
        self.assertEqual(result.data["make"], "toyota")

    def test_re_match_dbc_empty_catalog_emits_warning(self) -> None:
        from canarchy.cli import execute_command

        with patch("canarchy.cli._build_match_catalog", return_value=[]):
            _, result = execute_command(
                ["re", "match-dbc", str(FIXTURES / "sample.candump"), "--json"]
            )

        assert result is not None
        self.assertTrue(result.ok)
        self.assertIsNotNone(result.warnings)
        assert result.warnings is not None
        self.assertTrue(len(result.warnings) > 0)

    def test_re_match_dbc_limit_respected(self) -> None:
        from canarchy.cli import execute_command

        catalog = [
            {
                "name": f"dbc_{i}",
                "source_ref": f"opendbc:dbc_{i}",
                "message_ids": [0x18FEEE31, 0x18F00431],
            }
            for i in range(20)
        ]

        with patch("canarchy.cli._build_match_catalog", return_value=catalog):
            _, result = execute_command(
                ["re", "match-dbc", str(FIXTURES / "sample.candump"), "--limit", "3", "--json"]
            )

        assert result is not None
        self.assertLessEqual(len(result.data["candidates"]), 3)


class LoadReferenceSeriesTests(unittest.TestCase):
    def test_load_json_array_returns_sorted_reference(self) -> None:
        ref = load_reference_series(str(FIXTURES / "re_correlate_reference.json"))

        self.assertEqual(len(ref), 20)
        self.assertIsNone(ref.name)
        self.assertAlmostEqual(ref.timestamps[0], 0.0)
        self.assertAlmostEqual(ref.values[0], 10.0)
        self.assertAlmostEqual(ref.timestamps[-1], 1.9, places=5)
        self.assertAlmostEqual(ref.values[-1], 48.0)

    def test_load_json_named_object_returns_name_and_samples(self) -> None:
        ref = load_reference_series(str(FIXTURES / "re_correlate_reference_named.json"))

        self.assertEqual(ref.name, "vehicle_speed_kph")
        self.assertEqual(len(ref), 20)

    def test_load_jsonl_format(self) -> None:
        ref = load_reference_series(str(FIXTURES / "re_correlate_reference.jsonl"))

        self.assertEqual(len(ref), 20)
        self.assertAlmostEqual(ref.values[0], 10.0)

    def test_missing_file_raises_invalid_reference_file(self) -> None:
        with self.assertRaises(ReferenceSeriesError) as ctx:
            load_reference_series(str(FIXTURES / "nonexistent_reference.json"))

        self.assertEqual(ctx.exception.code, "INVALID_REFERENCE_FILE")

    def test_malformed_json_raises_invalid_reference_file(self) -> None:
        with self.assertRaises(ReferenceSeriesError) as ctx:
            load_reference_series(str(FIXTURES / "re_correlate_reference_malformed.json"))

        self.assertEqual(ctx.exception.code, "INVALID_REFERENCE_FILE")

    def test_non_finite_value_raises_invalid_reference_file(self) -> None:
        with self.assertRaises(ReferenceSeriesError) as ctx:
            load_reference_series(str(FIXTURES / "re_correlate_reference_nan.json"))

        self.assertEqual(ctx.exception.code, "INVALID_REFERENCE_FILE")
        self.assertIn("non-finite", str(ctx.exception))

    def test_fewer_than_10_samples_raises_invalid_reference_file(self) -> None:
        with self.assertRaises(ReferenceSeriesError) as ctx:
            load_reference_series(str(FIXTURES / "re_correlate_reference_short.json"))

        self.assertEqual(ctx.exception.code, "INVALID_REFERENCE_FILE")
        self.assertIn("3 samples", str(ctx.exception))


class CorrelateCandidatesTests(unittest.TestCase):
    def _load_linear_fixture(self):
        frames = LocalTransport().frames_from_file(str(FIXTURES / "re_correlate_linear.candump"))
        ref = load_reference_series(str(FIXTURES / "re_correlate_reference.json"))
        return frames, ref

    def test_correlate_returns_candidate_for_linear_field(self) -> None:
        frames, ref = self._load_linear_fixture()

        result = correlate_candidates(frames, ref)

        self.assertGreater(result["candidate_count"], 0)
        # start_bit=8, bit_length=8 encodes the linear field
        byte1 = next(
            (
                c
                for c in result["candidates"]
                if c["arbitration_id"] == 0x400 and c["start_bit"] == 8 and c["bit_length"] == 8
            ),
            None,
        )
        self.assertIsNotNone(byte1)
        assert byte1 is not None
        self.assertAlmostEqual(byte1["pearson_r"], 1.0, places=3)
        self.assertAlmostEqual(byte1["spearman_r"], 1.0, places=3)
        self.assertEqual(byte1["sample_count"], 20)
        self.assertEqual(byte1["lag_ms"], 0.0)

    def test_correlate_output_shape(self) -> None:
        frames, ref = self._load_linear_fixture()

        result = correlate_candidates(frames, ref)

        self.assertIn("candidate_count", result)
        self.assertIn("candidates", result)
        top = result["candidates"][0]
        for key in (
            "arbitration_id",
            "start_bit",
            "bit_length",
            "pearson_r",
            "spearman_r",
            "sample_count",
            "lag_ms",
        ):
            self.assertIn(key, top)

    def test_correlate_sorted_by_absolute_pearson_r(self) -> None:
        frames, ref = self._load_linear_fixture()

        result = correlate_candidates(frames, ref)

        candidates = result["candidates"]
        for i in range(len(candidates) - 1):
            self.assertGreaterEqual(
                abs(candidates[i]["pearson_r"]), abs(candidates[i + 1]["pearson_r"])
            )

    def test_correlate_insufficient_overlap_raises_error(self) -> None:
        frames = LocalTransport().frames_from_file(str(FIXTURES / "re_correlate_linear.candump"))
        from canarchy.reverse_engineering import ReferenceData

        # Reference range [10.0, 20.0] does not overlap with capture timestamps [0.0, 1.9]
        ref = ReferenceData(
            name=None,
            timestamps=tuple(float(10 + i) for i in range(20)),
            values=tuple(float(i) for i in range(20)),
        )

        with self.assertRaises(ReferenceSeriesError) as ctx:
            correlate_candidates(frames, ref)

        self.assertEqual(ctx.exception.code, "INSUFFICIENT_OVERLAP")
