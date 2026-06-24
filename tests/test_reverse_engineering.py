from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from canarchy.models import CanFrame
from canarchy.reverse_engineering import (
    ReferenceSeriesError,
    anomaly_candidates,
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


class AnomalyCandidatesTests(unittest.TestCase):
    """Unit tests for the anomaly detector (#321)."""

    def _frames(self, name: str):
        return LocalTransport().frames_from_file(str(FIXTURES / name))

    def test_baseline_flags_timing_unknown_and_dropped(self) -> None:
        frames = self._frames("anomaly_input.candump")
        baseline = self._frames("anomaly_baseline.candump")
        result = anomaly_candidates(frames, baseline=baseline)

        self.assertEqual(result["mode"], "baseline")
        kinds = {c["kind"]: c for c in result["candidates"]}
        self.assertIn("timing", kinds)
        self.assertIn("unknown-id", kinds)
        self.assertIn("dropped-id", kinds)
        # 0x100 has the big timing glitch; 0x300 is new; 0x200 dropped.
        self.assertEqual(kinds["timing"]["arbitration_id"], 0x100)
        self.assertEqual(kinds["unknown-id"]["arbitration_id"], 0x300)
        self.assertEqual(kinds["dropped-id"]["arbitration_id"], 0x200)
        self.assertGreaterEqual(abs(kinds["timing"]["z_score"]), 3.0)

    def test_self_consistency_flags_internal_glitch(self) -> None:
        frames = self._frames("anomaly_input.candump")
        result = anomaly_candidates(frames)

        self.assertEqual(result["mode"], "self-consistency")
        # No id-presence anomalies without a separate baseline.
        kinds = {c["kind"] for c in result["candidates"]}
        self.assertNotIn("unknown-id", kinds)
        self.assertNotIn("dropped-id", kinds)
        timing = [c for c in result["candidates"] if c["kind"] == "timing"]
        self.assertTrue(timing)
        self.assertEqual(timing[0]["arbitration_id"], 0x100)

    def test_event_traffic_is_not_flagged(self) -> None:
        # 0x400 is event-based (bursts then long silences); the CV guard must
        # classify it as event and skip timing analysis entirely.
        frames = self._frames("anomaly_event_mix.candump")
        result = anomaly_candidates(frames)

        self.assertIn(0x400, result["event_ids"])
        self.assertIn(0x100, result["cyclic_ids"])
        flagged_ids = {c["arbitration_id"] for c in result["candidates"]}
        self.assertNotIn(0x400, flagged_ids)

    def test_robust_stats_resist_outlier_masking(self) -> None:
        # A single huge gap must not inflate the spread enough to hide itself.
        frames = self._frames("anomaly_input.candump")
        result = anomaly_candidates(frames, z_threshold=3.0)
        self.assertTrue(any(c["kind"] == "timing" for c in result["candidates"]))

    def test_high_z_threshold_suppresses_timing(self) -> None:
        frames = self._frames("anomaly_input.candump")
        result = anomaly_candidates(frames, z_threshold=1e9)
        self.assertFalse(any(c["kind"] == "timing" for c in result["candidates"]))

    def test_dbc_send_type_overrides_event_classification(self) -> None:
        # 0x400 looks periodic in this capture, but the DBC marks it event:
        # the DBC classification is authoritative, so it is skipped.
        from canarchy.dbc import database_timing_map

        frames = self._frames("anomaly_dbc_capture.candump")
        timing = database_timing_map(str(FIXTURES / "anomaly_timing.dbc"))
        result = anomaly_candidates(frames, dbc_timing=timing)

        self.assertEqual(result["timing_source"], "dbc")
        self.assertIn(0x400, result["event_ids"])
        self.assertIn(0x100, result["cyclic_ids"])
        flagged = {c["arbitration_id"] for c in result["candidates"] if c["kind"] == "timing"}
        self.assertIn(0x100, flagged)
        self.assertNotIn(0x400, flagged)


class AnomalyAvailabilityTests(unittest.TestCase):
    """Rate-drop/spike and entropy-collapse detection vs a baseline (#457)."""

    @staticmethod
    def _varying(arb_id: int, count: int, period: float, *, start: float = 0.0):
        # Frames whose payload changes every frame (high byte entropy).
        return [
            CanFrame(
                arbitration_id=arb_id,
                data=bytes(((i * 37 + b * 53) & 0xFF) for b in range(8)),
                timestamp=start + i * period,
            )
            for i in range(count)
        ]

    @staticmethod
    def _frozen(arb_id: int, count: int, period: float, *, start: float = 0.0):
        # Frames whose payload never changes (zero byte entropy).
        return [
            CanFrame(
                arbitration_id=arb_id,
                data=b"\xde\xad\xbe\xef\x00\x00\x00\x00",
                timestamp=start + i * period,
            )
            for i in range(count)
        ]

    def test_entropy_collapse_flags_frozen_payload(self) -> None:
        baseline = self._varying(0x300, 100, 0.05)
        attack = self._frozen(0x300, 100, 0.05)
        result = anomaly_candidates(attack, baseline=baseline)

        collapse = [c for c in result["candidates"] if c["kind"] == "entropy-collapse"]
        self.assertEqual(len(collapse), 1)
        self.assertEqual(collapse[0]["arbitration_id"], 0x300)
        self.assertGreater(collapse[0]["score"], 0.0)

    def test_no_entropy_collapse_when_payload_unchanged(self) -> None:
        baseline = self._varying(0x300, 100, 0.05)
        attack = self._varying(0x300, 100, 0.05)
        result = anomaly_candidates(attack, baseline=baseline)
        self.assertFalse(any(c["kind"] == "entropy-collapse" for c in result["candidates"]))

    def test_rate_drop_flags_suppressed_id(self) -> None:
        baseline = self._varying(0x200, 240, 0.02)  # ~50 Hz over ~4.8 s
        attack = self._varying(0x200, 80, 0.06)  # ~16.6 Hz over ~4.7 s
        result = anomaly_candidates(attack, baseline=baseline)

        drops = [c for c in result["candidates"] if c["kind"] == "rate-drop"]
        self.assertEqual(len(drops), 1)
        self.assertEqual(drops[0]["arbitration_id"], 0x200)

    def test_rate_spike_flags_injected_id(self) -> None:
        baseline = self._varying(0x200, 50, 0.1)  # ~10 Hz
        attack = self._varying(0x200, 250, 0.02)  # ~50 Hz
        result = anomaly_candidates(attack, baseline=baseline)

        spikes = [c for c in result["candidates"] if c["kind"] == "rate-spike"]
        self.assertEqual(len(spikes), 1)
        self.assertEqual(spikes[0]["arbitration_id"], 0x200)

    def test_availability_anomalies_require_baseline(self) -> None:
        # Self-consistency mode emits neither rate nor entropy anomalies.
        attack = self._frozen(0x300, 100, 0.05)
        result = anomaly_candidates(attack)
        kinds = {c["kind"] for c in result["candidates"]}
        self.assertNotIn("entropy-collapse", kinds)
        self.assertNotIn("rate-drop", kinds)
        self.assertNotIn("rate-spike", kinds)

    def test_thresholds_echoed_in_result(self) -> None:
        baseline = self._varying(0x100, 50, 0.05)
        result = anomaly_candidates(baseline, baseline=baseline, entropy_drop=0.3, rate_drop=0.25)
        self.assertEqual(result["entropy_drop"], 0.3)
        self.assertEqual(result["rate_drop"], 0.25)


class AnomaliesCliTests(unittest.TestCase):
    """CLI-level tests for `canarchy re anomalies`."""

    def test_cli_baseline_run_json_shape(self) -> None:
        from canarchy.cli import execute_command

        exit_code, result = execute_command(
            [
                "re",
                "anomalies",
                str(FIXTURES / "anomaly_input.candump"),
                "--baseline",
                str(FIXTURES / "anomaly_baseline.candump"),
                "--json",
            ]
        )
        self.assertEqual(exit_code, 0)
        assert result is not None
        self.assertTrue(result.ok)
        self.assertEqual(result.command, "re anomalies")
        data = result.data
        self.assertEqual(data["mode"], "baseline")
        for key in ("candidates", "candidate_count", "cyclic_ids", "event_ids", "timing_source"):
            self.assertIn(key, data)
        self.assertGreaterEqual(data["candidate_count"], 1)

    def test_cli_self_consistency_run(self) -> None:
        from canarchy.cli import execute_command

        exit_code, result = execute_command(
            ["re", "anomalies", str(FIXTURES / "anomaly_input.candump"), "--json"]
        )
        self.assertEqual(exit_code, 0)
        assert result is not None
        self.assertEqual(result.data["mode"], "self-consistency")

    def test_cli_dbc_flag_sets_timing_source(self) -> None:
        from canarchy.cli import execute_command

        exit_code, result = execute_command(
            [
                "re",
                "anomalies",
                str(FIXTURES / "anomaly_dbc_capture.candump"),
                "--dbc",
                str(FIXTURES / "anomaly_timing.dbc"),
                "--json",
            ]
        )
        self.assertEqual(exit_code, 0)
        assert result is not None
        self.assertEqual(result.data["timing_source"], "dbc")
        self.assertIn(0x400, result.data["event_ids"])

    def test_cli_rejects_out_of_range_rate_drop(self) -> None:
        from canarchy.cli import execute_command

        exit_code, result = execute_command(
            [
                "re",
                "anomalies",
                str(FIXTURES / "anomaly_input.candump"),
                "--rate-drop",
                "1.5",
                "--json",
            ]
        )
        self.assertNotEqual(exit_code, 0)
        assert result is not None
        self.assertFalse(result.ok)
        self.assertEqual(result.errors[0]["code"], "INVALID_RATE_DROP")

    def test_cli_rejects_out_of_range_entropy_drop(self) -> None:
        from canarchy.cli import execute_command

        exit_code, result = execute_command(
            [
                "re",
                "anomalies",
                str(FIXTURES / "anomaly_input.candump"),
                "--entropy-drop",
                "0",
                "--json",
            ]
        )
        self.assertNotEqual(exit_code, 0)
        assert result is not None
        self.assertFalse(result.ok)
        self.assertEqual(result.errors[0]["code"], "INVALID_ENTROPY_DROP")


class J1939AnnotationTests(unittest.TestCase):
    """RE results carry PGN / source-address annotation for J1939 frames (#406)."""

    def _frames(self, name: str):
        return LocalTransport().frames_from_file(str(FIXTURES / name))

    def test_entropy_candidates_annotated_with_pgn_and_source_address(self) -> None:
        candidates = entropy_candidates(self._frames("re_j1939_tp_mix.candump"))

        ebc2 = next(c for c in candidates if c["arbitration_id"] == 0x18FEBF0B)
        self.assertEqual(ebc2["arbitration_id_hex"], "0x18FEBF0B")
        self.assertEqual(ebc2["pgn"], 65215)
        self.assertEqual(ebc2["pgn_label"], "EBC2")
        self.assertEqual(ebc2["source_address"], 11)
        self.assertEqual(ebc2["source_address_name"], "Brakes - System Controller")
        self.assertFalse(ebc2["j1939_transport"])

    def test_non_j1939_candidates_omit_annotation(self) -> None:
        candidates = entropy_candidates(self._frames("re_entropy_mixed.candump"))

        for candidate in candidates:
            self.assertIn("arbitration_id_hex", candidate)
            self.assertNotIn("pgn", candidate)
            self.assertNotIn("source_address", candidate)

    def test_counter_candidates_annotated(self) -> None:
        candidates = counter_candidates(self._frames("re_j1939_tp_mix.candump"))

        self.assertTrue(candidates)
        ebc2 = next(c for c in candidates if c["arbitration_id"] == 0x18FEBF0B)
        self.assertEqual(ebc2["pgn"], 65215)
        self.assertEqual(ebc2["pgn_label"], "EBC2")

    def test_corpus_coverage_annotated(self) -> None:
        from canarchy.corpus import corpus_analysis

        result = corpus_analysis([str(FIXTURES / "re_j1939_tp_mix.candump")])
        ebc2 = next(entry for entry in result["coverage"] if entry["arbitration_id"] == 0x18FEBF0B)
        self.assertEqual(ebc2["pgn"], 65215)
        self.assertEqual(ebc2["pgn_label"], "EBC2")
        self.assertEqual(ebc2["source_address_name"], "Brakes - System Controller")


class J1939TransportAwareTests(unittest.TestCase):
    """RE heuristics must not report J1939 TP framing as discoveries (#407)."""

    def _frames(self, name: str):
        return LocalTransport().frames_from_file(str(FIXTURES / name))

    def test_tp_dt_sequence_number_not_reported_as_counter(self) -> None:
        candidates = counter_candidates(self._frames("re_j1939_tp_mix.candump"))

        flagged_ids = {c["arbitration_id"] for c in candidates}
        self.assertNotIn(0x18EBFF00, flagged_ids)  # TP.DT
        self.assertNotIn(0x18ECFF00, flagged_ids)  # TP.CM
        # The genuine application counter is still found.
        self.assertIn(0x18FEBF0B, flagged_ids)

    def test_tp_frames_not_reported_as_signals(self) -> None:
        analysis = signal_analysis(self._frames("re_j1939_tp_mix.candump"))

        flagged_ids = {c["arbitration_id"] for c in analysis["candidates"]}
        self.assertNotIn(0x18EBFF00, flagged_ids)
        self.assertNotIn(0x18ECFF00, flagged_ids)
        excluded = {entry["arbitration_id"] for entry in analysis["excluded_transport_ids"]}
        self.assertEqual(excluded, {0x18EBFF00, 0x18ECFF00})
        labels = {entry["pgn_label"] for entry in analysis["excluded_transport_ids"]}
        self.assertEqual(labels, {"TP.DT", "TP.CM.xx"})

    def test_tp_entropy_candidates_labeled_as_transport(self) -> None:
        candidates = entropy_candidates(self._frames("re_j1939_tp_mix.candump"))

        tp_dt = next(c for c in candidates if c["arbitration_id"] == 0x18EBFF00)
        self.assertTrue(tp_dt["j1939_transport"])
        self.assertIn("transport-protocol framing", tp_dt["rationale"])


class AnomalySparseIdTests(unittest.TestCase):
    """No-baseline anomalies: sparse ids are low-rate, z-scores bounded (#408)."""

    def _frames(self, name: str):
        return LocalTransport().frames_from_file(str(FIXTURES / name))

    def test_sparse_bursty_id_reported_low_rate_not_ranked(self) -> None:
        result = anomaly_candidates(self._frames("anomaly_sparse_burst.candump"))

        self.assertEqual(result["mode"], "self-consistency")
        self.assertEqual(result["min_samples"], 10)
        flagged_ids = {c["arbitration_id"] for c in result["candidates"]}
        self.assertNotIn(0x18FECA0B, flagged_ids)
        self.assertIn(0x18FECA0B, result["low_rate_ids"])
        sparse = next(c for c in result["classifications"] if c["arbitration_id"] == 0x18FECA0B)
        self.assertEqual(sparse["source"], "low-sample")
        self.assertTrue(sparse["low_rate"])

    def test_reported_z_scores_are_capped(self) -> None:
        result = anomaly_candidates(self._frames("anomaly_sparse_burst.candump"))

        dropout = next(c for c in result["candidates"] if c["arbitration_id"] == 0x18FEF100)
        self.assertEqual(dropout["kind"], "timing")
        self.assertLessEqual(abs(dropout["z_score"]), 100.0)
        self.assertLessEqual(dropout["score"], 100.0)
        self.assertTrue(dropout["z_score_capped"])
        self.assertIn("capped", dropout["rationale"])

    def test_baseline_mode_keeps_lower_minimum(self) -> None:
        frames = self._frames("anomaly_input.candump")
        baseline = self._frames("anomaly_baseline.candump")
        result = anomaly_candidates(frames, baseline=baseline)
        self.assertEqual(result["min_samples"], 3)

    def test_min_samples_override(self) -> None:
        result = anomaly_candidates(self._frames("anomaly_sparse_burst.candump"), min_samples=3)
        flagged_ids = {c["arbitration_id"] for c in result["candidates"]}
        self.assertIn(0x18FECA0B, flagged_ids)

    def test_dropped_j1939_id_from_baseline_is_annotated(self) -> None:
        # An id present only in the baseline still gets J1939 annotation on
        # its dropped-id candidate (annotations include baseline frames).
        from canarchy.models import CanFrame

        def _ebc2(t: float) -> CanFrame:
            return CanFrame(
                arbitration_id=0x18FEBF0B,
                data=bytes(8),
                timestamp=t,
                is_extended_id=True,
            )

        def _other(t: float) -> CanFrame:
            return CanFrame(
                arbitration_id=0x18F00400,
                data=bytes(8),
                timestamp=t,
                is_extended_id=True,
            )

        baseline = [_ebc2(0.01 * i) for i in range(12)] + [_other(0.01 * i) for i in range(12)]
        frames = [_other(0.01 * i) for i in range(12)]

        result = anomaly_candidates(frames, baseline=baseline)

        dropped = next(c for c in result["candidates"] if c["kind"] == "dropped-id")
        self.assertEqual(dropped["arbitration_id"], 0x18FEBF0B)
        self.assertEqual(dropped["pgn"], 65215)
        self.assertEqual(dropped["pgn_label"], "EBC2")
        self.assertEqual(dropped["source_address"], 11)


class FileArgumentConventionTests(unittest.TestCase):
    """RE commands accept both positional and --file capture paths (#412)."""

    def _run(self, *argv: str):
        from canarchy.cli import execute_command

        return execute_command([*argv, "--json"])

    def test_re_commands_accept_file_flag(self) -> None:
        capture = str(FIXTURES / "re_entropy_mixed.candump")
        for argv in (
            ["re", "signals", "--file", capture],
            ["re", "counters", "--file", capture],
            ["re", "entropy", "--file", capture],
            ["re", "anomalies", "--file", capture],
        ):
            with self.subTest(argv=argv):
                exit_code, result = self._run(*argv)
                self.assertEqual(exit_code, 0)
                self.assertTrue(result.ok)
                self.assertEqual(result.data["file"], capture)

    def test_re_match_dbc_accepts_file_flag(self) -> None:
        capture = str(FIXTURES / "re_entropy_mixed.candump")
        exit_code, result = self._run("re", "match-dbc", "--file", capture)
        self.assertEqual(exit_code, 0)
        self.assertTrue(result.ok)
        self.assertEqual(result.data["capture"], capture)

    def test_re_corpus_accepts_repeated_file_flags(self) -> None:
        first = str(FIXTURES / "re_entropy_mixed.candump")
        second = str(FIXTURES / "re_signals_mixed.candump")
        exit_code, result = self._run("re", "corpus", "--file", first, "--file", second)
        self.assertEqual(exit_code, 0)
        self.assertTrue(result.ok)
        self.assertEqual(result.data["capture_count"], 2)

    def test_conflicting_file_forms_return_structured_error(self) -> None:
        first = str(FIXTURES / "re_entropy_mixed.candump")
        second = str(FIXTURES / "re_signals_mixed.candump")
        exit_code, result = self._run("re", "entropy", first, "--file", second)
        self.assertNotEqual(exit_code, 0)
        self.assertFalse(result.ok)
        self.assertEqual(result.errors[0]["code"], "CONFLICTING_FILE_ARGUMENTS")

    def test_missing_capture_returns_structured_error(self) -> None:
        exit_code, result = self._run("re", "entropy")
        self.assertNotEqual(exit_code, 0)
        self.assertFalse(result.ok)
        self.assertEqual(result.errors[0]["code"], "CAPTURE_FILE_REQUIRED")

    def test_matching_positional_and_flag_forms_are_accepted(self) -> None:
        capture = str(FIXTURES / "re_entropy_mixed.candump")
        exit_code, result = self._run("re", "entropy", capture, "--file", capture)
        self.assertEqual(exit_code, 0)
        self.assertTrue(result.ok)


class HexOutputConsistencyTests(unittest.TestCase):
    """All RE outputs carry arbitration_id_hex (#412)."""

    def _frames(self, name: str):
        return LocalTransport().frames_from_file(str(FIXTURES / name))

    def test_correlate_candidates_carry_hex(self) -> None:
        frames = self._frames("re_correlate_linear.candump")
        ref = load_reference_series(str(FIXTURES / "re_correlate_reference.json"))
        analysis = correlate_candidates(frames, ref)

        self.assertGreater(analysis["candidate_count"], 0)
        for candidate in analysis["candidates"]:
            self.assertEqual(candidate["arbitration_id_hex"], f"0x{candidate['arbitration_id']:X}")

    def test_signal_analysis_by_id_carries_hex(self) -> None:
        analysis = signal_analysis(self._frames("re_signals_mixed.candump"))

        self.assertTrue(analysis["analysis_by_id"])
        for entry in analysis["analysis_by_id"]:
            self.assertEqual(entry["arbitration_id_hex"], f"0x{entry['arbitration_id']:X}")
