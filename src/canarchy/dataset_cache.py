"""Dataset provider cache: manifest persistence under ~/.canarchy/cache/datasets/."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def cache_root() -> Path:
    return Path.home() / ".canarchy" / "cache" / "datasets"


def provider_cache_dir(provider_name: str) -> Path:
    return cache_root() / "providers" / provider_name


def provider_manifest_path(provider_name: str) -> Path:
    return provider_cache_dir(provider_name) / "manifest.json"


def dataset_provenance_path(provider_name: str, dataset_name: str) -> Path:
    return provider_cache_dir(provider_name) / "provenance" / f"{dataset_name}.json"


def load_manifest(provider_name: str) -> dict | None:
    import json

    path = provider_manifest_path(provider_name)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def save_manifest(provider_name: str, manifest: dict) -> None:
    import json

    path = provider_manifest_path(provider_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2))


def load_provenance(provider_name: str, dataset_name: str) -> dict | None:
    import json

    path = dataset_provenance_path(provider_name, dataset_name)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def save_provenance(provider_name: str, dataset_name: str, provenance: dict) -> Path:
    import json

    path = dataset_provenance_path(provider_name, dataset_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(provenance, indent=2))
    return path


def cache_list() -> list[dict[str, Any]]:
    """Return a summary of all cached dataset providers."""
    import json

    root = cache_root() / "providers"
    if not root.exists():
        return []
    entries = []
    for provider_dir in sorted(root.iterdir()):
        if not provider_dir.is_dir():
            continue
        manifest_path = provider_dir / "manifest.json"
        manifest: dict = {}
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text())
            except Exception:
                pass
        provenance_dir = provider_dir / "provenance"
        fetched_count = len(list(provenance_dir.glob("*.json"))) if provenance_dir.exists() else 0
        entries.append(
            {
                "provider": provider_dir.name,
                "dataset_count": manifest.get("dataset_count", 0),
                "generated_at": manifest.get("generated_at"),
                "fetched_count": fetched_count,
                "cache_dir": str(provider_dir),
            }
        )
    return entries


def load_datasets_config() -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "default_provider": os.environ.get("CANARCHY_DATASETS_DEFAULT_PROVIDER", "catalog"),
        "search_order": ["catalog"],
        "providers": {
            "catalog": {
                "enabled": True,
            }
        },
    }

    config_path = Path.home() / ".canarchy" / "config.toml"
    if not config_path.exists():
        return defaults

    try:
        import tomllib
    except ImportError:
        return defaults

    try:
        raw = tomllib.loads(config_path.read_text())
    except Exception:
        return defaults

    section: dict = raw.get("datasets", {})

    if "default_provider" in section:
        defaults["default_provider"] = section["default_provider"]
    if "search_order" in section:
        defaults["search_order"] = section["search_order"]
    if "providers" in section:
        for pname, pconf in section["providers"].items():
            if pname not in defaults["providers"]:
                defaults["providers"][pname] = {}
            defaults["providers"][pname].update(pconf)

    return defaults


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
