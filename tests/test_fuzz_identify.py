"""Tests for fuzz-replay culprit identification (canarchy.fuzz_identify)."""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from canarchy.fuzz_identify import (
    FuzzIdentifyError,
    load_identify_frames,
    load_observations_file,
    narrow,
    parse_observation,
)


class ObservationParsingTest(unittest.TestCase):
    def test_tokens(self) -> None:
        self.assertTrue(parse_observation("effect"))
        self.assertTrue(parse_observation(True))
        self.assertFalse(parse_observation("no-effect"))
        self.assertFalse(parse_observation(False))

    def test_invalid_token(self) -> None:
        with self.assertRaises(FuzzIdentifyError) as ctx:
            parse_observation("maybe")
        self.assertEqual(ctx.exception.code, "FUZZ_IDENTIFY_INVALID_OBSERVATION")


class NarrowTest(unittest.TestCase):
    def _drive_to_culprit(self, num_frames: int, culprit: int) -> int:
        """Simulate an oracle: a window reproduces the effect iff it covers culprit."""
        observations: list[bool] = []
        state = narrow(num_frames, observations)
        guard = 0
        while not state.resolved:
            guard += 1
            self.assertLess(guard, 64)
            lo, hi = state.next_window
            observations.append(lo <= culprit <= hi)
            state = narrow(num_frames, observations)
        return state.culprit

    def test_bisection_finds_each_frame(self) -> None:
        for num_frames in (1, 2, 5, 8, 17):
            for culprit in range(num_frames):
                with self.subTest(n=num_frames, culprit=culprit):
                    self.assertEqual(self._drive_to_culprit(num_frames, culprit), culprit)

    def test_initial_state_full_range(self) -> None:
        state = narrow(8, [])
        self.assertFalse(state.resolved)
        self.assertEqual((state.candidate_lo, state.candidate_hi), (0, 7))
        self.assertEqual(state.next_window, (0, 3))
        self.assertEqual(state.planned_rounds, 3)
        self.assertEqual(state.confidence, 0.0)

    def test_single_frame_resolves_immediately(self) -> None:
        state = narrow(1, [])
        self.assertTrue(state.resolved)
        self.assertEqual(state.culprit, 0)
        self.assertEqual(state.confidence, 1.0)

    def test_effect_narrows_lower_half(self) -> None:
        state = narrow(8, [True])
        self.assertEqual((state.candidate_lo, state.candidate_hi), (0, 3))
        self.assertEqual(state.rounds_completed, 1)

    def test_no_effect_narrows_upper_half(self) -> None:
        state = narrow(8, [False])
        self.assertEqual((state.candidate_lo, state.candidate_hi), (4, 7))

    def test_extra_observations_after_resolved_are_ignored(self) -> None:
        state = narrow(2, [True, True, True])
        self.assertTrue(state.resolved)
        self.assertEqual(state.culprit, 0)


class LoadFramesTest(unittest.TestCase):
    def _write(self, name: str, content: str) -> str:
        path = os.path.join(self.tmp, name)
        with open(path, "w") as handle:
            handle.write(content)
        return path

    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.tmp = self._dir.name

    def tearDown(self) -> None:
        self._dir.cleanup()

    def test_load_candump(self) -> None:
        path = self._write(
            "log.candump",
            "(0.0) can0 123#1122334455667788\n(0.1) can0 200#AABB\n",
        )
        frames = load_identify_frames(path)
        self.assertEqual(len(frames), 2)
        self.assertEqual(frames[0].arbitration_id, 0x123)

    def test_load_jsonl(self) -> None:
        lines = [
            json.dumps({"arbitration_id": 0x100, "data": "1122"}),
            json.dumps({"payload": {"arbitration_id": 0x101, "data": "33"}}),
        ]
        path = self._write("log.jsonl", "\n".join(lines) + "\n")
        frames = load_identify_frames(path)
        self.assertEqual([f.arbitration_id for f in frames], [0x100, 0x101])
        self.assertEqual(frames[1].data, b"\x33")

    def test_missing_file(self) -> None:
        with self.assertRaises(FuzzIdentifyError) as ctx:
            load_identify_frames(os.path.join(self.tmp, "nope.log"))
        self.assertEqual(ctx.exception.code, "FUZZ_IDENTIFY_LOG_UNAVAILABLE")

    def test_empty_log_is_invalid(self) -> None:
        path = self._write("empty.jsonl", "\n")
        with self.assertRaises(FuzzIdentifyError) as ctx:
            load_identify_frames(path)
        self.assertEqual(ctx.exception.code, "FUZZ_IDENTIFY_INVALID_LOG")

    def test_load_observations_file(self) -> None:
        path = self._write("obs.json", json.dumps(["no-effect", "effect", False]))
        self.assertEqual(load_observations_file(path), [False, True, False])

    def test_observations_file_must_be_array(self) -> None:
        path = self._write("obs.json", json.dumps({"a": 1}))
        with self.assertRaises(FuzzIdentifyError) as ctx:
            load_observations_file(path)
        self.assertEqual(ctx.exception.code, "FUZZ_IDENTIFY_INVALID_OBSERVATIONS")


