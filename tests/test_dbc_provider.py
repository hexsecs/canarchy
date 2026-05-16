"""Tests for the DBC provider registry, cache, and opendbc provider."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from canarchy.cli import EXIT_DECODE_ERROR, EXIT_OK, main
from canarchy.dbc import DbcError
from canarchy.dbc_provider import (
    DbcDescriptor,
    DbcResolution,
    ProviderRegistry,
    parse_provider_ref,
    reset_registry,
)
from canarchy.dbc_provider_local import LocalDbcProvider


FIXTURES = Path(__file__).parent / "fixtures"


def run_cli(*argv: str) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = main(argv)
    return exit_code, stdout.getvalue(), stderr.getvalue()


def tearDownModule() -> None:
    reset_registry()


class ParseProviderRefTests(unittest.TestCase):
    def test_opendbc_prefix_extracted(self) -> None:
        provider, name = parse_provider_ref("opendbc:toyota_tnga_k_pt_generated")
        self.assertEqual(provider, "opendbc")
        self.assertEqual(name, "toyota_tnga_k_pt_generated")

    def test_comma_alias_normalized_to_opendbc(self) -> None:
        provider, name = parse_provider_ref("comma:honda_civic")
        self.assertEqual(provider, "opendbc")
        self.assertEqual(name, "honda_civic")

    def test_bare_name_returns_none_provider(self) -> None:
        provider, name = parse_provider_ref("toyota_tnga_k_pt_generated")
        self.assertIsNone(provider)
        self.assertEqual(name, "toyota_tnga_k_pt_generated")

    def test_local_path_has_no_provider(self) -> None:
        provider, name = parse_provider_ref("/some/path/file.dbc")
        self.assertIsNone(provider)
        self.assertEqual(name, "/some/path/file.dbc")


class LocalDbcProviderTests(unittest.TestCase):
    def test_resolve_existing_file_returns_resolution(self) -> None:
        provider = LocalDbcProvider()
        resolution = provider.resolve(str(FIXTURES / "sample.dbc"))
        self.assertEqual(resolution.descriptor.provider, "local")
        self.assertEqual(resolution.descriptor.name, "sample.dbc")
        self.assertFalse(resolution.is_cached)
        self.assertTrue(resolution.local_path.exists())

    def test_resolve_missing_file_raises_dbc_not_found(self) -> None:
        provider = LocalDbcProvider()
        with self.assertRaises(DbcError) as ctx:
            provider.resolve("/does/not/exist.dbc")
        self.assertEqual(ctx.exception.code, "DBC_NOT_FOUND")

    def test_search_always_returns_empty(self) -> None:
        provider = LocalDbcProvider()
        self.assertEqual(provider.search("toyota"), [])

    def test_refresh_always_returns_empty(self) -> None:
        provider = LocalDbcProvider()
        self.assertEqual(provider.refresh(), [])


class ProviderRegistryTests(unittest.TestCase):
    def _make_registry(self) -> ProviderRegistry:
        registry = ProviderRegistry()
        registry.register(LocalDbcProvider())
        return registry

    def test_resolve_existing_local_path(self) -> None:
        registry = self._make_registry()
        ref = str(FIXTURES / "sample.dbc")
        resolution = registry.resolve(ref)
        self.assertEqual(resolution.descriptor.provider, "local")
        self.assertTrue(resolution.local_path.exists())

    def test_resolve_missing_local_path_raises_not_found(self) -> None:
        registry = self._make_registry()
        with self.assertRaises(DbcError) as ctx:
            registry.resolve("/no/such/file.dbc")
        self.assertEqual(ctx.exception.code, "DBC_NOT_FOUND")

    def test_resolve_unknown_provider_prefix_raises_provider_not_found(self) -> None:
        registry = self._make_registry()
        with self.assertRaises(DbcError) as ctx:
            registry.resolve("unknown:some_dbc")
        self.assertEqual(ctx.exception.code, "DBC_PROVIDER_NOT_FOUND")

    def test_list_providers_returns_registered_names(self) -> None:
        registry = self._make_registry()
        names = [p["name"] for p in registry.list_providers()]
        self.assertIn("local", names)

    def test_get_provider_returns_registered_provider(self) -> None:
        registry = self._make_registry()
        provider = registry.get_provider("local")
        self.assertIsNotNone(provider)
        self.assertEqual(provider.name, "local")

    def test_get_provider_returns_none_for_unknown(self) -> None:
        registry = self._make_registry()
        self.assertIsNone(registry.get_provider("opendbc"))


class ProviderRegistryWithOpendbc(unittest.TestCase):
    """Tests for opendbc provider routing when it's registered."""

    def _make_mock_opendbc_provider(self) -> MagicMock:
        mock = MagicMock()
        mock.name = "opendbc"
        mock.search.return_value = [
            DbcDescriptor(
                provider="opendbc",
                name="toyota_tnga_k_pt_generated",
                version="abc123",
                source_ref="opendbc:toyota_tnga_k_pt_generated",
                cache_path=None,
                sha256=None,
            )
        ]
        mock.resolve.return_value = DbcResolution(
            descriptor=DbcDescriptor(
                provider="opendbc",
                name="toyota_tnga_k_pt_generated",
                version="abc123",
                source_ref="opendbc:toyota_tnga_k_pt_generated",
                cache_path=None,
                sha256=None,
            ),
            local_path=FIXTURES / "sample.dbc",
            is_cached=True,
        )
        return mock

    def test_opendbc_prefix_routes_to_opendbc_provider(self) -> None:
        registry = ProviderRegistry()
        registry.register(LocalDbcProvider())
        mock_opendbc = self._make_mock_opendbc_provider()
        registry.register(mock_opendbc)

        resolution = registry.resolve("opendbc:toyota_tnga_k_pt_generated")
        self.assertEqual(resolution.descriptor.provider, "opendbc")
        mock_opendbc.resolve.assert_called_once_with("toyota_tnga_k_pt_generated")

    def test_comma_alias_routes_to_opendbc_provider(self) -> None:
        registry = ProviderRegistry()
        registry.register(LocalDbcProvider())
        mock_opendbc = self._make_mock_opendbc_provider()
        registry.register(mock_opendbc)

        registry.resolve("comma:toyota_tnga_k_pt_generated")
        mock_opendbc.resolve.assert_called_once_with("toyota_tnga_k_pt_generated")

    def test_search_aggregates_across_providers(self) -> None:
        registry = ProviderRegistry()
        registry.register(LocalDbcProvider())
        mock_opendbc = self._make_mock_opendbc_provider()
        registry.register(mock_opendbc)

        results = registry.search("toyota")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "toyota_tnga_k_pt_generated")


