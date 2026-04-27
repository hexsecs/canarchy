"""Skills provider registry: descriptors, ref parsing, and provider dispatch."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from canarchy.skills import SkillError

ProviderKind = Literal["github"]


@dataclass(frozen=True)
class SkillDescriptor:
    provider: ProviderKind
    name: str
    publisher: str
    version: str | None
    source_ref: str
    cache_path: Path | None
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class SkillResolution:
    descriptor: SkillDescriptor
    local_manifest_path: Path
    local_entry_path: Path
    is_cached: bool


@runtime_checkable
class SkillProvider(Protocol):
    name: str

    def search(self, query: str, limit: int = 20) -> list[SkillDescriptor]: ...
    def resolve(self, ref: str) -> SkillResolution: ...
    def refresh(self, ref: str | None = None) -> list[SkillDescriptor]: ...


def parse_provider_ref(ref: str) -> tuple[str | None, str]:
    if ":" in ref:
        provider, name = ref.split(":", 1)
        return provider, name
    return None, ref


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, SkillProvider] = {}
        self._search_order: list[str] = []

    def register(self, provider: SkillProvider, *, prepend: bool = False) -> None:
        self._providers[provider.name] = provider
        if provider.name not in self._search_order:
            if prepend:
                self._search_order.insert(0, provider.name)
            else:
                self._search_order.append(provider.name)

    def get_provider(self, name: str) -> SkillProvider | None:
        return self._providers.get(name)

    def resolve(self, ref: str) -> SkillResolution:
        provider_name, logical_name = parse_provider_ref(ref)
        if provider_name is not None:
            provider = self._providers.get(provider_name)
            if provider is None:
                raise SkillError(
                    code="SKILL_PROVIDER_NOT_FOUND",
                    message=f"Unknown skills provider '{provider_name}'.",
                    hint=f"Registered providers: {', '.join(self._providers) or 'none'}.",
                )
            return provider.resolve(logical_name)

        candidates: list[SkillDescriptor] = []
        for name in self._search_order:
            provider = self._providers[name]
            hits = provider.search(logical_name, limit=5)
            candidates.extend(hits)
            exact = [d for d in hits if d.name == logical_name]
            if exact:
                return self._providers[exact[0].provider].resolve(logical_name)

        candidate_names = [d.name for d in candidates[:5]]
        raise SkillError(
            code="SKILL_NOT_FOUND",
            message=f"No skill found for ref '{ref}'.",
            hint=(
                f"Did you mean: {', '.join(candidate_names)}?"
                if candidate_names
                else "Use 'github:<name>' after refreshing the skills catalog."
            ),
        )

    def search(self, query: str, providers: list[str] | None = None) -> list[SkillDescriptor]:
        names = providers if providers is not None else self._search_order
        results: list[SkillDescriptor] = []
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
    from canarchy.skills_cache import load_skills_config
    from canarchy.skills_github import GitHubSkillProvider

    registry = ProviderRegistry()
    cfg = load_skills_config()
    if cfg.get("providers", {}).get("github", {}).get("enabled", True):
        registry.register(GitHubSkillProvider())
    return registry


def reset_registry() -> None:
    global _registry
    _registry = None
