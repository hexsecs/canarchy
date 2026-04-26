# Event Schema

Every CANarchy command that produces structured output emits events using a canonical envelope. This document defines that envelope and every typed event subclass.

The event schema is the stable interface between CANarchy and downstream consumers: scripts, pipelines, analysis tools, and coding agents. If you are parsing CANarchy output programmatically, parse the event stream rather than the human-readable table output.

## Canonical Envelope

All events share the same top-level shape:

```json
{
  "event_type": "<string>",
  "source": "<string>",
  "timestamp": "<float | null>",
  "payload": { }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `event_type` | string | Discriminator. See event types below. |
| `source` | string | Dotted path identifying which command or subsystem emitted the event. Examples: `transport.capture`, `dbc.decode`, `gateway.src->dst`. |
| `timestamp` | float \| null | Seconds since epoch (or relative to capture start). `null` when not available. |
| `payload` | object | Event-specific fields. Shape varies by `event_type`. |

## Streaming

Use `--jsonl` on any command to receive one event per line on stdout, suitable for piping:

```bash
canarchy capture can0 --jsonl
canarchy j1939 decode trace.candump --jsonl
canarchy generate can0 --count 100 --gap 10 --jsonl
```

Use `--json` to receive the full command envelope with all events in a `data.events` array:

```bash
canarchy capture can0 --json
```

## Event Types

### `frame`

A raw CAN frame, as captured, generated, or forwarded.

Emitted by: `capture`, `send`, `generate`, `gateway`, `filter`, `replay`

```json
{
  "event_type": "frame",
  "source": "transport.capture",
  "timestamp": 0.0,
  "payload": {
    "frame": {
      "arbitration_id": 419360305,
      "bitrate_switch": false,
      "data": "11223344",
      "dlc": 4,
      "error_state_indicator": false,
      "frame_format": "can",
      "interface": "can0",
      "is_error_frame": false,
      "is_extended_id": true,
      "is_remote_frame": false,
      "timestamp": 0.0
    }
  }
}
```

**Frame fields:**

| Field | Type | Description |
|-------|------|-------------|
| `arbitration_id` | int | 11-bit standard (0–2047) or 29-bit extended (0–536870911) CAN identifier. |
| `data` | string | Hex-encoded payload bytes, lowercase, no separators. |
| `dlc` | int | Data length code: number of payload bytes (0–8 for classic CAN, 0–64 for CAN FD). |
| `frame_format` | `"can"` \| `"can_fd"` | Frame type. |
| `interface` | string \| null | Interface name such as `can0` or `239.0.0.1`. |
| `is_extended_id` | bool | `true` for 29-bit extended identifiers. |
| `is_remote_frame` | bool | `true` for RTR frames (no data bytes). |
| `is_error_frame` | bool | `true` for CAN error frames. |
| `bitrate_switch` | bool | CAN FD only — BRS flag. |
| `error_state_indicator` | bool | CAN FD only — ESI flag. |
| `timestamp` | float \| null | Frame timestamp, seconds. |

**Source values for `frame` events:**

| Source | Context |
|--------|---------|
| `transport.capture` | Capture via the selected transport backend (`python-can` or scaffold) |
| `transport.send` | Active frame transmission |
| `transport.generate` | Frame generation (`canarchy generate`) |
| `transport.filter` | File-backed filter result |
| `gateway.src->dst` | Forwarded frame, source to destination |
| `gateway.dst->src` | Forwarded frame, destination to source (bidirectional mode) |
| `replay.engine` | Replay plan frame |

---

### `decoded_message`

A CAN frame decoded against a DBC message definition. Includes the raw frame and all decoded signal values.

Emitted by: `decode`

```json
{
  "event_type": "decoded_message",
  "source": "dbc.decode",
  "timestamp": 0.0,
  "payload": {
    "frame": { },
    "message_name": "EngineStatus1",
    "signals": {
      "CoolantTemp": -23,
      "LampState": 68,
      "Load": 20.4,
      "OilTemp": -6
    }
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `frame` | object | Raw `CanFrame` payload (same shape as `frame` event). |
| `message_name` | string | DBC message name. |
| `signals` | object | Signal name → decoded physical value map. |

---

### `signal`

An individual decoded signal value. One `signal` event is emitted per signal per decoded frame, immediately following its parent `decoded_message` event in the stream.

Emitted by: `decode`

```json
{
  "event_type": "signal",
  "source": "dbc.decode",
  "timestamp": null,
  "payload": {
    "message_name": "EngineStatus1",
    "signal_name": "CoolantTemp",
    "units": "degC",
    "value": -23
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `message_name` | string \| null | Parent DBC message name. |
| `signal_name` | string | DBC signal name. |
| `units` | string \| null | Physical unit string from the DBC (empty string if not defined). |
| `value` | number | Decoded physical value after scaling and offset. |

---

### `dbc_database`

A DBC database summary emitted by `dbc inspect` before message and signal metadata.

Emitted by: `dbc inspect`

```json
{
  "event_type": "dbc_database",
  "source": "dbc.inspect",
  "timestamp": null,
  "payload": {
    "format": "dbc",
    "message_count": 2,
    "node_count": 0,
    "path": "tests/fixtures/sample.dbc",
    "signal_count": 6
  }
}
```

### `dbc_message`

DBC message metadata emitted by `dbc inspect`.

Emitted by: `dbc inspect`

```json
{
  "event_type": "dbc_message",
  "source": "dbc.inspect",
  "timestamp": null,
  "payload": {
    "arbitration_id": 419360305,
    "arbitration_id_hex": "0x18FEEE31",
    "cycle_time_ms": null,
    "is_extended_id": true,
    "length": 4,
    "name": "EngineStatus1",
    "senders": [],
    "signal_count": 4
  }
}
```

### `dbc_signal`

DBC signal metadata emitted by `dbc inspect`.

Emitted by: `dbc inspect`

```json
{
  "event_type": "dbc_signal",
  "source": "dbc.inspect",
  "timestamp": null,
  "payload": {
    "byte_order": "little_endian",
    "choices": null,
    "is_multiplexer": false,
    "is_signed": false,
    "length": 8,
    "maximum": 210,
    "message_name": "EngineStatus1",
    "minimum": 0,
    "multiplexer_ids": null,
    "name": "CoolantTemp",
    "offset": -40,
    "scale": 1,
    "start_bit": 0,
    "unit": "degC"
  }
}
```

---

### `j1939_pgn`

A J1939 frame observation with decomposed identifier fields.

Emitted by: `j1939 monitor`, `j1939 decode`, `j1939 pgn`

```json
{
  "event_type": "j1939_pgn",
  "source": "transport.j1939.decode",
  "timestamp": 0.0,
  "payload": {
    "destination_address": null,
    "frame": { },
    "pgn": 65262,
    "priority": 6,
    "source_address": 49
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `pgn` | int | Parameter Group Number (0–262143). |
| `source_address` | int | J1939 source address (0–255). |
| `destination_address` | int \| null | Peer-to-peer destination address, or `null` for broadcast PGNs. |
| `priority` | int \| null | J1939 frame priority (0–7). |
| `frame` | object | Raw `CanFrame` payload. |

---

### `uds_transaction`

A UDS request/response pair observed during a scan or trace.

Emitted by: `uds scan`, `uds trace`

```json
{
  "event_type": "uds_transaction",
  "source": "transport.uds.scan",
  "timestamp": 0.0,
  "payload": {
    "complete": true,
    "decoder": "built-in",
    "ecu_address": 2024,
    "negative_response_code": null,
    "negative_response_name": null,
    "request_data": "1001",
    "request_id": 2015,
    "request_summary": null,
    "response_data": "5001003201f4",
    "response_id": 2024,
    "response_summary": null,
    "service": 16,
    "service_name": "DiagnosticSessionControl"
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `service` | int | UDS service ID (hex values: 0x10 = DiagnosticSessionControl, 0x22 = RDBI, etc.). |
| `service_name` | string | Human-readable service name. |
| `request_id` | int | CAN arbitration ID of the request frame. |
| `response_id` | int | CAN arbitration ID of the response frame. |
| `ecu_address` | int \| null | Responding ECU address (typically equals `response_id`). |
| `request_data` | string | Request payload bytes, hex-encoded. |
| `response_data` | string | Response payload bytes, hex-encoded. |
| `complete` | bool | `true` when the response payload was fully reassembled; `false` when the capture ended early or consecutive frames arrived out of order. |
| `decoder` | string | Protocol decoder path used for transaction enrichment, such as `built-in` or `scapy`. |
| `request_summary` | string \| null | Optional summary-level request interpretation when the Scapy-backed adapter is available. |
| `response_summary` | string \| null | Optional summary-level response interpretation when the Scapy-backed adapter is available. |
| `negative_response_code` | int \| null | Negative response code for UDS negative responses. |
| `negative_response_name` | string \| null | Human-readable negative response name for UDS negative responses. |

---

### `replay_event`

A scheduled frame transmission from a replay plan.

Emitted by: `replay`

```json
{
  "event_type": "replay_event",
  "source": "replay.engine",
  "timestamp": 0.0,
  "payload": {
    "action": "send_frame",
    "frame": { },
    "rate": 1.0
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `action` | string | `"send_frame"` for frame transmission events; `"plan_start"` / `"plan_end"` for lifecycle events. |
| `rate` | float \| null | Replay rate multiplier (1.0 = original timing, 2.0 = double speed). |
| `frame` | object \| null | Raw `CanFrame` payload (absent for lifecycle events). |

---

### `alert`

A diagnostic notice from a command: active-transmit warnings, backend availability notices, or informational messages.

Emitted by: `send`, `generate`, `gateway`, and any command that raises a notable condition.

```json
{
  "event_type": "alert",
  "source": "transport.generate",
  "timestamp": null,
  "payload": {
    "code": "ACTIVE_TRANSMIT",
    "level": "warning",
    "message": "Active frame generation requested on the selected interface."
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `level` | `"info"` \| `"warning"` \| `"error"` | Severity. |
| `code` | string \| null | Machine-readable alert code. |
| `message` | string | Human-readable description. |

**Common alert codes:**

| Code | Level | Context |
|------|-------|---------|
| `ACTIVE_TRANSMIT` | warning | Frame generation or active transmission requested. |
| `CANDUMP_LIVE_BACKEND_REQUIRED` | error | `--candump` mode requires `python-can` backend. |
| `GATEWAY_LIVE_BACKEND_REQUIRED` | error | `gateway` requires `python-can` backend. |

---

## Consuming Events in Scripts

Parse JSONL output line by line and filter on `event_type`:

```bash
# Extract all frame arbitration IDs from a live capture
canarchy capture can0 --jsonl \
  | jq 'select(.event_type == "frame") | .payload.frame.arbitration_id'

# Decode a trace and print each signal value
canarchy decode trace.candump --dbc vehicle.dbc --jsonl \
  | jq 'select(.event_type == "signal") | [.payload.signal_name, .payload.value, .payload.units]'

# Watch for J1939 coolant temperature observations
canarchy j1939 decode trace.candump --jsonl \
  | jq 'select(.event_type == "j1939_pgn" and .payload.pgn == 65262)'
```

## Agent Integration

See [Agent Guide](agents.md) for how to invoke CANarchy commands as a coding agent and parse structured results.
