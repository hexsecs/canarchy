# Design Spec: XCP Measurement / Calibration Workflows

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy xcp scan`, `xcp info`, `xcp dump`, `xcp trace`, `xcp read`, `xcp commands` |
| Primary area | Protocol, transport, CLI |
| Related specs | `docs/design/uds-transaction-workflows.md`, `docs/design/active-transmit-safety.md` |
| Issues | #327, #467 |

## Goal

Bring XCP (Universal Measurement and Calibration Protocol, ASAM MCD-1) coverage
to the same structured-output surface used for UDS. XCP is the master/slave
protocol used for ECU calibration and measurement: the master sends Command
Transfer Objects (CTOs) and the slave answers and streams measured values as
Data Transfer Objects (DTOs). CANarchy speaks enough of the XCP-on-CAN command
layer to discover responders, pair command/response transactions from a capture,
and surface raw DAQ measurement payloads.

## User-Facing Motivation

Calibration/measurement tooling (Caring Caribou, vendor MC tools) treats XCP as
first-class, but CANarchy previously had no XCP awareness. Analysts working a
bus that carries XCP traffic could only see raw frames. These workflows let them
discover XCP slaves, read command/response exchanges with named commands and
error codes, and extract DAQ measurement payloads — all through the canonical
JSON/JSONL envelope.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-XCP-01` | Ubiquitous | The system shall provide a pure parser that maps CAN frames to XCP command/response transactions and DAQ measurement events, naming commands and error codes from a bundled catalog and opening no live hardware. |
| `REQ-XCP-02` | Event-driven | When `xcp scan <interface>` is invoked, the system shall transmit an XCP CONNECT command on the request id and report each CTO response on the response id as a transaction, parsing CONNECT positive responses into resource / max-CTO / max-DTO / version fields. |
| `REQ-XCP-03` | Event-driven | When `xcp trace <interface>` is invoked, the system shall pair command CTOs on the request id with the following response CTOs on the response id, emitting named transactions with positive/error status. |
| `REQ-XCP-04` | Event-driven | When `xcp read <interface>` is invoked, the system shall surface DAQ DTOs on the response id (packet identifier 0x00–0xFB) as raw measurement events, skipping CTO response/error/event/service frames. |
| `REQ-XCP-05` | Ubiquitous | `xcp scan` shall be an active-transmit command honouring the active-transmit safety model (`--ack-active`, `[safety].require_active_ack`, `YES` confirmation); `xcp trace`, `xcp read`, and `xcp commands` shall be passive/reference. |
| `REQ-XCP-05a` | Optional feature | Where `xcp scan --dry-run` is specified, the system shall report the planned CONNECT frame (`planned_frame`, `mode: dry_run`) without opening the transport or transmitting. |
| `REQ-XCP-06` | Optional feature | Where `--request-id` / `--response-id` are supplied, the system shall use those CAN ids; otherwise it shall default to 0x3E0 (request) and 0x3E1 (response). |
| `REQ-XCP-07` | Unwanted behaviour | If a supplied request/response id is not a valid CAN id, the system shall return a structured error with code `XCP_INVALID_ID` and exit code 1. |
| `REQ-XCP-08` | State-driven | While the scaffold transport backend is active, the system shall return deterministic sample XCP transactions/measurements instead of opening a live interface. |
| `REQ-XCP-09` | Ubiquitous | `xcp scan`, `xcp trace`, `xcp read`, and `xcp commands` shall be exposed as MCP tools (`xcp_scan`, `xcp_trace`, `xcp_read`, `xcp_commands`); the active `xcp_scan` tool shall be in `_ACTIVE_TRANSMIT_TOOLS` with a mandatory `ack_active=true` and `dry_run` defaulting to true. |
| `REQ-XCP-10` | Event-driven | When `xcp info <interface>` is invoked, the system shall CONNECT to the request/response id pair and report the slave's basic capabilities, additionally querying the optional GET_STATUS, GET_COMM_MODE_INFO, and GET_ID commands. |
| `REQ-XCP-11` | Event-driven | When `xcp dump <interface> --address --size` is invoked, the system shall CONNECT and upload the address range in `--chunk-size` chunks via SET_MTA + UPLOAD (or SHORT_UPLOAD with `--short-upload`), supporting an `--output` file and reporting `bytes_read` / `complete` progress metadata. |
| `REQ-XCP-12` | Ubiquitous | `xcp info` and `xcp dump` shall be active-transmit commands honouring the active-transmit safety model with `--dry-run` request plans that need no interface, and shall apply strict bounds (`MAX_DUMP_BYTES`, chunk size ≤ MAX_CTO-1). |
| `REQ-XCP-13` | Unwanted behaviour | `xcp info` / `xcp dump` errors shall distinguish no response (`XCP_NO_RESPONSE`), protocol error responses (`XCP_ERROR_RESPONSE`), unsupported optional commands (reported per-command as `status: unsupported`), bounds validation (`XCP_INVALID_VALUE` / `XCP_DUMP_TOO_LARGE` / `XCP_INVALID_CHUNK_SIZE`, exit 1), and transport failures (`TRANSPORT_UNAVAILABLE`, exit 2). |
| `REQ-XCP-14` | Ubiquitous | `xcp info` and `xcp dump` shall be CLI-only operator actions and shall not be exposed as MCP tools. |

