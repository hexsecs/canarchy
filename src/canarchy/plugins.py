"""Plugin registry: extension points for processors, sinks, and input adapters."""

from __future__ import annotations

import importlib.metadata
import warnings
from dataclasses import asdict, dataclass, field
from typing import Any, Iterator, Protocol, runtime_checkable

from canarchy import __version__
from canarchy.models import CanFrame

CANARCHY_API_VERSION = "1"


class PluginError(Exception):
    """Raised for plugin registration and compatibility failures."""

    def __init__(self, code: str, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.hint = hint


@dataclass(slots=True, frozen=True)
class ProcessorResult:
    """Result returned by a ProcessorPlugin.process() call."""

    candidates: list[dict[str, Any]]
    metadata: dict[str, Any]
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True, frozen=True)
class PluginMetadata:
    """Inspectable metadata for a registered plugin."""

    name: str
    kind: str
    api_version: str
    version: str | None = None
    source_distribution: str | None = None
    entry_point_group: str | None = None


@runtime_checkable
class ProcessorPlugin(Protocol):
    """Analysis processor: consumes frames and produces ranked candidates."""

    name: str
    api_version: str

    def process(self, frames: list[CanFrame], **kwargs: Any) -> ProcessorResult: ...


@runtime_checkable
class SinkPlugin(Protocol):
    """Output sink: writes a serialized command payload to an external destination."""

    name: str
    api_version: str
    supported_formats: list[str]

    def write(
        self, payload: dict[str, Any], destination: str, *, output_format: str = "json"
    ) -> dict[str, Any]: ...


@runtime_checkable
class InputAdapterPlugin(Protocol):
    """Input adapter: yields CanFrames from a custom source or file format."""

    name: str
    api_version: str
    supported_extensions: list[str]

    def read(self, source: str) -> Iterator[CanFrame]: ...


class PluginRegistry:
    """Registry for built-in and third-party CANarchy plugins."""

    def __init__(self) -> None:
        self._processors: dict[str, ProcessorPlugin] = {}
        self._sinks: dict[str, SinkPlugin] = {}
        self._input_adapters: dict[str, InputAdapterPlugin] = {}
        self._metadata: dict[tuple[str, str], PluginMetadata] = {}

    # --- registration ---

    def register_processor(
        self,
        plugin: ProcessorPlugin,
        *,
        source_distribution: str | None = None,
        version: str | None = None,
        entry_point_group: str | None = None,
    ) -> None:
        """Register a processor plugin. Raises PluginError on invalid interface, version mismatch, or duplicate name."""
        name = _require_interface(plugin, ProcessorPlugin, "process(frames, **kwargs)")
        _require_api_version(plugin.api_version, name)
        if name in self._processors:
            raise PluginError(
                code="PLUGIN_DUPLICATE",
                message=f"A processor named '{name}' is already registered.",
                hint="Use a unique name or unregister the existing processor first.",
            )
        self._processors[name] = plugin
        self._metadata[("processor", name)] = PluginMetadata(
            name=name,
            kind="processor",
            api_version=plugin.api_version,
            version=version,
            source_distribution=source_distribution,
            entry_point_group=entry_point_group,
        )

    def register_sink(
        self,
        plugin: SinkPlugin,
        *,
        source_distribution: str | None = None,
        version: str | None = None,
        entry_point_group: str | None = None,
    ) -> None:
        """Register a sink plugin. Raises PluginError on invalid interface, version mismatch, or duplicate name."""
        name = _require_interface(plugin, SinkPlugin, "supported_formats and write()")
        _require_api_version(plugin.api_version, name)
        if name in self._sinks:
            raise PluginError(
                code="PLUGIN_DUPLICATE",
                message=f"A sink named '{name}' is already registered.",
                hint="Use a unique name or unregister the existing sink first.",
            )
        self._sinks[name] = plugin
        self._metadata[("sink", name)] = PluginMetadata(
            name=name,
            kind="sink",
            api_version=plugin.api_version,
            version=version,
            source_distribution=source_distribution,
            entry_point_group=entry_point_group,
        )

    def register_input_adapter(
        self,
        plugin: InputAdapterPlugin,
        *,
        source_distribution: str | None = None,
        version: str | None = None,
        entry_point_group: str | None = None,
    ) -> None:
        """Register an input adapter plugin. Raises PluginError on invalid interface, version mismatch, or duplicate name."""
        name = _require_interface(plugin, InputAdapterPlugin, "supported_extensions and read()")
        _require_api_version(plugin.api_version, name)
        if name in self._input_adapters:
            raise PluginError(
                code="PLUGIN_DUPLICATE",
                message=f"An input adapter named '{name}' is already registered.",
                hint="Use a unique name or unregister the existing adapter first.",
            )
        self._input_adapters[name] = plugin
        self._metadata[("input", name)] = PluginMetadata(
            name=name,
            kind="input",
            api_version=plugin.api_version,
            version=version,
            source_distribution=source_distribution,
            entry_point_group=entry_point_group,
        )

    # --- lookup ---

    def get_processor(self, name: str) -> ProcessorPlugin | None:
        return self._processors.get(name)

    def get_sink(self, name: str) -> SinkPlugin | None:
        return self._sinks.get(name)

    def get_input_adapter(self, name: str) -> InputAdapterPlugin | None:
        return self._input_adapters.get(name)

    # --- inspection ---

    def list_processors(self) -> list[dict[str, Any]]:
        return [asdict(self._metadata[("processor", p.name)]) for p in self._processors.values()]

    def list_sinks(self) -> list[dict[str, Any]]:
        return [
            {
                **asdict(self._metadata[("sink", s.name)]),
                "supported_formats": s.supported_formats,
            }
            for s in self._sinks.values()
        ]

    def list_input_adapters(self) -> list[dict[str, Any]]:
        return [
            {
                **asdict(self._metadata[("input", a.name)]),
                "supported_extensions": a.supported_extensions,
            }
            for a in self._input_adapters.values()
        ]

    def list_plugins(self) -> list[dict[str, Any]]:
        """Return all registered plugins in deterministic name/kind order."""
        entries = [asdict(metadata) for metadata in self._metadata.values()]
        return sorted(entries, key=lambda entry: (entry["name"], entry["kind"]))

    def plugin_info(self, name: str) -> list[dict[str, Any]]:
        """Return all registered plugin entries matching ``name`` across namespaces."""
        return [entry for entry in self.list_plugins() if entry["name"] == name]


