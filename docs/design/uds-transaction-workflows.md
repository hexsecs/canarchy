# Design Spec: UDS Transaction Workflows

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy uds scan`, `uds trace` |
| Primary area | CLI, protocol |

## Goal

Provide structured UDS transaction views for responder discovery and session tracing through the shared transport layer.

## User-Facing Motivation

Operators need a protocol-aware UDS surface for discovery and transaction inspection without manually decoding request and response service bytes from raw traffic.

## Requirements

| ID | Requirement |
|----|-------------|
| `REQ-UDS-TX-01` | The system shall provide `uds scan` and `uds trace` commands. |
| `REQ-UDS-TX-02` | `uds scan` shall emit structured UDS transaction events representing responder discovery. |
| `REQ-UDS-TX-03` | `uds trace` shall emit structured UDS transaction events for traced request/response exchanges. |
| `REQ-UDS-TX-04` | `uds scan` shall communicate its active nature through a warning. |
| `REQ-UDS-TX-05` | UDS table output shall summarize service, ECU, request ID, and response ID information. |
| `REQ-UDS-TX-06` | Transport failures shall return structured transport errors. |

## Command Surface

```text
canarchy uds scan <interface> [--json] [--jsonl] [--table] [--raw]
canarchy uds trace <interface> [--json] [--jsonl] [--table] [--raw]
```

## Responsibilities And Boundaries

In scope:

* structured scan responder transactions
* structured trace transactions
* protocol-aware table rendering
* initial single-frame transport-backed behavior through the shared transport layer when `python-can` is selected

Out of scope:

* full ISO-TP reassembly
* exhaustive ECU-specific service negotiation
* deep ECU-specific timing and retry behavior

## Data Model

Both commands emit `uds_transaction` events with fields including:

* `service`
* `service_name`
* `request_id`
* `response_id`
* `request_data`
* `response_data`
* `ecu_address`

## Output Contracts

`--json` returns the standard CANarchy envelope. `--jsonl` emits one transaction event per line plus warning alerts when applicable.

Current implementation note:

* with the `python-can` backend, `uds scan` and `uds trace` use transport-backed single-frame heuristics
* with the `scaffold` backend, they emit explicit sample/reference transactions

## Error Contracts

| Code | Trigger | Exit code |
|------|---------|-----------|
| `TRANSPORT_UNAVAILABLE` | transport interface is unavailable | 2 |

## Deferred Decisions

* richer UDS service interpretation beyond the current transaction summaries
* ECU-specific scan profiles and configuration controls
