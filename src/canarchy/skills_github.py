"""GitHub-backed repository skills provider."""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from canarchy.skills import SkillError
from canarchy.skills_provider import SkillDescriptor, SkillResolution

_GITHUB_API = "https://api.github.com"
_RAW_BASE = "https://raw.githubusercontent.com"


def _github_get(url: str) -> Any:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def _download_text(url: str) -> str:
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def _download_file(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=30) as resp:
        dest.write_bytes(resp.read())


def _resolve_commit(repo: str, ref: str) -> str:
    data = _github_get(f"{_GITHUB_API}/repos/{repo}/commits/{ref}")
    return data["sha"]


def _list_skill_manifests(repo: str, commit: str) -> list[str]:
    tree_data = _github_get(f"{_GITHUB_API}/repos/{repo}/git/trees/{commit}?recursive=1")
    results: list[str] = []
    for item in tree_data.get("tree", []):
        path = item.get("path", "")
        if path.endswith(".skill.yaml") or path.endswith(".skill.yml"):
            results.append(path)
    return results


def _skill_entry_from_manifest(manifest: dict[str, Any], *, manifest_path: str) -> dict[str, Any]:
    required_top = ["schema_version", "skill", "provider", "provenance", "compatibility", "entry"]
    if any(key not in manifest for key in required_top):
        raise SkillError(
            code="SKILL_MANIFEST_INVALID",
            message=f"Skill manifest '{manifest_path}' is missing required top-level fields.",
            hint="Ensure schema_version, skill, provider, provenance, compatibility, and entry are present.",
        )
    skill = manifest["skill"]
    provider = manifest["provider"]
    provenance = manifest["provenance"]
    compatibility = manifest["compatibility"]
    entry = manifest["entry"]
    required_nested = {
        "skill": ["name", "summary", "description", "tags"],
        "provider": ["name", "kind"],
        "provenance": ["source_ref", "revision", "manifest_path"],
        "compatibility": ["canarchy"],
        "entry": ["path", "format"],
    }
    containers = {
        "skill": skill,
        "provider": provider,
        "provenance": provenance,
        "compatibility": compatibility,
        "entry": entry,
    }
    for section, keys in required_nested.items():
        if not isinstance(containers[section], dict) or any(key not in containers[section] for key in keys):
            raise SkillError(
                code="SKILL_MANIFEST_INVALID",
                message=f"Skill manifest '{manifest_path}' is missing required fields under '{section}'.",
                hint=f"Ensure {section} includes: {', '.join(keys)}.",
            )
    return {
        "name": skill["name"],
        "summary": skill["summary"],
        "description": skill["description"],
        "tags": list(skill.get("tags", [])),
        "domains": list(skill.get("domains", [])),
        "capabilities": list(skill.get("capabilities", [])),
        "publisher": provider["name"],
        "provider_kind": provider["kind"],
        "source_ref": provenance["source_ref"],
        "revision": provenance["revision"],
        "manifest_path": provenance["manifest_path"],
        "version": provenance.get("version"),
        "entry_path": entry["path"],
        "entry_format": entry["format"],
        "compatibility": compatibility,
    }


def _make_descriptor(entry: dict[str, Any], commit: str, cache_path: Path | None) -> SkillDescriptor:
    return SkillDescriptor(
        provider="github",
        name=entry["name"],
        publisher=entry["publisher"],
        version=entry.get("version") or commit[:12],
        source_ref=f"github:{entry['name']}",
        cache_path=cache_path,
        metadata={
            "summary": entry["summary"],
            "tags": entry.get("tags", []),
            "domains": entry.get("domains", []),
            "capabilities": entry.get("capabilities", []),
            "provider_kind": entry["provider_kind"],
            "source_ref": entry["source_ref"],
            "revision": entry["revision"],
            "manifest_path": entry["manifest_path"],
            "entry_path": entry["entry_path"],
            "entry_format": entry["entry_format"],
            "compatibility": entry.get("compatibility", {}),
        },
    )


def _score_match(entry: dict[str, Any], query: str) -> int:
    q = query.lower()
    name = entry["name"].lower()
    summary = entry.get("summary", "").lower()
    tags = [str(tag).lower() for tag in entry.get("tags", [])]
    if name == q:
        return 100
    if name.startswith(q):
        return 80
    if q in name:
        return 60
    if q in summary:
        return 40
    if q in tags:
        return 30
    return 0


