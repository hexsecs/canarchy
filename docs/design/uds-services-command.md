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

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-UDS-SVC-01` | Ubiquitous | The system shall provide a `canarchy uds services` command. |
| `REQ-UDS-SVC-02` | Event-driven | When `uds services` is invoked, the system shall return a stable catalogue of UDS services including service identifier, name, positive-response service identifier, category, and subfunction requirements. |
| `REQ-UDS-SVC-03` | Ubiquitous | The `uds services` command shall require no transport interface or live bus connection. |
| `REQ-UDS-SVC-04` | Ubiquitous | The command shall support standard CANarchy output modes with protocol-aware text output. |

## Command Surface

```text
canarchy uds services [--json] [--jsonl] [--text]
```

## Responsibilities And Boundaries

In scope:

* stable UDS service catalogue output
* mapping service identifiers to names and positive-response identifiers
* lightweight protocol metadata for operator reference

Out of scope:

* ECU-specific service discovery
* negative-response code catalogues
* live probing or transport interaction

## Data Model

Each catalogue entry includes:

* `service`
* `name`
* `positive_response_service`
* `category`
* `requires_subfunction`

## Output Contracts

### JSON and JSONL

Because `uds services` is reference-only and does not emit an event stream, both `--json` and `--jsonl` return a single CANarchy result object with `service_count` and `services` under `data`.

### Table

Text output presents a compact service catalogue with service identifier, positive-response identifier, category, and subfunction requirement.

## Error Contracts

This command has no command-specific error cases beyond standard CLI usage errors because it is reference-only and requires no external inputs.

## Deferred Decisions

* negative-response code reference output
* extended service metadata beyond the initial curated catalogue
* OEM or profile-specific service overlays
