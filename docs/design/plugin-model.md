# Design: Plugin Model

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented (Phase 1–4) |
| Test spec | `docs/tests/plugin-model.md` |
| Implementation | `src/canarchy/plugins.py`, `src/canarchy/re_processors.py` |
| Author guide | `docs/plugin-guide.md` |

---

## Motivation

CANarchy's shared `execute_command()` path is the behavioral contract for all front ends (CLI, shell, TUI, MCP).
The plugin model extends that shared engine at well-defined boundaries without requiring a fork.

Third-party authors can add custom decoders, analysis processors, and output sinks by publishing a Python
package and declaring it in `pyproject.toml`. CANarchy discovers and registers these at startup via Python
entry points, following the same lazy-singleton registry pattern already used by the DBC and skills providers.

---

## Guiding Constraints

1. Plugins extend the shared engine, not any specific front end.
2. No plugin may bypass the canonical `CommandResult` envelope or output modes.
3. Plugin loading must not break startup when a plugin is absent, broken, or incompatible.
4. The registry pattern follows the existing DBC provider model: lazy singleton, reset-able in tests, config-driven.
5. Phase 1 covers three extension points. Command registration is deferred to a later phase.

---

## Extension Points

### 1. Processor

A processor consumes a list of `CanFrame` objects and returns ranked candidates plus analysis metadata.

```
frames: list[CanFrame]  →  ProcessorPlugin.process()  →  ProcessorResult
```

Use cases: entropy analysis, counter detection, signal inference, custom anomaly detectors.

### 2. Sink

A sink writes a serialized command payload to an external destination or custom format.

```
payload: dict  →  SinkPlugin.write()  →  dict (write metadata)
```

Use cases: database export, remote telemetry, custom file formats, SIEM integration.

### 3. Input Adapter

An input adapter yields `CanFrame` objects from a custom source or file format not natively supported by
the transport layer.

```
source: str  →  InputAdapterPlugin.read()  →  Iterator[CanFrame]
```

Use cases: proprietary capture formats, hardware-specific log files, cloud storage backends.

---

## API Version Contract

Every plugin must declare `api_version = "1"`. The registry rejects any plugin whose `api_version` does
not exactly match `CANARCHY_API_VERSION`. This is an explicit compatibility gate; the registry never
silently degrades.

The API version will increment when a breaking change is made to any plugin protocol. Minor additive
changes (new optional kwargs, new metadata fields) do not require a version bump.

---

## Protocol Definitions

```python
CANARCHY_API_VERSION = "1"

@runtime_checkable
class ProcessorPlugin(Protocol):
    name: str
    api_version: str
    def process(self, frames: list[CanFrame], **kwargs: Any) -> ProcessorResult: ...

@runtime_checkable
class SinkPlugin(Protocol):
    name: str
    api_version: str
    supported_formats: list[str]
    def write(self, payload: dict[str, Any], destination: str, *, output_format: str = "json") -> dict[str, Any]: ...

@runtime_checkable
class InputAdapterPlugin(Protocol):
    name: str
    api_version: str
    supported_extensions: list[str]
    def read(self, source: str) -> Iterator[CanFrame]: ...

@dataclass(slots=True, frozen=True)
class ProcessorResult:
    candidates: list[dict[str, Any]]
    metadata: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
```

---

## Registry

`PluginRegistry` holds three independent namespaces: processors, sinks, and input adapters.
Names must be unique within each namespace.

### Registration errors

| Code | Condition |
|------|-----------|
| `PLUGIN_INCOMPATIBLE` | `api_version` does not match `CANARCHY_API_VERSION` |
| `PLUGIN_DUPLICATE` | A plugin with the same name is already registered |
| `PLUGIN_INVALID` | Object does not satisfy the runtime-checkable protocol |

### Singleton lifecycle

```python
get_registry()   # builds the default registry on first call
reset_registry() # resets to None (tests only)
```

`_build_default_registry()` registers all built-in plugins then calls `_load_entry_point_plugins()`.

---

## Discovery: Entry Points

Third-party plugins are discovered via Python packaging entry points.

| Entry point group | Extension point |
|-------------------|----------------|
| `canarchy.processors` | `ProcessorPlugin` |
| `canarchy.sinks` | `SinkPlugin` |
| `canarchy.input_adapters` | `InputAdapterPlugin` |

A third-party `pyproject.toml` example:

```toml
[project.entry-points."canarchy.processors"]
my-detector = "my_package.plugin:MyDetectorPlugin"
```

**Error isolation:** `PluginError` from an entry point plugin propagates (the author must fix the
incompatibility). Any other exception from loading a third-party entry point is caught and emitted as
a `warnings.warn` so that a single broken plugin does not prevent CANarchy from starting.

---

## Built-in Processors (Phase 3 Migration)

The three heuristic reverse-engineering processors are the first built-in implementations.
They are registered by `_build_default_registry()` and serve as the proof-of-contract migration.

| Name | Class | Source function |
|------|-------|-----------------|
| `counter-candidates` | `CounterCandidateProcessor` | `counter_candidates()` |
| `entropy-candidates` | `EntropyCandidateProcessor` | `entropy_candidates()` |
| `signal-analysis` | `SignalAnalysisProcessor` | `signal_analysis()` |

`reverse_engineering_payload()` in `cli.py` looks these up via `get_registry().get_processor(name)`.
If a processor is absent the command fails with `PLUGIN_NOT_FOUND`; the CLI surface and output envelope
are unchanged.

---

## Non-Goals (Phase 1)

- Plugin sandboxing or code signing
- Plugin marketplace or discovery UI
- Command registration via plugins (deferred to a later phase)
- Migrating every existing command — one proof migration is sufficient

---

## Future Work

- Command registration extension point so plugins can add new top-level commands
- Config-driven enable/disable per plugin (mirrors the DBC provider pattern)
- Plugin author verification / signing for security-sensitive deployments