class GitHubSkillProvider:
    name = "github"

    def __init__(self) -> None:
        from canarchy.skills_cache import load_skills_config

        cfg = load_skills_config()
        provider_cfg = cfg.get("providers", {}).get("github", {})
        self._repo: str = provider_cfg.get("repo", "hexsecs/canarchy-skills")
        self._ref: str = provider_cfg.get("ref", "main")
        self._auto_refresh: bool = bool(provider_cfg.get("auto_refresh", False))

    def _manifest(self) -> dict[str, Any] | None:
        from canarchy.skills_cache import load_manifest

        return load_manifest("github")

    def _catalog(self) -> list[dict[str, Any]]:
        manifest = self._manifest()
        if manifest is None:
            return []
        return manifest.get("skills", [])

    def _commit(self) -> str | None:
        manifest = self._manifest()
        if manifest is None:
            return None
        return manifest.get("commit")

    def search(self, query: str, limit: int = 20) -> list[SkillDescriptor]:
        catalog = self._catalog()
        if not catalog:
            return []
        commit = self._commit() or ""
        scored = [(entry, _score_match(entry, query)) for entry in catalog]
        scored = [(entry, score) for entry, score in scored if score > 0]
        scored.sort(key=lambda item: item[1], reverse=True)
        return [_make_descriptor(entry, commit, None) for entry, _score in scored[:limit]]

    def resolve(self, ref: str) -> SkillResolution:
        from canarchy.skills_cache import cached_file_path

        manifest = self._manifest()
        if manifest is None:
            if self._auto_refresh:
                self.refresh()
                manifest = self._manifest()
            if manifest is None:
                raise SkillError(
                    code="SKILL_CACHE_MISS",
                    message="The GitHub skills catalog has not been cached yet.",
                    hint="Run `canarchy skills cache refresh --provider github`.",
                )

        commit = manifest["commit"]
        catalog = manifest.get("skills", [])
        entry = next((item for item in catalog if item["name"] == ref), None)
        if entry is None:
            candidates = [item["name"] for item in catalog if ref.lower() in item["name"].lower()][:5]
            raise SkillError(
                code="SKILL_NOT_FOUND",
                message=f"Skill '{ref}' not found in GitHub skills catalog.",
                hint=(
                    f"Did you mean: {', '.join(candidates)}?"
                    if candidates
                    else "Run `canarchy skills search <query> --provider github` to find available skills."
                ),
            )

        manifest_path = entry["manifest_path"]
        entry_path = entry["entry_path"]
        local_manifest_path = cached_file_path("github", commit, manifest_path)
        local_entry_path = cached_file_path("github", commit, entry_path)
        already_cached = local_manifest_path.exists() and local_entry_path.exists()
        if not local_manifest_path.exists():
            _download_file(f"{_RAW_BASE}/{self._repo}/{commit}/{manifest_path}", local_manifest_path)
        if not local_entry_path.exists():
            _download_file(f"{_RAW_BASE}/{self._repo}/{commit}/{entry_path}", local_entry_path)
        descriptor = _make_descriptor(entry, commit, local_entry_path)
        return SkillResolution(
            descriptor=descriptor,
            local_manifest_path=local_manifest_path,
            local_entry_path=local_entry_path,
            is_cached=already_cached,
        )

    def refresh(self, ref: str | None = None) -> list[SkillDescriptor]:
        from canarchy.skills_cache import save_manifest

        try:
            commit = _resolve_commit(self._repo, self._ref)
            manifest_paths = _list_skill_manifests(self._repo, commit)
        except Exception as exc:
            raise SkillError(
                code="SKILL_PROVIDER_NOT_FOUND",
                message=f"Failed to refresh GitHub skills catalog from {self._repo}@{self._ref}.",
                hint="Check your network connection and the configured skills repo/ref in ~/.canarchy/config.toml.",
            ) from exc

        skills: list[dict[str, Any]] = []
        for manifest_path in manifest_paths:
            text = _download_text(f"{_RAW_BASE}/{self._repo}/{commit}/{manifest_path}")
            manifest = yaml.safe_load(text)
            if not isinstance(manifest, dict):
                raise SkillError(
                    code="SKILL_MANIFEST_INVALID",
                    message=f"Skill manifest '{manifest_path}' did not parse to a mapping.",
                    hint="Ensure repository-backed skill manifests are valid YAML mappings.",
                )
            skills.append(_skill_entry_from_manifest(manifest, manifest_path=manifest_path))

        manifest = {
            "provider": "github",
            "repo": self._repo,
            "commit": commit,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "skills": skills,
        }
        save_manifest("github", manifest)
        return [_make_descriptor(entry, commit, None) for entry in skills]
