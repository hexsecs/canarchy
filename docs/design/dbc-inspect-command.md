# Design Spec: `dbc inspect` Command

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy dbc inspect` |
| Primary area | CLI, DBC |
| Related specs | `docs/design/dbc-command-workflows.md`, `docs/design/dbc-runtime-schema-split.md` |

## Goal

Provide a DBC inspection command that exposes message and signal metadata as structured output so operators and agents can understand a database without leaving the CANarchy command surface.

## User-Facing Motivation

Operators often need to answer questions such as which messages exist in a database, which signals are required for encoding, what units and ranges apply, and whether a message uses standard or extended IDs. That metadata is currently implicit in the DBC file and inaccessible from the CANarchy CLI. A first-class inspection command makes the database inspectable, scriptable, and useful for downstream encode, decode, completion, and agent workflows.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-DBCI-01` | Ubiquitous | The system shall provide a `canarchy dbc inspect <dbc>` command for inspecting DBC metadata. |
| `REQ-DBCI-02` | Event-driven | When `dbc inspect <dbc>` is invoked, the system shall return a structured database summary including source path, source format, and counts for messages, signals, and nodes. |
| `REQ-DBCI-03` | Event-driven | When `dbc inspect <dbc>` is invoked, the system shall include message metadata containing at least message name, arbitration ID, frame length, ID format, and signal definitions. |
| `REQ-DBCI-04` | Event-driven | When `dbc inspect <dbc>` is invoked, the system shall include signal metadata containing at least signal name, bit start, bit length, byte order, signedness, scale, offset, min, max, unit, and choices where available. |
| `REQ-DBCI-05` | Optional feature | Where `--message <name>` is specified, the system shall restrict the response to the named message and its signal metadata. |
| `REQ-DBCI-06` | Optional feature | Where `--signals-only` is specified, the system shall emit signal-centric output without duplicating full database metadata. |
| `REQ-DBCI-07` | Unwanted behaviour | If the DBC file is invalid or unreadable, the system shall return a structured error with code `DBC_LOAD_FAILED` and exit code 3. |
| `REQ-DBCI-08` | Unwanted behaviour | If `--message <name>` references an unknown message, the system shall return a structured error with code `DBC_MESSAGE_NOT_FOUND` and exit code 3. |

## Command Surface

```text
canarchy dbc inspect <dbc> [--message <name>] [--signals-only] [--json] [--jsonl] [--text] [--raw]
```

### Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `<dbc>` | required | Path to the DBC file to inspect |
| `--message` | unset | Restrict output to a single message name |
| `--signals-only` | off | Emit signal-centric results instead of the full database summary |

## Responsibilities And Boundaries

In scope:

* database-level metadata inspection from a DBC file
* message- and signal-level metadata required for decode and encode workflows
* structured output suitable for automation and agent use

Out of scope:

* modifying or writing DBC files
* live bus decode or encode operations
* database diff, merge, or conversion workflows

## Data Model

The command returns a database summary plus zero or more message definitions.

### Database summary

| Field | Type | Meaning |
|-------|------|---------|
| `path` | string | source file path passed by the operator |
| `format` | string | detected source format such as `dbc` |
| `message_count` | integer | total messages in the database |
| `signal_count` | integer | total signals in the database |
| `node_count` | integer | total nodes in the database |

### Message metadata

| Field | Type | Meaning |
|-------|------|---------|
| `name` | string | DBC message name |
| `arbitration_id` | integer | numeric frame identifier |
| `arbitration_id_hex` | string | canonical hex identifier string |
| `is_extended_id` | boolean | whether the message uses a 29-bit identifier |
| `length` | integer | payload length in bytes |
| `cycle_time_ms` | integer or null | configured cycle time if present |
| `senders` | array[string] | transmitting nodes |
| `signal_count` | integer | number of signals in the message |
| `signals` | array[object] | signal definitions |

### Signal metadata

| Field | Type | Meaning |
|-------|------|---------|
| `name` | string | signal name |
| `start_bit` | integer | start bit within the frame |
| `length` | integer | bit length |
| `byte_order` | string | `little_endian` or `big_endian` |
| `is_signed` | boolean | whether the signal is signed |
| `scale` | number | signal scaling factor |
| `offset` | number | signal offset |
| `minimum` | number or null | minimum physical value |
| `maximum` | number or null | maximum physical value |
| `unit` | string or null | engineering unit |
| `choices` | object or null | optional choice-name mapping |
| `is_multiplexer` | boolean | whether the signal is the mux selector |
| `multiplexer_ids` | array[integer] or null | mux branch values where applicable |

## Output Contracts

### JSON

`--json` returns the standard CANarchy envelope.

Representative response:

```json
{
  "ok": true,
  "command": "dbc inspect",
  "data": {
    "database": {
      "format": "dbc",
      "message_count": 2,
      "node_count": 0,
      "path": "tests/fixtures/sample.dbc",
      "signal_count": 6
    },
    "messages": [
      {
        "arbitration_id": 419360305,
        "arbitration_id_hex": "0x18FEEE31",
        "cycle_time_ms": null,
        "is_extended_id": true,
        "length": 4,
        "name": "EngineStatus1",
        "senders": ["Vector__XXX"],
        "signal_count": 4,
        "signals": [
          {
            "byte_order": "little_endian",
            "choices": null,
            "is_multiplexer": false,
            "is_signed": false,
            "length": 8,
            "maximum": 210,
            "minimum": 0,
            "multiplexer_ids": null,
            "name": "CoolantTemp",
            "offset": -40,
            "scale": 1,
            "start_bit": 0,
            "unit": "degC"
          }
        ]
      }
    }
  },
  "warnings": [],
  "errors": []
}
```

### JSONL

`--jsonl` emits one metadata event per line. The initial event is a `dbc_database` summary event followed by one `dbc_message` event per included message and one `dbc_signal` event per included signal.

Representative lines:

```json
{"event_type":"dbc_database","source":"dbc.inspect","payload":{"path":"tests/fixtures/sample.dbc","format":"dbc","message_count":2,"signal_count":6,"node_count":0}}
{"event_type":"dbc_message","source":"dbc.inspect","payload":{"name":"EngineStatus1","arbitration_id":419360305,"is_extended_id":true,"length":4,"signal_count":4}}
{"event_type":"dbc_signal","source":"dbc.inspect","payload":{"message_name":"EngineStatus1","name":"CoolantTemp","start_bit":0,"length":8,"scale":1,"offset":-40,"unit":"degC"}}
```

### Table

`--text` returns a compact summary view.

```text
command: dbc inspect
file: tests/fixtures/sample.dbc
messages: 2
signals: 6
nodes: 1
- EngineStatus1 id=0x98FEEE31 len=4 signals=4
- EngineSpeed1 id=0x98F00431 len=4 signals=2
```

When `--message EngineStatus1` is specified, the table includes the message summary plus one line per signal.

### Raw

Emits the inspected file path on success or the first error message on failure.

## Error Contracts

| Code | Trigger | Exit code |
|------|---------|-----------|
| `DBC_LOAD_FAILED` | DBC file cannot be loaded or parsed | 3 |
| `DBC_MESSAGE_NOT_FOUND` | requested message name is unknown | 3 |

## Deferred Decisions

* whether `dbc inspect` should support non-DBC source formats directly or operate only on DBC inputs in the first version
* whether `--json-schema` should emit a machine-consumable JSON Schema document in addition to representative JSON output
* whether JSONL metadata events should extend the global event-type registry or remain command-local until schema tooling is broader
