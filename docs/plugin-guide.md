# Plugin Author Guide

CANarchy supports third-party plugins that extend the analysis engine without requiring a fork.
This guide shows how to build, package, and register a custom processor plugin.

## Extension Points

| Extension point | Use case |
|----------------|----------|
| `ProcessorPlugin` | Frame analysis: counters, entropy, anomaly detection, custom classifiers |
| `SinkPlugin` | Output routing: databases, SIEM, cloud telemetry, custom file formats |
| `InputAdapterPlugin` | Input parsing: proprietary capture formats, hardware-specific log files |

## API Version

Every plugin must declare `api_version = "1"`. If the version does not match the installed
CANarchy build, the plugin is rejected at registration time with a clear error message.

## Writing a Processor Plugin

A processor receives a list of `CanFrame` objects and returns a `ProcessorResult`.

```python
# my_package/plugin.py
from typing import Any
from canarchy.models import CanFrame
from canarchy.plugins import CANARCHY_API_VERSION, ProcessorResult


class RepeatingIDDetector:
    """Flag arbitration IDs that appear suspiciously often relative to others."""

    name = "repeating-id-detector"
    api_version = CANARCHY_API_VERSION

    def process(self, frames: list[CanFrame], **kwargs: Any) -> ProcessorResult:
        from collections import Counter

        counts = Counter(f.arbitration_id for f in frames if not f.is_error_frame)
        total = len(frames) or 1
        threshold = kwargs.get("threshold", 0.5)

        candidates = [
            {
                "arbitration_id": arb_id,
                "frame_count": count,
                "fraction": round(count / total, 4),
            }
            for arb_id, count in counts.most_common()
            if count / total >= threshold
        ]

        warns = []
        if not candidates:
            warns.append(f"No arbitration ID exceeded the {threshold:.0%} repetition threshold.")

        return ProcessorResult(
            candidates=candidates,
            metadata={
                "analysis": "repeating_id_detection",
                "candidate_count": len(candidates),
                "threshold": threshold,
            },
            warnings=warns,
        )
```

### Rules

- `name` must be a unique string across all registered processors.
- `api_version` must equal `canarchy.plugins.CANARCHY_API_VERSION`.
- `process()` must return a `ProcessorResult`; it must not raise on empty input.
- `**kwargs` lets callers pass optional parameters; always provide safe defaults.
- Do not import front-end modules (`cli`, `tui`, `mcp_server`) from within a plugin.

## Packaging and Registration

Declare the plugin via a Python entry point in your `pyproject.toml`:

```toml
[project]
name = "canarchy-repeating-id"
dependencies = ["canarchy>=0.6"]

[project.entry-points."canarchy.processors"]
repeating-id-detector = "my_package.plugin:RepeatingIDDetector"
```

Install the package into the same environment as CANarchy:

```
pip install -e .
# or
uv pip install -e .
```

CANarchy discovers and registers the plugin the next time `get_registry()` is called (on first
command execution).

## Entry Point Groups

| Group | Extension point |
|-------|----------------|
| `canarchy.processors` | `ProcessorPlugin` |
| `canarchy.sinks` | `SinkPlugin` |
| `canarchy.input_adapters` | `InputAdapterPlugin` |

## Local Verification

To confirm your plugin is registered before distributing it:

```python
from canarchy.plugins import get_registry, reset_registry

reset_registry()  # force a fresh build
registry = get_registry()
proc = registry.get_processor("repeating-id-detector")
assert proc is not None, "plugin not found — check entry point group and class name"
print(registry.list_processors())
```

## Error Isolation

CANarchy wraps third-party entry point loading in a `try/except`. If your plugin raises an
unexpected exception during loading, CANarchy emits a `warnings.warn` and continues starting.
A `PluginError` (version mismatch, duplicate name, invalid interface) propagates immediately
so you can diagnose it during development.

## Writing a Sink Plugin

A sink writes a serialized command payload to a custom destination.

```python
import json
from typing import Any
from canarchy.plugins import CANARCHY_API_VERSION


class JsonFileSink:
    name = "json-file"
    api_version = CANARCHY_API_VERSION
    supported_formats = ["json"]

    def write(
        self, payload: dict[str, Any], destination: str, *, output_format: str = "json"
    ) -> dict[str, Any]:
        with open(destination, "w") as f:
            json.dump(payload, f, indent=2)
        return {"destination": destination, "bytes_written": f.tell()}
```

Entry point group: `canarchy.sinks`.

## Writing an Input Adapter Plugin

An input adapter yields `CanFrame` objects from a custom source.

```python
from typing import Iterator, Any
from canarchy.models import CanFrame
from canarchy.plugins import CANARCHY_API_VERSION


class MyFormatAdapter:
    name = "my-format"
    api_version = CANARCHY_API_VERSION
    supported_extensions = [".mylog"]

    def read(self, source: str) -> Iterator[CanFrame]:
        with open(source) as f:
            for line in f:
                arb_id, data_hex = line.strip().split(",")
                yield CanFrame(
                    arbitration_id=int(arb_id, 16),
                    data=bytes.fromhex(data_hex),
                )
```

Entry point group: `canarchy.input_adapters`.

## Compatibility Policy

The `api_version` string will increment when any breaking change is made to a plugin protocol
(removed method, changed required signature). Additive changes — new optional `**kwargs`,
new metadata fields in `ProcessorResult` — do not require a version bump.
