"""Tests for the plugin registry, built-in processors, and CLI integration."""

from __future__ import annotations

import contextlib
import io
import json
import unittest
from pathlib import Path
from typing import Any, Iterator

from canarchy.models import CanFrame
from canarchy.plugins import (
    CANARCHY_API_VERSION,
    PluginError,
    PluginRegistry,
    ProcessorResult,
    get_registry,
    reset_registry,
)
from canarchy.transport import LocalTransport


FIXTURES = Path(__file__).parent / "fixtures"


def run_cli(*argv: str) -> tuple[int, str, str]:
    from canarchy.cli import main

    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = main(argv)
    return exit_code, stdout.getvalue(), stderr.getvalue()


def tearDownModule() -> None:
    reset_registry()


# ---------------------------------------------------------------------------
# Minimal stubs used across multiple tests
# ---------------------------------------------------------------------------


class _MinimalProcessor:
    name = "test-proc"
    api_version = CANARCHY_API_VERSION

    def process(self, frames: list[CanFrame], **kwargs: Any) -> ProcessorResult:
        return ProcessorResult(candidates=[], metadata={})


class _MinimalSink:
    name = "test-sink"
    api_version = CANARCHY_API_VERSION
    supported_formats = ["json"]

    def write(
        self, payload: dict[str, Any], destination: str, *, output_format: str = "json"
    ) -> dict[str, Any]:
        return {}


class _MinimalAdapter:
    name = "test-adapter"
    api_version = CANARCHY_API_VERSION
    supported_extensions = [".test"]

    def read(self, source: str) -> Iterator[CanFrame]:
        return iter([])


# ---------------------------------------------------------------------------
# TEST-PLUGIN-01  Default registry has all three built-in RE processors
# ---------------------------------------------------------------------------


class DefaultRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_registry()

    def tearDown(self) -> None:
        reset_registry()

    def test_builtin_processors_registered(self) -> None:
        registry = get_registry()
        for name in ("counter-candidates", "entropy-candidates", "signal-analysis"):
            with self.subTest(name=name):
                self.assertIsNotNone(registry.get_processor(name))

    def test_builtin_processor_api_versions(self) -> None:
        registry = get_registry()
        for name in ("counter-candidates", "entropy-candidates", "signal-analysis"):
            with self.subTest(name=name):
                proc = registry.get_processor(name)
                self.assertEqual(proc.api_version, CANARCHY_API_VERSION)

    def test_get_processor_unknown_returns_none(self) -> None:
        self.assertIsNone(get_registry().get_processor("nonexistent-processor"))

    def test_list_processors_contains_builtins(self) -> None:
        entries = get_registry().list_processors()
        names = {e["name"] for e in entries}
        self.assertIn("counter-candidates", names)
        self.assertIn("entropy-candidates", names)
        self.assertIn("signal-analysis", names)

    def test_list_processors_has_api_version(self) -> None:
        for entry in get_registry().list_processors():
            with self.subTest(name=entry["name"]):
                self.assertIn("api_version", entry)
                self.assertEqual(entry["api_version"], "1")

    def test_list_sinks_empty_by_default(self) -> None:
        self.assertEqual(get_registry().list_sinks(), [])

    def test_list_input_adapters_empty_by_default(self) -> None:
        self.assertEqual(get_registry().list_input_adapters(), [])

    def test_reset_causes_rebuild(self) -> None:
        first = get_registry()
        reset_registry()
        second = get_registry()
        self.assertIsNot(first, second)
        self.assertIsNotNone(second.get_processor("signal-analysis"))


# ---------------------------------------------------------------------------
# TEST-PLUGIN-04/05/06  Registration validation
# ---------------------------------------------------------------------------


class RegistrationValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = PluginRegistry()

    def test_duplicate_processor_raises_plugin_duplicate(self) -> None:
        self.registry.register_processor(_MinimalProcessor())
        with self.assertRaises(PluginError) as ctx:
            self.registry.register_processor(_MinimalProcessor())
        self.assertEqual(ctx.exception.code, "PLUGIN_DUPLICATE")

    def test_duplicate_sink_raises_plugin_duplicate(self) -> None:
        self.registry.register_sink(_MinimalSink())
        with self.assertRaises(PluginError) as ctx:
            self.registry.register_sink(_MinimalSink())
        self.assertEqual(ctx.exception.code, "PLUGIN_DUPLICATE")

    def test_duplicate_input_adapter_raises_plugin_duplicate(self) -> None:
        self.registry.register_input_adapter(_MinimalAdapter())
        with self.assertRaises(PluginError) as ctx:
            self.registry.register_input_adapter(_MinimalAdapter())
        self.assertEqual(ctx.exception.code, "PLUGIN_DUPLICATE")

    def test_incompatible_api_version_raises_plugin_incompatible(self) -> None:
        class BadVersion:
            name = "bad-version"
            api_version = "99"

            def process(self, frames: list[CanFrame], **kwargs: Any) -> ProcessorResult:
                return ProcessorResult(candidates=[], metadata={})

        with self.assertRaises(PluginError) as ctx:
            self.registry.register_processor(BadVersion())
        self.assertEqual(ctx.exception.code, "PLUGIN_INCOMPATIBLE")
        self.assertIn("99", str(ctx.exception))
        self.assertIn(CANARCHY_API_VERSION, str(ctx.exception))

    def test_invalid_processor_missing_process_raises_plugin_invalid(self) -> None:
        class NoProcessMethod:
            name = "no-process"
            api_version = CANARCHY_API_VERSION

        with self.assertRaises(PluginError) as ctx:
            self.registry.register_processor(NoProcessMethod())  # type: ignore[arg-type]
        self.assertEqual(ctx.exception.code, "PLUGIN_INVALID")

    def test_plugin_missing_name_attribute_raises_plugin_invalid(self) -> None:
        class NoNameAttr:
            api_version = CANARCHY_API_VERSION

            def process(self, frames: list[CanFrame], **kwargs: Any) -> ProcessorResult:
                return ProcessorResult(candidates=[], metadata={})

        with self.assertRaises(PluginError) as ctx:
            self.registry.register_processor(NoNameAttr())  # type: ignore[arg-type]
        self.assertEqual(ctx.exception.code, "PLUGIN_INVALID")

    def test_plugin_missing_name_does_not_raise_attribute_error(self) -> None:
        class NoNameAttr:
            api_version = CANARCHY_API_VERSION

        try:
            self.registry.register_processor(NoNameAttr())  # type: ignore[arg-type]
        except PluginError:
            pass
        except AttributeError:
            self.fail("register_processor raised AttributeError instead of PluginError")

    def test_incompatible_sink_version_raises_plugin_incompatible(self) -> None:
        class BadSinkVersion:
            name = "bad-sink"
            api_version = "0"
            supported_formats = ["json"]

            def write(self, payload: Any, destination: str, *, output_format: str = "json") -> dict:
                return {}

        with self.assertRaises(PluginError) as ctx:
            self.registry.register_sink(BadSinkVersion())
        self.assertEqual(ctx.exception.code, "PLUGIN_INCOMPATIBLE")

    def test_incompatible_adapter_version_raises_plugin_incompatible(self) -> None:
        class BadAdapterVersion:
            name = "bad-adapter"
            api_version = "2"
            supported_extensions = [".log"]

            def read(self, source: str) -> Iterator[CanFrame]:
                return iter([])

        with self.assertRaises(PluginError) as ctx:
            self.registry.register_input_adapter(BadAdapterVersion())
        self.assertEqual(ctx.exception.code, "PLUGIN_INCOMPATIBLE")


# ---------------------------------------------------------------------------
# TEST-PLUGIN-12/13/14  Built-in processor output shapes
# ---------------------------------------------------------------------------


class BuiltinProcessorOutputTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_registry()
        self.registry = get_registry()

    def tearDown(self) -> None:
        reset_registry()

    def test_counter_candidates_processor_output_shape(self) -> None:
        frames = LocalTransport().frames_from_file(str(FIXTURES / "re_counter_nibble.candump"))
        proc = self.registry.get_processor("counter-candidates")
        result = proc.process(frames)

        self.assertIsInstance(result, ProcessorResult)
        self.assertIsInstance(result.candidates, list)
        self.assertGreater(len(result.candidates), 0)
        self.assertEqual(result.metadata["analysis"], "counter_detection")
        self.assertIn("candidate_count", result.metadata)
        candidate = result.candidates[0]
        for key in ("arbitration_id", "start_bit", "bit_length", "score"):
            self.assertIn(key, candidate)

    def test_entropy_candidates_processor_output_shape(self) -> None:
        frames = LocalTransport().frames_from_file(str(FIXTURES / "re_entropy_mixed.candump"))
        proc = self.registry.get_processor("entropy-candidates")
        result = proc.process(frames)

        self.assertIsInstance(result, ProcessorResult)
        self.assertEqual(result.metadata["analysis"], "entropy_ranking")
        self.assertIn("candidate_count", result.metadata)
        self.assertIsInstance(result.warnings, list)

    def test_signal_analysis_processor_output_shape(self) -> None:
        frames = LocalTransport().frames_from_file(str(FIXTURES / "re_signals_mixed.candump"))
        proc = self.registry.get_processor("signal-analysis")
        result = proc.process(frames)

        self.assertIsInstance(result, ProcessorResult)
        self.assertEqual(result.metadata["analysis"], "signal_inference")
        self.assertIn("analysis_by_id", result.metadata)
        self.assertIn("low_sample_ids", result.metadata)
        self.assertIn("candidate_count", result.metadata)

    def test_processor_result_warnings_always_list(self) -> None:
        frames = LocalTransport().frames_from_file(str(FIXTURES / "re_counter_nibble.candump"))
        for name in ("counter-candidates", "entropy-candidates", "signal-analysis"):
            proc = self.registry.get_processor(name)
            result = proc.process(frames)
            with self.subTest(processor=name):
                self.assertIsInstance(result.warnings, list)

    def test_counter_processor_empty_input_returns_result(self) -> None:
        proc = self.registry.get_processor("counter-candidates")
        result = proc.process([])
        self.assertIsInstance(result, ProcessorResult)
        self.assertEqual(result.candidates, [])
        self.assertGreater(len(result.warnings), 0)

    def test_signal_processor_empty_input_returns_result(self) -> None:
        proc = self.registry.get_processor("signal-analysis")
        result = proc.process([])
        self.assertIsInstance(result, ProcessorResult)
        self.assertEqual(result.candidates, [])

    def test_entropy_processor_empty_input_returns_result(self) -> None:
        proc = self.registry.get_processor("entropy-candidates")
        result = proc.process([])
        self.assertIsInstance(result, ProcessorResult)
        self.assertEqual(result.candidates, [])


