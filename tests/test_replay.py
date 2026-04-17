from __future__ import annotations

import unittest

from canarchy.replay import build_replay_plan
from canarchy.transport import LocalTransport


class ReplayTests(unittest.TestCase):
    def test_replay_plan_preserves_frame_count(self) -> None:
        frames = LocalTransport().frames_from_file("capture.log")
        plan = build_replay_plan(frames, rate=1.0)

        self.assertEqual(plan.frame_count, 3)
        self.assertEqual(len(plan.events), 3)
        self.assertEqual(plan.duration, 0.2)

    def test_replay_rate_scales_relative_timing(self) -> None:
        frames = LocalTransport().frames_from_file("capture.log")
        plan = build_replay_plan(frames, rate=0.5)

        self.assertEqual(plan.events[0]["timestamp"], 0.0)
        self.assertEqual(plan.events[1]["timestamp"], 0.2)
        self.assertEqual(plan.events[2]["timestamp"], 0.4)

    def test_empty_replay_plan_is_valid(self) -> None:
        plan = build_replay_plan([], rate=1.0)

        self.assertEqual(plan.frame_count, 0)
        self.assertEqual(plan.duration, 0.0)
        self.assertEqual(plan.events, [])
