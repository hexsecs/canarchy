# Design Spec: J1939 Map Command

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy j1939 map` |
| Primary area | CLI, protocol |
| Related specs | `docs/design/j1939-summary-command.md`, `docs/design/j1939-expanded-workflows.md`, `docs/design/j1939-bounded-analysis.md` |
| Issue | #417 (surfaced by the UTHP/TCAT review in #221) |

## Goal

Extend the existing `j1939 inventory` / `j1939 compare` machinery into an explicit network-topology view: a CMAP-style nodes/edges artifact describing the source addresses observed on the bus, their claimed identities, and the PGN relationships between them, emitted in a structure suitable for graphing and diffing.

## User-Facing Motivation

Inventory answers "which ECUs are present and what do they call themselves?" and summary answers "what is in this capture?", but neither expresses the *relationships* between nodes. Operators and tooling that want to draw or diff a bus topology need an explicit nodes/edges model — who talks, who they claim to be, and which PGNs flow between which addresses — derived purely from a passive capture.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-J1939MAP-01` | Ubiquitous | The system shall provide a `canarchy j1939 map --file <file>` command that emits a nodes/edges network map for a file-backed J1939 capture. |
| `REQ-J1939MAP-02` | Event-driven | When `j1939 map <file>` is invoked, the system shall emit one node per observed source address, carrying the source address, its resolved name, and frame count. |
| `REQ-J1939MAP-03` | Event-driven | When address-claim traffic (PGN 60928, Address Claimed) is present for a source address, the system shall decode the 64-bit J1939 NAME into its constituent fields and attach it to that node. |
| `REQ-J1939MAP-04` | Event-driven | When `j1939 map <file>` is invoked, the system shall attach the component-identification and vehicle-identification strings already extracted by inventory to the matching node. |
| `REQ-J1939MAP-05` | Event-driven | When `j1939 map <file>` is invoked, the system shall emit edges describing observed PGN flows from a source address to a destination, aggregating repeated frames into a per-(source, destination, PGN) flow with a frame count. |
| `REQ-J1939MAP-06` | Ubiquitous | PDU1 traffic addressed to the global address (0xFF) shall be reported as a broadcast edge, the same as all PDU2 traffic. |
| `REQ-J1939MAP-07` | Ubiquitous | The map shall be derived purely from the captured frames, with no active probing or address-claim solicitation. |
| `REQ-J1939MAP-08` | Optional feature | Where `--max-frames`, `--seconds`, or `--offset` is specified, the system shall build the map only from the bounded capture window. |
| `REQ-J1939MAP-09` | Unwanted behaviour | If no J1939 nodes or edges can be built from the capture window, the system shall return an empty map with a structured warning rather than an error. |
| `REQ-J1939MAP-10` | Ubiquitous | The `--json` output for `j1939 map` shall use stable field names suitable for automation. |

## Command Surface

```text
canarchy j1939 map --file <capture> [--max-frames <n>] [--seconds <n>] [--offset <n>] [--json] [--jsonl] [--text]
```

## Responsibilities And Boundaries

In scope:

* per-source-address nodes with resolved names, frame counts, and identification strings
* decoded Address Claimed NAME fields where address-claim traffic is present
* observed PGN-flow edges with unicast/broadcast destinations and frame counts
* a structured nodes/edges artifact suitable for graphing and diffing

Out of scope:

* any active probing, request transmission, or address-claim solicitation
* graph rendering or layout (the command emits structured data, not images)
* inferring logical links beyond directly observed PGN traffic
* OEM-specific identification heuristics beyond what inventory already extracts

## Data Contract

The command returns the standard CANarchy result envelope. `data` for `j1939 map` includes:

* `mode`
* `file`
* `total_frames`
* `interfaces`
* `first_timestamp`
* `last_timestamp`
* `duration_seconds`
* `j1939_frame_count`
* `node_count`
* `edge_count`
* `address_claim_count`
* `nodes`
* `edges`

Each `nodes` entry includes:

* `source_address`
* `source_address_name`
* `frame_count`
* `name` — decoded Address Claimed NAME (`null` when no claim was observed), with fields `identity_number`, `manufacturer_code`, `ecu_instance`, `function_instance`, `function`, `vehicle_system`, `vehicle_system_instance`, `industry_group`, `arbitrary_address_capable`
* `component_identifications`
* `vehicle_identifications`
* `dm1_present`

Each `edges` entry includes:

* `source_address`
* `source_address_name`
* `destination_address` (`null` for broadcast)
* `destination_address_name` (`null` for broadcast)
* `broadcast`
* `pgn`
* `pgn_label`
* `frame_count`

## Output Contracts

`--json` returns a single stable result object. `--text` presents the node and edge lists as compact operator-facing lines without dropping the structured field naming in the JSON contract.

## Deferred Decisions

* emitting a ready-to-render graph format (DOT/GraphML) in addition to nodes/edges JSON
* a dedicated `j1939 map` diff mode layered over `j1939 compare`
* surfacing TP-session relationships as a distinct edge class
