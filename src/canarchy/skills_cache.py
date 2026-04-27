"""Cache directory management for repository-backed skills."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_CACHE_ROOT = Path.home() / ".canarchy" / "cache" / "skills"
_CONFIG_PATH = Path.home() / ".canarchy" / "config.toml"


def cache_root() -> Path:
    return _CACHE_ROOT


def provider_cache_dir(provider_name: str) -> Path:
    return _CACHE_ROOT / "providers" / provider_name


def provider_manifest_path(provider_name: str) -> Path:
    return provider_cache_dir(provider_name) / "manifest.json"


def load_manifest(provider_name: str) -> dict[str, Any] | None:
    path = provider_manifest_path(provider_name)
    if not path.exists():
        return None
    with path.open() as f:
        return json.load(f)


def save_manifest(provider_name: str, manifest: dict[str, Any]) -> None:
    path = provider_manifest_path(provider_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        json.dump(manifest, f, indent=2)


def cached_file_path(provider_name: str, commit: str, relative_path: str) -> Path:
    return provider_cache_dir(provider_name) / "files" / commit / relative_path


def safe_cached_file_path(provider_name: str, commit: str, relative_path: str) -> Path:
    base_dir = provider_cache_dir(provider_name) / "files" / commit
    target = (base_dir / relative_path).resolve(strict=False)
    if base_dir.resolve(strict=False) not in target.parents and target != base_dir.resolve(strict=False):
        raise ValueError(f"relative path escapes cache root: {relative_path}")
    return target


def cache_list() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    providers_dir = _CACHE_ROOT / "providers"
    if not providers_dir.exists():
        return results
    for provider_dir in sorted(providers_dir.iterdir()):
        manifest_path = provider_dir / "manifest.json"
        if not manifest_path.exists():
            continue
        with manifest_path.open() as f:
            manifest = json.load(f)
        results.append(
            {
                "provider": manifest.get("provider", provider_dir.name),
                "repo": manifest.get("repo"),
                "commit": manifest.get("commit"),
                "generated_at": manifest.get("generated_at"),
                "skill_count": len(manifest.get("skills", [])),
                "cache_dir": str(provider_dir),
            }
        )
    return results


def load_skills_config() -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "default_provider": os.environ.get("CANARCHY_SKILLS_DEFAULT_PROVIDER", "github"),
        "search_order": ["github"],
        "providers": {
            "github": {
                "enabled": True,
                "repo": os.environ.get("CANARCHY_SKILLS_GITHUB_REPO", "hexsecs/canarchy-skills"),
                "ref": os.environ.get("CANARCHY_SKILLS_GITHUB_REF", "main"),
                "auto_refresh": False,
            }
        },
    }
    if not _CONFIG_PATH.exists():
        return defaults
    try:
        import tomllib
        with _CONFIG_PATH.open("rb") as f:
            raw = tomllib.load(f)
    except Exception:
        return defaults
    skills_section = raw.get("skills", {})
    if not skills_section:
        return defaults
    result = dict(defaults)
    for key in ("default_provider", "search_order"):
        if key in skills_section:
            result[key] = skills_section[key]
    if "providers" in skills_section:
        for name, cfg in skills_section["providers"].items():
            if name not in result["providers"]:
                result["providers"][name] = {}
            result["providers"][name].update(cfg)
    return result
