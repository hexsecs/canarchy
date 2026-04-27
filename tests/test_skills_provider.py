from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from canarchy.cli import EXIT_DECODE_ERROR, EXIT_OK, main
from canarchy.skills import SkillError
from canarchy.skills_provider import ProviderRegistry, SkillDescriptor, SkillResolution, parse_provider_ref, reset_registry


FIXTURES = Path(__file__).parent / "fixtures" / "skills"


def run_cli(*argv: str) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = main(argv)
    return exit_code, stdout.getvalue(), stderr.getvalue()


def tearDownModule() -> None:
    reset_registry()


class ParseProviderRefTests(unittest.TestCase):
    def test_prefix_extracted(self) -> None:
        provider, name = parse_provider_ref("github:j1939_compare_triage")
        self.assertEqual(provider, "github")
        self.assertEqual(name, "j1939_compare_triage")

    def test_bare_name_returns_none_provider(self) -> None:
        provider, name = parse_provider_ref("uds_trace_summary")
        self.assertIsNone(provider)
        self.assertEqual(name, "uds_trace_summary")


class SkillsCacheTests(unittest.TestCase):
    def test_load_skills_config_returns_defaults_when_no_config_file(self) -> None:
        from canarchy.skills_cache import load_skills_config

        with patch("canarchy.skills_cache._CONFIG_PATH", Path("/does/not/exist/config.toml")):
            cfg = load_skills_config()
        self.assertEqual(cfg["default_provider"], "github")
        self.assertIn("github", cfg["search_order"])

    def test_cache_list_returns_manifest_entries(self) -> None:
        from canarchy.skills_cache import cache_list, save_manifest

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_root = Path(tmpdir)
            with patch("canarchy.skills_cache._CACHE_ROOT", cache_root):
                save_manifest("github", {
                    "provider": "github",
                    "repo": "hexsecs/canarchy-skills",
                    "commit": "abc123def456",
                    "generated_at": "2026-04-26T00:00:00Z",
                    "skills": [{"name": "j1939_compare_triage"}],
                })
                entries = cache_list()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["provider"], "github")
        self.assertEqual(entries[0]["skill_count"], 1)


class GitHubSkillProviderTests(unittest.TestCase):
    def _manifest_text(self, name: str) -> str:
        path = FIXTURES / f"{name}.skill.yaml"
        return path.read_text()

    def test_refresh_builds_catalog_from_skill_manifests(self) -> None:
        from canarchy.skills_github import GitHubSkillProvider

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_root = Path(tmpdir)
            with patch("canarchy.skills_cache._CACHE_ROOT", cache_root), patch(
                "canarchy.skills_github._resolve_commit", return_value="abc123def4567890"
            ), patch(
                "canarchy.skills_github._list_skill_manifests",
                return_value=[
                    "skills/j1939_compare_triage.skill.yaml",
                    "skills/uds_trace_minimal.skill.yaml",
                ],
            ), patch(
                "canarchy.skills_github._download_text",
                side_effect=[
                    self._manifest_text("j1939_compare_triage"),
                    self._manifest_text("uds_trace_minimal"),
                ],
            ), patch(
                "canarchy.skills_cache.load_skills_config",
                return_value={"providers": {"github": {"repo": "hexsecs/canarchy-skills", "ref": "main", "auto_refresh": False}}},
            ):
                provider = GitHubSkillProvider()
                descriptors = provider.refresh()

        self.assertEqual(len(descriptors), 2)
        self.assertEqual(descriptors[0].provider, "github")

    def test_resolve_fetches_manifest_and_entry(self) -> None:
        from canarchy.skills_cache import save_manifest
        from canarchy.skills_github import GitHubSkillProvider

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_root = Path(tmpdir)
            with patch("canarchy.skills_cache._CACHE_ROOT", cache_root), patch(
                "canarchy.skills_cache.load_skills_config",
                return_value={"providers": {"github": {"repo": "hexsecs/canarchy-skills", "ref": "main", "auto_refresh": False}}},
            ):
                save_manifest("github", {
                    "provider": "github",
                    "repo": "hexsecs/canarchy-skills",
                    "commit": "abc123def4567890",
                    "generated_at": "2026-04-26T00:00:00Z",
                    "skills": [{
                        "name": "uds_trace_summary",
                        "summary": "Summarize traced UDS request and response exchanges.",
                        "description": "desc",
                        "tags": ["uds"],
                        "domains": [],
                        "capabilities": [],
                        "publisher": "canarchy-labs",
                        "provider_kind": "repository",
                        "source_ref": "github:hexsecs/canarchy-skills",
                        "revision": "aa83d11",
                        "manifest_path": "skills/uds_trace_summary/skill.yaml",
                        "version": None,
                        "entry_path": "skills/uds_trace_summary/SKILL.md",
                        "entry_format": "markdown",
                        "compatibility": {"canarchy": ">=0.5.0"},
                    }],
                })

                def fake_download(url: str, dest: Path) -> None:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_text("content")

                with patch("canarchy.skills_github._download_file", side_effect=fake_download):
                    provider = GitHubSkillProvider()
                    resolution = provider.resolve("uds_trace_summary")
                    self.assertTrue(resolution.local_manifest_path.exists())
                    self.assertTrue(resolution.local_entry_path.exists())
                    self.assertEqual(resolution.descriptor.name, "uds_trace_summary")

    def test_refresh_rejects_invalid_manifest(self) -> None:
        from canarchy.skills_github import GitHubSkillProvider

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_root = Path(tmpdir)
            with patch("canarchy.skills_cache._CACHE_ROOT", cache_root), patch(
                "canarchy.skills_cache.load_skills_config",
                return_value={"providers": {"github": {"repo": "hexsecs/canarchy-skills", "ref": "main", "auto_refresh": False}}},
            ), patch("canarchy.skills_github._resolve_commit", return_value="abc123def4567890"), patch(
                "canarchy.skills_github._list_skill_manifests", return_value=["skills/invalid_missing_entry.skill.yaml"]
            ), patch(
                "canarchy.skills_github._download_text",
                return_value=self._manifest_text("invalid_missing_entry"),
            ):
                provider = GitHubSkillProvider()
                with self.assertRaises(SkillError) as ctx:
                    provider.refresh()

        self.assertEqual(ctx.exception.code, "SKILL_MANIFEST_INVALID")


