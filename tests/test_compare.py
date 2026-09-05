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

    def test_colliding_identifier_types_keep_independent_metrics(self) -> None:
        # Both forms use numeric 0x123; only the extended stream changes.
        for path, extended_times in ((self.baseline, range(5)), (self.attack, (0, 4))):
            rows = [(t, "123", "00") for t in range(5)]
            rows += [(t, "00000123", f"{t:02X}") for t in extended_times]
            path.write_text(
                "".join(
                    f"({t:.6f}) can0 {identifier}#{payload}\n"
                    for t, identifier, payload in sorted(rows)
                )
            )
        result = compare_captures([str(self.baseline), str(self.attack)], top=0)
        entries = {e["is_extended_id"]: e for e in result["comparison"]}
        self.assertEqual(result["id_count"], 2)
        self.assertEqual(result["summary"]["unique_ids"], 2)
        standard, extended = entries[False], entries[True]
        self.assertEqual(standard["frame_counts"], [5, 5])
        self.assertEqual(standard["rates_hz"], [1.25, 1.25])
        self.assertEqual(standard["mean_gap_ms"], [1000.0, 1000.0])
        self.assertEqual(standard["mean_byte_entropy"], [0.0, 0.0])
        self.assertEqual(standard["flags"], [])
        self.assertNotIn("pgn", standard)
        self.assertEqual(extended["frame_counts"], [5, 2])
        self.assertEqual(extended["rates_hz"], [1.25, 0.5])
        self.assertEqual(extended["mean_gap_ms"], [1000.0, 4000.0])
        self.assertGreater(extended["mean_byte_entropy"][0], 2.0)
        self.assertEqual(extended["mean_byte_entropy"][1], 1.0)
        self.assertEqual(set(extended["flags"]), {"rate-drop", "entropy-collapse", "timing-drift"})
        for category in ("rate_drop", "entropy_collapse", "timing_drift"):
            self.assertEqual(
                result["summary"][f"{category}_identifiers"],
                [{"arbitration_id": 0x123, "is_extended_id": True}],
            )
        self.assertEqual(result["comparison"][0], extended)

    def test_identifier_type_switch_is_new_and_dropped_through_cli(self) -> None:
        self.baseline.write_text("(0.0) can0 123#00\n(1.0) can0 123#01\n")
        self.attack.write_text("(0.0) can0 00000123#00\n(1.0) can0 00000123#01\n")
        code, result = execute_command(
            ["compare", str(self.baseline), str(self.attack), "--top", "1", "--json"]
        )
        self.assertEqual(code, 0)
        assert result is not None
        self.assertEqual(result.warnings, [])
        data = result.data
        self.assertEqual(data["id_count"], 2)
        self.assertEqual(data["returned_count"], 1)
        # Equal scores sort by numeric ID, then standard before extended.
        self.assertFalse(data["comparison"][0]["is_extended_id"])
        self.assertEqual(data["comparison"][0]["flags"], ["dropped-vs-baseline"])
        for category, extended in (("new", True), ("dropped", False)):
            self.assertEqual(data["summary"][f"{category}_ids"], [0x123])
            self.assertEqual(
                data["summary"][f"{category}_identifiers"],
                [{"arbitration_id": 0x123, "is_extended_id": extended}],
            )

    def test_numeric_summary_deduplicates_colliding_new_identifiers(self) -> None:
        self.baseline.write_text("(0.0) can0 456#00\n")
        self.attack.write_text("(0.0) can0 123#00\n(1.0) can0 00000123#00\n")
        result = compare_captures([str(self.baseline), str(self.attack)])
        self.assertEqual(result["summary"]["new_ids"], [0x123])
        self.assertEqual(
            result["summary"]["new_identifiers"],
            [
                {"arbitration_id": 0x123, "is_extended_id": False},
                {"arbitration_id": 0x123, "is_extended_id": True},
            ],
        )

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
