"""Tests for the offline (synthetic) dataset provider.

The point of this provider is that a sandboxed agent with no egress can still
run the dataset workflow end to end, so these tests assert the generated data
actually parses through the real conversion and analysis paths rather than only
checking descriptor metadata.
"""

from __future__ import annotations

import contextlib
import dataclasses
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from canarchy.dataset_convert import convert_file
from canarchy.dataset_offline import GENERATOR_VERSION, OfflineDatasetProvider
from canarchy.dataset_provider import DatasetError, DatasetProvider


def _raise(error: Exception):
    """Return a generator callable that always raises `error`."""

    def _generate(_name: str) -> str:
        raise error

    return _generate


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


class OfflineReviewRegressionTests(OfflineProviderCacheTestCase):
    """Regressions for the four defects found in review of #460 (PR #533)."""

    @contextlib.contextmanager
    def _generation_fails(self, name: str, error: Exception):
        """Make one dataset's generator raise.

        `generate` is a field on a frozen dataclass rather than a method, so
        the registry tuple is swapped rather than the type patched.
        """
        import canarchy.dataset_offline as module

        replaced = tuple(
            dataclasses.replace(entry, generate=_raise(error)) if entry.name == name else entry
            for entry in module._DATASETS
        )
        with patch.object(module, "_DATASETS", replaced):
            yield

    # --- BAM addressing -----------------------------------------------

    def test_bam_frames_use_the_global_destination_address(self) -> None:
        """A BAM must be addressed to 0xFF, not to node 0x00.

        TP.CM (0xEC) and TP.DT (0xEB) are PDU1, so the PGN's low byte is the
        destination address rather than part of the PGN. Leaving it at zero
        produced 0x1CEC0000 / 0x1CEB0000 — a session addressed to node 0x00
        while the payload's 0x20 control byte declared a BAM, which is
        self-contradictory and can be rejected or misclassified by
        protocol-aware consumers.
        """
        from canarchy.j1939 import decompose_arbitration_id

        resolution = self.provider.fetch("j1939-basic")
        text = resolution.cache_path.read_text(encoding="utf-8")

        seen = {}
        for line in text.splitlines():
            identifier = int(line.split()[2].split("#")[0], 16)
            decomposed = decompose_arbitration_id(identifier)
            if decomposed.pdu_format in (0xEC, 0xEB):
                seen.setdefault(decomposed.pdu_format, []).append(decomposed)

        self.assertIn(0xEC, seen, "no TP.CM announcement generated")
        self.assertIn(0xEB, seen, "no TP.DT data frames generated")
        for pdu_format, entries in seen.items():
            for decomposed in entries:
                self.assertEqual(
                    decomposed.destination_address,
                    0xFF,
                    f"PDU format 0x{pdu_format:02X} must be globally addressed for a BAM",
                )

    def test_bam_session_reassembles_as_a_global_broadcast(self) -> None:
        """The generated sequence must reassemble as a BAM to 0xFF."""
        from canarchy.j1939_decoder import get_j1939_decoder
        from canarchy.transport import LocalTransport

        resolution = self.provider.fetch("j1939-basic")
        frames = LocalTransport().iter_frames_from_file(str(resolution.cache_path))
        sessions = list(get_j1939_decoder().transport_protocol_sessions(frames))

        self.assertEqual(len(sessions), 1)
        session = sessions[0]
        self.assertEqual(session["session_type"], "bam")
        self.assertEqual(session["destination_address"], 0xFF)
        self.assertTrue(session["complete"])

    def test_destination_address_is_rejected_for_a_pdu2_pgn(self) -> None:
        """A PDU2 PGN has no destination field; asking for one is a bug."""
        from canarchy.dataset_offline import _j1939_id

        with self.assertRaises(ValueError):
            _j1939_id(6, 65226, 0x00, destination_address=0xFF)

    # --- atomic publish -----------------------------------------------

    def test_publish_is_atomic_and_cleans_up_on_failure(self) -> None:
        """The dataset must appear at its path complete, or not at all.

        The realistic failure is the cache filesystem filling up mid-write.
        A direct write to the target would leave a truncated file, and
        `fetch` treats any non-empty path as cached — so the next call would
        record provenance for, and hand back, partial data instead of
        regenerating it.

        The contract is checked at the publish boundary: if the rename into
        place fails, neither the target nor the temporary sibling may be left
        behind. Before the fix there was no rename at all — generation wrote
        straight to the target — so this fails there.
        """
        path = self.provider.data_path("can-basic")

        def _enospc(_src, _dst):
            raise OSError("No space left on device")

        with patch("canarchy.dataset_offline.os.replace", _enospc):
            with self.assertRaises(DatasetError) as caught:
                self.provider.fetch("can-basic")

        self.assertEqual(caught.exception.code, "DATASET_GENERATION_FAILED")
        self.assertFalse(
            path.exists(),
            "a failed publish must not leave a file the next fetch treats as cached",
        )
        siblings = sorted(path.parent.glob("*")) if path.parent.exists() else []
        self.assertEqual(siblings, [], f"temporary files left behind: {siblings}")

    def test_a_generation_error_reports_the_documented_code(self) -> None:
        """A generator failure surfaces as DATASET_GENERATION_FAILED."""
        with self._generation_fails("can-basic", OSError("No space left on device")):
            with self.assertRaises(DatasetError) as caught:
                self.provider.fetch("can-basic")

        self.assertEqual(caught.exception.code, "DATASET_GENERATION_FAILED")
        self.assertFalse(self.provider.data_path("can-basic").exists())

    def test_a_successful_fetch_after_a_failure_regenerates_cleanly(self) -> None:
        """Recovery path: the dataset is complete once the write succeeds."""
        path = self.provider.data_path("can-basic")

        with self._generation_fails("can-basic", OSError("No space left on device")):
            with self.assertRaises(DatasetError):
                self.provider.fetch("can-basic")

        resolution = self.provider.fetch("can-basic")
        self.assertTrue(path.is_file())
        self.assertGreater(path.stat().st_size, 0)
        self.assertTrue(resolution.data_materialized)

    # --- error category / exit code -----------------------------------

    def test_generation_failure_is_categorised_as_a_backend_error(self) -> None:
        """Storage failure is exit 2, not exit 1: it is not bad user input."""
        with self._generation_fails("can-basic", OSError("Permission denied")):
            with self.assertRaises(DatasetError) as caught:
                self.provider.fetch("can-basic")

        self.assertEqual(caught.exception.category, "backend")

    def test_dataset_error_defaults_to_the_user_category(self) -> None:
        """Every pre-existing raise site keeps exit 1."""
        self.assertEqual(DatasetError(code="X", message="y").category, "user")

    # --- fetch reports a usable next step ------------------------------

    def test_fetch_declares_that_data_was_materialised(self) -> None:
        resolution = self.provider.fetch("can-basic")
        self.assertTrue(resolution.data_materialized)
        self.assertTrue(resolution.cache_path.is_file())
