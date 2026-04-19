"""opendbc catalog provider: fetches DBC files from commaai/opendbc via GitHub API."""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from canarchy.dbc import DbcError
from canarchy.dbc_provider import DbcDescriptor, DbcResolution

_GITHUB_API = "https://api.github.com"
_RAW_BASE = "https://raw.githubusercontent.com"


def _github_get(url: str) -> Any:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def _resolve_commit(repo: str, ref: str) -> str:
    data = _github_get(f"{_GITHUB_API}/repos/{repo}/commits/{ref}")
    return data["sha"]


def _list_dbc_files(repo: str, commit: str) -> list[dict[str, str]]:
    """Return list of {name, path, sha} for all .dbc files under opendbc/dbc/."""
    tree_data = _github_get(
        f"{_GITHUB_API}/repos/{repo}/git/trees/{commit}?recursive=1"
    )
    results = []
    for item in tree_data.get("tree", []):
        path = item.get("path", "")
        if path.startswith("opendbc/dbc/") and path.endswith(".dbc"):
            results.append(
                {
                    "name": Path(path).stem,
                    "path": path,
                    "sha": item.get("sha", ""),
                }
            )
    return results


def _download_file(repo: str, commit: str, path: str, dest: Path) -> None:
    url = f"{_RAW_BASE}/{repo}/{commit}/{path}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=30) as resp:
        dest.write_bytes(resp.read())


def _make_descriptor(entry: dict[str, str], commit: str, cache_path: Path | None) -> DbcDescriptor:
    brand = _infer_brand(entry["name"])
    return DbcDescriptor(
        provider="opendbc",
        name=entry["name"],
        version=commit[:12],
        source_ref=f"opendbc:{entry['name']}",
        cache_path=cache_path,
        sha256=None,
        metadata={"path": entry["path"], "brand": brand},
    )


def _infer_brand(name: str) -> str | None:
    prefixes = [
        "toyota", "honda", "ford", "gm", "chevrolet", "cadillac", "buick",
        "chrysler", "dodge", "jeep", "ram", "hyundai", "kia", "genesis",
        "subaru", "volkswagen", "audi", "bmw", "mercedes", "nissan", "mazda",
        "volvo", "tesla", "rivian", "acura", "infiniti", "lexus",
    ]
    lower = name.lower()
    for prefix in prefixes:
        if lower.startswith(prefix):
            return prefix
    return None


def _score_match(name: str, query: str) -> int:
    lower_name = name.lower()
    lower_query = query.lower()
    if lower_name == lower_query:
        return 100
    if lower_name.startswith(lower_query):
        return 80
    if lower_query in lower_name:
        return 60
    words = lower_query.split()
    if all(w in lower_name for w in words):
        return 40
    if any(w in lower_name for w in words):
        return 20
    return 0


class OpenDbcProvider:
    name = "opendbc"

    def __init__(self) -> None:
        from canarchy.dbc_cache import load_dbc_config

        cfg = load_dbc_config()
        opendbc_cfg = cfg.get("providers", {}).get("opendbc", {})
        self._repo: str = opendbc_cfg.get("repo", "commaai/opendbc")
        self._ref: str = opendbc_cfg.get("ref", "master")
        self._auto_refresh: bool = bool(opendbc_cfg.get("auto_refresh", False))

    def _manifest(self) -> dict[str, Any] | None:
        from canarchy.dbc_cache import load_manifest

        return load_manifest("opendbc")

    def _catalog(self) -> list[dict[str, str]]:
        manifest = self._manifest()
        if manifest is None:
            return []
        return manifest.get("dbcs", [])

    def _commit(self) -> str | None:
        manifest = self._manifest()
        if manifest is None:
            return None
        return manifest.get("commit")

    def search(self, query: str, limit: int = 20) -> list[DbcDescriptor]:
        catalog = self._catalog()
        if not catalog:
            return []
        commit = self._commit() or ""
        scored = [
            (entry, _score_match(entry["name"], query))
            for entry in catalog
        ]
        scored = [(e, s) for e, s in scored if s > 0]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [
            _make_descriptor(entry, commit, None)
            for entry, _ in scored[:limit]
        ]

    def resolve(self, ref: str) -> DbcResolution:
        from canarchy.dbc_cache import cached_file_path, provider_cache_dir

        manifest = self._manifest()
        if manifest is None:
            if self._auto_refresh:
                self.refresh()
                manifest = self._manifest()
            if manifest is None:
                raise DbcError(
                    code="DBC_CACHE_MISS",
                    message=(
                        "The opendbc catalog has not been cached yet. "
                        "Run the following command to populate it:\n\n"
                        "  canarchy dbc cache refresh --provider opendbc\n\n"
                        "To avoid this step in the future, set "
                        "`auto_refresh = true` under "
                        "[dbc.providers.opendbc] in ~/.canarchy/config.toml."
                    ),
                    hint="canarchy dbc cache refresh --provider opendbc",
                )

        commit = manifest["commit"]
        catalog = manifest.get("dbcs", [])
        entry = next((e for e in catalog if e["name"] == ref), None)
        if entry is None:
            candidates = [e["name"] for e in catalog if ref.lower() in e["name"].lower()][:5]
            raise DbcError(
                code="DBC_NOT_FOUND",
                message=f"DBC '{ref}' not found in opendbc catalog.",
                hint=(
                    f"Did you mean: {', '.join(candidates)}?"
                    if candidates
                    else "Run `canarchy dbc search <query> --provider opendbc` to find available DBCs."
                ),
            )

        dest = cached_file_path("opendbc", commit, Path(entry["path"]).name)
        if not dest.exists():
            try:
                _download_file(self._repo, commit, entry["path"], dest)
            except Exception as exc:
                raise DbcError(
                    code="DBC_CACHE_STALE",
                    message=f"Failed to download '{ref}' from opendbc.",
                    hint="Check your network connection or re-run `canarchy dbc cache refresh --provider opendbc`.",
                ) from exc

        descriptor = _make_descriptor(entry, commit, dest)
        return DbcResolution(descriptor=descriptor, local_path=dest, is_cached=True)

    def refresh(self, ref: str | None = None) -> list[DbcDescriptor]:
        from canarchy.dbc_cache import save_manifest

        try:
            commit = _resolve_commit(self._repo, self._ref)
        except Exception as exc:
            raise DbcError(
                code="DBC_PROVIDER_NOT_FOUND",
                message=f"Failed to resolve opendbc ref '{self._ref}' from {self._repo}.",
                hint="Check your network connection and the configured repo/ref in ~/.canarchy/config.toml.",
            ) from exc

        try:
            dbc_files = _list_dbc_files(self._repo, commit)
        except Exception as exc:
            raise DbcError(
                code="DBC_PROVIDER_NOT_FOUND",
                message="Failed to list DBC files from opendbc.",
                hint="Check your network connection.",
            ) from exc

        manifest: dict[str, Any] = {
            "provider": "opendbc",
            "repo": self._repo,
            "commit": commit,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "dbcs": dbc_files,
        }
        save_manifest("opendbc", manifest)
        return [_make_descriptor(entry, commit, None) for entry in dbc_files]
