from __future__ import annotations

import unittest
from pathlib import Path

from canarchy.reverse_engineering import counter_candidates, entropy_candidates
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

        constant = next(candidate for candidate in candidates if candidate["arbitration_id"] == 0x100)
        alternating = next(candidate for candidate in candidates if candidate["arbitration_id"] == 0x101)
        high_entropy = next(candidate for candidate in candidates if candidate["arbitration_id"] == 0x102)

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

        low_sample = next(candidate for candidate in candidates if candidate["arbitration_id"] == 0x103)
        self.assertTrue(low_sample["low_sample"])
        self.assertEqual(low_sample["frame_count"], 5)
