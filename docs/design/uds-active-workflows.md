# Design Spec: Active UDS Diagnostic Workflows

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy uds services` (active mode), `uds subservices`, `uds ecu-reset`, `uds tester-present`, `uds security-seed`, `uds dump-dids`, `uds read-memory`, `uds auto` |
| Primary area | CLI, protocol, safety |
| Related specs | `docs/design/uds-transaction-workflows.md`, `docs/design/uds-services-command.md`, `docs/design/active-transmit-safety.md`, `docs/design/mcp-server.md` |
| Issues | #462, #463, #466 |

## Goal

Provide safe, structured, CLI-first **active** UDS workflows — service and
subfunction enumeration, ECU reset, TesterPresent, SecurityAccess seed
collection, DID dumping, memory reads, and a bounded zero-knowledge
reconnaissance chain — matching CaringCaribou's UDS modes (`services`,
`subservices`, `ecu_reset`, `testerpresent`, `security_seed`, `dump_dids`,
`read_mem`, `auto`) while preserving CANarchy's structured-event envelope and
active-transmit safety model.

## User-Facing Motivation

CANarchy already exposes passive UDS scan/trace and a reference service catalog,
but lacks the higher-level active workflows operators need for zero-knowledge
ECU diagnostic reconnaissance and follow-on testing in a lab. These commands let
an operator (or an explicitly authorised agent, via the CLI) discover diagnostic
responders, enumerate what they support, and extract bounded diagnostic data —
all behind the same active-transmit acknowledgement gate used by `uds scan`.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-UDS-ACT-01` | Ubiquitous | The system shall provide active UDS workflows `services` (probe mode), `subservices`, `ecu-reset`, `tester-present`, `security-seed`, `dump-dids`, `read-memory`, and `auto`. |
| `REQ-UDS-ACT-02` | Event-driven | When an active UDS workflow is invoked against an interface, the system shall emit a preflight active-transmit warning to `stderr` before any diagnostic request is sent. |
| `REQ-UDS-ACT-03` | Optional feature | Where active acknowledgement is required, the system shall require `--ack-active` (and a `YES` confirmation when interactive) before an active UDS workflow transmits. |
| `REQ-UDS-ACT-04` | Event-driven | When `--dry-run` is supplied, the system shall emit a request plan (planned request count and first request bytes) without opening the transport or transmitting, and shall not require an interface. |
| `REQ-UDS-ACT-05` | Ubiquitous | Each active workflow shall emit `uds_transaction` events for every exchange that received a response, enriched with negative-response-code decoding. |
| `REQ-UDS-ACT-06` | Ubiquitous | Structured output shall include per-request status distinguishing `positive`, `negative` (with NRC), and `no_response`. |
| `REQ-UDS-ACT-07` | Ubiquitous | `uds services` without an interface shall continue to return the static reference catalog (`mode: reference`); with an interface it shall actively probe (`mode: active`). |
| `REQ-UDS-ACT-08` | Ubiquitous | `uds dump-dids`, `uds read-memory`, and `uds auto` shall apply conservative bounded defaults (DID `--limit`, memory `MAX_MEMORY_DUMP_BYTES`, discovery id range, `--max-duration`) so a stray invocation cannot run away on a live bus. |
| `REQ-UDS-ACT-09` | Unwanted behaviour | If an operator supplies an out-of-range or inconsistent bound (inverted range, even SecurityAccess level, oversize memory read, malformed id), the system shall return a structured error with exit code 1 before transmitting. |
| `REQ-UDS-ACT-10` | Event-driven | When `uds read-memory --output <path>` is supplied and bytes were read, the system shall write the reassembled memory bytes to the path and report `bytes_written` plus provenance (`address`, `size`, `chunk_size`, request/response ids) in the result data. |
| `REQ-UDS-ACT-11` | Event-driven | When `uds auto` is invoked, the system shall discover responders over a bounded request-id range, optionally enumerate supported services per responder, optionally probe a bounded DID range, and report scan completeness. |
| `REQ-UDS-ACT-12` | Ubiquitous | Active workflows shall compose reusable UDS primitives (single-frame request building and `reassemble_uds_pdus`) rather than duplicating protocol logic. |
| `REQ-UDS-ACT-13` | Unwanted behaviour | If the transport interface is unavailable, the system shall return a structured error with code `TRANSPORT_UNAVAILABLE` and exit code 2. |
| `REQ-UDS-ACT-14` | Ubiquitous | The active UDS workflows beyond `uds services` shall be CLI-only operator actions and shall not be exposed as MCP tools (`docs/design/mcp-server.md`). |