class ProviderResolutionIntegrationTests(unittest.TestCase):
    """Integration tests: provider resolution flows through to cantools."""

    def test_existing_dbc_path_resolves_and_loads(self) -> None:
        from canarchy.dbc_runtime import load_runtime_database

        reset_registry()
        db = load_runtime_database(str(FIXTURES / "sample.dbc"))
        self.assertIsNotNone(db.get_message_by_name("EngineStatus1"))

    def test_missing_dbc_path_raises_dbc_not_found(self) -> None:
        from canarchy.dbc_runtime import load_runtime_database

        reset_registry()
        with self.assertRaises(DbcError) as ctx:
            load_runtime_database("/does/not/exist.dbc")
        self.assertEqual(ctx.exception.code, "DBC_NOT_FOUND")


class CacheTests(unittest.TestCase):
    def test_load_dbc_config_returns_defaults_when_no_config_file(self) -> None:
        from canarchy.dbc_cache import load_dbc_config

        with patch("canarchy.dbc_cache._CONFIG_PATH", Path("/does/not/exist/config.toml")):
            cfg = load_dbc_config()
        self.assertEqual(cfg["default_provider"], "local")
        self.assertIn("opendbc", cfg["search_order"])
        self.assertIn("opendbc", cfg["providers"])

    def test_cache_list_returns_empty_when_no_cache(self) -> None:
        from canarchy.dbc_cache import cache_list

        with patch("canarchy.dbc_cache._CACHE_ROOT", Path("/does/not/exist/cache")):
            entries = cache_list()
        self.assertEqual(entries, [])

    def test_cache_list_returns_manifest_entries(self) -> None:
        from canarchy.dbc_cache import cache_list, save_manifest

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_root = Path(tmpdir)
            with patch("canarchy.dbc_cache._CACHE_ROOT", cache_root):
                save_manifest(
                    "opendbc",
                    {
                        "provider": "opendbc",
                        "repo": "commaai/opendbc",
                        "commit": "abc123def456",
                        "generated_at": "2026-04-19T00:00:00Z",
                        "dbcs": [{"name": "foo", "path": "opendbc/dbc/foo.dbc", "sha256": ""}],
                    },
                )
                entries = cache_list()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["provider"], "opendbc")
        self.assertEqual(entries[0]["dbc_count"], 1)

    def test_cache_prune_removes_stale_commit_dirs(self) -> None:
        from canarchy.dbc_cache import cache_prune, save_manifest

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_root = Path(tmpdir)
            with patch("canarchy.dbc_cache._CACHE_ROOT", cache_root):
                save_manifest(
                    "opendbc",
                    {
                        "provider": "opendbc",
                        "repo": "commaai/opendbc",
                        "commit": "new123",
                        "generated_at": "2026-04-19T00:00:00Z",
                        "dbcs": [],
                    },
                )
                stale_dir = cache_root / "providers" / "opendbc" / "files" / "old456"
                stale_dir.mkdir(parents=True)
                (stale_dir / "foo.dbc").write_text("")
                kept_dir = cache_root / "providers" / "opendbc" / "files" / "new123"
                kept_dir.mkdir(parents=True)
                (kept_dir / "foo.dbc").write_text("")

                removed = cache_prune("opendbc")

        self.assertEqual(len(removed), 1)
        self.assertIn("old456", removed[0])


