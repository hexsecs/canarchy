# Design Spec: Expanded J1939 Workflows

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy j1939 spn`, `j1939 tp`, `j1939 dm1` |
| Primary area | CLI, protocol |

## Goal

Expand the J1939 command surface beyond PGN-only views so operators can inspect SPN values, transport-protocol sessions, and DM1 fault traffic using protocol-aware commands.

## User-Facing Motivation

Heavy-vehicle workflows should remain PGN and SPN first rather than forcing operators back to raw 29-bit identifiers when protocol-aware views are available.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-J1939-01` | Ubiquitous | The system shall provide `j1939 spn`, `j1939 tp`, and `j1939 dm1` commands for SPN, transport-protocol, and fault-traffic inspection over capture files. |
| `REQ-J1939-02` | Event-driven | When `j1939 spn <spn> --file <file>` is invoked, the system shall decode supported SPNs into structured observations including value, units, PGN, and addressing metadata. |
| `REQ-J1939-03` | Event-driven | When `j1939 tp <file>` is invoked, the system shall summarise BAM-based transport-protocol sessions including reassembled payload data. |
| `REQ-J1939-04` | Event-driven | When `j1939 dm1 <file>` is invoked, the system shall parse direct and TP-reassembled DM1 messages into structured fault records with lamp status and DTC details. |
| `REQ-J1939-05` | Ubiquitous | J1939 command output shall present PGN and SPN identifiers rather than raw 29-bit arbitration IDs wherever protocol-aware views are available. |
| `REQ-J1939-09` | Optional feature | Where a completed `j1939 tp` payload decodes cleanly as printable ASCII text, the system shall include the decoded text alongside the raw reassembled payload and mark it as heuristic. |
| `REQ-J1939-10` | Optional feature | Where the transferred PGN is known to carry identification-style J1939 data, the system shall include a stable payload label in `j1939 tp` output without removing the raw payload bytes. |
| `REQ-J1939-06` | Unwanted behaviour | If `j1939 spn` is invoked without `--file`, the system shall return a structured error with code `CAPTURE_FILE_REQUIRED` and exit code 1. |
| `REQ-J1939-07` | Unwanted behaviour | If `j1939 spn` is invoked with a negative SPN value, the system shall return a structured error with code `INVALID_SPN` and exit code 1. |
| `REQ-J1939-08` | Unwanted behaviour | If the requested SPN is not in the curated decoder map, the system shall return a structured error with code `J1939_SPN_UNSUPPORTED` and exit code 1. |

## Command Surface

```text
canarchy j1939 spn <spn> --file <capture>
canarchy j1939 tp <capture>
canarchy j1939 dm1 <capture>
```

## Responsibilities And Boundaries

In scope:

* curated SPN decoding for the initial supported set
* BAM-oriented transport-protocol session summaries
* DM1 parsing from direct frames and TP-reassembled payloads

Out of scope:

* broad SPN database coverage
* full RTS/CTS transport control state handling
* DM message families beyond DM1

## `j1939 spn`

The initial implementation uses a curated SPN decoder map rather than a general J1939 database.

### Supported SPNs

* `110` Engine Coolant Temperature from PGN `65262`
* `190` Engine Speed from PGN `61444`

### Observation contract

Each observation includes:

* `spn`
* `name`
* `pgn`
* `source_address`
* `destination_address`
* `value`
* `units`
* `raw`
* `timestamp`

Unsupported SPNs return `J1939_SPN_UNSUPPORTED`.

## `j1939 tp`

The first implementation focuses on BAM-based transport sessions:

* TP.CM BAM on PGN `60416` / `0xEC00`
* TP.DT data transfer on PGN `60160` / `0xEB00`

### Session summary contract

Each session summary includes:

* `session_type`
* `transfer_pgn`
* `source_address`
* `destination_address`
* `total_bytes`
* `total_packets`
* `packet_count`
* `complete`
* `reassembled_data`
* `decoded_text` when a completed payload is heuristically printable ASCII
* `decoded_text_encoding` when `decoded_text` is present
* `decoded_text_heuristic` to signal that printable-text decoding is a heuristic view
* `payload_label` when the transferred PGN is known to map to an identification-style payload
* `payload_label_source` when `payload_label` is present

## `j1939 dm1`

DM1 inspection reads both:

* direct DM1 frames on PGN `65226`
* TP-reassembled DM1 payloads whose transferred PGN is `65226`

### Message contract

Each message includes:

* `source_address`
* `destination_address`
* `transport`
* `lamp_status`
* `active_dtc_count`
* `dtcs`

Each DTC includes:

* `spn`
* `name` when known from the curated SPN map
* `fmi`
* `occurrence_count`
* `conversion_method`

## Output Contracts

For `j1939 spn`, `j1939 tp`, and `j1939 dm1`, both `--json` and `--jsonl` emit a single CANarchy result object because these commands return structured observations under `data` rather than event streams. Table output remains protocol-first and summarises SPN observations, TP sessions, and DM1 fault content without dropping to raw-ID-only views. For `j1939 tp`, raw `reassembled_data` remains authoritative even when heuristic text or payload labels are present.

## Error Contracts

| Code | Trigger | Exit code |
|------|---------|-----------|
| `CAPTURE_FILE_REQUIRED` | `j1939 spn` is run without `--file` | 1 |
| `INVALID_SPN` | requested SPN is negative | 1 |
| `J1939_SPN_UNSUPPORTED` | requested SPN is not in the curated decoder map | 1 |

## Deferred Decisions

* broader SPN coverage beyond the curated starter map
* RTS/CTS state-machine detail and abort handling for TP
* additional DM messages beyond DM1