# ---------------------------------------------------------------------------
# TEST-PLUGIN-18  Custom third-party processor round-trip
# ---------------------------------------------------------------------------


class ThirdPartyProcessorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = PluginRegistry()

    def test_custom_processor_registered_and_callable(self) -> None:
        class CustomProc:
            name = "custom-proc"
            api_version = CANARCHY_API_VERSION

            def process(self, frames: list[CanFrame], **kwargs: Any) -> ProcessorResult:
                return ProcessorResult(
                    candidates=[{"count": len(frames)}],
                    metadata={"analysis": "custom"},
                )

        self.registry.register_processor(CustomProc())
        proc = self.registry.get_processor("custom-proc")
        self.assertIsNotNone(proc)
        self.assertEqual(proc.name, "custom-proc")

        result = proc.process([])
        self.assertIsInstance(result, ProcessorResult)
        self.assertEqual(result.candidates[0]["count"], 0)

    def test_custom_sink_registered_and_listable(self) -> None:
        self.registry.register_sink(_MinimalSink())
        entries = self.registry.list_sinks()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["name"], "test-sink")
        self.assertIn("supported_formats", entries[0])

    def test_custom_adapter_registered_and_listable(self) -> None:
        self.registry.register_input_adapter(_MinimalAdapter())
        entries = self.registry.list_input_adapters()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["name"], "test-adapter")
        self.assertIn("supported_extensions", entries[0])

    def test_entry_point_plugin_error_is_isolated_not_reraised(self) -> None:
        """A PluginError from a third-party entry point should warn, not blow up the registry."""
        import importlib.metadata
        from unittest.mock import MagicMock, patch

        bad_ep = MagicMock()
        bad_ep.name = "bad-third-party"
        bad_ep.load.side_effect = PluginError(
            code="PLUGIN_INCOMPATIBLE",
            message="bad plugin version",
        )

        with patch.object(importlib.metadata, "entry_points", return_value=[bad_ep]):
            import warnings as _warnings

            with _warnings.catch_warnings(record=True) as caught:
                _warnings.simplefilter("always")
                from canarchy.plugins import _load_entry_point_plugins

                _load_entry_point_plugins(self.registry)

        self.assertEqual(len(self.registry.list_processors()), 0)
        self.assertTrue(any("bad-third-party" in str(w.message) for w in caught))


# ---------------------------------------------------------------------------
# TEST-PLUGIN-15/16/17  CLI integration: RE commands route through registry
# ---------------------------------------------------------------------------


class CliIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_registry()

    def tearDown(self) -> None:
        reset_registry()

    def test_re_signals_returns_ok_json(self) -> None:
        code, out, _ = run_cli(
            "re", "signals", str(FIXTURES / "re_signals_mixed.candump"), "--json"
        )
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertTrue(data["ok"])
        self.assertIn("candidates", data["data"])
        self.assertIn("analysis_by_id", data["data"])

    def test_re_counters_returns_ok_json(self) -> None:
        code, out, _ = run_cli(
            "re", "counters", str(FIXTURES / "re_counter_nibble.candump"), "--json"
        )
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertTrue(data["ok"])
        self.assertGreater(len(data["data"]["candidates"]), 0)

    def test_re_entropy_returns_ok_json(self) -> None:
        code, out, _ = run_cli(
            "re", "entropy", str(FIXTURES / "re_entropy_mixed.candump"), "--json"
        )
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertTrue(data["ok"])
        self.assertIn("candidates", data["data"])

    def test_re_signals_mode_and_file_in_output(self) -> None:
        fixture = str(FIXTURES / "re_signals_mixed.candump")
        code, out, _ = run_cli("re", "signals", fixture, "--json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["data"]["mode"], "passive")
        self.assertEqual(data["data"]["file"], fixture)