if __name__ == "__main__":
    unittest.main()


def run_cli(*argv: str) -> tuple[int, str, str]:
    import contextlib
    import io

    from canarchy.cli import main

    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = main(argv)
    return exit_code, stdout.getvalue(), stderr.getvalue()


class FuzzIdentifyCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.log = os.path.join(self._dir.name, "fuzz.candump")
        with open(self.log, "w") as handle:
            for index in range(8):
                handle.write(f"({index}.0) can0 {0x100 + index:03X}#0{index}\n")

    def tearDown(self) -> None:
        self._dir.cleanup()

    def test_dry_run_plans_next_window(self) -> None:
        exit_code, stdout, _ = run_cli("fuzz", "identify", self.log, "--dry-run", "--json")
        self.assertEqual(exit_code, 0)
        data = json.loads(stdout)["data"]
        self.assertEqual(data["mode"], "dry_run")
        self.assertEqual(data["frame_count"], 8)
        self.assertEqual(data["next_window"], {"lo": 0, "hi": 3, "frame_count": 4})

    def test_observations_narrow_candidate(self) -> None:
        exit_code, stdout, _ = run_cli(
            "fuzz",
            "identify",
            self.log,
            "--observe",
            "no-effect",
            "--observe",
            "effect",
            "--dry-run",
            "--json",
        )
        self.assertEqual(exit_code, 0)
        data = json.loads(stdout)["data"]
        self.assertEqual(data["observations"], ["no-effect", "effect"])
        self.assertEqual((data["candidate_lo"], data["candidate_hi"]), (4, 5))

    def test_full_observations_resolve_culprit(self) -> None:
        # effect, effect, effect bisects 8 frames down to index 0.
        exit_code, stdout, _ = run_cli(
            "fuzz",
            "identify",
            self.log,
            "--observe",
            "effect",
            "--observe",
            "effect",
            "--observe",
            "effect",
            "--json",
        )
        self.assertEqual(exit_code, 0)
        data = json.loads(stdout)["data"]
        self.assertTrue(data["resolved"])
        self.assertEqual(data["mode"], "resolved")
        self.assertEqual(data["culprit"]["index"], 0)
        self.assertEqual(data["confidence"], 1.0)

    def test_observations_file(self) -> None:
        obs = os.path.join(self._dir.name, "obs.json")
        with open(obs, "w") as handle:
            json.dump(["no-effect"], handle)
        exit_code, stdout, _ = run_cli(
            "fuzz", "identify", self.log, "--observations", obs, "--dry-run", "--json"
        )
        self.assertEqual(exit_code, 0)
        data = json.loads(stdout)["data"]
        self.assertEqual((data["candidate_lo"], data["candidate_hi"]), (4, 7))

    def test_active_replays_window(self) -> None:
        from unittest.mock import patch

        with patch.dict(os.environ, {"CANARCHY_TRANSPORT_BACKEND": "scaffold"}):
            exit_code, stdout, stderr = run_cli(
                "fuzz", "identify", self.log, "--interface", "can0", "--rate", "100000", "--json"
            )
        self.assertEqual(exit_code, 0, stdout)
        self.assertIn("will replay a window of fuzz frames", stderr)
        data = json.loads(stdout)["data"]
        self.assertEqual(data["mode"], "active")
        self.assertEqual(data["replayed_window"], {"lo": 0, "hi": 3, "frame_count": 4})
        frame_events = [e for e in data["events"] if e["event_type"] == "frame"]
        self.assertEqual(len(frame_events), 4)

    def test_active_requires_ack_when_configured(self) -> None:
        from unittest.mock import patch

        with patch.dict(
            os.environ,
            {"CANARCHY_TRANSPORT_BACKEND": "scaffold", "CANARCHY_REQUIRE_ACTIVE_ACK": "1"},
        ):
            exit_code, stdout, _ = run_cli(
                "fuzz", "identify", self.log, "--interface", "can0", "--json"
            )
        self.assertEqual(exit_code, 1)
        self.assertEqual(json.loads(stdout)["errors"][0]["code"], "ACTIVE_ACK_REQUIRED")

    def test_window_too_large_is_user_error(self) -> None:
        exit_code, stdout, _ = run_cli(
            "fuzz", "identify", self.log, "--max-window", "2", "--dry-run", "--json"
        )
        self.assertEqual(exit_code, 1)
        self.assertEqual(json.loads(stdout)["errors"][0]["code"], "FUZZ_IDENTIFY_WINDOW_TOO_LARGE")

    def test_invalid_log_user_error(self) -> None:
        exit_code, stdout, _ = run_cli(
            "fuzz", "identify", os.path.join(self._dir.name, "nope.log"), "--dry-run", "--json"
        )
        self.assertEqual(exit_code, 1)
        self.assertEqual(json.loads(stdout)["errors"][0]["code"], "FUZZ_IDENTIFY_LOG_UNAVAILABLE")
