"""Tests for the offline (synthetic) dataset provider.

The point of this provider is that a sandboxed agent with no egress can still
run the dataset workflow end to end, so these tests assert the generated data
actually parses through the real conversion and analysis paths rather than only
checking descriptor metadata.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from canarchy.dataset_convert import convert_file
from canarchy.dataset_offline import GENERATOR_VERSION, OfflineDatasetProvider
from canarchy.dataset_provider import DatasetError, DatasetProvider


class OfflineProviderCacheTestCase(unittest.TestCase):
    """Base case that redirects the dataset cache into a temporary directory."""

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        home = Path(self._tmp.name)
        patcher = patch("canarchy.dataset_cache.Path.home", return_value=home)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.provider = OfflineDatasetProvider()


class OfflineDatasetProviderTests(OfflineProviderCacheTestCase):
    def test_satisfies_the_provider_protocol(self) -> None:
        self.assertIsInstance(self.provider, DatasetProvider)
        self.assertEqual(self.provider.name, "offline")

    def test_every_dataset_is_labelled_synthetic(self) -> None:
        for descriptor in self.provider.search(""):
            with self.subTest(name=descriptor.name):
                # Three independent signals, so no consumer can miss it: the
                # licence string, the description, and a machine-readable flag.
                self.assertIn("Synthetic", descriptor.license)
                self.assertTrue(descriptor.description.startswith("SYNTHETIC:"))
                self.assertIs(descriptor.metadata["synthetic"], True)
                self.assertIs(descriptor.metadata["requires_network"], False)
                self.assertIsNotNone(descriptor.access_notes)
                self.assertIn("not captured vehicle traffic", descriptor.access_notes or "")

    def test_covers_every_parsed_source_format(self) -> None:
        formats = {descriptor.metadata["source_format"] for descriptor in self.provider.search("")}
        self.assertEqual(formats, {"candump", "hcrl-csv", "decoded-signal-csv"})

    def test_search_matches_name_and_protocol(self) -> None:
        self.assertTrue(self.provider.search("j1939"))
        self.assertEqual(self.provider.search("no-such-dataset"), [])

    def test_search_does_not_match_on_source_format(self) -> None:
        """A search for a research group must not surface synthetic data.

        `hcrl-csv` is a file layout named after the group that published it.
        Someone searching `hcrl` wants their datasets, so matching the format
        string would put synthetic data in the results for the one query most
        likely to be looking for the real thing.
        """
        self.assertEqual(self.provider.search("hcrl"), [])

    def test_search_limit_is_respected(self) -> None:
        self.assertEqual(len(self.provider.search("", limit=2)), 2)

    def test_inspect_unknown_dataset_reports_not_found(self) -> None:
        with self.assertRaises(DatasetError) as ctx:
            self.provider.inspect("no-such-dataset")
        self.assertEqual(ctx.exception.code, "DATASET_NOT_FOUND")
        self.assertIn("--provider offline", ctx.exception.hint or "")


class OfflineFetchTests(OfflineProviderCacheTestCase):
    def test_fetch_writes_real_data_and_reports_cache_state(self) -> None:
        first = self.provider.fetch("can-basic")
        self.assertFalse(first.is_cached)
        self.assertTrue(first.cache_path.is_file())
        self.assertGreater(first.cache_path.stat().st_size, 0)

        second = self.provider.fetch("can-basic")
        self.assertTrue(second.is_cached)
        self.assertEqual(first.cache_path, second.cache_path)

    def test_fetch_records_synthetic_provenance(self) -> None:
        resolution = self.provider.fetch("can-basic")
        self.assertIs(resolution.provenance["synthetic"], True)
        self.assertEqual(resolution.provenance["generator"], GENERATOR_VERSION)
        self.assertIn("do not publish", resolution.provenance["note"])

    def test_cache_path_is_versioned(self) -> None:
        """A generator bump must not silently reuse data from an older one."""
        path = self.provider.data_path("can-basic")
        self.assertIn(f"v{GENERATOR_VERSION}", path.parts)

    def test_fetch_unknown_dataset_reports_not_found(self) -> None:
        with self.assertRaises(DatasetError) as ctx:
            self.provider.fetch("no-such-dataset")
        self.assertEqual(ctx.exception.code, "DATASET_NOT_FOUND")

    def test_generation_is_deterministic(self) -> None:
        for name in ("can-basic", "j1939-basic", "can-intrusion", "signal-decoded"):
            with self.subTest(name=name):
                first = self.provider.fetch(name).cache_path.read_bytes()
                self.provider.data_path(name).unlink()
                second = self.provider.fetch(name).cache_path.read_bytes()
                self.assertEqual(first, second)

    def test_refresh_writes_a_manifest(self) -> None:
        from canarchy.dataset_cache import load_manifest

        descriptors = self.provider.refresh()
        manifest = load_manifest("offline")
        self.assertIsNotNone(manifest)
        assert manifest is not None
        self.assertEqual(manifest["dataset_count"], len(descriptors))
        self.assertTrue(all(entry["synthetic"] for entry in manifest["datasets"]))


class OfflineDataIsAnalysableTests(OfflineProviderCacheTestCase):
    """The generated data must survive the real parsers, not just exist."""

    def _frames(self, name: str) -> list:
        from canarchy.transport import iter_candump_file

        return list(iter_candump_file(self.provider.fetch(name).cache_path))

    def test_can_basic_carries_a_discoverable_counter(self) -> None:
        from canarchy.reverse_engineering import counter_candidates

        candidates = counter_candidates(self._frames("can-basic"))
        self.assertTrue(candidates, "expected the planted counter nibble to be found")
        self.assertEqual(candidates[0]["score"], 1.0)

    def test_j1939_dataset_decodes_pgns_tp_and_an_active_fault(self) -> None:
        from canarchy.j1939 import dm1_messages, transport_protocol_sessions

        frames = self._frames("j1939-basic")
        self.assertTrue(frames)

        sessions = transport_protocol_sessions(frames)
        self.assertTrue(sessions, "expected a BAM/TP session")
        self.assertTrue(any(session["complete"] for session in sessions))

        messages = dm1_messages(frames)
        self.assertTrue(messages, "expected DM1 messages")
        active = [message for message in messages if message["active_dtc_count"] > 0]
        self.assertTrue(active, "expected at least one active DTC")
        dtc = active[0]["dtcs"][0]
        self.assertEqual(dtc["spn"], 110)
        self.assertEqual(dtc["fmi"], 3)
        self.assertEqual(active[0]["lamp_status"]["amber_warning"], "on")

    def test_intrusion_dataset_converts_and_keeps_attack_labels(self) -> None:
        source = self.provider.fetch("can-intrusion").cache_path
        destination = source.parent / "converted.jsonl"
        result = convert_file(
            source, source_format="hcrl-csv", output_format="jsonl", destination=destination
        )
        self.assertGreater(result["frame_count"], 0)

        import json

        labels = set()
        for line in destination.read_text(encoding="utf-8").splitlines():
            payload = json.loads(line).get("payload", {})
            if payload.get("label") is not None:
                labels.add(payload["label"])
        self.assertEqual(labels, {"R", "T"}, "expected both normal and attack labels")

    def test_signal_dataset_converts(self) -> None:
        source = self.provider.fetch("signal-decoded").cache_path
        destination = source.parent / "signals.jsonl"
        result = convert_file(
            source,
            source_format="decoded-signal-csv",
            output_format="jsonl",
            destination=destination,
        )
        self.assertGreater(result["frame_count"], 0)


class OfflineProviderRegistrationTests(unittest.TestCase):
    def test_registered_in_the_default_registry_after_the_catalog(self) -> None:
        from canarchy.dataset_provider import get_registry, reset_registry

        reset_registry()
        self.addCleanup(reset_registry)
        registry = get_registry()
        names = [entry["name"] for entry in registry.list_providers()]
        self.assertIn("offline", names)
        # Order matters: a bare ref must still resolve to the real dataset of
        # that name rather than silently preferring synthetic data.
        self.assertLess(names.index("catalog"), names.index("offline"))

    def test_offline_prefix_resolves(self) -> None:
        from canarchy.dataset_provider import get_registry, reset_registry

        reset_registry()
        self.addCleanup(reset_registry)
        descriptor = get_registry().inspect("offline:can-basic")
        self.assertEqual(descriptor.provider, "offline")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
