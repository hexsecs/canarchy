"""DBC provider registry: type definitions, ref parsing, and provider dispatch."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from canarchy.dbc import DbcError

ProviderKind = Literal["local", "opendbc"]

_PROVIDER_ALIASES: dict[str, str] = {"comma": "opendbc"}


@dataclass(frozen=True)
class DbcDescriptor:
    provider: ProviderKind
    name: str
    version: str | None
    source_ref: str
    cache_path: Path | None
    sha256: str | None
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class DbcResolution:
    descriptor: DbcDescriptor
    local_path: Path
    is_cached: bool


@runtime_checkable
class DbcProvider(Protocol):
    name: str

    def search(self, query: str, limit: int = 20) -> list[DbcDescriptor]: ...
    def resolve(self, ref: str) -> DbcResolution: ...
    def refresh(self, ref: str | None = None) -> list[DbcDescriptor]: ...


def parse_provider_ref(ref: str) -> tuple[str | None, str]:
    """Return (provider_name, logical_name) from a ref like 'opendbc:foo' or 'foo'."""
    if ":" in ref:
        prefix, name = ref.split(":", 1)
        canonical = _PROVIDER_ALIASES.get(prefix, prefix)
        return canonical, name
    return None, ref


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, DbcProvider] = {}
        self._search_order: list[str] = []

    def register(self, provider: DbcProvider, *, prepend: bool = False) -> None:
        self._providers[provider.name] = provider
        if provider.name not in self._search_order:
            if prepend:
                self._search_order.insert(0, provider.name)
            else:
                self._search_order.append(provider.name)

    def get_provider(self, name: str) -> DbcProvider | None:
        return self._providers.get(name)

    def resolve(self, ref: str) -> DbcResolution:
        # 1. Explicit local path (absolute or relative) that exists on disk.
        candidate = Path(ref)
        if candidate.exists() and candidate.is_file():
            from canarchy.dbc_provider_local import LocalDbcProvider

            return LocalDbcProvider().resolve(ref)

        # 2. Provider-prefixed ref: opendbc:<name> or comma:<name>.
        provider_name, logical_name = parse_provider_ref(ref)
        if provider_name is not None:
            provider = self._providers.get(provider_name)
            if provider is None:
                raise DbcError(
                    code="DBC_PROVIDER_NOT_FOUND",
                    message=f"Unknown DBC provider '{provider_name}'.",
                    hint=f"Registered providers: {', '.join(self._providers) or 'none'}.",
                )
            return provider.resolve(logical_name)

        # 3. Bare name: search enabled providers in order.
        candidates: list[DbcDescriptor] = []
        for name in self._search_order:
            provider = self._providers[name]
            hits = provider.search(logical_name, limit=5)
            candidates.extend(hits)
            if hits:
                exact = [d for d in hits if d.name == logical_name]
                if exact:
                    return self._providers[exact[0].provider].resolve(logical_name)

        candidate_names = [d.name for d in candidates[:5]]
        raise DbcError(
            code="DBC_NOT_FOUND",
            message=f"No DBC found for ref '{ref}'.",
            hint=(
                f"Did you mean: {', '.join(candidate_names)}?"
                if candidate_names
                else "Use an absolute/relative path, or 'opendbc:<name>' to search the opendbc catalog."
            ),
        )

    def search(self, query: str, providers: list[str] | None = None) -> list[DbcDescriptor]:
        names = providers if providers is not None else self._search_order
        results: list[DbcDescriptor] = []
        for name in names:
            provider = self._providers.get(name)
            if provider is None:
                continue
            results.extend(provider.search(query))
        return results

    def list_providers(self) -> list[dict]:
        return [{"name": name, "registered": True} for name in self._search_order]


_registry: ProviderRegistry | None = None


def get_registry() -> ProviderRegistry:
    global _registry
    if _registry is None:
        _registry = _build_default_registry()
    return _registry


def _build_default_registry() -> ProviderRegistry:
    from canarchy.dbc_provider_local import LocalDbcProvider

    registry = ProviderRegistry()
    registry.register(LocalDbcProvider())

    try:
        from canarchy.dbc_opendbc import OpenDbcProvider
        from canarchy.dbc_cache import load_dbc_config

        cfg = load_dbc_config()
        if cfg.get("providers", {}).get("opendbc", {}).get("enabled", True):
            registry.register(OpenDbcProvider())
    except Exception:
        pass

    return registry


def reset_registry() -> None:
    """Reset the module-level registry (used in tests)."""
    global _registry
    _registry = None


def resolve_dbc_ref(ref: str) -> str:
    """Resolve a DBC ref to a local file path string suitable for cantools."""
    resolution = get_registry().resolve(ref)
    return str(resolution.local_path)
