# Plugin Author Guide

CANarchy supports third-party plugins that extend the analysis engine without requiring a fork.
This guide contains two complete walkthroughs followed by reference material for all extension
points.

## Extension Points

| Extension point | Entry-point group | Use case |
|----------------|-------------------|----------|
| `ProcessorPlugin` | `canarchy.processors` | Frame analysis: counters, entropy, anomaly detection, custom classifiers |
| `SinkPlugin` | `canarchy.sinks` | Output routing: databases, SIEM, cloud telemetry, custom file formats |
| `InputAdapterPlugin` | `canarchy.input_adapters` | Input parsing: proprietary capture formats, hardware-specific log files |

## API Version

Every plugin must declare `api_version = "1"`. If the version does not match the installed
CANarchy build, the plugin is rejected at registration time with a clear error message.

---

## Walkthrough 1 — Custom Decoder Plugin

This walkthrough builds a `ProcessorPlugin` that flags arbitration IDs whose frame count
exceeds a configurable fraction of the total traffic — useful for quickly identifying dominant
talkers in a capture.

### Project layout

```
canarchy-repeating-id/
├── pyproject.toml
├── my_package/
│   ├── __init__.py
│   └── plugin.py
└── tests/
    └── test_repeating_id.py
```

### Plugin code

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

### Processor plugin rules

- `name` must be a unique string across all registered processors.
- `api_version` must equal `canarchy.plugins.CANARCHY_API_VERSION`.
- `process()` must return a `ProcessorResult`; it must not raise on empty input.
- `**kwargs` lets callers pass optional parameters; always provide safe defaults.
- Do not import front-end modules (`cli`, `tui`, `mcp_server`) from within a plugin.

### Package and register

Declare the plugin via a Python entry point in your `pyproject.toml`:

```toml
[project]
name = "canarchy-repeating-id"
version = "0.1.0"
dependencies = ["canarchy>=0.8"]

[project.entry-points."canarchy.processors"]
repeating-id-detector = "my_package.plugin:RepeatingIDDetector"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

Install the package into the same environment as CANarchy:

```bash
pip install -e .
# or
uv pip install -e .
```

### Verify the registration

CANarchy discovers and registers the plugin the next time `get_registry()` is called (on first
command execution):

```bash
canarchy plugins list --json
canarchy plugins info repeating-id-detector --json
```

### Write a test

```python
# tests/test_repeating_id.py
import pytest
from canarchy.models import CanFrame
from canarchy.plugins import get_registry, reset_registry
from my_package.plugin import RepeatingIDDetector


@pytest.fixture(autouse=True)
def fresh_registry():
    reset_registry()
    yield
    reset_registry()


def _frame(arb_id: int) -> CanFrame:
    return CanFrame(arbitration_id=arb_id, data=b"\x00")


def test_dominant_id_detected():
    plugin = RepeatingIDDetector()
    frames = [_frame(0x100)] * 8 + [_frame(0x200)] * 2
    result = plugin.process(frames)
    assert result.candidates[0]["arbitration_id"] == 0x100
    assert result.candidates[0]["fraction"] == 0.8


def test_no_dominant_id_emits_warning():
    plugin = RepeatingIDDetector()
    frames = [_frame(i) for i in range(10)]
    result = plugin.process(frames, threshold=0.5)
    assert result.warnings


def test_empty_input_does_not_raise():
    plugin = RepeatingIDDetector()
    result = plugin.process([])
    assert result.candidates == []


def test_registered_via_entry_point():
    # After `pip install -e .`, the plugin appears in the registry.
    registry = get_registry()
    proc = registry.get_processor("repeating-id-detector")
    assert proc is not None
```

### Enable and disable via CLI

```bash
# Disable the plugin (persisted in ~/.canarchy/config.toml)
canarchy plugins disable repeating-id-detector --json

# Re-enable it
canarchy plugins enable repeating-id-detector --json

# Confirm status
canarchy plugins info repeating-id-detector --json
```

---

## Walkthrough 2 — Custom Sink Plugin

This walkthrough builds a `SinkPlugin` that persists command payloads to a SQLite database.
The completed implementation is the reference plugin shipped under
`contrib/plugins/sqlite_sink/` in the CANarchy repository.

### Project layout

```
canarchy-sqlite-sink/
├── pyproject.toml
├── sqlite_sink/
│   ├── __init__.py
│   └── plugin.py
└── tests/
    └── test_sqlite_sink.py
```

### Plugin code

```python
# sqlite_sink/plugin.py
from __future__ import annotations

import json
import sqlite3
import time
from typing import Any

from canarchy.plugins import CANARCHY_API_VERSION


