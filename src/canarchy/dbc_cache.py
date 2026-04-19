"""Cache directory management for DBC provider files."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

_CACHE_ROOT = Path.home() / ".canarchy" / "cache" / "dbc"
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


def cached_file_dir(provider_name: str, commit: str) -> Path:
    return provider_cache_dir(provider_name) / "files" / commit


def cached_file_path(provider_name: str, commit: str, filename: str) -> Path:
    return cached_file_dir(provider_name, commit) / filename


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def cache_list() -> list[dict[str, Any]]:
    """Return a summary of all cached provider manifests."""
    results = []
    providers_dir = _CACHE_ROOT / "providers"
    if not providers_dir.exists():
        return results
    for provider_dir in sorted(providers_dir.iterdir()):
        manifest_path = provider_dir / "manifest.json"
        if not manifest_path.exists():
            continue
        with manifest_path.open() as f:
            manifest = json.load(f)
        dbc_count = len(manifest.get("dbcs", []))
        results.append(
            {
                "provider": manifest.get("provider", provider_dir.name),
                "repo": manifest.get("repo"),
                "commit": manifest.get("commit"),
                "generated_at": manifest.get("generated_at"),
                "dbc_count": dbc_count,
                "cache_dir": str(provider_dir),
            }
        )
    return results


def cache_prune(provider_name: str | None = None) -> list[str]:
    """Remove stale commit snapshots, keeping only the pinned commit. Returns removed paths."""
    removed = []
    providers_dir = _CACHE_ROOT / "providers"
    if not providers_dir.exists():
        return removed

    targets = (
        [providers_dir / provider_name]
        if provider_name
        else list(providers_dir.iterdir())
    )
    for provider_dir in targets:
        if not provider_dir.is_dir():
            continue
        manifest_path = provider_dir / "manifest.json"
        if not manifest_path.exists():
            continue
        with manifest_path.open() as f:
            manifest = json.load(f)
        pinned_commit = manifest.get("commit")
        files_dir = provider_dir / "files"
        if not files_dir.exists():
            continue
        for commit_dir in files_dir.iterdir():
            if commit_dir.name != pinned_commit:
                import shutil
                shutil.rmtree(commit_dir)
                removed.append(str(commit_dir))
    return removed


def load_dbc_config() -> dict[str, Any]:
    """Return the [dbc] section from ~/.canarchy/config.toml, or defaults."""
    defaults: dict[str, Any] = {
        "default_provider": os.environ.get("CANARCHY_DBC_DEFAULT_PROVIDER", "local"),
        "search_order": ["local", "opendbc"],
        "providers": {
            "opendbc": {
                "enabled": True,
                "mode": "cache",
                "repo": os.environ.get("CANARCHY_DBC_OPENDBC_REPO", "commaai/opendbc"),
                "ref": os.environ.get("CANARCHY_DBC_OPENDBC_REF", "master"),
                "auto_refresh": False,
            }
        },
    }
    if not _CONFIG_PATH.exists():
        return defaults

    try:
        import tomllib
    except ImportError:
        return defaults

    try:
        with _CONFIG_PATH.open("rb") as f:
            raw = tomllib.load(f)
    except Exception:
        return defaults

    dbc_section = raw.get("dbc", {})
    if not dbc_section:
        return defaults

    # Merge top-level keys.
    result = dict(defaults)
    for key in ("default_provider", "search_order"):
        if key in dbc_section:
            result[key] = dbc_section[key]

    # Merge provider sub-sections.
    if "providers" in dbc_section:
        for pname, pconfig in dbc_section["providers"].items():
            if pname not in result["providers"]:
                result["providers"][pname] = {}
            result["providers"][pname].update(pconfig)

    return result
