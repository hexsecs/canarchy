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

| ID | Requirement |
|----|-------------|
| `REQ-J1939-01` | The system shall provide a `j1939 spn` command for SPN-first inspection over capture files. |
| `REQ-J1939-02` | The system shall provide a `j1939 tp` command for transport-protocol session summaries over capture files. |
| `REQ-J1939-03` | The system shall provide a `j1939 dm1` command for DM1 inspection over capture files. |
| `REQ-J1939-04` | `j1939 spn` shall decode supported SPNs into structured observations with protocol-relevant fields. |
| `REQ-J1939-05` | `j1939 tp` shall summarize BAM-based TP sessions including reassembled payload data. |
| `REQ-J1939-06` | `j1939 dm1` shall parse direct and TP-reassembled DM1 messages into structured fault content. |
| `REQ-J1939-07` | The expanded J1939 commands shall preserve PGN/SPN-first output rather than raw-ID-only views. |
| `REQ-J1939-08` | The commands shall return structured validation errors for unsupported SPN or missing required capture input. |

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

JSON and JSONL use standard CANarchy result envelopes with protocol-relevant fields under `data`. Table output remains protocol-first and summarizes SPN observations, TP sessions, and DM1 fault content without dropping to raw-ID-only views.

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
