"""Dataset provider registry: type definitions, ref parsing, and provider dispatch."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable


class DatasetError(Exception):
    """Raised for dataset provider and cache failures."""

    def __init__(self, code: str, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.hint = hint


@dataclass(frozen=True)
class DatasetDescriptor:
    """Metadata for a public CAN dataset."""

    provider: str
    name: str
    version: str | None
    source_url: str
    license: str
    protocol_family: str  # "can", "can_fd", "j1939", "j1708"
    formats: tuple[str, ...]  # source file formats: "csv", "pcap", "msgpack", etc.
    size_description: str  # human-readable: "3.5 GB", "unknown"
    description: str
    access_notes: str | None  # registration/form requirements, if any
    conversion_targets: tuple[str, ...]  # "candump", "jsonl"
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class DatasetResolution:
    """Result of a dataset fetch operation."""

    descriptor: DatasetDescriptor
    cache_path: Path
    is_cached: bool
    provenance: dict  # sha, fetched_at, source_url, provider


@runtime_checkable
class DatasetProvider(Protocol):
    """Provider protocol for a public CAN dataset catalog."""

    name: str

    def search(self, query: str, limit: int = 20) -> list[DatasetDescriptor]: ...
    def inspect(self, name: str) -> DatasetDescriptor: ...
    def fetch(self, name: str) -> DatasetResolution: ...
    def refresh(self, name: str | None = None) -> list[DatasetDescriptor]: ...


def parse_dataset_ref(ref: str) -> tuple[str | None, str]:
    """Return (provider_name, dataset_name) from 'catalog:road' or bare 'road'."""
    if ":" in ref:
        prefix, name = ref.split(":", 1)
        return prefix, name
    return None, ref


class DatasetProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, DatasetProvider] = {}
        self._search_order: list[str] = []

    def register(self, provider: DatasetProvider, *, prepend: bool = False) -> None:
        self._providers[provider.name] = provider
        if provider.name not in self._search_order:
            if prepend:
                self._search_order.insert(0, provider.name)
            else:
                self._search_order.append(provider.name)

    def get_provider(self, name: str) -> DatasetProvider | None:
        return self._providers.get(name)

    def inspect(self, ref: str) -> DatasetDescriptor:
        provider_name, dataset_name = parse_dataset_ref(ref)
        providers = (
            [self._providers[provider_name]]
            if provider_name and provider_name in self._providers
            else [self._providers[n] for n in self._search_order]
        )
        if provider_name and provider_name not in self._providers:
            raise DatasetError(
                code="DATASET_PROVIDER_NOT_FOUND",
                message=f"Unknown dataset provider '{provider_name}'.",
                hint=f"Registered providers: {', '.join(self._providers) or 'none'}.",
            )
        for provider in providers:
            try:
                return provider.inspect(dataset_name)
            except DatasetError:
                continue
        raise DatasetError(
            code="DATASET_NOT_FOUND",
            message=f"No dataset found for ref '{ref}'.",
            hint="Use `canarchy datasets search <query>` to browse available datasets.",
        )

    def fetch(self, ref: str) -> DatasetResolution:
        provider_name, dataset_name = parse_dataset_ref(ref)
        if provider_name:
            provider = self._providers.get(provider_name)
            if provider is None:
                raise DatasetError(
                    code="DATASET_PROVIDER_NOT_FOUND",
                    message=f"Unknown dataset provider '{provider_name}'.",
                    hint=f"Registered providers: {', '.join(self._providers) or 'none'}.",
                )
            return provider.fetch(dataset_name)
        for name in self._search_order:
            try:
                return self._providers[name].fetch(dataset_name)
            except DatasetError:
                continue
        raise DatasetError(
            code="DATASET_NOT_FOUND",
            message=f"No dataset found for ref '{ref}'.",
            hint="Use `canarchy datasets search <query>` to browse available datasets.",
        )

    def search(
        self, query: str, providers: list[str] | None = None, limit: int = 20
    ) -> list[DatasetDescriptor]:
        names = providers if providers is not None else self._search_order
        results: list[DatasetDescriptor] = []
        seen: set[str] = set()
        for name in names:
            provider = self._providers.get(name)
            if provider is None:
                continue
            for descriptor in provider.search(query, limit=limit):
                key = f"{descriptor.provider}:{descriptor.name}"
                if key not in seen:
                    seen.add(key)
                    results.append(descriptor)
        return results[:limit]

    def list_providers(self) -> list[dict]:
        return [{"name": name, "registered": True} for name in self._search_order]


_registry: DatasetProviderRegistry | None = None


def get_registry() -> DatasetProviderRegistry:
    global _registry
    if _registry is None:
        _registry = _build_default_registry()
    return _registry


def _build_default_registry() -> DatasetProviderRegistry:
    from canarchy.dataset_cache import load_datasets_config
    from canarchy.dataset_catalog import PublicDatasetProvider

    cfg = load_datasets_config()
    registry = DatasetProviderRegistry()

    catalog_cfg = cfg.get("providers", {}).get("catalog", {})
    if catalog_cfg.get("enabled", True):
        registry.register(PublicDatasetProvider())

    return registry


def reset_registry() -> None:
    """Reset the module-level registry (intended for tests)."""
    global _registry
    _registry = None
