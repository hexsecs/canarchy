# Design Spec: UDS Transaction Workflows

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy uds scan`, `uds trace` |
| Primary area | CLI, protocol |
| Related specs | `docs/design/scapy-diagnostic-integration.md` |

## Goal

Provide structured UDS transaction views for responder discovery and session tracing through the shared transport layer.

## User-Facing Motivation

Operators need a protocol-aware UDS surface for discovery and transaction inspection without manually decoding request and response service bytes from raw traffic.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-UDS-TX-01` | Ubiquitous | The system shall provide `uds scan` and `uds trace` commands for UDS responder discovery and session tracing. |
| `REQ-UDS-TX-02` | Event-driven | When `uds scan <interface>` is invoked, the system shall emit structured `uds_transaction` events representing discovered responders. |
| `REQ-UDS-TX-03` | Event-driven | When `uds scan <interface>` is invoked and validation succeeds, the system shall emit a preflight active-transmit warning to `stderr` before diagnostic requests are sent. |
| `REQ-UDS-TX-07` | Optional feature | Where `--ack-active` is supplied for `uds scan`, the system shall require a confirmation response of `YES` before a diagnostic request is sent. |
| `REQ-UDS-TX-08` | Optional feature | Where active acknowledgement is required, the system shall require `--ack-active` before `uds scan` sends a diagnostic request. |
| `REQ-UDS-TX-04` | Event-driven | When `uds trace <interface>` is invoked, the system shall emit structured `uds_transaction` events for traced request/response exchanges. |
| `REQ-UDS-TX-05` | Ubiquitous | UDS text output shall present service identifier, ECU address, request ID, and response ID for each transaction. |
| `REQ-UDS-TX-06` | Unwanted behaviour | If the transport interface is unavailable, the system shall return a structured error with code `TRANSPORT_UNAVAILABLE` and exit code 2. |
| `REQ-UDS-TX-09` | Event-driven | When `uds scan` or `uds trace` receives ISO 15765-2 first-frame and consecutive-frame responses, the system shall reassemble them into a single `uds_transaction` response payload before service decoding. |
| `REQ-UDS-TX-10` | Unwanted behaviour | If a segmented UDS response is truncated or arrives out of order, the system shall emit a `uds_transaction` event with `complete` equal to `false` and the partial reassembled response payload. |
| `REQ-UDS-TX-11` | Event-driven | When ISO 15765-2 flow-control frames appear in captured traffic, the system shall use them only for reassembly and shall not emit them as `uds_transaction` events. |
| `REQ-UDS-TX-12` | Ubiquitous | `uds scan` and `uds trace` shall report the active protocol decoder path in the result data as `protocol_decoder`. |

## Command Surface

```text
canarchy uds scan <interface> [--ack-active] [--json] [--jsonl] [--text]
canarchy uds trace <interface> [--json] [--jsonl] [--text]
```

## Responsibilities And Boundaries

In scope:

* structured scan responder transactions
* structured trace transactions
* protocol-aware text rendering
* transport-backed UDS response reassembly through the shared transport layer when `python-can` is selected

Out of scope:

* segmented request transmission
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
* `complete`
* `ecu_address`
* optional `decoder`, `request_summary`, `response_summary`, `negative_response_code`, and `negative_response_name`

## Output Contracts

`--json` returns the standard CANarchy envelope. `--jsonl` emits one transaction event per line. `uds scan` emits its preflight safety warning on `stderr`.

Current implementation note:

* with the `python-can` backend, `uds scan` and `uds trace` reassemble multi-frame UDS responses before transaction emission
* with the `scaffold` backend, they emit explicit sample/reference transactions
* where the optional Scapy extra is installed, UDS transactions may include summary-level request/response enrichment while preserving the same event type and envelope

## Error Contracts

| Code | Trigger | Exit code |
|------|---------|-----------|
| `TRANSPORT_UNAVAILABLE` | transport interface is unavailable | 2 |
| `ACTIVE_ACK_REQUIRED` | active acknowledgement is required but `--ack-active` was omitted for `uds scan` | 1 |
| `ACTIVE_CONFIRMATION_DECLINED` | `--ack-active` was supplied for `uds scan` but the confirmation response was not `YES` | 1 |

## Deferred Decisions

* richer UDS service interpretation beyond the current transaction summaries
* ECU-specific scan profiles and configuration controls
