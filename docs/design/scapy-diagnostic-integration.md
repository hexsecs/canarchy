# Design Spec: Scapy Diagnostic Integration

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy uds scan`, `uds trace` |
| Primary area | CLI, protocol, diagnostics |
| Related specs | `docs/design/uds-transaction-workflows.md` |

## Goal

Define a first-phase Scapy integration boundary that adds analyst-value diagnostic interpretation to existing UDS workflows without replacing CANarchy's frame model, transport layer, or command contract.

## User-Facing Motivation

Operators already have structured UDS scan and trace workflows, but deeper diagnostic interpretation is still limited. A small Scapy-backed enrichment layer can add clearer protocol summaries to UDS request/response payloads while keeping CANarchy's CLI-first behavior stable.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-SCAPY-01` | Ubiquitous | The system shall keep Scapy behind a CANarchy-owned adapter boundary rather than exposing Scapy packet objects directly through CLI, MCP, shell, or TUI results. |
| `REQ-SCAPY-02` | Optional feature | Where the optional Scapy dependency is available, the system shall use it to enrich `uds scan` and `uds trace` transactions with protocol-summary fields while preserving the canonical CANarchy result envelope. |
| `REQ-SCAPY-03` | State-driven | While the optional Scapy dependency is unavailable, the system shall keep `uds scan` and `uds trace` functional through the built-in decoder path and report `protocol_decoder="built-in"`. |
| `REQ-SCAPY-04` | Event-driven | When a UDS transaction carries a negative response payload, the system shall include the negative response code and a human-readable negative response name in structured output. |
| `REQ-SCAPY-05` | Ubiquitous | The first Scapy-backed phase shall not change command names, transport semantics, or the canonical `uds_transaction` event type. |

## Command Surface

```text
canarchy uds scan <interface> [--ack-active] [--json] [--jsonl] [--text]
canarchy uds trace <interface> [--json] [--jsonl] [--text]
```

## Responsibilities And Boundaries

In scope:

* optional Scapy-backed interpretation of existing UDS request/response payloads
* stable summary-level enrichment fields in UDS transaction output
* explicit reporting of which protocol decoder path was used

Out of scope:

* replacing ISO-TP reassembly with Scapy-owned transport flows
* making Scapy a required dependency for base CANarchy usage
* adding interactive Scapy UX concepts to the CLI
* deeper fuzzing or mutation workflows, which remain follow-on work

## Data Model

The existing `uds_transaction` payload remains authoritative and may now additionally include:

* `decoder`
* `request_summary`
* `response_summary`
* `negative_response_code`
* `negative_response_name`

The top-level `data` payload for `uds scan` and `uds trace` also includes `protocol_decoder` with values such as `built-in` or `scapy`.

## Output Contracts

### JSON and JSONL

The standard CANarchy result envelope and event schema remain unchanged except for the optional enrichment fields above.

### Table

Text output remains transaction-first and may show negative response naming and Scapy-backed response summaries when available.

## Error Contracts

No Scapy-specific user-visible error codes are introduced in phase 1. Missing or failing Scapy enrichment falls back to the built-in path instead of failing the command.

## Deferred Decisions

* whether Scapy should later back additional diagnostic workflows beyond `uds scan` and `uds trace`
* whether future Scapy-backed packet fields should be exposed beyond stable summary-level output
* whether advanced diagnostic fuzzing helpers should depend on this same adapter boundary
