"""Tests for canarchy.plot and the plot CLI command."""

from __future__ import annotations

import contextlib
import io
import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

FIXTURES = Path(__file__).parent / "fixtures"


def run_cli(*argv: str) -> tuple[int, str, str]:
    from canarchy.cli import main

    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = main(argv)
    return exit_code, stdout.getvalue(), stderr.getvalue()


class DecodeSignalSeriesTests(unittest.TestCase):
    def test_decode_known_signal(self) -> None:
        from canarchy.plot import decode_signal_series

        result = decode_signal_series(
            str(FIXTURES / "complex.candump"),
            str(FIXTURES / "complex.dbc"),
            ["EngineSpeed"],
        )
        self.assertIsInstance(result, dict)
        self.assertIn("EngineSpeed", result)
        pts = result["EngineSpeed"]
        self.assertIsInstance(pts, list)
        self.assertTrue(len(pts) > 0)
        for ts, val in pts:
            self.assertIsInstance(ts, float)
            self.assertIsInstance(val, float)

    def test_decode_unknown_signal_returns_empty(self) -> None:
        from canarchy.plot import decode_signal_series

        result = decode_signal_series(
            str(FIXTURES / "complex.candump"),
            str(FIXTURES / "complex.dbc"),
            ["NoSuchSignal"],
        )
        self.assertIn("NoSuchSignal", result)
        self.assertEqual(result["NoSuchSignal"], [])

    def test_decode_respects_max_frames(self) -> None:
        from canarchy.plot import decode_signal_series

        result = decode_signal_series(
            str(FIXTURES / "complex.candump"),
            str(FIXTURES / "complex.dbc"),
            ["EngineSpeed"],
            max_frames=1,
        )
        self.assertLessEqual(len(result["EngineSpeed"]), 1)

    def test_decode_offset_skips_frames(self) -> None:
        from canarchy.plot import decode_signal_series

        result_no_offset = decode_signal_series(
            str(FIXTURES / "complex.candump"),
            str(FIXTURES / "complex.dbc"),
            ["EngineSpeed"],
            offset=0,
        )
        result_with_offset = decode_signal_series(
            str(FIXTURES / "complex.candump"),
            str(FIXTURES / "complex.dbc"),
            ["EngineSpeed"],
            offset=1000,
        )
        self.assertLessEqual(
            len(result_with_offset["EngineSpeed"]),
            len(result_no_offset["EngineSpeed"]),
        )


class PlotSignalsTests(unittest.TestCase):
    def test_plot_png_calls_savefig(self) -> None:
        from canarchy.plot import plot_signals

        mock_plt = MagicMock()
        mock_plt.subplots.return_value = (MagicMock(), MagicMock())
        with patch("canarchy.plot.plt", mock_plt):
            plot_signals(
                {"EngineSpeed": [(0.0, 100.0), (1.0, 200.0)]},
                output_path="/tmp/test.png",
                output_format="png",
            )
        mock_plt.savefig.assert_called_once_with("/tmp/test.png", format="png")

    def test_plot_svg_calls_savefig_svg(self) -> None:
        from canarchy.plot import plot_signals

        mock_plt = MagicMock()
        mock_plt.subplots.return_value = (MagicMock(), MagicMock())
        with patch("canarchy.plot.plt", mock_plt):
            plot_signals(
                {"EngineSpeed": [(0.0, 100.0), (1.0, 200.0)]},
                output_path="/tmp/test.svg",
                output_format="svg",
            )
        mock_plt.savefig.assert_called_once_with("/tmp/test.svg", format="svg")

    def test_plot_missing_matplotlib_raises(self) -> None:
        from canarchy.plot import PlotDependencyError, plot_signals

        with patch("canarchy.plot.plt", None):
            with self.assertRaises(PlotDependencyError) as ctx:
                plot_signals(
                    {"EngineSpeed": [(0.0, 100.0)]},
                    output_path="/tmp/test.png",
                    output_format="png",
                )
        self.assertIn("matplotlib", ctx.exception.dependency)

    def test_plot_missing_plotly_raises(self) -> None:
        from canarchy.plot import PlotDependencyError, plot_signals

        with patch("canarchy.plot._PLOTLY_AVAILABLE", False):
            with self.assertRaises(PlotDependencyError) as ctx:
                plot_signals(
                    {"EngineSpeed": [(0.0, 100.0)]},
                    output_path="/tmp/test.html",
                    output_format="html",
                )
        self.assertIn("plotly", ctx.exception.dependency)


