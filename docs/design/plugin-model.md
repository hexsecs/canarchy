# Design: Plugin Model

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented (Phase 1–5) |
| Test spec | `docs/tests/plugin-model.md` |
| Implementation | `src/canarchy/plugins.py`, `src/canarchy/re_processors.py`, `src/canarchy/cli.py` |
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

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-PLUGIN-01` | Ubiquitous | The system shall build the default plugin registry with the built-in reverse-engineering processors registered. |
| `REQ-PLUGIN-02` | Ubiquitous | The system shall return registered plugins by exact name within their namespace. |
| `REQ-PLUGIN-03` | Ubiquitous | The system shall return no plugin when a namespace lookup uses an unknown name. |
| `REQ-PLUGIN-04` | Unwanted behaviour | If a duplicate plugin name is registered in the same namespace, the system shall raise `PLUGIN_DUPLICATE`. |
| `REQ-PLUGIN-05` | Unwanted behaviour | If a plugin declares an incompatible API version, the system shall raise `PLUGIN_INCOMPATIBLE`. |
| `REQ-PLUGIN-06` | Unwanted behaviour | If a plugin object does not satisfy its protocol, the system shall raise `PLUGIN_INVALID`. |
| `REQ-PLUGIN-07` | Event-driven | When `reset_registry()` is called, the system shall rebuild the default registry on the next `get_registry()` call. |
| `REQ-PLUGIN-08` | Ubiquitous | The system shall expose registered plugin metadata including name, kind, API version, source distribution, package version, and entry-point group. |
| `REQ-PLUGIN-09` | Ubiquitous | The system shall list empty sink and input-adapter namespaces when no plugins are registered in those namespaces. |
| `REQ-PLUGIN-10` | Unwanted behaviour | If a duplicate sink name is registered, the system shall raise `PLUGIN_DUPLICATE`. |
| `REQ-PLUGIN-11` | Unwanted behaviour | If a duplicate input-adapter name is registered, the system shall raise `PLUGIN_DUPLICATE`. |
| `REQ-PLUGIN-12` | Ubiquitous | The system shall route the built-in counter candidate processor through the plugin registry. |
| `REQ-PLUGIN-13` | Ubiquitous | The system shall route the built-in entropy candidate processor through the plugin registry. |
| `REQ-PLUGIN-14` | Ubiquitous | The system shall route the built-in signal analysis processor through the plugin registry. |
| `REQ-PLUGIN-15` | Ubiquitous | The system shall expose `re signals` through the canonical command envelope while using the registry-backed processor. |
| `REQ-PLUGIN-16` | Ubiquitous | The system shall expose `re counters` through the canonical command envelope while using the registry-backed processor. |
| `REQ-PLUGIN-17` | Ubiquitous | The system shall expose `re entropy` through the canonical command envelope while using the registry-backed processor. |
| `REQ-PLUGIN-18` | Ubiquitous | The system shall allow manually registered third-party processors to be discovered and invoked in tests. |
| `REQ-PLUGIN-19` | Ubiquitous | The system shall preserve `ProcessorResult.warnings` as a list even when no warnings are present. |
| `REQ-PLUGIN-20` | Ubiquitous | The system shall expose `canarchy plugins list` with canonical `--json`, `--jsonl`, and `--text` output. |
| `REQ-PLUGIN-21` | Ubiquitous | The system shall expose `canarchy plugins info <name>` with metadata, enabled state, source distribution, and configured options. |
| `REQ-PLUGIN-22` | Event-driven | When `canarchy plugins enable <name>` or `canarchy plugins disable <name>` is run for a discovered plugin, the system shall persist `[plugins."<name>"].enabled` in `~/.canarchy/config.toml`. |
| `REQ-PLUGIN-23` | Unwanted behaviour | If a plugin command names an undiscovered plugin, the system shall return `PLUGIN_NOT_FOUND` in the canonical envelope. |
| `REQ-PLUGIN-24` | Optional feature | Where MCP is used, the system shall expose read-only `plugins_list` and `plugins_info` tools while keeping plugin enable/disable CLI-only. |

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

The registry also records inspectable metadata for each registered plugin. Built-in plugins report
`source_distribution="canarchy"`; entry-point plugins report the Python distribution name/version
when `importlib.metadata` exposes it.

---

## CLI And MCP Surface

The CLI exposes plugin inspection and toggles through a dedicated command tree:

```text
canarchy plugins list [--json|--jsonl|--text]
canarchy plugins info <name> [--json|--jsonl|--text]
canarchy plugins enable <name> [--json|--jsonl|--text]
canarchy plugins disable <name> [--json|--jsonl|--text]
```

`plugins list` returns all discovered plugins with `name`, `kind`, `api_version`, `version`,
`source_distribution`, `entry_point_group`, `enabled`, and `configured_options` fields.

`plugins info` returns all namespace matches for a name plus the configured options from
`~/.canarchy/config.toml` under `[plugins."<name>"]`.

`plugins enable` and `plugins disable` write `[plugins."<name>"].enabled = true|false`. These
commands require the plugin to be discovered in the current Python environment and return
`PLUGIN_NOT_FOUND` for unknown names.

MCP mirrors only the read-only operations as `plugins_list` and `plugins_info`. Toggle commands are
kept CLI-only because they write user configuration.

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
- Plugin author verification / signing for security-sensitive deployments
