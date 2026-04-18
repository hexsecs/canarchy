# Design Spec: DBC Command Workflows

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy decode`, `encode` |
| Primary area | CLI, DBC |

## Goal

Provide DBC-backed decode and encode workflows that let operators move between captured frames and semantic message/signal views from the CLI.

## User-Facing Motivation

DBC-backed workflows are central to protocol-aware CAN analysis. Operators should be able to decode captured traffic and encode named messages without leaving the CANarchy command surface.

## Requirements

| ID | Requirement |
|----|-------------|
| `REQ-DBC-01` | The system shall provide a `decode` command for DBC-backed capture decoding. |
| `REQ-DBC-02` | The system shall provide an `encode` command for DBC-backed message encoding. |
| `REQ-DBC-03` | `decode` shall emit structured decoded-message and signal events for matching frames. |
| `REQ-DBC-04` | `encode` shall emit a structured frame result suitable for later transmit workflows. |
| `REQ-DBC-05` | Invalid or unreadable DBC inputs shall return structured decode errors. |

## Command Surface

```text
canarchy decode <file> --dbc <file> [--json] [--jsonl] [--table] [--raw]
canarchy encode --dbc <file> <message> <signal=value>... [--json] [--jsonl] [--table] [--raw]
```

## Responsibilities And Boundaries

In scope:

* decoding capture files through a DBC database
* encoding named messages from signal assignments
* structured event emission for machine-readable workflows

Out of scope:

* live transmit of encoded frames
* DBC editing or schema authoring

## Data Model

`decode` returns decoded-message and signal events. `encode` returns a frame plus frame events and CLI metadata describing the encoding request.

## Output Contracts

### JSON

Returns the standard CANarchy command envelope.

### JSONL

Event-producing commands emit one event per line; warnings without corresponding events are emitted as alert lines.

### Table and raw

Use the shared table/raw result rendering path.

## Error Contracts

| Code | Trigger | Exit code |
|------|---------|-----------|
| `DBC_LOAD_FAILED` | DBC file cannot be loaded or parsed | 3 |
| `DBC_MESSAGE_NOT_FOUND` | requested message name is unknown | 3 |
| `DBC_SIGNAL_INVALID` | signal assignment is invalid | 3 |

## Deferred Decisions

* deeper DBC coverage examples in the operator docs
* database composition or override workflows