## Command Surface

```text
canarchy uds services [<interface>] [--request-id 0x7E0] [--response-id 0x7E8]
                      [--probe-start 0x00 --probe-end 0xFF] [--max-requests N]
                      [--timeout S] [--dry-run] [--ack-active] [--json|--jsonl|--text]
canarchy uds subservices <interface> --service 0x19 [--sub-start 0x00] [--sub-end 0xFF] ...
canarchy uds ecu-reset <interface> [--reset-type 0x01] ...
canarchy uds tester-present <interface> [--suppress] ...
canarchy uds security-seed <interface> [--level 0x01] [--session 0x03] [--count N] [--max-duration S] ...
canarchy uds dump-dids <interface> [--did-start 0xF180] [--did-end 0xF1FF] [--limit N] [--max-duration S] ...
canarchy uds read-memory <interface> --address 0x080000 --size N [--chunk-size 4]
                        [--address-bytes N] [--size-bytes N] [--output PATH] ...
canarchy uds auto <interface> [--request-start 0x7E0] [--request-end 0x7E7]
                  [--no-services] [--probe-dids --did-start 0xF190 --did-end 0xF19F --did-limit 16]
                  [--response-id ID] [--max-duration S] ...
```

## Responsibilities And Boundaries

In scope:

* single-frame ISO-TP active request/response over the shared transport `transaction()` primitive;
* response reassembly via `canarchy.uds.reassemble_uds_pdus` (single- and multi-frame);
* structured per-request classification and `uds_transaction` events;
* bounded, acknowledgement-gated active workflows with `--dry-run` plans;
* bounded memory dump with chunk planning, output file, and provenance.

Out of scope:

* transmitting ISO-TP flow-control frames for long multi-frame responses (responses are kept small and bounded; see module docstring);
* SecurityAccess key computation / unlock (seed collection only);
* writing memory or DIDs (read-only);
* DoIP transport (`docs/design/doip-diagnostic-workflows.md`).

## Data Model

The pure protocol logic lives in `canarchy.uds_active`, built around a `UdsClient`
seam (`request(request_id, response_id, payload) -> UdsExchange`). `UdsExchange`
carries the request, the single reassembled response (or `None`), a `status`
(`positive`/`negative`/`no_response`), decoded negative-response code/name, and
elapsed time. `TransportUdsClient` is the only live implementation;
`SilentUdsClient` is used when no live backend is selected so the scaffold
transport yields a faithful "no responders" result instead of misreading
unrelated traffic. Workflow functions return typed records (`ServiceProbe`,
`SubserviceProbe`, `SeedObservation`, `DidRecord`, `MemoryChunk`, `Responder`,
`AutoReport`) that serialise into the command's `data` envelope, and responded
exchanges are bridged to canonical `UdsTransactionEvent`s for the `events` list.

## Safety Model

All workflows except the reference `uds services` catalog are active-transmit
commands gated by `docs/design/active-transmit-safety.md`: a `stderr` preflight
warning, `--ack-active` plus interactive `YES` (or
`CANARCHY_MCP_NONINTERACTIVE_ACK=1` for explicitly authorised non-interactive
callers), and `--dry-run` planning. Bounds (`--limit`, `MAX_MEMORY_DUMP_BYTES`,
discovery range, `--max-duration`) keep scans from running away. Per the MCP
exclusion matrix these workflows are CLI-only operator actions.