## Command Surface

```text
canarchy xcp scan  <interface> [--request-id 0x3E0] [--response-id 0x3E1] [--ack-active] [--dry-run] [--json|--jsonl|--text]
canarchy xcp info  <interface> [--request-id 0x3E0] [--response-id 0x3E1] [--timeout S] [--ack-active] [--dry-run] [--json|--jsonl|--text]
canarchy xcp dump  <interface> --address 0x08000000 --size N [--chunk-size 4] [--address-extension 0x00]
                   [--short-upload] [--output PATH] [--timeout S] [--ack-active] [--dry-run] [--json|--jsonl|--text]
canarchy xcp trace <interface> [--request-id 0x3E0] [--response-id 0x3E1] [--json|--jsonl|--text]
canarchy xcp read  <interface> [--response-id 0x3E1] [--json|--jsonl|--text]
canarchy xcp commands [--json|--jsonl|--text]
```

`xcp info` and `xcp dump` are implemented in `src/canarchy/xcp_active.py` on a
small `XcpClient` seam ("send one CTO, observe at most one response CTO"), so the
workflow logic is unit-tested with an in-memory fake and only `TransportXcpClient`
touches live hardware. `info` reports `capabilities` (connect / status /
comm_mode / identification); `dump` reports per-chunk records plus the assembled
`memory` hex and `complete` flag, and writes `--output` when bytes were read.

## Wire Model (XCP-on-CAN)

A CTO's first byte is the command code (request) or the response packet
identifier (`0xFF` positive, `0xFE` error, `0xFD` event, `0xFC` service). A DTO's
first byte is the packet identifier (ODT number, `0x00`–`0xFB`) followed by raw
measurement bytes. The CONNECT positive response carries `resource`,
`comm_mode_basic`, `max_cto`, `max_dto`, and the protocol/transport layer
versions. Real deployments configure the request/response CAN ids per slave in
the A2L; CANarchy defaults to 0x3E0 / 0x3E1 and lets the operator override them.

## Data Model

`xcp scan` / `xcp trace` emit `xcp_transaction` events (`command`,
`command_name`, `positive`, `error_code`/`error_name`, `connect_info`,
`request_data`, `response_data`, `request_id`, `response_id`). `xcp read` emits
`xcp_measurement` events (`pid`, `data`, `response_id`). `xcp commands` returns
the command catalog (code, name, category). Envelope `data` reports `mode`
(`active` for scan, `passive` for trace/read, `reference` for commands), the
resolved ids, and a count field.

## Output Contracts

`--json` returns the envelope with the `data` block and an `events` array;
`--jsonl` streams the events; `--text` renders an XCP table (responder/
transaction/measurement summaries). All three are shape-consistent with the UDS
output.

## Error Contracts

| Code | Trigger | Exit code |
|------|---------|-----------|
| `XCP_INVALID_ID` | `--request-id` / `--response-id` not a valid CAN id | 1 |
| `XCP_INVALID_VALUE` | `xcp dump` address/size/extension out of range | 1 |
| `XCP_DUMP_TOO_LARGE` | `xcp dump --size` over `MAX_DUMP_BYTES` (65536) | 1 |
| `XCP_INVALID_CHUNK_SIZE` | `xcp dump --chunk-size` outside 1–7 | 1 |
| `XCP_CHUNK_EXCEEDS_MAX_CTO` | chunk size larger than the slave's MAX_CTO-1 | 1 |
| `XCP_NO_RESPONSE` | `xcp info` / `xcp dump` got no CONNECT response | 2 |
| `XCP_ERROR_RESPONSE` | the slave rejected CONNECT | 2 |
| `ACTIVE_ACK_REQUIRED` | active `xcp` command without `--ack-active` while `[safety].require_active_ack` is set | 1 |
| `INTERFACE_REQUIRED` | no interface and no configured default | 1 |

## Responsibilities And Boundaries

In scope: the XCP-on-CAN command parser, scan/trace/read/commands workflows
through the standard transport, active-transmit safety on scan/info/dump, the
active `info` capability queries, and bounded `dump` memory upload.

Out of scope (v1): XCP-on-Ethernet (UDP/TCP) and XCP-on-USB transports; A2L-based
signal decoding of DAQ payloads (raw ODT bytes only); active DAQ configuration
(ALLOC_DAQ / SET_DAQ_PTR sequences) or calibration writes; seed/key unlock flows;
memory *writes* (`dump` is read-only). The active `info`/`dump` workflows are
CLI-only operator actions (not MCP tools); `dump` uploads a bounded range only.

## Deferred Decisions

* XCP-on-Ethernet transport (pairs conceptually with the DoIP transport work).
* A2L ingestion to decode DAQ ODT entries into named, scaled signals.