class PlotCliTests(unittest.TestCase):
    def test_plot_missing_dependency_returns_error_json(self) -> None:
        with patch("canarchy.plot.plt", None):
            exit_code, stdout, _stderr = run_cli(
                "plot",
                "--file",
                str(FIXTURES / "complex.candump"),
                "--dbc",
                str(FIXTURES / "complex.dbc"),
                "--signal",
                "EngineSpeed",
                "--out",
                "/tmp/out.png",
                "--json",
            )
        self.assertNotEqual(exit_code, 0)
        payload = json.loads(stdout)
        self.assertFalse(payload["ok"])
        error_codes = [e["code"] for e in payload["errors"]]
        self.assertIn("PLOT_DEPENDENCY_MISSING", error_codes)

    def test_plot_success_returns_ok_json(self) -> None:
        mock_plt = MagicMock()
        mock_plt.subplots.return_value = (MagicMock(), MagicMock())
        with patch("canarchy.plot.plt", mock_plt):
            exit_code, stdout, _stderr = run_cli(
                "plot",
                "--file",
                str(FIXTURES / "complex.candump"),
                "--dbc",
                str(FIXTURES / "complex.dbc"),
                "--signal",
                "EngineSpeed",
                "--out",
                "/tmp/out.png",
                "--json",
            )
        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout)
        self.assertTrue(payload["ok"])
        data = payload["data"]
        self.assertIn("out", data)
        self.assertIn("signals", data)
        self.assertIn("signals_plotted", data)

    def test_plot_text_output(self) -> None:
        mock_plt = MagicMock()
        mock_plt.subplots.return_value = (MagicMock(), MagicMock())
        with patch("canarchy.plot.plt", mock_plt):
            exit_code, stdout, _stderr = run_cli(
                "plot",
                "--file",
                str(FIXTURES / "complex.candump"),
                "--dbc",
                str(FIXTURES / "complex.dbc"),
                "--signal",
                "EngineSpeed",
                "--out",
                "/tmp/out.png",
            )
        self.assertEqual(exit_code, 0)
        self.assertIn("command: plot", stdout)
        self.assertIn("out:", stdout)


class PlotProviderRefTests(unittest.TestCase):
    """`plot --dbc` resolves provider refs like decode/encode (#427)."""

    def test_local_path_resolves_and_reports_dbc_source(self) -> None:
        mock_plt = MagicMock()
        mock_plt.subplots.return_value = (MagicMock(), MagicMock())
        with patch("canarchy.plot.plt", mock_plt):
            exit_code, stdout, _ = run_cli(
                "plot",
                "--file",
                str(FIXTURES / "complex.candump"),
                "--dbc",
                str(FIXTURES / "complex.dbc"),
                "--signal",
                "EngineSpeed",
                "--out",
                "/tmp/plot_provider_ref.png",
                "--json",
            )
        self.assertEqual(exit_code, 0)
        data = json.loads(stdout)["data"]
        self.assertEqual(data["dbc_source"]["kind"], "dbc")

    def test_bad_provider_ref_returns_dbc_error_not_plot_error(self) -> None:
        exit_code, stdout, _ = run_cli(
            "plot",
            "--file",
            str(FIXTURES / "complex.candump"),
            "--dbc",
            "opendbc:does_not_exist_xyz",
            "--signal",
            "EngineSpeed",
            "--out",
            "/tmp/plot_bad_ref.png",
            "--json",
        )
        self.assertEqual(exit_code, 3)
        payload = json.loads(stdout)
        self.assertFalse(payload["ok"])
        code = payload["errors"][0]["code"]
        self.assertTrue(code.startswith("DBC_"))
        self.assertNotEqual(code, "PLOT_ERROR")
