# Design Spec: `uds services` Command

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy uds services` |
| Primary area | CLI, protocol |

## Goal

Provide a deterministic UDS service reference from the CLI so operators and agents can inspect commonly used service identifiers without needing a live trace or external documentation.

## User-Facing Motivation

UDS workflows are easier to script and reason about when the command surface includes a protocol-first reference view of known services, names, and expected positive-response identifiers.

## Requirements

| ID | Requirement |
|----|-------------|
| `REQ-UDS-SVC-01` | The system shall provide a `canarchy uds services` command. |
| `REQ-UDS-SVC-02` | The command shall return a stable catalog of known UDS services with names and service identifiers. |
| `REQ-UDS-SVC-03` | The command shall include protocol-relevant metadata for each service, including positive-response service identifier and subfunction expectations. |
| `REQ-UDS-SVC-04` | The command shall remain reference-only and shall not require a transport interface or live bus activity. |
| `REQ-UDS-SVC-05` | The command shall support standard CANarchy output modes with protocol-aware table output. |

## Command Surface

```text
canarchy uds services [--json] [--jsonl] [--table] [--raw]
```

## Responsibilities And Boundaries

In scope:

* stable UDS service catalog output
* mapping service identifiers to names and positive-response identifiers
* lightweight protocol metadata for operator reference

Out of scope:

* ECU-specific service discovery
* negative-response code catalogs
* live probing or transport interaction

## Data Model

Each catalog entry includes:

* `service`
* `name`
* `positive_response_service`
* `category`
* `requires_subfunction`

## Output Contracts

### JSON and JSONL

Because `uds services` is reference-only and does not emit an event stream, both `--json` and `--jsonl` return a single CANarchy result object with `service_count` and `services` under `data`.

### Table

Table output presents a compact service catalog with service identifier, positive-response identifier, category, and subfunction requirement.

### Raw

Raw output emits the command name on success.

## Error Contracts

This command has no command-specific error cases beyond standard CLI usage errors because it is reference-only and requires no external inputs.

## Deferred Decisions

* negative-response code reference output
* extended service metadata beyond the initial curated catalog
* OEM or profile-specific service overlays