class SkillsCliTests(unittest.TestCase):
    def test_skills_provider_list_returns_registered_providers(self) -> None:
        registry = MagicMock()
        registry.list_providers.return_value = [{"name": "github", "registered": True}]
        with patch("canarchy.skills_provider.get_registry", return_value=registry):
            exit_code, stdout, stderr = run_cli("skills", "provider", "list", "--json")
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")
        self.assertIn('"name": "github"', stdout)

    def test_skills_search_returns_structured_results(self) -> None:
        descriptor = SkillDescriptor(
            provider="github",
            name="j1939_compare_triage",
            publisher="canarchy-labs",
            version="0.1.0",
            source_ref="github:j1939_compare_triage",
            cache_path=None,
            metadata={"tags": ["j1939"]},
        )
        registry = MagicMock()
        registry.search.return_value = [descriptor]
        with patch("canarchy.skills_provider.get_registry", return_value=registry):
            exit_code, stdout, stderr = run_cli("skills", "search", "j1939", "--json")
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")
        self.assertIn('"count": 1', stdout)
        self.assertIn('"source_ref": "github:j1939_compare_triage"', stdout)

    def test_skills_search_warns_when_catalog_is_empty(self) -> None:
        registry = MagicMock()
        registry.search.return_value = []
        with patch("canarchy.skills_provider.get_registry", return_value=registry):
            exit_code, stdout, stderr = run_cli("skills", "search", "missing", "--json")
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")
        self.assertIn('"warnings": ["No skills matched the query.', stdout)

    def test_skills_fetch_returns_local_paths(self) -> None:
        resolution = SkillResolution(
            descriptor=SkillDescriptor(
                provider="github",
                name="uds_trace_summary",
                publisher="canarchy-labs",
                version="0.1.0",
                source_ref="github:uds_trace_summary",
                cache_path=None,
                metadata={},
            ),
            local_manifest_path=Path("/tmp/skill.yaml"),
            local_entry_path=Path("/tmp/SKILL.md"),
            is_cached=True,
        )
        registry = MagicMock()
        registry.resolve.return_value = resolution
        with patch("canarchy.skills_provider.get_registry", return_value=registry):
            exit_code, stdout, stderr = run_cli("skills", "fetch", "github:uds_trace_summary", "--json")
        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(stderr, "")
        self.assertIn('"local_manifest_path": "/tmp/skill.yaml"', stdout)
        self.assertIn('"local_entry_path": "/tmp/SKILL.md"', stdout)

    def test_skills_cache_refresh_unknown_provider_returns_structured_error(self) -> None:
        registry = MagicMock()
        registry.get_provider.return_value = None
        registry.list_providers.return_value = [{"name": "github"}]
        with patch("canarchy.skills_provider.get_registry", return_value=registry):
            exit_code, stdout, stderr = run_cli("skills", "cache", "refresh", "--provider", "missing", "--json")
        self.assertEqual(exit_code, EXIT_DECODE_ERROR)
        self.assertEqual(stderr, "")
        self.assertIn('"code": "SKILL_PROVIDER_NOT_FOUND"', stdout)
