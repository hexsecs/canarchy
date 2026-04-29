"""Tests for the dataset provider registry, catalog, cache, and convert pipeline."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from canarchy.dataset_catalog import PublicDatasetProvider
from canarchy.dataset_convert import ConversionError, convert_file, stream_file
from canarchy.dataset_provider import (
    DatasetDescriptor,
    DatasetError,
    DatasetProviderRegistry,
    get_registry,
    parse_dataset_ref,
    reset_registry,
)


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
# parse_dataset_ref
# ---------------------------------------------------------------------------

class ParseDatasetRefTests(unittest.TestCase):
    def test_prefixed_ref_splits_provider_and_name(self) -> None:
        provider, name = parse_dataset_ref("catalog:road")
        self.assertEqual(provider, "catalog")
        self.assertEqual(name, "road")

    def test_bare_ref_returns_none_provider(self) -> None:
        provider, name = parse_dataset_ref("road")
        self.assertIsNone(provider)
        self.assertEqual(name, "road")

    def test_colon_in_name_only_splits_on_first(self) -> None:
        provider, name = parse_dataset_ref("catalog:some:name")
        self.assertEqual(provider, "catalog")
        self.assertEqual(name, "some:name")


# ---------------------------------------------------------------------------
# PublicDatasetProvider
# ---------------------------------------------------------------------------

class PublicDatasetProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = PublicDatasetProvider()

    def test_provider_name_is_catalog(self) -> None:
        self.assertEqual(self.provider.name, "catalog")

    def test_search_empty_query_returns_all(self) -> None:
        results = self.provider.search("")
        self.assertGreater(len(results), 0)
        for r in results:
            self.assertIsInstance(r, DatasetDescriptor)

    def test_search_by_name_returns_match(self) -> None:
        results = self.provider.search("road")
        names = [r.name for r in results]
        self.assertIn("road", names)

    def test_search_by_protocol_returns_j1939(self) -> None:
        results = self.provider.search("j1939")
        protocols = [r.protocol_family for r in results]
        self.assertIn("j1939", protocols)

    def test_search_with_limit(self) -> None:
        results = self.provider.search("", limit=3)
        self.assertLessEqual(len(results), 3)

    def test_search_unknown_query_returns_empty(self) -> None:
        results = self.provider.search("xyzzy-nonexistent-query-12345")
        self.assertEqual(results, [])

    def test_inspect_returns_full_descriptor(self) -> None:
        desc = self.provider.inspect("road")
        self.assertEqual(desc.name, "road")
        self.assertEqual(desc.provider, "catalog")
        self.assertIsNotNone(desc.source_url)
        self.assertIsNotNone(desc.license)
        self.assertIsNotNone(desc.description)
        self.assertIsInstance(desc.formats, tuple)
        self.assertIsInstance(desc.conversion_targets, tuple)

    def test_inspect_unknown_raises_dataset_not_found(self) -> None:
        with self.assertRaises(DatasetError) as ctx:
            self.provider.inspect("nonexistent-dataset-xyz")
        self.assertEqual(ctx.exception.code, "DATASET_NOT_FOUND")

    def test_all_catalog_entries_have_required_fields(self) -> None:
        for desc in self.provider.search(""):
            with self.subTest(name=desc.name):
                self.assertTrue(desc.name)
                self.assertTrue(desc.source_url)
                self.assertTrue(desc.license)
                self.assertTrue(desc.protocol_family)
                self.assertTrue(desc.description)
                self.assertIsInstance(desc.formats, tuple)
                self.assertIsInstance(desc.conversion_targets, tuple)

    def test_syncan_is_in_catalog(self) -> None:
        desc = self.provider.inspect("syncan")
        self.assertEqual(desc.license, "MIT")
        self.assertIn("candump", desc.conversion_targets)

    def test_fetch_records_provenance_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch("canarchy.dataset_cache.cache_root", return_value=Path(tmp) / "cache"):
                resolution = self.provider.fetch("road")
            self.assertTrue(resolution.is_cached)
            self.assertTrue(resolution.cache_path.exists())
            self.assertIn("source_url", resolution.provenance)
            self.assertIn("fetched_at", resolution.provenance)
            self.assertEqual(resolution.provenance["provider"], "catalog")

    def test_refresh_returns_all_descriptors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch("canarchy.dataset_cache.cache_root", return_value=Path(tmp) / "cache"):
                descriptors = self.provider.refresh()
        self.assertGreater(len(descriptors), 0)
        for d in descriptors:
            self.assertIsInstance(d, DatasetDescriptor)


# ---------------------------------------------------------------------------
# DatasetProviderRegistry
# ---------------------------------------------------------------------------

class DatasetProviderRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_registry()

    def tearDown(self) -> None:
        reset_registry()

    def test_default_registry_has_catalog_provider(self) -> None:
        registry = get_registry()
        self.assertIsNotNone(registry.get_provider("catalog"))

    def test_list_providers_contains_catalog(self) -> None:
        registry = get_registry()
        names = [p["name"] for p in registry.list_providers()]
        self.assertIn("catalog", names)

    def test_search_delegates_to_catalog(self) -> None:
        registry = get_registry()
        results = registry.search("road")
        self.assertGreater(len(results), 0)

    def test_inspect_by_bare_name(self) -> None:
        registry = get_registry()
        desc = registry.inspect("road")
        self.assertEqual(desc.name, "road")

    def test_inspect_by_prefixed_ref(self) -> None:
        registry = get_registry()
        desc = registry.inspect("catalog:road")
        self.assertEqual(desc.name, "road")

    def test_inspect_unknown_provider_raises_dataset_provider_not_found(self) -> None:
        registry = get_registry()
        with self.assertRaises(DatasetError) as ctx:
            registry.inspect("noprovider:road")
        self.assertEqual(ctx.exception.code, "DATASET_PROVIDER_NOT_FOUND")

    def test_inspect_unknown_dataset_raises_dataset_not_found(self) -> None:
        registry = get_registry()
        with self.assertRaises(DatasetError) as ctx:
            registry.inspect("catalog:nonexistent-xyz")
        self.assertEqual(ctx.exception.code, "DATASET_NOT_FOUND")

    def test_reset_registry_rebuilds_on_next_call(self) -> None:
        first = get_registry()
        reset_registry()
        second = get_registry()
        self.assertIsNot(first, second)
        self.assertIsNotNone(second.get_provider("catalog"))

    def test_config_enabled_false_suppresses_catalog_provider(self) -> None:
        cfg = {
            "default_provider": "catalog",
            "search_order": ["catalog"],
            "providers": {"catalog": {"enabled": False}},
        }
        with patch("canarchy.dataset_cache.load_datasets_config", return_value=cfg):
            reset_registry()
            registry = get_registry()
        self.assertIsNone(registry.get_provider("catalog"))
        reset_registry()

    def test_fetch_unknown_provider_raises_error(self) -> None:
        registry = DatasetProviderRegistry()
        with self.assertRaises(DatasetError) as ctx:
            registry.fetch("noprovider:road")
        self.assertEqual(ctx.exception.code, "DATASET_PROVIDER_NOT_FOUND")


# ---------------------------------------------------------------------------
# dataset_convert
# ---------------------------------------------------------------------------

class DatasetConvertTests(unittest.TestCase):
    def test_hcrl_csv_to_candump(self) -> None:
        src = str(FIXTURES / "dataset_hcrl_sample.csv")
        with tempfile.TemporaryDirectory() as tmp:
            dest = str(Path(tmp) / "out.log")
            result = convert_file(src, source_format="hcrl-csv", output_format="candump", destination=dest)
            self.assertEqual(result["frame_count"], 6)
            self.assertEqual(result["output_format"], "candump")
            lines = Path(dest).read_text().splitlines()
            self.assertEqual(len(lines), 6)
            # candump format: (timestamp) interface id#data
            self.assertTrue(lines[0].startswith("(0.000000)"))
            self.assertIn("316#", lines[0])

    def test_hcrl_csv_to_jsonl(self) -> None:
        src = str(FIXTURES / "dataset_hcrl_sample.csv")
        with tempfile.TemporaryDirectory() as tmp:
            dest = str(Path(tmp) / "out.jsonl")
            result = convert_file(src, source_format="hcrl-csv", output_format="jsonl", destination=dest)
            self.assertEqual(result["frame_count"], 6)
            lines = Path(dest).read_text().splitlines()
            self.assertEqual(len(lines), 6)
            event = json.loads(lines[0])
            self.assertEqual(event["event_type"], "frame")
            self.assertIn("arbitration_id", event["payload"])
            self.assertIn("data", event["payload"])

    def test_jsonl_label_preserved_for_attack_rows(self) -> None:
        src = str(FIXTURES / "dataset_hcrl_sample.csv")
        with tempfile.TemporaryDirectory() as tmp:
            dest = str(Path(tmp) / "out.jsonl")
            convert_file(src, source_format="hcrl-csv", output_format="jsonl", destination=dest)
            lines = Path(dest).read_text().splitlines()
            attack_events = [json.loads(l) for l in lines if json.loads(l)["payload"].get("label") == "Attack"]
            self.assertEqual(len(attack_events), 2)

    def test_unsupported_source_format_raises_conversion_error(self) -> None:
        src = str(FIXTURES / "dataset_hcrl_sample.csv")
        with tempfile.TemporaryDirectory() as tmp:
            dest = str(Path(tmp) / "out.log")
            with self.assertRaises(ConversionError) as ctx:
                convert_file(src, source_format="unknown-fmt", output_format="candump", destination=dest)
            self.assertEqual(ctx.exception.code, "UNSUPPORTED_SOURCE_FORMAT")

    def test_unsupported_output_format_raises_conversion_error(self) -> None:
        src = str(FIXTURES / "dataset_hcrl_sample.csv")
        with tempfile.TemporaryDirectory() as tmp:
            dest = str(Path(tmp) / "out.xyz")
            with self.assertRaises(ConversionError) as ctx:
                convert_file(src, source_format="hcrl-csv", output_format="xyz", destination=dest)
            self.assertEqual(ctx.exception.code, "UNSUPPORTED_OUTPUT_FORMAT")

    def test_missing_source_file_raises_conversion_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = str(Path(tmp) / "out.log")
            with self.assertRaises(ConversionError) as ctx:
                convert_file("/nonexistent/path.csv", source_format="hcrl-csv", output_format="candump", destination=dest)
            self.assertEqual(ctx.exception.code, "SOURCE_NOT_FOUND")

    def test_default_destination_suffix_for_candump(self) -> None:
        src = str(FIXTURES / "dataset_hcrl_sample.csv")
        result = convert_file(src, source_format="hcrl-csv", output_format="candump")
        expected_dest = str(FIXTURES / "dataset_hcrl_sample.log")
        self.assertEqual(result["destination"], expected_dest)
        Path(expected_dest).unlink(missing_ok=True)

    def test_candump_arbitration_id_is_hex_uppercase(self) -> None:
        src = str(FIXTURES / "dataset_hcrl_sample.csv")
        with tempfile.TemporaryDirectory() as tmp:
            dest = str(Path(tmp) / "out.log")
            convert_file(src, source_format="hcrl-csv", output_format="candump", destination=dest)
            first_line = Path(dest).read_text().splitlines()[0]
            # ID should be uppercase hex without leading zeros beyond necessary
            self.assertRegex(first_line, r"\([0-9.]+\) can0 [0-9A-F]+#[0-9A-F]*")

    def test_stream_hcrl_csv_to_jsonl_preserves_chunk_metadata(self) -> None:
        src = str(FIXTURES / "dataset_hcrl_sample.csv")
        with tempfile.TemporaryDirectory() as tmp:
            dest = str(Path(tmp) / "stream.jsonl")
            result = stream_file(
                src,
                source_format="hcrl-csv",
                output_format="jsonl",
                destination=dest,
                chunk_size=2,
                provider_ref="catalog:hcrl-car-hacking",
            )
            self.assertEqual(result["frame_count"], 6)
            self.assertEqual(result["chunks"], 3)
            events = [json.loads(line) for line in Path(dest).read_text().splitlines()]
            self.assertEqual(events[0]["payload"]["dataset"]["frame_offset"], 0)
            self.assertEqual(events[2]["payload"]["dataset"]["chunk_index"], 1)
            self.assertEqual(events[2]["payload"]["dataset"]["chunk_position"], 0)
            self.assertEqual(events[0]["payload"]["dataset"]["provider_ref"], "catalog:hcrl-car-hacking")

    def test_stream_hcrl_csv_to_candump_writes_incrementally(self) -> None:
        src = str(FIXTURES / "dataset_hcrl_sample.csv")
        with tempfile.TemporaryDirectory() as tmp:
            dest = str(Path(tmp) / "stream.log")
            result = stream_file(src, source_format="hcrl-csv", output_format="candump", destination=dest)
            lines = Path(dest).read_text().splitlines()
            self.assertEqual(result["frame_count"], 6)
            self.assertEqual(len(lines), 6)
            self.assertTrue(lines[0].startswith("(0.000000) can0 "))

    def test_stream_invalid_chunk_size_raises_conversion_error(self) -> None:
        src = str(FIXTURES / "dataset_hcrl_sample.csv")
        with self.assertRaises(ConversionError) as ctx:
            stream_file(src, source_format="hcrl-csv", output_format="jsonl", chunk_size=0)
        self.assertEqual(ctx.exception.code, "INVALID_CHUNK_SIZE")


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------

class CliIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_registry()

    def tearDown(self) -> None:
        reset_registry()

    def test_datasets_provider_list(self) -> None:
        code, out, _ = run_cli("datasets", "provider", "list", "--json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertTrue(data["ok"])
        names = [p["name"] for p in data["data"]["providers"]]
        self.assertIn("catalog", names)

    def test_datasets_provider_list_default_output_is_human_readable(self) -> None:
        code, out, _ = run_cli("datasets", "provider", "list")
        self.assertEqual(code, 0)
        self.assertIn("Dataset providers", out)
        self.assertIn("catalog (registered)", out)
        self.assertNotIn("providers: [{", out)

    def test_datasets_search_all(self) -> None:
        code, out, _ = run_cli("datasets", "search", "--json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertTrue(data["ok"])
        self.assertGreater(data["data"]["count"], 0)
        result = data["data"]["results"][0]
        for key in ("name", "protocol_family", "license", "source_url", "conversion_targets"):
            self.assertIn(key, result)

    def test_datasets_search_query(self) -> None:
        code, out, _ = run_cli("datasets", "search", "j1939", "--json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertTrue(data["ok"])
        protocols = [r["protocol_family"] for r in data["data"]["results"]]
        self.assertIn("j1939", protocols)

    def test_datasets_search_default_output_is_human_readable(self) -> None:
        code, out, _ = run_cli("datasets", "search", "hcrl")
        self.assertEqual(code, 0)
        self.assertIn('Datasets matching "hcrl" (9)', out)
        self.assertIn("REF", out)
        self.assertIn("PROTOCOL", out)
        self.assertIn("catalog:hcrl-car-hacking", out)
        self.assertIn("CAN", out)
        self.assertNotIn("results: [{", out)
        self.assertIn("Use `canarchy datasets inspect <ref>`", out)

    def test_datasets_search_verbose_output_shows_details(self) -> None:
        code, out, _ = run_cli("datasets", "search", "hcrl", "--verbose")
        self.assertEqual(code, 0)
        self.assertIn('Datasets matching "hcrl" (9)', out)
        self.assertIn("catalog:hcrl-car-hacking", out)
        self.assertIn("  Protocol: CAN", out)
        self.assertIn("  Description: HCRL Car-Hacking Dataset", out)
        self.assertIn("  Source: https://ocslab.hksecurity.net/Datasets/car-hacking-dataset", out)
        self.assertIn("  Access: Research-use agreement", out)

    def test_datasets_inspect_known(self) -> None:
        code, out, _ = run_cli("datasets", "inspect", "road", "--json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertTrue(data["ok"])
        self.assertEqual(data["data"]["name"], "road")
        self.assertIn("description", data["data"])
        self.assertIn("source_url", data["data"])

    def test_datasets_inspect_unknown_fails(self) -> None:
        code, out, _ = run_cli("datasets", "inspect", "nonexistent-xyz", "--json")
        self.assertNotEqual(code, 0)
        data = json.loads(out)
        self.assertFalse(data["ok"])

    def test_datasets_fetch_records_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch("canarchy.dataset_cache.cache_root", return_value=Path(tmp) / "cache"):
                code, out, _ = run_cli("datasets", "fetch", "catalog:road", "--json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertTrue(data["ok"])
        self.assertIn("provenance", data["data"])
        self.assertIn("download_instructions", data["data"])

    def test_datasets_cache_list(self) -> None:
        code, out, _ = run_cli("datasets", "cache", "list", "--json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertTrue(data["ok"])
        self.assertIn("entries", data["data"])

    def test_datasets_cache_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch("canarchy.dataset_cache.cache_root", return_value=Path(tmp) / "cache"):
                code, out, _ = run_cli("datasets", "cache", "refresh", "--json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertTrue(data["ok"])
        self.assertGreater(data["data"]["dataset_count"], 0)

    def test_datasets_convert_hcrl_to_candump(self) -> None:
        src = str(FIXTURES / "dataset_hcrl_sample.csv")
        with tempfile.TemporaryDirectory() as tmp:
            dest = str(Path(tmp) / "out.log")
            code, out, _ = run_cli(
                "datasets", "convert", src,
                "--source-format", "hcrl-csv",
                "--format", "candump",
                "--output", dest,
                "--json",
            )
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertTrue(data["ok"])
        self.assertEqual(data["data"]["frame_count"], 6)

    def test_datasets_convert_hcrl_to_jsonl(self) -> None:
        src = str(FIXTURES / "dataset_hcrl_sample.csv")
        with tempfile.TemporaryDirectory() as tmp:
            dest = str(Path(tmp) / "out.jsonl")
            code, out, _ = run_cli(
                "datasets", "convert", src,
                "--source-format", "hcrl-csv",
                "--format", "jsonl",
                "--output", dest,
                "--json",
            )
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertTrue(data["ok"])
        self.assertEqual(data["data"]["output_format"], "jsonl")

    def test_datasets_stream_hcrl_to_stdout_jsonl(self) -> None:
        src = str(FIXTURES / "dataset_hcrl_sample.csv")
        code, out, _ = run_cli(
            "datasets", "stream", src,
            "--source-format", "hcrl-csv",
            "--format", "jsonl",
            "--chunk-size", "2",
            "--provider-ref", "catalog:hcrl-car-hacking",
        )
        self.assertEqual(code, 0)
        events = [json.loads(line) for line in out.splitlines()]
        self.assertEqual(len(events), 6)
        self.assertEqual(events[2]["payload"]["dataset"]["chunk_index"], 1)

    def test_datasets_stream_json_summary_does_not_emit_frames(self) -> None:
        src = str(FIXTURES / "dataset_hcrl_sample.csv")
        code, out, _ = run_cli(
            "datasets", "stream", src,
            "--source-format", "hcrl-csv",
            "--format", "jsonl",
            "--chunk-size", "2",
            "--json",
        )
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertTrue(data["ok"])
        self.assertEqual(data["data"]["frame_count"], 6)
        self.assertEqual(data["data"]["chunks"], 3)

    def test_datasets_stream_invalid_chunk_size_returns_structured_error(self) -> None:
        src = str(FIXTURES / "dataset_hcrl_sample.csv")
        code, out, _ = run_cli(
            "datasets", "stream", src,
            "--source-format", "hcrl-csv",
            "--format", "jsonl",
            "--chunk-size", "0",
        )
        self.assertEqual(code, 1)
        data = json.loads(out)
        self.assertFalse(data["ok"])
        self.assertEqual(data["errors"][0]["code"], "INVALID_CHUNK_SIZE")
