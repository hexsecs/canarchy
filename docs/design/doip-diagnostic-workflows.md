# Design Spec: DoIP Diagnostic Workflows

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy uds scan`, `canarchy uds trace` (DoIP target syntax) |
| Primary area | Transport, protocol, CLI |
| Related specs | `docs/design/uds-transaction-workflows.md`, `docs/design/active-transmit-safety.md`, `docs/design/mcp-server.md` |

## Goal

Speak the [DoIP](https://www.iso.org/standard/74785.html) (Diagnostic over IP,
ISO 13400-2) wire format so the existing `uds scan` / `uds trace` workflows can
reach an ECU over a TCP/IP gateway — addressing it by 16-bit logical address —
instead of only over classic CAN / ISO-TP. The same canonical
`UdsTransactionEvent` envelope is emitted regardless of transport, so existing
consumers and output formats are unchanged.

## User-Facing Motivation

Modern vehicles and bench setups increasingly expose diagnostics over Automotive
Ethernet rather than (or in addition to) a CAN gateway. Tools such as Caring
Caribou and `udsoncan` already speak DoIP; without it an operator using CANarchy
against an IP-reachable gateway cannot run UDS discovery or tracing. DoIP support
extends CANarchy's protocol breadth without forking the UDS command surface.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-DOIP-01` | Ubiquitous | The system shall provide a pure codec that encodes and decodes the DoIP generic header, routing-activation request/response, and diagnostic-message payloads (version 2, ISO 13400-2), opening no live socket in the codec path. |
| `REQ-DOIP-02` | Optional feature | Where the `uds scan` / `uds trace` interface argument is a `doip://<host>:<port>?logical_address=0x0E80` URI, the system shall route the workflow over a DoIP TCP transport instead of the CAN backend. |
| `REQ-DOIP-03` | Event-driven | When `uds scan <doip-uri>` is invoked, the system shall open a TCP connection, perform routing activation, probe the default / programming / extended diagnostic sessions, and emit each ECU response as a canonical `UdsTransactionEvent`. |
| `REQ-DOIP-04` | Event-driven | When `uds trace <doip-uri>` is invoked, the system shall perform routing activation and a DiagnosticSessionControl + TesterPresent exchange, emitting the transactions as canonical events. |
| `REQ-DOIP-05` | State-driven | While a `uds scan` / `uds trace` target is a DoIP URI, the system shall apply the active-transmit safety model (preflight warning, `--ack-active`, `[safety].require_active_ack`, `YES` confirmation) before opening any socket. |
| `REQ-DOIP-06` | Unwanted behaviour | If the DoIP target is malformed, missing `logical_address`, or carries an out-of-range field, the system shall return a structured error with code `DOIP_INVALID_TARGET` and exit code 1. |
| `REQ-DOIP-07` | Unwanted behaviour | If the endpoint is unreachable or the connection drops, the system shall return `DOIP_CONNECTION_FAILED`; if a response does not arrive within the timeout, it shall return `DOIP_TIMEOUT`; both exit code 2. |
| `REQ-DOIP-08` | Unwanted behaviour | If routing activation is denied, a diagnostic message is negatively acknowledged, or a malformed DoIP message is received, the system shall return `DOIP_ROUTING_ACTIVATION_DENIED`, `DOIP_DIAGNOSTIC_NACK`, or `DOIP_PROTOCOL_ERROR` respectively, with exit code 2. |
| `REQ-DOIP-09` | Ubiquitous | The system shall surface UDS negative responses (service `0x7F`) as transaction events with `negative_response_code` / `negative_response_name`, not as transport-level errors. |
| `REQ-DOIP-10` | Unwanted behaviour | If an MCP caller passes a `doip://` interface to the `uds_scan` / `uds_trace` tools, the system shall refuse it with code `DOIP_MCP_EXCLUDED`; DoIP active network egress is a CLI-only operator action. |

## Command Surface

```text
canarchy uds scan  doip://<host>:<port>?logical_address=0x0E80 [--ack-active] [--json|--jsonl|--text]
canarchy uds trace doip://<host>:<port>?logical_address=0x0E80 [--ack-active] [--json|--jsonl|--text]
```

Target URI query parameters:

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `logical_address` (or `target_address`) | required | 16-bit ECU logical address |
| `source_address` | `0x0E00` | tester (client) logical address |
| `activation_type` | `0x00` | routing-activation type |
| `timeout` | `2.0` | per-response socket timeout in seconds |

Port defaults to `13400` when omitted.

## Wire Format (version 2)

All multi-byte integers big-endian.

```text
message = header payload
header  = protocol_version(1) inverse_version(1) payload_type(2) payload_length(4)
```

Payload types used: routing activation request (`0x0005`) / response (`0x0006`),
diagnostic message (`0x8001`), diagnostic message positive ack (`0x8002`) /
negative ack (`0x8003`). A diagnostic-message payload is
`source_address(2) target_address(2) user_data(N)`, where `user_data` is the raw
UDS PDU — DoIP frames the whole message, so there is no ISO-TP segmentation.

## Responsibilities And Boundaries

In scope:

* a pure codec (`src/canarchy/doip.py`) plus a thin framed TCP connection
* routing activation and diagnostic-message exchange over UDP-free TCP
* DoIP-routed `uds scan` (session enumeration) and `uds trace` (session +
  tester-present), reusing `UdsTransactionEvent` and its enrichment
* active-transmit safety on both DoIP-routed workflows

Out of scope (v1):

* UDP vehicle-discovery / announcement (`0x0001` / `0x0004`) and the UDP entity
  status messages — the TCP diagnostic path is the common case
* TLS-secured DoIP (port 3496) and authentication / confirmation handshakes
* a long-lived interactive DoIP session or full UDS client (read/write by
  identifier sequences); scan/trace cover discovery and liveness

## Data Model

The DoIP path emits the same `uds_transaction` events as the CAN path (see
`docs/design/uds-transaction-workflows.md`). The envelope `data` block adds
`transport: "doip"`, `host`, `port`, `logical_address`, `source_address`, and
`target`, with `mode: "active"`. `request_id` carries the tester source address
and `response_id` / `ecu_address` carry the ECU logical address.

## Output Contracts

`--json` returns the envelope with the `data` block above and an `events` array.
`--jsonl` streams the same events. `--text` renders the shared UDS transaction
table. All three are identical in shape to the CAN-backed `uds` output.

## Error Contracts

| Code | Trigger | Exit code |
|------|---------|-----------|
| `DOIP_INVALID_TARGET` | malformed URI / missing or out-of-range `logical_address` | 1 |
| `DOIP_CONNECTION_FAILED` | TCP connect refused / connection dropped | 2 |
| `DOIP_TIMEOUT` | no DoIP response within the timeout | 2 |
| `DOIP_ROUTING_ACTIVATION_DENIED` | routing activation response code != `0x10` | 2 |
| `DOIP_DIAGNOSTIC_NACK` | gateway returned a diagnostic-message negative ack | 2 |
| `DOIP_PROTOCOL_ERROR` | malformed header / payload / generic negative ack | 2 |
| `DOIP_MCP_EXCLUDED` | `doip://` target passed to the MCP `uds_scan` / `uds_trace` tools | n/a (MCP refusal envelope) |

A per-probe read timeout during `uds scan` is treated as a silent ECU and that
probe is skipped, not raised — only an initial/total failure surfaces as an
error.

## Deferred Decisions

* UDP vehicle discovery to enumerate logical addresses automatically.
* Whether DoIP warrants its own top-level `canarchy doip` command group if the
  workflow set grows beyond scan/trace.
