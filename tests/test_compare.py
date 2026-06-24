from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from canarchy.cli import execute_command
from canarchy.compare import compare_captures


def _write_capture(path: Path, rows: list[tuple[float, int, bytes]]) -> None:
    with path.open("w") as handle:
        for timestamp, arb_id, data in rows:
            handle.write(f"({timestamp:.6f}) can0 {arb_id:03X}#{data.hex().upper()}\n")


def _varying(arb_id: int, count: int, period: float) -> list[tuple[float, int, bytes]]:
    return [
        (i * period, arb_id, bytes(((i * 37 + b * 53) & 0xFF) for b in range(8)))
        for i in range(count)
    ]


def _frozen(arb_id: int, count: int, period: float) -> list[tuple[float, int, bytes]]:
    return [(i * period, arb_id, b"\xde\xad\xbe\xef\x00\x00\x00\x00") for i in range(count)]


class CompareCapturesTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

        # Baseline: 0x100 steady, 0x200 ~50 Hz varying, 0x300 ~20 Hz varying.
        base_rows = (
            _varying(0x100, 100, 0.05) + _varying(0x200, 240, 0.02) + _varying(0x300, 100, 0.05)
        )
        base_rows.sort()
        self.baseline = self.tmp / "baseline.candump"
        _write_capture(self.baseline, base_rows)

        # Attack: 0x200 suppressed (~16 Hz), 0x300 frozen payload, 0x100 unchanged.
        attack_rows = (
            _varying(0x100, 100, 0.05) + _varying(0x200, 80, 0.06) + _frozen(0x300, 100, 0.05)
        )
        attack_rows.sort()
        self.attack = self.tmp / "attack.candump"
        _write_capture(self.attack, attack_rows)

    def test_compare_flags_rate_and_entropy_changes(self) -> None:
        result = compare_captures([str(self.baseline), str(self.attack)])
        flags = {entry["arbitration_id"]: entry["flags"] for entry in result["comparison"]}
        self.assertIn("rate-drop", flags[0x200])
        self.assertIn("entropy-collapse", flags[0x300])
        self.assertEqual(flags[0x100], [])
        self.assertIn(0x200, result["summary"]["rate_drop_ids"])
        self.assertIn(0x300, result["summary"]["entropy_collapse_ids"])

    def test_baseline_is_first_file_by_default(self) -> None:
        result = compare_captures([str(self.baseline), str(self.attack)])
        self.assertEqual(result["baseline"], str(self.baseline))
        self.assertEqual(result["baseline_index"], 0)
        entry = next(e for e in result["comparison"] if e["arbitration_id"] == 0x200)
        # Baseline column is the reference, so its ratio is 1.0.
        self.assertEqual(entry["rate_ratio"][0], 1.0)
        self.assertLess(entry["rate_ratio"][1], 0.5)

    def test_top_caps_comparison_but_keeps_total(self) -> None:
        result = compare_captures([str(self.baseline), str(self.attack)], top=1)
        self.assertEqual(result["id_count"], 3)
        self.assertEqual(result["returned_count"], 1)
        self.assertEqual(len(result["comparison"]), 1)

    def test_cli_compare_json_shape(self) -> None:
        exit_code, result = execute_command(
            ["compare", str(self.baseline), str(self.attack), "--json"]
        )
        self.assertEqual(exit_code, 0)
        assert result is not None
        self.assertTrue(result.ok)
        self.assertEqual(result.command, "compare")
        for key in ("comparison", "summary", "id_count", "baseline", "file_count"):
            self.assertIn(key, result.data)

    def test_cli_compare_requires_two_files(self) -> None:
        exit_code, result = execute_command(["compare", str(self.baseline), "--json"])
        self.assertNotEqual(exit_code, 0)
        assert result is not None
        self.assertFalse(result.ok)
        self.assertEqual(result.data.get("errors", result.errors)[0]["code"], "COMPARE_NEEDS_FILES")

    def test_cli_compare_accepts_repeated_file_flags(self) -> None:
        exit_code, result = execute_command(
            ["compare", "--file", str(self.baseline), "--file", str(self.attack), "--json"]
        )
        self.assertEqual(exit_code, 0)
        assert result is not None
        self.assertTrue(result.ok)
        self.assertEqual(result.data["file_count"], 2)


class ReCandidateTopTests(unittest.TestCase):
    """The shared --top cap for re_* candidate output (#459)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        rows: list[tuple[float, int, bytes]] = []
        for arb_id in range(0x100, 0x10A):  # 10 distinct ids
            rows += _varying(arb_id, 30, 0.05)
        rows.sort()
        self.capture = self.tmp / "many_ids.candump"
        _write_capture(self.capture, rows)

    def _run(self, sub: str, *extra: str):
        exit_code, result = execute_command(["re", sub, str(self.capture), *extra, "--json"])
        self.assertEqual(exit_code, 0)
        assert result is not None
        self.assertTrue(result.ok)
        return result.data

    def test_signals_top_caps_candidates(self) -> None:
        data = self._run("signals", "--top", "3")
        self.assertEqual(len(data["candidates"]), 3)
        self.assertEqual(data["returned_count"], 3)
        self.assertGreaterEqual(data["candidate_count"], data["returned_count"])

    def test_entropy_top_zero_returns_all(self) -> None:
        capped = self._run("entropy", "--top", "2")
        self.assertEqual(capped["returned_count"], 2)
        full = self._run("entropy", "--top", "0")
        self.assertEqual(full["returned_count"], full["candidate_count"])
        self.assertEqual(len(full["candidates"]), full["candidate_count"])

    def test_counters_top_present_in_payload(self) -> None:
        data = self._run("counters", "--top", "5")
        self.assertIn("returned_count", data)
        self.assertIn("top", data)
        self.assertEqual(data["top"], 5)


if __name__ == "__main__":
    unittest.main()