def _require_interface(plugin: Any, protocol: type, required: str) -> str:
    """Validate that plugin satisfies the protocol and return its name.

    Raises PluginError(PLUGIN_INVALID) for missing attributes or a failed isinstance check,
    so callers always receive a structured error instead of a raw AttributeError.
    """
    try:
        name = plugin.name
    except AttributeError:
        raise PluginError(
            code="PLUGIN_INVALID",
            message="Plugin object is missing a 'name' attribute.",
            hint=f"Ensure the class declares 'name', 'api_version', and {required}.",
        )
    if not isinstance(plugin, protocol):
        raise PluginError(
            code="PLUGIN_INVALID",
            message=f"Plugin '{name}' does not implement {protocol.__name__}.",
            hint=f"Ensure the class declares 'name', 'api_version', and {required}.",
        )
    return name


def _require_api_version(api_version: str, plugin_name: str) -> None:
    if api_version != CANARCHY_API_VERSION:
        raise PluginError(
            code="PLUGIN_INCOMPATIBLE",
            message=(
                f"Plugin '{plugin_name}' declares api_version '{api_version}' "
                f"but this CANarchy build requires '{CANARCHY_API_VERSION}'."
            ),
            hint=f"Update the plugin to declare api_version='{CANARCHY_API_VERSION}'.",
        )


_registry: PluginRegistry | None = None


def get_registry() -> PluginRegistry:
    """Return the module-level plugin registry, building it on first access."""
    global _registry
    if _registry is None:
        _registry = _build_default_registry()
    return _registry


def _build_default_registry() -> PluginRegistry:
    registry = PluginRegistry()

    from canarchy.re_processors import (
        CounterCandidateProcessor,
        EntropyCandidateProcessor,
        SignalAnalysisProcessor,
    )

    registry.register_processor(
        CounterCandidateProcessor(), source_distribution="canarchy", version=__version__
    )
    registry.register_processor(
        EntropyCandidateProcessor(), source_distribution="canarchy", version=__version__
    )
    registry.register_processor(
        SignalAnalysisProcessor(), source_distribution="canarchy", version=__version__
    )

    _load_entry_point_plugins(registry)
    return registry


def _load_entry_point_plugins(registry: PluginRegistry) -> None:
    """Discover and register third-party plugins declared via Python entry points."""
    groups: list[tuple[str, Any]] = [
        ("canarchy.processors", registry.register_processor),
        ("canarchy.sinks", registry.register_sink),
        ("canarchy.input_adapters", registry.register_input_adapter),
    ]
    for group, register_fn in groups:
        try:
            eps = importlib.metadata.entry_points(group=group)
        except Exception:
            continue
        for ep in eps:
            try:
                plugin_cls = ep.load()
                dist = getattr(ep, "dist", None)
                source_distribution = getattr(dist, "name", None)
                version = getattr(dist, "version", None)
                register_fn(
                    plugin_cls(),
                    source_distribution=source_distribution,
                    version=version,
                    entry_point_group=group,
                )
            except Exception as exc:
                warnings.warn(
                    f"Failed to load plugin '{ep.name}' from group '{group}': {exc}",
                    stacklevel=2,
                )


def reset_registry() -> None:
    """Reset the module-level registry singleton (intended for tests)."""
    global _registry
    _registry = None