class SqliteSinkPlugin:
    """Write CANarchy command payloads to a SQLite database."""

    name = "sqlite-sink"
    api_version = CANARCHY_API_VERSION
    supported_formats = ["json"]

    def write(
        self,
        payload: dict[str, Any],
        destination: str,
        *,
        output_format: str = "json",
    ) -> dict[str, Any]:
        """Insert frame events from *payload* into a SQLite DB at *destination*.

        Creates the database and ``frames`` table if they do not exist.
        Returns a dict with ``destination`` and ``rows_written``.
        """
        con = sqlite3.connect(destination)
        try:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS frames (
                    id      INTEGER PRIMARY KEY,
                    ts      REAL,
                    command TEXT,
                    payload TEXT
                )
                """
            )
            con.commit()

            command = payload.get("command", "")
            events = payload.get("data", {}).get("events", [])

            rows_written = 0
            if events:
                for event in events:
                    ts = event.get("ts", time.time())
                    con.execute(
                        "INSERT INTO frames (ts, command, payload) VALUES (?, ?, ?)",
                        (ts, command, json.dumps(event)),
                    )
                    rows_written += 1
            else:
                ts = time.time()
                con.execute(
                    "INSERT INTO frames (ts, command, payload) VALUES (?, ?, ?)",
                    (ts, command, json.dumps(payload)),
                )
                rows_written = 1

            con.commit()
        finally:
            con.close()

        return {"destination": destination, "rows_written": rows_written}
```

### Sink plugin rules

- `name` must be a unique string across all registered sinks.
- `api_version` must equal `canarchy.plugins.CANARCHY_API_VERSION`.
- `supported_formats` lists the envelope formats the sink understands (currently `"json"`).
- `write()` must return a dict; it must not raise on an empty `"events"` list.
- `destination` is a string the caller controls — it may be a file path, a connection URL, or
  a topic name depending on your sink's semantics.

### Package and register

```toml
[project]
name = "canarchy-sqlite-sink"
version = "0.1.0"
dependencies = ["canarchy>=0.8"]

[project.entry-points."canarchy.sinks"]
sqlite-sink = "sqlite_sink.plugin:SqliteSinkPlugin"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

```bash
pip install -e .
```

### Verify the registration

```bash
canarchy plugins list --json
canarchy plugins info sqlite-sink --json
```

### Write a test

```python
# tests/test_sqlite_sink.py
import os
import sqlite3
import tempfile
import unittest

from canarchy.plugins import SinkPlugin
from sqlite_sink.plugin import SqliteSinkPlugin


class SqliteSinkTests(unittest.TestCase):
    def setUp(self):
        self.plugin = SqliteSinkPlugin()

    def test_events_land_in_db(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = os.path.join(td, "out.db")
            payload = {
                "command": "capture",
                "data": {
                    "events": [
                        {"type": "frame", "ts": 1.0, "arbitration_id": "0x100"},
                        {"type": "frame", "ts": 2.0, "arbitration_id": "0x200"},
                    ]
                },
            }
            result = self.plugin.write(payload, db_path)

            # Return contract
            assert result["rows_written"] == 2
            assert result["destination"] == db_path

            # Rows actually landed in the database
            con = sqlite3.connect(db_path)
            rows = con.execute("SELECT COUNT(*) FROM frames").fetchone()[0]
            con.close()
            assert rows == 2

    def test_db_created_if_missing(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = os.path.join(td, "new.db")
            self.plugin.write({"command": "test", "data": {}}, db_path)
            assert os.path.exists(db_path)

    def test_implements_sink_protocol(self):
        assert isinstance(self.plugin, SinkPlugin)
```

### Enable and disable via CLI

```bash
canarchy plugins disable sqlite-sink --json
canarchy plugins enable sqlite-sink --json
canarchy plugins info sqlite-sink --json
```

### Reference implementation

The completed plugin is available under `contrib/plugins/sqlite_sink/` in the CANarchy
repository. Clone the repo and run its tests directly:

```bash
# From the repo root
python -m pytest tests/test_contrib_sqlite_sink.py -v
```

---

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

---

## Entry Point Groups Reference

| Group | Extension point |
|-------|----------------|
| `canarchy.processors` | `ProcessorPlugin` |
| `canarchy.sinks` | `SinkPlugin` |
| `canarchy.input_adapters` | `InputAdapterPlugin` |

## Error Isolation

CANarchy wraps third-party entry point loading in a `try/except`. If your plugin raises an
unexpected exception during loading, CANarchy emits a `warnings.warn` and continues starting.
A `PluginError` (version mismatch, duplicate name, invalid interface) propagates immediately
so you can diagnose it during development.

## Compatibility Policy

The `api_version` string will increment when any breaking change is made to a plugin protocol
(removed method, changed required signature). Additive changes — new optional `**kwargs`,
new metadata fields in `ProcessorResult` — do not require a version bump.
