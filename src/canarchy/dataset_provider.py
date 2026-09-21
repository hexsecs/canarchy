"""Dataset provider registry: type definitions, ref parsing, and provider dispatch."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


class DatasetError(Exception):
    """Raised for dataset provider and cache failures.

    ``category`` separates a caller's mistake from an environment failure so
    the CLI can map it to the documented exit code: ``"user"`` (bad ref,
    unknown dataset, unsupported operation) exits 1, ``"backend"`` (cache
    write failure, unreachable host) exits 2. It defaults to ``"user"``,
    which is what every existing raise site means.
    """

    def __init__(
        self,
        code: str,
        message: str,
        hint: str | None = None,
        category: str = "user",
    ) -> None:
        super().__init__(message)
        self.code = code
        self.hint = hint
        self.category = category


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
    #: True when `cache_path` holds the dataset's actual bytes rather than a
    #: provenance record for a file that still has to be downloaded. Providers
    #: that generate or download data set this; the default False keeps the
    #: existing provenance-only providers behaving as before (#460 review).
    data_materialized: bool = False


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
        """Return registered providers in effective resolution order.

        `order` makes the effective `[datasets].search_order` inspectable: it
        is the position a bare ref consults this provider at (#514).
        """
        return [
            {"name": name, "registered": True, "order": index}
            for index, name in enumerate(self._search_order)
        ]

    def search_order(self) -> list[str]:
        """Return the effective provider resolution order for bare refs."""
        return list(self._search_order)


_registry: DatasetProviderRegistry | None = None


def get_registry() -> DatasetProviderRegistry:
    global _registry
    if _registry is None:
        _registry = _build_default_registry()
    return _registry


def _provider_factories() -> dict[str, Callable[[], DatasetProvider]]:
    """Return the built-in providers by name, in built-in resolution order."""
    from canarchy.dataset_catalog import PublicDatasetProvider
    from canarchy.dataset_offline import OfflineDatasetProvider

    return {"catalog": PublicDatasetProvider, "offline": OfflineDatasetProvider}


def _invalid_search_order(known: Sequence[str]) -> DatasetError:
    example = ", ".join(f'"{name}"' for name in known)
    return DatasetError(
        code="DATASET_SEARCH_ORDER_INVALID",
        message="`[datasets].search_order` must be a list of provider names.",
        hint=f"Set `search_order = [{example}]` in ~/.canarchy/config.toml.",
    )


def resolve_search_order(configured: Any, known: Sequence[str]) -> list[str]:
    """Return the effective provider order for a configured `search_order`.

    The configured names come first, in the order the operator wrote them, so
    `[datasets].search_order` actually decides which provider a bare ref
    resolves against. A known provider the operator did not list is appended
    after them rather than dropped: `search_order` states a preference, not an
    allow-list, so a partial list never silently makes `offline:can-basic`
    unresolvable (#514).

    An unknown name is an error rather than a no-op -- silently ignoring the
    whole setting is the defect this replaces.
    """
    if isinstance(configured, str) or not isinstance(configured, (list, tuple)):
        raise _invalid_search_order(known)

    order: list[str] = []
    for entry in configured:
        if not isinstance(entry, str):
            raise _invalid_search_order(known)
        if entry not in known:
            raise DatasetError(
                code="DATASET_PROVIDER_NOT_FOUND",
                message=f"Unknown dataset provider '{entry}' in `[datasets].search_order`.",
                hint=(
                    f"Known providers: {', '.join(known) or 'none'}. "
                    "Fix `[datasets].search_order` in ~/.canarchy/config.toml."
                ),
            )
        if entry not in order:
            order.append(entry)

    order.extend(name for name in known if name not in order)
    return order


def _build_default_registry() -> DatasetProviderRegistry:
    from canarchy.dataset_cache import DEFAULT_SEARCH_ORDER, load_datasets_config

    cfg = load_datasets_config()
    factories = _provider_factories()
    known = [name for name in DEFAULT_SEARCH_ORDER if name in factories]
    known.extend(name for name in factories if name not in known)

    order = resolve_search_order(cfg.get("search_order", list(DEFAULT_SEARCH_ORDER)), known)

    providers_cfg = cfg.get("providers", {}) or {}
    registry = DatasetProviderRegistry()
    for name in order:
        provider_cfg = providers_cfg.get(name, {}) or {}
        if provider_cfg.get("enabled", True):
            registry.register(factories[name]())

    return registry


def reset_registry() -> None:
    """Reset the module-level registry (intended for tests)."""
    global _registry
    _registry = None