class OpenDbcProviderTests(unittest.TestCase):
    """Tests for OpenDbcProvider using mocked GitHub API responses."""

    def _make_manifest(self, commit: str = "abc123def456") -> dict:
        return {
            "provider": "opendbc",
            "repo": "commaai/opendbc",
            "commit": commit,
            "generated_at": "2026-04-19T00:00:00Z",
            "dbcs": [
                {
                    "name": "toyota_tnga_k_pt_generated",
                    "path": "opendbc/dbc/toyota_tnga_k_pt_generated.dbc",
                    "sha": "sha1",
                },
                {
                    "name": "honda_civic_ex_2022",
                    "path": "opendbc/dbc/honda_civic_ex_2022.dbc",
                    "sha": "sha2",
                },
            ],
        }

    def test_search_returns_ranked_matches_from_manifest(self) -> None:
        from canarchy.dbc_opendbc import OpenDbcProvider

        with patch("canarchy.dbc_cache.load_manifest", return_value=self._make_manifest()):
            with patch(
                "canarchy.dbc_cache.load_dbc_config",
                return_value={
                    "providers": {
                        "opendbc": {
                            "enabled": True,
                            "repo": "commaai/opendbc",
                            "ref": "master",
                            "auto_refresh": False,
                        }
                    }
                },
            ):
                provider = OpenDbcProvider()
                results = provider.search("toyota")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "toyota_tnga_k_pt_generated")
        self.assertEqual(results[0].provider, "opendbc")

    def test_search_returns_empty_when_no_manifest(self) -> None:
        from canarchy.dbc_opendbc import OpenDbcProvider

        with patch("canarchy.dbc_cache.load_manifest", return_value=None):
            with patch(
                "canarchy.dbc_cache.load_dbc_config",
                return_value={
                    "providers": {
                        "opendbc": {
                            "enabled": True,
                            "repo": "commaai/opendbc",
                            "ref": "master",
                            "auto_refresh": False,
                        }
                    }
                },
            ):
                provider = OpenDbcProvider()
                results = provider.search("toyota")

        self.assertEqual(results, [])

    def test_resolve_cached_file_returns_resolution(self) -> None:
        from canarchy.dbc_opendbc import OpenDbcProvider

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_root = Path(tmpdir)
            commit = "abc123def456"
            cached = (
                cache_root
                / "providers"
                / "opendbc"
                / "files"
                / commit
                / "toyota_tnga_k_pt_generated.dbc"
            )
            cached.parent.mkdir(parents=True)
            cached.write_text("")

            with patch(
                "canarchy.dbc_cache.load_manifest", return_value=self._make_manifest(commit)
            ):
                with patch(
                    "canarchy.dbc_cache.load_dbc_config",
                    return_value={
                        "providers": {
                            "opendbc": {
                                "enabled": True,
                                "repo": "commaai/opendbc",
                                "ref": "master",
                                "auto_refresh": False,
                            }
                        }
                    },
                ):
                    with patch("canarchy.dbc_cache.cached_file_path", return_value=cached):
                        provider = OpenDbcProvider()
                        resolution = provider.resolve("toyota_tnga_k_pt_generated")

        self.assertEqual(resolution.descriptor.name, "toyota_tnga_k_pt_generated")
        self.assertTrue(resolution.is_cached)
        self.assertEqual(resolution.local_path, cached)

    def test_resolve_unknown_name_raises_not_found(self) -> None:
        from canarchy.dbc_opendbc import OpenDbcProvider

        with patch("canarchy.dbc_cache.load_manifest", return_value=self._make_manifest()):
            with patch(
                "canarchy.dbc_cache.load_dbc_config",
                return_value={
                    "providers": {
                        "opendbc": {
                            "enabled": True,
                            "repo": "commaai/opendbc",
                            "ref": "master",
                            "auto_refresh": False,
                        }
                    }
                },
            ):
                provider = OpenDbcProvider()
                with self.assertRaises(DbcError) as ctx:
                    provider.resolve("does_not_exist")

        self.assertEqual(ctx.exception.code, "DBC_NOT_FOUND")

    def test_resolve_without_manifest_raises_cache_miss(self) -> None:
        from canarchy.dbc_opendbc import OpenDbcProvider

        with patch("canarchy.dbc_cache.load_manifest", return_value=None):
            with patch(
                "canarchy.dbc_cache.load_dbc_config",
                return_value={
                    "providers": {
                        "opendbc": {
                            "enabled": True,
                            "repo": "commaai/opendbc",
                            "ref": "master",
                            "auto_refresh": False,
                        }
                    }
                },
            ):
                provider = OpenDbcProvider()
                with self.assertRaises(DbcError) as ctx:
                    provider.resolve("toyota_tnga_k_pt_generated")

        self.assertEqual(ctx.exception.code, "DBC_CACHE_MISS")

    def test_refresh_saves_manifest(self) -> None:
        from canarchy.dbc_opendbc import OpenDbcProvider

        commit = "freshcommit123"
        api_responses = {
            "https://api.github.com/repos/commaai/opendbc/commits/master": {"sha": commit},
            f"https://api.github.com/repos/commaai/opendbc/git/trees/{commit}?recursive=1": {
                "tree": [
                    {"path": "opendbc/dbc/toyota_tnga_k_pt_generated.dbc", "sha": "s1"},
                    {"path": "opendbc/dbc/honda_civic_ex_2022.dbc", "sha": "s2"},
                    {"path": "opendbc/car/toyota.py", "sha": "s3"},  # should be excluded
                ]
            },
        }

        saved: dict = {}

        def mock_github_get(url: str):
            return api_responses[url]

        def mock_save_manifest(provider: str, manifest: dict) -> None:
            saved.update(manifest)

        with patch("canarchy.dbc_opendbc._github_get", side_effect=mock_github_get):
            with patch("canarchy.dbc_cache.save_manifest", side_effect=mock_save_manifest):
                with patch(
                    "canarchy.dbc_cache.load_dbc_config",
                    return_value={
                        "providers": {
                            "opendbc": {
                                "enabled": True,
                                "repo": "commaai/opendbc",
                                "ref": "master",
                                "auto_refresh": False,
                            }
                        }
                    },
                ):
                    provider = OpenDbcProvider()
                    descriptors = provider.refresh()

        self.assertEqual(saved["commit"], commit)
        self.assertEqual(len(saved["dbcs"]), 2)
        dbc_names = {d["name"] for d in saved["dbcs"]}
        self.assertIn("toyota_tnga_k_pt_generated", dbc_names)
        self.assertNotIn("toyota", dbc_names)  # car/ files excluded
        self.assertEqual(len(descriptors), 2)

    def test_cache_miss_message_contains_refresh_command(self) -> None:
        """DBC_CACHE_MISS error includes the exact copy-pasteable fix command."""
        from canarchy.dbc_opendbc import OpenDbcProvider

        with patch("canarchy.dbc_cache.load_manifest", return_value=None):
            with patch(
                "canarchy.dbc_cache.load_dbc_config",
                return_value={
                    "providers": {
                        "opendbc": {
                            "enabled": True,
                            "repo": "commaai/opendbc",
                            "ref": "master",
                            "auto_refresh": False,
                        }
                    }
                },
            ):
                provider = OpenDbcProvider()
                with self.assertRaises(DbcError) as ctx:
                    provider.resolve("toyota_tnga_k_pt_generated")

        err = ctx.exception
        self.assertEqual(err.code, "DBC_CACHE_MISS")
        self.assertIn("canarchy dbc cache refresh --provider opendbc", err.hint)
        self.assertIn("canarchy dbc cache refresh --provider opendbc", err.message)
        self.assertIn("auto_refresh", err.message)

    def test_auto_refresh_true_triggers_refresh_and_succeeds(self) -> None:
        """When auto_refresh=True, a cold resolve() calls refresh() then retries."""
        from canarchy.dbc_opendbc import OpenDbcProvider

        commit = "autorefreshcommit"
        manifest = self._make_manifest(commit)

        call_sequence: list[str] = []

        def load_manifest_side_effect(provider_name: str):
            call_sequence.append("load_manifest")
            # Return None on first call (cache cold), manifest on subsequent calls.
            if call_sequence.count("load_manifest") == 1:
                return None
            return manifest

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_root = Path(tmpdir)
            cached = (
                cache_root
                / "providers"
                / "opendbc"
                / "files"
                / commit
                / "toyota_tnga_k_pt_generated.dbc"
            )
            cached.parent.mkdir(parents=True)
            cached.write_text("")

            with patch("canarchy.dbc_cache.load_manifest", side_effect=load_manifest_side_effect):
                with patch(
                    "canarchy.dbc_cache.load_dbc_config",
                    return_value={
                        "providers": {
                            "opendbc": {
                                "enabled": True,
                                "repo": "commaai/opendbc",
                                "ref": "master",
                                "auto_refresh": True,
                            }
                        }
                    },
                ):
                    with patch("canarchy.dbc_cache.cached_file_path", return_value=cached):
                        with patch.object(OpenDbcProvider, "refresh") as mock_refresh:
                            mock_refresh.return_value = []
                            provider = OpenDbcProvider()
                            resolution = provider.resolve("toyota_tnga_k_pt_generated")

        mock_refresh.assert_called_once()
        self.assertEqual(resolution.descriptor.name, "toyota_tnga_k_pt_generated")
        self.assertTrue(resolution.is_cached)

    def test_auto_refresh_true_network_failure_raises_cleanly(self) -> None:
        """When auto_refresh=True but network fails, a clean error is raised (no crash)."""
        from canarchy.dbc_opendbc import OpenDbcProvider

        with patch("canarchy.dbc_cache.load_manifest", return_value=None):
            with patch(
                "canarchy.dbc_cache.load_dbc_config",
                return_value={
                    "providers": {
                        "opendbc": {
                            "enabled": True,
                            "repo": "commaai/opendbc",
                            "ref": "master",
                            "auto_refresh": True,
                        }
                    }
                },
            ):
                with patch.object(
                    OpenDbcProvider,
                    "refresh",
                    side_effect=DbcError(
                        code="DBC_PROVIDER_NOT_FOUND",
                        message="Failed to resolve opendbc ref 'master'.",
                        hint="Check your network connection.",
                    ),
                ):
                    provider = OpenDbcProvider()
                    with self.assertRaises(DbcError) as ctx:
                        provider.resolve("toyota_tnga_k_pt_generated")

        self.assertIn(ctx.exception.code, {"DBC_CACHE_MISS", "DBC_PROVIDER_NOT_FOUND"})

    def test_auto_refresh_config_default_is_false(self) -> None:
        """auto_refresh defaults to False in load_dbc_config."""
        from canarchy.dbc_cache import load_dbc_config

        with patch("canarchy.dbc_cache._CONFIG_PATH", Path("/does/not/exist/config.toml")):
            cfg = load_dbc_config()

        self.assertFalse(cfg["providers"]["opendbc"]["auto_refresh"])


class CliProviderCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_registry()

    def tearDown(self) -> None:
        reset_registry()

    def _make_mock_opendbc_provider(self) -> MagicMock:
        mock = MagicMock()
        mock.name = "opendbc"
        mock.search.return_value = [
            DbcDescriptor(
                provider="opendbc",
                name="toyota_tnga_k_pt_generated",
                version="abc123",
                source_ref="opendbc:toyota_tnga_k_pt_generated",
                cache_path=None,
                sha256=None,
                metadata={"brand": "toyota"},
            )
        ]
        mock.resolve.return_value = DbcResolution(
            descriptor=DbcDescriptor(
                provider="opendbc",
                name="toyota_tnga_k_pt_generated",
                version="abc123",
                source_ref="opendbc:toyota_tnga_k_pt_generated",
                cache_path=None,
                sha256=None,
            ),
            local_path=FIXTURES / "sample.dbc",
            is_cached=True,
        )
        mock.refresh.return_value = [
            DbcDescriptor(
                provider="opendbc",
                name="toyota_tnga_k_pt_generated",
                version="abc123",
                source_ref="opendbc:toyota_tnga_k_pt_generated",
                cache_path=None,
                sha256=None,
            )
        ]
        return mock

    def test_dbc_provider_list_returns_registered_providers(self) -> None:
        exit_code, stdout, _ = run_cli("dbc", "provider", "list", "--json")
        self.assertEqual(exit_code, EXIT_OK)
        payload = json.loads(stdout)
        names = [p["name"] for p in payload["data"]["providers"]]
        self.assertIn("local", names)

    def test_dbc_search_with_mock_opendbc_returns_results(self) -> None:
        mock = self._make_mock_opendbc_provider()
        with patch("canarchy.dbc_provider._build_default_registry") as mock_build:
            registry = ProviderRegistry()
            registry.register(LocalDbcProvider())
            registry.register(mock)
            mock_build.return_value = registry

            reset_registry()
            exit_code, stdout, _ = run_cli(
                "dbc", "search", "toyota", "--provider", "opendbc", "--json"
            )

        self.assertEqual(exit_code, EXIT_OK)
        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["count"], 1)
        self.assertEqual(payload["data"]["results"][0]["name"], "toyota_tnga_k_pt_generated")

    def test_dbc_fetch_with_mock_opendbc_returns_resolution(self) -> None:
        mock = self._make_mock_opendbc_provider()
        with patch("canarchy.dbc_provider._build_default_registry") as mock_build:
            registry = ProviderRegistry()
            registry.register(LocalDbcProvider())
            registry.register(mock)
            mock_build.return_value = registry

            reset_registry()
            exit_code, stdout, _ = run_cli(
                "dbc", "fetch", "opendbc:toyota_tnga_k_pt_generated", "--json"
            )

        self.assertEqual(exit_code, EXIT_OK)
        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["name"], "toyota_tnga_k_pt_generated")
        self.assertTrue(payload["data"]["is_cached"])

    def test_dbc_cache_list_returns_entries(self) -> None:
        with patch(
            "canarchy.dbc_cache.cache_list",
            return_value=[
                {
                    "provider": "opendbc",
                    "commit": "abc123",
                    "dbc_count": 42,
                    "repo": "commaai/opendbc",
                    "generated_at": "2026-04-19",
                    "cache_dir": "/tmp/foo",
                }
            ],
        ):
            exit_code, stdout, _ = run_cli("dbc", "cache", "list", "--json")
        self.assertEqual(exit_code, EXIT_OK)
        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["count"], 1)

    def test_dbc_cache_prune_returns_removed_paths(self) -> None:
        with patch("canarchy.dbc_cache.cache_prune", return_value=["/some/old/path"]):
            exit_code, stdout, _ = run_cli("dbc", "cache", "prune", "--json")
        self.assertEqual(exit_code, EXIT_OK)
        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["count"], 1)

    def test_dbc_cache_refresh_returns_dbc_count(self) -> None:
        mock = self._make_mock_opendbc_provider()
        with patch("canarchy.dbc_provider._build_default_registry") as mock_build:
            registry = ProviderRegistry()
            registry.register(LocalDbcProvider())
            registry.register(mock)
            mock_build.return_value = registry

            reset_registry()
            exit_code, stdout, _ = run_cli(
                "dbc", "cache", "refresh", "--provider", "opendbc", "--json"
            )

        self.assertEqual(exit_code, EXIT_OK)
        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["provider"], "opendbc")
        self.assertEqual(payload["data"]["dbc_count"], 1)

    def test_dbc_cache_refresh_unknown_provider_returns_error(self) -> None:
        exit_code, stdout, _ = run_cli(
            "dbc", "cache", "refresh", "--provider", "unknown_provider", "--json"
        )
        self.assertEqual(exit_code, EXIT_DECODE_ERROR)
        payload = json.loads(stdout)
        self.assertEqual(payload["errors"][0]["code"], "DBC_PROVIDER_NOT_FOUND")

    def test_dbc_fetch_unknown_opendbc_ref_returns_not_found(self) -> None:
        mock = self._make_mock_opendbc_provider()
        mock.resolve.side_effect = DbcError(
            code="DBC_NOT_FOUND",
            message="DBC 'does_not_exist' not found in opendbc catalog.",
            hint="Run dbc search to find available DBCs.",
        )
        with patch("canarchy.dbc_provider._build_default_registry") as mock_build:
            registry = ProviderRegistry()
            registry.register(LocalDbcProvider())
            registry.register(mock)
            mock_build.return_value = registry

            reset_registry()
            exit_code, stdout, _ = run_cli("dbc", "fetch", "opendbc:does_not_exist", "--json")

        self.assertEqual(exit_code, EXIT_DECODE_ERROR)
        payload = json.loads(stdout)
        self.assertEqual(payload["errors"][0]["code"], "DBC_NOT_FOUND")

    def test_decode_accepts_resolved_opendbc_ref(self) -> None:
        mock = self._make_mock_opendbc_provider()
        with patch("canarchy.dbc_provider._build_default_registry") as mock_build:
            registry = ProviderRegistry()
            registry.register(LocalDbcProvider())
            registry.register(mock)
            mock_build.return_value = registry

            reset_registry()
            exit_code, stdout, _ = run_cli(
                "decode",
                "--file",
                str(FIXTURES / "sample.candump"),
                "--dbc",
                "opendbc:toyota_tnga_k_pt_generated",
                "--json",
            )

        self.assertEqual(exit_code, EXIT_OK)
        payload = json.loads(stdout)
        self.assertEqual(payload["command"], "decode")

    def test_decode_opendbc_ref_includes_dbc_source(self) -> None:
        mock = self._make_mock_opendbc_provider()
        with patch("canarchy.dbc_provider._build_default_registry") as mock_build:
            registry = ProviderRegistry()
            registry.register(LocalDbcProvider())
            registry.register(mock)
            mock_build.return_value = registry

            reset_registry()
            exit_code, stdout, _ = run_cli(
                "decode",
                "--file",
                str(FIXTURES / "sample.candump"),
                "--dbc",
                "opendbc:toyota_tnga_k_pt_generated",
                "--json",
            )

        self.assertEqual(exit_code, EXIT_OK)
        payload = json.loads(stdout)
        dbc_source = payload["data"]["dbc_source"]
        self.assertEqual(dbc_source["provider"], "opendbc")
        self.assertEqual(dbc_source["name"], "toyota_tnga_k_pt_generated")
        self.assertEqual(dbc_source["version"], "abc123")
        self.assertIn("path", dbc_source)

    def test_decode_local_ref_includes_dbc_source_with_local_provider(self) -> None:
        exit_code, stdout, _ = run_cli(
            "decode",
            "--file",
            str(FIXTURES / "sample.candump"),
            "--dbc",
            str(FIXTURES / "sample.dbc"),
            "--json",
        )
        self.assertEqual(exit_code, EXIT_OK)
        payload = json.loads(stdout)
        dbc_source = payload["data"]["dbc_source"]
        self.assertEqual(dbc_source["provider"], "local")
        self.assertIsNone(dbc_source["version"])

    def test_encode_opendbc_ref_includes_dbc_source(self) -> None:
        mock = self._make_mock_opendbc_provider()
        with patch("canarchy.dbc_provider._build_default_registry") as mock_build:
            registry = ProviderRegistry()
            registry.register(LocalDbcProvider())
            registry.register(mock)
            mock_build.return_value = registry

            reset_registry()
            exit_code, stdout, _ = run_cli(
                "encode",
                "--dbc",
                "opendbc:toyota_tnga_k_pt_generated",
                "EngineStatus1",
                "CoolantTemp=55",
                "OilTemp=65",
                "Load=40",
                "LampState=1",
                "--json",
            )

        self.assertEqual(exit_code, EXIT_OK)
        payload = json.loads(stdout)
        dbc_source = payload["data"]["dbc_source"]
        self.assertEqual(dbc_source["provider"], "opendbc")
        self.assertEqual(dbc_source["version"], "abc123")

    def test_encode_local_ref_includes_dbc_source_with_local_provider(self) -> None:
        exit_code, stdout, _ = run_cli(
            "encode",
            "--dbc",
            str(FIXTURES / "sample.dbc"),
            "EngineStatus1",
            "CoolantTemp=55",
            "OilTemp=65",
            "Load=40",
            "LampState=1",
            "--json",
        )
        self.assertEqual(exit_code, EXIT_OK)
        payload = json.loads(stdout)
        dbc_source = payload["data"]["dbc_source"]
        self.assertEqual(dbc_source["provider"], "local")
        self.assertIsNone(dbc_source["version"])

    def test_dbc_inspect_opendbc_ref_includes_dbc_source(self) -> None:
        mock = self._make_mock_opendbc_provider()
        with patch("canarchy.dbc_provider._build_default_registry") as mock_build:
            registry = ProviderRegistry()
            registry.register(LocalDbcProvider())
            registry.register(mock)
            mock_build.return_value = registry

            reset_registry()
            exit_code, stdout, _ = run_cli(
                "dbc",
                "inspect",
                "opendbc:toyota_tnga_k_pt_generated",
                "--json",
            )

        self.assertEqual(exit_code, EXIT_OK)
        payload = json.loads(stdout)
        dbc_source = payload["data"]["dbc_source"]
        self.assertEqual(dbc_source["provider"], "opendbc")
        self.assertEqual(dbc_source["version"], "abc123")

    def test_dbc_inspect_local_ref_includes_dbc_source_with_local_provider(self) -> None:
        exit_code, stdout, _ = run_cli(
            "dbc",
            "inspect",
            str(FIXTURES / "sample.dbc"),
            "--json",
        )
        self.assertEqual(exit_code, EXIT_OK)
        payload = json.loads(stdout)
        dbc_source = payload["data"]["dbc_source"]
        self.assertEqual(dbc_source["provider"], "local")
        self.assertIsNone(dbc_source["version"])
