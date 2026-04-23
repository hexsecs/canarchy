"""Performance benchmarks for J1939 commands."""

from __future__ import annotations

import time
import unittest
from pathlib import Path

FIXTURES = Path("tests/fixtures")


class J1939PerformanceTests(unittest.TestCase):
    """Performance tests for J1939 large-capture analysis."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = FIXTURES / "j1939_large_benchmark.candump"
        if not cls.fixture.exists():
            raise unittest.SkipTest(f"Benchmark fixture not found: {cls.fixture}")

    def _load_frames(self) -> list:
        from canarchy.transport import iter_candump_file

        return list(iter_candump_file(self.fixture))

    def test_j1939_summary_performance(self) -> None:
        from canarchy.j1939 import spn_observations, transport_protocol_sessions
        from canarchy.j1939 import dm1_messages

        frames = self._load_frames()
        start = time.perf_counter()
        _ = spn_observations(frames, spn=0)
        _ = transport_protocol_sessions(frames)
        _ = dm1_messages(frames)
        elapsed = time.perf_counter() - start

        self.assertLess(elapsed, 2.0, f"j1939 summary took {elapsed:.2f}s, expected < 2.0s")

    def test_j1939_decode_performance(self) -> None:
        from canarchy.j1939 import decompose_arbitration_id, spn_observations

        frames = self._load_frames()
        start = time.perf_counter()
        for frame in frames:
            decompose_arbitration_id(frame.arbitration_id)
            _ = spn_observations([frame], spn=0)
        elapsed = time.perf_counter() - start

        self.assertLess(elapsed, 3.0, f"j1939 decode took {elapsed:.2f}s, expected < 3.0s")

    def test_j1939_pgn_performance(self) -> None:
        from canarchy.j1939 import spn_observations

        frames = self._load_frames()
        start = time.perf_counter()
        _ = spn_observations(frames, spn=110)
        elapsed = time.perf_counter() - start

        self.assertLess(elapsed, 2.0, f"j1939 pgn took {elapsed:.2f}s, expected < 2.0s")

    def test_j1939_tp_performance(self) -> None:
        from canarchy.j1939 import transport_protocol_sessions

        frames = self._load_frames()
        start = time.perf_counter()
        _ = transport_protocol_sessions(frames)
        elapsed = time.perf_counter() - start

        self.assertLess(elapsed, 1.0, f"j1939 tp took {elapsed:.2f}s, expected < 1.0s")

    def test_j1939_dm1_performance(self) -> None:
        from canarchy.j1939 import dm1_messages

        frames = self._load_frames()
        start = time.perf_counter()
        _ = dm1_messages(frames)
        elapsed = time.perf_counter() - start

        self.assertLess(elapsed, 5.0, f"j1939 dm1 took {elapsed:.2f}s, expected < 5.0s")